"""
main.py - The daily stock news bot. Run it with:

    python main.py            (normal run: posts to Discord)
    python main.py --dry-run  (prints the message instead of posting it)

Steps:
  1. Get the latest headlines from Finnhub
  2. Ask Claude (one API call) which stocks the news could move
  3. Look up current prices with yfinance
  4. Save every pick to picks_log.csv
  5. Post the message to Discord

If any step fails, the bot keeps going with whatever it has and adds a
note to the message explaining what went wrong.

This is a research tool only. It never places trades.
"""

import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

from analyzer import analyze_headlines
from discord_notify import build_message, send_to_discord
from news import fetch_headlines
from picks_log import log_picks, save_day_details
from prices import get_prices
from watchlist import WATCHLIST


def main():
    dry_run = "--dry-run" in sys.argv

    # Load API keys from the .env file (on your computer). On GitHub Actions
    # there's no .env file; the keys come from GitHub Secrets instead.
    load_dotenv()
    finnhub_key = os.getenv("FINNHUB_API_KEY")
    anthropic_key = os.getenv("ANTHROPIC_API_KEY")
    webhook_url = os.getenv("DISCORD_WEBHOOK_URL")

    # Use US market time for the date.
    date_str = datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d")
    problems = []  # anything that goes wrong gets noted here

    # --- Step 1: News -------------------------------------------------------
    headlines = []
    if not finnhub_key:
        problems.append("FINNHUB_API_KEY is not set, so no news was fetched.")
    else:
        try:
            headlines = fetch_headlines(finnhub_key)
            print(f"Fetched {len(headlines)} headlines.")
            if not headlines:
                problems.append("Finnhub returned no recent headlines.")
        except Exception as e:
            problems.append(f"News (Finnhub) failed: {e}")

    # --- Step 2: Claude analysis --------------------------------------------
    analysis = None
    if headlines:
        if not anthropic_key:
            problems.append("ANTHROPIC_API_KEY is not set, so no analysis was done.")
        else:
            try:
                analysis = analyze_headlines(headlines, anthropic_key, WATCHLIST)
                print(f"Claude suggested {len(analysis['picks'])} picks.")
            except Exception as e:
                problems.append(f"Analysis (Claude) failed: {e}")

    # --- Step 3: Prices -----------------------------------------------------
    prices = {}
    if analysis and analysis["picks"]:
        prices = get_prices([p["ticker"] for p in analysis["picks"]])
        missing = [t for t, price in prices.items() if price is None]
        if missing:
            problems.append(f"Couldn't get prices for: {', '.join(missing)}")

    # --- Step 4: Log picks --------------------------------------------------
    if analysis and analysis["picks"] and dry_run:
        print("Dry run: picks were NOT saved to picks_log.csv.")
    elif analysis and analysis["picks"]:
        try:
            log_picks(date_str, analysis["picks"], prices)
            save_day_details(date_str, analysis, headlines)
            print("Saved picks to picks_log.csv and data/days/.")
        except Exception as e:
            problems.append(f"Saving picks failed: {e}")

    # --- Step 5: Send the message -------------------------------------------
    # Also print problems here, so they show up in the GitHub Actions log.
    for problem in problems:
        print(f"Problem: {problem}")

    message = build_message(date_str, analysis, prices, problems, headlines)

    if dry_run:
        print("\n----- DRY RUN: message not sent -----\n")
        print(message)
        return

    if not webhook_url:
        print("DISCORD_WEBHOOK_URL is not set. Here is the message:\n")
        print(message)
        sys.exit(1)

    try:
        send_to_discord(webhook_url, message)
        print("Message sent to Discord.")
    except Exception as e:
        # Print the message so it's still visible in the logs.
        print(f"Sending to Discord failed: {e}\n")
        print(message)
        sys.exit(1)  # makes the GitHub Actions run show as failed


if __name__ == "__main__":
    main()
