"""
logos.py - Looks up company logos from Finnhub (the same free account used
for the news) so the dashboard can show them. Each company is looked up
only once; the results are saved in data/logos.json.

Funds (like SPY) don't have logos; the dashboard shows a tidy ticker tile instead.
"""

import json
import os

import requests

FINNHUB_PROFILE_URL = "https://finnhub.io/api/v1/stock/profile2"
LOGO_FILE = os.path.join("data", "logos.json")


def load_logos(path=LOGO_FILE):
    """{ticker: logo URL ("" if the company has none)}, or {} if nothing is saved yet."""
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def update_logos(api_key, tickers, path=LOGO_FILE):
    """
    Looks up any tickers not already saved and adds them to data/logos.json.
    Returns how many were looked up. A failed lookup is simply tried again
    next time (it isn't saved).
    """
    logos = load_logos(path)
    looked_up = 0
    for ticker in sorted(set(tickers) - set(logos)):
        try:
            response = requests.get(
                FINNHUB_PROFILE_URL,
                params={"symbol": ticker},
                headers={"X-Finnhub-Token": api_key},  # key in a header, never the URL
                timeout=20,
            )
            response.raise_for_status()
            logo = (response.json() or {}).get("logo") or ""
        except Exception:
            continue
        logos[ticker] = logo if logo.startswith("https://") else ""
        looked_up += 1
    if looked_up:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(logos, f, indent=2, sort_keys=True)
    return looked_up
