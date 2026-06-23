import csv
from datetime import date
from io import StringIO

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AuditLog, MarketBar, MarketInstrument
from app.schemas.market import MarketBarImport, MarketCsvImportRequest, MarketImportRequest


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


def import_market_csv(db: Session, request: MarketCsvImportRequest) -> dict:
    reader = csv.DictReader(StringIO(request.csv_text.strip()))
    required = {"trade_time", "open", "high", "low", "close"}
    if reader.fieldnames is None:
        return _empty_csv_result(request.symbol, ["CSV header is required"])
    missing = required - set(reader.fieldnames)
    if missing:
        return _empty_csv_result(request.symbol, [f"missing columns: {', '.join(sorted(missing))}"])

    bars = []
    errors = []
    skipped = 0
    for row_number, row in enumerate(reader, start=2):
        try:
            bars.append(
                MarketBarImport(
                    symbol=request.symbol,
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
        result = _empty_csv_result(request.symbol, errors or ["no valid rows"])
        result["skipped_rows"] = skipped
        return result

    result = import_market_data(
        db,
        MarketImportRequest(
            instrument={
                "symbol": request.symbol,
                "name": request.name,
                "market": "a_share",
                "exchange": request.exchange,
                "asset_type": "stock",
                "status": "active",
            },
            bars=bars,
        ),
    )
    return {
        "symbol": request.symbol,
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
    issues.extend(_daily_gap_issues(list(reversed(bars))))
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


def _daily_gap_issues(bars: list[MarketBar]) -> list[dict]:
    issues = []
    grouped: dict[tuple[str, str], list[MarketBar]] = {}
    for bar in bars:
        if bar.frequency != "1d":
            continue
        grouped.setdefault((bar.symbol, bar.frequency), []).append(bar)
    for group_bars in grouped.values():
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
            if previous is not None and (current - previous).days > 4:
                issues.append(
                    _quality_issue(
                        bar,
                        "daily_gap",
                        "warning",
                        f"daily data gap after {previous_time}",
                    )
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
    if row is None or row.event_type != "market_import":
        return None
    payload = row.payload_json or {}
    if payload.get("owner_id") != owner_id:
        return None
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
        .where(AuditLog.event_type == "market_import")
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .limit(limit)
    )
    rows = db.scalars(statement).all()
    batches = []
    for row in rows:
        payload = row.payload_json or {}
        if payload.get("owner_id") != owner_id:
            continue
        batches.append(_batch_summary(row))
    return batches


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
