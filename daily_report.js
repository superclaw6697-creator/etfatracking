#!/usr/bin/env node
/**
 * daily_report.js — ETF 每日持股變動 + 折溢價 一站式資料收集
 *
 * 用途：
 *   1. git pull 到最新
 *   2. 找出 logs/ 底下最新一天的持股異動 log（.txt，人類可讀）
 *   3. 呼叫 fetch_etf_premium.js 抓 00981A / 00991A / 00403A 即時折溢價
 *   4. 印出一份 JSON，供上層（Claude / skill）讀取後做分析與 Telegram 推播
 *
 * Usage:
 *   node daily_report.js              # 自動找最新一天的 log
 *   node daily_report.js 2026-08-19   # 指定日期
 */

const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');

const ROOT = __dirname;
const LOGS_DIR = path.join(ROOT, 'logs');
const PREMIUM_SCRIPT = path.join(path.dirname(ROOT), 'projects', 'fetch_etf_premium.js');
const PREMIUM_ETFS = ['00981A', '00991A', '00403A'];

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
    .filter(f => f.endsWith('.txt'))
    .sort();
  if (files.length === 0) return null;
  return files[files.length - 1].replace('.txt', '');
}

function readLogText(dateStr) {
  const month = dateStr.slice(0, 7);
  const txtPath = path.join(LOGS_DIR, month, `${dateStr}.txt`);
  if (!fs.existsSync(txtPath)) return null;
  return fs.readFileSync(txtPath, 'utf8');
}

function fetchPremiums() {
  log(`抓折溢價：${PREMIUM_ETFS.join(', ')}`);
  try {
    const out = execSync(`node "${PREMIUM_SCRIPT}" ${PREMIUM_ETFS.join(' ')}`, {
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

  const logText = readLogText(dateStr);
  const premiums = fetchPremiums();

  console.log(JSON.stringify({
    date: dateStr,
    log_text: logText,
    premiums
  }, null, 2));
}

main();
