import { useState } from "react";
import {
  BacktestHistoryItem,
  BacktestReport,
  Notify,
  ParameterSnapshot,
  formatNumber,
  formatPercent,
  formatTimestamp,
  formatVersion,
  frequencyLabels,
  getErrorMessage,
  request,
  trendClass,
} from "./api";
import { BacktestView } from "./BacktestView";
import { OPERATORS } from "./RuleEditor";

type DiffField = { key: keyof ParameterSnapshot; label: string; format: (value: unknown) => string };

const pct = (value: unknown) => formatPercent(value as number);
const op = (value: unknown) => OPERATORS[String(value)] || String(value);
const diffFields: DiffField[] = [
  { key: "symbol", label: "股票", format: String },
  { key: "frequency", label: "周期", format: (v) => frequencyLabels[String(v)] || String(v) },
  { key: "start_date", label: "开始", format: String },
  { key: "end_date", label: "结束", format: String },
  { key: "entry_operator", label: "买入条件", format: op },
  { key: "entry_value", label: "买入阈值", format: (v) => formatNumber(v as number, 4) },
  { key: "exit_operator", label: "卖出条件", format: op },
  { key: "exit_value", label: "卖出阈值", format: (v) => formatNumber(v as number, 4) },
  { key: "order_size_value", label: "每次买入", format: pct },
  { key: "max_position_pct", label: "最大仓位", format: pct },
  { key: "stop_loss_pct", label: "止损", format: pct },
  { key: "take_profit_pct", label: "止盈", format: pct },
  { key: "max_drawdown_pct", label: "回撤上限", format: pct },
];

function differs(items: BacktestHistoryItem[], field: DiffField) {
  const values = items.map((item) => {
    const value = item.parameter_snapshot?.[field.key];
    return typeof value === "number" ? Number(value.toFixed(8)) : value ?? "";
  });
  return new Set(values).size > 1;
}

function shown(item: BacktestHistoryItem, field: DiffField) {
  const value = item.parameter_snapshot?.[field.key];
  return value === undefined || value === null || value === "" ? "-" : field.format(value);
}

export function HistoryPage({ token, history, notify }: { token: string; history: BacktestHistoryItem[]; notify: Notify }) {
  const [compare, setCompare] = useState<string[]>([]);
  const [openId, setOpenId] = useState("");
  const [report, setReport] = useState<BacktestReport | null>(null);
  const [filter, setFilter] = useState("");

  const visible = history.filter((item) => {
    const q = filter.trim().toUpperCase();
    return !q || item.symbol.includes(q) || item.strategy_name.toUpperCase().includes(q);
  });
  const compared = history.filter((item) => compare.includes(item.backtest_id));
  const changed = diffFields.filter((field) => compared.length > 1 && differs(compared, field));

  async function open(id: string) {
    setOpenId(id);
    try {
      setReport(await request<BacktestReport>(`/backtests/mine/${id}`, {}, token));
    } catch (error) {
      setReport(null);
      notify("error", `报告加载失败：${getErrorMessage(error)}`);
    }
  }

  function toggle(id: string) {
    setCompare((current) => (current.includes(id) ? current.filter((x) => x !== id) : [...current, id].slice(-4)));
  }

  if (history.length === 0) {
    return (
      <div className="page-pad">
        <div className="empty big">
          <h3>还没有回测记录</h3>
          <p>在「策略研究」里运行一次回测，结果会自动保存到这里。</p>
        </div>
      </div>
    );
  }

  return (
    <div className="page-pad history">
      <div className="history-main">
        <div className="toolbar">
          <h2>回测记录</h2>
          <input className="search" placeholder="按股票代码或策略名筛选" value={filter} onChange={(e) => setFilter(e.target.value)} />
          <span className="muted small">勾选 2 到 4 条可以对比参数</span>
        </div>
        <div className="table-wrap tall">
          <table className="data-table clickable">
            <thead>
              <tr>
                <th aria-label="对比" />
                <th>策略与股票</th>
                <th className="num">总收益</th>
                <th className="num">买入持有</th>
                <th className="num">最大回撤</th>
                <th className="num">交易</th>
                <th>运行时间</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((item) => (
                <tr key={item.backtest_id} className={item.backtest_id === openId ? "selected" : ""} onClick={() => open(item.backtest_id)}>
                  <td onClick={(e) => e.stopPropagation()}>
                    <input
                      type="checkbox"
                      aria-label="加入对比"
                      checked={compare.includes(item.backtest_id)}
                      onChange={() => toggle(item.backtest_id)}
                    />
                  </td>
                  <td>
                    <strong>{item.strategy_name}</strong> <span className="muted">{formatVersion(item.strategy_version)}</span>
                    <span className="cell-sub">
                      {item.symbol} · {frequencyLabels[item.frequency] || item.frequency}
                      {item.start_date ? ` · ${item.start_date} 至 ${item.end_date}` : ""}
                    </span>
                  </td>
                  <td className={`num ${trendClass(item.metrics.total_return)}`}>{formatPercent(item.metrics.total_return, true)}</td>
                  <td className={`num ${trendClass(item.metrics.benchmark_return)}`}>{formatPercent(item.metrics.benchmark_return, true)}</td>
                  <td className="num">{formatPercent(item.metrics.max_drawdown)}</td>
                  <td className="num">{formatNumber(item.metrics.trade_count, 0)}</td>
                  <td className="muted">{formatTimestamp(item.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {compared.length > 0 && (
          <section className="compare">
            <div className="toolbar">
              <h3>对比 {compared.length} 条</h3>
              <button className="text-button" onClick={() => setCompare([])}>
                清空
              </button>
            </div>
            {compared.length < 2 ? (
              <p className="muted">再勾选一条就能看到参数差异。</p>
            ) : changed.length === 0 ? (
              <p className="muted">这几次回测的主要参数相同。</p>
            ) : (
              <div className="table-wrap">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>参数</th>
                      {compared.map((item) => (
                        <th key={item.backtest_id}>
                          {item.symbol} {formatVersion(item.strategy_version)}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    <tr>
                      <td>总收益</td>
                      {compared.map((item) => (
                        <td key={item.backtest_id} className={trendClass(item.metrics.total_return)}>
                          {formatPercent(item.metrics.total_return, true)}
                        </td>
                      ))}
                    </tr>
                    {changed.map((field) => (
                      <tr key={field.key}>
                        <td>{field.label}</td>
                        {compared.map((item) => (
                          <td key={item.backtest_id}>{shown(item, field)}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        )}
      </div>

      <section className="history-detail">
        {report ? (
          <BacktestView report={report} />
        ) : (
          <div className="empty big">
            <h3>点一行查看完整报告</h3>
            <p>包括收益曲线、交易明细和提示。</p>
          </div>
        )}
      </section>
    </div>
  );
}
