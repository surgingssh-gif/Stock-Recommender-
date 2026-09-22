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
        if history.empty:
            return None
        return round(float(history["Close"].iloc[-1]), 2)
    except Exception:
        return None


def get_prices(tickers):
    """Returns a dict like {"XOM": 112.34, "BADTICKER": None}."""
    return {ticker: get_price(ticker) for ticker in tickers}
