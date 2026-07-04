"""Formatting helpers for Telegram pick cards (HTML parse mode)."""
from __future__ import annotations

from datetime import date

from model.scoring import PlayScore

_EMOJI = {"PRE_RUNUP": "🚀", "IV_CRUSH": "💥", "POST_MOMENTUM": "📈", "MOMENTUM": "🔥"}


def _bars(confidence: int) -> str:
    full = "█" * confidence
    empty = "░" * (10 - confidence)
    return f"{full}{empty} {confidence}/10"


def _tier(price: float) -> str:
    if price < 5:
        return "🪙 Penny"
    return "💵 Sub-$50"


def is_penny(ps: PlayScore) -> bool:
    return ps.data.price < 5.0


def pick_card(ps: PlayScore, narrative: str) -> str:
    d = ps.data
    emoji = _EMOJI.get(ps.play_type, "•")
    lines = [
        f"{emoji} <b>${d.ticker}</b> — <b>{ps.play_type}</b>",
        f"Confidence: <code>{_bars(ps.confidence)}</code>",
        "",
        f"💵 Price: <b>${d.price:,.2f}</b>  ·  {_tier(d.price)}",
    ]
    # Only show an earnings date that is actually upcoming (skip stale/past ones).
    if d.earnings_date and (d.days_to_earnings is None or d.days_to_earnings >= 0):
        when = f"{d.earnings_date}"
        if d.days_to_earnings is not None:
            when += f" (in {d.days_to_earnings}d)"
        if not d.earnings_date_confirmed:
            when += " ⚠️ unconfirmed"
        lines.append(f"📅 Earnings: <b>{when}</b>")
    lines.append(
        f"📊 IV-rank: <b>{d.iv_rank:.0f}</b> · Mom20d: <b>{d.momentum_20d:+.1f}%</b> "
        f"· RelVol: <b>{d.rel_volume:.1f}x</b>"
    )
    if d.earnings_surprise_pct is not None:
        lines.append(f"🎯 Last surprise: <b>{d.earnings_surprise_pct:+.1f}%</b>")
    lines += ["", f"<i>{narrative}</i>"]
    return "\n".join(lines)


def header(n_main: int, n_penny: int, n_momentum: int = 0,
           d: str | None = None) -> str:
    d = d or date.today().isoformat()
    parts = []
    if n_main:
        parts.append(f"{n_main} main")
    if n_penny:
        parts.append(f"{n_penny} penny")
    if n_momentum:
        parts.append(f"{n_momentum} trending")
    summary = " + ".join(parts) + " picks" if parts else "No plays"
    return (f"🔔 <b>EARNINGS EDGE — Morning Scan</b>\n"
            f"<i>{d}</i>\n"
            f"{summary} today\n"
            f"{'─' * 22}")


def section_header(title: str) -> str:
    return f"\n{'━' * 22}\n<b>{title}</b>\n{'━' * 22}"


def footer() -> str:
    return ("\n<i>⚠️ Informational only — not financial advice. "
            "Do your own research and manage risk.</i>")


def no_picks() -> str:
    return ("🔕 <b>EARNINGS EDGE — Morning Scan</b>\n"
            f"<i>{date.today().isoformat()}</i>\n\n"
            "No qualifying plays cleared the confidence gate today. "
            "Sitting in cash is a position too.")
