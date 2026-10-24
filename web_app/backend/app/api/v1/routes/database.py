from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import User
from app.services.auth_service import get_current_admin
from app.services.database_service import get_database_status, initialize_database


router = APIRouter()


@router.get("/status")
def database_status(db: Session = Depends(get_db)) -> dict:
    return get_database_status(db)


@router.post("/init")
def database_init(
    seed: bool = True,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> dict:
    """Re-run migrations and re-sync templates / bundled sample data (administrators only)."""
    return initialize_database(db, seed=seed)
