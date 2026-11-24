"""
PMMB Command Center — ממשק דור חדש אינטראקטיבי (Obsidian Glass Pro).

עצמאי לחלוטין (ללא משאבים חיצוניים), מרוכז בפשטות ובשליטה מלאה:
  - Crosshair אינטראקטיבי + Tooltip על גרפי נרות, קו, ועקומת הון משולבת
  - מסחר מהיר ידני (Paper Quick Trade), עריכת SL/TP חיה, וסגירת הכל בלחיצה
  - תצוגת עומק ספר פקודות L2 חי (Bid/Ask Depth)
  - עריכה ושמירה של הגדרות הסיכון והמהירות של הבוט ישירות מהדפדפן
"""
from __future__ import annotations

import json

_UI_CSS = r"""
:root {
  --bg: #05070d;
  --bg-glow-1: rgba(56, 189, 248, 0.09);
  --bg-glow-2: rgba(16, 185, 129, 0.06);
  --surface: rgba(13, 18, 30, 0.78);
  --surface-solid: #0d121e;
  --surface-2: rgba(20, 28, 46, 0.75);
  --hover: rgba(30, 42, 68, 0.75);
  --border: rgba(148, 163, 184, 0.14);
  --border-hi: rgba(56, 189, 248, 0.42);
  --text: #f8fafc;
  --muted: #94a3b8;
  --dim: #64748b;
  --cyan: #38bdf8;
  --cyan-soft: rgba(56, 189, 248, 0.14);
  --green: #10b981;
  --green-soft: rgba(16, 185, 129, 0.14);
  --red: #f43f5e;
  --red-soft: rgba(244, 63, 94, 0.14);
  --amber: #f59e0b;
  --amber-soft: rgba(245, 158, 11, 0.14);
  --sans: system-ui, -apple-system, 'SF Pro Display', 'Segoe UI', Arial, sans-serif;
  --mono: 'JetBrains Mono', ui-monospace, 'SFMono-Regular', Menlo, monospace;
}

*, *::before, *::after { box-sizing: border-box; }
html, body {
  margin: 0;
  padding: 0;
  min-height: 100%;
  background: var(--bg);
  background-image:
    radial-gradient(960px 460px at 85% -6%, var(--bg-glow-1), transparent 65%),
    radial-gradient(800px 400px at 10% -4%, var(--bg-glow-2), transparent 62%);
  color: var(--text);
  font-family: var(--sans);
  font-size: 14px;
  line-height: 1.55;
  -webkit-font-smoothing: antialiased;
}

.num {
  font-family: var(--mono);
  font-variant-numeric: tabular-nums;
  direction: ltr;
  unicode-bidi: isolate;
  display: inline-block;
}
.pos { color: var(--green); }
.neg { color: var(--red); }
.warn { color: var(--amber); }
.cyan { color: var(--cyan); }
.muted { color: var(--muted); }
.dim { color: var(--dim); }

/* Header */
.header {
  position: sticky;
  top: 0;
  z-index: 40;
  background: rgba(5, 7, 13, 0.84);
  backdrop-filter: blur(18px);
  border-bottom: 1px solid var(--border);
}
.header-inner {
  max-width: 1340px;
  margin: 0 auto;
  padding: 12px 22px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  flex-wrap: wrap;
}
.brand { display: flex; align-items: center; gap: 12px; }
.logo-mark {
  width: 36px;
  height: 36px;
  border-radius: 11px;
  background: linear-gradient(135deg, rgba(56, 189, 248, 0.24), rgba(16, 185, 129, 0.22));
  border: 1px solid rgba(56, 189, 248, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--cyan);
  box-shadow: 0 0 24px rgba(56, 189, 248, 0.16);
}
.brand-title { font-size: 15px; font-weight: 700; letter-spacing: -0.01em; }
.brand-sub { font-size: 12px; color: var(--muted); display: flex; align-items: center; gap: 7px; }
.status-dot {
  width: 8px; height: 8px; border-radius: 50%;
  background: var(--green);
  box-shadow: 0 0 10px var(--green);
}
.status-dot.idle { background: var(--amber); box-shadow: 0 0 8px var(--amber); }
.status-dot.halt { background: var(--red); box-shadow: 0 0 10px var(--red); }

/* Navigation */
.nav-pills {
  display: inline-flex;
  gap: 4px;
  padding: 4px;
  border-radius: 14px;
  background: rgba(15, 23, 42, 0.72);
  border: 1px solid var(--border);
}
.nav-tab {
  appearance: none;
  border: none;
  background: transparent;
  color: var(--muted);
  padding: 7px 15px;
  border-radius: 10px;
  font-size: 13px;
  font-weight: 600;
  font-family: inherit;
  cursor: pointer;
  transition: all 0.16s ease;
}
.nav-tab:hover { color: var(--text); }
.nav-tab.active {
  background: linear-gradient(135deg, rgba(56, 189, 248, 0.24), rgba(56, 189, 248, 0.08));
  color: #e0f2fe;
  box-shadow: inset 0 0 0 1px rgba(56, 189, 248, 0.36);
}
.header-actions { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }

/* Controls */
.btn {
  appearance: none;
  border: 1px solid var(--border);
  background: rgba(20, 28, 46, 0.84);
  color: var(--text);
  padding: 8px 14px;
  border-radius: 10px;
  font-size: 13px;
  font-weight: 600;
  font-family: inherit;
  cursor: pointer;
  text-decoration: none;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  transition: all 0.15s ease;
}
.btn:hover { background: var(--hover); border-color: rgba(148, 163, 184, 0.28); transform: translateY(-1px); }
.btn.sm { padding: 6px 11px; font-size: 12.5px; border-radius: 9px; }
.btn.xs { padding: 4px 8px; font-size: 11.5px; border-radius: 7px; }
.btn.primary {
  background: linear-gradient(135deg, #0284c7, #0ea5e9);
  border-color: rgba(56, 189, 248, 0.6);
  color: #ffffff;
  box-shadow: 0 4px 16px rgba(14, 165, 233, 0.24);
}
.btn.primary:hover { filter: brightness(1.08); }
.btn.soft-red {
  background: var(--red-soft);
  border-color: rgba(244, 63, 94, 0.34);
  color: #fecdd3;
}
.btn.soft-red:hover { background: rgba(244, 63, 94, 0.25); }
.btn.soft-green {
  background: var(--green-soft);
  border-color: rgba(16, 185, 129, 0.34);
  color: #a7f3d0;
}
.btn.soft-green:hover { background: rgba(16, 185, 129, 0.24); }
.btn.active-mode {
  background: var(--cyan-soft);
  border-color: var(--border-hi);
  color: #bae6fd;
}

.sel, .inp {
  background: rgba(10, 15, 26, 0.92);
  border: 1px solid var(--border);
  color: var(--text);
  border-radius: 10px;
  padding: 7px 11px;
  font-size: 13px;
  font-family: inherit;
  outline: none;
}
.sel:focus, .inp:focus { border-color: var(--cyan); }
.range-inp { accent-color: var(--cyan); width: 100%; cursor: pointer; }

/* Layout */
.container { max-width: 1340px; margin: 0 auto; padding: 22px 22px 48px; }
.tab-pane { display: none; }
.tab-pane.active { display: block; animation: fadeUp 0.2s ease; }
@keyframes fadeUp {
  from { opacity: 0; transform: translateY(4px); }
  to { opacity: 1; transform: translateY(0); }
}

.alert-banner {
  background: var(--red-soft);
  border: 1px solid rgba(244, 63, 94, 0.45);
  border-radius: 14px;
  padding: 12px 18px;
  margin-bottom: 18px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.card {
  background: var(--surface);
  backdrop-filter: blur(16px);
  border: 1px solid var(--border);
  border-radius: 18px;
  overflow: hidden;
  box-shadow: 0 12px 34px rgba(0, 0, 0, 0.28);
}
.card-pad { padding: 18px 20px; }
.card-head {
  padding: 14px 20px;
  border-bottom: 1px solid var(--border);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}
.card-title { font-size: 15px; font-weight: 700; letter-spacing: -0.01em; }
.card-sub { font-size: 12px; color: var(--muted); margin-top: 2px; }

/* Hero */
.hero-grid {
  display: grid;
  grid-template-columns: 1.45fr 1fr 1fr;
  gap: 16px;
  margin-bottom: 18px;
}
.hero-card {
  position: relative;
  padding: 20px 22px;
  background: linear-gradient(155deg, rgba(16, 23, 39, 0.90), rgba(9, 13, 22, 0.84));
  border: 1px solid var(--border);
  border-radius: 20px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  gap: 10px;
}
.hero-card.primary-glow {
  border-color: rgba(56, 189, 248, 0.30);
  box-shadow: 0 12px 40px rgba(14, 165, 233, 0.09);
}
.hero-label { font-size: 12.5px; color: var(--muted); font-weight: 600; display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.hero-value { font-size: 32px; font-weight: 800; letter-spacing: -0.025em; line-height: 1.1; }
.hero-sub { font-size: 12.5px; color: var(--muted); display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.alloc-bar { height: 6px; border-radius: 999px; background: rgba(148, 163, 184, 0.14); overflow: hidden; display: flex; }
.alloc-perps { background: linear-gradient(90deg, #0284c7, #38bdf8); }
.alloc-poly { background: linear-gradient(90deg, #059669, #10b981); }
.hero-split { display: flex; gap: 12px; padding-top: 6px; }
.hero-pill {
  flex: 1;
  background: rgba(15, 23, 42, 0.68);
  border: 1px solid rgba(148, 163, 184, 0.11);
  border-radius: 12px;
  padding: 8px 12px;
}
.hero-pill-k { font-size: 11px; color: var(--dim); }
.hero-pill-v { font-size: 14px; font-weight: 700; margin-top: 2px; }

/* Badges */
.badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 9px;
  border-radius: 999px;
  font-size: 11.5px;
  font-weight: 600;
  background: rgba(148, 163, 184, 0.12);
  color: var(--muted);
}
.badge.green { background: var(--green-soft); color: #6ee7b7; }
.badge.red { background: var(--red-soft); color: #fda4af; }
.badge.amber { background: var(--amber-soft); color: #fcd34d; }
.badge.blue { background: var(--cyan-soft); color: #7dd3fc; }

/* Split Grids */
.main-split { display: grid; grid-template-columns: 1.25fr 1fr; gap: 16px; margin-bottom: 18px; }
.grid-2 { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; margin-bottom: 18px; }

/* Interactive Chart + Crosshair Tooltip */
.chart-wrap {
  position: relative;
  height: 320px;
  width: 100%;
  border-radius: 14px;
  background: #070b13;
  border: 1px solid rgba(148, 163, 184, 0.12);
  overflow: hidden;
  cursor: crosshair;
}
.chart-wrap canvas { width: 100%; height: 100%; display: block; }
.chart-tip {
  position: absolute;
  top: 10px;
  right: 12px;
  pointer-events: none;
  background: rgba(10, 15, 28, 0.90);
  border: 1px solid var(--border-hi);
  border-radius: 10px;
  padding: 6px 10px;
  font-size: 11.5px;
  color: var(--text);
  display: none;
  z-index: 5;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.5);
}
.chart-stats { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 12px; font-size: 12.5px; color: var(--muted); }
.chart-stat-item { background: rgba(15, 23, 42, 0.65); border: 1px solid rgba(148, 163, 184, 0.1); padding: 5px 10px; border-radius: 9px; }
.chart-stat-item b { color: var(--text); font-weight: 600; }

/* Position Cards + Inline Edit */
.pos-list { display: flex; flex-direction: column; gap: 11px; max-height: 440px; overflow-y: auto; padding: 16px; }
.pos-item {
  background: rgba(16, 23, 39, 0.80);
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 14px 16px;
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s;
}
.pos-item:hover { background: var(--hover); border-color: rgba(148, 163, 184, 0.28); }
.pos-item.selected { border-color: var(--border-hi); box-shadow: inset 0 0 0 1px rgba(56, 189, 248, 0.24); }
.pos-top { display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; }
.pos-name { font-weight: 700; font-size: 14px; line-height: 1.35; }
.pos-pnl { font-family: var(--mono); font-weight: 800; font-size: 15px; text-align: left; white-space: nowrap; }
.pos-bar-wrap { margin: 10px 0 9px; height: 5px; border-radius: 999px; background: rgba(148, 163, 184, 0.14); overflow: hidden; }
.pos-bar-fill { height: 100%; border-radius: 999px; background: linear-gradient(90deg, var(--amber), var(--cyan), var(--green)); transition: width 0.25s ease; }
.pos-meta { display: flex; align-items: center; justify-content: space-between; gap: 8px; flex-wrap: wrap; font-size: 12px; color: var(--muted); }
.pos-edit-box {
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px solid rgba(148, 163, 184, 0.12);
  display: none;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}
.pos-edit-box.open { display: flex; }

/* Orderbook Depth Bar */
.depth-row {
  display: grid;
  grid-template-columns: 1fr 78px 1fr;
  gap: 8px;
  align-items: center;
  font-size: 11.5px;
  padding: 2px 0;
}
.depth-bar-l, .depth-bar-r {
  height: 16px;
  border-radius: 4px;
  position: relative;
  display: flex;
  align-items: center;
  padding: 0 6px;
  overflow: hidden;
}
.depth-bar-l { justify-content: flex-end; background: rgba(16, 185, 129, 0.08); }
.depth-bar-r { justify-content: flex-start; background: rgba(244, 63, 94, 0.08); }
.depth-fill-l { position: absolute; left: 0; top: 0; bottom: 0; background: rgba(16, 185, 129, 0.25); }
.depth-fill-r { position: absolute; right: 0; top: 0; bottom: 0; background: rgba(244, 63, 94, 0.25); }
.depth-txt { position: relative; z-index: 2; font-family: var(--mono); font-size: 11px; }

/* Tables */
.tbl-scroll { overflow-x: auto; max-height: 360px; overflow-y: auto; }
table.clean-tbl { width: 100%; border-collapse: collapse; font-size: 13px; }
table.clean-tbl th {
  text-align: right;
  padding: 11px 16px;
  font-size: 11.5px;
  font-weight: 600;
  color: var(--dim);
  border-bottom: 1px solid var(--border);
  background: var(--surface-solid);
  position: sticky;
  top: 0;
  white-space: nowrap;
}
table.clean-tbl td { padding: 11px 16px; border-bottom: 1px solid rgba(148, 163, 184, 0.07); vertical-align: middle; }
table.clean-tbl tbody tr:hover { background: rgba(56, 189, 248, 0.04); }
table.clean-tbl tbody tr.clickable { cursor: pointer; }

/* Sub-Nav */
.sub-nav {
  display: inline-flex;
  gap: 4px;
  background: rgba(13, 18, 30, 0.85);
  border: 1px solid var(--border);
  padding: 4px;
  border-radius: 13px;
  margin-bottom: 18px;
}
.sub-btn {
  appearance: none;
  border: none;
  background: transparent;
  color: var(--muted);
  padding: 8px 16px;
  border-radius: 9px;
  font-size: 13px;
  font-weight: 600;
  font-family: inherit;
  cursor: pointer;
}
.sub-btn.active { background: var(--cyan-soft); color: #bae6fd; }
.sub-view { display: none; }
.sub-view.active { display: block; }

/* Chips, Rules & Settings Form */
.chip-grid { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 8px; }
.chip { background: rgba(15, 23, 42, 0.72); border: 1px solid var(--border); border-radius: 10px; padding: 6px 10px; font-size: 12px; }
.rule-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; padding: 16px 20px; }
.rule-box { background: rgba(15, 23, 42, 0.65); border: 1px solid var(--border); border-radius: 13px; padding: 13px 15px; }
.rule-k { font-size: 12px; color: var(--muted); margin-bottom: 4px; }
.rule-v { font-size: 16px; font-weight: 700; color: var(--text); }
.cfg-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; padding: 18px 20px; }
.cfg-field { background: rgba(15, 23, 42, 0.65); border: 1px solid var(--border); border-radius: 12px; padding: 12px 14px; display: flex; flex-direction: column; gap: 6px; }
.cfg-field label { font-size: 12px; color: var(--muted); font-weight: 600; }

/* Quick Trade Segmented Side */
.side-toggle { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; }

/* Search Overlay (#spot-overlay) */
.spot-overlay {
  position: fixed;
  inset: 0;
  background: rgba(5, 7, 13, 0.78);
  backdrop-filter: blur(8px);
  z-index: 100;
  display: none;
  align-items: flex-start;
  justify-content: center;
  padding-top: 88px;
}
.spot-overlay.open { display: flex; }
.spot-box {
  width: min(600px, 92vw);
  background: #0d121e;
  border: 1px solid var(--border-hi);
  border-radius: 18px;
  box-shadow: 0 24px 60px rgba(0, 0, 0, 0.65);
  overflow: hidden;
}
.spot-head { padding: 14px 18px; border-bottom: 1px solid var(--border); display: flex; align-items: center; gap: 10px; }
.spot-inp { width: 100%; background: transparent; border: none; outline: none; color: var(--text); font-size: 14px; font-family: inherit; }
.spot-list { max-height: 360px; overflow-y: auto; }
.spot-item { padding: 12px 18px; border-bottom: 1px solid rgba(148, 163, 184, 0.08); display: flex; justify-content: space-between; align-items: center; cursor: pointer; }
.spot-item:hover { background: var(--hover); }

/* Toast */
.toast {
  position: fixed;
  bottom: 20px;
  left: 20px;
  z-index: 95;
  background: #0f172a;
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 12px 18px;
  font-size: 13px;
  box-shadow: 0 12px 32px rgba(0, 0, 0, 0.45);
  display: none;
  max-width: 440px;
}
.toast.show { display: block; }
.toast.ok { border-color: rgba(16, 185, 129, 0.5); color: #a7f3d0; }
.toast.err { border-color: rgba(244, 63, 94, 0.5); color: #fecdd3; }

@media (max-width: 1060px) {
  .hero-grid, .main-split, .grid-2, .rule-grid, .cfg-grid { grid-template-columns: 1fr; }
}
@media (max-width: 640px) {
  .header-inner { padding: 10px 14px; }
  .container { padding: 14px 12px 32px; }
  .hero-value { font-size: 26px; }
}
"""

_UI_JS = r"""
let DATA = window.__PMMB_INIT__ || {};
let ACTIVE_TAB = "home";
let ACTIVE_SUB = "perps";
let HOME_CHART_MODE = "equity"; // "equity" | "asset"
let SELECTED_ASSET = null;
let PERP_SYM = null;
let POLY_TID = null;
let CHART_CACHE = { home: null, perps: null, poly: null };
let POLL_TIMER = null;
let PERPS_ONLY_SIGNALS = false;
let QUICK_SIDE = "LONG";
let BOOK_CACHE = {};
let CHART_CROSSHAIR = { home: null, perps: null, poly: null };

const $ = (id) => document.getElementById(id);
function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#39;" }[c]));
}
function fmt(n, d = 2) {
  const v = Number(n);
  return Number.isFinite(v) ? v.toFixed(d) : "—";
}
function fmtSigned(n, d = 2) {
  const v = Number(n);
  return Number.isFinite(v) ? ((v >= 0 ? "+" : "") + v.toFixed(d)) : "—";
}
function fmtDateTime(ts) {
  if (!ts) return "—";
  const d = new Date(Number(ts) * 1000);
  return d.toISOString().slice(5, 16).replace("T", " ");
}
function pnlCls(n) {
  const v = Number(n);
  if (!Number.isFinite(v) || v === 0) return "muted";
  return v > 0 ? "pos" : "neg";
}
function toast(msg, isErr = false) {
  const el = $("toast");
  if (!el) return;
  el.textContent = msg;
  el.className = "toast show " + (isErr ? "err" : "ok");
  clearTimeout(window.__toastTimer);
  window.__toastTimer = setTimeout(() => { el.className = "toast"; }, 4200);
}

const STATUS_TOKEN = new URLSearchParams(window.location.search).get("token") || "";
if (STATUS_TOKEN && window.history && typeof window.history.replaceState === "function") {
  const safeQuery = new URLSearchParams(window.location.search);
  safeQuery.delete("token");
  const suffix = safeQuery.toString();
  window.history.replaceState(
    null, "",
    window.location.pathname + (suffix ? "?" + suffix : "") + window.location.hash
  );
}
async function apiGet(url) {
  const headers = STATUS_TOKEN ? { "X-Token": STATUS_TOKEN } : {};
  const r = await fetch(url, { cache: "no-store", headers });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.error || ("HTTP " + r.status));
  return j;
}
async function apiPost(url, body = {}) {
  const r = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(STATUS_TOKEN ? { "X-Token": STATUS_TOKEN } : {}),
    },
    body: JSON.stringify(body),
  });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.error || ("HTTP " + r.status));
  return j;
}
async function downloadTradesCsv() {
  try {
    const headers = STATUS_TOKEN ? { "X-Token": STATUS_TOKEN } : {};
    const response = await fetch("/api/export/trades.csv", { cache: "no-store", headers });
    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new Error(error.error || ("HTTP " + response.status));
    }
    const blob = await response.blob();
    const objectUrl = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = objectUrl;
    link.download = "pmmb_trades.csv";
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
  } catch (error) {
    toast(error.message || String(error), true);
  }
}

async function runAction(url, body = {}, confirmMsg = "") {
  if (confirmMsg && typeof window.confirm === "function" && !window.confirm(confirmMsg)) return;
  try {
    const res = await apiPost(url, body);
    toast(res.message || "הפעולה בוצעה בהצלחה", false);
    await refreshState();
  } catch (e) {
    toast(e.message || String(e), true);
  }
}

async function closePosition(arm, key, label) {
  const okMsg = `האם לסגור עכשיו את "${label}" במחיר השוק?`;
  if (typeof window.confirm === "function" && !window.confirm(okMsg)) return;
  try {
    const res = await apiPost("/api/positions/close", { arm, key, reason: "סגירה ידנית מהממשק" });
    toast(res.message || "העסקה נסגרה", false);
    await refreshState();
  } catch (e) {
    toast(e.message || String(e), true);
  }
}

async function closeAllPositions() {
  if (typeof window.confirm === "function" && !window.confirm("לסגור את כל הפוזיציות הפתוחות בכל הזרועות עכשיו?")) return;
  await runAction("/api/positions/close-all", { arm: "all" });
}

function toggleEditLevels(uid) {
  const el = $("edit-" + uid);
  if (el) el.classList.toggle("open");
}

async function savePositionLevels(arm, key, uid) {
  const slEl = $("sl-" + uid);
  const tpEl = $("tp-" + uid);
  const stop_price = slEl && slEl.value !== "" ? Number(slEl.value) : null;
  const target_price = tpEl && tpEl.value !== "" ? Number(tpEl.value) : null;
  await runAction("/api/positions/update", { arm, key, stop_price, target_price });
}

function setHomeChartMode(mode) {
  HOME_CHART_MODE = mode;
  const bEq = $("btn-hc-eq"), bDa = $("btn-hc-daily"), bAs = $("btn-hc-asset");
  if (bEq) bEq.className = "btn sm " + (mode === "equity" ? "active-mode" : "");
  if (bDa) bDa.className = "btn sm " + (mode === "daily" ? "active-mode" : "");
  if (bAs) bAs.className = "btn sm " + (mode === "asset" ? "active-mode" : "");
  drawHomeChart();
}

function switchTab(tab) {
  ACTIVE_TAB = tab;
  document.querySelectorAll(".nav-tab").forEach((b) => b.classList.toggle("active", b.getAttribute("data-tab") === tab));
  document.querySelectorAll(".tab-pane").forEach((p) => p.classList.toggle("active", p.id === "tab-" + tab));
  redrawActiveCharts();
}

function switchSubView(name) {
  ACTIVE_SUB = name;
  document.querySelectorAll(".sub-btn").forEach((b) => b.classList.toggle("active", b.getAttribute("data-sub") === name));
  document.querySelectorAll(".sub-view").forEach((v) => v.classList.toggle("active", v.id === "sub-" + name));
  redrawActiveCharts();
}

function toggleSignalFilter() {
  PERPS_ONLY_SIGNALS = !PERPS_ONLY_SIGNALS;
  const btn = $("btn-sig-filter");
  if (btn) btn.className = "btn sm " + (PERPS_ONLY_SIGNALS ? "primary" : "");
  renderMarketsTab();
}

function setQuickSide(side) {
  QUICK_SIDE = side;
  const bL = $("qt-long"), bS = $("qt-short");
  if (bL) bL.className = "btn sm " + (side === "LONG" ? "soft-green" : "");
  if (bS) bS.className = "btn sm " + (side === "SHORT" ? "soft-red" : "");
  updateQuickPreview();
}

function updateQuickPreview() {
  const m = Number(($("qt-margin") && $("qt-margin").value) || 25);
  const lev = Number(($("qt-lev") && $("qt-lev").value) || 15);
  const lbl = $("qt-lev-lbl");
  if (lbl) lbl.textContent = "×" + lev;
  const prv = $("qt-preview");
  const sym = PERP_SYM || "BTC";
  if (prv) {
    const notional = m * lev;
    const liqMove = (100 / Math.max(1, lev)).toFixed(1);
    prv.innerHTML = `${esc(sym)} <b>${QUICK_SIDE}</b> · נומינלי <b class="num cyan">$${fmt(notional, 0)}</b> · מרווח תנועה ~<b class="num">${liqMove}%</b> (מוגן אוטומטית ב־SL/TP)`;
  }
}

async function submitQuickOrder() {
  const sym = PERP_SYM || "BTC";
  const margin = Number(($("qt-margin") && $("qt-margin").value) || 25);
  const leverage = Number(($("qt-lev") && $("qt-lev").value) || 15);
  await runAction("/api/perps/order", { symbol: sym, side: QUICK_SIDE, margin, leverage });
}

async function saveBotConfig() {
  const payload = {
    perps_enabled: $("cfg-perps-en") ? $("cfg-perps-en").value === "1" : true,
    perps_risk_pct: Number(($("cfg-perps-risk") && $("cfg-perps-risk").value) || 2.8) / 100.0,
    perps_max_lev: Number(($("cfg-perps-lev") && $("cfg-perps-lev").value) || 50),
    perps_max_pos: Number(($("cfg-perps-pos") && $("cfg-perps-pos").value) || 4),
    perps_interval_sec: Number(($("cfg-perps-int") && $("cfg-perps-int").value) || 60),
    poly_risk_pct: Number(($("cfg-poly-risk") && $("cfg-poly-risk").value) || 3.0) / 100.0,
    poly_max_pos: Number(($("cfg-poly-pos") && $("cfg-poly-pos").value) || 7),
    trade_interval_sec: Number(($("cfg-poly-int") && $("cfg-poly-int").value) || 120),
  };
  await runAction("/api/config/update", payload);
}

function renderHeader() {
  const h = DATA.health || {};
  const hb = DATA.heartbeat || {};
  const tr = DATA.trader || {};
  const halt = DATA.halt || (hb && hb.halted);

  const dot = $("hdr-dot");
  if (dot) dot.className = "status-dot" + (halt ? " halt" : (tr.running && h.healthy ? "" : " idle"));

  const statusTxt = $("hdr-status-text");
  if (statusTxt) {
    const modeLabel = String(DATA.mode || "paper").toUpperCase() === "LIVE" ? "מסחר אמיתי (LIVE)" : "מצב סימולציה (Paper)";
    const stateLabel = halt ? "נעצר בחירום" : (tr.running ? "טייס אוטומטי פעיל" : "מושהה");
    statusTxt.textContent = `${modeLabel} · ${stateLabel}`;
  }

  const loopBtn = $("btn-loop");
  if (loopBtn) {
    loopBtn.textContent = tr.running ? "השהה בוט" : "הפעל בוט";
    loopBtn.setAttribute("data-running", tr.running ? "1" : "0");
    loopBtn.className = "btn sm " + (tr.running ? "" : "primary");
  }

  const banner = $("halt-banner");
  if (banner) {
    if (halt) {
      $("halt-reason").textContent = (DATA.halt && DATA.halt.reason) || (hb && hb.halt_reason) || "עצירת חירום פעילה";
      banner.style.display = "flex";
    } else {
      banner.style.display = "none";
    }
  }
}

function renderHero() {
  const hero = $("combined-hero");
  if (!hero) return;
  const comb = DATA.combined || {};
  const poly = DATA.bankroll || {};
  const perps = DATA.perps || {};
  const ov = DATA.overall || {};
  const soak = DATA.soak || {};
  const rd = DATA.readiness || {};
  const pwf = (DATA.analytics && DATA.analytics.perp_walkforward) || {};

  const unr = Number(poly.unrealized_pnl || 0) + Number(perps.unrealized_pnl || 0);
  const closedCnt = Number(comb.closed_trades || 0);
  const totalWr = closedCnt > 0
    ? (((Number(ov.wins || 0)) + ((Number(perps.closed_trades || 0) * Number(perps.win_rate_pct || 0)) / 100)) / closedCnt * 100)
    : 0;
  const freeCash = Number(poly.cash || 0) + Number(perps.cash || 0);
  const pShare = comb.equity > 0 ? Math.max(10, Math.min(90, Math.round((Number(perps.equity || 0) / comb.equity) * 100))) : 50;

  hero.innerHTML = `
    <div class="hero-card primary-glow">
      <div class="hero-label">
        <span>שווי התיק הכולל</span>
        <span class="badge ${rd.ready ? 'green' : 'blue'}">${rd.ready ? 'מוכן ל־Live' : `ניסיון ${soak.days ?? 0}/${soak.target_days ?? 7} ימים`}</span>
      </div>
      <div class="hero-value num">$${fmt(comb.equity)}</div>
      <div class="hero-sub">
        <span class="num ${pnlCls(comb.pnl)}"><b>${fmtSigned(comb.pnl)}$ (${fmtSigned(comb.return_pct)}%)</b></span>
        <span class="dim">מ־$${fmt(comb.starting_cash, 0)}</span>
        ${pwf.full_30d_return_pct != null ? `<span class="badge green">PERPS 30d OOS: +${fmt(pwf.full_30d_return_pct, 0)}%</span>` : ""}
      </div>
      <div class="alloc-bar"><div class="alloc-perps" style="width:${pShare}%"></div><div class="alloc-poly" style="width:${100 - pShare}%"></div></div>
      <div class="hero-split">
        <div class="hero-pill">
          <div class="hero-pill-k">זרוע PERPS ×50</div>
          <div class="hero-pill-v num cyan">$${fmt(perps.equity)}</div>
        </div>
        <div class="hero-pill">
          <div class="hero-pill-k">זרוע Polymarket</div>
          <div class="hero-pill-v num pos">$${fmt(poly.equity)}</div>
        </div>
      </div>
    </div>

    <div class="hero-card">
      <div class="hero-label">
        <span>רווח פתוח וביצועים</span>
        <span class="badge">${comb.open_positions ?? 0} עסקאות פתוחות</span>
      </div>
      <div class="hero-value num ${pnlCls(unr)}">${fmtSigned(unr)}$</div>
      <div class="hero-sub">
        <span><b>${closedCnt}</b> נסגרו</span>
        <span>הצלחה <b class="num">${fmt(totalWr, 0)}%</b></span>
        <span>עמלות <b class="num">$${fmt(comb.fees_paid)}</b></span>
      </div>
      <div class="hero-sub" style="margin-top:auto">
        <button class="btn sm primary" onclick="runAction('/api/perps/cycle')">סרוק PERPS עכשיו</button>
        <button class="btn sm" onclick="runAction('/api/paper-cycle')">סרוק Polymarket</button>
      </div>
    </div>

    <div class="hero-card">
      <div class="hero-label">
        <span>נזילות ושליטה</span>
        <button type="button" class="btn sm" onclick="downloadTradesCsv()">ייצוא CSV</button>
      </div>
      <div class="hero-value num">$${fmt(freeCash)}</div>
      <div class="hero-sub">
        <span>Polymarket: <b class="num">$${fmt(poly.cash)}</b></span>
        <span>PERPS פנוי: <b class="num">$${fmt(perps.cash)}</b></span>
      </div>
      <div class="hero-sub" style="margin-top:auto">
        <span>מרג׳ין פעיל: <b class="num cyan">$${fmt(perps.margin_used)}</b></span>
        <button class="btn sm" onclick="switchTab('settings')">הגדרות ו־Live</button>
      </div>
    </div>
  `;
}

function getAllSelectableAssets() {
  const perps = DATA.perps || {};
  const list = [];
  (perps.positions || []).forEach((p) => list.push({ arm: "perps", id: p.symbol, label: `פוזיציה · ${p.symbol} (${p.side} ×${fmt(p.leverage, 0)})` }));
  (DATA.positions || []).forEach((p) => {
    const tid = p.full_token_id || p.token_id;
    list.push({ arm: "poly", id: tid, label: `פוזיציה · ${(p.question || tid).slice(0, 36)}` });
  });
  (perps.intel || []).forEach((r) => {
    if (!list.some((x) => x.arm === "perps" && x.id === r.symbol)) list.push({ arm: "perps", id: r.symbol, label: `PERPS · ${r.symbol}` });
  });
  ((DATA.charts && DATA.charts.candidates) || []).forEach((c) => {
    if (!list.some((x) => x.arm === "poly" && x.id === c.token_id)) list.push({ arm: "poly", id: c.token_id, label: `Polymarket · ${(c.question || c.token_id).slice(0, 36)}` });
  });
  return list;
}

function syncSelectors() {
  const assets = getAllSelectableAssets();
  if (!SELECTED_ASSET && assets.length) SELECTED_ASSET = { arm: assets[0].arm, id: assets[0].id };
  const hSel = $("home-asset-sel");
  if (hSel) {
    hSel.innerHTML = assets.map((a) => `<option value="${esc(a.arm + ':' + a.id)}">${esc(a.label)}</option>`).join("");
    if (SELECTED_ASSET) hSel.value = SELECTED_ASSET.arm + ":" + SELECTED_ASSET.id;
  }

  const perps = DATA.perps || {};
  const syms = [];
  (perps.positions || []).forEach((p) => { if (!syms.includes(p.symbol)) syms.push(p.symbol); });
  (perps.intel || []).forEach((r) => { if (!syms.includes(r.symbol)) syms.push(r.symbol); });
  if (!syms.length && perps.default_chart && perps.default_chart.symbol) syms.push(perps.default_chart.symbol);
  if (!PERP_SYM && syms.length) PERP_SYM = syms[0];
  const pSel = $("perp-asset-sel");
  if (pSel) {
    pSel.innerHTML = syms.map((s) => `<option value="${esc(s)}">${esc(s)} / USDT</option>`).join("");
    if (PERP_SYM) pSel.value = PERP_SYM;
  }

  const cands = (DATA.charts && DATA.charts.candidates) || [];
  if (!POLY_TID && cands.length) POLY_TID = cands[0].token_id;
  const mSel = $("poly-asset-sel");
  if (mSel) {
    mSel.innerHTML = cands.map((c) => `<option value="${esc(c.token_id)}">${esc((c.question || c.token_id).slice(0, 50))}</option>`).join("");
    if (POLY_TID) mSel.value = POLY_TID;
  }
}

async function selectHomeAsset(arm, id, live = false) {
  SELECTED_ASSET = { arm, id };
  HOME_CHART_MODE = "asset";
  const bEq = $("btn-hc-eq"), bDa = $("btn-hc-daily"), bAs = $("btn-hc-asset");
  if (bEq) bEq.className = "btn sm";
  if (bDa) bDa.className = "btn sm";
  if (bAs) bAs.className = "btn sm active-mode";
  const hSel = $("home-asset-sel");
  if (hSel) hSel.value = arm + ":" + id;
  if (arm === "perps") {
    const dc = DATA.perps && DATA.perps.default_chart;
    if (!live && dc && dc.symbol === id && (dc.candles || []).length) {
      CHART_CACHE.home = { kind: "perps", data: dc };
    } else {
      try { CHART_CACHE.home = { kind: "perps", data: await apiGet(`/api/perps/chart?symbol=${encodeURIComponent(id)}&live=${live ? 1 : 0}`) }; } catch (_) {}
    }
  } else {
    const dc = DATA.charts && DATA.charts.default;
    if (!live && dc && String(dc.token_id || "").startsWith(String(id).slice(0, 12))) {
      CHART_CACHE.home = { kind: "poly", data: dc };
    } else {
      try { CHART_CACHE.home = { kind: "poly", data: await apiGet(`/api/chart?token=${encodeURIComponent(id)}&live=${live ? 1 : 0}`) }; } catch (_) {}
    }
  }
  drawHomeChart();
  renderPositionsPanel();
}

async function selectPerpAsset(sym, live = false) {
  PERP_SYM = sym;
  const pSel = $("perp-asset-sel");
  if (pSel) pSel.value = sym;
  const dc = DATA.perps && DATA.perps.default_chart;
  if (!live && dc && dc.symbol === sym && (dc.candles || []).length) {
    CHART_CACHE.perps = dc;
  } else {
    try { CHART_CACHE.perps = await apiGet(`/api/perps/chart?symbol=${encodeURIComponent(sym)}&live=${live ? 1 : 0}`); } catch (_) {}
  }
  drawPerpChart();
  renderPerpsThesis();
  updateQuickPreview();
  loadPerpBook(sym);
}

async function loadPerpBook(sym) {
  const box = $("perps-depth-box");
  if (!box) return;
  try {
    const bk = await apiGet(`/api/perps/book?symbol=${encodeURIComponent(sym)}`);
    BOOK_CACHE[sym] = bk;
    renderPerpDepth(bk);
  } catch (_) {}
}

function renderPerpDepth(bk) {
  const box = $("perps-depth-box");
  if (!box || !bk) return;
  const bids = (bk.bids || []).slice(0, 5);
  const asks = (bk.asks || []).slice(0, 5);
  const maxSz = Math.max(1e-6, ...bids.map((b) => b[1]), ...asks.map((a) => a[1]));
  const rows = [];
  for (let i = 0; i < Math.max(bids.length, asks.length); i++) {
    const b = bids[i], a = asks[i];
    const bw = b ? Math.round((b[1] / maxSz) * 100) : 0;
    const aw = a ? Math.round((a[1] / maxSz) * 100) : 0;
    rows.push(`
      <div class="depth-row">
        <div class="depth-bar-l"><div class="depth-fill-l" style="width:${bw}%"></div><span class="depth-txt pos">${b ? fmt(b[0], b[0] >= 10 ? 2 : 4) : "—"}</span></div>
        <div class="dim num" style="text-align:center;font-size:10.5px">${b && a ? fmt(b[1], 1) + " / " + fmt(a[1], 1) : ""}</div>
        <div class="depth-bar-r"><div class="depth-fill-r" style="width:${aw}%"></div><span class="depth-txt neg">${a ? fmt(a[0], a[0] >= 10 ? 2 : 4) : "—"}</span></div>
      </div>
    `);
  }
  box.innerHTML = `
    <div style="display:flex;justify-content:space-between;font-size:11.5px;margin-bottom:6px">
      <span>ספר פקודות חי · <b class="num">${esc(bk.symbol)}</b></span>
      <span class="muted">Spread <b class="num">${fmt(bk.spread_bps, 2)} bps</b> · Imbalance <b class="num ${pnlCls(bk.imbalance)}">${fmtSigned(bk.imbalance, 2)}</b></span>
    </div>
    ${rows.join("") || '<div class="muted">טוען ספר פקודות...</div>'}
  `;
}

async function selectPolyAsset(tid, live = false) {
  POLY_TID = tid;
  const mSel = $("poly-asset-sel");
  if (mSel) mSel.value = tid;
  const dc = DATA.charts && DATA.charts.default;
  if (!live && dc && dc.token_id === tid && (dc.ticks || []).length) {
    CHART_CACHE.poly = dc;
  } else {
    try { CHART_CACHE.poly = await apiGet(`/api/chart?token=${encodeURIComponent(tid)}&live=${live ? 1 : 0}`); } catch (_) {}
  }
  drawPolyChart();
}

function initCanvas(canvas) {
  if (!canvas || !canvas.getContext) return null;
  const rect = canvas.parentElement ? canvas.parentElement.getBoundingClientRect() : { width: 720, height: 320 };
  const w = Math.max(300, Math.floor(rect.width || 720));
  const h = Math.max(220, Math.floor(rect.height || 320));
  const dpr = window.devicePixelRatio || 1;
  canvas.width = w * dpr;
  canvas.height = h * dpr;
  const ctx = canvas.getContext("2d");
  if (!ctx) return null;
  if (typeof ctx.setTransform === "function") ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  return { ctx, w, h };
}

function updateTip(tipId, htmlText, show = true) {
  const tip = $(tipId);
  if (!tip) return;
  if (!show) { tip.style.display = "none"; return; }
  tip.innerHTML = htmlText;
  tip.style.display = "block";
}

function drawEquityCurve(canvas, points, tipId, hoverX) {
  const s = initCanvas(canvas);
  if (!s) return;
  const { ctx, w, h } = s;
  ctx.fillStyle = "#070b13";
  ctx.fillRect(0, 0, w, h);

  if (!points || points.length < 2) {
    ctx.fillStyle = "#94a3b8";
    ctx.font = "13px sans-serif";
    ctx.fillText("צובר נקודות הון לעקומה...", 22, 42);
    return;
  }
  const padL = 16, padR = 64, padT = 20, padB = 26;
  const cw = w - padL - padR, ch = h - padT - padB;
  let lo = Infinity, hi = -Infinity;
  points.forEach((p) => { if (p.equity < lo) lo = p.equity; if (p.equity > hi) hi = p.equity; });
  if (hi <= lo) hi = lo + 10;
  const sp = hi - lo;
  lo -= sp * 0.12;
  hi += sp * 0.12;
  const xOf = (i) => padL + (i / Math.max(1, points.length - 1)) * cw;
  const yOf = (v) => padT + ((hi - v) / (hi - lo)) * ch;

  ctx.strokeStyle = "rgba(148,163,184,0.08)";
  ctx.lineWidth = 1;
  ctx.font = "11px monospace";
  ctx.fillStyle = "#64748b";
  for (let i = 0; i <= 4; i++) {
    const gy = padT + (ch * i) / 4;
    const gp = hi - ((hi - lo) * i) / 4;
    ctx.beginPath(); ctx.moveTo(padL, gy); ctx.lineTo(w - padR, gy); ctx.stroke();
    ctx.fillText("$" + gp.toFixed(0), w - padR + 8, gy + 4);
  }

  ctx.beginPath();
  points.forEach((p, i) => {
    const x = xOf(i), y = yOf(p.equity);
    if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
  });
  ctx.strokeStyle = "#10b981";
  ctx.lineWidth = 2.6;
  ctx.stroke();

  ctx.lineTo(xOf(points.length - 1), h - padB);
  ctx.lineTo(xOf(0), h - padB);
  ctx.closePath();
  ctx.fillStyle = "rgba(16, 185, 129, 0.12)";
  ctx.fill();

  if (hoverX != null && hoverX >= padL && hoverX <= w - padR) {
    const idx = Math.max(0, Math.min(points.length - 1, Math.round(((hoverX - padL) / cw) * (points.length - 1))));
    const pt = points[idx];
    const cx = xOf(idx), cy = yOf(pt.equity);
    ctx.strokeStyle = "rgba(56, 189, 248, 0.55)";
    ctx.lineWidth = 1;
    if (typeof ctx.setLineDash === "function") ctx.setLineDash([4, 4]);
    ctx.beginPath(); ctx.moveTo(cx, padT); ctx.lineTo(cx, h - padB); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(padL, cy); ctx.lineTo(w - padR, cy); ctx.stroke();
    if (typeof ctx.setLineDash === "function") ctx.setLineDash([]);
    ctx.fillStyle = "#38bdf8";
    ctx.beginPath(); if (typeof ctx.arc === "function") ctx.arc(cx, cy, 4, 0, Math.PI * 2); ctx.fill();
    updateTip(tipId, `<b>${fmtDateTime(pt.ts)}</b> · הון <b class="num pos">$${fmt(pt.equity)}</b> · PERPS <span class="num">$${fmt(pt.perps)}</span> · Poly <span class="num">$${fmt(pt.poly)}</span>`, true);
  } else {
    updateTip(tipId, "", false);
  }
}

function drawDailyBars(canvas, days, tipId, hoverX) {
  const s = initCanvas(canvas);
  if (!s) return;
  const { ctx, w, h } = s;
  ctx.fillStyle = "#070b13";
  ctx.fillRect(0, 0, w, h);

  if (!days || !days.length) {
    ctx.fillStyle = "#94a3b8";
    ctx.font = "13px sans-serif";
    ctx.fillText("אין עדיין היסטוריית עסקאות סגורות לפי יום...", 22, 42);
    return;
  }
  const padL = 16, padR = 58, padT = 20, padB = 26;
  const cw = w - padL - padR, ch = h - padT - padB;
  let lo = 0, hi = 0;
  days.forEach((d) => { if (d.total < lo) lo = d.total; if (d.total > hi) hi = d.total; });
  if (hi <= lo) { hi += 5; lo -= 5; }
  const sp = hi - lo;
  lo -= sp * 0.12;
  hi += sp * 0.12;
  const yOf = (v) => padT + ((hi - v) / (hi - lo)) * ch;
  const y0 = yOf(0);

  ctx.strokeStyle = "rgba(148,163,184,0.16)";
  ctx.lineWidth = 1;
  ctx.beginPath(); ctx.moveTo(padL, y0); ctx.lineTo(w - padR, y0); ctx.stroke();
  ctx.font = "11px monospace";
  ctx.fillStyle = "#64748b";
  ctx.fillText(fmtSigned(hi, 0) + "$", w - padR + 8, padT + 6);
  ctx.fillText("0$", w - padR + 8, y0 + 4);
  ctx.fillText(fmtSigned(lo, 0) + "$", w - padR + 8, h - padB);

  const step = cw / Math.max(1, days.length);
  const bw = Math.max(6, Math.min(34, step * 0.65));
  days.forEach((d, i) => {
    const x = padL + (i + 0.5) * step - bw / 2;
    const yv = yOf(d.total);
    ctx.fillStyle = d.total >= 0 ? "rgba(16, 185, 129, 0.85)" : "rgba(244, 63, 94, 0.85)";
    const top = Math.min(y0, yv);
    const bh = Math.max(2, Math.abs(yv - y0));
    ctx.fillRect(x, top, bw, bh);
  });

  if (hoverX != null && hoverX >= padL && hoverX <= w - padR) {
    const idx = Math.max(0, Math.min(days.length - 1, Math.floor((hoverX - padL) / step)));
    const d = days[idx];
    const cx = padL + (idx + 0.5) * step;
    ctx.strokeStyle = "rgba(56, 189, 248, 0.55)";
    ctx.lineWidth = 1;
    if (typeof ctx.setLineDash === "function") ctx.setLineDash([4, 4]);
    ctx.beginPath(); ctx.moveTo(cx, padT); ctx.lineTo(cx, h - padB); ctx.stroke();
    if (typeof ctx.setLineDash === "function") ctx.setLineDash([]);
    updateTip(tipId, `<b>${esc(d.day)}</b> · סה״כ <b class="num ${pnlCls(d.total)}">${fmtSigned(d.total)}$</b> · PERPS <span class="num">${fmtSigned(d.perps)}$</span> · Poly <span class="num">${fmtSigned(d.poly)}$</span> (${d.trades} עסקאות)`, true);
  } else {
    updateTip(tipId, "", false);
  }
}

function drawCandles(canvas, payload, tipId, hoverX) {
  const s = initCanvas(canvas);
  if (!s) return;
  const { ctx, w, h } = s;
  ctx.fillStyle = "#070b13";
  ctx.fillRect(0, 0, w, h);

  const candles = (payload && payload.candles) || [];
  if (!candles.length) {
    ctx.fillStyle = "#94a3b8";
    ctx.font = "13px sans-serif";
    ctx.fillText("טוען נתוני שוק...", 22, 42);
    return;
  }
  const padL = 14, padR = 68, padT = 18, padB = 22;
  const cw = w - padL - padR, ch = h - padT - padB;
  const view = candles.slice(-72);
  let lo = Infinity, hi = -Infinity;
  view.forEach((c) => { if (c.low < lo) lo = c.low; if (c.high > hi) hi = c.high; });
  const ov = (payload && payload.overlays) || {};
  [ov.entry, ov.stop, ov.target].forEach((lv) => {
    const v = Number(lv);
    if (Number.isFinite(v) && v > 0) { if (v < lo) lo = v; if (v > hi) hi = v; }
  });
  if (hi <= lo) hi = lo * 1.01 + 1e-6;
  const span = hi - lo;
  lo -= span * 0.08;
  hi += span * 0.08;
  const yOf = (p) => padT + ((hi - p) / (hi - lo)) * ch;

  ctx.strokeStyle = "rgba(148,163,184,0.08)";
  ctx.lineWidth = 1;
  ctx.font = "11px monospace";
  ctx.fillStyle = "#64748b";
  for (let i = 0; i <= 4; i++) {
    const gy = padT + (ch * i) / 4;
    const gp = hi - ((hi - lo) * i) / 4;
    ctx.beginPath(); ctx.moveTo(padL, gy); ctx.lineTo(w - padR, gy); ctx.stroke();
    ctx.fillText(gp >= 100 ? gp.toFixed(1) : (gp >= 1 ? gp.toFixed(3) : gp.toFixed(4)), w - padR + 8, gy + 4);
  }

  const step = cw / view.length;
  const bw = Math.max(3, Math.min(10, step * 0.62));
  view.forEach((c, i) => {
    const x = padL + (i + 0.5) * step;
    const col = c.close >= c.open ? "#10b981" : "#f43f5e";
    ctx.strokeStyle = col;
    ctx.fillStyle = col;
    ctx.lineWidth = 1.2;
    ctx.beginPath(); ctx.moveTo(x, yOf(c.high)); ctx.lineTo(x, yOf(c.low)); ctx.stroke();
    const y1 = yOf(Math.max(c.open, c.close));
    const y2 = yOf(Math.min(c.open, c.close));
    ctx.fillRect(x - bw / 2, y1, bw, Math.max(2, y2 - y1));
  });

  [
    { px: ov.target, label: "יעד", col: "#10b981" },
    { px: ov.entry, label: "כניסה", col: "#38bdf8" },
    { px: ov.stop, label: "הגנה", col: "#f59e0b" },
  ].forEach((lv) => {
    const v = Number(lv.px);
    if (!Number.isFinite(v) || v <= 0) return;
    const y = yOf(v);
    if (y < padT || y > h - padB) return;
    ctx.strokeStyle = lv.col;
    ctx.lineWidth = 1.2;
    if (typeof ctx.setLineDash === "function") ctx.setLineDash([5, 4]);
    ctx.beginPath(); ctx.moveTo(padL, y); ctx.lineTo(w - padR, y); ctx.stroke();
    if (typeof ctx.setLineDash === "function") ctx.setLineDash([]);
    ctx.fillStyle = lv.col;
    ctx.fillText(lv.label, padL + 6, y - 4);
  });

  if (hoverX != null && hoverX >= padL && hoverX <= w - padR) {
    const idx = Math.max(0, Math.min(view.length - 1, Math.floor((hoverX - padL) / step)));
    const c = view[idx];
    const cx = padL + (idx + 0.5) * step;
    const cy = yOf(c.close);
    ctx.strokeStyle = "rgba(56, 189, 248, 0.55)";
    ctx.lineWidth = 1;
    if (typeof ctx.setLineDash === "function") ctx.setLineDash([4, 4]);
    ctx.beginPath(); ctx.moveTo(cx, padT); ctx.lineTo(cx, h - padB); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(padL, cy); ctx.lineTo(w - padR, cy); ctx.stroke();
    if (typeof ctx.setLineDash === "function") ctx.setLineDash([]);
    const d = c.close >= 100 ? 1 : (c.close >= 1 ? 3 : 4);
    updateTip(tipId, `<b>${fmtDateTime(c.ts)}</b> · O:<span class="num">${fmt(c.open, d)}</span> H:<span class="num pos">${fmt(c.high, d)}</span> L:<span class="num neg">${fmt(c.low, d)}</span> C:<b class="num cyan">${fmt(c.close, d)}</b>`, true);
  } else {
    updateTip(tipId, "", false);
  }
}

function drawSmoothLine(canvas, payload, tipId, hoverX) {
  const s = initCanvas(canvas);
  if (!s) return;
  const { ctx, w, h } = s;
  ctx.fillStyle = "#070b13";
  ctx.fillRect(0, 0, w, h);

  const ticks = (payload && payload.ticks) || [];
  if (!ticks.length) {
    ctx.fillStyle = "#94a3b8";
    ctx.font = "13px sans-serif";
    ctx.fillText("אין עדיין היסטוריית מחירים לשוק זה", 22, 42);
    return;
  }
  const padL = 14, padR = 54, padT = 18, padB = 22;
  const cw = w - padL - padR, ch = h - padT - padB;
  const pos = payload.position || {};
  let lo = Infinity, hi = -Infinity;
  ticks.forEach((t) => { if (t.price < lo) lo = t.price; if (t.price > hi) hi = t.price; });
  [pos.avg_price, pos.stop_price, pos.target_price].forEach((v) => {
    if (v != null && Number.isFinite(Number(v))) { if (v < lo) lo = Number(v); if (v > hi) hi = Number(v); }
  });
  if (hi <= lo) hi = lo + 0.02;
  const sp = hi - lo;
  lo = Math.max(0.01, lo - sp * 0.1);
  hi = Math.min(0.99, hi + sp * 0.1);
  const yOf = (p) => padT + ((hi - p) / (hi - lo)) * ch;
  const xOf = (i) => padL + (i / Math.max(1, ticks.length - 1)) * cw;

  ctx.strokeStyle = "rgba(148,163,184,0.08)";
  ctx.lineWidth = 1;
  ctx.font = "11px monospace";
  ctx.fillStyle = "#64748b";
  for (let i = 0; i <= 4; i++) {
    const gy = padT + (ch * i) / 4;
    const gp = hi - ((hi - lo) * i) / 4;
    ctx.beginPath(); ctx.moveTo(padL, gy); ctx.lineTo(w - padR, gy); ctx.stroke();
    ctx.fillText(gp.toFixed(3), w - padR + 8, gy + 4);
  }

  ctx.beginPath();
  ticks.forEach((t, i) => {
    const x = xOf(i), y = yOf(t.price);
    if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
  });
  ctx.strokeStyle = "#38bdf8";
  ctx.lineWidth = 2.4;
  ctx.stroke();

  ctx.lineTo(xOf(ticks.length - 1), h - padB);
  ctx.lineTo(xOf(0), h - padB);
  ctx.closePath();
  ctx.fillStyle = "rgba(56, 189, 248, 0.11)";
  ctx.fill();

  [
    { px: pos.target_price, label: "יעד", col: "#10b981" },
    { px: pos.avg_price, label: "כניסה", col: "#38bdf8" },
    { px: pos.stop_price, label: "הגנה", col: "#f43f5e" },
  ].forEach((lv) => {
    const v = Number(lv.px);
    if (!Number.isFinite(v) || v <= 0) return;
    const y = yOf(v);
    ctx.strokeStyle = lv.col;
    ctx.lineWidth = 1.2;
    if (typeof ctx.setLineDash === "function") ctx.setLineDash([5, 4]);
    ctx.beginPath(); ctx.moveTo(padL, y); ctx.lineTo(w - padR, y); ctx.stroke();
    if (typeof ctx.setLineDash === "function") ctx.setLineDash([]);
    ctx.fillStyle = lv.col;
    ctx.fillText(lv.label, padL + 6, y - 4);
  });

  if (hoverX != null && hoverX >= padL && hoverX <= w - padR) {
    const idx = Math.max(0, Math.min(ticks.length - 1, Math.round(((hoverX - padL) / cw) * (ticks.length - 1))));
    const tk = ticks[idx];
    const cx = xOf(idx), cy = yOf(tk.price);
    ctx.strokeStyle = "rgba(56, 189, 248, 0.55)";
    ctx.lineWidth = 1;
    if (typeof ctx.setLineDash === "function") ctx.setLineDash([4, 4]);
    ctx.beginPath(); ctx.moveTo(cx, padT); ctx.lineTo(cx, h - padB); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(padL, cy); ctx.lineTo(w - padR, cy); ctx.stroke();
    if (typeof ctx.setLineDash === "function") ctx.setLineDash([]);
    updateTip(tipId, `<b>${fmtDateTime(tk.ts)}</b> · מחיר <b class="num cyan">${fmt(tk.price, 3)}</b>`, true);
  } else {
    updateTip(tipId, "", false);
  }
}

function drawHomeChart() {
  const c = $("home-chart");
  if (!c) return;
  const stats = $("home-chart-stats");
  const curve = DATA.combined_equity_curve || [];
  if (HOME_CHART_MODE === "daily") {
    const days = (DATA.performance && DATA.performance.daily_pnl) || [];
    drawDailyBars(c, days, "home-tip", CHART_CROSSHAIR.home);
    if (stats) {
      const pf = (DATA.performance && DATA.performance.live_pf) || 0;
      const tot = days.reduce((s, d) => s + Number(d.total || 0), 0);
      stats.innerHTML = `
        <div class="chart-stat-item">ימי מסחר: <b class="num">${days.length}</b></div>
        <div class="chart-stat-item">רווח ממומש: <b class="num ${pnlCls(tot)}">${fmtSigned(tot)}$</b></div>
        <div class="chart-stat-item">Profit Factor חי: <b class="num cyan">${fmt(pf, 2)}</b></div>
      `;
    }
    return;
  }
  if (HOME_CHART_MODE === "equity" && curve.length >= 2) {
    drawEquityCurve(c, curve, "home-tip", CHART_CROSSHAIR.home);
    if (stats) {
      const first = curve[0], last = curve[curve.length - 1];
      const delta = last.equity - first.equity;
      stats.innerHTML = `
        <div class="chart-stat-item">תחילת מעקב: <b class="num">$${fmt(first.equity)}</b></div>
        <div class="chart-stat-item">כעת: <b class="num cyan">$${fmt(last.equity)}</b></div>
        <div class="chart-stat-item">שינוי בתקופה: <b class="num ${pnlCls(delta)}">${fmtSigned(delta)}$</b></div>
      `;
    }
    return;
  }

  const cached = CHART_CACHE.home;
  let kind = "perps", d = null;
  if (cached) { kind = cached.kind; d = cached.data; }
  else if (DATA.perps && DATA.perps.default_chart && (DATA.perps.default_chart.candles || []).length) { kind = "perps"; d = DATA.perps.default_chart; }
  else if (DATA.charts && DATA.charts.default) { kind = "poly"; d = DATA.charts.default; }
  if (!d) return;
  if (kind === "perps") drawCandles(c, d, "home-tip", CHART_CROSSHAIR.home); else drawSmoothLine(c, d, "home-tip", CHART_CROSSHAIR.home);

  if (!stats) return;
  if (kind === "perps") {
    const cs = d.candles || [];
    const last = cs[cs.length - 1] || {};
    const ov = d.overlays || {};
    stats.innerHTML = `
      <div class="chart-stat-item">נכס: <b>${esc(d.symbol)}</b></div>
      <div class="chart-stat-item">מחיר: <b class="num">${fmt(last.close, 4)}</b></div>
      ${ov.entry ? `<div class="chart-stat-item">כניסה: <b class="num cyan">${fmt(ov.entry, 4)}</b></div>` : ""}
      ${ov.stop ? `<div class="chart-stat-item">הגנה: <b class="num warn">${fmt(ov.stop, 4)}</b></div>` : ""}
      ${ov.target ? `<div class="chart-stat-item">יעד: <b class="num pos">${fmt(ov.target, 4)}</b></div>` : ""}
      ${ov.liq ? `<div class="chart-stat-item">ניזול: <b class="num neg">${fmt(ov.liq, 4)}</b></div>` : ""}
    `;
  } else {
    const ts = d.ticks || [];
    const last = ts[ts.length - 1] || {};
    const pos = d.position || {};
    stats.innerHTML = `
      <div class="chart-stat-item">שוק: <b>${esc((pos.question || d.question || d.token_id || "").slice(0, 48))}</b></div>
      <div class="chart-stat-item">מחיר: <b class="num">${fmt(last.price, 3)}</b></div>
      ${pos.avg_price ? `<div class="chart-stat-item">כניסה: <b class="num cyan">${fmt(pos.avg_price, 3)}</b></div>` : ""}
      ${pos.stop_price ? `<div class="chart-stat-item">הגנה: <b class="num warn">${fmt(pos.stop_price, 3)}</b></div>` : ""}
      ${pos.target_price ? `<div class="chart-stat-item">יעד: <b class="num pos">${fmt(pos.target_price, 3)}</b></div>` : ""}
    `;
  }
}

function drawPerpChart() {
  const c = $("perps-chart");
  const d = CHART_CACHE.perps || (DATA.perps && DATA.perps.default_chart);
  if (c && d) drawCandles(c, d, "perps-tip", CHART_CROSSHAIR.perps);
}
function drawPolyChart() {
  const c = $("mkt-chart");
  const d = CHART_CACHE.poly || (DATA.charts && DATA.charts.default);
  if (c && d) drawSmoothLine(c, d, "poly-tip", CHART_CROSSHAIR.poly);
}
function redrawActiveCharts() {
  if (ACTIVE_TAB === "home") drawHomeChart();
  if (ACTIVE_TAB === "markets" && ACTIVE_SUB === "perps") drawPerpChart();
  if (ACTIVE_TAB === "markets" && ACTIVE_SUB === "poly") drawPolyChart();
}

function bindCanvasCrosshair(canvasId, key, redrawFn) {
  const c = $(canvasId);
  if (!c || typeof c.addEventListener !== "function") return;
  c.addEventListener("mousemove", (ev) => {
    const rect = c.getBoundingClientRect ? c.getBoundingClientRect() : { left: 0 };
    CHART_CROSSHAIR[key] = ev.clientX - rect.left;
    redrawFn();
  });
  c.addEventListener("mouseleave", () => {
    CHART_CROSSHAIR[key] = null;
    redrawFn();
  });
}

function calcProgressPct(sl, tp, cur, side) {
  const s = Number(sl), t = Number(tp), c = Number(cur);
  if (!Number.isFinite(s) || !Number.isFinite(t) || !Number.isFinite(c) || Math.abs(t - s) < 1e-9) return 50;
  const raw = side === "SHORT" ? ((s - c) / (s - t)) * 100 : ((c - s) / (t - s)) * 100;
  return Math.max(4, Math.min(96, Math.round(raw)));
}

function renderPositionsPanel() {
  const box = $("home-positions-list");
  if (!box) return;
  const pRows = (DATA.perps && DATA.perps.positions) || [];
  const mRows = DATA.positions || [];
  const closeAllBtn = $("btn-close-all");
  if (closeAllBtn) closeAllBtn.style.display = (pRows.length + mRows.length) > 0 ? "inline-flex" : "none";
  const cards = [];

  pRows.forEach((p, idx) => {
    const isSel = SELECTED_ASSET && SELECTED_ASSET.arm === "perps" && SELECTED_ASSET.id === p.symbol;
    const key = esc(p.symbol);
    const uid = "p" + idx;
    const pct = calcProgressPct(p.stop_price, p.target_price, p.mark_price, p.side);
    cards.push(`
      <div class="pos-item ${isSel ? 'selected' : ''}" onclick="selectHomeAsset('perps','${key}')">
        <div class="pos-top">
          <div>
            <div class="pos-name">${esc(p.symbol)} <span class="badge blue">${esc(p.side)} ×${fmt(p.leverage, 1)}</span></div>
            <div class="muted" style="font-size:12px">${esc((p.exchange || "").toUpperCase())} · מרג׳ין <span class="num">$${fmt(p.margin_used, 2)}</span></div>
          </div>
          <div class="pos-pnl ${pnlCls(p.unrealized_pnl)}">
            ${fmtSigned(p.unrealized_pnl)}$
            <div style="font-size:11.5px;font-weight:500">${fmtSigned(p.roe_pct, 1)}%</div>
          </div>
        </div>
        <div class="pos-bar-wrap"><div class="pos-bar-fill" style="width:${pct}%"></div></div>
        <div class="pos-meta">
          <span><b class="num">${fmt(p.entry_price, p.entry_price >= 10 ? 2 : 4)}</b> → <b class="num">${fmt(p.mark_price, p.mark_price >= 10 ? 2 : 4)}</b></span>
          <span>SL <span class="num warn">${fmt(p.stop_price, 4)}</span> · TP <span class="num pos">${fmt(p.target_price, 4)}</span></span>
          <div style="display:flex;gap:6px">
            <button class="btn xs" onclick="event.stopPropagation(); toggleEditLevels('${uid}')">ערוך SL/TP</button>
            <button class="btn xs soft-red" onclick="event.stopPropagation(); closePosition('perps','${key}','${key} ${esc(p.side)}')">סגור עסקה</button>
          </div>
        </div>
        <div id="edit-${uid}" class="pos-edit-box" onclick="event.stopPropagation()">
          <input id="sl-${uid}" class="inp num" style="width:92px;padding:4px 8px;font-size:12px" type="number" step="any" value="${fmt(p.stop_price, 4)}" title="Stop Loss">
          <input id="tp-${uid}" class="inp num" style="width:92px;padding:4px 8px;font-size:12px" type="number" step="any" value="${fmt(p.target_price, 4)}" title="Take Profit">
          <button class="btn xs primary" onclick="savePositionLevels('perps','${key}','${uid}')">שמור</button>
        </div>
      </div>
    `);
  });

  mRows.forEach((p, idx) => {
    const key = esc(p.full_token_id || p.token_id);
    const isSel = SELECTED_ASSET && SELECTED_ASSET.arm === "poly" && SELECTED_ASSET.id === (p.full_token_id || p.token_id);
    const label = esc((p.question || p.token_id).slice(0, 34));
    const uid = "m" + idx;
    const pct = calcProgressPct(p.stop_price, p.target_price, p.mark_price ?? p.avg_price, "LONG");
    cards.push(`
      <div class="pos-item ${isSel ? 'selected' : ''}" onclick="selectHomeAsset('poly','${key}')">
        <div class="pos-top">
          <div>
            <div class="pos-name">${esc((p.question || p.token_id).slice(0, 56))}</div>
            <div class="muted" style="font-size:12px"><span class="badge">Polymarket</span> · ${fmt(p.size, 1)} מניות · ${fmt(p.age_hours, 1)} ש׳</div>
          </div>
          <div class="pos-pnl ${pnlCls(p.unrealized_pnl)}">
            ${fmtSigned(p.unrealized_pnl)}$
            <div style="font-size:11.5px;font-weight:500">${fmtSigned(p.unrealized_pct, 1)}%</div>
          </div>
        </div>
        <div class="pos-bar-wrap"><div class="pos-bar-fill" style="width:${pct}%"></div></div>
        <div class="pos-meta">
          <span><b class="num">${fmt(p.avg_price, 3)}</b> → <b class="num">${p.mark_price != null ? fmt(p.mark_price, 3) : "—"}</b></span>
          <span>SL <span class="num warn">${p.stop_price != null ? fmt(p.stop_price, 2) : "—"}</span> · TP <span class="num pos">${p.target_price != null ? fmt(p.target_price, 2) : "—"}</span></span>
          <div style="display:flex;gap:6px">
            <button class="btn xs" onclick="event.stopPropagation(); toggleEditLevels('${uid}')">ערוך SL/TP</button>
            <button class="btn xs soft-red" onclick="event.stopPropagation(); closePosition('polymarket','${key}','${label}')">סגור עסקה</button>
          </div>
        </div>
        <div id="edit-${uid}" class="pos-edit-box" onclick="event.stopPropagation()">
          <input id="sl-${uid}" class="inp num" style="width:76px;padding:4px 8px;font-size:12px" type="number" step="0.01" min="0.01" max="0.99" value="${p.stop_price != null ? fmt(p.stop_price, 3) : ''}" title="Stop Loss">
          <input id="tp-${uid}" class="inp num" style="width:76px;padding:4px 8px;font-size:12px" type="number" step="0.01" min="0.01" max="0.99" value="${p.target_price != null ? fmt(p.target_price, 3) : ''}" title="Take Profit">
          <button class="btn xs primary" onclick="savePositionLevels('polymarket','${key}','${uid}')">שמור</button>
        </div>
      </div>
    `);
  });

  box.innerHTML = cards.length ? cards.join("") : `<div class="muted" style="padding:28px;text-align:center">אין עסקאות פתוחות כרגע — הבוט ממתין לאיתות באיכות גבוהה.</div>`;
}

function renderHomeBottomTables() {
  const closedBody = $("home-closed-body");
  if (closedBody) {
    const rows = [];
    ((DATA.perps && DATA.perps.recent_trades) || []).slice(0, 8).forEach((t) => rows.push({ ts: t.ts, name: `${t.symbol} (PERPS ${t.side})`, pnl: t.realized, reason: t.reason }));
    (DATA.fills || []).filter((f) => f.side === "SELL").slice(0, 8).forEach((f) => rows.push({ ts: f.ts, name: f.question, pnl: f.realized, reason: f.reason }));
    rows.sort((a, b) => b.ts - a.ts);
    closedBody.innerHTML = rows.slice(0, 8).map((r) => `
      <tr>
        <td class="num muted">${fmtDateTime(r.ts)}</td>
        <td>${esc((r.name || "").slice(0, 44))}</td>
        <td class="num ${pnlCls(r.pnl)}"><b>${fmtSigned(r.pnl)}$</b></td>
        <td class="muted">${esc((r.reason || "").slice(0, 36))}</td>
      </tr>
    `).join("") || `<tr><td colspan="4" class="muted">אין עדיין עסקאות סגורות</td></tr>`;
  }

  const oppsBody = $("home-opps-body");
  if (oppsBody) {
    const items = [];
    ((DATA.perps && DATA.perps.intel) || []).slice(0, 5).forEach((r) => items.push({ arm: "PERPS", name: r.symbol, price: fmt(r.price, r.price >= 10 ? 2 : 4), score: fmt(r.score, 2), note: r.reason || r.status }));
    (DATA.market_intel || []).slice(0, 5).forEach((m) => items.push({ arm: "Polymarket", name: (m.question || m.token_id).slice(0, 42), price: fmt(m.price, 3), score: fmt(m.score, 2), note: m.reason || m.status }));
    oppsBody.innerHTML = items.map((x) => `
      <tr>
        <td><span class="badge ${x.arm === 'PERPS' ? 'blue' : ''}">${x.arm}</span></td>
        <td><b>${esc(x.name)}</b></td>
        <td class="num">${x.price}</td>
        <td class="num">${x.score}</td>
        <td class="muted">${esc((x.note || "").slice(0, 38))}</td>
      </tr>
    `).join("") || `<tr><td colspan="5" class="muted">ממתין לסריקת שווקים...</td></tr>`;
  }
}

function renderMarketsTab() {
  const perps = DATA.perps || {};
  const sBody = $("perps-scan-body");
  if (sBody) {
    const list = (perps.intel || []).filter((r) => !PERPS_ONLY_SIGNALS || (Number(r.score || 0) >= 0.50 || r.status === "OPEN" || r.status === "ENTRY"));
    sBody.innerHTML = list.map((r) => `
      <tr class="clickable" onclick="selectPerpAsset('${esc(r.symbol)}')">
        <td><b>${esc(r.symbol)}</b></td>
        <td class="muted">${esc((r.exchange || "").toUpperCase())}</td>
        <td class="num">${fmt(r.price, r.price >= 10 ? 2 : 4)}</td>
        <td><span class="badge">${esc(r.regime || "—")}</span></td>
        <td class="num">${fmt(r.score, 2)} (${esc(r.setup_tier || "B")})</td>
        <td><span class="badge ${r.status === 'OPEN' || r.status === 'ENTRY' ? 'green' : ''}">${esc(r.status || "סריקה")}</span></td>
        <td class="muted">${esc((r.reason || "").slice(0, 44))}</td>
      </tr>
    `).join("") || `<tr><td colspan="7" class="muted">אין נכסים תואמים לסינון</td></tr>`;
  }

  const mBody = $("poly-scan-body");
  if (mBody) {
    const q = ($("poly-filter") && $("poly-filter").value || "").trim().toLowerCase();
    const list = (DATA.market_intel || []).filter((m) => !q || String(m.question || "").toLowerCase().includes(q));
    mBody.innerHTML = list.slice(0, 30).map((m) => `
      <tr class="clickable" onclick="selectPolyAsset('${esc(m.token_id)}')">
        <td>${esc((m.question || m.token_id).slice(0, 58))}</td>
        <td><span class="badge">${esc(m.sector || "כללי")}</span></td>
        <td class="num">${fmt(m.price, 3)}</td>
        <td class="num">${fmtSigned(m.z_score, 2)}</td>
        <td class="num">${fmt(m.score, 2)}</td>
        <td class="muted">${esc((m.reason || "").slice(0, 44))}</td>
      </tr>
    `).join("") || `<tr><td colspan="6" class="muted">אין שווקים נסרקים</td></tr>`;
  }

  const wf = (DATA.analytics && DATA.analytics.walkforward) || {};
  const pwf = (DATA.analytics && DATA.analytics.perp_walkforward) || {};
  const wfEl = $("wf-summary-cards");
  if (wfEl) {
    wfEl.innerHTML = `
      <div class="rule-box">
        <div class="rule-k">Polymarket — אימות Walk-Forward מחוץ למדגם</div>
        <div class="rule-v ${pnlCls(wf.oos_pnl)}">${wf.oos_pnl != null ? fmtSigned(wf.oos_pnl) + " USDC" : "—"}</div>
        <div class="muted" style="font-size:12.5px">עקביות: <b>${wf.consistency != null ? fmt(wf.consistency * 100, 0) + "%" : "—"}</b> · הצלחה: <b>${wf.oos_win_rate != null ? fmt(wf.oos_win_rate, 1) + "%" : "—"}</b></div>
      </div>
      <div class="rule-box">
        <div class="rule-k">PERPS ×50 — אימות Walk-Forward (16 מטבעות נזילים)</div>
        <div class="rule-v ${pnlCls(pwf.oos_return_pct)}">${pwf.oos_return_pct != null ? fmtSigned(pwf.oos_return_pct) + "% OOS" : "—"}${pwf.full_30d_return_pct != null ? ` · <span class="num pos">${fmtSigned(pwf.full_30d_return_pct)}% (30d)</span>` : ""}</div>
        <div class="muted" style="font-size:12.5px">עקביות: <b>${pwf.consistency != null ? fmt(pwf.consistency * 100, 0) + "%" : "—"}</b> · ליקווידציות: <b class="pos">${pwf.total_liqs ?? 0}</b></div>
      </div>
    `;
  }

  const nBody = $("news-body");
  if (nBody) {
    nBody.innerHTML = (DATA.news || []).slice(0, 20).map((n) => `
      <tr>
        <td class="num muted">${fmtDateTime(n.ts)}</td>
        <td class="muted">${esc(n.source || "")}</td>
        <td><span class="badge ${n.sentiment > 0.1 ? 'green' : (n.sentiment < -0.1 ? 'red' : '')}">${n.sentiment > 0.1 ? "חיובי" : (n.sentiment < -0.1 ? "שלילי" : "ניטרלי")}</span></td>
        <td>${esc(n.title)}</td>
      </tr>
    `).join("") || `<tr><td colspan="4" class="muted">אין חדשות במאגר</td></tr>`;
  }

  const pf = DATA.performance || {};
  const kpiEl = $("perf-kpis");
  if (kpiEl) {
    kpiEl.innerHTML = `
      <div class="rule-box"><div class="rule-k">Profit Factor חי (סגורות)</div><div class="rule-v num cyan">${fmt(pf.live_pf, 2)}</div></div>
      <div class="rule-box"><div class="rule-k">אחוז הצלחה חי</div><div class="rule-v num">${fmt(pf.win_rate_pct, 1)}% (${pf.wins || 0}/${pf.total_trades || 0})</div></div>
      <div class="rule-box"><div class="rule-k">רווח ממוצע לעסקה</div><div class="rule-v num pos">+$${fmt(pf.avg_win, 2)}</div></div>
      <div class="rule-box"><div class="rule-k">הפסד ממוצע לעסקה</div><div class="rule-v num neg">-$${fmt(pf.avg_loss, 2)}</div></div>
    `;
  }
  const stBody = $("perf-strat-body");
  if (stBody) {
    stBody.innerHTML = (pf.by_strategy || []).map((s) => `
      <tr>
        <td><b>${esc(s.strategy)}</b></td>
        <td class="num">${s.trades}</td>
        <td class="num">${fmt(s.win_rate_pct, 1)}%</td>
        <td class="num ${pnlCls(s.pnl)}"><b>${fmtSigned(s.pnl)}$</b></td>
      </tr>
    `).join("") || `<tr><td colspan="4" class="muted">ממתין לסגירת עסקאות</td></tr>`;
  }
  const syBody = $("perf-sym-body");
  if (syBody) {
    syBody.innerHTML = (pf.top_symbols || []).map((s) => `
      <tr>
        <td><b>${esc(s.symbol)}</b></td>
        <td><span class="badge ${s.arm === 'perps' ? 'blue' : ''}">${s.arm === 'perps' ? 'PERPS' : 'Poly'}</span></td>
        <td class="num">${s.trades}</td>
        <td class="num ${pnlCls(s.pnl)}"><b>${fmtSigned(s.pnl)}$</b></td>
      </tr>
    `).join("") || `<tr><td colspan="4" class="muted">אין היסטוריית נכסים עדיין</td></tr>`;
  }

  renderPerpsThesis();
  if (BOOK_CACHE[PERP_SYM]) renderPerpDepth(BOOK_CACHE[PERP_SYM]);
}

function renderPerpsThesis() {
  const box = $("perps-thesis-box");
  if (!box) return;
  const perps = DATA.perps || {};
  const sym = PERP_SYM || "BTC";
  const pos = (perps.positions || []).find((p) => p.symbol === sym);
  const intel = (perps.intel || []).find((r) => r.symbol === sym);
  if (pos) {
    box.innerHTML = `
      <div style="display:flex;justify-content:space-between;align-items:center">
        <b>${esc(pos.symbol)} · ${esc(pos.side)} ×${fmt(pos.leverage, 1)}</b>
        <span class="num ${pnlCls(pos.unrealized_pnl)}"><b>${fmtSigned(pos.unrealized_pnl)}$</b></span>
      </div>
      <div class="chip-grid">
        <span class="chip">כניסה <b class="num">${fmt(pos.entry_price, 4)}</b></span>
        <span class="chip">כעת <b class="num">${fmt(pos.mark_price, 4)}</b></span>
        <span class="chip">ניזול <b class="num pos">${fmt(pos.liq_distance_pct, 1)}%</b></span>
      </div>
    `;
  } else if (intel) {
    box.innerHTML = `
      <div style="display:flex;justify-content:space-between;align-items:center">
        <b>${esc(intel.symbol)} (${esc((intel.exchange || "").toUpperCase())})</b>
        <span class="badge ${intel.score >= 0.56 ? 'green' : 'blue'}">${esc(intel.regime || "SCAN")}</span>
      </div>
      <div style="margin-top:6px" class="muted">${esc(intel.reason || "במעקב חי")}</div>
      <div class="chip-grid">
        <span class="chip">ADX <b class="num">${fmt(intel.adx, 1)}</b></span>
        <span class="chip">RSI <b class="num">${fmt(intel.rsi, 0)}</b></span>
        <span class="chip">ציון <b class="num">${fmt(intel.score, 2)}</b></span>
        <span class="chip">מינוף מוצע <b class="num">×${fmt(intel.rec_leverage, 1)}</b></span>
      </div>
    `;
  } else {
    box.textContent = "בחר מטבע מהרשימה לצפייה בגרף ובנתוני ההחלטה שלו.";
  }
}

async function runPerpsSim() {
  const out = $("perps-sim-res");
  const lev = Number(($("sim-lev") && $("sim-lev").value) || 50);
  const sl = Number(($("sim-sl") && $("sim-sl").value) || 1.5);
  const tp = Number(($("sim-tp") && $("sim-tp").value) || 2.6);
  try {
    if (out) out.textContent = "מריץ בדיקה על נתוני אמת היסטוריים...";
    const res = await apiPost("/api/perps/simulate", { max_leverage: lev, sl_atr_mult: sl, tp_atr_mult: tp });
    if (res.result && out) {
      const r = res.result;
      out.innerHTML = `תוצאה על ${r.assets} מטבעות: <b class="${pnlCls(r.return_pct)} num">${fmtSigned(r.return_pct)}%</b> · הצלחה <b>${fmt(r.win_rate_pct, 0)}%</b> · ירידה מרבית <b>${fmt(r.max_drawdown_pct, 1)}%</b> · ליקווידציות: <b class="${r.liquidations > 0 ? 'neg' : 'pos'}">${r.liquidations}</b>`;
    } else if (out) {
      out.textContent = res.message || "הושלם";
    }
  } catch (e) {
    if (out) out.textContent = "שגיאה: " + (e.message || e);
  }
}

function syncConfigForm() {
  const cfg = DATA.config || {};
  const pc = cfg.perps || {};
  const r = cfg.risk || {};
  const ap = cfg.autopilot || {};
  if ($("cfg-perps-en")) $("cfg-perps-en").value = pc.enabled === false ? "0" : "1";
  if ($("cfg-perps-risk") && pc.risk_per_trade_pct != null) $("cfg-perps-risk").value = (pc.risk_per_trade_pct * 100).toFixed(1);
  if ($("cfg-perps-lev") && pc.max_leverage != null) $("cfg-perps-lev").value = pc.max_leverage;
  if ($("cfg-perps-pos") && pc.max_open_positions != null) $("cfg-perps-pos").value = pc.max_open_positions;
  if ($("cfg-perps-int") && pc.interval_sec != null) $("cfg-perps-int").value = pc.interval_sec;
  if ($("cfg-poly-risk") && r.risk_per_trade_pct != null) $("cfg-poly-risk").value = (r.risk_per_trade_pct * 100).toFixed(1);
  if ($("cfg-poly-pos") && r.max_open_positions != null) $("cfg-poly-pos").value = r.max_open_positions;
  if ($("cfg-poly-int") && ap.trade_interval_sec != null) $("cfg-poly-int").value = ap.trade_interval_sec;
}

function renderSettingsTab() {
  syncConfigForm();
  const tr = DATA.trader || {};
  const autoEl = $("autonomous-strip");
  if (autoEl) {
    const au = DATA.autonomous || {};
    const upMin = Math.floor(Number(tr.uptime_sec || au.uptime_sec || 0) / 60);
    autoEl.innerHTML = `
      <div class="rule-box"><div class="rule-k">זמן פעילות רציף (Uptime)</div><div class="rule-v num cyan">${upMin} דק׳</div></div>
      <div class="rule-box"><div class="rule-k">מחזורי מסחר אוטומטיים</div><div class="rule-v num">${tr.cycles || 0} Poly · ${tr.perps_cycles || 0} PERPS</div></div>
      <div class="rule-box"><div class="rule-k">מחזורי אבולוציה ולמידה</div><div class="rule-v num pos">${tr.learn_cycles || 0} Poly · ${tr.perps_learn_cycles || au.perps_learn_cycles || 0} PERPS</div></div>
      <div class="rule-box"><div class="rule-k">תחזוקת DB וריפוי עצמי</div><div class="rule-v num">${tr.housekeeping_cycles || au.housekeeping_cycles || 0} תחזוקות · ${fmt(au.db_size_kb, 0)} KB (${tr.auto_recoveries || 0} התאוששויות)</div></div>
    `;
  }
  const rd = DATA.readiness || {};
  const rdBadge = $("readiness-summary");
  if (rdBadge) {
    rdBadge.textContent = rd.summary || "—";
    rdBadge.className = "badge " + (rd.ready ? "green" : "amber");
  }
  const rdBody = $("readiness-body");
  if (rdBody) {
    rdBody.innerHTML = (rd.checks || []).map((c) => {
      const cls = c.status === "ok" ? "green" : (c.status === "warn" ? "amber" : "red");
      const lbl = c.status === "ok" ? "תקין" : (c.status === "warn" ? "המלצה" : "ממתין");
      return `<tr><td><span class="badge ${cls}">${lbl}</span></td><td><b>${esc(c.label)}</b></td><td class="muted">${esc(c.detail)}</td></tr>`;
    }).join("") || `<tr><td colspan="3" class="muted">אין בדיקות</td></tr>`;
  }

  const rules = $("risk-rules-grid");
  if (rules && DATA.config) {
    const u = DATA.config.universe || {};
    const s = DATA.config.signal || {};
    const r = DATA.config.risk || {};
    const items = [
      ["הגנת הפסד יומית", `עד ${((r.max_daily_loss_pct || 0.05) * 100).toFixed(0)}% מההון`],
      ["עצירת חירום אוטומטית", `בירידה של ${((r.max_drawdown_pct || 0.2) * 100).toFixed(0)}% מהשיא`],
      ["הרחקה מהכרעת שווקים", `לפחות ${u.min_entry_hours_to_resolution ?? 48} שעות לפני סגירה`],
      ["טווח מחירים בטוח ב־Polymarket", `${(u.price_band || [0.2, 0.85]).join(" – ")}`],
      ["יעד והגנה לעסקת Polymarket", `יעד +${s.take_profit ?? 0.06} · הגנה -${s.stop_loss ?? 0.07}`],
      ["מינוף מדורג ב־PERPS", `עד ×${(DATA.perps && DATA.perps.max_leverage) || 50} (A+ 1.3× · A 1.1× · B 0.85×)`],
    ];
    rules.innerHTML = items.map(([k, v]) => `<div class="rule-box"><div class="rule-k">${esc(k)}</div><div class="rule-v">${esc(v)}</div></div>`).join("");
  }

  const apBody = $("autopilot-body");
  if (apBody) {
    apBody.innerHTML = (DATA.autopilot || []).slice(0, 12).map((a) => `
      <tr><td class="num muted">${fmtDateTime(a.ts)}</td><td class="muted">${esc(a.kind)}</td><td>${esc(a.summary || "")}</td></tr>
    `).join("") || `<tr><td colspan="3" class="muted">היומן יתעדכן במחזור האוטומטי הבא</td></tr>`;
  }

  const bkBody = $("backups-body");
  if (bkBody) {
    bkBody.innerHTML = (DATA.backups || []).slice(0, 6).map((b) => `
      <tr><td class="num">${esc(b.name)}</td><td class="num">${fmt(b.size_kb, 1)} KB</td><td class="num muted">${fmtDateTime(b.ts)}</td></tr>
    `).join("") || `<tr><td colspan="3" class="muted">אין גיבויים שמורים</td></tr>`;
  }
}

function openSpot() {
  const ov = $("spot-overlay");
  if (!ov) return;
  ov.classList.add("open");
  const inp = $("spot-inp");
  if (inp) { inp.value = ""; inp.focus(); }
  renderSpotList("");
}
function closeSpot() {
  const ov = $("spot-overlay");
  if (ov) ov.classList.remove("open");
}
function renderSpotList(q) {
  const box = $("spot-list");
  if (!box) return;
  const term = (q || "").trim().toLowerCase();
  const items = [];
  ((DATA.perps && DATA.perps.intel) || []).forEach((r) => items.push({ kind: "PERPS", title: `${r.symbol} (${r.exchange})`, sub: `${fmt(r.price, 3)}`, fn: () => { closeSpot(); switchTab("markets"); switchSubView("perps"); selectPerpAsset(r.symbol); } }));
  (DATA.positions || []).forEach((p) => {
    const tid = p.full_token_id || p.token_id;
    items.push({ kind: "פתוח", title: p.question || tid, sub: `כניסה ${fmt(p.avg_price, 3)}`, fn: () => { closeSpot(); switchTab("home"); selectHomeAsset("poly", tid); } });
  });
  (DATA.market_intel || []).slice(0, 18).forEach((m) => items.push({ kind: "שוק", title: m.question || m.token_id, sub: `${fmt(m.price, 3)}`, fn: () => { closeSpot(); switchTab("markets"); switchSubView("poly"); selectPolyAsset(m.token_id); } }));
  const filt = items.filter((it) => !term || it.title.toLowerCase().includes(term) || it.kind.toLowerCase().includes(term)).slice(0, 15);
  window.__spotItems = filt;
  box.innerHTML = filt.map((it, i) => `
    <div class="spot-item" onclick="window.__spotItems[${i}].fn()">
      <div><span class="badge">${esc(it.kind)}</span> ${esc(it.title.slice(0, 56))}</div>
      <span class="num muted">${esc(it.sub)}</span>
    </div>
  `).join("") || `<div class="spot-item muted">לא נמצאו תוצאות</div>`;
}

function renderAll() {
  syncSelectors();
  renderHeader();
  renderHero();
  renderPositionsPanel();
  renderHomeBottomTables();
  renderMarketsTab();
  renderSettingsTab();
  redrawActiveCharts();
}

async function refreshState() {
  try {
    DATA = await apiGet("/api/state");
    renderAll();
  } catch (_) {}
}

function toggleLoop() {
  const btn = $("btn-loop");
  const running = btn && btn.getAttribute("data-running") === "1";
  runAction(running ? "/api/trader/stop" : "/api/trader/start", {});
}

function initApp(refreshSec) {
  if (!(DATA.combined_equity_curve && DATA.combined_equity_curve.length >= 2)) HOME_CHART_MODE = "asset";
  setHomeChartMode(HOME_CHART_MODE);
  renderAll();
  if (SELECTED_ASSET) {
    const prevMode = HOME_CHART_MODE;
    selectHomeAsset(SELECTED_ASSET.arm, SELECTED_ASSET.id, false).then(() => {
      if (prevMode === "equity") setHomeChartMode("equity");
    });
  }
  if (PERP_SYM) selectPerpAsset(PERP_SYM, false);
  if (POLY_TID) selectPolyAsset(POLY_TID, false);
  updateQuickPreview();

  bindCanvasCrosshair("home-chart", "home", drawHomeChart);
  bindCanvasCrosshair("perps-chart", "perps", drawPerpChart);
  bindCanvasCrosshair("mkt-chart", "poly", drawPolyChart);

  document.addEventListener("keydown", (ev) => {
    if ((ev.metaKey || ev.ctrlKey) && ev.key.toLowerCase() === "k") { ev.preventDefault(); openSpot(); }
    else if (ev.key === "Escape") closeSpot();
  });
  window.addEventListener("resize", () => redrawActiveCharts());
  if (refreshSec > 0) POLL_TIMER = setInterval(() => refreshState(), Math.max(5, refreshSec) * 1000);
}
"""

_BRAND_SVG = (
    '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" '
    'stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
    '<polyline points="22 7 13.5 15.5 8.5 10.5 2 17"></polyline>'
    '<polyline points="16 7 22 7 22 13"></polyline></svg>'
)

_HTML_TEMPLATE = """<!doctype html>
<html lang="he" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>PMMB Command Center</title>
<style>__PMMB_CSS__</style>
</head>
<body>
<header class="header">
  <div class="header-inner">
    <div class="brand">
      <div class="logo-mark">__PMMB_SVG__</div>
      <div>
        <div class="brand-title">PMMB Command Center</div>
        <div class="brand-sub"><span id="hdr-dot" class="status-dot"></span><span id="hdr-status-text">טוען מצב מערכת...</span></div>
      </div>
    </div>
    <nav class="nav-pills">
      <button class="nav-tab active" data-tab="home" onclick="switchTab('home')">התיק והמסחר שלי</button>
      <button class="nav-tab" data-tab="markets" onclick="switchTab('markets')">שווקים, PERPS וחדשות</button>
      <button class="nav-tab" data-tab="settings" onclick="switchTab('settings')">מוכנות, סיכונים והגדרות</button>
    </nav>
    <div class="header-actions">
      <button class="btn sm" onclick="openSpot()">חיפוש (⌘K)</button>
      <button class="btn sm" onclick="runAction('/api/news-refresh')">רענן</button>
      <button id="btn-loop" class="btn sm primary" data-running="0" onclick="toggleLoop()">הפעל בוט</button>
      <button class="btn sm soft-red" onclick="runAction('/api/halt',{reason:'עצירת חירום ידנית'},'להפעיל עצירת חירום ולחסום פתיחת עסקאות חדשות?')">עצירת חירום</button>
    </div>
  </div>
</header>

<main class="container">
  <div id="halt-banner" class="alert-banner" style="display:none">
    <div><b>הבוט במצב עצירת חירום:</b> <span id="halt-reason"></span></div>
    <button class="btn sm" onclick="runAction('/api/resume',{})">בטל עצירה וחזור לפעילות</button>
  </div>

  <!-- TAB 1: Home / Essential Portfolio -->
  <section id="tab-home" class="tab-pane active">
    <div id="combined-hero" class="hero-grid"></div>

    <div class="main-split">
      <div class="card">
        <div class="card-head">
          <div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap">
            <button id="btn-hc-eq" class="btn sm active-mode" onclick="setHomeChartMode('equity')">עקומת הון התיק</button>
            <button id="btn-hc-daily" class="btn sm" onclick="setHomeChartMode('daily')">רווח יומי (עמודות)</button>
            <button id="btn-hc-asset" class="btn sm" onclick="setHomeChartMode('asset')">גרף נכס חי</button>
          </div>
          <div style="display:flex;gap:8px;align-items:center">
            <select id="home-asset-sel" class="sel" onchange="const v=this.value.split(':');selectHomeAsset(v[0],v.slice(1).join(':'),false)"></select>
            <button class="btn sm" onclick="if(SELECTED_ASSET)selectHomeAsset(SELECTED_ASSET.arm,SELECTED_ASSET.id,true)">עדכן חי</button>
          </div>
        </div>
        <div class="card-pad">
          <div class="chart-wrap">
            <canvas id="home-chart"></canvas>
            <div id="home-tip" class="chart-tip"></div>
          </div>
          <div id="home-chart-stats" class="chart-stats"></div>
        </div>
      </div>

      <div class="card">
        <div class="card-head">
          <div>
            <div class="card-title">הפוזיציות הפתוחות שלי</div>
            <div class="card-sub">ערוך הגנה/יעד, סגור עסקה בודדת או הכל</div>
          </div>
          <button id="btn-close-all" class="btn xs soft-red" style="display:none" onclick="closeAllPositions()">סגור הכל</button>
        </div>
        <div id="home-positions-list" class="pos-list"></div>
      </div>
    </div>

    <div class="grid-2">
      <div class="card">
        <div class="card-head">
          <div class="card-title">עסקאות אחרונות שנסגרו</div>
          <button type="button" class="btn sm" onclick="downloadTradesCsv()">הורד CSV</button>
        </div>
        <div class="tbl-scroll">
          <table class="clean-tbl">
            <thead><tr><th>זמן</th><th>נכס / שוק</th><th>רווח/הפסד</th><th>סיבה</th></tr></thead>
            <tbody id="home-closed-body"></tbody>
          </table>
        </div>
      </div>
      <div class="card">
        <div class="card-head">
          <div class="card-title">הזדמנויות שהבוט עוקב אחריהן</div>
          <span class="badge blue">PERPS ×50 · Polymarket</span>
        </div>
        <div class="tbl-scroll">
          <table class="clean-tbl">
            <thead><tr><th>מנוע</th><th>נכס / שוק</th><th>מחיר</th><th>ציון</th><th>מצב</th></tr></thead>
            <tbody id="home-opps-body"></tbody>
          </table>
        </div>
      </div>
    </div>
  </section>

  <!-- TAB 2: Markets, PERPS x50 & Walk-Forward -->
  <section id="tab-markets" class="tab-pane">
    <div class="sub-nav">
      <button class="sub-btn active" data-sub="perps" onclick="switchSubView('perps')">חוזי PERPS ×50</button>
      <button class="sub-btn" data-sub="poly" onclick="switchSubView('poly')">שווקי Polymarket</button>
      <button class="sub-btn" data-sub="research" onclick="switchSubView('research')">חדשות ואימות אסטרטגיה (Walk-Forward)</button>
    </div>

    <div id="sub-perps" class="sub-view active">
      <div class="main-split">
        <div class="card">
          <div class="card-head">
            <div>
              <div class="card-title">גרף נרות אינטראקטיבי PERPS ×50</div>
              <div class="card-sub">הזז עכבר על הנרות לפירוט OHLC · OKX / Hyperliquid</div>
            </div>
            <div style="display:flex;gap:8px">
              <select id="perp-asset-sel" class="sel" onchange="selectPerpAsset(this.value,false)"></select>
              <button class="btn sm primary" onclick="runAction('/api/perps/cycle')">סרוק PERPS עכשיו</button>
            </div>
          </div>
          <div class="card-pad">
            <div class="chart-wrap">
              <canvas id="perps-chart"></canvas>
              <div id="perps-tip" class="chart-tip"></div>
            </div>
            <div id="perps-depth-box" class="rule-box" style="margin-top:12px"></div>
          </div>
        </div>

        <div class="card">
          <div class="card-head"><div class="card-title">תזת נכס, מסחר מהיר וסימולטור</div></div>
          <div class="card-pad" style="display:flex;flex-direction:column;gap:14px">
            <div id="perps-thesis-box" class="rule-box" style="font-size:13px"></div>

            <!-- Quick Manual Paper Order -->
            <div class="rule-box" style="display:flex;flex-direction:column;gap:10px">
              <div style="display:flex;justify-content:space-between;align-items:center">
                <b style="font-size:13px">פתיחת עסקה ידנית (Paper)</b>
                <span class="badge blue">הגנת SL/TP אוטומטית</span>
              </div>
              <div class="side-toggle">
                <button id="qt-long" class="btn sm soft-green" onclick="setQuickSide('LONG')">LONG (עלייה)</button>
                <button id="qt-short" class="btn sm" onclick="setQuickSide('SHORT')">SHORT (ירידה)</button>
              </div>
              <div style="display:flex;gap:10px;align-items:center">
                <label style="font-size:12px;color:var(--muted);flex:1">מרג׳ין ($)<br>
                  <input id="qt-margin" class="inp num" style="width:100%;margin-top:4px" type="number" min="5" step="5" value="25" oninput="updateQuickPreview()">
                </label>
                <label style="font-size:12px;color:var(--muted);flex:1.4">מינוף: <b id="qt-lev-lbl" class="num cyan">×15</b><br>
                  <input id="qt-lev" class="range-inp" style="margin-top:9px" type="range" min="2" max="50" value="15" oninput="updateQuickPreview()">
                </label>
              </div>
              <div id="qt-preview" class="muted" style="font-size:12px"></div>
              <button class="btn sm primary" onclick="submitQuickOrder()">בצע עסקת PERPS</button>
            </div>

            <!-- Simulator -->
            <div class="rule-box" style="display:flex;flex-direction:column;gap:10px">
              <b style="font-size:13px">בדיקת תרחיש 30 יום (What-If)</b>
              <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:flex-end">
                <label style="font-size:11.5px;color:var(--muted)">מינוף<br><input id="sim-lev" class="inp num" style="width:68px;margin-top:4px" type="number" min="2" max="50" value="50"></label>
                <label style="font-size:11.5px;color:var(--muted)">SL (×ATR)<br><input id="sim-sl" class="inp num" style="width:68px;margin-top:4px" type="number" step="0.1" min="0.8" max="4" value="1.5"></label>
                <label style="font-size:11.5px;color:var(--muted)">TP (×ATR)<br><input id="sim-tp" class="inp num" style="width:68px;margin-top:4px" type="number" step="0.1" min="1.2" max="6" value="3.4"></label>
                <button class="btn sm primary" onclick="runPerpsSim()">הרץ בדיקה</button>
              </div>
              <div id="perps-sim-res" class="muted" style="font-size:12.5px">הרץ סימולציה על נתוני אמת היסטוריים.</div>
            </div>
          </div>
        </div>
      </div>

      <div class="card">
        <div class="card-head">
          <div class="card-title">16 הנכסים הנסרקים ב־PERPS ×50</div>
          <button id="btn-sig-filter" class="btn sm" onclick="toggleSignalFilter()">הצג רק איתותים פעילים</button>
        </div>
        <div class="tbl-scroll">
          <table class="clean-tbl">
            <thead><tr><th>מטבע</th><th>בורסה</th><th>מחיר</th><th>מגמה</th><th>ציון איכות</th><th>מצב</th><th>הסבר</th></tr></thead>
            <tbody id="perps-scan-body"></tbody>
          </table>
        </div>
      </div>
    </div>

    <div id="sub-poly" class="sub-view">
      <div class="card" style="margin-bottom:16px">
        <div class="card-head">
          <div class="card-title">גרף מחיר Polymarket</div>
          <div style="display:flex;gap:8px">
            <select id="poly-asset-sel" class="sel" onchange="selectPolyAsset(this.value,false)"></select>
            <button class="btn sm primary" onclick="runAction('/api/paper-cycle')">סרוק Polymarket עכשיו</button>
          </div>
        </div>
        <div class="card-pad">
          <div class="chart-wrap">
            <canvas id="mkt-chart"></canvas>
            <div id="poly-tip" class="chart-tip"></div>
          </div>
        </div>
      </div>
      <div class="card">
        <div class="card-head">
          <div class="card-title">שווקי תחזית נסרקים</div>
          <input id="poly-filter" class="inp" placeholder="חפש שוק..." oninput="renderMarketsTab()">
        </div>
        <div class="tbl-scroll">
          <table class="clean-tbl">
            <thead><tr><th>שוק</th><th>תחום</th><th>מחיר</th><th>סטייה (Z)</th><th>ציון</th><th>מצב</th></tr></thead>
            <tbody id="poly-scan-body"></tbody>
          </table>
        </div>
      </div>
    </div>

    <div id="sub-research" class="sub-view">
      <div class="card" style="margin-bottom:16px">
        <div class="card-head">
          <div class="card-title">אימות ביצועים מחוץ למדגם (Walk-Forward)</div>
          <button class="btn sm primary" onclick="runAction('/api/learn',{apply:true})">הרץ בדיקת למידה</button>
        </div>
        <div id="wf-summary-cards" class="rule-grid"></div>
      </div>

      <div class="card" style="margin-bottom:16px">
        <div class="card-head">
          <div class="card-title">ביצועי אמת לפי אסטרטגיה ונכסים (Performance Attribution)</div>
          <span class="badge blue">Live DB Analytics</span>
        </div>
        <div id="perf-kpis" class="rule-grid" style="grid-template-columns:repeat(4,minmax(0,1fr));padding-bottom:8px"></div>
        <div class="grid-2" style="padding:10px 20px 18px;margin-bottom:0">
          <div class="tbl-scroll" style="border:1px solid var(--border);border-radius:12px">
            <table class="clean-tbl">
              <thead><tr><th>אסטרטגיה</th><th>עסקאות</th><th>הצלחה</th><th>רווח/הפסד</th></tr></thead>
              <tbody id="perf-strat-body"></tbody>
            </table>
          </div>
          <div class="tbl-scroll" style="border:1px solid var(--border);border-radius:12px">
            <table class="clean-tbl">
              <thead><tr><th>נכס / שוק</th><th>מנוע</th><th>עסקאות</th><th>רווח/הפסד</th></tr></thead>
              <tbody id="perf-sym-body"></tbody>
            </table>
          </div>
        </div>
      </div>

      <div class="card">
        <div class="card-head"><div class="card-title">חדשות גלובליות המשפיעות על הבוט</div></div>
        <div class="tbl-scroll">
          <table class="clean-tbl">
            <thead><tr><th>זמן</th><th>מקור</th><th>השפעה</th><th>כותרת</th></tr></thead>
            <tbody id="news-body"></tbody>
          </table>
        </div>
      </div>
    </div>
  </section>

  <!-- TAB 3: Readiness, Live Settings & Autopilot -->
  <section id="tab-settings" class="tab-pane">
    <div class="card" style="margin-bottom:18px">
      <div class="card-head">
        <div>
          <div class="card-title">מנוע אוטונומיה והתפתחות עצמית רציפה</div>
          <div class="card-sub">ניהול עצמי של סריקות, אימות OOS, תחזוקת DB, ריפוי עצמי וגיבויים</div>
        </div>
        <button class="btn sm primary" onclick="runAction('/api/autonomous/evolve',{})">הרץ אבולוציה ותחזוקה מלאה עכשיו</button>
      </div>
      <div id="autonomous-strip" class="rule-grid"></div>
    </div>

    <div class="card" style="margin-bottom:18px">
      <div class="card-head">
        <div>
          <div class="card-title">שליטה ישירה בבוט ובניהול הסיכון</div>
          <div class="card-sub">השינויים מוחלים מיד על הבוט הרץ ונשמרים אוטומטית ב־config.yaml</div>
        </div>
        <button class="btn sm primary" onclick="saveBotConfig()">שמור והחל הגדרות</button>
      </div>
      <div class="cfg-grid">
        <div class="cfg-field"><label>זרוע PERPS ×50</label><select id="cfg-perps-en" class="sel"><option value="1">פעילה</option><option value="0">מושהית</option></select></div>
        <div class="cfg-field"><label>סיכון לעסקת PERPS (%)</label><input id="cfg-perps-risk" class="inp num" type="number" step="0.1" min="0.5" max="5.0" value="3.0"></div>
        <div class="cfg-field"><label>מינוף מקסימלי (×2–×50)</label><input id="cfg-perps-lev" class="inp num" type="number" min="2" max="50" value="50"></div>
        <div class="cfg-field"><label>מקסימום פוזיציות PERPS</label><input id="cfg-perps-pos" class="inp num" type="number" min="1" max="8" value="4"></div>
        <div class="cfg-field"><label>תדירות סריקת PERPS (שניות)</label><input id="cfg-perps-int" class="inp num" type="number" min="30" max="600" value="60"></div>
        <div class="cfg-field"><label>סיכון לעסקת Polymarket (%)</label><input id="cfg-poly-risk" class="inp num" type="number" step="0.1" min="0.5" max="5.0" value="3.0"></div>
        <div class="cfg-field"><label>מקסימום פוזיציות Polymarket</label><input id="cfg-poly-pos" class="inp num" type="number" min="1" max="12" value="7"></div>
        <div class="cfg-field"><label>תדירות מחזור Polymarket (שניות)</label><input id="cfg-poly-int" class="inp num" type="number" min="45" max="600" value="120"></div>
      </div>
    </div>

    <div class="grid-2">
      <div class="card">
        <div class="card-head"><div class="card-title">מוכנות למעבר לכסף אמיתי</div><span id="readiness-summary" class="badge">—</span></div>
        <div class="tbl-scroll">
          <table class="clean-tbl">
            <thead><tr><th>מצב</th><th>בדיקה</th><th>פירוט</th></tr></thead>
            <tbody id="readiness-body"></tbody>
          </table>
        </div>
      </div>
      <div class="card">
        <div class="card-head"><div class="card-title">כללי ההגנה של התיק</div></div>
        <div id="risk-rules-grid" class="rule-grid"></div>
      </div>
    </div>

    <div class="card" style="margin-bottom:16px">
      <div class="card-head">
        <div class="card-title">בקרת תשתית, גיבוי וייצוא</div>
        <div style="display:flex;gap:8px;flex-wrap:wrap">
          <button class="btn sm primary" onclick="runAction('/api/reconcile')">אמת חשבונות (Reconcile)</button>
          <button class="btn sm" onclick="runAction('/api/backup')">שמור גיבוי עכשיו</button>
          <button type="button" class="btn sm" onclick="downloadTradesCsv()">הורד היסטוריית עסקאות (CSV)</button>
          <button class="btn sm" onclick="runAction('/api/perps/learn',{apply:true})">כייל PERPS</button>
        </div>
      </div>
    </div>

    <div class="grid-2">
      <div class="card">
        <div class="card-head"><div class="card-title">יומן טייס אוטומטי</div></div>
        <div class="tbl-scroll">
          <table class="clean-tbl">
            <thead><tr><th>זמן</th><th>סוג</th><th>פירוט</th></tr></thead>
            <tbody id="autopilot-body"></tbody>
          </table>
        </div>
      </div>
      <div class="card">
        <div class="card-head"><div class="card-title">גיבויים שמורים</div></div>
        <div class="tbl-scroll">
          <table class="clean-tbl">
            <thead><tr><th>קובץ</th><th>גודל</th><th>תאריך</th></tr></thead>
            <tbody id="backups-body"></tbody>
          </table>
        </div>
      </div>
    </div>
  </section>
</main>

<div id="spot-overlay" class="spot-overlay" onclick="if(event.target===this)closeSpot()">
  <div class="spot-box">
    <div class="spot-head">
      <input id="spot-inp" class="spot-inp" placeholder="חפש מטבע, שוק או פוזיציה פתוחה..." oninput="renderSpotList(this.value)">
      <button class="btn sm" onclick="closeSpot()">סגור</button>
    </div>
    <div id="spot-list" class="spot-list"></div>
  </div>
</div>

<div id="toast" class="toast"></div>
<script>
window.__PMMB_INIT__ = __PMMB_DATA__;
__PMMB_JS__
initApp(__PMMB_REFRESH__);
</script>
</body>
</html>"""


def command_center_html(data: dict, *, refresh_sec: int = 30, interactive: bool = True) -> str:
    """מייצר ממשק אינטראקטיבי עצמאי, הייטקי ופשוט של PMMB Command Center."""
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    refresh_val = int(refresh_sec) if (interactive and refresh_sec > 0) else 0
    return (
        _HTML_TEMPLATE
        .replace("__PMMB_CSS__", _UI_CSS)
        .replace("__PMMB_SVG__", _BRAND_SVG)
        .replace("__PMMB_DATA__", payload)
        .replace("__PMMB_JS__", _UI_JS)
        .replace("__PMMB_REFRESH__", str(refresh_val))
    )
