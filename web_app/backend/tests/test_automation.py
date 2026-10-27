from datetime import datetime

import pytest

from app.db.session import SessionLocal
from app.models import AutomationRun, User
from app.services import notify_service
from app.services.auth_service import set_admin
from app.services.automation_service import BEIJING, compose_message, is_due, run_daily, run_due_jobs, update_settings
from app.services.json_utils import read_json
from app.services.legacy_paths import TEMPLATE_MODULE
from test_app import a_symbol, register


def _paper(client, headers, symbol: str, start: str = "2026-06-01") -> dict:
    strategy = read_json(TEMPLATE_MODULE / "templates" / "rsi_reversal.json")
    response = client.post("/api/v1/paper", headers=headers, json={
        "name": "自动跟踪", "strategy": strategy, "symbols": [symbol], "initial_cash": 100000, "start_date": start})
    assert response.status_code == 200, response.text
    return response.json()


def test_daily_run_syncs_paper_stocks_and_pushes_orders(client) -> None:
    admin_headers, _ = register(client, "autoadmin")
    with SessionLocal() as db:
        admin = db.query(User).order_by(User.id.desc()).first()
        set_admin(db, admin.email)
    symbol = a_symbol("SZ")
    _paper(client, admin_headers, symbol)
    saved = client.put("/api/v1/automation", headers=admin_headers, json={
        "enabled": True, "run_time": "16:30", "provider_id": "demo", "notify_channel": "pushplus",
        "notify_target": "abcd1234567890wxyz"}).json()["settings"]
    assert saved["enabled"] and saved["notify_target_hint"] == "abcd…wxyz"  # the token is never sent back whole

    sent = []
    with SessionLocal() as db:
        admin = db.query(User).order_by(User.id.desc()).first()
        run = run_daily(db, admin, "manual", datetime(2026, 10, 27, 17, 0, tzinfo=BEIJING),
                        send=lambda *args: sent.append(args))
        summary = run.summary_json
    synced = [s for s in summary["synced"] if s["symbol"] == symbol][0]
    assert synced["ok"] and synced["last_date"] <= "2026-10-27"
    assert any(a["name"] == "自动跟踪" for a in summary["accounts"])
    assert run.notify_status == "sent" and len(sent) == 1
    channel, target, title, body = sent[0]
    assert channel == "pushplus" and target == "abcd1234567890wxyz"
    assert title.startswith("AQuant 2026-10-27 收盘") and "自动跟踪" in body and "不会自动下单" in body

    history = client.get("/api/v1/automation", headers=admin_headers).json()["runs"]
    assert history[0]["id"] == run.id and history[0]["status"] in ("ok", "partial")


def test_non_admin_runs_without_syncing_shared_data(client) -> None:
    headers, _ = register(client, "auto")
    with SessionLocal() as db:
        user = db.query(User).order_by(User.id.desc()).first()
        run = run_daily(db, user, "manual", send=lambda *a: None)
    assert run.summary_json["synced"] == [] and any("还没有模拟盘" in w for w in run.summary_json["warnings"])
    assert client.post("/api/v1/automation/test-notify", headers=headers).status_code == 400  # no channel chosen


def test_schedule_fires_once_per_trading_day_after_its_time(client) -> None:
    headers, _ = register(client, "sched")
    with SessionLocal() as db:
        user = db.query(User).order_by(User.id.desc()).first()
        setting = update_settings(db, user.id, enabled=True, run_time="16:30", provider_id="demo")
        tuesday = datetime(2026, 10, 27, 16, 29, tzinfo=BEIJING)
        assert not is_due(setting, tuesday)
        assert is_due(setting, tuesday.replace(minute=31))
        assert not is_due(setting, datetime(2026, 10, 31, 17, 0, tzinfo=BEIJING))  # Saturday
        user_id = user.id

    calls = []
    late = datetime(2026, 10, 27, 20, 5, tzinfo=BEIJING)  # computer switched on late: still runs that evening
    assert run_due_jobs(SessionLocal, late, send=lambda *a: calls.append(a)) >= 1
    assert run_due_jobs(SessionLocal, late.replace(minute=6), send=lambda *a: calls.append(a)) == 0  # not twice
    with SessionLocal() as db:
        assert db.query(AutomationRun).filter(AutomationRun.owner_id == user_id, AutomationRun.trigger == "schedule").count() == 1


def test_message_lists_orders_and_warnings() -> None:
    title, body = compose_message("2026-10-27", {
        "orders": [{"side": "buy", "symbol": "600519.SH", "name": "贵州茅台", "reason": "买入信号", "close": 1500.0,
                    "account_name": "茅台 RSI"}],
        "accounts": [{"name": "茅台 RSI", "total_return": 0.032, "day_change": -0.005, "positions": 0, "last_date": "2026-10-27"}],
        "warnings": ["1 只股票行情同步失败"]})
    assert title == "AQuant 2026-10-27 收盘：明天开盘 1 笔待执行"
    assert "**买入** 600519.SH 贵州茅台" in body and "+3.20%" in body and "-0.50%" in body and "同步失败" in body


@pytest.mark.parametrize("url,key", [
    ("https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=x", "markdown"),
    ("https://oapi.dingtalk.com/robot/send?access_token=x", "markdown"),
    ("https://open.feishu.cn/open-apis/bot/v2/hook/x", "content"),
])
def test_webhook_bodies_match_each_bot(url, key) -> None:
    target, body, form = notify_service.build_request("webhook", url, "标题", "内容")
    assert target == url and key in body and not form


def test_push_channels_build_requests_and_reject_bad_input() -> None:
    url, body, form = notify_service.build_request("serverchan", "SCT123", "t", "m")
    assert url == "https://sctapi.ftqq.com/SCT123.send" and form and body["desp"] == "m"
    url, body, _ = notify_service.build_request("pushplus", "tok", "t", "m")
    assert body["template"] == "markdown" and body["token"] == "tok"
    with pytest.raises(ValueError):
        notify_service.build_request("webhook", "http://example.com/hook", "t", "m")
    with pytest.raises(ValueError):
        notify_service.send("pushplus", "  ", "t", "m")
    with pytest.raises(ValueError, match="token"):
        notify_service._check("pushplus", {"code": 903, "msg": "无效的用户token"})
    notify_service._check("serverchan", {"code": 0})
