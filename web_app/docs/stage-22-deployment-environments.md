# Stage 22 - Deployment Environment Configuration

## Goal

Prepare AQuant Studio for online deployment on platforms such as Render, Railway, or Fly.io without changing the local development workflow.

## Delivered Scope

- Added backend deployment container template:
  - `deploy/backend.Dockerfile`
- Added frontend static deployment container template:
  - `deploy/frontend.Dockerfile`
  - `deploy/nginx.frontend.conf`
- Added platform templates:
  - `deploy/render.yaml`
  - `deploy/railway.backend.json`
  - `deploy/railway.frontend.json`
  - `deploy/fly.backend.toml`
  - `deploy/fly.frontend.toml`
- Added frontend environment configuration:
  - `frontend/.env.example`
  - `VITE_API_BASE_URL`
- Updated frontend API client to read `VITE_API_BASE_URL`.
- Updated backend CORS settings to accept comma-separated `ALLOWED_ORIGINS`.
- Added automated test coverage for deployment-style CORS parsing.

## Required Environment Variables

### Backend

```env
APP_ENV=production
LIVE_TRADING_ENABLED=false
DATABASE_URL=postgresql+psycopg://user:password@host:5432/database
ALLOWED_ORIGINS=https://your-frontend-domain.example
MARKET_DATA_PROVIDER=demo_a_share
TUSHARE_TOKEN=
```

### Frontend

```env
VITE_API_BASE_URL=https://your-backend-domain.example/api/v1
```

## Recommended Deployment Shape

Deploy as two services:

1. Backend API service
   - FastAPI
   - PostgreSQL connection through `DATABASE_URL`
   - Health check: `/health`

2. Frontend static site
   - Vite build output
   - API URL injected through `VITE_API_BASE_URL`

This keeps the frontend and backend independently scalable and makes CORS explicit.

## Platform Notes

### Render

Use `deploy/render.yaml` as a blueprint template. The backend uses Python runtime and the frontend uses static runtime. The user must set `DATABASE_URL`, `ALLOWED_ORIGINS`, and `VITE_API_BASE_URL` in the Render dashboard.

### Railway

Use one backend service and one frontend service. Each can use its matching Railway JSON template. The user must add a PostgreSQL database plugin or external PostgreSQL URL, then set environment variables.

### Fly.io

Use separate Fly apps for backend and frontend. The provided TOML files are templates; app names may need to be changed because Fly app names must be globally unique.

## User-Owned Steps

The user still needs to personally choose or create:

- Deployment platform account.
- PostgreSQL database instance.
- Production frontend domain.
- Production backend domain.
- Environment variable values in the platform dashboard.

No custom domain is required for testing. A custom domain can be added later after the app works on the platform-provided URLs.

## Verification Checklist

After deployment:

1. Open backend `/health`.
2. Open backend `/api/v1/database/status`.
3. Confirm response contains `database: ready`.
4. Confirm frontend loads.
5. Register a test account.
6. Create or copy a strategy.
7. Run one backtest.
8. Check browser console for CORS or API URL errors.
