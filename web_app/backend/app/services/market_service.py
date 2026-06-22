from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import MarketBar, MarketInstrument
from app.schemas.market import MarketImportRequest


def list_market_instruments(db: Session) -> list[dict]:
    instruments = db.scalars(select(MarketInstrument).order_by(MarketInstrument.symbol)).all()
    return [_instrument_summary(db, instrument) for instrument in instruments]


def get_market_instrument(db: Session, symbol: str) -> dict | None:
    instrument = db.get(MarketInstrument, symbol)
    if instrument is None:
        return None
    return _instrument_summary(db, instrument)


def list_market_bars(db: Session, symbol: str, frequency: str = "1d", limit: int = 120) -> list[MarketBar]:
    statement = (
        select(MarketBar)
        .where(MarketBar.symbol == symbol, MarketBar.frequency == frequency)
        .order_by(MarketBar.trade_time.desc())
        .limit(limit)
    )
    bars = db.scalars(statement).all()
    return list(reversed(bars))


def get_market_coverage(db: Session) -> dict:
    instruments = db.scalars(select(MarketInstrument).order_by(MarketInstrument.symbol)).all()
    coverage = []
    total_bar_count = 0
    for instrument in instruments:
        summary = _instrument_summary(db, instrument)
        total_bar_count += summary["bar_count"]
        coverage.append(
            {
                "symbol": summary["symbol"],
                "name": summary["name"],
                "frequencies": summary["frequencies"],
                "bar_count": summary["bar_count"],
                "first_trade_time": summary["first_trade_time"],
                "last_trade_time": summary["last_trade_time"],
                "quality_status": _quality_status(summary),
            }
        )
    return {
        "market": "a_share",
        "instrument_count": len(instruments),
        "total_bar_count": total_bar_count,
        "coverage": coverage,
    }


def import_market_data(db: Session, request: MarketImportRequest) -> dict:
    instrument_payload = request.instrument.model_dump()
    instrument = db.get(MarketInstrument, request.instrument.symbol)
    if instrument is None:
        instrument = MarketInstrument(**instrument_payload)
        db.add(instrument)
    else:
        for key, value in instrument_payload.items():
            setattr(instrument, key, value)
    db.flush()

    inserted = 0
    updated = 0
    for bar_payload in request.bars:
        payload = bar_payload.model_dump()
        existing = db.scalar(
            select(MarketBar).where(
                MarketBar.symbol == payload["symbol"],
                MarketBar.frequency == payload["frequency"],
                MarketBar.trade_time == payload["trade_time"],
            )
        )
        if existing is None:
            db.add(MarketBar(**payload))
            inserted += 1
        else:
            for key, value in payload.items():
                setattr(existing, key, value)
            updated += 1
    db.commit()
    total_bars = db.scalar(select(func.count()).select_from(MarketBar).where(MarketBar.symbol == request.instrument.symbol)) or 0
    return {
        "symbol": request.instrument.symbol,
        "inserted_bars": inserted,
        "updated_bars": updated,
        "total_bars": total_bars,
        "message": "market data imported",
    }


def get_market_quality(db: Session, symbol: str | None = None, limit: int = 200) -> dict:
    statement = select(MarketBar).order_by(MarketBar.symbol, MarketBar.frequency, MarketBar.trade_time.desc())
    if symbol:
        statement = statement.where(MarketBar.symbol == symbol)
    bars = db.scalars(statement.limit(limit)).all()
    issues = []
    for bar in bars:
        if bar.high < max(bar.open, bar.close) or bar.low > min(bar.open, bar.close):
            issues.append(
                {
                    "symbol": bar.symbol,
                    "frequency": bar.frequency,
                    "trade_time": bar.trade_time,
                    "issue_type": "invalid_ohlc",
                    "message": "high/low does not contain open and close",
                }
            )
        if bar.volume < 0 or bar.amount < 0:
            issues.append(
                {
                    "symbol": bar.symbol,
                    "frequency": bar.frequency,
                    "trade_time": bar.trade_time,
                    "issue_type": "negative_liquidity",
                    "message": "volume or amount is negative",
                }
            )
    return {"checked_bar_count": len(bars), "issue_count": len(issues), "issues": issues}


def _instrument_summary(db: Session, instrument: MarketInstrument) -> dict:
    aggregate = db.execute(
        select(
            func.count(MarketBar.id),
            func.min(MarketBar.trade_time),
            func.max(MarketBar.trade_time),
        ).where(MarketBar.symbol == instrument.symbol)
    ).one()
    frequencies = db.scalars(
        select(MarketBar.frequency)
        .where(MarketBar.symbol == instrument.symbol)
        .distinct()
        .order_by(MarketBar.frequency)
    ).all()
    latest_close = db.scalar(
        select(MarketBar.close)
        .where(MarketBar.symbol == instrument.symbol)
        .order_by(MarketBar.trade_time.desc())
        .limit(1)
    )
    return {
        "symbol": instrument.symbol,
        "name": instrument.name,
        "market": instrument.market,
        "exchange": instrument.exchange,
        "asset_type": instrument.asset_type,
        "listed_date": instrument.listed_date,
        "status": instrument.status,
        "bar_count": aggregate[0] or 0,
        "first_trade_time": aggregate[1],
        "last_trade_time": aggregate[2],
        "latest_close": latest_close,
        "frequencies": list(frequencies),
    }


def _quality_status(summary: dict) -> str:
    if summary["bar_count"] <= 0:
        return "empty"
    if not summary["first_trade_time"] or not summary["last_trade_time"]:
        return "incomplete"
    return "ready"
