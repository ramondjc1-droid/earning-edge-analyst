"""Earnings calendar source.

Holds a broad watchlist biased toward affordable (<$50) and penny (<$5) names
that have liquid options and clean earnings reactions. Uses yfinance to determine
which names report within a lookahead window.

The watchlist is deliberately large (~400+ tickers) because most names are NOT
reporting in any given 2-week window. Stale/delisted symbols go in _BANNED.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from fetchers import yfinance_fetcher as yfin

WATCHLIST: list[str] = [
    # =====================================================================
    # SUB-$50 — the core of the picks (sorted by sector)
    # =====================================================================

    # Tech / software (affordable tier)
    "PLTR", "SNAP", "PINS", "HOOD", "RBLX", "DKNG", "SOFI", "AFRM",
    "FUBO", "GRPN", "WISH", "OPEN", "VUZI", "BIGC", "CLOV", "SKLZ",
    "BMBL", "MTTR", "PATH", "AI", "BRZE", "CWAN", "ASAN", "WEAV",
    "MNDY", "SEMR", "FRSH", "GTLB", "SPT", "BIRD",

    # Fintech / finance (sub-$50)
    "NU", "UPST", "LMND", "PSFE", "PAYO", "OWL", "GRAB", "BBD",
    "ITUB", "SAN", "BBAR", "BMA", "MELI", "STNE", "PAGS",
    "HBAN", "KEY", "CFG", "RF", "ZION", "CMA", "FHN", "WAL",
    "ALLY", "SYF", "CACC", "LC", "LU",

    # Biotech / pharma (sub-$50 — high IV around earnings)
    "SNDL", "TLRY", "ACB", "CGC", "CRON",  # cannabis
    "CPRX", "TEVA", "VTRS", "OGN", "AMRX",  # generic pharma
    "GERN", "AGEN", "APLS", "CRSP", "BEAM", "NTLA", "EDIT",
    "EXAS", "NTRA", "VEEV", "HIMS", "DOCS", "ACAD", "ARVN",
    "RXRX", "DNLI", "FATE", "ALNY", "SRPT", "IONS",
    "IOVA", "XNCR", "RCKT", "SAVA", "CORT", "OCUL",

    # Consumer / retail (sub-$50)
    "NKE", "DG", "DLTR", "BBY", "FIVE", "CROX", "SKX", "HBI",
    "LEVI", "GPS", "VSCO", "WRBY", "RENT", "PRPL", "CSPR",
    "BROS", "SHAK", "JACK", "WING", "NDLS", "LOCO", "ARCO",
    "BJ", "OLLI", "CATO", "RVLV", "REAL", "CURV", "XPOF",

    # Industrials / materials (sub-$50)
    "CLF", "X", "AA", "VALE", "RIG", "NOV", "HP", "PTEN",
    "SWN", "AR", "RRC", "CNX", "CTRA", "CHRD", "MUR", "SM",
    "KGC", "GOLD", "HL", "AG", "FSM", "PAAS", "MAG", "EGO",
    "BTG", "AUY", "SSRM", "GATO",

    # Airlines / travel / cruise (sub-$50, high beta)
    "AAL", "DAL", "UAL", "SAVE", "JBLU", "ALK", "HA",
    "CCL", "NCLH", "RCL",
    "ABNB", "EXPE", "TRIP", "LIND", "BKNG",
    "MGM", "WYNN", "CZR", "PENN", "RSI",

    # Autos / EV (sub-$50)
    "F", "GM", "RIVN", "LCID", "XPEV", "LI", "NIO", "GOEV",
    "QS", "CHPT", "BLNK", "EVGO", "DCFC", "MULN",
    "FSR", "PSNY", "WKHS", "NKLA", "REE", "HYLN",

    # Clean energy (sub-$50)
    "PLUG", "RUN", "ENPH", "SEDG", "ARRY", "MAXN", "NOVA",
    "STEM", "BLDP", "FCEL", "BE", "SPWR",

    # Media / entertainment (sub-$50)
    "WBD", "PARA", "LYV", "ROKU", "SPOT", "SONO", "GENI",
    "CARG", "YELP", "ANGI", "ZG", "OPRA", "PUBM",

    # Telecom / connectivity (sub-$50)
    "T", "LUMN", "ASTS", "IRDM", "GSAT",
    "DISH", "SATS", "GILT",

    # REITs / real estate (sub-$50)
    "AGNC", "NLY", "MFA", "RWT", "TWO", "ARR", "BRMK",
    "MPW", "SBRA", "OHI", "GMRE",

    # =====================================================================
    # PENNY STOCKS (<$5) — high volume movers with real earnings
    # =====================================================================
    "MARA", "RIOT", "CLSK", "BITF", "HUT", "ARBK",  # crypto miners
    "SOUN", "BBAI", "GFAI", "BFRG",  # AI penny plays
    "DNA", "ACHR", "JOBY", "RKLB", "LUNR", "RDW",  # space / drones
    "IONQ", "RGTI", "QUBT",  # quantum computing
    "VFS", "FFIE", "RIDE",  # EV pennies
    "CLVR", "IQ", "HUYA", "BILI",  # China internet
    "BYND", "IRBT", "PERI", "GDRX", "SDC",
    "APRE", "AMCR", "CIEN", "TRUP", "PETS",
    "PRCH", "OLO", "COUR", "UDMY",  # ed-tech / proptech

    # =====================================================================
    # LIQUID MID-CAPS ($20-$50) that frequently produce IV crush plays
    # =====================================================================
    "KMI", "MO", "T", "VZ", "WBA", "PFE", "INTC", "CSCO",
    "KHC", "KR", "GOLD", "HAL", "BKR", "SLB",
    "SNAP", "LYFT", "UBER", "COIN",
    "AMD", "MU", "MRVL", "ON", "STX", "WDC",
    "HPQ", "DELL", "SMCI",
    "PYPL", "SQ", "SHOP", "ETSY",
    "BAC", "C", "USB", "SCHW",
]

_BANNED = {"GPS", "GLD", "FB", "TWTR", "SQ"}
WATCHLIST = [t for t in dict.fromkeys(WATCHLIST) if t not in _BANNED]


def upcoming_earnings(
    lookahead_days: int = 14,
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
