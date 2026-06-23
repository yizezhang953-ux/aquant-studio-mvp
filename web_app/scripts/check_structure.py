from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

REQUIRED_PATHS = [
    "backend/app/main.py",
    "backend/app/api/v1/router.py",
    "backend/app/api/v1/routes/auth.py",
    "backend/app/api/v1/routes/system.py",
    "backend/app/api/v1/routes/security.py",
    "backend/app/api/v1/routes/templates.py",
    "backend/app/api/v1/routes/strategies.py",
    "backend/app/api/v1/routes/backtests.py",
    "backend/app/api/v1/routes/market.py",
    "backend/app/api/v1/routes/database.py",
    "backend/app/core/config.py",
    "backend/app/db/init_db.py",
    "backend/app/db/session.py",
    "backend/app/models/audit.py",
    "backend/app/models/backtest.py",
    "backend/app/models/market.py",
    "backend/app/models/strategy.py",
    "backend/app/models/template.py",
    "backend/app/models/user.py",
    "backend/app/schemas/auth.py",
    "backend/app/schemas/backtest.py",
    "backend/app/schemas/market.py",
    "backend/app/schemas/security.py",
    "backend/app/schemas/strategy.py",
    "backend/app/schemas/system.py",
    "backend/app/services/backtest_service.py",
    "backend/app/services/auth_service.py",
    "backend/app/services/database_service.py",
    "backend/app/services/market_service.py",
    "backend/app/services/market_data_source_service.py",
    "backend/app/services/trading_calendar_service.py",
    "backend/app/services/json_utils.py",
    "backend/app/services/legacy_paths.py",
    "backend/app/services/strategy_service.py",
    "backend/app/services/strategy_repository.py",
    "backend/app/services/template_service.py",
    "backend/pyproject.toml",
    "backend/.env.example",
    "frontend/package.json",
    "frontend/index.html",
    "frontend/src/App.tsx",
    "frontend/src/main.tsx",
    "frontend/src/styles.css",
    "docs/stage-1-web-app-structure.md",
    "docs/stage-2-backend-api-mvp.md",
    "docs/stage-3-database-design-migration.md",
    "docs/stage-4-user-account-strategy-persistence.md",
    "docs/stage-5-frontend-connected-workbench.md",
    "docs/stage-6-structured-strategy-editor.md",
    "docs/stage-7-backtest-frontend-loop.md",
    "docs/stage-8-backtest-persistence-history.md",
    "docs/stage-9-backtest-comparison.md",
    "docs/stage-10-strategy-version-backtest-binding.md",
    "docs/stage-11-backtest-parameter-diff.md",
    "docs/stage-12-market-data-browser.md",
    "docs/stage-13-market-data-import-quality.md",
    "docs/stage-14-market-csv-import.md",
    "docs/stage-15-market-import-history.md",
    "docs/stage-16-market-file-upload.md",
    "docs/stage-17-market-import-detail-failures.md",
    "docs/stage-18-market-quality-rules.md",
    "docs/stage-19-a-share-trading-calendar.md",
    "docs/stage-20-real-market-data-sources.md",
]


def main() -> None:
    checks = []
    for relative_path in REQUIRED_PATHS:
        path = ROOT / relative_path
        checks.append(
            {
                "path": relative_path,
                "exists": path.exists(),
                "size": path.stat().st_size if path.exists() else None,
            }
        )
    ok = all(item["exists"] for item in checks)
    output = {"ok": ok, "checks": checks}
    print(json.dumps(output, ensure_ascii=False, indent=2))
    if not ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
