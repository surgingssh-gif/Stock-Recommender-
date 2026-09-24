"""
market_data.py - A quick look at what's actually moving: the biggest
gainers, losers and most-traded stocks from the latest session, plus
pre-market moves for the stocks we follow. Free data from Yahoo (yfinance).

Everything here is optional: if Yahoo doesn't answer, the bot carries on
with the news alone.
"""

import yfinance as yf

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
