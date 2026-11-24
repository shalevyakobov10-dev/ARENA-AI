#!/usr/bin/env bash
# מפעיל אוטונומי מלא של PMMB Command Center + הבוט הדו-זרועי (Auto-Heal Supervisor).
# מוודא שלמות DB לפני עלייה, מריץ את השרת והלולאה הרציפה, ומאתחל אוטומטית בכל נפילה.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1

mkdir -p logs state backups reports
LOG="logs/autonomous.log"
HOST="${PMMB_HOST:-127.0.0.1}"
PORT="${PMMB_PORT:-8787}"
INTERVAL="${PMMB_INTERVAL:-120}"
REFRESH="${PMMB_REFRESH:-30}"
BIN="$(command -v pmmb || echo /usr/local/bin/pmmb)"

log_msg() {
  printf '%s [AUTONOMOUS] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" | tee -a "$LOG"
}

trap 'log_msg "קיבל אות עצירה — סוגר שרת אוטונומי"; pkill -f "pmmb serve.*--port ${PORT}" || true; exit 0' INT TERM

log_msg "מאתחל בדיקת שלמות וסנכרון DB לפני הרצה..."
"$BIN" reconcile >>"$LOG" 2>&1 || true
"$BIN" backup >>"$LOG" 2>&1 || true

while true; do
  log_msg "מפעיל את PMMB Command Center + Autopilot (host=$HOST, port=$PORT, interval=${INTERVAL}s)..."
  "$BIN" serve --host "$HOST" --port "$PORT" --autostart --interval "$INTERVAL" --refresh "$REFRESH" >>"$LOG" 2>&1
  rc=$?
  log_msg "השרת נעצר (exit=$rc) — מריץ בדיקת סנכרון ומאתחל מחדש בעוד 5 שניות..."
  "$BIN" reconcile >>"$LOG" 2>&1 || true
  sleep 5
done
