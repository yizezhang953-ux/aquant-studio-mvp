import { MouseEvent, useCallback, useState } from "react";
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
import { ContextMenu, MenuState } from "./ContextMenu";
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

// Two runs are duplicates when strategy, version, stock, period and results are all the same.
function runKey(item: BacktestHistoryItem) {
  const m = item.metrics;
  return [item.strategy_name, item.strategy_version, item.symbol, item.frequency, item.start_date, item.end_date,
    m.total_return, m.max_drawdown, m.trade_count, JSON.stringify(item.parameter_snapshot)].join("|");
}

export function HistoryPage({
  token,
  history,
  notify,
  onChanged,
}: {
  token: string;
  history: BacktestHistoryItem[];
  notify: Notify;
  onChanged: () => Promise<void>;
}) {
  const [compare, setCompare] = useState<string[]>([]);
  const [menu, setMenu] = useState<MenuState>(null);
  const closeMenu = useCallback(() => setMenu(null), []);
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
    setCompare((current) => (current.includes(id) ? current.filter((x) => x !== id) : [...current, id]));
  }

  function selectDuplicates() {
    // history is newest first, so the first copy seen is the one we keep
    const seen = new Set<string>();
    const extra = history.filter((item) => {
      const key = runKey(item);
      if (seen.has(key)) return true;
      seen.add(key);
      return false;
    });
    if (extra.length === 0) {
      notify("info", "没有重复的回测记录。");
      return;
    }
    setCompare(extra.map((item) => item.backtest_id));
    notify("info", `勾选了 ${extra.length} 条重复记录（每组保留最新的一条），确认后点「删除所选」。`);
  }

  async function remove(ids: string[]) {
    if (ids.length === 0) return;
    const names = history.filter((item) => ids.includes(item.backtest_id));
    const label = ids.length === 1 && names[0] ? `「${names[0].strategy_name} · ${names[0].symbol}」这条回测记录` : `选中的 ${ids.length} 条回测记录`;
    if (!window.confirm(`确定删除${label}吗？删除后无法恢复，但不影响策略本身和行情数据。`)) return;
    try {
      const result = await request<{ deleted: number }>("/backtests/delete", {
        method: "POST",
        body: JSON.stringify({ backtest_ids: ids }),
      }, token);
      setCompare((current) => current.filter((id) => !ids.includes(id)));
      if (ids.includes(openId)) {
        setOpenId("");
        setReport(null);
      }
      await onChanged();
      notify("success", `已删除 ${result.deleted} 条回测记录。`);
    } catch (error) {
      notify("error", `删除失败：${getErrorMessage(error)}`);
    }
  }

  function openMenu(event: MouseEvent, item: BacktestHistoryItem) {
    event.preventDefault();
    const others = compare.filter((id) => id !== item.backtest_id);
    const items = [
      { label: "查看报告", onClick: () => open(item.backtest_id) },
      {
        label: compare.includes(item.backtest_id) ? "取消勾选" : "勾选",
        onClick: () => toggle(item.backtest_id),
      },
      { label: "删除这条记录", danger: true, onClick: () => remove([item.backtest_id]) },
    ];
    if (others.length > 0 && compare.includes(item.backtest_id)) {
      items.push({ label: `删除勾选的 ${compare.length} 条`, danger: true, onClick: () => remove(compare) });
    }
    setMenu({ x: event.clientX, y: event.clientY, items });
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
          <span className="muted small">勾选 2 到 4 条可对比；右键一行可删除</span>
          <span className="spacer" />
          <button className="text-button" onClick={selectDuplicates}>
            选出重复记录
          </button>
          <button className="button small danger" disabled={compare.length === 0} onClick={() => remove(compare)}>
            删除所选{compare.length ? ` (${compare.length})` : ""}
          </button>
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
                <tr
                  key={item.backtest_id}
                  className={item.backtest_id === openId ? "selected" : ""}
                  onClick={() => open(item.backtest_id)}
                  onContextMenu={(event) => openMenu(event, item)}
                >
                  <td onClick={(e) => e.stopPropagation()}>
                    <input
                      type="checkbox"
                      aria-label="勾选"
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
            ) : compared.length > 4 ? (
              <p className="muted">对比最多 4 条；勾选多条可以一起删除。</p>
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

      <ContextMenu menu={menu} onClose={closeMenu} />

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
