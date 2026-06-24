"""6:00 PM ET heartbeat — grades the prior trading day's picks and logs P&L."""
from __future__ import annotations

import sys
from datetime import date, timedelta

import db
from fetchers import yfinance_fetcher as yfin
from telegram_bot import send_message


def _grade_outcome(pnl: float) -> str:
    if pnl >= 5:
        return "WIN"
    if pnl <= -5:
        return "LOSS"
    return "FLAT"


def run(dry_run: bool = False, target_date: str | None = None) -> None:
    db.init_db()
    # Default: grade yesterday's picks.
    d = target_date or (date.today() - timedelta(days=1)).isoformat()
    picks = db.picks_for_date(d)
    if not picks:
        msg = f"📋 <b>Grader</b> — no picks found for {d}."
        print(msg) if dry_run else send_message(msg)
        return

    lines = [f"📋 <b>Grade Card — {d}</b>", ""]
    wins = losses = 0
    total_pnl = 0.0
    for p in picks:
        td = yfin.fetch(p["ticker"])
        if not td.ok:
            lines.append(f"${p['ticker']}: data unavailable, skipped")
            continue
        entry = p["entry_price"] or td.price
        pnl = (td.price / entry - 1.0) * 100.0 if entry else 0.0
        outcome = _grade_outcome(pnl)
        wins += outcome == "WIN"
        losses += outcome == "LOSS"
        total_pnl += pnl
        db.insert_grade({
            "pick_id": p["id"],
            "grade_date": date.today().isoformat(),
            "exit_price": td.price,
            "pnl_pct": pnl,
            "outcome": outcome,
            "notes": p["play_type"],
        })
        icon = {"WIN": "🟢", "LOSS": "🔴", "FLAT": "⚪"}[outcome]
        lines.append(f"{icon} ${p['ticker']} ({p['play_type']}): {pnl:+.1f}% [{outcome}]")

    lines += ["", f"<b>Tally:</b> {wins}W / {losses}L · "
              f"avg {total_pnl / max(len(picks),1):+.1f}% per pick"]
    body = "\n".join(lines)
    print(body) if dry_run else send_message(body)


if __name__ == "__main__":
    run(dry_run="--dry-run" in sys.argv)
