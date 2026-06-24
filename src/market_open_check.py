"""9:30 AM ET heartbeat — confirms the day's picks and flags opening gaps."""
from __future__ import annotations

import sys
from datetime import date

import db
from fetchers import yfinance_fetcher as yfin
from telegram_bot import send_message


def run(dry_run: bool = False) -> None:
    db.init_db()
    picks = db.picks_for_date(date.today().isoformat())
    if not picks:
        msg = "🔔 <b>Market Open</b> — no picks on the board today."
        print(msg) if dry_run else send_message(msg)
        return

    lines = ["🔔 <b>Market Open Check</b>", ""]
    for p in picks:
        td = yfin.fetch(p["ticker"])
        gap = f"{td.gap_pct:+.1f}%" if td.ok else "n/a"
        last = f"${td.price:,.2f}" if td.ok else "n/a"
        lines.append(f"${p['ticker']} ({p['play_type']}): open gap {gap}, last {last}")
    body = "\n".join(lines)
    print(body) if dry_run else send_message(body)


if __name__ == "__main__":
    run(dry_run="--dry-run" in sys.argv)
