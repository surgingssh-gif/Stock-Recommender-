"""
prices.py - Looks up the latest price for each ticker using yfinance
(free Yahoo Finance data, no API key needed).
"""

import yfinance as yf


def get_price(ticker):
    """
    Returns the most recent price as a float, or None if it can't be found
    (for example if the ticker is wrong or Yahoo is having problems).
    """
    try:
        # Last 5 days of daily prices; the final row is the most recent.
        history = yf.Ticker(ticker).history(period="5d")
        # Yahoo sometimes returns a blank ("NaN") row for today, especially
        # after the market closes. Skip blanks and use the latest real price.
        closes = history["Close"].dropna() if not history.empty else history
        if closes.empty:
            return None
        return round(float(closes.iloc[-1]), 2)
    except Exception:
        return None


def get_prices(tickers):
    """Returns a dict like {"XOM": 112.34, "BADTICKER": None}."""
    return {ticker: get_price(ticker) for ticker in tickers}


def get_daily_swing(ticker, sessions=20):
    """
    How much the stock usually moves in a day, in percent: the typical size
    (standard deviation) of its daily moves over the last `sessions` trading
    days. A calm utility is around 1; a speculative small-cap can be 4 or
    more. None if Yahoo doesn't have enough prices.
    """
    try:
        closes = [float(c) for c in yf.Ticker(ticker).history(period="2mo")["Close"].dropna()][-(sessions + 1):]
        if len(closes) < 10:
            return None
        moves = [(b - a) / a * 100 for a, b in zip(closes, closes[1:])]
        mean = sum(moves) / len(moves)
        return round((sum((m - mean) ** 2 for m in moves) / (len(moves) - 1)) ** 0.5, 2)
    except Exception:
        return None


def get_daily_swings(tickers):
    """Returns a dict like {"XOM": 1.4, "IONQ": 4.1, "BADTICKER": None}."""
    return {ticker: get_daily_swing(ticker) for ticker in dict.fromkeys(tickers)}
