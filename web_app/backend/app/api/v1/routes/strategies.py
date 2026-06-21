from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import User, UserStrategy
from app.schemas.strategy import (
    StrategyCreateRequest,
    StrategyListResponse,
    StrategyResponse,
    StrategyUpdateRequest,
    StrategyValidationRequest,
    StrategyValidationResponse,
    StrategyVersionListResponse,
    StrategyVersionResponse,
)
from app.services.auth_service import get_current_user
from app.services.strategy_repository import (
    create_strategy,
    delete_strategy,
    get_user_strategy,
    list_strategy_versions,
    list_user_strategies,
    update_strategy,
)
from app.services.strategy_service import validate_strategy_payload


router = APIRouter()


@router.post("/validate", response_model=StrategyValidationResponse)
def validate_strategy(request: StrategyValidationRequest) -> StrategyValidationResponse:
    result = validate_strategy_payload(request.strategy)
    return StrategyValidationResponse(**result)


@router.get("", response_model=StrategyListResponse)
def list_strategies(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StrategyListResponse:
    return StrategyListResponse(
        strategies=[_strategy_response(strategy) for strategy in list_user_strategies(db, current_user)]
    )


@router.post("", response_model=StrategyResponse, status_code=status.HTTP_201_CREATED)
def create_user_strategy(
    request: StrategyCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StrategyResponse:
    strategy = create_strategy(
        db,
        current_user,
        name=request.name,
        strategy_json=request.strategy,
        source_template_id=request.source_template_id,
        change_note=request.change_note,
    )
    return _strategy_response(strategy)


@router.get("/{strategy_id}", response_model=StrategyResponse)
def get_strategy(
    strategy_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StrategyResponse:
    return _strategy_response(get_user_strategy(db, current_user, strategy_id))


@router.put("/{strategy_id}", response_model=StrategyResponse)
def update_user_strategy(
    strategy_id: str,
    request: StrategyUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StrategyResponse:
    strategy = update_strategy(
        db,
        current_user,
        strategy_id,
        name=request.name,
        strategy_json=request.strategy,
        status_value=request.status,
        change_note=request.change_note,
    )
    return _strategy_response(strategy)


@router.delete("/{strategy_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_strategy(
    strategy_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    delete_strategy(db, current_user, strategy_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{strategy_id}/versions", response_model=StrategyVersionListResponse)
def get_strategy_versions(
    strategy_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StrategyVersionListResponse:
    versions = list_strategy_versions(db, current_user, strategy_id)
    return StrategyVersionListResponse(
        strategy_id=strategy_id,
        versions=[
            StrategyVersionResponse(
                version=version.version,
                change_note=version.change_note,
                strategy=version.strategy_json,
            )
            for version in versions
        ],
    )


def _strategy_response(strategy: UserStrategy) -> StrategyResponse:
    return StrategyResponse(
        strategy_id=strategy.strategy_id,
        name=strategy.name,
        market=strategy.market,
        symbol=strategy.symbol,
        frequency=strategy.frequency,
        source_template_id=strategy.source_template_id,
        status=strategy.status,
        strategy=strategy.strategy_json,
    )
