# Stage 19 - A-share Trading Calendar and Missing Day Detection

## Goal

Upgrade data quality checks from simple calendar-day gaps to A-share trading-calendar-aware missing trading day detection.

## Delivered Scope

- Added `trading_calendar_service.py`.
- Added built-in A-share 2024 holiday calendar.
- Added trading-day helpers:
  - `is_a_share_trading_day`
  - `expected_a_share_trading_days`
  - `missing_a_share_trading_days`
- Updated market quality checks to emit `missing_trading_day` warnings.
- Added `calendar_name` and `missing_trading_days` to quality responses.
- Updated frontend quality panel to show calendar source and missing trading day preview.
- Added backend test coverage for missing A-share trading day detection.

## Quality API Additions

`GET /api/v1/market/quality?symbol=600519.SH`

New fields:

- `calendar_name`
- `missing_trading_days`

## Current Constraints

- The built-in holiday calendar currently covers 2024.
- Weekend make-up workdays are intentionally not treated as stock trading days.
- Future production use should replace or extend this with an exchange/vender-maintained calendar.

## Acceptance Checks

- Missing 2024-03-04 between 2024-03-01 and 2024-03-05 is detected.
- Quality response identifies the calendar source.
- Frontend shows missing trading day count and preview.
- Existing import, upload, and backtest tests remain green.
