# AQuant Studio Web App

FastAPI backend + React/Vite frontend for A-share, HK and Southbound Stock Connect (港股通) strategy research.

```text
web_app/
  backend/
    app/            api routes, models, schemas, services, tasks
    alembic/        database migrations (SQLite and PostgreSQL)
    tests/          API tests (isolated temporary database)
    requirements.txt, pyproject.toml, .env.example
  frontend/         React 18 + Vite
  deploy/           Dockerfiles, nginx template, Fly / Railway / Render configs
  docs/             stage-by-stage delivery notes (historical)
```

## Run locally

```bash
cd web_app/backend
pip install -r requirements.txt
uvicorn app.main:app --reload            # migrates the database and seeds templates/sample data on first start

cd web_app/frontend
pnpm install && pnpm dev                 # http://localhost:5173
```

The first account registered on a local install (`APP_ENV=local`) is an administrator. On a server, register
and then run `python -m app.tasks.database_maintenance make-admin you@example.com`.
Administrators write the shared market data (import / sync / corporate actions / FX / board lots); every
user can run backtests, which are private to their owner.

## Market data

- `POST /api/v1/market/sync` with `provider_id: "tencent"` loads raw daily bars, adj_factor and inferred
  dividends for A-shares and HK stocks; HK symbols also load HKD→CNY rates for 港股通.
- `POST /api/v1/market/board-lots/sync` updates HK board lots from the HKEX securities list.
- `POST /api/v1/market/corporate-actions` and `POST /api/v1/market/fx` accept exact data from other sources.
- Backtests and strategy validation read these tables directly.

## Maintenance

```bash
python -m app.tasks.database_maintenance migrate
python -m app.tasks.database_maintenance status
python -m app.tasks.database_maintenance backup --output-dir /data/backups
python -m app.tasks.database_maintenance restore /data/backups/aquant-backup-....json.gz --confirm
python -m app.tasks.database_maintenance make-admin you@example.com
```

Backups never contain login sessions (restored users sign in again) but do contain password hashes — keep them private.

## Deploy

- Backend image: `web_app/deploy/backend.Dockerfile` (data on the `/data` volume, runs as a non-root user).
- Frontend image: `web_app/deploy/frontend.Dockerfile --build-arg VITE_API_BASE_URL=https://<api>/api/v1`.
- Set `ALLOWED_ORIGINS` on the backend to the frontend origin. For PostgreSQL set `DATABASE_URL`.
