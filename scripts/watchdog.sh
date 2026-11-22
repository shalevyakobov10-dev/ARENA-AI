#!/usr/bin/env bash
# שומר סף: אם הדופק מתיישן — מפעיל מחדש את הבוט ומתריע.
# מיועד ל-cron/systemd timer. יוצא ב-0 תמיד (כדי לא להציף התראות על עצמו).
set -uo pipefail
cd "$(dirname "$0")/.." || exit 0

MAX_AGE="${PMMB_MAX_AGE:-600}"          # 10 דקות
LOG="logs/watchdog.log"
mkdir -p logs

say() { printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >> "$LOG"; }

notify() {
  [ -n "${PMMB_TELEGRAM_TOKEN:-}" ] && [ -n "${PMMB_TELEGRAM_CHAT_ID:-}" ] || return 0
  curl -s -m 10 -X POST "https://api.telegram.org/bot${PMMB_TELEGRAM_TOKEN}/sendMessage" \
    -d "chat_id=${PMMB_TELEGRAM_CHAT_ID}" -d "text=$1" >/dev/null || true
}

if pmmb status --json --max-age "$MAX_AGE" >/tmp/pmmb_status.json 2>/dev/null; then
  say "תקין"
  exit 0
fi

reason=$(python3 - <<'PY' 2>/dev/null || echo "unknown"
import json
try:
    d = json.load(open("/tmp/pmmb_status.json"))
    print(d["health"]["reason"])
except Exception:
    print("status command failed")
PY
)
say "לא בריא: $reason — מפעיל מחדש"

# systemd (אם קיים) ואחרת launchctl (macOS)
if command -v systemctl >/dev/null 2>&1; then
  systemctl restart pmmb-bot 2>/dev/null && say "systemctl restart pmmb-bot"
elif command -v launchctl >/dev/null 2>&1; then
  launchctl kickstart -k "gui/$(id -u)/com.pmmb.bot" 2>/dev/null && say "launchctl kickstart"
else
  say "אין systemd/launchd — לא ניתן לאתחל אוטומטית"
fi

notify "🔴 PMMB לא בריא: ${reason}. ניסיתי להפעיל מחדש."
exit 0
