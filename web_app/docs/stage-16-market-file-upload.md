# Stage 16 - Market CSV File Upload

## Goal

Upgrade market data import from pasted CSV text to real `.csv` file upload while keeping the same parsing, validation, and import history behavior.

## Delivered Scope

- Added FastAPI multipart upload support via `python-multipart`.
- Added authenticated `/api/v1/market/import/file` endpoint.
- Added `.csv` filename validation and UTF-8 decoding.
- Reused the CSV import parser and market import batch audit record.
- Added frontend file picker and upload form in the market data panel.
- Added backend tests for successful file upload and invalid file extension.

## Backend API

| Endpoint | Method | Auth | Content Type | Purpose |
| --- | --- | --- | --- | --- |
| `/api/v1/market/import/file` | POST | Required | `multipart/form-data` | Upload a `.csv` file and import OHLCV bars. |

Required form fields:

- `symbol`
- `name`
- `exchange`
- `frequency`
- `file`

## Frontend UX

- Users can choose a local `.csv` file.
- Users set symbol, name, and frequency before uploading.
- After upload, market coverage, K-line chart, quality check, and import history refresh automatically.

## Current Constraints

- File content must be UTF-8 encoded.
- The upload imports one instrument per file.
- Uploaded files are parsed immediately and are not stored on disk.

## Acceptance Checks

- Valid `.csv` upload imports bars.
- Non-CSV file extension is rejected with `400`.
- Import batch history records uploaded files as `csv_file`.
- Backend tests, frontend type check, and production build pass.
