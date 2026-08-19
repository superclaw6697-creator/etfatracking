"""Re-fetch and overwrite today's ETF holdings.

Run later the same evening as the regular 19:30 crawl (cron: 22:30 weekdays).
If moneydj.com hadn't published the day's finalized holdings yet when the
19:30 crawl ran, this catches the corrected data and overwrites the stale
CSVs (no diff/notify — just a silent correction of the historical record).

Only runs on weekdays (cron restricts to Mon-Fri), so "today" is always the
trading day being corrected.
"""
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from src.crawler import crawl_all

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
CONFIG_FILE = ROOT / "config" / "etfs.txt"


def main() -> None:
    etf_ids = [
        line.strip()
        for line in CONFIG_FILE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]
    target = date.today()
    print(f"[backfill] Re-fetching and overwriting {target.isoformat()}...")
    crawl_all(etf_ids, DATA_DIR, today=target)


if __name__ == "__main__":
    main()
