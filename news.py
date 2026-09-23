"""
news.py - Fetches recent market-moving headlines from Finnhub.

Finnhub's free "market news" endpoint returns the latest general business
and world news. We grab two categories (general news + mergers), keep only
headlines from the last day or so, remove duplicates, and return a tidy list.
"""

import time
from datetime import datetime, timezone

import requests

FINNHUB_NEWS_URL = "https://finnhub.io/api/v1/news"

# Which Finnhub news categories to pull. "general" covers world/business news,
# "merger" covers deals and acquisitions.
CATEGORIES = ["general", "merger"]

# Cap how many headlines we send to Claude, so the API cost stays small.
MAX_HEADLINES = 60


def _hours_to_look_back():
    """On Mondays, look back over the weekend (72h). Otherwise, 24h."""
    if datetime.now(timezone.utc).weekday() == 0:  # 0 = Monday
        return 72
    return 24


def fetch_headlines(api_key):
    """
    Returns a list of dicts like:
        {"headline": "...", "summary": "...", "source": "...", "time": "...",
         "url": "https://...", "image": "https://..."}

    Raises an exception if Finnhub can't be reached at all, so the caller
    can report the failure in the Discord message.
    """
    cutoff = time.time() - _hours_to_look_back() * 3600
    seen_headlines = set()
    headlines = []
    errors = []

    for category in CATEGORIES:
        try:
            response = requests.get(
                FINNHUB_NEWS_URL,
                params={"category": category},
                # The key goes in a header (not the URL) so it never shows
                # up in error messages that get posted to Discord.
                headers={"X-Finnhub-Token": api_key},
                timeout=20,
            )
            response.raise_for_status()  # turns HTTP errors (401, 429...) into exceptions
            articles = response.json()
        except Exception as e:
            # One category failing shouldn't stop the other from working.
            errors.append(f"{category}: {e}")
            continue

        for article in articles:
            headline = (article.get("headline") or "").strip()
            published = article.get("datetime") or 0

            # Skip empty, old, or duplicate headlines.
            if not headline or published < cutoff or headline in seen_headlines:
                continue
            seen_headlines.add(headline)

            headlines.append({
                "headline": headline,
                # Summaries can be long; trim them to keep the Claude call cheap.
                "summary": (article.get("summary") or "").strip()[:300],
                "source": article.get("source") or "unknown",
                "time": datetime.fromtimestamp(published, timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
                "published": published,
                # Link to the full article and its photo (used by the dashboard).
                "url": article.get("url") or "",
                "image": article.get("image") or "",
            })

    # If every category failed, treat that as a real failure.
    if errors and not headlines:
        raise RuntimeError("Finnhub request failed -> " + "; ".join(errors))

    # Newest first, then keep only the top MAX_HEADLINES.
    headlines.sort(key=lambda h: h["published"], reverse=True)
    return headlines[:MAX_HEADLINES]
