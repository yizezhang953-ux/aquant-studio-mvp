from __future__ import annotations

import sys
from typing import Any

from app.services.legacy_paths import DATA_MODULE, STRATEGY_MODULE


sys.path.insert(0, str(STRATEGY_MODULE))

from strategy_validator import validate_strategy  # noqa: E402


DEFAULT_DB_PATH = DATA_MODULE / "market_data.sqlite"


def validate_strategy_payload(strategy: dict[str, Any]) -> dict[str, Any]:
    result = validate_strategy(strategy, DEFAULT_DB_PATH)
    return result.to_dict()
