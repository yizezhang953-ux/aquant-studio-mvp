# Stage 23 - Online Database Initialization and Backup

## Goal

Prepare safe operational procedures for initializing an online PostgreSQL database and creating portable backups after deployment.

## Delivered Scope

- Added database backup service:
  - `backend/app/services/database_backup_service.py`
- Added backend maintenance CLI:
  - `backend/app/tasks/database_maintenance.py`
- Added environment variable:
  - `BACKUP_DIR=runtime/backups`
- Added automated backup test coverage.
- Extended structure checks for maintenance and backup files.

## Online Database Initialization

Run these commands in the backend service environment after `DATABASE_URL` points to the production PostgreSQL database.

```bash
python -m app.tasks.database_maintenance status
python -m app.tasks.database_maintenance init
python -m app.tasks.database_maintenance status
```

To create schema without seed data:

```bash
python -m app.tasks.database_maintenance init --no-seed
```

The application also still creates tables on startup, but the maintenance command gives a clearer deployment-time operation and prints a JSON result.

## Backup

Create a compressed JSON backup:

```bash
python -m app.tasks.database_maintenance backup
```

To choose a directory:

```bash
python -m app.tasks.database_maintenance backup --output-dir runtime/backups
```

The backup file is written as:

```text
aquant-backup-YYYYMMDD-HHMMSS.json.gz
```

It includes:

- metadata
- database dialect
- table row counts
- all current application table rows

## Recommended Online Backup Policy

- Before every manual deployment: create one backup.
- After database schema changes: create one backup.
- Weekly during early testing: create one backup.
- Before importing large market data files: create one backup.

## Restore Boundary

This stage delivers export backups and initialization procedures. Full automated restore is intentionally left for a later stage because restoring production data should include confirmation, conflict handling, and platform-specific PostgreSQL restore checks.

For emergency recovery, the backup JSON can be inspected and transformed into insert operations, but production restore should be implemented as a separate controlled task.

## User-Owned Steps

The user must personally:

- Create the online PostgreSQL database in the chosen platform.
- Copy the production `DATABASE_URL` into backend environment variables.
- Decide where backup files are stored or downloaded.
- Download backups from the platform if the runtime filesystem is temporary.

For Render/Railway/Fly free or container environments, local runtime disks may be ephemeral. Important backups should be downloaded or copied to persistent storage.
