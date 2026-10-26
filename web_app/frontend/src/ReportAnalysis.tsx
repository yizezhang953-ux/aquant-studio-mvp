import { BacktestReport, DrawdownEpisode, formatPercent, trendClass } from "./api";

// Extra report sections: comparison with 恒生指数 / 沪深300, drawdown durations, monthly-return heatmap.

const MONTHS = ["1月", "2月", "3月", "4月", "5月", "6月", "7月", "8月", "9月", "10月", "11月", "12月"];

function annualize(total: number | null | undefined, days: string[]) {
  if (total == null || days.length < 2) return null;
  const years = (Date.parse(days[days.length - 1]) - Date.parse(days[0])) / (365.25 * 86400000);
  return years >= 1 ? Math.pow(1 + total, 1 / years) - 1 : null;
}

/** Red for gains, green for losses (A-share/HK convention); stronger colour for bigger moves. */
export function heatColor(value: number | null) {
  if (value == null) return undefined;
  const strength = Math.min(Math.abs(value) / 0.1, 1);
  if (strength < 0.005) return undefined;
  const [r, g, b] = value > 0 ? [200, 50, 43] : [18, 122, 85];
  return `rgba(${r}, ${g}, ${b}, ${(0.08 + strength * 0.62).toFixed(3)})`;
}

function episodeText(e: DrawdownEpisode) {
  const end = e.recovered ? `${e.end} 回到前高` : `到 ${e.end} 仍未回到前高`;
  return `${e.start} 起，${end}`;
}

export function ReportAnalysis({ report }: { report: BacktestReport }) {
  const analysis = report.analysis;
  if (!analysis || analysis.days.length < 2) return null;
  const m = report.metrics || {};
  const dd = analysis.drawdown;
  const missing = analysis.benchmarks.filter((b) => !b.available);

  return (
    <div className="analysis">
      <section className="analysis-block">
        <h4>和大盘比</h4>
        <div className="table-wrap">
          <table className="data-table bench-table">
            <thead>
              <tr>
                <th />
                <th className="num">总收益</th>
                <th className="num">年化</th>
                <th className="num">本策略多赚</th>
              </tr>
            </thead>
            <tbody>
              <tr className="selected">
                <td>
                  <strong>本策略</strong>
                </td>
                <td className={`num ${trendClass(m.total_return)}`}>{formatPercent(m.total_return, true)}</td>
                <td className={`num ${trendClass(m.annualized_return)}`}>{formatPercent(m.annualized_return, true)}</td>
                <td className="num muted">-</td>
              </tr>
              <tr>
                <td>买入持有 {report.symbol}</td>
                <td className={`num ${trendClass(m.benchmark_return)}`}>{formatPercent(m.benchmark_return, true)}</td>
                <td className={`num ${trendClass(annualize(m.benchmark_return, analysis.days))}`}>
                  {formatPercent(annualize(m.benchmark_return, analysis.days), true)}
                </td>
                <td className={`num ${trendClass(m.excess_return)}`}>{formatPercent(m.excess_return, true)}</td>
              </tr>
              {analysis.benchmarks
                .filter((b) => b.available)
                .map((b) => (
                  <tr key={b.code}>
                    <td>
                      <span className={`swatch bench-${b.code}`} />
                      {b.name}
                    </td>
                    <td className={`num ${trendClass(b.total_return)}`}>{formatPercent(b.total_return, true)}</td>
                    <td className={`num ${trendClass(b.annualized_return)}`}>{formatPercent(b.annualized_return, true)}</td>
                    <td className={`num ${trendClass(b.excess_return)}`}>{formatPercent(b.excess_return, true)}</td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
        <p className="muted small">
          指数是价格指数，不含分红；股票的「买入持有」含分红再投入。
          {missing.length > 0 && ` 还没有${missing.map((b) => b.name).join("、")}这段时间的数据：管理员到「行情数据」→「指数基准」点一下同步即可，之后打开任何报告都会自动对比。`}
        </p>
      </section>

      {dd && (
        <section className="analysis-block">
          <h4>回撤持续时间</h4>
          <div className="dd-cards">
            <div className="dd-card">
              <span className="kpi-label">最长回撤</span>
              <strong className="kpi-value">{dd.longest ? `${dd.longest.days} 天` : "无"}</strong>
              {dd.longest && (
                <span className="kpi-sub">
                  {episodeText(dd.longest)}；期间最深 {formatPercent(dd.longest.depth)}
                </span>
              )}
            </div>
            <div className="dd-card">
              <span className="kpi-label">最大回撤 {dd.deepest ? formatPercent(dd.deepest.depth) : ""}</span>
              <strong className="kpi-value">
                {dd.deepest ? (dd.deepest.recovered ? `跌 ${dd.deepest.fall_days} 天，涨回 ${dd.deepest.recover_days} 天` : `跌 ${dd.deepest.fall_days} 天，尚未涨回`) : "无"}
              </strong>
              {dd.deepest && (
                <span className="kpi-sub">
                  {dd.deepest.start} 高点 → {dd.deepest.trough} 最低
                  {dd.deepest.recovered ? ` → ${dd.deepest.end} 回到高点` : ""}
                </span>
              )}
            </div>
            <div className="dd-card">
              <span className="kpi-label">处在回撤中的时间</span>
              <strong className="kpi-value">{formatPercent(dd.underwater_pct)}</strong>
              <span className="kpi-sub">共 {dd.count} 次回撤（低于前高就算）</span>
            </div>
          </div>
        </section>
      )}

      {analysis.monthly_returns.length > 0 && (
        <section className="analysis-block">
          <h4>月度收益</h4>
          <div className="table-wrap">
            <table className="heatmap">
              <thead>
                <tr>
                  <th />
                  {MONTHS.map((month) => (
                    <th key={month}>{month}</th>
                  ))}
                  <th>全年</th>
                </tr>
              </thead>
              <tbody>
                {analysis.monthly_returns.map((row) => (
                  <tr key={row.year}>
                    <th>{row.year}</th>
                    {row.months.map((value, i) => (
                      <td key={i} style={{ background: heatColor(value) }} title={value == null ? "" : `${row.year}年${i + 1}月 ${formatPercent(value, true)}`}>
                        {value == null ? "" : formatPercent(value, true).replace("%", "")}
                      </td>
                    ))}
                    <td className="year" style={{ background: heatColor(row.total) }}>
                      {formatPercent(row.total, true)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="muted small">格子里是当月收益（%），红色赚、绿色亏，颜色越深幅度越大；空格表示不在回测区间。</p>
        </section>
      )}
    </div>
  );
}

/** Index growth lines in equity units, aligned with the report's equity points. */
export function benchmarkLines(report: BacktestReport) {
  const analysis = report.analysis;
  if (!analysis) return [];
  const initial = report.metrics?.initial_cash || report.equity_curve?.[0]?.equity || 0;
  const position = new Map(analysis.days.map((day, i) => [day, i]));
  return analysis.benchmarks
    .filter((b) => b.available && b.growth)
    .map((b) => ({
      code: b.code,
      name: b.name,
      values: (report.equity_curve || []).map((p) => {
        const i = position.get(p.trade_time.slice(0, 10));
        return i == null ? NaN : initial * b.growth![i];
      }),
    }));
}
