from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import BacktestRun, User, UserStrategy
from app.schemas.backtest import (
    BacktestDeleteRequest,
    BacktestDeleteResponse,
    BacktestListResponse,
    BacktestRunRequest,
    BacktestRunResponse,
    BacktestSummary,
)
from app.services.auth_service import get_current_user
from app.services.backtest_service import (
    BacktestInputError,
    delete_user_backtests,
    get_user_backtest,
    list_user_backtests,
    persist_backtest_report,
    run_backtest_payload,
)


router = APIRouter()


@router.post("", response_model=BacktestRunResponse)
def create_backtest(
    request: BacktestRunRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BacktestRunResponse:
    """Run a backtest on the web database's market data and store it for the current user."""
    if request.source_strategy_id is not None:
        owned = db.scalar(select(UserStrategy).where(UserStrategy.strategy_id == request.source_strategy_id))
        if owned is None or (owned.owner_id is not None and owned.owner_id != current_user.id):
            raise HTTPException(status_code=404, detail="source strategy not found")
    try:
        report = run_backtest_payload(db, request.strategy)
    except BacktestInputError as exc:
        raise HTTPException(status_code=400, detail={"message": str(exc), "errors": exc.errors}) from exc
    backtest_id = report["backtest_id"]
    persist_backtest_report(db, backtest_id, report, owner_id=current_user.id, source_strategy_id=request.source_strategy_id)
    return BacktestRunResponse(
        backtest_id=backtest_id,
        status="completed",
        metrics=report["metrics"],
        warnings=report.get("warnings", []),
        market=report.get("market"),
        currency=report.get("currency"),
        report_path=f"/backtests/{backtest_id}",
    )


@router.get("", response_model=BacktestListResponse)
def list_backtests(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BacktestListResponse:
    return BacktestListResponse(backtests=[_summary(run) for run in list_user_backtests(db, current_user.id)])


@router.post("/delete", response_model=BacktestDeleteResponse)
def delete_backtests(
    request: BacktestDeleteRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BacktestDeleteResponse:
    return BacktestDeleteResponse(deleted=delete_user_backtests(db, current_user.id, request.backtest_ids))


@router.delete("/{backtest_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_backtest(
    backtest_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    if delete_user_backtests(db, current_user.id, [backtest_id]) == 0:
        raise HTTPException(status_code=404, detail="backtest not found")


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
def get_backtest(
    backtest_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    run = get_user_backtest(db, current_user.id, backtest_id)
    if run is None:
        raise HTTPException(status_code=404, detail="backtest not found")
    return run.report_json


@router.get("/{backtest_id}/report")
def get_backtest_report_endpoint(
    backtest_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    return get_backtest(backtest_id, current_user, db)


def _summary(run: BacktestRun) -> BacktestSummary:
    return BacktestSummary(
        backtest_id=run.backtest_id,
        strategy_id=run.strategy_id,
        source_strategy_id=run.source_strategy_id,
        strategy_version=run.strategy_version,
        strategy_name=run.strategy_name,
        symbol=run.symbol,
        frequency=run.frequency,
        status=run.status,
        start_date=run.start_date,
        end_date=run.end_date,
        created_at=run.created_at.isoformat() if run.created_at else None,
        metrics=run.metrics_json,
        parameter_snapshot=run.parameter_snapshot,
    )
