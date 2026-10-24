from fastapi import APIRouter

from app.schemas.system import SystemInfo


router = APIRouter()


@router.get("/system", response_model=SystemInfo)
def get_system_info() -> SystemInfo:
    return SystemInfo(
        name="AQuant Studio",
        market="a_share,hk_stock,hk_connect",
        stage="web_app_v0.2_multi_market",
        live_trading_status="blocked_for_live_trading",
    )
