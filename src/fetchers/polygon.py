"""Polygon.io fetcher (optional). Falls back to no-op if no API key is set."""
from __future__ import annotations

from typing import Optional

import requests

from config import POLYGON_API_KEY

BASE = "https://api.polygon.io"


def enabled() -> bool:
    return bool(POLYGON_API_KEY)


def prev_close(ticker: str) -> Optional[float]:
    if not enabled():
        return None
    try:
        r = requests.get(
            f"{BASE}/v2/aggs/ticker/{ticker}/prev",
            params={"apiKey": POLYGON_API_KEY},
            timeout=10,
        )
        r.raise_for_status()
        results = r.json().get("results") or []
        return float(results[0]["c"]) if results else None
    except Exception:
        return None
