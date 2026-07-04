"""yfinance-backed data fetcher.

Pulls price history, computes momentum / volume / volatility metrics, locates
the next earnings date, and derives an approximate IV rank from the options
chain. yfinance does not expose a true 52-week IV history, so ``iv_rank`` here
is a *proxy*: current at-the-money implied vol mapped against the name's own
realized-volatility range. It is directionally useful, not a Bloomberg figure.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timedelta, timezone
from typing import Optional

import numpy as np

try:
    import yfinance as yf
except Exception:  # pragma: no cover - import guard
    yf = None


@dataclass
class TickerData:
    ticker: str
    ok: bool = False
    error: str = ""
    price: float = 0.0
    avg_volume: float = 0.0
    rel_volume: float = 1.0          # today's vol / 30d avg
    momentum_20d: float = 0.0        # % change over 20 sessions
    momentum_5d: float = 0.0
    realized_vol: float = 0.0        # annualized 20d realized vol
    iv_atm: float = 0.0              # current ATM implied vol (from options)
    iv_rank: float = 0.0             # 0-100 proxy
    iv_vs_historical: float = 0.0    # iv_atm / realized_vol ratio, normalized
    beta: float = 1.0
    days_to_earnings: Optional[int] = None
    earnings_date: Optional[str] = None
    earnings_date_confirmed: bool = False  # True when both yf sources agree
    earnings_surprise_pct: Optional[float] = None
    gap_pct: float = 0.0             # most recent overnight gap
    analyst_drift: float = 0.0       # proxy for estimate revisions / recos
    extras: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return asdict(self)


def _annualized_vol(closes: np.ndarray, window: int = 20) -> float:
    if len(closes) < window + 1:
        window = max(2, len(closes) - 1)
    rets = np.diff(np.log(closes[-(window + 1):]))
    if len(rets) == 0:
        return 0.0
    return float(np.std(rets) * math.sqrt(252))


def _pct_change(closes: np.ndarray, lookback: int) -> float:
    if len(closes) <= lookback:
        return 0.0
    return float((closes[-1] / closes[-1 - lookback] - 1.0) * 100.0)


def _next_earnings_date(tk) -> tuple[Optional[date], bool]:
    """Best-effort next earnings date, cross-checked across both yfinance
    sources.

    Returns (date, confirmed). ``confirmed`` is True only when the earnings-
    history table and the calendar endpoint agree within a few days — dates
    from a single source are usable but flagged so scoring can discount them.
    Past dates and dates implausibly far out (>120d) are rejected outright;
    yfinance sometimes returns a trailing report as "next".
    """
    today = date.today()

    def _valid(d: Optional[date]) -> Optional[date]:
        if d and today <= d <= today + timedelta(days=120):
            return d
        return None

    from_history: Optional[date] = None
    try:
        df = tk.get_earnings_dates(limit=12)
        if df is not None and not df.empty:
            now = datetime.now(timezone.utc)
            future = [idx for idx in df.index if idx.to_pydatetime() >= now]
            if future:
                from_history = _valid(min(future).date())
    except Exception:
        pass

    from_calendar: Optional[date] = None
    try:
        cal = tk.calendar
        if isinstance(cal, dict):
            ed = cal.get("Earnings Date")
            if isinstance(ed, (list, tuple)) and ed:
                ed = ed[0]
            if ed:
                from_calendar = _valid(ed if isinstance(ed, date) else ed.date())
    except Exception:
        pass

    if from_history and from_calendar:
        if abs((from_history - from_calendar).days) <= 4:
            # Calendar tends to carry the company-announced date; prefer it.
            return from_calendar, True
        # Sources disagree badly — take the earlier (safer for pre-earnings
        # plays: better to exit early than hold through a surprise report).
        return min(from_history, from_calendar), False
    single = from_history or from_calendar
    return (single, False) if single else (None, False)


def _earnings_surprise(tk) -> Optional[float]:
    try:
        df = tk.get_earnings_dates(limit=8)
        if df is None or df.empty:
            return None
        col_est = next((c for c in df.columns if "Estimate" in c), None)
        col_rep = next((c for c in df.columns if "Reported" in c), None)
        if not col_est or not col_rep:
            return None
        now = datetime.now(timezone.utc)
        past = df[[i.to_pydatetime() < now for i in df.index]].dropna(
            subset=[col_est, col_rep]
        )
        if past.empty:
            return None
        row = past.iloc[0]
        est, rep = float(row[col_est]), float(row[col_rep])
        if est == 0:
            return None
        return (rep - est) / abs(est) * 100.0
    except Exception:
        return None


def _atm_iv(tk, spot: float) -> float:
    """Average ATM implied vol from the nearest expiry options chain."""
    try:
        exps = tk.options
        if not exps:
            return 0.0
        chain = tk.option_chain(exps[0])
        ivs = []
        for opt in (chain.calls, chain.puts):
            if opt is None or opt.empty or "impliedVolatility" not in opt:
                continue
            opt = opt.dropna(subset=["impliedVolatility", "strike"])
            if opt.empty:
                continue
            opt = opt.assign(dist=(opt["strike"] - spot).abs()).sort_values("dist")
            near = opt.head(3)
            ivs.extend(v for v in near["impliedVolatility"].tolist() if v > 0)
        if not ivs:
            return 0.0
        return float(np.mean(ivs))
    except Exception:
        return 0.0


def _analyst_drift(tk) -> float:
    """Crude positive/negative tilt from recommendation mean (1=Buy..5=Sell)."""
    try:
        info = tk.fast_info
        _ = info  # touch to ensure object built
    except Exception:
        pass
    try:
        rec = tk.info.get("recommendationMean")
        if rec:
            # Map 1..5 -> +1..-1
            return float((3.0 - rec) / 2.0)
    except Exception:
        pass
    return 0.0


def fetch(ticker: str) -> TickerData:
    if yf is None:
        return TickerData(ticker=ticker, ok=False, error="yfinance not installed")
    td = TickerData(ticker=ticker)
    try:
        tk = yf.Ticker(ticker)
        hist = tk.history(period="3mo", interval="1d", auto_adjust=False)
        if hist is None or hist.empty or len(hist) < 6:
            td.error = "no price history (delisted or bad symbol)"
            return td

        closes = hist["Close"].to_numpy(dtype=float)
        vols = hist["Volume"].to_numpy(dtype=float)
        opens = hist["Open"].to_numpy(dtype=float)

        td.price = float(closes[-1])
        td.avg_volume = float(np.mean(vols[-30:])) if len(vols) >= 5 else float(np.mean(vols))
        recent_v = float(vols[-1])
        td.rel_volume = (recent_v / td.avg_volume) if td.avg_volume > 0 else 1.0
        td.momentum_20d = _pct_change(closes, 20)
        td.momentum_5d = _pct_change(closes, 5)
        td.realized_vol = _annualized_vol(closes, 20)
        if closes[-2] > 0:
            td.gap_pct = float((opens[-1] / closes[-2] - 1.0) * 100.0)

        # Volatility / IV proxy
        td.iv_atm = _atm_iv(tk, td.price)
        if td.iv_atm > 0 and td.realized_vol > 0:
            ratio = td.iv_atm / td.realized_vol
            td.iv_vs_historical = float(max(0.0, min(2.0, ratio)))
            # Map IV-to-RV ratio onto a 0-100 "rank-like" proxy.
            td.iv_rank = float(max(0.0, min(100.0, (ratio - 0.6) / 1.4 * 100.0)))
        elif td.realized_vol > 0:
            # No options: fall back to realized vol percentile-ish proxy
            td.iv_rank = float(max(0.0, min(100.0, td.realized_vol * 100.0)))

        try:
            td.beta = float(tk.info.get("beta") or 1.0)
        except Exception:
            td.beta = 1.0

        ed, confirmed = _next_earnings_date(tk)
        if ed:
            td.earnings_date = ed.isoformat()
            td.days_to_earnings = (ed - date.today()).days
            td.earnings_date_confirmed = confirmed
        td.earnings_surprise_pct = _earnings_surprise(tk)
        td.analyst_drift = _analyst_drift(tk)

        td.ok = True
    except Exception as exc:  # pragma: no cover - network/runtime guard
        td.error = f"{type(exc).__name__}: {exc}"
    return td
