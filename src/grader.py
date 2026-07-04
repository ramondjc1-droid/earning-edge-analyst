"""6:00 PM ET heartbeat — grades picks against their own thesis.

Each play type has a defined exit and a defined success metric, so a pick is
graded when its exit date has passed, using the measure its thesis implies:

  PRE_RUNUP      exit 1 day before the report; graded on price drift since entry
  IV_CRUSH       exit 1 day after the report; graded on IV collapse vs price
                 blow-through (a premium seller wins when IV drops and the
                 stock does NOT move big — the stock's direction is irrelevant)
  POST_MOMENTUM  exit ~4 days after entry; graded on follow-through
  MOMENTUM       exit ~5 days after entry; graded on follow-through

Grading price moves alone would mislabel IV_CRUSH results and grade earnings
plays before their exit, which poisons any later weight tuning.
"""
from __future__ import annotations

import json
import sys
from datetime import date, datetime, timedelta
from typing import Optional

import db
from fetchers import yfinance_fetcher as yfin
from telegram_bot import send_message

# Thesis thresholds (percent moves; IV drop is a ratio).
PRE_RUNUP_WIN, PRE_RUNUP_LOSS = 2.0, -2.0
MOMO_WIN, MOMO_LOSS = 3.0, -3.0
IV_DROP_WIN = 0.80        # IV_now <= 80% of entry IV counts as a crush
IV_BLOWTHROUGH_PCT = 8.0  # |price move| beyond this overwhelms sold premium


def exit_date(play_type: str, pick_date: date,
              earnings_date: Optional[date]) -> Optional[date]:
    """The date on/after which a pick is gradeable. None = can't determine."""
    if play_type == "PRE_RUNUP":
        return earnings_date - timedelta(days=1) if earnings_date else None
    if play_type == "IV_CRUSH":
        return earnings_date + timedelta(days=1) if earnings_date else None
    if play_type == "POST_MOMENTUM":
        return pick_date + timedelta(days=4)
    if play_type == "MOMENTUM":
        return pick_date + timedelta(days=5)
    return pick_date + timedelta(days=1)


def grade_play(play_type: str, entry_price: float, price_now: float,
               iv_entry: float, iv_now: float) -> tuple[float, str, str]:
    """Return (pnl_pct, outcome, notes) per the play's own thesis."""
    pnl = (price_now / entry_price - 1.0) * 100.0 if entry_price else 0.0

    if play_type == "IV_CRUSH":
        moved_big = abs(pnl) >= IV_BLOWTHROUGH_PCT
        iv_dropped = iv_entry > 0 and iv_now > 0 and iv_now <= iv_entry * IV_DROP_WIN
        if moved_big:
            return pnl, "LOSS", (f"blow-through: stock moved {pnl:+.1f}%, "
                                 f"overwhelming sold premium")
        if iv_dropped:
            return pnl, "WIN", (f"IV crushed {iv_entry:.2f}→{iv_now:.2f} with "
                                f"contained move ({pnl:+.1f}%)")
        if iv_entry > 0 and iv_now > iv_entry:
            return pnl, "LOSS", f"IV rose {iv_entry:.2f}→{iv_now:.2f}"
        return pnl, "FLAT", (f"IV {iv_entry:.2f}→{iv_now:.2f}, move {pnl:+.1f}% "
                             "— thesis partially played out")

    if play_type == "PRE_RUNUP":
        if pnl >= PRE_RUNUP_WIN:
            return pnl, "WIN", f"pre-earnings drift {pnl:+.1f}%"
        if pnl <= PRE_RUNUP_LOSS:
            return pnl, "LOSS", f"drifted against entry {pnl:+.1f}%"
        return pnl, "FLAT", f"no meaningful drift ({pnl:+.1f}%)"

    # POST_MOMENTUM / MOMENTUM: follow-through
    if pnl >= MOMO_WIN:
        return pnl, "WIN", f"follow-through {pnl:+.1f}%"
    if pnl <= MOMO_LOSS:
        return pnl, "LOSS", f"momentum reversed {pnl:+.1f}%"
    return pnl, "FLAT", f"stalled ({pnl:+.1f}%)"


def _iso(s: Optional[str]) -> Optional[date]:
    try:
        return datetime.strptime(s, "%Y-%m-%d").date() if s else None
    except ValueError:
        return None


def run(dry_run: bool = False) -> None:
    db.init_db()
    today = date.today()
    due = []
    for p in db.ungraded_picks():
        ed = exit_date(p["play_type"], _iso(p["pick_date"]), _iso(p["earnings_date"]))
        if ed and ed <= today:
            due.append(p)

    if not due:
        msg = "📋 <b>Grader</b> — no picks have reached their exit date yet."
        print(msg) if dry_run else send_message(msg)
        return

    lines = ["📋 <b>Grade Card</b> (thesis-based)", ""]
    wins = losses = 0
    for p in due:
        td = yfin.fetch(p["ticker"])
        if not td.ok:
            lines.append(f"${p['ticker']}: data unavailable, will retry")
            continue
        try:
            iv_entry = float(json.loads(p["metrics_json"]).get("iv_atm") or 0.0)
        except Exception:
            iv_entry = 0.0
        entry = p["entry_price"] or td.price
        pnl, outcome, notes = grade_play(
            p["play_type"], entry, td.price, iv_entry, td.iv_atm
        )
        wins += outcome == "WIN"
        losses += outcome == "LOSS"
        db.insert_grade({
            "pick_id": p["id"],
            "grade_date": today.isoformat(),
            "exit_price": td.price,
            "pnl_pct": pnl,
            "outcome": outcome,
            "notes": f"{p['play_type']}: {notes}",
        })
        icon = {"WIN": "🟢", "LOSS": "🔴", "FLAT": "⚪"}[outcome]
        lines.append(
            f"{icon} ${p['ticker']} ({p['play_type']}, {p['pick_date']}): "
            f"{outcome} — {notes}"
        )

    lines += ["", f"<b>Tally:</b> {wins}W / {losses}L across {len(due)} graded"]
    body = "\n".join(lines)
    print(body) if dry_run else send_message(body)


if __name__ == "__main__":
    run(dry_run="--dry-run" in sys.argv)
