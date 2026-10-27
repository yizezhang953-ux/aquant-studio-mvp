import { useEffect, useMemo, useState } from "react";
import {
  BacktestTrade,
  EquityPoint,
  MarketInstrument,
  Notify,
  RuleGroup,
  StrategyRecord,
  formatMoney,
  formatNumber,
  formatPercent,
  getErrorMessage,
  marketLabels,
  request,
  today,
  trendClass,
} from "./api";
import { AutomationPanel } from "./AutomationPanel";
import { EquityChart } from "./charts";
import { OPERATORS, describeOperand } from "./RuleEditor";

// Daily signals (which stocks trigger a strategy on the latest close) and paper accounts
// (virtual money following a strategy from a start date, with the backtest engine's fills).

type ConditionValue = { left_value: number | null; right_value: number | null; met: boolean };
type SignalRow = {
  symbol: string;
  name: string;
  strategy_id: string | null;
  strategy_name: string;
  date: string | null;
  close: number | null;
  change: number | null;
  signal: "buy" | "sell" | "both" | null;
  error: string | null;
  stale: boolean;
  live?: boolean;
  entry_conditions?: ConditionValue[];
  exit_conditions?: ConditionValue[];
};
type ScanResult = { rows: SignalRow[]; latest_date: string | null; buy: number; sell: number; live?: boolean };

type PaperSummary = {
  equity: number;
  total_return: number;
  cash: number;
  day_change: number | null;
  hold_return: number | null;
  max_drawdown: number;
  last_date: string | null;
  positions: number;
  trades: number;
};
type PaperPosition = { symbol: string; name: string; quantity: number; entry_time: string; entry_price: number; last_close: number; market_value: number; unrealized_pnl: number; return_pct: number | null };
type PaperOrder = { symbol: string; name: string; side: "buy" | "sell"; reason: string; date: string; close: number };
type PaperSleeve = { symbol: string; name: string; status: "ok" | "waiting" | "error"; last_date: string | null; equity: number; total_return: number; hold_return: number | null; error?: string };
type PaperAccount = {
  account_id: string;
  name: string;
  strategy_name: string;
  market: string;
  currency: string;
  symbols: string[];
  initial_cash: number;
  start_date: string;
  summary: PaperSummary;
  positions: PaperPosition[];
  pending: PaperOrder[];
  curve?: EquityPoint[];
  trades?: (BacktestTrade & { name: string })[];
  sleeves?: PaperSleeve[];
};

const SIGNALS = { buy: "买入", sell: "卖出", both: "买卖同时" };

function parseSymbols(text: string) {
  return Array.from(new Set(text.split(/[\s,，、;；]+/).map((s) => s.trim().toUpperCase()).filter(Boolean)));
}

function conditionText(group: RuleGroup | undefined, values: ConditionValue[] | undefined) {
  return (group?.conditions || []).map((c, i) => {
    const v = values?.[i];
    const show = (n: number | null | undefined) => (n == null ? "无值" : formatNumber(n, 2));
    const right = c.right?.type === "constant" ? "" : `(${show(v?.right_value)})`;
    return {
      text: `${describeOperand(c.left)} ${show(v?.left_value)} ${OPERATORS[c.operator || ""] || c.operator} ${describeOperand(c.right)}${right}`,
      met: Boolean(v?.met),
    };
  });
}

export function SignalsPage({
  token,
  isAdmin,
  strategies,
  instruments,
  syncSymbols,
  notify,
}: {
  token: string;
  isAdmin: boolean;
  strategies: StrategyRecord[];
  instruments: MarketInstrument[];
  syncSymbols: (symbols: string[], startDate: string, endDate?: string) => Promise<boolean>;
  notify: Notify;
}) {
  const withData = instruments.filter((i) => i.bar_count > 20);
  const [picked, setPicked] = useState<string[]>([]);
  const [symbolText, setSymbolText] = useState("");
  const [busy, setBusy] = useState("");
  const [scan, setScan] = useState<ScanResult | null>(null);
  const [onlySignals, setOnlySignals] = useState(true);

  useEffect(() => {
    if (!picked.length && strategies.length) setPicked(strategies.slice(0, 20).map((s) => s.strategy_id));
  }, [strategies]);
  useEffect(() => {
    if (!symbolText && withData.length) setSymbolText(withData.slice(0, 100).map((i) => i.symbol).join(" "));
  }, [instruments]);

  const symbols = useMemo(() => parseSymbols(symbolText), [symbolText]);
  const chosen = strategies.filter((s) => picked.includes(s.strategy_id));
  const byId = new Map(strategies.map((s) => [s.strategy_id, s]));

  async function runScan(live = false) {
    setBusy(live ? "live" : "scan");
    try {
      const result = await request<ScanResult>(
        "/signals/scan",
        {
          method: "POST",
          body: JSON.stringify({ strategies: chosen.map((s) => ({ strategy_id: s.strategy_id, name: s.name, strategy: s.strategy })), symbols, live }),
        },
        token,
      );
      setScan({ ...result, live });
      notify("success", live ? `盘中预判完成：按现在的价格，${result.buy} 个买入信号，${result.sell} 个卖出信号。` : `扫描完成：${result.buy} 个买入信号，${result.sell} 个卖出信号（最新收盘 ${result.latest_date?.slice(0, 10) || "-"}）。`);
    } catch (error) {
      notify("error", `扫描失败：${getErrorMessage(error)}`);
    } finally {
      setBusy("");
    }
  }

  async function updateThenScan() {
    setBusy("update");
    // stocks already stored are only topped up from their last bar; new ones get three years
    await syncSymbols(symbols, `${Number(today().slice(0, 4)) - 3}-01-01`, today());
    await runScan();
  }

  const rows = (scan?.rows || []).filter((r) => !onlySignals || r.signal);

  return (
    <div className="page-pad batch signals">
      <section className="batch-setup">
        <h3 className="section-title">今日信号</h3>
        <div className="batch-field">
          <span className="field-label">
            策略 <span className="muted small">已选 {chosen.length} 个</span>
          </span>
          <div className="batch-chips">
            {strategies.map((s) => (
              <button
                key={s.strategy_id}
                className={picked.includes(s.strategy_id) ? "chip on" : "chip"}
                onClick={() => setPicked(picked.includes(s.strategy_id) ? picked.filter((x) => x !== s.strategy_id) : [...picked, s.strategy_id].slice(0, 20))}
              >
                {s.name}
              </button>
            ))}
            {strategies.length === 0 && <span className="muted">先在「策略研究」里保存一个策略。</span>}
          </div>
        </div>
        <div className="batch-field">
          <span className="field-label">
            股票 <span className="muted small">{symbols.length} 只</span>
          </span>
          <textarea rows={2} value={symbolText} placeholder="股票代码，空格或逗号隔开" onChange={(e) => setSymbolText(e.target.value.toUpperCase())} />
          <div className="batch-chips">
            <button className="text-button" onClick={() => setSymbolText(withData.slice(0, 100).map((i) => i.symbol).join(" "))}>
              用全部已有行情的股票（{withData.length}）
            </button>
          </div>
        </div>
        <div className="batch-run">
          <button className="button primary" disabled={busy !== "" || !chosen.length || !symbols.length} onClick={() => runScan()}>
            {busy === "scan" ? "扫描中…" : "扫描最新收盘"}
          </button>
          <button
            className="button"
            disabled={busy !== "" || !chosen.length || !symbols.length}
            onClick={() => runScan(true)}
            title="把现在的实时价格当作今天的收盘价来判断，收盘前看看今天会不会出信号"
          >
            {busy === "live" ? "读取实时价格…" : "盘中预判（用实时价）"}
          </button>
          {isAdmin && (
            <button className="button" disabled={busy !== "" || !chosen.length || !symbols.length} onClick={updateThenScan}>
              {busy === "update" ? "更新行情中…" : "先把行情更新到今天，再扫描"}
            </button>
          )}
          <span className="muted small">
            每天收盘后点「扫描最新收盘」：看哪些股票满足了策略的买入或卖出条件（按规则，第二天开盘成交）。交易时间里点「盘中预判」，用现在的价格先看一眼今天收盘可能出的信号。
          </span>
        </div>

        {scan && (
          <div className="signal-results">
            <div className="signal-head">
              <strong>
                {scan.live ? "按实时价格" : "最新收盘"} {scan.latest_date?.slice(0, 10) || "-"}：<span className="up">{scan.buy} 个买入</span>、<span className="down">{scan.sell} 个卖出</span>
              </strong>
              <div className="segmented small">
                <button className={onlySignals ? "active" : ""} onClick={() => setOnlySignals(true)}>
                  只看有信号的
                </button>
                <button className={!onlySignals ? "active" : ""} onClick={() => setOnlySignals(false)}>
                  全部
                </button>
              </div>
            </div>
            {rows.length === 0 ? (
              <p className="muted">今天没有股票触发信号。</p>
            ) : (
              <div className="table-wrap">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>信号</th>
                      <th>股票</th>
                      <th>策略</th>
                      <th>{scan.live ? "日期" : "收盘日"}</th>
                      <th className="num">{scan.live ? "价格" : "收盘价"}</th>
                      <th className="num">涨跌</th>
                      <th>条件（当天数值）</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((r) => {
                      const strategy = r.strategy_id ? byId.get(r.strategy_id)?.strategy : undefined;
                      const conditions = r.signal === "sell" ? conditionText(strategy?.exit, r.exit_conditions) : conditionText(strategy?.entry, r.entry_conditions);
                      return (
                        <tr key={`${r.strategy_id}|${r.symbol}`} className={r.error ? "failed" : ""}>
                          <td>{r.signal ? <span className={`signal-badge ${r.signal}`}>{SIGNALS[r.signal]}</span> : <span className="muted">-</span>}</td>
                          <td>
                            <strong>{r.name}</strong>
                            <span className="cell-sub">{r.symbol}</span>
                          </td>
                          <td>{r.strategy_name}</td>
                          {r.error ? (
                            <td colSpan={4} className="muted small">
                              {r.error}
                            </td>
                          ) : (
                            <>
                              <td className="nowrap">
                                {r.date?.slice(0, 10)}
                                {r.stale && <span className="tag warn" title="这只股票的行情比其他股票旧，先更新行情">行情旧</span>}
                                {r.live && <span className="tag" title="用实时价格代替今天的收盘价算出来的，收盘前可能变">盘中</span>}
                              </td>
                              <td className="num">{formatNumber(r.close, 3)}</td>
                              <td className={`num ${trendClass(r.change)}`}>{formatPercent(r.change, true)}</td>
                              <td className="small">
                                {conditions.map((c, i) => (
                                  <span key={i} className={c.met ? "cond met" : "cond"}>
                                    {c.met ? "✓ " : "✗ "}
                                    {c.text}
                                  </span>
                                ))}
                              </td>
                            </>
                          )}
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}
      </section>

      <PaperSection token={token} strategies={strategies} notify={notify} />
      <AutomationPanel token={token} isAdmin={isAdmin} notify={notify} />
    </div>
  );
}

function PaperSection({ token, strategies, notify }: { token: string; strategies: StrategyRecord[]; notify: Notify }) {
  const [accounts, setAccounts] = useState<PaperAccount[]>([]);
  const [openId, setOpenId] = useState("");
  const [detail, setDetail] = useState<PaperAccount | null>(null);
  const [creating, setCreating] = useState(false);
  const [busy, setBusy] = useState("");

  async function reload() {
    try {
      setAccounts((await request<{ accounts: PaperAccount[] }>("/paper", {}, token)).accounts);
    } catch (error) {
      notify("error", `读取模拟盘失败：${getErrorMessage(error)}`);
    }
  }

  async function open(id: string) {
    setOpenId(id);
    setBusy(`open:${id}`);
    try {
      setDetail(await request<PaperAccount>(`/paper/${id}`, {}, token));
    } catch (error) {
      notify("error", `读取模拟盘失败：${getErrorMessage(error)}`);
    } finally {
      setBusy("");
    }
  }

  async function remove(account: PaperAccount) {
    if (!window.confirm(`删除模拟盘「${account.name}」？删除后不能恢复。`)) return;
    await request(`/paper/${account.account_id}`, { method: "DELETE" }, token);
    setDetail(null);
    setOpenId("");
    await reload();
    notify("success", "已删除模拟盘。");
  }

  useEffect(() => {
    reload();
  }, [token]);

  return (
    <section className="batch-setup paper">
      <div className="paper-head">
        <h3 className="section-title">模拟盘</h3>
        <button className="button primary small" onClick={() => setCreating(!creating)} disabled={!strategies.length}>
          {creating ? "收起" : "+ 新建模拟盘"}
        </button>
      </div>
      <p className="muted small">
        用虚拟资金按策略规则自动买卖（信号出现后第二天开盘成交，手续费、整手、T+1 和回测一样）。资金平均分给每只股票。行情每更新一天，模拟盘就往前走一天。
      </p>

      {creating && (
        <PaperForm
          token={token}
          strategies={strategies}
          notify={notify}
          onCreated={async (account) => {
            setCreating(false);
            await reload();
            setOpenId(account.account_id);
            setDetail(account);
          }}
        />
      )}

      {accounts.length === 0 && !creating && <p className="muted">还没有模拟盘。点「新建模拟盘」，选一个策略和几只股票开始跟踪。</p>}
      <div className="paper-cards">
        {accounts.map((a) => (
          <button key={a.account_id} className={a.account_id === openId ? "paper-card active" : "paper-card"} onClick={() => open(a.account_id)}>
            <strong>{a.name}</strong>
            <span className="muted small">
              {a.strategy_name} · {a.symbols.length} 只 · {a.start_date} 起
            </span>
            <span className={`paper-return ${trendClass(a.summary.total_return)}`}>{formatPercent(a.summary.total_return, true)}</span>
            <span className="small">
              {formatMoney(a.summary.equity)} {a.currency}
              {a.summary.last_date ? ` · 截至 ${a.summary.last_date}` : " · 等待第一根行情"}
            </span>
            {a.pending.length > 0 && <span className="tag warn">明天 {a.pending.length} 笔待成交</span>}
          </button>
        ))}
      </div>

      {detail && detail.account_id === openId && <PaperDetail account={detail} busy={busy !== ""} onDelete={() => remove(detail)} />}
    </section>
  );
}

function PaperForm({ token, strategies, notify, onCreated }: { token: string; strategies: StrategyRecord[]; notify: Notify; onCreated: (a: PaperAccount) => void }) {
  const [strategyId, setStrategyId] = useState(strategies[0]?.strategy_id || "");
  const strategy = strategies.find((s) => s.strategy_id === strategyId);
  const [name, setName] = useState("");
  const [symbolText, setSymbolText] = useState(strategy?.symbol || "");
  const [cash, setCash] = useState(String(strategy?.strategy.position?.initial_cash || 1000000));
  const [start, setStart] = useState(today());
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!strategy) return;
    setSymbolText(strategy.symbol);
    setCash(String(strategy.strategy.position?.initial_cash || 1000000));
  }, [strategyId]);

  async function submit() {
    if (!strategy) return;
    setBusy(true);
    try {
      const account = await request<PaperAccount>(
        "/paper",
        {
          method: "POST",
          body: JSON.stringify({
            name: name.trim() || `${strategy.name} 模拟盘`,
            strategy: strategy.strategy,
            source_strategy_id: strategy.strategy_id,
            symbols: parseSymbols(symbolText),
            initial_cash: Number(cash),
            start_date: start,
          }),
        },
        token,
      );
      notify("success", `已建立模拟盘「${account.name}」。`);
      onCreated(account);
    } catch (error) {
      notify("error", `建立失败：${getErrorMessage(error)}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="paper-form">
      <label>
        策略
        <select value={strategyId} onChange={(e) => setStrategyId(e.target.value)}>
          {strategies.map((s) => (
            <option key={s.strategy_id} value={s.strategy_id}>
              {s.name} · {marketLabels[s.market as keyof typeof marketLabels] || s.market}
            </option>
          ))}
        </select>
      </label>
      <label>
        名称
        <input value={name} placeholder={strategy ? `${strategy.name} 模拟盘` : ""} onChange={(e) => setName(e.target.value)} />
      </label>
      <label className="wide">
        股票（最多 20 只，和策略同一个市场）
        <input value={symbolText} onChange={(e) => setSymbolText(e.target.value.toUpperCase())} />
      </label>
      <label>
        虚拟资金
        <input inputMode="numeric" value={cash} onChange={(e) => setCash(e.target.value.replace(/[^\d.]/g, ""))} />
      </label>
      <label>
        从哪天开始
        <input type="date" value={start} onChange={(e) => setStart(e.target.value)} />
      </label>
      <div className="wide paper-form-foot">
        <button className="button primary" disabled={busy || !strategy || !parseSymbols(symbolText).length || !(Number(cash) > 0)} onClick={submit}>
          {busy ? "建立中…" : "建立模拟盘"}
        </button>
        <span className="muted small">从今天开始就是真正的「向前跟踪」；选过去的日期相当于从那天起回测，可以先看看效果。策略会在建立时固定下来，之后修改策略不影响这个模拟盘。</span>
      </div>
    </div>
  );
}

function PaperDetail({ account, busy, onDelete }: { account: PaperAccount; busy: boolean; onDelete: () => void }) {
  const s = account.summary;
  const curve = account.curve || [];
  return (
    <div className="paper-detail">
      <div className="kpi-strip batch-kpis">
        <div className="kpi">
          <span className="kpi-label">当前权益</span>
          <strong className="kpi-value">{formatMoney(s.equity)}</strong>
          <span className="kpi-sub">
            {account.currency} · 现金 {formatMoney(s.cash)}
          </span>
        </div>
        <div className="kpi">
          <span className="kpi-label">总收益</span>
          <strong className={`kpi-value ${trendClass(s.total_return)}`}>{formatPercent(s.total_return, true)}</strong>
          <span className="kpi-sub">{account.start_date} 起</span>
        </div>
        <div className="kpi">
          <span className="kpi-label">同期买入持有</span>
          <strong className={`kpi-value ${trendClass(s.hold_return)}`}>{formatPercent(s.hold_return, true)}</strong>
          <span className="kpi-sub">这些股票等权平均</span>
        </div>
        <div className="kpi">
          <span className="kpi-label">最新一天</span>
          <strong className={`kpi-value ${trendClass(s.day_change)}`}>{formatPercent(s.day_change, true)}</strong>
          <span className="kpi-sub">{s.last_date || "还没有行情"}</span>
        </div>
        <div className="kpi">
          <span className="kpi-label">最大回撤</span>
          <strong className="kpi-value">{formatPercent(s.max_drawdown)}</strong>
          <span className="kpi-sub">
            {s.positions} 只持仓 · {s.trades} 笔已平仓
          </span>
        </div>
      </div>

      {account.pending.length > 0 && (
        <div className="paper-pending">
          <strong>下个交易日开盘会执行：</strong>
          {account.pending.map((o) => (
            <span key={o.symbol} className={`signal-badge ${o.side}`}>
              {o.side === "buy" ? "买入" : "卖出"} {o.name}（{o.reason}，{o.date} 收盘 {formatNumber(o.close, 3)}）
            </span>
          ))}
        </div>
      )}

      {curve.length > 1 ? (
        <EquityChart points={curve} trades={[]} initialCash={account.initial_cash} currency={account.currency} />
      ) : (
        <p className="muted">开始日期之后还没有行情。每天收盘后更新行情，这里就会出现权益曲线。</p>
      )}

      <h4>当前持仓</h4>
      {account.positions.length === 0 ? (
        <p className="muted">空仓。</p>
      ) : (
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>股票</th>
                <th>买入日</th>
                <th className="num">数量</th>
                <th className="num">成本价</th>
                <th className="num">最新价</th>
                <th className="num">市值</th>
                <th className="num">浮动盈亏</th>
                <th className="num">涨跌</th>
              </tr>
            </thead>
            <tbody>
              {account.positions.map((p) => (
                <tr key={p.symbol}>
                  <td>
                    <strong>{p.name}</strong>
                    <span className="cell-sub">{p.symbol}</span>
                  </td>
                  <td>{p.entry_time.slice(0, 10)}</td>
                  <td className="num">{formatNumber(p.quantity, 0)}</td>
                  <td className="num">{formatNumber(p.entry_price, 3)}</td>
                  <td className="num">{formatNumber(p.last_close, 3)}</td>
                  <td className="num">{formatMoney(p.market_value)}</td>
                  <td className={`num ${trendClass(p.unrealized_pnl)}`}>{formatMoney(p.unrealized_pnl)}</td>
                  <td className={`num ${trendClass(p.return_pct)}`}>{formatPercent(p.return_pct, true)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <h4>每只股票</h4>
      <div className="table-wrap">
        <table className="data-table">
          <thead>
            <tr>
              <th>股票</th>
              <th>状态</th>
              <th className="num">分到的资金现在</th>
              <th className="num">收益</th>
              <th className="num">买入持有</th>
            </tr>
          </thead>
          <tbody>
            {(account.sleeves || []).map((sl) => (
              <tr key={sl.symbol}>
                <td>
                  <strong>{sl.name}</strong>
                  <span className="cell-sub">{sl.symbol}</span>
                </td>
                <td className="small">{sl.status === "ok" ? `行情到 ${sl.last_date}` : sl.status === "waiting" ? "等待开始日之后的行情" : sl.error}</td>
                <td className="num">{formatMoney(sl.equity)}</td>
                <td className={`num ${trendClass(sl.total_return)}`}>{formatPercent(sl.total_return, true)}</td>
                <td className={`num ${trendClass(sl.hold_return)}`}>{formatPercent(sl.hold_return, true)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <h4>已平仓交易</h4>
      {(account.trades || []).length === 0 ? (
        <p className="muted">还没有平仓的交易。</p>
      ) : (
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>股票</th>
                <th>买入</th>
                <th>卖出</th>
                <th className="num">数量</th>
                <th className="num">盈亏</th>
                <th className="num">收益率</th>
              </tr>
            </thead>
            <tbody>
              {(account.trades || []).slice(0, 100).map((t, i) => (
                <tr key={i}>
                  <td>{t.name}</td>
                  <td>{t.entry_time.slice(0, 10)}</td>
                  <td>{t.exit_time.slice(0, 10)}</td>
                  <td className="num">{formatNumber(t.quantity, 0)}</td>
                  <td className={`num ${trendClass(t.net_pnl)}`}>{formatMoney(t.net_pnl)}</td>
                  <td className={`num ${trendClass(t.return_pct)}`}>{formatPercent(t.return_pct, true)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="paper-foot">
        <button className="button small danger" disabled={busy} onClick={onDelete}>
          删除这个模拟盘
        </button>
      </div>
    </div>
  );
}
