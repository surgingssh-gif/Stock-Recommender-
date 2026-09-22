# Project: Daily Stock News Bot

## Goal
A bot that runs every weekday morning, reads current world and business
news, identifies events likely to move markets (trade deals, tariffs,
oil prices, interest rates, AI/tech news, earnings, regulation, conflicts),
and sends me a short list of stock ideas with reasoning.

This is a research/idea tool, not an auto-trader. It never places trades.

## About me
I'm fairly new to coding. Explain what you're doing in plain language,
tell me exactly what to click or type when I need to do something
myself (like getting API keys), and keep the code simple and well-commented.

## Tech stack
- Python 3
- Finnhub API for news (free tier)
- Claude API (Anthropic) for analyzing news and picking tickers
- yfinance for price data
- Discord webhook for delivering results
- GitHub Actions for scheduling (so it runs even when my computer is off)

## Rules
- Never hardcode API keys. Use a .env file locally and GitHub Secrets
  in Actions. Make sure .env is in .gitignore.
- Log every pick to picks_log.csv (date, ticker, direction, reason,
  price at time of pick) so performance can be checked later.
- Every daily message ends with: "Ideas for research only, not
  financial advice."
- Handle errors gracefully: if one API fails, still send what's available
  plus a note about what failed.
- Keep API costs low: batch headlines into one Claude call per run.
