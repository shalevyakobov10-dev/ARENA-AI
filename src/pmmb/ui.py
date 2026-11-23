"""
ממשק הבוט של PMMB — ממשק נקי, פשוט, אסתטי וברור בעברית.

עיצוב מודרני רגוע ומאוורר (Modern Slate Dark), עצמאי לחלוטין (ללא משאבים חיצוניים),
שמציג בדיוק את מה שצריך תוך 2 שניות: שווי, פוזיציות פתוחות עם סגירה בלחיצה, גרפים,
שווקים וחדשות, ובקרת מוכנות ובטיחות.
"""
from __future__ import annotations

import json

_UI_CSS = """
:root {
  --bg: #0D1117;
  --surface: #151B23;
  --surface-2: #1B232E;
  --hover: #212A38;
  --border: #242E3D;
  --border-soft: rgba(255, 255, 255, 0.06);
  --text: #F0F4F8;
  --muted: #93A1B5;
  --dim: #6B7A90;
  --green: #10B981;
  --green-soft: rgba(16, 185, 129, 0.13);
  --red: #EF4444;
  --red-soft: rgba(239, 68, 68, 0.13);
  --amber: #F59E0B;
  --amber-soft: rgba(245, 158, 11, 0.13);
  --accent: #3B82F6;
  --accent-soft: rgba(59, 130, 246, 0.14);
  --sans: system-ui, -apple-system, 'Segoe UI', Arial, sans-serif;
  --mono: 'JetBrains Mono', ui-monospace, 'SFMono-Regular', Menlo, monospace;
}
*, *::before, *::after { box-sizing: border-box; }
html, body {
  margin: 0;
  padding: 0;
  background: var(--bg);
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
.muted { color: var(--muted); }
.dim { color: var(--dim); }

/* Header */
.header {
  position: sticky;
  top: 0;
  z-index: 40;
  background: rgba(13, 17, 23, 0.94);
  border-bottom: 1px solid var(--border);
}
.header-inner {
  max-width: 1380px;
  margin: 0 auto;
  padding: 12px 20px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}
.brand {
  display: flex;
  align-items: center;
  gap: 12px;
}
.logo-mark {
  width: 34px;
  height: 34px;
  border-radius: 9px;
  background: linear-gradient(135deg, #2563EB, #10B981);
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 800;
  font-size: 13px;
  color: #fff;
  letter-spacing: 0.03em;
}
.brand-title {
  font-size: 15px;
  font-weight: 700;
  color: var(--text);
}
.brand-sub {
  font-size: 12px;
  color: var(--muted);
  display: flex;
  align-items: center;
  gap: 8px;
}
.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--green);
  display: inline-block;
}
.status-dot.halt { background: var(--red); }
.status-dot.idle { background: var(--amber); }

/* Navigation Segmented Bar */
.nav-pills {
  display: flex;
  align-items: center;
  gap: 4px;
  background: var(--surface);
  border: 1px solid var(--border);
  padding: 4px;
  border-radius: 10px;
}
.nav-tab {
  appearance: none;
  border: none;
  background: transparent;
  color: var(--muted);
  padding: 7px 14px;
  border-radius: 7px;
  font-size: 13px;
  font-weight: 600;
  font-family: inherit;
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
  white-space: nowrap;
}
.nav-tab:hover { color: var(--text); }
.nav-tab.active {
  background: var(--surface-2);
  color: var(--text);
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.25);
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

/* Buttons & Badges */
.btn {
  appearance: none;
  border: 1px solid var(--border);
  background: var(--surface-2);
  color: var(--text);
  border-radius: 8px;
  padding: 7px 13px;
  font-size: 13px;
  font-weight: 600;
  font-family: inherit;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  transition: background 0.15s, border-color 0.15s, transform 0.08s;
  white-space: nowrap;
  text-decoration: none;
}
.btn:hover { background: var(--hover); border-color: #354358; }
.btn:active { transform: scale(0.99); }
.btn.sm { padding: 5px 10px; font-size: 12px; border-radius: 7px; }
.btn.primary { background: var(--accent); border-color: var(--accent); color: #fff; }
.btn.primary:hover { background: #2563EB; }
.btn.soft-green { background: var(--green-soft); border-color: rgba(16, 185, 129, 0.35); color: var(--green); }
.btn.soft-red { background: var(--red-soft); border-color: rgba(239, 68, 68, 0.35); color: var(--red); }
.btn.soft-red:hover { background: rgba(239, 68, 68, 0.22); }

.badge {
  display: inline-flex;
  align-items: center;
  padding: 3px 8px;
  border-radius: 6px;
  font-size: 11.5px;
  font-weight: 600;
  background: var(--surface-2);
  color: var(--muted);
  border: 1px solid var(--border-soft);
  white-space: nowrap;
}
.badge.green { background: var(--green-soft); color: var(--green); border-color: rgba(16, 185, 129, 0.25); }
.badge.red { background: var(--red-soft); color: var(--red); border-color: rgba(239, 68, 68, 0.25); }
.badge.amber { background: var(--amber-soft); color: var(--amber); border-color: rgba(245, 158, 11, 0.25); }
.badge.blue { background: var(--accent-soft); color: #60A5FA; border-color: rgba(59, 130, 246, 0.25); }

/* Container & Layout */
.container {
  max-width: 1380px;
  margin: 0 auto;
  padding: 20px 20px 44px;
}
.tab-pane { display: none; }
.tab-pane.active { display: block; }

.alert-banner {
  background: var(--red-soft);
  border: 1px solid rgba(239, 68, 68, 0.35);
  border-radius: 12px;
  padding: 12px 16px;
  margin-bottom: 18px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  color: #FECACA;
}

/* Summary Hero Cards (4 spacious cards) */
.hero-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
  margin-bottom: 18px;
}
.card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 12px;
  box-shadow: 0 6px 20px rgba(0, 0, 0, 0.22);
  overflow: hidden;
}
.card-pad { padding: 18px 20px; }
.hero-label {
  font-size: 12.5px;
  color: var(--muted);
  margin-bottom: 8px;
  font-weight: 500;
}
.hero-value {
  font-size: 26px;
  font-weight: 700;
  color: var(--text);
  line-height: 1.2;
}
.hero-sub {
  margin-top: 8px;
  font-size: 12.5px;
  color: var(--muted);
}

/* Main Workspace 2 Columns */
.main-split {
  display: grid;
  grid-template-columns: minmax(0, 1.35fr) minmax(340px, 1fr);
  gap: 16px;
  margin-bottom: 18px;
  align-items: start;
}
.grid-2 {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
  margin-bottom: 18px;
}

.card-head {
  padding: 14px 18px;
  border-bottom: 1px solid var(--border);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  flex-wrap: wrap;
}
.card-title {
  font-size: 15px;
  font-weight: 700;
  color: var(--text);
}
.card-sub {
  font-size: 12px;
  color: var(--muted);
}

/* Form Elements */
.sel, .inp {
  background: var(--bg);
  color: var(--text);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 6px 11px;
  font-size: 13px;
  font-family: inherit;
  outline: none;
}
.sel:focus, .inp:focus { border-color: var(--accent); }

/* Chart */
.chart-wrap {
  position: relative;
  height: 320px;
  width: 100%;
  background: #0B0F15;
  border: 1px solid var(--border-soft);
  border-radius: 10px;
  overflow: hidden;
}
.chart-wrap canvas { width: 100%; height: 100%; display: block; }
.chart-stats {
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--border-soft);
  font-size: 12.5px;
  color: var(--muted);
}
.chart-stat-item b { color: var(--text); font-weight: 600; }

/* Position Cards (Human Friendly) */
.pos-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-height: 410px;
  overflow-y: auto;
  padding: 14px;
}
.pos-item {
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 13px 14px;
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s;
}
.pos-item:hover { background: var(--hover); border-color: #36455B; }
.pos-item.selected { border-color: var(--accent); }
.pos-top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 8px;
}
.pos-name {
  font-weight: 600;
  font-size: 13.5px;
  color: var(--text);
  line-height: 1.35;
}
.pos-pnl {
  font-family: var(--mono);
  font-weight: 700;
  font-size: 14px;
  text-align: left;
  white-space: nowrap;
}
.pos-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  flex-wrap: wrap;
  font-size: 12px;
  color: var(--muted);
}

/* Clean Tables */
.tbl-scroll { overflow-x: auto; max-height: 400px; overflow-y: auto; }
table.clean-tbl {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
table.clean-tbl th {
  text-align: right;
  padding: 10px 14px;
  font-size: 12px;
  font-weight: 600;
  color: var(--muted);
  border-bottom: 1px solid var(--border);
  background: var(--surface);
  position: sticky;
  top: 0;
  white-space: nowrap;
}
table.clean-tbl td {
  padding: 10px 14px;
  border-bottom: 1px solid var(--border-soft);
  vertical-align: middle;
}
table.clean-tbl tbody tr:hover { background: rgba(255, 255, 255, 0.025); }
table.clean-tbl tbody tr.clickable { cursor: pointer; }

/* Sub-switcher inside Markets tab */
.sub-nav {
  display: inline-flex;
  gap: 4px;
  background: var(--surface);
  border: 1px solid var(--border);
  padding: 4px;
  border-radius: 10px;
  margin-bottom: 16px;
}
.sub-btn {
  appearance: none;
  border: none;
  background: transparent;
  color: var(--muted);
  padding: 7px 16px;
  border-radius: 7px;
  font-size: 13px;
  font-weight: 600;
  font-family: inherit;
  cursor: pointer;
}
.sub-btn.active {
  background: var(--accent-soft);
  color: #93C5FD;
}
.sub-view { display: none; }
.sub-view.active { display: block; }

/* Checklist & Rules */
.rule-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  padding: 16px 18px;
}
.rule-box {
  background: var(--surface-2);
  border: 1px solid var(--border-soft);
  border-radius: 9px;
  padding: 12px 14px;
}
.rule-k { font-size: 12px; color: var(--muted); margin-bottom: 4px; }
.rule-v { font-size: 15px; font-weight: 700; color: var(--text); }

/* Search Overlay (#spot-overlay) */
.spot-overlay {
  position: fixed;
  inset: 0;
  background: rgba(9, 12, 17, 0.78);
  z-index: 100;
  display: none;
  align-items: flex-start;
  justify-content: center;
  padding-top: 88px;
}
.spot-overlay.open { display: flex; }
.spot-box {
  width: min(600px, 92vw);
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 14px;
  box-shadow: 0 20px 50px rgba(0, 0, 0, 0.5);
  overflow: hidden;
}
.spot-head {
  padding: 12px 16px;
  border-bottom: 1px solid var(--border);
  display: flex;
  align-items: center;
  gap: 10px;
}
.spot-inp {
  width: 100%;
  background: transparent;
  border: none;
  outline: none;
  color: var(--text);
  font-size: 14px;
  font-family: inherit;
}
.spot-list { max-height: 360px; overflow-y: auto; }
.spot-item {
  padding: 11px 16px;
  border-bottom: 1px solid var(--border-soft);
  display: flex;
  justify-content: space-between;
  align-items: center;
  cursor: pointer;
}
.spot-item:hover { background: var(--hover); }

/* Toast */
.toast {
  position: fixed;
  bottom: 18px;
  left: 18px;
  z-index: 95;
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 11px 16px;
  font-size: 13px;
  box-shadow: 0 10px 28px rgba(0, 0, 0, 0.4);
  display: none;
  max-width: 420px;
}
.toast.show { display: block; }
.toast.ok { border-color: rgba(16, 185, 129, 0.45); color: #A7F3D0; }
.toast.err { border-color: rgba(239, 68, 68, 0.45); color: #FECACA; }

@media (max-width: 1080px) {
  .hero-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .main-split, .grid-2, .rule-grid { grid-template-columns: 1fr; }
}
@media (max-width: 640px) {
  .hero-grid { grid-template-columns: 1fr; }
  .header-inner { padding: 10px 14px; }
  .container { padding: 14px 12px 32px; }
}
"""

_UI_JS = r"""
let DATA = window.__PMMB_INIT__ || {};
let ACTIVE_TAB = "home";
let ACTIVE_SUB = "perps";
let SELECTED_ASSET = null; // { arm: "perps"|"poly", id: "..." }
let PERP_SYM = null;
let POLY_TID = null;
let CHART_CACHE = { home: null, perps: null, poly: null };
let POLL_TIMER = null;

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

async function apiGet(url) {
  const r = await fetch(url, { cache: "no-store" });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.error || ("HTTP " + r.status));
  return j;
}
async function apiPost(url, body = {}) {
  const r = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.error || ("HTTP " + r.status));
  return j;
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

function switchTab(tab) {
  ACTIVE_TAB = tab;
  document.querySelectorAll(".nav-tab").forEach((b) => {
    b.classList.toggle("active", b.getAttribute("data-tab") === tab);
  });
  document.querySelectorAll(".tab-pane").forEach((p) => {
    p.classList.toggle("active", p.id === "tab-" + tab);
  });
  redrawActiveCharts();
}

function switchSubView(name) {
  ACTIVE_SUB = name;
  document.querySelectorAll(".sub-btn").forEach((b) => {
    b.classList.toggle("active", b.getAttribute("data-sub") === name);
  });
  document.querySelectorAll(".sub-view").forEach((v) => {
    v.classList.toggle("active", v.id === "sub-" + name);
  });
  redrawActiveCharts();
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
    const stateLabel = halt ? "המסחר נעצר (חירום)" : (tr.running ? "הבוט פעיל אוטומטית" : "הבוט מושהה");
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

  const unr = Number(poly.unrealized_pnl || 0) + Number(perps.unrealized_pnl || 0);
  const closedCnt = Number(comb.closed_trades || 0);
  const totalWr = closedCnt > 0
    ? (((Number(ov.wins || 0)) + ((Number(perps.closed_trades || 0) * Number(perps.win_rate_pct || 0)) / 100)) / closedCnt * 100)
    : 0;
  const freeCash = Number(poly.cash || 0) + Number(perps.cash || 0);

  hero.innerHTML = `
    <div class="card card-pad">
      <div class="hero-label">שווי התיק הכולל</div>
      <div class="hero-value num">$${fmt(comb.equity)}</div>
      <div class="hero-sub">
        <span class="num ${pnlCls(comb.pnl)}">${fmtSigned(comb.pnl)}$ (${fmtSigned(comb.return_pct)}%)</span>
        <span class="dim"> · מ-${fmt(comb.starting_cash, 0)}$</span>
      </div>
      <div class="hero-sub">Polymarket <span class="num">$${fmt(poly.equity)}</span> · PERPS <span class="num">$${fmt(perps.equity)}</span></div>
    </div>

    <div class="card card-pad">
      <div class="hero-label">רווח פתוח והצלחת עסקאות</div>
      <div class="hero-value num ${pnlCls(unr)}">${fmtSigned(unr)}$</div>
      <div class="hero-sub">פוזיציות פתוחות עכשיו: <b>${comb.open_positions ?? 0}</b></div>
      <div class="hero-sub">${closedCnt} עסקאות נסגרו · הצלחה <span class="num">${fmt(totalWr, 0)}%</span> · עמלות <span class="num">$${fmt(comb.fees_paid)}</span></div>
    </div>

    <div class="card card-pad">
      <div class="hero-label">מזומן פנוי להשקעה</div>
      <div class="hero-value num">$${fmt(freeCash)}</div>
      <div class="hero-sub">פנוי ב־Polymarket: <span class="num">$${fmt(poly.cash)}</span></div>
      <div class="hero-sub">פנוי ב־PERPS ×50: <span class="num">$${fmt(perps.cash)}</span> (בשימוש <span class="num">$${fmt(perps.margin_used)}</span>)</div>
    </div>

    <div class="card card-pad">
      <div class="hero-label">מוכנות למעבר לכסף אמיתי</div>
      <div class="hero-value" style="font-size:20px">${rd.ready ? '<span class="pos">מוכן ל־Live</span>' : '<span class="warn">צבירת ניסיון</span>'}</div>
      <div class="hero-sub">הרצה נקייה: <b>${soak.days ?? 0}</b> מתוך <b>${soak.target_days ?? 7}</b> ימים</div>
      <div class="hero-sub"><button class="btn sm" style="margin-top:4px" onclick="switchTab('settings')">צפה בצ׳קליסט המלא</button></div>
    </div>
  `;
}

function getAllSelectableAssets() {
  const perps = DATA.perps || {};
  const list = [];
  (perps.positions || []).forEach((p) => {
    list.push({ arm: "perps", id: p.symbol, label: `פוזיציה פתוחה · ${p.symbol} (${p.side} ×${fmt(p.leverage, 0)})` });
  });
  (DATA.positions || []).forEach((p) => {
    const tid = p.full_token_id || p.token_id;
    list.push({ arm: "poly", id: tid, label: `פוזיציה פתוחה · ${(p.question || tid).slice(0, 38)}` });
  });
  (perps.intel || []).forEach((r) => {
    if (!list.some((x) => x.arm === "perps" && x.id === r.symbol)) {
      list.push({ arm: "perps", id: r.symbol, label: `PERPS · ${r.symbol} (${r.exchange})` });
    }
  });
  ((DATA.charts && DATA.charts.candidates) || []).forEach((c) => {
    if (!list.some((x) => x.arm === "poly" && x.id === c.token_id)) {
      list.push({ arm: "poly", id: c.token_id, label: `Polymarket · ${(c.question || c.token_id).slice(0, 38)}` });
    }
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
  const hSel = $("home-asset-sel");
  if (hSel) hSel.value = arm + ":" + id;
  if (arm === "perps") {
    const dc = DATA.perps && DATA.perps.default_chart;
    if (!live && dc && dc.symbol === id && (dc.candles || []).length) {
      CHART_CACHE.home = { kind: "perps", data: dc };
    } else {
      try {
        CHART_CACHE.home = { kind: "perps", data: await apiGet(`/api/perps/chart?symbol=${encodeURIComponent(id)}&live=${live ? 1 : 0}`) };
      } catch (_) {}
    }
  } else {
    const dc = DATA.charts && DATA.charts.default;
    if (!live && dc && String(dc.token_id || "").startsWith(String(id).slice(0, 12))) {
      CHART_CACHE.home = { kind: "poly", data: dc };
    } else {
      try {
        CHART_CACHE.home = { kind: "poly", data: await apiGet(`/api/chart?token=${encodeURIComponent(id)}&live=${live ? 1 : 0}`) };
      } catch (_) {}
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
    try {
      CHART_CACHE.perps = await apiGet(`/api/perps/chart?symbol=${encodeURIComponent(sym)}&live=${live ? 1 : 0}`);
    } catch (_) {}
  }
  drawPerpChart();
  renderPerpsThesis();
}

async function selectPolyAsset(tid, live = false) {
  POLY_TID = tid;
  const mSel = $("poly-asset-sel");
  if (mSel) mSel.value = tid;
  const dc = DATA.charts && DATA.charts.default;
  if (!live && dc && dc.token_id === tid && (dc.ticks || []).length) {
    CHART_CACHE.poly = dc;
  } else {
    try {
      CHART_CACHE.poly = await apiGet(`/api/chart?token=${encodeURIComponent(tid)}&live=${live ? 1 : 0}`);
    } catch (_) {}
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

function drawCandles(canvas, payload) {
  const s = initCanvas(canvas);
  if (!s) return;
  const { ctx, w, h } = s;
  ctx.fillStyle = "#0B0F15";
  ctx.fillRect(0, 0, w, h);

  const candles = (payload && payload.candles) || [];
  if (!candles.length) {
    ctx.fillStyle = "#93A1B5";
    ctx.font = "13px sans-serif";
    ctx.fillText("טוען נתוני נרות מהשוק...", 22, 42);
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

  ctx.strokeStyle = "rgba(255,255,255,0.05)";
  ctx.lineWidth = 1;
  ctx.font = "11px monospace";
  ctx.fillStyle = "#6B7A90";
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
    const col = c.close >= c.open ? "#10B981" : "#EF4444";
    ctx.strokeStyle = col;
    ctx.fillStyle = col;
    ctx.lineWidth = 1.2;
    ctx.beginPath(); ctx.moveTo(x, yOf(c.high)); ctx.lineTo(x, yOf(c.low)); ctx.stroke();
    const y1 = yOf(Math.max(c.open, c.close));
    const y2 = yOf(Math.min(c.open, c.close));
    ctx.fillRect(x - bw / 2, y1, bw, Math.max(2, y2 - y1));
  });

  [
    { px: ov.target, label: "יעד רווח", col: "#10B981" },
    { px: ov.entry, label: "כניסה", col: "#93C5FD" },
    { px: ov.stop, label: "הגנה (SL)", col: "#F59E0B" },
  ].forEach((lv) => {
    const v = Number(lv.px);
    if (!Number.isFinite(v) || v <= 0) return;
    const y = yOf(v);
    if (y < padT || y > h - padB) return;
    ctx.strokeStyle = lv.col;
    ctx.lineWidth = 1.1;
    if (typeof ctx.setLineDash === "function") ctx.setLineDash([5, 4]);
    ctx.beginPath(); ctx.moveTo(padL, y); ctx.lineTo(w - padR, y); ctx.stroke();
    if (typeof ctx.setLineDash === "function") ctx.setLineDash([]);
    ctx.fillStyle = lv.col;
    ctx.fillText(lv.label, padL + 6, y - 4);
  });
}

function drawSmoothLine(canvas, payload) {
  const s = initCanvas(canvas);
  if (!s) return;
  const { ctx, w, h } = s;
  ctx.fillStyle = "#0B0F15";
  ctx.fillRect(0, 0, w, h);

  const ticks = (payload && payload.ticks) || [];
  if (!ticks.length) {
    ctx.fillStyle = "#93A1B5";
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

  ctx.strokeStyle = "rgba(255,255,255,0.05)";
  ctx.lineWidth = 1;
  ctx.font = "11px monospace";
  ctx.fillStyle = "#6B7A90";
  for (let i = 0; i <= 4; i++) {
    const gy = padT + (ch * i) / 4;
    const gp = hi - ((hi - lo) * i) / 4;
    ctx.beginPath(); ctx.moveTo(padL, gy); ctx.lineTo(w - padR, gy); ctx.stroke();
    ctx.fillText(gp.toFixed(3), w - padR + 8, gy + 4);
  }

  // Soft Area Fill + Line
  ctx.beginPath();
  ticks.forEach((t, i) => {
    const x = xOf(i), y = yOf(t.price);
    if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
  });
  ctx.strokeStyle = "#3B82F6";
  ctx.lineWidth = 2.2;
  ctx.stroke();

  ctx.lineTo(xOf(ticks.length - 1), h - padB);
  ctx.lineTo(xOf(0), h - padB);
  ctx.closePath();
  ctx.fillStyle = "rgba(59, 130, 246, 0.09)";
  ctx.fill();

  [
    { px: pos.target_price, label: "יעד רווח", col: "#10B981" },
    { px: pos.avg_price, label: "כניסה", col: "#93C5FD" },
    { px: pos.stop_price, label: "הגנה", col: "#EF4444" },
  ].forEach((lv) => {
    const v = Number(lv.px);
    if (!Number.isFinite(v) || v <= 0) return;
    const y = yOf(v);
    ctx.strokeStyle = lv.col;
    ctx.lineWidth = 1.1;
    if (typeof ctx.setLineDash === "function") ctx.setLineDash([5, 4]);
    ctx.beginPath(); ctx.moveTo(padL, y); ctx.lineTo(w - padR, y); ctx.stroke();
    if (typeof ctx.setLineDash === "function") ctx.setLineDash([]);
    ctx.fillStyle = lv.col;
    ctx.fillText(lv.label, padL + 6, y - 4);
  });
}

function drawHomeChart() {
  const c = $("home-chart");
  if (!c) return;
  const cached = CHART_CACHE.home;
  let kind = "perps", d = null;
  if (cached) {
    kind = cached.kind;
    d = cached.data;
  } else if (DATA.perps && DATA.perps.default_chart && (DATA.perps.default_chart.candles || []).length) {
    kind = "perps";
    d = DATA.perps.default_chart;
  } else if (DATA.charts && DATA.charts.default) {
    kind = "poly";
    d = DATA.charts.default;
  }
  if (!d) return;
  if (kind === "perps") drawCandles(c, d); else drawSmoothLine(c, d);

  const stats = $("home-chart-stats");
  if (!stats) return;
  if (kind === "perps") {
    const cs = d.candles || [];
    const last = cs[cs.length - 1] || {};
    const ov = d.overlays || {};
    stats.innerHTML = `
      <div class="chart-stat-item">נכס: <b>${esc(d.symbol)}</b></div>
      <div class="chart-stat-item">מחיר אחרון: <b class="num">${fmt(last.close, 4)}</b></div>
      ${ov.entry ? `<div class="chart-stat-item">כניסה: <b class="num">${fmt(ov.entry, 4)}</b></div>` : ""}
      ${ov.stop ? `<div class="chart-stat-item">הגנת הפסד: <b class="num warn">${fmt(ov.stop, 4)}</b></div>` : ""}
      ${ov.target ? `<div class="chart-stat-item">יעד רווח: <b class="num pos">${fmt(ov.target, 4)}</b></div>` : ""}
      ${ov.liq ? `<div class="chart-stat-item">נקודת ניזול: <b class="num neg">${fmt(ov.liq, 4)}</b></div>` : ""}
    `;
  } else {
    const ts = d.ticks || [];
    const last = ts[ts.length - 1] || {};
    const pos = d.position || {};
    stats.innerHTML = `
      <div class="chart-stat-item">שוק: <b>${esc((pos.question || d.question || d.token_id || "").slice(0, 52))}</b></div>
      <div class="chart-stat-item">מחיר כעת: <b class="num">${fmt(last.price, 3)}</b></div>
      ${pos.avg_price ? `<div class="chart-stat-item">כניסה: <b class="num">${fmt(pos.avg_price, 3)}</b></div>` : ""}
      ${pos.stop_price ? `<div class="chart-stat-item">הגנה: <b class="num warn">${fmt(pos.stop_price, 3)}</b></div>` : ""}
      ${pos.target_price ? `<div class="chart-stat-item">יעד: <b class="num pos">${fmt(pos.target_price, 3)}</b></div>` : ""}
    `;
  }
}

function drawPerpChart() {
  const c = $("perps-chart");
  const d = CHART_CACHE.perps || (DATA.perps && DATA.perps.default_chart);
  if (c && d) drawCandles(c, d);
}
function drawPolyChart() {
  const c = $("mkt-chart");
  const d = CHART_CACHE.poly || (DATA.charts && DATA.charts.default);
  if (c && d) drawSmoothLine(c, d);
}

function redrawActiveCharts() {
  if (ACTIVE_TAB === "home") drawHomeChart();
  if (ACTIVE_TAB === "markets" && ACTIVE_SUB === "perps") drawPerpChart();
  if (ACTIVE_TAB === "markets" && ACTIVE_SUB === "poly") drawPolyChart();
}

function renderPositionsPanel() {
  const box = $("home-positions-list");
  if (!box) return;
  const pRows = DATA.perps && DATA.perps.positions || [];
  const mRows = DATA.positions || [];
  const cards = [];

  pRows.forEach((p) => {
    const isSel = SELECTED_ASSET && SELECTED_ASSET.arm === "perps" && SELECTED_ASSET.id === p.symbol;
    const key = esc(p.symbol);
    cards.push(`
      <div class="pos-item ${isSel ? 'selected' : ''}" onclick="selectHomeAsset('perps','${key}')">
        <div class="pos-top">
          <div>
            <div class="pos-name">${esc(p.symbol)} <span class="badge blue">${esc(p.side)} ×${fmt(p.leverage, 1)}</span></div>
            <div class="muted" style="font-size:12px">זירת ${esc((p.exchange || "").toUpperCase())} · מרג׳ין <span class="num">$${fmt(p.margin_used, 2)}</span></div>
          </div>
          <div class="pos-pnl ${pnlCls(p.unrealized_pnl)}">
            ${fmtSigned(p.unrealized_pnl)}$
            <div style="font-size:11.5px;font-weight:500">${fmtSigned(p.roe_pct, 1)}%</div>
          </div>
        </div>
        <div class="pos-meta">
          <span>כניסה <b class="num">${fmt(p.entry_price, p.entry_price >= 10 ? 2 : 4)}</b> → כעת <b class="num">${fmt(p.mark_price, p.mark_price >= 10 ? 2 : 4)}</b></span>
          <span>הגנה <span class="num warn">${fmt(p.stop_price, 4)}</span> · יעד <span class="num pos">${fmt(p.target_price, 4)}</span></span>
          <button class="btn sm soft-red" onclick="event.stopPropagation(); closePosition('perps','${key}','${key} ${esc(p.side)}')">סגור עסקה</button>
        </div>
      </div>
    `);
  });

  mRows.forEach((p) => {
    const key = esc(p.full_token_id || p.token_id);
    const isSel = SELECTED_ASSET && SELECTED_ASSET.arm === "poly" && SELECTED_ASSET.id === (p.full_token_id || p.token_id);
    const label = esc((p.question || p.token_id).slice(0, 34));
    cards.push(`
      <div class="pos-item ${isSel ? 'selected' : ''}" onclick="selectHomeAsset('poly','${key}')">
        <div class="pos-top">
          <div>
            <div class="pos-name">${esc((p.question || p.token_id).slice(0, 56))}</div>
            <div class="muted" style="font-size:12px"><span class="badge">Polymarket</span> · ${fmt(p.size, 1)} מניות · גיל ${fmt(p.age_hours, 1)} ש׳</div>
          </div>
          <div class="pos-pnl ${pnlCls(p.unrealized_pnl)}">
            ${fmtSigned(p.unrealized_pnl)}$
            <div style="font-size:11.5px;font-weight:500">${fmtSigned(p.unrealized_pct, 1)}%</div>
          </div>
        </div>
        <div class="pos-meta">
          <span>כניסה <b class="num">${fmt(p.avg_price, 3)}</b> → כעת <b class="num">${p.mark_price != null ? fmt(p.mark_price, 3) : "—"}</b></span>
          <span>הגנה <span class="num warn">${p.stop_price != null ? fmt(p.stop_price, 2) : "—"}</span> · יעד <span class="num pos">${p.target_price != null ? fmt(p.target_price, 2) : "—"}</span></span>
          <button class="btn sm soft-red" onclick="event.stopPropagation(); closePosition('polymarket','${key}','${label}')">סגור עסקה</button>
        </div>
      </div>
    `);
  });

  box.innerHTML = cards.length ? cards.join("") : `<div class="muted" style="padding:20px;text-align:center">אין עסקאות פתוחות כרגע — הבוט ממתין להזדמנות איכותית.</div>`;
}

function renderHomeBottomTables() {
  const closedBody = $("home-closed-body");
  if (closedBody) {
    const rows = [];
    ((DATA.perps && DATA.perps.recent_trades) || []).slice(0, 8).forEach((t) => {
      rows.push({ ts: t.ts, name: `${t.symbol} (PERPS ${t.side})`, pnl: t.realized, reason: t.reason });
    });
    (DATA.fills || []).filter((f) => f.side === "SELL").slice(0, 10).forEach((f) => {
      rows.push({ ts: f.ts, name: f.question, pnl: f.realized, reason: f.reason });
    });
    rows.sort((a, b) => b.ts - a.ts);
    closedBody.innerHTML = rows.slice(0, 10).map((r) => `
      <tr>
        <td class="num muted">${fmtDateTime(r.ts)}</td>
        <td>${esc((r.name || "").slice(0, 46))}</td>
        <td class="num ${pnlCls(r.pnl)}"><b>${fmtSigned(r.pnl)}$</b></td>
        <td class="muted">${esc((r.reason || "").slice(0, 38))}</td>
      </tr>
    `).join("") || `<tr><td colspan="4" class="muted">אין עדיין עסקאות שנסגרו</td></tr>`;
  }

  const oppsBody = $("home-opps-body");
  if (oppsBody) {
    const items = [];
    ((DATA.perps && DATA.perps.intel) || []).slice(0, 6).forEach((r) => {
      items.push({ arm: "PERPS", name: r.symbol, price: fmt(r.price, r.price >= 10 ? 2 : 4), score: fmt(r.score, 2), status: r.status, note: r.reason });
    });
    (DATA.market_intel || []).slice(0, 6).forEach((m) => {
      items.push({ arm: "Polymarket", name: (m.question || m.token_id).slice(0, 44), price: fmt(m.price, 3), score: fmt(m.score, 2), status: m.status, note: m.reason });
    });
    oppsBody.innerHTML = items.map((x) => `
      <tr>
        <td><span class="badge ${x.arm === 'PERPS' ? 'blue' : ''}">${x.arm}</span></td>
        <td><b>${esc(x.name)}</b></td>
        <td class="num">${x.price}</td>
        <td class="num">${x.score}</td>
        <td class="muted">${esc((x.note || x.status || "").slice(0, 42))}</td>
      </tr>
    `).join("") || `<tr><td colspan="5" class="muted">טוען הזדמנויות שוק...</td></tr>`;
  }
}

function renderMarketsTab() {
  const perps = DATA.perps || {};
  const sBody = $("perps-scan-body");
  if (sBody) {
    sBody.innerHTML = (perps.intel || []).map((r) => `
      <tr class="clickable" onclick="selectPerpAsset('${esc(r.symbol)}')">
        <td><b>${esc(r.symbol)}</b></td>
        <td class="muted">${esc((r.exchange || "").toUpperCase())}</td>
        <td class="num">${fmt(r.price, r.price >= 10 ? 2 : 4)}</td>
        <td><span class="badge">${esc(r.regime || "—")}</span></td>
        <td class="num">${fmt(r.score, 2)} (${esc(r.setup_tier || "B")})</td>
        <td><span class="badge ${r.status === 'OPEN' || r.status === 'ENTRY' ? 'green' : ''}">${esc(r.status || "סריקה")}</span></td>
        <td class="muted">${esc((r.reason || "").slice(0, 44))}</td>
      </tr>
    `).join("") || `<tr><td colspan="7" class="muted">אין עדיין נתוני PERPS</td></tr>`;
  }

  const mBody = $("poly-scan-body");
  if (mBody) {
    const q = ($("poly-filter") && $("poly-filter").value || "").trim().toLowerCase();
    const list = (DATA.market_intel || []).filter((m) => !q || String(m.question || "").toLowerCase().includes(q));
    mBody.innerHTML = list.slice(0, 35).map((m) => `
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

  // News + Walk-Forward
  const wf = (DATA.analytics && DATA.analytics.walkforward) || {};
  const pwf = (DATA.analytics && DATA.analytics.perp_walkforward) || {};
  const wfEl = $("wf-summary-cards");
  if (wfEl) {
    wfEl.innerHTML = `
      <div class="rule-box">
        <div class="rule-k">Polymarket — אימות מחוץ למדגם (Walk-Forward)</div>
        <div class="rule-v ${pnlCls(wf.oos_pnl)}">${wf.oos_pnl != null ? fmtSigned(wf.oos_pnl) + " USDC" : "—"}</div>
        <div class="muted" style="font-size:12px">עקביות: <b>${wf.consistency != null ? fmt(wf.consistency * 100, 0) + "%" : "—"}</b> · הצלחה: <b>${wf.oos_win_rate != null ? fmt(wf.oos_win_rate, 1) + "%" : "—"}</b></div>
      </div>
      <div class="rule-box">
        <div class="rule-k">PERPS ×50 — אימות מחוץ למדגם (Walk-Forward)</div>
        <div class="rule-v ${pnlCls(pwf.oos_return_pct)}">${pwf.oos_return_pct != null ? fmtSigned(pwf.oos_return_pct) + "%" : "—"}</div>
        <div class="muted" style="font-size:12px">עקביות: <b>${pwf.consistency != null ? fmt(pwf.consistency * 100, 0) + "%" : "—"}</b> · ליקווידציות: <b class="pos">${pwf.total_liqs ?? 0}</b></div>
      </div>
    `;
  }

  const nBody = $("news-body");
  if (nBody) {
    nBody.innerHTML = (DATA.news || []).slice(0, 25).map((n) => `
      <tr>
        <td class="num muted">${fmtDateTime(n.ts)}</td>
        <td class="muted">${esc(n.source || "")}</td>
        <td><span class="badge ${n.sentiment > 0.1 ? 'green' : (n.sentiment < -0.1 ? 'red' : '')}">${n.sentiment > 0.1 ? "חיובי" : (n.sentiment < -0.1 ? "שלילי" : "ניטרלי")}</span></td>
        <td>${esc(n.title)}</td>
      </tr>
    `).join("") || `<tr><td colspan="4" class="muted">אין חדשות במאגר</td></tr>`;
  }
  renderPerpsThesis();
}

function renderPerpsThesis() {
  const box = $("perps-thesis-box");
  if (!box) return;
  const perps = DATA.perps || {};
  const sym = PERP_SYM || "BTC";
  const pos = (perps.positions || []).find((p) => p.symbol === sym);
  const intel = (perps.intel || []).find((r) => r.symbol === sym);
  if (pos) {
    box.innerHTML = `<b>${esc(pos.symbol)} (${esc(pos.side)} ×${fmt(pos.leverage, 1)})</b> — כניסה <span class="num">${fmt(pos.entry_price, 4)}</span> · כעת <span class="num">${fmt(pos.mark_price, 4)}</span> · מרחק מניזול <span class="num">${fmt(pos.liq_distance_pct, 1)}%</span>.`;
  } else if (intel) {
    box.innerHTML = `<b>${esc(intel.symbol)}</b> (${esc((intel.exchange || "").toUpperCase())}) — משטר <b>${esc(intel.regime)}</b> · ${esc(intel.reason || "במעקב")}`;
  } else {
    box.textContent = "בחר מטבע מהרשימה לצפייה בגרף ובנתוני הסיכון שלו.";
  }
}

async function runPerpsSim() {
  const out = $("perps-sim-res");
  const lev = Number(($("sim-lev") && $("sim-lev").value) || 50);
  const sl = Number(($("sim-sl") && $("sim-sl").value) || 1.5);
  const tp = Number(($("sim-tp") && $("sim-tp").value) || 2.6);
  try {
    if (out) out.textContent = "מריץ בדיקה על הנתונים ההיסטוריים...";
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

function renderSettingsTab() {
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
      ["מינוף מקסימלי ב־PERPS", `עד ×${(DATA.perps && DATA.perps.max_leverage) || 50} (מבודד עם הגנת ניזול)`],
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
  ((DATA.perps && DATA.perps.intel) || []).forEach((r) => {
    items.push({ kind: "PERPS", title: `${r.symbol} (${r.exchange})`, sub: `${fmt(r.price, 3)}`, fn: () => { closeSpot(); switchTab("markets"); switchSubView("perps"); selectPerpAsset(r.symbol); } });
  });
  (DATA.positions || []).forEach((p) => {
    const tid = p.full_token_id || p.token_id;
    items.push({ kind: "פתוח", title: p.question || tid, sub: `כניסה ${fmt(p.avg_price, 3)}`, fn: () => { closeSpot(); switchTab("home"); selectHomeAsset("poly", tid); } });
  });
  (DATA.market_intel || []).slice(0, 18).forEach((m) => {
    items.push({ kind: "שוק", title: m.question || m.token_id, sub: `${fmt(m.price, 3)}`, fn: () => { closeSpot(); switchTab("markets"); switchSubView("poly"); selectPolyAsset(m.token_id); } });
  });
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
  renderAll();
  if (SELECTED_ASSET) selectHomeAsset(SELECTED_ASSET.arm, SELECTED_ASSET.id, false);
  if (PERP_SYM) selectPerpAsset(PERP_SYM, false);
  if (POLY_TID) selectPolyAsset(POLY_TID, false);

  document.addEventListener("keydown", (ev) => {
    if ((ev.metaKey || ev.ctrlKey) && ev.key.toLowerCase() === "k") { ev.preventDefault(); openSpot(); }
    else if (ev.key === "Escape") closeSpot();
  });
  window.addEventListener("resize", () => redrawActiveCharts());
  if (refreshSec > 0) POLL_TIMER = setInterval(() => refreshState(), Math.max(5, refreshSec) * 1000);
}
"""


def command_center_html(data: dict, *, refresh_sec: int = 30, interactive: bool = True) -> str:
    """מייצר ממשק אינטראקטיבי עצמאי, פשוט ומסודר של PMMB Command Center."""
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    refresh_val = int(refresh_sec) if (interactive and refresh_sec > 0) else 0

    return (
        '<!doctype html><html lang="he" dir="rtl"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>PMMB Command Center</title>'
        f"<style>{_UI_CSS}</style></head><body>"
        # Header
        '<header class="header"><div class="header-inner">'
        '<div class="brand">'
        '<div class="logo-mark">PM</div>'
        '<div><div class="brand-title">PMMB Command Center</div>'
        '<div class="brand-sub"><span id="hdr-dot" class="status-dot"></span><span id="hdr-status-text">טוען מצב מערכת...</span></div></div>'
        '</div>'
        '<nav class="nav-pills">'
        '<button class="nav-tab active" data-tab="home" onclick="switchTab(\'home\')">התיק והמסחר שלי</button>'
        '<button class="nav-tab" data-tab="markets" onclick="switchTab(\'markets\')">שווקים, PERPS וחדשות</button>'
        '<button class="nav-tab" data-tab="settings" onclick="switchTab(\'settings\')">מוכנות, סיכונים והגדרות</button>'
        '</nav>'
        '<div class="header-actions">'
        '<button class="btn sm" onclick="openSpot()">חיפוש (⌘K)</button>'
        '<button class="btn sm" onclick="runAction(\'/api/news-refresh\')">רענן שוק</button>'
        '<button id="btn-loop" class="btn sm primary" data-running="0" onclick="toggleLoop()">הפעל בוט</button>'
        '<button class="btn sm soft-red" onclick="runAction(\'/api/halt\',{reason:\'עצירת חירום ידנית\'},\'להפעיל עצירת חירום ולחסום פתיחת עסקאות חדשות?\')">עצירת חירום</button>'
        '</div>'
        '</div></header>'
        # Main Container
        '<main class="container">'
        '<div id="halt-banner" class="alert-banner" style="display:none">'
        '<div><b>הבוט במצב עצירת חירום:</b> <span id="halt-reason"></span></div>'
        '<button class="btn sm" onclick="runAction(\'/api/resume\',{})">בטל עצירה וחזור לפעילות</button>'
        '</div>'
        # TAB 1: Home / Portfolio & Live Positions
        '<section id="tab-home" class="tab-pane active">'
        '<div id="combined-hero" class="hero-grid"></div>'
        '<div class="main-split">'
        '<div class="card">'
        '<div class="card-head">'
        '<div><div class="card-title">גרף מחיר חי ורמות יעד והגנה</div><div class="card-sub">בחר עסקה או שוק לצפייה בגרף</div></div>'
        '<div style="display:flex;gap:8px;align-items:center">'
        '<select id="home-asset-sel" class="sel" onchange="const v=this.value.split(\':\');selectHomeAsset(v[0],v.slice(1).join(\':\'),false)"></select>'
        '<button class="btn sm" onclick="if(SELECTED_ASSET)selectHomeAsset(SELECTED_ASSET.arm,SELECTED_ASSET.id,true)">עדכן חי</button>'
        '</div></div>'
        '<div class="card-pad">'
        '<div class="chart-wrap"><canvas id="home-chart"></canvas></div>'
        '<div id="home-chart-stats" class="chart-stats"></div>'
        '</div></div>'
        '<div class="card">'
        '<div class="card-head"><div><div class="card-title">הפוזיציות הפתוחות שלי</div><div class="card-sub">לחץ על פוזיציה להצגת הגרף, או סגור ידנית</div></div></div>'
        '<div id="home-positions-list" class="pos-list"></div>'
        '</div>'
        '</div>'
        '<div class="grid-2">'
        '<div class="card">'
        '<div class="card-head"><div class="card-title">עסקאות שנסגרו לאחרונה</div><a class="btn sm" href="/api/export/trades.csv">הורד CSV</a></div>'
        '<div class="tbl-scroll"><table class="clean-tbl"><thead><tr><th>זמן</th><th>נכס / שוק</th><th>תוצאה</th><th>סיבת סגירה</th></tr></thead><tbody id="home-closed-body"></tbody></table></div>'
        '</div>'
        '<div class="card">'
        '<div class="card-head"><div class="card-title">הזדמנויות שהבוט בוחן כרגע</div><div class="card-sub">PERPS ×50 ו־Polymarket</div></div>'
        '<div class="tbl-scroll"><table class="clean-tbl"><thead><tr><th>מנוע</th><th>נכס / שוק</th><th>מחיר</th><th>ציון</th><th>מצב נוכחי</th></tr></thead><tbody id="home-opps-body"></tbody></table></div>'
        '</div>'
        '</div>'
        '</section>'
        # TAB 2: Markets, PERPS x50 & News
        '<section id="tab-markets" class="tab-pane">'
        '<div class="sub-nav">'
        '<button class="sub-btn active" data-sub="perps" onclick="switchSubView(\'perps\')">חוזי PERPS ×50</button>'
        '<button class="sub-btn" data-sub="poly" onclick="switchSubView(\'poly\')">שווקי Polymarket</button>'
        '<button class="sub-btn" data-sub="research" onclick="switchSubView(\'research\')">חדשות ואימות אסטרטגיה (Walk-Forward)</button>'
        '</div>'
        # Sub 2A: PERPS x50
        '<div id="sub-perps" class="sub-view active">'
        '<div class="main-split">'
        '<div class="card"><div class="card-head"><div><div class="card-title">גרף נרות PERPS ×50</div><div class="card-sub">1H בזמן אמת מ־OKX / Hyperliquid</div></div>'
        '<div style="display:flex;gap:8px"><select id="perp-asset-sel" class="sel" onchange="selectPerpAsset(this.value,false)"></select>'
        '<button class="btn sm primary" onclick="runAction(\'/api/perps/cycle\')">סרוק PERPS עכשיו</button></div></div>'
        '<div class="card-pad"><div class="chart-wrap"><canvas id="perps-chart"></canvas></div></div></div>'
        '<div class="card"><div class="card-head"><div class="card-title">ניתוח נכס ובדיקת תרחישים</div></div>'
        '<div class="card-pad" style="display:flex;flex-direction:column;gap:14px">'
        '<div id="perps-thesis-box" class="rule-box" style="font-size:13px"></div>'
        '<div style="display:flex;gap:10px;flex-wrap:wrap;align-items:flex-end">'
        '<label style="font-size:12px;color:var(--muted)">מינוף מקסימלי<br><input id="sim-lev" class="inp num" style="width:76px;margin-top:4px" type="number" min="2" max="50" value="50"></label>'
        '<label style="font-size:12px;color:var(--muted)">הגנה (×ATR)<br><input id="sim-sl" class="inp num" style="width:76px;margin-top:4px" type="number" step="0.1" min="0.8" max="4" value="1.5"></label>'
        '<label style="font-size:12px;color:var(--muted)">יעד (×ATR)<br><input id="sim-tp" class="inp num" style="width:76px;margin-top:4px" type="number" step="0.1" min="1.2" max="6" value="2.6"></label>'
        '<button class="btn sm primary" onclick="runPerpsSim()">בדוק תרחיש</button>'
        '</div>'
        '<div id="perps-sim-res" class="rule-box muted" style="font-size:13px">הרץ בדיקת סימולציה על הנתונים ההיסטוריים.</div>'
        '</div></div>'
        '</div>'
        '<div class="card"><div class="card-head"><div class="card-title">16 המטבעות הנסרקים ב־PERPS ×50</div></div>'
        '<div class="tbl-scroll"><table class="clean-tbl"><thead><tr><th>מטבע</th><th>בורסה</th><th>מחיר</th><th>מגמה</th><th>ציון איכות</th><th>מצב</th><th>הסבר</th></tr></thead><tbody id="perps-scan-body"></tbody></table></div></div>'
        '</div>'
        # Sub 2B: Polymarket
        '<div id="sub-poly" class="sub-view">'
        '<div class="card" style="margin-bottom:16px"><div class="card-head"><div><div class="card-title">גרף מחיר Polymarket</div></div>'
        '<div style="display:flex;gap:8px"><select id="poly-asset-sel" class="sel" onchange="selectPolyAsset(this.value,false)"></select>'
        '<button class="btn sm primary" onclick="runAction(\'/api/paper-cycle\')">סרוק Polymarket עכשיו</button></div></div>'
        '<div class="card-pad"><div class="chart-wrap"><canvas id="mkt-chart"></canvas></div></div></div>'
        '<div class="card"><div class="card-head"><div class="card-title">שווקים נסרקים</div><input id="poly-filter" class="inp" placeholder="חפש שוק..." oninput="renderMarketsTab()"></div>'
        '<div class="tbl-scroll"><table class="clean-tbl"><thead><tr><th>שוק</th><th>תחום</th><th>מחיר</th><th>סטייה (Z)</th><th>ציון</th><th>מצב</th></tr></thead><tbody id="poly-scan-body"></tbody></table></div></div>'
        '</div>'
        # Sub 2C: Research & News
        '<div id="sub-research" class="sub-view">'
        '<div class="card" style="margin-bottom:16px"><div class="card-head"><div class="card-title">אימות ביצועים מחוץ למדגם (Walk-Forward)</div><button class="btn sm primary" onclick="runAction(\'/api/learn\',{apply:true})">הרץ בדיקת למידה</button></div>'
        '<div id="wf-summary-cards" class="rule-grid"></div></div>'
        '<div class="card"><div class="card-head"><div class="card-title">חדשות שוק אחרונות המשפיעות על הבוט</div></div>'
        '<div class="tbl-scroll"><table class="clean-tbl"><thead><tr><th>זמן</th><th>מקור</th><th>השפעה</th><th>כותרת</th></tr></thead><tbody id="news-body"></tbody></table></div></div>'
        '</div>'
        '</section>'
        # TAB 3: Readiness, Risk Rules & Settings
        '<section id="tab-settings" class="tab-pane">'
        '<div class="grid-2">'
        '<div class="card"><div class="card-head"><div class="card-title">מוכנות למעבר לכסף אמיתי</div><span id="readiness-summary" class="badge">—</span></div>'
        '<div class="tbl-scroll"><table class="clean-tbl"><thead><tr><th>מצב</th><th>בדיקה</th><th>פירוט</th></tr></thead><tbody id="readiness-body"></tbody></table></div></div>'
        '<div class="card"><div class="card-head"><div class="card-title">כללי ההגנה של התיק שלך</div></div>'
        '<div id="risk-rules-grid" class="rule-grid"></div></div>'
        '</div>'
        '<div class="card" style="margin-bottom:16px"><div class="card-head"><div class="card-title">כלי מערכת, גיבוי וייצוא</div>'
        '<div style="display:flex;gap:8px;flex-wrap:wrap">'
        '<button class="btn sm primary" onclick="runAction(\'/api/reconcile\')">אמת חשבונות (Reconcile)</button>'
        '<button class="btn sm" onclick="runAction(\'/api/backup\')">שמור גיבוי עכשיו</button>'
        '<a class="btn sm" href="/api/export/trades.csv">הורד היסטוריית עסקאות (CSV)</a>'
        '<button class="btn sm" onclick="runAction(\'/api/perps/learn\',{apply:true})">כייל PERPS</button>'
        '</div></div></div>'
        '<div class="grid-2">'
        '<div class="card"><div class="card-head"><div class="card-title">יומן טייס אוטומטי</div></div>'
        '<div class="tbl-scroll"><table class="clean-tbl"><thead><tr><th>זמן</th><th>סוג</th><th>פירוט</th></tr></thead><tbody id="autopilot-body"></tbody></table></div></div>'
        '<div class="card"><div class="card-head"><div class="card-title">גיבויים שמורים</div></div>'
        '<div class="tbl-scroll"><table class="clean-tbl"><thead><tr><th>קובץ</th><th>גודל</th><th>תאריך</th></tr></thead><tbody id="backups-body"></tbody></table></div></div>'
        '</div>'
        '</section>'
        '</main>'
        # Search Overlay (#spot-overlay)
        '<div id="spot-overlay" class="spot-overlay" onclick="if(event.target===this)closeSpot()">'
        '<div class="spot-box">'
        '<div class="spot-head"><input id="spot-inp" class="spot-inp" placeholder="חפש מטבע, שוק או עסקה פתוחה..." oninput="renderSpotList(this.value)"><button class="btn sm" onclick="closeSpot()">סגור</button></div>'
        '<div id="spot-list" class="spot-list"></div>'
        '</div></div>'
        '<div id="toast" class="toast"></div>'
        f"<script>window.__PMMB_INIT__ = {payload};\n{_UI_JS}\ninitApp({refresh_val});</script>"
        '</body></html>'
    )
