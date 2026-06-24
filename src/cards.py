"""Formatting helpers for Telegram pick cards (HTML parse mode)."""
from __future__ import annotations

from datetime import date

from model.scoring import PlayScore

_EMOJI = {"PRE_RUNUP": "🚀", "IV_CRUSH": "💥", "POST_MOMENTUM": "📈"}


def _bars(confidence: int) -> str:
    full = "█" * confidence
    empty = "░" * (10 - confidence)
    return f"{full}{empty} {confidence}/10"


def pick_card(ps: PlayScore, narrative: str) -> str:
    d = ps.data
    emoji = _EMOJI.get(ps.play_type, "•")
    lines = [
        f"{emoji} <b>${d.ticker}</b> — <b>{ps.play_type}</b>",
        f"Confidence: <code>{_bars(ps.confidence)}</code>",
        "",
        f"💵 Price: <b>${d.price:,.2f}</b>",
    ]
    if d.earnings_date:
        when = f"{d.earnings_date}"
        if d.days_to_earnings is not None:
            when += f" (in {d.days_to_earnings}d)"
        lines.append(f"📅 Earnings: <b>{when}</b>")
    lines.append(
        f"📊 IV-rank: <b>{d.iv_rank:.0f}</b> · Mom20d: <b>{d.momentum_20d:+.1f}%</b> "
        f"· RelVol: <b>{d.rel_volume:.1f}x</b>"
    )
    if d.earnings_surprise_pct is not None:
        lines.append(f"🎯 Last surprise: <b>{d.earnings_surprise_pct:+.1f}%</b>")
    lines += ["", f"<i>{narrative}</i>"]
    return "\n".join(lines)


def header(n: int, d: str | None = None) -> str:
    d = d or date.today().isoformat()
    return (f"🔔 <b>EARNINGS EDGE — Morning Scan</b>\n"
            f"<i>{d}</i>\n"
            f"Top {n} play{'s' if n != 1 else ''} today\n"
            f"{'─' * 22}")


def footer() -> str:
    return ("\n<i>⚠️ Informational only — not financial advice. "
            "Do your own research and manage risk.</i>")


def no_picks() -> str:
    return ("🔕 <b>EARNINGS EDGE — Morning Scan</b>\n"
            f"<i>{date.today().isoformat()}</i>\n\n"
            "No qualifying plays cleared the confidence gate today. "
            "Sitting in cash is a position too.")
