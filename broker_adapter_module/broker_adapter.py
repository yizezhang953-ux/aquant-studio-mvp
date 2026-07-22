from __future__ import annotations

import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from market_rules_module.market_rules import calculate_fee_breakdown, read_json as read_market_rules_json


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass
class BrokerOrderAck:
    broker_order_id: str
    gateway_order_id: str
    status: str
    message: str
    acknowledged_at: str


@dataclass
class BrokerFill:
    fill_id: str
    broker_order_id: str
    gateway_order_id: str
    symbol: str
    side: str
    quantity: int
    fill_price: float
    amount: float
    fee: float
    fee_details: dict[str, float]
    filled_at: str


class BrokerAdapter(ABC):
    @abstractmethod
    def query_account(self) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def query_positions(self) -> dict[str, int]:
        raise NotImplementedError

    @abstractmethod
    def submit_order(self, order: Any) -> tuple[BrokerOrderAck, BrokerFill | None]:
        raise NotImplementedError

    @abstractmethod
    def cancel_order(self, broker_order_id: str) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def query_order(self, broker_order_id: str) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def query_fills(self, broker_order_id: str | None = None) -> list[BrokerFill]:
        raise NotImplementedError


class SandboxBrokerAdapter(BrokerAdapter):
    def __init__(self, config: dict[str, Any], account_state: dict[str, Any]):
        self.config = config
        self.account_state = account_state
        self.orders: dict[str, dict[str, Any]] = {}
        self.fills: list[BrokerFill] = []
        rules_path = ROOT / config.get("market_rules_path", "market_rules_module/configs/market_rules.json")
        self.market_rules = read_market_rules_json(rules_path)

    def query_account(self) -> dict[str, Any]:
        return dict(self.account_state)

    def query_positions(self) -> dict[str, int]:
        return dict(self.account_state.get("positions", {}))

    def submit_order(self, order: Any) -> tuple[BrokerOrderAck, BrokerFill | None]:
        broker_order_id = f"SANDBOX-{order.gateway_order_id}"
        ack = BrokerOrderAck(
            broker_order_id=broker_order_id,
            gateway_order_id=order.gateway_order_id,
            status="accepted",
            message="sandbox adapter accepted order",
            acknowledged_at=now_iso(),
        )
        self.orders[broker_order_id] = {
            "broker_order_id": broker_order_id,
            "gateway_order_id": order.gateway_order_id,
            "status": "accepted",
            "symbol": order.symbol,
            "side": order.side,
            "quantity": order.quantity,
        }
        fill = self._fill_order(order, broker_order_id)
        self.orders[broker_order_id]["status"] = "filled"
        return ack, fill

    def _fill_order(self, order: Any, broker_order_id: str) -> BrokerFill:
        account = self.config["account"]
        slippage_rate = float(account["slippage_rate"])
        if order.side == "buy":
            fill_price = order.estimated_price * (1 + slippage_rate)
        else:
            fill_price = order.estimated_price * (1 - slippage_rate)
        amount = order.quantity * fill_price
        fee_breakdown = calculate_fee_breakdown(self.market_rules, order.symbol, order.side, amount)
        fee = fee_breakdown.total_fee
        positions = self.account_state.setdefault("positions", {})
        current_qty = int(positions.get(order.symbol, 0))

        if order.side == "buy":
            self.account_state["cash"] -= amount + fee
            positions[order.symbol] = current_qty + order.quantity
        else:
            self.account_state["cash"] += amount - fee
            positions[order.symbol] = current_qty - order.quantity

        self.account_state["cash"] = round(self.account_state["cash"], 6)
        fill = BrokerFill(
            fill_id=f"FILL-{order.gateway_order_id}",
            broker_order_id=broker_order_id,
            gateway_order_id=order.gateway_order_id,
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            fill_price=round(fill_price, 6),
            amount=round(amount, 6),
            fee=round(fee, 6),
            fee_details=fee_breakdown.components,
            filled_at=now_iso(),
        )
        self.fills.append(fill)
        return fill

    def cancel_order(self, broker_order_id: str) -> dict[str, Any]:
        order = self.orders.get(broker_order_id)
        if not order:
            return {"broker_order_id": broker_order_id, "status": "not_found"}
        if order["status"] == "filled":
            return {"broker_order_id": broker_order_id, "status": "cannot_cancel_filled"}
        order["status"] = "canceled"
        return {"broker_order_id": broker_order_id, "status": "canceled"}

    def query_order(self, broker_order_id: str) -> dict[str, Any]:
        return self.orders.get(broker_order_id, {"broker_order_id": broker_order_id, "status": "not_found"})

    def query_fills(self, broker_order_id: str | None = None) -> list[BrokerFill]:
        if broker_order_id is None:
            return list(self.fills)
        return [fill for fill in self.fills if fill.broker_order_id == broker_order_id]
