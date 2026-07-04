"""The scoring formula.

Each play type produces a 0-1 score from a weighted blend of normalized
features, then a 0-10 confidence. Weights live in config/formula.yaml and are
adjustable at runtime via the /tune command.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from config import formula
from fetchers.yfinance_fetcher import TickerData

PLAY_TYPES = ("PRE_RUNUP", "IV_CRUSH", "POST_MOMENTUM")


@dataclass
class PlayScore:
    ticker: str
    play_type: str
    score: float          # 0-1 raw
    confidence: int       # 0-10
    rationale: dict       # feature -> contribution, for transparency
    data: TickerData

    @property
    def passes_gate(self) -> bool:
        f = formula()
        if self.confidence < f.get("min_confidence_to_send", 5):
            return False
        if self.data.price < f.get("min_price", 1.0):
            return False
        if self.data.price > f.get("max_price", 1e9):
            return False
        if self.data.avg_volume < f.get("min_avg_volume", 500000):
            return False
        return True


def _clip01(x: float) -> float:
    return max(0.0, min(1.0, x))


def _norm_momentum(pct: float) -> float:
    # Map -15%..+15% onto 0..1, centered at 0.5
    return _clip01(0.5 + pct / 30.0)


def _norm_rel_volume(rv: float) -> float:
    # 1x avg -> 0.5, 3x avg -> ~1.0
    return _clip01(rv / 3.0)


def _days_to_earnings_score(days: Optional[int], window: list[int]) -> float:
    if days is None:
        return 0.0
    lo, hi = window
    if lo <= days <= hi:
        return 1.0
    # Linear decay outside the sweet-spot window
    if days < lo:
        return _clip01(1.0 - (lo - days) / max(lo, 1))
    return _clip01(1.0 - (days - hi) / max(hi, 1))


def _to_confidence(score: float) -> int:
    return int(round(_clip01(score) * 10))


def score_pre_runup(d: TickerData) -> PlayScore:
    cfg = formula()["pre_runup"]
    w = cfg["weights"]
    window = cfg.get("ideal_days_before", [3, 10])

    feats = {
        "momentum_20d": _norm_momentum(d.momentum_20d),
        "rel_volume": _norm_rel_volume(d.rel_volume),
        "iv_rank": _clip01(d.iv_rank / 100.0),
        "days_to_earnings": _days_to_earnings_score(d.days_to_earnings, window),
        "analyst_drift": _clip01(0.5 + d.analyst_drift / 2.0),
    }
    contributions = {k: feats[k] * w[k] for k in w}
    raw = sum(contributions.values())
    # Normalize by sum of positive weights so score lands in a sane 0-1 band
    denom = sum(abs(v) for v in w.values()) or 1.0
    score = _clip01((raw + abs(min(0, sum(v for v in w.values() if v < 0)))) / denom)
    # Timing-sensitive play: discount when the earnings date is single-source.
    if not d.earnings_date_confirmed:
        score *= 0.85
    return PlayScore(d.ticker, "PRE_RUNUP", score, _to_confidence(score),
                     contributions, d)


def score_iv_crush(d: TickerData) -> PlayScore:
    cfg = formula()["iv_crush"]
    w = cfg["weights"]

    liquidity = _clip01(d.avg_volume / 5_000_000)
    stability = _clip01(1.0 - (d.beta - 1.0) / 2.0)  # lower beta -> higher
    feats = {
        "iv_rank": _clip01(d.iv_rank / 100.0),
        "iv_vs_historical": _clip01((d.iv_vs_historical - 0.8) / 1.2),
        "liquidity": liquidity,
        "stability": stability,
    }
    contributions = {k: feats[k] * w[k] for k in w}
    denom = sum(w.values()) or 1.0
    score = _clip01(sum(contributions.values()) / denom)

    # Hard gate: IV rank must clear the configured floor
    if d.iv_rank < cfg.get("min_iv_rank", 50):
        score *= 0.3
    # Timing-sensitive play: discount when the earnings date is single-source.
    if not d.earnings_date_confirmed:
        score *= 0.85
    return PlayScore(d.ticker, "IV_CRUSH", score, _to_confidence(score),
                     contributions, d)


def score_post_momentum(d: TickerData) -> PlayScore:
    cfg = formula()["post_momentum"]
    w = cfg["weights"]

    surprise = d.earnings_surprise_pct or 0.0
    feats = {
        "earnings_surprise": _clip01(surprise / 20.0),
        "gap_strength": _clip01(d.gap_pct / 10.0),
        "volume_confirm": _norm_rel_volume(d.rel_volume),
        "momentum_5d": _norm_momentum(d.momentum_5d),
    }
    contributions = {k: feats[k] * w[k] for k in w}
    denom = sum(w.values()) or 1.0
    score = _clip01(sum(contributions.values()) / denom)

    if surprise < cfg.get("min_surprise_pct", 3.0):
        score *= 0.4
    return PlayScore(d.ticker, "POST_MOMENTUM", score, _to_confidence(score),
                     contributions, d)


def score_all(d: TickerData) -> list[PlayScore]:
    """Score a ticker across every enabled play type."""
    f = formula()
    out: list[PlayScore] = []
    if f["pre_runup"].get("enabled", True):
        out.append(score_pre_runup(d))
    if f["iv_crush"].get("enabled", True):
        out.append(score_iv_crush(d))
    if f["post_momentum"].get("enabled", True):
        out.append(score_post_momentum(d))
    return out


def best_play(d: TickerData) -> Optional[PlayScore]:
    """Return the single highest-confidence play for a ticker."""
    scores = score_all(d)
    return max(scores, key=lambda s: s.score) if scores else None


def score_momentum(d: TickerData) -> PlayScore:
    """Off-season TRENDING play — pure momentum/volume/IV, no earnings needed.

    Used to fill the card when few names are reporting. Rewards names that are
    moving (20d + 5d momentum aligned), trading on elevated relative volume, and
    carrying juiced implied vol.
    """
    cfg = formula().get("momentum", {})
    w = cfg.get("weights", {
        "momentum_20d": 0.35, "momentum_5d": 0.25,
        "rel_volume": 0.25, "iv_rank": 0.15,
    })
    feats = {
        "momentum_20d": _norm_momentum(d.momentum_20d),
        "momentum_5d": _norm_momentum(d.momentum_5d),
        "rel_volume": _norm_rel_volume(d.rel_volume),
        "iv_rank": _clip01(d.iv_rank / 100.0),
    }
    contributions = {k: feats[k] * w[k] for k in w}
    denom = sum(w.values()) or 1.0
    score = _clip01(sum(contributions.values()) / denom)
    return PlayScore(d.ticker, "MOMENTUM", score, _to_confidence(score),
                     contributions, d)
