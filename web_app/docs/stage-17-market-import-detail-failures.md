# Stage 17 - Market Import Details and Failure Records

## Goal

Make market import batches inspectable and preserve failed imports. Users can now open an import batch to see status, source, message, and row-level errors.

## Delivered Scope

- Added import batch detail schema and endpoint.
- Added failed import audit records for invalid CSV text and invalid uploaded files.
- Stored parser errors, source, parsed row count, and total bar count in the audit payload.
- Added frontend clickable import history rows.
- Added frontend detail panel with status, source, message, and error list.
- Added backend tests for successful detail lookup and failed import records.

## Backend API

| Endpoint | Method | Auth | Purpose |
| --- | --- | --- | --- |
| `/api/v1/market/imports/{batch_id}` | GET | Required | Read one import batch detail scoped to the current user. |

## Failure Recording

Failed imports are recorded when:

- CSV text is missing required columns.
- CSV file upload has an unsupported extension.
- CSV file upload parses zero valid rows.

## Frontend UX

- Import history rows are clickable.
- Selected import batch is highlighted.
- Detail panel shows status, source, summary message, and up to four error messages.

## Current Constraints

- Failed UTF-8 decoding errors are still returned immediately and not recorded because the file content cannot be safely parsed.
- The detail panel shows a compact error preview rather than a full paginated error table.

## Acceptance Checks

- Completed CSV imports have readable details.
- Failed CSV imports are visible in history with `failed` status.
- Uploaded file failures are recorded as `csv_file` failures.
- Backend tests and frontend build pass.
