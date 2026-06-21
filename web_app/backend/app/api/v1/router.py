from fastapi import APIRouter

from app.api.v1.routes import auth, backtests, database, security, strategies, system, templates


api_router = APIRouter()
api_router.include_router(system.router, tags=["system"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(security.router, prefix="/security", tags=["security"])
api_router.include_router(templates.router, prefix="/templates", tags=["templates"])
api_router.include_router(strategies.router, prefix="/strategies", tags=["strategies"])
api_router.include_router(backtests.router, prefix="/backtests", tags=["backtests"])
api_router.include_router(database.router, prefix="/database", tags=["database"])
