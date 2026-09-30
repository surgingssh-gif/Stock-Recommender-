"""
market_data.py - A quick look at what's actually moving: the biggest
gainers, losers and most-traded stocks from the latest session, plus
pre-market moves for the stocks we follow. Free data from Yahoo (yfinance).

Everything here is optional: if Yahoo doesn't answer, the bot carries on
with the news alone.
"""

import yfinance as yf

from watchlist import SECTORS

# Yahoo's ready-made stock lists, and how we describe each one.
SCREENS = {
    "day_gainers": "Biggest gainers",
    "day_losers": "Biggest losers",
    "most_actives": "Most traded",
}
PER_SCREEN = 6


def get_market_movers():
    """{"Biggest gainers": [(ticker, name, change %), ...], ...}; lists Yahoo skips are left out."""
    movers = {}
    for screen, label in SCREENS.items():
        try:
            quotes = yf.screen(screen, count=PER_SCREEN)["quotes"]
            movers[label] = [
                (q["symbol"], q.get("shortName") or q["symbol"], round(q.get("regularMarketChangePercent") or 0, 2))
                for q in quotes
            ]
        except Exception:
            continue
    return movers


def get_premarket_moves(tickers):
    """[(ticker, change %), ...] for tickers trading before the open (only filled in before 9:30 AM ET)."""
    moves = []
    for ticker in tickers:
        try:
            info = yf.Ticker(ticker).info
            change = info.get("preMarketChangePercent")
            if info.get("marketState") == "PRE" and change is not None:
                moves.append((ticker, round(change, 2)))
        except Exception:
            continue
    return moves


def format_market_data(movers, premarket):
    """The movers as a few plain-text lines for Claude, or None if there's nothing."""
    lines = []
    for label, items in movers.items():
        if items:
            lines.append(f"{label} in the latest session: " + ", ".join(f"{t} ({name}) {chg:+.2f}%" for t, name, chg in items))
    if premarket:
        premarket = sorted(premarket, key=lambda m: abs(m[1]), reverse=True)
        lines.append("Pre-market moves right now: " + ", ".join(f"{t} {chg:+.2f}%" for t, chg in premarket))
    return "\n".join(lines) or None


def _change(closes, days_back):
    if len(closes) <= days_back:
        return None
    return (closes[-1] - closes[-1 - days_back]) / closes[-1 - days_back] * 100


def get_market_backdrop():
    """
    The bigger picture, as text for Claude: how the S&P 500 has moved over the
    last day, week and month, and each sector over the last week. None if
    Yahoo has nothing.
    """
    lines = []
    try:
        spy = [float(c) for c in yf.Ticker("SPY").history(period="2mo")["Close"].dropna()]
        parts = [f"{label} {chg:+.1f}%" for label, n in (("1 day", 1), ("1 week", 5), ("1 month", 21))
                 if (chg := _change(spy, n)) is not None]
        if parts:
            lines.append("S&P 500 (SPY): " + ", ".join(parts))
    except Exception:
        pass
    sectors = []
    for ticker, name in SECTORS.items():
        try:
            closes = [float(c) for c in yf.Ticker(ticker).history(period="1mo")["Close"].dropna()]
            chg = _change(closes, 5)
            if chg is not None:
                sectors.append((name, chg))
        except Exception:
            continue
    if sectors:
        sectors.sort(key=lambda x: x[1], reverse=True)
        lines.append("Sectors over the last week: " + ", ".join(f"{n} {c:+.1f}%" for n, c in sectors))
    return "\n".join(lines) or None
