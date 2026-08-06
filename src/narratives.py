"""AI narrative generation for picks.

Uses the Anthropic API to turn a scored play into a short, human narrative. If
no API key is configured (or the call fails), it falls back to a deterministic
template so the pipeline never breaks.
"""
from __future__ import annotations

from config import ANTHROPIC_API_KEY, NARRATIVE_MODEL
from model.scoring import PlayScore

_PLAY_BLURB = {
    "PRE_RUNUP": "buy before earnings and ride the pre-report drift, exiting ~1 day before the report",
    "IV_CRUSH": "sell elevated options premium before earnings, exiting ~1 day after the report",
    "POST_MOMENTUM": "enter after a confirmed beat and ride 3-5 days of follow-through",
    "MOMENTUM": "a trending/high-IV momentum name (no imminent earnings) — a swing/watchlist idea, not an earnings event play",
}

SYSTEM = (
    "You are a concise sell-side-style trade-idea writer for an earnings play "
    "scanner. Write a tight 3-4 sentence narrative for ONE stock. Be specific "
    "about the setup and the numbers given. Never give financial advice, never "
    "promise outcomes, and always note this is informational only. No preamble."
)


def iv_label(d) -> str:
    """Name the IV-rank basis honestly: a real percentile once enough IV
    history has accumulated for that ticker, the IV/RV proxy before then."""
    if d.extras.get("iv_rank_source") == "history":
        return "IV-rank"
    return "IV-rank proxy"


def _fallback(ps: PlayScore) -> str:
    d = ps.data
    blurb = _PLAY_BLURB.get(ps.play_type, ps.play_type)
    # Only mention an earnings date when there actually is one (trending names
    # have none).
    if d.earnings_date:
        when = f" Reports {d.earnings_date}"
        if d.days_to_earnings is not None:
            when += f", in {d.days_to_earnings} days"
        when += "."
    else:
        when = ""
    return (
        f"${d.ticker} screens as a {ps.play_type} setup (confidence {ps.confidence}/10). "
        f"The play: {blurb}.{when}"
        f" Context: 20-day momentum {d.momentum_20d:+.1f}%, relative volume "
        f"{d.rel_volume:.1f}x, {iv_label(d)} {d.iv_rank:.0f}. "
        "Informational only — not financial advice."
    )


def generate(ps: PlayScore) -> str:
    if not ANTHROPIC_API_KEY:
        return _fallback(ps)
    try:
        import anthropic

        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        d = ps.data
        facts = (
            f"Ticker: {d.ticker}\n"
            f"Play type: {ps.play_type} ({_PLAY_BLURB.get(ps.play_type)})\n"
            f"Confidence: {ps.confidence}/10 (raw score {ps.score:.2f})\n"
            f"Price: {d.price:.2f}\n"
            f"Earnings date: {d.earnings_date} (in {d.days_to_earnings} days)\n"
            f"20d momentum: {d.momentum_20d:+.1f}%  5d momentum: {d.momentum_5d:+.1f}%\n"
            f"Relative volume: {d.rel_volume:.1f}x  Avg volume: {d.avg_volume:,.0f}\n"
            f"{iv_label(d)}: {d.iv_rank:.0f}  IV/RV: {d.iv_vs_historical:.2f}  Beta: {d.beta:.2f}\n"
            f"Last earnings surprise: {d.earnings_surprise_pct}\n"
            f"Score breakdown: {ps.rationale}\n"
        )
        msg = client.messages.create(
            model=NARRATIVE_MODEL,
            max_tokens=350,
            system=SYSTEM,
            messages=[{"role": "user", "content": f"Write the narrative.\n\n{facts}"}],
        )
        parts = [b.text for b in msg.content if getattr(b, "type", "") == "text"]
        text = "".join(parts).strip()
        return text or _fallback(ps)
    except Exception:
        return _fallback(ps)
