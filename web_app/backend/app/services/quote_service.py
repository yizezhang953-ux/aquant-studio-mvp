"""Live quotes from Tencent (about 3 s delayed), cached for a few seconds so several open pages
refreshing at once still send one request per batch."""
from __future__ import annotations

import re
import sys
import threading
import time
from typing import Any

from app.core.config import settings
from app.services.legacy_paths import REPO_ROOT
from app.services.market_data_source_service import tencent

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from market_rules_module.market_rules import normalize_symbol as loose_symbol  # noqa: E402

CACHE_SECONDS = 3.0
MAX_QUOTES = 500

_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_lock = threading.Lock()


def parse_symbols(raw: list[str] | str) -> list[str]:
    """Codes as people type them: '600519', 'sh600519', '700.hk', separated by spaces, commas or new lines."""
    items = re.split(r"[\s,，、;；]+", raw) if isinstance(raw, str) else raw
    return list(dict.fromkeys(loose_symbol(s) for s in items if s and s.strip()))


def get_quotes(symbols: list[str], fetch_bytes=None) -> dict[str, dict[str, Any]]:
    if not settings.market_data_network_enabled:
        raise ValueError("network data sources are disabled (MARKET_DATA_NETWORK_ENABLED=false)")
    if len(symbols) > MAX_QUOTES:
        raise ValueError(f"一次最多 {MAX_QUOTES} 只")
    now = time.time()
    with _lock:
        fresh = {s: q for s, (t, q) in ((s, _cache[s]) for s in symbols if s in _cache) if now - t < CACHE_SECONDS}
    missing = [s for s in symbols if s not in fresh]
    if missing:
        try:
            fetched = tencent.fetch_quotes(missing, fetch_bytes)
        except RuntimeError as exc:
            raise ValueError(f"连不上腾讯实时行情（{str(exc).split(': ')[-1][:80]}）") from exc
        with _lock:
            for symbol, quote in fetched.items():
                _cache[symbol] = (now, quote)
        fresh.update(fetched)
    return {s: fresh[s] for s in symbols if s in fresh}
