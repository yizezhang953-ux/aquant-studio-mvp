"""Market rules for A-shares, Hong Kong stocks (direct) and Southbound Stock Connect (港股通).

One module answers every "what does this market allow / cost" question for the backtest engine,
paper traders, the trading gateway and the web backend:

* which market a symbol belongs to (``a_share`` / ``hk_stock``) and the channel it is traded
  through (``hk_connect`` for 港股通);
* lot rules (A-share 100-share lots, STAR 200-share minimum, HK per-stock board lots);
* daily price limits by board (main 10%, ST 5%, ChiNext/STAR 20%, BSE 30%; HK has none);
* T+1 (A-share) vs T+0 (HK and 港股通);
* fees by component, with date-dependent schedules (e.g. A-share stamp duty cut on 2023-08-28);
* dividend withholding tax (A-share holding-period tiers, 港股通 20% flat by default).

Values live in ``configs/market_rules.json``; nothing here is broker-confirmed.
"""
from __future__ import annotations

import copy
import json
import math
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any


DEFAULT_RULES_PATH = Path(__file__).resolve().parent / "configs" / "market_rules.json"
MARKET_KEYS = ("a_share", "hk_stock", "hk_connect")
MARKET_ALIASES = {
    "a": "a_share", "ashare": "a_share", "a_share": "a_share", "cn": "a_share",
    "hk": "hk_stock", "hk_stock": "hk_stock", "hkex": "hk_stock",
    "hk_connect": "hk_connect", "connect": "hk_connect", "southbound": "hk_connect", "港股通": "hk_connect",
}


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


@dataclass(frozen=True)
class LotRule:
    buy_min_qty: int
    buy_step: int
    sell_odd_lot_allowed: bool
    lot_size: int
    lot_source: str  # "instrument", "config", "board", "default"


# --------------------------------------------------------------------------- loading


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


@lru_cache(maxsize=8)
def _cached_rules(path: str) -> dict[str, Any]:
    return read_json(Path(path))


def load_rules(path: str | Path | None = None) -> dict[str, Any]:
    """Load (and cache) the rules file. Returns a deep copy so callers may mutate it."""
    return copy.deepcopy(_cached_rules(str(Path(path or DEFAULT_RULES_PATH).resolve())))


def normalize_market(market: str | None) -> str | None:
    if market is None:
        return None
    return MARKET_ALIASES.get(str(market).strip().lower(), MARKET_ALIASES.get(str(market).strip()))


def normalize_symbol(symbol: str) -> str:
    """'700.hk' -> '00700.HK', 'sh600519' -> '600519.SH', '600519' -> '600519.SH'."""
    text = str(symbol or "").strip().upper()
    match = re.fullmatch(r"(SH|SZ|BJ|HK)(\d+)", text)
    if match:
        text = f"{match.group(2)}.{match.group(1)}"
    if re.fullmatch(r"\d+\.HK", text):
        code = text.split(".")[0].lstrip("0") or "0"
        return f"{code.zfill(5)}.HK"
    if re.fullmatch(r"\d{6}", text):
        if text.startswith(("4", "8", "92")):
            return f"{text}.BJ"
        if text.startswith(("6", "9")):
            return f"{text}.SH"
        return f"{text}.SZ"
    return text


def exchange_of(symbol: str) -> str:
    return symbol.rsplit(".", 1)[-1].upper() if "." in symbol else ""


def infer_market(symbol: str, rules: dict[str, Any]) -> str | None:
    """Market by listing venue: 'a_share' or 'hk_stock' (never 'hk_connect', which is a channel)."""
    for market, rule in rules.get("markets", {}).items():
        if rule.get("underlying_market"):
            continue
        if re.match(rule["symbol_pattern"], symbol):
            return market
    return None


def _merged_rule(rules: dict[str, Any], market: str) -> dict[str, Any]:
    markets = rules.get("markets", {})
    rule = markets[market]
    base_key = rule.get("underlying_market")
    if not base_key or base_key not in markets:
        return rule
    merged = copy.deepcopy(markets[base_key])
    for key, value in rule.items():
        merged[key] = copy.deepcopy(value)
    return merged


def get_market_rule(
    rules: dict[str, Any], symbol: str, market: str | None = None
) -> tuple[str | None, dict[str, Any] | None]:
    """Resolve the rule set used for ``symbol``.

    ``market`` may name a channel ('hk_connect'); it must be compatible with the symbol's venue.
    """
    venue = infer_market(symbol, rules)
    requested = normalize_market(market) if market else None
    if requested is None:
        if venue is None:
            return None, None
        return venue, _merged_rule(rules, venue)
    if requested not in rules.get("markets", {}):
        return None, None
    rule = rules["markets"][requested]
    expected_venue = rule.get("underlying_market", requested)
    if venue != expected_venue:
        return None, None
    return requested, _merged_rule(rules, requested)


# --------------------------------------------------------------------------- date-effective values


def _in_range(trade_date: str | None, entry: dict[str, Any]) -> bool:
    if not trade_date:
        return False
    day = str(trade_date)[:10]
    start = entry.get("from")
    until = entry.get("until")
    return (start is None or day >= start) and (until is None or day <= until)


def effective_fee_model(rule: dict[str, Any], trade_date: str | None = None) -> dict[str, Any]:
    fee_model = dict(rule.get("fee_model", {}))
    for entry in rule.get("history", []):
        if _in_range(trade_date, entry):
            fee_model.update(entry.get("fee_model", {}))
    return fee_model


def board_for(rule: dict[str, Any], symbol: str) -> dict[str, Any] | None:
    for board in rule.get("boards", []):
        if re.search(board["pattern"], symbol):
            return board
    return None


def is_st_name(name: str | None) -> bool:
    return bool(name) and "ST" in str(name).upper()


def price_limit_pct(
    rule: dict[str, Any], symbol: str, name: str | None = None, trade_date: str | None = None
) -> float | None:
    """Daily price-limit fraction (0.10 = ±10%), or None when the market has no daily limit."""
    board = board_for(rule, symbol)
    if board is None or "price_limit_pct" not in board:
        return None
    values = {"price_limit_pct": board.get("price_limit_pct"), "st_price_limit_pct": board.get("st_price_limit_pct")}
    for entry in board.get("price_limit_history", []):
        if _in_range(trade_date, entry):
            values.update({k: v for k, v in entry.items() if k.endswith("price_limit_pct")})
    if is_st_name(name) and values.get("st_price_limit_pct") is not None:
        return float(values["st_price_limit_pct"])
    return float(values["price_limit_pct"]) if values.get("price_limit_pct") is not None else None


def limit_prices(reference_price: float, pct: float | None, tick: float = 0.01) -> tuple[float | None, float | None]:
    """(limit_down, limit_up) rounded to the tick, as exchanges publish them."""
    if pct is None or reference_price <= 0:
        return None, None
    up = math.floor(reference_price * (1 + pct) / tick + 0.5 + 1e-9) * tick
    down = math.floor(reference_price * (1 - pct) / tick + 0.5 + 1e-9) * tick
    return round(down, 4), round(up, 4)


def board_lot_size(rule: dict[str, Any], symbol: str) -> int:
    board_lots = rule.get("board_lots", {})
    return int(board_lots.get(symbol, rule.get("default_board_lot", 1)))


def lot_rule(rule: dict[str, Any], symbol: str, instrument_lot_size: int | None = None) -> LotRule:
    """How many shares may be bought/sold. ``instrument_lot_size`` (from the data feed) wins for HK."""
    board = board_for(rule, symbol)
    if board is not None:  # A-share boards
        return LotRule(
            buy_min_qty=int(board.get("buy_min_qty", 100)),
            buy_step=int(board.get("buy_step", 100)),
            sell_odd_lot_allowed=bool(rule.get("allow_odd_lot_sell", True)),
            lot_size=int(board.get("buy_step", 100)),
            lot_source="board",
        )
    if instrument_lot_size and int(instrument_lot_size) > 0:
        lot, source = int(instrument_lot_size), "instrument"
    elif symbol in rule.get("board_lots", {}):
        lot, source = int(rule["board_lots"][symbol]), "config"
    else:
        lot, source = int(rule.get("default_board_lot", 1)), "default"
    return LotRule(lot, lot, bool(rule.get("allow_odd_lot_sell", True)), lot, source)


def round_buy_quantity(lot: LotRule, quantity: float) -> int:
    quantity = int(math.floor(quantity + 1e-9))
    if quantity < lot.buy_min_qty:
        return 0
    extra = (quantity - lot.buy_min_qty) // lot.buy_step * lot.buy_step
    return lot.buy_min_qty + extra


def dividend_tax_rate(rule: dict[str, Any], symbol: str, holding_days: int | None = None) -> float:
    config = rule.get("dividend_tax", {})
    overrides = config.get("overrides", {})
    if symbol in overrides:
        return float(overrides[symbol])
    if config.get("mode") == "holding_period":
        days = holding_days if holding_days is not None else 0
        for tier in config.get("tiers", []):
            if tier.get("max_days") is None or days <= int(tier["max_days"]):
                return float(tier["rate"])
        return 0.0
    return float(config.get("rate", 0.0))


def is_connect_eligible(rule: dict[str, Any], symbol: str, instrument_flag: bool | None = None) -> bool | None:
    """True/False when known; None when eligibility is not configured (cannot be checked)."""
    if instrument_flag is not None:
        return bool(instrument_flag)
    eligible = rule.get("eligible_symbols") or []
    if not eligible:
        return None
    return symbol in eligible


# --------------------------------------------------------------------------- fees


def round_cent(value: float) -> float:
    return round(value + 1e-12, 2)


def calculate_fee_breakdown(
    rules: dict[str, Any],
    symbol: str,
    side: str,
    gross_amount: float,
    market: str | None = None,
    trade_date: str | None = None,
    overrides: dict[str, Any] | None = None,
) -> FeeBreakdown:
    """Fees for one fill, in the quote currency (CNY for A-shares, HKD for HK and 港股通).

    ``overrides`` replaces fee_model keys (e.g. a strategy's own ``commission_rate``).
    """
    resolved, rule = get_market_rule(rules, symbol, market)
    if resolved is None or rule is None:
        return FeeBreakdown("unknown", side, round(gross_amount, 6), 0.0, {})

    fee_model = effective_fee_model(rule, trade_date)
    if overrides:
        fee_model.update({k: v for k, v in overrides.items() if v is not None})
    components: dict[str, float] = {}
    rate = lambda key: float(fee_model.get(key, 0) or 0)  # noqa: E731

    if resolved == "a_share":
        components["commission"] = round_cent(max(gross_amount * rate("commission_rate"), rate("min_commission")))
        components["transfer_fee"] = round_cent(gross_amount * rate("transfer_fee_rate"))
        if side == "sell":
            components["stamp_duty"] = round_cent(gross_amount * rate("stamp_duty_sell_rate"))
    else:  # hk_stock and hk_connect share HKEX statutory fees
        if resolved == "hk_connect":
            components["commission"] = round_cent(max(gross_amount * rate("commission_rate"), rate("min_commission")))
        else:
            components["brokerage"] = round_cent(max(gross_amount * rate("brokerage_rate"), rate("min_brokerage")))
        components["sfc_transaction_levy"] = round_cent(gross_amount * rate("sfc_transaction_levy_rate"))
        components["afrc_transaction_levy"] = round_cent(gross_amount * rate("afrc_transaction_levy_rate"))
        components["trading_fee"] = round_cent(gross_amount * rate("trading_fee_rate"))
        if rate("settlement_fee_rate"):
            fee = gross_amount * rate("settlement_fee_rate")
            if fee_model.get("min_settlement_fee") is not None:
                fee = max(fee, rate("min_settlement_fee"))
            if fee_model.get("max_settlement_fee"):
                fee = min(fee, rate("max_settlement_fee"))
            components["settlement_fee"] = round_cent(fee)
        if rate("stamp_duty_rate"):
            # HK stamp duty is charged on both sides and rounded up to the whole dollar.
            components["stamp_duty"] = float(math.ceil(gross_amount * rate("stamp_duty_rate") - 1e-9))

    total_fee = round(sum(components.values()), 6)
    return FeeBreakdown(resolved, side, round(gross_amount, 6), total_fee, components)


def estimated_fee_rate(rules: dict[str, Any], symbol: str, side: str, market: str | None = None,
                       trade_date: str | None = None, overrides: dict[str, Any] | None = None) -> float:
    """Proportional fee rate (ignores minimums) — used for sizing an order before the fill."""
    resolved, rule = get_market_rule(rules, symbol, market)
    if rule is None:
        return 0.0
    fee_model = effective_fee_model(rule, trade_date)
    if overrides:
        fee_model.update({k: v for k, v in overrides.items() if v is not None})
    keys = ["commission_rate", "brokerage_rate", "transfer_fee_rate", "sfc_transaction_levy_rate",
            "afrc_transaction_levy_rate", "trading_fee_rate", "settlement_fee_rate", "stamp_duty_rate"]
    if side == "sell":
        keys.append("stamp_duty_sell_rate")
    return sum(float(fee_model.get(key, 0) or 0) for key in keys) + 0.0005


# --------------------------------------------------------------------------- order checks


def validate_market_order(rules: dict[str, Any], order: dict[str, Any], account_state: dict[str, Any]) -> MarketRuleCheck:
    """Pre-trade checks for one order.

    The order may carry ``market`` (or ``channel``) = 'hk_connect' to trade an HK stock via 港股通,
    ``lot_size`` (board lot from the data feed), ``name`` (for ST detection) and
    ``market_snapshot`` with ``limit_up``/``limit_down`` or ``prev_close``.
    """
    reasons: list[str] = []
    facts: dict[str, Any] = {}
    symbol = str(order.get("symbol", ""))
    side = order.get("side")
    order_type = order.get("order_type")
    quantity = order.get("quantity")
    channel = order.get("market") or order.get("channel")

    market, rule = get_market_rule(rules, symbol, channel)
    if market is None or rule is None:
        detail = f" via {channel}" if channel else ""
        return MarketRuleCheck(None, False, [f"unsupported market symbol: {symbol}{detail}"], facts)

    facts["market"] = market
    facts["market_name"] = rule.get("name", market)
    facts["currency"] = rule.get("currency")
    allowed_order_types = rule.get("allowed_order_types", [])
    if order_type not in allowed_order_types:
        reasons.append(f"order_type {order_type} is not allowed for {market}")

    if not isinstance(quantity, int) or quantity <= 0:
        reasons.append("quantity must be a positive integer before market rule checks")
        return MarketRuleCheck(market, False, reasons, facts)

    lot = lot_rule(rule, symbol, order.get("lot_size"))
    facts["board_lot_size"] = lot.lot_size
    facts["lot_source"] = lot.lot_source
    if side == "buy":
        if quantity < lot.buy_min_qty:
            reasons.append(f"buy quantity must be at least {lot.buy_min_qty}")
        elif (quantity - lot.buy_min_qty) % lot.buy_step != 0:
            if market == "a_share":
                reasons.append(f"A-share buy quantity must be a multiple of {lot.buy_step}")
            else:
                reasons.append(f"Hong Kong stock quantity must be a multiple of board lot {lot.lot_size}")
    elif side == "sell" and not lot.sell_odd_lot_allowed and quantity % lot.lot_size != 0:
        reasons.append(f"sell quantity must be a multiple of {lot.lot_size}")

    max_board_lots = rule.get("max_board_lots_per_order")
    if market != "a_share" and max_board_lots and quantity > lot.lot_size * int(max_board_lots):
        reasons.append(f"Hong Kong stock order exceeds {max_board_lots} board lots")

    if side == "sell":
        positions = account_state.get("available_positions", account_state.get("positions", {})) if rule.get("t_plus_one") else account_state.get("positions", {})
        sellable_qty = int(positions.get(symbol, 0))
        facts["sellable_quantity"] = sellable_qty
        if quantity > sellable_qty:
            if rule.get("t_plus_one"):
                reasons.append("A-share T+1 rule rejects selling more than sellable quantity")
            else:
                reasons.append("sell quantity exceeds position")

    if market == "hk_connect":
        eligible = is_connect_eligible(rule, symbol, order.get("connect_eligible"))
        facts["connect_eligible"] = eligible
        if eligible is False and side == "buy":
            reasons.append(f"{symbol} is not eligible for Southbound Stock Connect buying")

    snapshot = order.get("market_snapshot", {}) or {}
    lower, upper = snapshot.get("limit_down"), snapshot.get("limit_up")
    pct = price_limit_pct(rule, symbol, order.get("name"), order.get("trade_date"))
    if pct is not None and (lower is None or upper is None) and isinstance(snapshot.get("prev_close"), (int, float)):
        lower, upper = limit_prices(float(snapshot["prev_close"]), pct)
    facts["price_limit_pct"] = pct
    estimated_price = order.get("estimated_price")
    if rule.get("price_controls", {}).get("require_limit_fields") and not (
        isinstance(lower, (int, float)) and isinstance(upper, (int, float))
    ):
        reasons.append("price limit fields are required for this market")
    elif isinstance(lower, (int, float)) and isinstance(upper, (int, float)) and isinstance(estimated_price, (int, float)):
        if not float(lower) <= float(estimated_price) <= float(upper):
            reasons.append("estimated_price is outside configured price limit bounds")

    return MarketRuleCheck(market, not reasons, reasons, facts)


def validate_rules_file(path: Path) -> dict[str, Any]:
    rules = read_json(path)
    checks = []
    for market in rules.get("markets", {}):
        rule = _merged_rule(rules, market)
        checks.append(
            {
                "market": market,
                "has_symbol_pattern": bool(rule.get("symbol_pattern")),
                "has_order_types": bool(rule.get("allowed_order_types")),
                "has_fee_model": bool(rule.get("fee_model")),
                "has_currency": bool(rule.get("currency")),
            }
        )
    return {"ok": all(all(v for k, v in item.items() if k != "market") for item in checks), "markets": checks}


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Validate AQuant market rules")
    parser.add_argument("--rules", default=str(DEFAULT_RULES_PATH))
    args = parser.parse_args()
    print(json.dumps(validate_rules_file(Path(args.rules)), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
