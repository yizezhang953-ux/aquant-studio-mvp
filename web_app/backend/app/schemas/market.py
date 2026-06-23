from pydantic import BaseModel


class MarketInstrumentSummary(BaseModel):
    symbol: str
    name: str
    market: str
    exchange: str
    asset_type: str
    listed_date: str | None = None
    status: str
    bar_count: int = 0
    first_trade_time: str | None = None
    last_trade_time: str | None = None
    latest_close: float | None = None
    frequencies: list[str] = []


class MarketInstrumentListResponse(BaseModel):
    instruments: list[MarketInstrumentSummary]


class MarketBarResponse(BaseModel):
    trade_time: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    amount: float
    adj_factor: float
    source: str


class MarketBarListResponse(BaseModel):
    symbol: str
    frequency: str
    bars: list[MarketBarResponse]


class MarketCoverageItem(BaseModel):
    symbol: str
    name: str
    frequencies: list[str]
    bar_count: int
    first_trade_time: str | None = None
    last_trade_time: str | None = None
    quality_status: str


class MarketCoverageResponse(BaseModel):
    market: str
    instrument_count: int
    total_bar_count: int
    coverage: list[MarketCoverageItem]


class MarketInstrumentImport(BaseModel):
    symbol: str
    name: str
    market: str = "a_share"
    exchange: str
    asset_type: str = "stock"
    listed_date: str | None = None
    status: str = "active"


class MarketBarImport(BaseModel):
    symbol: str
    frequency: str = "1d"
    trade_time: str
    open: float
    high: float
    low: float
    close: float
    volume: float = 0
    amount: float = 0
    adj_factor: float = 1.0
    source: str = "manual"


class MarketImportRequest(BaseModel):
    instrument: MarketInstrumentImport
    bars: list[MarketBarImport]


class MarketImportResponse(BaseModel):
    symbol: str
    inserted_bars: int
    updated_bars: int
    total_bars: int
    message: str


class MarketCsvImportRequest(BaseModel):
    symbol: str
    name: str
    exchange: str
    frequency: str = "1d"
    csv_text: str
    source: str = "csv"


class MarketCsvImportResponse(BaseModel):
    symbol: str
    parsed_rows: int
    inserted_bars: int
    updated_bars: int
    total_bars: int
    skipped_rows: int
    errors: list[str]
    message: str


class MarketImportBatch(BaseModel):
    id: int
    import_type: str
    symbol: str
    frequency: str | None = None
    inserted_bars: int = 0
    updated_bars: int = 0
    skipped_rows: int = 0
    issue_count: int = 0
    status: str
    created_at: str


class MarketImportBatchDetail(MarketImportBatch):
    message: str
    source: str | None = None
    errors: list[str] = []
    payload: dict = {}


class MarketImportBatchListResponse(BaseModel):
    imports: list[MarketImportBatch]


class MarketQualityIssue(BaseModel):
    symbol: str
    frequency: str
    trade_time: str
    issue_type: str
    severity: str = "error"
    message: str


class MarketQualityResponse(BaseModel):
    checked_bar_count: int
    issue_count: int
    error_count: int = 0
    warning_count: int = 0
    quality_score: int = 100
    issue_summary: dict[str, int] = {}
    issues: list[MarketQualityIssue]
