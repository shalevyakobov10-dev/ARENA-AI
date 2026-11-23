"""
PMMB Command Center — טרמינל מסחר מוסדי וניתוח שווקים בזמן אמת (RTL).

תכנון מסוף מקצועי:
  - 4 סביבות עבודה: סקירה ומסחר | שווקים וגרפים (Split Desk) | חדשות מכל העולם | למידה ותפעול.
  - גרפי TradingView-Style על Canvas (Crosshair + Tooltip חי, תת-גרף RSI, טווחי זמן 12H/24H/72H/ALL).
  - סולמית עומק ספר פקודות חיה (Order Book Depth Ladder), מדדי מיקום SL-TP וסנטימנט גלובלי.
  - 100% self-contained: אפס URLs חיצוניים, אפס אימוג'ים קרטוניים, עובד מלא גם כקובץ סטטי.
"""
from __future__ import annotations

import json


def command_center_html(initial_data: dict, *, refresh_sec: int = 15, interactive: bool = True) -> str:
    payload = json.dumps(initial_data, ensure_ascii=False).replace("</", "<\\/")
    refresh_ms = max(0, int(refresh_sec)) * 1000 if interactive else 0
    inter_js = "true" if interactive else "false"

    return f"""<!doctype html>
<html lang="he" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>PMMB Command Center</title>
<style>
  :root {{
    --bg: #080c12;
    --surface: #0f151f;
    --surface-2: #151d2b;
    --surface-3: #1b2434;
    --border: rgba(255,255,255,0.07);
    --border-strong: rgba(255,255,255,0.14);
    --text: #f1f5f9;
    --text-2: #94a3b8;
    --text-3: #64748b;
    --accent: #3b82f6;
    --accent-soft: rgba(59,130,246,0.13);
    --green: #10b981;
    --green-soft: rgba(16,185,129,0.13);
    --red: #ef4444;
    --red-soft: rgba(239,68,68,0.13);
    --amber: #f59e0b;
    --amber-soft: rgba(245,158,11,0.13);
    --radius: 10px;
  }}
  * {{ box-sizing: border-box; }}
  html, body {{
    margin: 0; padding: 0; background: var(--bg); color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    font-size: 13px; line-height: 1.5; -webkit-font-smoothing: antialiased;
  }}
  .num {{ font-variant-numeric: tabular-nums; direction: ltr; unicode-bidi: embed; display: inline-block; }}
  .mono {{ font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }}

  /* --- Topbar & Pulse Ribbon --- */
  .topbar {{
    position: sticky; top: 0; z-index: 40;
    background: rgba(8,12,18,0.92); backdrop-filter: blur(14px);
    border-bottom: 1px solid var(--border);
  }}
  .topbar-inner {{
    max-width: 1500px; margin: 0 auto; padding: 0 22px;
    height: 56px; display: flex; align-items: center; justify-content: space-between; gap: 14px;
  }}
  .brand {{ display: flex; align-items: center; gap: 11px; }}
  .brand-mark {{
    width: 32px; height: 32px; border-radius: 8px;
    background: linear-gradient(135deg, rgba(59,130,246,0.22), rgba(16,185,129,0.12));
    border: 1px solid var(--border-strong);
    display: grid; place-items: center; color: #60a5fa;
  }}
  .brand-title {{ font-weight: 600; font-size: 14.5px; letter-spacing: 0.01em; }}
  .brand-sub {{ font-size: 11px; color: var(--text-3); }}

  .nav-tabs {{
    display: flex; align-items: center; gap: 4px;
    background: var(--surface); border: 1px solid var(--border);
    padding: 3px; border-radius: 9px;
  }}
  .nav-tab {{
    background: transparent; border: none; color: var(--text-2);
    padding: 6px 14px; border-radius: 6px; cursor: pointer;
    font-size: 12.5px; font-weight: 500; transition: all 0.14s ease;
    display: inline-flex; align-items: center; gap: 7px; white-space: nowrap;
  }}
  .nav-tab:hover {{ color: var(--text); }}
  .nav-tab.active {{ background: var(--surface-2); color: var(--text); box-shadow: inset 0 0 0 1px var(--border-strong); }}

  .top-actions {{ display: flex; align-items: center; gap: 8px; }}
  .status-pill {{
    display: inline-flex; align-items: center; gap: 7px;
    padding: 5px 11px; border-radius: 999px; font-size: 11.5px; font-weight: 500;
    background: var(--surface); border: 1px solid var(--border); color: var(--text-2);
  }}
  .dot {{ width: 7px; height: 7px; border-radius: 50%; background: var(--text-3); flex-shrink: 0; }}
  .dot.ok {{ background: var(--green); box-shadow: 0 0 0 3px var(--green-soft); }}
  .dot.warn {{ background: var(--amber); box-shadow: 0 0 0 3px var(--amber-soft); }}
  .dot.err {{ background: var(--red); box-shadow: 0 0 0 3px var(--red-soft); }}

  .pulse-ribbon {{
    background: #0b1018; border-bottom: 1px solid var(--border);
  }}
  .pulse-inner {{
    max-width: 1500px; margin: 0 auto; padding: 6px 22px;
    display: flex; align-items: center; justify-content: space-between; gap: 16px; flex-wrap: wrap;
    font-size: 11.5px; color: var(--text-3);
  }}
  .pulse-group {{ display: flex; align-items: center; gap: 18px; flex-wrap: wrap; }}
  .pulse-item {{ display: inline-flex; align-items: center; gap: 6px; }}
  .pulse-item strong {{ color: var(--text-2); font-weight: 500; }}

  /* --- Controls --- */
  .btn {{
    background: var(--surface-2); color: var(--text);
    border: 1px solid var(--border-strong); border-radius: 7px;
    padding: 6px 12px; font-size: 12px; font-weight: 500;
    cursor: pointer; transition: all 0.14s ease;
    display: inline-flex; align-items: center; gap: 6px; white-space: nowrap;
  }}
  .btn:hover {{ background: var(--surface-3); border-color: rgba(255,255,255,0.22); }}
  .btn:disabled {{ opacity: 0.45; cursor: not-allowed; }}
  .btn-primary {{ background: var(--accent); border-color: var(--accent); color: #fff; }}
  .btn-primary:hover {{ background: #2563eb; border-color: #2563eb; }}
  .btn-danger {{ background: var(--red-soft); border-color: rgba(239,68,68,0.35); color: #fca5a5; }}
  .btn-danger:hover {{ background: rgba(239,68,68,0.24); }}
  .btn-ghost {{ background: transparent; border-color: var(--border); color: var(--text-2); }}
  .btn-ghost:hover {{ color: var(--text); background: var(--surface); }}
  .btn-xs {{ padding: 4px 9px; font-size: 11px; border-radius: 5px; }}
  .btn-xs.active {{ background: var(--accent-soft); border-color: rgba(59,130,246,0.4); color: #93c5fd; }}

  .input {{
    background: var(--surface-2); color: var(--text); border: 1px solid var(--border-strong);
    border-radius: 7px; padding: 6px 11px; font-size: 12px; outline: none; width: 100%;
  }}
  .input:focus {{ border-color: var(--accent); }}

  /* --- Layout --- */
  .wrap {{ max-width: 1500px; margin: 0 auto; padding: 18px 22px 52px; }}

  .banner {{
    padding: 10px 14px; border-radius: var(--radius); margin-bottom: 14px;
    font-size: 12.5px; display: flex; align-items: center; justify-content: space-between; gap: 12px;
  }}
  .banner.err {{ background: var(--red-soft); border: 1px solid rgba(239,68,68,0.35); color: #fecaca; }}

  .kpi-row {{
    display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 12px; margin-bottom: 14px;
  }}
  .kpi {{
    background: var(--surface); border: 1px solid var(--border);
    border-radius: var(--radius); padding: 13px 15px; position: relative;
  }}
  .kpi-label {{ font-size: 11px; color: var(--text-3); margin-bottom: 5px; font-weight: 500; }}
  .kpi-val {{ font-size: 21px; font-weight: 600; color: var(--text); letter-spacing: -0.02em; }}
  .kpi-sub {{ font-size: 11px; color: var(--text-2); margin-top: 4px; }}

  .grid-2 {{ display: grid; grid-template-columns: 1.55fr 1fr; gap: 14px; margin-bottom: 14px; }}
  .grid-even {{ display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-bottom: 14px; }}
  .desk-grid {{ display: grid; grid-template-columns: 360px minmax(0, 1fr); gap: 14px; align-items: start; }}

  .card {{
    background: var(--surface); border: 1px solid var(--border);
    border-radius: var(--radius); overflow: hidden; margin-bottom: 14px;
  }}
  .grid-2 .card, .grid-even .card, .desk-grid .card {{ margin-bottom: 0; }}
  .card-head {{
    padding: 11px 15px; border-bottom: 1px solid var(--border);
    display: flex; align-items: center; justify-content: space-between; gap: 10px; flex-wrap: wrap;
  }}
  .card-title {{ font-size: 13px; font-weight: 600; color: var(--text); }}
  .card-meta {{ font-size: 11.5px; color: var(--text-3); }}
  .card-body {{ padding: 14px 15px; }}
  .card-body.flush {{ padding: 0; }}

  /* --- Tables & Meters --- */
  .table-wrap {{ overflow-x: auto; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
  th {{
    text-align: right; padding: 8px 13px; font-weight: 500; font-size: 11px;
    color: var(--text-3); border-bottom: 1px solid var(--border); background: rgba(255,255,255,0.015);
    white-space: nowrap;
  }}
  td {{ padding: 9px 13px; border-bottom: 1px solid var(--border); color: var(--text-2); vertical-align: middle; }}
  tr:last-child td {{ border-bottom: none; }}
  tr.clickable {{ cursor: pointer; transition: background 0.1s; }}
  tr.clickable:hover td {{ background: rgba(255,255,255,0.03); }}
  .q-cell {{ color: var(--text); font-weight: 500; }}

  .range-meter {{
    display: flex; align-items: center; gap: 7px; min-width: 155px;
  }}
  .range-track {{
    flex: 1; height: 5px; border-radius: 99px; background: rgba(255,255,255,0.08);
    position: relative; overflow: visible;
  }}
  .range-fill {{
    position: absolute; top: 0; height: 100%; border-radius: 99px; background: var(--accent);
  }}
  .range-pin {{
    position: absolute; top: -3px; width: 3px; height: 11px; border-radius: 2px; background: #fff;
    transform: translateX(-50%); box-shadow: 0 0 6px rgba(255,255,255,0.6);
  }}

  /* --- Watchlist (Trading Desk Left Pane) --- */
  .wl-scroll {{ max-height: 670px; overflow-y: auto; }}
  .wl-item {{
    padding: 10px 13px; border-bottom: 1px solid var(--border); cursor: pointer;
    transition: background 0.12s;
  }}
  .wl-item:hover {{ background: rgba(255,255,255,0.025); }}
  .wl-item.active {{ background: rgba(59,130,246,0.1); border-right: 3px solid var(--accent); }}
  .wl-top {{ display: flex; justify-content: space-between; align-items: flex-start; gap: 8px; margin-bottom: 5px; }}
  .wl-q {{ font-size: 12px; font-weight: 500; color: var(--text); line-height: 1.35; }}
  .wl-sub {{ display: flex; justify-content: space-between; align-items: center; font-size: 11px; color: var(--text-3); gap: 8px; }}

  /* --- Order Book Depth Ladder --- */
  .ob-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }}
  .ob-row {{
    position: relative; display: flex; justify-content: space-between;
    padding: 4px 8px; font-size: 11.5px; border-radius: 4px; margin-bottom: 3px; overflow: hidden;
  }}
  .ob-bar {{ position: absolute; top: 0; bottom: 0; opacity: 0.16; pointer-events: none; }}
  .ob-bid .ob-bar {{ right: 0; background: var(--green); }}
  .ob-ask .ob-bar {{ left: 0; background: var(--red); }}

  /* --- Badges & Progress --- */
  .badge {{
    display: inline-flex; align-items: center; padding: 2px 7px; border-radius: 5px;
    font-size: 10.5px; font-weight: 500; border: 1px solid transparent; white-space: nowrap;
  }}
  .badge-ok {{ background: var(--green-soft); color: #6ee7b7; border-color: rgba(16,185,129,0.25); }}
  .badge-warn {{ background: var(--amber-soft); color: #fcd34d; border-color: rgba(245,158,11,0.25); }}
  .badge-err {{ background: var(--red-soft); color: #fca5a5; border-color: rgba(239,68,68,0.25); }}
  .badge-info {{ background: var(--accent-soft); color: #93c5fd; border-color: rgba(59,130,246,0.25); }}
  .badge-mute {{ background: rgba(255,255,255,0.04); color: var(--text-2); border-color: var(--border); }}

  .bar-row {{ margin-bottom: 10px; }}
  .bar-row:last-child {{ margin-bottom: 0; }}
  .bar-top {{ display: flex; justify-content: space-between; font-size: 11.5px; margin-bottom: 4px; color: var(--text-2); }}
  .bar-track {{ height: 4px; border-radius: 99px; background: rgba(255,255,255,0.07); overflow: hidden; }}
  .bar-fill {{ height: 100%; border-radius: 99px; background: var(--accent); }}

  /* --- Chart Canvases & Tooltips --- */
  .chart-wrap {{ position: relative; width: 100%; height: 295px; }}
  .rsi-wrap {{ position: relative; width: 100%; height: 82px; margin-top: 6px; border-top: 1px solid var(--border); padding-top: 4px; }}
  .eq-wrap {{ position: relative; width: 100%; height: 185px; }}
  canvas.plot {{ width: 100%; height: 100%; display: block; cursor: crosshair; }}
  .tooltip {{
    position: absolute; top: 8px; right: 12px; pointer-events: none;
    background: rgba(15,21,31,0.92); border: 1px solid var(--border-strong);
    border-radius: 6px; padding: 5px 10px; font-size: 11px; color: var(--text);
    display: none; backdrop-filter: blur(8px); z-index: 10;
  }}

  /* --- News & Decision Tape --- */
  .filter-pills {{ display: flex; gap: 5px; flex-wrap: wrap; }}
  .pill-btn {{
    background: transparent; color: var(--text-2); border: 1px solid var(--border);
    border-radius: 999px; padding: 4px 10px; font-size: 11px; cursor: pointer;
  }}
  .pill-btn.active {{ background: var(--surface-2); color: var(--text); border-color: var(--border-strong); }}

  .news-item {{
    padding: 10px 15px; border-bottom: 1px solid var(--border);
    display: flex; align-items: flex-start; justify-content: space-between; gap: 12px;
  }}
  .news-item:last-child {{ border-bottom: none; }}
  .news-title {{ color: var(--text); font-size: 12.5px; font-weight: 500; line-height: 1.45; }}
  .news-meta {{ font-size: 11px; color: var(--text-3); margin-top: 3px; display: flex; gap: 10px; flex-wrap: wrap; }}

  .tape-item {{
    padding: 8px 14px; border-bottom: 1px solid var(--border);
    display: flex; align-items: baseline; gap: 10px; font-size: 12px;
  }}
  .tape-item:last-child {{ border-bottom: none; }}

  .kv-list {{ display: grid; grid-template-columns: 1fr 1fr; gap: 6px 18px; }}
  .kv-item {{
    display: flex; justify-content: space-between; align-items: center;
    padding: 6px 0; border-bottom: 1px solid var(--border); font-size: 12px;
  }}
  .kv-k {{ color: var(--text-3); }}
  .kv-v {{ color: var(--text); font-weight: 500; }}

  .toast {{
    position: fixed; bottom: 20px; left: 20px; z-index: 60;
    background: var(--surface-2); border: 1px solid var(--border-strong); color: var(--text);
    padding: 10px 16px; border-radius: 8px; font-size: 12px;
    box-shadow: 0 12px 30px rgba(0,0,0,0.45); display: none; max-width: 440px;
  }}
  .tab-pane {{ display: none; }}
  .tab-pane.active {{ display: block; }}

  .pos {{ color: var(--green); }}
  .neg {{ color: var(--red); }}

  @media (max-width: 1180px) {{
    .desk-grid {{ grid-template-columns: 1fr; }}
    .wl-scroll {{ max-height: 300px; }}
  }}
  @media (max-width: 1020px) {{
    .kpi-row {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
    .grid-2, .grid-even {{ grid-template-columns: 1fr; }}
    .topbar-inner {{ height: auto; padding: 10px 14px; flex-wrap: wrap; }}
  }}
  @media (max-width: 640px) {{
    .wrap {{ padding: 12px 12px 36px; }}
    .kv-list, .ob-grid {{ grid-template-columns: 1fr; }}
    .nav-tabs {{ width: 100%; overflow-x: auto; }}
  }}
</style>
</head>
<body>

<header class="topbar">
  <div class="topbar-inner">
    <div class="brand">
      <div class="brand-mark" aria-hidden="true">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"></polyline>
        </svg>
      </div>
      <div>
        <div class="brand-title">PMMB Command Center</div>
        <div class="brand-sub" id="sub-status">טוען נתונים...</div>
      </div>
    </div>

    <nav class="nav-tabs" aria-label="ניווט ראשי">
      <button class="nav-tab active" data-tab="overview">סקירה ומסחר</button>
      <button class="nav-tab" data-tab="perps">⚡ חוזים (PERPS ×50)</button>
      <button class="nav-tab" data-tab="markets">שווקים וגרפים</button>
      <button class="nav-tab" data-tab="intel">חדשות ולמידה</button>
      <button class="nav-tab" data-tab="system">תפעול אוטונומי</button>
    </nav>

    <div class="top-actions">
      <div class="status-pill" id="live-pill">
        <span class="dot" id="live-dot"></span>
        <span id="live-label">מצב</span>
      </div>
      <button class="btn btn-primary" id="btn-toggle-ap" onclick="toggleAutopilot()">הפעל אוטופיילוט</button>
      <button class="btn btn-ghost" onclick="refreshAll()" title="רענון מיידי">רענן</button>
    </div>
  </div>
  <div class="pulse-ribbon">
    <div class="pulse-inner" id="pulse-ribbon"></div>
  </div>
</header>

<main class="wrap">
  <div id="halt-banner" class="banner err" style="display:none">
    <span id="halt-text"></span>
    <button class="btn" onclick="postAction('/api/resume', {{}})">בטל עצירה</button>
  </div>

  <!-- ========== TAB 1: סקירה ומסחר ========== -->
  <section id="tab-overview" class="tab-pane active">
    <div class="kpi-row" id="kpi-row"></div>

    <div class="grid-2">
      <div class="card">
        <div class="card-head">
          <span class="card-title">עקומת הון חיה</span>
          <span class="card-meta" id="eq-meta">—</span>
        </div>
        <div class="card-body">
          <div class="eq-wrap">
            <canvas id="eq-canvas" class="plot"></canvas>
            <div id="eq-tip" class="tooltip"></div>
          </div>
        </div>
      </div>
      <div class="card">
        <div class="card-head">
          <span class="card-title">בקרת סיכון ומרווחי הון</span>
          <span class="card-meta" id="risk-meta">Mean Reversion + RSI + Spread/Edge</span>
        </div>
        <div class="card-body" id="risk-bars"></div>
      </div>
    </div>

    <div class="card">
      <div class="card-head">
        <span class="card-title">פוזיציות פתוחות</span>
        <span class="card-meta">סרגל SL ↔ Entry ↔ TP · לחיצה פותחת את דסק השוק</span>
      </div>
      <div class="card-body flush">
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>שוק</th>
                <th>כמות</th>
                <th>כניסה</th>
                <th>נוכחי</th>
                <th>מיקום בין SL ל-TP</th>
                <th>רווח/הפסד</th>
                <th>גיל</th>
              </tr>
            </thead>
            <tbody id="pos-tbody"></tbody>
          </table>
        </div>
      </div>
    </div>

    <div class="grid-even">
      <div class="card">
        <div class="card-head">
          <span class="card-title">זרם החלטות ואירועי מערכת (Live Tape)</span>
          <span class="card-meta" id="tape-meta">—</span>
        </div>
        <div class="card-body flush" id="decision-tape"></div>
      </div>
      <div class="card">
        <div class="card-head">
          <span class="card-title">עסקאות סגורות אחרונות</span>
          <span class="card-meta" id="trades-meta">—</span>
        </div>
        <div class="card-body flush">
          <div class="table-wrap">
            <table>
              <thead><tr><th>מועד</th><th>שוק</th><th>כמות</th><th>מחיר</th><th>PnL</th><th>סיבה</th></tr></thead>
              <tbody id="trades-tbody"></tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  </section>

  <!-- ========== TAB 2: שווקים וגרפים (Split Desk) ========== -->
  <section id="tab-markets" class="tab-pane">
    <div class="desk-grid">
      <!-- ימין: רדאר ורשימת מעקב אינטראקטיבית -->
      <div class="card">
        <div class="card-head" style="flex-direction:column;align-items:stretch;gap:8px">
          <div style="display:flex;justify-content:space-between;align-items:center">
            <span class="card-title">רדאר מודיעין שווקים חי</span>
            <span class="card-meta" id="wl-count">—</span>
          </div>
          <input type="text" id="wl-search" class="input" placeholder="חיפוש שוק או סקטור..." oninput="renderMarketsIntel()">
          <div class="filter-pills" id="intel-filters">
            <button class="pill-btn active" onclick="setIntelFilter('ALL', this)">הכל</button>
            <button class="pill-btn" onclick="setIntelFilter('OPEN', this)">פתוחות</button>
            <button class="pill-btn" onclick="setIntelFilter('NEAR', this)">מתחממים</button>
            <button class="pill-btn" onclick="setIntelFilter('APLUS', this)">A+/A</button>
            <button class="pill-btn" onclick="setIntelFilter('CATALYST_BLOCK', this)">נחסמו</button>
          </div>
        </div>
        <div class="wl-scroll" id="wl-list"></div>
      </div>

      <!-- שמאל: גרף Trading Desk + ספר פקודות + תיזת בוט -->
      <div style="display:flex;flex-direction:column;gap:14px">
        <div class="card">
          <div class="card-head">
            <div>
              <div class="card-title" id="desk-title">בחר שוק מהרדאר</div>
              <div class="card-meta" id="desk-sub">—</div>
            </div>
            <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap">
              <button class="btn btn-xs" onclick="setRange(12, this)">12H</button>
              <button class="btn btn-xs" onclick="setRange(24, this)">24H</button>
              <button class="btn btn-xs" onclick="setRange(72, this)">72H</button>
              <button class="btn btn-xs active" onclick="setRange(9999, this)">ALL</button>
              <button class="btn btn-ghost btn-xs" onclick="loadChart(SELECTED_TOKEN, true)">משוך חי</button>
            </div>
          </div>
          <div class="card-body">
            <div class="chart-wrap">
              <canvas id="price-canvas" class="plot"></canvas>
              <div id="price-tip" class="tooltip"></div>
            </div>
            <div class="rsi-wrap">
              <canvas id="rsi-canvas" class="plot"></canvas>
            </div>
          </div>
        </div>

        <div class="grid-even">
          <div class="card">
            <div class="card-head">
              <span class="card-title">תיזת הסוחר המקצועי לשוק</span>
              <span class="card-meta" id="thesis-badge">—</span>
            </div>
            <div class="card-body" id="desk-thesis"></div>
          </div>
          <div class="card">
            <div class="card-head">
              <span class="card-title">עומק ספר פקודות (Order Book)</span>
              <span class="card-meta" id="ob-meta">—</span>
            </div>
            <div class="card-body" id="desk-ob"></div>
          </div>
        </div>
      </div>
    </div>
  </section>

  <!-- ========== TAB 3: חדשות ולמידה ========== -->
  <section id="tab-intel" class="tab-pane">
    <div class="kpi-row" id="news-pulse-kpis"></div>

    <div class="grid-even">
      <div class="card">
        <div class="card-head" style="flex-direction:column;align-items:stretch;gap:8px">
          <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap">
            <span class="card-title">פיד חדשות מוסדי גלובלי (19 רשתות עולמיות)</span>
            <button class="btn btn-ghost btn-xs" onclick="postAction('/api/news-refresh', {{}})">רענן פיד גלובלי</button>
          </div>
          <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
            <input type="text" id="news-search" class="input" style="max-width:210px" placeholder="חיפוש בכותרת, אזור או רשת..." oninput="renderNews()">
            <div class="filter-pills">
              <button class="pill-btn active" onclick="setNewsFilter('ALL', this)">הכל</button>
              <button class="pill-btn" onclick="setNewsFilter('CATALYST', this)">חריגות</button>
              <button class="pill-btn" onclick="setNewsFilter('MATCHED', this)">קשור לשוק</button>
              <button class="pill-btn" onclick="setNewsFilter('REG:אסיה', this)">אסיה</button>
              <button class="pill-btn" onclick="setNewsFilter('REG:מזרח תיכון', this)">מזרח תיכון</button>
              <button class="pill-btn" onclick="setNewsFilter('REG:אמריקה ושווקים', this)">אמריקה</button>
              <button class="pill-btn" onclick="setNewsFilter('REG:אירופה', this)">אירופה</button>
              <button class="pill-btn" onclick="setNewsFilter('sports', this)">ספורט</button>
            </div>
          </div>
        </div>
        <div class="card-body flush" style="max-height:580px;overflow-y:auto">
          <div id="news-list"></div>
        </div>
      </div>

      <div style="display:flex;flex-direction:column;gap:14px">
        <div class="card">
          <div class="card-head">
            <span class="card-title">מנוע למידה עצמית (OOS Walk-Forward)</span>
            <button class="btn btn-ghost btn-xs" onclick="postAction('/api/learn', {{apply:true}})">הרץ הערכה</button>
          </div>
          <div class="card-body" id="learn-insights"></div>
        </div>

        <div class="card">
          <div class="card-head">
            <span class="card-title">דיוק אותות לפי Z-Score ואופק</span>
            <span class="card-meta" id="learn-total">—</span>
          </div>
          <div class="card-body flush">
            <div class="table-wrap">
              <table>
                <thead><tr><th>טווח Z</th><th>6ש'</th><th>24ש'</th><th>48ש'</th><th>הצלחה עדכנית</th><th>תשואה ממוצעת</th></tr></thead>
                <tbody id="learn-z-tbody"></tbody>
              </table>
            </div>
          </div>
        </div>

        <div class="card">
          <div class="card-head">
            <span class="card-title">היסטוריית מחזורי כיול OOS</span>
            <span class="card-meta">4 שערי בטיחות</span>
          </div>
          <div class="card-body flush">
            <div class="table-wrap">
              <table>
                <thead><tr><th>מועד</th><th>בסיס</th><th>מועמד</th><th>התמדה</th><th>עודכן</th></tr></thead>
                <tbody id="learn-runs-tbody"></tbody>
              </table>
            </div>
          </div>
        </div>
      </div>
    </div>
  </section>

  <!-- ========== TAB 4: תפעול אוטונומי ========== -->
  <section id="tab-system" class="tab-pane">
    <div class="card">
      <div class="card-head">
        <span class="card-title">בקרה ושליטה מהירה</span>
        <span class="card-meta">הבוט מתפעל הכל אוטומטית ברקע — כאן ניתן לבצע פעולה יזומה</span>
      </div>
      <div class="card-body" style="display:flex;gap:10px;flex-wrap:wrap;align-items:center">
        <button class="btn btn-primary" onclick="postAction('/api/autopilot/maintain', {{}})">תחזוקה מלאה עכשיו</button>
        <button class="btn" onclick="postAction('/api/paper-cycle', {{}})">מחזור מסחר בודד</button>
        <button class="btn" onclick="postAction('/api/backup', {{}})">גיבוי מיידי</button>
        <button class="btn" onclick="postAction('/api/reconcile', {{fix:true}})">אימות DB</button>
        <button class="btn btn-danger" style="margin-right:auto" onclick="postAction('/api/halt', {{reason:'עצירה מהממשק'}})">עצירת חירום</button>
      </div>
    </div>

    <div class="grid-even">
      <div class="card">
        <div class="card-head">
          <span class="card-title">יומן טייס אוטומטי (Autopilot)</span>
          <span class="card-meta" id="ap-meta">—</span>
        </div>
        <div class="card-body flush">
          <div class="table-wrap">
            <table>
              <thead><tr><th>מועד</th><th>משימה</th><th>סטטוס</th><th>פירוט</th></tr></thead>
              <tbody id="ap-tbody"></tbody>
            </table>
          </div>
        </div>
      </div>

      <div class="card">
        <div class="card-head">
          <span class="card-title">מוכנות למעבר ל-Live</span>
          <span class="card-meta" id="ready-summary">—</span>
        </div>
        <div class="card-body flush">
          <div class="table-wrap">
            <table>
              <thead><tr><th>בדיקה</th><th>סטטוס</th><th>פירוט</th></tr></thead>
              <tbody id="ready-tbody"></tbody>
            </table>
          </div>
        </div>
      </div>
    </div>

    <div class="grid-even">
      <div class="card">
        <div class="card-head">
          <span class="card-title">ביצועי אסטרטגיה (פורטפוליו Backtest &amp; Walk-Forward)</span>
          <span class="card-meta">מדדי יחוס אמפיריים</span>
        </div>
        <div class="card-body" id="analytics-box"></div>
      </div>

      <div class="card">
        <div class="card-head">
          <span class="card-title">תצורת מסחר מוסדית פעילה</span>
          <span class="card-meta" id="cfg-mode">paper</span>
        </div>
        <div class="card-body" id="cfg-box"></div>
      </div>
    </div>
  </section>

  <!-- ========== TAB PERPS: חוזים תמידיים עד ×50 ========== -->
  <section id="tab-perps" class="tab-pane">
    <div style="display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap;margin-bottom:14px">
      <div>
        <div style="font-size:15px;font-weight:700">זרוע חוזים תמידיים (PERPS · Isolated Margin עד ×50)</div>
        <div style="font-size:12px;color:var(--text-3)" id="perps-sub-hdr">OKX + Hyperliquid + Binance · Multi-Regime + Funding + Global Macro</div>
      </div>
      <div style="display:flex;gap:8px;flex-wrap:wrap">
        <button class="btn btn-primary" onclick="postAction('/api/perps/cycle', {{}})">מחזור PERPS עכשיו</button>
        <button class="btn" onclick="postAction('/api/perps/learn', {{}})">כיול Walk-Forward</button>
        <button class="btn btn-ghost" id="btn-perps-toggle" onclick="postAction('/api/perps/toggle', {{}})">השהה PERPS</button>
      </div>
    </div>

    <div class="kpi-row" id="perps-kpi-row"></div>

    <div class="grid-2">
      <div class="card">
        <div class="card-head">
          <span class="card-title">עקומת הון PERPS</span>
          <span class="card-meta" id="perps-eq-meta">—</span>
        </div>
        <div class="card-body">
          <div class="eq-wrap"><canvas id="perps-eq-canvas" class="plot"></canvas></div>
        </div>
      </div>
      <div class="card">
        <div class="card-head">
          <span class="card-title">הגנות מרג׳ין וליקווידציה (עד ×50)</span>
          <span class="card-meta" id="perps-guard-meta">Isolated Margin</span>
        </div>
        <div class="card-body" id="perps-guards-box"></div>
      </div>
    </div>

    <div class="card">
      <div class="card-head">
        <span class="card-title">פוזיציות PERPS פתוחות</span>
        <span class="card-meta">לחיצה על שורה טוענת את גרף החוזה וקווי SL / TP / LIQ</span>
      </div>
      <div class="card-body flush">
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>חוזה / בורסה</th><th>כיוון</th><th>מינוף</th><th>מרג׳ין</th><th>נומינלי</th>
                <th>כניסה</th><th>נוכחי</th><th>SL / TP</th><th>ליקווידציה (LIQ)</th><th>ROE / PnL</th>
              </tr>
            </thead>
            <tbody id="perps-pos-tbody"></tbody>
          </table>
        </div>
      </div>
    </div>

    <div class="desk-grid">
      <div class="card">
        <div class="card-head" style="flex-direction:column;align-items:stretch;gap:8px">
          <div style="display:flex;justify-content:space-between;align-items:center">
            <span class="card-title">רדאר חוזים רב-בורסות</span>
            <span class="card-meta" id="perps-intel-cnt">—</span>
          </div>
          <input type="text" id="perps-search" class="input" placeholder="חיפוש מטבע (BTC, ETH, SOL...)" oninput="renderPerps()">
        </div>
        <div class="wl-scroll" id="perps-wl"></div>
      </div>

      <div style="display:flex;flex-direction:column;gap:14px">
        <div class="card">
          <div class="card-head">
            <div>
              <div class="card-title" id="perps-chart-title">גרף חוזה חי</div>
              <div class="card-meta" id="perps-chart-sub">1h · Multi-Regime</div>
            </div>
            <button class="btn btn-ghost btn-xs" onclick="loadPerpChart(SELECTED_PERP_SYM, true)">משוך חי</button>
          </div>
          <div class="card-body">
            <div class="chart-wrap">
              <canvas id="perps-price-canvas" class="plot"></canvas>
              <div id="perps-price-tip" class="tooltip"></div>
            </div>
          </div>
        </div>

        <div class="grid-even">
          <div class="card">
            <div class="card-head"><span class="card-title">עסקאות PERPS סגורות</span><span class="card-meta" id="perps-tr-cnt">—</span></div>
            <div class="card-body flush">
              <div class="table-wrap">
                <table>
                  <thead><tr><th>מועד</th><th>חוזה</th><th>כיוון</th><th>מינוף</th><th>PnL</th><th>סיבה</th></tr></thead>
                  <tbody id="perps-trades-tbody"></tbody>
                </table>
              </div>
            </div>
          </div>
          <div class="card">
            <div class="card-head"><span class="card-title">למידה עצמית OOS (PERPS)</span></div>
            <div class="card-body flush">
              <div class="table-wrap">
                <table>
                  <thead><tr><th>מועד</th><th>Baseline</th><th>מועמד</th><th>עקביות</th><th>סטטוס</th></tr></thead>
                  <tbody id="perps-learn-tbody"></tbody>
                </table>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </section>
</main>

<div id="toast" class="toast"></div>

<script>
const INITIAL = {payload};
let STATE = INITIAL;
let ACTIVE_TAB = 'overview';
let INTEL_FILTER = 'ALL';
let NEWS_FILTER = 'ALL';
let CHART_RANGE = 9999;
let CURRENT_CHART = (INITIAL.charts && INITIAL.charts.default) || null;
let SELECTED_TOKEN = (CURRENT_CHART && CURRENT_CHART.token_id) || '';
let CURRENT_PERP_CHART = (INITIAL.perps && INITIAL.perps.default_chart) || null;
let SELECTED_PERP_SYM = (CURRENT_PERP_CHART && CURRENT_PERP_CHART.symbol) || 'BTC';
const LIVE_ORIGIN = {inter_js} && Boolean(window.location && window.location.protocol && window.location.protocol.startsWith('http'));

const esc = (s) => String(s ?? '').replace(/[&<>"']/g, m => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[m]));
const fmtNum = (v, d = 2) => (v === null || v === undefined || Number.isNaN(Number(v))) ? '—' : Number(v).toFixed(d);
const fmtSign = (v, d = 2) => {{
  if (v === null || v === undefined || Number.isNaN(Number(v))) return '—';
  const n = Number(v);
  return (n >= 0 ? '+' : '') + n.toFixed(d);
}};
const fmtTime = (ts) => {{
  if (!ts) return '—';
  return new Date(Number(ts) * 1000).toLocaleTimeString('he-IL', {{hour:'2-digit', minute:'2-digit'}});
}};
const fmtDateTime = (ts) => {{
  if (!ts) return '—';
  const d = new Date(Number(ts) * 1000);
  return d.toLocaleDateString('he-IL', {{day:'2-digit', month:'2-digit'}}) + ' ' + d.toLocaleTimeString('he-IL', {{hour:'2-digit', minute:'2-digit'}});
}};

function showToast(msg, isErr = false) {{
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.style.borderColor = isErr ? 'rgba(239,68,68,0.55)' : 'rgba(59,130,246,0.5)';
  el.style.display = 'block';
  clearTimeout(window.__toastTimer);
  window.__toastTimer = setTimeout(() => {{ el.style.display = 'none'; }}, 4000);
}}

document.querySelectorAll('.nav-tab').forEach(btn => {{
  btn.addEventListener('click', () => {{
    ACTIVE_TAB = btn.dataset.tab;
    document.querySelectorAll('.nav-tab').forEach(b => b.classList.toggle('active', b === btn));
    document.querySelectorAll('.tab-pane').forEach(p => p.classList.toggle('active', p.id === 'tab-' + ACTIVE_TAB));
    if (ACTIVE_TAB === 'markets') {{ drawPriceChart(); drawRsiChart(); }}
    if (ACTIVE_TAB === 'overview') drawEquityChart();
    if (ACTIVE_TAB === 'perps') {{ drawPerpEqChart(); drawPerpPriceChart(); }}
  }});
}});

function switchToMarket(tokenId) {{
  if (!tokenId) return;
  SELECTED_TOKEN = tokenId;
  ACTIVE_TAB = 'markets';
  document.querySelectorAll('.nav-tab').forEach(b => b.classList.toggle('active', b.dataset.tab === 'markets'));
  document.querySelectorAll('.tab-pane').forEach(p => p.classList.toggle('active', p.id === 'tab-markets'));
  renderMarketsIntel();
  loadChart(tokenId, true);
}}

function setIntelFilter(val, btn) {{
  INTEL_FILTER = val;
  document.querySelectorAll('#intel-filters .pill-btn').forEach(b => b.classList.toggle('active', b === btn));
  renderMarketsIntel();
}}

function setNewsFilter(val, btn) {{
  NEWS_FILTER = val;
  btn.parentElement.querySelectorAll('.pill-btn').forEach(b => b.classList.toggle('active', b === btn));
  renderNews();
}}

function setRange(hours, btn) {{
  CHART_RANGE = hours;
  btn.parentElement.querySelectorAll('.btn-xs').forEach(b => {{ if (b.textContent !== 'משוך חי') b.classList.toggle('active', b === btn); }});
  drawPriceChart();
  drawRsiChart();
}}

async function postAction(path, body) {{
  if (!LIVE_ORIGIN) {{
    showToast('הפעולה זמינה בחיבור לשרת החי בלבד', true);
    return;
  }}
  try {{
    const res = await fetch(path, {{
      method: 'POST',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify(body || {{}})
    }});
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'בקשה נכשלה');
    showToast(data.message || 'בוצע');
    await refreshAll();
  }} catch (e) {{
    showToast(e.message || 'שגיאה בביצוע הפעולה', true);
  }}
}}

async function toggleAutopilot() {{
  const running = Boolean(STATE.trader && STATE.trader.running);
  const path = running ? '/api/trader/stop' : '/api/trader/start';
  await postAction(path, running ? {{}} : {{interval_sec: (STATE.config && STATE.config.autopilot && STATE.config.autopilot.trade_interval_sec) || 180}});
}}

async function refreshAll() {{
  if (!LIVE_ORIGIN) return;
  try {{
    const res = await fetch('/api/state');
    if (res.ok) {{
      STATE = await res.json();
      renderAll();
    }}
  }} catch (e) {{}}
}}

async function loadChart(tokenId, live = false) {{
  if (!tokenId) return;
  SELECTED_TOKEN = tokenId;
  renderMarketsIntel();
  if (!LIVE_ORIGIN) {{
    renderDeskPanels();
    drawPriceChart();
    drawRsiChart();
    return;
  }}
  try {{
    const res = await fetch('/api/chart?token=' + encodeURIComponent(tokenId) + (live ? '&live=1' : ''));
    if (res.ok) {{
      CURRENT_CHART = await res.json();
      renderDeskPanels();
      drawPriceChart();
      drawRsiChart();
    }}
  }} catch (e) {{}}
}}

function renderAll() {{
  renderHeader();
  renderOverview();
  renderPerps();
  renderMarketsIntel();
  renderDeskPanels();
  drawEquityChart();
  drawPerpEqChart();
  drawPerpPriceChart();
  drawPriceChart();
  drawRsiChart();
  renderNews();
  renderLearning();
  renderSystem();
}}

async function loadPerpChart(sym, live = false) {{
  if (!sym) return;
  SELECTED_PERP_SYM = sym;
  renderPerps();
  if (!LIVE_ORIGIN) {{ drawPerpPriceChart(); return; }}
  try {{
    const res = await fetch('/api/perps/chart?symbol=' + encodeURIComponent(sym) + (live ? '&live=1' : ''));
    if (res.ok) {{
      CURRENT_PERP_CHART = await res.json();
      drawPerpPriceChart();
    }}
  }} catch (e) {{}}
}}

function renderPerps() {{
  const ps = STATE.perps || {{}};
  const tr = STATE.trader || {{}};
  const enabled = ps.enabled !== false;
  const btnT = document.getElementById('btn-perps-toggle');
  if (btnT) btnT.textContent = enabled ? 'השהה PERPS' : 'הפעל PERPS';
  const hdrSub = document.getElementById('perps-sub-hdr');
  if (hdrSub) {{
    hdrSub.textContent = `${{(ps.exchanges || ['okx','hyperliquid']).join(' + ').toUpperCase()}} · מצב ${{(ps.mode || 'paper').toUpperCase()}} · ${{(ps.timeframe || '1h')}} · מקס׳ ×${{ps.max_leverage || 50}} · מחזורים: ${{tr.perps_cycles || 0}}`;
  }}

  const eq = Number(ps.equity || 1000);
  const cash = Number(ps.cash || 0);
  const mrg = Number(ps.margin_used || 0);
  const notl = Number(ps.notional || 0);
  const unr = Number(ps.unrealized_pnl || 0);
  const ov = Number(ps.overall_pnl || 0);
  const pkpis = [
    {{ l: 'הון PERPS (USDC)', v: fmtNum(eq), s: `לא ממומש: ${{fmtSign(unr)}} · DD ${{fmtNum(ps.drawdown_pct || 0, 1)}}%`, c: '' }},
    {{ l: 'מרג׳ין ומינוף חי', v: `×${{fmtNum(ps.avg_leverage || 0, 1)}}`, s: `מרג׳ין ${{fmtNum(mrg)}} | נומינלי $${{Math.round(notl).toLocaleString()}}`, c: '' }},
    {{ l: 'מזומן פנוי', v: fmtNum(cash), s: `פוזיציות: ${{(ps.positions || []).length}} | מינוף שיא ×${{fmtNum(ps.max_leverage_open || 0, 0)}}`, c: '' }},
    {{ l: 'PnL + Funding', v: fmtSign(ov), s: `היום ${{fmtSign(ps.today_pnl || 0)}} · Funding ${{fmtSign(ps.funding_net || 0, 3)}}`, c: ov >= 0 ? 'pos' : 'neg' }},
    {{ l: 'WR / Profit Factor', v: `${{fmtNum(ps.win_rate_pct || 0, 0)}}%`, s: `${{ps.closed_trades || 0}} עסקאות · PF ${{fmtNum(ps.profit_factor || 0, 2)}}`, c: '' }},
  ];
  const kpiEl = document.getElementById('perps-kpi-row');
  if (kpiEl) kpiEl.innerHTML = pkpis.map(k => `<div class="kpi"><div class="kpi-label">${{esc(k.l)}}</div><div class="kpi-val num ${{k.c}}">${{esc(k.v)}}</div><div class="kpi-sub">${{esc(k.s)}}</div></div>`).join('');

  const g = ps.guards || {{}};
  const gBox = document.getElementById('perps-guards-box');
  if (gBox) {{
    const gBars = [
      {{ lbl: 'ניצול Margin מהתיק', txt: `${{fmtNum(g.used_margin_pct || 0, 1)}}% / ${{g.max_margin_pct || 65}}%`, pct: Math.min(100, Number(g.used_margin_pct || 0) / Math.max(1, Number(g.max_margin_pct || 65)) * 100), col: 'var(--accent)' }},
      {{ lbl: 'Drawdown מוגבל', txt: `${{fmtNum(ps.drawdown_pct || 0, 1)}}% / ${{g.dd_limit_pct || 18}}%`, pct: Math.min(100, Number(ps.drawdown_pct || 0) / Math.max(1, Number(g.dd_limit_pct || 18)) * 100), col: 'var(--amber)' }},
      {{ lbl: 'מגן ליקווידציה (Buffer)', txt: `×${{g.liq_buffer_mult || 2.2}} ATR · SL ${{g.sl_atr_mult || 1.7}} / TP ${{g.tp_atr_mult || 3.0}}`, pct: 70, col: 'var(--green)' }},
    ];
    gBox.innerHTML = gBars.map(b => `<div class="bar-row"><div class="bar-top"><span>${{esc(b.lbl)}}</span><span class="num">${{esc(b.txt)}}</span></div><div class="bar-track"><div class="bar-fill" style="width:${{b.pct.toFixed(1)}}%;background:${{b.col}}"></div></div></div>`).join('');
  }}

  const pos = ps.positions || [];
  const posEl = document.getElementById('perps-pos-tbody');
  if (posEl) posEl.innerHTML = pos.length ? pos.map(p => {{
    const u = Number(p.unrealized_pnl || 0);
    const roe = Number(p.roe_pct || 0);
    const sideCls = p.side === 'LONG' ? 'badge-ok' : 'badge-err';
    const liqD = Number(p.liq_distance_pct || 0);
    return `<tr class="clickable" onclick="loadPerpChart('${{esc(p.symbol)}}', true)">
      <td style="color:var(--text);font-weight:600">${{esc(p.symbol)}} <span class="badge badge-mute">${{esc((p.exchange || '').toUpperCase())}}</span></td>
      <td><span class="badge ${{sideCls}}">${{esc(p.side)}}</span></td>
      <td class="num"><span class="badge badge-warn">×${{Number(p.leverage).toFixed(0)}}</span></td>
      <td class="num">$${{fmtNum(p.margin_used, 2)}}</td>
      <td class="num">$${{Math.round(p.notional).toLocaleString()}}</td>
      <td class="num">${{fmtNum(p.entry_price, 4)}}</td>
      <td class="num">${{fmtNum(p.mark_price, 4)}}</td>
      <td class="num" style="color:var(--text-3)">${{fmtNum(p.stop_price, 4)}} / ${{fmtNum(p.target_price, 4)}}</td>
      <td class="num" style="color:${{liqD < 4 ? 'var(--red)' : 'var(--amber)'}}">${{fmtNum(p.liquidation_price, 4)}} (${{liqD.toFixed(1)}}%)</td>
      <td class="num ${{u >= 0 ? 'pos' : 'neg'}}">${{fmtSign(roe, 1)}}% (${{fmtSign(u, 2)}})</td>
    </tr>`;
  }}).join('') : '<tr><td colspan="10" style="text-align:center;color:var(--text-3);padding:18px">אין פוזיציות PERPS פתוחות כרגע</td></tr>';

  const intel = ps.intel || [];
  const q = (document.getElementById('perps-search')?.value || '').trim().toLowerCase();
  const filt = intel.filter(r => !q || String(r.symbol || '').toLowerCase().includes(q));
  const icEl = document.getElementById('perps-intel-cnt');
  if (icEl) icEl.textContent = `${{filt.length}} חוזים חיים`;
  const wlEl = document.getElementById('perps-wl');
  if (wlEl) wlEl.innerHTML = filt.length ? filt.map(r => {{
    const act = r.symbol === SELECTED_PERP_SYM;
    const regCls = r.regime === 'TREND_UP' ? 'badge-ok' : (r.regime === 'TREND_DOWN' ? 'badge-err' : 'badge-info');
    const okxF = r.okx_funding_1h !== null && r.okx_funding_1h !== undefined ? (Number(r.okx_funding_1h)*100).toFixed(4)+'%' : null;
    const hlF = r.hl_funding_1h !== null && r.hl_funding_1h !== undefined ? (Number(r.hl_funding_1h)*100).toFixed(4)+'%' : null;
    const fundTxt = (okxF && hlF) ? `OKX ${{okxF}} | HL ${{hlF}}` : `Fund ${{r.funding_1h ? (Number(r.funding_1h)*100).toFixed(4)+'%' : '0%'}}`;
    return `<div class="wl-item ${{act ? 'active' : ''}}" onclick="loadPerpChart('${{esc(r.symbol)}}', true)">
      <div class="wl-top">
        <div class="wl-q">${{esc(r.symbol)}} <span style="color:var(--text-3);font-weight:400">(${{esc((r.exchange || '').toUpperCase())}})</span></div>
        <span class="badge ${{regCls}}">${{esc(r.regime || 'RANGE')}} · ×${{Number(r.rec_leverage || 10).toFixed(0)}}</span>
      </div>
      <div class="wl-sub">
        <span class="num" style="color:var(--text)">$${{fmtNum(r.price, r.price > 100 ? 2 : 4)}}</span>
        <span class="num">ADX ${{fmtNum(r.adx, 1)}}</span>
        <span class="num">Z ${{fmtSign(r.z_score, 2)}}</span>
        <span class="num">RSI ${{fmtNum(r.rsi, 0)}}</span>
        <span class="num">${{fundTxt}}</span>
      </div>
    </div>`;
  }}).join('') : '<div style="padding:18px;text-align:center;color:var(--text-3)">טרם בוצעה סריקת PERPS — לחץ "מחזור PERPS עכשיו"</div>';

  const trs = ps.recent_trades || [];
  const tcEl = document.getElementById('perps-tr-cnt');
  if (tcEl) tcEl.textContent = `${{trs.length}} אחרונות`;
  const tbEl = document.getElementById('perps-trades-tbody');
  if (tbEl) tbEl.innerHTML = trs.length ? trs.slice(0, 12).map(t => {{
    const rz = Number(t.realized || 0);
    return `<tr>
      <td class="num" style="color:var(--text-3)">${{fmtDateTime(t.ts)}}</td>
      <td style="color:var(--text)">${{esc(t.symbol)}}</td>
      <td>${{esc(t.side)}}</td>
      <td class="num">×${{Number(t.leverage || 1).toFixed(0)}}</td>
      <td class="num ${{rz >= 0 ? 'pos' : 'neg'}}">${{fmtSign(rz, 2)}}</td>
      <td style="color:var(--text-3)">${{esc((t.reason || '').slice(0, 26))}}</td>
    </tr>`;
  }}).join('') : '<tr><td colspan="6" style="text-align:center;color:var(--text-3);padding:16px">אין עסקאות סגורות עדיין</td></tr>';

  const lr = ps.learning_runs || [];
  const lrEl = document.getElementById('perps-learn-tbody');
  if (lrEl) lrEl.innerHTML = lr.length ? lr.slice(0, 8).map(r => `<tr>
    <td class="num" style="color:var(--text-3)">${{fmtDateTime(r.ts)}}</td>
    <td class="num">${{fmtSign(r.baseline_oos, 2)}}%</td>
    <td class="num">${{fmtSign(r.candidate_oos, 2)}}%</td>
    <td class="num">${{(Number(r.consistency || 0)*100).toFixed(0)}}%</td>
    <td>${{r.applied ? '<span class="badge badge-ok">קודם</span>' : '<span class="badge badge-mute">נשמר</span>'}}</td>
  </tr>`).join('') : '<tr><td colspan="5" style="text-align:center;color:var(--text-3);padding:16px">טרם בוצע כיול OOS ל-PERPS</td></tr>';
}}

function drawPerpEqChart() {{
  const canvas = document.getElementById('perps-eq-canvas');
  if (!canvas) return;
  const {{ ctx, w, h }} = prepCanvas(canvas);
  ctx.clearRect(0, 0, w, h);
  const raw = ((STATE.perps && STATE.perps.equity_curve) || []).filter(p => typeof p.equity === 'number');
  if (raw.length < 2) {{
    ctx.fillStyle = '#64748b'; ctx.font = '12px sans-serif'; ctx.textAlign = 'center';
    ctx.fillText('עקומת הון PERPS תיבנה אוטומטית מהמחזור הבא...', w / 2, h / 2);
    return;
  }}
  const pts = raw.map(p => p.equity);
  const minV = Math.min(...pts), maxV = Math.max(...pts);
  const pad = Math.max((maxV - minV) * 0.14, 1);
  const lo = minV - pad, hi = maxV + pad;
  const pxL = 12, pxR = 54, pyT = 12, pyB = 20, gw = w - pxL - pxR, gh = h - pyT - pyB;
  const up = pts[pts.length - 1] >= pts[0];
  const stroke = up ? '#10b981' : '#ef4444';
  const meta = document.getElementById('perps-eq-meta');
  if (meta) meta.textContent = `${{pts[0].toFixed(2)}} -> ${{pts[pts.length-1].toFixed(2)}} (${{fmtSign(pts[pts.length-1]-pts[0])}})`;
  const X = i => pxL + (i / (pts.length - 1)) * gw;
  const Y = v => pyT + gh - ((v - lo) / (hi - lo)) * gh;
  ctx.beginPath();
  pts.forEach((v, i) => i === 0 ? ctx.moveTo(X(i), Y(v)) : ctx.lineTo(X(i), Y(v)));
  ctx.strokeStyle = stroke; ctx.lineWidth = 2; ctx.stroke();
}}

let PERP_HOVER = null;
function drawPerpPriceChart() {{
  const canvas = document.getElementById('perps-price-canvas');
  if (!canvas) return;
  const {{ ctx, w, h }} = prepCanvas(canvas);
  ctx.clearRect(0, 0, w, h);
  const ch = CURRENT_PERP_CHART || {{}};
  const cs = (ch.candles || []).slice(-100);
  const tEl = document.getElementById('perps-chart-title');
  const sEl = document.getElementById('perps-chart-sub');
  if (tEl) tEl.textContent = `${{ch.symbol || SELECTED_PERP_SYM}} Perpetual (${{ch.timeframe || '1h'}})`;
  if (sEl && ch.intel && ch.intel.symbol) {{
    sEl.textContent = `${{(ch.intel.exchange || '').toUpperCase()}} · ${{ch.intel.regime || ''}} · ADX ${{fmtNum(ch.intel.adx, 1)}} · Z ${{fmtSign(ch.intel.z_score, 2)}} · מינוף מומלץ ×${{Number(ch.intel.rec_leverage || 10).toFixed(0)}}`;
  }}
  if (cs.length < 2) {{
    ctx.fillStyle = '#64748b'; ctx.font = '12px sans-serif'; ctx.textAlign = 'center';
    ctx.fillText('אין עדיין נרות לחוזה זה — לחץ "משוך חי"', w / 2, h / 2);
    return;
  }}
  const ov = ch.overlays || {{}};
  const all = [];
  cs.forEach(c => {{ all.push(Number(c.high || c.close)); all.push(Number(c.low || c.close)); }});
  if (ov.stop) all.push(Number(ov.stop));
  if (ov.target) all.push(Number(ov.target));
  if (ov.liq) all.push(Number(ov.liq));
  const minV = Math.min(...all), maxV = Math.max(...all);
  const pad = Math.max((maxV - minV) * 0.12, maxV * 0.002);
  const lo = minV - pad, hi = maxV + pad;
  const pxL = 14, pxR = 66, pyT = 14, pyB = 20, gw = w - pxL - pxR, gh = h - pyT - pyB;
  const X = i => pxL + ((i + 0.5) / cs.length) * gw;
  const Y = v => pyT + gh - ((v - lo) / (hi - lo)) * gh;

  ctx.strokeStyle = 'rgba(255,255,255,0.05)'; ctx.fillStyle = '#64748b'; ctx.font = '10px monospace'; ctx.textAlign = 'left';
  for (let i = 0; i <= 4; i++) {{
    const y = pyT + gh * (i / 4);
    ctx.beginPath(); ctx.moveTo(pxL, y); ctx.lineTo(w - pxR, y); ctx.stroke();
    const v = hi - (hi - lo) * (i / 4);
    ctx.fillText(v > 100 ? v.toFixed(1) : v.toFixed(4), w - pxR + 6, y + 3);
  }}
  const hLn = (v, col, lbl) => {{
    if (!v) return;
    const y = Y(Number(v));
    if (y < pyT || y > pyT + gh) return;
    ctx.save(); ctx.setLineDash([4, 4]); ctx.strokeStyle = col;
    ctx.beginPath(); ctx.moveTo(pxL, y); ctx.lineTo(w - pxR, y); ctx.stroke();
    ctx.fillStyle = col; ctx.fillText(lbl, pxL + 6, y - 4);
    ctx.restore();
  }};
  if (ov.entry) {{
    hLn(ov.target, '#10b981', 'TP ' + Number(ov.target).toFixed(4));
    hLn(ov.entry, '#94a3b8', 'ENTRY ×' + Number(ov.leverage || 1).toFixed(0));
    hLn(ov.stop, '#f59e0b', 'SL ' + Number(ov.stop).toFixed(4));
    hLn(ov.liq, '#ef4444', 'LIQ ' + Number(ov.liq).toFixed(4));
  }}

  const cw = Math.max(2, Math.min(9, (gw / cs.length) * 0.64));
  cs.forEach((c, i) => {{
    const x = X(i);
    const o = Number(c.open || c.close), hiC = Number(c.high || c.close), loC = Number(c.low || c.close), cl = Number(c.close);
    const up = cl >= o;
    const col = up ? '#10b981' : '#ef4444';
    ctx.strokeStyle = col; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(x, Y(hiC)); ctx.lineTo(x, Y(loC)); ctx.stroke();
    const yTop = Y(Math.max(o, cl)), yBot = Y(Math.min(o, cl));
    ctx.fillStyle = col;
    ctx.fillRect(x - cw / 2, yTop, cw, Math.max(1.5, yBot - yTop));
  }});

  const tip = document.getElementById('perps-price-tip');
  if (PERP_HOVER !== null && PERP_HOVER >= 0 && PERP_HOVER < cs.length) {{
    const c = cs[PERP_HOVER];
    const hx = X(PERP_HOVER), hy = Y(Number(c.close));
    ctx.save(); ctx.setLineDash([3, 3]); ctx.strokeStyle = 'rgba(255,255,255,0.28)';
    ctx.beginPath(); ctx.moveTo(hx, pyT); ctx.lineTo(hx, pyT + gh); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(pxL, hy); ctx.lineTo(w - pxR, hy); ctx.stroke();
    ctx.restore();
    const d = c.close > 100 ? 2 : 4;
    if (tip) {{
      tip.style.display = 'block';
      tip.innerHTML = `<span class="num">${{fmtDateTime(c.ts)}}</span> | O <span class="num">${{Number(c.open).toFixed(d)}}</span> H <span class="num">${{Number(c.high).toFixed(d)}}</span> L <span class="num">${{Number(c.low).toFixed(d)}}</span> C <strong class="num">${{Number(c.close).toFixed(d)}}</strong>`;
    }}
  }} else if (tip) {{
    tip.style.display = 'none';
  }}
}}

function renderHeader() {{
  const tr = STATE.trader || {{}};
  const h = STATE.health || {{}};
  const hb = STATE.heartbeat || {{}};
  const cfg = STATE.config || {{}};
  const wp = STATE.world_pulse || {{}};
  const mode = (cfg.execution && cfg.execution.mode) || 'paper';
  const running = Boolean(tr.running);
  const halted = Boolean(STATE.halt || (hb && hb.halted));

  const dot = document.getElementById('live-dot');
  const lbl = document.getElementById('live-label');
  if (halted) {{
    dot.className = 'dot err'; lbl.textContent = 'עצירה פעילה';
  }} else if (running && h.healthy) {{
    dot.className = 'dot ok'; lbl.textContent = 'אוטופיילוט פעיל';
  }} else if (h.healthy) {{
    dot.className = 'dot warn'; lbl.textContent = 'האזנה בלבד';
  }} else {{
    dot.className = 'dot err'; lbl.textContent = 'ממתין לדופק';
  }}

  const btnAp = document.getElementById('btn-toggle-ap');
  if (btnAp) {{
    btnAp.textContent = running ? 'השהה אוטופיילוט' : 'הפעל אוטופיילוט';
    btnAp.className = running ? 'btn' : 'btn btn-primary';
  }}

  const cyc = tr.cycles || hb.cycle || 0;
  const tel = STATE.telemetry || {{}};
  document.getElementById('sub-status').textContent =
    `${{mode.toUpperCase()}} · מחזור #${{cyc}} · ${{(tel.intel || 0)}} שווקים במעקב`;

  const intel = STATE.market_intel || [];
  const aPlus = intel.filter(x => x.setup_tier === 'A+' || x.setup_tier === 'A').length;
  const nearCnt = intel.filter(x => x.status === 'NEAR').length;
  const sent = Number(wp.avg_sentiment || 0);
  const sentCls = sent >= 0.05 ? 'pos' : (sent <= -0.05 ? 'neg' : '');
  document.getElementById('pulse-ribbon').innerHTML = `
    <div class="pulse-group">
      <div class="pulse-item"><span class="dot ${{running ? 'ok' : 'warn'}}"></span><strong>מצב רציף:</strong> <span>${{running ? 'סורק כל ' + Math.round((tr.interval_sec || 180)/60) + ' דק׳' : 'מושהה'}}</span></div>
      <div class="pulse-item"><strong>פיד עולמי:</strong> <span>${{wp.sources || 0}} רשתות · ${{wp.total || tel.news || 0}} כתבות</span></div>
      <div class="pulse-item"><strong>מצב מאקרו:</strong> <span class="${{sentCls}}">${{esc(wp.regime || 'מאוזן')}} (${{fmtSign(sent, 2)}})</span></div>
      <div class="pulse-item"><strong>סטאפים A/A+:</strong> <span class="num">${{aPlus}}</span> · <strong>מתחממים:</strong> <span class="num">${{nearCnt}}</span></div>
    </div>
    <div class="pulse-group">
      <div class="pulse-item"><strong>עדכון גרפים:</strong> <span>${{fmtTime(tr.last_stream_ts)}}</span></div>
      <div class="pulse-item"><strong>אימות DB:</strong> <span>${{tr.last_reconcile_ts ? fmtTime(tr.last_reconcile_ts) : 'במחזור הבא'}}</span></div>
      <div class="pulse-item"><strong>גיבוי אחרון:</strong> <span>${{tr.last_backup_ts ? fmtTime(tr.last_backup_ts) : 'אוטומטי'}}</span></div>
    </div>`;

  const hbBanner = document.getElementById('halt-banner');
  if (halted) {{
    const reason = (STATE.halt && STATE.halt.reason) || (hb && hb.halt_reason) || 'עצירת סיכון פעילה';
    document.getElementById('halt-text').textContent = 'עצירת מסחר פעילה: ' + reason;
    hbBanner.style.display = 'flex';
  }} else {{
    hbBanner.style.display = 'none';
  }}
}}

function renderOverview() {{
  const bank = STATE.bankroll || {{}};
  const today = STATE.today || {{}};
  const overall = STATE.overall || {{}};
  const soak = STATE.soak || {{days: 0, target_days: 7}};

  const eq = Number(bank.equity || 0);
  const cash = Number(bank.cash || 0);
  const exp = Number(bank.exposure || 0);
  const expPct = eq > 0 ? (exp / eq * 100) : 0;
  const unr = Number(bank.unrealized_pnl || 0);
  const totPnl = Number(overall.realized_pnl || 0);
  const wr = Number(overall.win_rate_pct || 0);
  const pf = overall.profit_factor ? Number(overall.profit_factor).toFixed(2) : '—';

  const kpis = [
    {{ label: 'הון נקי (USDC)', val: fmtNum(eq), sub: `לא ממומש: ${{fmtSign(unr)}}`, cls: '' }},
    {{ label: 'מזומן זמין', val: fmtNum(cash), sub: `חשיפה בשוק: ${{fmtNum(exp)}} (${{expPct.toFixed(0)}}%)`, cls: '' }},
    {{ label: 'PnL מצטבר', val: fmtSign(totPnl), sub: `היום: ${{fmtSign(today.realized_pnl || 0)}} · עמלות ${{fmtNum(overall.fees || 0)}}`, cls: totPnl >= 0 ? 'pos' : 'neg' }},
    {{ label: 'שיעור הצלחה', val: `${{wr.toFixed(0)}}%`, sub: `${{overall.exits || 0}} סגורות · Profit Factor ${{pf}}`, cls: '' }},
    {{ label: 'צבירת הוכחה (Soak)', val: `${{soak.days || 0}}/${{soak.target_days || 7}}`, sub: `פוזיציות פתוחות: ${{bank.open_positions || 0}}`, cls: '' }},
  ];
  document.getElementById('kpi-row').innerHTML = kpis.map(k => `
    <div class="kpi">
      <div class="kpi-label">${{esc(k.label)}}</div>
      <div class="kpi-val num ${{k.cls}}">${{esc(k.val)}}</div>
      <div class="kpi-sub">${{esc(k.sub)}}</div>
    </div>`).join('');

  // מדדי סיכון + DD Throttling
  const g = STATE.guards || {{}};
  const dlUsed = Number(g.daily_loss_used || 0);
  const dlLim = Math.max(Number(g.daily_loss_limit || 1), 0.01);
  const ddPct = Number(g.drawdown_pct || 0);
  const ddLim = Math.max(Number(g.drawdown_limit_pct || 20), 0.01);
  const ddThrPct = ((STATE.config && STATE.config.risk && STATE.config.risk.drawdown_throttle_pct) || 0.05) * 100;
  const posOpen = Number(bank.open_positions || 0);
  const posLim = Math.max(posOpen + Number(g.positions_room || 0), 1);
  const maxExp = exp + Number(g.exposure_room || 0);

  const bars = [
    {{ lbl: 'מגבלת הפסד יומי', txt: `${{fmtNum(dlUsed)}} / ${{fmtNum(dlLim)}} USDC`, pct: Math.min(100, Math.max(0, dlUsed / dlLim * 100)), color: 'var(--green)' }},
    {{ lbl: `Drawdown (Throttle ב-${{ddThrPct.toFixed(0)}}%)`, txt: `${{ddPct.toFixed(2)}}% / ${{ddLim.toFixed(0)}}%`, pct: Math.min(100, ddPct / ddLim * 100), color: ddPct >= ddThrPct ? 'var(--amber)' : 'var(--accent)' }},
    {{ lbl: 'ניצול תקציב חשיפה', txt: `${{fmtNum(exp)}} / ${{fmtNum(maxExp)}} USDC`, pct: maxExp > 0 ? Math.min(100, exp / maxExp * 100) : 0, color: 'var(--accent)' }},
    {{ lbl: 'פוזיציות פתוחות', txt: `${{posOpen}} / ${{posLim}}`, pct: Math.min(100, posOpen / posLim * 100), color: 'var(--accent)' }},
  ];
  document.getElementById('risk-bars').innerHTML = bars.map(b => `
    <div class="bar-row">
      <div class="bar-top"><span>${{esc(b.lbl)}}</span><span class="num">${{esc(b.txt)}}</span></div>
      <div class="bar-track"><div class="bar-fill" style="width:${{b.pct.toFixed(1)}}%;background:${{b.color}}"></div></div>
    </div>`).join('');

  // פוזיציות פתוחות עם מד SL ↔ Entry ↔ TP
  const pos = STATE.positions || [];
  document.getElementById('pos-tbody').innerHTML = pos.length ? pos.map(p => {{
    const u = p.unrealized_pnl;
    const upct = p.unrealized_pct;
    const uCls = (u || 0) >= 0 ? 'pos' : 'neg';
    const sl = Number(p.stop_price || 0);
    const tp = Number(p.target_price || 0);
    const mk = Number(p.mark_price ?? p.avg_price ?? 0);
    const span = Math.max(tp - sl, 0.01);
    const pctPos = Math.max(0, Math.min(100, ((mk - sl) / span) * 100));
    const entryPct = Math.max(0, Math.min(100, ((Number(p.avg_price || 0) - sl) / span) * 100));
    const barCol = mk >= Number(p.avg_price || 0) ? 'var(--green)' : 'var(--amber)';

    return `<tr class="clickable" onclick="switchToMarket('${{esc(p.token_id)}}')">
      <td class="q-cell">${{esc((p.question || p.token_id).slice(0, 56))}}</td>
      <td class="num">${{fmtNum(p.size, 1)}}</td>
      <td class="num">${{fmtNum(p.avg_price, 3)}}</td>
      <td class="num">${{p.mark_price !== null && p.mark_price !== undefined ? fmtNum(p.mark_price, 3) : '—'}}</td>
      <td>
        <div class="range-meter">
          <span class="num" style="font-size:10.5px;color:var(--red)">${{sl ? sl.toFixed(2) : '—'}}</span>
          <div class="range-track">
            <div class="range-fill" style="left:${{Math.min(entryPct, pctPos).toFixed(1)}}%;width:${{Math.abs(pctPos - entryPct).toFixed(1)}}%;background:${{barCol}}"></div>
            <div class="range-pin" style="left:${{pctPos.toFixed(1)}}%" title="מחיר נוכחי"></div>
          </div>
          <span class="num" style="font-size:10.5px;color:var(--green)">${{tp ? tp.toFixed(2) : '—'}}</span>
        </div>
      </td>
      <td class="num ${{uCls}}">${{u !== null && u !== undefined ? `${{fmtSign(u)}} (${{fmtSign(upct, 1)}}%)` : '—'}}</td>
      <td class="num">${{fmtNum(p.age_hours, 1)}}h</td>
    </tr>`;
  }}).join('') : '<tr><td colspan="7" style="text-align:center;color:var(--text-3);padding:20px">אין כרגע פוזיציות פתוחות</td></tr>';

  // Live Execution & Decision Tape (שילוב סיגנלים חריגים + אירועי מערכת)
  const evs = (STATE.events || []).slice(0, 6);
  const sigS = (STATE.signals || []).filter(s => s.direction !== 'FLAT' || (s.z !== null && Math.abs(Number(s.z)) >= 1.5)).slice(0, 6);
  const tapeItems = [
    ...sigS.map(s => ({{
      ts: s.ts,
      cls: s.direction !== 'FLAT' ? 'badge-ok' : 'badge-warn',
      kind: s.direction !== 'FLAT' ? `${{s.direction}} ${{s.setup_tier || ''}}` : `Z=${{fmtSign(s.z, 1)}}`,
      msg: `${{(s.question || s.token_id || '').slice(0, 38)}} — ${{s.reason || ''}}`,
      tok: s.token_id,
    }})),
    ...evs.map(e => ({{
      ts: e.ts,
      cls: e.level === 'ERROR' ? 'badge-err' : (e.level === 'WARNING' ? 'badge-warn' : 'badge-info'),
      kind: e.kind || 'event',
      msg: e.msg || '',
      tok: '',
    }})),
  ].sort((a, b) => Number(b.ts || 0) - Number(a.ts || 0)).slice(0, 10);
  document.getElementById('tape-meta').textContent = `${{tapeItems.length}} החלטות ואירועים אחרונים`;
  document.getElementById('decision-tape').innerHTML = tapeItems.length ? tapeItems.map(it => `
    <div class="tape-item" ${{it.tok ? `style="cursor:pointer" onclick="switchToMarket('${{esc(it.tok)}}')"` : ''}}>
      <span class="num" style="color:var(--text-3);flex-shrink:0">${{fmtTime(it.ts)}}</span>
      <span class="badge ${{it.cls}}">${{esc(it.kind)}}</span>
      <span style="color:var(--text-2)">${{esc(it.msg)}}</span>
    </div>`).join('') : '<div style="padding:18px;text-align:center;color:var(--text-3)">יופיעו החלטות ואירועים בזמן אמת</div>';

  // עסקאות סגורות
  const trs = (STATE.recent_trades || []).slice(0, 10);
  document.getElementById('trades-meta').textContent = `${{trs.length}} אחרונות`;
  document.getElementById('trades-tbody').innerHTML = trs.length ? trs.map(t => {{
    const rz = Number(t.realized || 0);
    return `<tr>
      <td class="num" style="color:var(--text-3)">${{fmtDateTime(t.ts)}}</td>
      <td style="color:var(--text)">${{esc((t.question || '').slice(0, 32))}}</td>
      <td class="num">${{fmtNum(t.size, 1)}}</td>
      <td class="num">${{fmtNum(t.price, 3)}}</td>
      <td class="num ${{rz >= 0 ? 'pos' : 'neg'}}">${{fmtSign(rz)}}</td>
      <td style="color:var(--text-3)">${{esc((t.reason || '').slice(0, 24))}}</td>
    </tr>`;
  }}).join('') : '<tr><td colspan="6" style="text-align:center;color:var(--text-3);padding:18px">אין עסקאות סגורות עדיין</td></tr>';
}}

function renderMarketsIntel() {{
  const rows = STATE.market_intel || [];
  const qSearch = (document.getElementById('wl-search')?.value || '').trim().toLowerCase();
  const filtered = rows.filter(r => {{
    if (INTEL_FILTER === 'OPEN' && r.status !== 'OPEN') return false;
    if (INTEL_FILTER === 'NEAR' && r.status !== 'NEAR' && r.status !== 'CANDIDATE') return false;
    if (INTEL_FILTER === 'APLUS' && r.setup_tier !== 'A+' && r.setup_tier !== 'A') return false;
    if (INTEL_FILTER === 'CATALYST_BLOCK' && r.status !== 'CATALYST_BLOCK') return false;
    if (qSearch && !((r.question || '').toLowerCase().includes(qSearch) || (r.sector || '').toLowerCase().includes(qSearch))) return false;
    return true;
  }});

  document.getElementById('wl-count').textContent = `${{filtered.length}} מתוך ${{rows.length}}`;
  if (!SELECTED_TOKEN && filtered.length) SELECTED_TOKEN = filtered[0].token_id;

  const statusTag = (r) => {{
    if (r.status === 'OPEN') return '<span class="badge badge-info">פתוחה</span>';
    if (r.status === 'BUY') return '<span class="badge badge-ok">כניסה</span>';
    if (r.status === 'CATALYST_BLOCK') return '<span class="badge badge-warn">חסימת קטליזטור</span>';
    if (r.status === 'CANDIDATE') return '<span class="badge badge-ok">מועמד</span>';
    if (r.status === 'NEAR') return '<span class="badge badge-info">מתחמם</span>';
    if (r.setup_tier === 'A+') return '<span class="badge badge-ok">A+</span>';
    if (r.setup_tier === 'A') return '<span class="badge badge-info">A</span>';
    return '<span class="badge badge-mute">מעקב</span>';
  }};

  document.getElementById('wl-list').innerHTML = filtered.length ? filtered.map(r => {{
    const isAct = r.token_id === SELECTED_TOKEN;
    const z = r.z_score;
    const vr = Number(r.volume_ratio || 1);
    const chg24 = r.chg_24h !== null && r.chg_24h !== undefined ? fmtSign(r.chg_24h * 100, 1) + '%' : '—';
    return `<div class="wl-item ${{isAct ? 'active' : ''}}" onclick="loadChart('${{esc(r.token_id)}}', true)">
      <div class="wl-top">
        <div class="wl-q">${{esc((r.question || '').slice(0, 62))}}</div>
        ${{statusTag(r)}}
      </div>
      <div class="wl-sub">
        <span class="num" style="color:var(--text)">${{fmtNum(r.price, 3)}}</span>
        <span class="num">Z ${{z !== null && z !== undefined ? fmtSign(z, 2) : '—'}}</span>
        <span class="num">RSI ${{r.rsi !== null && r.rsi !== undefined ? Number(r.rsi).toFixed(0) : '—'}}</span>
        <span class="num" style="color:${{vr >= 4 ? 'var(--amber)' : 'var(--text-3)'}}">${{vr.toFixed(1)}}x</span>
        <span class="num">${{chg24}}</span>
      </div>
    </div>`;
  }}).join('') : '<div style="padding:20px;text-align:center;color:var(--text-3)">לא נמצאו שווקים מתאימים</div>';
}}

function renderDeskPanels() {{
  const ch = CURRENT_CHART || {{}};
  const intel = ch.intel || (STATE.market_intel || []).find(x => x.token_id === (ch.token_id || SELECTED_TOKEN)) || null;
  const pos = ch.position || null;
  const title = (pos && pos.question) || ch.question || (intel && intel.question) || 'בחר שוק מהרדאר';
  document.getElementById('desk-title').textContent = title;
  document.getElementById('desk-sub').textContent = intel
    ? `סקטור: ${{intel.sector}} · נפח 24ש׳: $${{Math.round(intel.volume_24h || 0).toLocaleString()}} · תאוצת נפח: ${{Number(intel.volume_ratio || 1).toFixed(1)}}x`
    : 'גרף מחיר וסיגנל בזמן אמת';

  // תיזת סוחר מקצועי
  const tier = (intel && intel.setup_tier) || 'B';
  document.getElementById('thesis-badge').innerHTML = intel
    ? `<span class="badge ${{tier === 'A+' ? 'badge-ok' : (tier === 'A' ? 'badge-info' : 'badge-mute')}}">Setup ${{esc(tier)}}</span>`
    : '—';

  const mNews = ch.matched_news || [];
  if (intel) {{
    const spEdge = (intel.edge_net && intel.edge_net > 0 && intel.spread) ? (intel.spread / intel.edge_net).toFixed(2) + 'x' : '—';
    const items = [
      ['Z-Score (24h)', intel.z_score !== null && intel.z_score !== undefined ? fmtSign(intel.z_score, 2) : '—'],
      ['RSI (14)', intel.rsi !== null && intel.rsi !== undefined ? Number(intel.rsi).toFixed(1) : '—'],
      ['Microprice / Mid', `${{intel.microprice ? Number(intel.microprice).toFixed(3) : '—'}} / ${{fmtNum(intel.price, 3)}}`],
      ['Spread / Net Edge', `${{fmtNum(intel.spread, 3)}} / ${{spEdge}}`],
      ['שינוי 1ש׳ / 6ש׳ / 24ש׳', `${{intel.chg_1h !== null ? fmtSign(intel.chg_1h*100,1)+'%' : '—'}} · ${{intel.chg_6h !== null ? fmtSign(intel.chg_6h*100,1)+'%' : '—'}} · ${{intel.chg_24h !== null ? fmtSign(intel.chg_24h*100,1)+'%' : '—'}}`],
      ['החלטת הבוט', intel.reason || intel.status || '—'],
    ];
    document.getElementById('desk-thesis').innerHTML = `
      <div class="kv-list" style="grid-template-columns:1fr">${{items.map(([k, v]) => `<div class="kv-item"><span class="kv-k">${{esc(k)}}</span><span class="kv-v num">${{esc(v)}}</span></div>`).join('')}}</div>
      <div style="margin-top:10px;font-size:11.5px;color:var(--text-3)">
        ${{mNews.length ? 'כותרות חדשות קשורות: ' + mNews.slice(0, 2).map(t => `<div style="color:var(--text-2);margin-top:3px">• ${{esc(t)}}</div>`).join('') : 'אין ידיעות מתפרצות ישירות על שוק זה.'}}
      </div>`;
  }} else {{
    document.getElementById('desk-thesis').innerHTML = '<div style="color:var(--text-3);font-size:12px">בחר שוק מהרשימה לצפייה בניתוח הטכני והחדשותי המלא.</div>';
  }}

  // סולמית ספר פקודות
  const lv = ch.book_levels || null;
  const bk = (ch.books && ch.books.length) ? ch.books[ch.books.length - 1] : null;
  document.getElementById('ob-meta').textContent = bk ? `Bid ${{fmtNum(bk.best_bid, 3)}} / Ask ${{fmtNum(bk.best_ask, 3)}} · Imb ${{fmtSign(bk.imbalance, 2)}}` : 'Snapshot';
  if (lv && ((lv.bids && lv.bids.length) || (lv.asks && lv.asks.length))) {{
    const allSz = [...(lv.bids || []), ...(lv.asks || [])].map(x => Number(x[1] || 0));
    const maxSz = Math.max(...allSz, 1);
    const bidRows = (lv.bids || []).map(([p, s]) => `<div class="ob-row ob-bid"><div class="ob-bar" style="width:${{(s/maxSz*100).toFixed(0)}}%"></div><span class="num pos">${{Number(p).toFixed(3)}}</span><span class="num">${{Number(s).toFixed(0)}}</span></div>`).join('');
    const askRows = (lv.asks || []).map(([p, s]) => `<div class="ob-row ob-ask"><div class="ob-bar" style="width:${{(s/maxSz*100).toFixed(0)}}%"></div><span class="num neg">${{Number(p).toFixed(3)}}</span><span class="num">${{Number(s).toFixed(0)}}</span></div>`).join('');
    document.getElementById('desk-ob').innerHTML = `<div class="ob-grid"><div><div style="font-size:11px;color:var(--text-3);margin-bottom:5px">קונים (Bids)</div>${{bidRows}}</div><div><div style="font-size:11px;color:var(--text-3);margin-bottom:5px">מוכרים (Asks)</div>${{askRows}}</div></div>`;
  }} else if (bk) {{
    const tot = Math.max(Number(bk.bid_depth || 0) + Number(bk.ask_depth || 0), 1);
    const bPct = (Number(bk.bid_depth || 0) / tot * 100);
    document.getElementById('desk-ob').innerHTML = `
      <div class="bar-row">
        <div class="bar-top"><span>עומק קונים (Bids)</span><span class="num pos">$${{Math.round(bk.bid_depth || 0)}} (${{bPct.toFixed(0)}}%)</span></div>
        <div class="bar-track"><div class="bar-fill" style="width:${{bPct.toFixed(0)}}%;background:var(--green)"></div></div>
      </div>
      <div class="bar-row">
        <div class="bar-top"><span>עומק מוכרים (Asks)</span><span class="num neg">$${{Math.round(bk.ask_depth || 0)}} (${{(100-bPct).toFixed(0)}}%)</span></div>
        <div class="bar-track"><div class="bar-fill" style="width:${{(100-bPct).toFixed(0)}}%;background:var(--red)"></div></div>
      </div>
      <div style="font-size:11px;color:var(--text-3);margin-top:8px">לחץ על "משוך חי" לטעינת 6 שכבות העומק המלאות בזמן אמת.</div>`;
  }} else {{
    document.getElementById('desk-ob').innerHTML = '<div style="color:var(--text-3);font-size:12px">אין עדיין צילום ספר פקודות לשוק זה.</div>';
  }}
}}

function renderNews() {{
  const wp = STATE.world_pulse || {{}};
  const byCat = wp.by_category || {{}};
  const byReg = wp.by_region || {{}};
  const sent = Number(wp.avg_sentiment || 0);
  document.getElementById('news-pulse-kpis').innerHTML = [
    {{ l: 'פיד גלובלי', v: `${{wp.sources || 0}} רשתות`, s: `${{wp.total || 0}} כתבות אחרונות`, c: '' }},
    {{ l: 'משטר חדשות עולמי', v: wp.regime || 'מאוזן', s: `סנטימנט ממוצע: ${{fmtSign(sent, 2)}}`, c: sent >= 0.05 ? 'pos' : (sent <= -0.05 ? 'neg' : '') }},
    {{ l: 'התראות קטליזטור', v: String(wp.catalysts || 0), s: 'כתבות בעלות השפעה >= 0.45', c: '' }},
    {{ l: 'אסיה ומזה״ת', v: String((byReg['אסיה'] || 0) + (byReg['מזרח תיכון'] || 0)), s: `אסיה ${{byReg['אסיה'] || 0}} · מזה״ת ${{byReg['מזרח תיכון'] || 0}}`, c: '' }},
    {{ l: 'אמריקה, אירופה וספורט', v: String((byReg['אמריקה ושווקים'] || 0) + (byReg['אירופה'] || 0)), s: `ספורט ${{byReg['ספורט'] || 0}} · קריפטו ${{byReg['קריפטו'] || 0}}`, c: '' }},
  ].map(x => `<div class="kpi"><div class="kpi-label">${{esc(x.l)}}</div><div class="kpi-val ${{x.c}}" style="font-size:18px">${{esc(x.v)}}</div><div class="kpi-sub">${{esc(x.s)}}</div></div>`).join('');

  const news = STATE.news || [];
  const q = (document.getElementById('news-search')?.value || '').trim().toLowerCase();
  const filtered = news.filter(n => {{
    if (NEWS_FILTER === 'CATALYST' && Number(n.impact || 0) < 0.45) return false;
    else if (NEWS_FILTER === 'MATCHED' && !n.matched_tokens) return false;
    else if (NEWS_FILTER.startsWith('REG:') && (n.region || '') !== NEWS_FILTER.slice(4)) return false;
    else if (NEWS_FILTER === 'sports' && n.category !== 'sports' && (n.region || '') !== 'ספורט') return false;
    if (q && !((n.title || '').toLowerCase().includes(q) || (n.source || '').toLowerCase().includes(q) || (n.region || '').toLowerCase().includes(q))) return false;
    return true;
  }});

  document.getElementById('news-list').innerHTML = filtered.length ? filtered.slice(0, 80).map(n => {{
    const s = Number(n.sentiment || 0);
    const imp = Number(n.impact || 0);
    const sBadge = s >= 0.15 ? '<span class="badge badge-ok">חיובי</span>'
                 : s <= -0.15 ? '<span class="badge badge-err">שלילי</span>'
                 : '<span class="badge badge-mute">נייטרלי</span>';
    const impBadge = imp >= 0.45 ? `<span class="badge badge-warn">השפעה ${{imp.toFixed(2)}}</span>` : '';
    return `<div class="news-item">
      <div>
        <div class="news-title">${{esc(n.title)}}</div>
        <div class="news-meta">
          <strong style="color:var(--text-2)">${{esc(n.source || n.category || 'RSS')}}</strong>
          ${{n.region ? `<span class="badge badge-mute">${{esc(n.region)}}</span>` : ''}}
          <span>${{esc(n.category || 'world')}}</span>
          <span class="num">${{fmtDateTime(n.ts)}}</span>
          ${{n.matched_tokens ? '<span style="color:var(--accent)">קשור לשוק פתוח/במעקב</span>' : ''}}
        </div>
      </div>
      <div style="display:flex;gap:5px;flex-shrink:0">${{impBadge}}${{sBadge}}</div>
    </div>`;
  }}).join('') : '<div style="padding:20px;text-align:center;color:var(--text-3)">אין כתבות תואמות לסינון הנוכחי</div>';
}}

function renderLearning() {{
  const lr = STATE.learning || {{}};
  const st = lr.stats || {{}};
  const insights = lr.insights || [];
  const runs = lr.runs || [];

  const rawEval = Number(st.raw_evaluated || 0);
  const uniqEval = Number(st.total_evaluated || 0);
  document.getElementById('learn-total').textContent =
    rawEval > uniqEval
      ? `${{uniqEval}} אותות הוערכו (מתוך ${{rawEval}} דגימות)`
      : `${{uniqEval}} אותות הוערכו`;
  document.getElementById('learn-insights').innerHTML = insights.length
    ? '<ul style="margin:0;padding-right:18px;color:var(--text-2);font-size:12px">' +
      insights.map(x => `<li style="margin-bottom:5px">${{esc(x)}}</li>`).join('') + '</ul>'
    : '<div style="color:var(--text-3);font-size:12px">הבוט אוגר תוצאות אותות על פני 6ש׳ / 24ש׳ / 48ש׳ לכיול Walk-Forward.</div>';

  const zMap = st.by_z_bucket || {{}};
  const zKeys = Object.keys(zMap);
  document.getElementById('learn-z-tbody').innerHTML = zKeys.length ? zKeys.map(k => {{
    const row = zMap[k] || {{}};
    const hit = row.hit_latest_pct;
    const mean = row.mean_latest;
    return `<tr>
      <td class="num" style="color:var(--text)">${{esc(k)}}</td>
      <td class="num">${{row.n_6h || 0}}</td>
      <td class="num">${{row.n_24h || 0}}</td>
      <td class="num">${{row.n_48h || 0}}</td>
      <td class="num">${{hit !== null && hit !== undefined ? hit + '%' : '—'}}</td>
      <td class="num ${{(mean || 0) >= 0 ? 'pos' : 'neg'}}">${{mean !== null && mean !== undefined ? fmtSign(mean, 4) : '—'}}</td>
    </tr>`;
  }}).join('') : '<tr><td colspan="6" style="text-align:center;color:var(--text-3);padding:16px">אין נתוני הערכה עדיין</td></tr>';

  document.getElementById('learn-runs-tbody').innerHTML = runs.length ? runs.slice(0, 8).map(r => `<tr>
    <td class="num" style="color:var(--text-3)">${{fmtDateTime(r.ts)}}</td>
    <td class="num">${{fmtSign(r.baseline_oos)}}</td>
    <td class="num">${{fmtSign(r.candidate_oos)}}</td>
    <td class="num">${{((Number(r.consistency || 0)) * 100).toFixed(0)}}%</td>
    <td>${{r.applied ? '<span class="badge badge-ok">קודם</span>' : '<span class="badge badge-mute">נשמר</span>'}}</td>
  </tr>`).join('') : '<tr><td colspan="5" style="text-align:center;color:var(--text-3);padding:16px">לא רצו עדיין מחזורי כיול</td></tr>';
}}

function renderSystem() {{
  const ap = STATE.autopilot || [];
  document.getElementById('ap-meta').textContent = `${{ap.length}} משימות אחרונות`;
  document.getElementById('ap-tbody').innerHTML = ap.length ? ap.slice(0, 12).map(a => {{
    const cls = a.status === 'ok' ? 'badge-ok' : (a.status === 'fixed' ? 'badge-info' : 'badge-warn');
    return `<tr>
      <td class="num" style="color:var(--text-3)">${{fmtDateTime(a.ts)}}</td>
      <td style="color:var(--text)">${{esc(a.task)}}</td>
      <td><span class="badge ${{cls}}">${{esc(a.status)}}</span></td>
      <td>${{esc(a.summary)}}</td>
    </tr>`;
  }}).join('') : '<tr><td colspan="4" style="text-align:center;color:var(--text-3);padding:18px">משימות האוטופיילוט יתועדו כאן אוטומטית</td></tr>';

  const rd = STATE.readiness || {{}};
  document.getElementById('ready-summary').textContent = (rd.summary || '—').replace(/[\\u{{1F300}}-\\u{{1FAFF}}\\u2600-\\u27BF]/gu, '').trim();
  const checks = rd.checks || [];
  document.getElementById('ready-tbody').innerHTML = checks.length ? checks.map(c => {{
    const cls = c.status === 'ok' ? 'badge-ok' : (c.status === 'warn' ? 'badge-warn' : 'badge-err');
    const lbl = c.status === 'ok' ? 'תקין' : (c.status === 'warn' ? 'אזהרה' : 'חסר');
    return `<tr>
      <td style="color:var(--text)">${{esc(c.label || c.id || c.name || '')}}</td>
      <td><span class="badge ${{cls}}">${{lbl}}</span></td>
      <td>${{esc(c.detail)}}</td>
    </tr>`;
  }}).join('') : '<tr><td colspan="3" style="text-align:center;color:var(--text-3);padding:18px">אין בדיקות מוכנות</td></tr>';

  const an = STATE.analytics || {{}};
  const ps = an.portfolio_summary || {{}};
  const wf = an.walkforward || {{}};
  const metrics = [
    ['תשואת פורטפוליו נטו', ps.return_pct || '—'],
    ['הון סופי (מ-1000)', ps.final_equity ? ps.final_equity + ' USDC' : '—'],
    ['Profit Factor', ps.profit_factor || '—'],
    ['Sharpe Ratio', ps.sharpe || '—'],
    ['Max Drawdown', ps.max_dd || '—'],
    ['שיעור הצלחה', ps.win_rate || '—'],
    ['OOS Walk-Forward', wf.total_oos_pnl !== undefined ? fmtSign(wf.total_oos_pnl) + ' USDC' : (wf.oos_pnl !== undefined ? fmtSign(wf.oos_pnl) + ' USDC' : '—')],
    ['התמדת חלונות OOS', wf.consistency !== undefined ? (Number(wf.consistency) * 100).toFixed(0) + '%' : '—'],
  ];
  document.getElementById('analytics-box').innerHTML = `<div class="kv-list">
    ${{metrics.map(([k, v]) => `<div class="kv-item"><span class="kv-k">${{esc(k)}}</span><span class="kv-v num">${{esc(v)}}</span></div>`).join('')}}
  </div>`;

  const cfg = STATE.config || {{}};
  const ex = cfg.execution || {{}};
  const sig = cfg.signal || {{}};
  const rk = cfg.risk || {{}};
  const nw = cfg.news || {{}};
  const apc = cfg.autopilot || {{}};
  document.getElementById('cfg-mode').textContent = (ex.mode || 'paper').toUpperCase();
  const cfgItems = [
    ['מנוע + RSI Confluence', `${{sig.engine || 'meanrev'}} (RSI <= ${{sig.rsi_max || 'off'}})`],
    ['סף כניסה / ספרד-ל-Edge', `Z>=${{sig.z_entry || 1.8}} / <=${{sig.max_spread_to_edge || 'off'}}x`],
    ['יעד / סטופ / Time Stop', `+${{sig.take_profit || 0.05}} / -${{sig.stop_loss || 0.08}} / ${{sig.time_stop_hours || 48}}h`],
    ['Kelly / סיכון / DD Throttle', `${{((rk.kelly_fraction || 0.25)*100).toFixed(0)}}% / ${{((rk.risk_per_trade_pct || 0.02)*100).toFixed(1)}}% / ${{(Number(rk.drawdown_throttle_pct||0.05)*100).toFixed(0)}}%`],
    ['תקרת חשיפה / פוזיציות', `${{((rk.max_total_exposure_pct || 0.4)*100).toFixed(0)}}% / ${{rk.max_open_positions || 5}}`],
    ['תקרת סקטור / קירור', `מקס' ${{rk.max_positions_per_sector || 2}} לסקטור · קירור ${{rk.cooldown_minutes || 0}}m`],
    ['מגן חדשות / יציאת חירום', `impact>=${{nw.spike_impact_threshold || 0.65}} / exit>=${{nw.emergency_exit_impact || 0.85}}`],
    ['זינוק נפח שבועי', `${{nw.volume_spike_ratio || 6}}x`],
    ['תדירות אוטופיילוט', `מסחר ${{apc.trade_interval_sec || 180}}s · גיבוי ${{Math.round((apc.backup_interval_sec || 14400)/3600)}}h`],
  ];
  document.getElementById('cfg-box').innerHTML = `<div class="kv-list">
    ${{cfgItems.map(([k, v]) => `<div class="kv-item"><span class="kv-k">${{esc(k)}}</span><span class="kv-v num">${{esc(v)}}</span></div>`).join('')}}
  </div>`;
}}

/* --- Interactive Canvas Charts with Crosshair --- */
function prepCanvas(canvas) {{
  const rect = canvas.parentElement.getBoundingClientRect();
  const w = Math.max(280, Math.floor(rect.width));
  const h = Math.max(70, Math.floor(rect.height));
  const dpr = window.devicePixelRatio || 1;
  canvas.width = w * dpr;
  canvas.height = h * dpr;
  const ctx = canvas.getContext('2d');
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  return {{ ctx, w, h }};
}}

let EQ_HOVER = null;
function drawEquityChart() {{
  const canvas = document.getElementById('eq-canvas');
  if (!canvas) return;
  const {{ ctx, w, h }} = prepCanvas(canvas);
  const raw = (STATE.equity_curve || []).filter(p => typeof p.equity === 'number');
  ctx.clearRect(0, 0, w, h);

  if (raw.length < 2) {{
    ctx.fillStyle = '#64748b'; ctx.font = '12px sans-serif'; ctx.textAlign = 'center';
    ctx.fillText('אוסף נקודות הון לעקומה חיה...', w / 2, h / 2);
    return;
  }}

  const pts = raw.map(p => p.equity);
  const minV = Math.min(...pts), maxV = Math.max(...pts);
  const pad = Math.max((maxV - minV) * 0.14, 1);
  const lo = minV - pad, hi = maxV + pad;
  const pxL = 12, pxR = 54, pyT = 12, pyB = 20;
  const gw = w - pxL - pxR, gh = h - pyT - pyB;
  const up = pts[pts.length - 1] >= pts[0];
  const stroke = up ? '#10b981' : '#ef4444';

  document.getElementById('eq-meta').textContent = `${{pts[0].toFixed(2)}} -> ${{pts[pts.length - 1].toFixed(2)}} (${{fmtSign(pts[pts.length - 1] - pts[0])}})`;

  ctx.strokeStyle = 'rgba(255,255,255,0.05)'; ctx.lineWidth = 1;
  ctx.fillStyle = '#64748b'; ctx.font = '11px monospace'; ctx.textAlign = 'left';
  for (let i = 0; i <= 3; i++) {{
    const y = pyT + gh * (i / 3);
    const val = hi - (hi - lo) * (i / 3);
    ctx.beginPath(); ctx.moveTo(pxL, y); ctx.lineTo(w - pxR, y); ctx.stroke();
    ctx.fillText(val.toFixed(1), w - pxR + 6, y + 4);
  }}

  const X = (i) => pxL + (i / (pts.length - 1)) * gw;
  const Y = (v) => pyT + gh - ((v - lo) / (hi - lo)) * gh;

  const grad = ctx.createLinearGradient(0, pyT, 0, pyT + gh);
  grad.addColorStop(0, up ? 'rgba(16,185,129,0.22)' : 'rgba(239,68,68,0.22)');
  grad.addColorStop(1, 'rgba(16,185,129,0.0)');

  ctx.beginPath();
  pts.forEach((v, i) => i === 0 ? ctx.moveTo(X(i), Y(v)) : ctx.lineTo(X(i), Y(v)));
  ctx.strokeStyle = stroke; ctx.lineWidth = 2; ctx.stroke();

  ctx.lineTo(X(pts.length - 1), pyT + gh);
  ctx.lineTo(X(0), pyT + gh);
  ctx.closePath(); ctx.fillStyle = grad; ctx.fill();

  const tip = document.getElementById('eq-tip');
  if (EQ_HOVER !== null && EQ_HOVER >= 0 && EQ_HOVER < raw.length) {{
    const hx = X(EQ_HOVER), hy = Y(pts[EQ_HOVER]);
    ctx.save(); ctx.setLineDash([3, 3]); ctx.strokeStyle = 'rgba(255,255,255,0.25)';
    ctx.beginPath(); ctx.moveTo(hx, pyT); ctx.lineTo(hx, pyT + gh); ctx.stroke();
    ctx.restore();
    ctx.beginPath(); ctx.arc(hx, hy, 4, 0, Math.PI * 2); ctx.fillStyle = stroke; ctx.fill();
    tip.style.display = 'block';
    tip.innerHTML = `<span class="num">${{pts[EQ_HOVER].toFixed(2)}} USDC</span> · ${{fmtDateTime(raw[EQ_HOVER].ts)}}`;
  }} else if (tip) {{
    tip.style.display = 'none';
  }}
}}

let PRICE_HOVER = null;
function _slicedChart() {{
  const ch = CURRENT_CHART || {{}};
  const ticks = ch.ticks || [];
  if (!ticks.length) return {{ ticks: [], sma: [], lb: [], rsi: [] }};
  const n = Math.min(ticks.length, CHART_RANGE);
  const start = ticks.length - n;
  return {{
    ticks: ticks.slice(start),
    sma: (ch.sma || []).slice(start),
    lb: (ch.lower_band || []).slice(start),
    rsi: (ch.rsi || []).slice(start),
  }};
}}

function drawPriceChart() {{
  const canvas = document.getElementById('price-canvas');
  if (!canvas) return;
  const {{ ctx, w, h }} = prepCanvas(canvas);
  ctx.clearRect(0, 0, w, h);

  const ch = CURRENT_CHART || {{}};
  const {{ ticks, sma, lb, rsi }} = _slicedChart();
  if (ticks.length < 2) {{
    ctx.fillStyle = '#64748b'; ctx.font = '12px sans-serif'; ctx.textAlign = 'center';
    ctx.fillText('אין מספיק נרות מחיר — לחץ "משוך חי"', w / 2, h / 2);
    return;
  }}

  const prices = ticks.map(t => Number(t.price));
  const pos = ch.position || null;
  const allVals = [...prices];
  sma.forEach(v => {{ if (v !== null && v !== undefined) allVals.push(Number(v)); }});
  lb.forEach(v => {{ if (v !== null && v !== undefined) allVals.push(Number(v)); }});
  if (pos && pos.stop_price) allVals.push(Number(pos.stop_price));
  if (pos && pos.target_price) allVals.push(Number(pos.target_price));

  const minV = Math.min(...allVals), maxV = Math.max(...allVals);
  const pad = Math.max((maxV - minV) * 0.14, 0.012);
  const lo = Math.max(0, minV - pad), hi = Math.min(1, maxV + pad);
  const pxL = 14, pxR = 54, pyT = 14, pyB = 22;
  const gw = w - pxL - pxR, gh = h - pyT - pyB;
  const X = (i) => pxL + (i / (prices.length - 1)) * gw;
  const Y = (v) => pyT + gh - ((v - lo) / (hi - lo)) * gh;

  ctx.strokeStyle = 'rgba(255,255,255,0.05)'; ctx.lineWidth = 1;
  ctx.fillStyle = '#64748b'; ctx.font = '11px monospace'; ctx.textAlign = 'left';
  for (let i = 0; i <= 4; i++) {{
    const y = pyT + gh * (i / 4);
    const val = hi - (hi - lo) * (i / 4);
    ctx.beginPath(); ctx.moveTo(pxL, y); ctx.lineTo(w - pxR, y); ctx.stroke();
    ctx.fillText(val.toFixed(3), w - pxR + 6, y + 4);
  }}

  const hLine = (val, color, label) => {{
    if (val === null || val === undefined) return;
    const y = Y(Number(val));
    if (y < pyT || y > pyT + gh) return;
    ctx.save(); ctx.setLineDash([4, 4]); ctx.strokeStyle = color; ctx.lineWidth = 1.2;
    ctx.beginPath(); ctx.moveTo(pxL, y); ctx.lineTo(w - pxR, y); ctx.stroke();
    ctx.fillStyle = color; ctx.fillText(label, pxL + 6, y - 4);
    ctx.restore();
  }};
  if (pos) {{
    hLine(pos.target_price, 'rgba(16,185,129,0.8)', 'TP ' + Number(pos.target_price || 0).toFixed(3));
    hLine(pos.avg_price, 'rgba(148,163,184,0.65)', 'ENTRY ' + Number(pos.avg_price || 0).toFixed(3));
    hLine(pos.stop_price, 'rgba(239,68,68,0.8)', 'SL ' + Number(pos.stop_price || 0).toFixed(3));
  }}

  // רצועת כניסה Z
  ctx.beginPath(); let st = false;
  lb.forEach((v, i) => {{
    if (v === null || v === undefined) return;
    if (!st) {{ ctx.moveTo(X(i), Y(Number(v))); st = true; }} else ctx.lineTo(X(i), Y(Number(v)));
  }});
  ctx.strokeStyle = 'rgba(245,158,11,0.55)'; ctx.lineWidth = 1.2; ctx.stroke();

  // ממוצע נע SMA
  ctx.beginPath(); st = false;
  sma.forEach((v, i) => {{
    if (v === null || v === undefined) return;
    if (!st) {{ ctx.moveTo(X(i), Y(Number(v))); st = true; }} else ctx.lineTo(X(i), Y(Number(v)));
  }});
  ctx.strokeStyle = 'rgba(148,163,184,0.72)'; ctx.lineWidth = 1.3; ctx.stroke();

  // מחיר ראשי
  ctx.beginPath();
  prices.forEach((v, i) => i === 0 ? ctx.moveTo(X(i), Y(v)) : ctx.lineTo(X(i), Y(v)));
  ctx.strokeStyle = '#3b82f6'; ctx.lineWidth = 2.1; ctx.stroke();

  const tip = document.getElementById('price-tip');
  if (PRICE_HOVER !== null && PRICE_HOVER >= 0 && PRICE_HOVER < prices.length) {{
    const hx = X(PRICE_HOVER), hy = Y(prices[PRICE_HOVER]);
    ctx.save(); ctx.setLineDash([3, 3]); ctx.strokeStyle = 'rgba(255,255,255,0.28)';
    ctx.beginPath(); ctx.moveTo(hx, pyT); ctx.lineTo(hx, pyT + gh); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(pxL, hy); ctx.lineTo(w - pxR, hy); ctx.stroke();
    ctx.restore();
    ctx.beginPath(); ctx.arc(hx, hy, 4, 0, Math.PI * 2); ctx.fillStyle = '#3b82f6'; ctx.fill();
    const sVal = sma[PRICE_HOVER] !== null && sma[PRICE_HOVER] !== undefined ? Number(sma[PRICE_HOVER]).toFixed(3) : '—';
    const rVal = rsi[PRICE_HOVER] !== null && rsi[PRICE_HOVER] !== undefined ? Number(rsi[PRICE_HOVER]).toFixed(1) : '—';
    tip.style.display = 'block';
    tip.innerHTML = `<span class="num">${{fmtDateTime(ticks[PRICE_HOVER].ts)}}</span> | מחיר <strong class="num">${{prices[PRICE_HOVER].toFixed(3)}}</strong> | SMA <span class="num">${{sVal}}</span> | RSI <span class="num">${{rVal}}</span>`;
  }} else if (tip) {{
    tip.style.display = 'none';
  }}
}}

function drawRsiChart() {{
  const canvas = document.getElementById('rsi-canvas');
  if (!canvas) return;
  const {{ ctx, w, h }} = prepCanvas(canvas);
  ctx.clearRect(0, 0, w, h);
  const {{ rsi }} = _slicedChart();
  const valid = rsi.filter(v => v !== null && v !== undefined);
  if (valid.length < 2) return;

  const pxL = 14, pxR = 54, pyT = 8, pyB = 8;
  const gw = w - pxL - pxR, gh = h - pyT - pyB;
  const X = (i) => pxL + (i / Math.max(rsi.length - 1, 1)) * gw;
  const Y = (v) => pyT + gh - (Math.max(0, Math.min(100, v)) / 100) * gh;

  // אזור Oversold מתחת ל-45
  ctx.fillStyle = 'rgba(16,185,129,0.08)';
  ctx.fillRect(pxL, Y(45), gw, Y(0) - Y(45));

  ctx.font = '10px monospace'; ctx.fillStyle = '#64748b'; ctx.textAlign = 'left';
  for (const lvl of [30, 45, 70]) {{
    const y = Y(lvl);
    ctx.strokeStyle = lvl === 45 ? 'rgba(16,185,129,0.35)' : 'rgba(255,255,255,0.06)';
    ctx.beginPath(); ctx.moveTo(pxL, y); ctx.lineTo(w - pxR, y); ctx.stroke();
    ctx.fillText(String(lvl), w - pxR + 6, y + 3);
  }}

  ctx.beginPath(); let st = false;
  rsi.forEach((v, i) => {{
    if (v === null || v === undefined) return;
    if (!st) {{ ctx.moveTo(X(i), Y(Number(v))); st = true; }} else ctx.lineTo(X(i), Y(Number(v)));
  }});
  ctx.strokeStyle = '#a78bfa'; ctx.lineWidth = 1.5; ctx.stroke();
  ctx.fillStyle = '#94a3b8'; ctx.fillText('RSI(14)', pxL + 4, pyT + 9);
}}

// Crosshair Listeners
(function bindCrosshairs() {{
  const eqC = document.getElementById('eq-canvas');
  if (eqC) {{
    eqC.addEventListener('mousemove', (ev) => {{
      const pts = (STATE.equity_curve || []).filter(p => typeof p.equity === 'number');
      if (pts.length < 2) return;
      const rect = eqC.getBoundingClientRect();
      const rel = (ev.clientX - rect.left - 12) / Math.max(rect.width - 66, 1);
      EQ_HOVER = Math.max(0, Math.min(pts.length - 1, Math.round(rel * (pts.length - 1))));
      drawEquityChart();
    }});
    eqC.addEventListener('mouseleave', () => {{ EQ_HOVER = null; drawEquityChart(); }});
  }}
  const prC = document.getElementById('price-canvas');
  if (prC) {{
    prC.addEventListener('mousemove', (ev) => {{
      const {{ ticks }} = _slicedChart();
      if (ticks.length < 2) return;
      const rect = prC.getBoundingClientRect();
      const rel = (ev.clientX - rect.left - 14) / Math.max(rect.width - 68, 1);
      PRICE_HOVER = Math.max(0, Math.min(ticks.length - 1, Math.round(rel * (ticks.length - 1))));
      drawPriceChart();
    }});
    prC.addEventListener('mouseleave', () => {{ PRICE_HOVER = null; drawPriceChart(); }});
  }}
  const ppC = document.getElementById('perps-price-canvas');
  if (ppC) {{
    ppC.addEventListener('mousemove', (ev) => {{
      const cs = ((CURRENT_PERP_CHART && CURRENT_PERP_CHART.candles) || []).slice(-100);
      if (cs.length < 2) return;
      const rect = ppC.getBoundingClientRect();
      const rel = (ev.clientX - rect.left - 14) / Math.max(rect.width - 80, 1);
      PERP_HOVER = Math.max(0, Math.min(cs.length - 1, Math.round(rel * (cs.length - 1))));
      drawPerpPriceChart();
    }});
    ppC.addEventListener('mouseleave', () => {{ PERP_HOVER = null; drawPerpPriceChart(); }});
  }}
}})();

window.addEventListener('resize', () => {{
  if (ACTIVE_TAB === 'overview') drawEquityChart();
  if (ACTIVE_TAB === 'perps') {{ drawPerpEqChart(); drawPerpPriceChart(); }}
  if (ACTIVE_TAB === 'markets') {{ drawPriceChart(); drawRsiChart(); }}
}});

renderAll();
if (LIVE_ORIGIN && {refresh_ms} > 0) {{
  setInterval(refreshAll, {refresh_ms});
}}
</script>
</body>
</html>
"""
