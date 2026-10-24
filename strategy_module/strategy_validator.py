from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from market_rules_module.market_rules import get_market_rule, load_rules, normalize_market, normalize_symbol  # noqa: E402


SUPPORTED_MARKETS = {"a_share", "hk_stock", "hk_connect"}
SYMBOL_HINT = {
    "a_share": "6-digit code + .SH / .SZ / .BJ, e.g. 600519.SH",
    "hk_stock": "5-digit code + .HK, e.g. 00700.HK",
    "hk_connect": "5-digit code + .HK, e.g. 00700.HK (traded via 港股通)",
}
SUPPORTED_EXECUTION_MODES = {"next_open", "current_close"}
MACD_OUTPUTS = {"macd", "signal", "hist"}
BOLL_OUTPUTS = {"upper", "middle", "lower"}
CoverageFn = Callable[[str, str, str, str], tuple[int, str | None, str | None]]


SUPPORTED_INDICATORS = {"MA", "EMA", "MACD", "RSI", "BOLL", "VOLUME_MA", "RETURN", "VOLATILITY"}
SUPPORTED_OPERATORS = {"gt", "lt", "eq", "gte", "lte", "cross_above", "cross_below"}
SUPPORTED_FREQUENCIES = {"1d", "60m", "30m", "15m"}
SUPPORTED_PRICE_FIELDS = {"open", "high", "low", "close", "volume", "amount"}
SYMBOL_PATTERN = re.compile(r"^[0-9]{6}\.(SH|SZ|BJ)$|^[0-9]{5}\.HK$")


@dataclass
class ValidationResult:
    ok: bool
    errors: list[str]
    warnings: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "errors": self.errors, "warnings": self.warnings}


def load_strategy(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_strategy(
    strategy: dict[str, Any], db_path: Path | None = None, coverage: CoverageFn | None = None
) -> ValidationResult:
    """Validate the DSL. Data coverage is checked against ``coverage`` (callable) or ``db_path``."""
    errors: list[str] = []
    warnings: list[str] = []

    require(strategy, "schema_version", errors)
    require(strategy, "strategy_id", errors)
    require(strategy, "name", errors)
    require(strategy, "market", errors)
    require(strategy, "universe", errors)
    require(strategy, "data", errors)
    require(strategy, "entry", errors)
    require(strategy, "exit", errors)
    require(strategy, "position", errors)
    require(strategy, "risk", errors)

    if errors:
        return ValidationResult(False, errors, warnings)

    if strategy["schema_version"] != "1.0":
        errors.append("schema_version must be 1.0")
    market = normalize_market(strategy["market"])
    if market not in SUPPORTED_MARKETS:
        errors.append("market must be one of a_share, hk_stock, hk_connect (港股通)")
        market = None

    validate_universe(strategy["universe"], market, errors)
    validate_data(strategy["data"], errors)
    validate_rule_group("entry", strategy["entry"], errors)
    validate_rule_group("exit", strategy["exit"], errors)
    validate_position(strategy["position"], errors)
    validate_risk(strategy["risk"], warnings, errors)
    validate_execution(strategy.get("execution", {}), warnings, errors)

    if not errors and (coverage or db_path):
        validate_data_coverage(strategy, db_path, warnings, errors, coverage)

    return ValidationResult(not errors, errors, warnings)


def require(obj: dict[str, Any], key: str, errors: list[str]) -> None:
    if key not in obj:
        errors.append(f"missing required field: {key}")


def validate_universe(universe: dict[str, Any], market: str | None, errors: list[str]) -> None:
    if universe.get("type") != "single":
        errors.append("universe.type must be single in MVP")
    symbols = universe.get("symbols")
    if not isinstance(symbols, list) or len(symbols) != 1:
        errors.append("universe.symbols must contain exactly one symbol")
        return
    symbol = symbols[0]
    if not isinstance(symbol, str) or not SYMBOL_PATTERN.match(normalize_symbol(symbol)):
        errors.append(f"invalid symbol: {symbol} (expected {SYMBOL_HINT.get(market or 'a_share')})")
        return
    if market and get_market_rule(load_rules(), normalize_symbol(symbol), market)[0] is None:
        errors.append(f"symbol {symbol} cannot be traded in market {market} ({SYMBOL_HINT[market]})")


def validate_data(data: dict[str, Any], errors: list[str]) -> None:
    frequency = data.get("frequency")
    if frequency not in SUPPORTED_FREQUENCIES:
        errors.append(f"unsupported frequency: {frequency}")
    if data.get("adjustment") not in {"forward", "backward", "none"}:
        errors.append("data.adjustment must be forward, backward, or none")
    start_date = data.get("start_date")
    end_date = data.get("end_date")
    if not start_date or not end_date:
        errors.append("data.start_date and data.end_date are required")
    elif start_date > end_date:
        errors.append("data.start_date must be earlier than or equal to data.end_date")


def validate_rule_group(name: str, group: dict[str, Any], errors: list[str]) -> None:
    if group.get("logic") not in {"all", "any"}:
        errors.append(f"{name}.logic must be all or any")
    conditions = group.get("conditions")
    if not isinstance(conditions, list) or not conditions:
        errors.append(f"{name}.conditions must contain at least one condition")
        return
    for index, condition in enumerate(conditions):
        validate_condition(f"{name}.conditions[{index}]", condition, errors)


def validate_condition(path: str, condition: dict[str, Any], errors: list[str]) -> None:
    operator = condition.get("operator")
    if operator not in SUPPORTED_OPERATORS:
        errors.append(f"{path}.operator is unsupported: {operator}")
    validate_expression(f"{path}.left", condition.get("left"), errors)
    validate_expression(f"{path}.right", condition.get("right"), errors)
    lookback = condition.get("lookback_bars")
    if lookback is not None and (not isinstance(lookback, int) or lookback <= 0):
        errors.append(f"{path}.lookback_bars must be a positive integer when provided")


def validate_expression(path: str, expr: Any, errors: list[str]) -> None:
    if not isinstance(expr, dict):
        errors.append(f"{path} must be an expression object")
        return
    expr_type = expr.get("type")
    if expr_type == "price":
        field = expr.get("field")
        if field not in SUPPORTED_PRICE_FIELDS:
            errors.append(f"{path}.field is unsupported: {field}")
    elif expr_type == "indicator":
        name = expr.get("name")
        if name not in SUPPORTED_INDICATORS:
            errors.append(f"{path}.name is unsupported: {name}")
        params = expr.get("params", {})
        if not isinstance(params, dict):
            errors.append(f"{path}.params must be an object")
        validate_indicator_params(path, name, params, errors)
    elif expr_type == "constant":
        if not isinstance(expr.get("value"), (int, float)):
            errors.append(f"{path}.value must be numeric for constant expressions")
    else:
        errors.append(f"{path}.type is unsupported: {expr_type}")


def validate_indicator_params(path: str, name: str, params: dict[str, Any], errors: list[str]) -> None:
    if name in {"MA", "EMA", "RSI", "VOLUME_MA", "RETURN", "VOLATILITY"}:
        period = params.get("period")
        if not isinstance(period, (int, float)) or period <= 0:
            errors.append(f"{path}.params.period must be positive for {name}")
    if name in {"MA", "EMA", "RSI", "RETURN", "VOLATILITY"}:
        field = params.get("field", "close")
        if field not in SUPPORTED_PRICE_FIELDS:
            errors.append(f"{path}.params.field is unsupported: {field}")
    if name == "MACD":
        for key in ("fast", "slow", "signal"):
            value = params.get(key)
            if value is not None and (not isinstance(value, (int, float)) or value <= 0):
                errors.append(f"{path}.params.{key} must be positive for MACD")
        if params.get("output", "macd") not in MACD_OUTPUTS:
            errors.append(f"{path}.params.output must be one of {sorted(MACD_OUTPUTS)} for MACD")
        if params.get("field", "close") not in SUPPORTED_PRICE_FIELDS:
            errors.append(f"{path}.params.field is unsupported: {params.get('field')}")
    if name == "BOLL":
        period = params.get("period")
        std = params.get("std")
        if not isinstance(period, (int, float)) or period <= 0:
            errors.append(f"{path}.params.period must be positive for BOLL")
        if std is not None and (not isinstance(std, (int, float)) or std <= 0):
            errors.append(f"{path}.params.std must be positive for BOLL")
        if params.get("output", "middle") not in BOLL_OUTPUTS:
            errors.append(f"{path}.params.output must be one of {sorted(BOLL_OUTPUTS)} for BOLL")
        if params.get("field", "close") not in SUPPORTED_PRICE_FIELDS:
            errors.append(f"{path}.params.field is unsupported: {params.get('field')}")


def validate_position(position: dict[str, Any], errors: list[str]) -> None:
    initial_cash = position.get("initial_cash")
    order_size_value = position.get("order_size_value")
    max_position_pct = position.get("max_position_pct")
    if not isinstance(initial_cash, (int, float)) or initial_cash <= 0:
        errors.append("position.initial_cash must be positive")
    if position.get("order_size_type") != "cash_pct":
        errors.append("position.order_size_type must be cash_pct in MVP")
    if not isinstance(order_size_value, (int, float)) or not 0 < order_size_value <= 1:
        errors.append("position.order_size_value must be in (0, 1]")
    if not isinstance(max_position_pct, (int, float)) or not 0 < max_position_pct <= 1:
        errors.append("position.max_position_pct must be in (0, 1]")
    if isinstance(order_size_value, (int, float)) and isinstance(max_position_pct, (int, float)):
        if order_size_value > max_position_pct:
            errors.append("position.order_size_value cannot exceed max_position_pct")


def validate_risk(risk: dict[str, Any], warnings: list[str], errors: list[str]) -> None:
    for key in ("stop_loss_pct", "take_profit_pct", "max_drawdown_pct"):
        value = risk.get(key)
        if value is not None and (not isinstance(value, (int, float)) or value <= 0):
            errors.append(f"risk.{key} must be positive or null")
    if risk.get("stop_loss_pct") is None:
        warnings.append("risk.stop_loss_pct is null; strategy has no fixed stop loss")
    if risk.get("max_drawdown_pct") is None:
        warnings.append("risk.max_drawdown_pct is null; strategy has no max drawdown stop")
    max_holding_bars = risk.get("max_holding_bars")
    if max_holding_bars is not None and (not isinstance(max_holding_bars, int) or max_holding_bars <= 0):
        errors.append("risk.max_holding_bars must be a positive integer or null")


def validate_execution(execution: dict[str, Any], warnings: list[str], errors: list[str]) -> None:
    for key in ("entry_price", "exit_price"):
        mode = execution.get(key, "next_open")
        if mode not in SUPPORTED_EXECUTION_MODES:
            errors.append(f"execution.{key} must be next_open or current_close")
        elif mode == "current_close":
            warnings.append(f"execution.{key}=current_close fills at the signal bar's close (closing-auction assumption)")
    for key in ("fee_rate", "commission_rate", "min_commission", "slippage_rate", "fx_spread", "fx_rate"):
        value = execution.get(key)
        if value is not None and (not isinstance(value, (int, float)) or value < 0):
            errors.append(f"execution.{key} must be a non-negative number")
    if execution.get("fee_rate") is not None and execution.get("commission_rate") is None:
        warnings.append("execution.fee_rate is treated as the broker commission rate; stamp duty and exchange fees come from market rules")


def coverage_from_sqlite(db_path: Path) -> CoverageFn:
    def coverage(symbol: str, frequency: str, start_date: str, end_date: str) -> tuple[int, str | None, str | None]:
        with sqlite3.connect(db_path) as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS rows, MIN(trade_time) AS start_time, MAX(trade_time) AS end_time
                FROM bars
                WHERE symbol = ? AND frequency = ? AND trade_time >= ? AND trade_time <= ?
                """,
                (symbol, frequency, start_date, end_date if len(end_date) > 10 else f"{end_date} 23:59:59"),
            ).fetchone()
        return int(row[0]), row[1], row[2]

    return coverage


def validate_data_coverage(
    strategy: dict[str, Any],
    db_path: Path | None,
    warnings: list[str],
    errors: list[str],
    coverage: CoverageFn | None = None,
) -> None:
    symbol = normalize_symbol(strategy["universe"]["symbols"][0])
    frequency = strategy["data"]["frequency"]
    start_date = strategy["data"]["start_date"]
    end_date = strategy["data"]["end_date"]

    if coverage is None:
        if db_path is None or not Path(db_path).exists():
            warnings.append(f"data coverage skipped; database does not exist: {db_path}")
            return
        coverage = coverage_from_sqlite(Path(db_path))

    rows, start_time, end_time = coverage(symbol, frequency, start_date, end_date)
    if rows == 0:
        errors.append(f"no market data found for {symbol} {frequency} from {start_date} to {end_date}")
    else:
        warnings.append(f"data coverage: {rows} bars from {start_time} to {end_time}")
        if rows < 120:
            warnings.append(f"only {rows} bars available; backtest results will not be statistically meaningful")


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate AQuant strategy DSL")
    parser.add_argument("strategy_path")
    parser.add_argument("--db", help="Optional market data SQLite path for coverage validation")
    args = parser.parse_args()

    strategy = load_strategy(Path(args.strategy_path))
    result = validate_strategy(strategy, Path(args.db) if args.db else None)
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    if not result.ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
