"""4:30 PM ET heartbeat — end-of-day move on each of today's picks."""
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
        msg = "🌆 <b>Post-Market</b> — no picks to update today."
        print(msg) if dry_run else send_message(msg)
        return

    lines = ["🌆 <b>Post-Market Update</b>", ""]
    for p in picks:
        td = yfin.fetch(p["ticker"])
        if not td.ok:
            lines.append(f"${p['ticker']}: data unavailable")
            continue
        entry = p["entry_price"] or td.price
        chg = (td.price / entry - 1.0) * 100.0 if entry else 0.0
        arrow = "🟢" if chg >= 0 else "🔴"
        lines.append(
            f"{arrow} ${p['ticker']} ({p['play_type']}): "
            f"${td.price:,.2f} ({chg:+.1f}% vs entry)"
        )
    body = "\n".join(lines)
    print(body) if dry_run else send_message(body)


if __name__ == "__main__":
    run(dry_run="--dry-run" in sys.argv)
