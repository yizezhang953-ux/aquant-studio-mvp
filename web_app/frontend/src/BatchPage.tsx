import { useEffect, useMemo, useState } from "react";
import {
  BacktestReport,
  BacktestRunResponse,
  MarketInstrument,
  MarketKey,
  Notify,
  StrategyRecord,
  formatNumber,
  formatPercent,
  frequencyLabels,
  getErrorMessage,
  marketLabels,
  request,
  today,
  trendClass,
} from "./api";
import { BacktestView } from "./BacktestView";

type Period = { start_date: string; end_date: string };
type PeriodMode = "whole" | "yearly" | "custom";

type BatchRow = {
  symbol: string;
  name: string;
  market: MarketKey;
  start_date: string;
  end_date: string;
  ok: boolean;
  missing_data: boolean;
  error: string | null;
  metrics: Record<string, number | null>;
  warning_count: number;
};

type BatchSummary = {
  runs: number;
  completed: number;
  failed: number;
  profitable: number;
  beat_buy_hold: number;
  mean_return: number | null;
  median_return: number | null;
  best_return: number | null;
  worst_return: number | null;
  mean_excess: number | null;
  mean_max_drawdown: number | null;
  worst_max_drawdown: number | null;
};

type SortKey = "symbol" | "period" | "total_return" | "benchmark_return" | "excess" | "annualized_return" | "max_drawdown" | "sharpe" | "win_rate" | "trade_count";

const MAX_RUNS = 120;

const excessOf = (row: BatchRow) =>
  row.metrics.total_return != null && row.metrics.benchmark_return != null ? row.metrics.total_return - row.metrics.benchmark_return : null;

function sortValue(row: BatchRow, key: SortKey): number | string | null {
  if (key === "symbol") return row.symbol;
  if (key === "period") return row.start_date;
  if (key === "excess") return excessOf(row);
  return row.metrics[key] ?? null;
}

/** Calendar years between start and end, clipped to both ends. */
export function yearlyPeriods(start: string, end: string): Period[] {
  const periods: Period[] = [];
  for (let year = Number(start.slice(0, 4)); year <= Number(end.slice(0, 4)); year++) {
    const from = year === Number(start.slice(0, 4)) ? start : `${year}-01-01`;
    const to = year === Number(end.slice(0, 4)) ? end : `${year}-12-31`;
    if (from <= to) periods.push({ start_date: from, end_date: to });
  }
  return periods;
}

function parseSymbols(text: string) {
  return text
    .split(/[\s,，、;；]+/)
    .map((s) => s.trim().toUpperCase())
    .filter(Boolean);
}

export function BatchPage({
  token,
  isAdmin,
  strategies,
  instruments,
  syncSymbol,
  onBacktestSaved,
  notify,
}: {
  token: string;
  isAdmin: boolean;
  strategies: StrategyRecord[];
  instruments: MarketInstrument[];
  syncSymbol: (symbol: string, startDate: string, endDate?: string) => Promise<boolean>;
  onBacktestSaved: () => void;
  notify: Notify;
}) {
  const [strategyId, setStrategyId] = useState("");
  const [symbolText, setSymbolText] = useState("");
  const [mode, setMode] = useState<PeriodMode>("whole");
  const [start, setStart] = useState("2021-01-01");
  const [end, setEnd] = useState(today());
  const [custom, setCustom] = useState<Period[]>([{ start_date: "2021-01-01", end_date: "2023-12-31" }, { start_date: "2024-01-01", end_date: today() }]);
  const [busy, setBusy] = useState("");
  const [rows, setRows] = useState<BatchRow[]>([]);
  const [summary, setSummary] = useState<BatchSummary | null>(null);
  const [ranWith, setRanWith] = useState<StrategyRecord | null>(null);
  const [sort, setSort] = useState<{ key: SortKey; desc: boolean }>({ key: "total_return", desc: true });
  const [report, setReport] = useState<BacktestReport | null>(null);
  const [openKey, setOpenKey] = useState("");

  const strategy = strategies.find((s) => s.strategy_id === strategyId) || null;
  const symbols = useMemo(() => Array.from(new Set(parseSymbols(symbolText))), [symbolText]);
  const periods = mode === "whole" ? [{ start_date: start, end_date: end }] : mode === "yearly" ? yearlyPeriods(start, end) : custom;
  const runs = symbols.length * periods.length;
  const withData = instruments.filter((item) => item.bar_count > 20);

  useEffect(() => {
    if (!strategyId && strategies.length) setStrategyId(strategies[0].strategy_id);
  }, [strategies, strategyId]);

  useEffect(() => {
    // start with the strategy's own stock so the first run has something to compare against
    if (strategy && !symbolText) setSymbolText(strategy.symbol);
  }, [strategy?.strategy_id]);

  const sorted = useMemo(() => {
    const list = [...rows];
    list.sort((a, b) => {
      const x = sortValue(a, sort.key);
      const y = sortValue(b, sort.key);
      if (x === null && y === null) return 0;
      if (x === null) return 1; // failed runs always at the bottom
      if (y === null) return -1;
      const order = x < y ? -1 : x > y ? 1 : 0;
      return sort.desc ? -order : order;
    });
    return list;
  }, [rows, sort]);

  function addSymbols(list: string[]) {
    setSymbolText(Array.from(new Set([...symbols, ...list])).join(" "));
  }

  async function run() {
    if (!strategy) return;
    if (periods.some((p) => !p.start_date || !p.end_date || p.start_date > p.end_date)) {
      notify("error", "有时间段的开始日期晚于结束日期，或者没填完整。");
      return;
    }
    setBusy("run");
    setReport(null);
    setOpenKey("");
    try {
      const result = await request<{ rows: BatchRow[]; summary: BatchSummary }>(
        "/backtests/batch",
        { method: "POST", body: JSON.stringify({ strategy: strategy.strategy, symbols, periods }) },
        token,
      );
      setRows(result.rows);
      setSummary(result.summary);
      setRanWith(strategy);
      const failed = result.summary.failed ? `，${result.summary.failed} 组没有跑成（见表格底部）` : "";
      notify("success", `批量回测完成：${result.summary.completed} 组${failed}。`);
    } catch (error) {
      notify("error", `批量回测失败：${getErrorMessage(error)}`);
    } finally {
      setBusy("");
    }
  }

  async function syncMissing() {
    const missing = Array.from(new Set(rows.filter((r) => r.missing_data).map((r) => r.symbol)));
    const earliest = rows.reduce((min, r) => (r.start_date < min ? r.start_date : min), today());
    setBusy("sync");
    // a year of extra history so indicators are warmed up on the first day
    const from = `${Number(earliest.slice(0, 4)) - 1}${earliest.slice(4)}`;
    for (const symbol of missing) await syncSymbol(symbol, from, today());
    setBusy("");
    notify("info", "同步完成，可以再点一次「开始批量回测」。");
  }

  async function saveAndShow(row: BatchRow) {
    if (!ranWith) return;
    const key = `${row.symbol}|${row.start_date}`;
    setBusy(key);
    const runStrategy = {
      ...ranWith.strategy,
      market: row.market,
      universe: { ...(ranWith.strategy.universe || {}), type: "single", symbols: [row.symbol] },
      data: { ...ranWith.strategy.data, start_date: row.start_date, end_date: row.end_date },
    };
    try {
      const saved = await request<BacktestRunResponse>(
        "/backtests",
        { method: "POST", body: JSON.stringify({ strategy: runStrategy, source_strategy_id: ranWith.strategy_id }) },
        token,
      );
      setReport(await request<BacktestReport>(`/backtests/mine/${saved.backtest_id}`, {}, token));
      setOpenKey(key);
      onBacktestSaved();
      window.setTimeout(() => document.getElementById("batch-detail")?.scrollIntoView({ behavior: "smooth", block: "start" }), 50);
      notify("success", `已保存到「回测记录」：${row.name} ${row.start_date} 至 ${row.end_date}。`);
    } catch (error) {
      notify("error", `保存失败：${getErrorMessage(error)}`);
    } finally {
      setBusy("");
    }
  }

  function header(key: SortKey, label: string, numeric = true) {
    const active = sort.key === key;
    return (
      <th className={`${numeric ? "num " : ""}sortable${active ? " active" : ""}`} onClick={() => setSort({ key, desc: active ? !sort.desc : true })}>
        {label}
        {active ? (sort.desc ? " ↓" : " ↑") : ""}
      </th>
    );
  }

  if (strategies.length === 0) {
    return (
      <div className="page-pad">
        <div className="empty big">
          <h3>还没有策略</h3>
          <p>先在「策略研究」里新建并保存一个策略，再来这里批量回测。</p>
        </div>
      </div>
    );
  }

  const missingCount = rows.filter((r) => r.missing_data).length;

  return (
    <div className="page-pad batch">
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
            股票 <span className="muted small">{symbols.length} 只</span>
          </span>
          <textarea
            rows={2}
            value={symbolText}
            placeholder="输入股票代码，用空格或逗号隔开，例如 00168.HK 09987.HK 600519.SH"
            onChange={(e) => setSymbolText(e.target.value.toUpperCase())}
          />
          <div className="batch-chips">
            <button className="text-button" onClick={() => addSymbols(withData.map((i) => i.symbol))} disabled={withData.length === 0}>
              加入全部已有行情的股票（{withData.length}）
            </button>
            {withData.slice(0, 12).map((item) => (
              <button
                key={item.symbol}
                className={symbols.includes(item.symbol) ? "chip on" : "chip"}
                title={`${item.symbol} · ${item.first_trade_time?.slice(0, 10)} 至 ${item.last_trade_time?.slice(0, 10)}`}
                onClick={() =>
                  symbols.includes(item.symbol)
                    ? setSymbolText(symbols.filter((s) => s !== item.symbol).join(" "))
                    : addSymbols([item.symbol])
                }
              >
                {item.name}
              </button>
            ))}
            {symbols.length > 0 && (
              <button className="text-button" onClick={() => setSymbolText("")}>
                清空
              </button>
            )}
          </div>
        </div>

        <div className="batch-field">
          <span className="field-label">时间段</span>
          <div className="segmented small">
            {(
              [
                ["whole", "整段"],
                ["yearly", "按年拆分"],
                ["custom", "自定义"],
              ] as [PeriodMode, string][]
            ).map(([key, label]) => (
              <button key={key} className={mode === key ? "active" : ""} onClick={() => setMode(key)}>
                {label}
              </button>
            ))}
          </div>
          {mode !== "custom" ? (
            <div className="batch-dates">
              <input type="date" value={start} onChange={(e) => setStart(e.target.value)} />
              <span>至</span>
              <input type="date" value={end} onChange={(e) => setEnd(e.target.value)} />
              {mode === "yearly" && <span className="muted small">拆成 {periods.length} 段，每年单独回测，看策略是不是只在某一年有效。</span>}
            </div>
          ) : (
            <div className="batch-periods">
              {custom.map((p, i) => (
                <div className="batch-dates" key={i}>
                  <input type="date" value={p.start_date} onChange={(e) => setCustom(custom.map((x, j) => (j === i ? { ...x, start_date: e.target.value } : x)))} />
                  <span>至</span>
                  <input type="date" value={p.end_date} onChange={(e) => setCustom(custom.map((x, j) => (j === i ? { ...x, end_date: e.target.value } : x)))} />
                  {custom.length > 1 && (
                    <button className="text-button danger" onClick={() => setCustom(custom.filter((_, j) => j !== i))}>
                      删除
                    </button>
                  )}
                </div>
              ))}
              {custom.length < 12 && (
                <button className="text-button" onClick={() => setCustom([...custom, { start_date: end.slice(0, 4) + "-01-01", end_date: end }])}>
                  + 添加时间段
                </button>
              )}
            </div>
          )}
        </div>

        <div className="batch-run">
          <button className="button primary" disabled={!strategy || runs === 0 || runs > MAX_RUNS || busy !== ""} onClick={run}>
            {busy === "run" ? "回测中…" : `开始批量回测（${runs} 组）`}
          </button>
          {runs > MAX_RUNS && <span className="error-text small">一次最多 {MAX_RUNS} 组，请减少股票或时间段。</span>}
          <span className="muted small">结果不会自动保存；想留下某一组，点那一行的「保存并查看」。</span>
        </div>
      </section>

      {summary && (
        <div className="batch-results">
          <div className="batch-main">
            <div className="kpi-strip batch-kpis">
              <div className="kpi">
                <span className="kpi-label">赚钱的组数</span>
                <strong className="kpi-value">
                  {summary.profitable} / {summary.completed}
                </strong>
                <span className="kpi-sub">{summary.completed ? formatPercent(summary.profitable / summary.completed) : "-"}</span>
              </div>
              <div className="kpi">
                <span className="kpi-label">跑赢买入持有</span>
                <strong className="kpi-value">
                  {summary.beat_buy_hold} / {summary.completed}
                </strong>
                <span className="kpi-sub">平均超额 {formatPercent(summary.mean_excess, true)}</span>
              </div>
              <div className="kpi">
                <span className="kpi-label">收益中位数</span>
                <strong className={`kpi-value ${trendClass(summary.median_return)}`}>{formatPercent(summary.median_return, true)}</strong>
                <span className="kpi-sub">平均 {formatPercent(summary.mean_return, true)}</span>
              </div>
              <div className="kpi">
                <span className="kpi-label">最好 / 最差</span>
                <strong className="kpi-value small-value">
                  <span className={trendClass(summary.best_return)}>{formatPercent(summary.best_return, true)}</span>
                  {" / "}
                  <span className={trendClass(summary.worst_return)}>{formatPercent(summary.worst_return, true)}</span>
                </strong>
              </div>
              <div className="kpi">
                <span className="kpi-label">平均最大回撤</span>
                <strong className="kpi-value">{formatPercent(summary.mean_max_drawdown)}</strong>
                <span className="kpi-sub">最深 {formatPercent(summary.worst_max_drawdown)}</span>
              </div>
            </div>

            {missingCount > 0 && (
              <p className="batch-missing">
                有 {missingCount} 组缺少行情。
                {isAdmin ? (
                  <button className="text-button strong" disabled={busy !== ""} onClick={syncMissing}>
                    {busy === "sync" ? "同步中…" : "一键同步缺少的股票"}
                  </button>
                ) : (
                  "请管理员先同步这些股票。"
                )}
              </p>
            )}

            <div className="table-wrap tall">
              <table className="data-table batch-table">
                <thead>
                  <tr>
                    {header("symbol", "股票", false)}
                    {header("period", "时间段", false)}
                    {header("total_return", "总收益")}
                    {header("benchmark_return", "买入持有")}
                    {header("excess", "超额")}
                    {header("annualized_return", "年化")}
                    {header("max_drawdown", "最大回撤")}
                    {header("sharpe", "夏普")}
                    {header("win_rate", "胜率")}
                    {header("trade_count", "交易")}
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {sorted.map((row) => {
                    const key = `${row.symbol}|${row.start_date}`;
                    const m = row.metrics;
                    return (
                      <tr key={key} className={key === openKey ? "selected" : row.ok ? "" : "failed"}>
                        <td>
                          <strong>{row.name}</strong>
                          <span className="cell-sub">
                            {row.symbol}
                            {ranWith && row.market !== ranWith.strategy.market ? ` · 按${marketLabels[row.market]}规则` : ""}
                          </span>
                        </td>
                        <td className="nowrap">
                          {row.start_date.slice(0, 7)} 至 {row.end_date.slice(0, 7)}
                        </td>
                        {row.ok ? (
                          <>
                            <td className={`num ${trendClass(m.total_return)}`}>{formatPercent(m.total_return, true)}</td>
                            <td className={`num ${trendClass(m.benchmark_return)}`}>{formatPercent(m.benchmark_return, true)}</td>
                            <td className={`num ${trendClass(excessOf(row))}`}>{formatPercent(excessOf(row), true)}</td>
                            <td className={`num ${trendClass(m.annualized_return)}`}>{formatPercent(m.annualized_return, true)}</td>
                            <td className="num">{formatPercent(m.max_drawdown)}</td>
                            <td className="num">{formatNumber(m.sharpe)}</td>
                            <td className="num">{m.trade_count ? formatPercent(m.win_rate) : "-"}</td>
                            <td className="num">{formatNumber(m.trade_count, 0)}</td>
                            <td>
                              <button className="text-button" disabled={busy !== ""} onClick={() => saveAndShow(row)}>
                                {busy === key ? "保存中…" : "保存并查看"}
                              </button>
                            </td>
                          </>
                        ) : (
                          <td colSpan={9} className="muted small">
                            {row.error}
                          </td>
                        )}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <p className="muted small">
              「超额」= 总收益 − 同期买入持有这只股票的收益。看一个策略靠不靠谱，主要看「赚钱的组数」和「跑赢买入持有」是不是多数，而不是最好的那一组。
            </p>
          </div>

          <section className="history-detail batch-detail" id="batch-detail">
            {report ? (
              <BacktestView report={report} />
            ) : (
              <div className="empty big">
                <h3>点「保存并查看」看完整报告</h3>
                <p>那一组会存进「回测记录」，并在这里显示收益曲线和交易明细。</p>
              </div>
            )}
          </section>
        </div>
      )}
    </div>
  );
}
