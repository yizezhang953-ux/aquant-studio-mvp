from pydantic import BaseModel


class SystemInfo(BaseModel):
    name: str
    market: str
    stage: str
    live_trading_status: str
