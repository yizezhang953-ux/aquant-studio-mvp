# Stage 15 - Market Import History

## Goal

Make market data import traceable. After manual or CSV imports, users can see recent import batches, inserted/updated counts, skipped rows, and status in the web app.

## Delivered Scope

- Reused the existing `audit_logs` table to record market import batches.
- Added authenticated import history API.
- Recorded successful manual and CSV imports with owner, symbol, frequency, row counts, and issue counts.
- Added frontend import history panel inside the market data workspace.
- Added backend tests for manual and CSV import history.

## Backend API

| Endpoint | Method | Auth | Purpose |
| --- | --- | --- | --- |
| `/api/v1/market/imports` | GET | Required | List the current user's recent market import batches. |

## Audit Payload

Each import batch stores:

- user id
- import type: `manual` or `csv`
- symbol
- frequency
- inserted bar count
- updated bar count
- skipped row count
- issue count
- created timestamp

## Frontend UX

- The market panel now shows the latest import batches for the logged-in user.
- The history refreshes after manual import and CSV import.
- Logout clears the local import history state.

## Current Constraints

- Import history is stored in generic audit logs rather than a dedicated import batch table.
- Failed imports are not persisted yet.
- Batch detail drill-down is not included yet.

## Acceptance Checks

- Manual import creates a visible `manual` batch.
- CSV import creates a visible `csv` batch.
- Import history is scoped to the current authenticated user.
- Tests and frontend build pass.
