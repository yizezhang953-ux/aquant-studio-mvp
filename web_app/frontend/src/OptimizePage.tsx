import { useEffect, useMemo, useState } from "react";
import {
  BacktestReport,
  BacktestRunResponse,
  Notify,
  StrategyJson,
  StrategyRecord,
  formatNumber,
  formatPercent,
  frequencyLabels,
  getErrorMessage,
  request,
  trendClass,
} from "./api";
import { BacktestView } from "./BacktestView";
import { OPERATORS, describeOperand } from "./RuleEditor";

// Parameter optimization: try every combination, rank on the train window only, then show how the
// same combinations did on the later test window the ranking never saw.

type Kind = "int" | "pct" | "num";
type Tunable = { path: string; label: string; current: number; kind: Kind };
type Metric = "total_return" | "annualized_return" | "sharpe" | "max_drawdown" | "win_rate";
type Method = "holdout" | "walk_forward";

type WindowMetrics = Record<string, number | null>;
type OptRow = {
  values: number[];
  is_current: boolean;
  ok: boolean;
  error: string | null;
  rank?: number;
  train: WindowMetrics;
  test: WindowMetrics;
};
type Window = { train_start: string; train_end: string; test_start: string; test_end: string };
type OptResult = {
  metric: Metric;
  parameters: { path: string; label: string }[];
  windows: Window[];
  rows: OptRow[];
  best: OptRow;
  current: OptRow | null;
  fold_selection: (Window & { fold: number; values: number[]; train_value: number | null; test_value: number | null })[];
  out_of_sample_mean: number | null;
  rank_correlation: number | null;
  verdict: { level: "good" | "caution" | "overfit"; reasons: string[]; median_test_value: number | null; best_test_value: number | null };
  candidate_count: number;
  failed_count: number;
};

const METRICS: Record<Metric, string> = {
  total_return: "总收益",
  annualized_return: "年化收益",
  sharpe: "夏普",
  max_drawdown: "最大回撤（越小越好）",
  win_rate: "胜率",
};
const VERDICTS = { good: "检验通过", caution: "需要谨慎", overfit: "疑似过拟合" };
const MAX_CANDIDATES = 200;
const MAX_PARAMS = 3;
const INDICATOR_PARAMS: Record<string, string> = { period: "周期", fast: "快线", slow: "慢线", signal: "信号", std: "倍数" };

/** Every numeric knob in the strategy that can be tuned, labelled the way the editor shows it. */
export function tunables(strategy: StrategyJson): Tunable[] {
  const out: Tunable[] = [];
  (["entry", "exit"] as const).forEach((group) => {
    const groupLabel = group === "entry" ? "买入" : "卖出";
    const conditions = strategy[group]?.conditions || [];
    conditions.forEach((condition, i) => {
      const prefix = conditions.length > 1 ? `${groupLabel}条件${i + 1}` : `${groupLabel}条件`;
      (["left", "right"] as const).forEach((side) => {
        const operand = condition[side];
        if (operand?.type === "indicator") {
          Object.entries(operand.params || {}).forEach(([key, value]) => {
            if (typeof value === "number" && INDICATOR_PARAMS[key])
              out.push({
                path: `${group}.conditions.${i}.${side}.params.${key}`,
                label: `${prefix} · ${operand.name} ${INDICATOR_PARAMS[key]}`,
                current: value,
                kind: key === "std" ? "num" : "int",
              });
          });
        } else if (operand?.type === "constant" && typeof operand.value === "number") {
          const op = OPERATORS[condition.operator || ""] || condition.operator;
          const left = condition.left?.type === "indicator" ? condition.left.name : describeOperand(condition.left);
          out.push({
            path: `${group}.conditions.${i}.${side}.value`,
            label: `${prefix} · ${left} ${op}多少`,
            current: operand.value,
            kind: Number.isInteger(operand.value) ? "int" : "num",
          });
        }
      });
    });
  });
  const extra: [string, string, number | null | undefined, Kind][] = [
    ["position.order_size_value", "每次买入仓位", strategy.position?.order_size_value, "pct"],
    ["risk.stop_loss_pct", "止损", strategy.risk?.stop_loss_pct, "pct"],
    ["risk.take_profit_pct", "止盈", strategy.risk?.take_profit_pct, "pct"],
    ["risk.max_holding_bars", "最长持有 K 线数", strategy.risk?.max_holding_bars, "int"],
  ];
  for (const [path, label, value, kind] of extra) if (typeof value === "number") out.push({ path, label, current: value, kind });
  return out;
}

const round = (value: number, digits = 4) => Number(value.toFixed(digits));

/** A starting set of values around the current one, so one click gives a sensible grid. */
export function suggestValues(item: Tunable): number[] {
  const c = item.current;
  let values: number[];
  if (item.kind === "int" && item.path.endsWith(".value")) values = [c - 10, c - 5, c, c + 5, c + 10];
  else if (item.kind === "int") values = [0.5, 0.75, 1, 1.5, 2].map((f) => Math.max(1, Math.round(c * f)));
  else if (item.kind === "pct") values = [0.5, 1, 1.5].map((f) => round(c * f));
  else values = [0.75, 1, 1.25].map((f) => round(c * f));
  return Array.from(new Set(values.filter((v) => v > 0 || (c <= 0 && v <= 0))));
}

/** "10, 14, 20" or "10-30/5" (10 to 30 every 5), mixed freely. */
export function parseValues(text: string): number[] {
  const values: number[] = [];
  for (const part of text.split(/[\s,，、;；]+/).filter(Boolean)) {
    const range = part.match(/^(-?[\d.]+)[-~～到](-?[\d.]+)\/([\d.]+)$/);
    if (range) {
      const [from, to, step] = range.slice(1).map(Number);
      if (step > 0 && to >= from && (to - from) / step <= 100) for (let v = from; v <= to + 1e-9; v += step) values.push(round(v));
    } else if (Number.isFinite(Number(part))) values.push(Number(part));
  }
  return Array.from(new Set(values));
}

function showValue(value: number | undefined, kind: Kind) {
  if (value === undefined) return "-";
  return kind === "pct" ? `${round(value * 100, 2)}%` : String(value);
}

function metricText(metric: Metric, value: number | null | undefined, signed = true) {
  if (metric === "sharpe") return formatNumber(value);
  return formatPercent(value, signed && metric !== "max_drawdown" && metric !== "win_rate");
}

export function OptimizePage({
  token,
  strategies,
  reloadStrategies,
  onBacktestSaved,
  notify,
}: {
  token: string;
  strategies: StrategyRecord[];
  reloadStrategies: () => Promise<unknown>;
  onBacktestSaved: () => void;
  notify: Notify;
}) {
  const [strategyId, setStrategyId] = useState("");
  const [picked, setPicked] = useState<Record<string, string>>({});
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [metric, setMetric] = useState<Metric>("total_return");
  const [method, setMethod] = useState<Method>("holdout");
  const [trainRatio, setTrainRatio] = useState(0.7);
  const [folds, setFolds] = useState(3);
  const [busy, setBusy] = useState("");
  const [result, setResult] = useState<OptResult | null>(null);
  const [ranWith, setRanWith] = useState<{ record: StrategyRecord; strategy: StrategyJson; items: Tunable[] } | null>(null);
  const [report, setReport] = useState<BacktestReport | null>(null);
  const [openKey, setOpenKey] = useState("");

  const strategy = strategies.find((s) => s.strategy_id === strategyId) || null;
  const items = useMemo(() => (strategy ? tunables(strategy.strategy) : []), [strategy]);
  const chosen = items.filter((item) => item.path in picked);
  const grids = chosen.map((item) => parseValues(picked[item.path]));
  const combos = grids.reduce((n, g) => n * g.length, chosen.length ? 1 : 0);

  useEffect(() => {
    if (!strategyId && strategies.length) setStrategyId(strategies[0].strategy_id);
  }, [strategies, strategyId]);

  useEffect(() => {
    // a new strategy starts with its first two knobs ticked, each with suggested values
    if (!strategy) return;
    setStart(strategy.strategy.data?.start_date || "");
    setEnd(strategy.strategy.data?.end_date || "");
    const next: Record<string, string> = {};
    for (const item of tunables(strategy.strategy).slice(0, 2)) next[item.path] = suggestValues(item).join(", ");
    setPicked(next);
  }, [strategy?.strategy_id]);

  function toggle(item: Tunable) {
    const next = { ...picked };
    if (item.path in next) delete next[item.path];
    else next[item.path] = suggestValues(item).join(", ");
    setPicked(next);
  }

  function withValues(base: StrategyJson, values: number[], params: Tunable[]): StrategyJson {
    const copy = JSON.parse(JSON.stringify(base));
    params.forEach((item, i) => {
      const parts = item.path.split(".");
      let node = copy;
      for (const part of parts.slice(0, -1)) node = node[/^\d+$/.test(part) ? Number(part) : part];
      node[parts[parts.length - 1]] = values[i];
    });
    return copy;
  }

  async function run() {
    if (!strategy) return;
    if (!start || !end || start > end) {
      notify("error", "开始日期不能晚于结束日期。");
      return;
    }
    const runStrategy = { ...strategy.strategy, data: { ...strategy.strategy.data, start_date: start, end_date: end } };
    setBusy("run");
    setReport(null);
    setOpenKey("");
    try {
      const payload = await request<OptResult>(
        "/backtests/optimize",
        {
          method: "POST",
          body: JSON.stringify({
            strategy: runStrategy,
            parameters: chosen.map((item, i) => ({ path: item.path, label: item.label, values: grids[i] })),
            metric,
            validation: method === "holdout" ? { method, train_ratio: trainRatio } : { method, folds },
          }),
        },
        token,
      );
      setResult(payload);
      setRanWith({ record: strategy, strategy: runStrategy, items: chosen });
      notify("success", `参数优化完成：试了 ${payload.candidate_count} 组参数。`);
    } catch (error) {
      notify("error", `参数优化失败：${getErrorMessage(error)}`);
    } finally {
      setBusy("");
    }
  }

  async function backtestRow(row: OptRow) {
    if (!ranWith) return;
    const key = row.values.join("|");
    setBusy(`bt:${key}`);
    try {
      const saved = await request<BacktestRunResponse>(
        "/backtests",
        {
          method: "POST",
          body: JSON.stringify({ strategy: withValues(ranWith.strategy, row.values, ranWith.items), source_strategy_id: ranWith.record.strategy_id }),
        },
        token,
      );
      setReport(await request<BacktestReport>(`/backtests/mine/${saved.backtest_id}`, {}, token));
      setOpenKey(key);
      onBacktestSaved();
      window.setTimeout(() => document.getElementById("optimize-detail")?.scrollIntoView({ behavior: "smooth", block: "start" }), 50);
      notify("success", "已用这组参数跑完整区间回测，并保存到「回测记录」。");
    } catch (error) {
      notify("error", `回测失败：${getErrorMessage(error)}`);
    } finally {
      setBusy("");
    }
  }

  async function saveVersion(row: OptRow) {
    if (!ranWith) return;
    const { record, items: params } = ranWith;
    const note = "参数优化：" + params.map((item, i) => `${item.label}=${showValue(row.values[i], item.kind)}`).join("，");
    setBusy(`save:${row.values.join("|")}`);
    try {
      // apply the values to the saved strategy as it is, keeping its own dates
      await request<StrategyRecord>(
        `/strategies/${record.strategy_id}`,
        {
          method: "PUT",
          body: JSON.stringify({ name: record.name, status: record.status, strategy: withValues(record.strategy, row.values, params), change_note: note }),
        },
        token,
      );
      await reloadStrategies();
      notify("success", `已存为「${record.name}」的新版本（${note}）。在「策略研究」里可以看到，也能回退到旧版本。`);
    } catch (error) {
      notify("error", `保存失败：${getErrorMessage(error)}`);
    } finally {
      setBusy("");
    }
  }

  if (strategies.length === 0) {
    return (
      <div className="page-pad">
        <div className="empty big">
          <h3>还没有策略</h3>
          <p>先在「策略研究」里新建并保存一个策略，再来这里优化参数。</p>
        </div>
      </div>
    );
  }

  const resultItems = ranWith?.items || [];
  const m = result?.metric || metric;
  const firstWindow = result?.windows[0];
  const lastWindow = result?.windows[result.windows.length - 1];

  return (
    <div className="page-pad batch optimize">
      <section className="batch-setup">
        <div className="batch-field">
          <span className="field-label">策略</span>
          <select value={strategyId} onChange={(e) => setStrategyId(e.target.value)}>
            {strategies.map((s) => (
              <option key={s.strategy_id} value={s.strategy_id}>
                {s.name} · {s.symbol} · {frequencyLabels[s.frequency] || s.frequency}
              </option>
            ))}
          </select>
          <span className="muted small">用的是已保存的版本；编辑器里没保存的修改不会算进来。</span>
        </div>

        <div className="batch-field">
          <span className="field-label">
            要试的参数 <span className="muted small">最多选 {MAX_PARAMS} 个</span>
          </span>
          {items.length === 0 ? (
            <p className="muted">这个策略没有可以调的数值参数。</p>
          ) : (
            <div className="opt-params">
              {items.map((item) => {
                const on = item.path in picked;
                const values = on ? parseValues(picked[item.path]) : [];
                return (
                  <div className={on ? "opt-param on" : "opt-param"} key={item.path}>
                    <label className="opt-param-name">
                      <input type="checkbox" checked={on} disabled={!on && chosen.length >= MAX_PARAMS} onChange={() => toggle(item)} />
                      <span>{item.label}</span>
                      <span className="muted small">现在 {showValue(item.current, item.kind)}</span>
                    </label>
                    {on && (
                      <div className="opt-param-values">
                        <input
                          aria-label={`${item.label} 的取值`}
                          value={picked[item.path]}
                          onChange={(e) => setPicked({ ...picked, [item.path]: e.target.value })}
                        />
                        <span className={values.length ? "muted small" : "error-text small"}>
                          {values.length ? `${values.length} 个取值` : "没有有效数值"}
                          {item.kind === "pct" ? "（0.05 表示 5%）" : ""}
                        </span>
                      </div>
                    )}
                  </div>
                );
              })}
              <span className="muted small">取值用逗号隔开，例如 10, 14, 20；也可以写 10-30/5，表示 10 到 30 每隔 5 取一个。</span>
            </div>
          )}
        </div>

        <div className="opt-row">
          <div className="batch-field">
            <span className="field-label">回测区间</span>
            <div className="batch-dates">
              <input type="date" value={start} onChange={(e) => setStart(e.target.value)} />
              <span>至</span>
              <input type="date" value={end} onChange={(e) => setEnd(e.target.value)} />
            </div>
          </div>
          <div className="batch-field">
            <span className="field-label">按什么选最优</span>
            <select value={metric} onChange={(e) => setMetric(e.target.value as Metric)}>
              {Object.entries(METRICS).map(([key, label]) => (
                <option key={key} value={key}>
                  {label}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="batch-field">
          <span className="field-label">怎么检验</span>
          <div className="segmented small">
            <button className={method === "holdout" ? "active" : ""} onClick={() => setMethod("holdout")}>
              前段选参数、后段检验
            </button>
            <button className={method === "walk_forward" ? "active" : ""} onClick={() => setMethod("walk_forward")}>
              滚动检验（更严格）
            </button>
          </div>
          {method === "holdout" ? (
            <div className="batch-dates">
              <span>前</span>
              <select value={trainRatio} onChange={(e) => setTrainRatio(Number(e.target.value))}>
                {[0.5, 0.6, 0.7, 0.8].map((r) => (
                  <option key={r} value={r}>
                    {r * 100}%
                  </option>
                ))}
              </select>
              <span className="muted small">
                的行情用来挑参数（训练段），剩下 {Math.round((1 - trainRatio) * 100)}% 留作检验段：挑参数时完全不看它，只用来检验。
              </span>
            </div>
          ) : (
            <div className="batch-dates">
              <span>切成</span>
              <select value={folds} onChange={(e) => setFolds(Number(e.target.value))}>
                {[2, 3, 4, 5].map((n) => (
                  <option key={n} value={n}>
                    {n} 段
                  </option>
                ))}
              </select>
              <span className="muted small">
                后半段行情切成 {folds} 个检验段；每段只用它之前的行情挑参数，再看挑出来的参数在这一段的表现。
              </span>
            </div>
          )}
        </div>

        <div className="batch-run">
          <button className="button primary" disabled={!strategy || combos === 0 || combos > MAX_CANDIDATES || busy !== ""} onClick={run}>
            {busy === "run" ? "优化中…" : `开始参数优化（${combos} 组）`}
          </button>
          {combos > MAX_CANDIDATES && <span className="error-text small">一次最多 {MAX_CANDIDATES} 组参数，请减少取值。</span>}
          <span className="muted small">结果不会自动保存；觉得某组好，可以「回测看看」或「存为新版本」。</span>
        </div>
      </section>

      {result && ranWith && (
        <div className="batch-results">
          <div className="batch-main">
            <div className={`opt-verdict ${result.verdict.level}`}>
              <strong>{VERDICTS[result.verdict.level]}</strong>
              <ul>
                {result.verdict.reasons.map((reason) => (
                  <li key={reason}>{reason}</li>
                ))}
              </ul>
            </div>

            <div className="kpi-strip batch-kpis">
              <div className="kpi">
                <span className="kpi-label">最优参数 · 训练段</span>
                <strong className={`kpi-value ${trendClass(result.best.train[m])}`}>{metricText(m, result.best.train[m])}</strong>
                <span className="kpi-sub">挑参数用的成绩</span>
              </div>
              <div className="kpi">
                <span className="kpi-label">最优参数 · 检验段</span>
                <strong className={`kpi-value ${trendClass(result.best.test[m])}`}>{metricText(m, result.best.test[m])}</strong>
                <span className="kpi-sub">没见过的行情，这个才算数</span>
              </div>
              <div className="kpi">
                <span className="kpi-label">当前参数 · 检验段</span>
                <strong className={`kpi-value ${trendClass(result.current?.test[m])}`}>
                  {result.current ? metricText(m, result.current.test[m]) : "-"}
                </strong>
                <span className="kpi-sub">{result.current ? `训练段 ${metricText(m, result.current.train[m])}` : "当前参数不在试的取值里"}</span>
              </div>
              <div className="kpi">
                <span className="kpi-label">检验段中位数</span>
                <strong className={`kpi-value ${trendClass(result.verdict.median_test_value)}`}>{metricText(m, result.verdict.median_test_value)}</strong>
                <span className="kpi-sub">所有参数组合的检验段成绩</span>
              </div>
              <div className="kpi">
                <span className="kpi-label">排名一致性</span>
                <strong className="kpi-value">{formatNumber(result.rank_correlation)}</strong>
                <span className="kpi-sub">1 = 训练段好的检验段也好，0 = 没关系</span>
              </div>
            </div>

            {firstWindow && lastWindow && (
              <p className="muted small">
                {result.windows.length === 1
                  ? `训练段 ${firstWindow.train_start} 至 ${firstWindow.train_end}，检验段 ${firstWindow.test_start} 至 ${firstWindow.test_end}。`
                  : `滚动检验 ${result.windows.length} 段，检验段从 ${firstWindow.test_start} 到 ${lastWindow.test_end}；表格里的训练段/检验段成绩是各段平均（交易次数是合计）。`}
                {" "}表格按训练段成绩排名；检验段那几列在挑参数时完全没用到。
              </p>
            )}

            <div className="table-wrap tall">
              <table className="data-table batch-table">
                <thead>
                  <tr>
                    <th className="num">排名</th>
                    {resultItems.map((item) => (
                      <th key={item.path}>{item.label}</th>
                    ))}
                    <th className="num">训练段 {METRICS[m].replace("（越小越好）", "")}</th>
                    <th className="num">检验段 {METRICS[m].replace("（越小越好）", "")}</th>
                    {m !== "total_return" && <th className="num">检验段 总收益</th>}
                    <th className="num">检验段 买入持有</th>
                    <th className="num">检验段 最大回撤</th>
                    <th className="num">检验段 交易</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {result.rows.map((row) => {
                    const key = row.values.join("|");
                    return (
                      <tr key={key} className={key === openKey ? "selected" : row.ok ? "" : "failed"}>
                        <td className="num">
                          {row.rank ?? "-"}
                          {row.is_current && <span className="tag">当前</span>}
                        </td>
                        {resultItems.map((item, i) => (
                          <td key={item.path}>{showValue(row.values[i], item.kind)}</td>
                        ))}
                        {row.ok ? (
                          <>
                            <td className={`num ${trendClass(row.train[m])}`}>{metricText(m, row.train[m])}</td>
                            <td className={`num ${trendClass(row.test[m])}`}>
                              <strong>{metricText(m, row.test[m])}</strong>
                            </td>
                            {m !== "total_return" && (
                              <td className={`num ${trendClass(row.test.total_return)}`}>{formatPercent(row.test.total_return, true)}</td>
                            )}
                            <td className={`num ${trendClass(row.test.benchmark_return)}`}>{formatPercent(row.test.benchmark_return, true)}</td>
                            <td className="num">{formatPercent(row.test.max_drawdown)}</td>
                            <td className="num">{formatNumber(row.test.trade_count, 0)}</td>
                            <td className="nowrap">
                              <button className="text-button" disabled={busy !== ""} onClick={() => backtestRow(row)}>
                                {busy === `bt:${key}` ? "回测中…" : "回测看看"}
                              </button>
                              {!row.is_current && (
                                <button className="text-button" disabled={busy !== ""} onClick={() => saveVersion(row)}>
                                  {busy === `save:${key}` ? "保存中…" : "存为新版本"}
                                </button>
                              )}
                            </td>
                          </>
                        ) : (
                          <td colSpan={m === "total_return" ? 6 : 7} className="muted small">
                            {row.error}
                          </td>
                        )}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {result.windows.length > 1 && (
              <>
                <h4 className="opt-subhead">
                  滚动检验：每段只用之前的行情挑参数{" "}
                  <span className="muted small">样本外平均 {metricText(m, result.out_of_sample_mean)}</span>
                </h4>
                <div className="table-wrap">
                  <table className="data-table batch-table">
                    <thead>
                      <tr>
                        <th>段</th>
                        <th>挑参数用的行情</th>
                        <th>检验段</th>
                        <th>挑出的参数</th>
                        <th className="num">训练段</th>
                        <th className="num">检验段</th>
                      </tr>
                    </thead>
                    <tbody>
                      {result.fold_selection.map((fold) => (
                        <tr key={fold.fold}>
                          <td>{fold.fold}</td>
                          <td className="nowrap">
                            {fold.train_start} 至 {fold.train_end}
                          </td>
                          <td className="nowrap">
                            {fold.test_start} 至 {fold.test_end}
                          </td>
                          <td>{resultItems.map((item, i) => `${item.label.split(" · ").pop()} ${showValue(fold.values[i], item.kind)}`).join("，")}</td>
                          <td className={`num ${trendClass(fold.train_value)}`}>{metricText(m, fold.train_value)}</td>
                          <td className={`num ${trendClass(fold.test_value)}`}>{metricText(m, fold.test_value)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            )}

            <p className="muted small">
              怎么看：参数是只用「训练段」挑的。如果第一名在「检验段」也还靠前，说明这组参数可能真有用；如果第一名到了检验段掉到一半以下，或者排名一致性接近 0 甚至为负，说明好成绩多半是把参数调到刚好贴合历史，换一段行情就不灵了。
            </p>
          </div>

          <section className="history-detail batch-detail" id="optimize-detail">
            {report ? (
              <BacktestView report={report} />
            ) : (
              <div className="empty big">
                <h3>点「回测看看」看完整报告</h3>
                <p>用那组参数跑完整区间（训练段 + 检验段），存进「回测记录」，并在这里显示收益曲线和交易明细。</p>
              </div>
            )}
          </section>
        </div>
      )}
    </div>
  );
}
