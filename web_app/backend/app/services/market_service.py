import csv
import re
from datetime import date
from io import StringIO

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AuditLog, MarketBar, MarketCorporateAction, MarketFxRate, MarketInstrument
from app.schemas.market import MarketBarImport, MarketCsvImportRequest, MarketImportRequest
from app.services.trading_calendar_service import calendar_label, missing_trading_days

SYMBOL_RE = re.compile(r"^[0-9]{6}\.(SH|SZ|BJ)$|^[0-9]{5}\.HK$")
CURRENCY = {"a_share": "CNY", "hk_stock": "HKD"}


def normalize_symbol(symbol: str) -> str:
    text = str(symbol or "").strip().upper()
    if re.fullmatch(r"\d{1,5}\.HK", text):
        return text.split(".")[0].zfill(5) + ".HK"
    return text


def market_for_symbol(symbol: str) -> tuple[str, str]:
    """(market, exchange) from a symbol; raises ValueError for unsupported formats."""
    symbol = normalize_symbol(symbol)
    if not SYMBOL_RE.match(symbol):
        raise ValueError(f"unsupported symbol {symbol}: use 600519.SH / 000001.SZ / 430047.BJ / 00700.HK")
    exchange = symbol.rsplit(".", 1)[1]
    return ("hk_stock" if exchange == "HK" else "a_share"), exchange


def instrument_payload(data: dict) -> dict:
    """Fill market/exchange/currency from the symbol and reject inconsistent values."""
    symbol = normalize_symbol(data["symbol"])
    market, exchange = market_for_symbol(symbol)
    if data.get("market") not in (None, "", market):
        if not (data["market"] == "hk_connect" and market == "hk_stock"):
            raise ValueError(f"{symbol} is listed in {market}, not {data['market']}")
    if data.get("exchange") not in (None, "", exchange):
        raise ValueError(f"{symbol} trades on {exchange}, not {data['exchange']}")
    payload = {**data, "symbol": symbol, "market": market, "exchange": exchange,
               "currency": data.get("currency") or CURRENCY[market]}
    return {k: v for k, v in payload.items() if v is not None or k in {"lot_size", "connect_eligible", "listed_date"}}


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
                "market": summary["market"],
                "currency": summary["currency"],
                "lot_size": summary["lot_size"],
                "frequencies": summary["frequencies"],
                "bar_count": summary["bar_count"],
                "first_trade_time": summary["first_trade_time"],
                "last_trade_time": summary["last_trade_time"],
                "quality_status": _quality_status(summary),
            }
        )
    return {
        "market": "multi",
        "instrument_count": len(instruments),
        "total_bar_count": total_bar_count,
        "coverage": coverage,
    }


def import_market_data(db: Session, request: MarketImportRequest) -> dict:
    """Upsert one instrument and its bars (one existence query per import, not per bar)."""
    payload = instrument_payload(request.instrument.model_dump())
    symbol = payload["symbol"]
    instrument = db.get(MarketInstrument, symbol)
    if instrument is None:
        instrument = MarketInstrument(**payload)
        db.add(instrument)
    else:
        for key, value in payload.items():
            if value is None and key in {"lot_size", "connect_eligible"}:
                continue  # keep known board lots when a feed does not send them
            setattr(instrument, key, value)
    db.flush()

    bars = [bar.model_dump() | {"symbol": symbol} for bar in request.bars]
    keys = {(bar["frequency"], bar["trade_time"]) for bar in bars}
    existing: dict[tuple[str, str], MarketBar] = {}
    if keys:
        times = sorted(t for _, t in keys)
        rows = db.scalars(
            select(MarketBar).where(
                MarketBar.symbol == symbol,
                MarketBar.frequency.in_({f for f, _ in keys}),
                MarketBar.trade_time >= times[0],
                MarketBar.trade_time <= times[-1],
            )
        ).all()
        existing = {(row.frequency, row.trade_time): row for row in rows}

    inserted = 0
    updated = 0
    for bar_payload in bars:
        row = existing.get((bar_payload["frequency"], bar_payload["trade_time"]))
        if row is None:
            row = MarketBar(**bar_payload)
            db.add(row)
            existing[(bar_payload["frequency"], bar_payload["trade_time"])] = row
            inserted += 1
        else:
            for key, value in bar_payload.items():
                setattr(row, key, value)
            updated += 1
    db.commit()
    total_bars = db.scalar(select(func.count()).select_from(MarketBar).where(MarketBar.symbol == symbol)) or 0
    return {
        "symbol": symbol,
        "inserted_bars": inserted,
        "updated_bars": updated,
        "total_bars": total_bars,
        "message": "market data imported",
    }


def import_corporate_actions(db: Session, symbol: str, actions: list[dict], source: str,
                             start: str | None = None, end: str | None = None) -> int:
    """Replace ``source``'s actions for ``symbol`` inside [start, end] (all when no window), then
    rebuild the symbol's adj_factor over its full stored history."""
    symbol = normalize_symbol(symbol)
    if db.get(MarketInstrument, symbol) is None:
        raise ValueError(f"unknown instrument {symbol}; import its bars first")
    statement = select(MarketCorporateAction).where(MarketCorporateAction.symbol == symbol,
                                                    MarketCorporateAction.source == source)
    if start:
        statement = statement.where(MarketCorporateAction.ex_date >= start)
    if end:
        statement = statement.where(MarketCorporateAction.ex_date <= end)
    for row in db.scalars(statement).all():
        db.delete(row)
    db.flush()
    seen = {(a.ex_date) for a in db.scalars(select(MarketCorporateAction).where(
        MarketCorporateAction.symbol == symbol, MarketCorporateAction.source == source)).all()}
    for action in actions:
        if action["ex_date"] in seen:
            continue
        db.add(MarketCorporateAction(symbol=symbol, ex_date=action["ex_date"], cash_dividend=float(action.get("cash_dividend") or 0),
                                     bonus_ratio=float(action.get("bonus_ratio") or 0), currency=action.get("currency"), source=source))
    db.flush()
    rebuild_adj_factors(db, symbol)
    db.commit()
    return len(actions)


def rebuild_adj_factors(db: Session, symbol: str) -> int:
    """Recompute adj_factor of every stored bar from raw daily closes + effective corporate actions."""
    from app.services.legacy_paths import REPO_ROOT
    import sys

    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    from data_module.adjust import factors_from_actions

    daily = db.scalars(select(MarketBar).where(MarketBar.symbol == symbol, MarketBar.frequency == "1d")
                       .order_by(MarketBar.trade_time)).all()
    if not daily:
        return 0
    by_day: dict[str, list[MarketCorporateAction]] = {}
    for action in db.scalars(select(MarketCorporateAction).where(MarketCorporateAction.symbol == symbol)).all():
        by_day.setdefault(action.ex_date, []).append(action)
    effective = []
    for day in sorted(by_day):
        explicit = [a for a in by_day[day] if not (a.source or "").endswith("_derived")]
        effective.extend({"ex_date": a.ex_date, "cash_dividend": a.cash_dividend, "bonus_ratio": a.bonus_ratio}
                         for a in (explicit or by_day[day]))
    days = [bar.trade_time[:10] for bar in daily]
    factors = factors_from_actions(days, [bar.close for bar in daily], effective)
    factor_by_day = dict(zip(days, factors))
    for bar, factor in zip(daily, factors):
        bar.adj_factor = factor
    for bar in db.scalars(select(MarketBar).where(MarketBar.symbol == symbol, MarketBar.frequency != "1d")).all():
        if bar.trade_time[:10] in factor_by_day:
            bar.adj_factor = factor_by_day[bar.trade_time[:10]]
    return len(daily)


def list_corporate_actions(db: Session, symbol: str) -> list[dict]:
    rows = db.scalars(select(MarketCorporateAction).where(MarketCorporateAction.symbol == normalize_symbol(symbol))
                      .order_by(MarketCorporateAction.ex_date)).all()
    return [{"ex_date": r.ex_date, "cash_dividend": r.cash_dividend, "bonus_ratio": r.bonus_ratio,
             "currency": r.currency, "source": r.source} for r in rows]


def import_fx_rates(db: Session, pair: str, rates: dict[str, float], source: str) -> int:
    for day, rate in rates.items():
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(day)):
            raise ValueError(f"invalid FX date {day!r}; use YYYY-MM-DD")
        if not rate or float(rate) <= 0:
            raise ValueError(f"FX rate for {day} must be positive")
    existing = {r.rate_date: r for r in db.scalars(select(MarketFxRate).where(MarketFxRate.pair == pair)).all()}
    for day, rate in rates.items():
        row = existing.get(day)
        if row is None:
            db.add(MarketFxRate(pair=pair, rate_date=day, rate=float(rate), source=source))
        else:
            row.rate, row.source = float(rate), source
    db.commit()
    return len(rates)


def fx_coverage(db: Session) -> list[dict]:
    rows = db.execute(select(MarketFxRate.pair, func.count(MarketFxRate.id), func.min(MarketFxRate.rate_date),
                             func.max(MarketFxRate.rate_date)).group_by(MarketFxRate.pair)).all()
    return [{"pair": r[0], "rows": r[1], "start_date": r[2], "end_date": r[3]} for r in rows]


def set_board_lots(db: Session, lots: dict[str, int]) -> int:
    updated = 0
    for instrument in db.scalars(select(MarketInstrument).where(MarketInstrument.market == "hk_stock")).all():
        code = instrument.symbol.split(".")[0]
        if code in lots:
            instrument.lot_size = int(lots[code])
            updated += 1
    db.commit()
    return updated


def import_market_csv(db: Session, request: MarketCsvImportRequest) -> dict:
    try:
        symbol = normalize_symbol(request.symbol)
        market, exchange = market_for_symbol(symbol)
        if request.exchange and request.exchange.upper() != exchange:
            raise ValueError(f"{symbol} trades on {exchange}, not {request.exchange}")
    except ValueError as exc:
        return _empty_csv_result(request.symbol, [str(exc)])
    reader = csv.DictReader(StringIO(request.csv_text.strip()))
    required = {"trade_time", "open", "high", "low", "close"}
    if reader.fieldnames is None:
        return _empty_csv_result(symbol, ["CSV header is required"])
    missing = required - set(reader.fieldnames)
    if missing:
        return _empty_csv_result(symbol, [f"missing columns: {', '.join(sorted(missing))}"])

    bars = []
    errors = []
    skipped = 0
    for row_number, row in enumerate(reader, start=2):
        try:
            bars.append(
                MarketBarImport(
                    symbol=symbol,
                    frequency=request.frequency,
                    trade_time=str(row["trade_time"]).strip(),
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=_float_or_zero(row.get("volume")),
                    amount=_float_or_zero(row.get("amount")),
                    adj_factor=_float_or_one(row.get("adj_factor")),
                    source=request.source,
                )
            )
        except (TypeError, ValueError) as exc:
            skipped += 1
            errors.append(f"row {row_number}: {exc}")

    if not bars:
        result = _empty_csv_result(symbol, errors or ["no valid rows"])
        result["skipped_rows"] = skipped
        return result

    result = import_market_data(
        db,
        MarketImportRequest(
            instrument={
                "symbol": symbol,
                "name": request.name,
                "market": market,
                "exchange": exchange,
                "asset_type": "stock",
                "status": "active",
                "lot_size": request.lot_size,
            },
            bars=bars,
        ),
    )
    return {
        "symbol": symbol,
        "parsed_rows": len(bars),
        "inserted_bars": result["inserted_bars"],
        "updated_bars": result["updated_bars"],
        "total_bars": result["total_bars"],
        "skipped_rows": skipped,
        "errors": errors,
        "message": "CSV market data imported",
    }


def get_market_quality(db: Session, symbol: str | None = None, limit: int = 200) -> dict:
    statement = select(MarketBar).order_by(MarketBar.symbol, MarketBar.frequency, MarketBar.trade_time.desc())
    if symbol:
        statement = statement.where(MarketBar.symbol == symbol)
    bars = db.scalars(statement.limit(limit)).all()
    issues = []
    for bar in bars:
        if min(bar.open, bar.high, bar.low, bar.close) <= 0:
            issues.append(
                _quality_issue(
                    bar,
                    "non_positive_price",
                    "error",
                    "open/high/low/close must all be positive",
                )
            )
        if bar.high < bar.low:
            issues.append(
                _quality_issue(
                    bar,
                    "invalid_high_low",
                    "error",
                    "high must be greater than or equal to low",
                )
            )
        if bar.high < max(bar.open, bar.close) or bar.low > min(bar.open, bar.close):
            issues.append(
                _quality_issue(
                    bar,
                    "invalid_ohlc",
                    "error",
                    "high/low does not contain open and close",
                )
            )
        if bar.volume < 0 or bar.amount < 0:
            issues.append(
                _quality_issue(
                    bar,
                    "negative_liquidity",
                    "error",
                    "volume or amount is negative",
                )
            )
        if bar.volume == 0:
            issues.append(
                _quality_issue(
                    bar,
                    "zero_volume",
                    "warning",
                    "volume is zero",
                )
            )
    markets = {i.symbol: i.market for i in db.scalars(select(MarketInstrument).where(
        MarketInstrument.symbol.in_({bar.symbol for bar in bars}))).all()} if bars else {}
    issues.extend(_daily_gap_issues(list(reversed(bars)), markets))
    summary: dict[str, int] = {}
    for issue in issues:
        summary[issue["issue_type"]] = summary.get(issue["issue_type"], 0) + 1
    error_count = sum(1 for issue in issues if issue["severity"] == "error")
    warning_count = sum(1 for issue in issues if issue["severity"] == "warning")
    score = max(0, 100 - error_count * 20 - warning_count * 5)
    return {
        "checked_bar_count": len(bars),
        "issue_count": len(issues),
        "error_count": error_count,
        "warning_count": warning_count,
        "quality_score": score,
        "calendar_name": calendar_label(markets.get(symbol) if symbol else (next(iter(set(markets.values()))) if len(set(markets.values())) == 1 else None)),
        "missing_trading_days": [
            issue["trade_time"] for issue in issues if issue["issue_type"] == "missing_trading_day"
        ],
        "issue_summary": summary,
        "issues": issues,
    }


def _quality_issue(bar: MarketBar, issue_type: str, severity: str, message: str) -> dict:
    return {
        "symbol": bar.symbol,
        "frequency": bar.frequency,
        "trade_time": bar.trade_time,
        "issue_type": issue_type,
        "severity": severity,
        "message": message,
    }


def _daily_gap_issues(bars: list[MarketBar], markets: dict[str, str] | None = None) -> list[dict]:
    markets = markets or {}
    issues = []
    grouped: dict[tuple[str, str], list[MarketBar]] = {}
    for bar in bars:
        if bar.frequency != "1d":
            continue
        grouped.setdefault((bar.symbol, bar.frequency), []).append(bar)
    for (group_symbol, _), group_bars in grouped.items():
        market = markets.get(group_symbol, "a_share")
        ordered = sorted(group_bars, key=lambda item: item.trade_time)
        previous: date | None = None
        previous_time = ""
        for bar in ordered:
            try:
                current = date.fromisoformat(bar.trade_time[:10])
            except ValueError:
                issues.append(
                    _quality_issue(
                        bar,
                        "invalid_trade_date",
                        "error",
                        "trade_time must start with ISO date YYYY-MM-DD",
                    )
                )
                continue
            if previous is not None:
                for missing_day in missing_trading_days(market, previous, current):
                    issues.append(
                        {
                            "symbol": bar.symbol,
                            "frequency": bar.frequency,
                            "trade_time": missing_day.isoformat(),
                            "issue_type": "missing_trading_day",
                            "severity": "warning",
                            "message": f"missing trading day between {previous_time} and {bar.trade_time}",
                        }
                    )
            previous = current
            previous_time = bar.trade_time
    return issues


def record_market_import_batch(
    db: Session,
    *,
    owner_id: int,
    import_type: str,
    result: dict,
    frequency: str | None = None,
    status: str = "completed",
    source: str | None = None,
) -> int:
    log = AuditLog(
        event_type="market_import",
        owner_id=owner_id,
        status=status,
        message=result.get("message") or f"{import_type} import for {result['symbol']}",
        payload_json={
            "owner_id": owner_id,
            "import_type": import_type,
            "symbol": result["symbol"],
            "frequency": frequency,
            "inserted_bars": result.get("inserted_bars", 0),
            "updated_bars": result.get("updated_bars", 0),
            "skipped_rows": result.get("skipped_rows", 0),
            "issue_count": len(result.get("errors", [])),
            "source": source,
            "errors": result.get("errors", []),
            "parsed_rows": result.get("parsed_rows", 0),
            "total_bars": result.get("total_bars", 0),
        },
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return log.id


def get_market_import_batch(db: Session, owner_id: int, batch_id: int) -> dict | None:
    row = db.get(AuditLog, batch_id)
    if row is None or row.event_type != "market_import" or row.owner_id != owner_id:
        return None
    payload = row.payload_json or {}
    return {
        "id": row.id,
        "import_type": payload.get("import_type", "unknown"),
        "symbol": payload.get("symbol", "-"),
        "frequency": payload.get("frequency"),
        "inserted_bars": payload.get("inserted_bars", 0),
        "updated_bars": payload.get("updated_bars", 0),
        "skipped_rows": payload.get("skipped_rows", 0),
        "issue_count": payload.get("issue_count", 0),
        "status": row.status,
        "created_at": row.created_at.isoformat() if row.created_at else "",
        "message": row.message,
        "source": payload.get("source"),
        "errors": payload.get("errors", []),
        "payload": payload,
    }


def _batch_summary(row: AuditLog) -> dict:
    payload = row.payload_json or {}
    return {
        "id": row.id,
        "import_type": payload.get("import_type", "unknown"),
        "symbol": payload.get("symbol", "-"),
        "frequency": payload.get("frequency"),
        "inserted_bars": payload.get("inserted_bars", 0),
        "updated_bars": payload.get("updated_bars", 0),
        "skipped_rows": payload.get("skipped_rows", 0),
        "issue_count": payload.get("issue_count", 0),
        "status": row.status,
        "created_at": row.created_at.isoformat() if row.created_at else "",
    }


def list_market_import_batches(db: Session, owner_id: int, limit: int = 20) -> list[dict]:
    statement = (
        select(AuditLog)
        .where(AuditLog.event_type == "market_import", AuditLog.owner_id == owner_id)
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .limit(limit)
    )
    return [_batch_summary(row) for row in db.scalars(statement).all()]


def _float_or_zero(value: str | None) -> float:
    if value is None or value == "":
        return 0
    return float(value)


def _float_or_one(value: str | None) -> float:
    if value is None or value == "":
        return 1.0
    return float(value)


def _empty_csv_result(symbol: str, errors: list[str]) -> dict:
    return {
        "symbol": symbol,
        "parsed_rows": 0,
        "inserted_bars": 0,
        "updated_bars": 0,
        "total_bars": 0,
        "skipped_rows": 0,
        "errors": errors,
        "message": "CSV market data import failed",
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
        "currency": instrument.currency or CURRENCY.get(instrument.market, "CNY"),
        "lot_size": instrument.lot_size,
        "connect_eligible": instrument.connect_eligible,
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
