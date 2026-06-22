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
