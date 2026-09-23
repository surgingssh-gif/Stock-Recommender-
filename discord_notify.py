"""
discord_notify.py - Builds the daily message and posts it to Discord
through a webhook (a special URL that lets a program post into a channel).
"""

import requests

DISCLAIMER = "Ideas for research only, not financial advice."

# Discord rejects messages longer than 2000 characters.
DISCORD_LIMIT = 2000


def build_message(date_str, analysis, prices, problems, headlines=None):
    """
    Creates the text of the daily message.

    analysis  - Claude's result dict, or None if analysis failed
    prices    - dict of ticker -> price (or None)
    problems  - list of strings describing anything that went wrong
    headlines - today's news; only shown if Claude's analysis failed,
                so you still get something useful
    """
    lines = [f"**📈 Daily Stock Ideas - {date_str}**", ""]

    if analysis:
        lines.append(f"*{analysis['market_mood']}*")
        lines.append("")

        if not analysis["picks"]:
            lines.append("No strong ideas from today's news.")

        # The "Top 5 buys of the day" come first, ranked best first.
        top_buys = analysis.get("top_buys") or []
        if top_buys:
            lines.append("**🏆 Top buys of the day**")
            for rank, buy in enumerate(top_buys, start=1):
                lines.append(
                    f"{rank}. **{buy['ticker']}** ({buy['company']}) - "
                    f"{_price_text(prices, buy['ticker'])} - {buy['pitch']}"
                )
            lines.append("")

        # Then every other idea (the top buys aren't repeated).
        top_tickers = {b["ticker"] for b in top_buys}
        others = [p for p in analysis["picks"] if p["ticker"] not in top_tickers]
        if top_buys and others:
            lines.append("**Other ideas**")
        for pick in others:
            arrow = "🟢 ▲" if pick["direction"] == "bullish" else "🔴 ▼"
            lines.append(
                f"{arrow} **{pick['ticker']}** ({pick['company']}) - "
                f"{pick['direction']}, {pick['confidence']} confidence, {_price_text(prices, pick['ticker'])}"
            )
            lines.append(f"> {pick['reason']}")
            lines.append("")

    elif headlines:
        lines.append("Couldn't generate stock ideas today, but here are the top headlines:")
        for h in headlines[:8]:
            lines.append(f"- {h['headline']} ({h['source']})")
        lines.append("")

    if problems:
        lines.append("⚠️ **Some things went wrong today:**")
        for problem in problems:
            lines.append(f"- {problem}")
        lines.append("")

    # Required on every message.
    lines.append(f"_{DISCLAIMER}_")
    return "\n".join(lines)


def _price_text(prices, ticker):
    price = prices.get(ticker)
    return f"${price:,.2f}" if price is not None else "price n/a"


def _split_message(text):
    """Split long text into chunks under Discord's limit, breaking on lines."""
    chunks, current = [], ""
    for line in text.split("\n"):
        # A single very long line gets cut hard (rare, but keeps us safe).
        line = line[: DISCORD_LIMIT - 10]
        if len(current) + len(line) + 1 > DISCORD_LIMIT:
            chunks.append(current)
            current = ""
        current += line + "\n"
    if current.strip():
        chunks.append(current)
    return chunks


def send_to_discord(webhook_url, text):
    """Posts the message, splitting it into several posts if it's too long."""
    for chunk in _split_message(text):
        response = requests.post(webhook_url, json={"content": chunk}, timeout=20)
        if not response.ok:
            # Don't include the webhook URL in the error - it's a secret.
            raise RuntimeError(f"Discord returned {response.status_code}: {response.text[:200]}")
