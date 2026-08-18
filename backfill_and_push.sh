#!/bin/bash
set -e
cd /Users/superclaw/etf_tracking
/opt/homebrew/bin/python3 backfill_last_trading_day.py
git add data/
if ! git diff --staged --quiet; then
  git commit -m "data: morning backfill correction $(date +%Y-%m-%d)"
  git push
else
  echo "[backfill] No changes to commit."
fi
