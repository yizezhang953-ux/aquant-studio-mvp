# Stage 12 - Market Data Browser

## Goal

Expose the seeded A-share market data as first-class backend APIs and connect it to the web app so users can inspect available instruments before editing or backtesting strategies.

## Delivered Scope

- Added market data API endpoints under `/api/v1/market`.
- Added instrument summary, bar list, and coverage response schemas.
- Added a backend service layer for market instrument summaries, K-line bars, and data coverage quality.
- Added frontend market data panel inside the main strategy workspace.
- Added test coverage for market data browser endpoints.
- Updated the structure checker to include the new market module.

## Backend API

| Endpoint | Method | Purpose |
| --- | --- | --- |
| `/api/v1/market/instruments` | GET | List available A-share instruments with bar counts and latest close. |
| `/api/v1/market/instruments/{symbol}` | GET | Read one instrument summary. |
| `/api/v1/market/bars?symbol=600519.SH&frequency=1d&limit=80` | GET | Read OHLCV bars for the selected symbol and frequency. |
| `/api/v1/market/coverage` | GET | Read overall market data coverage and quality status. |

## Frontend UX

- Users can select a symbol from the available A-share instruments.
- Users can switch available frequencies for that instrument.
- The panel shows latest close, K-line count, start/end date, exchange, and data quality status.
- A compact close-price bar chart gives a quick visual check of the loaded data.

## Current Constraints

- The market browser uses seeded demo A-share data from the existing data module.
- No external live data vendor is connected yet.
- Data quality status is currently structural: ready, incomplete, or empty.
- Intraday and broader A-share coverage should be added after a data vendor decision.

## Acceptance Checks

- Backend tests pass for the new market endpoints.
- Frontend TypeScript check and production build pass.
- Structure checker includes the new route, schema, service, and documentation.
