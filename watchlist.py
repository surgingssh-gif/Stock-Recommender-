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
