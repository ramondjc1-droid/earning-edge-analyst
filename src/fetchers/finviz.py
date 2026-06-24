"""Finviz fundamentals scrape (optional, best-effort, no key required)."""
from __future__ import annotations

from typing import Optional

import requests

_HEADERS = {"User-Agent": "Mozilla/5.0 (earnings-edge-analyst)"}


def snapshot(ticker: str) -> Optional[dict]:
    """Return a small dict of fundamentals, or None on any failure.

    Intentionally lightweight and failure-tolerant; finviz markup changes often
    and this is only ever a nice-to-have enrichment.
    """
    try:
        import pandas as pd

        url = f"https://finviz.com/quote.ashx?t={ticker}"
        r = requests.get(url, headers=_HEADERS, timeout=10)
        r.raise_for_status()
        tables = pd.read_html(r.text)
        for tbl in tables:
            if tbl.shape[1] >= 2 and tbl.shape[0] >= 6:
                flat = {}
                for _, row in tbl.iterrows():
                    cells = row.tolist()
                    for i in range(0, len(cells) - 1, 2):
                        flat[str(cells[i])] = str(cells[i + 1])
                if "P/E" in flat or "EPS (ttm)" in flat:
                    return flat
        return None
    except Exception:
        return None
