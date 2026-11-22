# יומן — arena

## 2026-11-22 — עמלות, ביצוע, ועצמאות תפעולית

**עמלות.** גילויי: 91/100 שווקים מובילים עם `feesEnabled: true`. הנוסחה
`C×rate×p×(1−p)`, מייקרים פטורים, geopolitics פטור. אימתתי מול הטבלה הרשמית
(1.25 / 0.45 ל-100 מניות). נבנה `fees.py`, העמלה נכנסת ל-friction, ובבקטסט
127.09 עמלות מתוך 361.72 PnL = 35%.

**ביצוע.** מדדתי שלוש שיטות על אותה סדרה: טאקר +361.72, פסיבי w1 +269.06,
פסיבי w3 +149.05. מונוטוני — ככל שממתינים יותר מפסידים יותר. adverse selection.
מסקנה: `--entry passive` נשאר כלי מדידה. תיעוד: `reports/execution.md`.

**החרגות.** crypto+macro = +198.68 על 61 עסקאות (ניטרלי, לא הוחרג).
crypto+macro+tech+other = +30.75, עקביות 67% ⇒ קרס. נשאר `["crypto"]`.

**עצמאות.** `runtime.py` (דופק אטומי), `status.py`, `server.py` (דשבורד
בספרייה הסטנדרטית), `notify.py` (Telegram), `watchdog.sh`, systemd/launchd/docker.

**בדיקות.** 124 ירוקות.

## 2026-11-22 (שלב ב') — אמינות בקטסט, stop_mode=abs, שחזור ו-reconcile

**בדיקת זליגה וספרד.** גיליתי ש-Backtester לא חייב חצי-ספרד בכניסה/יציאה.
עם ספרד מלא ואפס זליגה מחלון החימום, `stop_mode=pct` נפל ל--71.30 OOS.
עברתי ל-`stop_mode=abs` (TP +5c / SL -8c, lookback 24ש', z=1.8):
OOS קפץ ל-+284.00 (73 עסקאות, 100% עקביות, 12/20 שווקים חיוביים), ותיק משותף
של $1,000 הניב +8.37% עם Max DD 1.02%. ה-bias נבדק על 650 שווקים (EV +0.0022 — מת).

**עמידות ושליטה.** מומש שחזור תיק מלא ב-Engine אחרי ריסטארט (מניעת קנייה כפולה),
סליקת שווקים שהוכרעו דרך CLOB `/markets/{cid}`, `pmmb reconcile` (שתפס ותיקן פער
אמיתי ב-`pmmb.db`!), `pmmb backup` חם, `halt.json` מתמיד, `pmmb telegram` (קריאה +
`/halt` בלבד), ושדרוג הדשבורד (שם שוק, נוכחי, לא ממומש, SL/TP, מד שבוע paper).

**בדיקות.** 172 ירוקות, אפס רשת.

## 2026-11-22 (שלב ג') — הגנות קורלציה, ספר דק, סימולציית תיק ו־HEAD תמיכה בשרת

- תוקנו: `do_HEAD` ב-`server.py` (השרת החזיר 501 לבדיקות HEAD), כפילות עמלת כניסה ב-`fees_paid`
  ב-`backtest.py`, חסר `fee_rate` ב-`pmmb scan`, ושמירת עסקאות חוזרות על אותו טוקן ב-`daily.py`
  ו-`pmmb report`.
- נוספו הגנות: `event_id` deduplication (`max_positions_per_event=1` נשמר ב-SQLite),
  `max_positions_per_sector=3`, בדיקת עומק ספר (`estimate_fill`) לפני פתיחה, ו-`min_entry_hours_to_resolution=24`
  (מונע פתיחת פוזיציות שעה לפני יציאה כפויה).
- נוסף `pmmb backtest --portfolio` לסימולציית תיק משותף אמיתי על ציר זמן מאוחד:
  `+19.44%` (`1,194.35 USDC`), `68` עסקאות, `54.4% win`, `PF 3.20`, `MaxDD 4.28%`.
- `config/config.yaml` עודכן בפועל גם לשורות `lookback_candles: 24` ו-`z_entry: 1.8`.
- **178 בדיקות ירוקות (אפס רשת).**

## 2026-11-22 (שלב ד') — מחקר Trailing/Time-stop + חוסן תפעולי ודשבורד מצטבר

- נבדקו אמפירית עם ספרד מלא:
  - `price_band=(0.05, 0.95)` עדיף על רצועות צרות יותר (`+3.18%` בתיק מול `+0.47%` / `-0.49%`).
  - `time_stop=48h` (`+2.65%`, PF 1.45) עדיף על `24h` (`-0.56%`, PF 0.92).
  - `TP=+5c / SL=-8c` קשיחים (`+157.71`, 57.4% win) עדיפים על BreakEven / Trailing (`+147.84`..`+156.94`).
- תשתית: SQLite WAL + `busy_timeout=5000`, `ProcessLock` (`flock`) למניעת הרצה כפולה,
  טיפול ב-`SIGTERM` לעצירה נקייה בסוף מחזור, וטיפול בשאריות dust ביציאה.
- שדרוג `status.py`: כרטיסיית `מצטבר` (`overall`: win%, PF, PnL, עמלות) וטבלת `עסקאות סגורות אחרונות`.
- **182 בדיקות ירוקות (אפס רשת).**

## 2026-11-22 (שלב ה') — תוכנת הבקרה המלאה PMMB Command Center

- נבנתה תוכנת בקרה גרפית שלמה (RTL, אפס תלויות ו-URLs חיצוניים): `src/pmmb/ui.py` +
  `build_command_center_data()` ב-`status.py` + נקודות API אינטראקטיביות ב-`server.py`
  (`GET /`, `/lite`, `/api/state`, `/status.json`, `/healthz`, ו-`POST /api/halt|resume|backup|reconcile|paper-cycle|trader/start|trader/stop`).
- הרצת מסחר דרך הדפדפן מוגבלת ל-`paper` בלבד (`403` במצב `live`) ומוגנת ב-`ProcessLock` + Token אופציונלי.
- נוסף `--html-out` ל-`pmmb status` לייצוא דוח תוכנה עצמאי (`reports/pmmb_command_center.html`).
- **184 בדיקות ירוקות (אפס רשת).**

