from typing import Any

from pydantic import BaseModel, Field


class StrategyValidationRequest(BaseModel):
    strategy: dict[str, Any]


class StrategyValidationResponse(BaseModel):
    ok: bool
    errors: list[str]
    warnings: list[str]


class StrategyCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    strategy: dict[str, Any]
    source_template_id: str | None = None
    change_note: str = "Initial version"


class StrategyUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    strategy: dict[str, Any] | None = None
    status: str | None = Field(default=None, pattern="^(draft|active|archived)$")
    change_note: str = "Updated strategy"


class StrategyResponse(BaseModel):
    strategy_id: str
    name: str
    market: str
    symbol: str
    frequency: str
    source_template_id: str | None = None
    status: str
    strategy: dict[str, Any]


class StrategyListResponse(BaseModel):
    strategies: list[StrategyResponse]


class StrategyVersionResponse(BaseModel):
    version: int
    change_note: str
    strategy: dict[str, Any]


class StrategyVersionListResponse(BaseModel):
    strategy_id: str
    versions: list[StrategyVersionResponse]
