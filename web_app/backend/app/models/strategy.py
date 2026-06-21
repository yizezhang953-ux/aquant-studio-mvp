from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class UserStrategy(Base):
    __tablename__ = "user_strategies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    strategy_id: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    market: Mapped[str] = mapped_column(String(40), default="a_share")
    symbol: Mapped[str] = mapped_column(String(40))
    frequency: Mapped[str] = mapped_column(String(20))
    source_template_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="draft")
    strategy_json: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
    )

    versions: Mapped[list["StrategyVersion"]] = relationship(
        back_populates="strategy",
        cascade="all, delete-orphan",
    )


class StrategyVersion(Base):
    __tablename__ = "strategy_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    strategy_id: Mapped[str] = mapped_column(ForeignKey("user_strategies.strategy_id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    change_note: Mapped[str] = mapped_column(Text, default="")
    strategy_json: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    strategy: Mapped[UserStrategy] = relationship(back_populates="versions")
