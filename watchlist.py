"""
watchlist.py - The "Market watch" stocks shown on the dashboard's Stock Charts
tab every day, next to the bot's picks.

Each day Claude also writes a one-sentence note for each of these about what
the news means for it (in the same single request that picks the stocks).

To change the list, add or remove lines below: "TICKER": "Name shown on the page".
Keep it to about 20 or fewer so the page (and the Claude request) stays small.
"""

WATCHLIST = {
    "SPY": "S&P 500 (index fund)",
    "QQQ": "Nasdaq 100 (index fund)",
    "DIA": "Dow Jones (index fund)",
    "AAPL": "Apple",
    "MSFT": "Microsoft",
    "NVDA": "NVIDIA",
    "AMZN": "Amazon",
    "GOOGL": "Alphabet (Google)",
    "META": "Meta Platforms",
    "TSLA": "Tesla",
    "JPM": "JPMorgan Chase",
    "XOM": "Exxon Mobil",
    "GLD": "Gold (fund)",
    "TLT": "Long-term US Treasury bonds (fund)",
}


# The 11 sector funds shown in the "Sectors" heat map on the Today tab.
# (Prices only - Claude doesn't write notes for these, so they cost nothing.)
SECTORS = {
    "XLK": "Technology",
    "XLC": "Communication",
    "XLY": "Consumer Discretionary",
    "XLP": "Consumer Staples",
    "XLE": "Energy",
    "XLF": "Financials",
    "XLV": "Health Care",
    "XLI": "Industrials",
    "XLB": "Materials",
    "XLRE": "Real Estate",
    "XLU": "Utilities",
}

# Funds (not companies), so they have no earnings dates to look up.
FUNDS = {"SPY", "QQQ", "DIA", "GLD", "TLT", *SECTORS}

# Federal Reserve interest-rate meetings (the second day, when the decision
# is announced). From federalreserve.gov - add next year's dates each December.
FED_MEETINGS = [
    "2026-01-28", "2026-03-18", "2026-04-29", "2026-06-17",
    "2026-07-29", "2026-09-16", "2026-10-28", "2026-12-09",
]
