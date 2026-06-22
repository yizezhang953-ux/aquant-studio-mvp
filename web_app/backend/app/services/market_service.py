from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import MarketBar, MarketInstrument


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
