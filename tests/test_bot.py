"""
Tests that run WITHOUT any API keys or internet. They swap the real
Finnhub/Claude/yfinance/Discord calls for fake ones.

Run them with:  python -m pytest
"""

import csv
import json
import sys
from pathlib import Path

# Let the tests import main.py, news.py, etc. from the project folder.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import discord_notify
import main
from build_dashboard import build_data, read_picks, score_pick
from discord_notify import DISCLAIMER, DISCORD_LIMIT, _split_message, build_message
from picks_log import log_picks, save_day_details

FAKE_HEADLINES = [
    {"headline": "Oil jumps 5% after supply cut", "summary": "", "source": "Reuters",
     "time": "2026-09-22 11:00 UTC", "published": 1},
]
FAKE_ANALYSIS = {
    "market_mood": "Energy is in focus.",
    "picks": [
        {"ticker": "XOM", "company": "Exxon Mobil", "direction": "bullish",
         "confidence": "medium", "reason": "Higher oil prices lift producer profits."},
        {"ticker": "DAL", "company": "Delta Air Lines", "direction": "bearish",
         "confidence": "low", "reason": "Jet fuel costs rise with oil."},
    ],
}


def test_message_always_ends_with_disclaimer():
    full = build_message("2026-09-22", FAKE_ANALYSIS, {"XOM": 110.5, "DAL": None}, [])
    empty = build_message("2026-09-22", None, {}, ["Everything broke"])
    assert full.endswith(f"_{DISCLAIMER}_")
    assert empty.endswith(f"_{DISCLAIMER}_")
    assert "$110.50" in full and "price n/a" in full


def test_headlines_shown_when_analysis_fails():
    msg = build_message("2026-09-22", None, {}, ["Claude failed"], FAKE_HEADLINES)
    assert "Oil jumps 5%" in msg and "Claude failed" in msg


def test_long_message_is_split_under_discord_limit():
    text = "\n".join(["x" * 150] * 40) + f"\n_{DISCLAIMER}_"
    chunks = _split_message(text)
    assert len(chunks) > 1
    assert all(len(c) <= DISCORD_LIMIT for c in chunks)
    assert chunks[-1].strip().endswith(f"_{DISCLAIMER}_")


def test_log_picks_writes_header_and_rows(tmp_path):
    log_file = tmp_path / "picks_log.csv"
    log_picks("2026-09-22", FAKE_ANALYSIS["picks"], {"XOM": 110.5}, log_file=str(log_file))
    log_picks("2026-09-23", FAKE_ANALYSIS["picks"][:1], {"XOM": 111.0}, log_file=str(log_file))
    rows = list(csv.reader(log_file.open()))
    assert rows[0] == ["date", "ticker", "direction", "reason", "price_at_pick"]
    assert rows[1][:3] == ["2026-09-22", "XOM", "bullish"] and rows[1][4] == "110.5"
    assert rows[2][4] == ""  # DAL had no price
    assert len(rows) == 4


def _run_main(monkeypatch, tmp_path, *, news=None, analysis=None):
    """Runs main() with fake services. Returns the list of messages 'sent'."""
    monkeypatch.chdir(tmp_path)  # so picks_log.csv is written to a temp folder
    monkeypatch.setattr(main, "load_dotenv", lambda: None)
    for key in ("FINNHUB_API_KEY", "ANTHROPIC_API_KEY", "DISCORD_WEBHOOK_URL"):
        monkeypatch.setenv(key, "fake")
    monkeypatch.setattr(sys, "argv", ["main.py"])

    def fake_news(_key):
        if isinstance(news, Exception):
            raise news
        return news

    def fake_analysis(_headlines, _key):
        if isinstance(analysis, Exception):
            raise analysis
        return analysis

    sent = []
    monkeypatch.setattr(main, "fetch_headlines", fake_news)
    monkeypatch.setattr(main, "analyze_headlines", fake_analysis)
    monkeypatch.setattr(main, "get_prices", lambda tickers: {"XOM": 110.5, "DAL": None})
    monkeypatch.setattr(main, "send_to_discord", lambda url, text: sent.append(text))
    main.main()
    return sent


def test_full_run_logs_and_sends(monkeypatch, tmp_path):
    sent = _run_main(monkeypatch, tmp_path, news=FAKE_HEADLINES, analysis=FAKE_ANALYSIS)
    assert len(sent) == 1 and "XOM" in sent[0]
    assert "Couldn't get prices for: DAL" in sent[0]
    assert (tmp_path / "picks_log.csv").exists()


def test_news_failure_still_sends_message(monkeypatch, tmp_path):
    sent = _run_main(monkeypatch, tmp_path, news=RuntimeError("Finnhub down"))
    assert "News (Finnhub) failed: Finnhub down" in sent[0]
    assert sent[0].endswith(f"_{DISCLAIMER}_")


def test_claude_failure_still_sends_headlines(monkeypatch, tmp_path):
    sent = _run_main(monkeypatch, tmp_path, news=FAKE_HEADLINES, analysis=RuntimeError("overloaded"))
    assert "Analysis (Claude) failed: overloaded" in sent[0]
    assert "Oil jumps 5%" in sent[0]
    assert not (tmp_path / "picks_log.csv").exists()


def test_discord_error_hides_webhook_url(monkeypatch):
    class FakeResponse:
        ok, status_code, text = False, 404, "Unknown Webhook"

    monkeypatch.setattr(discord_notify.requests, "post", lambda *a, **k: FakeResponse())
    try:
        discord_notify.send_to_discord("https://discord.com/api/webhooks/SECRET", "hi")
    except RuntimeError as e:
        assert "SECRET" not in str(e) and "404" in str(e)
    else:
        raise AssertionError("expected an error")


# --- Dashboard ----------------------------------------------------------------


def test_score_pick_flips_bearish_calls():
    bull = score_pick({"direction": "bullish", "price_at_pick": 100.0}, 110.0)
    bear = score_pick({"direction": "bearish", "price_at_pick": 100.0}, 110.0)
    flat = score_pick({"direction": "bearish", "price_at_pick": 100.0}, 100.0)
    none = score_pick({"direction": "bullish", "price_at_pick": None}, 110.0)
    assert bull["return_pct"] == 10.0 and bull["directional_return_pct"] == 10.0 and bull["correct"] is True
    assert bear["directional_return_pct"] == -10.0 and bear["correct"] is False
    assert flat["correct"] is None and str(flat["directional_return_pct"]) == "0.0"  # no "-0.0"
    assert none["correct"] is None and none["return_pct"] is None


def test_read_picks_keeps_latest_duplicate(tmp_path):
    log_file = tmp_path / "picks_log.csv"
    log_picks("2026-09-22", FAKE_ANALYSIS["picks"], {"XOM": 110.5}, log_file=str(log_file))
    log_picks("2026-09-22", FAKE_ANALYSIS["picks"][:1], {"XOM": 112.0}, log_file=str(log_file))
    picks = read_picks(str(log_file))
    assert len(picks) == 2  # XOM counted once
    assert next(p for p in picks if p["ticker"] == "XOM")["price_at_pick"] == 112.0


def test_build_data_scores_and_merges_details(tmp_path):
    picks = [
        {"date": "2026-09-21", "ticker": "XOM", "direction": "bullish", "reason": "r", "price_at_pick": 100.0},
        {"date": "2026-09-21", "ticker": "DAL", "direction": "bearish", "reason": "r", "price_at_pick": 50.0},
        {"date": "2026-09-22", "ticker": "NVDA", "direction": "bullish", "reason": "r", "price_at_pick": 200.0},
    ]
    save_day_details("2026-09-21", FAKE_ANALYSIS, FAKE_HEADLINES, days_dir=str(tmp_path))
    days = {"2026-09-21": json.loads((tmp_path / "2026-09-21.json").read_text())}
    histories = {
        "XOM": [["2026-09-18", 95.0], ["2026-09-21", 100.0], ["2026-09-22", 105.0]],  # up 5%: right
        "DAL": [["2026-09-21", 50.0], ["2026-09-22", 55.0]],                          # up 10%: bearish call wrong
        "NVDA": [["2026-09-22", 200.0]],                                              # flat: too early
    }
    data = build_data(picks, days, histories)

    assert [p["date"] for p in data["picks"]] == ["2026-09-22", "2026-09-21", "2026-09-21"]
    xom = next(p for p in data["picks"] if p["ticker"] == "XOM")
    assert xom["company"] == "Exxon Mobil" and xom["confidence"] == "medium"
    assert xom["history"][0][0] == "2026-09-21"  # history starts at the pick date
    stats = data["stats"]
    assert stats["total_picks"] == 3 and stats["days_tracked"] == 2
    assert stats["judged"] == 2 and stats["correct"] == 1 and stats["hit_rate"] == 50.0
    assert stats["best"]["ticker"] == "XOM" and stats["worst"]["ticker"] == "DAL"
    assert data["charts"]["XOM"][0] == ["2026-09-18", 95.0]  # full history kept for the big chart
    assert data["days"][1]["market_mood"] == "Energy is in focus."
    assert data["days"][1]["headlines"][0]["headline"] == "Oil jumps 5% after supply cut"
