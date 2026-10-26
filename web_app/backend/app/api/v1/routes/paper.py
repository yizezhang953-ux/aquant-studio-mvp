from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import User
from app.services.auth_service import get_current_user
from app.services.market_service import normalize_symbol
from app.services.signal_service import (
    MAX_PAPER_SYMBOLS,
    MAX_SCAN,
    PaperInputError,
    create_paper_account,
    evaluate_paper_account,
    get_paper_account,
    list_paper_accounts,
    scan_signals,
)

router = APIRouter()


class ScanStrategy(BaseModel):
    strategy_id: str | None = None
    name: str | None = None
    strategy: dict[str, Any]


class SignalScanRequest(BaseModel):
    strategies: list[ScanStrategy] = Field(min_length=1, max_length=20)
    symbols: list[str] = Field(min_length=1, max_length=100)


class PaperCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    strategy: dict[str, Any]
    source_strategy_id: str | None = None
    symbols: list[str] = Field(min_length=1, max_length=MAX_PAPER_SYMBOLS)
    initial_cash: float = Field(gt=0, le=1e10)
    start_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")


def _symbols(raw: list[str]) -> list[str]:
    return list(dict.fromkeys(normalize_symbol(s) for s in raw if s.strip()))


@router.post("/signals/scan")
def scan(request: SignalScanRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    """Which stocks trigger each strategy's buy or sell rules on their latest close. Nothing is saved."""
    symbols = _symbols(request.symbols)
    if len(symbols) * len(request.strategies) > MAX_SCAN:
        raise HTTPException(status_code=400, detail=f"一次最多扫描 {MAX_SCAN} 组（股票数 × 策略数）")
    return scan_signals(db, [s.model_dump() for s in request.strategies], symbols)


@router.get("/paper")
def list_accounts(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    accounts = [evaluate_paper_account(db, a) for a in list_paper_accounts(db, current_user.id)]
    for account in accounts:  # the list only needs the headline numbers
        for key in ("curve", "trades", "sleeves"):
            account.pop(key)
    return {"accounts": accounts}


@router.post("/paper")
def create_account(request: PaperCreateRequest, current_user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)) -> dict:
    try:
        account = create_paper_account(db, current_user.id, request.name, request.strategy, request.source_strategy_id,
                                       _symbols(request.symbols), request.initial_cash, request.start_date)
    except PaperInputError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return evaluate_paper_account(db, account)


@router.get("/paper/{account_id}")
def get_account(account_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    account = get_paper_account(db, current_user.id, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="paper account not found")
    return evaluate_paper_account(db, account)


@router.delete("/paper/{account_id}")
def delete_account(account_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    account = get_paper_account(db, current_user.id, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="paper account not found")
    db.delete(account)
    db.commit()
    return {"deleted": account_id}
