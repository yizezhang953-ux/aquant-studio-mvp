from fastapi import APIRouter

from app.schemas.strategy import StrategyValidationRequest, StrategyValidationResponse
from app.services.strategy_service import validate_strategy_payload


router = APIRouter()


@router.post("/validate", response_model=StrategyValidationResponse)
def validate_strategy(request: StrategyValidationRequest) -> StrategyValidationResponse:
    result = validate_strategy_payload(request.strategy)
    return StrategyValidationResponse(**result)
