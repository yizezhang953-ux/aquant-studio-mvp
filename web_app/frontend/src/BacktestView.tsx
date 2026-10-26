import { useState } from "react";
import {
  BacktestReport,
  formatMoney,
  formatNumber,
  formatPercent,
  frequencyLabels,
  marketLabels,
  trendClass,
} from "./api";
import { EquityChart } from "./charts";
import { ReportAnalysis, benchmarkLines } from "./ReportAnalysis";

const BLOCKED_LABELS: Record<string, string> = {
  suspended_or_market_closed: "停牌或休市",
  limit_up: "涨停买不进",
  limit_down: "跌停卖不出",
  not_connect_eligible: "不在港股通名单",
  insufficient_cash_for_one_lot: "资金不够买一手",
  t_plus_one: "T+1 当天不能卖",
};

const EXIT_LABELS: Record<string, string> = {
  exit_rule: "卖出信号",
  stop_loss: "止损",
  take_profit: "止盈",
  max_holding_bars: "持有到期",
  max_drawdown_stop: "回撤止损",
  end_of_data: "回测结束",
};

/** The engine reports warnings in English; show the common ones in Chinese. */
export function translateWarning(text: string): string {
  const rules: [RegExp, (m: RegExpMatchArray) => string][] = [
    [/^no indicator warm-up history before start_date/, () => "开始日期之前没有足够历史，指标前几天可能没有值。把行情同步得更早一些可以解决。"],
    [/^board lot for (\S+) unknown; using default (\d+)/, (m) => `${m[1]} 的每手股数未知，暂按 ${m[2]} 股计算。到「行情数据」点「更新港股每手股数」。`],
    [/^港股通 eligibility not configured/, () => "没有配置港股通名单，默认这只股票可以通过港股通买入。"],
    [/^(\S+) is not eligible for 港股通/, (m) => `${m[1]} 不在港股通名单内，买单都会被拒绝。`],
    [/^dividends\/bonus shares derived from adj_factor/, () => "分红送股是从复权数据推算的，属于近似值。"],
    [/^no volume in the data/, () => "数据里没有成交量，无法识别停牌。"],
    [/^current_close execution/, () => "按信号当根 K 线的收盘价成交（假设参加收盘集合竞价）。"],
    [/^no (\S+) rates loaded; used default rate (\S+)/, (m) => `没有 ${m[1]} 汇率数据，全程按 ${m[2]} 换算。同步一次港股行情会顺带下载汇率。`],
    [/^sample shorter than (\d+) calendar days/, (m) => `样本不足 ${m[1]} 天，不计算年化收益。`],
    [/^only (\d+) bars in the backtest window/, (m) => `回测区间只有 ${m[1]} 根 K 线，结果没有统计意义。`],
    [/^exchange_calendars not installed/, () => "没有安装交易日历库，港股通休市日未建模。"],
  ];
  for (const [pattern, render] of rules) {
    const match = text.match(pattern);
    if (match) return render(match);
  }
  return text;
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

type Tab = "trades" | "notes" | "detail";

export function BacktestView({ report }: { report: BacktestReport }) {
  const [tab, setTab] = useState<Tab>("trades");
  const m = report.metrics || {};
  const blocked = (m as Record<string, unknown>).blocked_orders as Record<string, number> | undefined;
  const blockedEntries = Object.entries(blocked || {});
  const warnings = (report.warnings || []).map(translateWarning);
  const currency = report.currency || "CNY";
  const notesCount = warnings.length + (blockedEntries.length ? 1 : 0);

  return (
    <div className="report">
      <div className="report-head">
        <div>
          <h3>{report.strategy_name}</h3>
          <p className="muted">
            {report.symbol} · {frequencyLabels[report.frequency] || report.frequency} ·{" "}
            {report.market ? marketLabels[report.market] : "A股"} · 每手 {report.lot_size ?? "-"} 股
            {report.start_date && ` · ${report.start_date} 至 ${report.end_date}`}
          </p>
        </div>
      </div>

      <div className="kpi-strip">
        <Kpi label="总收益" value={formatPercent(m.total_return, true)} tone={trendClass(m.total_return)} sub={`${formatMoney(m.final_equity)} ${currency}`} />
        <Kpi label="买入持有" value={formatPercent(m.benchmark_return, true)} tone={trendClass(m.benchmark_return)} sub={m.excess_return != null ? `超额 ${formatPercent(m.excess_return, true)}` : undefined} />
        <Kpi label="年化" value={formatPercent(m.annualized_return, true)} tone={trendClass(m.annualized_return)} />
        <Kpi label="最大回撤" value={formatPercent(m.max_drawdown)} tone={m.max_drawdown ? "down" : ""} />
        <Kpi label="夏普" value={formatNumber(m.sharpe)} />
        <Kpi label="胜率" value={formatPercent(m.win_rate)} sub={`${formatNumber(m.trade_count, 0)} 笔交易`} />
      </div>

      <EquityChart points={report.equity_curve || []} trades={report.trades || []} initialCash={m.initial_cash || report.equity_curve?.[0]?.equity || 0} currency={currency} benchmarks={benchmarkLines(report)} />

      <ReportAnalysis report={report} />

      <div className="tabs" role="tablist">
        <button role="tab" aria-selected={tab === "trades"} className={tab === "trades" ? "active" : ""} onClick={() => setTab("trades")}>
          交易明细 <span className="count">{report.trades.length}</span>
        </button>
        <button role="tab" aria-selected={tab === "notes"} className={tab === "notes" ? "active" : ""} onClick={() => setTab("notes")}>
          提示 <span className={notesCount ? "count warn" : "count"}>{notesCount}</span>
        </button>
        <button role="tab" aria-selected={tab === "detail"} className={tab === "detail" ? "active" : ""} onClick={() => setTab("detail")}>
          费用与持仓
        </button>
      </div>

      {tab === "trades" &&
        (report.trades.length === 0 ? (
          <p className="empty">这段时间没有成交。看看「提示」里的未成交原因，或放宽买入条件。</p>
        ) : (
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>买入</th>
                  <th>卖出</th>
                  <th className="num">数量</th>
                  <th className="num">买价</th>
                  <th className="num">卖价</th>
                  <th className="num">盈亏</th>
                  <th className="num">收益率</th>
                  <th>卖出原因</th>
                </tr>
              </thead>
              <tbody>
                {report.trades.map((trade, index) => (
                  <tr key={`${trade.entry_time}-${index}`}>
                    <td>{trade.entry_time.slice(0, 16)}</td>
                    <td>{trade.exit_time.slice(0, 16)}</td>
                    <td className="num">{formatNumber(trade.quantity, 0)}</td>
                    <td className="num">{formatNumber(trade.entry_price, 3)}</td>
                    <td className="num">{formatNumber(trade.exit_price, 3)}</td>
                    <td className={`num ${trendClass(trade.net_pnl)}`}>{formatMoney(trade.net_pnl)}</td>
                    <td className={`num ${trendClass(trade.return_pct)}`}>{formatPercent(trade.return_pct, true)}</td>
                    <td>{EXIT_LABELS[trade.exit_reason] || trade.exit_reason}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ))}

      {tab === "notes" && (
        <div className="notes">
          {notesCount === 0 && <p className="empty">没有需要注意的地方。</p>}
          {blockedEntries.length > 0 && (
            <div className="note-block">
              <h4>未成交的订单</h4>
              <ul>
                {blockedEntries.map(([key, count]) => (
                  <li key={key}>
                    {BLOCKED_LABELS[key] || key}：{count} 次
                  </li>
                ))}
              </ul>
            </div>
          )}
          {warnings.length > 0 && (
            <ul className="warning-list">
              {warnings.map((warning) => (
                <li key={warning}>{warning}</li>
              ))}
            </ul>
          )}
        </div>
      )}

      {tab === "detail" && (
        <dl className="detail-grid">
          <dt>初始资金</dt>
          <dd>
            {formatMoney(m.initial_cash)} {currency}
          </dd>
          <dt>期末权益</dt>
          <dd>
            {formatMoney(m.final_equity)} {currency}
          </dd>
          <dt>费用合计</dt>
          <dd>{formatMoney(m.total_fees)}</dd>
          <dt>税后分红</dt>
          <dd>{formatMoney(m.dividends_net)}</dd>
          <dt>红利税</dt>
          <dd>{formatMoney(m.dividend_tax)}</dd>
          <dt>持仓时间占比</dt>
          <dd>{formatPercent(m.exposure_pct)}</dd>
          <dt>盈亏比</dt>
          <dd>{formatNumber(m.profit_factor)}</dd>
          <dt>平均持有</dt>
          <dd>{formatNumber(m.average_holding_bars, 1)} 根 K 线</dd>
          <dt>K 线数量</dt>
          <dd>{formatNumber(m.bar_count, 0)}</dd>
          <dt>期末持仓</dt>
          <dd>
            {report.open_position
              ? `${formatNumber(report.open_position.quantity, 0)} 股，${report.open_position.entry_time.slice(0, 10)} 买入，浮动盈亏 ${formatMoney(report.open_position.unrealized_pnl)}`
              : "空仓"}
          </dd>
        </dl>
      )}
    </div>
  );
}
