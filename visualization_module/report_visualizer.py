from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
from typing import Any


def load_report(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def pct(value: float | int | None) -> str:
    if value is None:
        return "-"
    return f"{float(value) * 100:.2f}%"


def money(value: float | int | None) -> str:
    if value is None:
        return "-"
    return f"{float(value):,.2f}"


def number(value: float | int | None) -> str:
    if value is None:
        return "-"
    if isinstance(value, int):
        return str(value)
    return f"{float(value):.4f}"


def esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def series_points(values: list[float], width: int, height: int, padding: int) -> str:
    if not values:
        return ""
    if len(values) == 1:
        x = width / 2
        y = height / 2
        return f"{x:.2f},{y:.2f}"
    min_value = min(values)
    max_value = max(values)
    span = max_value - min_value
    points = []
    for index, value in enumerate(values):
        x = padding + index * ((width - padding * 2) / (len(values) - 1))
        if span == 0:
            y = height / 2
        else:
            y = height - padding - ((value - min_value) / span) * (height - padding * 2)
        points.append(f"{x:.2f},{y:.2f}")
    return " ".join(points)


def render_chart(report: dict[str, Any]) -> str:
    curve = report.get("equity_curve", [])
    width = 920
    height = 320
    padding = 34
    equity = [float(item["equity"]) for item in curve]
    close = [float(item["close"]) for item in curve]
    drawdown = [float(item["drawdown_pct"]) for item in curve]
    equity_points = series_points(equity, width, height, padding)
    close_points = series_points(close, width, height, padding)
    drawdown_points = series_points([value * -1 for value in drawdown], width, height, padding)
    labels = "".join(
        f'<span style="left:{(index / max(len(curve) - 1, 1)) * 100:.2f}%">{esc(item["trade_time"])}</span>'
        for index, item in enumerate(curve)
    )
    return f"""
      <div class="chart-wrap">
        <svg viewBox="0 0 {width} {height}" role="img" aria-label="权益曲线、回撤曲线和收盘价走势">
          <defs>
            <linearGradient id="equityFill" x1="0" x2="0" y1="0" y2="1">
              <stop offset="0%" stop-color="#0f766e" stop-opacity="0.20"/>
              <stop offset="100%" stop-color="#0f766e" stop-opacity="0.02"/>
            </linearGradient>
          </defs>
          <g class="grid">
            <line x1="34" y1="54" x2="886" y2="54"></line>
            <line x1="34" y1="126" x2="886" y2="126"></line>
            <line x1="34" y1="198" x2="886" y2="198"></line>
            <line x1="34" y1="270" x2="886" y2="270"></line>
          </g>
          <polyline points="{equity_points}" fill="none" stroke="#0f766e" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"></polyline>
          <polyline points="{close_points}" fill="none" stroke="#b7791f" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" opacity="0.82"></polyline>
          <polyline points="{drawdown_points}" fill="none" stroke="#c2410c" stroke-width="3" stroke-dasharray="8 8" stroke-linecap="round" stroke-linejoin="round"></polyline>
        </svg>
        <div class="x-labels">{labels}</div>
      </div>
    """


def render_metric_cards(metrics: dict[str, Any]) -> str:
    cards = [
        ("最终权益", money(metrics.get("final_equity")), "neutral"),
        ("总收益率", pct(metrics.get("total_return")), "good" if metrics.get("total_return", 0) >= 0 else "bad"),
        ("年化收益", pct(metrics.get("annualized_return")), "good" if metrics.get("annualized_return", 0) >= 0 else "bad"),
        ("最大回撤", pct(metrics.get("max_drawdown")), "bad"),
        ("胜率", pct(metrics.get("win_rate")), "neutral"),
        ("交易次数", number(metrics.get("trade_count")), "neutral"),
        ("夏普比率", number(metrics.get("sharpe")), "neutral"),
        ("手续费", money(metrics.get("total_fees")), "neutral"),
    ]
    return "\n".join(
        f'<div class="metric {tone}"><span>{esc(label)}</span><strong>{esc(value)}</strong></div>'
        for label, value, tone in cards
    )


def render_trades(trades: list[dict[str, Any]]) -> str:
    if not trades:
        return '<tr><td colspan="10" class="empty">暂无已平仓交易</td></tr>'
    rows = []
    for trade in trades:
        rows.append(
            "<tr>"
            f"<td>{esc(trade['symbol'])}</td>"
            f"<td>{esc(trade['entry_time'])}</td>"
            f"<td>{esc(trade['exit_time'])}</td>"
            f"<td>{money(trade['entry_price'])}</td>"
            f"<td>{money(trade['exit_price'])}</td>"
            f"<td>{esc(trade['quantity'])}</td>"
            f"<td class=\"{'good-text' if trade['net_pnl'] >= 0 else 'bad-text'}\">{money(trade['net_pnl'])}</td>"
            f"<td>{pct(trade['return_pct'])}</td>"
            f"<td>{money(trade['entry_fee'] + trade['exit_fee'])}</td>"
            f"<td>{esc(trade['exit_reason'])}</td>"
            "</tr>"
        )
    return "\n".join(rows)


def render_equity_rows(curve: list[dict[str, Any]]) -> str:
    rows = []
    for item in curve:
        rows.append(
            "<tr>"
            f"<td>{esc(item['trade_time'])}</td>"
            f"<td>{money(item['cash'])}</td>"
            f"<td>{esc(item['position_qty'])}</td>"
            f"<td>{money(item['close'])}</td>"
            f"<td>{money(item['equity'])}</td>"
            f"<td>{pct(item['drawdown_pct'])}</td>"
            "</tr>"
        )
    return "\n".join(rows)


def render_html(report: dict[str, Any]) -> str:
    metrics = report["metrics"]
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{esc(report['strategy_name'])} - 回测报告</title>
  <style>
    :root {{
      --bg: #f5f7f8;
      --panel: #ffffff;
      --line: #dfe5e8;
      --text: #17202a;
      --muted: #667085;
      --brand: #0f766e;
      --brand-soft: #e5f3ef;
      --gold: #b7791f;
      --bad: #c2410c;
      --good: #15803d;
      font-family: "Microsoft YaHei", "PingFang SC", Arial, sans-serif;
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; background: var(--bg); color: var(--text); }}
    .shell {{ min-height: 100vh; display: grid; grid-template-columns: 224px 1fr; }}
    aside {{ background: #111827; color: white; padding: 22px 16px; }}
    .brand {{ font-size: 20px; font-weight: 700; margin-bottom: 26px; }}
    .nav {{ display: grid; gap: 8px; }}
    .nav a {{ color: #d1d5db; text-decoration: none; padding: 10px 12px; border-radius: 6px; }}
    .nav a.active {{ background: #263244; color: #fff; }}
    main {{ min-width: 0; }}
    header {{ background: var(--panel); border-bottom: 1px solid var(--line); padding: 20px 28px; display: flex; justify-content: space-between; gap: 18px; align-items: center; }}
    h1 {{ margin: 0; font-size: 22px; }}
    .sub {{ color: var(--muted); margin-top: 6px; font-size: 14px; }}
    .badge {{ display: inline-flex; align-items: center; min-height: 26px; padding: 3px 9px; border-radius: 999px; background: var(--brand-soft); color: var(--brand); font-size: 13px; }}
    .content {{ padding: 24px 28px; display: grid; gap: 22px; }}
    .metrics {{ display: grid; grid-template-columns: repeat(4, minmax(150px, 1fr)); gap: 14px; }}
    .metric {{ background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 15px; }}
    .metric span {{ display: block; color: var(--muted); font-size: 13px; }}
    .metric strong {{ display: block; margin-top: 8px; font-size: 24px; }}
    .metric.good strong, .good-text {{ color: var(--good); }}
    .metric.bad strong, .bad-text {{ color: var(--bad); }}
    .panel {{ background: var(--panel); border: 1px solid var(--line); border-radius: 8px; overflow: hidden; }}
    .panel-head {{ padding: 16px 18px; border-bottom: 1px solid var(--line); display: flex; justify-content: space-between; align-items: center; gap: 12px; }}
    .panel-head h2 {{ margin: 0; font-size: 16px; }}
    .legend {{ display: flex; flex-wrap: wrap; gap: 10px; color: var(--muted); font-size: 13px; }}
    .legend span::before {{ content: ""; display: inline-block; width: 18px; height: 3px; vertical-align: middle; margin-right: 6px; background: var(--brand); }}
    .legend .price::before {{ background: var(--gold); }}
    .legend .drawdown::before {{ background: var(--bad); }}
    .chart-wrap {{ padding: 16px 18px 28px; position: relative; }}
    svg {{ width: 100%; height: 320px; display: block; }}
    .grid line {{ stroke: #edf1f3; stroke-width: 1; }}
    .x-labels {{ position: relative; height: 24px; margin: 0 34px; color: var(--muted); font-size: 12px; }}
    .x-labels span {{ position: absolute; transform: translateX(-50%); white-space: nowrap; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
    th, td {{ padding: 12px 14px; border-bottom: 1px solid var(--line); text-align: left; white-space: nowrap; }}
    th {{ color: var(--muted); background: #fafafa; font-weight: 600; }}
    .empty {{ color: var(--muted); text-align: center; padding: 28px; }}
    .table-wrap {{ overflow-x: auto; }}
    .summary-grid {{ display: grid; grid-template-columns: repeat(3, minmax(180px, 1fr)); gap: 14px; }}
    .summary-item {{ background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 14px; }}
    .summary-item span {{ color: var(--muted); font-size: 13px; display: block; margin-bottom: 7px; }}
    @media (max-width: 980px) {{
      .shell {{ grid-template-columns: 1fr; }}
      aside {{ display: none; }}
      header {{ align-items: flex-start; flex-direction: column; }}
      .metrics, .summary-grid {{ grid-template-columns: 1fr 1fr; }}
    }}
    @media (max-width: 640px) {{
      .metrics, .summary-grid {{ grid-template-columns: 1fr; }}
      .content {{ padding: 16px; }}
    }}
  </style>
</head>
<body>
  <div class="shell">
    <aside>
      <div class="brand">AQuant Studio</div>
      <nav class="nav">
        <a href="#overview" class="active">报告总览</a>
        <a href="#chart">曲线分析</a>
        <a href="#trades">交易明细</a>
        <a href="#equity">权益数据</a>
      </nav>
    </aside>
    <main>
      <header id="overview">
        <div>
          <h1>{esc(report['strategy_name'])}</h1>
          <div class="sub">{esc(report['symbol'])} · {esc(report['frequency'])} · {esc(report['start_date'])} 至 {esc(report['end_date'])}</div>
        </div>
        <span class="badge">回测报告 MVP</span>
      </header>
      <section class="content">
        <div class="summary-grid">
          <div class="summary-item"><span>策略 ID</span>{esc(report['strategy_id'])}</div>
          <div class="summary-item"><span>初始资金</span>{money(metrics.get('initial_cash'))}</div>
          <div class="summary-item"><span>平均持仓 K 线</span>{number(metrics.get('average_holding_bars'))}</div>
        </div>
        <section class="metrics">
          {render_metric_cards(metrics)}
        </section>
        <section class="panel" id="chart">
          <div class="panel-head">
            <h2>曲线分析</h2>
            <div class="legend"><span>权益</span><span class="price">收盘价</span><span class="drawdown">回撤</span></div>
          </div>
          {render_chart(report)}
        </section>
        <section class="panel" id="trades">
          <div class="panel-head"><h2>交易明细</h2><span class="badge">{len(report.get('trades', []))} 笔交易</span></div>
          <div class="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>标的</th><th>买入时间</th><th>卖出时间</th><th>买入价</th><th>卖出价</th><th>数量</th><th>净收益</th><th>收益率</th><th>手续费</th><th>原因</th>
                </tr>
              </thead>
              <tbody>{render_trades(report.get('trades', []))}</tbody>
            </table>
          </div>
        </section>
        <section class="panel" id="equity">
          <div class="panel-head"><h2>权益曲线数据</h2></div>
          <div class="table-wrap">
            <table>
              <thead><tr><th>时间</th><th>现金</th><th>持仓</th><th>收盘价</th><th>总权益</th><th>回撤</th></tr></thead>
              <tbody>{render_equity_rows(report.get('equity_curve', []))}</tbody>
            </table>
          </div>
        </section>
      </section>
    </main>
  </div>
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Render AQuant backtest report HTML")
    parser.add_argument("report_json")
    parser.add_argument("--output", default="visualization_module/output/report.html")
    parser.add_argument("--title", help="Optional display title override")
    args = parser.parse_args()

    report = load_report(Path(args.report_json))
    if args.title:
        report["strategy_name"] = args.title
    html_text = render_html(report)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html_text, encoding="utf-8")
    print(json.dumps({"ok": True, "output": str(output)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
