from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class SectorDaily(Base):
    """One sector (industry index) on one day, for cross-sectional rotation backtests.

    ``universe`` names a set of sectors that are ranked against each other (e.g. citic40).
    Amounts are in CNY; the flow fields are empty when the source has no active buy/sell split.
    """

    __tablename__ = "sector_daily"
    __table_args__ = (UniqueConstraint("universe", "code", "trade_date", name="uq_sector_daily"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    universe: Mapped[str] = mapped_column(String(40), index=True)
    code: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(80))
    trade_date: Mapped[str] = mapped_column(String(10), index=True)
    close: Mapped[float] = mapped_column(Float)
    amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    float_mv: Mapped[float | None] = mapped_column(Float, nullable=True)
    buy_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    sell_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String(40))


class DataCredential(Base):
    """A data vendor's API token, kept in the local database (never in the repository)."""

    __tablename__ = "data_credentials"

    provider: Mapped[str] = mapped_column(String(40), primary_key=True)
    secret: Mapped[str] = mapped_column(String(500))
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
