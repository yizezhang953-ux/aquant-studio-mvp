from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class PaperAccount(Base):
    """A virtual-money account that follows one strategy on a few stocks from ``start_date`` on.

    The strategy is frozen at creation, so later edits to the saved strategy don't rewrite history.
    """

    __tablename__ = "paper_accounts"

    account_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    source_strategy_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    strategy_json: Mapped[dict] = mapped_column(JSON)
    symbols_json: Mapped[list] = mapped_column(JSON)
    initial_cash: Mapped[float] = mapped_column(Float)
    start_date: Mapped[str] = mapped_column(String(10))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
