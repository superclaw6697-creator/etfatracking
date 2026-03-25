import os

import requests


def _send(token: str, chat_id: str, text: str) -> None:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
    }
    resp = requests.post(url, json=payload, timeout=15)
    resp.raise_for_status()


def _format_row(row: dict) -> str:
    values = list(row.values())
    # Show code + name + up to 2 more fields (ratio, shares)
    parts = values[:4]
    return "  " + "  ".join(str(v) for v in parts if v)


def _parse_num(s: str) -> float:
    try:
        return float(s.replace(",", ""))
    except (ValueError, AttributeError):
        return 0.0


def _format_change(entry: dict) -> str:
    prev, today = entry["prev"], entry["today"]
    code = prev["股票代號"]
    name = prev["個股名稱"]
    fields = [k for k in prev if k != "股票代號" and k != "個股名稱"]
    parts = []
    for f in fields:
        p, t = prev.get(f, ""), today.get(f, "")
        if p != t:
            parts.append(f"{f}: {p} → {t}")
    return f"  {code} {name}  " + "  ".join(parts)


def _classify_changed(changed: list) -> tuple:
    """Split changed entries into (增持, 減持, 其他) based on 持有股數."""
    increased, decreased, other = [], [], []
    for entry in changed:
        prev_shares = _parse_num(entry["prev"].get("持有股數", "0"))
        today_shares = _parse_num(entry["today"].get("持有股數", "0"))
        if today_shares > prev_shares:
            increased.append(entry)
        elif today_shares < prev_shares:
            decreased.append(entry)
        else:
            other.append(entry)
    return increased, decreased, other


def format_diff_message(diff: dict) -> str:
    etf_id = diff["etf_id"]
    today = diff["today"]

    if diff.get("error"):
        return f"<b>{etf_id}</b> ({today})\n⚠️ {diff['error']}"

    added = diff["added"]
    removed = diff["removed"]
    changed = diff.get("changed", [])

    if not added and not removed and not changed:
        return f"<b>{etf_id}</b> ({today})\n✅ 持股無變化"

    lines = [f"<b>{etf_id}</b> ({today})"]

    if added:
        lines.append(f"\n🟢 新增 {len(added)} 檔：")
        for row in added:
            lines.append(_format_row(row))

    if removed:
        lines.append(f"\n🔴 移除 {len(removed)} 檔：")
        for row in removed:
            lines.append(_format_row(row))

    if changed:
        increased, decreased, other = _classify_changed(changed)
        if increased:
            lines.append(f"\n📈 增持 {len(increased)} 檔：")
            for entry in increased:
                lines.append(_format_change(entry))
        if decreased:
            lines.append(f"\n📉 減持 {len(decreased)} 檔：")
            for entry in decreased:
                lines.append(_format_change(entry))
        if other:
            lines.append(f"\n🔄 其他異動 {len(other)} 檔：")
            for entry in other:
                lines.append(_format_change(entry))

    return "\n".join(lines)


def send_diffs(diffs: list[dict]) -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        print("[notify] TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set, skipping notification")
        return

    message = "\n\n".join(format_diff_message(d) for d in diffs)
    print(f"[notify] Sending combined diff for {[d['etf_id'] for d in diffs]}...")
    try:
        _send(token, chat_id, message)
    except Exception as e:
        print(f"[notify] ERROR sending message: {e}")
