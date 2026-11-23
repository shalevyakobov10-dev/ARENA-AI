# HANDOFF — קרא את זה ראשון

_המסמך הזה הוא נקודת הכניסה היחידה לפרויקט. אם אתה סוכן AI שנוגע בקוד הזה,
קרא אותו לפני שאתה נוגע בשורה. האחרון שעדכן: Arena (2026-11-22)._

---

## 1. מה הבוט הזה, בדיוק

בוט מסחר על Polymarket שנבנה בסדר הזה: **מודדים, אחר כך בונים.**
כל אסטרטגיה שקיימת כאן שרדה מדידה. כל אסטרטגיה שמתה — מתועדת כאן כדי
שאף אחד לא יבנה אותה שוב.

- מנוע ברירת מחדל: **mean-reversion** (היפוך לממוצע) על נרות שעה.
- מצב: **paper** כברירת מחדל. live מוגן ב-3 שכבות.
- אופק: 48 שעות. כניסה LONG על טבילה חריגה, יציאה ב-TP 10c / SL 12c / time stop.

---

## 2. מה נמדד ומת — **אל תבנה את אלה מחדש**

| השערה | תוצאה | איפה מתועד |
|---|---|---|
| **מומנטום** (המשך מגמה) | מת. corr שלילי חזק | README שלב 1 |
| **SHORT / קניית NO** | גרוע יותר מ-LONG | config `allow_short: false` |
| **ארביטראז'** (YES+NO<1) | **לא קיים.** min ask(Y)+ask(N)=1.0010 על 71 שווקים; כל סל negRisk 1.004–1.049 | session memory |
| **הטיית פייבוריט/לונגשוט** | לא מובהקת גם בהרחבה: EV +0.0022 על 367 שווקים כלולים (650 שנסרקו) | `scripts/research_bias.py` |
| **trend guard** | נדחה בכל החלונות | שלב 4 |
| **החרגת politics** | **הרגה את ה-OOS** (+38.45 → +5.24) | שלב 6 |
| **כניסה פסיבית (מייקר)** | **מפסידה.** 362 → 269 → 149 ככל שממתינים יותר | `reports/execution.md` |
| **crypto לסקטור** | נטו 8% hit, −0.27 — הוחרג | `universe.exclude_sectors` |
| **Trailing Break-Even Stop** | קיצץ win rate (75%→69.2%) ותשואה (+3.11%→+2.98%) עקב ניעור מוקדם | ADR #17 |

---

## 3. שלוש אמיתות שהעבודה הזו הסתמכה עליהן

1. **העמלות אמיתיות.** `fee = C × rate × p × (1 − p)`, **מייקרים פטורים**,
   **geopolitics פטור לגמרי**. 91 מ-100 שווקים מובילים עם `feesEnabled: true`.
   ⇒ העמלה נכנסת ל-`friction` בתוך הסיגנל. אסור לחזור לתת לה `0`.
2. **היסטוריה של שוק סגור** ניתנת לשליפה רק עם `startTs`/`endTs`
   (`interval=max` מחזיר אפס שורות — מלכודת).
3. **`outcomePrices[0]` אינו YES.** חלק מהשווקים מסדרים `["No","Yes"]`.
   תמיד למפות דרך `outcomes.index("yes")`.

---

## 4. המצב הנוכחי (מדויק, לא שיווקי)

```
223 בדיקות · 27 פקודות (כולל pmmb perps *) · אפס קריאות רשת בבדיקות
1) זרוע Polymarket (ADR #18–22):
  Portfolio Backtest (`pmmb backtest --top 35 --portfolio`, 25 שווקים, spread=0.015):
    47 עסקאות | Win Rate 66.0% | PF 2.16 | תשואה +17.56% (1175.57 USDC) | Max DD 4.11% | עמלות 13.92 USDC
  Walk-Forward OOS (`pmmb walkforward --markets 35 --spread 0.01`, 3 חלונות, 25 שווקים):
    +56.19 USDC OOS על 54 עסקאות (ללא מוביל +28.23, 13/21 שווקים חיוביים, עקביות 100%) | Baseline OOS: +82.01 USDC

2) זרוע חוזים תמידיים — PERPS ×50 (ADR #23–24, OKX + Hyperliquid + Binance):
  Portfolio Backtest (`pmmb perps backtest --assets 16 --lookback 720`, נרות 1h + Funding אמיתי):
    96 עסקאות | Win Rate 67.7% | PF 1.62 | תשואה +38.29% (1382.90 USDC) | Max DD 9.4% | ליקווידציות 0
    מינוף ממוצע ×20.7 (שיא ×46.4, תקרה ×50) | 3-Fold Walk-Forward OOS: +21.79% (עקביות 100%, לעומת +6.83% ב-24 נכסים)
    פרמטרים מקובעים: `max_assets=16`, `sl_atr_mult=1.5`, `tp_atr_mult=2.6`, `z_entry=1.8`, `adx_trend_threshold=25.0`, `liquidation_buffer_mult=2.2`

רשת חדשות של 22+ פידים מוסדיים (כולל קריפטו-מאקרו) + למידה רקע אסינכרונית + ניטור תוך-מחזורי (60s) + Command Center UI (`pmmb serve --autostart`)
```

פרמטרים מכוילים: `lookback_candles=24`, `z_entry=1.8`, `z_max=6.5`, `reversion_ratio=0.55`,
`rsi_max=40.0`, `max_spread_to_edge=0.75`, `min_score=0.55`, `min_edge=0.005` (נמדד **אחרי** ספרד ועמלה),
`max_taker_fee_rate=0.02`, `max_hours_to_resolution=1080`, `price_band=[0.12, 0.88]`,
`stop_mode=abs`, TP +0.06, SL -0.07, `time_stop_hours=48`, `kelly_fraction=0.65`, `cooldown_minutes=360`,
`max_open_positions=5`, `max_positions_per_sector=2`, `drawdown_throttle_pct=0.05`.

---

## 5. חוקי הברזל — אל תפר אותם

1. **`make test` ירוק לפני כל push.** אין יוצאי דופן. הבדיקות לא נוגעות ברשת.
2. **paper נשאר ברירת מחדל.** `live` דורש `mode: live` + מפתחות + אישור מפורש.
3. **כל החרגת סקטור או שינוי פרמטר — רק עם הוכחת walk-forward.**
   politics נראתה גרועה בטבלה והחרגתה הרגה את ה-OOS. הטבלה משקרת, ה-OOS לא.
4. **מיגרציות DB הן תוספתיות בלבד** (`_migrate()`), כל עוד אין גרסה חיה.
5. **אף פעם לא לדווח PnL בלי עמלות.** הדוח חייב להראות `fees_paid`.
6. **deliverables בעברית.** קוד ומזהים באנגלית, הסברים בעברית.

---

## 6. איפה עוד יש כסף על הרצפה (רעיונות לא ממומשים, לפי סדר עדיפות)

1. **מילוי פסיבי אמיתי** — למדוד עם Trade API v2
   (`data-api.polymarket.com/v2/trades?condition=<id>`), לא עם נרות שעה.
   המדידה הנוכחית מכוונת **לרעת** הפסיבי, ולכן המסקנה שמרנית ולא סופית.
2. **imbalance** — התשתית קיימת (`books` table, `pmmb imbalance`), אבל יש
   רק 2 דקות דאטה. צריך שעות של `pmmb collect` לפני שאפשר לשפוט.
3. **maker rebates** — `rebateRate: 0.15`. לא נמדד בכלל. אם פוזיציה מחזיקה
   48 שעות, אולי שווה לספק נזילות סביב הפוזיציה.
4. **bias study** — הורחב ל-650 שווקים (367 כלולים): EV=+0.0022 — לא עובר עלות סבב.
5. **סקטור culture** — נטו +0.0499 אבל n=9. רעש, לא ממצא.

---

## 7. איך מריצים

```bash
pip install -e ".[dev]"
make test            # 124 בדיקות
pmmb paper --cycles 1
pmmb status          # בריאות + הון + פוזיציות
pmmb serve           # דשבורד לטלפון על :8787
pmmb readiness       # שער המעבר ל-live (exit 0 = מוכן)
pmmb reconcile       # סנכרון DB מול החשבון/הבורסה (--fix לתקן)
pmmb backup          # גיבוי חם ומאומת של SQLite
pmmb halt / resume   # עצירת חירום מתמדת
pmmb telegram        # לולאת פקודות לטלפון (/status, /positions, /halt)
```

פריסה עצמאית: `deploy/README.md` (systemd / launchd / docker).

---

## 7.5 שער ה-live

`pmmb readiness` חוסם מעבר ל-live עד ש: עמלות מתומחרות ונגבו בפועל,
walk-forward חיובי ועקבי (≥66%), 7 ימי paper עם דופק, ≤3 שגיאות ERROR,
וגבולות סיכון שפויים. **אין לעקוף אותו.**

## 8. איך מתאמים איתנו

ראה `docs/COORDINATION.md`. בקצרה: ענף לכל סוכן, `docs/claims.json` לבעלות
על קבצים, יומן ב-`docs/journal/`, ו-`scripts/sync.sh` שעושה את הכל בטוח.
