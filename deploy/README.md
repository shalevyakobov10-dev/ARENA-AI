# פריסה עצמאית — מחשב + טלפון

המטרה: הבוט רץ לבד 24/7, מתאושש מקריסות, שורד reboot, ומאפשר לראות
מה קורה מהטלפון. שלושה מסלולים — בחר אחד.

---

## 1. לינוקס (מומלץ) — systemd

```bash
sudo mkdir -p /opt && sudo cp -r polymarket-momentum-bot /opt/
cd /opt/polymarket-momentum-bot
python3 -m venv .venv && .venv/bin/pip install -e .
cp .env.example .env            # מלא TELEGRAM + (אם live) מפתחות

sudo cp deploy/systemd/pmmb-bot.service      /etc/systemd/system/
sudo cp deploy/systemd/pmmb-status.service   /etc/systemd/system/
sudo cp deploy/systemd/pmmb-watchdog.service /etc/systemd/system/
sudo cp deploy/systemd/pmmb-watchdog.timer   /etc/systemd/system/
sudo cp deploy/systemd/pmmb-telegram.service /etc/systemd/system/
sudo cp deploy/systemd/pmmb-backup.service   /etc/systemd/system/
sudo cp deploy/systemd/pmmb-backup.timer     /etc/systemd/system/

sudo systemctl daemon-reload
sudo systemctl enable --now pmmb-bot pmmb-status pmmb-telegram
sudo systemctl enable --now pmmb-watchdog.timer pmmb-backup.timer

systemctl status pmmb-bot --no-pager
journalctl -u pmmb-bot -f          # לוג חי
```

מה זה נותן: `Restart=always` (קם אחרי קריסה), `MemoryMax=1G` (לא אוכל את
המחשב), ו-watchdog שכל 10 דקות בודק את הדופק ומפעיל מחדש אם נתקע.

## 2. macOS — launchd

```bash
cp deploy/launchd/com.pmmb.bot.plist ~/Library/LaunchAgents/
# ערוך את USERNAME בתוך הקובץ
launchctl load ~/Library/LaunchAgents/com.pmmb.bot.plist
launchctl list | grep pmmb
```

`KeepAlive: true` ⇒ השרת מחזיר את הבוט גם אחרי reboot.

## 3. Docker — הכי נייד

```bash
docker compose -f deploy/docker/docker-compose.yml up -d --build
docker compose -f deploy/docker/docker-compose.yml logs -f bot
```

שני קונטיינרים: `bot` (מסחר) ו-`status` (דשבורד). ה-DB, הלוגים והדוחות
בכרכים חיצוניים ⇒ הנתונים שורדים עדכון תמונה. ה-`HEALTHCHECK` מחזיר
`unhealthy` אם הדופק מתיישן, ו-Docker יכול להפעיל מחדש אוטומטית.

---

## הטלפון — איך בעצם רואים

שלוש דרכים, מהבטוחה לפחות:

| שיטה | איך | מתאים ל |
|---|---|---|
| **Telegram** | `PMMB_TELEGRAM_TOKEN` + `PMMB_TELEGRAM_CHAT_ID` ב-`.env`, ואז `pmmb notify-test` | כל מקום, גם בלי IP ציבורי. **מומלץ** |
| **Tailscale** | להתקין על המחשב ועל הטלפון, ואז `http://<machine>:8787` מהרשת הפרטית | דשבורד מלא, בלי לפתוח פורט לאינטרנט |
| **פורט ציבורי** | `pmmb serve --port 8787 --token <סוד>` + פתיחת פורט/Cloudflare Tunnel | רק עם טוקן. הדשבורד קריאה בלבד |

```bash
pmmb serve --host 0.0.0.0 --port 8787 --token "$(openssl rand -hex 16)"
# מהטלפון: http://<ip>:8787/?token=<הטוקן>
```

### מה רואים בדשבורד
הון · מזומן · חשיפה · פוזיציות פתוחות (כיוון/גודל/מחיר/גיל) · PnL ועמלות היום ·
אירועים אחרונים · נורית בריאות (ירוק/אדום). מתעדכן לבד כל 30 שניות, בלי JS,
בלי משאבים חיצוניים ⇒ עובד גם ברשת איטית.

---

## הגנות שרצות בלי מגע אדם

| הגנה | מה עושה | איפה |
|---|---|---|
| דופק | קובץ שמתעדכן כל מחזור; גיל > 10 דק' ⇒ לא בריא | `state/heartbeat.json` |
| watchdog | מפעיל מחדש + מתריע בטלגרם | `scripts/watchdog.sh` (timer/cron) |
| סטופ יומי | עוצר ב-5% הפסד יומי | `risk/manager.py` |
| drawdown kill | עוצר ב-20% ירידה מהשיא | `risk/manager.py` |
| cooldown | 30 דקות אחרי יציאה, לא נכנסים שוב לאותו שוק | `risk/manager.py` |
| תקרת חשיפה | 40% מההון, 10% לפוזיציה, 5 פוזיציות | `risk/manager.py` |
| התראת עצירה | הודעת Telegram כשהבוט עוצר את עצמו | `notify.py` |

---

## שער המעבר ל-live — נבדק ע"י מכונה

```bash
pmmb readiness            # exit 0 = מוכן · exit 2 = לא מוכן
```

| בדיקה | חוסם? |
|---|---|
| עמלות במודל + נגבו בפועל בבקטסט | ❌ חוסם |
| walk-forward חיובי ועקביות ≥66% | ❌ חוסם |
| 7 ימי paper עם דופק | ❌ חוסם |
| יותר מ-3 שגיאות ERROR | ❌ חוסם |
| גבולות סיכון שפויים (יומי ≤10%, DD ≤30%, חשיפה ≤60%) | ❌ חוסם |
| פערים ברציפות, התראות טלפון, גיבוי DB | ⚠️ מזהיר בלבד |

## צ'קליסט לפני live

- [ ] `pmmb paper` רץ לפחות שבוע בלי תקלות, `state/heartbeat.json` תמיד טרי
- [ ] `pmmb walkforward` — כל החלונות חיוביים
- [ ] `pmmb status` מחזיר 🟢 ו-`pmmb reconcile` מחזיר 🟢 (אפס פערים)
- [ ] `pmmb backup` רץ יומית (timer פעיל)
- [ ] `pmmb notify-test` — הגיעה הודעה לטלפון
- [ ] watchdog מוגדר ובדוק (הרוג ידנית את הבוט, חכה 10 דק', וודא שקם)
- [ ] `.env` עם `PMMB_MODE=live` ומפתחות — **לא מסונכרן ל-GitHub**
- [ ] סכום התחלתי קטן שאתה מוכן להפסיד
