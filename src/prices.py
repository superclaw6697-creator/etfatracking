"""Fetch daily closing prices from fubon-ebrokerdj for TW-listed stocks."""
import re
import time
from typing import Optional

import requests
from bs4 import BeautifulSoup

PRICE_URL = "https://fubon-ebrokerdj.fbs.com.tw/Z/ZC/ZCX/ZCX_{code}.djhtm"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-TW,zh;q=0.9",
}


def _sanitize_price(raw: str) -> Optional[str]:
    """Strip commas/spaces and validate as a positive number."""
    cleaned = raw.replace(",", "").replace(" ", "").strip()
    if re.match(r"^\d+(\.\d+)?$", cleaned) and float(cleaned) > 0:
        return cleaned
    return None


def fetch_price(code: str) -> Optional[str]:
    """Fetch 收盤價 for one TW stock code. Returns sanitized price string or None."""
    try:
        resp = requests.get(PRICE_URL.format(code=code), headers=HEADERS, timeout=15)
        resp.encoding = "big5"
        soup = BeautifulSoup(resp.text, "lxml")
        for td in soup.find_all("td"):
            if td.get_text(strip=True) == "收盤價":
                next_td = td.find_next_sibling("td")
                if next_td:
                    return _sanitize_price(next_td.get_text(strip=True))
    except Exception as e:
        print(f"[prices] {code}: {e}")
    return None


def fetch_prices(codes: list[str], delay: float = 0.4) -> dict[str, str]:
    """
    Fetch closing prices for all TW stock codes (4–5 digit numeric).
    Returns {code: price_str}. Failed / non-TW codes are omitted.
    """
    tw_codes = [c for c in dict.fromkeys(codes) if re.match(r"^\d{4,5}$", c)]
    if not tw_codes:
        return {}

    print(f"[prices] Fetching {len(tw_codes)} TW stock prices…")
    results: dict[str, str] = {}

    for i, code in enumerate(tw_codes):
        price = fetch_price(code)
        if price:
            results[code] = price
        if i < len(tw_codes) - 1:
            time.sleep(delay)

    print(f"[prices] Got {len(results)}/{len(tw_codes)} prices")
    return results
