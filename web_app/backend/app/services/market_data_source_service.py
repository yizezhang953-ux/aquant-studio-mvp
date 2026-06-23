from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol

from app.core.config import settings
from app.schemas.market import MarketBarImport, MarketInstrumentImport


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


class MarketDataProvider(Protocol):
    provider_id: str

    def info(self) -> DataSourceInfo:
        raise NotImplementedError

    def fetch_bars(
        self,
        *,
        symbol: str,
        start_date: str,
        end_date: str,
        frequency: str,
    ) -> DataSourcePayload:
        raise NotImplementedError


class DemoAshareProvider:
    provider_id = "demo_a_share"

    _names = {
        "600519.SH": ("贵州茅台", "SH"),
        "000001.SZ": ("平安银行", "SZ"),
        "300750.SZ": ("宁德时代", "SZ"),
    }

    def info(self) -> DataSourceInfo:
        return DataSourceInfo(
            provider_id=self.provider_id,
            name="Demo A-share fixture",
            market="a_share",
            status="ready",
            auth_required=False,
            supported_frequencies=["1d"],
            note="Local deterministic provider for development and integration testing.",
        )

    def fetch_bars(
        self,
        *,
        symbol: str,
        start_date: str,
        end_date: str,
        frequency: str,
    ) -> DataSourcePayload:
        if frequency != "1d":
            raise ValueError("demo_a_share currently supports only 1d frequency")
        start = date.fromisoformat(start_date)
        end = date.fromisoformat(end_date)
        if start > end:
            raise ValueError("start_date must be before or equal to end_date")

        name, exchange = self._names.get(symbol, (symbol, symbol.split(".")[-1] if "." in symbol else "SH"))
        bars = []
        cursor = start
        index = 0
        while cursor <= end:
            if cursor.weekday() < 5:
                close = round(100 + index * 1.7 + len(symbol) * 0.03, 2)
                bars.append(
                    MarketBarImport(
                        symbol=symbol,
                        frequency=frequency,
                        trade_time=cursor.isoformat(),
                        open=round(close - 0.8, 2),
                        high=round(close + 1.2, 2),
                        low=round(close - 1.4, 2),
                        close=close,
                        volume=100000 + index * 1200,
                        amount=round(close * (100000 + index * 1200), 2),
                        adj_factor=1.0,
                        source=self.provider_id,
                    )
                )
                index += 1
            cursor = date.fromordinal(cursor.toordinal() + 1)

        return DataSourcePayload(
            instrument=MarketInstrumentImport(
                symbol=symbol,
                name=name,
                market="a_share",
                exchange=exchange,
                asset_type="stock",
                status="active",
            ),
            bars=bars,
        )


class TushareProvider:
    provider_id = "tushare"

    def info(self) -> DataSourceInfo:
        status = "configured" if settings.tushare_token else "needs_token"
        return DataSourceInfo(
            provider_id=self.provider_id,
            name="Tushare Pro",
            market="a_share",
            status=status,
            auth_required=True,
            supported_frequencies=["1d"],
            note="Set TUSHARE_TOKEN and install tushare before enabling production synchronization.",
        )

    def fetch_bars(
        self,
        *,
        symbol: str,
        start_date: str,
        end_date: str,
        frequency: str,
    ) -> DataSourcePayload:
        if not settings.tushare_token:
            raise ValueError("TUSHARE_TOKEN is required for tushare provider")
        if frequency != "1d":
            raise ValueError("tushare provider currently supports only 1d frequency")
        raise ValueError("tushare runtime adapter is planned but not enabled in this MVP build")


def list_market_data_sources() -> list[DataSourceInfo]:
    return [provider.info() for provider in _providers().values()]


def sync_market_data_from_source(
    *,
    provider_id: str,
    symbol: str,
    start_date: str,
    end_date: str,
    frequency: str,
) -> DataSourcePayload:
    provider = _providers().get(provider_id)
    if provider is None:
        raise ValueError(f"unknown market data provider: {provider_id}")
    return provider.fetch_bars(
        symbol=symbol,
        start_date=start_date,
        end_date=end_date,
        frequency=frequency,
    )


def _providers() -> dict[str, MarketDataProvider]:
    return {
        "demo_a_share": DemoAshareProvider(),
        "tushare": TushareProvider(),
    }
