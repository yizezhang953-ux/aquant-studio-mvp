from typing import Any

from pydantic import BaseModel, Field


class BacktestRunRequest(BaseModel):
    strategy: dict[str, Any]
    source_strategy_id: str | None = None


class BacktestRunResponse(BaseModel):
    backtest_id: str
    status: str
    metrics: dict[str, Any]
    warnings: list[str] = []
    market: str | None = None
    currency: str | None = None
    report_path: str


class BacktestSummary(BaseModel):
    backtest_id: str
    strategy_id: str
    source_strategy_id: str | None = None
    strategy_version: int | None = None
    strategy_name: str
    display_name: str
    symbol: str
    frequency: str
    status: str
    start_date: str | None = None
    end_date: str | None = None
    created_at: str | None = None
    metrics: dict[str, Any]
    parameter_snapshot: dict[str, Any] | None = None


class BacktestListResponse(BaseModel):
    backtests: list[BacktestSummary]


class BacktestDeleteRequest(BaseModel):
    backtest_ids: list[str] = Field(min_length=1, max_length=500)


class BacktestDeleteResponse(BaseModel):
    deleted: int


class BacktestRenameRequest(BaseModel):
    display_name: str = Field(default="", max_length=200)
