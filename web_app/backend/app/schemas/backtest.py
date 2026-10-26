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


class OptimizeParameter(BaseModel):
    path: str = Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9_.]+$")
    label: str = Field(min_length=1, max_length=60)
    values: list[float] = Field(min_length=1, max_length=50)


class OptimizeValidation(BaseModel):
    method: str = Field(default="holdout", pattern=r"^(holdout|walk_forward)$")
    train_ratio: float = Field(default=0.7, ge=0.3, le=0.9)
    split_date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    folds: int = Field(default=3, ge=2, le=6)
    initial_train_ratio: float = Field(default=0.5, ge=0.3, le=0.8)


class BacktestOptimizeRequest(BaseModel):
    strategy: dict[str, Any]
    parameters: list[OptimizeParameter] = Field(min_length=1, max_length=4)
    metric: str = "total_return"
    validation: OptimizeValidation = OptimizeValidation()
