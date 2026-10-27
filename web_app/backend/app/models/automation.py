from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class AutomationSetting(Base):
    """One user's daily after-close job: when it runs and where its summary is pushed."""

    __tablename__ = "automation_settings"

    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    run_time: Mapped[str] = mapped_column(String(5), default="16:30")  # Beijing time, HH:MM
    provider_id: Mapped[str] = mapped_column(String(40), default="tencent")
    notify_channel: Mapped[str] = mapped_column(String(20), default="none")  # none / pushplus / serverchan / webhook
    notify_target: Mapped[str] = mapped_column(String(500), default="")  # token, SendKey or webhook URL
    last_run_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class AutomationRun(Base):
    """What one daily run did: data synced, paper accounts updated, orders due at the next open."""

    __tablename__ = "automation_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    run_date: Mapped[str] = mapped_column(String(10))
    trigger: Mapped[str] = mapped_column(String(20))  # schedule / manual
    status: Mapped[str] = mapped_column(String(20))  # ok / partial / error
    summary_json: Mapped[dict] = mapped_column(JSON)
    message: Mapped[str] = mapped_column(Text, default="")
    notify_status: Mapped[str] = mapped_column(String(20), default="off")  # off / sent / failed
    notify_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
