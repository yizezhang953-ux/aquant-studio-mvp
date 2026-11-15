"""Sector data (Tushare / CSV / demo) and the sector rotation backtest. Writes need an admin."""
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import SessionLocal, get_db
from app.models import User
from app.services import sector_data_service as sectors
from app.services.auth_service import get_current_admin, get_current_user
from app.services.rotation_service import backtest, factor_list

router = APIRouter()
DATE = r"^\d{4}-\d{2}-\d{2}$"


def _status(db: Session) -> dict:
    return {"universes": sectors.list_universes(db), "tushare_token_hint": sectors.credential_hint(db, "tushare"),
            "job": sectors.get_sync(), "factors": factor_list()}


@router.get("")
def sector_status(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    return _status(db)


class CredentialUpdate(BaseModel):
    provider: Literal["tushare"] = "tushare"
    secret: str = Field(min_length=8, max_length=500)


@router.put("/credentials")
def put_credential(request: CredentialUpdate, current_user: User = Depends(get_current_admin),
                   db: Session = Depends(get_db)) -> dict:
    sectors.save_credential(db, request.provider, request.secret.strip())
    return _status(db)


class SectorSyncRequest(BaseModel):
    provider: Literal["tushare", "demo"]
    start_date: str = Field(pattern=DATE)
    end_date: str | None = Field(default=None, pattern=DATE)


@router.post("/sync")
def start_sector_sync(request: SectorSyncRequest, current_user: User = Depends(get_current_admin),
                      db: Session = Depends(get_db)) -> dict:
    end = request.end_date or date.today().isoformat()
    if request.start_date > end:
        raise HTTPException(status_code=400, detail="开始日期不能晚于结束日期")
    if request.provider == "tushare" and not sectors.get_credential(db, "tushare"):
        raise HTTPException(status_code=400, detail="先填写并保存 Tushare token")
    try:
        return {"job": sectors.start_sync(SessionLocal, provider=request.provider, start=request.start_date, end=end)}
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/sync")
def latest_sector_sync(current_user: User = Depends(get_current_user)) -> dict:
    return {"job": sectors.get_sync()}


@router.post("/sync/{job_id}/cancel")
def cancel_sector_sync(job_id: str, current_user: User = Depends(get_current_admin)) -> dict:
    job = sectors.cancel_sync(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="sync job not found")
    return {"job": job}


@router.post("/import-csv")
async def import_sector_csv(universe: str = Form(min_length=1, max_length=40, pattern=r"^[\w\-一-鿿]+$"),
                            file: UploadFile = File(...), current_user: User = Depends(get_current_admin),
                            db: Session = Depends(get_db)) -> dict:
    if universe in (sectors.TUSHARE_UNIVERSE, sectors.DEMO_UNIVERSE):
        raise HTTPException(status_code=400, detail="这个名字留给内置数据源了，换一个名字")
    content = await file.read(sectors.MAX_CSV_BYTES + 1)
    if len(content) > sectors.MAX_CSV_BYTES:
        raise HTTPException(status_code=413, detail="文件太大（上限 40 MB）")
    try:
        rows = sectors.parse_csv(content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    stored = sectors.store_rows(db, universe, rows, "csv")
    return {"imported": stored, **_status(db)}


@router.delete("/{universe}")
def delete_sector_universe(universe: str, current_user: User = Depends(get_current_admin),
                           db: Session = Depends(get_db)) -> dict:
    job = sectors.get_sync()
    if job and job["status"] == "running":
        raise HTTPException(status_code=409, detail="同步进行中，先取消或等它结束")
    return {"deleted": sectors.delete_universe(db, universe), **_status(db)}


class RotationRequest(BaseModel):
    universe: str = Field(min_length=1, max_length=40)
    factor: Literal["net_active_buy", "momentum", "reversal", "turnover"] = "net_active_buy"
    windows: list[int] = Field(default=[20, 21, 22, 23, 24], min_length=1, max_length=10)
    top_n: int = Field(default=5, ge=1, le=50)
    frequency: Literal["weekly", "monthly"] = "weekly"
    fee_rate: float = Field(default=0.0, ge=0, le=0.05)  # per side, e.g. 0.001 = 0.1%
    start_date: str | None = Field(default=None, pattern=DATE)
    end_date: str | None = Field(default=None, pattern=DATE)


@router.post("/backtest")
def run_rotation_backtest(request: RotationRequest, current_user: User = Depends(get_current_user),
                          db: Session = Depends(get_db)) -> dict:
    if any(w < 1 or w > 500 for w in request.windows):
        raise HTTPException(status_code=400, detail="回看窗口要在 1 到 500 个交易日之间")
    try:
        return backtest(db, universe=request.universe, factor=request.factor, windows=request.windows,
                        top_n=request.top_n, frequency=request.frequency, fee_rate=request.fee_rate,
                        start=request.start_date, end=request.end_date)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
