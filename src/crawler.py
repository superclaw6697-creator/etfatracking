import csv
import re
import time
from datetime import date
from pathlib import Path
from typing import Optional

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.moneydj.com/etf/x/basic/basic0007b.xdjhtm?etfid={etf_id}.tw"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
    "Referer": "https://www.moneydj.com/",
}


def _extract_code(name_cell: str) -> str:
    """Extract stock code from '台積電(2330.TW)' → '2330'."""
    m = re.search(r"\(([^)]+)\)", name_cell)
    if m:
        return m.group(1).split(".")[0]
    return name_cell


def fetch_holdings(etf_id: str) -> list[dict]:
    url = BASE_URL.format(etf_id=etf_id)
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"

    soup = BeautifulSoup(resp.text, "lxml")

    # Find the individual holdings table (contains 個股名稱 header)
    table = None
    for t in soup.find_all("table", class_="datalist"):
        header_text = t.find("tr")
        if header_text and "個股名稱" in header_text.get_text():
            table = t
            break

    if table is None:
        raise ValueError(f"Could not find holdings table for {etf_id}")

    rows = table.find_all("tr")
    if not rows:
        raise ValueError(f"No rows found in holdings table for {etf_id}")

    holdings = []
    for row in rows[1:]:
        cells = row.find_all("td")
        if not cells or len(cells) < 2:
            continue
        name_text = cells[0].get_text(strip=True)
        if not name_text:
            continue
        record = {
            "股票代號": _extract_code(name_text),
            "個股名稱": name_text,
            "投資比例(%)": cells[1].get_text(strip=True) if len(cells) > 1 else "",
            "持有股數": cells[2].get_text(strip=True) if len(cells) > 2 else "",
        }
        holdings.append(record)

    return holdings


def save_csv(etf_id: str, holdings: list[dict], data_dir: Path, today: Optional[date] = None) -> Path:
    if today is None:
        today = date.today()
    date_str = today.strftime("%Y_%m_%d")
    filename = data_dir / f"{etf_id}_{date_str}.csv"

    if not holdings:
        raise ValueError(f"No holdings data to save for {etf_id}")

    fieldnames = list(holdings[0].keys())
    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(holdings)

    return filename


def crawl_all(etf_ids: list[str], data_dir: Path, today: Optional[date] = None) -> dict[str, Path]:
    results = {}
    for i, etf_id in enumerate(etf_ids):
        print(f"[crawler] Fetching {etf_id}...")
        try:
            holdings = fetch_holdings(etf_id)
            path = save_csv(etf_id, holdings, data_dir, today)
            print(f"[crawler] Saved {len(holdings)} holdings → {path}")
            results[etf_id] = path
        except Exception as e:
            print(f"[crawler] ERROR {etf_id}: {e}")
        if i < len(etf_ids) - 1:
            time.sleep(1)  # polite delay between requests
    return results
