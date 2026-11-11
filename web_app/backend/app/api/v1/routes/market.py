"""Market data endpoints. Reads are public; every write to the shared market data needs an admin."""
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import SessionLocal, get_db
from app.models import User
from app.schemas.market import (
    IndexSyncRequest,
    BoardLotSyncResponse,
    CorporateActionImportRequest,
    CorporateActionListResponse,
    FxCoverageResponse,
    FxRateImportRequest,
    MarketBarListResponse,
    MarketBarResponse,
    MarketCoverageResponse,
    MarketCsvImportRequest,
    MarketCsvImportResponse,
    MarketDataDeleteResponse,
    MarketDataSourceListResponse,
    MarketDataSourceSummary,
    MarketDataSyncRequest,
    MarketDataSyncResponse,
    MarketImportBatchDetail,
    MarketImportBatchListResponse,
    MarketImportRequest,
    MarketImportResponse,
    MarketInstrumentListResponse,
    MarketInstrumentSummary,
    MarketQualityResponse,
)
from app.services.auth_service import get_current_admin, get_current_user
from app.services.benchmark_service import index_status, sync_indices
from app.services.market_data_source_service import (
    fetch_hk_board_lots,
    list_market_data_sources,
)
from app.services.market_sync_service import MAX_BATCH, TooManyBars, cancel_batch, get_batch, start_batch, sync_symbol
from app.services.quote_service import get_quotes, parse_symbols
from app.services.market_service import (
    delete_market_data,
    fx_coverage,
    get_market_coverage,
    get_market_import_batch,
    get_market_instrument,
    get_market_quality,
    import_corporate_actions,
    import_fx_rates,
    import_market_csv,
    import_market_data,
    list_corporate_actions,
    list_market_bars,
    list_market_import_batches,
    list_market_instruments,
    market_for_symbol,
    normalize_symbol,
    record_market_import_batch,
    set_board_lots,
)


router = APIRouter()
UPLOAD_CHUNK = 64 * 1024


def _too_many_bars(count: int) -> None:
    if count > settings.max_import_bars:
        raise HTTPException(status_code=413, detail=f"at most {settings.max_import_bars} bars per import")


@router.get("/instruments", response_model=MarketInstrumentListResponse)
def get_instruments(db: Session = Depends(get_db)) -> MarketInstrumentListResponse:
    instruments = [MarketInstrumentSummary(**item) for item in list_market_instruments(db)]
    return MarketInstrumentListResponse(instruments=instruments)


@router.get("/instruments/{symbol}", response_model=MarketInstrumentSummary)
def get_instrument(symbol: str, db: Session = Depends(get_db)) -> MarketInstrumentSummary:
    instrument = get_market_instrument(db, normalize_symbol(symbol))
    if instrument is None:
        raise HTTPException(status_code=404, detail="instrument not found")
    return MarketInstrumentSummary(**instrument)


@router.delete("/instruments/{symbol}", response_model=MarketDataDeleteResponse)
def delete_instrument_data(
    symbol: str,
    frequency: str | None = None,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> MarketDataDeleteResponse:
    """Delete a symbol's bars (one frequency, or all). Removes the symbol itself once it has no bars."""
    try:
        return MarketDataDeleteResponse(**delete_market_data(db, normalize_symbol(symbol), frequency))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="instrument not found") from exc


@router.get("/bars", response_model=MarketBarListResponse)
def get_bars(
    symbol: str,
    frequency: str = "1d",
    limit: int = Query(default=120, ge=1, le=5000),
    db: Session = Depends(get_db),
) -> MarketBarListResponse:
    symbol = normalize_symbol(symbol)
    if get_market_instrument(db, symbol) is None:
        raise HTTPException(status_code=404, detail="instrument not found")
    bars = list_market_bars(db, symbol=symbol, frequency=frequency, limit=limit)
    return MarketBarListResponse(
        symbol=symbol,
        frequency=frequency,
        bars=[
            MarketBarResponse(
                trade_time=bar.trade_time, open=bar.open, high=bar.high, low=bar.low, close=bar.close,
                volume=bar.volume, amount=bar.amount, adj_factor=bar.adj_factor, source=bar.source,
            )
            for bar in bars
        ],
    )


@router.get("/coverage", response_model=MarketCoverageResponse)
def get_coverage(db: Session = Depends(get_db)) -> MarketCoverageResponse:
    return MarketCoverageResponse(**get_market_coverage(db))


@router.get("/quality", response_model=MarketQualityResponse)
def get_quality(
    symbol: str | None = None,
    limit: int = Query(default=200, ge=1, le=5000),
    db: Session = Depends(get_db),
) -> MarketQualityResponse:
    return MarketQualityResponse(**get_market_quality(db, symbol=normalize_symbol(symbol) if symbol else None, limit=limit))


@router.get("/data-sources", response_model=MarketDataSourceListResponse)
def get_data_sources() -> MarketDataSourceListResponse:
    sources = [MarketDataSourceSummary(**item.__dict__) for item in list_market_data_sources()]
    return MarketDataSourceListResponse(sources=sources)


@router.post("/sync", response_model=MarketDataSyncResponse)
def sync_data_source(
    request: MarketDataSyncRequest,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> MarketDataSyncResponse:
    try:
        result = sync_symbol(db, owner_id=current_user.id, provider_id=request.provider_id, symbol=request.symbol,
                             start_date=request.start_date, end_date=request.end_date, frequency=request.frequency)
    except TooManyBars as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return MarketDataSyncResponse(
        provider_id=request.provider_id,
        symbol=result["symbol"],
        frequency=request.frequency,
        start_date=request.start_date,
        end_date=request.end_date,
        fetched_bars=result["fetched_bars"],
        inserted_bars=result["inserted_bars"],
        updated_bars=result["updated_bars"],
        total_bars=result["total_bars"],
        corporate_actions=result["corporate_actions"],
        fx_rates=result["fx_rates"],
        message="market data synchronized",
    )


class BatchSyncRequest(BaseModel):
    symbols: list[str] = Field(min_length=1, max_length=MAX_BATCH)
    start_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")  # for stocks with no data yet
    end_date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    provider_id: Literal["tencent", "demo"] = "tencent"


@router.post("/sync-batch")
def start_batch_sync(request: BatchSyncRequest, current_user: User = Depends(get_current_admin)) -> dict:
    """Sync many stocks in the background: new ones from start_date, the rest from their last bar."""
    symbols = parse_symbols(request.symbols)
    bad = [s for s in symbols if not _valid_symbol(s)]
    if bad:
        raise HTTPException(status_code=400, detail=f"看不懂这些代码：{'、'.join(bad[:10])}")
    end = request.end_date or date.today().isoformat()
    if request.start_date > end:
        raise HTTPException(status_code=400, detail="开始日期不能晚于结束日期")
    try:
        return start_batch(SessionLocal, owner_id=current_user.id, provider_id=request.provider_id, symbols=symbols,
                           first_start=request.start_date, end_date=end)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/sync-batch")
def latest_batch_sync(current_user: User = Depends(get_current_user)) -> dict:
    return {"job": get_batch()}


@router.post("/sync-batch/{job_id}/cancel")
def cancel_batch_sync(job_id: str, current_user: User = Depends(get_current_admin)) -> dict:
    job = cancel_batch(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="sync job not found")
    return {"job": job}


@router.get("/quotes")
def live_quotes(symbols: str = Query(min_length=1, max_length=8000)) -> dict:
    """Live prices (Tencent, ~3 s delayed). symbols: comma or space separated."""
    try:
        quotes = get_quotes(parse_symbols(symbols))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"quotes": list(quotes.values())}


def _valid_symbol(symbol: str) -> bool:
    try:
        market_for_symbol(symbol)
    except ValueError:
        return False
    return True


@router.get("/indices")
def list_indices(db: Session = Depends(get_db)) -> dict:
    """Benchmark indices (恒生指数, 沪深300) held for report comparisons."""
    return {"indices": index_status(db)}


@router.post("/indices/sync")
def sync_index_data(
    request: IndexSyncRequest,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> dict:
    try:
        results = sync_indices(db, request.start_date, request.end_date, request.provider_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"results": results, "indices": index_status(db)}


@router.post("/board-lots/sync", response_model=BoardLotSyncResponse)
def sync_board_lots(
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> BoardLotSyncResponse:
    try:
        updated = set_board_lots(db, fetch_hk_board_lots())
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return BoardLotSyncResponse(updated=updated, message="HK board lots updated from the HKEX securities list")


@router.get("/corporate-actions/{symbol}", response_model=CorporateActionListResponse)
def get_corporate_actions(symbol: str, db: Session = Depends(get_db)) -> CorporateActionListResponse:
    symbol = normalize_symbol(symbol)
    return CorporateActionListResponse(symbol=symbol, actions=list_corporate_actions(db, symbol))


@router.post("/corporate-actions", response_model=CorporateActionListResponse)
def post_corporate_actions(
    request: CorporateActionImportRequest,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> CorporateActionListResponse:
    try:
        import_corporate_actions(db, request.symbol, [a.model_dump() for a in request.actions], request.source)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    symbol = normalize_symbol(request.symbol)
    return CorporateActionListResponse(symbol=symbol, actions=list_corporate_actions(db, symbol))


@router.get("/fx", response_model=FxCoverageResponse)
def get_fx(db: Session = Depends(get_db)) -> FxCoverageResponse:
    return FxCoverageResponse(pairs=fx_coverage(db))


@router.post("/fx", response_model=FxCoverageResponse)
def post_fx(
    request: FxRateImportRequest,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> FxCoverageResponse:
    if len(request.rates) > settings.max_import_bars:
        raise HTTPException(status_code=413, detail=f"at most {settings.max_import_bars} rates per import")
    try:
        import_fx_rates(db, request.pair.upper(), request.rates, request.source)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return FxCoverageResponse(pairs=fx_coverage(db))


@router.post("/import", response_model=MarketImportResponse)
def import_data(
    request: MarketImportRequest,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> MarketImportResponse:
    _too_many_bars(len(request.bars))
    symbol = normalize_symbol(request.instrument.symbol)
    if any(normalize_symbol(bar.symbol) != symbol for bar in request.bars):
        raise HTTPException(status_code=400, detail="all bars must use the imported instrument symbol")
    try:
        result = import_market_data(db, request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    frequency = request.bars[0].frequency if request.bars else None
    record_market_import_batch(db, owner_id=current_user.id, import_type="manual", result=result, frequency=frequency)
    return MarketImportResponse(**result)


def _csv_import(db: Session, user: User, request: MarketCsvImportRequest, import_type: str, source: str) -> MarketCsvImportResponse:
    _too_many_bars(request.csv_text.count("\n"))
    result = import_market_csv(db, request)
    failed = result["parsed_rows"] == 0
    record_market_import_batch(
        db, owner_id=user.id, import_type=import_type, result=result, frequency=request.frequency,
        status="failed" if failed else "completed", source=source,
    )
    if failed:
        raise HTTPException(status_code=400, detail={"message": result["message"], "errors": result["errors"]})
    return MarketCsvImportResponse(**result)


@router.post("/import/csv", response_model=MarketCsvImportResponse)
def import_csv_data(
    request: MarketCsvImportRequest,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> MarketCsvImportResponse:
    if len(request.csv_text.encode("utf-8")) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail=f"CSV text exceeds {settings.max_upload_bytes} bytes")
    return _csv_import(db, current_user, request, "csv", "csv_text")


@router.post("/import/file", response_model=MarketCsvImportResponse)
async def import_csv_file(
    symbol: str = Form(...),
    name: str = Form(...),
    exchange: str | None = Form(None),
    frequency: str = Form("1d"),
    lot_size: int | None = Form(None),
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> MarketCsvImportResponse:
    def fail(message: str, status_code: int = 400) -> HTTPException:
        record_market_import_batch(
            db, owner_id=current_user.id, import_type="csv_file",
            result={"symbol": symbol, "message": "CSV file import failed", "errors": [message]},
            frequency=frequency, status="failed", source=file.filename,
        )
        return HTTPException(status_code=status_code, detail=message)

    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise fail("only .csv files are supported")
    chunks: list[bytes] = []
    size = 0
    while chunk := await file.read(UPLOAD_CHUNK):
        size += len(chunk)
        if size > settings.max_upload_bytes:
            raise fail(f"file exceeds {settings.max_upload_bytes} bytes", 413)
        chunks.append(chunk)
    try:
        csv_text = b"".join(chunks).decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise fail("CSV file must be UTF-8 encoded") from exc
    request = MarketCsvImportRequest(
        symbol=symbol, name=name, exchange=exchange, frequency=frequency, csv_text=csv_text,
        source=f"file:{file.filename}", lot_size=lot_size,
    )
    return _csv_import(db, current_user, request, "csv_file", file.filename)


@router.get("/imports", response_model=MarketImportBatchListResponse)
def get_imports(
    limit: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MarketImportBatchListResponse:
    return MarketImportBatchListResponse(imports=list_market_import_batches(db, current_user.id, limit=limit))


@router.get("/imports/{batch_id}", response_model=MarketImportBatchDetail)
def get_import_detail(
    batch_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MarketImportBatchDetail:
    batch = get_market_import_batch(db, current_user.id, batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="import batch not found")
    return MarketImportBatchDetail(**batch)
