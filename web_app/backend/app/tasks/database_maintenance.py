"""Database maintenance: python -m app.tasks.database_maintenance {migrate|init|status|backup|restore|make-admin}."""
from __future__ import annotations

import argparse
import json

from app.db.session import SessionLocal
from app.services.auth_service import set_admin
from app.services.database_backup_service import create_database_backup, restore_database_backup
from app.services.database_service import create_database, get_database_status, initialize_database


def main() -> None:
    parser = argparse.ArgumentParser(description="AQuant Studio database maintenance tasks")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("migrate", help="Apply Alembic migrations (SQLite or PostgreSQL)")

    init_parser = subparsers.add_parser("init", help="Migrate and optionally seed data")
    init_parser.add_argument("--no-seed", action="store_true", help="Create schema without seed data")

    subparsers.add_parser("status", help="Print database status and row counts")

    backup_parser = subparsers.add_parser("backup", help="Create a gzipped JSON database backup")
    backup_parser.add_argument("--output-dir", default=None, help="Backup output directory")

    admin_parser = subparsers.add_parser("make-admin", help="Grant (or with --revoke remove) the administrator role")
    admin_parser.add_argument("email")
    admin_parser.add_argument("--revoke", action="store_true")

    restore_parser = subparsers.add_parser("restore", help="Replace all data with a backup (destructive)")
    restore_parser.add_argument("backup_path")
    restore_parser.add_argument("--confirm", action="store_true", help="Required: confirms data will be replaced")

    args = parser.parse_args()
    if args.command == "migrate":
        create_database()
        print(json.dumps({"status": "migrated"}))
        return
    with SessionLocal() as db:
        if args.command == "init":
            result = initialize_database(db, seed=not args.no_seed)
        elif args.command == "status":
            result = get_database_status(db)
        elif args.command == "backup":
            result = create_database_backup(db, output_dir=args.output_dir)
        elif args.command == "make-admin":
            user = set_admin(db, args.email, not args.revoke)
            result = {"email": user.email, "is_admin": user.is_admin}
        elif args.command == "restore":
            if not args.confirm:
                parser.error("restore replaces every table; re-run with --confirm")
            create_database()
            result = restore_database_backup(db, args.backup_path)
        else:
            parser.error(f"unknown command: {args.command}")
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
