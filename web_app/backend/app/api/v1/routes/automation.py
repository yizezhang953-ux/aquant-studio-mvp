"""Daily after-close job: settings, run now, test push, history."""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import User
from app.services import notify_service
from app.services.auth_service import get_current_user
from app.services.automation_service import get_settings, list_runs, run_daily, run_view, settings_view, update_settings

router = APIRouter()


class AutomationSettingsUpdate(BaseModel):
    enabled: bool | None = None
    run_time: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    provider_id: Literal["tencent", "demo"] | None = None
    notify_channel: Literal["none", "pushplus", "serverchan", "webhook"] | None = None
    notify_target: str | None = Field(default=None, max_length=500)  # omitted = keep the saved token


def _view(db: Session, user: User) -> dict:
    return {"settings": settings_view(get_settings(db, user.id)), "runs": [run_view(r) for r in list_runs(db, user.id)]}


@router.get("")
def get_automation(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    return _view(db, current_user)


@router.put("")
def put_automation(request: AutomationSettingsUpdate, current_user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)) -> dict:
    fields = request.model_dump()
    if fields["notify_target"] is not None:
        fields["notify_target"] = fields["notify_target"].strip()
    update_settings(db, current_user.id, **fields)
    return _view(db, current_user)


@router.post("/run")
def run_now(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    """Run the daily job right away (syncs data, so it can take a little while)."""
    return run_view(run_daily(db, current_user, "manual"))


@router.post("/test-notify")
def test_notify(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    setting = get_settings(db, current_user.id)
    if setting.notify_channel == "none":
        raise HTTPException(status_code=400, detail="先选择一种推送方式")
    try:
        notify_service.send(setting.notify_channel, setting.notify_target, "AQuant 测试推送",
                            "收到这条消息，说明每日自动运行的推送已经设置好了。")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"sent": True}
