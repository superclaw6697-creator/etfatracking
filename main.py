import sys
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
LOGS_DIR = ROOT / "logs"
CONFIG_FILE = ROOT / "config" / "etfs.txt"

DATA_DIR.mkdir(exist_ok=True)


def load_etf_ids() -> list[str]:
    ids = []
    for line in CONFIG_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            ids.append(line)
    return ids


def cmd_fetch(etf_ids: list[str]) -> None:
    from src.crawler import crawl_all
    crawl_all(etf_ids, DATA_DIR)


def cmd_diff(etf_ids: list[str]) -> None:
    from src.diff import diff_all
    from src.log import save_daily_log
    from src.notify import send_diffs
    diffs = diff_all(etf_ids, DATA_DIR)
    for d in diffs:
        if d.get("error"):
            print(f"[diff] {d['etf_id']}: {d['error']}")
        else:
            print(f"[diff] {d['etf_id']}: +{len(d['added'])} -{len(d['removed'])} ~{len(d.get('changed', []))}")
    save_daily_log(diffs, LOGS_DIR, date.today().strftime("%Y-%m-%d"))
    send_diffs(diffs)


def cmd_query(code: str, etf_id: str | None) -> None:
    from src.query import query_stock
    events = query_stock(LOGS_DIR, code, etf_id)
    if not events:
        print(f"No events found for {code}" + (f" in {etf_id}" if etf_id else ""))
        return
    for e in events:
        print(f"{e['date']}  {e['etf_id']}  {e['action']}  {e['shares']}  ({e['ratio']}%)")


def main() -> None:
    command = sys.argv[1] if len(sys.argv) > 1 else "all"
    etf_ids = load_etf_ids()

    if not etf_ids:
        print("No ETF IDs found in config/etfs.txt")
        sys.exit(1)

    print(f"[main] ETFs: {etf_ids}")

    if command == "fetch":
        cmd_fetch(etf_ids)
    elif command == "diff":
        cmd_diff(etf_ids)
    elif command == "all":
        cmd_fetch(etf_ids)
        cmd_diff(etf_ids)
    elif command == "query":
        if len(sys.argv) < 3:
            print("Usage: python main.py query <stock_code> [etf_id]")
            sys.exit(1)
        code = sys.argv[2]
        etf_id = sys.argv[3] if len(sys.argv) > 3 else None
        cmd_query(code, etf_id)
    else:
        print(f"Unknown command: {command}. Use fetch / diff / all / query")
        sys.exit(1)


if __name__ == "__main__":
    main()
