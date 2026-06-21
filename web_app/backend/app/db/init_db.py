from app.db.session import SessionLocal
from app.services.database_service import initialize_database


def main() -> None:
    with SessionLocal() as db:
        status = initialize_database(db, seed=True)
    print(status)


if __name__ == "__main__":
    main()
