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

## Key implementation notes

- `write_index` in `crawler.py` scans `data/{ETF_ID}/*.csv` subdirs and links `prices_file` per date — must be run after every crawl
- `diff.py` uses `IGNORE = {"Price"}` so price fluctuations don't appear as holding changes
- `prices.py` uses `resp.encoding = "big5"` (fubon page declares charset=big5)
- Price sanitization strips commas/spaces and validates as positive number
- Dashboard caches loaded CSVs in `csvCache` — keyed by `{etfId}_{date}`
- On mobile, `renderTable()` checks `isMobile()` and renders card list instead of `<table>`
