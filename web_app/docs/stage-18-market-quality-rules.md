# Stage 18 - Enhanced Market Data Quality Rules

## Goal

Strengthen market data quality checks so imported A-share K-line data can be evaluated before it is used in strategy backtests.

## Delivered Scope

- Added quality score from 0 to 100.
- Added error and warning counts.
- Added issue summary grouped by issue type.
- Added new validation rules:
  - non-positive OHLC prices
  - high lower than low
  - high/low not containing open and close
  - negative volume or amount
  - zero volume warning
  - invalid daily trade date
  - daily data gap warning
- Updated frontend quality panel to show score, error/warning counts, grouped issue summary, and issue severity.
- Added backend test coverage for enhanced quality issues.

## Backend API

`GET /api/v1/market/quality?symbol=600519.SH`

Response now includes:

- `quality_score`
- `error_count`
- `warning_count`
- `issue_summary`
- `issues[].severity`

## Current Constraints

- Daily gap detection uses a simple calendar-day threshold, not a full A-share trading calendar.
- Duplicate K-line detection is not meaningful yet because the database enforces symbol, frequency, and trade time uniqueness.
- Quality scoring is intentionally simple and should be tuned later.

## Acceptance Checks

- Bad OHLC values lower the quality score.
- Error and warning counts are returned.
- Frontend renders quality score and grouped issue tags.
- Existing import, upload, and backtest tests remain green.
