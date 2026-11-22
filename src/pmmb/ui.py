"""
PMMB Command Center — ממשק מסחר מוסדי נקי ומינימליסטי (RTL).

תכנון חזותי:
  - כהה מאופק, גבולות דקים, טיפוגרפיה נקייה (`tabular-nums`), אייקוני SVG דקים בלבד (ללא אימוג'ים).
  - 4 לשוניות ברורות: סקירה ומסחר | שווקים וגרפים | חדשות ולמידה | תפעול אוטונומי.
  - 100% self-contained: ללא תלויות CDN/פונטים/קריאות חיצוניות (עובד מושלם גם בקובץ HTML מקומי).
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
<title>PMMB Terminal</title>
<style>
  :root {{
    --bg: #0a0e14;
    --surface: #11161f;
    --surface-2: #161c27;
    --border: rgba(255,255,255,0.075);
    --border-strong: rgba(255,255,255,0.14);
    --text: #eef2f7;
    --text-2: #94a3b8;
    --text-3: #64748b;
    --accent: #3b82f6;
    --accent-soft: rgba(59,130,246,0.12);
    --green: #10b981;
    --green-soft: rgba(16,185,129,0.12);
    --red: #ef4444;
    --red-soft: rgba(239,68,68,0.12);
    --amber: #f59e0b;
    --amber-soft: rgba(245,158,11,0.12);
    --radius: 10px;
  }}
  * {{ box-sizing: border-box; }}
  html, body {{
    margin: 0; padding: 0; background: var(--bg); color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    font-size: 13.5px; line-height: 1.5; -webkit-font-smoothing: antialiased;
  }}
  .num {{ font-variant-numeric: tabular-nums; direction: ltr; unicode-bidi: embed; display: inline-block; }}
  .mono {{ font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }}

  /* --- Topbar --- */
  .topbar {{
    position: sticky; top: 0; z-index: 40;
    background: rgba(10,14,20,0.92); backdrop-filter: blur(12px);
    border-bottom: 1px solid var(--border);
  }}
  .topbar-inner {{
    max-width: 1380px; margin: 0 auto; padding: 0 22px;
    height: 58px; display: flex; align-items: center; justify-content: space-between; gap: 16px;
  }}
  .brand {{
    display: flex; align-items: center; gap: 12px;
  }}
  .brand-mark {{
    width: 30px; height: 30px; border-radius: 8px;
    background: var(--surface-2); border: 1px solid var(--border-strong);
    display: grid; place-items: center; color: var(--accent);
  }}
  .brand-title {{ font-weight: 600; font-size: 14.5px; letter-spacing: 0.01em; color: var(--text); }}
  .brand-sub {{ font-size: 11.5px; color: var(--text-3); }}

  .nav-tabs {{
    display: flex; align-items: center; gap: 4px;
    background: var(--surface); border: 1px solid var(--border);
    padding: 3px; border-radius: 9px;
  }}
  .nav-tab {{
    background: transparent; border: none; color: var(--text-2);
    padding: 6px 14px; border-radius: 6px; cursor: pointer;
    font-size: 12.5px; font-weight: 500; transition: all 0.15s ease;
    display: inline-flex; align-items: center; gap: 7px;
  }}
  .nav-tab:hover {{ color: var(--text); }}
  .nav-tab.active {{ background: var(--surface-2); color: var(--text); box-shadow: inset 0 0 0 1px var(--border-strong); }}

  .top-actions {{
    display: flex; align-items: center; gap: 10px;
  }}
  .status-pill {{
    display: inline-flex; align-items: center; gap: 7px;
    padding: 5px 11px; border-radius: 999px; font-size: 12px; font-weight: 500;
    background: var(--surface); border: 1px solid var(--border); color: var(--text-2);
  }}
  .dot {{ width: 7px; height: 7px; border-radius: 50%; background: var(--text-3); flex-shrink: 0; }}
  .dot.ok {{ background: var(--green); box-shadow: 0 0 0 3px var(--green-soft); }}
  .dot.warn {{ background: var(--amber); box-shadow: 0 0 0 3px var(--amber-soft); }}
  .dot.err {{ background: var(--red); box-shadow: 0 0 0 3px var(--red-soft); }}

  .btn {{
    background: var(--surface-2); color: var(--text);
    border: 1px solid var(--border-strong); border-radius: 7px;
    padding: 6px 12px; font-size: 12px; font-weight: 500;
    cursor: pointer; transition: all 0.14s ease;
    display: inline-flex; align-items: center; gap: 6px;
  }}
  .btn:hover {{ background: #1e2635; border-color: rgba(255,255,255,0.22); }}
  .btn:disabled {{ opacity: 0.45; cursor: not-allowed; }}
  .btn-primary {{ background: var(--accent); border-color: var(--accent); color: #fff; }}
  .btn-primary:hover {{ background: #2563eb; border-color: #2563eb; }}
  .btn-danger {{ background: var(--red-soft); border-color: rgba(239,68,68,0.35); color: #fca5a5; }}
  .btn-danger:hover {{ background: rgba(239,68,68,0.22); }}
  .btn-ghost {{ background: transparent; border-color: var(--border); color: var(--text-2); }}
  .btn-ghost:hover {{ color: var(--text); background: var(--surface); }}

  /* --- Main Container --- */
  .wrap {{ max-width: 1380px; margin: 0 auto; padding: 20px 22px 48px; }}

  .banner {{
    padding: 10px 14px; border-radius: var(--radius); margin-bottom: 16px;
    font-size: 12.5px; display: flex; align-items: center; justify-content: space-between; gap: 12px;
  }}
  .banner.err {{ background: var(--red-soft); border: 1px solid rgba(239,68,68,0.32); color: #fecaca; }}
  .banner.info {{ background: var(--surface); border: 1px solid var(--border); color: var(--text-2); }}

  /* --- Grid & Cards --- */
  .kpi-row {{
    display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 12px; margin-bottom: 16px;
  }}
  .kpi {{
    background: var(--surface); border: 1px solid var(--border);
    border-radius: var(--radius); padding: 14px 16px;
  }}
  .kpi-label {{ font-size: 11.5px; color: var(--text-3); margin-bottom: 6px; font-weight: 500; }}
  .kpi-val {{ font-size: 21px; font-weight: 600; color: var(--text); letter-spacing: -0.02em; }}
  .kpi-sub {{ font-size: 11.5px; color: var(--text-2); margin-top: 4px; }}

  .grid-2 {{ display: grid; grid-template-columns: 1.45fr 1fr; gap: 14px; margin-bottom: 16px; }}
  .grid-even {{ display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-bottom: 16px; }}
  .grid-3 {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; margin-bottom: 16px; }}

  .card {{
    background: var(--surface); border: 1px solid var(--border);
    border-radius: var(--radius); overflow: hidden; margin-bottom: 16px;
  }}
  .grid-2 .card, .grid-even .card, .grid-3 .card {{ margin-bottom: 0; }}
  .card-head {{
    padding: 12px 16px; border-bottom: 1px solid var(--border);
    display: flex; align-items: center; justify-content: space-between; gap: 12px;
  }}
  .card-title {{ font-size: 13px; font-weight: 600; color: var(--text); }}
  .card-meta {{ font-size: 11.5px; color: var(--text-3); }}
  .card-body {{ padding: 14px 16px; }}
  .card-body.flush {{ padding: 0; }}

  /* --- Autopilot Strip --- */
  .ap-strip {{
    background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius);
    padding: 10px 16px; margin-bottom: 16px;
    display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 12px;
  }}
  .ap-items {{ display: flex; align-items: center; flex-wrap: wrap; gap: 18px; }}
  .ap-item {{ display: flex; align-items: center; gap: 7px; font-size: 12px; color: var(--text-2); }}
  .ap-item strong {{ color: var(--text); font-weight: 500; }}

  /* --- Tables --- */
  .table-wrap {{ overflow-x: auto; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 12.5px; }}
  th {{
    text-align: right; padding: 9px 14px; font-weight: 500; font-size: 11.5px;
    color: var(--text-3); border-bottom: 1px solid var(--border); background: rgba(255,255,255,0.015);
    white-space: nowrap;
  }}
  td {{
    padding: 10px 14px; border-bottom: 1px solid var(--border);
    color: var(--text-2); vertical-align: middle;
  }}
  tr:last-child td {{ border-bottom: none; }}
  tr.clickable {{ cursor: pointer; transition: background 0.12s; }}
  tr.clickable:hover td {{ background: rgba(255,255,255,0.025); }}
  .q-cell {{ color: var(--text); font-weight: 500; max-width: 340px; }}

  /* --- Badges & Progress --- */
  .badge {{
    display: inline-flex; align-items: center; padding: 2px 8px; border-radius: 5px;
    font-size: 11px; font-weight: 500; border: 1px solid transparent; white-space: nowrap;
  }}
  .badge-ok {{ background: var(--green-soft); color: #6ee7b7; border-color: rgba(16,185,129,0.25); }}
  .badge-warn {{ background: var(--amber-soft); color: #fcd34d; border-color: rgba(245,158,11,0.25); }}
  .badge-err {{ background: var(--red-soft); color: #fca5a5; border-color: rgba(239,68,68,0.25); }}
  .badge-info {{ background: var(--accent-soft); color: #93c5fd; border-color: rgba(59,130,246,0.25); }}
  .badge-mute {{ background: rgba(255,255,255,0.04); color: var(--text-2); border-color: var(--border); }}

  .bar-row {{ margin-bottom: 11px; }}
  .bar-row:last-child {{ margin-bottom: 0; }}
  .bar-top {{ display: flex; justify-content: space-between; font-size: 12px; margin-bottom: 5px; color: var(--text-2); }}
  .bar-track {{ height: 4px; border-radius: 99px; background: rgba(255,255,255,0.07); overflow: hidden; }}
  .bar-fill {{ height: 100%; border-radius: 99px; background: var(--accent); transition: width 0.3s ease; }}

  /* --- Charts & Filters --- */
  .select {{
    background: var(--surface-2); color: var(--text); border: 1px solid var(--border-strong);
    border-radius: 7px; padding: 6px 10px; font-size: 12.5px; outline: none; min-width: 260px; max-width: 100%;
  }}
  .filter-pills {{ display: flex; gap: 6px; flex-wrap: wrap; }}
  .pill-btn {{
    background: transparent; color: var(--text-2); border: 1px solid var(--border);
    border-radius: 999px; padding: 4px 11px; font-size: 11.5px; cursor: pointer;
  }}
  .pill-btn.active {{ background: var(--surface-2); color: var(--text); border-color: var(--border-strong); }}

  .news-list {{ display: flex; flex-direction: column; }}
  .news-item {{
    padding: 11px 16px; border-bottom: 1px solid var(--border);
    display: flex; align-items: flex-start; justify-content: space-between; gap: 12px;
  }}
  .news-item:last-child {{ border-bottom: none; }}
  .news-title {{ color: var(--text); font-size: 12.5px; font-weight: 500; line-height: 1.45; }}
  .news-meta {{ font-size: 11px; color: var(--text-3); margin-top: 3px; display: flex; gap: 10px; flex-wrap: wrap; }}

  .kv-list {{ display: grid; grid-template-columns: 1fr 1fr; gap: 8px 18px; }}
  .kv-item {{
    display: flex; justify-content: space-between; align-items: center;
    padding: 7px 0; border-bottom: 1px solid var(--border); font-size: 12px;
  }}
  .kv-k {{ color: var(--text-3); }}
  .kv-v {{ color: var(--text); font-weight: 500; }}

  .chart-box {{ position: relative; width: 100%; height: 270px; }}
  .eq-box {{ position: relative; width: 100%; height: 170px; }}
  canvas.plot {{ width: 100%; height: 100%; display: block; }}

  .toast {{
    position: fixed; bottom: 20px; left: 20px; z-index: 60;
    background: var(--surface-2); border: 1px solid var(--border-strong); color: var(--text);
    padding: 10px 16px; border-radius: 8px; font-size: 12.5px;
    box-shadow: 0 12px 30px rgba(0,0,0,0.45); display: none; max-width: 420px;
  }}
  .tab-pane {{ display: none; }}
  .tab-pane.active {{ display: block; }}

  .pos {{ color: var(--green); }}
  .neg {{ color: var(--red); }}

  @media (max-width: 1080px) {{
    .kpi-row {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
    .grid-2, .grid-even, .grid-3 {{ grid-template-columns: 1fr; }}
    .topbar-inner {{ height: auto; padding: 10px 14px; flex-wrap: wrap; }}
  }}
  @media (max-width: 640px) {{
    .wrap {{ padding: 14px 12px 36px; }}
    .kv-list {{ grid-template-columns: 1fr; }}
    .nav-tabs {{ width: 100%; overflow-x: auto; }}
  }}
</style>
</head>
<body>

<header class="topbar">
  <div class="topbar-inner">
    <div class="brand">
      <div class="brand-mark" aria-hidden="true">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
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
      <button class="btn btn-ghost" onclick="refreshAll()" title="רענון נתונים">רענן</button>
    </div>
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

    <div class="ap-strip" id="ap-strip"></div>

    <div class="grid-2">
      <div class="card">
        <div class="card-head">
          <span class="card-title">עקומת הון חיה</span>
          <span class="card-meta" id="eq-meta">—</span>
        </div>
        <div class="card-body">
          <div class="eq-box"><canvas id="eq-canvas" class="plot"></canvas></div>
        </div>
      </div>
      <div class="card">
        <div class="card-head">
          <span class="card-title">בקרת סיכון ומרווחים</span>
          <span class="card-meta" id="risk-meta">Mean Reversion</span>
        </div>
        <div class="card-body" id="risk-bars"></div>
      </div>
    </div>

    <div class="card">
      <div class="card-head">
        <span class="card-title">פוזיציות פתוחות</span>
        <span class="card-meta">לחיצה על שוק פותחת גרף וחדשות</span>
      </div>
      <div class="card-body flush">
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>שוק</th>
                <th>כמות</th>
                <th>מחיר כניסה</th>
                <th>מחיר שוק</th>
                <th>סטופ / יעד</th>
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
          <span class="card-title">עסקאות סגורות אחרונות</span>
          <span class="card-meta" id="trades-meta">—</span>
        </div>
        <div class="card-body flush">
          <div class="table-wrap">
            <table>
              <thead><tr><th>זמן</th><th>שוק</th><th>כמות</th><th>מחיר</th><th>PnL</th><th>סיבה</th></tr></thead>
              <tbody id="trades-tbody"></tbody>
            </table>
          </div>
        </div>
      </div>
      <div class="card">
        <div class="card-head">
          <span class="card-title">פילוח סינון סיגנלים</span>
          <span class="card-meta">מחזור אחרון</span>
        </div>
        <div class="card-body" id="skip-bars"></div>
      </div>
    </div>
  </section>

  <!-- ========== TAB 2: שווקים וגרפים ========== -->
  <section id="tab-markets" class="tab-pane">
    <div class="card">
      <div class="card-head">
        <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap">
          <span class="card-title">גרף מחיר וסיגנל</span>
          <select id="chart-select" class="select" onchange="loadChart(this.value, true)"></select>
        </div>
        <div style="display:flex;align-items:center;gap:8px">
          <span class="card-meta" id="chart-stats">—</span>
          <button class="btn btn-ghost" onclick="loadChart(document.getElementById('chart-select').value, true)">משוך חי</button>
        </div>
      </div>
      <div class="card-body">
        <div class="chart-box"><canvas id="price-canvas" class="plot"></canvas></div>
        <div id="chart-intel-bar" style="display:flex;gap:16px;flex-wrap:wrap;margin-top:12px;padding-top:10px;border-top:1px solid var(--border);font-size:12px;color:var(--text-2)"></div>
        <div id="chart-news-box" style="margin-top:8px;font-size:12px;color:var(--text-3)"></div>
      </div>
    </div>

    <div class="card">
      <div class="card-head">
        <span class="card-title">רדאר מודיעין שווקים חי</span>
        <div class="filter-pills" id="intel-filters">
          <button class="pill-btn active" onclick="setIntelFilter('ALL', this)">הכל</button>
          <button class="pill-btn" onclick="setIntelFilter('OPEN', this)">פוזיציות</button>
          <button class="pill-btn" onclick="setIntelFilter('CANDIDATE', this)">מועמדים</button>
          <button class="pill-btn" onclick="setIntelFilter('CATALYST_BLOCK', this)">נחסמו מחדשות/נפח</button>
        </div>
      </div>
      <div class="card-body flush">
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>שוק</th>
                <th>סקטור</th>
                <th>מחיר</th>
                <th>ספרד</th>
                <th>עומק ספר</th>
                <th>שינוי 1ש' / 6ש' / 24ש'</th>
                <th>Z-Score</th>
                <th>נפח יחסי</th>
                <th>חדשות</th>
                <th>סטטוס</th>
              </tr>
            </thead>
            <tbody id="intel-tbody"></tbody>
          </table>
        </div>
      </div>
    </div>
  </section>

  <!-- ========== TAB 3: חדשות ולמידה ========== -->
  <section id="tab-intel" class="tab-pane">
    <div class="grid-even">
      <div class="card">
        <div class="card-head">
          <span class="card-title">פיד חדשות מוסדי חי</span>
          <div style="display:flex;align-items:center;gap:8px">
            <div class="filter-pills">
              <button class="pill-btn active" onclick="setNewsFilter('ALL', this)">הכל</button>
              <button class="pill-btn" onclick="setNewsFilter('CATALYST', this)">חריגות</button>
              <button class="pill-btn" onclick="setNewsFilter('MATCHED', this)">מותאם לשוק</button>
            </div>
            <button class="btn btn-ghost" onclick="postAction('/api/news-refresh', {{}})">רענן פיד</button>
          </div>
        </div>
        <div class="card-body flush">
          <div class="news-list" id="news-list"></div>
        </div>
      </div>

      <div style="display:flex;flex-direction:column;gap:14px">
        <div class="card">
          <div class="card-head">
            <span class="card-title">מנוע למידה עצמית (OOS)</span>
            <button class="btn btn-ghost" onclick="postAction('/api/learn', {{apply:true}})">הרץ הערכה</button>
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
            <span class="card-title">היסטוריית מחזורי שיפור</span>
            <span class="card-meta">Walk-Forward OOS</span>
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
        <span class="card-title">שליטה מהירה</span>
        <span class="card-meta">הבוט מתפעל סנכרון, גיבויים ודוחות לבד — הפעולות כאן הן לשליטה יזומה</span>
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
          <span class="card-meta">מדדי יחוס היסטוריים</span>
        </div>
        <div class="card-body" id="analytics-box"></div>
      </div>

      <div class="card">
        <div class="card-head">
          <span class="card-title">תצורת מערכת פעילה</span>
          <span class="card-meta" id="cfg-mode">paper</span>
        </div>
        <div class="card-body" id="cfg-box"></div>
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
let CURRENT_CHART = (INITIAL.charts && INITIAL.charts.default) || null;
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
  const d = new Date(Number(ts) * 1000);
  return d.toLocaleTimeString('he-IL', {{hour:'2-digit', minute:'2-digit'}});
}};
const fmtDateTime = (ts) => {{
  if (!ts) return '—';
  const d = new Date(Number(ts) * 1000);
  return d.toLocaleDateString('he-IL', {{day:'2-digit', month:'2-digit'}}) + ' ' + d.toLocaleTimeString('he-IL', {{hour:'2-digit', minute:'2-digit'}});
}};

function showToast(msg, isErr = false) {{
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.style.borderColor = isErr ? 'rgba(239,68,68,0.5)' : 'rgba(59,130,246,0.45)';
  el.style.display = 'block';
  clearTimeout(window.__toastTimer);
  window.__toastTimer = setTimeout(() => {{ el.style.display = 'none'; }}, 4000);
}}

document.querySelectorAll('.nav-tab').forEach(btn => {{
  btn.addEventListener('click', () => {{
    ACTIVE_TAB = btn.dataset.tab;
    document.querySelectorAll('.nav-tab').forEach(b => b.classList.toggle('active', b === btn));
    document.querySelectorAll('.tab-pane').forEach(p => p.classList.toggle('active', p.id === 'tab-' + ACTIVE_TAB));
    if (ACTIVE_TAB === 'markets') drawPriceChart();
    if (ACTIVE_TAB === 'overview') drawEquityChart();
  }});
}});

function switchToMarket(tokenId) {{
  ACTIVE_TAB = 'markets';
  document.querySelectorAll('.nav-tab').forEach(b => b.classList.toggle('active', b.dataset.tab === 'markets'));
  document.querySelectorAll('.tab-pane').forEach(p => p.classList.toggle('active', p.id === 'tab-markets'));
  const sel = document.getElementById('chart-select');
  if (sel) sel.value = tokenId;
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
  if (!LIVE_ORIGIN) {{
    drawPriceChart();
    return;
  }}
  try {{
    const res = await fetch('/api/chart?token=' + encodeURIComponent(tokenId) + (live ? '&live=1' : ''));
    if (res.ok) {{
      CURRENT_CHART = await res.json();
      drawPriceChart();
    }}
  }} catch (e) {{}}
}}

function renderAll() {{
  renderHeader();
  renderOverview();
  renderMarketsIntel();
  renderChartSelector();
  drawEquityChart();
  drawPriceChart();
  renderNews();
  renderLearning();
  renderSystem();
}}

function renderHeader() {{
  const tr = STATE.trader || {{}};
  const h = STATE.health || {{}};
  const hb = STATE.heartbeat || {{}};
  const cfg = STATE.config || {{}};
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
    `${{mode.toUpperCase()}} · מחזור #${{cyc}} · ${{(tel.intel || 0)}} שווקים במעקב · ${{(tel.news || 0)}} כתבות`;

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
  const tr = STATE.trader || {{}};
  const tel = STATE.telemetry || {{}};

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
    {{ label: 'מוכנות צבירה (Soak)', val: `${{soak.days || 0}}/${{soak.target_days || 7}}`, sub: `פוזיציות פתוחות: ${{bank.open_positions || 0}}`, cls: '' }},
  ];
  document.getElementById('kpi-row').innerHTML = kpis.map(k => `
    <div class="kpi">
      <div class="kpi-label">${{esc(k.label)}}</div>
      <div class="kpi-val num ${{k.cls}}">${{esc(k.val)}}</div>
      <div class="kpi-sub">${{esc(k.sub)}}</div>
    </div>`).join('');

  // רצועת אוטופיילוט נקייה
  const apItems = [
    {{ dot: tr.running ? 'ok' : 'warn', title: 'מסחר אוטונומי', val: tr.running ? `פעיל (כל ${{Math.round((tr.interval_sec || 180)/60)}} דק')` : 'מושהה' }},
    {{ dot: tr.last_stream_ts ? 'ok' : 'warn', title: 'שידור גרפים', val: fmtTime(tr.last_stream_ts) }},
    {{ dot: tr.last_news_ts ? 'ok' : 'warn', title: 'סורק חדשות', val: `${{tel.news || 0}} כתבות (${{fmtTime(tr.last_news_ts)}})` }},
    {{ dot: tr.last_reconcile_ts ? 'ok' : 'warn', title: 'אימות DB', val: tr.last_reconcile_ts ? fmtTime(tr.last_reconcile_ts) : 'מחזור הבא' }},
    {{ dot: tr.last_learn_ts ? 'ok' : 'warn', title: 'למידה OOS', val: tr.last_learn_ts ? fmtTime(tr.last_learn_ts) : 'מתוכנן' }},
    {{ dot: tr.last_backup_ts ? 'ok' : 'warn', title: 'גיבוי חם', val: tr.last_backup_ts ? fmtTime(tr.last_backup_ts) : 'אוטומטי' }},
  ];
  document.getElementById('ap-strip').innerHTML = `
    <div class="ap-items">
      ${{apItems.map(x => `<div class="ap-item"><span class="dot ${{x.dot}}"></span><strong>${{esc(x.title)}}:</strong><span>${{esc(x.val)}}</span></div>`).join('')}}
    </div>
    <span class="card-meta">${{tr.last_error ? 'התראה אחרונה: ' + esc(tr.last_error.slice(0,50)) : 'כל המערכות פועלות באופן עצמאי'}}</span>`;

  // מדדי סיכון
  const g = STATE.guards || {{}};
  const dlUsed = Number(g.daily_loss_used || 0);
  const dlLim = Math.max(Number(g.daily_loss_limit || 1), 0.01);
  const ddPct = Number(g.drawdown_pct || 0);
  const ddLim = Math.max(Number(g.drawdown_limit_pct || 10), 0.01);
  const posOpen = Number(bank.open_positions || 0);
  const posLim = Math.max(posOpen + Number(g.positions_room || 0), 1);
  const maxExp = exp + Number(g.exposure_room || 0);

  const bars = [
    {{ lbl: 'מגבלת הפסד יומי', txt: `${{fmtNum(dlUsed)}} / ${{fmtNum(dlLim)}} USDC`, pct: Math.min(100, Math.max(0, dlUsed / dlLim * 100)), color: 'var(--green)' }},
    {{ lbl: 'Drawdown מהשיא', txt: `${{ddPct.toFixed(2)}}% / ${{ddLim.toFixed(0)}}%`, pct: Math.min(100, ddPct / ddLim * 100), color: ddPct > ddLim * 0.6 ? 'var(--amber)' : 'var(--accent)' }},
    {{ lbl: 'ניצול חשיפה מותרת', txt: `${{fmtNum(exp)}} / ${{fmtNum(maxExp)}} USDC`, pct: maxExp > 0 ? Math.min(100, exp / maxExp * 100) : 0, color: 'var(--accent)' }},
    {{ lbl: 'תפוסת פוזיציות', txt: `${{posOpen}} / ${{posLim}} פתוחות`, pct: Math.min(100, posOpen / posLim * 100), color: 'var(--accent)' }},
  ];
  document.getElementById('risk-bars').innerHTML = bars.map(b => `
    <div class="bar-row">
      <div class="bar-top"><span>${{esc(b.lbl)}}</span><span class="num">${{esc(b.txt)}}</span></div>
      <div class="bar-track"><div class="bar-fill" style="width:${{b.pct.toFixed(1)}}%;background:${{b.color}}"></div></div>
    </div>`).join('');

  // פוזיציות פתוחות
  const pos = STATE.positions || [];
  document.getElementById('pos-tbody').innerHTML = pos.length ? pos.map(p => {{
    const u = p.unrealized_pnl;
    const upct = p.unrealized_pct;
    const uCls = (u || 0) >= 0 ? 'pos' : 'neg';
    const sl = p.stop_price ? Number(p.stop_price).toFixed(2) : '—';
    const tp = p.target_price ? Number(p.target_price).toFixed(2) : '—';
    return `<tr class="clickable" onclick="switchToMarket('${{esc(p.token_id)}}')">
      <td class="q-cell">${{esc((p.question || p.token_id).slice(0, 62))}}</td>
      <td class="num">${{fmtNum(p.size, 1)}}</td>
      <td class="num">${{fmtNum(p.avg_price, 3)}}</td>
      <td class="num">${{p.mark_price !== null && p.mark_price !== undefined ? fmtNum(p.mark_price, 3) : '—'}}</td>
      <td class="num" style="color:var(--text-3)">${{sl}} / ${{tp}}</td>
      <td class="num ${{uCls}}">${{u !== null && u !== undefined ? `${{fmtSign(u)}} (${{fmtSign(upct, 1)}}%)` : '—'}}</td>
      <td class="num">${{fmtNum(p.age_hours, 1)}}h</td>
    </tr>`;
  }}).join('') : '<tr><td colspan="7" style="text-align:center;color:var(--text-3);padding:20px">אין כרגע פוזיציות פתוחות</td></tr>';

  // עסקאות סגורות
  const trs = (STATE.recent_trades || []).slice(0, 12);
  document.getElementById('trades-meta').textContent = `${{trs.length}} אחרונות`;
  document.getElementById('trades-tbody').innerHTML = trs.length ? trs.map(t => {{
    const rz = Number(t.realized || 0);
    return `<tr>
      <td class="num" style="color:var(--text-3)">${{fmtDateTime(t.ts)}}</td>
      <td style="color:var(--text)">${{esc((t.question || '').slice(0, 34))}}</td>
      <td class="num">${{fmtNum(t.size, 1)}}</td>
      <td class="num">${{fmtNum(t.price, 3)}}</td>
      <td class="num ${{rz >= 0 ? 'pos' : 'neg'}}">${{fmtSign(rz)}}</td>
      <td style="color:var(--text-3)">${{esc((t.reason || '').slice(0, 26))}}</td>
    </tr>`;
  }}).join('') : '<tr><td colspan="6" style="text-align:center;color:var(--text-3);padding:18px">אין עסקאות סגורות עדיין</td></tr>';

  // סינון סיגנלים
  const skipped = STATE.skipped || {{}};
  const entries = Object.entries(skipped).sort((a, b) => b[1] - a[1]).slice(0, 8);
  const totSkip = entries.reduce((acc, kv) => acc + kv[1], 0) || 1;
  document.getElementById('skip-bars').innerHTML = entries.length ? entries.map(([k, v]) => `
    <div class="bar-row">
      <div class="bar-top"><span>${{esc(k)}}</span><span class="num">${{v}}</span></div>
      <div class="bar-track"><div class="bar-fill" style="width:${{(v/totSkip*100).toFixed(1)}}%;background:rgba(148,163,184,0.45)"></div></div>
    </div>`).join('') : '<div style="color:var(--text-3);font-size:12px">יופיע לאחר מחזור הסריקה הבא</div>';
}}

function renderChartSelector() {{
  const cands = (STATE.charts && STATE.charts.candidates) || [];
  const sel = document.getElementById('chart-select');
  if (!sel) return;
  const prev = sel.value;
  sel.innerHTML = cands.length ? cands.map(c =>
    `<option value="${{esc(c.token_id)}}">${{c.open ? '[פתוחה] ' : ''}}${{esc((c.question || c.token_id).slice(0, 58))}}</option>`
  ).join('') : '<option value="">אין נתוני גרף עדיין</option>';
  if (prev && cands.some(c => c.token_id === prev)) {{
    sel.value = prev;
  }} else if (CURRENT_CHART && CURRENT_CHART.token_id) {{
    sel.value = CURRENT_CHART.token_id;
  }}
}}

function renderMarketsIntel() {{
  const rows = STATE.market_intel || [];
  const filtered = rows.filter(r => {{
    if (INTEL_FILTER === 'ALL') return true;
    return r.status === INTEL_FILTER;
  }});

  const statusBadge = (st) => {{
    if (st === 'OPEN') return '<span class="badge badge-info">בפוזיציה</span>';
    if (st === 'BUY') return '<span class="badge badge-ok">כניסה בוצעה</span>';
    if (st === 'CATALYST_BLOCK') return '<span class="badge badge-warn">נחסם קטליזטור</span>';
    if (st === 'CANDIDATE') return '<span class="badge badge-ok">מועמד קנייה</span>';
    return '<span class="badge badge-mute">במעקב</span>';
  }};

  document.getElementById('intel-tbody').innerHTML = filtered.length ? filtered.map(r => {{
    const z = r.z_score;
    const zCls = (z !== null && z !== undefined && z <= -1.8) ? 'pos' : '';
    const vr = Number(r.volume_ratio || 1);
    const vrCls = vr >= 4.0 ? 'badge badge-warn' : '';
    const depth = (Number(r.bid_depth || 0) + Number(r.ask_depth || 0));
    const chg1 = r.chg_1h !== null && r.chg_1h !== undefined ? fmtSign(r.chg_1h * 100, 1) + '%' : '—';
    const chg6 = r.chg_6h !== null && r.chg_6h !== undefined ? fmtSign(r.chg_6h * 100, 1) + '%' : '—';
    const chg24 = r.chg_24h !== null && r.chg_24h !== undefined ? fmtSign(r.chg_24h * 100, 1) + '%' : '—';
    const nBadge = r.news_count > 0
      ? `<span class="badge ${{r.news_impact >= 0.45 ? 'badge-warn' : 'badge-mute'}}">${{r.news_count}} (${{Number(r.news_impact).toFixed(2)}})</span>`
      : '<span style="color:var(--text-3)">—</span>';

    return `<tr class="clickable" onclick="switchToMarket('${{esc(r.token_id)}}')">
      <td class="q-cell">${{esc((r.question || '').slice(0, 56))}}</td>
      <td>${{esc(r.sector || 'other')}}</td>
      <td class="num">${{fmtNum(r.price, 3)}}</td>
      <td class="num">${{fmtNum(r.spread, 3)}}</td>
      <td class="num">$${{Math.round(depth)}}</td>
      <td class="num" style="font-size:11.5px">${{chg1}} / ${{chg6}} / ${{chg24}}</td>
      <td class="num ${{zCls}}">${{z !== null && z !== undefined ? fmtSign(z, 2) : '—'}}</td>
      <td class="num">${{vrCls ? `<span class="${{vrCls}}">${{vr.toFixed(1)}}x</span>` : vr.toFixed(1) + 'x'}}</td>
      <td>${{nBadge}}</td>
      <td>${{statusBadge(r.status)}}</td>
    </tr>`;
  }}).join('') : '<tr><td colspan="10" style="text-align:center;color:var(--text-3);padding:22px">נתוני המודיעין יאכלסו אוטומטית בסיום סריקת השוק הקרובה</td></tr>';
}}

function renderNews() {{
  const news = STATE.news || [];
  const filtered = news.filter(n => {{
    if (NEWS_FILTER === 'CATALYST') return Number(n.impact || 0) >= 0.45;
    if (NEWS_FILTER === 'MATCHED') return Boolean(n.matched_tokens);
    return true;
  }});

  document.getElementById('news-list').innerHTML = filtered.length ? filtered.slice(0, 30).map(n => {{
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
          <span>${{esc(n.source || n.category || 'RSS')}}</span>
          <span>${{fmtDateTime(n.ts)}}</span>
          ${{n.matched_tokens ? '<span style="color:var(--accent)">קשור לשוק פעיל</span>' : ''}}
        </div>
      </div>
      <div style="display:flex;gap:6px;flex-shrink:0">${{impBadge}}${{sBadge}}</div>
    </div>`;
  }}).join('') : '<div style="padding:20px;text-align:center;color:var(--text-3)">אין כתבות להצגה במסנן זה</div>';
}}

function renderLearning() {{
  const lr = STATE.learning || {{}};
  const st = lr.stats || {{}};
  const insights = lr.insights || [];
  const runs = lr.runs || [];

  document.getElementById('learn-total').textContent = `${{st.total_evaluated || 0}} אותות הוערכו`;

  document.getElementById('learn-insights').innerHTML = insights.length
    ? '<ul style="margin:0;padding-right:18px;color:var(--text-2);font-size:12.5px">' +
      insights.map(x => `<li style="margin-bottom:6px">${{esc(x)}}</li>`).join('') + '</ul>'
    : '<div style="color:var(--text-3);font-size:12.5px">הבוט אוגר תוצאות אותות על פני 6ש׳ / 24ש׳ / 48ש׳ לכיול Walk-Forward.</div>';

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
  document.getElementById('ap-meta').textContent = `${{ap.length}} פעולות אחרונות`;
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

  // תצוגה מובנית של ביצועי Backtest ו-Walk-Forward ללא Markdown גולמי
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
    ['OOS Walk-Forward', wf.total_oos_pnl !== undefined ? fmtSign(wf.total_oos_pnl) + ' USDC' : '—'],
    ['התמדת חלונות OOS', wf.consistency !== undefined ? (Number(wf.consistency) * 100).toFixed(0) + '%' : '—'],
  ];
  document.getElementById('analytics-box').innerHTML = `<div class="kv-list">
    ${{metrics.map(([k, v]) => `<div class="kv-item"><span class="kv-k">${{esc(k)}}</span><span class="kv-v num">${{esc(v)}}</span></div>`).join('')}}
  </div>`;

  // תצורת מערכת נקייה
  const cfg = STATE.config || {{}};
  const ex = cfg.execution || {{}};
  const sig = cfg.signal || {{}};
  const rk = cfg.risk || {{}};
  const nw = cfg.news || {{}};
  const apc = cfg.autopilot || {{}};
  document.getElementById('cfg-mode').textContent = (ex.mode || 'paper').toUpperCase();
  const cfgItems = [
    ['מנוע אסטרטגיה', sig.engine || 'mean_reversion'],
    ['חלון / Z כניסה', `${{sig.lookback_candles || 24}}h / Z>=${{sig.z_entry || 1.8}}`],
    ['יעד רווח / סטופ', `+${{sig.take_profit || 0.05}} / -${{sig.stop_loss || 0.08}}`],
    ['Time Stop', `${{sig.time_stop_hours || 48}} שעות`],
    ['קלי / סיכון מקסימלי', `${{((rk.kelly_fraction || 0.5)*100).toFixed(0)}}% / ${{rk.risk_per_trade_pct || 2}}%`],
    ['תקרת חשיפה / פוזיציות', `${{rk.max_total_exposure_pct || 50}}% / ${{rk.max_open_positions || 8}}`],
    ['מגן חדשות / נפח', `impact>=${{nw.spike_impact_threshold || 0.45}} / ${{nw.volume_spike_ratio || 6}}x`],
    ['תדירות אוטופיילוט', `מסחר ${{apc.trade_interval_sec || 180}}s · גיבוי ${{Math.round((apc.backup_interval_sec || 14400)/3600)}}h`],
  ];
  document.getElementById('cfg-box').innerHTML = `<div class="kv-list">
    ${{cfgItems.map(([k, v]) => `<div class="kv-item"><span class="kv-k">${{esc(k)}}</span><span class="kv-v num">${{esc(v)}}</span></div>`).join('')}}
  </div>`;
}}

/* --- Canvas Renderers (Sharp DPI, Zero External Deps) --- */
function prepCanvas(canvas) {{
  const rect = canvas.parentElement.getBoundingClientRect();
  const w = Math.max(300, Math.floor(rect.width));
  const h = Math.max(150, Math.floor(rect.height));
  const dpr = window.devicePixelRatio || 1;
  canvas.width = w * dpr;
  canvas.height = h * dpr;
  const ctx = canvas.getContext('2d');
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  return {{ ctx, w, h }};
}}

function drawEquityChart() {{
  const canvas = document.getElementById('eq-canvas');
  if (!canvas) return;
  const {{ ctx, w, h }} = prepCanvas(canvas);
  const pts = (STATE.equity_curve || []).map(p => Number(p.equity)).filter(v => !Number.isNaN(v));
  ctx.clearRect(0, 0, w, h);

  if (pts.length < 2) {{
    ctx.fillStyle = '#64748b'; ctx.font = '12px sans-serif'; ctx.textAlign = 'center';
    ctx.fillText('אוסף נקודות הון לעקומה חיה...', w / 2, h / 2);
    return;
  }}

  const minV = Math.min(...pts), maxV = Math.max(...pts);
  const pad = Math.max((maxV - minV) * 0.14, 1);
  const lo = minV - pad, hi = maxV + pad;
  const pxL = 12, pxR = 54, pyT = 12, pyB = 22;
  const gw = w - pxL - pxR, gh = h - pyT - pyB;
  const up = pts[pts.length - 1] >= pts[0];
  const stroke = up ? '#10b981' : '#ef4444';

  document.getElementById('eq-meta').textContent = `${{pts[0].toFixed(2)}} -> ${{pts[pts.length - 1].toFixed(2)}} (${{fmtSign(pts[pts.length - 1] - pts[0])}})`;

  // קווי רוחב עדינים
  ctx.strokeStyle = 'rgba(255,255,255,0.05)';
  ctx.lineWidth = 1;
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
}}

function drawPriceChart() {{
  const canvas = document.getElementById('price-canvas');
  if (!canvas) return;
  const {{ ctx, w, h }} = prepCanvas(canvas);
  ctx.clearRect(0, 0, w, h);

  const ch = CURRENT_CHART;
  const ticks = (ch && ch.ticks) || [];
  if (ticks.length < 2) {{
    ctx.fillStyle = '#64748b'; ctx.font = '12px sans-serif'; ctx.textAlign = 'center';
    ctx.fillText('אין מספיק טיקים לשוק זה — לחץ "משוך חי"', w / 2, h / 2);
    return;
  }}

  const prices = ticks.map(t => Number(t.price));
  const sma = (ch.sma || []).map(v => v === null ? null : Number(v));
  const lb = (ch.lower_band || []).map(v => v === null ? null : Number(v));
  const pos = ch.position || null;
  const intel = ch.intel || null;

  const allVals = [...prices];
  sma.forEach(v => {{ if (v !== null) allVals.push(v); }});
  lb.forEach(v => {{ if (v !== null) allVals.push(v); }});
  if (pos && pos.stop_price) allVals.push(Number(pos.stop_price));
  if (pos && pos.target_price) allVals.push(Number(pos.target_price));

  const minV = Math.min(...allVals), maxV = Math.max(...allVals);
  const pad = Math.max((maxV - minV) * 0.14, 0.015);
  const lo = Math.max(0, minV - pad), hi = Math.min(1, maxV + pad);
  const pxL = 14, pxR = 54, pyT = 16, pyB = 26;
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

  // קווי סטופ/יעד אם קיימת פוזיציה
  const hLine = (val, color, label) => {{
    if (val === null || val === undefined) return;
    const y = Y(Number(val));
    ctx.save(); ctx.setLineDash([4, 4]); ctx.strokeStyle = color; ctx.lineWidth = 1.2;
    ctx.beginPath(); ctx.moveTo(pxL, y); ctx.lineTo(w - pxR, y); ctx.stroke();
    ctx.fillStyle = color; ctx.fillText(label, pxL + 6, y - 4);
    ctx.restore();
  }};
  if (pos) {{
    hLine(pos.target_price, 'rgba(16,185,129,0.75)', 'יעד ' + Number(pos.target_price || 0).toFixed(3));
    hLine(pos.avg_price, 'rgba(148,163,184,0.6)', 'כניסה ' + Number(pos.avg_price || 0).toFixed(3));
    hLine(pos.stop_price, 'rgba(239,68,68,0.75)', 'סטופ ' + Number(pos.stop_price || 0).toFixed(3));
  }}

  // רצועה תחתונה (Z=1.8)
  ctx.beginPath(); let started = false;
  lb.forEach((v, i) => {{
    if (v === null) return;
    if (!started) {{ ctx.moveTo(X(i), Y(v)); started = true; }} else ctx.lineTo(X(i), Y(v));
  }});
  ctx.strokeStyle = 'rgba(245,158,11,0.55)'; ctx.lineWidth = 1.3; ctx.stroke();

  // ממוצע נע SMA
  ctx.beginPath(); started = false;
  sma.forEach((v, i) => {{
    if (v === null) return;
    if (!started) {{ ctx.moveTo(X(i), Y(v)); started = true; }} else ctx.lineTo(X(i), Y(v));
  }});
  ctx.strokeStyle = 'rgba(148,163,184,0.7)'; ctx.lineWidth = 1.4; ctx.stroke();

  // מחיר ראשי
  ctx.beginPath();
  prices.forEach((v, i) => i === 0 ? ctx.moveTo(X(i), Y(v)) : ctx.lineTo(X(i), Y(v)));
  ctx.strokeStyle = '#3b82f6'; ctx.lineWidth = 2.1; ctx.stroke();

  const lastPx = prices[prices.length - 1];
  document.getElementById('chart-stats').textContent =
    `${{prices.length}} נרות · מחיר אחרון ${{lastPx.toFixed(3)}}`;

  // שורת מידע רב-ממדית מתחת לגרף
  const bk = (ch.books && ch.books.length) ? ch.books[ch.books.length - 1] : null;
  const parts = [];
  if (bk) {{
    parts.push(`Bid/Ask: <span class="num">${{fmtNum(bk.best_bid,3)}} / ${{fmtNum(bk.best_ask,3)}}</span>`);
    parts.push(`עומק: <span class="num">$${{Math.round((bk.bid_depth||0)+(bk.ask_depth||0))}}</span>`);
    parts.push(`חוסר-איזון ספר: <span class="num">${{fmtSign(bk.imbalance,2)}}</span>`);
  }}
  if (intel) {{
    parts.push(`Z-Score: <span class="num">${{intel.z_score !== null ? fmtSign(intel.z_score,2) : '—'}}</span>`);
    parts.push(`נפח יחסי: <span class="num">${{fmtNum(intel.volume_ratio,1)}}x</span>`);
  }}
  document.getElementById('chart-intel-bar').innerHTML = parts.join(' &nbsp;|&nbsp; ');

  const mNews = ch.matched_news || [];
  document.getElementById('chart-news-box').innerHTML = mNews.length
    ? 'כתבות קשורות: ' + mNews.slice(0, 3).map(t => `<span style="color:var(--text-2)">${{esc(t)}}</span>`).join(' · ')
    : 'אין התראות חדשות ישירות על שוק זה';
}}

window.addEventListener('resize', () => {{
  if (ACTIVE_TAB === 'overview') drawEquityChart();
  if (ACTIVE_TAB === 'markets') drawPriceChart();
}});

renderAll();
if (LIVE_ORIGIN && {refresh_ms} > 0) {{
  setInterval(refreshAll, {refresh_ms});
}}
</script>
</body>
</html>
"""
