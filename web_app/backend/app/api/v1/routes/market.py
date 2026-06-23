from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.market import (
    MarketBarListResponse,
    MarketBarResponse,
    MarketCoverageResponse,
    MarketCsvImportRequest,
    MarketCsvImportResponse,
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
from app.models import User
from app.services.auth_service import get_current_user
from app.services.market_service import (
    get_market_coverage,
    get_market_instrument,
    get_market_import_batch,
    get_market_quality,
    import_market_csv,
    import_market_data,
    list_market_import_batches,
    list_market_bars,
    list_market_instruments,
    record_market_import_batch,
)
from app.services.market_data_source_service import (
    list_market_data_sources,
    sync_market_data_from_source,
)


router = APIRouter()


@router.get("/instruments", response_model=MarketInstrumentListResponse)
def get_instruments(db: Session = Depends(get_db)) -> MarketInstrumentListResponse:
    instruments = [MarketInstrumentSummary(**item) for item in list_market_instruments(db)]
    return MarketInstrumentListResponse(instruments=instruments)


@router.get("/instruments/{symbol}", response_model=MarketInstrumentSummary)
def get_instrument(symbol: str, db: Session = Depends(get_db)) -> MarketInstrumentSummary:
    instrument = get_market_instrument(db, symbol)
    if instrument is None:
        raise HTTPException(status_code=404, detail="instrument not found")
    return MarketInstrumentSummary(**instrument)


@router.get("/bars", response_model=MarketBarListResponse)
def get_bars(
    symbol: str,
    frequency: str = "1d",
    limit: int = Query(default=120, ge=1, le=1000),
    db: Session = Depends(get_db),
) -> MarketBarListResponse:
    if get_market_instrument(db, symbol) is None:
        raise HTTPException(status_code=404, detail="instrument not found")
    bars = list_market_bars(db, symbol=symbol, frequency=frequency, limit=limit)
    return MarketBarListResponse(
        symbol=symbol,
        frequency=frequency,
        bars=[
            MarketBarResponse(
                trade_time=bar.trade_time,
                open=bar.open,
                high=bar.high,
                low=bar.low,
                close=bar.close,
                volume=bar.volume,
                amount=bar.amount,
                adj_factor=bar.adj_factor,
                source=bar.source,
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
    limit: int = Query(default=200, ge=1, le=2000),
    db: Session = Depends(get_db),
) -> MarketQualityResponse:
    return MarketQualityResponse(**get_market_quality(db, symbol=symbol, limit=limit))


@router.get("/data-sources", response_model=MarketDataSourceListResponse)
def get_data_sources() -> MarketDataSourceListResponse:
    sources = [MarketDataSourceSummary(**item.__dict__) for item in list_market_data_sources()]
    return MarketDataSourceListResponse(sources=sources)


@router.post("/sync", response_model=MarketDataSyncResponse)
def sync_data_source(
    request: MarketDataSyncRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MarketDataSyncResponse:
    try:
        payload = sync_market_data_from_source(
            provider_id=request.provider_id,
            symbol=request.symbol,
            start_date=request.start_date,
            end_date=request.end_date,
            frequency=request.frequency,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    result = import_market_data(
        db,
        MarketImportRequest(
            instrument=payload.instrument,
            bars=payload.bars,
        ),
    )
    record_market_import_batch(
        db,
        owner_id=current_user.id,
        import_type="data_source_sync",
        result=result,
        frequency=request.frequency,
        source=request.provider_id,
    )
    return MarketDataSyncResponse(
        provider_id=request.provider_id,
        symbol=request.symbol,
        frequency=request.frequency,
        start_date=request.start_date,
        end_date=request.end_date,
        fetched_bars=len(payload.bars),
        inserted_bars=result["inserted_bars"],
        updated_bars=result["updated_bars"],
        total_bars=result["total_bars"],
        message="market data synchronized",
    )


@router.post("/import", response_model=MarketImportResponse)
def import_data(
    request: MarketImportRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MarketImportResponse:
    if any(bar.symbol != request.instrument.symbol for bar in request.bars):
        raise HTTPException(status_code=400, detail="all bars must use the imported instrument symbol")
    result = import_market_data(db, request)
    frequency = request.bars[0].frequency if request.bars else None
    record_market_import_batch(
        db,
        owner_id=current_user.id,
        import_type="manual",
        result=result,
        frequency=frequency,
    )
    return MarketImportResponse(**result)


@router.post("/import/csv", response_model=MarketCsvImportResponse)
def import_csv_data(
    request: MarketCsvImportRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MarketCsvImportResponse:
    result = import_market_csv(db, request)
    if result["parsed_rows"] == 0:
        record_market_import_batch(
            db,
            owner_id=current_user.id,
            import_type="csv",
            result=result,
            frequency=request.frequency,
            status="failed",
            source="csv_text",
        )
        raise HTTPException(status_code=400, detail={"message": result["message"], "errors": result["errors"]})
    record_market_import_batch(
        db,
        owner_id=current_user.id,
        import_type="csv",
        result=result,
        frequency=request.frequency,
        source="csv_text",
    )
    return MarketCsvImportResponse(**result)


@router.post("/import/file", response_model=MarketCsvImportResponse)
async def import_csv_file(
    symbol: str = Form(...),
    name: str = Form(...),
    exchange: str = Form(...),
    frequency: str = Form("1d"),
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MarketCsvImportResponse:
    if not file.filename or not file.filename.lower().endswith(".csv"):
        record_market_import_batch(
            db,
            owner_id=current_user.id,
            import_type="csv_file",
            result={
                "symbol": symbol,
                "message": "CSV file import failed",
                "errors": ["only .csv files are supported"],
            },
            frequency=frequency,
            status="failed",
            source=file.filename,
        )
        raise HTTPException(status_code=400, detail="only .csv files are supported")
    raw = await file.read()
    try:
        csv_text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail="CSV file must be UTF-8 encoded") from exc
    result = import_market_csv(
        db,
        MarketCsvImportRequest(
            symbol=symbol,
            name=name,
            exchange=exchange,
            frequency=frequency,
            csv_text=csv_text,
            source=f"file:{file.filename}",
        ),
    )
    if result["parsed_rows"] == 0:
        record_market_import_batch(
            db,
            owner_id=current_user.id,
            import_type="csv_file",
            result=result,
            frequency=frequency,
            status="failed",
            source=file.filename,
        )
        raise HTTPException(status_code=400, detail={"message": result["message"], "errors": result["errors"]})
    record_market_import_batch(
        db,
        owner_id=current_user.id,
        import_type="csv_file",
        result=result,
        frequency=frequency,
        source=file.filename,
    )
    return MarketCsvImportResponse(**result)


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
