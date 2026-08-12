import json
from pathlib import Path
from typing import Optional


def _load_all_logs(logs_dir: Path) -> list[dict]:
    """Load every logs/{date}.json, tagging each diff with its date."""
    records = []
    for path in sorted(logs_dir.glob("*.json")):
        date_str = path.stem
        diffs = json.loads(path.read_text(encoding="utf-8"))
        for d in diffs:
            d["_date"] = date_str
            records.append(d)
    return records


def query_stock(logs_dir: Path, code: str, etf_id: Optional[str] = None) -> list[dict]:
    """Find every buy/sell/new/removed event for a stock code across all saved logs."""
    events = []
    for diff in _load_all_logs(logs_dir):
        if diff.get("error"):
            continue
        if etf_id and diff["etf_id"] != etf_id:
            continue

        for row in diff.get("added", []):
            if row.get("股票代號") == code:
                events.append({
                    "date": diff["_date"], "etf_id": diff["etf_id"], "action": "新增",
                    "shares": row.get("持有股數"), "ratio": row.get("投資比例(%)"),
                })
        for row in diff.get("removed", []):
            if row.get("股票代號") == code:
                events.append({
                    "date": diff["_date"], "etf_id": diff["etf_id"], "action": "移除",
                    "shares": row.get("持有股數"), "ratio": row.get("投資比例(%)"),
                })
        for entry in diff.get("changed", []):
            prev, today = entry["prev"], entry["today"]
            if prev.get("股票代號") == code:
                p_shares = prev.get("持有股數", "0")
                t_shares = today.get("持有股數", "0")
                events.append({
                    "date": diff["_date"], "etf_id": diff["etf_id"], "action": "增持" if _num(t_shares) > _num(p_shares) else "減持",
                    "shares": f"{p_shares} → {t_shares}", "ratio": today.get("投資比例(%)"),
                })

    events.sort(key=lambda e: e["date"])
    return events


def _num(s: str) -> float:
    try:
        return float(str(s).replace(",", ""))
    except (ValueError, AttributeError):
        return 0.0


def query_etf_history(logs_dir: Path, etf_id: str) -> list[dict]:
    """All logged diff events for one ETF, across every saved date."""
    return [d for d in _load_all_logs(logs_dir) if d["etf_id"] == etf_id]
