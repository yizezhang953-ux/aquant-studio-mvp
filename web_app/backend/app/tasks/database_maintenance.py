from __future__ import annotations

import argparse
import json

from app.db.session import SessionLocal
from app.services.database_backup_service import create_database_backup
from app.services.database_service import get_database_status, initialize_database


def main() -> None:
    parser = argparse.ArgumentParser(description="AQuant Studio database maintenance tasks")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Create schema and optionally seed data")
    init_parser.add_argument("--no-seed", action="store_true", help="Create schema without seed data")

    subparsers.add_parser("status", help="Print database status and row counts")

    backup_parser = subparsers.add_parser("backup", help="Create a gzipped JSON database backup")
    backup_parser.add_argument("--output-dir", default=None, help="Backup output directory")

    args = parser.parse_args()
    with SessionLocal() as db:
        if args.command == "init":
            result = initialize_database(db, seed=not args.no_seed)
        elif args.command == "status":
            result = get_database_status(db)
        elif args.command == "backup":
            result = create_database_backup(db, output_dir=args.output_dir)
        else:
            parser.error(f"unknown command: {args.command}")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
