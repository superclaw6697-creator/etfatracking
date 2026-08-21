#!/usr/bin/env node
/**
 * daily_report.js — ETF 每日持股變動 + 折溢價 一站式資料收集
 *
 * 用途：
 *   1. git pull 到最新
 *   2. 讀出 logs/ 底下最新一天的持股異動 JSON log（結構化：added/removed/changed，含新舊股數與股價）
 *   3. 針對全部 ETF 算出「跨 ETF 淨買超排行」（單位：張）
 *   4. 針對「全部」有追蹤的 ETF，算出資金流排行（把股價漲跌造成的規模變化，跟
 *      經理人實際加減碼造成的規模變化分開估算），找出今天資金流入/流出最多的基金
 *   5. 針對三檔主動式旗艦 ETF（00981A/00991A/00403A）算出深度數據：
 *      - 加碼/減碼 Top N（張數、個股當日股價漲跌%）
 *      - 是否為「清倉式減碼」（今日剩餘部位 < 清倉門檻）
 *      - 估算 AUM（用當日全持股 市值加總 / 已投資權重% 反推，含現金部位）及較前一日增減方向
 *   6. 呼叫 fetch_etf_premium.js 抓這三檔的即時折溢價
 *   7. 印出一份 JSON，供上層（Claude / skill）讀取後做分析與 Telegram 推播
 *
 * Usage:
 *   node daily_report.js              # 自動找最新一天的 log
 *   node daily_report.js 2026-08-19   # 指定日期
 */

const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');

const ROOT = __dirname;
const DATA_DIR = path.join(ROOT, 'data');
const LOGS_DIR = path.join(ROOT, 'logs');
const CONFIG_FILE = path.join(ROOT, 'config', 'etfs.txt');
const PREMIUM_SCRIPT = path.join(path.dirname(ROOT), 'projects', 'fetch_etf_premium.js');
const TARGET_ETFS = ['00981A', '00991A', '00403A'];
const LOT_SIZE = 1000; // 1 張 = 1000 股（台股）
const WIPEOUT_LOT_THRESHOLD = 10; // 減碼後剩不到 10 張 → 視為「清倉式減碼」
const NOTABLE_FLOW_PCT = 3; // |資金流動%| 超過這個門檻才標記為「顯著」機會/風險訊號

function loadAllEtfIds() {
  return fs.readFileSync(CONFIG_FILE, 'utf8').split('\n')
    .map(l => l.trim())
    .filter(l => l && !l.startsWith('#'));
}

function log(msg) {
  process.stderr.write(`[daily_report] ${msg}\n`);
}

function gitPull() {
  log('git pull...');
  try {
    const out = execSync('git pull --no-edit', { cwd: ROOT, encoding: 'utf8' });
    log(out.trim());
  } catch (e) {
    log(`git pull 失敗（繼續往下跑，用本地現有資料）: ${e.message}`);
  }
}

function findLatestLogDate() {
  const months = fs.readdirSync(LOGS_DIR)
    .filter(d => /^\d{4}-\d{2}$/.test(d))
    .sort();
  if (months.length === 0) return null;
  const latestMonth = months[months.length - 1];
  const files = fs.readdirSync(path.join(LOGS_DIR, latestMonth))
    .filter(f => f.endsWith('.json'))
    .sort();
  if (files.length === 0) return null;
  return files[files.length - 1].replace('.json', '');
}

function readJsonLog(dateStr) {
  const month = dateStr.slice(0, 7);
  const jsonPath = path.join(LOGS_DIR, month, `${dateStr}.json`);
  if (!fs.existsSync(jsonPath)) return null;
  return JSON.parse(fs.readFileSync(jsonPath, 'utf8'));
}

function parseNum(str) {
  if (str === undefined || str === null) return null;
  const n = parseFloat(String(str).replace(/,/g, ''));
  return Number.isFinite(n) ? n : null;
}

function pctChange(prevPrice, todayPrice) {
  if (prevPrice === null || todayPrice === null || prevPrice === 0) return null;
  return ((todayPrice - prevPrice) / prevPrice) * 100;
}

// 讀取一份 CSV 的全部持股，回傳陣列
function readCsvHoldings(csvPath) {
  if (!fs.existsSync(csvPath)) return null;
  // CSV 是 CRLF 換行，先統一去掉 \r 再切割，不然欄位名/欄位值最後都會黏著一個看不見的 \r
  const lines = fs.readFileSync(csvPath, 'utf8').replace(/\r/g, '').trim().split('\n');
  const header = lines[0].split(',');
  return lines.slice(1).map(line => {
    // 個股名稱可能含逗號被引號包住，用簡易 CSV parser
    const cells = [];
    let cur = '', inQuotes = false;
    for (const ch of line) {
      if (ch === '"') inQuotes = !inQuotes;
      else if (ch === ',' && !inQuotes) { cells.push(cur); cur = ''; }
      else cur += ch;
    }
    cells.push(cur);
    const row = {};
    header.forEach((h, i) => row[h] = cells[i]);
    return row;
  });
}

// 估算 ETF 總 AUM：sum(股數*股價) / (已投資權重% / 100)，含現金部位估算
function estimateAUM(holdings) {
  let marketValue = 0;
  let weightSum = 0;
  for (const h of holdings) {
    const shares = parseNum(h['持有股數']);
    const price = parseNum(h['Price']);
    const weight = parseNum(h['投資比例(%)']);
    if (shares !== null && price !== null) marketValue += shares * price;
    if (weight !== null) weightSum += weight;
  }
  if (weightSum <= 0) return null;
  return marketValue / (weightSum / 100);
}

function dateToFilename(dateStr) {
  return dateStr.replace(/-/g, '_') + '.csv';
}

function findPrevCsvPath(etfId, todayDateStr) {
  // 從 today_path 往前找最近一份存在的 CSV（跳過假日）
  const etfDir = path.join(DATA_DIR, etfId);
  if (!fs.existsSync(etfDir)) return null;
  const files = fs.readdirSync(etfDir)
    .filter(f => f.endsWith('.csv') && f < dateToFilename(todayDateStr))
    .sort();
  if (files.length === 0) return null;
  return path.join(etfDir, files[files.length - 1]);
}

// 部分發行商網站偶爾會在某天回傳格式跑掉的列（股票代號變成中文名稱、Price 是空字串）
// 這種列不是真的換股，是爬蟲當天抓到排版跑掉的雜訊
function isValidStockRow(item) {
  const code = item['股票代號'];
  if (!code) return false;
  // 台股代號通常是 4-6 碼數字（含興櫃*/KY 等後綴股名不影響代號本身），美股/日股/韓股代號則是英數混合但不會是純中文
  return !/^[一-鿿]/.test(code);
}

// 若某天的 added 列表裡混有雜訊列，代表當天爬蟲對這檔 ETF 的解析很可能整體跑掉了
// （常見情況：today 那一批列被誤判成「新增」，對應的 prev 列就會被誤判成「移除」，
//  形成假的買賣訊號）。這種情況直接整批跳過這檔 ETF 當天的異動，比只濾掉一半更安全。
function hasDataQualityIssue(entry) {
  return (entry.added || []).some(item => !isValidStockRow(item));
}

// 針對單一 ETF，組出加碼/減碼明細（含張數、個股當日漲跌%）
function buildEtfMoves(entry) {
  const moves = [];

  if (hasDataQualityIssue(entry)) {
    return { moves: [], data_quality_issue: true };
  }

  for (const item of entry.added || []) {
    const shares = parseNum(item['持有股數']);
    moves.push({
      code: item['股票代號'], name: item['個股名稱'],
      type: 'added',
      lot_delta: shares !== null ? Math.round(shares / LOT_SIZE) : null,
      today_lots: shares !== null ? Math.round(shares / LOT_SIZE) : null,
      weight_pct: parseNum(item['投資比例(%)']),
      price_pct: null
    });
  }

  for (const item of entry.removed || []) {
    const shares = parseNum(item['持有股數']);
    moves.push({
      code: item['股票代號'], name: item['個股名稱'],
      type: 'removed',
      lot_delta: shares !== null ? -Math.round(shares / LOT_SIZE) : null,
      today_lots: 0,
      weight_pct: 0,
      price_pct: null
    });
  }

  for (const c of entry.changed || []) {
    const prevShares = parseNum(c.prev['持有股數']);
    const todayShares = parseNum(c.today['持有股數']);
    const prevPrice = parseNum(c.prev['Price']);
    const todayPrice = parseNum(c.today['Price']);
    const lotDelta = (prevShares !== null && todayShares !== null)
      ? Math.round((todayShares - prevShares) / LOT_SIZE) : null;
    const todayLots = todayShares !== null ? Math.round(todayShares / LOT_SIZE) : null;
    moves.push({
      code: c.today['股票代號'], name: c.today['個股名稱'],
      type: lotDelta > 0 ? 'increased' : 'decreased',
      lot_delta: lotDelta,
      today_lots: todayLots,
      weight_pct: parseNum(c.today['投資比例(%)']),
      price_pct: pctChange(prevPrice, todayPrice),
      is_near_wipeout: (lotDelta < 0 && todayLots !== null && todayLots < WIPEOUT_LOT_THRESHOLD)
    });
  }

  moves.sort((a, b) => Math.abs(b.lot_delta || 0) - Math.abs(a.lot_delta || 0));
  return { moves, data_quality_issue: false };
}

function buildTargetEtfDetail(dateStr, entry) {
  if (!entry) return null;
  const todayCsv = path.join(DATA_DIR, entry.etf_id, dateToFilename(dateStr));
  const prevCsv = findPrevCsvPath(entry.etf_id, dateStr);

  const todayHoldings = readCsvHoldings(todayCsv);
  const prevHoldings = prevCsv ? readCsvHoldings(prevCsv) : null;

  const aumToday = todayHoldings ? estimateAUM(todayHoldings) : null;
  const aumPrev = prevHoldings ? estimateAUM(prevHoldings) : null;

  const { moves, data_quality_issue } = buildEtfMoves(entry);

  return {
    etf_id: entry.etf_id,
    moves,
    data_quality_issue,
    aum_estimate: aumToday,
    aum_prev_estimate: aumPrev,
    aum_change_pct: (aumToday !== null && aumPrev !== null && aumPrev !== 0)
      ? ((aumToday - aumPrev) / aumPrev) * 100 : null
  };
}

// 跨「全部」ETF 的淨買超排行（張數），給每檔股票標出各 ETF 的貢獻與當日股價%
function buildCrossEtfRanking(logData) {
  const byStock = {}; // code -> { name, total_lot_delta, contributions: [{etf, lot_delta}], price_pct }
  const skippedEtfs = [];

  for (const entry of logData) {
    if (entry.error) continue;
    const { moves, data_quality_issue } = buildEtfMoves(entry);
    if (data_quality_issue) { skippedEtfs.push(entry.etf_id); continue; }
    for (const m of moves) {
      if (m.lot_delta === null || m.lot_delta === 0) continue;
      if (!byStock[m.code]) {
        byStock[m.code] = { code: m.code, name: m.name, total_lot_delta: 0, contributions: [], price_pct: m.price_pct };
      }
      byStock[m.code].total_lot_delta += m.lot_delta;
      byStock[m.code].contributions.push({ etf: entry.etf_id, lot_delta: m.lot_delta });
      if (byStock[m.code].price_pct === null) byStock[m.code].price_pct = m.price_pct;
    }
  }

  const all = Object.values(byStock);
  const topBuys = all.filter(s => s.total_lot_delta > 0)
    .sort((a, b) => b.total_lot_delta - a.total_lot_delta).slice(0, 5);
  const topSells = all.filter(s => s.total_lot_delta < 0)
    .sort((a, b) => a.total_lot_delta - b.total_lot_delta).slice(0, 5);

  return { top_buys: topBuys, top_sells: topSells, skipped_etfs_data_quality: skippedEtfs };
}

// 估算「資金流」而非單純市值變化：把今天的持股數量，用「前一天的價格」重新估價，
// 這樣可以把「股價自然漲跌造成的規模變化」跟「經理人實際加減碼造成的規模變化」分開。
// 後者才是比較接近「真的有錢進來/出去」的訊號，而不是「大盤漲，所以規模變大」。
function estimateFundFlow(todayHoldings, prevHoldings) {
  if (!todayHoldings || !prevHoldings) return null;

  const prevMap = {};
  for (const h of prevHoldings) {
    const code = h['股票代號'];
    if (!code) continue;
    prevMap[code] = { shares: parseNum(h['持有股數']) || 0, price: parseNum(h['Price']) };
  }
  const todayMap = {};
  for (const h of todayHoldings) {
    const code = h['股票代號'];
    if (!code) continue;
    todayMap[code] = { shares: parseNum(h['持有股數']) || 0, price: parseNum(h['Price']) };
  }

  const allCodes = new Set([...Object.keys(prevMap), ...Object.keys(todayMap)]);
  let flow = 0;
  for (const code of allCodes) {
    const prevShares = prevMap[code]?.shares || 0;
    const todayShares = todayMap[code]?.shares || 0;
    // 估價一律用前一天的收盤價（若是全新持股、前一天沒有價格，退而求其次用當天價格）
    const refPrice = prevMap[code]?.price ?? todayMap[code]?.price;
    if (refPrice === null || refPrice === undefined) continue;
    flow += (todayShares - prevShares) * refPrice;
  }
  return flow;
}

// 針對「全部」有在追蹤的 ETF，算出資金流排行（不只三檔旗艦），用來回答
// 「整體主動式ETF裡，今天錢實際上是往哪個基金流入/流出，佔比多少」
function buildFundFlowRanking(dateStr, logData) {
  const etfIds = loadAllEtfIds();
  const dataQualityIssueEtfs = new Set(
    logData.filter(e => !e.error && hasDataQualityIssue(e)).map(e => e.etf_id)
  );
  const results = [];
  const skipped = [];

  for (const etfId of etfIds) {
    if (dataQualityIssueEtfs.has(etfId)) { skipped.push(etfId); continue; }
    const todayCsv = path.join(DATA_DIR, etfId, dateToFilename(dateStr));
    const prevCsv = findPrevCsvPath(etfId, dateStr);
    const todayHoldings = readCsvHoldings(todayCsv);
    const prevHoldings = prevCsv ? readCsvHoldings(prevCsv) : null;
    if (!todayHoldings || !prevHoldings) continue;

    const aumPrev = estimateAUM(prevHoldings);
    const aumToday = estimateAUM(todayHoldings);
    const flowEstimate = estimateFundFlow(todayHoldings, prevHoldings);
    if (aumPrev === null || aumPrev === 0 || flowEstimate === null) continue;

    const flowPct = (flowEstimate / aumPrev) * 100;
    results.push({
      etf_id: etfId,
      aum_estimate: aumToday,
      flow_estimate: flowEstimate,
      flow_pct: flowPct,
      signal: Math.abs(flowPct) >= NOTABLE_FLOW_PCT
        ? (flowPct > 0 ? 'notable_inflow' : 'notable_outflow')
        : 'normal'
    });
  }

  results.sort((a, b) => b.flow_pct - a.flow_pct);
  return {
    all: results,
    top_inflow: results.length ? results[0] : null,
    top_outflow: results.length ? results[results.length - 1] : null,
    skipped_etfs_data_quality: skipped
  };
}

function fetchPremiums() {
  log(`抓折溢價：${TARGET_ETFS.join(', ')}`);
  try {
    const out = execSync(`node "${PREMIUM_SCRIPT}" ${TARGET_ETFS.join(' ')}`, {
      encoding: 'utf8', timeout: 60000
    });
    return JSON.parse(out);
  } catch (e) {
    log(`折溢價抓取失敗: ${e.message}`);
    return { error: e.message };
  }
}

function main() {
  const targetDate = process.argv[2] || null;

  gitPull();

  const dateStr = targetDate || findLatestLogDate();
  if (!dateStr) {
    console.log(JSON.stringify({ error: '找不到任何 log 檔案' }));
    process.exit(1);
  }

  const logData = readJsonLog(dateStr);
  if (!logData) {
    console.log(JSON.stringify({ error: `找不到 ${dateStr} 的 log 檔案` }));
    process.exit(1);
  }

  const crossEtfRanking = buildCrossEtfRanking(logData);
  const fundFlowRanking = buildFundFlowRanking(dateStr, logData);

  const targetDetails = {};
  for (const etfId of TARGET_ETFS) {
    const entry = logData.find(e => e.etf_id === etfId);
    targetDetails[etfId] = buildTargetEtfDetail(dateStr, entry);
  }

  const premiums = fetchPremiums();

  console.log(JSON.stringify({
    date: dateStr,
    cross_etf_ranking: crossEtfRanking,
    fund_flow_ranking: fundFlowRanking,
    target_etf_detail: targetDetails,
    premiums
  }, null, 2));
}

main();
