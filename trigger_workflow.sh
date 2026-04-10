#!/bin/bash
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
source /Users/superclaw/etf_tracking/.env
export GH_TOKEN
/opt/homebrew/bin/gh workflow run "ETF Holdings Tracker" --repo superclaw6697-creator/etfatracking
