# HANDOFF — תדריך מלא והעברת הקשר לצ'אט חדש

_מסמך הכניסה והאמת היחיד של הפרויקט (`polymarket-momentum-bot` / PMMB Command Center). אם אתה סוכן AI או מפתח בצ'אט חדש — קרא מסמך זה לפני נגיעה בקוד. עודכן לאחרונה: 2026-11-23 (commit `94168b4` -> העברה לצ'אט חדש)._

---

## 1. תמונת מצב כללית — מה המערכת הזו?

מערכת מסחר דו־זרועית אוטונומית מלאה עם דשבורד בזמן אמת (`Command Center`):
1. **זרוע 1 — Polymarket CLOB (שווקי חיזוי)**:
   - מנוע Mean-Reversion (`src/pmmb/engine.py`) על נרות שעה עם סריקת שווקים מקבילית (`ThreadPoolExecutor`), שערים מבוססי עלויות אמיתיות (ספרד + עמלת טייקר מדויקת), גידור סקטוריאלי וזמינות, ו־Kill Switch (`pmmb halt` / `resume`).
2. **זרוע 2 — חוזים תמידיים `PERPS ×50` (OKX + Hyperliquid + fallback ל־Binance/Gate)**:
   - מנוע רב־נכסי (`src/pmmb/perps/engine.py`, 16 נכסים מובילים) המשלב שני משטרי אותות (`pullback` ו־`breakout` לפי ADX), פילטר Funding/OI/News Alpha, ו**הקצאת סיכון מדורגת (`Tiered Risk Allocation`)** (`A+ 1.30×`, `A 1.10×`, `B 0.85×`) עם שמירת מרחק בטוח ממחיר חיסול (`liquidation_buffer_mult=2.2`, תקרת מינוף `50×`).
3. **ליבה אוטונומית ומתפתחת עצמאית (`Autopilot + Auto-Evolution + Self-Healing`)**:
   - סריקת זרמי מחירים, הזנת חדשות מוסדיות (22+ פידים + News Alpha), למידה רציפה מבוקרת **Walk-Forward Out-Of-Sample** לשתי הזרועות כל 20 דקות (`perps/learning.py` + `learning.py`), תחזוקת DB אוטונומית כל 30 דקות (`PRAGMA optimize`, `wal_checkpoint`, `reconcile`, דוחות, גיבויים, `reports/autonomous_status.json`), והתאוששות עצמית של התהליך (`scripts/run_autonomous.sh` + `scripts/watchdog.sh`).

---

## 2. מדדים ותוצאות מאומתות נכון ל־2026-11-23 (Live Server + Backtests)

- **מצב Live Paper נוכחי (`http://127.0.0.1:8787`, PID רץ תחת `scripts/run_autonomous.sh`)**:
  - **הון משולב**: `$1,963.87` (`Polymarket $951.06` · `PERPS $1,012.81` · התחלה `$2,000.00`).
  - **בדיקות אוטומטיות**: **`229 passed`** (`pytest -q`, אפס קריאות רשת) + בדיקת JS runtime מלאה (`node --check` + DOM VM על `404KB` HTML).
  - **DB ומצב סינכרון**: `pmmb.db` בגודל `~9.4 MB`, `pmmb reconcile` = `0` פערים, גיבויים חמים קיימים ב־`backups/`, מוכנות ל־Live = `7/11` (נכשל רק קריטריון `soak`: כרגע 3 מתוך 7 ימי הרצה נקיים, וחסר `PMMB_PRIVATE_KEY` עבור Live אמיתי).
- **ביצועי Walk-Forward מאומתים — PERPS ×50 (`16` נכסים, `1h`, 720 נרות, Tiered Risk)**:
  - **30 יום מלא (`Full`)**: **`+155.19%`**, Win Rate **`66.4%`**, Profit Factor **`1.61`**, Max Drawdown **`22.8%`**, **`0` ליקווידציות**.
  - **Walk-Forward Out-Of-Sample (`3-Fold OOS`)**: **`+113.80%`**, עקביות **`100%`**, `104` עסקאות, **`0` ליקווידציות**.
  - פרמטרים מכוילים פעילים ב־`config/config.yaml`: `tp_atr_mult: 3.4`, `sl_atr_mult: 1.5`, `trailing_trigger_atr: 1.4`, `trailing_dist_atr: 0.95`, `risk_per_trade_pct: 0.03`, `max_total_margin_pct: 0.59`, `z_entry: 1.8`, `adx_trend_threshold: 25.0`, `max_open_positions: 7`, `max_positions_per_direction: 4`, `cooldown_bars: 6`, `learn_interval_sec: 1200.0`.
- **ביצועי Walk-Forward — Polymarket**:
  - OOS היסטורי שמור ב־`reports/walkforward.json`: **`+74.68 USDC`** על 37 עסקאות, עקביות `67%`, עמלות במודל `13.02 USDC` על 56 עסקאות.
  - פרמטרים ב־`config/config.yaml`: `take_profit: 0.06`, `stop_loss: 0.07`, `z_entry: 1.8`, `interval_sec: 1200`.

---

## 3. מה נוסה ונפסל — **אסור להחזיר את אלה**

| השערה / ניסוי שנפסל | תוצאה שנמדדה | איפה נשמר / הסיבה |
|---|---|---|
| **מומנטום קלאסי ב-Polymarket** | מת (מתאם שלילי) | `docs/DECISIONS.md` |
| **SHORT / קניית NO ב-Polymarket** | מוריד תשואה | `allow_short: false` |
| **ארביטראז' YES+NO<1 או negRisk** | לא קיים בשווקים אמיתיים (`>1.001`) | נמדד על 71 שווקים |
| **הטיית Favorite/Longshot** | EV `+0.0022` — לא עובר עמלה/ספרד | `scripts/research_bias.py` |
| **החרגת סקטור `politics`** | הפילה OOS מ־`+38.45` ל־`+5.24` | תיעוד שלב 6 |
| **כניסת Maker פסיבית ב-Polymarket** | מאבדת מילוי ומורידה רווח (`362→149`) | `reports/execution.md` |
| **החרגת Crypto אומץ** | הוחרג ב-Polymarket (`exclude_sectors`) | `config/config.yaml` |
| **Break-Even Lock דינמי ב-PERPS** (`1.00–1.25 ATR`) | פוגע ברווחי מגמה (הפיל מ־`+141%`/`+96% OOS` ל־`+82–117%`/`+55–74% OOS`, עקביות ירדה ל־`67%`) | נבדק ישירות על 16 נכסים |
| **צמצום PERPS ל־`max_open=5` / `cooldown=4` / `tight_trail(1.1/0.85)`** | הוריד OOS ל־`+38.8%..+62.4%` | נמדד ונפסל |

---

## 4. פירוט השדרוגים האחרונים (לפי סדר הקומיטים)

- **`417738f`**: עיצוב Obsidian Glass Pro UI + אסטרטגיית `breakout` ב־PERPS + כיול Walk-Forward.
- **`01fdfdf`**:
  - Tiered Risk Allocation ב־PERPS (`1.30 / 1.10 / 0.85`).
  - סריקת CLOB מקבילית עם `ThreadPoolExecutor` ב־`src/pmmb/engine.py`.
  - גרף `combined_equity_curve`, API למסחר ידני (`POST /api/trade/order`), עריכת SL/TP (`POST /api/positions/sltp`), סגירת פוזיציה/הכל (`POST /api/positions/close`, `/close-all`), ספר פקודות חי L2 (`GET /api/perps/book`), עדכון קונפיג חי (`POST /api/config/update`), ו־`_TraderManager(config_path=...)`.
- **`94168b4`** (הגרסה העדכנית הפעילה כעת):
  - **תשתית אוטונומית**:
    - `run_autonomous_housekeeping` ב־`src/pmmb/autopilot.py` (`PRAGMA optimize`, WAL checkpoint, reconcile, reports, `reports/autonomous_status.json`).
    - `_TraderManager` ב־`src/pmmb/server.py` עם מעקב חיות (`uptime_sec`, `housekeeping_cycles`, `perps_learn_cycles`, `auto_recoveries`), התאוששות אוטומטית משגיאות לולאה, תחזוקה תקופתית כל 1800 שניות, ו־`evolve_and_maintain_now()`.
    - נקודות קצה חדשות: **`GET /api/analytics/performance`** ו־**`POST /api/autonomous/evolve`**.
    - סקריפטי הפעלה אוטונומיים: `scripts/run_autonomous.sh` (לולאת auto-heal + preflight `reconcile`/`backup`) ו־`scripts/watchdog.sh` מעודכן.
  - **כיול והרחבת למידה**:
    - `src/pmmb/perps/learning.py`: רשת של 7 מועמדי Walk-Forward וכתיבה אוטומטית של `reports/perp_walkforward.json` בכל מחזור למידה.
    - `config/config.yaml`: כיול מנצח `tp_atr_mult=3.4`, `risk_per_trade_pct=0.03`, `max_total_margin_pct=0.59`, `learning.interval_sec=1200`.
  - **פיצ'רים חדשים ב־UI (`src/pmmb/ui.py` ו־`src/pmmb/status.py`)**:
    - `build_performance_analytics`: חישוב Profit Factor חי, Win Rate, Avg Win/Loss, רווח יומי לפי זרוע, ופירוט לפי אסטרטגיה ונכס.
    - מצב גרף 3 בדף הבית: **`רווח יומי (עמודות)`** (`drawDailyBars` + Tooltip אינטראקטיבי).
    - פאנל **`Performance Attribution`** בטאב המחקר.
    - סרגל שליטה **`מנוע אוטונומיה והתפתחות עצמית רציפה`** בטאב ההגדרות (כולל כפתור `הרץ אבולוציה ותחזוקה מלאה עכשיו`).

---

## 5. מפת קבצים מרכזיים ונקודות API

- **ליבת התוכנה**:
  - `config/config.yaml` — הגדרות מערכת ופרמטרים מכוילים (נערך גם בלייב ע"י הממשק/הלמידה).
  - `src/pmmb/engine.py` — זרוע Polymarket (Prefetch מקבילי, סיגנלים, ניהול פוזיציות).
  - `src/pmmb/perps/{engine.py,signals.py,risk.py,exchange.py,backtest.py,learning.py}` — זרוע ה־`PERPS ×50`.
  - `src/pmmb/autopilot.py` — מחזורי סריקה, למידה ותחזוקת DB אוטונומית (`run_autonomous_housekeeping`).
  - `src/pmmb/status.py` — איסוף מצב חי, `build_performance_analytics`, `build_command_center_data`.
  - `src/pmmb/server.py` — שרת HTTP + `_TraderManager` + כל נקודות ה־API.
  - `src/pmmb/ui.py` — דשבורד HTML/Canvas/JS מקומי לחלוטין (אפס קישורי `http://`/`https://` בקוד הדשבורד).
  - `src/pmmb/readiness.py` — שער המעבר ל־Live (7 ימי paper, Walk-Forward, עמלות, סיכון).
- **סקריפטים תפעוליים**:
  - `scripts/run_autonomous.sh` — הפעלת השרת האוטונומי עם התאוששות וגיבוי.
  - `scripts/watchdog.sh` — בדיקת חיות והרמה מחדש ברקע.
  - `scripts/setup_remote.sh` & `scripts/push_to_github.sh` — חיבור ודחיפה ל־GitHub בצורה מאובטחת (ללא שמירת טוקנים בדיסק).
- **נקודות API מרכזיות בשרת (`:8787`)**:
  - `GET /`, `GET /healthz`, `GET /api/state`, `GET /api/analytics/performance`, `GET /api/perps/book?symbol=...`, `GET /api/export/trades.csv`
  - `POST /api/trade/order`, `POST /api/positions/sltp`, `POST /api/positions/close`, `POST /api/positions/close-all`
  - `POST /api/config/update`, `POST /api/autonomous/evolve`, `POST /api/trader/toggle`, `POST /api/learn/run`, `POST /api/backup`, `POST /api/halt`, `POST /api/resume`

---

## 6. חוקי ברזל טכניים ואינווריאנטים בבדיקות (חשוב מאוד!)

1. **תאימות בדיקות `tests/test_perps.py` ו־`tests/test_status.py`**:
   - ב־`ui.py`: חובה לשמור על מחרוזות נדרשות (כמו `"PMMB Command Center"`, `"Walk-Forward"`, `"התיק והמסחר שלי"`, `"שווקים, PERPS וחדשות"`, `"מוכנות, סיכונים והגדרות"`, `"הפוזיציות הפתוחות שלי"`, `"יומן טייס אוטומטי"`, `"PERPS ×50"`, `"sub-perps"`, `"combined-hero"`, `"spot-overlay"`, `"perps-thesis-box"`, `"perps-sim-res"`), **אסור** שתופענה כתובות `http://` או `https://` בתוך ה־HTML המיוצר, ו**אסור** להשתמש באימוג'ים `("📡", "📊", "🛑", "📰", "🧠", "⚙️")`.
   - ב־`PerpsRiskConfig` (ברירת מחדל של dataclass, לא YAML): להשאיר `tp_atr_mult=2.6`, `sl_atr_mult=1.5`, `max_leverage=50.0`, `liquidation_buffer_mult=2.2`.
   - ב־`readiness.Thresholds`: להשאיר `max_daily_loss_pct=0.10`, `max_drawdown_pct=0.30`, `max_exposure_pct=0.60`, `max_risk_per_trade_pct=0.05`.
2. **תמיד להריץ before commit/push**:
   - `/usr/local/bin/pytest -q` (חייב להיות ירוק ללא רשת).
   - `node --check` + בדיקת DOM VM על ה־JS של `src/pmmb/ui.py` (שים לב: stub את `setInterval` אחרת `node` ימתין לנצח).
3. **זהירות עם תהליכים והרצות**:
   - אל תריץ `pkill -f "pmmb serve"` מתוך `bash` — זה הורג את מעטפת ה־shell של הפקודה עצמה; סנן PIDs בפייתון עם `os.getpid()`.
   - קומיט ב־Git בסביבה זו דורש `-c user.name=... -c user.email=...` אם לא הוגדר גלובלית.

---

## 7. מה פתוח לשלבים הבאים (Roadmap מומלץ לצ'אט החדש)

1. **סנכרון עם GitHub**:
   - ל־Arena אין מחבר מובנה ל־GitHub (`unsupported`), ולריפו חסר כרגע `origin`.
   - בעת העבודה ממחשב אישי או מ־GitHub Codespaces/סביבה עם טוקן: להריץ `GITHUB_TOKEN=... ./scripts/push_to_github.sh <repo-url>`.
2. **השלמת שער המעבר ל־Live (`pmmb readiness`)**:
   - השלמת `soak` של 7 ימי Paper רציפים (כרגע 3/7 ימים).
   - הגדרת מפתחות Telegram (`PMMB_TG_TOKEN` / `CHAT_ID`) להתראות והפעלה מרחוק, ומפתחות ארנק/בורסה (`PMMB_PRIVATE_KEY` וכו') רק אחרי שה־readiness ירוק `11/11`.
3. **מחקר אלפא ואופטימיזציות נוספות**:
   - איסוף Order Book Imbalance (`pmmb collect` / L2 snapshots) ובחינת מילוי פסיבי מול Trade API v2.
   - פירוק אוטומטי ב־DB/אנליטיקה בין אסטרטגיות PERPS (`pullback` מול `breakout`) בעמודת `reason`/`strategy` של הטבלאות והצגתן ב־`Performance Attribution`.
   - הרצת אסטרטגיות רב־זמניות (4h trend filter לסינון עסקאות נגד מגמת־על ב־1h) — בכפוף למבחן Walk-Forward OOS חיובי.
   - בדיקות אינטגרציה ואבטחה לפני Live אמיתי (Rate limits, slip guard, ניטור עומסי CPU/זמן תגובה).

---

## 8. פרומפט מוכן להדבקה ישירה לצ'אט החדש

העתק והדבק את הטקסט הבא בתחילת הצ'אט החדש (וודא שהקוד / הריפו זמין לו דרך GitHub או העלאת קבצים):

```text
אנחנו ממשיכים את הפיתוח של הפרויקט `polymarket-momentum-bot` (PMMB Command Center).
קרא בבקשה מיד את הקבצים הבאים בסדר הזה לפני שאתה משנה שורה בקוד:
1. `docs/HANDOFF.md` (מסמך התדרוך המלא המעודכן נכון לקומיט `94168b4`)
2. `docs/DECISIONS.md` ו־`config/config.yaml`
3. הרץ `/usr/local/bin/pytest -q` ובדוק את `git log -n 5 --oneline` ו־`pmmb status`.

תקציר ההקשר העדכני:
- מדובר בבוט מסחר אוטונומי דו־זרועי (Polymarket CLOB + PERPS ×50 ב־OKX/Hyperliquid) עם שרת `0.0.0.0:8787`, דשבורד Obsidian Glass Pro, לולאות למידה רציפות מגובות Walk-Forward OOS (כל 20 דק'), תחזוקת DB אוטונומית (`run_autonomous_housekeeping` כל 30 דק'), וסקריפט supervisor אוטונומי (`scripts/run_autonomous.sh`).
- ב־Walk-Forward האחרון (16 נכסים, `tp_atr_mult=3.4`, `risk_per_trade_pct=0.03`, `max_total_margin_pct=0.59`, Tiered Risk): PERPS השיג `+155.19%` מלא / `+113.80%` OOS עם `100%` עקביות ו־`0` ליקווידציות. `229` טסטים עוברים ב־`pytest`.
- מבקש ממך לא לפגוע באסטרטגיות שמתו (מתועדות ב־`docs/HANDOFF.md`), לא לדלג על מבחני Walk-Forward לפני שינוי פרמטרים, ולשמור על כל האינווריאנטים של הבדיקות.
המטרה שלנו בצ'אט החדש היא: [כתוב כאן מה תרצה לעשות הלאה — למשל: להמשיך שדרוגים, לחבר ל-GitHub/Live, או להוסיף אסטרטגיות חדשות].
```
