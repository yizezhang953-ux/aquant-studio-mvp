from fastapi import APIRouter

from app.schemas.system import SystemInfo


router = APIRouter()


@router.get("/system", response_model=SystemInfo)
def get_system_info() -> SystemInfo:
    return SystemInfo(
        name="AQuant Studio",
        market="a_share",
        stage="web_app_stage_2_backend_api_mvp",
        live_trading_status="blocked_for_live_trading",
    )
