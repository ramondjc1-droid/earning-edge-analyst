"""Earnings calendar source.

Despite the legacy name, this no longer scrapes earningswhispers.com. It holds a
curated, liquid watchlist and uses yfinance to determine which names report
within a lookahead window. Stale/delisted symbols from the original handoff
(GPS, GLD, SQ) have been removed.

Expand WATCHLIST toward the full S&P 500 — or swap in a paid earnings calendar
API — for broader coverage.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from fetchers import yfinance_fetcher as yfin

# Curated liquid watchlist (~150 names across sectors). Mega/large-cap biased
# because the strategies need liquid options and clean earnings reactions.
WATCHLIST: list[str] = [
    # Mega-cap tech
    "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA", "AVGO", "ORCL",
    "ADBE", "CRM", "AMD", "INTC", "QCOM", "TXN", "CSCO", "IBM", "NOW", "INTU",
    "AMAT", "MU", "LRCX", "KLAC", "PANW", "SNPS", "CDNS", "ANET", "FTNT",
    # Software / internet
    "NFLX", "UBER", "ABNB", "SHOP", "SNOW", "PLTR", "CRWD", "DDOG", "NET",
    "ZS", "MDB", "TEAM", "WDAY", "ROKU", "PINS", "SNAP", "SPOT",
    # Financials
    "JPM", "BAC", "WFC", "C", "GS", "MS", "SCHW", "BLK", "AXP", "V", "MA",
    "PYPL", "COF", "USB", "PNC", "BX", "KKR",
    # Healthcare / biotech / pharma
    "UNH", "JNJ", "LLY", "PFE", "MRK", "ABBV", "TMO", "ABT", "DHR", "BMY",
    "AMGN", "GILD", "CVS", "ISRG", "VRTX", "REGN", "MRNA", "BIIB",
    # Consumer / retail
    "WMT", "COST", "HD", "LOW", "TGT", "NKE", "SBUX", "MCD", "CMG", "LULU",
    "DIS", "BKNG", "MAR", "DPZ", "ULTA", "ROST", "TJX", "DG", "DLTR",
    # Consumer staples
    "PG", "KO", "PEP", "PM", "MO", "MDLZ", "CL", "KHC", "GIS", "KMB",
    # Industrials / transport
    "CAT", "DE", "BA", "GE", "HON", "UPS", "FDX", "RTX", "LMT", "UNP", "MMM",
    "EMR", "ETN", "PH",
    # Energy
    "XOM", "CVX", "COP", "SLB", "EOG", "MPC", "PSX", "OXY", "DVN",
    # Communications / media
    "T", "VZ", "TMUS", "CMCSA", "WBD",
    # Semis / hardware extras
    "MRVL", "ON", "MCHP", "STX", "WDC", "DELL", "HPQ", "SMCI",
    # Autos / EV
    "F", "GM", "RIVN", "LCID",
    # Misc high-beta movers often with juicy earnings IV
    "COIN", "HOOD", "DKNG", "RBLX", "AFRM",
    # --- Affordable / sub-$50 names with liquid earnings reactions ---
    "SOFI", "PLTR", "NIO", "RIG", "AAL", "CCL", "NCLH", "UAL", "DAL",
    "GRAB", "BBD", "NU", "VALE", "KGC", "GOLD", "KMI", "GRPN",
    "CHPT", "RUN", "FUBO", "DNA", "IONQ", "RKLB", "ACHR", "JOBY",
    # --- Penny / low-priced (<$5) names that still trade big volume ---
    "PLUG", "MARA", "RIOT", "CLSK", "BBAI", "SOUN", "LCID", "RIVN",
    "WBD", "F", "SNAP", "PARA", "HBAN", "KEY", "RIG", "AMCR", "VTRS",
]
# Drop any known-bad / delisted / renamed symbols.
_BANNED = {"GPS", "GLD", "SQ", "FB", "TWTR"}
WATCHLIST = [t for t in dict.fromkeys(WATCHLIST) if t not in _BANNED]


def upcoming_earnings(
    lookahead_days: int = 10,
    tickers: Optional[list[str]] = None,
    skip: Optional[set[str]] = None,
) -> list[yfin.TickerData]:
    """Return TickerData for names reporting within ``lookahead_days``.

    Each returned object already carries the full metric set, so callers can
    score directly without re-fetching.
    """
    tickers = tickers or WATCHLIST
    skip = skip or set()
    results: list[yfin.TickerData] = []
    for t in tickers:
        if t in skip:
            continue
        td = yfin.fetch(t)
        if not td.ok:
            continue
        if td.days_to_earnings is None:
            continue
        if 0 <= td.days_to_earnings <= lookahead_days:
            results.append(td)
    return results


def force_fetch(ticker: str) -> yfin.TickerData:
    """Fetch a single ticker regardless of its earnings window (/add command)."""
    return yfin.fetch(ticker.upper())
