"""Central configuration: loads .env and config/formula.yaml."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DATA_DIR = ROOT / "data"
LOGS_DIR = ROOT / "logs"
DB_PATH = DATA_DIR / "picks.db"
FORMULA_PATH = ROOT / "config" / "formula.yaml"

DATA_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)


def env(key: str, default: str = "") -> str:
    val = os.getenv(key, default)
    # Treat the handoff placeholders as unset
    if val in ("not_set", "set", "", "changeme"):
        return default
    return val


# --- API keys / secrets (all optional; system degrades gracefully) ----------
ANTHROPIC_API_KEY = env("ANTHROPIC_API_KEY")
POLYGON_API_KEY = env("POLYGON_API_KEY")
UNUSUAL_WHALES_API_KEY = env("UNUSUAL_WHALES_API_KEY")
TELEGRAM_BOT_TOKEN = env("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = env("TELEGRAM_CHAT_ID")
REDDIT_CLIENT_ID = env("REDDIT_CLIENT_ID")
REDDIT_CLIENT_SECRET = env("REDDIT_CLIENT_SECRET")

# Model used for narrative generation. Override with NARRATIVE_MODEL in .env.
NARRATIVE_MODEL = env("NARRATIVE_MODEL", "claude-opus-4-8")


@lru_cache(maxsize=1)
def formula() -> dict:
    """Load and cache the tunable scoring formula."""
    with open(FORMULA_PATH, "r") as fh:
        return yaml.safe_load(fh)


def reload_formula() -> dict:
    formula.cache_clear()
    return formula()
