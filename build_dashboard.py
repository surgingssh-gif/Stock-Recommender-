"""
build_dashboard.py - Builds the data for the dashboard web page.

It reads every pick from picks_log.csv (plus the extra details saved in
data/days/), looks up how each stock has moved since it was picked, works
out the scorecard numbers, and writes everything to docs/data.js.
The web page (docs/index.html) reads that file.

Run it with:  python build_dashboard.py
(GitHub Actions runs it automatically after the daily bot.)
"""

import csv
import json
import math
import os
from datetime import date, datetime, timedelta, timezone

import yfinance as yf

from watchlist import FED_MEETINGS, FUNDS, SECTORS, WATCHLIST

LOG_FILE = "picks_log.csv"
DAYS_DIR = os.path.join("data", "days")
OUTPUT_FILE = os.path.join("docs", "data.js")

# How far back the stock charts go before a stock's first pick.
CHART_LOOKBACK_DAYS = 180

# Only the most recent days keep their full list of headlines on the page,
# so docs/data.js stays small as the months go by.
HEADLINE_DAYS = 10


# --- Reading the saved picks -------------------------------------------------

def read_picks(log_file=LOG_FILE):
    """
    Reads picks_log.csv. If the bot ran more than once on the same day and
    picked the same ticker twice, only the latest row is kept.
    """
    if not os.path.exists(log_file):
        return []
    latest = {}
    with open(log_file, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            latest[(row["date"], row["ticker"])] = {
                "date": row["date"],
                "ticker": row["ticker"],
                "direction": row["direction"],
                "reason": row["reason"],
                "price_at_pick": _number(row.get("price_at_pick")),
            }
    return list(latest.values())


def _number(text):
    """A price from the CSV as a number, or None if it's blank or "nan"."""
    try:
        value = float(text)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def read_days(days_dir=DAYS_DIR):
    """Reads the daily detail files (market mood, confidence, headlines)."""
    days = {}
    if not os.path.isdir(days_dir):
        return days
    for name in sorted(os.listdir(days_dir)):
        if name.endswith(".json"):
            with open(os.path.join(days_dir, name), encoding="utf-8") as f:
                day = json.load(f)
            days[day["date"]] = day
    return days


# --- Prices ------------------------------------------------------------------

def fetch_history(ticker, start_date):
    """
    Returns daily closing prices from about 6 months before start_date up to
    today, as a list of [date, price] pairs, or [] if Yahoo has nothing for
    this ticker. The extra months give the stock charts some context.
    """
    try:
        start = date.fromisoformat(start_date) - timedelta(days=CHART_LOOKBACK_DAYS)
        history = yf.Ticker(ticker).history(start=start.isoformat())
        # Skip blank ("NaN") rows, which Yahoo sometimes returns for today.
        return [
            [index.strftime("%Y-%m-%d"), round(float(close), 2)]
            for index, close in history["Close"].items()
            if math.isfinite(close)
        ]
    except Exception:
        return []


def fetch_earnings_date(ticker):
    """The company's next earnings date as "YYYY-MM-DD", or None if unknown."""
    try:
        dates = yf.Ticker(ticker).calendar.get("Earnings Date") or []
        return min(dates).isoformat() if dates else None
    except Exception:
        return None


# Key facts for each stock's fact sheet (the chart popup). Yahoo's names for them.
FACT_FIELDS = [
    "quoteType", "sector", "industry", "category", "marketCap", "totalAssets",
    "trailingPE", "forwardPE", "fiftyTwoWeekHigh", "fiftyTwoWeekLow", "dividendYield",
    "netExpenseRatio", "beta", "targetMeanPrice", "recommendationKey",
    "numberOfAnalystOpinions", "longBusinessSummary",
]
SUMMARY_LENGTH = 320  # characters of the company description to keep


def fetch_facts(ticker):
    """
    A few key facts about a stock or fund from Yahoo (size, P/E ratio,
    52-week range, dividend, analysts' price target...). Missing ones are
    left out; returns {} if Yahoo has nothing.
    """
    try:
        info = yf.Ticker(ticker).info or {}
    except Exception:
        return {}
    facts = {}
    for key in FACT_FIELDS:
        value = info.get(key)
        if value is None or value == "" or (isinstance(value, float) and not math.isfinite(value)):
            continue
        if key == "longBusinessSummary" and len(value) > SUMMARY_LENGTH:
            value = value[:SUMMARY_LENGTH].rsplit(" ", 1)[0] + "…"
        facts[key] = round(value, 2) if isinstance(value, float) else value
    return facts


# The pretend portfolio starts with this much money.
PORTFOLIO_START = 10_000


def _price_on(history, day, since):
    """The latest close on or before `day` (but not before `since`), or None."""
    price = None
    for d, close in history:
        if d > day:
            break
        if d >= since:
            price = close
    return price


def pretend_portfolio(picks, histories, benchmark="SPY"):
    """
    What $10,000 would be worth if, every day the bot ran, you had split it
    equally across that day's Top 5 buys (bought at the pick price) and held
    them until the next day's Top 5 - compared with simply buying the S&P 500
    fund (SPY) on the same first day. No trading costs or taxes; just a
    rough "is this any good?" check.

    Returns None until there's a Top 5 and some prices after it.
    """
    groups = {}
    for p in picks:
        if p.get("top_rank") and p.get("price_at_pick"):
            groups.setdefault(p["date"], []).append(p)
    spy = histories.get(benchmark) or []
    if not groups or not spy:
        return None
    pick_days = sorted(groups)
    first = pick_days[0]
    spy_start = _price_on(spy, _day_before(first), "0000")
    trading_days = [d for d, _ in spy if d >= first]
    if not trading_days or not spy_start:
        return None

    start_label = _day_before(first)
    series = [[start_label, PORTFOLIO_START, PORTFOLIO_START]]
    value, base, holdings, next_group = PORTFOLIO_START, PORTFOLIO_START, [], 0
    for day in trading_days:
        # A new Top 5 was picked this morning: sell the old ones, buy the new ones.
        while next_group < len(pick_days) and pick_days[next_group] <= day:
            base = value
            holdings = groups[pick_days[next_group]]
            next_group += 1
        ratios = []
        for p in holdings:
            price = _price_on(histories.get(p["ticker"], []), day, p["date"])
            ratios.append(price / p["price_at_pick"] if price else 1.0)
        value = base * sum(ratios) / len(ratios)
        bench = PORTFOLIO_START * _price_on(spy, day, "0000") / spy_start
        series.append([day, round(value, 2), round(bench, 2)])

    return {
        "start": PORTFOLIO_START,
        "series": series,
        "top5_return_pct": round((series[-1][1] / PORTFOLIO_START - 1) * 100, 2) + 0.0,
        "spy_return_pct": round((series[-1][2] / PORTFOLIO_START - 1) * 100, 2) + 0.0,
        "pick_days": len(pick_days),
    }


def _day_before(day):
    return (date.fromisoformat(day) - timedelta(days=1)).isoformat()


# How far ahead the "Coming up" calendar looks.
EVENT_DAYS_AHEAD = 45


def build_events(earnings, names, today):
    """
    The "Coming up" calendar: upcoming earnings dates (from `earnings`,
    ticker -> date) plus Fed meetings, soonest first. `today` is "YYYY-MM-DD".
    """
    end = (date.fromisoformat(today) + timedelta(days=EVENT_DAYS_AHEAD)).isoformat()
    events = [
        {"date": d, "kind": "earnings", "ticker": t, "label": f"{names.get(t) or t} earnings"}
        for t, d in earnings.items()
        if d and today <= d <= end
    ]
    events += [
        {"date": d, "kind": "fed", "ticker": None, "label": "Fed interest-rate decision"}
        for d in FED_MEETINGS
        if today <= d <= end
    ]
    return sorted(events, key=lambda e: (e["date"], e["label"]))


def sector_moves(histories):
    """
    For the sector heat map: each sector fund's move over the last day,
    week (5 trading days), month (21) and 3 months (63), in percent.
    """
    periods = {"1D": 1, "1W": 5, "1M": 21, "3M": 63}
    sectors = []
    for ticker, name in SECTORS.items():
        closes = [c for _, c in histories.get(ticker, [])]
        if len(closes) < 2:
            continue
        changes = {
            label: round((closes[-1] - closes[-1 - n]) / closes[-1 - n] * 100, 2) + 0.0
            if len(closes) > n else None
            for label, n in periods.items()
        }
        sectors.append({"ticker": ticker, "name": name, "changes": changes})
    return sectors


# --- Scorecard math ----------------------------------------------------------

def score_pick(pick, price_now):
    """
    Adds the performance numbers to one pick:
      return_pct              - how much the stock moved since the pick (%)
      directional_return_pct  - the same, but flipped for bearish calls, so
                                positive always means "the call was right"
      correct                 - True/False, or None if we can't tell yet
    """
    pick = dict(pick, price_now=price_now)
    start = pick["price_at_pick"]
    if start and price_now:
        move = (price_now - start) / start * 100
        sign = 1 if pick["direction"] == "bullish" else -1
        # "+ 0.0" turns a rounded -0.0 into a plain 0.0.
        pick["return_pct"] = round(move, 2) + 0.0
        pick["directional_return_pct"] = round(move * sign, 2) + 0.0
        pick["correct"] = (move * sign) > 0 if move != 0 else None
    else:
        pick["return_pct"] = None
        pick["directional_return_pct"] = None
        pick["correct"] = None
    return pick


# How long after the pick each "hold period" score is taken, in trading days.
HORIZONS = [("1 day", 1), ("1 week", 5), ("1 month", 21)]


def horizon_returns(pick, history):
    """
    The move in the direction of the call after 1 day, 1 week and 1 month
    (trading days, counting the pick day's close as day 1). A horizon that
    hasn't been reached yet is None.
    """
    start = pick.get("price_at_pick")
    closes = [c for d, c in history if d >= pick["date"]]
    sign = 1 if pick["direction"] == "bullish" else -1
    return {
        label: round((closes[n - 1] - start) / start * 100 * sign, 2) + 0.0 if start and len(closes) >= n else None
        for label, n in HORIZONS
    }


def level_status(pick, history):
    """
    "target" if the stock closed at or past its target price after the pick,
    "stop" if it closed at or past its "proven wrong" price - whichever
    happened first - else None.
    """
    target, stop = pick.get("target_price"), pick.get("stop_price")
    if not (target and stop):
        return None
    bullish = pick["direction"] == "bullish"
    for d, close in history:
        if d < pick["date"]:
            continue
        if (close >= target) if bullish else (close <= target):
            return "target"
        if (close <= stop) if bullish else (close >= stop):
            return "stop"
    return None


def _group_stats(label, picks):
    return {
        "label": label,
        "count": len(picks),
        "hit_rate": _hit_rate(picks),
        "avg_directional_return": _average([p["directional_return_pct"] for p in picks]),
    }


def by_theme(picks):
    """Hit rate and average move for each news theme (most-used first)."""
    themes = {}
    for p in picks:
        if p.get("theme"):
            themes.setdefault(p["theme"], []).append(p)
    return [_group_stats(t, ps) for t, ps in sorted(themes.items(), key=lambda kv: (-len(kv[1]), kv[0]))]


def by_horizon(picks):
    """For each hold period: how many calls were right and the average move."""
    rows = []
    for label, _ in HORIZONS:
        moves = [p["horizons"][label] for p in picks if p.get("horizons", {}).get(label) is not None]
        rows.append({
            "label": label,
            "count": len(moves),
            "hit_rate": round(len([m for m in moves if m > 0]) / len(moves) * 100, 1) if moves else None,
            "avg_directional_return": _average(moves),
        })
    return rows


def _hit_rate(picks):
    """Share of picks (with a result) whose call has been right so far."""
    judged = [p for p in picks if p["correct"] is not None]
    if not judged:
        return None
    return round(sum(p["correct"] for p in judged) / len(judged) * 100, 1)


def _average(values):
    values = [v for v in values if v is not None]
    return round(sum(values) / len(values), 2) if values else None


def summarize(picks):
    """Builds the scorecard: overall numbers plus breakdowns."""
    scored = [p for p in picks if p["directional_return_pct"] is not None]
    best = max(scored, key=lambda p: p["directional_return_pct"], default=None)
    worst = min(scored, key=lambda p: p["directional_return_pct"], default=None)

    def group(key, values):
        return [
            {
                "label": value,
                "count": len([p for p in picks if p.get(key) == value]),
                "hit_rate": _hit_rate([p for p in picks if p.get(key) == value]),
                "avg_directional_return": _average(
                    [p["directional_return_pct"] for p in picks if p.get(key) == value]
                ),
            }
            for value in values
        ]

    by_day = {}
    for p in picks:
        by_day.setdefault(p["date"], []).append(p)

    return {
        "total_picks": len(picks),
        "days_tracked": len(by_day),
        "hit_rate": _hit_rate(picks),
        "judged": len([p for p in picks if p["correct"] is not None]),
        "correct": len([p for p in picks if p["correct"]]),
        "avg_directional_return": _average([p["directional_return_pct"] for p in picks]),
        "best": _brief(best),
        "worst": _brief(worst),
        "by_direction": group("direction", ["bullish", "bearish"]),
        "by_confidence": group("confidence", ["high", "medium", "low"]),
        "by_day": [
            {
                "date": d,
                "count": len(ps),
                "hit_rate": _hit_rate(ps),
                "avg_directional_return": _average([p["directional_return_pct"] for p in ps]),
            }
            for d, ps in sorted(by_day.items())
        ],
    }


def top_buys_record(picks):
    """
    How the "Top 5 buys" have done: their numbers next to all the other
    picks (only counting days that had a Top 5), plus one row per day.
    """
    top_days = {p["date"] for p in picks if p.get("top_rank")}
    top = [p for p in picks if p.get("top_rank")]
    rest = [p for p in picks if p["date"] in top_days and not p.get("top_rank")]

    def group(label, ps):
        return {
            "label": label,
            "count": len(ps),
            "hit_rate": _hit_rate(ps),
            "avg_directional_return": _average([p["directional_return_pct"] for p in ps]),
        }

    by_day = []
    for d in sorted(top_days, reverse=True):
        ps = sorted((p for p in top if p["date"] == d), key=lambda p: p["top_rank"])
        by_day.append({
            "date": d,
            "hit_rate": _hit_rate(ps),
            "avg_directional_return": _average([p["directional_return_pct"] for p in ps]),
            "buys": [
                {k: p.get(k) for k in ("top_rank", "ticker", "company", "return_pct", "correct")}
                for p in ps
            ],
        })

    return {
        "groups": [group("Top 5 buys", top), group("Other picks", rest)],
        "judged": len([p for p in top if p["correct"] is not None]),
        "by_day": by_day,
    }


def weekly_report(picks):
    """
    One "report card" per week (Monday to Friday), newest first: how many
    ideas, how often they were right, the average move, the best and worst
    call, and how the Top 5 did.
    """
    weeks = {}
    for p in picks:
        monday = date.fromisoformat(p["date"]) - timedelta(days=date.fromisoformat(p["date"]).weekday())
        weeks.setdefault(monday.isoformat(), []).append(p)
    cards = []
    for monday, ps in sorted(weeks.items(), reverse=True):
        scored = [p for p in ps if p["directional_return_pct"] is not None]
        top = [p for p in ps if p.get("top_rank")]
        cards.append({
            "week_start": monday,
            "week_end": (date.fromisoformat(monday) + timedelta(days=4)).isoformat(),
            "days": len({p["date"] for p in ps}),
            "count": len(ps),
            "judged": len([p for p in ps if p["correct"] is not None]),
            "correct": len([p for p in ps if p["correct"]]),
            "hit_rate": _hit_rate(ps),
            "avg_directional_return": _average([p["directional_return_pct"] for p in ps]),
            "best": _brief(max(scored, key=lambda p: p["directional_return_pct"], default=None)),
            "worst": _brief(min(scored, key=lambda p: p["directional_return_pct"], default=None)),
            "top5_count": len(top),
            "top5_hit_rate": _hit_rate(top),
            "top5_avg": _average([p["directional_return_pct"] for p in top]),
        })
    return cards


def latest_run_only(picks, days):
    """
    If the bot ran more than once on the same day, picks_log.csv has rows
    from every run, but data/days/<date>.json only describes the latest one.
    Show just the latest run's picks for that day (in the order Claude gave).
    The CSV itself is never changed, so every pick stays on record.
    """
    kept = []
    for pick in picks:
        day_picks = days.get(pick["date"], {}).get("picks")
        if not day_picks or any(p["ticker"] == pick["ticker"] for p in day_picks):
            kept.append(pick)

    def order(p):
        tickers = [d["ticker"] for d in days.get(p["date"], {}).get("picks", [])]
        return tickers.index(p["ticker"]) if p["ticker"] in tickers else len(tickers)

    return sorted(kept, key=lambda p: (p["date"], order(p)))


# Many news sources send their own logo instead of a real photo. These are
# known logo images, and any image used for several stories on the same day
# is treated as a logo too.
LOGO_URL_HINTS = ("/logo/", "whirlpooldata", "logo.", "_logo", "placeholder")
LOGO_REPEAT_LIMIT = 3


def _real_photos(headlines):
    """Returns the headlines with logo 'photos' removed (image set to "")."""
    counts = {}
    for h in headlines:
        if h.get("image"):
            counts[h["image"]] = counts.get(h["image"], 0) + 1
    cleaned = []
    for h in headlines:
        image = h.get("image") or ""
        is_logo = (
            any(hint in image.lower() for hint in LOGO_URL_HINTS)
            or counts.get(image, 0) >= LOGO_REPEAT_LIMIT
        )
        cleaned.append(dict(h, image="" if is_logo else image))
    return cleaned


def _article_for(sources, headlines):
    """
    Picks the news story to show next to a pick: the first of its source
    headlines that has a real photo, or else simply its first source headline.
    `sources` are headline numbers starting at 1.
    """
    headlines = _real_photos(headlines)
    stories = [headlines[n - 1] for n in sources if isinstance(n, int) and 1 <= n <= len(headlines)]
    if not stories:
        return None
    story = next((h for h in stories if h.get("image")), stories[0])
    return {k: story.get(k, "") for k in ("headline", "source", "url", "image")}


def _with_tickers(day_date, days, picks):
    """The day's headlines, each tagged with the tickers it led to."""
    day = days.get(day_date, {})
    used = {}
    for extra in day.get("picks", []):
        for n in extra.get("sources", []):
            used.setdefault(n, []).append(extra["ticker"])
    headlines = _real_photos(day.get("headlines", []))
    return [dict(h, tickers=used.get(i, [])) for i, h in enumerate(headlines, start=1)]


def _watchlist_cards(days):
    """
    One entry per market-watch stock: its name and the most recent note
    Claude wrote about it (from the newest day that has notes).
    """
    notes, notes_date = {}, None
    for d in sorted(days, reverse=True):
        found = days[d].get("watchlist_notes") or []
        if found:
            notes = {n["ticker"]: n["note"] for n in found}
            notes_date = d
            break
    return [
        {"ticker": t, "name": name, "note": notes.get(t), "note_date": notes_date if t in notes else None}
        for t, name in WATCHLIST.items()
    ]


def _top_buys(latest_date, days, enriched):
    """
    The latest day's "Top 5 buys", best first. Each one gets the price
    numbers from its matching pick (every top buy is also saved as a pick).
    """
    day = days.get(latest_date, {})
    cards = []
    for rank, buy in enumerate(day.get("top_buys") or [], start=1):
        pick = next((p for p in enriched if p["date"] == latest_date and p["ticker"] == buy["ticker"]), {})
        cards.append(dict(
            buy,
            rank=rank,
            date=latest_date,
            article=_article_for(buy.get("sources", []), day.get("headlines", [])),
            **{k: pick.get(k) for k in ("price_at_pick", "price_now", "return_pct", "correct", "history",
                                         "target_price", "stop_price", "target_pct", "stop_pct", "level_status")},
        ))
    return cards


def _brief(pick):
    if not pick:
        return None
    return {k: pick[k] for k in ("date", "ticker", "direction", "directional_return_pct")}


# --- Putting it together -----------------------------------------------------

def build_data(picks, days, histories, events=None, facts=None):
    """
    Combines picks, daily details and price histories into the one object
    the web page needs. Kept separate from the network calls so it can be
    tested with fake data.
    """
    picks = latest_run_only(picks, days)
    enriched = []
    for pick in picks:
        # Add company name + confidence from that day's detail file, if saved.
        day = days.get(pick["date"], {})
        extra = next((p for p in day.get("picks", []) if p["ticker"] == pick["ticker"]), {})
        history = histories.get(pick["ticker"], [])
        # Only score a pick against prices from its own day or later. (If
        # Yahoo is missing recent days, older prices would give fake results.)
        since_pick = [h for h in history if h[0] >= pick["date"]]
        price_now = since_pick[-1][1] if since_pick else None
        if pick["price_at_pick"] is None:
            # No price was logged: use that day's closing price, if known.
            pick = dict(pick, price_at_pick=next((c for d, c in history if d == pick["date"]), None))
        top_tickers = [b["ticker"] for b in day.get("top_buys") or []]
        full = dict(
            pick,
            company=extra.get("company"),
            # 1-5 if this was one of the day's "Top 5 buys", otherwise None.
            top_rank=top_tickers.index(pick["ticker"]) + 1 if pick["ticker"] in top_tickers else None,
            confidence=extra.get("confidence"),
            # What kind of news drove it, and its price levels (newer picks only).
            theme=extra.get("theme"),
            target_price=extra.get("target_price"),
            stop_price=extra.get("stop_price"),
            target_pct=extra.get("target_pct"),
            stop_pct=extra.get("stop_pct"),
            # The news story this idea came from (with its photo, if any).
            article=_article_for(extra.get("sources", []), day.get("headlines", [])),
            # Only the part of the price history from the pick date onwards.
            history=[h for h in history if h[0] >= pick["date"]] or history[-1:],
        )
        full["horizons"] = horizon_returns(full, history)
        full["level_status"] = level_status(full, history)
        enriched.append(score_pick(full, price_now))

    # Newest first, and within a day keep the order Claude gave.
    enriched.sort(key=lambda p: p["date"], reverse=True)

    all_dates = sorted({p["date"] for p in enriched} | set(days), reverse=True)
    recent = set(all_dates[:HEADLINE_DAYS])
    day_list = [
        {
            "date": d,
            "market_mood": days.get(d, {}).get("market_mood"),
            "self_check": days.get(d, {}).get("self_check"),
            "summary": days.get(d, {}).get("summary"),
            "headlines": _with_tickers(d, days, enriched) if d in recent else [],
            "headline_count": len(days.get(d, {}).get("headlines", [])),
            "tickers": [p["ticker"] for p in enriched if p["date"] == d],
        }
        for d in all_dates
    ]

    stats = summarize(enriched)
    stats["top_buys"] = top_buys_record(enriched)
    stats["weeks"] = weekly_report(enriched)
    stats["by_theme"] = by_theme(enriched)
    stats["by_horizon"] = by_horizon(enriched)

    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "stats": stats,
        "picks": enriched,
        "days": day_list,
        # Full price history per ticker, for the stock charts (not the sector funds,
        # which only need the numbers in "sectors").
        "charts": {t: h for t, h in sorted(histories.items()) if h and t not in SECTORS},
        # The sector heat map.
        "sectors": sector_moves(histories),
        # The "Coming up" calendar (earnings dates and Fed meetings).
        "events": events or [],
        # Key facts per ticker, for the fact sheet in the chart popup.
        "facts": facts or {},
        # The pretend $10,000 portfolio that follows the Top 5.
        "portfolio": pretend_portfolio(enriched, histories),
        # The "market watch" stocks, with the latest note Claude wrote for each.
        "watchlist": _watchlist_cards(days),
        # Today's "Top 5 buys", with the longer "why" for each.
        "top_buys": _top_buys(all_dates[0], days, enriched) if all_dates else [],
    }


def main():
    days = read_days()
    picks = latest_run_only(read_picks(), days)

    # One price lookup per ticker, starting from its earliest pick.
    first_seen = {}
    for p in picks:
        first_seen[p["ticker"]] = min(p["date"], first_seen.get(p["ticker"], p["date"]))
    # Market-watch stocks and sector funds get the same ~6 months of history, counted from today.
    for t in list(WATCHLIST) + list(SECTORS):
        first_seen.setdefault(t, date.today().isoformat())
    histories = {t: fetch_history(t, d) for t, d in first_seen.items()}
    missing = [t for t, h in histories.items() if not h]
    if missing:
        print(f"No price history for: {', '.join(missing)}")

    # Upcoming earnings for the companies on the page (the last 10 days' picks
    # plus the market-watch list). Funds don't have earnings, so skip them.
    recent = sorted({p["date"] for p in picks}, reverse=True)[:HEADLINE_DAYS]
    names = {d["ticker"]: d.get("company") for day in days.values() for d in day.get("picks", [])}
    names.update(WATCHLIST)
    companies = {p["ticker"] for p in picks if p["date"] in recent} | set(WATCHLIST)
    earnings = {t: fetch_earnings_date(t) for t in sorted(companies - FUNDS)}
    events = build_events(earnings, names, date.today().isoformat())

    # Fact sheets for every stock that has a chart on the page.
    facts = {t: fetch_facts(t) for t in sorted(companies | {p["ticker"] for p in picks})}

    data = build_data(picks, days, histories, events, {t: f for t, f in facts.items() if f})

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        # Saved as a small JavaScript file (not plain JSON) so the page also
        # works when you open docs/index.html straight from your computer.
        f.write("window.DASHBOARD_DATA = ")
        # allow_nan=False: fail loudly rather than put "NaN" on the page.
        json.dump(data, f, indent=1, allow_nan=False)
        f.write(";\n")
    print(f"Dashboard data written: {data['stats']['total_picks']} picks over {data['stats']['days_tracked']} day(s).")


if __name__ == "__main__":
    main()
