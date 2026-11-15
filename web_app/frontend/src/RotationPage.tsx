import { useEffect, useMemo, useRef, useState, MouseEvent } from "react";
import { Notify, formatNumber, formatPercent, getErrorMessage, request, requestFormData, today, trendClass } from "./api";

// 行业轮动: sector data (Tushare / CSV / demo) and the cross-sectional rotation backtest
// (rank sectors by a factor, hold the top N with equal weights, rebalance weekly, compare with the equal-weight basket).

type Universe = {
  universe: string;
  name: string;
  sectors: number;
  days: number;
  first_date: string;
  last_date: string;
  has_flow: boolean;
  has_float_mv: boolean;
  source: string;
};
type SyncJob = {
  job_id: string;
  status: "running" | "done" | "cancelled" | "error";
  provider: "tushare" | "demo";
  total: number;
  done: number;
  current_date: string;
  rows: number;
  error: string | null;
};
type Factor = { id: string; name: string; needs: string[] };
type Status = { universes: Universe[]; tushare_token_hint: string; job: SyncJob | null; factors: Factor[] };
type Metrics = {
  total_return: number;
  annualized_return: number | null;
  volatility: number | null;
  sharpe: number | null;
  max_drawdown: number;
  calmar: number | null;
  excess_annualized?: number | null;
  rebalances?: number;
  avg_turnover?: number | null;
};
type Rebalance = { signal_date: string; trade_date: string; holdings: { code: string; score: number }[]; turnover: number };
type Run = {
  window: number;
  nav: number[];
  metrics: Metrics;
  yearly: { year: string; strategy: number; benchmark: number | null; excess: number | null }[];
  rebalances: Rebalance[];
};
type Result = {
  universe: string;
  factor: string;
  factor_name: string;
  top_n: number;
  frequency: "weekly" | "monthly";
  days: string[];
  names: Record<string, string>;
  benchmark_nav: number[];
  benchmark_metrics: Metrics;
  average: Partial<Metrics>;
  runs: Run[];
};

const SOURCE_LABELS: Record<string, string> = { tushare: "Tushare", csv: "CSV 导入", demo: "演示" };
const LINE_COLORS = ["#1e3a5f", "#c8322b", "#b7791f", "#127a55", "#7c5cc4", "#0e7490", "#be185d", "#4d7c0f", "#9a3412", "#475569"];

export function RotationPage({ token, isAdmin, notify }: { token: string; isAdmin: boolean; notify: Notify }) {
  const [status, setStatus] = useState<Status | null>(null);
  const [universe, setUniverse] = useState("");
  const [factor, setFactor] = useState("net_active_buy");
  const [windows, setWindows] = useState("20, 21, 22, 23, 24");
  const [topN, setTopN] = useState("5");
  const [frequency, setFrequency] = useState<"weekly" | "monthly">("weekly");
  const [fee, setFee] = useState("0");
  const [start, setStart] = useState("2018-12-31");
  const [end, setEnd] = useState("");
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<Result | null>(null);
  const [picked, setPicked] = useState(0);

  function apply(next: Status) {
    setStatus(next);
    setUniverse((current) => (next.universes.some((u) => u.universe === current) ? current : next.universes[0]?.universe || ""));
  }

  async function reload() {
    try {
      apply(await request<Status>("/sectors", {}, token));
    } catch (error) {
      notify("error", `读取行业数据失败：${getErrorMessage(error)}`);
    }
  }

  useEffect(() => {
    reload();
  }, [token]);

  const chosen = status?.universes.find((u) => u.universe === universe);
  const factorInfo = status?.factors.find((f) => f.id === factor);
  const missing = chosen && factorInfo ? factorInfo.needs.filter((f) => ((f === "buy_amount" || f === "sell_amount") && !chosen.has_flow) || (f === "float_mv" && !chosen.has_float_mv)) : [];
  const windowList = Array.from(new Set(windows.split(/[\s,，、]+/).map(Number).filter((w) => Number.isInteger(w) && w > 0)));

  async function run() {
    if (!chosen) return;
    setRunning(true);
    try {
      const body = {
        universe,
        factor,
        windows: windowList,
        top_n: Number(topN),
        frequency,
        fee_rate: Number(fee) / 100,
        start_date: start || null,
        end_date: end || null,
      };
      const next = await request<Result>("/sectors/backtest", { method: "POST", body: JSON.stringify(body) }, token);
      setResult(next);
      setPicked(0);
    } catch (error) {
      notify("error", `回测失败：${getErrorMessage(error)}`);
    } finally {
      setRunning(false);
    }
  }

  if (!status) return <div className="page-pad muted">正在读取…</div>;

  return (
    <div className="page-pad rotation">
      <DataPanel token={token} isAdmin={isAdmin} status={status} apply={apply} reload={reload} notify={notify} />

      <section className="batch-setup">
        <div className="paper-head">
          <h3 className="section-title">轮动回测</h3>
          <span className="muted small">每期末按因子给行业打分，持有得分最高的几个，等权；下一个交易日收盘换仓；基准是全部行业等权</span>
        </div>
        {status.universes.length === 0 ? (
          <p className="muted">还没有行业数据。{isAdmin ? "先在上面同步或导入；想先看看效果，可以生成一份演示数据。" : "请管理员先同步或导入行业数据。"}</p>
        ) : (
          <div className="paper-form rotation-form">
            <label>
              行业集合
              <select value={universe} onChange={(e) => setUniverse(e.target.value)}>
                {status.universes.map((u) => (
                  <option key={u.universe} value={u.universe}>
                    {u.name}（{u.sectors} 个行业）
                  </option>
                ))}
              </select>
            </label>
            <label className="span-2">
              因子
              <select value={factor} onChange={(e) => setFactor(e.target.value)}>
                {status.factors.map((f) => (
                  <option key={f.id} value={f.id}>
                    {f.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              回看窗口 W（交易日，可填多个）
              <input value={windows} onChange={(e) => setWindows(e.target.value)} placeholder="20, 21, 22, 23, 24" />
            </label>
            <label>
              持有行业数
              <input type="number" min={1} max={chosen?.sectors || 50} value={topN} onChange={(e) => setTopN(e.target.value)} />
            </label>
            <label>
              调仓频率
              <select value={frequency} onChange={(e) => setFrequency(e.target.value as "weekly" | "monthly")}>
                <option value="weekly">每周</option>
                <option value="monthly">每月</option>
              </select>
            </label>
            <label>
              开始日期
              <input type="date" value={start} onChange={(e) => setStart(e.target.value)} />
            </label>
            <label>
              结束日期（留空 = 到最新）
              <input type="date" value={end} onChange={(e) => setEnd(e.target.value)} />
            </label>
            <label>
              单边费率（%）
              <input type="number" min={0} max={5} step={0.01} value={fee} onChange={(e) => setFee(e.target.value)} />
            </label>
            <div className="wide paper-form-foot">
              <button className="button primary" disabled={running || !chosen || windowList.length === 0 || windowList.length > 10 || !(Number(topN) >= 1) || missing.length > 0} onClick={run}>
                {running ? "回测中…" : "运行回测"}
              </button>
              {missing.length > 0 && <span className="danger-text small">这份数据没有{missing.includes("float_mv") ? "流通市值" : "主动买入 / 卖出额"}，这个因子算不了，换一个因子或换数据。</span>}
              {windowList.length > 10 && <span className="danger-text small">一次最多 10 个窗口。</span>}
              {chosen && missing.length === 0 && (
                <span className="muted small">
                  数据 {chosen.first_date} 至 {chosen.last_date}；开始日期前要留出至少 W 个交易日给因子预热。
                </span>
              )}
            </div>
          </div>
        )}
      </section>

      {result && <ResultView result={result} picked={Math.min(picked, result.runs.length - 1)} onPick={setPicked} />}
    </div>
  );
}

// --------------------------------------------------------------------------- data

function DataPanel({ token, isAdmin, status, apply, reload, notify }: { token: string; isAdmin: boolean; status: Status; apply: (s: Status) => void; reload: () => void; notify: Notify }) {
  const [job, setJob] = useState<SyncJob | null>(status.job);
  const [secret, setSecret] = useState("");
  const [provider, setProvider] = useState<"tushare" | "demo">(status.tushare_token_hint ? "tushare" : "demo");
  const [start, setStart] = useState("2018-06-01");
  const [csvName, setCsvName] = useState("wind");
  const [busy, setBusy] = useState("");
  const fileInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (job?.status !== "running") return;
    const timer = window.setInterval(async () => {
      try {
        const next = (await request<{ job: SyncJob | null }>("/sectors/sync", {}, token)).job;
        setJob(next);
        if (next && next.status !== "running") {
          reload();
          if (next.status === "done") notify("success", `行业数据同步完成，写入 ${formatNumber(next.rows, 0)} 行。`);
          if (next.status === "error") notify("error", `行业数据同步出错：${next.error}`);
        }
      } catch {
        /* keep polling */
      }
    }, 1000);
    return () => window.clearInterval(timer);
  }, [job?.job_id, job?.status, token]);

  async function act(name: string, work: () => Promise<void>) {
    setBusy(name);
    try {
      await work();
    } catch (error) {
      notify("error", getErrorMessage(error));
    } finally {
      setBusy("");
    }
  }

  const saveToken = () =>
    act("token", async () => {
      apply(await request<Status>("/sectors/credentials", { method: "PUT", body: JSON.stringify({ provider: "tushare", secret: secret.trim() }) }, token));
      setSecret("");
      setProvider("tushare");
      notify("success", "Tushare token 已保存在本机数据库里。");
    });

  const startSync = () =>
    act("sync", async () => {
      const body = { provider, start_date: start, end_date: today() };
      setJob((await request<{ job: SyncJob }>("/sectors/sync", { method: "POST", body: JSON.stringify(body) }, token)).job);
    });

  const cancel = () =>
    act("cancel", async () => {
      if (job) setJob((await request<{ job: SyncJob }>(`/sectors/sync/${job.job_id}/cancel`, { method: "POST" }, token)).job);
    });

  const upload = (file: File) =>
    act("csv", async () => {
      const data = new FormData();
      data.append("universe", csvName.trim());
      data.append("file", file);
      const next = await requestFormData<Status & { imported: number }>("/sectors/import-csv", data, token);
      apply(next);
      notify("success", `已导入 ${formatNumber(next.imported, 0)} 行到「${csvName.trim()}」。`);
    });

  const remove = (u: Universe) =>
    act("delete", async () => {
      if (!window.confirm(`删除「${u.name}」的全部 ${u.days} 天行业数据？`)) return;
      apply(await request<Status>(`/sectors/${encodeURIComponent(u.universe)}`, { method: "DELETE" }, token));
    });

  const running = job?.status === "running";

  return (
    <section className="batch-setup">
      <div className="paper-head">
        <h3 className="section-title">行业数据</h3>
        <span className="muted small">存在本机数据库里，同步一次以后只补新的交易日</span>
      </div>

      {status.universes.length > 0 && (
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>行业集合</th>
                <th>来源</th>
                <th className="num">行业数</th>
                <th className="num">交易日</th>
                <th>日期范围</th>
                <th>主动买卖额</th>
                {isAdmin && <th />}
              </tr>
            </thead>
            <tbody>
              {status.universes.map((u) => (
                <tr key={u.universe}>
                  <td>
                    <strong>{u.name}</strong>
                  </td>
                  <td>{SOURCE_LABELS[u.source] || u.source}</td>
                  <td className="num">{u.sectors}</td>
                  <td className="num">{formatNumber(u.days, 0)}</td>
                  <td>
                    {u.first_date} 至 {u.last_date}
                  </td>
                  <td>{u.has_flow ? <span className="tag ok">有</span> : <span className="tag warn">没有</span>}</td>
                  {isAdmin && (
                    <td className="num">
                      <button className="button small" disabled={busy !== "" || running} onClick={() => remove(u)}>
                        删除
                      </button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {job && (
        <div className="batch-progress">
          <div className="batch-progress-head">
            <strong>{running ? "正在同步行业数据" : job.status === "cancelled" ? "同步已取消" : job.status === "error" ? "同步出错" : "同步完成"}</strong>
            <span className="muted small">
              {job.done}/{job.total} 个交易日{job.current_date ? ` · 已到 ${job.current_date}` : ""}
            </span>
            {running ? (
              <button className="button small" disabled={!isAdmin} onClick={cancel}>
                取消
              </button>
            ) : (
              <button className="button small" onClick={() => setJob(null)}>
                关闭
              </button>
            )}
          </div>
          <div className="progress-track">
            <div className="progress-fill" style={{ width: `${running ? (job.total ? Math.round((job.done / job.total) * 100) : 0) : 100}%` }} />
          </div>
          {job.error && <p className="danger-text small">{job.error}（已经存下的交易日不会丢，修好后再点同步会接着往后补）</p>}
        </div>
      )}

      {isAdmin ? (
        <div className="paper-form rotation-data">
          <label className="span-2">
            Tushare token
            <input type="password" autoComplete="off" value={secret} placeholder={status.tushare_token_hint ? `已保存（${status.tushare_token_hint}），不改就留空` : "在 tushare.pro 个人主页复制接口 TOKEN，粘贴到这里"} onChange={(e) => setSecret(e.target.value)} />
          </label>
          <div className="paper-form-foot end">
            <button className="button" disabled={busy !== "" || secret.trim().length < 8} onClick={saveToken}>
              保存 token
            </button>
          </div>
          <label>
            数据来源
            <select value={provider} onChange={(e) => setProvider(e.target.value as "tushare" | "demo")}>
              <option value="tushare">Tushare：中信 40 行业</option>
              <option value="demo">演示数据（随机生成）</option>
            </select>
          </label>
          <label>
            从哪天开始
            <input type="date" value={start} onChange={(e) => setStart(e.target.value)} />
          </label>
          <div className="paper-form-foot end">
            <button className="button primary" disabled={busy !== "" || running || !start || (provider === "tushare" && !status.tushare_token_hint)} onClick={startSync}>
              {provider === "demo" ? "生成演示数据" : "同步到今天"}
            </button>
          </div>
          <p className="wide muted small">
            {provider === "tushare"
              ? "Tushare 没有现成的行业主动买卖额，程序会按中信行业成分把个股资金流（moneyflow）加总成行业数据，行业涨跌幅按成分股流通市值加权。需要账号积分：中信行业成分 5000，个股资金流 2000。每个交易日约 1 秒，第一次同步几年的数据要半小时左右，中途可以取消，下次接着补。"
              : "演示数据是程序随机生成的 40 个行业，只用来熟悉页面，回测结果没有任何参考意义。"}
          </p>
          <label>
            导入 CSV：行业集合名字
            <input value={csvName} maxLength={40} onChange={(e) => setCsvName(e.target.value)} />
          </label>
          <div className="paper-form-foot end span-2">
            <input ref={fileInput} type="file" accept=".csv" hidden onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; if (f) upload(f); }} />
            <button className="button" disabled={busy !== "" || !csvName.trim()} onClick={() => fileInput.current?.click()}>
              {busy === "csv" ? "导入中…" : "选择 CSV 文件导入"}
            </button>
          </div>
          <p className="wide muted small">
            Wind、同花顺 iFinD、Choice 导出的行业数据可以这样导入：每行是一个行业的一天，列名 trade_date、code、name、close，可选 amount、float_mv、buy_amount、sell_amount（也认 日期、代码、名称、收盘价、成交额、流通市值、主动买入额、主动卖出额）。同一个名字再导入会覆盖相同日期。
          </p>
        </div>
      ) : (
        <p className="muted small">同步和导入行业数据需要管理员账号。</p>
      )}
    </section>
  );
}

// --------------------------------------------------------------------------- result

function ResultView({ result, picked, onPick }: { result: Result; picked: number; onPick: (i: number) => void }) {
  const run = result.runs[picked];
  const bench = result.benchmark_metrics;
  const avg = result.average;
  const many = result.runs.length > 1;
  const latest = run.rebalances[run.rebalances.length - 1];
  const recent = run.rebalances.slice(-12).reverse();
  const label = (code: string) => result.names[code] || code;

  return (
    <section className="batch-setup rotation-result">
      <div className="paper-head">
        <h3 className="section-title">
          {result.factor_name.split("（")[0]} · 前 {result.top_n} 个行业 · {result.frequency === "weekly" ? "周" : "月"}频
        </h3>
        <span className="muted small">
          {result.days[0]} 至 {result.days[result.days.length - 1]}
          {many ? ` · 下面的大数字是 ${result.runs.length} 个窗口的平均` : ""}
        </span>
      </div>

      <div className="kpi-strip">
        <Kpi label="年化收益" value={formatPercent(avg.annualized_return, true)} tone={trendClass(avg.annualized_return)} sub={`等权基准 ${formatPercent(bench.annualized_return, true)}`} />
        <Kpi label="年化超额" value={formatPercent(avg.excess_annualized, true)} tone={trendClass(avg.excess_annualized)} />
        <Kpi label="夏普" value={formatNumber(avg.sharpe)} sub={`基准 ${formatNumber(bench.sharpe)}`} />
        <Kpi label="最大回撤" value={formatPercent(avg.max_drawdown)} tone="down" sub={`基准 ${formatPercent(bench.max_drawdown)}`} />
        <Kpi label="年化波动" value={formatPercent(avg.volatility)} sub={`基准 ${formatPercent(bench.volatility)}`} />
        <Kpi label="每次换手" value={formatPercent(avg.avg_turnover)} sub={`${run.metrics.rebalances} 次调仓`} />
      </div>

      <NavChart result={result} picked={picked} />

      <div className="table-wrap tall">
        <table className={`data-table${many ? " clickable" : ""}`}>
          <thead>
            <tr>
              <th>窗口</th>
              <th className="num">年化收益</th>
              <th className="num">年化波动</th>
              <th className="num">夏普</th>
              <th className="num">最大回撤</th>
              <th className="num">卡玛</th>
              <th className="num">年化超额</th>
              <th className="num">总收益</th>
            </tr>
          </thead>
          <tbody>
            {result.runs.map((r, i) => (
              <tr key={r.window} className={many && i === picked ? "selected" : ""} onClick={() => onPick(i)}>
                <td>
                  <span className="rot-swatch" style={{ background: LINE_COLORS[i % LINE_COLORS.length] }} />W = {r.window}
                </td>
                <MetricCells m={r.metrics} />
              </tr>
            ))}
            {many && (
              <tr className="summary-row">
                <td>平均</td>
                <MetricCells m={avg} />
              </tr>
            )}
            <tr className="summary-row">
              <td>
                <span className="rot-swatch bench" />行业等权基准
              </td>
              <MetricCells m={bench} />
            </tr>
          </tbody>
        </table>
      </div>

      <div className="rotation-split">
        <div>
          <h4 className="sub-title">分年度（W = {run.window}）</h4>
          <div className="table-wrap tall">
            <table className="data-table">
              <thead>
                <tr>
                  <th>年份</th>
                  <th className="num">策略</th>
                  <th className="num">基准</th>
                  <th className="num">超额</th>
                </tr>
              </thead>
              <tbody>
                {run.yearly.map((y) => (
                  <tr key={y.year}>
                    <td>{y.year}</td>
                    <td className={`num ${trendClass(y.strategy)}`}>{formatPercent(y.strategy, true)}</td>
                    <td className={`num ${trendClass(y.benchmark)}`}>{formatPercent(y.benchmark, true)}</td>
                    <td className={`num ${trendClass(y.excess)}`}>{formatPercent(y.excess, true)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
        <div>
          <h4 className="sub-title">最近的调仓（W = {run.window}）</h4>
          {latest ? (
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>信号日</th>
                    <th>换仓日</th>
                    <th>持有行业（按得分从高到低）</th>
                    <th className="num">换手</th>
                  </tr>
                </thead>
                <tbody>
                  {recent.map((r) => (
                    <tr key={r.trade_date}>
                      <td>{r.signal_date}</td>
                      <td>{r.trade_date}</td>
                      <td>{r.holdings.map((h) => label(h.code)).join("、")}</td>
                      <td className="num">{formatPercent(r.turnover)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="muted">这段时间里一次调仓都没有：开始日期前的数据不够因子预热，或者区间太短。</p>
          )}
        </div>
      </div>
    </section>
  );
}

function MetricCells({ m }: { m: Partial<Metrics> }) {
  return (
    <>
      <td className={`num ${trendClass(m.annualized_return)}`}>{formatPercent(m.annualized_return, true)}</td>
      <td className="num">{formatPercent(m.volatility)}</td>
      <td className="num">{formatNumber(m.sharpe)}</td>
      <td className="num">{formatPercent(m.max_drawdown)}</td>
      <td className="num">{formatNumber(m.calmar)}</td>
      <td className={`num ${trendClass(m.excess_annualized)}`}>{m.excess_annualized === undefined ? "" : formatPercent(m.excess_annualized, true)}</td>
      <td className={`num ${trendClass(m.total_return)}`}>{formatPercent(m.total_return, true)}</td>
    </>
  );
}

function Kpi({ label, value, tone, sub }: { label: string; value: string; tone?: string; sub?: string }) {
  return (
    <div className="kpi">
      <span className="kpi-label">{label}</span>
      <strong className={`kpi-value ${tone || ""}`}>{value}</strong>
      {sub && <span className="kpi-sub">{sub}</span>}
    </div>
  );
}

/** Net value of every window against the equal-weight benchmark; the picked window is drawn on top. */
function NavChart({ result, picked }: { result: Result; picked: number }) {
  const W = 1000;
  const H = 260;
  const n = result.days.length;
  const [hover, setHover] = useState<number | null>(null);
  const { lo, hi } = useMemo(() => {
    const all = [...result.benchmark_nav, ...result.runs.flatMap((r) => r.nav)];
    const min = Math.min(...all);
    const max = Math.max(...all);
    const pad = (max - min || 1) * 0.06;
    return { lo: min - pad, hi: max + pad };
  }, [result]);
  if (n < 2) return null;
  const x = (i: number) => (i / (n - 1)) * W;
  const y = (v: number) => H - ((v - lo) / (hi - lo)) * H;
  const d = (values: number[]) => values.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join("");
  function onMove(event: MouseEvent<HTMLDivElement>) {
    const rect = event.currentTarget.getBoundingClientRect();
    setHover(Math.round(Math.min(Math.max((event.clientX - rect.left) / rect.width, 0), 1) * (n - 1)));
  }
  const order = result.runs.map((_, i) => i).filter((i) => i !== picked).concat(picked);

  return (
    <div className="chart">
      <div className="chart-legend">
        {result.runs.map((r, i) => (
          <span key={r.window} className="key" style={{ color: LINE_COLORS[i % LINE_COLORS.length] }}>
            <span className="legend-text">W = {r.window}</span>
          </span>
        ))}
        <span className="key hold">行业等权基准</span>
      </div>
      <div className="chart-body">
        <div className="y-labels" style={{ height: H }}>
          <span>{formatNumber(hi)}</span>
          <span>{formatNumber(lo)}</span>
        </div>
        <div onMouseMove={onMove} onMouseLeave={() => setHover(null)}>
          <svg viewBox={`0 0 ${W} ${H}`} style={{ height: H }} preserveAspectRatio="none" role="img" aria-label="净值曲线">
            <line x1="0" x2={W} y1={y(1)} y2={y(1)} className="baseline" vectorEffect="non-scaling-stroke" />
            <path d={d(result.benchmark_nav)} className="line hold" vectorEffect="non-scaling-stroke" />
            {order.map((i) => (
              <path key={i} d={d(result.runs[i].nav)} className="line" style={{ stroke: LINE_COLORS[i % LINE_COLORS.length], opacity: i === picked ? 1 : 0.45, strokeWidth: i === picked ? 2 : 1.2 }} vectorEffect="non-scaling-stroke" />
            ))}
            {hover != null && <line x1={x(hover)} x2={x(hover)} y1="0" y2={H} className="crosshair" vectorEffect="non-scaling-stroke" />}
          </svg>
        </div>
      </div>
      <div className="x-labels">
        <span>{result.days[0]}</span>
        <span>净值，起点 = 1</span>
        <span>{result.days[n - 1]}</span>
      </div>
      {hover != null && (
        <div className="chart-tip" style={{ left: `calc(52px + (100% - 52px) * ${hover / (n - 1)})` }}>
          <strong>{result.days[hover]}</strong>
          {result.runs.map((r) => (
            <span key={r.window}>
              W={r.window} {formatNumber(r.nav[hover], 3)}
            </span>
          ))}
          <span>基准 {formatNumber(result.benchmark_nav[hover], 3)}</span>
        </div>
      )}
    </div>
  );
}
