"""
track_record.py - Tells Claude how its recent calls have actually done,
so each morning it can learn from what worked and what didn't.

It reads the scored picks from the dashboard data (docs/data.js), which the
evening recap refreshes with closing prices, so no extra price lookups are
needed. This file only reads; it never changes anything.
"""

import json
import os

DASHBOARD_DATA = os.path.join("docs", "data.js")

# How many of the most recent scored calls to list one by one.
MAX_CALLS = 25


def load_dashboard_data(path=DASHBOARD_DATA):
    """The dashboard data as a dict, or None if it's missing or unreadable."""
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
        return json.loads(text[text.index("{"): text.rindex("}") + 1])
    except (OSError, ValueError):
        return None


def _rate(calls):
    right = len([p for p in calls if p["correct"]])
    return f"{right} of {len(calls)} right ({round(right / len(calls) * 100)}%)"


def build_track_record(data, max_calls=MAX_CALLS):
    """
    A short plain-text summary of how the bot's calls have done, or None
    if nothing has a result yet. Example:

        Overall: 9 of 14 right (64%), average move for the call +0.85%.
        Bullish: 6 of 9 right (67%). Bearish: 3 of 5 right (60%).
        ...
        2026-09-22 CPRI bullish, high confidence, Top 5 #1: +8.94% (right)
    """
    if not data:
        return None
    judged = [p for p in data.get("picks", []) if p.get("correct") is not None]
    if not judged:
        return None

    lines = []
    avg = sum(p["directional_return_pct"] for p in judged) / len(judged)
    lines.append(f"Overall: {_rate(judged)}, average move for the call {avg:+.2f}%.")

    groups = []
    for label, key, value in [
        ("Bullish", "direction", "bullish"), ("Bearish", "direction", "bearish"),
        ("High confidence", "confidence", "high"), ("Medium confidence", "confidence", "medium"),
        ("Low confidence", "confidence", "low"),
    ]:
        subset = [p for p in judged if p.get(key) == value]
        if subset:
            groups.append(f"{label}: {_rate(subset)}")
    top = [p for p in judged if p.get("top_rank")]
    if top:
        groups.append(f"Top 5 ideas: {_rate(top)}")
    lines.append(". ".join(groups) + ".")

    # Compared with simply buying the S&P 500 over the same time.
    market = (data.get("stats") or {}).get("vs_market") or {}
    if market.get("judged"):
        lines.append(
            f"Against the market: {market['beat']} of {market['judged']} calls beat the S&P 500 "
            f"({market['rate']:.0f}%), by {market['avg_vs_market']:+.2f}% on average."
        )

    # By news theme (only themes with a few results, so one call isn't a "pattern").
    themes = {}
    for p in judged:
        if p.get("theme"):
            themes.setdefault(p["theme"], []).append(p)
    theme_lines = [f"{t}: {_rate(ps)}" for t, ps in sorted(themes.items()) if len(ps) >= 3]
    if theme_lines:
        lines.append("By theme: " + ". ".join(theme_lines) + ".")

    # How the calls do the longer they're held.
    horizons = [h for h in (data.get("stats") or {}).get("by_horizon", []) if h.get("count")]
    if horizons:
        lines.append("By hold period: " + ", ".join(
            f"after {h['label']} {h['hit_rate']:.0f}% right, average {h['avg_directional_return']:+.2f}% ({h['count']} calls)"
            for h in horizons) + ".")

    # Targets and "proven wrong" prices that were reached.
    hits = [p for p in judged if p.get("level_status")]
    if hits:
        reached = len([p for p in hits if p["level_status"] == "target"])
        lines.append(f"Price levels: {reached} target(s) reached and {len(hits) - reached} 'proven wrong' price(s) hit.")

    lines.append("Most recent calls (move from the opening price after the pick, in the direction of the call):")
    for p in judged[:max_calls]:  # the dashboard lists the newest first
        tags = [p["direction"]]
        if p.get("confidence"):
            tags.append(f"{p['confidence']} confidence")
        if p.get("top_rank"):
            tags.append(f"Top 5 #{p['top_rank']}")
        if p.get("theme"):
            tags.append(p["theme"])
        verdict = "right" if p["correct"] else "wrong"
        vs = f", {p['vs_market_pct']:+.2f}% vs the S&P 500" if p.get("vs_market_pct") is not None else ""
        lines.append(f"{p['date']} {p['ticker']} {', '.join(tags)}: {p['directional_return_pct']:+.2f}% ({verdict}{vs})")
    return "\n".join(lines)


# How many of the bot's recent run-days to list, so it can avoid repeating itself.
RECENT_DAYS = 3


def recent_picks_text(picks, days=RECENT_DAYS):
    """
    "2026-09-29: XOM bullish, TLT bearish, ..." for the last few days the bot
    ran (from picks_log.csv rows), newest first, or None if there are none.
    """
    by_day = {}
    for p in picks:
        by_day.setdefault(p["date"], []).append(p)
    lines = []
    for day in sorted(by_day, reverse=True)[:days]:
        lines.append(f"{day}: " + ", ".join(f"{p['ticker']} {p['direction']}" for p in by_day[day]))
    return "\n".join(lines) or None


def recent_tickers(picks, before, days=RECENT_DAYS):
    """Tickers picked on the last `days` run-days before the date `before` (YYYY-MM-DD)."""
    dates = sorted({p["date"] for p in picks if p["date"] < before}, reverse=True)[:days]
    return sorted({p["ticker"] for p in picks if p["date"] in dates})
