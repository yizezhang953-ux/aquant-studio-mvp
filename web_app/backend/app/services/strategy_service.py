from __future__ import annotations

import sys
from typing import Any

from sqlalchemy.orm import Session

from app.services.legacy_paths import STRATEGY_MODULE
from app.services.market_data_access import coverage_for

if str(STRATEGY_MODULE) not in sys.path:
    sys.path.insert(0, str(STRATEGY_MODULE))

from strategy_validator import validate_strategy  # noqa: E402


def validate_strategy_payload(strategy: dict[str, Any], db: Session | None = None) -> dict[str, Any]:
    """Validate the DSL; when ``db`` is given, data coverage is checked against the web database."""
    result = validate_strategy(strategy, coverage=coverage_for(db) if db is not None else None)
    return result.to_dict()
