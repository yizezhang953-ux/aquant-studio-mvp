from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from typing import Any

USER_AGENT = "Mozilla/5.0 (AQuant Studio research data loader)"


def get_bytes(url: str, params: dict[str, Any] | None = None, timeout: float = 20, retries: int = 2) -> bytes:
    if params:
        url = f"{url}?{urllib.parse.urlencode(params, safe=',')}"
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - fixed https hosts
                return response.read()
        except Exception as exc:  # network errors are retried, then surfaced
            last_error = exc
            time.sleep(0.8 * (attempt + 1))
    raise RuntimeError(f"request failed: {url}: {last_error}")


def get_json(url: str, params: dict[str, Any] | None = None, timeout: float = 20) -> Any:
    return json.loads(get_bytes(url, params, timeout).decode("utf-8"))
