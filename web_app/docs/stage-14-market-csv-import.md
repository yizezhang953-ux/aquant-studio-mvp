# Stage 14 - Market CSV Bulk Import

## Goal

Move market data maintenance from single-row manual entry to practical bulk import. Users can paste CSV text into the web app and import many OHLCV bars for an A-share instrument in one action.

## Delivered Scope

- Added authenticated CSV import API.
- Added backend CSV parser with required-column validation.
- Added row-level parsing errors and skipped-row counts.
- Added frontend CSV paste/import form inside the market data panel.
- Added backend tests for successful CSV import and invalid CSV rejection.
- Kept existing market coverage, bar browser, and quality checks refreshed after import.

## Backend API

| Endpoint | Method | Auth | Purpose |
| --- | --- | --- | --- |
| `/api/v1/market/import/csv` | POST | Required | Parse CSV text and upsert OHLCV bars. |

## Required CSV Columns

```csv
trade_time,open,high,low,close,volume,amount
2024-03-01,20,21,19.5,20.8,1000,20800
2024-03-04,20.8,22,20.2,21.5,1200,25800
```

Required columns:

- `trade_time`
- `open`
- `high`
- `low`
- `close`

Optional columns:

- `volume`
- `amount`
- `adj_factor`

## Frontend UX

- Users can paste CSV text into the market panel.
- Users can set symbol, name, and frequency before import.
- After import, the selected symbol refreshes automatically and the chart/quality panel updates.

## Current Constraints

- CSV is pasted as text; file upload is still a future stage.
- The import path assumes one instrument per CSV submission.
- Deeper quality checks such as missing trading days and split/dividend adjustment validation are not included yet.

## Acceptance Checks

- Valid CSV inserts multiple bars.
- Invalid CSV with missing required columns returns `400`.
- Frontend TypeScript and production build pass.
- Existing manual import and quality checks remain green.
