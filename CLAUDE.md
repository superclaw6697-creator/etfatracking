# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this does

Crawls ETF holdings from moneydj.com daily, saves date-stamped CSVs to `data/`, computes day-over-day diffs, sends a Telegram notification, and serves a static visualization dashboard on GitHub Pages.

## Commands

```bash
# Local development
cp .env.example .env          # fill in tokens
pip install -r requirements.txt

python main.py fetch           # crawl today's holdings → data/{ETF_ID}/*.csv
python main.py diff            # compare today vs yesterday → Telegram
python main.py all             # fetch + diff (default)

# Local dashboard preview
python3 -m http.server 8000    # open http://localhost:8000/dashboard.html

# Docker
docker build -t etf-tracker .
docker run --env-file .env -v $PWD/data:/app/data etf-tracker all
```

## Architecture

### Data pipeline (Python)

- `config/etfs.txt` — one ETF ID per line (e.g. `00981A`)
- `data/{ETF_ID}/{YYYY_MM_DD}.csv` — daily holdings snapshots per ETF
- `data/prices_{YYYY_MM_DD}.json` — `{code: price}` flat lookup for all TW stocks that day
- `data/index.json` — manifest of all CSV files + prices files; rebuilt on every crawl
- `src/crawler.py` — fetches `basic0007b.xdjhtm?etfid={ID}.tw`, parses holdings table, fetches prices, saves CSVs + price JSON, rebuilds index
- `src/prices.py` — fetches 收盤價 from `fubon-ebrokerdj.fbs.com.tw` (Big5 encoding, find `<td>收盤價</td>`, take next sibling)
- `src/diff.py` — compares today vs most recent previous CSV (up to 7 days back); **excludes `Price` column** from change comparison to avoid false positives
- `src/notify.py` — sends Telegram message via Bot API
- `main.py` — entry point, loads `.env` via python-dotenv

### CSV format

Fields: `股票代號, 個股名稱, 投資比例(%), 持有股數, Price`

The first column (`股票代號`) is the key used for diffing. `Price` is today's closing price (TWD), empty for non-TW stocks.

### Dashboard (static HTML)

- `dashboard.html` — single-file SPA, loads data via `fetch()` from `data/`
- `index.html` — meta-refresh redirect to `dashboard.html` (for GitHub Pages root)
- Data flow: `index.json` → per-ETF CSVs → `prices_{date}.json` for price change badges
- Price change: `pricePct = (today_price - prev_price) / prev_price * 100`; `pct > 0` → red ▲ (up), `pct < 0` → green ▼ (down) — **Taiwan convention: red = rise, green = fall**
- Clicking TW stocks opens `https://ytdf.yuanta.com.tw/prod/YesiDmz/StockPreview/{code}`
- URL routing: `?q={ETF_ID}` opens that ETF directly (case-insensitive); `history.pushState` on navigation
- RWD: sidebar collapses on mobile; table replaced by card list on mobile (≤ 640px); sticky topbar with ☰ toggle + ETF dropdown

## GitHub Actions

Workflow at `.github/workflows/daily.yml` runs weekdays at 15:00 Taiwan time (07:00 UTC). Builds the Docker image, mounts `data/` as a volume, then commits any new CSVs.

Required secrets: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`.

GitHub Pages: `https://superclaw6697-creator.github.io/etfatracking/`

## Local cron jobs (crontab, not LaunchAgents)

- `30 19 * * 1-5` → `trigger_workflow.sh` — manually triggers the GH Actions workflow (redundant with its own 15:00 UTC schedule, kept as a backup trigger)
- `30 22 * * 1-5` → `backfill_and_push.sh` — re-fetches **today's** holdings and overwrites if moneydj.com hadn't published finalized data yet when the 19:30 evening crawl ran (moneydj sometimes lags). Pulls first before committing to avoid conflicting with the GH Actions commit for the same date — **always keep this `git pull` step**, removing it reintroduces recurring add/add merge conflicts on the day's CSV files.
- `backfill_last_trading_day.py` — the actual re-fetch logic; target date is always `date.today()` since the cron runs same-night, not next-morning

## daily_report.js — analysis skill entry point

`node daily_report.js [YYYY-MM-DD]` — git pulls, reads the latest (or given) date's human-readable diff log from `logs/YYYY-MM/YYYY-MM-DD.txt`, and fetches live premium/discount for 00981A/00991A/00403A via `../projects/fetch_etf_premium.js`. Prints combined JSON to stdout. Used by the `etf-daily-report` Claude skill (`~/.claude/skills/etf-daily-report/skill.md`) to generate a Telegram-pushed daily summary — highlights cross-ETF synchronized buys/sells (the "📊 跨 ETF 同步異動" block at the end of each day's log) as the strongest signal, since that means multiple active-fund managers moved on the same stock the same day.

## Key implementation notes

- `write_index` in `crawler.py` scans `data/{ETF_ID}/*.csv` subdirs and links `prices_file` per date — must be run after every crawl
- `diff.py` uses `IGNORE = {"Price"}` so price fluctuations don't appear as holding changes
- `prices.py` uses `resp.encoding = "big5"` (fubon page declares charset=big5)
- Price sanitization strips commas/spaces and validates as positive number
- Dashboard caches loaded CSVs in `csvCache` — keyed by `{etfId}_{date}`
- On mobile, `renderTable()` checks `isMobile()` and renders card list instead of `<table>`
