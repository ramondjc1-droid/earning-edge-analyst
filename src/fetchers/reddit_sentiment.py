"""Reddit sentiment via PRAW (optional). No-op fallback when creds are unset."""
from __future__ import annotations

from typing import Optional

from config import REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET

_BULL = {"moon", "calls", "buy", "long", "rocket", "squeeze", "beat", "rip"}
_BEAR = {"puts", "short", "sell", "dump", "crash", "miss", "drill", "bag"}


def enabled() -> bool:
    return bool(REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET)


def sentiment(ticker: str, limit: int = 50) -> Optional[float]:
    """Return a crude -1..+1 sentiment from recent r/wallstreetbets mentions."""
    if not enabled():
        return None
    try:
        import praw  # imported lazily so the dep stays optional

        reddit = praw.Reddit(
            client_id=REDDIT_CLIENT_ID,
            client_secret=REDDIT_CLIENT_SECRET,
            user_agent="earnings-edge-analyst/1.0",
        )
        bull = bear = 0
        for sub in reddit.subreddit("wallstreetbets").search(
            ticker, sort="new", time_filter="week", limit=limit
        ):
            text = f"{sub.title} {getattr(sub, 'selftext', '')}".lower()
            bull += sum(w in text for w in _BULL)
            bear += sum(w in text for w in _BEAR)
        total = bull + bear
        return (bull - bear) / total if total else 0.0
    except Exception:
        return None
