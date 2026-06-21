from typing import Any

from pydantic import BaseModel


class BacktestRunRequest(BaseModel):
    strategy: dict[str, Any]


class BacktestRunResponse(BaseModel):
    backtest_id: str
    status: str
    metrics: dict[str, Any]
    report_path: str
