"""Read market data from the web database in the shapes the backtest engine and validator use.

Backtests and validation read the same tables the import/sync endpoints write
(market_bars / market_instruments / market_corporate_actions / market_fx_rates), on SQLite and
PostgreSQL alike.
"""
from __future__ import annotations

import sys
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import MarketBar, MarketCorporateAction, MarketFxRate, MarketInstrument
from app.services.legacy_paths import BACKTEST_MODULE, REPO_ROOT

for _path in (REPO_ROOT, BACKTEST_MODULE):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from backtest_engine import (  # noqa: E402
    Bar,
    CorporateAction,
    InstrumentInfo,
    MarketContext,
    end_bound,
    required_warmup_bars,
)
from market_rules_module.market_rules import normalize_symbol  # noqa: E402

FX_PAIR = "HKDCNY"


def _to_bar(row: MarketBar) -> Bar:
    return Bar(row.symbol, row.frequency, row.trade_time, row.open, row.high, row.low, row.close,
               row.volume, row.amount, row.adj_factor or 1.0)


def load_engine_bars(db: Session, strategy: dict[str, Any], warmup_bars: int | None = None) -> list[Bar]:
    symbol = normalize_symbol(strategy["universe"]["symbols"][0])
    frequency = strategy["data"]["frequency"]
    start = strategy["data"]["start_date"]
    end = end_bound(strategy["data"]["end_date"])
    warmup = required_warmup_bars(strategy) if warmup_bars is None else warmup_bars
    base = select(MarketBar).where(MarketBar.symbol == symbol, MarketBar.frequency == frequency)
    rows = db.scalars(base.where(MarketBar.trade_time >= start, MarketBar.trade_time <= end)
                      .order_by(MarketBar.trade_time)).all()
    history: list[MarketBar] = []
    if warmup:
        history = list(db.scalars(base.where(MarketBar.trade_time < start)
                                  .order_by(MarketBar.trade_time.desc()).limit(warmup)).all())
    return [_to_bar(r) for r in reversed(history)] + [_to_bar(r) for r in rows]


def available_data(db: Session, limit: int = 8) -> list[dict[str, Any]]:
    """What bars the database holds, per symbol and frequency (for actionable "no data" messages)."""
    rows = db.execute(
        select(MarketBar.symbol, MarketBar.frequency, func.count(), func.min(MarketBar.trade_time),
               func.max(MarketBar.trade_time))
        .group_by(MarketBar.symbol, MarketBar.frequency)
        .order_by(func.count().desc())
        .limit(limit)
    ).all()
    return [{"symbol": r[0], "frequency": r[1], "bars": r[2], "start": str(r[3])[:10], "end": str(r[4])[:10]}
            for r in rows]


def load_engine_context(db: Session, strategy: dict[str, Any]) -> MarketContext:
    symbol = normalize_symbol(strategy["universe"]["symbols"][0])
    context = MarketContext()
    instrument = db.get(MarketInstrument, symbol)
    if instrument is not None:
        context.instrument = InstrumentInfo(symbol, instrument.name, instrument.lot_size, instrument.connect_eligible)
    actions = db.scalars(select(MarketCorporateAction).where(MarketCorporateAction.symbol == symbol)
                         .order_by(MarketCorporateAction.ex_date)).all()
    if actions:
        by_day: dict[str, list[MarketCorporateAction]] = {}
        for action in actions:  # explicit actions win over feed-derived ones on the same ex-date
            by_day.setdefault(action.ex_date, []).append(action)
        chosen = []
        for day in sorted(by_day):
            explicit = [a for a in by_day[day] if not (a.source or "").endswith("_derived")]
            chosen.extend(explicit or by_day[day])
        context.corporate_actions = [CorporateAction(a.ex_date, a.cash_dividend or 0.0, a.bonus_ratio or 0.0, a.source)
                                     for a in chosen]
    if symbol.endswith(".HK"):
        rates = db.execute(select(MarketFxRate.rate_date, MarketFxRate.rate).where(MarketFxRate.pair == FX_PAIR)).all()
        context.fx_rates = {str(day)[:10]: float(rate) for day, rate in rates}
    return context


def coverage_for(db: Session):
    """Coverage callback for strategy_validator.validate_strategy(coverage=...)."""

    def coverage(symbol: str, frequency: str, start_date: str, end_date: str) -> tuple[int, str | None, str | None]:
        row = db.execute(
            select(func.count(MarketBar.id), func.min(MarketBar.trade_time), func.max(MarketBar.trade_time)).where(
                MarketBar.symbol == symbol,
                MarketBar.frequency == frequency,
                MarketBar.trade_time >= start_date,
                MarketBar.trade_time <= end_bound(end_date),
            )
        ).one()
        return int(row[0] or 0), row[1], row[2]

    return coverage
