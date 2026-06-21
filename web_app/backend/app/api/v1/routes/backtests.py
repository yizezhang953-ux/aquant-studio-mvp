from fastapi import APIRouter, HTTPException

from app.schemas.backtest import BacktestRunRequest, BacktestRunResponse
from app.services.backtest_service import get_backtest_report, run_backtest_payload


router = APIRouter()


@router.post("", response_model=BacktestRunResponse)
def create_backtest(request: BacktestRunRequest) -> BacktestRunResponse:
    result = run_backtest_payload(request.strategy)
    return BacktestRunResponse(**result)


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
