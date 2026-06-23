# Stage 20 - Real Market Data Source Integration Plan

## Goal

Build the first production-shaped data source layer for AQuant Studio. The application should no longer depend only on manual input and CSV upload; it should expose a stable synchronization API that can later connect to real A-share providers such as Tushare, AkShare, exchange files, or a paid vendor.

## Delivered Scope

- Added a provider abstraction in `backend/app/services/market_data_source_service.py`.
- Added `GET /api/v1/market/data-sources` to list available providers and their readiness.
- Added `POST /api/v1/market/sync` to fetch bars from a selected provider and write them through the existing market import pipeline.
- Added a deterministic `demo_a_share` provider for safe local development, testing, and frontend integration.
- Added a `tushare` provider placeholder with explicit token readiness checks.
- Added configuration fields:
  - `MARKET_DATA_PROVIDER`
  - `TUSHARE_TOKEN`
- Added automated tests for provider listing, authenticated sync, imported bars, import history, and unsupported frequency handling.

## Current Provider Matrix

| Provider | Status | Purpose | Notes |
| --- | --- | --- | --- |
| `demo_a_share` | Ready | Local development and automated tests | Generates deterministic 1d A-share bars without network access. |
| `tushare` | Planned | Real A-share daily bars | Requires user-created Tushare account, API token, dependency installation, and provider adapter activation. |

## API Contract

### List Data Sources

`GET /api/v1/market/data-sources`

Returns provider id, market, status, auth requirement, supported frequencies, and setup note.

### Sync Market Data

`POST /api/v1/market/sync`

Authenticated request body:

```json
{
  "provider_id": "demo_a_share",
  "symbol": "600519.SH",
  "start_date": "2024-03-01",
  "end_date": "2024-03-05",
  "frequency": "1d"
}
```

Response includes fetched, inserted, updated, and total bar counts. Imported rows are recorded in market import history as `data_source_sync`.

## Real Provider Rollout Steps

1. Choose the production provider: Tushare is recommended for the next implementation because it has broad A-share coverage and a clear token model.
2. Create the provider account personally, because API tokens and billing belong to the user.
3. Store the token in backend `.env` as `TUSHARE_TOKEN=...`.
4. Add the provider dependency to backend packaging.
5. Implement provider-specific symbol conversion, date conversion, retry handling, and rate-limit handling.
6. Add data normalization checks before import: OHLC validity, duplicate bars, trading calendar gaps, and source metadata.
7. Add scheduled synchronization after manual sync is stable.

## Product Boundary

This stage creates the real integration architecture and a safe sync endpoint. It does not yet make live internet calls because the current development environment has restricted network access and no user-owned market data token.
