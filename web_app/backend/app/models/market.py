from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class MarketInstrument(Base):
    __tablename__ = "market_instruments"

    symbol: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    market: Mapped[str] = mapped_column(String(40), default="a_share")
    exchange: Mapped[str] = mapped_column(String(20))
    asset_type: Mapped[str] = mapped_column(String(40), default="stock")
    listed_date: Mapped[str | None] = mapped_column(String(20), nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
    )

    bars: Mapped[list["MarketBar"]] = relationship(back_populates="instrument")


class MarketBar(Base):
    __tablename__ = "market_bars"
    __table_args__ = (
        UniqueConstraint("symbol", "frequency", "trade_time", name="uq_market_bar_identity"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(ForeignKey("market_instruments.symbol"), index=True)
    frequency: Mapped[str] = mapped_column(String(20), index=True)
    trade_time: Mapped[str] = mapped_column(String(32), index=True)
    open: Mapped[float] = mapped_column(Float)
    high: Mapped[float] = mapped_column(Float)
    low: Mapped[float] = mapped_column(Float)
    close: Mapped[float] = mapped_column(Float)
    volume: Mapped[float] = mapped_column(Float)
    amount: Mapped[float] = mapped_column(Float)
    adj_factor: Mapped[float] = mapped_column(Float, default=1.0)
    source: Mapped[str] = mapped_column(String(80), default="seed")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    instrument: Mapped[MarketInstrument] = relationship(back_populates="bars")
