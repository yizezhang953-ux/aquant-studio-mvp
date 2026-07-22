from __future__ import annotations

import json
import math
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass
class MarketRuleCheck:
    market: str | None
    accepted: bool
    reasons: list[str]
    facts: dict[str, Any]


@dataclass
class FeeBreakdown:
    market: str
    side: str
    gross_amount: float
    total_fee: float
    components: dict[str, float]


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def infer_market(symbol: str, rules: dict[str, Any]) -> str | None:
    for market, rule in rules.get("markets", {}).items():
        if re.match(rule["symbol_pattern"], symbol):
            return market
    return None


def get_market_rule(rules: dict[str, Any], symbol: str) -> tuple[str | None, dict[str, Any] | None]:
    market = infer_market(symbol, rules)
    if market is None:
        return None, None
    return market, rules["markets"][market]


def board_lot_size(rule: dict[str, Any], symbol: str) -> int:
    board_lots = rule.get("board_lots", {})
    return int(board_lots.get(symbol, rule.get("default_board_lot", 1)))


def validate_market_order(rules: dict[str, Any], order: dict[str, Any], account_state: dict[str, Any]) -> MarketRuleCheck:
    reasons: list[str] = []
    facts: dict[str, Any] = {}
    symbol = str(order.get("symbol", ""))
    side = order.get("side")
    order_type = order.get("order_type")
    quantity = order.get("quantity")

    market, rule = get_market_rule(rules, symbol)
    if market is None or rule is None:
        return MarketRuleCheck(None, False, [f"unsupported market symbol: {symbol}"], facts)

    facts["market"] = market
    facts["market_name"] = rule.get("name", market)
    allowed_order_types = rule.get("allowed_order_types", [])
    if order_type not in allowed_order_types:
        reasons.append(f"order_type {order_type} is not allowed for {market}")

    if not isinstance(quantity, int) or quantity <= 0:
        reasons.append("quantity must be a positive integer before market rule checks")
        return MarketRuleCheck(market, False, reasons, facts)

    if market == "a_share":
        buy_lot = int(rule.get("buy_lot_size", 100))
        sell_lot = int(rule.get("sell_lot_size", 1))
        if side == "buy" and quantity % buy_lot != 0:
            reasons.append(f"A-share buy quantity must be a multiple of {buy_lot}")
        if side == "sell" and quantity % sell_lot != 0:
            reasons.append(f"A-share sell quantity must be a multiple of {sell_lot}")
        if side == "sell" and rule.get("t_plus_one", True):
            available_positions = account_state.get("available_positions", account_state.get("positions", {}))
            sellable_qty = int(available_positions.get(symbol, 0))
            facts["sellable_quantity"] = sellable_qty
            if quantity > sellable_qty:
                reasons.append("A-share T+1 rule rejects selling more than sellable quantity")

    if market == "hk_stock":
        lot = board_lot_size(rule, symbol)
        facts["board_lot_size"] = lot
        if quantity % lot != 0:
            reasons.append(f"Hong Kong stock quantity must be a multiple of board lot {lot}")
        max_board_lots = int(rule.get("max_board_lots_per_order", 3000))
        if quantity > lot * max_board_lots:
            reasons.append(f"Hong Kong stock order exceeds {max_board_lots} board lots")

    price_controls = rule.get("price_controls", {})
    if price_controls.get("require_limit_fields"):
        market_snapshot = order.get("market_snapshot", {})
        lower = market_snapshot.get("limit_down")
        upper = market_snapshot.get("limit_up")
        estimated_price = order.get("estimated_price")
        if not isinstance(lower, (int, float)) or not isinstance(upper, (int, float)):
            reasons.append("price limit fields are required for this market")
        elif isinstance(estimated_price, (int, float)) and not (float(lower) <= float(estimated_price) <= float(upper)):
            reasons.append("estimated_price is outside configured price limit bounds")

    return MarketRuleCheck(market, not reasons, reasons, facts)


def round_cent(value: float) -> float:
    return round(value + 1e-12, 2)


def calculate_fee_breakdown(rules: dict[str, Any], symbol: str, side: str, gross_amount: float) -> FeeBreakdown:
    market, rule = get_market_rule(rules, symbol)
    if market is None or rule is None:
        return FeeBreakdown("unknown", side, round(gross_amount, 6), 0.0, {})

    components: dict[str, float] = {}
    fee_model = rule.get("fee_model", {})

    if market == "a_share":
        commission = max(gross_amount * float(fee_model.get("commission_rate", 0)), float(fee_model.get("min_commission", 0)))
        components["commission"] = round_cent(commission)
        components["transfer_fee"] = round_cent(gross_amount * float(fee_model.get("transfer_fee_rate", 0)))
        if side == "sell":
            components["stamp_duty"] = round_cent(gross_amount * float(fee_model.get("stamp_duty_sell_rate", 0)))

    if market == "hk_stock":
        components["brokerage"] = round_cent(gross_amount * float(fee_model.get("brokerage_rate", 0)))
        components["sfc_transaction_levy"] = round_cent(gross_amount * float(fee_model.get("sfc_transaction_levy_rate", 0)))
        components["afrc_transaction_levy"] = round_cent(gross_amount * float(fee_model.get("afrc_transaction_levy_rate", 0)))
        components["trading_fee"] = round_cent(gross_amount * float(fee_model.get("trading_fee_rate", 0)))
        if fee_model.get("stamp_duty_rate", 0):
            components["stamp_duty"] = float(math.ceil(gross_amount * float(fee_model["stamp_duty_rate"])))
        if side == "sell" and fee_model.get("transfer_deed_stamp_duty"):
            components["transfer_deed_stamp_duty"] = float(fee_model["transfer_deed_stamp_duty"])

    total_fee = round(sum(components.values()), 6)
    return FeeBreakdown(market, side, round(gross_amount, 6), total_fee, components)


def validate_rules_file(path: Path) -> dict[str, Any]:
    rules = read_json(path)
    markets = rules.get("markets", {})
    checks = []
    for market, rule in markets.items():
        checks.append(
            {
                "market": market,
                "has_symbol_pattern": bool(rule.get("symbol_pattern")),
                "has_order_types": bool(rule.get("allowed_order_types")),
                "has_fee_model": bool(rule.get("fee_model")),
            }
        )
    return {"ok": all(all(item.values()) for item in checks), "markets": checks}


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Validate AQuant market rules")
    parser.add_argument("--rules", default="market_rules_module/configs/market_rules.json")
    args = parser.parse_args()
    print(json.dumps(validate_rules_file(Path(args.rules)), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
