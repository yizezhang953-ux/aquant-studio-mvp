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


class BacktestPeriod(BaseModel):
    start_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    end_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")


class BacktestBatchRequest(BaseModel):
    strategy: dict[str, Any]
    symbols: list[str] = Field(min_length=1, max_length=30)
    periods: list[BacktestPeriod] = Field(min_length=1, max_length=12)


class BacktestBatchRow(BaseModel):
    symbol: str
    name: str
    market: str
    start_date: str
    end_date: str
    ok: bool
    missing_data: bool
    error: str | None = None
    metrics: dict[str, Any]
    warning_count: int


class BacktestBatchResponse(BaseModel):
    rows: list[BacktestBatchRow]
    summary: dict[str, Any]
