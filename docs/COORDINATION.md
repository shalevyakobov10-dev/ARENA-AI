# תאום בין סוכנים — GitHub כמקור אמת יחיד

שני סוכני AI עובדים על הריפו הזה. בלי פרוטוקול, זה נגמר בקונפליקטים
ובקוד שמבטל אחד את השני. הפרוטוקול הזה קצר בכוונה, והוא **חובה**.

---

## 1. מודל ההרשאות על קבצים

לפני שנוגעים בקובץ — טוענים בעלות ב-`docs/claims.json`:

```json
{
  "claims": [
    {"agent": "arena", "paths": ["src/pmmb/fees.py", "src/pmmb/feeview.py"],
     "issue": "fee model", "since": "2026-11-22T07:00:00Z", "expires": "2026-11-25T07:00:00Z"}
  ]
}
```

כללים:
- **בעלות בתוקף** (לפני `expires`) ⇒ הסוכן השני **לא נוגע** בקבצים האלה.
  הוא יכול לפתוח issue/הערה, לא לערוך.
- תוקף מקסימלי: **72 שעות**. תביעה שפגה — פנויה.
- קובץ שאינו תחת בעלות — כל אחד יכול לערוך, אבל ראה סעיף 3 (rebase).
- **קבצים שאין לגעת בהם אף פעם** (בעלות גלובלית): `docs/HANDOFF.md`
  (עדכון בתור — ראה סעיף 5), `config/config.yaml` בשורות `mode` ו-`db_path`,
  `pmmb.db`, `state/`, `.env`, `logs/`.

---

## 2. ענפים

```
main                       ← תמיד ירוק, תמיד עובד
agent/<name>/<topic>        ← עבודה
```

- אסור לדחוף ישירות ל-`main` כשיש סוכן שני פעיל.
- כל סוכן עובד בענף משלו, וממזג ל-main דרך PR (או fast-forward אם אין סוכן שני).
- שם ענף: `agent/arena/fees`, `agent/claude/imbalance` — קצר ותיאורי.

---

## 3. מחזור סנכרון (הפקודה היחידה שצריך לזכור)

```bash
scripts/sync.sh "תיאור השינוי בעברית"
```

מה היא עושה, בסדר הזה:
1. `git stash` אם יש שינויים לא-מקומטים.
2. `git fetch origin` + `git rebase origin/main`.
3. **מריצה `make test`** — ואם אדום, **עוצרת ולא דוחפת** (השינויים נשארים מקומיים).
4. `git push` לענף שלי.
5. רושמת שורה ב-`docs/journal/<agent>.md`.

**קונפליקט:** אם הקונפליקט בקובץ שתחת בעלותו של הסוכן השני —
`git rebase --abort`, ולתעד ב-journal. לא "לנצח" בקונפליקט.
אם הקונפליקט בקובץ פנוי — לפתור ידנית, להריץ טסטים, להמשיך.

---

## 4. חוזה ממשקים (מה שאסור לשבור)

| רכיב | חוזה |
|---|---|
| `signals.Engine.evaluate(market, prices, *, market_price, spread, extra)` | מחזיר `Signal`; `extra["fee_rate"]` **חייב** להשפיע על friction |
| `models.Market` | שדות `taker_fee_rate`, `fees_enabled`, `sector` נטענים ב-`from_gamma` |
| `execution.Broker.execute(order, book, aggressive)` | מחזיר `Fill` או `None`; אף פעם לא זורק |
| `data.store.Store` | מיגרציות תוספתיות בלבד; `record_*` לא משנות סכימות קיימות |
| `runtime.Heartbeat` + `state/heartbeat.json` | סכימה: `ts, cycle, mode, engine, equity, cash, exposure, positions, last_cycle, halted, pid` |
| `pmmb status --json` | **קוד יציאה 0 = בריא, 3 = לא בריא.** ה-watchdog מסתמך על זה |

שינוי בכל אחד מאלה ⇒ להשפיע גם על הבדיקות וגם על `docs/HANDOFF.md`.

---

## 5. יומן והחלטות

- `docs/journal/<agent>.md` — **append-only**. מה עשיתי, למה, ומה המדידה.
  לא מוחקים שורות של הסוכן השני.
- `docs/DECISIONS.md` — החלטות ארכיטקטוניות בפורמט ADR מקוצר.
  החלטה חדשה = שורה חדשה. לא עורכים החלטה קודמת; מוסיפים "נדחתה על ידי".
- `docs/HANDOFF.md` — מתעדכן **רק** כשמשהו מהותי משתנה (אסטרטגיה, פרמטר
  מרכזי, מסקנת מדידה). זו לא רשימת שינויים.

---

## 6. כללי מדידה — הלב של הפרויקט

כל סוכן שמציע שיפור חייב להציג **לפני/אחרי** על אותו מדד:

```
walkforward OOS (USDC, עסקאות, עקביות בין חלונות)
בקטסט (PnL נטו, fees_paid, win rate)
```

שיפור שנראה טוב בטבלה ונכשל ב-OOS — **נדחה**. זה קרה עם politics,
עם trend guard ועם כניסה פסיבית. שלוש פעמים זה כבר דפוס, לא מקרה.

---

## 7. הרשאות מסוכנות

- **`live` לא נדחף ל-main אף פעם.** אם צריך לבדוק, בענף, עם `--cycles 1`,
  ובמפתחות בדיקה.
- אין לדחוף `.env`, מפתחות, `state/`, `pmmb.db`.
- שינוי ב-`risk/` מחייב בדיקה חדשה שמראה שההגנות עדיין עוצרות
  (daily stop, drawdown kill, cooldown).
