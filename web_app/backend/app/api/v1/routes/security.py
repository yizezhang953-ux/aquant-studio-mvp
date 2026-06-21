from fastapi import APIRouter

from app.core.config import settings
from app.schemas.security import SecurityStatus


router = APIRouter()


@router.get("/status", response_model=SecurityStatus)
def get_security_status() -> SecurityStatus:
    return SecurityStatus(
        live_trading_enabled=settings.live_trading_enabled,
        live_trading_status="blocked_for_live_trading",
        message="Live trading is disabled in the MVP web app.",
    )
