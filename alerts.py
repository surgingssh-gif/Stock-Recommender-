"""
alerts.py - Big-move alerts. Runs every hour while the US market is open and
pings Discord when one of the bot's recent picks has moved 5% or more since
it was picked. It pings again only if the move keeps growing (10%, 15%, ...),
so you don't get the same alert every hour.

Run it with:
    python alerts.py            (only does anything while the market is open)
    python alerts.py --dry-run  (prints alerts instead of sending them)
    python alerts.py --force    (checks even when the market is closed)

It only reads picks_log.csv. What it has already alerted on is remembered
in data/alerts.json.
"""

import json
import math
import os
import sys
from datetime import datetime, time
from zoneinfo import ZoneInfo

import yfinance as yf
from dotenv import load_dotenv

from build_dashboard import latest_run_only, read_days, read_picks
from discord_notify import DISCLAIMER, send_to_discord
from main import dashboard_url

ALERT_STEP = 5.0         # alert at every 5% of movement since the pick
RECENT_PICK_DAYS = 5     # watch the picks from the last 5 days the bot ran
STATE_FILE = os.path.join("data", "alerts.json")
NEW_YORK = ZoneInfo("America/New_York")


def market_is_open(now):
    """Weekdays, 9:30 AM - 4:00 PM New York time. (Holidays just find no new prices.)"""
    return now.weekday() < 5 and time(9, 30) <= now.time() <= time(16, 0)


def get_live_price(ticker):
    """The latest trading price, or None if Yahoo doesn't have one."""
    try:
        price = float(yf.Ticker(ticker).fast_info["lastPrice"])
        return round(price, 2) if math.isfinite(price) and price > 0 else None
    except Exception:
        return None


def load_state(path=STATE_FILE):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_state(state, path=STATE_FILE):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, sort_keys=True)


def find_alerts(picks, prices, state):
    """
    Returns (alerts, new_state). An alert is a pick whose move since the pick
    has reached a new 5% step (or flipped direction) since the last alert.
    """
    alerts, new_state = [], dict(state)
    for p in picks:
        start, now = p.get("price_at_pick"), prices.get(p["ticker"])
        if not (start and now):
            continue
        move = (now - start) / start * 100
        level = int(abs(move) // ALERT_STEP)
        if level == 0:
            continue
        key = f"{p['date']}:{p['ticker']}"
        sign = 1 if move > 0 else -1
        last = state.get(key)
        if last and last["sign"] == sign and last["level"] >= level:
            continue  # already alerted at this size of move
        new_state[key] = {"level": level, "sign": sign}
        sign_of_call = 1 if p["direction"] == "bullish" else -1
        alerts.append(dict(p, price_now=now, move=move, working=move * sign_of_call > 0))
    return alerts, new_state


def build_alert_message(alerts, dashboard=None):
    lines = ["**🚨 Big move alert**", ""]
    for a in sorted(alerts, key=lambda a: abs(a["move"]), reverse=True):
        arrow = "▲" if a["direction"] == "bullish" else "▼"
        verdict = "✅ with the call" if a["working"] else "❌ against the call"
        rank = f", Top 5 #{a['top_rank']}" if a.get("top_rank") else ""
        lines.append(
            f"{arrow} **{a['ticker']}** {a['move']:+.2f}% since the pick - {verdict}\n"
            f"> {a['direction'].capitalize()} call{rank} on {a['date']} at ${a['price_at_pick']:,.2f}, now ${a['price_now']:,.2f}"
        )
    lines.append("")
    if dashboard:
        lines.append(f"📰 Charts and details: {dashboard}")
        lines.append("")
    lines.append(f"_{DISCLAIMER}_")
    return "\n".join(lines)


def main():
    dry_run = "--dry-run" in sys.argv
    load_dotenv()
    now = datetime.now(NEW_YORK)
    if not market_is_open(now) and "--force" not in sys.argv:
        print("The market is closed, so there's nothing to check.")
        return

    days = read_days()
    picks = latest_run_only(read_picks(), days)
    recent_days = sorted({p["date"] for p in picks}, reverse=True)[:RECENT_PICK_DAYS]
    picks = [p for p in picks if p["date"] in recent_days]
    # Mark Top 5 buys, so the alert can say so.
    for p in picks:
        top = [b["ticker"] for b in days.get(p["date"], {}).get("top_buys") or []]
        p["top_rank"] = top.index(p["ticker"]) + 1 if p["ticker"] in top else None

    prices = {t: get_live_price(t) for t in sorted({p["ticker"] for p in picks})}
    alerts, new_state = find_alerts(picks, prices, load_state())
    if not alerts:
        print(f"Checked {len(prices)} stocks; no new big moves.")
        return

    message = build_alert_message(alerts, dashboard_url())
    webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
    if dry_run or not webhook_url:
        print(message)
        if not dry_run:
            print("DISCORD_WEBHOOK_URL is not set, so the alert was only printed.")
            sys.exit(1)
        return
    send_to_discord(webhook_url, message)
    # Only remember alerts that were actually sent.
    save_state(new_state)
    print(f"Sent {len(alerts)} alert(s) to Discord.")


if __name__ == "__main__":
    main()
