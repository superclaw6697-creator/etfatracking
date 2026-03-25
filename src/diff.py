import csv
from datetime import date, timedelta
from pathlib import Path
from typing import Optional


def _load_csv(path: Path) -> dict[str, dict]:
    """Load CSV and return dict keyed by first column (stock code)."""
    holdings = {}
    with open(path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            key = list(row.values())[0]  # first column = stock code
            if key:
                holdings[key] = row
    return holdings


def _find_csv(etf_id: str, target_date: date, data_dir: Path) -> Optional[Path]:
    date_str = target_date.strftime("%Y_%m_%d")
    path = data_dir / etf_id / f"{date_str}.csv"
    return path if path.exists() else None


def _find_previous_csv(etf_id: str, today: date, data_dir: Path) -> Optional[Path]:
    """Find the most recent CSV before today (up to 7 days back)."""
    for days_back in range(1, 8):
        candidate = today - timedelta(days=days_back)
        path = _find_csv(etf_id, candidate, data_dir)
        if path:
            return path
    return None


def compute_diff(etf_id: str, data_dir: Path, today: Optional[date] = None) -> dict:
    if today is None:
        today = date.today()

    today_path = _find_csv(etf_id, today, data_dir)
    prev_path = _find_previous_csv(etf_id, today, data_dir)

    result = {
        "etf_id": etf_id,
        "today": today.strftime("%Y-%m-%d"),
        "today_path": str(today_path) if today_path else None,
        "prev_path": str(prev_path) if prev_path else None,
        "added": [],
        "removed": [],
        "changed": [],
        "error": None,
    }

    if today_path is None:
        result["error"] = f"今日資料不存在 ({today.strftime('%Y_%m_%d')}.csv)"
        return result

    if prev_path is None:
        result["error"] = "找不到前一個交易日資料（無法比較）"
        return result

    today_holdings = _load_csv(today_path)
    prev_holdings = _load_csv(prev_path)

    today_codes = set(today_holdings.keys())
    prev_codes = set(prev_holdings.keys())

    for code in sorted(today_codes - prev_codes):
        result["added"].append(today_holdings[code])

    for code in sorted(prev_codes - today_codes):
        result["removed"].append(prev_holdings[code])

    IGNORE = {"Price"}
    for code in sorted(today_codes & prev_codes):
        t = {k: v for k, v in today_holdings[code].items() if k not in IGNORE}
        p = {k: v for k, v in prev_holdings[code].items() if k not in IGNORE}
        if t != p:
            result["changed"].append({
                "prev": prev_holdings[code],
                "today": today_holdings[code],
            })

    return result


def diff_all(etf_ids: list[str], data_dir: Path, today: Optional[date] = None) -> list[dict]:
    return [compute_diff(etf_id, data_dir, today) for etf_id in etf_ids]
