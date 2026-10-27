"""Fetch one stock's bars from a data source and store them (shared by the sync endpoint and the daily job)."""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.schemas.market import MarketImportRequest
from app.services.market_data_source_service import sync_market_data_from_source
from app.services.market_service import (
    import_corporate_actions,
    import_fx_rates,
    import_market_data,
    record_market_import_batch,
)


class TooManyBars(ValueError):
    pass


def sync_symbol(db: Session, *, owner_id: int, provider_id: str, symbol: str, start_date: str, end_date: str,
                frequency: str = "1d") -> dict[str, Any]:
    payload = sync_market_data_from_source(provider_id=provider_id, symbol=symbol, start_date=start_date,
                                           end_date=end_date, frequency=frequency)
    if len(payload.bars) > settings.max_import_bars:
        raise TooManyBars(f"at most {settings.max_import_bars} bars per import")
    result = import_market_data(db, MarketImportRequest(instrument=payload.instrument, bars=payload.bars))
    actions = import_corporate_actions(
        db, result["symbol"], payload.corporate_actions, payload.source,
        payload.bars[0].trade_time[:10], payload.bars[-1].trade_time[:10],
    ) if payload.source and payload.bars else 0
    rates = import_fx_rates(db, payload.fx_pair, payload.fx_rates, "frankfurter_ecb") if payload.fx_rates else 0
    record_market_import_batch(db, owner_id=owner_id, import_type="data_source_sync", result=result,
                               frequency=frequency, source=provider_id)
    return {**result, "fetched_bars": len(payload.bars), "corporate_actions": actions, "fx_rates": rates,
            "last_date": payload.bars[-1].trade_time[:10] if payload.bars else None}
