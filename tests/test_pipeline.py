"""Offline smoke tests — validate scoring/cards/db without live market data.

Live data (yfinance/Yahoo) is intentionally not exercised here so the suite is
deterministic and runnable anywhere, including egress-restricted CI.
"""
import json
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from fetchers.yfinance_fetcher import TickerData  # noqa: E402
from model import scoring  # noqa: E402
import cards  # noqa: E402
import narratives  # noqa: E402


def _high_iv_name() -> TickerData:
    return TickerData(
        ticker="FDX", ok=True, price=45.30, avg_volume=2_400_000, rel_volume=1.8,
        momentum_20d=4.2, momentum_5d=1.1, realized_vol=0.28, iv_atm=0.55,
        iv_rank=100.0, iv_vs_historical=1.96, beta=1.15, days_to_earnings=2,
        earnings_date=(date.today() + timedelta(days=2)).isoformat(),
        earnings_date_confirmed=True,
        earnings_surprise_pct=6.4,
    )


def test_unconfirmed_date_scores_lower():
    confirmed = scoring.best_play(_high_iv_name())
    d = _high_iv_name()
    d.earnings_date_confirmed = False
    unconfirmed = scoring.best_play(d)
    assert unconfirmed.score < confirmed.score


def test_high_iv_picks_iv_crush():
    best = scoring.best_play(_high_iv_name())
    assert best.play_type == "IV_CRUSH"
    assert best.confidence >= 7
    assert best.passes_gate


def test_low_iv_does_not_pick_iv_crush():
    d = _high_iv_name()
    d.iv_rank = 10.0
    d.iv_vs_historical = 0.7
    best = scoring.best_play(d)
    assert best.play_type != "IV_CRUSH"


def test_illiquid_name_fails_gate():
    d = _high_iv_name()
    d.avg_volume = 50_000  # below min_avg_volume (200k)
    best = scoring.best_play(d)
    assert not best.passes_gate


def test_pricey_name_fails_gate():
    d = _high_iv_name()
    d.price = 950.0  # above max_price cap
    best = scoring.best_play(d)
    assert not best.passes_gate


def test_penny_name_passes_price_floor():
    d = _high_iv_name()
    d.price = 3.20  # penny, above the $1 floor
    best = scoring.best_play(d)
    assert best.passes_gate


def test_momentum_scores_trending_name():
    d = _high_iv_name()
    d.earnings_date = None  # no imminent earnings
    d.days_to_earnings = None
    d.momentum_20d = 18.0
    d.momentum_5d = 7.0
    d.rel_volume = 2.5
    ms = scoring.score_momentum(d)
    assert ms.play_type == "MOMENTUM"
    assert ms.confidence >= 5
    assert ms.passes_gate


def test_all_play_types_scored():
    scores = scoring.score_all(_high_iv_name())
    assert {s.play_type for s in scores} == set(scoring.PLAY_TYPES)
    for s in scores:
        assert 0.0 <= s.score <= 1.0
        assert 0 <= s.confidence <= 10


def test_card_and_narrative_render():
    best = scoring.best_play(_high_iv_name())
    narrative = narratives.generate(best)  # template fallback w/o API key
    card = cards.pick_card(best, narrative)
    assert "$FDX" in card
    assert "IV_CRUSH" in card
    assert "not financial advice" in narrative.lower()


def test_metrics_json_roundtrips():
    d = _high_iv_name()
    blob = json.dumps(d.as_dict(), default=str)
    assert json.loads(blob)["ticker"] == "FDX"


def test_iv_history_percentile():
    import db
    from datetime import timedelta as td_
    db.init_db()
    tkr = "TESTIV"
    # Below min_obs -> None (cold start falls back to proxy)
    db.record_iv(tkr, 0.30)
    assert db.iv_percentile(tkr, 0.30) is None
    # Seed 20 observations from 0.20 rising to 0.39
    for i in range(20):
        db.record_iv(tkr, 0.20 + i * 0.01,
                     obs_date=(date.today() - td_(days=i + 1)).isoformat())
    high = db.iv_percentile(tkr, 0.50)
    low = db.iv_percentile(tkr, 0.10)
    assert high is not None and high > 90
    assert low is not None and low < 10
    # Cleanup so reruns stay deterministic
    with db.connect() as conn:
        conn.execute("DELETE FROM iv_history WHERE ticker = ?", (tkr,))


def test_grader_thesis_logic():
    import grader

    # IV_CRUSH: IV collapses, small move -> WIN even if the stock dipped
    pnl, outcome, _ = grader.grade_play("IV_CRUSH", 100.0, 97.0, 0.60, 0.40)
    assert outcome == "WIN" and pnl < 0
    # IV_CRUSH: big blow-through move -> LOSS even though IV dropped
    _, outcome, _ = grader.grade_play("IV_CRUSH", 100.0, 112.0, 0.60, 0.40)
    assert outcome == "LOSS"
    # PRE_RUNUP: drift up -> WIN
    _, outcome, _ = grader.grade_play("PRE_RUNUP", 100.0, 103.0, 0, 0)
    assert outcome == "WIN"
    # MOMENTUM: reversal -> LOSS
    _, outcome, _ = grader.grade_play("MOMENTUM", 100.0, 95.0, 0, 0)
    assert outcome == "LOSS"


def test_grader_exit_dates():
    import grader
    picked = date(2026, 7, 1)
    reports = date(2026, 7, 10)
    assert grader.exit_date("PRE_RUNUP", picked, reports) == date(2026, 7, 9)
    assert grader.exit_date("IV_CRUSH", picked, reports) == date(2026, 7, 11)
    assert grader.exit_date("MOMENTUM", picked, None) == date(2026, 7, 6)
    # Earnings plays without a date can't be graded yet
    assert grader.exit_date("IV_CRUSH", picked, None) is None


if __name__ == "__main__":
    # Allow running without pytest installed.
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    for fn in fns:
        fn()
        print(f"  ✓ {fn.__name__}")
        passed += 1
    print(f"\n{passed}/{len(fns)} tests passed")
