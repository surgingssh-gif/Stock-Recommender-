"""
picks_log.py - Appends every pick to picks_log.csv so performance can be
checked later. Open the file in Excel or Google Sheets to look at it.
"""

import csv
import json
import os

LOG_FILE = "picks_log.csv"
COLUMNS = ["date", "ticker", "direction", "reason", "price_at_pick"]


def log_picks(date_str, picks, prices, log_file=LOG_FILE):
    """Adds one row per pick. Creates the file (with a header row) if needed."""
    file_is_new = not os.path.exists(log_file)

    # newline="" stops Windows from adding blank lines between rows.
    with open(log_file, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if file_is_new:
            writer.writerow(COLUMNS)
        for pick in picks:
            price = prices.get(pick["ticker"])
            writer.writerow([
                date_str,
                pick["ticker"],
                pick["direction"],
                pick["reason"],
                "" if price is None else price,  # blank if price lookup failed
            ])


DAYS_DIR = os.path.join("data", "days")


def save_day_details(date_str, analysis, headlines, days_dir=DAYS_DIR):
    """
    Saves the day's extra details (market mood, company names, confidence,
    and the headlines Claude read) to data/days/<date>.json. The dashboard
    uses these; picks_log.csv stays the main record.
    """
    os.makedirs(days_dir, exist_ok=True)
    details = {
        "date": date_str,
        "market_mood": analysis["market_mood"],
        "picks": analysis["picks"],
        # One-sentence notes for the "market watch" stocks (see watchlist.py).
        "watchlist_notes": analysis.get("watchlist_notes", []),
        # The "Top 5 buys of the day", with their longer explanations.
        "top_buys": analysis.get("top_buys", []),
        # Picks refer to headlines by number ("sources": [3, 7]), starting
        # at 1, so keep them in the same order Claude saw them.
        "headlines": [
            {
                "headline": h["headline"],
                "source": h["source"],
                "time": h["time"],
                "summary": h.get("summary", ""),
                "url": h.get("url", ""),
                "image": h.get("image", ""),
            }
            for h in headlines
        ],
    }
    with open(os.path.join(days_dir, f"{date_str}.json"), "w", encoding="utf-8") as f:
        json.dump(details, f, indent=2)
