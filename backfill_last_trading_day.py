"""Re-fetch and overwrite the most recent trading day's ETF holdings.

Run the morning after the regular evening crawl. If moneydj.com hadn't
published the day's finalized holdings yet when the 19:30 crawl ran, this
catches the corrected data and overwrites the stale CSVs (no diff/notify —
just a silent correction of the historical record).
"""
from datetime import date, timedelta
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from src.crawler import crawl_all

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
CONFIG_FILE = ROOT / "config" / "etfs.txt"


def last_business_day(from_date: date) -> date:
    d = from_date - timedelta(days=1)
    while d.weekday() >= 5:  # Sat=5, Sun=6
        d -= timedelta(days=1)
    return d


def main() -> None:
    etf_ids = [
        line.strip()
        for line in CONFIG_FILE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]
    target = last_business_day(date.today())
    print(f"[backfill] Re-fetching and overwriting {target.isoformat()}...")
    crawl_all(etf_ids, DATA_DIR, today=target)


if __name__ == "__main__":
    main()
