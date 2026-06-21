from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.database_service import get_database_status, initialize_database


router = APIRouter()


@router.get("/status")
def database_status(db: Session = Depends(get_db)) -> dict:
    return get_database_status(db)


@router.post("/init")
def database_init(seed: bool = True, db: Session = Depends(get_db)) -> dict:
    return initialize_database(db, seed=seed)
