from pydantic import BaseModel


class SecurityStatus(BaseModel):
    live_trading_enabled: bool
    live_trading_status: str
    message: str
