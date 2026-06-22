from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class BacktestRun(Base):
    __tablename__ = "backtest_runs"

    backtest_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    strategy_id: Mapped[str] = mapped_column(String(120), index=True)
    source_strategy_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    strategy_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    strategy_name: Mapped[str] = mapped_column(String(200))
    symbol: Mapped[str] = mapped_column(String(40), index=True)
    frequency: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(40), default="completed")
    start_date: Mapped[str | None] = mapped_column(String(20), nullable=True)
    end_date: Mapped[str | None] = mapped_column(String(20), nullable=True)
    metrics_json: Mapped[dict] = mapped_column(JSON)
    report_json: Mapped[dict] = mapped_column(JSON)
    parameter_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    trades: Mapped[list["BacktestTrade"]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
    )
    equity_points: Mapped[list["BacktestEquityPoint"]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
    )


class BacktestTrade(Base):
    __tablename__ = "backtest_trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    backtest_id: Mapped[str] = mapped_column(ForeignKey("backtest_runs.backtest_id"), index=True)
    symbol: Mapped[str] = mapped_column(String(40))
    entry_time: Mapped[str] = mapped_column(String(32))
    exit_time: Mapped[str] = mapped_column(String(32))
    entry_price: Mapped[float] = mapped_column(Float)
    exit_price: Mapped[float] = mapped_column(Float)
    quantity: Mapped[float] = mapped_column(Float)
    gross_pnl: Mapped[float] = mapped_column(Float)
    net_pnl: Mapped[float] = mapped_column(Float)
    return_pct: Mapped[float] = mapped_column(Float)
    exit_reason: Mapped[str] = mapped_column(String(80))

    run: Mapped[BacktestRun] = relationship(back_populates="trades")


class BacktestEquityPoint(Base):
    __tablename__ = "backtest_equity_points"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    backtest_id: Mapped[str] = mapped_column(ForeignKey("backtest_runs.backtest_id"), index=True)
    trade_time: Mapped[str] = mapped_column(String(32))
    cash: Mapped[float] = mapped_column(Float)
    position_qty: Mapped[float] = mapped_column(Float)
    close: Mapped[float] = mapped_column(Float)
    equity: Mapped[float] = mapped_column(Float)
    drawdown_pct: Mapped[float] = mapped_column(Float)

    run: Mapped[BacktestRun] = relationship(back_populates="equity_points")
