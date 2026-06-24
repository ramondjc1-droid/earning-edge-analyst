"""MAIN daily script.

Scans the earnings calendar, scores every name across the three play types,
picks the top N, generates narratives, persists them, and delivers pick cards
to Telegram. Run with --dry-run to preview without sending.

    python src/morning_scan.py --dry-run
    python src/morning_scan.py
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date

import cards
import db
import narratives
from config import formula
from fetchers import earnings_whispers as cal
from model import scoring
from telegram_bot import send_message


def run(dry_run: bool = False, lookahead: int = 10, verbose: bool = True) -> list:
    db.init_db()
    f = formula()
    max_picks = f.get("max_picks_per_day", 5)
    skip = db.skips_for_today()

    if verbose:
        print(f"[scan] {date.today().isoformat()} — fetching earnings calendar "
              f"(lookahead {lookahead}d, {len(cal.WATCHLIST)} tickers)…")

    candidates = cal.upcoming_earnings(lookahead_days=lookahead, skip=skip)
    if verbose:
        print(f"[scan] {len(candidates)} names report within {lookahead} days.")

    # Best play per ticker, then rank by score.
    plays = []
    for td in candidates:
        ps = scoring.best_play(td)
        if ps and ps.passes_gate:
            plays.append(ps)
    plays.sort(key=lambda p: p.score, reverse=True)
    top = plays[:max_picks]

    if verbose:
        print(f"[scan] {len(plays)} plays cleared the gate; taking top {len(top)}.")

    # Build, persist, and collect cards.
    sent_cards = []
    for ps in top:
        narrative = narratives.generate(ps)
        pick_id = db.insert_pick({
            "pick_date": date.today().isoformat(),
            "ticker": ps.data.ticker,
            "play_type": ps.play_type,
            "confidence": ps.confidence,
            "score": ps.score,
            "entry_price": ps.data.price,
            "iv_rank": ps.data.iv_rank,
            "earnings_date": ps.data.earnings_date,
            "narrative": narrative,
            "metrics_json": json.dumps(ps.data.as_dict(), default=str),
        })
        card = cards.pick_card(ps, narrative)
        sent_cards.append((pick_id, card))
        if verbose:
            print(f"\n{'='*50}\n{card}\n")

    # Deliver.
    if not top:
        body = cards.no_picks()
        if dry_run:
            print("\n[dry-run] would send:\n" + body)
        else:
            send_message(body)
        return top

    full = cards.header(len(top)) + "\n\n" + \
        "\n\n".join(c for _, c in sent_cards) + "\n" + cards.footer()

    if dry_run:
        print("\n[dry-run] would send the above cards to Telegram. "
              "Re-run without --dry-run to deliver.")
    else:
        if send_message(full):
            for pick_id, _ in sent_cards:
                db.mark_sent(pick_id)
            if verbose:
                print(f"[scan] delivered {len(top)} picks to Telegram.")
        else:
            print("[scan] Telegram not configured or send failed; picks saved to DB.")
    return top


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Earnings Edge — morning scan")
    p.add_argument("--dry-run", action="store_true",
                   help="preview picks without sending to Telegram")
    p.add_argument("--lookahead", type=int, default=10,
                   help="earnings lookahead window in days (default 10)")
    p.add_argument("--quiet", action="store_true", help="suppress progress output")
    args = p.parse_args(argv)
    run(dry_run=args.dry_run, lookahead=args.lookahead, verbose=not args.quiet)
    return 0


if __name__ == "__main__":
    sys.exit(main())
