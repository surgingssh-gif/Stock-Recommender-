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
        groups.append(f"Top 5 buys: {_rate(top)}")
    lines.append(". ".join(groups) + ".")

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

    lines.append("Most recent calls (move since the pick, in the direction of the call):")
    for p in judged[:max_calls]:  # the dashboard lists the newest first
        tags = [p["direction"]]
        if p.get("confidence"):
            tags.append(f"{p['confidence']} confidence")
        if p.get("top_rank"):
            tags.append(f"Top 5 #{p['top_rank']}")
        if p.get("theme"):
            tags.append(p["theme"])
        verdict = "right" if p["correct"] else "wrong"
        lines.append(f"{p['date']} {p['ticker']} {', '.join(tags)}: {p['directional_return_pct']:+.2f}% ({verdict})")
    return "\n".join(lines)
