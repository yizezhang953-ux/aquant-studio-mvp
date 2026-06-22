from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import BacktestRun, User
from app.schemas.backtest import (
    BacktestListResponse,
    BacktestRunRequest,
    BacktestRunResponse,
    BacktestSummary,
)
from app.services.auth_service import get_current_user
from app.services.backtest_service import (
    get_backtest_report,
    get_user_backtest,
    list_user_backtests,
    persist_backtest_report,
    run_backtest_payload,
)


router = APIRouter()


@router.post("", response_model=BacktestRunResponse)
def create_backtest(
    request: BacktestRunRequest,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> BacktestRunResponse:
    result = run_backtest_payload(request.strategy)
    report = get_backtest_report(result["backtest_id"])
    if report is not None and authorization:
        try:
            current_user = get_current_user(authorization=authorization, db=db)
            persist_backtest_report(
                db,
                result["backtest_id"],
                report,
                owner_id=current_user.id,
                source_strategy_id=request.source_strategy_id,
            )
        except HTTPException:
            pass
    return BacktestRunResponse(**result)


@router.get("", response_model=BacktestListResponse)
def list_backtests(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BacktestListResponse:
    return BacktestListResponse(backtests=[_summary(run) for run in list_user_backtests(db, current_user.id)])


@router.get("/mine/{backtest_id}")
def get_my_backtest(
    backtest_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    run = get_user_backtest(db, current_user.id, backtest_id)
    if run is None:
        raise HTTPException(status_code=404, detail="backtest not found")
    return run.report_json


@router.get("/{backtest_id}")
def get_backtest(backtest_id: str) -> dict:
    report = get_backtest_report(backtest_id)
    if report is None:
        raise HTTPException(status_code=404, detail="backtest not found")
    return report


@router.get("/{backtest_id}/report")
def get_backtest_report_endpoint(backtest_id: str) -> dict:
    report = get_backtest_report(backtest_id)
    if report is None:
        raise HTTPException(status_code=404, detail="backtest report not found")
    return report


def _summary(run: BacktestRun) -> BacktestSummary:
    return BacktestSummary(
        backtest_id=run.backtest_id,
        strategy_id=run.strategy_id,
        source_strategy_id=run.source_strategy_id,
        strategy_name=run.strategy_name,
        symbol=run.symbol,
        frequency=run.frequency,
        status=run.status,
        metrics=run.metrics_json,
    )
