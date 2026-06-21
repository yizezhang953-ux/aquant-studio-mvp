from fastapi import APIRouter

from app.api.v1.routes import security, system


api_router = APIRouter()
api_router.include_router(system.router, tags=["system"])
api_router.include_router(security.router, prefix="/security", tags=["security"])
