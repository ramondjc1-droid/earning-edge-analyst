"""All SQLite operations for picks and grades."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterator, Optional

from config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS picks (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    pick_date       TEXT NOT NULL,
    ticker          TEXT NOT NULL,
    play_type       TEXT NOT NULL,
    confidence      INTEGER NOT NULL,
    score           REAL NOT NULL,
    entry_price     REAL,
    iv_rank         REAL,
    earnings_date   TEXT,
    narrative       TEXT,
    metrics_json    TEXT,
    sent            INTEGER DEFAULT 0,
    created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS grades (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    pick_id         INTEGER NOT NULL,
    grade_date      TEXT NOT NULL,
    exit_price      REAL,
    pnl_pct         REAL,
    outcome         TEXT,
    notes           TEXT,
    created_at      TEXT NOT NULL,
    FOREIGN KEY (pick_id) REFERENCES picks(id)
);

CREATE TABLE IF NOT EXISTS skips (
    ticker          TEXT NOT NULL,
    skip_date       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS run_log (
    stage           TEXT NOT NULL,
    run_date        TEXT NOT NULL,
    created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS iv_history (
    ticker          TEXT NOT NULL,
    obs_date        TEXT NOT NULL,
    iv_atm          REAL NOT NULL,
    UNIQUE(ticker, obs_date)
);
CREATE INDEX IF NOT EXISTS idx_iv_ticker ON iv_history(ticker);

CREATE INDEX IF NOT EXISTS idx_picks_date ON picks(pick_date);
CREATE INDEX IF NOT EXISTS idx_picks_ticker ON picks(ticker);
"""


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    Path(DB_PATH).parent.mkdir(exist_ok=True)
    with connect() as conn:
        conn.executescript(SCHEMA)


def insert_pick(pick: dict) -> int:
    with connect() as conn:
        cur = conn.execute(
            """INSERT INTO picks
               (pick_date, ticker, play_type, confidence, score, entry_price,
                iv_rank, earnings_date, narrative, metrics_json, sent, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                pick["pick_date"],
                pick["ticker"],
                pick["play_type"],
                pick["confidence"],
                pick["score"],
                pick.get("entry_price"),
                pick.get("iv_rank"),
                pick.get("earnings_date"),
                pick.get("narrative"),
                pick.get("metrics_json"),
                pick.get("sent", 0),
                datetime.utcnow().isoformat(),
            ),
        )
        return cur.lastrowid


def mark_sent(pick_id: int) -> None:
    with connect() as conn:
        conn.execute("UPDATE picks SET sent = 1 WHERE id = ?", (pick_id,))


def picks_for_date(d: Optional[str] = None) -> list[sqlite3.Row]:
    d = d or date.today().isoformat()
    with connect() as conn:
        return conn.execute(
            "SELECT * FROM picks WHERE pick_date = ? ORDER BY confidence DESC", (d,)
        ).fetchall()


def picks_for_ticker(ticker: str) -> list[sqlite3.Row]:
    with connect() as conn:
        return conn.execute(
            "SELECT * FROM picks WHERE ticker = ? ORDER BY pick_date DESC",
            (ticker.upper(),),
        ).fetchall()


def add_skip(ticker: str) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO skips (ticker, skip_date) VALUES (?, ?)",
            (ticker.upper(), date.today().isoformat()),
        )


def skips_for_today() -> set[str]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT ticker FROM skips WHERE skip_date = ?",
            (date.today().isoformat(),),
        ).fetchall()
    return {r["ticker"] for r in rows}


def already_ran_today(stage: str) -> bool:
    """True if ``stage`` has already been logged as run today (idempotency)."""
    with connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM run_log WHERE stage = ? AND run_date = ? LIMIT 1",
            (stage, date.today().isoformat()),
        ).fetchone()
    return row is not None


def log_run(stage: str) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO run_log (stage, run_date, created_at) VALUES (?,?,?)",
            (stage, date.today().isoformat(), datetime.utcnow().isoformat()),
        )


def insert_grade(grade: dict) -> int:
    with connect() as conn:
        cur = conn.execute(
            """INSERT INTO grades
               (pick_id, grade_date, exit_price, pnl_pct, outcome, notes, created_at)
               VALUES (?,?,?,?,?,?,?)""",
            (
                grade["pick_id"],
                grade["grade_date"],
                grade.get("exit_price"),
                grade.get("pnl_pct"),
                grade.get("outcome"),
                grade.get("notes"),
                datetime.utcnow().isoformat(),
            ),
        )
        return cur.lastrowid


def record_iv(ticker: str, iv_atm: float, obs_date: Optional[str] = None) -> None:
    """Log today's observed ATM IV for a ticker (one observation per day)."""
    if iv_atm <= 0:
        return
    obs_date = obs_date or date.today().isoformat()
    with connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO iv_history (ticker, obs_date, iv_atm) "
            "VALUES (?,?,?)",
            (ticker.upper(), obs_date, iv_atm),
        )


def iv_percentile(ticker: str, iv_atm: float, min_obs: int = 10,
                  window_days: int = 365) -> Optional[float]:
    """Percentile (0-100) of ``iv_atm`` within the name's own IV history.

    Returns None until at least ``min_obs`` observations exist — callers fall
    back to the IV/RV proxy during the cold-start period.
    """
    cutoff = (date.today() - timedelta(days=window_days)).isoformat()
    with connect() as conn:
        rows = conn.execute(
            "SELECT iv_atm FROM iv_history WHERE ticker = ? AND obs_date >= ?",
            (ticker.upper(), cutoff),
        ).fetchall()
    if len(rows) < min_obs:
        return None
    values = [r["iv_atm"] for r in rows]
    below = sum(1 for v in values if v < iv_atm)
    return below / len(values) * 100.0


def ungraded_picks(max_age_days: int = 30) -> list[sqlite3.Row]:
    """Picks with no grade yet, newest-first, bounded to a sane window."""
    cutoff = (date.today() - timedelta(days=max_age_days)).isoformat()
    with connect() as conn:
        return conn.execute(
            """SELECT p.* FROM picks p
               LEFT JOIN grades g ON g.pick_id = p.id
               WHERE g.id IS NULL AND p.pick_date >= ?
               ORDER BY p.pick_date DESC""",
            (cutoff,),
        ).fetchall()


def pnl_since(since_iso: str) -> list[sqlite3.Row]:
    with connect() as conn:
        return conn.execute(
            """SELECT p.ticker, p.play_type, p.pick_date, g.pnl_pct, g.outcome
               FROM grades g JOIN picks p ON p.id = g.pick_id
               WHERE p.pick_date >= ? ORDER BY p.pick_date DESC""",
            (since_iso,),
        ).fetchall()


if __name__ == "__main__":
    init_db()
    print(f"Initialized database at {DB_PATH}")
