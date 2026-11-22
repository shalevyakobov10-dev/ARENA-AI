"""
ממשק תוכנת הבקרה השלמה — PMMB Command Center.

עובד הן כיישום Web אינטראקטיבי חי דרך `pmmb serve` (מתרענן חיה + פעולות בקרה +
הזרמת גרפים, חדשות ולמידה עצמית ללא הפסקה)
והן כדוח עצמאי מלא (Bootstrap JSON מוטמע, אפס תלויות חיצוניות / CDN, אפס URLs).
"""
from __future__ import annotations

import json


def command_center_html(initial_state: dict, *, refresh_sec: int = 15, interactive: bool = True) -> str:
    boot = json.dumps(initial_state, ensure_ascii=False).replace("</", "<\\/")
    return f"""<!doctype html>
<html lang="he" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>PMMB — Command Center</title>
<style>
:root {{
  --bg:#090d13; --panel:#111722; --panel2:#161e2c; --border:#232e42;
  --text:#e8eef8; --muted:#8c9bb3; --dim:#5c6b82;
  --green:#22c55e; --red:#ef4444; --amber:#f59e0b; --blue:#3b82f6; --cyan:#06b6d4; --purple:#a855f7;
}}
* {{ box-sizing:border-box; }}
body {{
  margin:0; background:var(--bg); color:var(--text);
  font-family:system-ui,-apple-system,'Segoe UI',Rubik,Arial,sans-serif;
  line-height:1.45; font-size:14px;
}}
.topbar {{
  position:sticky; top:0; z-index:40;
  background:rgba(11,16,24,.94); border-bottom:1px solid var(--border);
  padding:12px 20px; display:flex; flex-wrap:wrap; align-items:center;
  justify-content:space-between; gap:12px;
}}
.brand {{ display:flex; align-items:center; gap:10px; }}
.dot {{ width:11px; height:11px; border-radius:50%; background:var(--green); }}
.dot.bad {{ background:var(--red); box-shadow:0 0 12px var(--red); }}
.dot.ok {{ background:var(--green); box-shadow:0 0 12px var(--green); }}
.badge {{
  font-size:11px; font-weight:700; padding:2px 8px; border-radius:999px;
  background:#1d283a; color:#93c5fd; border:1px solid #2b3a55;
}}
.badge.live {{ background:#3b1116; color:#fca5a5; border-color:#ef4444; }}
.badge.ok {{ background:#0f2d1e; color:#86efac; border-color:#16a34a; }}
.badge.warn {{ background:#332308; color:#fcd34d; border-color:#d97706; }}
.badge.bad {{ background:#3b1116; color:#fca5a5; border-color:#dc2626; }}
.actions {{ display:flex; flex-wrap:wrap; gap:8px; align-items:center; }}
button {{
  background:#1a2436; color:var(--text); border:1px solid #2d3c56;
  padding:7px 12px; border-radius:8px; cursor:pointer; font-size:12px; font-weight:600;
}}
button:hover {{ background:#223047; border-color:#42587d; }}
button.primary {{ background:#1d4ed8; border-color:#2563eb; }}
button.primary:hover {{ background:#1e40af; }}
button.danger {{ background:#7f1d1d; border-color:#dc2626; color:#fee2e2; }}
button.danger:hover {{ background:#991b1b; }}
button.success {{ background:#14532d; border-color:#16a34a; color:#dcfce7; }}
button:disabled {{ opacity:.5; cursor:not-allowed; }}
.nav {{
  display:flex; gap:6px; padding:10px 20px 0; border-bottom:1px solid var(--border);
  background:var(--panel); overflow-x:auto;
}}
.tab {{
  padding:10px 15px; border:none; border-bottom:2px solid transparent;
  background:transparent; color:var(--muted); border-radius:6px 6px 0 0; font-size:13px; white-space:nowrap;
}}
.tab.active {{ color:var(--text); border-bottom-color:var(--blue); background:var(--bg); }}
.wrap {{ max-width:1300px; margin:0 auto; padding:18px 20px 48px; }}
.grid {{ display:grid; gap:12px; }}
.g-kpi {{ grid-template-columns:repeat(auto-fit,minmax(145px,1fr)); margin-bottom:16px; }}
.g-2 {{ grid-template-columns:repeat(auto-fit,minmax(340px,1fr)); margin-bottom:16px; }}
.g-3 {{ grid-template-columns:repeat(auto-fit,minmax(260px,1fr)); margin-bottom:16px; }}
.card {{
  background:var(--panel); border:1px solid var(--border); border-radius:12px; padding:14px 16px;
}}
.kpi-title {{ color:var(--muted); font-size:12px; margin-bottom:4px; }}
.kpi-val {{ font-size:21px; font-weight:700; letter-spacing:-0.3px; }}
.kpi-sub {{ color:var(--dim); font-size:11px; margin-top:3px; }}
h2 {{ font-size:15px; color:var(--muted); margin:0 0 10px; font-weight:600; }}
table {{ width:100%; border-collapse:collapse; font-size:12.5px; }}
th {{ text-align:right; color:var(--dim); font-weight:600; padding:7px 8px; border-bottom:1px solid var(--border); }}
td {{ padding:8px; border-bottom:1px solid #1b2434; vertical-align:middle; }}
tr:hover td {{ background:rgba(255,255,255,.02); }}
.pos {{ color:var(--green); font-weight:600; }}
.neg {{ color:var(--red); font-weight:600; }}
.muted {{ color:var(--muted); }}
.dim {{ color:var(--dim); }}
.bar-bg {{ background:#1b2435; border-radius:6px; height:8px; overflow:hidden; flex:1; }}
.bar-fg {{ height:100%; border-radius:6px; background:var(--blue); }}
.banner {{
  padding:12px 15px; border-radius:10px; margin-bottom:14px; font-size:13px;
  display:flex; justify-content:space-between; align-items:center; gap:10px; flex-wrap:wrap;
}}
.banner.halt {{ background:#3b1116; border:1px solid var(--red); color:#fecaca; }}
.banner.warn {{ background:#2c1e07; border:1px solid var(--amber); color:#fde68a; }}
.banner.info {{ background:#0d2136; border:1px solid #1d4ed8; color:#bfdbfe; }}
.range-track {{ position:relative; width:96px; height:6px; background:#232f44; border-radius:4px; display:inline-block; }}
.range-pin {{ position:absolute; top:-3px; width:4px; height:12px; background:var(--cyan); border-radius:2px; }}
.check-item {{
  display:flex; justify-content:space-between; align-items:flex-start; gap:10px;
  padding:10px 12px; border:1px solid var(--border); border-radius:10px; background:var(--panel2);
}}
.search, select {{
  background:var(--panel2); color:var(--text); border:1px solid var(--border);
  border-radius:8px; padding:6px 10px; font-size:12px; max-width:100%;
}}
.news-item {{
  padding:10px 12px; border:1px solid var(--border); border-radius:10px;
  background:var(--panel2); margin-bottom:8px;
}}
.news-meta {{ display:flex; gap:8px; flex-wrap:wrap; align-items:center; font-size:11px; margin-top:4px; color:var(--muted); }}
.pill-row {{ display:flex; gap:10px; flex-wrap:wrap; font-size:12px; margin-bottom:10px; }}
.pill {{ background:var(--panel2); border:1px solid var(--border); border-radius:8px; padding:6px 10px; }}
pre {{
  background:#0a0f17; border:1px solid var(--border); border-radius:8px; padding:12px;
  overflow:auto; font-size:12px; color:#cbd5e1; white-space:pre-wrap; margin:0;
}}
.toast {{
  position:fixed; bottom:18px; left:18px; background:#1e293b; color:var(--text);
  border:1px solid var(--blue); border-radius:10px; padding:10px 14px; z-index:99;
  display:none; max-width:440px; font-size:12.5px; box-shadow:0 10px 30px rgba(0,0,0,.5);
}}
.hide {{ display:none !important; }}
.scroll-x {{ overflow-x:auto; }}
</style>
</head>
<body>
<div class="topbar">
  <div class="brand">
    <div id="h-dot" class="dot"></div>
    <div>
      <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
        <strong style="font-size:16px">PMMB Command Center</strong>
        <span id="b-mode" class="badge">PAPER</span>
        <span id="b-eng" class="badge">MEANREV</span>
        <span id="b-trader" class="badge">סוחר ידני</span>
      </div>
      <div id="h-sub" class="muted" style="font-size:12px">טוען נתונים...</div>
    </div>
  </div>
  <div class="actions" id="ctrl-bar">
    <button class="primary" onclick="act('api/paper-cycle', null, 'מריץ מחזור Paper...')">⚡ הרץ מחזור</button>
    <button id="btn-trader" class="success" onclick="toggleTrader()">▶️ מצב רציף 24/7</button>
    <button onclick="act('api/news-refresh', null, 'מושך חדשות וגרפים חיים...')">📰 רענן שידור חי</button>
    <button onclick="act('api/learn', null, 'מריץ מחזור למידה עצמית...')">🧠 למד והשתפר</button>
    <button id="btn-halt" class="danger" onclick="toggleHalt()">🛑 עצירת חירום</button>
    <button onclick="refreshNow()">🔄 רענן</button>
  </div>
</div>

<div class="nav">
  <button class="tab active" data-tab="overview" onclick="switchTab('overview')">📊 סקירה חיה</button>
  <button class="tab" data-tab="live" onclick="switchTab('live')">📈 גרפים וחדשות בשידור חי</button>
  <button class="tab" data-tab="learning" onclick="switchTab('learning')">🧠 למידה עצמית ואבולוציה</button>
  <button class="tab" data-tab="trading" onclick="switchTab('trading')">💼 פוזיציות, מילויים וסיגנלים</button>
  <button class="tab" data-tab="research" onclick="switchTab('research')">🔬 מחקר, Walk-Forward ומוכנות</button>
  <button class="tab" data-tab="ops" onclick="switchTab('ops')">⚙️ קונפיגורציה, גיבויים ותפעול</button>
</div>

<div class="wrap">
  <div id="banners"></div>

  <!-- 1. סקירה חיה -->
  <section id="tab-overview">
    <div id="kpi-grid" class="grid g-kpi"></div>
    <div id="stream-bar" class="pill-row"></div>
    <div class="grid g-2">
      <div class="card">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
          <h2 style="margin:0">עקומת הון</h2>
          <span id="eq-delta" class="dim" style="font-size:12px"></span>
        </div>
        <div id="eq-chart"></div>
      </div>
      <div class="card">
        <h2>מגיני סיכון חיים</h2>
        <div id="guards-box"></div>
      </div>
    </div>
    <div class="grid g-2">
      <div class="card">
        <h2>משפך החלטות (למה לא נסחר במחזור האחרון)</h2>
        <div id="skip-box"></div>
      </div>
      <div class="card">
        <h2>מוכנות למעבר ל-Live</h2>
        <div id="ready-mini"></div>
      </div>
    </div>
    <div class="grid g-2">
      <div class="card scroll-x">
        <h2>פוזיציות פתוחות כרגע</h2>
        <div id="ov-positions"></div>
      </div>
      <div class="card scroll-x">
        <h2>עסקאות סגורות אחרונות</h2>
        <div id="ov-trades"></div>
      </div>
    </div>
  </section>

  <!-- 2. גרפים וחדשות בשידור חי -->
  <section id="tab-live" class="hide">
    <div class="grid g-2">
      <div class="card">
        <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:10px">
          <h2 style="margin:0">גרף שוק בשידור חי (מחיר + SMA + רצועת Z + SL/TP)</h2>
          <div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap">
            <select id="chart-select" onchange="loadChart(false)"></select>
            <button id="btn-live-chart" class="primary" onclick="loadChart(true)">⚡ משוך חי</button>
          </div>
        </div>
        <div id="market-chart-meta" class="pill-row"></div>
        <div id="market-chart-svg"></div>
        <div id="market-chart-news" style="margin-top:10px"></div>
      </div>

      <div class="card">
        <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:10px">
          <h2 style="margin:0">פיד חדשות שווקים חיות + זיהוי קטליזטור ("סכין נופלת")</h2>
          <div style="display:flex;gap:6px;flex-wrap:wrap">
            <input id="news-q" class="search" placeholder="חפש כותרת, מקור או סקטור..." oninput="renderNews()">
            <button id="btn-news-refresh" onclick="act('api/news-refresh', null, 'מעדכן חדשות חיות...')">📰 משוך עכשיו</button>
          </div>
        </div>
        <div id="news-feed" style="max-height:540px;overflow:auto"></div>
      </div>
    </div>
  </section>

  <!-- 3. למידה עצמית ואבולוציה -->
  <section id="tab-learning" class="hide">
    <div class="card" style="margin-bottom:16px">
      <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px">
        <div>
          <h2 style="margin:0">מנוע למידה עצמית רציף (Live Signal Tracking + Walk-Forward Promotion)</h2>
          <div id="learn-headline" class="muted" style="font-size:13px;margin-top:4px"></div>
        </div>
        <button id="btn-learn-now" class="primary" onclick="act('api/learn', null, 'מריץ מחזור למידה ובדיקת Walk-Forward...')">🧠 הפעל מחזור למידה עכשיו</button>
      </div>
      <div id="learn-insights" style="margin-top:12px"></div>
    </div>

    <div class="grid g-2">
      <div class="card scroll-x">
        <h2>ביצועי אותות בזמן אמת (לאחר 24/48 שעות)</h2>
        <div id="live-outcomes-box"></div>
      </div>
      <div class="card scroll-x">
        <h2>היסטוריית ניסויי למידה ואבולוציית פרמטרים</h2>
        <div id="learn-runs-box"></div>
      </div>
    </div>
  </section>

  <!-- 4. פוזיציות, מילויים וסיגנלים -->
  <section id="tab-trading" class="hide">
    <div class="card scroll-x" style="margin-bottom:16px">
      <h2>פוזיציות פתוחות (כולל מרחק מ-SL ל-TP)</h2>
      <div id="tr-positions"></div>
    </div>
    <div class="card scroll-x" style="margin-bottom:16px">
      <div style="display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:10px">
        <h2 style="margin:0">יומן מילויים מלא (Fills Ledger)</h2>
        <input id="fill-q" class="search" placeholder="חפש שוק, BUY/SELL או סיבה..." oninput="renderFills()">
      </div>
      <div id="tr-fills"></div>
    </div>
    <div class="card scroll-x">
      <div style="display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:10px">
        <h2 style="margin:0">סיגנלים אחרונים שנמדדו בשווקים</h2>
        <input id="sig-q" class="search" placeholder="סנן לפי כיוון (BUY/HOLD) או הסבר..." oninput="renderSignals()">
      </div>
      <div id="tr-signals"></div>
    </div>
  </section>

  <!-- 5. מחקר ומוכנות -->
  <section id="tab-research" class="hide">
    <div class="card" style="margin-bottom:16px">
      <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;margin-bottom:10px">
        <h2 style="margin:0">שער המעבר ל-Live (9 בדיקות אוטומטיות)</h2>
        <span id="ready-badge" class="badge"></span>
      </div>
      <div id="ready-grid" class="grid g-3"></div>
    </div>
    <div class="grid g-2">
      <div class="card scroll-x">
        <h2>Walk-Forward Out-of-Sample</h2>
        <div id="wf-box"></div>
      </div>
      <div class="card scroll-x">
        <h2>פילוח ביצועים לפי סקטור</h2>
        <div id="sec-box"></div>
      </div>
    </div>
    <div class="grid g-2">
      <div class="card scroll-x">
        <h2>סימולציית תיק משותף אמיתי (Portfolio Backtest)</h2>
        <pre id="port-md"></pre>
      </div>
      <div class="card">
        <h2>מדריך נתוני Order-Book Imbalance</h2>
        <pre id="imb-md"></pre>
      </div>
    </div>
  </section>

  <!-- 6. קונפיגורציה, גיבויים ותפעול -->
  <section id="tab-ops" class="hide">
    <div class="grid g-2">
      <div class="card">
        <h2>פעולות תפעול ובקרה</h2>
        <div style="display:flex;flex-wrap:wrap;gap:8px;margin-bottom:12px" id="ops-btns">
          <button class="primary" onclick="act('api/paper-cycle', null, 'מריץ מחזור Paper...')">⚡ מחזור Paper</button>
          <button onclick="act('api/news-refresh', null, 'מושך חדשות וגרפים...')">📰 רענן חדשות וגרפים</button>
          <button onclick="act('api/learn', null, 'מריץ מחזור למידה עצמית...')">🧠 הרץ למידה עצמית</button>
          <button onclick="act('api/reconcile', null, 'בודק סנכרון חשבון...')">🔍 סנכרון (Reconcile)</button>
          <button onclick="act('api/backup', null, 'מגבה מסד נתונים...')">💾 גיבוי DB חם</button>
          <button class="danger" onclick="act('api/halt', {{reason:'עצירה ידנית מהתוכנה'}}, 'מפעיל עצירת חירום...')">🛑 הפעל Halt</button>
          <button class="success" onclick="act('api/resume', null, 'משחרר עצירה...')">▶️ בטל Halt</button>
        </div>
        <pre id="ops-out">מוכן לפקודות בקרה.</pre>
      </div>
      <div class="card scroll-x">
        <h2>גיבויי מסד נתונים (backups/)</h2>
        <div id="backups-box"></div>
      </div>
    </div>
    <div class="card" style="margin-bottom:16px">
      <h2>פרמטרים פעילים (Config)</h2>
      <div id="cfg-grid" class="grid g-3"></div>
    </div>
    <div class="grid g-2">
      <div class="card">
        <h2>יומן אירועי מערכת אחרונים</h2>
        <div id="events-box"></div>
      </div>
      <div class="card">
        <h2>מדריך פקודות CLI (26 פקודות)</h2>
        <pre>pmmb serve --autostart --port 8787  הרצה רציפה 24/7 + ממשק בקרה
pmmb paper --cycles 1               מחזור סימולציה מול ספר אמיתי
pmmb news --refresh                 משיכה והצגת חדשות שווקים חיות
pmmb learn                          מחזור למידה עצמית והשוואת OOS
pmmb scan --all                     סריקת שווקים וסיגנלים חיים
pmmb backtest --portfolio           סימולציית תיק משותף אמיתי
pmmb walkforward --markets 32       אימות מחוץ למדגם (OOS)
pmmb readiness                      בדיקת מוכנות ל-live
pmmb reconcile --fix                סנכרון ותיקון DB מול חשבון
pmmb backup                         גיבוי SQLite חם ומאומת
pmmb status --html-out out.html     ייצוא ממשק עצמאי לקובץ</pre>
      </div>
    </div>
  </section>
</div>

<div id="toast" class="toast"></div>
<script id="pmmb-boot" type="application/json">{boot}</script>
<script>
const INTERACTIVE = {str(interactive).lower()};
let S = JSON.parse(document.getElementById('pmmb-boot').textContent);
let ACTIVE_TAB = 'overview';
let CURRENT_CHART = (S.charts && S.charts.default) || null;

function esc(v) {{
  return String(v ?? '').replace(/[&<>"']/g, c => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));
}}
function fmtTime(ts) {{
  if (!ts) return '—';
  const d = new Date(ts * 1000);
  const p = n => String(n).padStart(2, '0');
  return `${{p(d.getUTCDate())}}/${{p(d.getUTCMonth()+1)}} ${{p(d.getUTCHours())}}:${{p(d.getUTCMinutes())}}`;
}}
function tokenHeader() {{
  const u = new URLSearchParams(location.search);
  const t = u.get('token') || '';
  return t ? {{'X-Token': t}} : {{}};
}}
function toast(msg, ok=true) {{
  const el = document.getElementById('toast');
  el.style.borderColor = ok ? '#22c55e' : '#ef4444';
  el.textContent = msg;
  el.style.display = 'block';
  setTimeout(() => {{ el.style.display = 'none'; }}, 4500);
}}
function switchTab(name) {{
  ACTIVE_TAB = name;
  document.querySelectorAll('.tab').forEach(b => b.classList.toggle('active', b.dataset.tab === name));
  ['overview','live','learning','trading','research','ops'].forEach(t => {{
    document.getElementById('tab-' + t).classList.toggle('hide', t !== name);
  }});
  if (name === 'live' && !CURRENT_CHART) {{
    loadChart(false);
  }}
}}

function renderChart(pts) {{
  const vals = (pts || []).map(p => Number(p.equity)).filter(v => Number.isFinite(v));
  const box = document.getElementById('eq-chart');
  const dEl = document.getElementById('eq-delta');
  if (vals.length < 2) {{
    dEl.textContent = '';
    box.innerHTML = '<div class="dim">צריך לפחות 2 נקודות מדידה כדי לצייר גרף הון</div>';
    return;
  }}
  const w = 520, h = 140, pad = 16;
  const lo = Math.min(...vals), hi = Math.max(...vals);
  const span = (hi - lo) || 1;
  const step = (w - 2 * pad) / (vals.length - 1);
  const coords = vals.map((v, i) => [
    (pad + i * step).toFixed(1),
    (h - pad - ((v - lo) / span) * (h - 2 * pad)).toFixed(1)
  ]);
  const line = coords.map(c => c.join(',')).join(' ');
  const area = `${{pad}},${{h-pad}} ${{line}} ${{(w-pad).toFixed(1)}},${{h-pad}}`;
  const delta = vals[vals.length - 1] - vals[0];
  const col = delta >= 0 ? '#22c55e' : '#ef4444';
  dEl.innerHTML = `<span class="${{delta>=0?'pos':'neg'}}">${{vals[0].toFixed(2)}} → ${{vals[vals.length-1].toFixed(2)}} (${{delta>=0?'+':''}}${{delta.toFixed(2)}})</span>`;
  box.innerHTML = `<svg viewBox="0 0 ${{w}} ${{h}}" width="100%" height="145" style="display:block">
    <defs><linearGradient id="eqg" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="${{col}}" stop-opacity="0.32"/>
      <stop offset="100%" stop-color="${{col}}" stop-opacity="0.0"/>
    </linearGradient></defs>
    <line x1="${{pad}}" y1="${{pad}}" x2="${{w-pad}}" y2="${{pad}}" stroke="#1e293b" stroke-dasharray="3,3"/>
    <line x1="${{pad}}" y1="${{h-pad}}" x2="${{w-pad}}" y2="${{h-pad}}" stroke="#1e293b" stroke-dasharray="3,3"/>
    <polygon points="${{area}}" fill="url(#eqg)"/>
    <polyline points="${{line}}" fill="none" stroke="${{col}}" stroke-width="2.4" stroke-linejoin="round" stroke-linecap="round"/>
    <text x="${{w-pad}}" y="${{pad-4}}" fill="#64748b" font-size="10" text-anchor="end">שיא ${{hi.toFixed(2)}}</text>
    <text x="${{w-pad}}" y="${{h-3}}" fill="#64748b" font-size="10" text-anchor="end">שפל ${{lo.toFixed(2)}}</text>
  </svg>`;
}}

function renderMarketChart(chart) {{
  const svgBox = document.getElementById('market-chart-svg');
  const metaBox = document.getElementById('market-chart-meta');
  const newsBox = document.getElementById('market-chart-news');
  if (!chart || !chart.ticks || chart.ticks.length < 2) {{
    metaBox.innerHTML = '';
    svgBox.innerHTML = '<div class="dim" style="padding:18px 0">אין מספיק נקודות מחיר לטוקן זה עדיין — משוך גרף חי או הרץ מחזור סריקה.</div>';
    newsBox.innerHTML = '';
    return;
  }}

  const ticks = chart.ticks;
  const prices = ticks.map(t => Number(t.price));
  const sma = chart.sma || [];
  const band = chart.lower_band || [];
  const pos = chart.position;
  const lastBk = (chart.books && chart.books.length) ? chart.books[chart.books.length - 1] : null;
  const allVals = [...prices];
  if (pos && pos.stop_price != null) allVals.push(Number(pos.stop_price));
  if (pos && pos.target_price != null) allVals.push(Number(pos.target_price));
  sma.forEach(v => {{ if (v != null) allVals.push(Number(v)); }});
  band.forEach(v => {{ if (v != null) allVals.push(Number(v)); }});

  const lo = Math.min(...allVals) * 0.99, hi = Math.max(...allVals) * 1.01;
  const span = (hi - lo) || 0.01;
  const w = 620, h = 230, pad = 22;
  const xAt = i => pad + (i / Math.max(ticks.length - 1, 1)) * (w - 2 * pad);
  const yAt = v => h - pad - ((v - lo) / span) * (h - 2 * pad);

  const pxLine = prices.map((v, i) => `${{xAt(i).toFixed(1)}},${{yAt(v).toFixed(1)}}`).join(' ');
  const smaPts = sma.map((v, i) => v == null ? null : `${{xAt(i).toFixed(1)}},${{yAt(v).toFixed(1)}}`).filter(Boolean).join(' ');
  const bandPts = band.map((v, i) => v == null ? null : `${{xAt(i).toFixed(1)}},${{yAt(v).toFixed(1)}}`).filter(Boolean).join(' ');

  let posLines = '';
  if (pos) {{
    if (pos.target_price != null) {{
      const y = yAt(Number(pos.target_price)).toFixed(1);
      posLines += `<line x1="${{pad}}" y1="${{y}}" x2="${{w-pad}}" y2="${{y}}" stroke="#22c55e" stroke-dasharray="4,3" stroke-width="1.2"/>
        <text x="${{pad+4}}" y="${{Number(y)-4}}" fill="#22c55e" font-size="10">TP ${{Number(pos.target_price).toFixed(3)}}</text>`;
    }}
    if (pos.stop_price != null) {{
      const y = yAt(Number(pos.stop_price)).toFixed(1);
      posLines += `<line x1="${{pad}}" y1="${{y}}" x2="${{w-pad}}" y2="${{y}}" stroke="#ef4444" stroke-dasharray="4,3" stroke-width="1.2"/>
        <text x="${{pad+4}}" y="${{Number(y)+11}}" fill="#ef4444" font-size="10">SL ${{Number(pos.stop_price).toFixed(3)}}</text>`;
    }}
    if (pos.avg_price != null) {{
      const y = yAt(Number(pos.avg_price)).toFixed(1);
      posLines += `<line x1="${{pad}}" y1="${{y}}" x2="${{w-pad}}" y2="${{y}}" stroke="#94a3b8" stroke-dasharray="2,3" stroke-width="1"/>`;
    }}
  }}

  const lastPx = prices[prices.length - 1];
  const pills = [
    `<div class="pill">מחיר אחרון: <strong>${{lastPx.toFixed(3)}}</strong></div>`,
    `<div class="pill">נקודות: <strong>${{ticks.length}}</strong></div>`,
  ];
  if (lastBk) {{
    const sp = (lastBk.best_ask != null && lastBk.best_bid != null) ? (lastBk.best_ask - lastBk.best_bid).toFixed(3) : '—';
    pills.push(`<div class="pill">Bid/Ask: <strong>${{lastBk.best_bid ?? '—'}} / ${{lastBk.best_ask ?? '—'}}</strong> (ספרד ${{sp}})</div>`);
    pills.push(`<div class="pill">Imbalance: <strong>${{lastBk.imbalance != null ? Number(lastBk.imbalance).toFixed(2) : '—'}}</strong></div>`);
  }}
  metaBox.innerHTML = pills.join('');

  svgBox.innerHTML = `<svg viewBox="0 0 ${{w}} ${{h}}" width="100%" height="235" style="display:block;background:#0b1018;border-radius:10px;border:1px solid #1e293b">
    <line x1="${{pad}}" y1="${{pad}}" x2="${{w-pad}}" y2="${{pad}}" stroke="#1a2232" stroke-dasharray="3,3"/>
    <line x1="${{pad}}" y1="${{h-pad}}" x2="${{w-pad}}" y2="${{h-pad}}" stroke="#1a2232" stroke-dasharray="3,3"/>
    ${{posLines}}
    ${{bandPts ? `<polyline points="${{bandPts}}" fill="none" stroke="#a855f7" stroke-width="1.2" stroke-dasharray="3,3" opacity="0.8"/>` : ''}}
    ${{smaPts ? `<polyline points="${{smaPts}}" fill="none" stroke="#f59e0b" stroke-width="1.4" stroke-dasharray="5,3" opacity="0.9"/>` : ''}}
    <polyline points="${{pxLine}}" fill="none" stroke="#38bdf8" stroke-width="2.2" stroke-linejoin="round" stroke-linecap="round"/>
    <circle cx="${{xAt(prices.length-1).toFixed(1)}}" cy="${{yAt(lastPx).toFixed(1)}}" r="3.5" fill="#38bdf8"/>
    <text x="${{w-pad}}" y="${{pad-5}}" fill="#64748b" font-size="10" text-anchor="end">${{hi.toFixed(3)}}</text>
    <text x="${{w-pad}}" y="${{h-5}}" fill="#64748b" font-size="10" text-anchor="end">${{lo.toFixed(3)}}</text>
    <text x="${{pad}}" y="${{h-5}}" fill="#64748b" font-size="10">${{fmtTime(ticks[0].ts)}} → ${{fmtTime(ticks[ticks.length-1].ts)}}</text>
  </svg>
  <div class="dim" style="font-size:11px;margin-top:6px">
    <span style="color:#38bdf8">━ מחיר שוק</span> ·
    <span style="color:#f59e0b">┈ ממוצע נע (SMA)</span> ·
    <span style="color:#a855f7">┈ רצועת קנייה Z</span> ·
    <span style="color:#22c55e">┈ יעד TP</span> ·
    <span style="color:#ef4444">┈ סטופ SL</span>
  </div>`;

  const mNews = chart.matched_news || [];
  newsBox.innerHTML = mNews.length ?
    `<div class="news-item"><strong>📰 כתבות הקשורות לשוק זה:</strong><ul style="margin:6px 0 0;padding-inline-start:18px;font-size:12px">` +
    mNews.map(t => `<li>${{esc(t)}}</li>`).join('') + `</ul></div>` : '';
}}

async function loadChart(liveFlag) {{
  const sel = document.getElementById('chart-select');
  const tid = sel ? sel.value : '';
  if (!tid) {{ renderMarketChart(CURRENT_CHART); return; }}
  if (!INTERACTIVE) {{
    if (CURRENT_CHART && CURRENT_CHART.token_id === tid) renderMarketChart(CURRENT_CHART);
    return;
  }}
  try {{
    const r = await fetch(`api/chart?token=${{encodeURIComponent(tid)}}&live=${{liveFlag ? 1 : 0}}`, {{headers: tokenHeader()}});
    if (!r.ok) throw new Error('HTTP ' + r.status);
    CURRENT_CHART = await r.json();
    renderMarketChart(CURRENT_CHART);
  }} catch (e) {{
    toast('טעינת גרף נכשלה: ' + e.message, false);
  }}
}}

function renderNews() {{
  const q = (document.getElementById('news-q')?.value || '').toLowerCase();
  const list = (S.news || []).filter(n => !q ||
    (n.title + ' ' + n.source + ' ' + n.category).toLowerCase().includes(q));
  const box = document.getElementById('news-feed');
  if (!list.length) {{
    box.innerHTML = '<div class="dim">אין כתבות חדשות שמורות כרגע — לחץ "משוך עכשיו" או הרץ מחזור.</div>';
    return;
  }}
  box.innerHTML = list.map(n => {{
    const imp = Number(n.impact || 0);
    const sent = Number(n.sentiment || 0);
    const sBadge = sent > 0.15 ? '<span class="badge ok">חיובי</span>' :
                   (sent < -0.15 ? '<span class="badge bad">שלילי</span>' : '<span class="badge">ניטרלי</span>');
    const cBadge = imp >= 0.65 ? '<span class="badge warn">🔥 קטליזטור חזק</span>' : '';
    const mTok = n.matched_tokens ? `<span class="badge ok">מקושר לשוק פעיל</span>` : '';
    return `<div class="news-item">
      <div style="font-weight:600;font-size:13px">${{esc(n.title)}}</div>
      <div class="news-meta">
        <span>${{fmtTime(n.ts)}}</span>
        <span>${{esc(n.source || 'RSS')}}</span>
        <span class="badge">${{esc(n.category || 'macro')}}</span>
        ${{sBadge}} ${{cBadge}} ${{mTok}}
        <span>השפעה: ${{imp.toFixed(2)}}</span>
      </div>
    </div>`;
  }}).join('');
}}

function renderLearning() {{
  const lr = S.learning || {{}};
  const runs = lr.runs || [];
  const stats = lr.stats || {{}};
  const last = runs[0];
  document.getElementById('learn-headline').textContent = last ?
    `מחזור אחרון (${{fmtTime(last.ts)}}): ${{last.summary}}` :
    'המערכת אוספת אותות בזמן אמת ותתחיל לכייל Walk-Forward ברגע שיצטברו נתונים.';

  const insights = lr.insights || [];
  document.getElementById('learn-insights').innerHTML = insights.length ?
    `<div class="pill-row">` + insights.map(x => `<div class="pill">💡 ${{esc(x)}}</div>`).join('') + `</div>` :
    '<div class="dim" style="font-size:12px">עדיין נצברים אותות לסטטיסטיקה מובהקת (מינימום 12 אותות חיים בעלי היסטוריית 24/48 שעות).</div>';

  // Live signal outcomes
  const outRows = [];
  const act = stats.actionable;
  if (act && act.n) outRows.push(['כל האותות הפעילים', act]);
  Object.entries(stats.by_z_bucket || {{}}).forEach(([k, v]) => outRows.push([`עומק z=${{k}}`, v]));
  Object.entries(stats.by_sector || {{}}).forEach(([k, v]) => outRows.push([`סקטור: ${{k}}`, v]));
  const bn = stats.by_news || {{}};
  if (bn.quiet && bn.quiet.n) outRows.push(['שוק שקט (ללא חדשות)', bn.quiet]);
  if (bn.news_catalyst && bn.news_catalyst.n) outRows.push(['גל חדשות (Catalyst)', bn.news_catalyst]);

  document.getElementById('live-outcomes-box').innerHTML = outRows.length ? `<table>
    <tr><th>פלח</th><th>n</th><th>Hit 24ש'</th><th>Hit 48ש'</th><th>Hit (מצטבר)</th><th>ממוצע (מצטבר)</th></tr>` +
    outRows.map(([lbl, r]) => `<tr>
      <td>${{esc(lbl)}}</td><td>${{r.n}}</td>
      <td>${{r.hit_24h_pct != null ? `${{r.hit_24h_pct}}% (${{r.n_24h}})` : '—'}}</td>
      <td>${{r.hit_48h_pct != null ? `${{r.hit_48h_pct}}% (${{r.n_48h}})` : '—'}}</td>
      <td>${{r.hit_latest_pct != null ? r.hit_latest_pct + '%' : '—'}}</td>
      <td class="${{(r.mean_latest||0)>=0?'pos':'neg'}}">${{r.mean_latest != null ? (r.mean_latest>=0?'+':'')+r.mean_latest.toFixed(4) : '—'}}</td>
    </tr>`).join('') + '</table>' :
    '<div class="dim">ממתין לאותות בני 6-48 שעות כדי למדוד הצלחה בפועל מול השוק.</div>';

  document.getElementById('learn-runs-box').innerHTML = runs.length ? `<table>
    <tr><th>זמן</th><th>Baseline OOS</th><th>מועמד OOS</th><th>עקביות</th><th>יושם</th><th>סיכום</th></tr>` +
    runs.map(r => `<tr>
      <td class="dim">${{fmtTime(r.ts)}}</td>
      <td>${{Number(r.baseline_oos||0).toFixed(2)}}</td>
      <td class="${{(r.candidate_oos||0)>(r.baseline_oos||0)?'pos':'muted'}}">${{Number(r.candidate_oos||0).toFixed(2)}}</td>
      <td>${{Math.round((r.consistency||0)*100)}}%</td>
      <td>${{r.applied ? '<span class="badge ok">קודם ✅</span>' : '<span class="badge">נשמר 🛡️</span>'}}</td>
      <td class="muted">${{esc(r.summary)}}</td>
    </tr>`).join('') + '</table>' : '<div class="dim">עדיין לא הורץ מחזור למידה. לחץ "הפעל מחזור למידה עכשיו".</div>';
}}

function posTable(list, detailed) {{
  if (!list || !list.length) return '<div class="dim" style="padding:8px">אין פוזיציות פתוחות כרגע</div>';
  return `<table><tr>
    <th>שוק</th><th>כיוון</th><th>גודל</th><th>כניסה</th><th>נוכחי</th><th>לא ממומש</th>
    ${{detailed ? '<th>SL / TP</th><th>מרחק ליעד</th>' : ''}}<th>גיל</th></tr>` +
    list.map(p => {{
      const unr = p.unrealized_pnl;
      const cls = unr == null ? '' : (unr >= 0 ? 'pos' : 'neg');
      const unrTxt = unr == null ? '—' : `${{unr>=0?'+':''}}${{unr.toFixed(2)}} (${{p.unrealized_pct>=0?'+':''}}${{p.unrealized_pct.toFixed(1)}}%)`;
      let bar = '—';
      if (detailed && p.stop_price != null && p.target_price != null && p.mark_price != null && p.target_price > p.stop_price) {{
        const pct = Math.max(0, Math.min(100, (p.mark_price - p.stop_price) / (p.target_price - p.stop_price) * 100));
        bar = `<div class="range-track"><div class="range-pin" style="left:${{pct.toFixed(0)}}%"></div></div>`;
      }}
      return `<tr>
        <td>${{esc(p.question)}}</td>
        <td><span class="badge">${{esc(p.direction)}}</span></td>
        <td>${{Number(p.size).toFixed(1)}}</td>
        <td>${{Number(p.avg_price).toFixed(3)}}</td>
        <td>${{p.mark_price != null ? Number(p.mark_price).toFixed(3) : '—'}}</td>
        <td class="${{cls}}">${{unrTxt}}</td>
        ${{detailed ? `<td class="muted">${{p.stop_price ?? '—'}} / ${{p.target_price ?? '—'}}</td><td>${{bar}}</td>` : ''}}
        <td class="muted">${{Number(p.age_hours).toFixed(1)}}ש'</td>
      </tr>`;
    }}).join('') + '</table>';
}}

function renderFills() {{
  const q = (document.getElementById('fill-q')?.value || '').toLowerCase();
  const list = (S.fills || []).filter(f => !q ||
    (f.question + ' ' + f.side + ' ' + f.reason).toLowerCase().includes(q));
  const box = document.getElementById('tr-fills');
  if (!list.length) {{ box.innerHTML = '<div class="dim">אין מילויים תואמים</div>'; return; }}
  box.innerHTML = `<table><tr><th>זמן</th><th>פעולה</th><th>שוק</th><th>כמות</th><th>מחיר</th><th>שווי</th><th>עמלה</th><th>PnL ממומש</th><th>סיבה</th></tr>` +
    list.map(f => `<tr>
      <td class="dim">${{fmtTime(f.ts)}}</td>
      <td><span class="badge ${{f.side==='BUY'?'ok':'warn'}}">${{f.side}}</span></td>
      <td>${{esc(f.question)}}</td>
      <td>${{f.size.toFixed(2)}}</td>
      <td>${{f.price.toFixed(3)}}</td>
      <td>$${{f.notional.toFixed(2)}}</td>
      <td class="muted">$${{f.fee.toFixed(3)}}</td>
      <td class="${{f.realized > 0 ? 'pos' : (f.realized < 0 ? 'neg' : 'muted')}}">${{f.side==='SELL' ? (f.realized>=0?'+':'')+f.realized.toFixed(2) : '—'}}</td>
      <td class="muted">${{esc(f.reason)}}</td>
    </tr>`).join('') + '</table>';
}}

function renderSignals() {{
  const q = (document.getElementById('sig-q')?.value || '').toLowerCase();
  const list = (S.signals || []).filter(g => !q ||
    (g.direction + ' ' + g.reason + ' ' + g.question).toLowerCase().includes(q));
  const box = document.getElementById('tr-signals');
  if (!list.length) {{ box.innerHTML = '<div class="dim">אין סיגנלים תואמים</div>'; return; }}
  box.innerHTML = `<table><tr><th>זמן</th><th>שוק / טוקן</th><th>כיוון</th><th>z</th><th>score</th><th>שוק→הוגן</th><th>edge</th><th>הסבר</th></tr>` +
    list.map(g => `<tr>
      <td class="dim">${{fmtTime(g.ts)}}</td>
      <td>${{esc(g.question || g.token_id)}}</td>
      <td><span class="badge ${{(g.direction==='BUY'||g.direction==='LONG')?'ok':''}}">${{esc(g.direction)}}</span></td>
      <td>${{g.z != null ? g.z.toFixed(2) : '—'}}</td>
      <td>${{g.score.toFixed(2)}}</td>
      <td>${{g.market_price.toFixed(3)}} → ${{g.fair_price.toFixed(3)}}</td>
      <td class="${{g.edge>0?'pos':'muted'}}">${{(g.edge>=0?'+':'')+g.edge.toFixed(4)}}</td>
      <td class="muted">${{esc(g.reason)}}</td>
    </tr>`).join('') + '</table>';
}}

function render() {{
  const h = S.health || {{}}, hb = S.heartbeat || {{}}, bank = S.bankroll || {{}};
  const today = S.today || {{}}, ov = S.overall || {{}}, soak = S.soak || {{}};
  const trader = S.trader || {{}}, tel = S.telemetry || {{}};
  const ok = Boolean(h.healthy);
  document.getElementById('h-dot').className = 'dot ' + (ok ? 'ok' : 'bad');
  const mEl = document.getElementById('b-mode');
  mEl.textContent = String(S.mode || 'paper').toUpperCase();
  mEl.className = 'badge ' + (S.mode === 'live' ? 'live' : 'ok');
  document.getElementById('b-eng').textContent = String(S.engine || '').toUpperCase();
  const tEl = document.getElementById('b-trader');
  tEl.textContent = trader.running ? `רץ ללא הפסקה (#${{trader.cycles || 0}})` : 'סוחר ידני';
  tEl.className = 'badge ' + (trader.running ? 'ok' : '');
  const ageTxt = hb.age_sec != null ? `${{Math.round(hb.age_sec)}}שנ'` : '—';
  document.getElementById('h-sub').textContent = `${{h.reason || ''}} · מחזור #${{hb.cycle || 0}} · דופק לפני ${{ageTxt}}`;

  document.getElementById('ctrl-bar').classList.toggle('hide', !INTERACTIVE);
  ['btn-live-chart','btn-news-refresh','btn-learn-now'].forEach(id => {{
    const el = document.getElementById(id);
    if (el) el.classList.toggle('hide', !INTERACTIVE);
  }});
  const opsBtns = document.getElementById('ops-btns');
  if (opsBtns && !INTERACTIVE) {{
    opsBtns.classList.add('hide');
    const opsOut = document.getElementById('ops-out');
    if (opsOut) opsOut.textContent = 'תצוגת Snapshot סטטית. להרצה רציפה 24/7 בזמן אמת הפעילו: pmmb serve --autostart --port 8787';
  }}
  const btTrader = document.getElementById('btn-trader');
  if (btTrader) {{
    btTrader.textContent = trader.running ? '⏹ עצור ריצה רציפה' : '▶️ מצב רציף 24/7';
    btTrader.disabled = S.mode === 'live';
  }}
  const btHalt = document.getElementById('btn-halt');
  if (btHalt) {{
    const halted = Boolean(S.halt || (hb && hb.halted));
    btHalt.textContent = halted ? '▶️ שחרר עצירה' : '🛑 עצירת חירום';
    btHalt.className = halted ? 'success' : 'danger';
  }}

  // Banners
  const banners = [];
  if (S.halt || (hb && hb.halted)) {{
    const r = (S.halt && S.halt.reason) || (hb && hb.halt_reason) || 'עצירת חירום פעילה';
    banners.push(`<div class="banner halt"><div>🛑 <strong>הבוט עצור:</strong> ${{esc(r)}}</div>
      ${{INTERACTIVE ? '<button class="success" onclick="act(\\'api/resume\\', null, \\'מבטל עצירה...\\')">▶️ שחרר עצירה</button>' : ''}}</div>`);
  }} else if (!ok) {{
    banners.push(`<div class="banner warn"><div>⚠️ <strong>${{esc(h.reason || 'אין דופק טרי')}}</strong></div>
      ${{INTERACTIVE && S.mode==='paper' ? '<button class="primary" onclick="act(\\'api/paper-cycle\\', null, \\'מריץ מחזור...\\')">⚡ הרץ מחזור עכשיו</button>' : ''}}</div>`);
  }}
  document.getElementById('banners').innerHTML = banners.join('');

  // KPIs
  const eq = Number(bank.equity || 0), cash = Number(bank.cash || 0), exp = Number(bank.exposure || 0);
  const unr = Number(bank.unrealized_pnl || 0);
  const ovPnl = Number(ov.realized_pnl || 0), tPnl = Number(today.realized_pnl || 0);
  const kpis = [
    ['הון תיק', `$${{eq.toFixed(2)}}`, `לא ממומש ${{unr>=0?'+':''}}${{unr.toFixed(2)}}`],
    ['מזומן פנוי', `$${{cash.toFixed(2)}}`, `${{eq>0 ? (cash/eq*100).toFixed(0) : 0}}% נזיל`],
    ['חשיפה בשוק', `$${{exp.toFixed(2)}}`, `${{eq>0 ? (exp/eq*100).toFixed(1) : 0}}% מהתיק`],
    ['פוזיציות', `${{bank.open_positions ?? 0}} / ${{(S.config?.risk?.max_open_positions) || 5}}`, 'פתוחות כרגע'],
    ['PnL היום', `${{tPnl>=0?'+':''}}${{tPnl.toFixed(2)}}`, `${{today.exits || 0}} יציאות · $${{Number(today.fees||0).toFixed(2)}} עמלה`],
    ['PnL מצטבר', `${{ovPnl>=0?'+':''}}${{ovPnl.toFixed(2)}}`, `${{ov.exits || 0}} סגורות · ${{ov.win_rate_pct || 0}}% · PF ${{ov.profit_factor ?? '—'}}`],
    ['עמלות סה"כ', `$${{Number(ov.fees || today.fees || 0).toFixed(2)}}`, 'מודל Polymarket'],
    ['שבוע Paper', `${{soak.days || 0}} / ${{soak.target_days || 7}}`, (soak.days||0)>=(soak.target_days||7) ? 'עבר שער ימים' : 'צובר ימי ניסיון'],
  ];
  document.getElementById('kpi-grid').innerHTML = kpis.map(([t,v,s]) =>
    `<div class="card"><div class="kpi-title">${{t}}</div><div class="kpi-val">${{v}}</div><div class="kpi-sub">${{s}}</div></div>`
  ).join('');

  // Telemetry & live streams bar
  document.getElementById('stream-bar').innerHTML = [
    `<div class="pill">📈 טיקים בגרפים: <strong>${{(tel.ticks || 0).toLocaleString()}}</strong></div>`,
    `<div class="pill">📚 ספר פקודות: <strong>${{(tel.books || 0).toLocaleString()}}</strong></div>`,
    `<div class="pill">📰 כתבות חדשות: <strong>${{tel.news || 0}}</strong> (${{trader.last_news_ts ? fmtTime(trader.last_news_ts) : 'פעיל'}})</div>`,
    `<div class="pill">🧠 מחזורי למידה: <strong>${{(S.learning?.runs || []).length}}</strong></div>`,
    `<div class="pill">🔄 מחזורי מסחר: <strong>${{trader.cycles || hb.cycle || 0}}</strong></div>`,
  ].join('');

  renderChart(S.equity_curve);

  // Risk Guards
  const g = S.guards || {{}};
  const dLim = Number(g.daily_loss_limit || 50), dUsed = Number(g.daily_loss_used || 0);
  const dd = Number(g.drawdown_pct || 0), ddLim = Number(g.drawdown_limit_pct || 20);
  const maxExp = eq * Number(S.config?.risk?.max_total_exposure_pct || 0.4);
  const maxPos = Number(S.config?.risk?.max_open_positions || 5);
  const bars = [
    ['הפסד יומי', `$${{dUsed.toFixed(2)}} / $${{dLim.toFixed(2)}}`, dLim > 0 ? dUsed/dLim*100 : 0, '#f59e0b'],
    ['Drawdown', `${{dd.toFixed(2)}}% / ${{ddLim.toFixed(0)}}%`, ddLim > 0 ? dd/ddLim*100 : 0, '#ef4444'],
    ['חשיפה מנוצלת', `$${{exp.toFixed(1)}} / $${{maxExp.toFixed(0)}}`, maxExp > 0 ? exp/maxExp*100 : 0, '#3b82f6'],
    ['תפוסת פוזיציות', `${{bank.open_positions || 0}} / ${{maxPos}}`, maxPos > 0 ? (bank.open_positions||0)/maxPos*100 : 0, '#22c55e'],
  ];
  document.getElementById('guards-box').innerHTML = bars.map(([lbl,txt,pct,col]) => `
    <div style="margin-bottom:11px">
      <div style="display:flex;justify-content:space-between;font-size:12px;margin-bottom:4px">
        <span class="muted">${{lbl}}</span><span>${{txt}}</span>
      </div>
      <div class="bar-bg"><div class="bar-fg" style="width:${{Math.min(100,Math.max(0,pct)).toFixed(0)}}%;background:${{col}}"></div></div>
    </div>`).join('');

  // Skipped
  const sk = S.skipped || {{}};
  const skTot = Object.values(sk).reduce((a,b) => a+b, 0) || 1;
  document.getElementById('skip-box').innerHTML = Object.entries(sk).sort((a,b)=>b[1]-a[1]).map(([k,v]) => `
    <div style="display:flex;align-items:center;gap:8px;margin:6px 0">
      <div class="muted" style="flex:0 0 185px;font-size:12px">${{esc(k)}}</div>
      <div class="bar-bg"><div class="bar-fg" style="width:${{(v/skTot*100).toFixed(0)}}%"></div></div>
      <div class="dim" style="flex:0 0 28px;text-align:left;font-size:11px">${{v}}</div>
    </div>`).join('') || '<div class="dim">אין דחיות מהמחזור האחרון</div>';

  // Readiness mini + full
  const rd = S.readiness || {{checks:[]}};
  const icon = {{ok:'✅', warn:'⚠️', fail:'❌'}};
  document.getElementById('ready-mini').innerHTML = (rd.checks || []).map(c => `
    <div style="display:flex;justify-content:space-between;gap:8px;padding:4px 0;border-bottom:1px solid #1b2434;font-size:12px">
      <span>${{icon[c.status] || '•'}} ${{esc(c.label)}}</span>
      <span class="muted">${{esc(c.detail)}}</span>
    </div>`).join('');

  const rBadge = document.getElementById('ready-badge');
  rBadge.textContent = rd.ready ? 'מוכן למעבר ל-LIVE' : (rd.summary || 'בתהליך אימות');
  rBadge.className = 'badge ' + (rd.ready ? 'ok' : 'warn');
  document.getElementById('ready-grid').innerHTML = (rd.checks || []).map(c => `
    <div class="check-item">
      <div><strong>${{icon[c.status] || ''}} ${{esc(c.label)}}</strong>
      <div class="muted" style="font-size:12px;margin-top:3px">${{esc(c.detail)}}</div></div>
    </div>`).join('');

  // Overview + Trading tables
  document.getElementById('ov-positions').innerHTML = posTable(S.positions, false);
  document.getElementById('tr-positions').innerHTML = posTable(S.positions, true);
  document.getElementById('ov-trades').innerHTML = (S.recent_trades && S.recent_trades.length) ?
    `<table><tr><th>שוק</th><th>יציאה</th><th>PnL</th><th>סיבה</th></tr>` +
    S.recent_trades.map(t => `<tr>
      <td>${{esc(t.question)}}</td><td>${{Number(t.price).toFixed(3)}}</td>
      <td class="${{t.realized>=0?'pos':'neg'}}">${{t.realized>=0?'+':''}}${{Number(t.realized).toFixed(2)}}</td>
      <td class="muted">${{esc(t.reason)}}</td></tr>`).join('') + '</table>' :
    '<div class="dim">אין עסקאות סגורות עדיין</div>';
  renderFills();
  renderSignals();

  // Chart selector + News + Learning
  const sel = document.getElementById('chart-select');
  const cands = (S.charts && S.charts.candidates) || [];
  if (sel) {{
    const prev = sel.value;
    sel.innerHTML = cands.map(c => `<option value="${{esc(c.token_id)}}">${{c.open ? '🟢 ' : ''}}${{esc(c.question.slice(0, 56))}}</option>`).join('');
    if (prev && cands.some(c => c.token_id === prev)) sel.value = prev;
  }}
  if (!CURRENT_CHART && S.charts && S.charts.default) CURRENT_CHART = S.charts.default;
  renderMarketChart(CURRENT_CHART);
  renderNews();
  renderLearning();

  // Analytics
  const an = S.analytics || {{}};
  const wf = an.walkforward;
  document.getElementById('wf-box').innerHTML = wf ? `
    <div style="margin-bottom:10px;font-size:13px">
      OOS סה"כ: <strong class="${{wf.oos_pnl>=0?'pos':'neg'}}">${{wf.oos_pnl>=0?'+':''}}${{wf.oos_pnl}} USDC</strong>
      · ללא מוביל: <strong>${{wf.oos_pnl_ex_top ?? '—'}}</strong>
      · עקביות: <strong>${{Math.round((wf.consistency||0)*100)}}%</strong>
      · מצב סטופ: <span class="badge">${{esc(wf.stop_mode || 'pct')}}</span>
    </div>
    <table><tr><th>חלון</th><th>OOS PnL</th><th>עסקאות</th><th>Win%</th><th>פרמטרים</th></tr>` +
    (wf.folds || []).map(f => `<tr>
      <td>#${{f.index}}</td>
      <td class="${{f.oos_pnl>=0?'pos':'neg'}}">${{f.oos_pnl>=0?'+':''}}${{f.oos_pnl}}</td>
      <td>${{f.oos_trades}}</td><td>${{f.oos_win_rate}}%</td>
      <td class="dim">${{esc(Object.entries(f.best_params||{{}}).map(([k,v])=>`${{k}}=${{v}}`).join(', '))}}</td>
    </tr>`).join('') + '</table>' : '<div class="dim">אין reports/walkforward.json</div>';

  const sec = an.sectors;
  document.getElementById('sec-box').innerHTML = (sec && sec.rows) ? `<table>
    <tr><th>סקטור</th><th>סיגנלים</th><th>Hit%</th><th>התממש</th><th>עמלה</th><th>נטו אחרי הכל</th></tr>` +
    sec.rows.map(r => `<tr>
      <td>${{esc(r.sector)}}</td><td>${{r.n}}</td><td>${{Math.round(r.hit_rate*100)}}%</td>
      <td>${{r.mean_realized>=0?'+':''}}${{r.mean_realized}}</td>
      <td class="muted">${{r.mean_fee}}</td>
      <td class="${{r.net_of_cost>=0?'pos':'neg'}}">${{r.net_of_cost>=0?'+':''}}${{r.net_of_cost}}</td>
    </tr>`).join('') + '</table>' : '<div class="dim">הרץ pmmb sectors ליצירת דוח סקטורים</div>';

  document.getElementById('port-md').textContent = an.portfolio_md || 'הרץ pmmb backtest --portfolio';
  document.getElementById('imb-md').textContent = an.imbalance_md || 'אין נתוני imbalance עדיין';

  // Ops / Backups / Config / Events
  document.getElementById('backups-box').innerHTML = (S.backups && S.backups.length) ?
    `<table><tr><th>קובץ גיבוי</th><th>גודל</th><th>תאריך</th></tr>` +
    S.backups.map(b => `<tr><td>${{esc(b.name)}}</td><td>${{b.size_kb}} KB</td><td class="muted">${{fmtTime(b.ts)}}</td></tr>`).join('') +
    '</table>' : '<div class="dim">אין גיבויים עדיין</div>';

  const cfg = S.config || {{}};
  document.getElementById('cfg-grid').innerHTML = Object.entries(cfg).map(([secName, obj]) => `
    <div style="background:var(--panel2);border:1px solid var(--border);border-radius:10px;padding:10px 12px">
      <div style="font-weight:700;margin-bottom:6px;color:#93c5fd">${{esc(secName)}}</div>
      ${{Object.entries(obj || {{}}).map(([k,v]) =>
        `<div style="display:flex;justify-content:space-between;font-size:12px;padding:2px 0;border-bottom:1px solid #1e293b">
          <span class="muted">${{esc(k)}}</span><span>${{esc(Array.isArray(v)?v.join(', '):v)}}</span>
        </div>`).join('')}}
    </div>`).join('');

  document.getElementById('events-box').innerHTML = (S.events && S.events.length) ?
    `<ul style="padding-inline-start:18px;margin:0;font-size:12.5px">` +
    S.events.map(e => `<li style="margin:5px 0"><span class="dim">${{fmtTime(e.ts)}}</span> <b>[${{esc(e.kind)}}]</b> ${{esc(e.msg)}}</li>`).join('') +
    '</ul>' : '<div class="dim">אין אירועים מתועדים</div>';
}}

async function refreshNow() {{
  if (!INTERACTIVE) return;
  try {{
    const r = await fetch('api/state', {{headers: tokenHeader()}});
    if (!r.ok) throw new Error('HTTP ' + r.status);
    S = await r.json();
    render();
    if (ACTIVE_TAB === 'live') loadChart(false);
  }} catch (e) {{
    toast('רענון נכשל: ' + e.message, false);
  }}
}}

async function act(endpoint, payload, waitMsg) {{
  if (!INTERACTIVE) return;
  toast(waitMsg || 'מבצע...');
  const outEl = document.getElementById('ops-out');
  if (outEl) outEl.textContent = waitMsg || 'מבצע...';
  try {{
    const r = await fetch(endpoint, {{
      method: 'POST',
      headers: {{'Content-Type': 'application/json', ...tokenHeader()}},
      body: JSON.stringify(payload || {{}}),
    }});
    const data = await r.json().catch(() => ({{}}));
    if (!r.ok) throw new Error(data.error || ('HTTP ' + r.status));
    if (outEl) outEl.textContent = data.output || JSON.stringify(data, null, 2);
    toast(data.message || 'הפעולה הושלמה', true);
    await refreshNow();
  }} catch (e) {{
    if (outEl) outEl.textContent = 'שגיאה: ' + e.message;
    toast('שגיאה: ' + e.message, false);
  }}
}}

function toggleHalt() {{
  const halted = Boolean(S.halt || (S.heartbeat && S.heartbeat.halted));
  if (halted) {{
    act('api/resume', null, 'מבטל עצירת חירום...');
  }} else {{
    act('api/halt', {{reason: 'עצירה ידנית מהתוכנה'}}, 'מפעיל עצירת חירום...');
  }}
}}

function toggleTrader() {{
  const running = Boolean(S.trader && S.trader.running);
  if (running) {{
    act('api/trader/stop', null, 'עוצר ריצה רציפה...');
  }} else {{
    act('api/trader/start', {{interval_sec: 180}}, 'מפעיל לולאה רציפה 24/7 (מסחר + גרפים + חדשות + למידה)...');
  }}
}}

render();
if (INTERACTIVE && {refresh_sec} > 0) {{
  setInterval(refreshNow, {refresh_sec} * 1000);
}}
</script>
</body>
</html>"""
