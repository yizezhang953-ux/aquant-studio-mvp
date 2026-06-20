from __future__ import annotations

import argparse
import csv
import json
import math
import sqlite3
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any


@dataclass
class Bar:
    symbol: str
    frequency: str
    trade_time: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    amount: float


@dataclass
class Trade:
    symbol: str
    entry_time: str
    exit_time: str
    entry_price: float
    exit_price: float
    quantity: int
    gross_pnl: float
    net_pnl: float
    return_pct: float
    entry_fee: float
    exit_fee: float
    exit_reason: str
    holding_bars: int


@dataclass
class EquityPoint:
    trade_time: str
    cash: float
    position_qty: int
    close: float
    equity: float
    drawdown_pct: float


def load_strategy(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_bars(db_path: Path, strategy: dict[str, Any]) -> list[Bar]:
    symbol = strategy["universe"]["symbols"][0]
    frequency = strategy["data"]["frequency"]
    start = strategy["data"]["start_date"]
    end = strategy["data"]["end_date"]
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT symbol, frequency, trade_time, open, high, low, close, volume, amount
            FROM bars
            WHERE symbol = ? AND frequency = ? AND trade_time >= ? AND trade_time <= ?
            ORDER BY trade_time ASC
            """,
            (symbol, frequency, start, end),
        ).fetchall()
    return [Bar(**dict(row)) for row in rows]


def moving_average(values: list[float], period: int) -> list[float | None]:
    result: list[float | None] = []
    for index in range(len(values)):
        if index + 1 < period:
            result.append(None)
        else:
            window = values[index + 1 - period : index + 1]
            result.append(sum(window) / period)
    return result


def exponential_moving_average(values: list[float], period: int) -> list[float | None]:
    result: list[float | None] = []
    multiplier = 2 / (period + 1)
    ema: float | None = None
    for index, value in enumerate(values):
        if index + 1 < period:
            result.append(None)
            continue
        if ema is None:
            ema = sum(values[index + 1 - period : index + 1]) / period
        else:
            ema = value * multiplier + ema * (1 - multiplier)
        result.append(ema)
    return result


def rsi(values: list[float], period: int) -> list[float | None]:
    result: list[float | None] = [None]
    gains: list[float] = []
    losses: list[float] = []
    for index in range(1, len(values)):
        delta = values[index] - values[index - 1]
        gains.append(max(delta, 0))
        losses.append(abs(min(delta, 0)))
        if index < period:
            result.append(None)
            continue
        avg_gain = sum(gains[index - period : index]) / period
        avg_loss = sum(losses[index - period : index]) / period
        if avg_loss == 0:
            result.append(100.0)
        else:
            rs = avg_gain / avg_loss
            result.append(100 - 100 / (1 + rs))
    return result


def build_series_cache(bars: list[Bar]) -> dict[str, list[float]]:
    return {
        "open": [bar.open for bar in bars],
        "high": [bar.high for bar in bars],
        "low": [bar.low for bar in bars],
        "close": [bar.close for bar in bars],
        "volume": [bar.volume for bar in bars],
        "amount": [bar.amount for bar in bars],
    }


def expression_values(expr: dict[str, Any], bars: list[Bar], cache: dict[str, list[float]]) -> list[float | None]:
    expr_type = expr["type"]
    if expr_type == "price":
        return list(cache[expr["field"]])
    if expr_type == "constant":
        return [float(expr["value"]) for _ in bars]
    if expr_type == "indicator":
        name = expr["name"]
        params = expr.get("params", {})
        field = params.get("field", "close")
        period = int(params.get("period", 14))
        values = cache[field]
        if name == "MA":
            return moving_average(values, period)
        if name == "EMA":
            return exponential_moving_average(values, period)
        if name == "RSI":
            return rsi(values, period)
        if name == "VOLUME_MA":
            return moving_average(cache["volume"], period)
        if name == "RETURN":
            result: list[float | None] = []
            for index, value in enumerate(values):
                if index < period or values[index - period] == 0:
                    result.append(None)
                else:
                    result.append(value / values[index - period] - 1)
            return result
        if name == "VOLATILITY":
            returns: list[float] = [0]
            for index in range(1, len(values)):
                returns.append(values[index] / values[index - 1] - 1)
            result = []
            for index in range(len(returns)):
                if index + 1 < period:
                    result.append(None)
                else:
                    window = returns[index + 1 - period : index + 1]
                    mean = sum(window) / period
                    variance = sum((item - mean) ** 2 for item in window) / period
                    result.append(math.sqrt(variance))
            return result
    raise ValueError(f"unsupported expression: {expr}")


def compare(left: float, right: float, operator: str) -> bool:
    if operator == "gt":
        return left > right
    if operator == "lt":
        return left < right
    if operator == "eq":
        return left == right
    if operator == "gte":
        return left >= right
    if operator == "lte":
        return left <= right
    raise ValueError(f"operator requires cross evaluation: {operator}")


def condition_met(
    condition: dict[str, Any],
    index: int,
    bars: list[Bar],
    cache: dict[str, list[float]],
) -> bool:
    left_values = expression_values(condition["left"], bars, cache)
    right_values = expression_values(condition["right"], bars, cache)
    left = left_values[index]
    right = right_values[index]
    if left is None or right is None:
        return False
    operator = condition["operator"]
    if operator in {"cross_above", "cross_below"}:
        if index == 0:
            return False
        prev_left = left_values[index - 1]
        prev_right = right_values[index - 1]
        if prev_left is None or prev_right is None:
            return False
        if operator == "cross_above":
            return prev_left <= prev_right and left > right
        return prev_left >= prev_right and left < right
    return compare(float(left), float(right), operator)


def rule_group_met(group: dict[str, Any], index: int, bars: list[Bar], cache: dict[str, list[float]]) -> bool:
    values = [condition_met(condition, index, bars, cache) for condition in group["conditions"]]
    return all(values) if group["logic"] == "all" else any(values)


def execution_price(mode: str, bars: list[Bar], index: int, side: str, slippage_rate: float) -> tuple[float, int] | None:
    exec_index = index
    if mode == "next_open":
        exec_index = index + 1
        if exec_index >= len(bars):
            return None
        raw_price = bars[exec_index].open
    elif mode == "current_close":
        raw_price = bars[exec_index].close
    else:
        raise ValueError(f"unsupported execution price mode: {mode}")

    if side == "buy":
        return raw_price * (1 + slippage_rate), exec_index
    return raw_price * (1 - slippage_rate), exec_index


def run_backtest(strategy: dict[str, Any], bars: list[Bar]) -> dict[str, Any]:
    if not bars:
        raise ValueError("no bars available for backtest")

    cache = build_series_cache(bars)
    symbol = strategy["universe"]["symbols"][0]
    initial_cash = float(strategy["position"]["initial_cash"])
    order_size_value = float(strategy["position"]["order_size_value"])
    max_position_pct = float(strategy["position"]["max_position_pct"])
    execution = strategy.get("execution", {})
    entry_mode = execution.get("entry_price", "next_open")
    exit_mode = execution.get("exit_price", "next_open")
    fee_rate = float(execution.get("fee_rate", 0))
    slippage_rate = float(execution.get("slippage_rate", 0))
    risk = strategy["risk"]

    cash = initial_cash
    position_qty = 0
    entry_price = 0.0
    entry_fee = 0.0
    entry_time = ""
    entry_index = 0
    stopped = False
    peak_equity = initial_cash
    trades: list[Trade] = []
    equity_curve: list[EquityPoint] = []

    for index, bar in enumerate(bars):
        close = bar.close
        equity = cash + position_qty * close
        peak_equity = max(peak_equity, equity)
        drawdown_pct = 0 if peak_equity == 0 else (peak_equity - equity) / peak_equity

        if position_qty > 0:
            exit_reason = None
            gross_return = close / entry_price - 1 if entry_price else 0
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
                    fee = position_qty * price * fee_rate
                    proceeds = position_qty * price - fee
                    gross_pnl = position_qty * (price - entry_price)
                    net_pnl = gross_pnl - entry_fee - fee
                    cash += proceeds
                    trades.append(
                        Trade(
                            symbol=symbol,
                            entry_time=entry_time,
                            exit_time=bars[exec_index].trade_time,
                            entry_price=round(entry_price, 6),
                            exit_price=round(price, 6),
                            quantity=position_qty,
                            gross_pnl=round(gross_pnl, 6),
                            net_pnl=round(net_pnl, 6),
                            return_pct=round(net_pnl / (position_qty * entry_price + entry_fee), 6),
                            entry_fee=round(entry_fee, 6),
                            exit_fee=round(fee, 6),
                            exit_reason=exit_reason,
                            holding_bars=exec_index - entry_index + 1,
                        )
                    )
                    position_qty = 0
                    entry_price = 0.0
                    entry_fee = 0.0
                    entry_time = ""
                    entry_index = 0

        equity = cash + position_qty * close
        peak_equity = max(peak_equity, equity)
        drawdown_pct = 0 if peak_equity == 0 else (peak_equity - equity) / peak_equity
        if risk.get("max_drawdown_pct") is not None and drawdown_pct >= float(risk["max_drawdown_pct"]):
            stopped = True

        if not stopped and position_qty == 0 and rule_group_met(strategy["entry"], index, bars, cache):
            priced = execution_price(entry_mode, bars, index, "buy", slippage_rate)
            if priced:
                price, exec_index = priced
                target_cash = min(cash * order_size_value, initial_cash * max_position_pct)
                quantity = int(target_cash / (price * (1 + fee_rate)))
                if quantity > 0:
                    cost = quantity * price
                    fee = cost * fee_rate
                    cash -= cost + fee
                    position_qty = quantity
                    entry_price = price
                    entry_fee = fee
                    entry_time = bars[exec_index].trade_time
                    entry_index = exec_index

        mark_equity = cash + position_qty * close
        peak_equity = max(peak_equity, mark_equity)
        drawdown_pct = 0 if peak_equity == 0 else (peak_equity - mark_equity) / peak_equity
        equity_curve.append(
            EquityPoint(
                trade_time=bar.trade_time,
                cash=round(cash, 6),
                position_qty=position_qty,
                close=close,
                equity=round(mark_equity, 6),
                drawdown_pct=round(drawdown_pct, 6),
            )
        )

    final_equity = equity_curve[-1].equity
    metrics = calculate_metrics(initial_cash, final_equity, trades, equity_curve, bars)
    return {
        "strategy_id": strategy["strategy_id"],
        "strategy_name": strategy["name"],
        "symbol": symbol,
        "frequency": strategy["data"]["frequency"],
        "start_date": strategy["data"]["start_date"],
        "end_date": strategy["data"]["end_date"],
        "metrics": metrics,
        "trades": [asdict(trade) for trade in trades],
        "equity_curve": [asdict(point) for point in equity_curve],
    }


def calculate_metrics(
    initial_cash: float,
    final_equity: float,
    trades: list[Trade],
    equity_curve: list[EquityPoint],
    bars: list[Bar],
) -> dict[str, Any]:
    total_return = final_equity / initial_cash - 1
    max_drawdown = max((point.drawdown_pct for point in equity_curve), default=0)
    wins = [trade for trade in trades if trade.net_pnl > 0]
    losses = [trade for trade in trades if trade.net_pnl < 0]
    win_rate = len(wins) / len(trades) if trades else 0
    gross_profit = sum(trade.net_pnl for trade in wins)
    gross_loss = abs(sum(trade.net_pnl for trade in losses))
    profit_factor = gross_profit / gross_loss if gross_loss else None
    total_fees = sum(trade.entry_fee + trade.exit_fee for trade in trades)
    average_holding_bars = sum(trade.holding_bars for trade in trades) / len(trades) if trades else 0
    periods = max(len(bars), 1)
    annual_factor = 252
    annualized_return = (final_equity / initial_cash) ** (annual_factor / periods) - 1 if final_equity > 0 else -1
    equity_returns = []
    for index in range(1, len(equity_curve)):
        previous = equity_curve[index - 1].equity
        current = equity_curve[index].equity
        equity_returns.append(current / previous - 1 if previous else 0)
    sharpe = calculate_sharpe(equity_returns, annual_factor)
    return {
        "initial_cash": round(initial_cash, 6),
        "final_equity": round(final_equity, 6),
        "total_return": round(total_return, 6),
        "annualized_return": round(annualized_return, 6),
        "max_drawdown": round(max_drawdown, 6),
        "win_rate": round(win_rate, 6),
        "profit_factor": round(profit_factor, 6) if profit_factor is not None else None,
        "trade_count": len(trades),
        "average_holding_bars": round(average_holding_bars, 6),
        "total_fees": round(total_fees, 6),
        "sharpe": round(sharpe, 6) if sharpe is not None else None,
    }


def calculate_sharpe(returns: list[float], annual_factor: int) -> float | None:
    if len(returns) < 2:
        return None
    mean = sum(returns) / len(returns)
    variance = sum((item - mean) ** 2 for item in returns) / (len(returns) - 1)
    std = math.sqrt(variance)
    if std == 0:
        return None
    return mean / std * math.sqrt(annual_factor)


def write_report(report: dict[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(output_dir / "trades.csv", report["trades"])
    write_csv(output_dir / "equity_curve.csv", report["equity_curve"])


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run AQuant MVP backtest")
    parser.add_argument("strategy_path")
    parser.add_argument("--db", default="data_module/market_data.sqlite")
    parser.add_argument("--output-dir", default="backtest_module/output/latest")
    args = parser.parse_args()

    strategy = load_strategy(Path(args.strategy_path))
    bars = load_bars(Path(args.db), strategy)
    report = run_backtest(strategy, bars)
    write_report(report, Path(args.output_dir))
    print(json.dumps({"ok": True, "output_dir": args.output_dir, "metrics": report["metrics"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
