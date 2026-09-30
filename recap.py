"""
recap.py - The evening recap. Runs after the US market closes and posts a
short Discord message on how the morning's picks actually moved.
On Fridays it adds a "week in review" report card.

Run it with:
    python recap.py            (posts to Discord)
    python recap.py --dry-run  (prints the message instead)
    python recap.py --date 2026-09-22  (recap an earlier day)

It only reads picks_log.csv and prices; it never changes the log.
"""

import os
import sys
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import yfinance as yf
from dotenv import load_dotenv

from build_dashboard import entry_date, latest_run_only, read_days, read_picks
from discord_notify import DISCLAIMER, send_to_discord
from main import dashboard_url


def get_sessions(ticker):
    """The last ~10 trading days as [(date, open, close), ...], or [] if Yahoo has nothing."""
    try:
        history = yf.Ticker(ticker).history(period="10d")
        return [
            (index.strftime("%Y-%m-%d"), round(float(row["Open"]), 2), round(float(row["Close"]), 2))
            for index, row in history.iterrows()
            if row["Open"] == row["Open"] and row["Close"] == row["Close"]  # skip blank (NaN) rows
        ]
    except Exception:
        return []


def open_and_close(sessions, start_day):
    """
    (opening price on the first session on or after start_day, latest close
    since then), or (None, None). The open is what you could actually have
    bought at, since the bot picks before the market opens.
    """
    later = [s for s in sessions if s[0] >= start_day]
    if not later:
        return None, None
    return later[0][1], later[-1][2]


def score(pick, close, entry=None, market_move=None):
    """
    Adds "move" (percent in the direction of the call, so positive = the call
    worked), "raw_move" (plain percent) and "vs_market" (how much better the
    call did than the same bet on the S&P 500) to a pick. Measured from
    `entry` (the opening price) when given, else from the logged pick price.
    """
    start = entry or pick["price_at_pick"]
    if not (start and close):
        return dict(pick, entry=start, close=close, move=None, raw_move=None, vs_market=None)
    raw = (close - start) / start * 100
    sign = 1 if pick["direction"] == "bullish" else -1
    vs = (raw - market_move) * sign if market_move is not None else None
    return dict(pick, entry=start, close=close, move=raw * sign, raw_move=raw, vs_market=vs)


def _line(p, rank=None):
    """One pick as a line, e.g. '#1 ✅ ▲ CPRI +2.10% ($14.31 → $14.61)'."""
    arrow = "▲" if p["direction"] == "bullish" else "▼"
    prefix = f"#{rank} " if rank else ""
    if p["move"] is None:
        return f"{prefix}⏳ {arrow} **{p['ticker']}** - no closing price yet"
    mark = "✅" if p["move"] > 0 else "❌" if p["move"] < 0 else "➖"
    return (
        f"{prefix}{mark} {arrow} **{p['ticker']}** {p['raw_move']:+.2f}% "
        f"(${p['entry']:,.2f} → ${p['close']:,.2f})"
    )


def _summary(scored):
    """'3 of 5 calls worked · average +0.84% for the calls'."""
    judged = [p for p in scored if p["move"] is not None]
    if not judged:
        return "No closing prices yet, so nothing to score."
    right = len([p for p in judged if p["move"] > 0])
    avg = sum(p["move"] for p in judged) / len(judged)
    text = f"{right} of {len(judged)} calls worked · average {avg:+.2f}% for the calls"
    vs = [p for p in judged if p.get("vs_market") is not None]
    if vs:
        text += f" · {len([p for p in vs if p['vs_market'] > 0])} of {len(vs)} beat the S&P 500"
    return text


def build_recap(date_str, today_picks, top_tickers, week_picks=None, dashboard=None):
    """
    Builds the evening message.
    today_picks  - today's picks, already scored (see score())
    top_tickers  - today's Top 5, best first
    week_picks   - this week's picks, scored, on Fridays (else None)
    """
    lines = [f"**🌆 Evening Recap - {date_str}**", ""]
    if not today_picks:
        lines.append("No picks today, so nothing to recap.")
        lines.append("")
    else:
        lines.append(f"*{_summary(today_picks)}*")
        lines.append("")
        by_ticker = {p["ticker"]: p for p in today_picks}
        top = [by_ticker[t] for t in top_tickers if t in by_ticker]
        if top:
            lines.append("**🏆 Top ideas**")
            lines += [_line(p, rank) for rank, p in enumerate(top, start=1)]
            lines.append("")
        others = [p for p in today_picks if p["ticker"] not in top_tickers]
        if others:
            if top:
                lines.append("**Other ideas**")
            lines += [_line(p) for p in others]
            lines.append("")

    if week_picks:
        judged = [p for p in week_picks if p["move"] is not None]
        lines.append("**📅 Week in review**")
        n_days = len({p["date"] for p in week_picks})
        lines.append(f"{len(week_picks)} ideas over {n_days} day{'s' if n_days != 1 else ''} · {_summary(week_picks)}")
        top = [p for p in week_picks if p.get("top")]
        if top:
            lines.append(f"Top 5 ideas: {_summary(top)}")
        if judged:
            best = max(judged, key=lambda p: p["move"])
            worst = min(judged, key=lambda p: p["move"])
            lines.append(f"Best call: **{best['ticker']}** {best['move']:+.2f}% ({best['direction']}, {best['date']})")
            lines.append(f"Worst call: **{worst['ticker']}** {worst['move']:+.2f}% ({worst['direction']}, {worst['date']})")
        lines.append("")

    if dashboard:
        lines.append(f"📰 Full scorecard: {dashboard}")
        lines.append("")
    lines.append(f"_{DISCLAIMER}_")
    return "\n".join(lines)


def main():
    dry_run = "--dry-run" in sys.argv
    load_dotenv()
    webhook_url = os.getenv("DISCORD_WEBHOOK_URL")

    today = datetime.now(ZoneInfo("America/New_York")).date()
    # An earlier day can be chosen with --date or the RECAP_DATE setting.
    chosen = os.getenv("RECAP_DATE")
    if "--date" in sys.argv:
        chosen = sys.argv[sys.argv.index("--date") + 1]
    if chosen:
        today = date.fromisoformat(chosen.strip())
    date_str = today.isoformat()
    days = read_days()
    picks = latest_run_only(read_picks(), days)

    todays = [p for p in picks if p["date"] == date_str]
    top_tickers = [b["ticker"] for b in days.get(date_str, {}).get("top_buys") or []]

    # On Fridays, recap the whole week (Monday to today).
    week = None
    if today.weekday() == 4:
        monday = (today - timedelta(days=4)).isoformat()
        week = [p for p in picks if monday <= p["date"] <= date_str] or None

    if not todays and not week:
        print(f"No picks for {date_str}; no recap to send.")
        return

    # One price lookup per ticker (plus SPY, the S&P 500, to compare with).
    tickers = {p["ticker"] for p in (week or todays)} | {"SPY"}
    sessions = {t: get_sessions(t) for t in sorted(tickers)}
    if not any(s[0] >= date_str for rows in sessions.values() for s in rows):
        # Market holiday, or Yahoo hasn't got today's prices yet.
        print(f"No prices for {date_str} (market closed?); no recap sent.")
        return

    def scored(p):
        # Bought at the first opening bell after the pick; compared with the
        # S&P 500 bought at that same open.
        start_day = entry_date(p["date"], days.get(p["date"], {}).get("picked_at"))
        entry, close = open_and_close(sessions.get(p["ticker"], []), start_day)
        spy_open, spy_close = open_and_close(sessions["SPY"], start_day)
        market = (spy_close - spy_open) / spy_open * 100 if spy_open and spy_close else None
        return score(p, close, entry, market)

    def top_of(p):
        day_top = [b["ticker"] for b in days.get(p["date"], {}).get("top_buys") or []]
        return p["ticker"] in day_top

    scored_today = [scored(p) for p in todays]
    scored_week = [dict(scored(p), top=top_of(p)) for p in week] if week else None

    message = build_recap(date_str, scored_today, top_tickers, scored_week, dashboard_url())
    if dry_run or not webhook_url:
        print(message)
        if not dry_run:
            print("DISCORD_WEBHOOK_URL is not set, so the recap was only printed.")
            sys.exit(1)
        return
    send_to_discord(webhook_url, message)
    print("Evening recap sent to Discord.")


if __name__ == "__main__":
    main()
