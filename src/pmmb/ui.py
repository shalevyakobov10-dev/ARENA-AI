"""
PMMB Command Center — ממשק מסחר ולמידה בסגנון Apple macOS Sequoia / Stocks (RTL).

תכנון ממוקד:
  - בהירות, מרווח ופשטות בסגנון Apple HIG: כל מה שצריך במסך ברור אחד, בלי רעש ובלי כפילות.
  - 5 סביבות עבודה: סקירה ומסחר | חוזים (PERPS ×50) | שווקים וגרפים | חדשות ולמידה | תפעול אוטונומי.
  - כולל Spotlight (⌘K / Ctrl+K), תיק מאוחד חי, גרפי נרות OHLC, תיזת סוחר אנושית ומעבדת What-If.
  - 100% self-contained: אפס URLs חיצוניים ואפס אימוג'ים קרטוניים.
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
    --bg: #000000;
    --surface: rgba(28, 28, 30, 0.68);
    --surface-elev: rgba(38, 38, 42, 0.78);
    --surface-subtle: rgba(255, 255, 255, 0.035);
    --border: rgba(255, 255, 255, 0.085);
    --border-strong: rgba(255, 255, 255, 0.16);
    --text: #f5f5f7;
    --text-2: #aeaeb2;
    --text-3: #8e8e93;
    --accent: #0a84ff;
    --accent-soft: rgba(10, 132, 255, 0.15);
    --green: #30d158;
    --green-soft: rgba(48, 209, 88, 0.15);
    --red: #ff453a;
    --red-soft: rgba(255, 69, 58, 0.15);
    --amber: #ff9f0a;
    --amber-soft: rgba(255, 159, 10, 0.15);
    --purple: #bf5af2;
    --radius: 20px;
    --radius-sm: 12px;
    --ease: cubic-bezier(0.22, 1, 0.36, 1);
  }}
  * {{ box-sizing: border-box; }}
  html, body {{
    margin: 0; padding: 0; color: var(--text); min-height: 100vh;
    background:
      radial-gradient(ellipse 70% 45% at 15% -8%, rgba(10, 132, 255, 0.13), transparent 65%),
      radial-gradient(ellipse 55% 40% at 85% 4%, rgba(94, 92, 230, 0.09), transparent 60%),
      #000000;
    background-attachment: fixed;
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", "Helvetica Neue", Arial, sans-serif;
    font-size: 13.5px; line-height: 1.5; -webkit-font-smoothing: antialiased;
    letter-spacing: -0.008em;
  }}
  .num {{ font-variant-numeric: tabular-nums; direction: ltr; unicode-bidi: embed; display: inline-block; }}
  .mono {{ font-family: "SF Mono", ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }}

  /* --- Apple Unified Toolbar --- */
  .topbar {{
    position: sticky; top: 0; z-index: 40;
    background: rgba(14, 14, 16, 0.72);
    backdrop-filter: saturate(190%) blur(28px);
    -webkit-backdrop-filter: saturate(190%) blur(28px);
    border-bottom: 1px solid rgba(255, 255, 255, 0.075);
  }}
  .topbar-inner {{
    max-width: 1380px; margin: 0 auto; padding: 0 24px;
    height: 60px; display: flex; align-items: center; justify-content: space-between; gap: 16px;
  }}
  .brand {{ display: flex; align-items: center; gap: 11px; flex-shrink: 0; }}
  .brand-mark {{
    width: 34px; height: 34px; border-radius: 10px;
    background: linear-gradient(155deg, rgba(255,255,255,0.16) 0%, rgba(10,132,255,0.24) 100%);
    border: 1px solid rgba(255,255,255,0.18);
    box-shadow: inset 0 1px 0 rgba(255,255,255,0.22);
    display: grid; place-items: center; color: #ffffff;
  }}
  .brand-title {{ font-weight: 600; font-size: 14.5px; letter-spacing: -0.02em; }}
  .brand-sub {{ font-size: 11px; color: var(--text-3); }}

  /* --- Segmented Navigation Control --- */
  .nav-tabs {{
    display: flex; align-items: center; gap: 2px;
    background: rgba(118, 118, 128, 0.2);
    border: 1px solid rgba(255, 255, 255, 0.08);
    padding: 3px; border-radius: 999px;
  }}
  .nav-tab {{
    background: transparent; border: none; color: var(--text-2);
    padding: 6px 14px; border-radius: 999px; cursor: pointer;
    font-size: 12.5px; font-weight: 500; transition: all 0.2s var(--ease);
    display: inline-flex; align-items: center; gap: 6px; white-space: nowrap;
  }}
  .nav-tab:hover {{ color: var(--text); }}
  .nav-tab.active {{
    background: rgba(255, 255, 255, 0.16); color: #ffffff; font-weight: 600;
    box-shadow: 0 2px 10px rgba(0,0,0,0.35), inset 0 1px 0 rgba(255,255,255,0.22);
  }}

  .top-actions {{ display: flex; align-items: center; gap: 8px; flex-shrink: 0; }}
  .ap-pill {{
    display: inline-flex; align-items: center; gap: 7px; cursor: pointer;
    padding: 6px 13px; border-radius: 999px; font-size: 12px; font-weight: 500;
    background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.11); color: var(--text);
    transition: all 0.18s var(--ease);
  }}
  .ap-pill:hover {{ background: rgba(255,255,255,0.12); border-color: rgba(255,255,255,0.22); }}
  .ap-pill:active {{ transform: scale(0.97); }}
  .dot {{ width: 7px; height: 7px; border-radius: 50%; background: var(--text-3); flex-shrink: 0; }}
  .dot.ok {{ background: var(--green); box-shadow: 0 0 0 3px var(--green-soft); }}
  .dot.warn {{ background: var(--amber); box-shadow: 0 0 0 3px var(--amber-soft); }}
  .dot.err {{ background: var(--red); box-shadow: 0 0 0 3px var(--red-soft); }}

  /* --- Apple Pill Controls --- */
  .btn {{
    background: rgba(255, 255, 255, 0.08); color: var(--text);
    border: 1px solid rgba(255, 255, 255, 0.13); border-radius: 999px;
    padding: 6px 14px; font-size: 12.5px; font-weight: 500;
    cursor: pointer; transition: all 0.18s var(--ease);
    display: inline-flex; align-items: center; justify-content: center; gap: 6px; white-space: nowrap;
  }}
  .btn:hover {{ background: rgba(255, 255, 255, 0.14); border-color: rgba(255,255,255,0.24); }}
  .btn:active {{ transform: scale(0.96); }}
  .btn-icon {{ width: 32px; height: 32px; padding: 0; border-radius: 50%; }}
  .btn-primary {{
    background: var(--accent); border-color: rgba(255,255,255,0.2); color: #fff; font-weight: 600;
    box-shadow: 0 4px 14px rgba(10, 132, 255, 0.32);
  }}
  .btn-primary:hover {{ background: #2190ff; }}
  .btn-danger {{ background: var(--red-soft); border-color: rgba(255,69,58,0.35); color: #ff8a82; }}
  .btn-danger:hover {{ background: rgba(255,69,58,0.25); }}
  .btn-ghost {{ background: rgba(255,255,255,0.035); border-color: var(--border); color: var(--text-2); }}
  .btn-ghost:hover {{ color: var(--text); background: rgba(255,255,255,0.09); }}
  .btn-xs {{ padding: 4px 11px; font-size: 11px; }}
  .btn-xs.active {{ background: rgba(255,255,255,0.16); border-color: rgba(255,255,255,0.22); color: #fff; font-weight: 600; }}

  .input {{
    background: rgba(118, 118, 128, 0.16); color: var(--text);
    border: 1px solid rgba(255,255,255,0.09); border-radius: 12px;
    padding: 8px 12px; font-size: 12.5px; outline: none; width: 100%;
    transition: border-color 0.18s ease, background 0.18s ease;
  }}
  .input:focus {{ border-color: var(--accent); background: rgba(118, 118, 128, 0.24); }}

  /* --- Spacious Apple Layout --- */
  .wrap {{ max-width: 1380px; margin: 0 auto; padding: 24px 24px 64px; }}
  .banner {{
    padding: 13px 18px; border-radius: 16px; margin-bottom: 18px;
    font-size: 13px; display: flex; align-items: center; justify-content: space-between; gap: 12px;
  }}
  .banner.err {{ background: var(--red-soft); border: 1px solid rgba(255,69,58,0.38); color: #ffd2cf; }}

  /* --- Unified Hero Card --- */
  .hero {{
    background: linear-gradient(140deg, rgba(32,32,36,0.78) 0%, rgba(20,24,34,0.72) 100%);
    backdrop-filter: saturate(180%) blur(28px); -webkit-backdrop-filter: saturate(180%) blur(28px);
    border: 1px solid rgba(255,255,255,0.11);
    box-shadow: inset 0 1px 0 rgba(255,255,255,0.1), 0 14px 40px rgba(0,0,0,0.45);
    border-radius: 24px; padding: 22px 26px; margin-bottom: 18px;
  }}
  .hero-top {{
    display: flex; align-items: flex-end; justify-content: space-between; gap: 24px; flex-wrap: wrap;
    padding-bottom: 18px; border-bottom: 1px solid rgba(255,255,255,0.075);
  }}
  .hero-nav {{ font-size: 34px; font-weight: 700; letter-spacing: -0.035em; color: #ffffff; line-height: 1.1; }}
  .hero-alloc {{ height: 6px; border-radius: 999px; background: rgba(255,255,255,0.08); overflow: hidden; display: flex; min-width: 260px; margin-top: 8px; }}
  .hero-stats {{
    display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 16px; padding-top: 16px;
  }}
  .stat-cell-lbl {{ font-size: 11px; color: var(--text-3); margin-bottom: 2px; }}
  .stat-cell-val {{ font-size: 17px; font-weight: 600; color: var(--text); letter-spacing: -0.02em; }}

  /* --- Compact Metric Strip (Perps & Learning) --- */
  .metric-strip {{
    display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px; margin-bottom: 18px;
  }}
  .metric-tile {{
    background: var(--surface); backdrop-filter: saturate(180%) blur(24px);
    border: 1px solid var(--border); box-shadow: inset 0 1px 0 rgba(255,255,255,0.06);
    border-radius: 18px; padding: 15px 18px;
  }}
  .metric-lbl {{ font-size: 11px; color: var(--text-3); font-weight: 500; }}
  .metric-val {{ font-size: 21px; font-weight: 700; color: #ffffff; letter-spacing: -0.025em; margin-top: 4px; }}
  .metric-sub {{ font-size: 11px; color: var(--text-2); margin-top: 3px; }}

  .grid-2 {{ display: grid; grid-template-columns: 1.5fr 1fr; gap: 18px; margin-bottom: 18px; }}
  .grid-even {{ display: grid; grid-template-columns: 1fr 1fr; gap: 18px; margin-bottom: 18px; }}
  .desk-grid {{ display: grid; grid-template-columns: 330px minmax(0, 1fr); gap: 18px; align-items: start; }}

  .card {{
    background: var(--surface);
    backdrop-filter: saturate(180%) blur(24px);
    -webkit-backdrop-filter: saturate(180%) blur(24px);
    border: 1px solid var(--border);
    box-shadow: inset 0 1px 0 rgba(255,255,255,0.06), 0 10px 32px rgba(0,0,0,0.4);
    border-radius: var(--radius); overflow: hidden; margin-bottom: 18px;
  }}
  .grid-2 .card, .grid-even .card, .desk-grid .card {{ margin-bottom: 0; }}
  .card-head {{
    padding: 14px 20px; border-bottom: 1px solid rgba(255,255,255,0.065);
    display: flex; align-items: center; justify-content: space-between; gap: 10px; flex-wrap: wrap;
  }}
  .card-title {{ font-size: 14px; font-weight: 600; color: #ffffff; letter-spacing: -0.012em; }}
  .card-meta {{ font-size: 11.5px; color: var(--text-3); }}
  .card-body {{ padding: 18px 20px; }}
  .card-body.flush {{ padding: 0; }}

  /* --- Inner Segmented Pill --- */
  .seg-sm {{
    display: inline-flex; gap: 2px; padding: 3px; border-radius: 999px;
    background: rgba(118,118,128,0.18); border: 1px solid rgba(255,255,255,0.07);
  }}
  .seg-sm button {{
    background: transparent; border: none; color: var(--text-3);
    padding: 4px 11px; border-radius: 999px; font-size: 11.5px; font-weight: 500; cursor: pointer;
    transition: all 0.16s ease;
  }}
  .seg-sm button.active {{ background: rgba(255,255,255,0.15); color: #fff; font-weight: 600; }}

  /* --- Clean Tables & Meters --- */
  .table-wrap {{ overflow-x: auto; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 12.5px; }}
  th {{
    text-align: right; padding: 10px 16px; font-weight: 500; font-size: 11px;
    color: var(--text-3); border-bottom: 1px solid rgba(255,255,255,0.065);
    background: rgba(255,255,255,0.018); white-space: nowrap;
  }}
  td {{ padding: 11px 16px; border-bottom: 1px solid rgba(255,255,255,0.05); color: var(--text-2); vertical-align: middle; }}
  tr:last-child td {{ border-bottom: none; }}
  tr.clickable {{ cursor: pointer; transition: background 0.14s ease; }}
  tr.clickable:hover td {{ background: rgba(255,255,255,0.04); }}

  .range-meter {{ display: flex; align-items: center; gap: 8px; min-width: 140px; }}
  .range-track {{ flex: 1; height: 4px; border-radius: 99px; background: rgba(255,255,255,0.1); position: relative; }}
  .range-fill {{ position: absolute; top: 0; height: 100%; border-radius: 99px; background: var(--accent); }}
  .range-pin {{
    position: absolute; top: -3px; width: 4px; height: 10px; border-radius: 99px; background: #fff;
    transform: translateX(-50%); box-shadow: 0 0 6px rgba(255,255,255,0.75);
  }}

  /* --- Airy 2-Line Watchlist --- */
  .wl-scroll {{ max-height: 620px; overflow-y: auto; }}
  .wl-item {{ padding: 12px 18px; border-bottom: 1px solid rgba(255,255,255,0.055); cursor: pointer; transition: background 0.14s; }}
  .wl-item:hover {{ background: rgba(255,255,255,0.035); }}
  .wl-item.active {{ background: rgba(10,132,255,0.14); border-right: 3px solid var(--accent); }}
  .wl-top {{ display: flex; justify-content: space-between; align-items: center; gap: 8px; margin-bottom: 4px; }}
  .wl-q {{ font-size: 13px; font-weight: 500; color: var(--text); line-height: 1.35; }}
  .wl-sub {{ display: flex; justify-content: space-between; align-items: center; font-size: 11.5px; color: var(--text-3); gap: 8px; }}

  .ob-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }}
  .ob-row {{ position: relative; display: flex; justify-content: space-between; padding: 5px 9px; font-size: 11.5px; border-radius: 8px; margin-bottom: 3px; overflow: hidden; }}
  .ob-bar {{ position: absolute; top: 0; bottom: 0; opacity: 0.18; pointer-events: none; }}
  .ob-bid .ob-bar {{ right: 0; background: var(--green); }}
  .ob-ask .ob-bar {{ left: 0; background: var(--red); }}

  .badge {{
    display: inline-flex; align-items: center; padding: 2px 9px; border-radius: 999px;
    font-size: 10.5px; font-weight: 600; border: 1px solid transparent; white-space: nowrap;
  }}
  .badge-ok {{ background: var(--green-soft); color: #67f589; border-color: rgba(48,209,88,0.26); }}
  .badge-warn {{ background: var(--amber-soft); color: #ffc15a; border-color: rgba(255,159,10,0.26); }}
  .badge-err {{ background: var(--red-soft); color: #ff857d; border-color: rgba(255,69,58,0.26); }}
  .badge-info {{ background: var(--accent-soft); color: #66b4ff; border-color: rgba(10,132,255,0.26); }}
  .badge-mute {{ background: rgba(255,255,255,0.06); color: var(--text-2); border-color: rgba(255,255,255,0.08); }}

  .bar-row {{ margin-bottom: 14px; }}
  .bar-row:last-child {{ margin-bottom: 0; }}
  .bar-top {{ display: flex; justify-content: space-between; font-size: 12px; margin-bottom: 6px; color: var(--text-2); }}
  .bar-track {{ height: 5px; border-radius: 99px; background: rgba(255,255,255,0.09); overflow: hidden; }}
  .bar-fill {{ height: 100%; border-radius: 99px; background: var(--accent); transition: width 0.35s var(--ease); }}

  /* --- Canvases & Tooltips --- */
  .chart-wrap {{ position: relative; width: 100%; height: 285px; }}
  .rsi-wrap {{ position: relative; width: 100%; height: 78px; margin-top: 6px; border-top: 1px solid var(--border); padding-top: 4px; }}
  .eq-wrap {{ position: relative; width: 100%; height: 205px; }}
  canvas.plot {{ width: 100%; height: 100%; display: block; cursor: crosshair; }}
  .tooltip {{
    position: absolute; top: 8px; right: 12px; pointer-events: none;
    background: rgba(28, 28, 30, 0.9); border: 1px solid rgba(255,255,255,0.16);
    border-radius: 10px; padding: 6px 11px; font-size: 11px; color: #ffffff;
    display: none; backdrop-filter: blur(18px); z-index: 10;
  }}

  /* --- Apple Reader & Grouped Lists --- */
  .filter-pills {{ display: flex; gap: 6px; flex-wrap: wrap; }}
  .pill-btn {{
    background: rgba(255,255,255,0.04); color: var(--text-2); border: 1px solid rgba(255,255,255,0.08);
    border-radius: 999px; padding: 4px 12px; font-size: 11.5px; cursor: pointer; transition: all 0.15s;
  }}
  .pill-btn:hover {{ background: rgba(255,255,255,0.09); color: var(--text); }}
  .pill-btn.active {{ background: rgba(255,255,255,0.16); color: #ffffff; border-color: rgba(255,255,255,0.22); font-weight: 600; }}

  .news-item {{
    padding: 14px 20px; border-bottom: 1px solid rgba(255,255,255,0.055);
    display: flex; align-items: flex-start; justify-content: space-between; gap: 14px;
  }}
  .news-item:last-child {{ border-bottom: none; }}
  .news-title {{ color: var(--text); font-size: 13px; font-weight: 500; line-height: 1.45; }}
  .news-meta {{ font-size: 11px; color: var(--text-3); margin-top: 4px; display: flex; gap: 10px; flex-wrap: wrap; }}

  .tape-item {{
    padding: 10px 18px; border-bottom: 1px solid rgba(255,255,255,0.05);
    display: flex; align-items: baseline; gap: 10px; font-size: 12px;
  }}
  .tape-item:last-child {{ border-bottom: none; }}

  .kv-list {{ display: grid; grid-template-columns: 1fr 1fr; gap: 4px 22px; }}
  .kv-item {{
    display: flex; justify-content: space-between; align-items: center;
    padding: 9px 0; border-bottom: 1px solid rgba(255,255,255,0.055); font-size: 12.5px;
  }}
  .kv-item:last-child {{ border-bottom: none; }}
  .kv-k {{ color: var(--text-3); }}
  .kv-v {{ color: var(--text); font-weight: 500; }}

  .thesis-summary {{
    padding: 10px 14px; border-radius: 12px; background: rgba(255,255,255,0.04);
    border: 1px solid rgba(255,255,255,0.07); color: var(--text); font-size: 12.5px; margin-bottom: 12px;
  }}

  /* --- Apple Range Sliders & Spotlight Search (⌘K) --- */
  .slider-row {{ display: flex; flex-direction: column; gap: 6px; }}
  .slider-row input[type=range] {{
    -webkit-appearance: none; appearance: none; width: 100%; height: 4px; border-radius: 99px;
    background: rgba(255,255,255,0.16); outline: none;
  }}
  .slider-row input[type=range]::-webkit-slider-thumb {{
    -webkit-appearance: none; appearance: none; width: 16px; height: 16px; border-radius: 50%;
    background: #ffffff; box-shadow: 0 2px 8px rgba(0,0,0,0.5); cursor: pointer;
  }}
  .spot-overlay {{
    position: fixed; inset: 0; z-index: 90; background: rgba(0,0,0,0.62);
    backdrop-filter: blur(12px); display: none; align-items: flex-start; justify-content: center; padding-top: 11vh;
  }}
  .spot-overlay.open {{ display: flex; }}
  .spot-box {{
    width: min(620px, 92vw); background: rgba(28,28,30,0.92); backdrop-filter: saturate(190%) blur(32px);
    border: 1px solid rgba(255,255,255,0.18); border-radius: 20px; overflow: hidden;
    box-shadow: 0 28px 80px rgba(0,0,0,0.75), inset 0 1px 0 rgba(255,255,255,0.15);
  }}
  .spot-input {{
    width: 100%; padding: 16px 20px; background: transparent; border: none;
    border-bottom: 1px solid rgba(255,255,255,0.09); color: #ffffff; font-size: 15px; outline: none;
  }}
  .spot-list {{ max-height: 360px; overflow-y: auto; }}
  .spot-item {{
    padding: 11px 18px; display: flex; align-items: center; justify-content: space-between; gap: 10px;
    border-bottom: 1px solid rgba(255,255,255,0.05); cursor: pointer; transition: background 0.12s;
  }}
  .spot-item:hover {{ background: rgba(10,132,255,0.18); }}

  .toast {{
    position: fixed; bottom: 22px; left: 22px; z-index: 60;
    background: rgba(28, 28, 30, 0.9); backdrop-filter: saturate(180%) blur(24px);
    border: 1px solid rgba(255,255,255,0.18); color: #ffffff;
    padding: 12px 18px; border-radius: 14px; font-size: 12.5px; font-weight: 500;
    box-shadow: 0 16px 40px rgba(0,0,0,0.55); display: none; max-width: 420px;
  }}
  .tab-pane {{ display: none; }}
  .tab-pane.active {{ display: block; }}

  .pos {{ color: var(--green); }}
  .neg {{ color: var(--red); }}

  @media (max-width: 1120px) {{
    .desk-grid {{ grid-template-columns: 1fr; }}
    .wl-scroll {{ max-height: 290px; }}
  }}
  @media (max-width: 960px) {{
    .hero-stats, .metric-strip {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
    .grid-2, .grid-even {{ grid-template-columns: 1fr; }}
    .topbar-inner {{ height: auto; padding: 10px 14px; flex-wrap: wrap; }}
  }}
  @media (max-width: 640px) {{
    .wrap {{ padding: 14px 12px 40px; }}
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
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
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
      <button class="nav-tab" data-tab="perps">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"></polygon></svg>
        חוזים (PERPS ×50)
      </button>
      <button class="nav-tab" data-tab="markets">שווקים וגרפים</button>
      <button class="nav-tab" data-tab="intel">חדשות ולמידה</button>
      <button class="nav-tab" data-tab="system">תפעול אוטונומי</button>
    </nav>

    <div class="top-actions">
      <button class="btn btn-ghost" onclick="openSpotlight()" title="חיפוש ופקודות (⌘K)">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>
        <span class="mono" style="font-size:10.5px;opacity:0.75">⌘K</span>
      </button>
      <button class="ap-pill" id="btn-toggle-ap" onclick="toggleAutopilot()" title="לחץ להפעלה או השהיה">
        <span class="dot" id="live-dot"></span>
        <span id="live-label">מצב</span>
      </button>
      <button class="btn btn-ghost btn-icon" onclick="refreshAll()" title="רענון מיידי" aria-label="רענן">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 4 23 10 17 10"></polyline><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"></path></svg>
      </button>
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
    <div id="combined-hero" class="hero"></div>

    <div class="grid-2">
      <div class="card">
        <div class="card-head">
          <span class="card-title">עקומת הון חיה</span>
          <div style="display:flex;align-items:center;gap:10px">
            <span class="card-meta" id="eq-meta">—</span>
            <div class="seg-sm">
              <button class="active" id="eq-sw-poly" onclick="setEqArm('poly', this)">Polymarket</button>
              <button id="eq-sw-perps" onclick="setEqArm('perps', this)">PERPS ×50</button>
            </div>
          </div>
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
          <span class="card-title">שומרי סיכון (דו-זרועי)</span>
          <span class="card-meta" id="risk-meta">מוגן אוטומטית</span>
        </div>
        <div class="card-body" id="risk-bars"></div>
      </div>
    </div>

    <div class="card">
      <div class="card-head">
        <span class="card-title">פוזיציות חיות עכשיו</span>
        <span class="card-meta" id="all-pos-meta">לחיצה על שורה פותחת את גרף הנכס</span>
      </div>
      <div class="card-body flush">
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>נכס / זרוע</th>
                <th>גודל ופוזיציה</th>
                <th>כניסה ← נוכחי</th>
                <th>מד הגנה ויעד</th>
                <th>רווח / הפסד</th>
              </tr>
            </thead>
            <tbody id="pos-tbody"></tbody>
          </table>
        </div>
      </div>
    </div>

    <div class="card">
      <div class="card-head">
        <span class="card-title">יומן פעילות ועסקאות</span>
        <div class="seg-sm">
          <button class="active" onclick="setActView('trades', this)">עסקאות סגורות</button>
          <button onclick="setActView('tape', this)">זרם החלטות חי</button>
        </div>
      </div>
      <div class="card-body flush" id="act-trades-pane">
        <div class="table-wrap">
          <table>
            <thead><tr><th>מועד</th><th>נכס / זרוע</th><th>סוג</th><th>רווח / הפסד</th><th>סיבה</th></tr></thead>
            <tbody id="trades-tbody"></tbody>
          </table>
        </div>
      </div>
      <div class="card-body flush" id="act-tape-pane" style="display:none">
        <div id="decision-tape"></div>
      </div>
    </div>
  </section>

  <!-- ========== TAB PERPS: חוזים תמידיים עד ×50 ========== -->
  <section id="tab-perps" class="tab-pane">
    <div style="display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;margin-bottom:16px">
      <div>
        <div style="font-size:17px;font-weight:700;letter-spacing:-0.02em">חוזים תמידיים (PERPS ×50)</div>
        <div style="font-size:12px;color:var(--text-3)" id="perps-sub-hdr">OKX + Hyperliquid · Isolated Margin</div>
      </div>
      <div style="display:flex;gap:8px;flex-wrap:wrap">
        <button class="btn btn-primary" onclick="postAction('/api/perps/cycle', {{}})">מחזור PERPS עכשיו</button>
        <button class="btn" onclick="postAction('/api/perps/learn', {{}})">כיול Walk-Forward</button>
        <button class="btn btn-ghost" id="btn-perps-toggle" onclick="postAction('/api/perps/toggle', {{}})">השהה</button>
      </div>
    </div>

    <div class="metric-strip" id="perps-kpi-row"></div>

    <div class="card">
      <div class="card-head">
        <span class="card-title">פוזיציות PERPS פתוחות</span>
        <span class="card-meta">לחיצה טוענת את גרף החוזה וקווי SL / TP / LIQ</span>
      </div>
      <div class="card-body flush">
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>חוזה</th><th>כיוון ומינוף</th><th>מרג׳ין (נומינלי)</th>
                <th>כניסה ← נוכחי</th><th>הגנה / יעד / LIQ</th><th>רווח / הפסד</th>
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
            <span class="card-title">רדאר חוזים</span>
            <span class="card-meta" id="perps-intel-cnt">—</span>
          </div>
          <input type="text" id="perps-search" class="input" placeholder="חיפוש חוזה (BTC, ETH, SOL...)" oninput="renderPerps()">
        </div>
        <div class="wl-scroll" id="perps-wl"></div>
      </div>

      <div style="display:flex;flex-direction:column;gap:16px">
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

        <div class="card">
          <div class="card-head">
            <span class="card-title">תיזת הסוחר לחוזה</span>
            <span class="card-meta" id="perps-thesis-badge">—</span>
          </div>
          <div class="card-body" id="perps-thesis-box"></div>
        </div>

        <div class="card">
          <div class="card-head">
            <span class="card-title">היסטוריה ומעבדת אסטרטגיה</span>
            <div class="seg-sm">
              <button class="active" onclick="setPerpSubView('history', this)">עסקאות וכיול</button>
              <button onclick="setPerpSubView('sim', this)">סימולציית What-If</button>
            </div>
          </div>
          <div id="perp-sub-history" class="card-body flush">
            <div class="table-wrap">
              <table>
                <thead><tr><th>מועד</th><th>חוזה</th><th>כיוון / מינוף</th><th>PnL</th><th>סיבה</th></tr></thead>
                <tbody id="perps-trades-tbody"></tbody>
              </table>
            </div>
            <div style="border-top:1px solid var(--border);padding:12px 16px;font-size:11.5px;color:var(--text-3)" id="perps-learn-summary">—</div>
          </div>
          <div id="perp-sub-sim" class="card-body" style="display:none">
            <div style="display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px;margin-bottom:14px">
              <div class="slider-row">
                <div style="display:flex;justify-content:space-between;font-size:11.5px"><span style="color:var(--text-3)">תקרת מינוף</span><strong class="num" id="sim-lev-val">50x</strong></div>
                <input type="range" id="sim-lev" min="5" max="50" step="5" value="50" oninput="document.getElementById('sim-lev-val').textContent=this.value+'x'">
              </div>
              <div class="slider-row">
                <div style="display:flex;justify-content:space-between;font-size:11.5px"><span style="color:var(--text-3)">Stop Loss (ATR)</span><strong class="num" id="sim-sl-val">1.5</strong></div>
                <input type="range" id="sim-sl" min="1.0" max="2.5" step="0.1" value="1.5" oninput="document.getElementById('sim-sl-val').textContent=Number(this.value).toFixed(1)">
              </div>
              <div class="slider-row">
                <div style="display:flex;justify-content:space-between;font-size:11.5px"><span style="color:var(--text-3)">Take Profit (ATR)</span><strong class="num" id="sim-tp-val">2.6</strong></div>
                <input type="range" id="sim-tp" min="1.6" max="4.0" step="0.1" value="2.6" oninput="document.getElementById('sim-tp-val').textContent=Number(this.value).toFixed(1)">
              </div>
              <div class="slider-row">
                <div style="display:flex;justify-content:space-between;font-size:11.5px"><span style="color:var(--text-3)">טריגר Trailing</span><strong class="num" id="sim-trl-val">1.4</strong></div>
                <input type="range" id="sim-trl" min="0.8" max="2.2" step="0.1" value="1.4" oninput="document.getElementById('sim-trl-val').textContent=Number(this.value).toFixed(1)">
              </div>
            </div>
            <div style="display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap">
              <div id="perps-sim-res" style="font-size:12px;color:var(--text-3)">כוון פרמטרים ולחץ להרצה מיידית על נתוני ה-DB.</div>
              <button class="btn btn-primary btn-xs" onclick="runPerpsSimulation()">הרץ סימולציה</button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </section>

  <!-- ========== TAB 2: שווקים וגרפים ========== -->
  <section id="tab-markets" class="tab-pane">
    <div class="desk-grid">
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
          </div>
        </div>
        <div class="wl-scroll" id="wl-list"></div>
      </div>

      <div style="display:flex;flex-direction:column;gap:16px">
        <div class="card">
          <div class="card-head">
            <div>
              <div class="card-title" id="desk-title">בחר שוק מהרדאר</div>
              <div class="card-meta" id="desk-sub">—</div>
            </div>
            <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap">
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
            <div class="rsi-wrap"><canvas id="rsi-canvas" class="plot"></canvas></div>
          </div>
        </div>

        <div class="grid-even">
          <div class="card">
            <div class="card-head">
              <span class="card-title">תיזת הסוחר</span>
              <span class="card-meta" id="thesis-badge">—</span>
            </div>
            <div class="card-body" id="desk-thesis"></div>
          </div>
          <div class="card">
            <div class="card-head">
              <span class="card-title">עומק ספר פקודות</span>
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
    <div class="metric-strip" id="news-pulse-kpis"></div>

    <div class="grid-even">
      <div class="card">
        <div class="card-head" style="flex-direction:column;align-items:stretch;gap:8px">
          <div style="display:flex;justify-content:space-between;align-items:center;gap:8px">
            <span class="card-title">פיד חדשות חי (22+ רשתות)</span>
            <button class="btn btn-ghost btn-xs" onclick="postAction('/api/news-refresh', {{}})">רענן פיד</button>
          </div>
          <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
            <input type="text" id="news-search" class="input" style="max-width:190px" placeholder="חיפוש בכותרת או רשת..." oninput="renderNews()">
            <div class="filter-pills">
              <button class="pill-btn active" onclick="setNewsFilter('ALL', this)">הכל</button>
              <button class="pill-btn" onclick="setNewsFilter('CATALYST', this)">משפיעות</button>
              <button class="pill-btn" onclick="setNewsFilter('MATCHED', this)">קשור לשווקים</button>
              <button class="pill-btn" onclick="setNewsFilter('crypto', this)">קריפטו ומאקרו</button>
            </div>
          </div>
        </div>
        <div class="card-body flush" style="max-height:600px;overflow-y:auto">
          <div id="news-list"></div>
        </div>
      </div>

      <div style="display:flex;flex-direction:column;gap:16px">
        <div class="card">
          <div class="card-head">
            <span class="card-title">מנוע למידה מתמשכת (24/7)</span>
            <button class="btn btn-ghost btn-xs" onclick="postAction('/api/learn', {{apply:true}})">הרץ למידה עכשיו</button>
          </div>
          <div class="card-body" id="learn-insights"></div>
        </div>

        <div class="card">
          <div class="card-head">
            <span class="card-title" id="learn-tab-title">נתוני למידה מאומתים</span>
            <div class="seg-sm">
              <button class="active" onclick="setLearnTab('news', this)">News Alpha</button>
              <button onclick="setLearnTab('signals', this)">דיוק אותות</button>
              <button onclick="setLearnTab('runs', this)">כיולי OOS</button>
            </div>
          </div>
          <div id="learn-pane-news" class="card-body flush">
            <div class="table-wrap">
              <table>
                <thead><tr><th>מקור חדשות</th><th>כתבות</th><th>דיוק כיווני</th><th>תזוזה ±%</th></tr></thead>
                <tbody id="news-alpha-tbody"></tbody>
              </table>
            </div>
          </div>
          <div id="learn-pane-signals" class="card-body flush" style="display:none">
            <div class="table-wrap">
              <table>
                <thead><tr><th>זרוע / טווח</th><th>דגימות</th><th>הצלחה</th><th>תשואה ממוצעת</th></tr></thead>
                <tbody id="learn-z-tbody"></tbody>
              </table>
            </div>
          </div>
          <div id="learn-pane-runs" class="card-body flush" style="display:none">
            <div class="table-wrap">
              <table>
                <thead><tr><th>מועד</th><th>בסיס</th><th>מועמד</th><th>התמדה</th><th>סטטוס</th></tr></thead>
                <tbody id="learn-runs-tbody"></tbody>
              </table>
            </div>
          </div>
        </div>
      </div>
    </div>
  </section>

  <!-- ========== TAB 4: תפעול אוטונומי (macOS Settings Style) ========== -->
  <section id="tab-system" class="tab-pane">
    <div class="card">
      <div class="card-head">
        <span class="card-title">שליטה ומצב המערכת</span>
        <span class="card-meta">הבוט מתפעל הכל אוטומטית ברקע</span>
      </div>
      <div class="card-body" style="display:flex;gap:10px;flex-wrap:wrap;align-items:center">
        <button class="btn btn-primary" onclick="postAction('/api/autopilot/maintain', {{}})">תחזוקה מלאה עכשיו</button>
        <button class="btn" onclick="postAction('/api/paper-cycle', {{}})">מחזור ניסיון בודד</button>
        <button class="btn" onclick="postAction('/api/backup', {{}})">גיבוי מיידי</button>
        <button class="btn" onclick="postAction('/api/reconcile', {{fix:true}})">אימות DB</button>
        <button class="btn btn-danger" style="margin-right:auto" onclick="postAction('/api/halt', {{reason:'עצירה מהממשק'}})">עצירת חירום</button>
      </div>
    </div>

    <div class="grid-even">
      <div class="card">
        <div class="card-head">
          <span class="card-title">מוכנות למסחר חי (Live)</span>
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

      <div class="card">
        <div class="card-head">
          <span class="card-title">יומן טייס אוטומטי</span>
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
    </div>

    <div class="grid-even">
      <div class="card">
        <div class="card-head">
          <span class="card-title">ביצועי אסטרטגיה מאומתים (Walk-Forward)</span>
        </div>
        <div class="card-body" id="analytics-box"></div>
      </div>
      <div class="card">
        <div class="card-head">
          <span class="card-title">תצורת מסחר פעילה</span>
          <span class="card-meta" id="cfg-mode">paper</span>
        </div>
        <div class="card-body" id="cfg-box"></div>
      </div>
    </div>
  </section>
</main>

<div id="spot-overlay" class="spot-overlay" onclick="if(event.target===this) closeSpotlight()">
  <div class="spot-box">
    <input type="text" id="spot-input" class="spot-input" placeholder="חפש שוק, חוזה PERPS או פקודת מערכת (ESC לסגירה)..." oninput="renderSpotlight()">
    <div id="spot-list" class="spot-list"></div>
  </div>
</div>

<div id="toast" class="toast"></div>

<script>
const INITIAL = {payload};
let STATE = INITIAL;
let ACTIVE_TAB = 'overview';
let EQ_ARM = 'poly';
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
const fmtTime = (ts) => ts ? new Date(Number(ts) * 1000).toLocaleTimeString('he-IL', {{hour:'2-digit', minute:'2-digit'}}) : '—';
const fmtDateTime = (ts) => {{
  if (!ts) return '—';
  const d = new Date(Number(ts) * 1000);
  return d.toLocaleDateString('he-IL', {{day:'2-digit', month:'2-digit'}}) + ' ' + d.toLocaleTimeString('he-IL', {{hour:'2-digit', minute:'2-digit'}});
}};

function showToast(msg, isErr = false) {{
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.style.borderColor = isErr ? 'rgba(255,69,58,0.55)' : 'rgba(10,132,255,0.5)';
  el.style.display = 'block';
  clearTimeout(window.__toastTimer);
  window.__toastTimer = setTimeout(() => {{ el.style.display = 'none'; }}, 3800);
}}

function switchTab(tabId) {{
  ACTIVE_TAB = tabId;
  document.querySelectorAll('.nav-tab').forEach(b => b.classList.toggle('active', b.dataset.tab === tabId));
  document.querySelectorAll('.tab-pane').forEach(p => p.classList.toggle('active', p.id === 'tab-' + tabId));
  if (tabId === 'markets') {{ drawPriceChart(); drawRsiChart(); }}
  if (tabId === 'overview') drawEquityChart();
  if (tabId === 'perps') drawPerpPriceChart();
}}

document.querySelectorAll('.nav-tab').forEach(btn => {{
  btn.addEventListener('click', () => switchTab(btn.dataset.tab));
}});

function switchToMarket(tokenId) {{
  if (!tokenId) return;
  SELECTED_TOKEN = tokenId;
  switchTab('markets');
  renderMarketsIntel();
  loadChart(tokenId, true);
}}

function setEqArm(arm, btn) {{
  EQ_ARM = arm;
  btn.parentElement.querySelectorAll('button').forEach(b => b.classList.toggle('active', b === btn));
  drawEquityChart();
}}

function setActView(view, btn) {{
  btn.parentElement.querySelectorAll('button').forEach(b => b.classList.toggle('active', b === btn));
  document.getElementById('act-trades-pane').style.display = view === 'trades' ? 'block' : 'none';
  document.getElementById('act-tape-pane').style.display = view === 'tape' ? 'block' : 'none';
}}

function setPerpSubView(view, btn) {{
  btn.parentElement.querySelectorAll('button').forEach(b => b.classList.toggle('active', b === btn));
  document.getElementById('perp-sub-history').style.display = view === 'history' ? 'block' : 'none';
  document.getElementById('perp-sub-sim').style.display = view === 'sim' ? 'block' : 'none';
}}

function setLearnTab(tab, btn) {{
  btn.parentElement.querySelectorAll('button').forEach(b => b.classList.toggle('active', b === btn));
  document.getElementById('learn-pane-news').style.display = tab === 'news' ? 'block' : 'none';
  document.getElementById('learn-pane-signals').style.display = tab === 'signals' ? 'block' : 'none';
  document.getElementById('learn-pane-runs').style.display = tab === 'runs' ? 'block' : 'none';
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
      method: 'POST', headers: {{'Content-Type': 'application/json'}}, body: JSON.stringify(body || {{}})
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
  if (!LIVE_ORIGIN) {{ renderDeskPanels(); drawPriceChart(); drawRsiChart(); return; }}
  try {{
    const res = await fetch('/api/chart?token=' + encodeURIComponent(tokenId) + (live ? '&live=1' : ''));
    if (res.ok) {{
      CURRENT_CHART = await res.json();
      renderDeskPanels(); drawPriceChart(); drawRsiChart();
    }}
  }} catch (e) {{}}
}}

async function loadPerpChart(sym, live = false) {{
  if (!sym) return;
  SELECTED_PERP_SYM = sym;
  renderPerps();
  if (!LIVE_ORIGIN) {{ drawPerpPriceChart(); renderPerpThesis(); return; }}
  try {{
    const res = await fetch('/api/perps/chart?symbol=' + encodeURIComponent(sym) + (live ? '&live=1' : ''));
    if (res.ok) {{
      CURRENT_PERP_CHART = await res.json();
      drawPerpPriceChart();
      renderPerpThesis();
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
  drawPerpPriceChart();
  drawPriceChart();
  drawRsiChart();
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
    dot.className = 'dot err'; lbl.textContent = 'מושהה — הפעל';
  }}

  const cyc = tr.cycles || hb.cycle || 0;
  const tel = STATE.telemetry || {{}};
  document.getElementById('sub-status').textContent =
    `${{mode.toUpperCase()}} · מחזור #${{cyc}} · ${{(tel.intel || 0)}} שווקים`;

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
  const comb = STATE.combined || {{}};
  const ps = STATE.perps || {{}};
  const eq = Number(bank.equity || 0);
  const perpEq = Number(ps.equity || 0);
  const cEq = Number(comb.equity || (eq + perpEq));
  const cPoly = Number(comb.poly_equity || eq);
  const cPerp = Number(comb.perps_equity || perpEq);
  const cRet = Number(comb.return_pct || 0);
  const polyPct = cEq > 0 ? (cPoly / cEq * 100) : 50;
  const perpPct = Math.max(0, 100 - polyPct);
  const todayNet = Number(today.realized_pnl || 0) + Number(ps.today_pnl || 0);
  const openAll = Number(comb.open_positions || ((bank.open_positions || 0) + (ps.positions || []).length));
  const closedAll = Number(comb.closed_trades || ((overall.exits || 0) + (ps.closed_trades || 0)));

  const heroEl = document.getElementById('combined-hero');
  if (heroEl) {{
    heroEl.innerHTML = `
      <div class="hero-top">
        <div>
          <div style="font-size:12px;color:var(--text-3);font-weight:500">שווי תיק מאוחד</div>
          <div style="display:flex;align-items:baseline;gap:12px;margin-top:6px">
            <span class="hero-nav num">$${{fmtNum(cEq, 2)}}</span>
            <span class="badge ${{cRet >= 0 ? 'badge-ok' : 'badge-err'}} num">${{fmtSign(cRet, 2)}}%</span>
          </div>
        </div>
        <div style="min-width:280px">
          <div style="display:flex;justify-content:space-between;font-size:11.5px;color:var(--text-2);gap:14px">
            <span>Polymarket <strong class="num" style="color:var(--accent)">$${{fmtNum(cPoly, 2)}}</strong></span>
            <span>PERPS ×50 <strong class="num" style="color:var(--green)">$${{fmtNum(cPerp, 2)}}</strong></span>
          </div>
          <div class="hero-alloc">
            <div style="width:${{polyPct.toFixed(1)}}%;background:var(--accent)"></div>
            <div style="width:${{perpPct.toFixed(1)}}%;background:var(--green)"></div>
          </div>
        </div>
      </div>
      <div class="hero-stats">
        <div>
          <div class="stat-cell-lbl">רווח / הפסד היום</div>
          <div class="stat-cell-val num ${{todayNet >= 0 ? 'pos' : 'neg'}}">${{fmtSign(todayNet, 2)}}</div>
        </div>
        <div>
          <div class="stat-cell-lbl">פוזיציות חיות</div>
          <div class="stat-cell-val num">${{openAll}}</div>
        </div>
        <div>
          <div class="stat-cell-lbl">עסקאות שנסגרו</div>
          <div class="stat-cell-val num">${{closedAll}}</div>
        </div>
        <div>
          <div class="stat-cell-lbl">צבירת Soak</div>
          <div class="stat-cell-val num">${{soak.days || 0}}/${{soak.target_days || 7}} ימים</div>
        </div>
      </div>`;
  }}

  const g = STATE.guards || {{}};
  const pg = ps.guards || {{}};
  const bars = [
    {{ lbl: 'מגבלת הפסד יומי (Poly)', txt: `${{fmtNum(g.daily_loss_used || 0)}} / ${{fmtNum(g.daily_loss_limit || 50)}}`, pct: Math.min(100, Math.max(0, Number(g.daily_loss_used || 0) / Math.max(1, Number(g.daily_loss_limit || 1)) * 100)), color: 'var(--green)' }},
    {{ lbl: 'Drawdown Polymarket', txt: `${{fmtNum(g.drawdown_pct || 0, 1)}}% / ${{fmtNum(g.drawdown_limit_pct || 20, 0)}}%`, pct: Math.min(100, Number(g.drawdown_pct || 0) / Math.max(1, Number(g.drawdown_limit_pct || 20)) * 100), color: 'var(--accent)' }},
    {{ lbl: 'ניצול Margin (PERPS ×50)', txt: `${{fmtNum(pg.used_margin_pct || 0, 1)}}% / ${{pg.max_margin_pct || 65}}%`, pct: Math.min(100, Number(pg.used_margin_pct || 0) / Math.max(1, Number(pg.max_margin_pct || 65)) * 100), color: 'var(--accent)' }},
    {{ lbl: 'Drawdown PERPS', txt: `${{fmtNum(ps.drawdown_pct || 0, 1)}}% / ${{pg.dd_limit_pct || 18}}%`, pct: Math.min(100, Number(ps.drawdown_pct || 0) / Math.max(1, Number(pg.dd_limit_pct || 18)) * 100), color: 'var(--amber)' }},
  ];
  document.getElementById('risk-bars').innerHTML = bars.map(b => `
    <div class="bar-row">
      <div class="bar-top"><span>${{esc(b.lbl)}}</span><span class="num">${{esc(b.txt)}}</span></div>
      <div class="bar-track"><div class="bar-fill" style="width:${{b.pct.toFixed(1)}}%;background:${{b.color}}"></div></div>
    </div>`).join('');

  // טבלה מאוחדת נקייה של כל הפוזיציות החיות (PERPS + Polymarket)
  const polyPos = (STATE.positions || []).map(p => {{
    const sl = Number(p.stop_price || 0), tp = Number(p.target_price || 0);
    const mk = Number(p.mark_price ?? p.avg_price ?? 0);
    const span = Math.max(tp - sl, 0.01);
    const pctPos = Math.max(0, Math.min(100, ((mk - sl) / span) * 100));
    const u = p.unrealized_pnl;
    return {{
      click: `switchToMarket('${{esc(p.token_id)}}')`,
      title: (p.question || p.token_id).slice(0, 48),
      arm: '<span class="badge badge-info">Polymarket</span>',
      sizeTxt: `${{fmtNum(p.size, 1)}} יח׳`,
      pxTxt: `${{fmtNum(p.avg_price, 3)}} ← ${{p.mark_price != null ? fmtNum(p.mark_price, 3) : '—'}}`,
      loLbl: sl ? sl.toFixed(2) : '—',
      hiLbl: tp ? tp.toFixed(2) : '—',
      pct: pctPos,
      u: u,
      uTxt: u != null ? `${{fmtSign(u)}} (${{fmtSign(p.unrealized_pct, 1)}}%)` : '—',
    }};
  }});
  const perpPos = (ps.positions || []).map(p => {{
    const sl = Number(p.stop_price || 0), tp = Number(p.target_price || 0), mk = Number(p.mark_price || p.entry_price || 0);
    const lo = Math.min(sl, tp), hi = Math.max(sl, tp);
    const span = Math.max(hi - lo, 0.0001);
    const pctPos = Math.max(0, Math.min(100, ((mk - lo) / span) * 100));
    const u = Number(p.unrealized_pnl || 0);
    const d = mk > 100 ? 2 : 4;
    return {{
      click: `switchTab('perps'); loadPerpChart('${{esc(p.symbol)}}', true)`,
      title: `${{p.symbol}} (${{(p.exchange || '').toUpperCase()}})`,
      arm: `<span class="badge ${{p.side === 'LONG' ? 'badge-ok' : 'badge-err'}}">${{p.side}} ×${{Number(p.leverage).toFixed(0)}}</span>`,
      sizeTxt: `$${{fmtNum(p.margin_used, 1)}} מרג׳ין`,
      pxTxt: `${{fmtNum(p.entry_price, d)}} ← ${{fmtNum(mk, d)}}`,
      loLbl: p.side === 'LONG' ? sl.toFixed(d) : tp.toFixed(d),
      hiLbl: p.side === 'LONG' ? tp.toFixed(d) : sl.toFixed(d),
      pct: pctPos,
      u: u,
      uTxt: `${{fmtSign(u)}} (${{fmtSign(p.roe_pct, 1)}}%)`,
    }};
  }});
  const allPos = [...perpPos, ...polyPos];
  const metaP = document.getElementById('all-pos-meta');
  if (metaP) metaP.textContent = `${{allPos.length}} פוזיציות פעילות · לחיצה פותחת גרף`;
  document.getElementById('pos-tbody').innerHTML = allPos.length ? allPos.map(r => `
    <tr class="clickable" onclick="${{r.click}}">
      <td style="color:var(--text);font-weight:500">${{esc(r.title)}} <span style="margin-right:6px">${{r.arm}}</span></td>
      <td class="num">${{esc(r.sizeTxt)}}</td>
      <td class="num">${{esc(r.pxTxt)}}</td>
      <td>
        <div class="range-meter">
          <span class="num" style="font-size:10px;color:var(--text-3)">${{r.loLbl}}</span>
          <div class="range-track"><div class="range-pin" style="left:${{r.pct.toFixed(1)}}%"></div></div>
          <span class="num" style="font-size:10px;color:var(--text-3)">${{r.hiLbl}}</span>
        </div>
      </td>
      <td class="num ${{(r.u || 0) >= 0 ? 'pos' : 'neg'}}">${{esc(r.uTxt)}}</td>
    </tr>`).join('') : '<tr><td colspan="5" style="text-align:center;color:var(--text-3);padding:22px">אין פוזיציות פתוחות כרגע</td></tr>';

  // עסקאות סגורות מאוחדות
  const trPoly = (STATE.recent_trades || []).slice(0, 6).map(t => ({{
    ts: t.ts, name: (t.question || '').slice(0, 36), tag: 'Polymarket', rz: Number(t.realized || 0), reason: t.reason || '',
  }}));
  const trPerp = (ps.recent_trades || []).slice(0, 6).map(t => ({{
    ts: t.ts, name: `${{t.symbol}} ×${{Number(t.leverage || 1).toFixed(0)}}`, tag: 'PERPS', rz: Number(t.realized || 0), reason: t.reason || '',
  }}));
  const trAll = [...trPerp, ...trPoly].sort((a, b) => Number(b.ts || 0) - Number(a.ts || 0)).slice(0, 8);
  document.getElementById('trades-tbody').innerHTML = trAll.length ? trAll.map(t => `
    <tr>
      <td class="num" style="color:var(--text-3)">${{fmtDateTime(t.ts)}}</td>
      <td style="color:var(--text)">${{esc(t.name)}}</td>
      <td><span class="badge badge-mute">${{esc(t.tag)}}</span></td>
      <td class="num ${{t.rz >= 0 ? 'pos' : 'neg'}}">${{fmtSign(t.rz)}}</td>
      <td style="color:var(--text-3)">${{esc(t.reason.slice(0, 26))}}</td>
    </tr>`).join('') : '<tr><td colspan="5" style="text-align:center;color:var(--text-3);padding:18px">אין עסקאות סגורות עדיין</td></tr>';

  // זרם החלטות
  const evs = (STATE.events || []).slice(0, 5);
  const sigS = (STATE.signals || []).filter(s => s.direction !== 'FLAT').slice(0, 5);
  const tape = [
    ...sigS.map(s => ({{ ts: s.ts, cls: 'badge-ok', kind: s.direction, msg: `${{(s.question || '').slice(0, 42)}} — ${{s.reason || ''}}`, tok: s.token_id }})),
    ...evs.map(e => ({{ ts: e.ts, cls: e.level === 'ERROR' ? 'badge-err' : 'badge-info', kind: e.kind || 'מערכת', msg: e.msg || '', tok: '' }})),
  ].sort((a, b) => Number(b.ts || 0) - Number(a.ts || 0)).slice(0, 8);
  document.getElementById('decision-tape').innerHTML = tape.length ? tape.map(it => `
    <div class="tape-item" ${{it.tok ? `style="cursor:pointer" onclick="switchToMarket('${{esc(it.tok)}}')"` : ''}}>
      <span class="num" style="color:var(--text-3)">${{fmtTime(it.ts)}}</span>
      <span class="badge ${{it.cls}}">${{esc(it.kind)}}</span>
      <span style="color:var(--text-2)">${{esc(it.msg)}}</span>
    </div>`).join('') : '<div style="padding:18px;text-align:center;color:var(--text-3)">זרם ההחלטות יתעדכן במחזור הבא</div>';
}}

function renderPerps() {{
  const ps = STATE.perps || {{}};
  const tr = STATE.trader || {{}};
  const enabled = ps.enabled !== false;
  const btnT = document.getElementById('btn-perps-toggle');
  if (btnT) btnT.textContent = enabled ? 'השהה' : 'הפעל';
  const hdrSub = document.getElementById('perps-sub-hdr');
  if (hdrSub) hdrSub.textContent = `${{(ps.exchanges || ['okx','hyperliquid']).join(' + ').toUpperCase()}} · ${{(ps.mode || 'paper').toUpperCase()}} · מקס׳ ×${{ps.max_leverage || 50}} · מחזורים: ${{tr.perps_cycles || 0}}`;

  const eq = Number(ps.equity || 1000);
  const ov = Number(ps.overall_pnl || 0);
  const g = ps.guards || {{}};
  const pkpis = [
    {{ l: 'הון PERPS (USDC)', v: fmtNum(eq), s: `מזומן פנוי $${{fmtNum(ps.cash || 0)}} · DD ${{fmtNum(ps.drawdown_pct || 0, 1)}}%`, c: '' }},
    {{ l: 'מינוף ממוצע ומרג׳ין', v: `×${{fmtNum(ps.avg_leverage || 0, 1)}}`, s: `$${{fmtNum(ps.margin_used || 0)}} מרג׳ין · ניצול ${{fmtNum(g.used_margin_pct || 0, 1)}}%`, c: '' }},
    {{ l: 'PnL + Funding', v: fmtSign(ov), s: `היום ${{fmtSign(ps.today_pnl || 0)}} · Funding ${{fmtSign(ps.funding_net || 0, 3)}}`, c: ov >= 0 ? 'pos' : 'neg' }},
    {{ l: 'דיוק / Profit Factor', v: `${{fmtNum(ps.win_rate_pct || 0, 0)}}%`, s: `${{ps.closed_trades || 0}} עסקאות · PF ${{fmtNum(ps.profit_factor || 0, 2)}}`, c: '' }},
  ];
  const kpiEl = document.getElementById('perps-kpi-row');
  if (kpiEl) kpiEl.innerHTML = pkpis.map(k => `<div class="metric-tile"><div class="metric-lbl">${{esc(k.l)}}</div><div class="metric-val num ${{k.c}}">${{esc(k.v)}}</div><div class="metric-sub">${{esc(k.s)}}</div></div>`).join('');

  const pos = ps.positions || [];
  const posEl = document.getElementById('perps-pos-tbody');
  if (posEl) posEl.innerHTML = pos.length ? pos.map(p => {{
    const u = Number(p.unrealized_pnl || 0), roe = Number(p.roe_pct || 0), liqD = Number(p.liq_distance_pct || 0);
    const d = Number(p.entry_price || 0) > 100 ? 2 : 4;
    return `<tr class="clickable" onclick="loadPerpChart('${{esc(p.symbol)}}', true)">
      <td style="color:var(--text);font-weight:600">${{esc(p.symbol)}} <span style="color:var(--text-3);font-weight:400">${{esc((p.exchange || '').toUpperCase())}}</span></td>
      <td><span class="badge ${{p.side === 'LONG' ? 'badge-ok' : 'badge-err'}}">${{esc(p.side)}} ×${{Number(p.leverage).toFixed(0)}}</span></td>
      <td class="num">$${{fmtNum(p.margin_used, 2)}} <span style="color:var(--text-3)">($${{Math.round(p.notional).toLocaleString()}})</span></td>
      <td class="num">${{fmtNum(p.entry_price, d)}} ← ${{fmtNum(p.mark_price, d)}}</td>
      <td class="num"><span style="color:var(--text-3)">${{fmtNum(p.stop_price, d)}} / ${{fmtNum(p.target_price, d)}}</span> · <span style="color:${{liqD < 4 ? 'var(--red)' : 'var(--amber)'}}">LIQ ${{fmtNum(p.liquidation_price, d)}}</span></td>
      <td class="num ${{u >= 0 ? 'pos' : 'neg'}}">${{fmtSign(roe, 1)}}% (${{fmtSign(u, 2)}})</td>
    </tr>`;
  }}).join('') : '<tr><td colspan="6" style="text-align:center;color:var(--text-3);padding:18px">אין פוזיציות PERPS פתוחות כרגע</td></tr>';

  const intel = ps.intel || [];
  const q = (document.getElementById('perps-search')?.value || '').trim().toLowerCase();
  const filt = intel.filter(r => !q || String(r.symbol || '').toLowerCase().includes(q));
  const icEl = document.getElementById('perps-intel-cnt');
  if (icEl) icEl.textContent = `${{filt.length}} חוזים`;
  const wlEl = document.getElementById('perps-wl');
  if (wlEl) wlEl.innerHTML = filt.length ? filt.map(r => {{
    const regCls = r.regime === 'TREND_UP' ? 'badge-ok' : (r.regime === 'TREND_DOWN' ? 'badge-err' : 'badge-info');
    return `<div class="wl-item ${{r.symbol === SELECTED_PERP_SYM ? 'active' : ''}}" onclick="loadPerpChart('${{esc(r.symbol)}}', true)">
      <div class="wl-top">
        <div class="wl-q">${{esc(r.symbol)}} <span style="font-size:11px;color:var(--text-3)">${{esc((r.exchange || '').toUpperCase())}}</span></div>
        <span class="badge ${{regCls}}">${{esc(r.regime || 'RANGE')}} · ×${{Number(r.rec_leverage || 10).toFixed(0)}}</span>
      </div>
      <div class="wl-sub">
        <span class="num" style="color:var(--text)">$${{fmtNum(r.price, r.price > 100 ? 2 : 4)}}</span>
        <span class="num">Z ${{fmtSign(r.z_score, 2)}} · ADX ${{fmtNum(r.adx, 0)}}</span>
      </div>
    </div>`;
  }}).join('') : '<div style="padding:18px;text-align:center;color:var(--text-3)">לחץ "מחזור PERPS עכשיו" לטעינת החוזים</div>';

  const trs = ps.recent_trades || [];
  const tbEl = document.getElementById('perps-trades-tbody');
  if (tbEl) tbEl.innerHTML = trs.length ? trs.slice(0, 8).map(t => {{
    const rz = Number(t.realized || 0);
    return `<tr>
      <td class="num" style="color:var(--text-3)">${{fmtDateTime(t.ts)}}</td>
      <td style="color:var(--text)">${{esc(t.symbol)}}</td>
      <td>${{esc(t.side)}} ×${{Number(t.leverage || 1).toFixed(0)}}</td>
      <td class="num ${{rz >= 0 ? 'pos' : 'neg'}}">${{fmtSign(rz, 2)}}</td>
      <td style="color:var(--text-3)">${{esc((t.reason || '').slice(0, 26))}}</td>
    </tr>`;
  }}).join('') : '<tr><td colspan="5" style="text-align:center;color:var(--text-3);padding:16px">אין עסקאות סגורות עדיין</td></tr>';

  const lr = ps.learning_runs || [];
  const lsEl = document.getElementById('perps-learn-summary');
  if (lsEl) {{
    lsEl.textContent = lr.length
      ? `כיול OOS אחרון (${{fmtDateTime(lr[0].ts)}}): בסיס ${{fmtSign(lr[0].baseline_oos, 2)}}% ← מועמד ${{fmtSign(lr[0].candidate_oos, 2)}}% (עקביות ${{(Number(lr[0].consistency || 0)*100).toFixed(0)}}%)`
      : 'כיול Walk-Forward OOS מתבצע אוטומטית כל 30 דקות.';
  }}

  renderPerpThesis();
}}

function renderPerpThesis() {{
  const box = document.getElementById('perps-thesis-box');
  const bdg = document.getElementById('perps-thesis-badge');
  if (!box) return;
  const ch = CURRENT_PERP_CHART || {{}};
  const ps = STATE.perps || {{}};
  const row = (ch.intel && ch.intel.symbol) ? ch.intel : ((ps.intel || []).find(x => x.symbol === SELECTED_PERP_SYM) || null);
  if (!row) {{
    box.innerHTML = '<div style="color:var(--text-3);font-size:12px">בחר חוזה מהרדאר לצפייה בניתוח המשטר, הספר וה-Funding.</div>';
    if (bdg) bdg.textContent = '—';
    return;
  }}
  if (bdg) {{
    const t = row.setup_tier || 'B';
    bdg.innerHTML = `<span class="badge ${{t === 'A+' ? 'badge-ok' : (t === 'A' ? 'badge-info' : 'badge-mute')}}">Setup ${{esc(t)}} · ${{esc(row.regime || 'RANGE')}}</span>`;
  }}
  const fSpread = (row.okx_funding_1h != null && row.hl_funding_1h != null)
    ? ((Number(row.okx_funding_1h) - Number(row.hl_funding_1h)) * 100).toFixed(4) + '%' : '—';
  const items = [
    ['ADX(14) / Efficiency Ratio', `${{fmtNum(row.adx, 1)}} / ${{fmtNum(row.er, 2)}}`],
    ['RSI(14) / Z-Score', `${{fmtNum(row.rsi, 1)}} / ${{fmtSign(row.z_score, 2)}}`],
    ['עומק L2 (Bid / Ask)', `$${{Math.round(row.bid_depth_usd || 0).toLocaleString()}} / $${{Math.round(row.ask_depth_usd || 0).toLocaleString()}}`],
    ['פער Funding (OKX - HL)', fSpread],
  ];
  box.innerHTML = `
    <div class="thesis-summary">${{esc(row.reason || 'במעקב — ממתין לסטאפ איכותי')}} · מינוף מומלץ <strong class="num">×${{Number(row.rec_leverage || 10).toFixed(0)}}</strong></div>
    <div class="kv-list">${{items.map(([k, v]) => `<div class="kv-item"><span class="kv-k">${{esc(k)}}</span><span class="kv-v num">${{esc(v)}}</span></div>`).join('')}}</div>`;
}}

async function runPerpsSimulation() {{
  const outEl = document.getElementById('perps-sim-res');
  if (!LIVE_ORIGIN) {{
    if (outEl) outEl.innerHTML = '<span style="color:var(--amber)">הסימולציה זמינה בחיבור לשרת החי בלבד.</span>';
    return;
  }}
  if (outEl) outEl.textContent = 'מריץ סימולציה על נרות השעה השמורים...';
  const body = {{
    max_leverage: Number(document.getElementById('sim-lev').value || 50),
    sl_atr_mult: Number(document.getElementById('sim-sl').value || 1.5),
    tp_atr_mult: Number(document.getElementById('sim-tp').value || 2.6),
    trailing_trigger_atr: Number(document.getElementById('sim-trl').value || 1.4),
  }};
  try {{
    const res = await fetch('/api/perps/simulate', {{
      method: 'POST', headers: {{'Content-Type': 'application/json'}}, body: JSON.stringify(body)
    }});
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'כשל בסימולציה');
    const r = data.result;
    if (!r) {{ outEl.textContent = data.message || 'אין נתונים'; return; }}
    const cls = Number(r.return_pct) >= 0 ? 'pos' : 'neg';
    outEl.innerHTML = `
      <div style="display:flex;gap:14px;flex-wrap:wrap;align-items:center">
        <span>חוזים: <strong class="num">${{r.assets}}</strong></span>
        <span>תשואה: <strong class="num ${{cls}}">${{fmtSign(r.return_pct, 2)}}%</strong></span>
        <span>עסקאות: <strong class="num">${{r.trades}}</strong> (WR <strong class="num">${{fmtNum(r.win_rate_pct, 0)}}%</strong>)</span>
        <span>PF <strong class="num">${{fmtNum(r.profit_factor, 2)}}</strong></span>
        <span>ליקווידציות: <strong class="num ${{r.liquidations === 0 ? 'pos' : 'neg'}}">${{r.liquidations}}</strong></span>
      </div>`;
  }} catch (e) {{
    if (outEl) outEl.innerHTML = `<span style="color:var(--red)">${{esc(e.message)}}</span>`;
  }}
}}

function renderMarketsIntel() {{
  const rows = STATE.market_intel || [];
  const qSearch = (document.getElementById('wl-search')?.value || '').trim().toLowerCase();
  const filtered = rows.filter(r => {{
    if (INTEL_FILTER === 'OPEN' && r.status !== 'OPEN') return false;
    if (INTEL_FILTER === 'NEAR' && r.status !== 'NEAR' && r.status !== 'CANDIDATE') return false;
    if (INTEL_FILTER === 'APLUS' && r.setup_tier !== 'A+' && r.setup_tier !== 'A') return false;
    if (qSearch && !((r.question || '').toLowerCase().includes(qSearch) || (r.sector || '').toLowerCase().includes(qSearch))) return false;
    return true;
  }});

  document.getElementById('wl-count').textContent = `${{filtered.length}} מתוך ${{rows.length}}`;
  if (!SELECTED_TOKEN && filtered.length) SELECTED_TOKEN = filtered[0].token_id;

  const statusTag = (r) => {{
    if (r.status === 'OPEN') return '<span class="badge badge-info">פתוחה</span>';
    if (r.status === 'BUY') return '<span class="badge badge-ok">כניסה</span>';
    if (r.status === 'CATALYST_BLOCK') return '<span class="badge badge-warn">חסימת חדשות</span>';
    if (r.status === 'CANDIDATE') return '<span class="badge badge-ok">מועמד</span>';
    if (r.setup_tier === 'A+' || r.setup_tier === 'A') return `<span class="badge badge-info">${{esc(r.setup_tier)}}</span>`;
    return '<span class="badge badge-mute">מעקב</span>';
  }};

  document.getElementById('wl-list').innerHTML = filtered.length ? filtered.map(r => `
    <div class="wl-item ${{r.token_id === SELECTED_TOKEN ? 'active' : ''}}" onclick="loadChart('${{esc(r.token_id)}}', true)">
      <div class="wl-top">
        <div class="wl-q">${{esc((r.question || '').slice(0, 56))}}</div>
        ${{statusTag(r)}}
      </div>
      <div class="wl-sub">
        <span class="num" style="color:var(--text)">${{fmtNum(r.price, 3)}}</span>
        <span class="num">Z ${{r.z_score != null ? fmtSign(r.z_score, 2) : '—'}} · ${{Number(r.volume_ratio || 1).toFixed(1)}}x</span>
      </div>
    </div>`).join('') : '<div style="padding:20px;text-align:center;color:var(--text-3)">לא נמצאו שווקים</div>';
}}

function renderDeskPanels() {{
  const ch = CURRENT_CHART || {{}};
  const intel = ch.intel || (STATE.market_intel || []).find(x => x.token_id === (ch.token_id || SELECTED_TOKEN)) || null;
  const pos = ch.position || null;
  document.getElementById('desk-title').textContent = (pos && pos.question) || ch.question || (intel && intel.question) || 'בחר שוק מהרדאר';
  document.getElementById('desk-sub').textContent = intel
    ? `${{intel.sector}} · נפח 24ש׳ $${{Math.round(intel.volume_24h || 0).toLocaleString()}}`
    : 'גרף מחיר וסיגנל בזמן אמת';

  const tier = (intel && intel.setup_tier) || 'B';
  document.getElementById('thesis-badge').innerHTML = intel ? `<span class="badge ${{tier === 'A+' ? 'badge-ok' : 'badge-mute'}}">Setup ${{esc(tier)}}</span>` : '—';

  const mNews = ch.matched_news || [];
  if (intel) {{
    const items = [
      ['Z-Score (24h)', intel.z_score != null ? fmtSign(intel.z_score, 2) : '—'],
      ['RSI (14)', intel.rsi != null ? Number(intel.rsi).toFixed(1) : '—'],
      ['Mid / Spread', `${{fmtNum(intel.price, 3)}} / ${{fmtNum(intel.spread, 3)}}`],
      ['שינוי 24ש׳', intel.chg_24h != null ? fmtSign(intel.chg_24h * 100, 1) + '%' : '—'],
    ];
    document.getElementById('desk-thesis').innerHTML = `
      <div class="thesis-summary">${{esc(intel.reason || intel.status || 'במעקב')}}</div>
      <div class="kv-list" style="grid-template-columns:1fr">${{items.map(([k, v]) => `<div class="kv-item"><span class="kv-k">${{esc(k)}}</span><span class="kv-v num">${{esc(v)}}</span></div>`).join('')}}</div>
      ${{mNews.length ? `<div style="margin-top:10px;font-size:11.5px;color:var(--text-3)">כותרת קשורה: <span style="color:var(--text-2)">${{esc(mNews[0])}}</span></div>` : ''}}`;
  }} else {{
    document.getElementById('desk-thesis').innerHTML = '<div style="color:var(--text-3);font-size:12px">בחר שוק מהרשימה לצפייה בניתוח.</div>';
  }}

  const lv = ch.book_levels || null;
  const bk = (ch.books && ch.books.length) ? ch.books[ch.books.length - 1] : null;
  document.getElementById('ob-meta').textContent = bk ? `Bid ${{fmtNum(bk.best_bid, 3)}} / Ask ${{fmtNum(bk.best_ask, 3)}}` : 'Snapshot';
  if (lv && ((lv.bids && lv.bids.length) || (lv.asks && lv.asks.length))) {{
    const maxSz = Math.max(...[...(lv.bids || []), ...(lv.asks || [])].map(x => Number(x[1] || 0)), 1);
    const bidRows = (lv.bids || []).slice(0, 5).map(([p, s]) => `<div class="ob-row ob-bid"><div class="ob-bar" style="width:${{(s/maxSz*100).toFixed(0)}}%"></div><span class="num pos">${{Number(p).toFixed(3)}}</span><span class="num">${{Number(s).toFixed(0)}}</span></div>`).join('');
    const askRows = (lv.asks || []).slice(0, 5).map(([p, s]) => `<div class="ob-row ob-ask"><div class="ob-bar" style="width:${{(s/maxSz*100).toFixed(0)}}%"></div><span class="num neg">${{Number(p).toFixed(3)}}</span><span class="num">${{Number(s).toFixed(0)}}</span></div>`).join('');
    document.getElementById('desk-ob').innerHTML = `<div class="ob-grid"><div><div style="font-size:11px;color:var(--text-3);margin-bottom:4px">קונים</div>${{bidRows}}</div><div><div style="font-size:11px;color:var(--text-3);margin-bottom:4px">מוכרים</div>${{askRows}}</div></div>`;
  }} else {{
    document.getElementById('desk-ob').innerHTML = '<div style="color:var(--text-3);font-size:12px">לחץ "משוך חי" לטעינת ספר פקודות.</div>';
  }}
}}

function renderNews() {{
  const wp = STATE.world_pulse || {{}};
  const na = (STATE.learning && STATE.learning.news_alpha) || STATE.news_alpha || {{}};
  const sent = Number(wp.avg_sentiment || 0);
  document.getElementById('news-pulse-kpis').innerHTML = [
    {{ l: 'פיד גלובלי', v: `${{wp.sources || 0}} רשתות`, s: `${{wp.total || 0}} כתבות עדכניות`, c: '' }},
    {{ l: 'משטר חדשות עולמי', v: wp.regime || 'מאוזן', s: `סנטימנט ${{fmtSign(sent, 2)}}`, c: sent >= 0.05 ? 'pos' : (sent <= -0.05 ? 'neg' : '') }},
    {{ l: 'דיוק News Alpha', v: na.directional_hit_pct != null ? `${{na.directional_hit_pct}}%` : '—', s: `${{na.total_measured || 0}} כתבות נמדדו מול השוק`, c: '' }},
    {{ l: 'התראות השפעה', v: String(wp.catalysts || 0), s: 'כתבות בעלות משקל גבוה', c: '' }},
  ].map(x => `<div class="metric-tile"><div class="metric-lbl">${{esc(x.l)}}</div><div class="metric-val ${{x.c}}" style="font-size:19px">${{esc(x.v)}}</div><div class="metric-sub">${{esc(x.s)}}</div></div>`).join('');

  const news = STATE.news || [];
  const q = (document.getElementById('news-search')?.value || '').trim().toLowerCase();
  const filtered = news.filter(n => {{
    if (NEWS_FILTER === 'CATALYST' && Number(n.impact || 0) < 0.45) return false;
    else if (NEWS_FILTER === 'MATCHED' && !n.matched_tokens) return false;
    else if (NEWS_FILTER === 'crypto' && n.category !== 'crypto' && n.category !== 'macro' && (n.region || '') !== 'קריפטו') return false;
    if (q && !((n.title || '').toLowerCase().includes(q) || (n.source || '').toLowerCase().includes(q))) return false;
    return true;
  }});

  document.getElementById('news-list').innerHTML = filtered.length ? filtered.slice(0, 60).map(n => {{
    const s = Number(n.sentiment || 0);
    const sBadge = s >= 0.15 ? '<span class="badge badge-ok">חיובי</span>'
                 : s <= -0.15 ? '<span class="badge badge-err">שלילי</span>'
                 : '<span class="badge badge-mute">נייטרלי</span>';
    return `<div class="news-item">
      <div>
        <div class="news-title">${{esc(n.title)}}</div>
        <div class="news-meta">
          <strong style="color:var(--text-2)">${{esc(n.source || n.category || 'RSS')}}</strong>
          <span class="num">${{fmtDateTime(n.ts)}}</span>
          ${{n.matched_tokens ? '<span style="color:var(--accent)">קשור לשוק</span>' : ''}}
        </div>
      </div>
      ${{sBadge}}
    </div>`;
  }}).join('') : '<div style="padding:20px;text-align:center;color:var(--text-3)">אין כתבות תואמות</div>';
}}

function renderLearning() {{
  const lr = STATE.learning || {{}};
  const st = lr.stats || {{}};
  const na = lr.news_alpha || STATE.news_alpha || {{}};
  const psStats = (STATE.perps && STATE.perps.signal_stats) || {{}};
  const insights = lr.insights || [];
  const runs = lr.runs || [];

  document.getElementById('learn-insights').innerHTML = insights.length
    ? '<ul style="margin:0;padding-right:18px;color:var(--text-2);font-size:12.5px">' +
      insights.map(x => `<li style="margin-bottom:6px">${{esc(x)}}</li>`).join('') + '</ul>'
    : '<div style="color:var(--text-3);font-size:12.5px">מיקרו-למידה פועלת אוטומטית כל 5 דקות על מסחר וחדשות.</div>';

  const srcs = na.by_source || [];
  document.getElementById('news-alpha-tbody').innerHTML = srcs.length ? srcs.slice(0, 10).map(s => `<tr>
    <td style="color:var(--text);font-weight:500">${{esc(s.source)}}</td>
    <td class="num">${{s.n}}</td>
    <td class="num">${{s.hit_pct != null ? s.hit_pct + '%' : '—'}}</td>
    <td class="num">${{s.avg_move_pct != null ? '±' + Number(s.avg_move_pct).toFixed(2) + '%' : '—'}}</td>
  </tr>`).join('') : '<tr><td colspan="4" style="text-align:center;color:var(--text-3);padding:16px">אוסף מדידות מחיר של 1ש׳ / 4ש׳ מרגע פרסום כתבות...</td></tr>';

  const zMap = st.by_z_bucket || {{}};
  const regMap = psStats.by_regime || {{}};
  const allRows = [
    ...Object.keys(zMap).map(k => {{
      const row = zMap[k] || {{}};
      return `<tr><td class="num" style="color:var(--text)">Poly Z ${{esc(k)}}</td><td class="num">${{row.n || 0}}</td><td class="num">${{row.hit_latest_pct != null ? row.hit_latest_pct + '%' : '—'}}</td><td class="num ${{(row.mean_latest || 0) >= 0 ? 'pos' : 'neg'}}">${{row.mean_latest != null ? fmtSign(row.mean_latest, 4) : '—'}}</td></tr>`;
    }}),
    ...Object.keys(regMap).map(k => {{
      const row = regMap[k] || {{}};
      return `<tr><td class="num" style="color:var(--accent)">PERPS ${{esc(k)}}</td><td class="num">${{row.n || 0}}</td><td class="num">${{row.hit_pct != null ? row.hit_pct + '%' : '—'}}</td><td class="num ${{(row.mean_pct || 0) >= 0 ? 'pos' : 'neg'}}">${{row.mean_pct != null ? fmtSign(row.mean_pct, 2) + '%' : '—'}}</td></tr>`;
    }}),
  ];
  document.getElementById('learn-z-tbody').innerHTML = allRows.length ? allRows.join('') : '<tr><td colspan="4" style="text-align:center;color:var(--text-3);padding:16px">צובר תוצאות אותות חיים...</td></tr>';

  document.getElementById('learn-runs-tbody').innerHTML = runs.length ? runs.slice(0, 8).map(r => `<tr>
    <td class="num" style="color:var(--text-3)">${{fmtDateTime(r.ts)}}</td>
    <td class="num">${{fmtSign(r.baseline_oos)}}</td>
    <td class="num">${{fmtSign(r.candidate_oos)}}</td>
    <td class="num">${{((Number(r.consistency || 0)) * 100).toFixed(0)}}%</td>
    <td>${{r.applied ? '<span class="badge badge-ok">קודם</span>' : '<span class="badge badge-mute">נשמר</span>'}}</td>
  </tr>`).join('') : '<tr><td colspan="5" style="text-align:center;color:var(--text-3);padding:16px">טרם בוצע כיול OOS</td></tr>';
}}

function renderSystem() {{
  const ap = STATE.autopilot || [];
  document.getElementById('ap-meta').textContent = `${{ap.length}} משימות אחרונות`;
  document.getElementById('ap-tbody').innerHTML = ap.length ? ap.slice(0, 8).map(a => `<tr>
    <td class="num" style="color:var(--text-3)">${{fmtDateTime(a.ts)}}</td>
    <td style="color:var(--text)">${{esc(a.task)}}</td>
    <td><span class="badge ${{a.status === 'ok' ? 'badge-ok' : 'badge-warn'}}">${{esc(a.status)}}</span></td>
    <td>${{esc(a.summary)}}</td>
  </tr>`).join('') : '<tr><td colspan="4" style="text-align:center;color:var(--text-3);padding:18px">פעולות אוטומטיות יתועדו כאן</td></tr>';

  const rd = STATE.readiness || {{}};
  document.getElementById('ready-summary').textContent = (rd.summary || '—').replace(/[\\u{{1F300}}-\\u{{1FAFF}}\\u2600-\\u27BF]/gu, '').trim();
  const checks = rd.checks || [];
  document.getElementById('ready-tbody').innerHTML = checks.length ? checks.map(c => `<tr>
    <td style="color:var(--text)">${{esc(c.label || c.id || c.name || '')}}</td>
    <td><span class="badge ${{c.status === 'ok' ? 'badge-ok' : (c.status === 'warn' ? 'badge-warn' : 'badge-err')}}">${{c.status === 'ok' ? 'תקין' : (c.status === 'warn' ? 'אזהרה' : 'חסר')}}</span></td>
    <td>${{esc(c.detail)}}</td>
  </tr>`).join('') : '<tr><td colspan="3" style="text-align:center;color:var(--text-3);padding:18px">אין בדיקות</td></tr>';

  const an = STATE.analytics || {{}}, ps = an.portfolio_summary || {{}}, wf = an.walkforward || {{}};
  const metrics = [
    ['Polymarket תשואה נטו', ps.return_pct || '—'],
    ['Profit Factor / WR', `${{ps.profit_factor || '—'}} / ${{ps.win_rate || '—'}}`],
    ['Polymarket OOS', wf.total_oos_pnl !== undefined ? fmtSign(wf.total_oos_pnl) + ' USDC' : (wf.oos_pnl !== undefined ? fmtSign(wf.oos_pnl) + ' USDC' : '—')],
    ['התמדת חלונות OOS', wf.consistency !== undefined ? (Number(wf.consistency) * 100).toFixed(0) + '%' : '—'],
  ];
  document.getElementById('analytics-box').innerHTML = `<div class="kv-list" style="grid-template-columns:1fr">${{metrics.map(([k, v]) => `<div class="kv-item"><span class="kv-k">${{esc(k)}}</span><span class="kv-v num">${{esc(v)}}</span></div>`).join('')}}</div>`;

  const cfg = STATE.config || {{}}, sig = cfg.signal || {{}}, rk = cfg.risk || {{}}, pr = (STATE.perps && STATE.perps.guards) || {{}};
  document.getElementById('cfg-mode').textContent = ((cfg.execution && cfg.execution.mode) || 'paper').toUpperCase();
  const cfgItems = [
    ['אסטרטגיה וכניסה (Poly)', `${{sig.engine || 'meanrev'}} · Z>=${{sig.z_entry || 1.8}} · RSI<=${{sig.rsi_max || 40}}`],
    ['יציאה (Poly)', `TP +${{sig.take_profit || 0.06}} / SL -${{sig.stop_loss || 0.07}} / ${{sig.time_stop_hours || 48}}h`],
    ['ניהול סיכון (Poly)', `Kelly ${{((rk.kelly_fraction || 0.65)*100).toFixed(0)}}% · קירור ${{rk.cooldown_minutes || 360}}m`],
    ['הגנות PERPS ×50', `SL ${{pr.sl_atr_mult || 1.5}} / TP ${{pr.tp_atr_mult || 2.6}} ATR · Buffer ×${{pr.liq_buffer_mult || 2.2}}`],
  ];
  document.getElementById('cfg-box').innerHTML = `<div class="kv-list" style="grid-template-columns:1fr">${{cfgItems.map(([k, v]) => `<div class="kv-item"><span class="kv-k">${{esc(k)}}</span><span class="kv-v num">${{esc(v)}}</span></div>`).join('')}}</div>`;
}}

/* --- Apple Stocks Style Canvas Charts --- */
function prepCanvas(canvas) {{
  const rect = canvas.parentElement.getBoundingClientRect();
  const w = Math.max(280, Math.floor(rect.width)), h = Math.max(70, Math.floor(rect.height));
  const dpr = window.devicePixelRatio || 1;
  canvas.width = w * dpr; canvas.height = h * dpr;
  const ctx = canvas.getContext('2d');
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  return {{ ctx, w, h }};
}}

let EQ_HOVER = null;
function drawEquityChart() {{
  const canvas = document.getElementById('eq-canvas');
  if (!canvas) return;
  const {{ ctx, w, h }} = prepCanvas(canvas);
  ctx.clearRect(0, 0, w, h);
  const src = EQ_ARM === 'perps' ? ((STATE.perps && STATE.perps.equity_curve) || []) : (STATE.equity_curve || []);
  const raw = src.filter(p => typeof p.equity === 'number');
  if (raw.length < 2) {{
    ctx.fillStyle = '#8e8e93'; ctx.font = '12px sans-serif'; ctx.textAlign = 'center';
    ctx.fillText('אוסף נקודות הון לעקומה חיה...', w / 2, h / 2);
    return;
  }}
  const pts = raw.map(p => p.equity);
  const minV = Math.min(...pts), maxV = Math.max(...pts), pad = Math.max((maxV - minV) * 0.14, 1);
  const lo = minV - pad, hi = maxV + pad;
  const pxL = 12, pxR = 54, pyT = 12, pyB = 20, gw = w - pxL - pxR, gh = h - pyT - pyB;
  const up = pts[pts.length - 1] >= pts[0], stroke = up ? '#30d158' : '#ff453a';
  document.getElementById('eq-meta').textContent = `${{pts[0].toFixed(2)}} -> ${{pts[pts.length - 1].toFixed(2)}} (${{fmtSign(pts[pts.length - 1] - pts[0])}})`;

  ctx.strokeStyle = 'rgba(255,255,255,0.05)'; ctx.lineWidth = 1;
  ctx.fillStyle = '#8e8e93'; ctx.font = '11px SF Mono, ui-monospace, monospace'; ctx.textAlign = 'left';
  for (let i = 0; i <= 3; i++) {{
    const y = pyT + gh * (i / 3), val = hi - (hi - lo) * (i / 3);
    ctx.beginPath(); ctx.moveTo(pxL, y); ctx.lineTo(w - pxR, y); ctx.stroke();
    ctx.fillText(val.toFixed(1), w - pxR + 6, y + 4);
  }}
  const X = i => pxL + (i / (pts.length - 1)) * gw, Y = v => pyT + gh - ((v - lo) / (hi - lo)) * gh;
  const grad = ctx.createLinearGradient(0, pyT, 0, pyT + gh);
  grad.addColorStop(0, up ? 'rgba(48,209,88,0.24)' : 'rgba(255,69,58,0.24)');
  grad.addColorStop(1, 'rgba(48,209,88,0.0)');
  ctx.beginPath();
  pts.forEach((v, i) => i === 0 ? ctx.moveTo(X(i), Y(v)) : ctx.lineTo(X(i), Y(v)));
  ctx.strokeStyle = stroke; ctx.lineWidth = 2.2; ctx.stroke();
  ctx.lineTo(X(pts.length - 1), pyT + gh); ctx.lineTo(X(0), pyT + gh); ctx.closePath();
  ctx.fillStyle = grad; ctx.fill();

  const tip = document.getElementById('eq-tip');
  if (EQ_HOVER !== null && EQ_HOVER >= 0 && EQ_HOVER < raw.length) {{
    const hx = X(EQ_HOVER), hy = Y(pts[EQ_HOVER]);
    ctx.save(); ctx.setLineDash([3, 3]); ctx.strokeStyle = 'rgba(255,255,255,0.25)';
    ctx.beginPath(); ctx.moveTo(hx, pyT); ctx.lineTo(hx, pyT + gh); ctx.stroke(); ctx.restore();
    ctx.beginPath(); ctx.arc(hx, hy, 4, 0, Math.PI * 2); ctx.fillStyle = stroke; ctx.fill();
    tip.style.display = 'block';
    tip.innerHTML = `<span class="num">${{pts[EQ_HOVER].toFixed(2)}} USDC</span> · ${{fmtDateTime(raw[EQ_HOVER].ts)}}`;
  }} else if (tip) tip.style.display = 'none';
}}

let PERP_HOVER = null;
function drawPerpPriceChart() {{
  const canvas = document.getElementById('perps-price-canvas');
  if (!canvas) return;
  const {{ ctx, w, h }} = prepCanvas(canvas);
  ctx.clearRect(0, 0, w, h);
  const ch = CURRENT_PERP_CHART || {{}}, cs = (ch.candles || []).slice(-100);
  const tEl = document.getElementById('perps-chart-title'), sEl = document.getElementById('perps-chart-sub');
  if (tEl) tEl.textContent = `${{ch.symbol || SELECTED_PERP_SYM}} Perpetual (${{ch.timeframe || '1h'}})`;
  if (sEl && ch.intel && ch.intel.symbol) sEl.textContent = `${{(ch.intel.exchange || '').toUpperCase()}} · ${{ch.intel.regime || ''}} · מינוף ×${{Number(ch.intel.rec_leverage || 10).toFixed(0)}}`;
  if (cs.length < 2) {{
    ctx.fillStyle = '#8e8e93'; ctx.font = '12px sans-serif'; ctx.textAlign = 'center';
    ctx.fillText('אין עדיין נרות לחוזה זה — לחץ "משוך חי"', w / 2, h / 2);
    return;
  }}
  const ov = ch.overlays || {{}}, all = [];
  cs.forEach(c => {{ all.push(Number(c.high || c.close)); all.push(Number(c.low || c.close)); }});
  if (ov.stop) all.push(Number(ov.stop));
  if (ov.target) all.push(Number(ov.target));
  if (ov.liq) all.push(Number(ov.liq));
  const minV = Math.min(...all), maxV = Math.max(...all), pad = Math.max((maxV - minV) * 0.12, maxV * 0.002);
  const lo = minV - pad, hi = maxV + pad, pxL = 14, pxR = 66, pyT = 14, pyB = 20, gw = w - pxL - pxR, gh = h - pyT - pyB;
  const X = i => pxL + ((i + 0.5) / cs.length) * gw, Y = v => pyT + gh - ((v - lo) / (hi - lo)) * gh;

  ctx.strokeStyle = 'rgba(255,255,255,0.05)'; ctx.fillStyle = '#8e8e93'; ctx.font = '10px SF Mono, monospace'; ctx.textAlign = 'left';
  for (let i = 0; i <= 4; i++) {{
    const y = pyT + gh * (i / 4), v = hi - (hi - lo) * (i / 4);
    ctx.beginPath(); ctx.moveTo(pxL, y); ctx.lineTo(w - pxR, y); ctx.stroke();
    ctx.fillText(v > 100 ? v.toFixed(1) : v.toFixed(4), w - pxR + 6, y + 3);
  }}
  const hLn = (v, col, lbl) => {{
    if (!v) return;
    const y = Y(Number(v)); if (y < pyT || y > pyT + gh) return;
    ctx.save(); ctx.setLineDash([4, 4]); ctx.strokeStyle = col;
    ctx.beginPath(); ctx.moveTo(pxL, y); ctx.lineTo(w - pxR, y); ctx.stroke();
    ctx.fillStyle = col; ctx.fillText(lbl, pxL + 6, y - 4); ctx.restore();
  }};
  if (ov.entry) {{
    hLn(ov.target, '#30d158', 'TP ' + Number(ov.target).toFixed(4));
    hLn(ov.entry, '#aeaeb2', 'ENTRY ×' + Number(ov.leverage || 1).toFixed(0));
    hLn(ov.stop, '#ff9f0a', 'SL ' + Number(ov.stop).toFixed(4));
    hLn(ov.liq, '#ff453a', 'LIQ ' + Number(ov.liq).toFixed(4));
  }}
  const cw = Math.max(2, Math.min(9, (gw / cs.length) * 0.64));
  cs.forEach((c, i) => {{
    const x = X(i), o = Number(c.open || c.close), hiC = Number(c.high || c.close), loC = Number(c.low || c.close), cl = Number(c.close);
    const col = cl >= o ? '#30d158' : '#ff453a';
    ctx.strokeStyle = col; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(x, Y(hiC)); ctx.lineTo(x, Y(loC)); ctx.stroke();
    const yTop = Y(Math.max(o, cl)), yBot = Y(Math.min(o, cl));
    ctx.fillStyle = col; ctx.fillRect(x - cw / 2, yTop, cw, Math.max(1.5, yBot - yTop));
  }});
  const tip = document.getElementById('perps-price-tip');
  if (PERP_HOVER !== null && PERP_HOVER >= 0 && PERP_HOVER < cs.length) {{
    const c = cs[PERP_HOVER], hx = X(PERP_HOVER), hy = Y(Number(c.close)), d = c.close > 100 ? 2 : 4;
    ctx.save(); ctx.setLineDash([3, 3]); ctx.strokeStyle = 'rgba(255,255,255,0.28)';
    ctx.beginPath(); ctx.moveTo(hx, pyT); ctx.lineTo(hx, pyT + gh); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(pxL, hy); ctx.lineTo(w - pxR, hy); ctx.stroke(); ctx.restore();
    if (tip) {{ tip.style.display = 'block'; tip.innerHTML = `<span class="num">${{fmtDateTime(c.ts)}}</span> | O <span class="num">${{Number(c.open).toFixed(d)}}</span> H <span class="num">${{Number(c.high).toFixed(d)}}</span> L <span class="num">${{Number(c.low).toFixed(d)}}</span> C <strong class="num">${{Number(c.close).toFixed(d)}}</strong>`; }}
  }} else if (tip) tip.style.display = 'none';
}}

let PRICE_HOVER = null;
function _slicedChart() {{
  const ch = CURRENT_CHART || {{}}, ticks = ch.ticks || [];
  if (!ticks.length) return {{ ticks: [], sma: [], lb: [], rsi: [] }};
  const n = Math.min(ticks.length, CHART_RANGE), start = ticks.length - n;
  return {{ ticks: ticks.slice(start), sma: (ch.sma || []).slice(start), lb: (ch.lower_band || []).slice(start), rsi: (ch.rsi || []).slice(start) }};
}}

function drawPriceChart() {{
  const canvas = document.getElementById('price-canvas');
  if (!canvas) return;
  const {{ ctx, w, h }} = prepCanvas(canvas);
  ctx.clearRect(0, 0, w, h);
  const ch = CURRENT_CHART || {{}}, {{ ticks, sma, lb, rsi }} = _slicedChart();
  if (ticks.length < 2) {{
    ctx.fillStyle = '#8e8e93'; ctx.font = '12px sans-serif'; ctx.textAlign = 'center';
    ctx.fillText('אין מספיק נתונים — לחץ "משוך חי"', w / 2, h / 2);
    return;
  }}
  const prices = ticks.map(t => Number(t.price)), pos = ch.position || null, allVals = [...prices];
  sma.forEach(v => {{ if (v != null) allVals.push(Number(v)); }});
  lb.forEach(v => {{ if (v != null) allVals.push(Number(v)); }});
  if (pos && pos.stop_price) allVals.push(Number(pos.stop_price));
  if (pos && pos.target_price) allVals.push(Number(pos.target_price));
  const minV = Math.min(...allVals), maxV = Math.max(...allVals), pad = Math.max((maxV - minV) * 0.14, 0.012);
  const lo = Math.max(0, minV - pad), hi = Math.min(1, maxV + pad), pxL = 14, pxR = 54, pyT = 14, pyB = 22, gw = w - pxL - pxR, gh = h - pyT - pyB;
  const X = i => pxL + (i / (prices.length - 1)) * gw, Y = v => pyT + gh - ((v - lo) / (hi - lo)) * gh;

  ctx.strokeStyle = 'rgba(255,255,255,0.05)'; ctx.fillStyle = '#8e8e93'; ctx.font = '11px SF Mono, monospace'; ctx.textAlign = 'left';
  for (let i = 0; i <= 4; i++) {{
    const y = pyT + gh * (i / 4), val = hi - (hi - lo) * (i / 4);
    ctx.beginPath(); ctx.moveTo(pxL, y); ctx.lineTo(w - pxR, y); ctx.stroke();
    ctx.fillText(val.toFixed(3), w - pxR + 6, y + 4);
  }}
  const hLine = (val, col, lbl) => {{
    if (val == null) return;
    const y = Y(Number(val)); if (y < pyT || y > pyT + gh) return;
    ctx.save(); ctx.setLineDash([4, 4]); ctx.strokeStyle = col;
    ctx.beginPath(); ctx.moveTo(pxL, y); ctx.lineTo(w - pxR, y); ctx.stroke();
    ctx.fillStyle = col; ctx.fillText(lbl, pxL + 6, y - 4); ctx.restore();
  }};
  if (pos) {{
    hLine(pos.target_price, '#30d158', 'TP ' + Number(pos.target_price || 0).toFixed(3));
    hLine(pos.avg_price, '#aeaeb2', 'ENTRY ' + Number(pos.avg_price || 0).toFixed(3));
    hLine(pos.stop_price, '#ff453a', 'SL ' + Number(pos.stop_price || 0).toFixed(3));
  }}
  ctx.beginPath(); let st = false;
  lb.forEach((v, i) => {{ if (v == null) return; if (!st) {{ ctx.moveTo(X(i), Y(Number(v))); st = true; }} else ctx.lineTo(X(i), Y(Number(v))); }});
  ctx.strokeStyle = 'rgba(255,159,10,0.5)'; ctx.lineWidth = 1.2; ctx.stroke();
  ctx.beginPath(); st = false;
  sma.forEach((v, i) => {{ if (v == null) return; if (!st) {{ ctx.moveTo(X(i), Y(Number(v))); st = true; }} else ctx.lineTo(X(i), Y(Number(v))); }});
  ctx.strokeStyle = 'rgba(174,174,178,0.6)'; ctx.lineWidth = 1.2; ctx.stroke();
  ctx.beginPath(); prices.forEach((v, i) => i === 0 ? ctx.moveTo(X(i), Y(v)) : ctx.lineTo(X(i), Y(v)));
  ctx.strokeStyle = '#0a84ff'; ctx.lineWidth = 2.2; ctx.stroke();

  const tip = document.getElementById('price-tip');
  if (PRICE_HOVER !== null && PRICE_HOVER >= 0 && PRICE_HOVER < prices.length) {{
    const hx = X(PRICE_HOVER), hy = Y(prices[PRICE_HOVER]);
    ctx.save(); ctx.setLineDash([3, 3]); ctx.strokeStyle = 'rgba(255,255,255,0.28)';
    ctx.beginPath(); ctx.moveTo(hx, pyT); ctx.lineTo(hx, pyT + gh); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(pxL, hy); ctx.lineTo(w - pxR, hy); ctx.stroke(); ctx.restore();
    ctx.beginPath(); ctx.arc(hx, hy, 4, 0, Math.PI * 2); ctx.fillStyle = '#0a84ff'; ctx.fill();
    tip.style.display = 'block';
    tip.innerHTML = `<span class="num">${{fmtDateTime(ticks[PRICE_HOVER].ts)}}</span> | מחיר <strong class="num">${{prices[PRICE_HOVER].toFixed(3)}}</strong>`;
  }} else if (tip) tip.style.display = 'none';
}}

function drawRsiChart() {{
  const canvas = document.getElementById('rsi-canvas');
  if (!canvas) return;
  const {{ ctx, w, h }} = prepCanvas(canvas);
  ctx.clearRect(0, 0, w, h);
  const {{ rsi }} = _slicedChart();
  if (rsi.filter(v => v != null).length < 2) return;
  const pxL = 14, pxR = 54, pyT = 8, pyB = 8, gw = w - pxL - pxR, gh = h - pyT - pyB;
  const X = i => pxL + (i / Math.max(rsi.length - 1, 1)) * gw, Y = v => pyT + gh - (Math.max(0, Math.min(100, v)) / 100) * gh;
  ctx.fillStyle = 'rgba(48,209,88,0.08)'; ctx.fillRect(pxL, Y(45), gw, Y(0) - Y(45));
  ctx.font = '10px SF Mono, monospace'; ctx.fillStyle = '#8e8e93'; ctx.textAlign = 'left';
  for (const lvl of [30, 45, 70]) {{
    const y = Y(lvl);
    ctx.strokeStyle = lvl === 45 ? 'rgba(48,209,88,0.35)' : 'rgba(255,255,255,0.06)';
    ctx.beginPath(); ctx.moveTo(pxL, y); ctx.lineTo(w - pxR, y); ctx.stroke();
    ctx.fillText(String(lvl), w - pxR + 6, y + 3);
  }}
  ctx.beginPath(); let st = false;
  rsi.forEach((v, i) => {{ if (v == null) return; if (!st) {{ ctx.moveTo(X(i), Y(Number(v))); st = true; }} else ctx.lineTo(X(i), Y(Number(v))); }});
  ctx.strokeStyle = '#bf5af2'; ctx.lineWidth = 1.6; ctx.stroke();
  ctx.fillStyle = '#aeaeb2'; ctx.fillText('RSI(14)', pxL + 4, pyT + 9);
}}

(function bindCrosshairs() {{
  const eqC = document.getElementById('eq-canvas');
  if (eqC) {{
    eqC.addEventListener('mousemove', (ev) => {{
      const src = EQ_ARM === 'perps' ? ((STATE.perps && STATE.perps.equity_curve) || []) : (STATE.equity_curve || []);
      const pts = src.filter(p => typeof p.equity === 'number');
      if (pts.length < 2) return;
      const rect = eqC.getBoundingClientRect();
      EQ_HOVER = Math.max(0, Math.min(pts.length - 1, Math.round(((ev.clientX - rect.left - 12) / Math.max(rect.width - 66, 1)) * (pts.length - 1))));
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
      PRICE_HOVER = Math.max(0, Math.min(ticks.length - 1, Math.round(((ev.clientX - rect.left - 14) / Math.max(rect.width - 68, 1)) * (ticks.length - 1))));
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
      PERP_HOVER = Math.max(0, Math.min(cs.length - 1, Math.round(((ev.clientX - rect.left - 14) / Math.max(rect.width - 80, 1)) * (cs.length - 1))));
      drawPerpPriceChart();
    }});
    ppC.addEventListener('mouseleave', () => {{ PERP_HOVER = null; drawPerpPriceChart(); }});
  }}
}})();

window.addEventListener('resize', () => {{
  if (ACTIVE_TAB === 'overview') drawEquityChart();
  if (ACTIVE_TAB === 'perps') drawPerpPriceChart();
  if (ACTIVE_TAB === 'markets') {{ drawPriceChart(); drawRsiChart(); }}
}});

/* --- macOS Spotlight Search (⌘K / Ctrl+K) --- */
function openSpotlight() {{
  const ov = document.getElementById('spot-overlay'), inp = document.getElementById('spot-input');
  if (!ov || !inp) return;
  ov.classList.add('open'); inp.value = ''; renderSpotlight(); setTimeout(() => inp.focus(), 30);
}}
function closeSpotlight() {{
  const ov = document.getElementById('spot-overlay');
  if (ov) ov.classList.remove('open');
}}
function renderSpotlight() {{
  const list = document.getElementById('spot-list'), q = (document.getElementById('spot-input')?.value || '').trim().toLowerCase();
  if (!list) return;
  const items = [];
  (STATE.perps?.intel || []).forEach(p => {{
    if (!q || p.symbol.toLowerCase().includes(q) || (p.regime || '').toLowerCase().includes(q)) {{
      items.push({{ tag: 'PERPS', title: `${{p.symbol}} ($${{fmtNum(p.price, p.price > 100 ? 2 : 4)}})`, sub: `${{p.regime}} · ×${{Number(p.rec_leverage||10).toFixed(0)}}`, act: () => {{ closeSpotlight(); switchTab('perps'); loadPerpChart(p.symbol, true); }} }});
    }}
  }});
  (STATE.market_intel || []).forEach(m => {{
    if (!q || (m.question || '').toLowerCase().includes(q) || (m.sector || '').toLowerCase().includes(q)) {{
      items.push({{ tag: 'שוק', title: (m.question || '').slice(0, 56), sub: `${{m.sector}} · Z ${{fmtSign(m.z_score, 1)}}`, act: () => {{ closeSpotlight(); switchToMarket(m.token_id); }} }});
    }}
  }});
  const cmds = [
    {{ tag: 'פקודה', title: 'הרץ מחזור PERPS עכשיו', sub: 'סריקה וכניסה/יציאה ב-16 חוזים', act: () => {{ closeSpotlight(); postAction('/api/perps/cycle', {{}}); }} }},
    {{ tag: 'פקודה', title: 'רענן חדשות + למידת News Alpha', sub: '22+ רשתות חדשות', act: () => {{ closeSpotlight(); postAction('/api/news-refresh', {{}}); }} }},
    {{ tag: 'פקודה', title: 'הרץ למידה עצמית (OOS Walk-Forward)', sub: 'כיול דו-זרועי מבוקר', act: () => {{ closeSpotlight(); postAction('/api/learn', {{apply:true}}); }} }},
    {{ tag: 'פקודה', title: 'גיבוי DB מיידי', sub: 'שמירה מאומתת ל-backups/', act: () => {{ closeSpotlight(); postAction('/api/backup', {{}}); }} }},
  ];
  cmds.forEach(c => {{ if (!q || c.title.toLowerCase().includes(q) || c.sub.toLowerCase().includes(q)) items.push(c); }});
  window.__SPOT_ACTS = items.slice(0, 12).map(x => x.act);
  list.innerHTML = items.slice(0, 12).map((x, i) => `
    <div class="spot-item" onclick="window.__SPOT_ACTS[${{i}}]()">
      <div>
        <div style="color:#fff;font-weight:500">${{esc(x.title)}}</div>
        <div style="font-size:11px;color:var(--text-3)">${{esc(x.sub)}}</div>
      </div>
      <span class="badge badge-info">${{esc(x.tag)}}</span>
    </div>`).join('') || '<div style="padding:18px;text-align:center;color:var(--text-3)">לא נמצאו תוצאות</div>';
}}
document.addEventListener('keydown', (e) => {{
  if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {{
    e.preventDefault();
    const ov = document.getElementById('spot-overlay');
    if (ov && ov.classList.contains('open')) closeSpotlight(); else openSpotlight();
  }} else if (e.key === 'Escape') closeSpotlight();
}});

renderAll();
if (LIVE_ORIGIN && {refresh_ms} > 0) setInterval(refreshAll, {refresh_ms});
</script>
</body>
</html>
"""
