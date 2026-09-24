# Daily Stock News Bot

Every weekday morning this bot:

1. Reads the latest world and business headlines (from **Finnhub**)
2. Asks **Claude** which stocks the news could move, and why (one API call per day)
3. Looks up each stock's current price (with **yfinance**)
4. Saves every idea to `picks_log.csv` so you can check later how they did
5. Sends you a short list in **Discord**
6. Updates a **dashboard web page** (styled like a newspaper) with every pick and a running scorecard

> This is a research tool, not a trading bot. It never buys or sells anything.
> Ideas for research only, not financial advice.

Example message:

```
📈 Daily Stock Ideas - 2026-09-22
Energy is in focus after an OPEC supply cut.

🟢 ▲ XOM (Exxon Mobil) - bullish, medium confidence, $158.95
> Higher oil prices tend to lift oil producers' profits.

🔴 ▼ DAL (Delta Air Lines) - bearish, low confidence, $52.10
> Jet fuel is a big cost for airlines, so an oil jump can hurt margins.

Ideas for research only, not financial advice.
```

---

## What each file does

| File | What it does |
|---|---|
| `main.py` | The main script. Runs all the steps in order. |
| `news.py` | Gets headlines from Finnhub. |
| `analyzer.py` | Sends the headlines to Claude and gets stock ideas back. |
| `prices.py` | Looks up stock prices. |
| `picks_log.py` | Adds each pick to `picks_log.csv`. |
| `discord_notify.py` | Builds the message and posts it to Discord. |
| `track_record.py` | Sums up how the bot's recent calls did, so Claude can learn from them. |
| `market_data.py` | Gets the market's biggest movers and pre-market moves from Yahoo. |
| `watchlist.py` | The "Market watch" stocks shown on the Stock Charts tab every day. Edit it to add or remove stocks. |
| `recap.py` | The evening recap: after the market closes, posts how the day's picks moved (and a weekly report card on Fridays). |
| `alerts.py` | Big-move alerts: pings Discord when a recent pick has moved 5% or more. |
| `build_dashboard.py` | Scores every pick against the latest prices and writes the dashboard data (`docs/data.js`). |
| `docs/` | The dashboard web page (`index.html`, `app.js`) and its data. |
| `data/days/` | One file per day with extra details: market mood, confidence, and the headlines Claude read (with links and photos). |
| `.github/workflows/daily.yml` | Tells GitHub to run the bot every weekday morning. |
| `.github/workflows/alerts.yml` | Checks for big moves every hour while the market is open. |
| `.github/workflows/recap.yml` | Tells GitHub to send the evening recap every weekday after the close. |
| `tests/test_bot.py` | Automatic checks that use fake data, so no keys are needed. |

If something breaks (for example, Finnhub is down), the bot still sends a
message with whatever it has, plus a note saying what failed.

---

## Setup, step by step

### Step 1: Get your 3 keys

You need three secret values. Keep them private, like passwords.

**A) Finnhub API key (free)**
1. Go to https://finnhub.io and click **Get free API key**.
2. Sign up, then open your **Dashboard**.
3. Copy the long code next to **API Key**.

**B) Anthropic (Claude) API key**
1. Go to https://console.anthropic.com and sign up or log in.
2. Click **Settings** > **Billing** and add a small amount of credit ($5 is plenty to start).
3. Click **Settings** > **API Keys** > **Create Key**. Name it `stock-bot`.
4. Copy the key (it starts with `sk-ant-`). **It's only shown once**, so paste it somewhere safe.

**C) Discord webhook URL**
1. In Discord, pick (or create) the channel where you want the messages.
2. Hover over the channel name and click the ⚙️ gear (**Edit Channel**).
3. Click **Integrations** > **Webhooks** > **New Webhook**.
4. Click the new webhook, then **Copy Webhook URL**.

### Step 2: Run it on your computer (optional but recommended)

Open a terminal in the project folder and type:

```bash
pip install -r requirements.txt
```

Then make your private settings file:

1. Make a copy of `.env.example` and name the copy `.env`
   (Mac/Linux: `cp .env.example .env` / Windows: `copy .env.example .env`).
2. Open `.env` and paste your three keys in place of the `paste-your-...` text.

`.env` is listed in `.gitignore`, so it will **never** be uploaded to GitHub.

Test it **without** posting to Discord and without writing to the log:

```bash
python main.py --dry-run
```

You should see the message printed in your terminal. When it looks good, do a real run:

```bash
python main.py
```

Check your Discord channel. The message should be there.

### Step 3: Make it run automatically on GitHub

GitHub can run the bot for you every weekday, even when your computer is off.

1. On GitHub, open this repository.
2. Click **Settings** (top menu) > **Secrets and variables** (left side) > **Actions**.
3. Click **New repository secret** and add each of these (name must match exactly):

   | Name | Value |
   |---|---|
   | `FINNHUB_API_KEY` | your Finnhub key |
   | `ANTHROPIC_API_KEY` | your Claude key |
   | `DISCORD_WEBHOOK_URL` | your Discord webhook URL |

4. **Make sure this code is on your default branch** (usually `main`). GitHub only
   runs schedules from the default branch. You can see which branch is the default
   under **Settings** > **General** > **Default branch**.
5. Test it: click the **Actions** tab > **Daily stock ideas** > **Run workflow** > **Run workflow**.
   After about a minute, you should see a green check and a Discord message.

From then on it runs automatically at **8:30 AM New York time** (7:30 AM in winter),
Monday to Friday. GitHub sometimes starts scheduled runs a few minutes late. That's normal.

Each run also saves `picks_log.csv` back into the repository, so the log builds up over time.

### Step 4: Turn on the dashboard web page

The dashboard is a free web page hosted by GitHub (a feature called GitHub Pages).
You only set this up once:

1. On GitHub, open this repository and click **Settings**.
2. On the left, click **Pages**.
3. Under **Build and deployment** > **Source**, choose **Deploy from a branch**.
4. Under **Branch**, choose `main` and the folder `/docs`, then click **Save**.
5. Wait a minute or two, then refresh that page. A link appears at the top, like
   `https://<your-username>.github.io/Stock-Recommender-/`. Bookmark it.

The page updates itself after every weekday run. Note: anyone with the link can
see it (your API keys are never on it).

To preview it on your computer, run `python build_dashboard.py`, then double-click
`docs/index.html` to open it in your browser.

**News photos:** the News tab and each pick show the photo and link from the news
story behind it. Photos load straight from the news sites, so a few may be missing.

**Top 5 buys of the day:** the Today tab starts with Claude's 5 most promising
bullish ideas, ranked. Click **Show more info** on any of them to see why it could
be a good buy, what could go wrong, what to watch next, and the news story behind
it. Every top buy is also saved to `picks_log.csv`, so the scorecard tracks them too.
The Results tab has a **How the Top 5 Did** section comparing them with the other
picks, and The Record can be filtered to **Top 5 buys only**.

**Getting around:** the strip under the menu shows how the big market funds and
stocks moved on the latest day. Click any of them for its chart. Use **Find a stock**
(top right) to open any stock's chart, and the ‹ › buttons in the chart popup to
flip through them. The daily Discord message links to the dashboard. To use a
different address, add a `DASHBOARD_URL` secret.

**Fact sheets and My Stocks:** every chart popup has a fact sheet from Yahoo Finance
(company size, P/E ratio, 52-week range, dividend, analysts' price target). Tap the ☆
on any stock to add it to **My Stocks**. Starred stocks lead the markets strip and
have their own view on the Stock Charts tab. Stars are saved in your browser, so
each device keeps its own list.

**Big-move alerts:** every hour while the market is open, the bot checks its picks
from the last 5 days it ran. If one has moved 5% or more since it was picked, you get
a Discord ping saying whether the move is with or against the call. It pings again
only if the move keeps growing (10%, 15%...). To change the 5%, edit `ALERT_STEP` in
`alerts.py`. To test it: **Actions** tab > **Big-move alerts** > **Run workflow**.

**How the bot learns:** each morning Claude also gets (1) company news for the
market-watch stocks and anything picked in the last 5 days, (2) the market's biggest
gainers, losers and most-traded stocks, plus pre-market moves, and (3) its own track
record: which recent calls were right or wrong. It writes a one-line **self-check**
about what it learned, which appears on the Today tab and in Discord. All of this is
still one Claude request, and it adds about 2-3 cents a day. If any of the extras
fail, the bot carries on without them and says so in the message.

**Sectors and Coming Up:** the bottom of the Today tab has a heat map of the 11 market
sectors (switch between day, week, month and 3 months) and a calendar of upcoming
earnings dates and Fed meetings. The sector list and Fed dates live in `watchlist.py`.
Add next year's Fed dates there each December.

**Evening recap:** every weekday at about 5:15 PM New York time (4:15 PM in winter),
a second automatic run posts how the morning's picks actually moved and refreshes
the dashboard with closing prices. On Fridays it adds a week-in-review report card.
The Results tab keeps a **Weekly Report Card** for every week, graded A-F on the
share of calls that were right. The Results tab also runs **The $10,000 Test**: what
$10,000 would be worth if you'd split it across each day's Top 5 (held until the next
Top 5), next to just buying the S&P 500. It ignores trading costs and taxes, so treat
it as a rough check. To test the recap: **Actions** tab > **Evening recap** >
**Run workflow**. To preview it on your computer: `python recap.py --dry-run`.

**How the scorecard works:** each pick is compared with the latest closing price.
A bullish call is "right so far" if the stock is up since it was picked; a bearish
call if it's down. New picks show "Too early to tell" until the next market close.

---

## Changing things

- **Run time:** edit the `cron:` line in `.github/workflows/daily.yml`. The time is in UTC.
  `"30 12 * * 1-5"` means 12:30 UTC, Monday (1) to Friday (5).
- **Claude model:** the default is `claude-opus-5`. To use a cheaper model, add
  `CLAUDE_MODEL=claude-sonnet-5` to `.env`, and add a GitHub secret named
  `CLAUDE_MODEL` with the same value.
- **Number of headlines:** change `MAX_HEADLINES` in `news.py`.
- **What Claude looks for:** edit `SYSTEM_PROMPT` in `analyzer.py`.
- **Market watch stocks:** edit `watchlist.py` (one line per stock: `"TICKER": "Name",`). Claude
  writes a one-sentence note for each one in the same daily request.

## Cost

Finnhub, yfinance, Discord and GitHub Actions are free for this use.
Claude is the only paid part: one request per weekday with about 60 headlines.
That usually costs around 8-15 cents per run, which adds up to roughly $2-4
a month on `claude-opus-5`, and less on `claude-sonnet-5`. You can see exact usage at
https://console.anthropic.com under **Usage**.

## Running the tests

```bash
pip install pytest
python -m pytest
```

These use fake data, so they don't need keys and don't cost anything.

## Troubleshooting

| Problem | What to check |
|---|---|
| `FINNHUB_API_KEY is not set` | Is the `.env` file named exactly `.env` (not `.env.txt`)? On GitHub, is the secret added? |
| `News (Finnhub) failed: 401` | The Finnhub key is wrong. Copy it again from your dashboard. |
| `Analysis (Claude) failed: ... credit balance` | Add credit at console.anthropic.com > Billing. |
| `Discord returned 404` | The webhook was deleted or the URL is wrong. Make a new one. |
| `Couldn't get prices for: XYZ` | Yahoo didn't recognize that ticker. The idea is still logged, just without a price. |
| GitHub run fails at "Save picks_log.csv" | Settings > Actions > General > Workflow permissions > choose **Read and write permissions**. |
