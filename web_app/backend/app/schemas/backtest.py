from typing import Any

from pydantic import BaseModel


class BacktestRunRequest(BaseModel):
    strategy: dict[str, Any]
    source_strategy_id: str | None = None


class BacktestRunResponse(BaseModel):
    backtest_id: str
    status: str
    metrics: dict[str, Any]
    report_path: str


class BacktestSummary(BaseModel):
    backtest_id: str
    strategy_id: str
    source_strategy_id: str | None = None
    strategy_version: int | None = None
    strategy_name: str
    symbol: str
    frequency: str
    status: str
    metrics: dict[str, Any]
    parameter_snapshot: dict[str, Any] | None = None


class BacktestListResponse(BaseModel):
    backtests: list[BacktestSummary]
