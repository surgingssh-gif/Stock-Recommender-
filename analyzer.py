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
- Include both obvious and second-order effects when they are well supported \
(e.g. an oil spike hurting airlines)."""

# The exact JSON shape we want back from Claude.
OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "market_mood": {
            "type": "string",
            "description": "One or two sentences on the overall theme of today's news.",
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
                },
                "required": ["ticker", "company", "direction", "confidence", "reason"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["market_mood", "picks"],
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


def analyze_headlines(headlines, api_key):
    """
    Returns a dict: {"market_mood": "...", "picks": [ {ticker, company,
    direction, confidence, reason}, ... ]}

    Raises an exception if Claude can't be reached or declines to answer,
    so the caller can report it.
    """
    client = anthropic.Anthropic(api_key=api_key)
    model = os.getenv("CLAUDE_MODEL") or DEFAULT_MODEL

    user_message = (
        "Here are the latest headlines. Suggest stock ideas based on them.\n\n"
        + _format_headlines(headlines)
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
    for pick in result["picks"]:
        pick["ticker"] = pick["ticker"].strip().upper().lstrip("$")

    return result
