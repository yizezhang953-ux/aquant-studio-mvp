"""Fetch stocks' bars from a data source and store them: one stock (the sync endpoint), many stocks at
once in a background job (批量同步), and the daily automation.

Fetching is network-bound and runs on a few threads; storing stays on one thread and one session,
so SQLite never sees concurrent writers.
"""
from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
from typing import Any, Callable
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import MarketBar
from app.schemas.market import MarketImportRequest
from app.services.benchmark_service import sync_indices
from app.services.market_data_source_service import DataSourcePayload, sync_market_data_from_source
from app.services.market_service import (
    import_corporate_actions,
    import_fx_rates,
    import_market_data,
    record_market_import_batch,
)

FETCH_WORKERS = 4  # polite to the free endpoint, still ~4x faster than one at a time
OVERLAP_DAYS = 7  # re-fetch the last week too, so late corrections and adjustments are picked up
MAX_BATCH = 1000


class TooManyBars(ValueError):
    pass


def fetch_payload(provider_id: str, symbol: str, start_date: str, end_date: str, frequency: str = "1d") -> DataSourcePayload:
    payload = sync_market_data_from_source(provider_id=provider_id, symbol=symbol, start_date=start_date,
                                           end_date=end_date, frequency=frequency)
    if len(payload.bars) > settings.max_import_bars:
        raise TooManyBars(f"at most {settings.max_import_bars} bars per import")
    return payload


def store_payload(db: Session, payload: DataSourcePayload, *, owner_id: int, provider_id: str,
                  frequency: str = "1d") -> dict[str, Any]:
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


def sync_symbol(db: Session, *, owner_id: int, provider_id: str, symbol: str, start_date: str, end_date: str,
                frequency: str = "1d") -> dict[str, Any]:
    payload = fetch_payload(provider_id, symbol, start_date, end_date, frequency)
    return store_payload(db, payload, owner_id=owner_id, provider_id=provider_id, frequency=frequency)


def start_dates(db: Session, symbols: list[str], first_start: str | dict[str, str]) -> dict[str, str]:
    """Where each stock's fetch begins: a week before its last stored daily bar, or ``first_start``
    (one date for all, or per stock) when it has none yet."""
    last = dict(db.execute(select(MarketBar.symbol, func.max(MarketBar.trade_time))
                           .where(MarketBar.symbol.in_(symbols), MarketBar.frequency == "1d")
                           .group_by(MarketBar.symbol)).all())
    out = {}
    for symbol in symbols:
        if last.get(symbol):
            out[symbol] = (date.fromisoformat(last[symbol][:10]) - timedelta(days=OVERLAP_DAYS)).isoformat()
        else:
            out[symbol] = first_start[symbol] if isinstance(first_start, dict) else first_start
    return out


Progress = Callable[[dict[str, Any]], None]


def sync_many(db: Session, *, owner_id: int, provider_id: str, starts: dict[str, str], end_date: str,
              progress: Progress | None = None, cancelled: Callable[[], bool] = lambda: False) -> list[dict[str, Any]]:
    """Fetch every stock in ``starts`` on a few threads and store each as it arrives."""
    rows: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=FETCH_WORKERS) as pool:
        futures = {pool.submit(fetch_payload, provider_id, symbol, start, end_date): symbol
                   for symbol, start in starts.items() if start <= end_date}
        for future in as_completed(futures):
            symbol = futures[future]
            row: dict[str, Any] = {"symbol": symbol, "ok": False, "name": None, "last_date": None, "bars": 0, "error": None}
            if cancelled():
                for pending in futures:
                    pending.cancel()  # those already downloading finish, and are dropped
                break
            try:
                payload = future.result()
                stored = store_payload(db, payload, owner_id=owner_id, provider_id=provider_id)
                row.update(ok=True, name=payload.instrument.name, last_date=stored["last_date"], bars=stored["fetched_bars"])
            except Exception as exc:  # one bad code must not stop the batch
                db.rollback()
                row["error"] = str(exc)[:300]
            rows.append(row)
            if progress:
                progress(row)
    return rows


# --------------------------------------------------------------------------- background batch jobs

_jobs: dict[str, dict[str, Any]] = {}
_lock = threading.Lock()


def _public(job: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in job.items() if not k.startswith("_")}


def start_batch(session_factory: Callable[[], Session], *, owner_id: int, provider_id: str, symbols: list[str],
                first_start: str, end_date: str) -> dict[str, Any]:
    with _lock:
        if any(j["status"] == "running" for j in _jobs.values()):
            raise ValueError("已经有一个批量同步在进行，等它结束或取消后再开始")
        job = {"job_id": f"sync_{uuid4().hex[:10]}", "status": "running", "total": len(symbols), "done": 0, "ok": 0,
               "failed": [], "symbols": symbols, "provider_id": provider_id, "started_at": time.time(),
               "finished_at": None, "_cancel": False}
        _jobs.clear()  # only the latest job is kept
        _jobs[job["job_id"]] = job

    def progress(row: dict[str, Any]) -> None:
        with _lock:
            job["done"] += 1
            if row["ok"]:
                job["ok"] += 1
            else:
                job["failed"].append({"symbol": row["symbol"], "error": row["error"]})

    def run() -> None:
        with session_factory() as db:
            try:
                starts = start_dates(db, symbols, first_start)
                job["total"] = sum(1 for s in starts.values() if s <= end_date)
                sync_many(db, owner_id=owner_id, provider_id=provider_id, starts=starts, end_date=end_date,
                          progress=progress, cancelled=lambda: job["_cancel"])
                if job["ok"] and not job["_cancel"]:
                    try:  # keep 恒指 / 沪深300 covering the same dates for report comparisons
                        sync_indices(db, min(starts.values()), end_date, provider_id)
                    except ValueError:
                        db.rollback()
                job["status"] = "cancelled" if job["_cancel"] else "done"
            except Exception as exc:
                job["status"], job["error"] = "error", str(exc)[:300]
            finally:
                job["finished_at"] = time.time()

    threading.Thread(target=run, name=job["job_id"], daemon=True).start()
    return _public(job)


def get_batch(job_id: str | None = None) -> dict[str, Any] | None:
    with _lock:
        job = _jobs.get(job_id) if job_id else next(iter(_jobs.values()), None)
        return _public(job) if job else None


def cancel_batch(job_id: str) -> dict[str, Any] | None:
    with _lock:
        job = _jobs.get(job_id)
        if job and job["status"] == "running":
            job["_cancel"] = True
        return _public(job) if job else None
