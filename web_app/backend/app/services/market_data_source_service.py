"""Market-data providers for the sync endpoint.

* ``tencent``  real daily bars for A-shares (SH/SZ/BJ) and HK stocks: raw prices, adj_factor and
               inferred dividend/bonus events; for HK symbols also HKD->CNY rates (Frankfurter/ECB)
               so 港股通 backtests convert currency per day. No token required.
* ``demo``     deterministic synthetic bars for offline development and tests (not market data).
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Callable, Protocol

from app.core.config import settings
from app.schemas.market import MarketBarImport, MarketInstrumentImport
from app.services.legacy_paths import REPO_ROOT
from app.services.market_service import market_for_symbol, normalize_symbol

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from data_module.sources import fx as fx_source  # noqa: E402
from data_module.sources import hkex, tencent  # noqa: E402


@dataclass(frozen=True)
class DataSourceInfo:
    provider_id: str
    name: str
    market: str
    status: str
    auth_required: bool
    supported_frequencies: list[str]
    note: str


@dataclass(frozen=True)
class DataSourcePayload:
    instrument: MarketInstrumentImport
    bars: list[MarketBarImport]
    corporate_actions: list[dict[str, Any]] = field(default_factory=list)
    fx_rates: dict[str, float] = field(default_factory=dict)
    fx_pair: str = "HKDCNY"
    source: str = ""


class MarketDataProvider(Protocol):
    provider_id: str

    def info(self) -> DataSourceInfo: ...

    def fetch_bars(self, *, symbol: str, start_date: str, end_date: str, frequency: str) -> DataSourcePayload: ...


def _check_dates(start_date: str, end_date: str) -> None:
    if date.fromisoformat(start_date) > date.fromisoformat(end_date):
        raise ValueError("start_date must be before or equal to end_date")


class TencentProvider:
    provider_id = "tencent"
    # Injected in tests; defaults call the live public endpoints.
    fetch_json: Callable[[str, dict[str, Any]], Any] | None = None
    fetch_name: Callable[[str], str | None] | None = None
    fetch_fx: Callable[[str, str], dict[str, float]] | None = None

    def info(self) -> DataSourceInfo:
        return DataSourceInfo(
            provider_id=self.provider_id,
            name="Tencent quotes (A-share + HK) / ECB HKD-CNY",
            market="a_share,hk_stock,hk_connect",
            status="ready" if settings.market_data_network_enabled else "disabled",
            auth_required=False,
            supported_frequencies=["1d"],
            note="Raw daily OHLCV with forward-adjust factor and inferred dividends; HK symbols also load "
                 "HKD/CNY rates for 港股通. Unofficial public endpoints — verify important figures.",
        )

    def fetch_bars(self, *, symbol: str, start_date: str, end_date: str, frequency: str) -> DataSourcePayload:
        if not settings.market_data_network_enabled:
            raise ValueError("network data sources are disabled (MARKET_DATA_NETWORK_ENABLED=false)")
        if frequency != "1d":
            raise ValueError("tencent provider supports 1d bars; import intraday bars as CSV")
        _check_dates(start_date, end_date)
        symbol = normalize_symbol(symbol)
        market, exchange = market_for_symbol(symbol)
        try:
            result = tencent.fetch_daily_with_actions(symbol, start_date, end_date, fetch=self.fetch_json)
        except RuntimeError as exc:
            raise ValueError(f"tencent request failed: {exc}") from exc
        if not result["bars"]:
            raise ValueError(f"tencent returned no bars for {symbol} {start_date}..{end_date}")
        name = (self.fetch_name or tencent.fetch_name)(symbol) or symbol
        currency = "HKD" if market == "hk_stock" else "CNY"
        rates: dict[str, float] = {}
        if market == "hk_stock":
            fetch_fx = self.fetch_fx or (lambda a, b: fx_source.fetch_rates_by_year("HKD", "CNY", a, b))
            try:
                rates = fetch_fx(start_date, end_date)
            except Exception:
                rates = {}  # bars are still useful for hk_stock; 港股通 falls back to the default rate
        return DataSourcePayload(
            instrument=MarketInstrumentImport(symbol=symbol, name=name, market=market, exchange=exchange,
                                              currency=currency),
            bars=[MarketBarImport(**bar) for bar in result["bars"]],
            corporate_actions=[{**a, "currency": currency} for a in result["actions"]],
            fx_rates=rates,
            source="tencent_derived",
        )


class DemoProvider:
    provider_id = "demo"

    def info(self) -> DataSourceInfo:
        return DataSourceInfo(
            provider_id=self.provider_id,
            name="Synthetic demo bars",
            market="a_share,hk_stock,hk_connect",
            status="ready",
            auth_required=False,
            supported_frequencies=["1d"],
            note="Deterministic synthetic series for offline development and tests. NOT market data.",
        )

    def fetch_bars(self, *, symbol: str, start_date: str, end_date: str, frequency: str) -> DataSourcePayload:
        if frequency != "1d":
            raise ValueError("demo provider currently supports only 1d frequency")
        _check_dates(start_date, end_date)
        symbol = normalize_symbol(symbol)
        market, exchange = market_for_symbol(symbol)
        start, end = date.fromisoformat(start_date), date.fromisoformat(end_date)
        bars = []
        cursor, index = start, 0
        while cursor <= end:
            if cursor.weekday() < 5:
                close = round(100 + index * 1.7 + len(symbol) * 0.03, 2)
                bars.append(MarketBarImport(
                    symbol=symbol, frequency=frequency, trade_time=cursor.isoformat(),
                    open=round(close - 0.8, 2), high=round(close + 1.2, 2), low=round(close - 1.4, 2), close=close,
                    volume=100000 + index * 1200, amount=round(close * (100000 + index * 1200), 2),
                    adj_factor=1.0, source=self.provider_id,
                ))
                index += 1
            cursor = date.fromordinal(cursor.toordinal() + 1)
        return DataSourcePayload(
            instrument=MarketInstrumentImport(symbol=symbol, name=f"{symbol} (synthetic)", market=market, exchange=exchange),
            bars=bars,
        )


_PROVIDERS: dict[str, MarketDataProvider] = {"tencent": TencentProvider(), "demo": DemoProvider()}


def get_provider(provider_id: str) -> MarketDataProvider | None:
    return _PROVIDERS.get(provider_id)


def list_market_data_sources() -> list[DataSourceInfo]:
    return [provider.info() for provider in _PROVIDERS.values()]


def sync_market_data_from_source(*, provider_id: str, symbol: str, start_date: str, end_date: str,
                                 frequency: str) -> DataSourcePayload:
    provider = get_provider(provider_id)
    if provider is None:
        raise ValueError(f"unknown market data provider: {provider_id}")
    return provider.fetch_bars(symbol=symbol, start_date=start_date, end_date=end_date, frequency=frequency)


def fetch_hk_board_lots() -> dict[str, int]:
    if not settings.market_data_network_enabled:
        raise ValueError("network data sources are disabled (MARKET_DATA_NETWORK_ENABLED=false)")
    return hkex.fetch_board_lots()
