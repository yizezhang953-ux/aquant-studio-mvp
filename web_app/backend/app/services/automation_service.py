"""The daily after-close job: refresh the paper accounts' stocks and the benchmark indices, replay every
paper account, list the orders due at the next open, and push a summary to the user's phone.

The scheduler is a background thread inside the running app (start.bat), so it only fires while the
app is open; a run missed while the computer was off happens as soon as the app starts that day.
"""
from __future__ import annotations

import logging
import threading
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AutomationRun, AutomationSetting, User
from app.services import notify_service
from app.services.benchmark_service import sync_indices
from app.services.market_sync_service import start_dates, sync_many
from app.services.signal_service import evaluate_paper_account, list_paper_accounts
from app.services.trading_calendar_service import is_trading_day

logger = logging.getLogger(__name__)

BEIJING = timezone(timedelta(hours=8))  # A-share and HK sessions both run on UTC+8, no daylight saving
FIRST_SYNC_DAYS = 400  # history fetched for a stock with no bars yet (covers MA200-style warm-up)
SIDES = {"buy": "买入", "sell": "卖出"}

Sender = Callable[[str, str, str, str], None]


def beijing_now() -> datetime:
    return datetime.now(BEIJING)


def _beijing_clock() -> datetime:
    """Run timestamps are stored as naive Beijing time, the way the user reads them."""
    return datetime.now(BEIJING).replace(tzinfo=None)


# --------------------------------------------------------------------------- settings

def get_settings(db: Session, owner_id: int) -> AutomationSetting:
    setting = db.get(AutomationSetting, owner_id)
    if setting is None:
        setting = AutomationSetting(owner_id=owner_id, enabled=False, run_time="16:30", provider_id="tencent",
                                    notify_channel="none", notify_target="")
        db.add(setting)
        db.commit()
        db.refresh(setting)
    return setting


def update_settings(db: Session, owner_id: int, **fields: Any) -> AutomationSetting:
    setting = get_settings(db, owner_id)
    for key, value in fields.items():
        if value is not None:
            setattr(setting, key, value)
    db.commit()
    db.refresh(setting)
    return setting


def settings_view(setting: AutomationSetting) -> dict[str, Any]:
    target = setting.notify_target or ""
    return {
        "enabled": setting.enabled,
        "run_time": setting.run_time,
        "provider_id": setting.provider_id,
        "notify_channel": setting.notify_channel,
        # the token is a password for the user's push channel: show only its ends
        "notify_target_hint": (target[:4] + "…" + target[-4:]) if len(target) > 12 else ("已填写" if target else ""),
        "last_run_date": setting.last_run_date,
        "channels": notify_service.CHANNELS,
    }


def list_runs(db: Session, owner_id: int, limit: int = 20) -> list[AutomationRun]:
    return list(db.scalars(select(AutomationRun).where(AutomationRun.owner_id == owner_id)
                           .order_by(AutomationRun.id.desc()).limit(limit)))


def run_view(run: AutomationRun) -> dict[str, Any]:
    return {
        "id": run.id, "run_date": run.run_date, "trigger": run.trigger, "status": run.status,
        "summary": run.summary_json, "message": run.message, "notify_status": run.notify_status,
        "notify_error": run.notify_error,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
    }


# --------------------------------------------------------------------------- the run

def _sync_stocks(db: Session, user: User, provider_id: str, symbols: dict[str, str], today: date) -> list[dict[str, Any]]:
    """symbols: {symbol: earliest paper start date}. Stocks with no bars yet get FIRST_SYNC_DAYS of history."""
    first = {s: (date.fromisoformat(d) - timedelta(days=FIRST_SYNC_DAYS)).isoformat() for s, d in symbols.items()}
    starts = start_dates(db, list(symbols), first)
    rows = sync_many(db, owner_id=user.id, provider_id=provider_id, starts=starts, end_date=today.isoformat())
    return sorted(rows, key=lambda r: r["symbol"])


def _order_line(order: dict[str, Any], account_name: str) -> str:
    close = order.get("close")
    price = f"，收盘 {close:.2f}" if isinstance(close, (int, float)) else ""
    return f"- **{SIDES.get(order['side'], order['side'])}** {order['symbol']} {order.get('name') or ''}" \
           f"（{order.get('reason', '')}，模拟盘「{account_name}」{price}）"


def _pct(value: Any) -> str:
    return "-" if value is None else f"{value * 100:+.2f}%"


def compose_message(run_date: str, summary: dict[str, Any]) -> tuple[str, str]:
    orders = summary["orders"]
    title = f"AQuant {run_date} 收盘：明天开盘 {len(orders)} 笔待执行" if orders else f"AQuant {run_date} 收盘：明天无操作"
    lines: list[str] = []
    if orders:
        lines.append("**明天开盘要执行的单**")
        lines += [_order_line(o, o["account_name"]) for o in orders]
    else:
        lines.append("所有模拟盘明天都不用操作。")
    if summary["accounts"]:
        lines.append("")
        lines.append("**模拟盘**")
        for a in summary["accounts"]:
            lines.append(f"- {a['name']}：总收益 {_pct(a['total_return'])}，当日 {_pct(a['day_change'])}，"
                         f"持仓 {a['positions']} 只，数据到 {a['last_date'] or '-'}")
    if summary["warnings"]:
        lines.append("")
        lines.append("**注意**")
        lines += [f"- {w}" for w in summary["warnings"]]
    lines.append("")
    lines.append("以上是模拟盘按策略算出的信号，不会自动下单。")
    return title, "\n".join(lines)


def run_daily(db: Session, user: User, trigger: str = "manual", now: datetime | None = None,
              send: Sender = notify_service.send) -> AutomationRun:
    now = now or beijing_now()
    today = now.date()
    setting = get_settings(db, user.id)
    run = AutomationRun(owner_id=user.id, run_date=today.isoformat(), trigger=trigger, status="running",
                        summary_json={}, message="", notify_status="off", started_at=_beijing_clock())
    db.add(run)
    db.commit()

    try:
        _fill_run(db, user, setting, run, now, send)
    except Exception as exc:
        logger.exception("daily run %s failed", run.id)
        db.rollback()
        run.status, run.message = "error", f"运行出错：{exc}"
        run.finished_at = _beijing_clock()
        db.commit()
    db.refresh(run)
    return run


def _fill_run(db: Session, user: User, setting: AutomationSetting, run: AutomationRun, now: datetime,
              send: Sender) -> None:
    today = now.date()
    warnings: list[str] = []
    accounts = list_paper_accounts(db, user.id)
    symbols: dict[str, str] = {}
    for account in accounts:
        for symbol in account.symbols_json:
            symbols[symbol] = min(symbols.get(symbol, account.start_date), account.start_date)

    synced: list[dict[str, Any]] = []
    if not accounts:
        warnings.append("还没有模拟盘：到「每日信号」页建一个，自动运行才有东西可跟踪")
    elif not user.is_admin:
        warnings.append("只有管理员账号能同步行情，这次用的是库里已有的数据")
    else:
        synced = _sync_stocks(db, user, setting.provider_id, symbols, today)
        failed = [s for s in synced if not s["ok"]]
        if failed:
            warnings.append(f"{len(failed)} 只股票行情同步失败：" + "；".join(f"{s['symbol']} {s['error']}" for s in failed[:5]))
        try:
            sync_indices(db, (today - timedelta(days=30)).isoformat(), today.isoformat(), setting.provider_id)
        except ValueError:
            db.rollback()

    account_rows: list[dict[str, Any]] = []
    orders: list[dict[str, Any]] = []
    for account in accounts:
        try:
            result = evaluate_paper_account(db, account, today.isoformat())
        except Exception as exc:  # one broken account must not stop the others
            logger.exception("paper account %s failed", account.account_id)
            warnings.append(f"模拟盘「{account.name}」计算出错：{exc}")
            continue
        summary = result["summary"]
        market = result.get("market") or "a_share"
        last_date = summary["last_date"]
        # after the close on a trading day the latest bar should be today's
        if is_trading_day(market, today) and now.hour >= 16 and (last_date or "") < today.isoformat():
            warnings.append(f"模拟盘「{account.name}」的数据只到 {last_date or '无'}，今天的行情还没同步到")
        account_rows.append({"account_id": account.account_id, "name": account.name, "equity": summary["equity"],
                             "total_return": summary["total_return"], "day_change": summary["day_change"],
                             "positions": summary["positions"], "last_date": last_date,
                             "pending": len(result["pending"])})
        orders += [{**o, "account_id": account.account_id, "account_name": account.name} for o in result["pending"]]

    summary_json = {"synced": synced, "accounts": account_rows, "orders": orders, "warnings": warnings}
    title, message = compose_message(today.isoformat(), summary_json)
    run.summary_json = summary_json
    run.message = f"{title}\n\n{message}"
    run.status = "partial" if warnings else "ok"
    if setting.notify_channel != "none":
        try:
            send(setting.notify_channel, setting.notify_target, title, message)
            run.notify_status = "sent"
        except ValueError as exc:
            run.notify_status, run.notify_error = "failed", str(exc)
    run.finished_at = _beijing_clock()
    db.commit()


# --------------------------------------------------------------------------- scheduler

def is_due(setting: AutomationSetting, now: datetime) -> bool:
    today = now.date()
    if not setting.enabled or setting.last_run_date == today.isoformat():
        return False
    if not (is_trading_day("a_share", today) or is_trading_day("hk_stock", today)):
        return False
    return now.strftime("%H:%M") >= setting.run_time


def run_due_jobs(session_factory: Callable[[], Session], now: datetime | None = None,
                 send: Sender = notify_service.send) -> int:
    now = now or beijing_now()
    count = 0
    with session_factory() as db:
        for setting in db.scalars(select(AutomationSetting).where(AutomationSetting.enabled.is_(True))).all():
            if not is_due(setting, now):
                continue
            setting.last_run_date = now.date().isoformat()  # mark first, so a crash doesn't retry all evening
            db.commit()
            user = db.get(User, setting.owner_id)
            if user is None:
                continue
            try:
                run_daily(db, user, "schedule", now, send)
                count += 1
            except Exception:
                logger.exception("daily automation failed for user %s", setting.owner_id)
                db.rollback()
    return count


class Scheduler:
    """Checks once a minute whether any user's daily job is due."""

    def __init__(self, session_factory: Callable[[], Session], interval: float = 60.0):
        self.session_factory = session_factory
        self.interval = interval
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, name="aquant-automation", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)

    def _loop(self) -> None:
        while not self._stop.wait(self.interval):
            try:
                run_due_jobs(self.session_factory)
            except Exception:
                logger.exception("automation scheduler tick failed")
