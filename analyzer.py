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
not recommendations. If the news is too quiet for 5 solid ideas, return fewer."""

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
                },
                "required": ["ticker", "company", "direction", "confidence", "reason", "sources"],
                "additionalProperties": False,
            },
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
                },
                "required": ["ticker", "company", "confidence", "pitch", "why", "risks", "watch", "sources"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["market_mood", "picks", "watchlist_notes", "top_buys"],
    "additionalProperties": False,
}


def _format_headlines(headlines):
    """Turn the list of headline dicts into one numbered block of text."""
    lines = []
    for i, h in enumerate(headlines, start=1):
        line = f"{i}. [{h['time']}] ({h['source']}) {h['headline']}"
        if h["summary"]:
            line += f"\n   {h['summary']}"
        lines.append(line)
    return "\n".join(lines)


def analyze_headlines(headlines, api_key, watchlist=None):
    """
    Returns a dict: {"market_mood": "...", "picks": [ {ticker, company,
    direction, confidence, reason, sources}, ... ]}
    where "sources" are the numbers (starting at 1) of the headlines used,
    plus "watchlist_notes": [ {ticker, note}, ... ] for the watchlist tickers,
    plus "top_buys": up to 5 ranked bullish ideas {ticker, company,
    confidence, pitch, why, risks, watch, sources}. Every top buy is also
    in "picks".

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
            }
            result["picks"].append(new_pick)
            by_ticker[buy["ticker"]] = new_pick
    result["top_buys"] = top_buys
    return result
