from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import BacktestRun, MarketInstrument, User, UserStrategy
from app.schemas.backtest import (
    BacktestBatchRequest,
    BacktestBatchResponse,
    BacktestDeleteRequest,
    BacktestDeleteResponse,
    BacktestListResponse,
    BacktestRenameRequest,
    BacktestRunRequest,
    BacktestRunResponse,
    BacktestSummary,
)
from app.services.auth_service import get_current_user
from app.services.market_service import normalize_symbol
from app.services.backtest_service import (
    BacktestInputError,
    backtest_name,
    delete_user_backtests,
    get_user_backtest,
    list_user_backtests,
    persist_backtest_report,
    rename_user_backtest,
    run_batch_backtests,
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
    runs = list_user_backtests(db, current_user.id)
    symbols = {run.symbol for run in runs}
    names = {i.symbol: i.name for i in db.scalars(select(MarketInstrument).where(MarketInstrument.symbol.in_(symbols)))}
    return BacktestListResponse(backtests=[_summary(run, backtest_name(db, run, names)) for run in runs])


@router.patch("/{backtest_id}", response_model=BacktestSummary)
def rename_backtest(
    backtest_id: str,
    request: BacktestRenameRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BacktestSummary:
    """Rename a saved run; an empty name restores the generated one."""
    run = rename_user_backtest(db, current_user.id, backtest_id, request.display_name)
    if run is None:
        raise HTTPException(status_code=404, detail="backtest not found")
    return _summary(run, backtest_name(db, run))


@router.post("/batch", response_model=BacktestBatchResponse)
def create_batch_backtest(
    request: BacktestBatchRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BacktestBatchResponse:
    """Run one strategy on several stocks and periods; results are returned, not saved."""
    symbols = list(dict.fromkeys(normalize_symbol(s) for s in request.symbols if s.strip()))
    periods = [(p.start_date, p.end_date) for p in request.periods]
    if any(start > end for start, end in periods):
        raise HTTPException(status_code=400, detail="开始日期不能晚于结束日期")
    if len(symbols) * len(periods) > 120:
        raise HTTPException(status_code=400, detail="一次最多 120 组（股票数 × 时间段数）")
    return BacktestBatchResponse(**run_batch_backtests(db, request.strategy, symbols, periods))


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


def _summary(run: BacktestRun, name: str) -> BacktestSummary:
    return BacktestSummary(
        backtest_id=run.backtest_id,
        display_name=name,
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
