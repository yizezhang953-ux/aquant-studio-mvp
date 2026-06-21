from typing import Any

from pydantic import BaseModel


class StrategyValidationRequest(BaseModel):
    strategy: dict[str, Any]


class StrategyValidationResponse(BaseModel):
    ok: bool
    errors: list[str]
    warnings: list[str]
