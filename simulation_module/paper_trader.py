from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backtest_module"))

from backtest_engine import (  # noqa: E402
    Bar,
    build_series_cache,
    execution_price,
    load_bars,
    load_strategy,
    rule_group_met,
)


@dataclass
class Order:
    order_id: str
    trade_time: str
    symbol: str
    side: str
    order_type: str
    quantity: int
    price: float
    status: str
    reason: str


@dataclass
class Fill:
    fill_id: str
    order_id: str
    trade_time: str
    symbol: str
    side: str
    quantity: int
    price: float
    fee: float
    amount: float


@dataclass
class AccountSnapshot:
    trade_time: str
    cash: float
    position_qty: int
    close: float
    market_value: float
    equity: float
    drawdown_pct: float
    state: str


@dataclass
class Event:
    trade_time: str
    event_type: str
    message: str
    payload: dict[str, Any]


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def make_event(trade_time: str, event_type: str, message: str, payload: dict[str, Any] | None = None) -> Event:
    return Event(trade_time=trade_time, event_type=event_type, message=message, payload=payload or {})


def create_order(
    sequence: int,
    trade_time: str,
    symbol: str,
    side: str,
    quantity: int,
    price: float,
    reason: str,
    status: str = "accepted",
) -> Order:
    return Order(
        order_id=f"ORD-{sequence:04d}",
        trade_time=trade_time,
        symbol=symbol,
        side=side,
        order_type="market_simulated",
        quantity=quantity,
        price=round(price, 6),
        status=status,
        reason=reason,
    )


def create_fill(sequence: int, order: Order, fee_rate: float) -> Fill:
    amount = order.quantity * order.price
    fee = amount * fee_rate
    return Fill(
        fill_id=f"FIL-{sequence:04d}",
        order_id=order.order_id,
        trade_time=order.trade_time,
        symbol=order.symbol,
        side=order.side,
        quantity=order.quantity,
        price=order.price,
        fee=round(fee, 6),
        amount=round(amount, 6),
    )


def run_paper_trading(config: dict[str, Any]) -> dict[str, Any]:
    strategy = load_strategy(ROOT / config["strategy_path"])
    bars = load_bars(ROOT / config["db_path"], strategy)
    if not bars:
        raise ValueError("no bars available for paper trading simulation")

    symbol = strategy["universe"]["symbols"][0]
    cache = build_series_cache(bars)
    initial_cash = float(config["account"].get("initial_cash", strategy["position"]["initial_cash"]))
    cash = initial_cash
    position_qty = 0
    entry_price = 0.0
    entry_index = 0
    peak_equity = initial_cash
    state = "running"

    order_size_value = float(strategy["position"]["order_size_value"])
    max_position_pct = float(strategy["position"]["max_position_pct"])
    execution = strategy.get("execution", {})
    entry_mode = execution.get("entry_price", "current_close")
    exit_mode = execution.get("exit_price", "current_close")
    fee_rate = float(execution.get("fee_rate", 0))
    slippage_rate = float(execution.get("slippage_rate", 0))
    risk = strategy["risk"]

    orders: list[Order] = []
    fills: list[Fill] = []
    snapshots: list[AccountSnapshot] = []
    events: list[Event] = [
        make_event(bars[0].trade_time, "simulation_started", "paper trading simulation started", {"strategy_id": strategy["strategy_id"]})
    ]

    order_seq = 0
    fill_seq = 0

    for index, bar in enumerate(bars):
        equity_before = cash + position_qty * bar.close
        peak_equity = max(peak_equity, equity_before)
        drawdown_pct = 0 if peak_equity == 0 else (peak_equity - equity_before) / peak_equity
        events.append(
            make_event(
                bar.trade_time,
                "bar",
                "received market bar",
                {"open": bar.open, "high": bar.high, "low": bar.low, "close": bar.close, "volume": bar.volume},
            )
        )

        if position_qty > 0:
            exit_reason = None
            gross_return = bar.close / entry_price - 1 if entry_price else 0
            if rule_group_met(strategy["exit"], index, bars, cache):
                exit_reason = "exit_rule"
            elif risk.get("stop_loss_pct") is not None and gross_return <= -float(risk["stop_loss_pct"]):
                exit_reason = "stop_loss"
            elif risk.get("take_profit_pct") is not None and gross_return >= float(risk["take_profit_pct"]):
                exit_reason = "take_profit"
            elif risk.get("max_holding_bars") is not None and index - entry_index + 1 >= int(risk["max_holding_bars"]):
                exit_reason = "max_holding_bars"

            if exit_reason:
                priced = execution_price(exit_mode, bars, index, "sell", slippage_rate)
                if priced:
                    price, exec_index = priced
                    order_seq += 1
                    order = create_order(order_seq, bars[exec_index].trade_time, symbol, "sell", position_qty, price, exit_reason)
                    fill_seq += 1
                    fill = create_fill(fill_seq, order, fee_rate)
                    cash += fill.amount - fill.fee
                    position_qty = 0
                    orders.append(order)
                    fills.append(fill)
                    events.append(make_event(order.trade_time, "order_filled", "sell order filled", asdict(fill)))

        equity = cash + position_qty * bar.close
        peak_equity = max(peak_equity, equity)
        drawdown_pct = 0 if peak_equity == 0 else (peak_equity - equity) / peak_equity
        if (
            config.get("risk_controls", {}).get("halt_on_max_drawdown", True)
            and risk.get("max_drawdown_pct") is not None
            and drawdown_pct >= float(risk["max_drawdown_pct"])
        ):
            state = "halted"
            events.append(make_event(bar.trade_time, "risk_halt", "max drawdown limit reached", {"drawdown_pct": drawdown_pct}))

        if state == "running" and position_qty == 0 and rule_group_met(strategy["entry"], index, bars, cache):
            priced = execution_price(entry_mode, bars, index, "buy", slippage_rate)
            if priced:
                price, exec_index = priced
                target_cash = min(cash * order_size_value, initial_cash * max_position_pct)
                quantity = int(target_cash / (price * (1 + fee_rate)))
                if quantity <= 0:
                    events.append(make_event(bar.trade_time, "order_rejected", "quantity is zero", {"target_cash": target_cash, "price": price}))
                else:
                    order_cost = quantity * price
                    fee = order_cost * fee_rate
                    if config.get("risk_controls", {}).get("reject_order_when_cash_insufficient", True) and order_cost + fee > cash:
                        order_seq += 1
                        order = create_order(order_seq, bars[exec_index].trade_time, symbol, "buy", quantity, price, "entry_rule", "rejected")
                        orders.append(order)
                        events.append(make_event(order.trade_time, "order_rejected", "cash is insufficient", asdict(order)))
                    else:
                        order_seq += 1
                        order = create_order(order_seq, bars[exec_index].trade_time, symbol, "buy", quantity, price, "entry_rule")
                        fill_seq += 1
                        fill = create_fill(fill_seq, order, fee_rate)
                        cash -= fill.amount + fill.fee
                        position_qty += quantity
                        entry_price = price
                        entry_index = exec_index
                        orders.append(order)
                        fills.append(fill)
                        events.append(make_event(order.trade_time, "order_filled", "buy order filled", asdict(fill)))

        market_value = position_qty * bar.close
        equity = cash + market_value
        peak_equity = max(peak_equity, equity)
        drawdown_pct = 0 if peak_equity == 0 else (peak_equity - equity) / peak_equity
        snapshots.append(
            AccountSnapshot(
                trade_time=bar.trade_time,
                cash=round(cash, 6),
                position_qty=position_qty,
                close=bar.close,
                market_value=round(market_value, 6),
                equity=round(equity, 6),
                drawdown_pct=round(drawdown_pct, 6),
                state=state,
            )
        )

    final_snapshot = snapshots[-1]
    events.append(make_event(final_snapshot.trade_time, "simulation_finished", "paper trading simulation finished", {"final_equity": final_snapshot.equity}))
    return {
        "simulation_id": config["simulation_id"],
        "name": config["name"],
        "mode": config["mode"],
        "strategy_id": strategy["strategy_id"],
        "symbol": symbol,
        "frequency": strategy["data"]["frequency"],
        "start_date": strategy["data"]["start_date"],
        "end_date": strategy["data"]["end_date"],
        "summary": {
            "initial_cash": initial_cash,
            "final_cash": final_snapshot.cash,
            "final_equity": final_snapshot.equity,
            "total_return": round(final_snapshot.equity / initial_cash - 1, 6),
            "max_drawdown": max(snapshot.drawdown_pct for snapshot in snapshots),
            "order_count": len(orders),
            "fill_count": len(fills),
            "final_position_qty": final_snapshot.position_qty,
            "state": final_snapshot.state,
        },
        "orders": [asdict(order) for order in orders],
        "fills": [asdict(fill) for fill in fills],
        "snapshots": [asdict(snapshot) for snapshot in snapshots],
        "events": [asdict(event) for event in events],
    }


def render_html(report: dict[str, Any]) -> str:
    summary = report["summary"]
    order_rows = "\n".join(
        "<tr>"
        f"<td>{order['order_id']}</td><td>{order['trade_time']}</td><td>{order['side']}</td>"
        f"<td>{order['quantity']}</td><td>{order['price']}</td><td>{order['status']}</td><td>{order['reason']}</td>"
        "</tr>"
        for order in report["orders"]
    ) or '<tr><td colspan="7" class="empty">暂无订单</td></tr>'
    snapshot_rows = "\n".join(
        "<tr>"
        f"<td>{snapshot['trade_time']}</td><td>{snapshot['cash']}</td><td>{snapshot['position_qty']}</td>"
        f"<td>{snapshot['close']}</td><td>{snapshot['equity']}</td><td>{snapshot['drawdown_pct']:.2%}</td><td>{snapshot['state']}</td>"
        "</tr>"
        for snapshot in report["snapshots"]
    )
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{report['name']} - 模拟盘报告</title>
  <style>
    :root {{ --bg:#f5f7f8; --panel:#fff; --line:#dfe5e8; --text:#17202a; --muted:#667085; --brand:#0f766e; --soft:#e5f3ef; }}
    * {{ box-sizing: border-box; }}
    body {{ margin:0; background:var(--bg); color:var(--text); font-family:"Microsoft YaHei","PingFang SC",Arial,sans-serif; }}
    header {{ background:var(--panel); border-bottom:1px solid var(--line); padding:22px 28px; }}
    h1 {{ margin:0; font-size:22px; }}
    .sub {{ color:var(--muted); margin-top:8px; }}
    main {{ padding:24px 28px; display:grid; gap:20px; }}
    .cards {{ display:grid; grid-template-columns:repeat(4,minmax(160px,1fr)); gap:14px; }}
    .card {{ background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:15px; }}
    .card span {{ display:block; color:var(--muted); font-size:13px; }}
    .card strong {{ display:block; margin-top:8px; font-size:24px; }}
    .panel {{ background:var(--panel); border:1px solid var(--line); border-radius:8px; overflow:hidden; }}
    .panel h2 {{ margin:0; font-size:16px; padding:16px 18px; border-bottom:1px solid var(--line); }}
    table {{ width:100%; border-collapse:collapse; font-size:14px; }}
    th,td {{ padding:12px 14px; border-bottom:1px solid var(--line); text-align:left; white-space:nowrap; }}
    th {{ color:var(--muted); background:#fafafa; }}
    .wrap {{ overflow-x:auto; }}
    .empty {{ text-align:center; color:var(--muted); }}
    @media (max-width:760px) {{ .cards {{ grid-template-columns:1fr 1fr; }} main {{ padding:16px; }} }}
  </style>
</head>
<body>
  <header>
    <h1>{report['name']}</h1>
    <div class="sub">{report['symbol']} · {report['frequency']} · {report['start_date']} 至 {report['end_date']} · {report['mode']}</div>
  </header>
  <main>
    <section class="cards">
      <div class="card"><span>最终权益</span><strong>{summary['final_equity']:.2f}</strong></div>
      <div class="card"><span>总收益率</span><strong>{summary['total_return']:.2%}</strong></div>
      <div class="card"><span>最大回撤</span><strong>{summary['max_drawdown']:.2%}</strong></div>
      <div class="card"><span>成交数量</span><strong>{summary['fill_count']}</strong></div>
    </section>
    <section class="panel">
      <h2>订单记录</h2>
      <div class="wrap"><table><thead><tr><th>订单号</th><th>时间</th><th>方向</th><th>数量</th><th>价格</th><th>状态</th><th>原因</th></tr></thead><tbody>{order_rows}</tbody></table></div>
    </section>
    <section class="panel">
      <h2>账户快照</h2>
      <div class="wrap"><table><thead><tr><th>时间</th><th>现金</th><th>持仓</th><th>收盘价</th><th>权益</th><th>回撤</th><th>状态</th></tr></thead><tbody>{snapshot_rows}</tbody></table></div>
    </section>
  </main>
</body>
</html>
"""


def write_outputs(report: dict[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(output_dir / "simulation_report.json", report)
    write_csv(output_dir / "orders.csv", report["orders"])
    write_csv(output_dir / "fills.csv", report["fills"])
    write_csv(output_dir / "account_snapshots.csv", report["snapshots"])
    write_csv(output_dir / "events.csv", report["events"])
    (output_dir / "paper_trading_report.html").write_text(render_html(report), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run AQuant paper trading simulation")
    parser.add_argument("config")
    parser.add_argument("--output-dir", default="simulation_module/output/price_breakout_paper")
    args = parser.parse_args()

    config = read_json(Path(args.config))
    report = run_paper_trading(config)
    write_outputs(report, Path(args.output_dir))
    print(json.dumps({"ok": True, "output_dir": args.output_dir, "summary": report["summary"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
