# Stage 21 - PostgreSQL Migration

## Goal

Prepare AQuant Studio to run on PostgreSQL for online deployment while keeping SQLite available for local development.

## Delivered Scope

- Added PostgreSQL driver dependency: `psycopg[binary]`.
- Updated database session creation to support:
  - `sqlite:///...`
  - `postgresql+psycopg://...`
  - cloud-style `postgres://...` URLs
  - plain `postgresql://...` URLs
- Added connection health checking with SQLAlchemy `pool_pre_ping=True`.
- Kept SQLite `check_same_thread=False` only for SQLite connections.
- Added database dialect to `/api/v1/database/status` and `/api/v1/database/init`.
- Updated `.env.example` with a PostgreSQL `DATABASE_URL` template.
- Added automated tests for PostgreSQL URL normalization and connection argument selection.

## Local Development

SQLite remains the default:

```env
DATABASE_URL=sqlite:///./aquant_web_app.db
```

This keeps the app easy to run without installing a database server.

## PostgreSQL Configuration

For PostgreSQL, set:

```env
DATABASE_URL=postgresql+psycopg://aquant:aquant_password@localhost:5432/aquant_studio
```

Many cloud platforms expose URLs in this form:

```env
DATABASE_URL=postgres://user:password@host:5432/database
```

The backend now normalizes that automatically to the SQLAlchemy `psycopg` driver URL.

## Migration Procedure

1. Create a PostgreSQL database.
2. Set the backend environment variable `DATABASE_URL`.
3. Install backend dependencies.
4. Run the database initializer:

```bash
python -m app.db.init_db
```

5. Start the backend.
6. Check:

```http
GET /api/v1/database/status
```

The response should include:

```json
{
  "database": "ready",
  "dialect": "postgresql"
}
```

## What The User Must Do Later

For a deployed online app, the user must personally create or approve the managed PostgreSQL database because it may involve account ownership and billing. Recommended options:

- Supabase
- Render PostgreSQL
- Railway PostgreSQL
- Neon

After the database is created, copy its connection string into the backend deployment environment as `DATABASE_URL`.

## Current Boundary

This stage makes the application PostgreSQL-ready. It does not yet create a paid cloud database or perform live production data migration from an existing SQLite file.
