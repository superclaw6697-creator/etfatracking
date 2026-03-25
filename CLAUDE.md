# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this does

Crawls ETF holdings from moneydj.com daily, saves date-stamped CSVs to `data/`, and sends a Telegram diff (added/removed holdings vs previous day). Runs on GitHub Actions via Docker.

## Commands

```bash
# Local development
cp .env.example .env          # fill in tokens
pip install -r requirements.txt

python main.py fetch           # crawl today's holdings → data/*.csv
python main.py diff            # compare today vs yesterday → Telegram
python main.py all             # fetch + diff (default)

# Docker
docker build -t etf-tracker .
docker run --env-file .env -v $PWD/data:/app/data etf-tracker fetch
docker run --env-file .env -v $PWD/data:/app/data etf-tracker all
```

## Architecture

- `config/etfs.txt` — one ETF ID per line (e.g. `00981A`)
- `data/` — CSV snapshots named `{ETF_ID}_{YYYY}_{MM}_{DD}.csv`
- `src/crawler.py` — fetches `basic0007.xdjhtm?etfid={ID}.tw`, parses holdings table with BeautifulSoup
- `src/diff.py` — compares today vs most recent previous CSV (up to 7 days back)
- `src/notify.py` — sends Telegram message via Bot API
- `main.py` — entry point, loads `.env` via python-dotenv

## GitHub Actions

Workflow at `.github/workflows/daily.yml` runs weekdays at 15:00 Taiwan time (07:00 UTC). Builds the Docker image, mounts `data/` as a volume, then commits any new CSVs.

Required secrets in repo Settings → Secrets: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`.

## Crawler notes

The moneydj.com holdings table uses `id="oMainTable"`. If the page structure changes, `crawler.py` has a fallback that searches for any table containing 持股/股票代號 in its text. The first column of each CSV row is treated as the stock code key for diffing.
