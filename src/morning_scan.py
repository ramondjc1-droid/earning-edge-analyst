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


def run(dry_run: bool = False, lookahead: int = 21, verbose: bool = True) -> list:
    db.init_db()
    f = formula()
    max_picks = f.get("max_picks_per_day", 5)
    skip = db.skips_for_today()

    if verbose:
        print(f"[scan] {date.today().isoformat()} — fetching "
              f"{len(cal.WATCHLIST)} tickers (lookahead {lookahead}d)…")

    # One fetch pass; reused for both earnings and trending selection.
    pool = cal.fetch_all(skip=skip)
    candidates = cal.upcoming_earnings(lookahead_days=lookahead, prefetched=pool)
    if verbose:
        print(f"[scan] {len(pool)} tickers resolved; "
              f"{len(candidates)} report within {lookahead} days.")

    max_main = f.get("max_main_picks", 3)
    max_penny = f.get("max_penny_picks", 3)

    # Best play per ticker, then split into main ($5-$50) vs penny (<$5).
    all_plays = []
    for td in candidates:
        ps = scoring.best_play(td)
        if ps and ps.passes_gate:
            all_plays.append(ps)
    all_plays.sort(key=lambda p: p.score, reverse=True)

    main_picks = [p for p in all_plays if not cards.is_penny(p)][:max_main]
    penny_picks = [p for p in all_plays if cards.is_penny(p)][:max_penny]

    # Off-season TRENDING fill: high-momentum names with no imminent earnings.
    mcfg = f.get("momentum", {})
    momentum_picks = []
    if mcfg.get("enabled", True):
        already = {p.data.ticker for p in main_picks + penny_picks}
        earnings_window = {td.ticker for td in candidates}
        min_conf = mcfg.get("min_confidence", 5)
        cand = []
        for td in pool:
            if td.ticker in already or td.ticker in earnings_window:
                continue
            ms = scoring.score_momentum(td)
            if ms.passes_gate and ms.confidence >= min_conf:
                cand.append(ms)
        cand.sort(key=lambda p: p.score, reverse=True)
        momentum_picks = cand[:mcfg.get("max_momentum_picks", 3)]

    top = main_picks + penny_picks + momentum_picks

    if verbose:
        print(f"[scan] taking {len(main_picks)} main + {len(penny_picks)} penny "
              f"+ {len(momentum_picks)} trending.")

    # Build, persist, and collect cards per section.
    def _persist_and_card(ps):
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
        if verbose:
            print(f"\n{'='*50}\n{card}\n")
        return pick_id, card

    main_cards = [_persist_and_card(ps) for ps in main_picks]
    penny_cards = [_persist_and_card(ps) for ps in penny_picks]
    momentum_cards = [_persist_and_card(ps) for ps in momentum_picks]

    # Deliver.
    if not top:
        body = cards.no_picks()
        if dry_run:
            print("\n[dry-run] would send:\n" + body)
        else:
            send_message(body)
        return top

    # Build the full message with separate sections.
    sections = [cards.header(len(main_picks), len(penny_picks), len(momentum_picks))]
    if main_cards:
        sections.append(cards.section_header("💵 MAIN PICKS (under $50)"))
        sections.extend(c for _, c in main_cards)
    if penny_cards:
        sections.append(cards.section_header("🪙 PENNY PICKS (under $5)"))
        sections.extend(c for _, c in penny_cards)
    if momentum_cards:
        sections.append(cards.section_header("🔥 TRENDING (no earnings yet)"))
        sections.extend(c for _, c in momentum_cards)
    sections.append(cards.footer())
    full = "\n\n".join(sections)

    if dry_run:
        print("\n[dry-run] would send the above cards to Telegram. "
              "Re-run without --dry-run to deliver.")
    else:
        if send_message(full):
            for pick_id, _ in main_cards + penny_cards + momentum_cards:
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
    p.add_argument("--lookahead", type=int, default=21,
                   help="earnings lookahead window in days (default 21)")
    p.add_argument("--quiet", action="store_true", help="suppress progress output")
    args = p.parse_args(argv)
    run(dry_run=args.dry_run, lookahead=args.lookahead, verbose=not args.quiet)
    return 0


if __name__ == "__main__":
    sys.exit(main())
