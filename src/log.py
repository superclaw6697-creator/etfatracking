import json
from pathlib import Path

from .notify import format_cross_etf_summary, format_diff_message


def save_daily_log(diffs: list[dict], logs_dir: Path, today_str: str) -> None:
    """Persist today's diffs as JSON (queryable) + formatted text (human-readable, git-diff-friendly)."""
    logs_dir.mkdir(exist_ok=True)

    json_path = logs_dir / f"{today_str}.json"
    json_path.write_text(json.dumps(diffs, ensure_ascii=False, indent=2), encoding="utf-8")

    parts = [format_diff_message(d) for d in diffs]
    summary = format_cross_etf_summary(diffs)
    if summary:
        parts.append(summary)
    text = "\n\n".join(parts)
    # Strip Telegram HTML tags for a plain-text log
    text = text.replace("<b>", "").replace("</b>", "")

    txt_path = logs_dir / f"{today_str}.txt"
    txt_path.write_text(text, encoding="utf-8")
