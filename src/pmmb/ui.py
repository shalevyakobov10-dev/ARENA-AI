"""
ממשק הטרמינל המוסדי של PMMB — עיצוב שולחן מסחר כהה, חד ותכליתי.

אפס משאבים חיצוניים (עצמאי לחלוטין), RTL מלא, קווי הפרדה דקים,
טיפוגרפיה מונו-נומרית (tabular-nums) ופקדי מסחר וסגירה חיים.
"""
from __future__ import annotations

import json

_TERMINAL_CSS = """
:root {
  --bg: #0B0E11;
  --panel: #11161D;
  --panel-alt: #161C24;
  --hover: #1C2430;
  --line: #202731;
  --line-strong: #2E3746;
  --text: #EAECEF;
  --muted: #848E9C;
  --dim: #5E6673;
  --green: #00C087;
  --green-bg: rgba(0, 192, 135, 0.11);
  --green-bd: rgba(0, 192, 135, 0.32);
  --red: #F6465D;
  --red-bg: rgba(246, 70, 93, 0.11);
  --red-bd: rgba(246, 70, 93, 0.32);
  --amber: #F0B90B;
  --amber-bg: rgba(240, 185, 11, 0.11);
  --amber-bd: rgba(240, 185, 11, 0.32);
  --blue: #5E9BFF;
  --blue-bg: rgba(94, 155, 255, 0.10);
  --blue-bd: rgba(94, 155, 255, 0.32);
  --mono: 'JetBrains Mono', ui-monospace, 'SFMono-Regular', Menlo, Consolas, monospace;
  --sans: system-ui, -apple-system, 'Segoe UI', Arial, sans-serif;
}
*, *::before, *::after { box-sizing: border-box; }
html, body {
  margin: 0;
  padding: 0;
  background: var(--bg);
  color: var(--text);
  font-family: var(--sans);
  font-size: 13px;
  line-height: 1.45;
  -webkit-font-smoothing: antialiased;
}
.mono {
  font-family: var(--mono);
  font-variant-numeric: tabular-nums;
  direction: ltr;
  unicode-bidi: isolate;
}
.num {
  font-family: var(--mono);
  font-variant-numeric: tabular-nums;
  direction: ltr;
  display: inline-block;
}
.pos { color: var(--green); }
.neg { color: var(--red); }
.warn { color: var(--amber); }
.info { color: var(--blue); }
.muted { color: var(--muted); }
.dim { color: var(--dim); }

/* Header & Navigation */
.topbar {
  position: sticky;
  top: 0;
  z-index: 40;
  background: var(--panel);
  border-bottom: 1px solid var(--line);
}
.topbar-inner {
  max-width: 1580px;
  margin: 0 auto;
  padding: 8px 14px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}
.brand-grp {
  display: flex;
  align-items: center;
  gap: 10px;
}
.brand-mark {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 700;
  font-size: 13px;
  letter-spacing: 0.04em;
  color: var(--text);
}
.dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--green);
  flex-shrink: 0;
}
.dot.halt { background: var(--red); }
.dot.warn { background: var(--amber); }

.tag {
  display: inline-flex;
  align-items: center;
  padding: 2px 6px;
  border-radius: 2px;
  font-size: 11px;
  font-weight: 600;
  font-family: var(--mono);
  border: 1px solid var(--line-strong);
  background: var(--panel-alt);
  color: var(--muted);
  white-space: nowrap;
}
.tag.green { color: var(--green); background: var(--green-bg); border-color: var(--green-bd); }
.tag.red { color: var(--red); background: var(--red-bg); border-color: var(--red-bd); }
.tag.amber { color: var(--amber); background: var(--amber-bg); border-color: var(--amber-bd); }
.tag.blue { color: var(--blue); background: var(--blue-bg); border-color: var(--blue-bd); }

.ticker-strip {
  display: flex;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
}
.ticker-item {
  display: flex;
  align-items: baseline;
  gap: 6px;
  font-size: 12px;
}
.ticker-item .lbl { color: var(--muted); font-size: 11px; }
.ticker-item .val { font-family: var(--mono); font-weight: 600; font-size: 12.5px; }

.ctrl-grp {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}
.btn {
  appearance: none;
  border: 1px solid var(--line-strong);
  background: var(--panel-alt);
  color: var(--text);
  border-radius: 3px;
  padding: 5px 10px;
  font-size: 12px;
  font-weight: 600;
  font-family: inherit;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  transition: background 0.12s, border-color 0.12s;
  white-space: nowrap;
}
.btn:hover { background: var(--hover); border-color: #3E4A5C; }
.btn:disabled { opacity: 0.45; cursor: not-allowed; }
.btn.sm { padding: 3px 8px; font-size: 11px; }
.btn.primary {
  background: var(--blue-bg);
  border-color: var(--blue-bd);
  color: var(--blue);
}
.btn.primary:hover { background: rgba(94, 155, 255, 0.18); }
.btn.buy {
  background: var(--green-bg);
  border-color: var(--green-bd);
  color: var(--green);
}
.btn.danger {
  background: var(--red-bg);
  border-color: var(--red-bd);
  color: var(--red);
}
.btn.danger:hover { background: rgba(246, 70, 93, 0.20); }

.nav-bar {
  background: var(--bg);
  border-bottom: 1px solid var(--line);
}
.nav-tabs {
  max-width: 1580px;
  margin: 0 auto;
  padding: 0 14px;
  display: flex;
  align-items: center;
  gap: 2px;
  overflow-x: auto;
}
.nav-tab {
  appearance: none;
  background: transparent;
  border: none;
  border-bottom: 2px solid transparent;
  color: var(--muted);
  padding: 9px 14px;
  font-size: 12.5px;
  font-weight: 600;
  font-family: inherit;
  cursor: pointer;
  white-space: nowrap;
}
.nav-tab:hover { color: var(--text); }
.nav-tab.active {
  color: var(--text);
  border-bottom-color: var(--amber);
}

/* Main Layout */
.wrap {
  max-width: 1580px;
  margin: 0 auto;
  padding: 12px 14px 28px;
}
.banner {
  background: var(--red-bg);
  border: 1px solid var(--red-bd);
  border-radius: 3px;
  padding: 8px 12px;
  margin-bottom: 10px;
  color: #FCA5A5;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}
.tab-pane { display: none; }
.tab-pane.active { display: block; }

/* Flat Institutional KPI Strip */
.kpi-strip {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  border: 1px solid var(--line);
  background: var(--panel);
  border-radius: 3px;
  margin-bottom: 10px;
}
.kpi-cell {
  padding: 10px 12px;
  border-left: 1px solid var(--line);
}
.kpi-cell:last-child { border-left: none; }
.kpi-k { font-size: 11px; color: var(--muted); margin-bottom: 4px; }
.kpi-v { font-family: var(--mono); font-variant-numeric: tabular-nums; font-size: 18px; font-weight: 700; color: var(--text); }
.kpi-s { font-size: 11px; color: var(--dim); margin-top: 2px; font-family: var(--mono); }

/* Terminal Grids */
.desk-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.85fr) minmax(300px, 1fr);
  gap: 10px;
  margin-bottom: 10px;
}
.grid-2 {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 10px;
}
.grid-3 {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 10px;
}
.panel {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 3px;
  overflow: hidden;
  margin-bottom: 10px;
}
.panel.no-mb { margin-bottom: 0; }
.panel-hd {
  padding: 8px 12px;
  background: var(--panel-alt);
  border-bottom: 1px solid var(--line);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  flex-wrap: wrap;
}
.panel-title {
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.01em;
  color: var(--text);
}
.panel-sub { font-size: 11px; color: var(--muted); }
.panel-bd { padding: 10px 12px; }
.panel-bd.flush { padding: 0; }

/* Inputs & Selects */
.inp, .sel {
  background: var(--bg);
  color: var(--text);
  border: 1px solid var(--line-strong);
  border-radius: 3px;
  padding: 4px 8px;
  font-size: 12px;
  font-family: inherit;
  outline: none;
}
.inp:focus, .sel:focus { border-color: var(--blue); }
.inp.mono, .sel.mono { font-family: var(--mono); }

/* Charts */
.chart-box {
  position: relative;
  width: 100%;
  height: 310px;
  background: var(--bg);
  border: 1px solid var(--line);
  border-radius: 2px;
}
.chart-box.tall { height: 340px; }
.chart-box canvas { width: 100%; height: 100%; display: block; }
.chart-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  flex-wrap: wrap;
  margin-top: 6px;
  font-size: 11px;
  color: var(--muted);
}

/* Orderbook Microstructure */
.ob-wrap { font-family: var(--mono); font-size: 11.5px; }
.ob-row {
  position: relative;
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  padding: 3px 8px;
  border-bottom: 1px solid rgba(32, 39, 49, 0.45);
}
.ob-bar {
  position: absolute;
  top: 0;
  bottom: 0;
  left: 0;
  pointer-events: none;
  opacity: 0.16;
}
.ob-bar.ask { background: var(--red); }
.ob-bar.bid { background: var(--green); }
.ob-spread {
  padding: 4px 8px;
  background: var(--panel-alt);
  border-top: 1px solid var(--line);
  border-bottom: 1px solid var(--line);
  display: flex;
  justify-content: space-between;
  font-size: 11px;
  color: var(--muted);
}

.kv-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  border-top: 1px solid var(--line);
}
.kv-item {
  padding: 7px 10px;
  border-bottom: 1px solid var(--line);
  border-left: 1px solid var(--line);
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 6px;
  font-size: 11.5px;
}
.kv-item:nth-child(even) { border-left: none; }

/* Tables */
.tbl-wrap { overflow-x: auto; max-height: 440px; overflow-y: auto; }
table.tbl {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}
table.tbl th {
  position: sticky;
  top: 0;
  z-index: 2;
  background: var(--panel-alt);
  color: var(--muted);
  font-weight: 600;
  font-size: 11px;
  text-align: right;
  padding: 7px 9px;
  border-bottom: 1px solid var(--line-strong);
  white-space: nowrap;
}
table.tbl td {
  padding: 6px 9px;
  border-bottom: 1px solid var(--line);
  vertical-align: middle;
  white-space: nowrap;
}
table.tbl td.wrap-txt { white-space: normal; min-width: 180px; max-width: 340px; }
table.tbl tbody tr:hover { background: var(--hover); }
table.tbl tbody tr.clickable { cursor: pointer; }

/* Subtabs inside Blotter */
.subtabs {
  display: flex;
  align-items: center;
  gap: 4px;
}
.subtab {
  appearance: none;
  background: transparent;
  border: 1px solid transparent;
  color: var(--muted);
  padding: 4px 10px;
  border-radius: 2px;
  font-size: 11.5px;
  font-weight: 600;
  font-family: inherit;
  cursor: pointer;
}
.subtab:hover { color: var(--text); }
.subtab.active {
  background: var(--panel);
  border-color: var(--line-strong);
  color: var(--text);
}

/* Stress test & Thesis */
.thesis-box {
  padding: 9px 12px;
  background: var(--bg);
  border: 1px solid var(--line);
  border-radius: 2px;
  font-size: 12px;
  color: var(--text);
  line-height: 1.5;
}
.sim-form {
  display: flex;
  align-items: flex-end;
  gap: 8px;
  flex-wrap: wrap;
}
.sim-field {
  display: flex;
  flex-direction: column;
  gap: 3px;
  font-size: 11px;
  color: var(--muted);
}

/* Command Palette (#spot-overlay) */
.spot-overlay {
  position: fixed;
  inset: 0;
  background: rgba(5, 7, 10, 0.78);
  z-index: 100;
  display: none;
  align-items: flex-start;
  justify-content: center;
  padding-top: 84px;
}
.spot-overlay.open { display: flex; }
.spot-box {
  width: min(640px, 94vw);
  background: var(--panel);
  border: 1px solid var(--line-strong);
  border-radius: 4px;
  overflow: hidden;
}
.spot-inp-wrap {
  padding: 10px 12px;
  border-bottom: 1px solid var(--line);
  display: flex;
  align-items: center;
  gap: 8px;
}
.spot-inp {
  width: 100%;
  background: transparent;
  border: none;
  outline: none;
  color: var(--text);
  font-size: 13.5px;
  font-family: inherit;
}
.spot-list { max-height: 360px; overflow-y: auto; }
.spot-item {
  padding: 8px 12px;
  border-bottom: 1px solid var(--line);
  display: flex;
  justify-content: space-between;
  align-items: center;
  cursor: pointer;
  font-size: 12px;
}
.spot-item:hover { background: var(--hover); }

/* Toast */
.toast {
  position: fixed;
  bottom: 14px;
  left: 14px;
  z-index: 90;
  background: var(--panel-alt);
  border: 1px solid var(--line-strong);
  border-radius: 3px;
  padding: 8px 12px;
  font-size: 12px;
  color: var(--text);
  display: none;
  max-width: 440px;
}
.toast.show { display: block; }
.toast.ok { border-color: var(--green-bd); color: var(--green); }
.toast.err { border-color: var(--red-bd); color: var(--red); }

@media (max-width: 1120px) {
  .kpi-strip { grid-template-columns: repeat(3, minmax(0, 1fr)); }
  .desk-grid { grid-template-columns: 1fr; }
  .grid-2, .grid-3 { grid-template-columns: 1fr; }
}
@media (max-width: 640px) {
  .kpi-strip { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .ticker-strip { display: none; }
}
"""

_TERMINAL_JS = r"""
let DATA = window.__PMMB_INIT__ || {};
let ACTIVE_TAB = "overview";
let ACTIVE_BLOTTER = "positions";
let OV_SELECTION = null; // { arm: "perps"|"poly", id: "..." }
let PERP_SYM = null;
let POLY_TID = null;
let CHART_CACHE = { ov: null, perps: null, poly: null };
let POLL_TIMER = null;

const $ = (id) => document.getElementById(id);
function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#39;" }[c]));
}
function fmt(n, d = 2) {
  const v = Number(n);
  if (!Number.isFinite(v)) return "—";
  return v.toFixed(d);
}
function fmtSigned(n, d = 2) {
  const v = Number(n);
  if (!Number.isFinite(v)) return "—";
  return (v >= 0 ? "+" : "") + v.toFixed(d);
}
function fmtTime(ts) {
  if (!ts) return "—";
  const d = new Date(Number(ts) * 1000);
  return d.toISOString().slice(11, 19);
}
function fmtDateTime(ts) {
  if (!ts) return "—";
  const d = new Date(Number(ts) * 1000);
  return d.toISOString().slice(5, 16).replace("T", " ");
}
function clsPnl(n) {
  const v = Number(n);
  if (!Number.isFinite(v) || v === 0) return "muted";
  return v > 0 ? "pos" : "neg";
}
function showToast(msg, isErr = false) {
  const t = $("toast");
  if (!t) return;
  t.textContent = msg;
  t.className = "toast show " + (isErr ? "err" : "ok");
  clearTimeout(window.__toastT);
  window.__toastT = setTimeout(() => { t.className = "toast"; }, 4200);
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
    showToast(res.message || "בוצע בהצלחה", false);
    await refreshState();
  } catch (e) {
    showToast(e.message || String(e), true);
  }
}

async function closePosition(arm, key, label) {
  const msg = `לסגור את הפוזיציה ${label} במחיר השוק כעת?`;
  if (typeof window.confirm === "function" && !window.confirm(msg)) return;
  try {
    const res = await apiPost("/api/positions/close", { arm, key, reason: "סגירה ידנית מהטרמינל" });
    showToast(res.message || "הפוזיציה נסגרה", false);
    await refreshState();
  } catch (e) {
    showToast(e.message || String(e), true);
  }
}

function switchTab(tab) {
  ACTIVE_TAB = tab;
  document.querySelectorAll(".nav-tab").forEach((el) => {
    el.classList.toggle("active", el.getAttribute("data-tab") === tab);
  });
  document.querySelectorAll(".tab-pane").forEach((el) => {
    el.classList.toggle("active", el.id === "tab-" + tab);
  });
  redrawActiveCharts();
}

function switchBlotter(name) {
  ACTIVE_BLOTTER = name;
  document.querySelectorAll(".subtab").forEach((el) => {
    el.classList.toggle("active", el.getAttribute("data-blotter") === name);
  });
  document.querySelectorAll(".blotter-pane").forEach((el) => {
    el.style.display = el.id === "blotter-" + name ? "block" : "none";
  });
}

function renderTopBar() {
  const h = DATA.health || {};
  const hb = DATA.heartbeat || {};
  const tr = DATA.trader || {};
  const comb = DATA.combined || {};
  const poly = DATA.bankroll || {};
  const perps = DATA.perps || {};
  const halt = DATA.halt || (hb && hb.halted);

  const dot = $("hdr-dot");
  if (dot) dot.className = "dot" + (halt ? " halt" : (h.healthy ? "" : " warn"));

  const modeTag = $("hdr-mode");
  if (modeTag) {
    const m = String(DATA.mode || "paper").toUpperCase();
    modeTag.textContent = m;
    modeTag.className = "tag " + (m === "LIVE" ? "red" : "blue");
  }
  const stTag = $("hdr-status");
  if (stTag) {
    if (halt) {
      stTag.textContent = "HALTED";
      stTag.className = "tag red";
    } else if (tr.running) {
      stTag.textContent = `AUTO · #${hb.cycle || 0}`;
      stTag.className = "tag green";
    } else {
      stTag.textContent = "IDLE";
      stTag.className = "tag amber";
    }
  }
  const ageEl = $("hdr-age");
  if (ageEl) ageEl.textContent = h.age_sec != null ? `${Number(h.age_sec).toFixed(0)}s` : "—";

  const hbEl = $("halt-banner");
  if (hbEl) {
    if (halt) {
      const rsn = (DATA.halt && DATA.halt.reason) || (hb && hb.halt_reason) || "עצירת מסחר פעילה";
      $("halt-reason").textContent = rsn;
      hbEl.style.display = "flex";
    } else {
      hbEl.style.display = "none";
    }
  }

  const loopBtn = $("btn-loop");
  if (loopBtn) {
    loopBtn.textContent = tr.running ? "עצור לולאה" : "הפעל לולאה";
    loopBtn.setAttribute("data-running", tr.running ? "1" : "0");
  }

  const strip = $("hdr-ticker");
  if (strip) {
    const ret = Number(comb.return_pct || 0);
    strip.innerHTML = [
      `<div class="ticker-item"><span class="lbl">הון מאוחד</span><span class="val">${fmt(comb.equity)} USDC</span></div>`,
      `<div class="ticker-item"><span class="lbl">תשואה</span><span class="val ${clsPnl(ret)}">${fmtSigned(ret)}%</span></div>`,
      `<div class="ticker-item"><span class="lbl">Polymarket</span><span class="val">${fmt(poly.equity)}</span></div>`,
      `<div class="ticker-item"><span class="lbl">PERPS ×50</span><span class="val">${fmt(perps.equity)}</span></div>`,
      `<div class="ticker-item"><span class="lbl">פוזיציות</span><span class="val">${comb.open_positions ?? 0}</span></div>`,
    ].join("");
  }
}

function renderCombinedHero() {
  const comb = DATA.combined || {};
  const poly = DATA.bankroll || {};
  const perps = DATA.perps || {};
  const ov = DATA.overall || {};
  const hero = $("combined-hero");
  if (!hero) return;
  const unrTot = Number(poly.unrealized_pnl || 0) + Number(perps.unrealized_pnl || 0);
  const polyStart = Number((DATA.config && DATA.config.execution && DATA.config.execution.starting_cash) || 1000);
  const polyRet = polyStart > 0 ? ((Number(poly.equity || polyStart) - polyStart) / polyStart * 100) : 0;
  const perpRet = Number(perps.equity || 1000) - 1000;
  const cells = [
    { k: "הון כולל משולב", v: `$${fmt(comb.equity)}`, s: `הון התחלתי $${fmt(comb.starting_cash, 0)}`, c: "" },
    { k: "רווח / תשואה נטו", v: `${fmtSigned(comb.pnl)}`, s: `${fmtSigned(comb.return_pct)}% על התיק`, c: clsPnl(comb.pnl) },
    { k: "לא-ממומש חי", v: `${fmtSigned(unrTot)}`, s: `Poly ${fmtSigned(poly.unrealized_pnl)} | Perps ${fmtSigned(perps.unrealized_pnl)}`, c: clsPnl(unrTot) },
    { k: "זרוע Polymarket", v: `$${fmt(poly.equity)}`, s: `מזומן $${fmt(poly.cash)} | ${fmtSigned(polyRet, 1)}%`, c: clsPnl(polyRet) },
    { k: "זרוע PERPS ×50", v: `$${fmt(perps.equity)}`, s: `מרג'ין $${fmt(perps.margin_used)} | ממוצע ×${fmt(perps.avg_leverage, 1)} | ${fmtSigned(perpRet, 2)}`, c: clsPnl(perpRet) },
    { k: "ביצוע מצטבר", v: `${comb.closed_trades ?? 0} עסקאות`, s: `Poly WR ${fmt(ov.win_rate_pct, 0)}% | Perps WR ${fmt(perps.win_rate_pct, 0)}% | עמלות $${fmt(comb.fees_paid)}`, c: "" },
  ];
  hero.innerHTML = cells.map((c) => `
    <div class="kpi-cell">
      <div class="kpi-k">${esc(c.k)}</div>
      <div class="kpi-v ${c.c}">${esc(c.v)}</div>
      <div class="kpi-s">${esc(c.s)}</div>
    </div>
  `).join("");
}

function getOvAssets() {
  const perps = DATA.perps || {};
  const list = [];
  (perps.positions || []).forEach((p) => {
    list.push({ arm: "perps", id: p.symbol, label: `PERPS · ${p.symbol} ${p.side} ×${fmt(p.leverage, 0)}` });
  });
  (DATA.positions || []).forEach((p) => {
    const tid = p.full_token_id || p.token_id;
    list.push({ arm: "poly", id: tid, label: `POLY · ${(p.question || tid).slice(0, 34)}` });
  });
  (perps.intel || []).forEach((r) => {
    if (!list.some((x) => x.arm === "perps" && x.id === r.symbol)) {
      list.push({ arm: "perps", id: r.symbol, label: `PERPS · ${r.symbol} (${r.exchange})` });
    }
  });
  ((DATA.charts && DATA.charts.candidates) || []).forEach((c) => {
    if (!list.some((x) => x.arm === "poly" && x.id === c.token_id)) {
      list.push({ arm: "poly", id: c.token_id, label: `POLY · ${(c.question || c.token_id).slice(0, 34)}` });
    }
  });
  return list;
}

function syncSelectors() {
  const ovList = getOvAssets();
  if (!OV_SELECTION && ovList.length) OV_SELECTION = { arm: ovList[0].arm, id: ovList[0].id };
  const ovSel = $("ov-asset-sel");
  if (ovSel) {
    ovSel.innerHTML = ovList.map((a) => `<option value="${esc(a.arm + ':' + a.id)}">${esc(a.label)}</option>`).join("");
    if (OV_SELECTION) ovSel.value = OV_SELECTION.arm + ":" + OV_SELECTION.id;
  }

  const perps = DATA.perps || {};
  const pSyms = [];
  (perps.positions || []).forEach((p) => { if (!pSyms.includes(p.symbol)) pSyms.push(p.symbol); });
  (perps.intel || []).forEach((r) => { if (!pSyms.includes(r.symbol)) pSyms.push(r.symbol); });
  if (!pSyms.length && perps.default_chart && perps.default_chart.symbol) pSyms.push(perps.default_chart.symbol);
  if (!PERP_SYM && pSyms.length) PERP_SYM = pSyms[0];
  const pSel = $("perp-asset-sel");
  if (pSel) {
    pSel.innerHTML = pSyms.map((s) => `<option value="${esc(s)}">${esc(s)} / USDT</option>`).join("");
    if (PERP_SYM) pSel.value = PERP_SYM;
  }

  const cands = (DATA.charts && DATA.charts.candidates) || [];
  if (!POLY_TID && cands.length) POLY_TID = cands[0].token_id;
  const mSel = $("poly-asset-sel");
  if (mSel) {
    mSel.innerHTML = cands.map((c) => `<option value="${esc(c.token_id)}">${esc((c.question || c.token_id).slice(0, 48))}</option>`).join("");
    if (POLY_TID) mSel.value = POLY_TID;
  }
}

async function selectOvAsset(arm, id, forceLive = false) {
  OV_SELECTION = { arm, id };
  const ovSel = $("ov-asset-sel");
  if (ovSel) ovSel.value = arm + ":" + id;
  if (arm === "perps") {
    const dc = DATA.perps && DATA.perps.default_chart;
    if (!forceLive && dc && dc.symbol === id && (dc.candles || []).length) {
      CHART_CACHE.ov = { kind: "perps", data: dc };
    } else {
      try {
        const ch = await apiGet(`/api/perps/chart?symbol=${encodeURIComponent(id)}&live=${forceLive ? 1 : 0}`);
        CHART_CACHE.ov = { kind: "perps", data: ch };
      } catch (_) {}
    }
  } else {
    const dc = DATA.charts && DATA.charts.default;
    if (!forceLive && dc && String(dc.token_id || "").startsWith(String(id).slice(0, 12))) {
      CHART_CACHE.ov = { kind: "poly", data: dc };
    } else {
      try {
        const ch = await apiGet(`/api/chart?token=${encodeURIComponent(id)}&live=${forceLive ? 1 : 0}`);
        CHART_CACHE.ov = { kind: "poly", data: ch };
      } catch (_) {}
    }
  }
  drawOverviewChart();
  renderOrderbookAndMicro();
}

async function selectPerpAsset(sym, forceLive = false) {
  PERP_SYM = sym;
  const pSel = $("perp-asset-sel");
  if (pSel) pSel.value = sym;
  const dc = DATA.perps && DATA.perps.default_chart;
  if (!forceLive && dc && dc.symbol === sym && (dc.candles || []).length) {
    CHART_CACHE.perps = dc;
  } else {
    try {
      CHART_CACHE.perps = await apiGet(`/api/perps/chart?symbol=${encodeURIComponent(sym)}&live=${forceLive ? 1 : 0}`);
    } catch (_) {}
  }
  drawPerpChart();
  renderPerpsThesis();
}

async function selectPolyAsset(tid, forceLive = false) {
  POLY_TID = tid;
  const mSel = $("poly-asset-sel");
  if (mSel) mSel.value = tid;
  const dc = DATA.charts && DATA.charts.default;
  if (!forceLive && dc && dc.token_id === tid && (dc.ticks || []).length) {
    CHART_CACHE.poly = dc;
  } else {
    try {
      CHART_CACHE.poly = await apiGet(`/api/chart?token=${encodeURIComponent(tid)}&live=${forceLive ? 1 : 0}`);
    } catch (_) {}
  }
  drawPolyChart();
}

function setupCanvas(canvas) {
  if (!canvas || !canvas.getContext) return null;
  const rect = canvas.parentElement ? canvas.parentElement.getBoundingClientRect() : { width: 700, height: 300 };
  const w = Math.max(320, Math.floor(rect.width || 700));
  const h = Math.max(220, Math.floor(rect.height || 300));
  const dpr = window.devicePixelRatio || 1;
  canvas.width = w * dpr;
  canvas.height = h * dpr;
  const ctx = canvas.getContext("2d");
  if (!ctx) return null;
  if (typeof ctx.setTransform === "function") ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  return { ctx, w, h };
}

function drawCandlestickCanvas(canvas, payload) {
  const setup = setupCanvas(canvas);
  if (!setup) return;
  const { ctx, w, h } = setup;
  ctx.fillStyle = "#0B0E11";
  ctx.fillRect(0, 0, w, h);

  const candles = (payload && payload.candles) || [];
  if (!candles.length) {
    ctx.fillStyle = "#848E9C";
    ctx.font = "12px sans-serif";
    ctx.fillText("אין נרות טעונים עדיין לנכס זה", 20, 40);
    return;
  }
  const padL = 12, padR = 68, padT = 16, padB = 24;
  const cw = w - padL - padR;
  const ch = h - padT - padB;
  const view = candles.slice(-96);
  let lo = Infinity, hi = -Infinity;
  view.forEach((c) => {
    if (c.low < lo) lo = c.low;
    if (c.high > hi) hi = c.high;
  });
  const ov = (payload && payload.overlays) || {};
  [ov.entry, ov.stop, ov.target, ov.liq].forEach((lv) => {
    const v = Number(lv);
    if (Number.isFinite(v) && v > 0) {
      if (v < lo) lo = v;
      if (v > hi) hi = v;
    }
  });
  if (hi <= lo) { hi = lo * 1.01 + 1e-6; }
  const span = hi - lo;
  lo -= span * 0.06;
  hi += span * 0.06;
  const yOf = (p) => padT + (hi - p) / (hi - lo) * ch;

  // Grid
  ctx.strokeStyle = "#181E26";
  ctx.lineWidth = 1;
  ctx.font = "10.5px monospace";
  ctx.fillStyle = "#5E6673";
  for (let i = 0; i <= 4; i++) {
    const gy = padT + (ch * i) / 4;
    const gp = hi - ((hi - lo) * i) / 4;
    ctx.beginPath();
    ctx.moveTo(padL, gy);
    ctx.lineTo(w - padR, gy);
    ctx.stroke();
    ctx.fillText(gp >= 100 ? gp.toFixed(1) : (gp >= 1 ? gp.toFixed(3) : gp.toFixed(4)), w - padR + 6, gy + 3);
  }

  // EMA20
  const closes = view.map((c) => c.close);
  const k20 = 2 / 21;
  let ema = closes[0];
  ctx.strokeStyle = "#5E9BFF";
  ctx.lineWidth = 1.25;
  ctx.beginPath();
  const step = cw / view.length;
  view.forEach((c, i) => {
    ema = c.close * k20 + ema * (1 - k20);
    const x = padL + (i + 0.5) * step;
    const y = yOf(ema);
    if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
  });
  ctx.stroke();

  // Candles
  const bodyW = Math.max(2, Math.min(9, step * 0.65));
  view.forEach((c, i) => {
    const x = padL + (i + 0.5) * step;
    const up = c.close >= c.open;
    const col = up ? "#00C087" : "#F6465D";
    ctx.strokeStyle = col;
    ctx.fillStyle = col;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(x, yOf(c.high));
    ctx.lineTo(x, yOf(c.low));
    ctx.stroke();
    const y1 = yOf(Math.max(c.open, c.close));
    const y2 = yOf(Math.min(c.open, c.close));
    ctx.fillRect(x - bodyW / 2, y1, bodyW, Math.max(1.5, y2 - y1));
  });

  // Position Levels
  const levels = [
    { px: ov.target, label: "TP", color: "#00C087" },
    { px: ov.entry, label: "ENTRY", color: "#EAECEF" },
    { px: ov.stop, label: "SL", color: "#F0B90B" },
    { px: ov.liq, label: "LIQ", color: "#F6465D" },
  ];
  levels.forEach((lv) => {
    const v = Number(lv.px);
    if (!Number.isFinite(v) || v <= 0) return;
    const y = yOf(v);
    if (y < padT || y > h - padB) return;
    ctx.strokeStyle = lv.color;
    ctx.lineWidth = 1;
    if (typeof ctx.setLineDash === "function") ctx.setLineDash([4, 3]);
    ctx.beginPath();
    ctx.moveTo(padL, y);
    ctx.lineTo(w - padR, y);
    ctx.stroke();
    if (typeof ctx.setLineDash === "function") ctx.setLineDash([]);
    ctx.fillStyle = lv.color;
    ctx.fillText(`${lv.label} ${v >= 10 ? v.toFixed(2) : v.toFixed(4)}`, padL + 4, y - 3);
  });
}

function drawPolyLineCanvas(canvas, payload) {
  const setup = setupCanvas(canvas);
  if (!setup) return;
  const { ctx, w, h } = setup;
  ctx.fillStyle = "#0B0E11";
  ctx.fillRect(0, 0, w, h);

  const ticks = (payload && payload.ticks) || [];
  if (!ticks.length) {
    ctx.fillStyle = "#848E9C";
    ctx.font = "12px sans-serif";
    ctx.fillText("אין נתוני מחיר לשוק זה", 20, 40);
    return;
  }
  const padL = 12, padR = 54, padT = 16, padB = 24;
  const cw = w - padL - padR;
  const ch = h - padT - padB;
  const sma = payload.sma || [];
  const lower = payload.lower_band || [];
  const pos = payload.position || {};

  let lo = Infinity, hi = -Infinity;
  ticks.forEach((t, i) => {
    if (t.price < lo) lo = t.price;
    if (t.price > hi) hi = t.price;
    if (lower[i] != null && lower[i] < lo) lo = lower[i];
  });
  [pos.avg_price, pos.stop_price, pos.target_price].forEach((v) => {
    if (v != null && Number.isFinite(Number(v))) {
      if (v < lo) lo = Number(v);
      if (v > hi) hi = Number(v);
    }
  });
  if (hi <= lo) hi = lo + 0.02;
  const sp = hi - lo;
  lo = Math.max(0.01, lo - sp * 0.08);
  hi = Math.min(0.99, hi + sp * 0.08);
  const yOf = (p) => padT + (hi - p) / (hi - lo) * ch;
  const xOf = (i) => padL + (i / Math.max(1, ticks.length - 1)) * cw;

  ctx.strokeStyle = "#181E26";
  ctx.lineWidth = 1;
  ctx.font = "10.5px monospace";
  ctx.fillStyle = "#5E6673";
  for (let i = 0; i <= 4; i++) {
    const gy = padT + (ch * i) / 4;
    const gp = hi - ((hi - lo) * i) / 4;
    ctx.beginPath();
    ctx.moveTo(padL, gy);
    ctx.lineTo(w - padR, gy);
    ctx.stroke();
    ctx.fillText(gp.toFixed(3), w - padR + 6, gy + 3);
  }

  // Lower Z-Band & SMA
  const drawSeries = (arr, color, dash) => {
    ctx.strokeStyle = color;
    ctx.lineWidth = 1.1;
    if (typeof ctx.setLineDash === "function") ctx.setLineDash(dash || []);
    ctx.beginPath();
    let started = false;
    arr.forEach((v, i) => {
      if (v == null) return;
      const x = xOf(i), y = yOf(v);
      if (!started) { ctx.moveTo(x, y); started = true; } else ctx.lineTo(x, y);
    });
    ctx.stroke();
    if (typeof ctx.setLineDash === "function") ctx.setLineDash([]);
  };
  drawSeries(sma, "#5E9BFF", [3, 3]);
  drawSeries(lower, "#F0B90B", [2, 3]);

  // Price line
  ctx.strokeStyle = "#00C087";
  ctx.lineWidth = 1.8;
  ctx.beginPath();
  ticks.forEach((t, i) => {
    const x = xOf(i), y = yOf(t.price);
    if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
  });
  ctx.stroke();

  [
    { px: pos.target_price, label: "TP", color: "#00C087" },
    { px: pos.avg_price, label: "ENTRY", color: "#EAECEF" },
    { px: pos.stop_price, label: "SL", color: "#F6465D" },
  ].forEach((lv) => {
    const v = Number(lv.px);
    if (!Number.isFinite(v) || v <= 0) return;
    const y = yOf(v);
    ctx.strokeStyle = lv.color;
    ctx.lineWidth = 1;
    if (typeof ctx.setLineDash === "function") ctx.setLineDash([4, 3]);
    ctx.beginPath();
    ctx.moveTo(padL, y);
    ctx.lineTo(w - padR, y);
    ctx.stroke();
    if (typeof ctx.setLineDash === "function") ctx.setLineDash([]);
    ctx.fillStyle = lv.color;
    ctx.fillText(`${lv.label} ${v.toFixed(3)}`, padL + 4, y - 3);
  });
}

function drawOverviewChart() {
  const c = $("ov-chart");
  if (!c) return;
  const cached = CHART_CACHE.ov;
  if (!cached) {
    const dc = DATA.perps && DATA.perps.default_chart;
    if (dc && (dc.candles || []).length) {
      drawCandlestickCanvas(c, dc);
      updateOvMeta("perps", dc);
    } else if (DATA.charts && DATA.charts.default) {
      drawPolyLineCanvas(c, DATA.charts.default);
      updateOvMeta("poly", DATA.charts.default);
    }
    return;
  }
  if (cached.kind === "perps") {
    drawCandlestickCanvas(c, cached.data);
    updateOvMeta("perps", cached.data);
  } else {
    drawPolyLineCanvas(c, cached.data);
    updateOvMeta("poly", cached.data);
  }
}

function updateOvMeta(kind, data) {
  const meta = $("ov-chart-meta");
  if (!meta) return;
  if (kind === "perps") {
    const cs = data.candles || [];
    const last = cs[cs.length - 1] || {};
    const ov = data.overlays || {};
    meta.innerHTML = `
      <span class="mono">${esc(data.symbol || "")} · ${esc(data.timeframe || "1h")} | C: ${fmt(last.close, 4)} H: ${fmt(last.high, 4)} L: ${fmt(last.low, 4)}</span>
      <span class="mono">${ov.side ? `${ov.side} ×${fmt(ov.leverage, 0)} | SL ${fmt(ov.stop, 4)} | TP ${fmt(ov.target, 4)} | LIQ ${fmt(ov.liq, 4)}` : "ללא פוזיציה פתוחה"}</span>
    `;
  } else {
    const ts = data.ticks || [];
    const last = ts[ts.length - 1] || {};
    const pos = data.position || {};
    meta.innerHTML = `
      <span>${esc((pos.question || data.question || data.token_id || "").slice(0, 64))}</span>
      <span class="mono">Last: ${fmt(last.price, 4)} ${pos.avg_price ? `| Entry ${fmt(pos.avg_price, 3)} | TP ${fmt(pos.target_price, 3)} | SL ${fmt(pos.stop_price, 3)}` : ""}</span>
    `;
  }
}

function drawPerpChart() {
  const c = $("perps-chart");
  if (!c) return;
  const d = CHART_CACHE.perps || (DATA.perps && DATA.perps.default_chart);
  if (d) {
    drawCandlestickCanvas(c, d);
    const meta = $("perps-chart-meta");
    if (meta) {
      const cs = d.candles || [];
      const last = cs[cs.length - 1] || {};
      const ov = d.overlays || {};
      meta.innerHTML = `
        <span class="mono">${esc(d.symbol || "")} · ${esc(d.timeframe || "1h")} | Close ${fmt(last.close, 4)}</span>
        <span class="mono">${ov.side ? `${ov.side} ×${fmt(ov.leverage, 1)} | Entry ${fmt(ov.entry, 4)} | SL ${fmt(ov.stop, 4)} | TP ${fmt(ov.target, 4)} | LIQ ${fmt(ov.liq, 4)}` : "סריקה פעילה"}</span>
      `;
    }
  }
}

function drawPolyChart() {
  const c = $("mkt-chart");
  if (!c) return;
  const d = CHART_CACHE.poly || (DATA.charts && DATA.charts.default);
  if (d) drawPolyLineCanvas(c, d);
}

function redrawActiveCharts() {
  if (ACTIVE_TAB === "overview") drawOverviewChart();
  if (ACTIVE_TAB === "perps") drawPerpChart();
  if (ACTIVE_TAB === "markets") drawPolyChart();
}

function renderOrderbookAndMicro() {
  const box = $("ov-micro-box");
  if (!box) return;
  const sel = OV_SELECTION || { arm: "perps", id: PERP_SYM || "BTC" };
  const perps = DATA.perps || {};
  const g = DATA.guards || {};
  const perpGuards = perps.guards || {};

  let rowsHtml = "";
  let obHtml = "";
  if (sel.arm === "perps") {
    const intel = (perps.intel || []).find((r) => r.symbol === sel.id) || (perps.intel || [])[0] || {};
    const px = Number(intel.price || 0);
    const spBps = Number(intel.spread_bps || 2.0);
    const halfSp = px * (spBps / 20000);
    const bidDepth = Number(intel.bid_depth_usd || 25000);
    const askDepth = Number(intel.ask_depth_usd || 25000);
    const maxD = Math.max(bidDepth, askDepth, 1);

    const asks = [3, 2, 1].map((lv) => {
      const p = px + halfSp * lv;
      const sz = askDepth * (0.18 + 0.14 * lv);
      const pct = Math.min(100, (sz / maxD) * 70);
      return `<div class="ob-row"><div class="ob-bar ask" style="width:${pct.toFixed(0)}%"></div><span class="neg">${fmt(p, px >= 10 ? 3 : 5)}</span><span class="muted">${fmt(sz / 1000, 1)}k</span><span class="dim">ASK L${lv}</span></div>`;
    }).join("");
    const bids = [1, 2, 3].map((lv) => {
      const p = px - halfSp * lv;
      const sz = bidDepth * (0.18 + 0.14 * lv);
      const pct = Math.min(100, (sz / maxD) * 70);
      return `<div class="ob-row"><div class="ob-bar bid" style="width:${pct.toFixed(0)}%"></div><span class="pos">${fmt(p, px >= 10 ? 3 : 5)}</span><span class="muted">${fmt(sz / 1000, 1)}k</span><span class="dim">BID L${lv}</span></div>`;
    }).join("");
    obHtml = `
      <div class="ob-wrap">
        ${asks}
        <div class="ob-spread"><span>SPREAD ${fmt(spBps, 2)} bps</span><span>IMB ${fmtSigned(intel.imbalance, 2)}</span></div>
        ${bids}
      </div>
    `;
    rowsHtml = `
      <div class="kv-item"><span class="muted">Regime</span><span class="mono">${esc(intel.regime || "—")}</span></div>
      <div class="kv-item"><span class="muted">ADX / ER</span><span class="mono">${fmt(intel.adx, 1)} / ${fmt(intel.er, 2)}</span></div>
      <div class="kv-item"><span class="muted">Z / RSI</span><span class="mono">${fmtSigned(intel.z_score, 2)} / ${fmt(intel.rsi, 0)}</span></div>
      <div class="kv-item"><span class="muted">Funding 1h</span><span class="mono">${fmtSigned((intel.funding_1h || 0) * 100, 4)}%</span></div>
      <div class="kv-item"><span class="muted">Perps Margin</span><span class="mono">${fmt(perps.margin_used)} / ${perpGuards.max_margin_pct || 45}%</span></div>
      <div class="kv-item"><span class="muted">Daily Loss Room</span><span class="mono">${fmt(g.daily_room)} USDC</span></div>
    `;
  } else {
    const mi = (DATA.market_intel || []).find((r) => String(r.token_id).startsWith(String(sel.id).slice(0, 12))) || {};
    const mid = Number(mi.price || 0.5);
    const sp = Number(mi.spread || 0.01);
    const bd = Number(mi.bid_depth || 400);
    const ad = Number(mi.ask_depth || 400);
    const maxD = Math.max(bd, ad, 1);
    const asks = [3, 2, 1].map((lv) => `<div class="ob-row"><div class="ob-bar ask" style="width:${Math.min(100, (ad / maxD) * 55).toFixed(0)}%"></div><span class="neg">${fmt(mid + sp * 0.5 * lv, 3)}</span><span class="muted">${fmt(ad * 0.3, 0)}</span><span class="dim">ASK</span></div>`).join("");
    const bids = [1, 2, 3].map((lv) => `<div class="ob-row"><div class="ob-bar bid" style="width:${Math.min(100, (bd / maxD) * 55).toFixed(0)}%"></div><span class="pos">${fmt(mid - sp * 0.5 * lv, 3)}</span><span class="muted">${fmt(bd * 0.3, 0)}</span><span class="dim">BID</span></div>`).join("");
    obHtml = `<div class="ob-wrap">${asks}<div class="ob-spread"><span>SPREAD ${fmt(sp, 3)}</span><span>IMB ${fmtSigned(mi.imbalance, 2)}</span></div>${bids}</div>`;
    rowsHtml = `
      <div class="kv-item"><span class="muted">Z-Score</span><span class="mono">${fmtSigned(mi.z_score, 2)}</span></div>
      <div class="kv-item"><span class="muted">RSI(14)</span><span class="mono">${fmt(mi.rsi, 1)}</span></div>
      <div class="kv-item"><span class="muted">Net Edge</span><span class="mono">${fmtSigned((mi.edge || 0) * 100, 2)}%</span></div>
      <div class="kv-item"><span class="muted">Drawdown</span><span class="mono">${fmt(g.drawdown_pct, 2)}% / ${fmt(g.drawdown_limit_pct, 0)}%</span></div>
      <div class="kv-item"><span class="muted">Exposure Room</span><span class="mono">${fmt(g.exposure_room)} USDC</span></div>
      <div class="kv-item"><span class="muted">Open Slots</span><span class="mono">${g.positions_room ?? 0}</span></div>
    `;
  }
  box.innerHTML = obHtml + `<div class="kv-grid">${rowsHtml}</div>`;
}

function renderBlotter() {
  const posBody = $("ov-positions-body");
  if (posBody) {
    const pRows = (DATA.perps && DATA.perps.positions) || [];
    const mRows = DATA.positions || [];
    const rows = [];
    pRows.forEach((p) => {
      const key = esc(p.symbol);
      const label = esc(`PERPS ${p.symbol} ${p.side}`);
      rows.push(`
        <tr class="clickable" onclick="selectOvAsset('perps','${key}')">
          <td><span class="tag blue">PERPS</span></td>
          <td><b>${esc(p.symbol)}</b> <span class="dim">${esc(p.exchange.toUpperCase())}</span></td>
          <td><span class="tag ${p.side === 'LONG' ? 'green' : 'red'}">${esc(p.side)} ×${fmt(p.leverage, 1)}</span></td>
          <td class="num">${fmt(p.entry_price, p.entry_price >= 10 ? 3 : 5)}</td>
          <td class="num">${fmt(p.mark_price, p.mark_price >= 10 ? 3 : 5)}</td>
          <td class="num">$${fmt(p.notional, 0)} <span class="dim">(${fmt(p.margin_used, 1)})</span></td>
          <td class="num"><span class="warn">${fmt(p.stop_price, 4)}</span> / <span class="pos">${fmt(p.target_price, 4)}</span> / <span class="neg">${fmt(p.liquidation_price, 4)}</span></td>
          <td class="num ${clsPnl(p.unrealized_pnl)}"><b>${fmtSigned(p.unrealized_pnl)}</b> (${fmtSigned(p.roe_pct, 1)}%)</td>
          <td class="num muted">${fmt(p.age_hours, 1)}h</td>
          <td><button class="btn sm danger" onclick="event.stopPropagation(); closePosition('perps','${key}','${label}')">סגור</button></td>
        </tr>
      `);
    });
    mRows.forEach((p) => {
      const key = esc(p.full_token_id || p.token_id);
      const label = esc((p.question || p.token_id).slice(0, 32));
      rows.push(`
        <tr class="clickable" onclick="selectOvAsset('poly','${key}')">
          <td><span class="tag">POLY</span></td>
          <td class="wrap-txt">${esc((p.question || p.token_id).slice(0, 56))}</td>
          <td><span class="tag green">${esc(p.direction)}</span></td>
          <td class="num">${fmt(p.avg_price, 4)}</td>
          <td class="num">${p.mark_price != null ? fmt(p.mark_price, 4) : "—"}</td>
          <td class="num">${fmt(p.size, 1)} <span class="dim">($${fmt(p.size * (p.mark_price || p.avg_price), 1)})</span></td>
          <td class="num"><span class="warn">${p.stop_price != null ? fmt(p.stop_price, 3) : "—"}</span> / <span class="pos">${p.target_price != null ? fmt(p.target_price, 3) : "—"}</span></td>
          <td class="num ${clsPnl(p.unrealized_pnl)}"><b>${fmtSigned(p.unrealized_pnl)}</b> (${fmtSigned(p.unrealized_pct, 1)}%)</td>
          <td class="num muted">${fmt(p.age_hours, 1)}h</td>
          <td><button class="btn sm danger" onclick="event.stopPropagation(); closePosition('polymarket','${key}','${label}')">סגור</button></td>
        </tr>
      `);
    });
    posBody.innerHTML = rows.length ? rows.join("") : `<tr><td colspan="10" class="muted">אין פוזיציות פתוחות בשתי הזרועות</td></tr>`;
  }

  // רדאר מודיעין שווקים חי
  const rBody = $("ov-radar-body");
  if (rBody) {
    const q = ($("radar-filter") && $("radar-filter").value || "").trim().toLowerCase();
    const list = (DATA.market_intel || []).filter((m) => !q || String(m.question || "").toLowerCase().includes(q) || String(m.sector || "").toLowerCase().includes(q));
    rBody.innerHTML = list.slice(0, 35).map((m) => {
      const stCls = m.status === "ENTRY" || m.status === "OPEN" ? "green" : (String(m.status).includes("BLOCK") ? "red" : "");
      return `
        <tr class="clickable" onclick="selectOvAsset('poly','${esc(m.token_id)}')">
          <td class="wrap-txt">${esc((m.question || m.token_id).slice(0, 58))}</td>
          <td><span class="tag">${esc(m.sector || "general")}</span></td>
          <td class="num">${fmt(m.price, 3)}</td>
          <td class="num">${fmtSigned(m.z_score, 2)}</td>
          <td class="num">${m.rsi != null ? fmt(m.rsi, 0) : "—"}</td>
          <td class="num ${clsPnl(m.edge)}">${fmtSigned((m.edge || 0) * 100, 2)}%</td>
          <td class="num">${fmt(m.score, 2)}</td>
          <td><span class="tag ${stCls}">${esc(m.status || "SCAN")}</span></td>
          <td class="muted">${esc((m.reason || "").slice(0, 44))}</td>
        </tr>
      `;
    }).join("") || `<tr><td colspan="9" class="muted">אין נתוני סריקה עדיין</td></tr>`;
  }

  // מילואים אחרונים (Fills)
  const fBody = $("ov-fills-body");
  if (fBody) {
    const rows = [];
    ((DATA.perps && DATA.perps.recent_trades) || []).slice(0, 15).forEach((t) => {
      rows.push({ ts: t.ts, arm: "PERPS", title: `${t.symbol} ${t.side} ×${fmt(t.leverage, 0)}`, side: "CLOSE", px: t.price, size: t.notional, pnl: t.realized, fee: t.fee, reason: t.reason });
    });
    (DATA.fills || []).slice(0, 25).forEach((f) => {
      rows.push({ ts: f.ts, arm: "POLY", title: f.question, side: f.side, px: f.price, size: f.notional, pnl: f.realized, fee: f.fee, reason: f.reason });
    });
    rows.sort((a, b) => b.ts - a.ts);
    fBody.innerHTML = rows.slice(0, 35).map((r) => `
      <tr>
        <td class="num muted">${fmtDateTime(r.ts)}</td>
        <td><span class="tag ${r.arm === 'PERPS' ? 'blue' : ''}">${r.arm}</span></td>
        <td class="wrap-txt">${esc((r.title || "").slice(0, 52))}</td>
        <td><span class="tag ${r.side === 'BUY' ? 'green' : 'amber'}">${esc(r.side)}</span></td>
        <td class="num">${fmt(r.px, 4)}</td>
        <td class="num">$${fmt(r.size, 2)}</td>
        <td class="num ${clsPnl(r.pnl)}">${r.pnl ? fmtSigned(r.pnl) : "—"}</td>
        <td class="num muted">${fmt(r.fee, 3)}</td>
        <td class="muted">${esc((r.reason || "").slice(0, 40))}</td>
      </tr>
    `).join("") || `<tr><td colspan="9" class="muted">אין מילואים עדיין</td></tr>`;
  }
}

function renderPerpsTab() {
  const perps = DATA.perps || {};
  const pwf = (DATA.analytics && DATA.analytics.perp_walkforward) || {};
  const kpi = $("perps-kpi-strip");
  if (kpi) {
    const cells = [
      { k: "הון PERPS", v: `$${fmt(perps.equity)}`, s: `מזומן פנוי $${fmt(perps.cash)}`, c: "" },
      { k: "מרג'ין ומינוף", v: `$${fmt(perps.margin_used)}`, s: `נומינלי $${fmt(perps.notional, 0)} | ממוצע ×${fmt(perps.avg_leverage, 1)}`, c: "" },
      { k: "רווח ממומש", v: `${fmtSigned(perps.overall_pnl)}`, s: `היום ${fmtSigned(perps.today_pnl)} | לא-ממומש ${fmtSigned(perps.unrealized_pnl)}`, c: clsPnl(perps.overall_pnl) },
      { k: "Win Rate & PF", v: `${fmt(perps.win_rate_pct, 1)}%`, s: `PF ${fmt(perps.profit_factor, 2)} | ${perps.closed_trades ?? 0} סגורות`, c: "" },
      { k: "Funding & Fees", v: `${fmtSigned(perps.funding_net, 3)}`, s: `עמלות $${fmt(perps.fees_paid)} | DD ${fmt(perps.drawdown_pct, 2)}%`, c: clsPnl(perps.funding_net) },
      { k: "Walk-Forward OOS", v: pwf.oos_return_pct != null ? `${fmtSigned(pwf.oos_return_pct)}%` : "—", s: pwf.consistency != null ? `עקביות ${fmt(pwf.consistency * 100, 0)}% | ${pwf.total_liqs ?? 0} Liq` : "הרץ oos-test", c: clsPnl(pwf.oos_return_pct) },
    ];
    kpi.innerHTML = cells.map((c) => `
      <div class="kpi-cell">
        <div class="kpi-k">${esc(c.k)}</div>
        <div class="kpi-v ${c.c}">${esc(c.v)}</div>
        <div class="kpi-s">${esc(c.s)}</div>
      </div>
    `).join("");
  }

  const pBody = $("perps-pos-body");
  if (pBody) {
    const ps = perps.positions || [];
    pBody.innerHTML = ps.map((p) => `
      <tr class="clickable" onclick="selectPerpAsset('${esc(p.symbol)}')">
        <td><b>${esc(p.symbol)}</b> <span class="dim">${esc(p.exchange)}</span></td>
        <td><span class="tag ${p.side === 'LONG' ? 'green' : 'red'}">${esc(p.side)} ×${fmt(p.leverage, 1)}</span></td>
        <td class="num">${fmt(p.entry_price, p.entry_price >= 10 ? 3 : 5)}</td>
        <td class="num">${fmt(p.mark_price, p.mark_price >= 10 ? 3 : 5)}</td>
        <td class="num">$${fmt(p.margin_used, 2)} / $${fmt(p.notional, 0)}</td>
        <td class="num warn">${fmt(p.stop_price, 4)}</td>
        <td class="num pos">${fmt(p.target_price, 4)}</td>
        <td class="num neg">${fmt(p.liquidation_price, 4)} (${fmt(p.liq_distance_pct, 1)}%)</td>
        <td class="num ${clsPnl(p.unrealized_pnl)}"><b>${fmtSigned(p.unrealized_pnl)}</b> (${fmtSigned(p.roe_pct, 1)}%)</td>
        <td><button class="btn sm danger" onclick="event.stopPropagation(); closePosition('perps','${esc(p.symbol)}','${esc(p.symbol + ' ' + p.side)}')">סגור</button></td>
      </tr>
    `).join("") || `<tr><td colspan="10" class="muted">אין פוזיציות PERPS פתוחות כרגע</td></tr>`;
  }

  const sBody = $("perps-scan-body");
  if (sBody) {
    const intel = perps.intel || [];
    sBody.innerHTML = intel.map((r) => `
      <tr class="clickable" onclick="selectPerpAsset('${esc(r.symbol)}')">
        <td><b>${esc(r.symbol)}</b></td>
        <td class="muted">${esc((r.exchange || "").toUpperCase())}</td>
        <td class="num">${fmt(r.price, r.price >= 10 ? 3 : 5)}</td>
        <td><span class="tag">${esc(r.regime || "—")}</span></td>
        <td class="num">${fmt(r.adx, 1)}</td>
        <td class="num">${fmt(r.rsi, 1)}</td>
        <td class="num">${fmtSigned(r.z_score, 2)}</td>
        <td class="num">${fmt(r.atr_pct, 2)}%</td>
        <td class="num">${fmtSigned((r.funding_1h || 0) * 100, 4)}%</td>
        <td class="num">${fmt(r.score, 2)} (${esc(r.setup_tier || "B")})</td>
        <td><span class="tag ${r.status === 'OPEN' || r.status === 'ENTRY' ? 'green' : ''}">${esc(r.status || "SCAN")}</span></td>
        <td class="muted">${esc((r.reason || "").slice(0, 42))}</td>
      </tr>
    `).join("") || `<tr><td colspan="12" class="muted">טרם נסרקו נכסי PERPS</td></tr>`;
  }
  renderPerpsThesis();
}

function renderPerpsThesis() {
  const box = $("perps-thesis-box");
  if (!box) return;
  const perps = DATA.perps || {};
  const sym = PERP_SYM || (perps.positions && perps.positions[0] && perps.positions[0].symbol) || "BTC";
  const pos = (perps.positions || []).find((p) => p.symbol === sym);
  const intel = (perps.intel || []).find((r) => r.symbol === sym);
  if (pos) {
    box.innerHTML = `<b>${esc(pos.symbol)} ${esc(pos.side)} ×${fmt(pos.leverage, 1)}</b> (${esc(pos.strategy)} / ${esc(pos.regime)}) — כניסה <span class="mono">${fmt(pos.entry_price, 4)}</span> · נוכחי <span class="mono">${fmt(pos.mark_price, 4)}</span> · מרחק ליקווידציה <span class="mono">${fmt(pos.liq_distance_pct, 1)}%</span> · ROE <span class="mono ${clsPnl(pos.roe_pct)}">${fmtSigned(pos.roe_pct, 1)}%</span>.`;
  } else if (intel) {
    box.innerHTML = `<b>${esc(intel.symbol)}</b> (${esc((intel.exchange || "").toUpperCase())}) — משטר <span class="mono">${esc(intel.regime)}</span> · ADX <span class="mono">${fmt(intel.adx, 1)}</span> · Z <span class="mono">${fmtSigned(intel.z_score, 2)}</span> · ${esc(intel.reason || "במעקב")}`;
  } else {
    box.textContent = "בחר נכס מהטבלה או מהבורר כדי להציג נתוני משטר ומינוף.";
  }
}

async function runPerpsSim() {
  const resEl = $("perps-sim-res");
  const lev = Number(($("sim-lev") && $("sim-lev").value) || 50);
  const sl = Number(($("sim-sl") && $("sim-sl").value) || 1.5);
  const tp = Number(($("sim-tp") && $("sim-tp").value) || 2.6);
  try {
    if (resEl) resEl.textContent = "מריץ בדיקת לחץ על נרות היסטוריים...";
    const res = await apiPost("/api/perps/simulate", { max_leverage: lev, sl_atr_mult: sl, tp_atr_mult: tp });
    if (res.result && resEl) {
      const r = res.result;
      resEl.innerHTML = `<span class="mono">נכסים: ${r.assets} | תשואה: <b class="${clsPnl(r.return_pct)}">${fmtSigned(r.return_pct)}%</b> | PF: ${fmt(r.profit_factor, 2)} | WR: ${fmt(r.win_rate_pct, 0)}% | DD: ${fmt(r.max_drawdown_pct, 1)}% | ליקווידציות: <b class="${r.liquidations > 0 ? 'neg' : 'pos'}">${r.liquidations}</b></span>`;
    } else if (resEl) {
      resEl.textContent = res.message || "הושלם";
    }
  } catch (e) {
    if (resEl) resEl.textContent = "שגיאה: " + (e.message || e);
  }
}

function renderMarketsTab() {
  const mPos = $("poly-pos-body");
  if (mPos) {
    const ps = DATA.positions || [];
    mPos.innerHTML = ps.map((p) => {
      const tid = esc(p.full_token_id || p.token_id);
      return `
        <tr class="clickable" onclick="selectPolyAsset('${tid}')">
          <td class="wrap-txt">${esc((p.question || p.token_id).slice(0, 62))}</td>
          <td><span class="tag green">${esc(p.direction)}</span></td>
          <td class="num">${fmt(p.size, 1)}</td>
          <td class="num">${fmt(p.avg_price, 4)}</td>
          <td class="num">${p.mark_price != null ? fmt(p.mark_price, 4) : "—"}</td>
          <td class="num"><span class="warn">${p.stop_price != null ? fmt(p.stop_price, 3) : "—"}</span> / <span class="pos">${p.target_price != null ? fmt(p.target_price, 3) : "—"}</span></td>
          <td class="num ${clsPnl(p.unrealized_pnl)}">${fmtSigned(p.unrealized_pnl)} (${fmtSigned(p.unrealized_pct, 1)}%)</td>
          <td class="num muted">${fmt(p.age_hours, 1)}h</td>
          <td><button class="btn sm danger" onclick="event.stopPropagation(); closePosition('polymarket','${tid}','${esc((p.question || tid).slice(0, 30))}')">סגור</button></td>
        </tr>
      `;
    }).join("") || `<tr><td colspan="9" class="muted">אין פוזיציות Polymarket פתוחות</td></tr>`;
  }

  const sigBody = $("poly-signals-body");
  if (sigBody) {
    sigBody.innerHTML = (DATA.signals || []).slice(0, 30).map((s) => `
      <tr>
        <td class="num muted">${fmtDateTime(s.ts)}</td>
        <td class="wrap-txt">${esc((s.question || s.token_id).slice(0, 50))}</td>
        <td><span class="tag ${s.direction === 'BUY' ? 'green' : ''}">${esc(s.direction)}</span></td>
        <td class="num">${fmt(s.market_price, 3)} -> ${fmt(s.fair_price, 3)}</td>
        <td class="num">${s.z != null ? fmtSigned(s.z, 2) : "—"}</td>
        <td class="num ${clsPnl(s.edge)}">${fmtSigned((s.edge || 0) * 100, 2)}%</td>
        <td class="num">${fmt(s.score, 2)}</td>
        <td class="muted">${esc((s.reason || "").slice(0, 44))}</td>
      </tr>
    `).join("") || `<tr><td colspan="8" class="muted">אין אותות רשומים</td></tr>`;
  }
}

function renderNewsAndLearningTab() {
  const pulse = DATA.world_pulse || {};
  const na = DATA.news_alpha || {};
  const lr = DATA.learning || {};
  const wf = (DATA.analytics && DATA.analytics.walkforward) || {};
  const pwf = (DATA.analytics && DATA.analytics.perp_walkforward) || {};

  const kpi = $("news-kpi-strip");
  if (kpi) {
    const cells = [
      { k: "מצב מאקרו גלובלי", v: esc(pulse.regime || "שקט"), s: `סנטימנט ${fmtSigned(pulse.avg_sentiment, 2)} | ${pulse.sources || 0} מקורות`, c: clsPnl(pulse.avg_sentiment) },
      { k: "קטליסטים פעילים", v: `${pulse.catalysts ?? 0}`, s: `מתוך ${pulse.total ?? 0} כתבות (72h)`, c: "" },
      { k: "דיוק חדשות חי (News Alpha)", v: na.directional_hit_pct != null ? `${fmt(na.directional_hit_pct, 1)}%` : "ממתין לדגימה", s: `${na.total_measured ?? 0} כתבות נמדדו מול מחיר`, c: "" },
      { k: "Polymarket OOS (Walk-Forward)", v: wf.oos_pnl != null ? `${fmtSigned(wf.oos_pnl)} USDC` : "—", s: wf.consistency != null ? `עקביות ${fmt(wf.consistency * 100, 0)}% | ${wf.oos_trades ?? 0} עסקאות` : "", c: clsPnl(wf.oos_pnl) },
      { k: "PERPS OOS (Walk-Forward)", v: pwf.oos_return_pct != null ? `${fmtSigned(pwf.oos_return_pct)}%` : "—", s: pwf.consistency != null ? `עקביות ${fmt(pwf.consistency * 100, 0)}% | ${pwf.total_trades ?? 0} עסקאות` : "", c: clsPnl(pwf.oos_return_pct) },
      { k: "מחזורי למידה", v: `${(lr.runs || []).length}`, s: "OOS מבוקר (ללא קידום רעש)", c: "" },
    ];
    kpi.innerHTML = cells.map((c) => `
      <div class="kpi-cell">
        <div class="kpi-k">${esc(c.k)}</div>
        <div class="kpi-v ${c.c}">${c.v}</div>
        <div class="kpi-s">${esc(c.s)}</div>
      </div>
    `).join("");
  }

  const nBody = $("news-body");
  if (nBody) {
    nBody.innerHTML = (DATA.news || []).slice(0, 60).map((n) => `
      <tr>
        <td class="num muted">${fmtDateTime(n.ts)}</td>
        <td><span class="tag">${esc(n.region || "Global")}</span></td>
        <td class="muted">${esc(n.source || "")}</td>
        <td class="num ${n.impact >= 0.65 ? 'warn' : 'muted'}">${fmt(n.impact, 2)}</td>
        <td class="num ${clsPnl(n.sentiment)}">${fmtSigned(n.sentiment, 2)}</td>
        <td class="wrap-txt">${esc(n.title)}</td>
      </tr>
    `).join("") || `<tr><td colspan="6" class="muted">אין כתבות במאגר</td></tr>`;
  }

  const wfBody = $("wf-folds-body");
  if (wfBody) {
    const rows = [];
    (wf.folds || []).forEach((f) => {
      rows.push(`<tr><td><span class="tag">POLY #${f.index}</span></td><td class="num ${clsPnl(f.train_pnl)}">${fmtSigned(f.train_pnl)} (${f.train_trades})</td><td class="num ${clsPnl(f.oos_pnl)}"><b>${fmtSigned(f.oos_pnl)}</b></td><td class="num">${f.oos_trades} (${fmt(f.oos_win_rate, 0)}%)</td></tr>`);
    });
    (pwf.folds || []).forEach((f) => {
      rows.push(`<tr><td><span class="tag blue">PERPS #${f.index}</span></td><td class="num">—</td><td class="num ${clsPnl(f.oos_return_pct)}"><b>${fmtSigned(f.oos_return_pct)}%</b></td><td class="num">${f.oos_trades} (Liq ${f.oos_liqs})</td></tr>`);
    });
    wfBody.innerHTML = rows.join("") || `<tr><td colspan="4" class="muted">הרץ בדיקת Walk-Forward לצפייה בחלונות OOS</td></tr>`;
  }

  const naBody = $("news-alpha-body");
  if (naBody) {
    const srcs = (na && na.by_source) || [];
    naBody.innerHTML = srcs.slice(0, 12).map((s) => `
      <tr>
        <td>${esc(s.source)}</td>
        <td class="num">${s.n}</td>
        <td class="num ${s.hit_pct >= 55 ? 'pos' : ''}">${s.hit_pct != null ? fmt(s.hit_pct, 1) + "%" : "—"}</td>
      </tr>
    `).join("") || `<tr><td colspan="3" class="muted">צובר תצפיות News Alpha</td></tr>`;
  }
}

function renderOpsTab() {
  const rd = DATA.readiness || {};
  const rdTitle = $("readiness-summary");
  if (rdTitle) {
    rdTitle.textContent = rd.summary || "—";
    rdTitle.className = "tag " + (rd.ready ? "green" : "amber");
  }
  const rdBody = $("readiness-body");
  if (rdBody) {
    rdBody.innerHTML = (rd.checks || []).map((c) => {
      const cls = c.status === "ok" ? "green" : (c.status === "warn" ? "amber" : "red");
      return `
        <tr>
          <td><span class="tag ${cls}">${esc(String(c.status).toUpperCase())}</span></td>
          <td><b>${esc(c.label)}</b></td>
          <td class="muted wrap-txt">${esc(c.detail)}</td>
        </tr>
      `;
    }).join("") || `<tr><td colspan="3" class="muted">אין בדיקות מוכנות</td></tr>`;
  }

  const cfgBody = $("cfg-body");
  if (cfgBody && DATA.config) {
    const u = DATA.config.universe || {};
    const s = DATA.config.signal || {};
    const r = DATA.config.risk || {};
    const ex = DATA.config.execution || {};
    const rows = [
      ["מצב ביצוע", `${ex.mode} | עמלות ${ex.fee_mode} | ${ex.order_type}`],
      ["טווח מחירים וזמן הכרעה", `[${(u.price_band || []).join(", ")}] | כניסה ≥ ${u.min_entry_hours_to_resolution}h לפני פדיון`],
      ["מנוע וסיגנל Polymarket", `${s.engine} | z≥${s.z_entry} | RSI≤${s.rsi_max} | TP ${s.take_profit} / SL ${s.stop_loss} (${s.stop_mode})`],
      ["גבולות סיכון Polymarket", `Daily ${(r.max_daily_loss_pct * 100).toFixed(0)}% | MaxDD ${(r.max_drawdown_pct * 100).toFixed(0)}% | Exposure ${(r.max_total_exposure_pct * 100).toFixed(0)}% | ${r.max_open_positions} פוזיציות`],
      ["זרוע PERPS", `×${(DATA.perps && DATA.perps.max_leverage) || 50} מקסימלי | Isolated Margin | Dynamic Volatility Cap`],
    ];
    cfgBody.innerHTML = rows.map(([k, v]) => `<tr><td class="muted">${esc(k)}</td><td class="mono">${esc(v)}</td></tr>`).join("");
  }

  const apBody = $("autopilot-body");
  if (apBody) {
    apBody.innerHTML = (DATA.autopilot || []).slice(0, 20).map((a) => `
      <tr>
        <td class="num muted">${fmtDateTime(a.ts)}</td>
        <td><span class="tag">${esc(a.kind)}</span></td>
        <td class="wrap-txt">${esc(a.summary || "")}</td>
      </tr>
    `).join("") || `<tr><td colspan="3" class="muted">אין רישומים ביומן עדיין</td></tr>`;
  }

  const bkBody = $("backups-body");
  if (bkBody) {
    bkBody.innerHTML = (DATA.backups || []).slice(0, 8).map((b) => `
      <tr>
        <td class="mono">${esc(b.name)}</td>
        <td class="num">${fmt(b.size_kb, 1)} KB</td>
        <td class="num muted">${fmtDateTime(b.ts)}</td>
      </tr>
    `).join("") || `<tr><td colspan="3" class="muted">אין גיבויים</td></tr>`;
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
    items.push({ kind: "PERPS", title: `${r.symbol} (${r.exchange}) · ${r.regime}`, sub: `${fmt(r.price, 3)} | Z=${fmtSigned(r.z_score, 2)}`, fn: () => { closeSpot(); switchTab("perps"); selectPerpAsset(r.symbol); } });
  });
  (DATA.positions || []).forEach((p) => {
    const tid = p.full_token_id || p.token_id;
    items.push({ kind: "OPEN", title: p.question || tid, sub: `Entry ${fmt(p.avg_price, 3)}`, fn: () => { closeSpot(); switchTab("markets"); selectPolyAsset(tid); } });
  });
  (DATA.market_intel || []).slice(0, 20).forEach((m) => {
    items.push({ kind: "POLY", title: m.question || m.token_id, sub: `${fmt(m.price, 3)} | ${m.status}`, fn: () => { closeSpot(); switchTab("overview"); selectOvAsset("poly", m.token_id); } });
  });
  const filt = items.filter((it) => !term || it.title.toLowerCase().includes(term) || it.kind.toLowerCase().includes(term)).slice(0, 18);
  window.__spotItems = filt;
  box.innerHTML = filt.map((it, i) => `
    <div class="spot-item" onclick="window.__spotItems[${i}].fn()">
      <div><span class="tag">${esc(it.kind)}</span> ${esc(it.title.slice(0, 62))}</div>
      <span class="mono muted">${esc(it.sub)}</span>
    </div>
  `).join("") || `<div class="spot-item muted">אין התאמות</div>`;
}

function renderAll() {
  syncSelectors();
  renderTopBar();
  renderCombinedHero();
  renderOrderbookAndMicro();
  renderBlotter();
  renderPerpsTab();
  renderMarketsTab();
  renderNewsAndLearningTab();
  renderOpsTab();
  redrawActiveCharts();
}

async function refreshState() {
  try {
    DATA = await apiGet("/api/state");
    renderAll();
  } catch (e) {
    console.warn("state poll failed", e);
  }
}

function toggleLoop() {
  const btn = $("btn-loop");
  const running = btn && btn.getAttribute("data-running") === "1";
  runAction(running ? "/api/trader/stop" : "/api/trader/start", {});
}

function initTerminal(refreshSec) {
  renderAll();
  if (OV_SELECTION) selectOvAsset(OV_SELECTION.arm, OV_SELECTION.id, false);
  if (PERP_SYM) selectPerpAsset(PERP_SYM, false);
  if (POLY_TID) selectPolyAsset(POLY_TID, false);

  document.addEventListener("keydown", (ev) => {
    if ((ev.metaKey || ev.ctrlKey) && ev.key.toLowerCase() === "k") {
      ev.preventDefault();
      openSpot();
    } else if (ev.key === "Escape") {
      closeSpot();
    }
  });
  window.addEventListener("resize", () => redrawActiveCharts());
  if (refreshSec > 0) {
    POLL_TIMER = setInterval(() => refreshState(), Math.max(5, refreshSec) * 1000);
  }
}
"""


def command_center_html(data: dict, *, refresh_sec: int = 30, interactive: bool = True) -> str:
    """מייצר קובץ HTML עצמאי של הטרמינל המוסדי של PMMB."""
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    refresh_val = int(refresh_sec) if (interactive and refresh_sec > 0) else 0

    return (
        '<!doctype html><html lang="he" dir="rtl"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>PMMB Command Center — Institutional Trading Terminal</title>'
        f"<style>{_TERMINAL_CSS}</style></head><body>"
        # Top Institutional Ticker Bar
        '<header class="topbar"><div class="topbar-inner">'
        '<div class="brand-grp">'
        '<div class="brand-mark"><span id="hdr-dot" class="dot"></span><span>PMMB Command Center</span></div>'
        '<span id="hdr-mode" class="tag blue">PAPER</span>'
        '<span id="hdr-status" class="tag green">INIT</span>'
        '<span class="dim mono" style="font-size:11px">HEARTBEAT <span id="hdr-age">—</span></span>'
        '</div>'
        '<div id="hdr-ticker" class="ticker-strip"></div>'
        '<div class="ctrl-grp">'
        '<button class="btn sm" onclick="openSpot()">חיפוש <span class="mono muted">⌘K</span></button>'
        '<button class="btn sm primary" onclick="runAction(\'/api/news-refresh\')">סנכרן שוק</button>'
        '<button id="btn-loop" class="btn sm" data-running="0" onclick="toggleLoop()">הפעל לולאה</button>'
        '<button class="btn sm danger" onclick="runAction(\'/api/halt\',{reason:\'עצירת חירום מהטרמינל\'},\'להפעיל Kill Switch ולעצור כניסות חדשות?\')">KILL SWITCH</button>'
        '</div>'
        '</div>'
        '<nav class="nav-bar"><div class="nav-tabs">'
        '<button class="nav-tab active" data-tab="overview" onclick="switchTab(\'overview\')">סקירה ומסחר</button>'
        '<button class="nav-tab" data-tab="perps" onclick="switchTab(\'perps\')">PERPS ×50</button>'
        '<button class="nav-tab" data-tab="markets" onclick="switchTab(\'markets\')">שווקים וגרפים</button>'
        '<button class="nav-tab" data-tab="learning" onclick="switchTab(\'learning\')">חדשות ולמידה</button>'
        '<button class="nav-tab" data-tab="ops" onclick="switchTab(\'ops\')">תפעול אוטונומי</button>'
        '</div></nav></header>'
        # Main Content
        '<main class="wrap">'
        '<div id="halt-banner" class="banner" style="display:none">'
        '<div><b>TRADING HALTED:</b> <span id="halt-reason"></span></div>'
        '<button class="btn sm" onclick="runAction(\'/api/resume\',{})">שחרר עצירה</button>'
        '</div>'
        # TAB 1: Overview & Execution Desk
        '<section id="tab-overview" class="tab-pane active">'
        '<div id="combined-hero" class="kpi-strip"></div>'
        '<div class="desk-grid">'
        '<div class="panel no-mb">'
        '<div class="panel-hd">'
        '<div><span class="panel-title">גרף ביצוע ורמות סיכון</span> <span class="panel-sub">קנבס זמן אמת</span></div>'
        '<div class="ctrl-grp">'
        '<select id="ov-asset-sel" class="sel" onchange="const v=this.value.split(\':\');selectOvAsset(v[0],v.slice(1).join(\':\'),false)"></select>'
        '<button class="btn sm" onclick="if(OV_SELECTION)selectOvAsset(OV_SELECTION.arm,OV_SELECTION.id,true)">רענן חי</button>'
        '</div>'
        '</div>'
        '<div class="panel-bd">'
        '<div class="chart-box"><canvas id="ov-chart"></canvas></div>'
        '<div id="ov-chart-meta" class="chart-meta"></div>'
        '</div>'
        '</div>'
        '<div class="panel no-mb">'
        '<div class="panel-hd"><span class="panel-title">L2 Orderbook ומדדי סיכון</span><span class="panel-sub">מיקרו-מבנה בזמן אמת</span></div>'
        '<div id="ov-micro-box" class="panel-bd flush"></div>'
        '</div>'
        '</div>'
        # Blotter
        '<div class="panel">'
        '<div class="panel-hd">'
        '<div class="subtabs">'
        '<button class="subtab active" data-blotter="positions" onclick="switchBlotter(\'positions\')">פוזיציות פתוחות</button>'
        '<button class="subtab" data-blotter="radar" onclick="switchBlotter(\'radar\')">רדאר מודיעין שווקים חי</button>'
        '<button class="subtab" data-blotter="fills" onclick="switchBlotter(\'fills\')">מילואים אחרונים</button>'
        '</div>'
        '<div class="ctrl-grp">'
        '<input id="radar-filter" class="inp" placeholder="סינון שוק / סקטור..." oninput="renderBlotter()">'
        '<button class="btn sm" onclick="runAction(\'/api/perps/cycle\')">מחזור PERPS</button>'
        '<button class="btn sm" onclick="runAction(\'/api/paper-cycle\')">מחזור POLY</button>'
        '</div>'
        '</div>'
        '<div id="blotter-positions" class="blotter-pane tbl-wrap">'
        '<table class="tbl"><thead><tr>'
        '<th>זרוע</th><th>נכס / שוק</th><th>כיוון ומינוף</th><th>כניסה</th><th>נוכחי</th>'
        '<th>גודל / נומינלי</th><th>SL / TP / LIQ</th><th>לא-ממומש</th><th>גיל</th><th>ביצוע</th>'
        '</tr></thead><tbody id="ov-positions-body"></tbody></table></div>'
        '<div id="blotter-radar" class="blotter-pane tbl-wrap" style="display:none">'
        '<table class="tbl"><thead><tr>'
        '<th>שוק</th><th>סקטור</th><th>מחיר</th><th>Z</th><th>RSI</th><th>Net Edge</th><th>ציון</th><th>סטטוס</th><th>נימוק</th>'
        '</tr></thead><tbody id="ov-radar-body"></tbody></table></div>'
        '<div id="blotter-fills" class="blotter-pane tbl-wrap" style="display:none">'
        '<table class="tbl"><thead><tr>'
        '<th>זמן</th><th>זרוע</th><th>נכס / שוק</th><th>פעולה</th><th>מחיר</th><th>נומינלי</th><th>ממומש</th><th>עמלה</th><th>סיבה</th>'
        '</tr></thead><tbody id="ov-fills-body"></tbody></table></div>'
        '</div>'
        '</section>'
        # TAB 2: PERPS x50
        '<section id="tab-perps" class="tab-pane">'
        '<div id="perps-kpi-strip" class="kpi-strip"></div>'
        '<div class="desk-grid">'
        '<div class="panel no-mb">'
        '<div class="panel-hd">'
        '<span class="panel-title">גרף נרות PERPS ×50 (1H)</span>'
        '<div class="ctrl-grp">'
        '<select id="perp-asset-sel" class="sel mono" onchange="selectPerpAsset(this.value,false)"></select>'
        '<button class="btn sm" onclick="if(PERP_SYM)selectPerpAsset(PERP_SYM,true)">שידור חי</button>'
        '<button class="btn sm primary" onclick="runAction(\'/api/perps/cycle\')">הרץ מחזור</button>'
        '</div></div>'
        '<div class="panel-bd">'
        '<div class="chart-box tall"><canvas id="perps-chart"></canvas></div>'
        '<div id="perps-chart-meta" class="chart-meta"></div>'
        '</div></div>'
        '<div class="panel no-mb">'
        '<div class="panel-hd"><span class="panel-title">תיזת פוזיציה ובדיקת לחץ (OOS Stress Test)</span></div>'
        '<div class="panel-bd" style="display:flex;flex-direction:column;gap:10px">'
        '<div id="perps-thesis-box" class="thesis-box"></div>'
        '<div class="sim-form">'
        '<label class="sim-field"><span>Max Lev</span><input id="sim-lev" class="inp mono" style="width:74px" type="number" min="2" max="50" value="50"></label>'
        '<label class="sim-field"><span>SL × ATR</span><input id="sim-sl" class="inp mono" style="width:74px" type="number" step="0.1" min="0.8" max="4" value="1.5"></label>'
        '<label class="sim-field"><span>TP × ATR</span><input id="sim-tp" class="inp mono" style="width:74px" type="number" step="0.1" min="1.2" max="6" value="2.6"></label>'
        '<button class="btn sm primary" onclick="runPerpsSim()">הרץ בדיקת לחץ</button>'
        '</div>'
        '<div id="perps-sim-res" class="thesis-box muted">תוצאת סימולציית פורטפוליו תופיע כאן.</div>'
        '</div></div>'
        '</div>'
        '<div class="panel">'
        '<div class="panel-hd"><span class="panel-title">פוזיציות PERPS פתוחות</span></div>'
        '<div class="tbl-wrap"><table class="tbl"><thead><tr>'
        '<th>נכס</th><th>כיוון ומינוף</th><th>כניסה</th><th>נוכחי</th><th>מרג\'ין / נומינלי</th>'
        '<th>Stop</th><th>Target</th><th>Liquidation</th><th>PnL / ROE</th><th>פעולה</th>'
        '</tr></thead><tbody id="perps-pos-body"></tbody></table></div></div>'
        '<div class="panel">'
        '<div class="panel-hd"><span class="panel-title">סריקת Top-16 נכסי קריפטו (OKX + Hyperliquid)</span></div>'
        '<div class="tbl-wrap"><table class="tbl"><thead><tr>'
        '<th>נכס</th><th>זירה</th><th>מחיר</th><th>משטר</th><th>ADX</th><th>RSI</th><th>Z</th><th>ATR%</th><th>Fund 1h</th><th>ציון</th><th>סטטוס</th><th>הערה</th>'
        '</tr></thead><tbody id="perps-scan-body"></tbody></table></div></div>'
        '</section>'
        # TAB 3: Polymarket Execution & Charts
        '<section id="tab-markets" class="tab-pane">'
        '<div class="panel">'
        '<div class="panel-hd"><span class="panel-title">גרף מחיר ותיקון לממוצע — Polymarket</span>'
        '<div class="ctrl-grp"><select id="poly-asset-sel" class="sel" onchange="selectPolyAsset(this.value,false)"></select>'
        '<button class="btn sm" onclick="if(POLY_TID)selectPolyAsset(POLY_TID,true)">רענן ספר</button></div></div>'
        '<div class="panel-bd"><div class="chart-box"><canvas id="mkt-chart"></canvas></div></div>'
        '</div>'
        '<div class="panel"><div class="panel-hd"><span class="panel-title">פוזיציות Polymarket פתוחות</span></div>'
        '<div class="tbl-wrap"><table class="tbl"><thead><tr>'
        '<th>שוק</th><th>כיוון</th><th>מניות</th><th>כניסה</th><th>נוכחי</th><th>SL / TP</th><th>לא-ממומש</th><th>גיל</th><th>ביצוע</th>'
        '</tr></thead><tbody id="poly-pos-body"></tbody></table></div></div>'
        '<div class="panel"><div class="panel-hd"><span class="panel-title">היסטוריית אותות מסחר אחרונים</span></div>'
        '<div class="tbl-wrap"><table class="tbl"><thead><tr>'
        '<th>זמן</th><th>שוק</th><th>כיוון</th><th>מחיר -> הוגן</th><th>Z</th><th>Edge</th><th>ציון</th><th>סיבה</th>'
        '</tr></thead><tbody id="poly-signals-body"></tbody></table></div></div>'
        '</section>'
        # TAB 4: News & Walk-Forward Learning
        '<section id="tab-learning" class="tab-pane">'
        '<div id="news-kpi-strip" class="kpi-strip"></div>'
        '<div class="grid-2">'
        '<div class="panel no-mb"><div class="panel-hd"><span class="panel-title">חלונות Walk-Forward OOS (Polymarket + PERPS)</span>'
        '<button class="btn sm primary" onclick="runAction(\'/api/learn\',{apply:true})">הרץ למידה OOS</button></div>'
        '<div class="tbl-wrap"><table class="tbl"><thead><tr><th>חלון</th><th>אימון</th><th>מבחן OOS</th><th>עסקאות</th></tr></thead><tbody id="wf-folds-body"></tbody></table></div></div>'
        '<div class="panel no-mb"><div class="panel-hd"><span class="panel-title">דירוג דיוק מקורות חדשות (News Alpha)</span></div>'
        '<div class="tbl-wrap"><table class="tbl"><thead><tr><th>מקור</th><th>נמדדו</th><th>דיוק כיווני</th></tr></thead><tbody id="news-alpha-body"></tbody></table></div></div>'
        '</div>'
        '<div class="panel"><div class="panel-hd"><span class="panel-title">זרם חדשות מאקרו ושווקים (19 סוכנויות)</span></div>'
        '<div class="tbl-wrap"><table class="tbl"><thead><tr><th>זמן</th><th>אזור</th><th>מקור</th><th>Impact</th><th>Sentiment</th><th>כותרת</th></tr></thead><tbody id="news-body"></tbody></table></div></div>'
        '</section>'
        # TAB 5: Readiness, Risk & Autopilot
        '<section id="tab-ops" class="tab-pane">'
        '<div class="panel"><div class="panel-hd"><span class="panel-title">שליטה, אימות מאזן וגיבוי מערכת</span>'
        '<div class="ctrl-grp">'
        '<button class="btn sm primary" onclick="runAction(\'/api/reconcile\')">אימות מאזן DB</button>'
        '<button class="btn sm" onclick="runAction(\'/api/backup\')">גיבוי חם</button>'
        '<button class="btn sm" onclick="runAction(\'/api/autopilot/maintain\')">תחזוקה מלאה</button>'
        '<button class="btn sm" onclick="runAction(\'/api/perps/learn\',{apply:true})">אימות PERPS OOS</button>'
        '</div></div></div>'
        '<div class="grid-2">'
        '<div class="panel no-mb"><div class="panel-hd"><span class="panel-title">שער מוכנות ל-Live (Readiness Gate)</span><span id="readiness-summary" class="tag">—</span></div>'
        '<div class="tbl-wrap"><table class="tbl"><thead><tr><th>סטטוס</th><th>בדיקה</th><th>ממצא</th></tr></thead><tbody id="readiness-body"></tbody></table></div></div>'
        '<div class="panel no-mb"><div class="panel-hd"><span class="panel-title">פרמטרי ניהול סיכונים ויקום פעילים</span></div>'
        '<div class="tbl-wrap"><table class="tbl"><thead><tr><th>פרמטר</th><th>ערך פעיל</th></tr></thead><tbody id="cfg-body"></tbody></table></div></div>'
        '</div>'
        '<div class="grid-2">'
        '<div class="panel no-mb"><div class="panel-hd"><span class="panel-title">יומן טייס אוטומטי</span></div>'
        '<div class="tbl-wrap"><table class="tbl"><thead><tr><th>זמן</th><th>סוג</th><th>פעולה</th></tr></thead><tbody id="autopilot-body"></tbody></table></div></div>'
        '<div class="panel no-mb"><div class="panel-hd"><span class="panel-title">גיבויי DB שמורים</span></div>'
        '<div class="tbl-wrap"><table class="tbl"><thead><tr><th>קובץ</th><th>גודל</th><th>זמן</th></tr></thead><tbody id="backups-body"></tbody></table></div></div>'
        '</div>'
        '</section>'
        '</main>'
        # Command Palette (#spot-overlay)
        '<div id="spot-overlay" class="spot-overlay" onclick="if(event.target===this)closeSpot()">'
        '<div class="spot-box">'
        '<div class="spot-inp-wrap"><span class="mono muted">&gt;</span>'
        '<input id="spot-inp" class="spot-inp" placeholder="חפש נכס PERPS, שוק Polymarket או פוזיציה..." oninput="renderSpotList(this.value)">'
        '<button class="btn sm" onclick="closeSpot()">ESC</button></div>'
        '<div id="spot-list" class="spot-list"></div>'
        '</div></div>'
        '<div id="toast" class="toast"></div>'
        f"<script>window.__PMMB_INIT__ = {payload};\n{_TERMINAL_JS}\ninitTerminal({refresh_val});</script>"
        '</body></html>'
    )
