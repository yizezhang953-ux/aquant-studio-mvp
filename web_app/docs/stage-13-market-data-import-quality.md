# Stage 13 - Market Data Import and Quality Check

## Goal

Turn the market data module from a read-only browser into a maintainable data entry path. Users can now import or update A-share OHLCV bars through the backend and inspect basic data quality from the web app.

## Delivered Scope

- Added authenticated market data import API.
- Added market data quality check API.
- Added upsert logic for instruments and OHLCV bars.
- Added frontend controls to manually import or update a daily bar.
- Added frontend quality summary for the selected instrument.
- Added backend tests for authenticated import, update, bar readback, and quality check.

## Backend API

| Endpoint | Method | Auth | Purpose |
| --- | --- | --- | --- |
| `/api/v1/market/import` | POST | Required | Upsert one instrument and one or more OHLCV bars. |
| `/api/v1/market/quality?symbol=600519.SH` | GET | Public | Check recent bars for invalid OHLC or negative volume/amount. |

## Import Contract

```json
{
  "instrument": {
    "symbol": "600519.SH",
    "name": "贵州茅台",
    "market": "a_share",
    "exchange": "SH",
    "asset_type": "stock",
    "status": "active"
  },
  "bars": [
    {
      "symbol": "600519.SH",
      "frequency": "1d",
      "trade_time": "2024-02-01",
      "open": 1660,
      "high": 1680,
      "low": 1650,
      "close": 1672,
      "volume": 1000,
      "amount": 1672000,
      "adj_factor": 1,
      "source": "manual"
    }
  ]
}
```

## Frontend UX

- The market panel now shows quality issue count for the selected symbol.
- Users can enter code, name, exchange, date, and close price to import or update a daily bar.
- After import, the panel refreshes instrument coverage, K-line data, and quality status.

## Current Constraints

- Manual frontend import uses one close-price daily bar and sets OHLC to the same price.
- Bulk CSV upload and vendor scheduled sync are still future stages.
- Quality checks are intentionally lightweight and structural at this stage.

## Acceptance Checks

- Import API requires authentication.
- Re-importing the same symbol, frequency, and trade time updates the existing bar.
- Quality API returns issue count and issue details.
- Frontend build remains green.
