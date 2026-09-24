"""
analyzer.py - Sends all of today's headlines to Claude in ONE request
and gets back a short list of stock ideas.

We ask Claude to reply in a strict JSON format (a "schema"), so we don't
have to guess how to read its answer - the API guarantees the shape.
"""

import json
import os

import anthropic

# Which Claude model to use. You can override it with CLAUDE_MODEL in your
# .env file or GitHub Secrets (for example "claude-sonnet-5" is cheaper).
DEFAULT_MODEL = "claude-opus-5"

# Instructions that tell Claude what its job is.
SYSTEM_PROMPT = """You are a market research assistant. Each weekday morning you \
read the latest world and business headlines and point out a few stocks that \
could be affected, so a person can research them further. You never give \
financial advice and nothing you say is an instruction to trade.

Focus on events that tend to move markets: trade deals and tariffs, oil and \
commodity prices, interest rates and central banks, AI and tech news, earnings \
and guidance, regulation and lawsuits, mergers, and geopolitical conflicts.

Guidelines:
- Pick 3 to 6 ideas. Fewer, well-reasoned ideas beat many weak ones. If the \
news is quiet, it is fine to return fewer.
- Only use tickers listed on major US exchanges (NYSE/NASDAQ), including \
ETFs when a whole sector is affected. Use the plain ticker symbol, e.g. "XOM".
- "bullish" means the news could push the price up; "bearish" means down.
- Base every idea on the headlines provided. Mention which news drives it, \
and keep each reason to one or two plain-English sentences a beginner can follow.
- In "sources", list the numbers of the headlines each idea is based on, \
most important first.
- Include both obvious and second-order effects when they are well supported \
(e.g. an oil spike hurting airlines).
- You'll also get a "market watch" list of tickers. For each one, write a \
single short, plain-English sentence in "watchlist_notes" about what today's \
headlines mean for it. If none of the headlines are relevant to it, say \
"No major news today." rather than guessing.
- Finally, choose today's 5 most promising bullish ideas as "top_buys", \
ranked best first. They can repeat tickers from "picks" (never one you called \
bearish) or add new ones, but each must be backed by today's headlines. For \
each, give a one-line "pitch", then explain in plain English "why" it could be \
a good buy (2 to 4 sentences), what "risks" could make it go wrong (1 or 2 \
sentences), and what to "watch" next, like an earnings date or a decision \
(1 sentence). Be honest about the downside: these are research candidates, \
not recommendations. If the news is too quiet for 5 solid ideas, return fewer.
- Some headlines are marked "(about TICKER)": those were fetched for that \
company specifically. You may also get a "Market data" section listing the \
biggest movers and pre-market moves. Use it to see what the market is already \
reacting to, but base each idea on the news behind a move, not the move alone, \
and be wary of chasing a stock that has already jumped.
- You may also get "Your track record": how your recent calls have done, \
measured from the price when each was picked. Use it to calibrate: notice \
which kinds of calls have worked or failed (direction, confidence, sectors, \
chasing news that was already priced in) and adjust. A few days of results \
are mostly noise, so don't overreact to one call or avoid a stock just \
because it lost. In "self_check", write one or two plain-English sentences \
on what your record suggests and how it shaped today's picks. With no track \
record yet, write: Not enough results yet to learn from.
- For every pick and top buy, set two price levels as percent moves from \
today's price: "target_pct" is how far the stock could realistically move in \
the direction of your call over the next few weeks (e.g. 8 means +8% for a \
bullish call, -8% for a bearish one), and "stop_pct" is how far it would have \
to move against your call for the idea to be proven wrong (e.g. 5). Use \
positive numbers for both. Base them on how much the stock usually moves and \
how big the news is: a sleepy utility and a volatile small-cap need \
different levels.
- Tag every pick and top buy with the one "theme" that best describes the \
news driving it.
- Finally, write a 60-second "summary" for someone in a hurry: the day's \
"big_story" in one sentence, the "top_pick" (your #1 idea and why, in one \
sentence), and what to "watch" today (one sentence)."""

# What drove each idea. Used on the dashboard to show which kinds of news the
# bot reads well (and in its track record, so it can learn from that too).
THEMES = [
    "Oil & energy", "AI & tech", "Mergers & deals", "Interest rates & the Fed",
    "Earnings & guidance", "Trade & tariffs", "Regulation & legal",
    "Geopolitics", "Consumer & retail", "Health & biotech", "Other",
]

# Fields every idea (pick or top buy) carries: its theme and price levels.
IDEA_FIELDS = {
    "theme": {"type": "string", "enum": THEMES},
    "target_pct": {"type": "number"},
    "stop_pct": {"type": "number"},
}

# The exact JSON shape we want back from Claude.
OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "market_mood": {
            "type": "string",
            "description": "One or two sentences on the overall theme of today's news.",
        },
        # One short note per "market watch" ticker (see watchlist.py).
        "watchlist_notes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "ticker": {"type": "string"},
                    "note": {"type": "string"},
                },
                "required": ["ticker", "note"],
                "additionalProperties": False,
            },
        },
        "picks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "ticker": {"type": "string"},
                    "company": {"type": "string"},
                    "direction": {"type": "string", "enum": ["bullish", "bearish"]},
                    "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
                    "reason": {"type": "string"},
                    # Numbers of the headlines this idea came from (1 = first
                    # headline in the list). The dashboard uses them to show
                    # the right article and photo next to each pick.
                    "sources": {"type": "array", "items": {"type": "integer"}},
                    **IDEA_FIELDS,
                },
                "required": ["ticker", "company", "direction", "confidence", "reason", "sources", *IDEA_FIELDS],
                "additionalProperties": False,
            },
        },
        # The "In 60 seconds" box at the top of the Today tab.
        "summary": {
            "type": "object",
            "properties": {
                "big_story": {"type": "string"},
                "top_pick": {"type": "string"},
                "watch": {"type": "string"},
            },
            "required": ["big_story", "top_pick", "watch"],
            "additionalProperties": False,
        },
        # What Claude learned from its own track record, and how it adjusted.
        "self_check": {
            "type": "string",
            "description": "One or two sentences on what the recent track record suggests and how it shaped today's picks.",
        },
        # The "Top 5 buys of the day": the most promising bullish ideas,
        # ranked best first, with a longer explanation for each.
        "top_buys": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "ticker": {"type": "string"},
                    "company": {"type": "string"},
                    "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
                    "pitch": {"type": "string"},
                    "why": {"type": "string"},
                    "risks": {"type": "string"},
                    "watch": {"type": "string"},
                    "sources": {"type": "array", "items": {"type": "integer"}},
                    **IDEA_FIELDS,
                },
                "required": ["ticker", "company", "confidence", "pitch", "why", "risks", "watch", "sources", *IDEA_FIELDS],
                "additionalProperties": False,
            },
        },
    },
    "required": ["market_mood", "picks", "watchlist_notes", "top_buys", "self_check", "summary"],
    "additionalProperties": False,
}


def _format_headlines(headlines):
    """Turn the list of headline dicts into one numbered block of text."""
    lines = []
    for i, h in enumerate(headlines, start=1):
        about = f" (about {h['about']})" if h.get("about") else ""
        line = f"{i}. [{h['time']}] ({h['source']}){about} {h['headline']}"
        if h["summary"]:
            line += f"\n   {h['summary']}"
        lines.append(line)
    return "\n".join(lines)


def analyze_headlines(headlines, api_key, watchlist=None, track_record=None, market_data=None):
    """
    Returns a dict: {"market_mood": "...", "picks": [ {ticker, company,
    direction, confidence, reason, sources}, ... ]}
    where "sources" are the numbers (starting at 1) of the headlines used,
    plus "watchlist_notes": [ {ticker, note}, ... ] for the watchlist tickers,
    plus "top_buys": up to 5 ranked bullish ideas {ticker, company,
    confidence, pitch, why, risks, watch, sources}. Every top buy is also
    in "picks". Also "self_check": what Claude took from its track record.

    track_record - text from track_record.build_track_record() (optional)
    market_data  - text from market_data.format_market_data() (optional)

    Raises an exception if Claude can't be reached or declines to answer,
    so the caller can report it.
    """
    client = anthropic.Anthropic(api_key=api_key)
    model = os.getenv("CLAUDE_MODEL") or DEFAULT_MODEL

    user_message = (
        "Here are the latest headlines. Suggest stock ideas based on them.\n\n"
        + _format_headlines(headlines)
    )
    if watchlist:
        user_message += (
            "\n\nMarket watch tickers (write one note for each): "
            + ", ".join(f"{t} ({name})" for t, name in watchlist.items())
        )
    if market_data:
        user_message += "\n\nMarket data (prices, not news):\n" + market_data
    user_message += "\n\nYour track record:\n" + (track_record or "No results yet - this is one of the first runs.")

    response = client.beta.messages.create(
        model=model,
        max_tokens=16000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
        # "medium" effort keeps costs down while still reasoning carefully.
        output_config={
            "effort": "medium",
            "format": {"type": "json_schema", "schema": OUTPUT_SCHEMA},
        },
        # If Claude's safety filter ever declines the request, the API
        # automatically retries on a recommended backup model instead of
        # failing. (This needs the "betas" flag below.)
        fallbacks="default",
        betas=["server-side-fallback-2026-07-01"],
    )

    if response.stop_reason == "refusal":
        raise RuntimeError("Claude declined to analyze today's headlines.")
    if response.stop_reason == "max_tokens":
        raise RuntimeError("Claude's answer was cut off (hit max_tokens).")

    # With a JSON schema, the answer is a text block containing valid JSON.
    text = next(block.text for block in response.content if block.type == "text")
    result = json.loads(text)

    # Clean up ticker symbols (e.g. " xom" -> "XOM").
    for item in result["picks"] + result.get("watchlist_notes", []) + result.get("top_buys", []):
        item["ticker"] = item["ticker"].strip().upper().lstrip("$")

    return add_top_buys_to_picks(result)


TOP_BUYS_COUNT = 5


def add_top_buys_to_picks(result):
    """
    Makes sure every top buy is also in the normal list of picks, so it gets
    a price, is saved to picks_log.csv and is tracked on the scorecard like
    any other idea. Also keeps at most 5 top buys and drops any that clash
    with a bearish pick for the same stock.
    """
    by_ticker = {p["ticker"]: p for p in result["picks"]}
    top_buys = []
    for buy in result.get("top_buys", []):
        pick = by_ticker.get(buy["ticker"])
        if pick and pick["direction"] == "bearish":
            continue  # Claude contradicted itself; skip this one
        if any(b["ticker"] == buy["ticker"] for b in top_buys):
            continue  # listed twice
        top_buys.append(buy)
        if len(top_buys) == TOP_BUYS_COUNT:
            break
    for buy in top_buys:
        if buy["ticker"] not in by_ticker:
            new_pick = {
                "ticker": buy["ticker"],
                "company": buy["company"],
                "direction": "bullish",
                "confidence": buy["confidence"],
                "reason": buy["pitch"],
                "sources": buy["sources"],
                "theme": buy.get("theme", "Other"),
                "target_pct": buy.get("target_pct"),
                "stop_pct": buy.get("stop_pct"),
            }
            result["picks"].append(new_pick)
            by_ticker[buy["ticker"]] = new_pick
    result["top_buys"] = top_buys
    return result


# Sensible bounds for the price levels, in case Claude's numbers are odd.
MIN_LEVEL_PCT, MAX_LEVEL_PCT = 1.0, 50.0


def add_price_levels(picks, prices):
    """
    Turns each pick's target_pct / stop_pct into actual prices, using the
    price when it was picked. For a bullish call the target is above and the
    "proven wrong" price below; for a bearish call it's the other way round.
    Picks without a price (or without levels) get None.
    """
    for pick in picks:
        price = prices.get(pick["ticker"])
        sign = 1 if pick["direction"] == "bullish" else -1
        for key, direction in (("target", sign), ("stop", -sign)):
            pct = pick.get(f"{key}_pct")
            if price and isinstance(pct, (int, float)):
                pct = min(max(abs(pct), MIN_LEVEL_PCT), MAX_LEVEL_PCT)
                pick[f"{key}_pct"] = round(pct, 1)
                pick[f"{key}_price"] = round(price * (1 + direction * pct / 100), 2)
            else:
                pick[f"{key}_price"] = None
    return picks
