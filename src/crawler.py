import csv
import json
import re
import time
from datetime import date, datetime
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

FIELDNAMES = ["股票代號", "個股名稱", "投資比例(%)", "持有股數", "Price"]


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
            "Price": "",
        }
        holdings.append(record)

    return holdings


def save_csv(etf_id: str, holdings: list[dict], data_dir: Path, today: Optional[date] = None) -> Path:
    if today is None:
        today = date.today()
    etf_dir = data_dir / etf_id
    etf_dir.mkdir(exist_ok=True)
    filename = etf_dir / f"{today.strftime('%Y_%m_%d')}.csv"

    if not holdings:
        raise ValueError(f"No holdings data to save for {etf_id}")

    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(holdings)

    return filename


def save_prices_json(prices: dict[str, str], data_dir: Path, today: Optional[date] = None) -> Path:
    """Save {code: price} mapping to prices_{date}.json."""
    if today is None:
        today = date.today()
    path = data_dir / f"prices_{today.strftime('%Y_%m_%d')}.json"
    path.write_text(json.dumps(prices, ensure_ascii=False), encoding="utf-8")
    print(f"[prices] Saved price index → {path}")
    return path


def write_index(data_dir: Path) -> None:
    """Scan data_dir for ETF CSVs and prices JSONs, write index.json."""
    # Collect prices files: prices_{date}.json → date string
    price_dates: dict[str, str] = {}
    for f in data_dir.glob("prices_*.json"):
        m = re.match(r"^prices_(\d{4})_(\d{2})_(\d{2})$", f.stem)
        if m:
            d = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
            price_dates[d] = f.name

    entries = []
    for etf_dir in sorted(d for d in data_dir.iterdir() if d.is_dir()):
        etf_id = etf_dir.name
        for f in sorted(etf_dir.glob("*.csv")):
            m = re.match(r"^(\d{4})_(\d{2})_(\d{2})$", f.stem)
            if not m:
                continue
            date_str = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
            entry: dict = {"etf": etf_id, "date": date_str, "file": f"{etf_id}/{f.name}"}
            if date_str in price_dates:
                entry["prices_file"] = price_dates[date_str]
            entries.append(entry)

    index = {"files": entries, "updated": datetime.now().isoformat(timespec="seconds")}
    out = data_dir / "index.json"
    out.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[index] Written {len(entries)} entries → {out}")


def crawl_all(etf_ids: list[str], data_dir: Path, today: Optional[date] = None) -> dict[str, Path]:
    # ── Step 1: fetch all holdings ──────────────────────────────────────────
    all_holdings: dict[str, list[dict]] = {}
    for i, etf_id in enumerate(etf_ids):
        print(f"[crawler] Fetching {etf_id}...")
        try:
            holdings = fetch_holdings(etf_id)
            all_holdings[etf_id] = holdings
            print(f"[crawler] Got {len(holdings)} holdings for {etf_id}")
        except Exception as e:
            print(f"[crawler] ERROR {etf_id}: {e}")
        if i < len(etf_ids) - 1:
            time.sleep(1)

    # ── Step 2: fetch prices for unique TW stocks ────────────────────────────
    try:
        from src.prices import fetch_prices
        tw_codes = list(dict.fromkeys(
            h["股票代號"]
            for holdings in all_holdings.values()
            for h in holdings
            if re.match(r"^\d{4,5}$", h["股票代號"])
        ))
        prices = fetch_prices(tw_codes, delay=0.5)
        # Stamp each holding with its price
        for holdings in all_holdings.values():
            for h in holdings:
                h["Price"] = prices.get(h["股票代號"], "")
        # Save standalone price index JSON
        save_prices_json(prices, data_dir, today)
    except Exception as e:
        print(f"[prices] Skipped: {e}")

    # ── Step 3: save CSVs ────────────────────────────────────────────────────
    results: dict[str, Path] = {}
    for etf_id, holdings in all_holdings.items():
        try:
            path = save_csv(etf_id, holdings, data_dir, today)
            print(f"[crawler] Saved → {path}")
            results[etf_id] = path
        except Exception as e:
            print(f"[crawler] Save ERROR {etf_id}: {e}")

    # ── Step 4: write index ──────────────────────────────────────────────────
    try:
        write_index(data_dir)
    except Exception as e:
        print(f"[index] ERROR: {e}")

    return results
