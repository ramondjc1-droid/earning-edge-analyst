"""Unusual Whales fetcher (optional). No-op fallback when the key is unset."""
from __future__ import annotations

from typing import Optional

import requests

from config import UNUSUAL_WHALES_API_KEY

BASE = "https://api.unusualwhales.com/api"


def enabled() -> bool:
    return bool(UNUSUAL_WHALES_API_KEY)


def flow_sentiment(ticker: str) -> Optional[float]:
    """Return a -1..+1 options-flow sentiment, or None if unavailable."""
    if not enabled():
        return None
    try:
        r = requests.get(
            f"{BASE}/stock/{ticker}/flow-alerts",
            headers={"Authorization": f"Bearer {UNUSUAL_WHALES_API_KEY}"},
            timeout=10,
        )
        r.raise_for_status()
        data = r.json().get("data") or []
        if not data:
            return 0.0
        calls = sum(1 for a in data if str(a.get("type", "")).lower() == "call")
        puts = sum(1 for a in data if str(a.get("type", "")).lower() == "put")
        total = calls + puts
        return (calls - puts) / total if total else 0.0
    except Exception:
        return None
