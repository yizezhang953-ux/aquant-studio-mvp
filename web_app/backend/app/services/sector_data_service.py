"""Sector (industry) daily data for rotation backtests: where it comes from and how it is stored.

Sources: ``tushare`` (the 40 CITIC sectors of the Huatai fund-flow report, built from stock-level tables),
a CSV file (exports from Wind / iFinD / Choice, any sector set), and ``demo`` (synthetic, for trying the page).
Rows live in ``sector_daily`` grouped by ``universe``: the set of sectors that are ranked against each other.
"""
from __future__ import annotations

import csv
import io
import sys
import threading
import time
from datetime import date, timedelta
from typing import Any, Callable
from uuid import uuid4

import numpy as np
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models import DataCredential, SectorDaily
from app.services.legacy_paths import REPO_ROOT
from app.services.trading_calendar_service import expected_trading_days

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from data_module.sources import tushare  # noqa: E402

TUSHARE_UNIVERSE = "citic40"
DEMO_UNIVERSE = "demo"
UNIVERSE_NAMES = {TUSHARE_UNIVERSE: "中信 40 行业（Tushare）", DEMO_UNIVERSE: "演示数据（随机生成，不是真实行情）"}
BASE_CLOSE = 1000.0  # sector indices built from constituent returns start here
CALL_PAUSE = 0.35  # seconds between Tushare days: three calls each, well under the per-minute limit
MAX_CSV_BYTES = 40 * 1024 * 1024
FIELDS = ("close", "amount", "float_mv", "buy_amount", "sell_amount")

CSV_COLUMNS = {
    "trade_date": ("trade_date", "date", "日期", "交易日期"),
    "code": ("code", "代码", "行业代码", "证券代码"),
    "name": ("name", "名称", "行业名称", "证券简称"),
    "close": ("close", "收盘价", "收盘"),
    "amount": ("amount", "成交额", "成交金额"),
    "float_mv": ("float_mv", "流通市值"),
    "buy_amount": ("buy_amount", "主动买入额", "主动买入金额"),
    "sell_amount": ("sell_amount", "主动卖出额", "主动卖出金额"),
}


# --------------------------------------------------------------------------- credentials

def save_credential(db: Session, provider: str, secret: str) -> None:
    row = db.get(DataCredential, provider)
    if row is None:
        db.add(DataCredential(provider=provider, secret=secret))
    else:
        row.secret = secret
    db.commit()


def get_credential(db: Session, provider: str) -> str:
    row = db.get(DataCredential, provider)
    return row.secret if row else ""


def credential_hint(db: Session, provider: str) -> str:
    """Enough to recognise the saved token, never the token itself."""
    secret = get_credential(db, provider)
    return (secret[:4] + "…" + secret[-4:]) if len(secret) > 12 else ("已填写" if secret else "")


# --------------------------------------------------------------------------- storage

def store_rows(db: Session, universe: str, rows: list[dict[str, Any]], source: str) -> int:
    """Insert rows, replacing whatever the universe already has on those days."""
    days = sorted({r["trade_date"] for r in rows})
    for i in range(0, len(days), 500):
        db.execute(delete(SectorDaily).where(SectorDaily.universe == universe, SectorDaily.trade_date.in_(days[i:i + 500])))
    db.bulk_insert_mappings(SectorDaily, [{
        "universe": universe, "code": r["code"], "name": r.get("name") or r["code"], "trade_date": r["trade_date"],
        "close": r["close"], "amount": r.get("amount"), "float_mv": r.get("float_mv"),
        "buy_amount": r.get("buy_amount"), "sell_amount": r.get("sell_amount"), "source": source} for r in rows])
    db.commit()
    return len(rows)


def delete_universe(db: Session, universe: str) -> int:
    count = db.execute(delete(SectorDaily).where(SectorDaily.universe == universe)).rowcount
    db.commit()
    return count


def list_universes(db: Session) -> list[dict[str, Any]]:
    rows = db.execute(select(
        SectorDaily.universe, func.count(func.distinct(SectorDaily.code)), func.count(func.distinct(SectorDaily.trade_date)),
        func.min(SectorDaily.trade_date), func.max(SectorDaily.trade_date), func.count(SectorDaily.buy_amount),
        func.count(SectorDaily.float_mv), func.max(SectorDaily.source),
    ).group_by(SectorDaily.universe).order_by(SectorDaily.universe)).all()
    return [{"universe": u, "name": UNIVERSE_NAMES.get(u, u), "sectors": sectors, "days": days, "first_date": first,
             "last_date": last, "has_flow": flows > 0, "has_float_mv": mvs > 0, "source": source}
            for u, sectors, days, first, last, flows, mvs, source in rows]


def load_panel(db: Session, universe: str) -> tuple[list[str], list[str], dict[str, str], dict[str, np.ndarray]]:
    """(days, codes, {code: name}, {field: days x sectors array}); NaN where a sector has no value."""
    rows = db.execute(select(SectorDaily.trade_date, SectorDaily.code, SectorDaily.name, SectorDaily.close,
                             SectorDaily.amount, SectorDaily.float_mv, SectorDaily.buy_amount, SectorDaily.sell_amount)
                      .where(SectorDaily.universe == universe).order_by(SectorDaily.trade_date)).all()
    days = sorted({r[0] for r in rows})
    names = {r[1]: r[2] for r in rows}  # rows are in date order, so the latest name wins
    codes = sorted(names)
    day_at = {d: i for i, d in enumerate(days)}
    code_at = {c: j for j, c in enumerate(codes)}
    panel = {f: np.full((len(days), len(codes)), np.nan) for f in FIELDS}
    for row in rows:
        i, j = day_at[row[0]], code_at[row[1]]
        for k, field in enumerate(FIELDS):
            if row[3 + k] is not None:
                panel[field][i, j] = row[3 + k]
    return days, codes, names, panel


# --------------------------------------------------------------------------- sources

def demo_rows(start: str, end: str, seed: int = 7) -> list[dict[str, Any]]:
    """Synthetic sectors whose net active buying leads returns a little, so every factor has something to show."""
    days = [d.isoformat() for d in expected_trading_days("a_share", date.fromisoformat(start), date.fromisoformat(end))]
    names = tushare.CITIC40
    rng = np.random.default_rng(seed)
    n = len(names)
    size = rng.uniform(0.5, 4.0, n) * 1e10
    close = np.full(n, BASE_CLOSE)
    mood = np.zeros(n)
    rows: list[dict[str, Any]] = []
    for day in days:
        returns = rng.normal(0.0003, 0.009) + 0.00035 * mood + rng.normal(0, 0.011, n)
        close = close * (1 + returns)
        mood = 0.97 * mood + rng.normal(0, 0.25, n)  # today's buying pressure, felt in the coming days' returns
        amount = size * np.exp(rng.normal(0, 0.25, n))
        tilt = np.clip(0.02 * mood + rng.normal(0, 0.01, n), -0.5, 0.5)
        for j, name in enumerate(names):
            rows.append({"code": f"DEMO{j + 1:02d}", "name": name, "trade_date": day, "close": round(float(close[j]), 4),
                         "amount": float(amount[j]), "float_mv": float(size[j] * 40 * close[j] / BASE_CLOSE),
                         "buy_amount": float(amount[j] * 0.45 * (1 + tilt[j])),
                         "sell_amount": float(amount[j] * 0.45 * (1 - tilt[j]))})
    return rows


def _number(text: str | None) -> float | None:
    text = (text or "").replace(",", "").strip()
    if not text:
        return None
    return float(text)


def parse_csv(content: bytes) -> list[dict[str, Any]]:
    """Long-format CSV, one row per sector per day. Needs date, code and close; the other columns are optional."""
    for encoding in ("utf-8-sig", "gbk"):
        try:
            text = content.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ValueError("文件编码看不懂，请存成 UTF-8 或 GBK 的 CSV")
    reader = csv.DictReader(io.StringIO(text))
    header = {(h or "").strip().lower(): h for h in reader.fieldnames or []}
    columns = {field: next((header[a] for a in aliases if a in header), None) for field, aliases in CSV_COLUMNS.items()}
    missing = [field for field in ("trade_date", "code", "close") if columns[field] is None]
    if missing:
        raise ValueError(f"CSV 缺少这些列：{'、'.join(missing)}（需要 trade_date、code、close，"
                         "可选 name、amount、float_mv、buy_amount、sell_amount）")
    rows: dict[tuple[str, str], dict[str, Any]] = {}
    for line, record in enumerate(reader, start=2):
        try:
            raw_day = (record[columns["trade_date"]] or "").strip().replace("/", "-")
            if len(raw_day) == 8 and raw_day.isdigit():
                raw_day = f"{raw_day[:4]}-{raw_day[4:6]}-{raw_day[6:]}"
            day = date.fromisoformat("-".join(part.zfill(2) for part in raw_day[:10].split("-"))).isoformat()
            code = (record[columns["code"]] or "").strip()
            close = _number(record[columns["close"]])
            if not code or close is None or close <= 0:
                raise ValueError("代码或收盘价为空")
            row = {"trade_date": day, "code": code, "close": close,
                   "name": (record[columns["name"]] or "").strip() if columns["name"] else code}
            for field in ("amount", "float_mv", "buy_amount", "sell_amount"):
                row[field] = _number(record[columns[field]]) if columns[field] else None
        except (ValueError, TypeError) as exc:
            raise ValueError(f"第 {line} 行有问题：{exc}") from exc
        rows[(day, code)] = row
    if not rows:
        raise ValueError("CSV 里没有数据行")
    return list(rows.values())


def last_closes(db: Session, universe: str) -> tuple[str | None, dict[str, float]]:
    last = db.scalar(select(func.max(SectorDaily.trade_date)).where(SectorDaily.universe == universe))
    if last is None:
        return None, {}
    latest = select(SectorDaily.code, func.max(SectorDaily.trade_date).label("day")) \
        .where(SectorDaily.universe == universe).group_by(SectorDaily.code).subquery()
    rows = db.execute(select(SectorDaily.code, SectorDaily.close).join(
        latest, (SectorDaily.code == latest.c.code) & (SectorDaily.trade_date == latest.c.day))
        .where(SectorDaily.universe == universe)).all()
    return last, dict(rows)


def sync_tushare(db: Session, token: str, start: str, end: str, *, progress: Callable[[int, int, str], None],
                 cancelled: Callable[[], bool], post: tushare.Poster | None = None, pause: float = CALL_PAUSE) -> int:
    """Append trading days after the last stored one. Each sector's index is chained from its constituents'
    float-value-weighted return, so days must arrive in order: the first failure stops the run."""
    last, closes = last_closes(db, TUSHARE_UNIVERSE)
    if last and last >= start:
        start = (date.fromisoformat(last) + timedelta(days=1)).isoformat()
    days = [d.isoformat() for d in expected_trading_days("a_share", date.fromisoformat(start), date.fromisoformat(end))] \
        if start <= end else []
    progress(0, len(days), "")
    if not days:
        return 0
    membership = tushare.fetch_membership(token, post)
    if not membership:
        raise tushare.TushareError("没有取到中信行业成分（ci_index_member），请确认积分够 5000")
    stored = 0
    for index, day in enumerate(days):
        if cancelled():
            break
        rows = tushare.fetch_sector_day(token, day, membership, post)
        for row in rows:
            row["close"] = closes.get(row["code"], BASE_CLOSE) * (1 + row["ret"])
            closes[row["code"]] = row["close"]
        if rows:
            stored += store_rows(db, TUSHARE_UNIVERSE, rows, "tushare")
        progress(index + 1, len(days), day)
        if pause:
            time.sleep(pause)
    return stored


# --------------------------------------------------------------------------- background job

_jobs: dict[str, dict[str, Any]] = {}
_lock = threading.Lock()


def _public(job: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in job.items() if not k.startswith("_")}


def start_sync(session_factory: Callable[[], Session], *, provider: str, start: str, end: str) -> dict[str, Any]:
    with _lock:
        if any(j["status"] == "running" for j in _jobs.values()):
            raise ValueError("已经有一个行业数据同步在进行，等它结束或取消后再开始")
        job = {"job_id": f"sector_{uuid4().hex[:10]}", "status": "running", "provider": provider, "total": 0, "done": 0,
               "current_date": "", "rows": 0, "error": None, "_cancel": False}
        _jobs.clear()
        _jobs[job["job_id"]] = job

    def progress(done: int, total: int, day: str) -> None:
        job.update(done=done, total=total, current_date=day)

    def run() -> None:
        with session_factory() as db:
            try:
                if provider == "demo":
                    rows = demo_rows(start, end)
                    delete_universe(db, DEMO_UNIVERSE)
                    job["rows"] = store_rows(db, DEMO_UNIVERSE, rows, "demo")
                    days = len({r["trade_date"] for r in rows})
                    progress(days, days, max(r["trade_date"] for r in rows) if rows else "")
                else:
                    token = get_credential(db, "tushare")
                    if not token:
                        raise ValueError("还没有填 Tushare token")
                    job["rows"] = sync_tushare(db, token, start, end, progress=progress, cancelled=lambda: job["_cancel"])
                job["status"] = "cancelled" if job["_cancel"] else "done"
            except Exception as exc:  # shown to the user in the progress box
                db.rollback()
                job["status"], job["error"] = "error", str(exc)[:300]

    threading.Thread(target=run, name=job["job_id"], daemon=True).start()
    return _public(job)


def get_sync() -> dict[str, Any] | None:
    with _lock:
        job = next(iter(_jobs.values()), None)
        return _public(job) if job else None


def cancel_sync(job_id: str) -> dict[str, Any] | None:
    with _lock:
        job = _jobs.get(job_id)
        if job and job["status"] == "running":
            job["_cancel"] = True
        return _public(job) if job else None
