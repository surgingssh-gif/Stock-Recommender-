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

    def fake_analysis(_headlines, _key, _watchlist=None):
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


def test_picks_get_their_source_article_and_photo(tmp_path):
    headlines = [
        {"headline": "Fed holds rates", "summary": "", "source": "AP", "time": "t1", "url": "https://a/1", "image": ""},
        {"headline": "Oil jumps 5%", "summary": "", "source": "Reuters", "time": "t2", "url": "https://a/2", "image": "https://img/2.jpg"},
    ]
    analysis = {"market_mood": "m", "picks": [
        {"ticker": "XOM", "company": "Exxon", "direction": "bullish", "confidence": "high", "reason": "r", "sources": [1, 2]},
        {"ticker": "DAL", "company": "Delta", "direction": "bearish", "confidence": "low", "reason": "r", "sources": [99]},
    ]}
    save_day_details("2026-09-23", analysis, headlines, days_dir=str(tmp_path))
    days = {"2026-09-23": json.loads((tmp_path / "2026-09-23.json").read_text())}
    picks = [{"date": "2026-09-23", "ticker": t, "direction": "bullish", "reason": "r", "price_at_pick": 10.0} for t in ("XOM", "DAL")]
    data = build_data(picks, days, {})

    xom = next(p for p in data["picks"] if p["ticker"] == "XOM")
    dal = next(p for p in data["picks"] if p["ticker"] == "DAL")
    assert xom["article"]["headline"] == "Oil jumps 5%"  # the source that has a photo wins
    assert xom["article"]["image"] == "https://img/2.jpg"
    assert dal["article"] is None  # a headline number that doesn't exist is ignored
    assert [h["tickers"] for h in data["days"][0]["headlines"]] == [["XOM"], ["XOM"]]
    assert data["days"][0]["headline_count"] == 2


def test_rerun_on_same_day_shows_only_latest_run():
    # Run 1 picked XOM and DAL; run 2 (same day) picked NVDA and XOM.
    picks = [
        {"date": "2026-09-23", "ticker": "XOM", "direction": "bullish", "reason": "r", "price_at_pick": 10.0},
        {"date": "2026-09-23", "ticker": "DAL", "direction": "bearish", "reason": "r", "price_at_pick": 20.0},
        {"date": "2026-09-23", "ticker": "NVDA", "direction": "bullish", "reason": "r", "price_at_pick": 30.0},
        {"date": "2026-09-22", "ticker": "OLD", "direction": "bullish", "reason": "r", "price_at_pick": 5.0},
    ]
    days = {"2026-09-23": {"date": "2026-09-23", "market_mood": "m", "headlines": [], "picks": [
        {"ticker": "NVDA", "company": "NVIDIA"}, {"ticker": "XOM", "company": "Exxon"}]}}
    data = build_data(picks, days, {})
    # DAL is dropped, latest run's order is kept, and days without a detail file are untouched.
    assert [p["ticker"] for p in data["picks"]] == ["NVDA", "XOM", "OLD"]
    assert data["stats"]["total_picks"] == 3


def test_blank_prices_never_become_nan(monkeypatch, tmp_path):
    import math
    import pandas as pd
    import prices
    from build_dashboard import _number

    # Yahoo returning a blank row for today: use the last real price instead.
    class FakeTicker:
        def __init__(self, _t): pass
        def history(self, **_k):
            return pd.DataFrame({"Close": [148.16, float("nan")]})
    monkeypatch.setattr(prices.yf, "Ticker", FakeTicker)
    assert prices.get_price("USO") == 148.16

    # "nan" or blank in the CSV is read as "no price".
    assert _number("nan") is None and _number("") is None and _number("12.5") == 12.5

    # A missing pick price is filled from that day's close.
    picks = [{"date": "2026-09-22", "ticker": "BHF", "direction": "bullish", "reason": "r", "price_at_pick": None}]
    data = build_data(picks, {}, {"BHF": [["2026-09-22", 50.0], ["2026-09-23", 55.0]]})
    p = data["picks"][0]
    assert p["price_at_pick"] == 50.0 and p["return_pct"] == 10.0 and p["correct"] is True
    assert not any(isinstance(v, float) and math.isnan(v) for v in p.values())


def test_picks_are_not_scored_against_older_prices():
    # Yahoo is missing the pick day, so the newest price is from the day before.
    picks = [{"date": "2026-09-22", "ticker": "USO", "direction": "bearish", "reason": "r", "price_at_pick": 144.08}]
    data = build_data(picks, {}, {"USO": [["2026-09-18", 153.82], ["2026-09-21", 148.16]]})
    p = data["picks"][0]
    assert p["price_now"] is None and p["return_pct"] is None and p["correct"] is None


def test_logo_images_are_not_used_as_photos():
    from build_dashboard import _real_photos
    heads = [
        {"headline": "a", "image": "https://static2.finnhub.io/file/finnhub/logo/reuters_logo.jpeg"},
        {"headline": "b", "image": "https://cdn.example/same.png"},
        {"headline": "c", "image": "https://cdn.example/same.png"},
        {"headline": "d", "image": "https://cdn.example/same.png"},
        {"headline": "e", "image": "https://image.cnbcfm.com/real-photo.jpg"},
        {"headline": "f", "image": ""},
    ]
    assert [h["image"] for h in _real_photos(heads)] == ["", "", "", "", "https://image.cnbcfm.com/real-photo.jpg", ""]


def test_watchlist_cards_use_latest_notes():
    from watchlist import WATCHLIST
    days = {
        "2026-09-21": {"date": "2026-09-21", "picks": [], "headlines": [], "watchlist_notes": [{"ticker": "SPY", "note": "old"}]},
        "2026-09-22": {"date": "2026-09-22", "picks": [], "headlines": [], "watchlist_notes": [{"ticker": "SPY", "note": "new"}]},
    }
    cards = build_data([], days, {})["watchlist"]
    assert [c["ticker"] for c in cards] == list(WATCHLIST)
    spy = next(c for c in cards if c["ticker"] == "SPY")
    assert spy["note"] == "new" and spy["note_date"] == "2026-09-22"
    assert next(c for c in cards if c["ticker"] == "AAPL")["note"] is None


def _top_buy(ticker, **extra):
    buy = {"ticker": ticker, "company": ticker + " Inc", "confidence": "medium",
           "pitch": f"{ticker} pitch", "why": "Why.", "risks": "Risks.", "watch": "Watch.", "sources": [1]}
    buy.update(extra)
    return buy


def test_top_buys_become_picks_and_skip_bearish_clashes():
    from analyzer import add_top_buys_to_picks

    result = {
        "market_mood": "",
        "watchlist_notes": [],
        "picks": [dict(p, sources=[1]) for p in FAKE_ANALYSIS["picks"]],
        "top_buys": [_top_buy("XOM"), _top_buy("DAL"), _top_buy("CVX"), _top_buy("CVX"),
                     _top_buy("A"), _top_buy("B"), _top_buy("C"), _top_buy("D")],
    }
    add_top_buys_to_picks(result)
    # DAL was called bearish, so it can't be a top buy; CVX only counts once.
    assert [b["ticker"] for b in result["top_buys"]] == ["XOM", "CVX", "A", "B", "C"]
    # New top buys are added as bullish picks (so they get logged); XOM isn't duplicated.
    tickers = [p["ticker"] for p in result["picks"]]
    assert tickers == ["XOM", "DAL", "CVX", "A", "B", "C"]
    cvx = next(p for p in result["picks"] if p["ticker"] == "CVX")
    assert cvx["direction"] == "bullish" and cvx["reason"] == "CVX pitch"


def test_message_lists_top_buys_first_without_repeats():
    analysis = dict(FAKE_ANALYSIS, top_buys=[_top_buy("XOM", company="Exxon Mobil")])
    msg = build_message("2026-09-22", analysis, {"XOM": 110.5, "DAL": None}, [])
    assert "Top buys of the day" in msg
    assert "1. **XOM** (Exxon Mobil) - $110.50 - XOM pitch" in msg
    assert msg.count("**XOM**") == 1  # not repeated under "Other ideas"
    assert "Other ideas" in msg and "**DAL**" in msg
    assert msg.endswith(f"_{DISCLAIMER}_")


def test_dashboard_top_buys_get_prices_from_their_pick():
    picks = [{"date": "2026-09-22", "ticker": "XOM", "direction": "bullish",
              "reason": "r", "price_at_pick": 100.0}]
    days = {"2026-09-22": {"date": "2026-09-22", "market_mood": "", "headlines": FAKE_HEADLINES,
                           "picks": [{"ticker": "XOM", "sources": [1]}],
                           "top_buys": [_top_buy("XOM")]}}
    data = build_data(picks, days, {"XOM": [["2026-09-22", 100.0], ["2026-09-23", 110.0]]})
    (buy,) = data["top_buys"]
    assert buy["rank"] == 1 and buy["why"] == "Why."
    assert buy["price_now"] == 110.0 and buy["return_pct"] == 10.0
    assert buy["article"]["headline"] == FAKE_HEADLINES[0]["headline"]


def test_top_buys_record_compares_top_5_with_other_picks():
    picks = [
        {"date": "2026-09-22", "ticker": t, "direction": d, "reason": "r", "price_at_pick": 100.0}
        for t, d in [("XOM", "bullish"), ("CVX", "bullish"), ("DAL", "bearish")]
    ]
    days = {"2026-09-22": {"date": "2026-09-22", "market_mood": "", "headlines": [],
                           "picks": [{"ticker": t, "sources": []} for t in ("XOM", "CVX", "DAL")],
                           "top_buys": [_top_buy("CVX"), _top_buy("XOM")]}}
    histories = {"XOM": [["2026-09-23", 90.0]], "CVX": [["2026-09-23", 120.0]], "DAL": [["2026-09-23", 95.0]]}
    data = build_data(picks, days, histories)

    ranks = {p["ticker"]: p["top_rank"] for p in data["picks"]}
    assert ranks == {"CVX": 1, "XOM": 2, "DAL": None}
    record = data["stats"]["top_buys"]
    top, rest = record["groups"]
    assert (top["count"], top["hit_rate"], top["avg_directional_return"]) == (2, 50.0, 5.0)
    assert (rest["count"], rest["hit_rate"], rest["avg_directional_return"]) == (1, 100.0, 5.0)
    (day,) = record["by_day"]
    assert [b["ticker"] for b in day["buys"]] == ["CVX", "XOM"]


def test_message_links_to_dashboard_before_disclaimer(monkeypatch):
    monkeypatch.delenv("DASHBOARD_URL", raising=False)
    monkeypatch.setenv("GITHUB_REPOSITORY", "Someone/My-Bot")
    url = main.dashboard_url()
    assert url == "https://someone.github.io/My-Bot/"
    msg = build_message("2026-09-22", FAKE_ANALYSIS, {}, [], dashboard_url=url)
    assert url in msg
    assert msg.endswith(f"_{DISCLAIMER}_")


def test_evening_recap_scores_calls_and_ends_with_disclaimer():
    from recap import build_recap, score

    xom = score({"date": "2026-09-25", "ticker": "XOM", "direction": "bullish", "price_at_pick": 100.0}, 102.0)
    dal = score({"date": "2026-09-25", "ticker": "DAL", "direction": "bearish", "price_at_pick": 50.0}, 51.0)
    bhf = score({"date": "2026-09-25", "ticker": "BHF", "direction": "bullish", "price_at_pick": None}, None)
    msg = build_recap("2026-09-25", [xom, dal, bhf], ["XOM"], dashboard="https://x.test/")
    assert "1 of 2 calls worked" in msg
    assert "#1 ✅ ▲ **XOM** +2.00% ($100.00 → $102.00)" in msg
    assert "❌ ▼ **DAL** +2.00%" in msg          # the stock rose, so the bearish call was wrong
    assert "⏳ ▲ **BHF**" in msg
    assert msg.endswith(f"_{DISCLAIMER}_")

    week = [dict(xom, top=True), dict(dal, top=False)]
    friday = build_recap("2026-09-25", [xom, dal], ["XOM"], week)
    assert "Week in review" in friday and "Best call: **XOM** +2.00%" in friday
    assert "Worst call: **DAL** -2.00%" in friday
    assert friday.endswith(f"_{DISCLAIMER}_")


def test_events_calendar_keeps_upcoming_dates_in_order():
    from build_dashboard import build_events

    earnings = {"NVDA": "2026-10-20", "AAPL": "2026-12-30", "XOM": "2026-09-01", "META": None}
    events = build_events(earnings, {"NVDA": "NVIDIA"}, "2026-09-23")
    # Past dates and ones more than 45 days out are left off; the Fed meeting on Oct 28 is in.
    assert [(e["date"], e["label"]) for e in events] == [
        ("2026-10-20", "NVIDIA earnings"),
        ("2026-10-28", "Fed interest-rate decision"),
    ]


def test_sector_moves_and_weekly_report():
    from build_dashboard import sector_moves, weekly_report

    history = [[f"2026-09-{d:02d}", 100.0 + d] for d in range(1, 11)]
    (tech,) = [s for s in sector_moves({"XLK": history}) if s["ticker"] == "XLK"]
    assert tech["changes"]["1D"] == round((110 - 109) / 109 * 100, 2)
    assert tech["changes"]["1M"] is None  # not enough history yet

    def pick(d, t, move, top=None):
        return {"date": d, "ticker": t, "direction": "bullish", "top_rank": top,
                "directional_return_pct": move, "correct": None if move is None else move > 0}

    cards = weekly_report([pick("2026-09-21", "A", 2.0, 1), pick("2026-09-23", "B", -1.0),
                           pick("2026-09-28", "C", None)])
    assert [c["week_start"] for c in cards] == ["2026-09-28", "2026-09-21"]
    last_week = cards[1]
    assert (last_week["count"], last_week["hit_rate"], last_week["top5_hit_rate"]) == (2, 50.0, 100.0)
    assert last_week["best"]["ticker"] == "A" and last_week["worst"]["ticker"] == "B"


def test_pretend_portfolio_follows_the_top_5_and_compares_with_spy():
    from build_dashboard import pretend_portfolio

    picks = [
        {"date": "2026-09-22", "ticker": "A", "top_rank": 1, "price_at_pick": 10.0},
        {"date": "2026-09-22", "ticker": "B", "top_rank": 2, "price_at_pick": 20.0},
        {"date": "2026-09-22", "ticker": "C", "top_rank": None, "price_at_pick": 5.0},  # not a top buy
        {"date": "2026-09-24", "ticker": "C", "top_rank": 1, "price_at_pick": 5.0},
    ]
    histories = {
        "SPY": [["2026-09-21", 100.0], ["2026-09-22", 101.0], ["2026-09-23", 102.0], ["2026-09-24", 103.0]],
        "A": [["2026-09-22", 11.0], ["2026-09-23", 12.0]],   # +10%, then +20%
        "B": [["2026-09-22", 20.0], ["2026-09-23", 18.0]],   # 0%, then -10%
        "C": [["2026-09-24", 5.5]],                          # +10%
    }
    result = pretend_portfolio(picks, histories)
    days = [row[0] for row in result["series"]]
    assert days == ["2026-09-21", "2026-09-22", "2026-09-23", "2026-09-24"]
    top5 = [row[1] for row in result["series"]]
    assert top5 == [10000, 10500.0, 10500.0, 11550.0]  # (+10% + 0%)/2, (+20% - 10%)/2, then all in C +10%
    assert result["series"][-1][2] == 10300.0          # SPY from $100 to $103
    assert (result["top5_return_pct"], result["spy_return_pct"]) == (15.5, 3.0)
    assert pretend_portfolio([], histories) is None
