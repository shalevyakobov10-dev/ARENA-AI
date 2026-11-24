#!/usr/bin/env bash
# paper trading ארוך-טווח: watchdog + לוגים מתגלגלים + דוח יומי.
# שימוש:  ./scripts/paper_forever.sh [interval_sec]
set -uo pipefail
cd "$(dirname "$0")/.."

INTERVAL="${1:-60}"
RESTART_DELAY="${PMMB_RESTART_DELAY_SEC:-30}"
if ! [[ "$RESTART_DELAY" =~ ^[0-9]+([.][0-9]+)?$ ]]; then
  echo "PMMB_RESTART_DELAY_SEC must be a non-negative number" >&2
  exit 2
fi

CHILD_PID=""
STOPPING=0

shutdown() {
  STOPPING=1
  if [[ -n "$CHILD_PID" ]] && kill -0 "$CHILD_PID" 2>/dev/null; then
    echo "[$(date -Is)] שולח TERM לתהליך paper (pid=$CHILD_PID)" | tee -a "$LOG"
    kill -TERM "$CHILD_PID" 2>/dev/null || true
    wait "$CHILD_PID" 2>/dev/null || true
  fi
  CHILD_PID=""
}
trap 'shutdown; exit 0' INT TERM

LOG_DIR="logs"
mkdir -p "$LOG_DIR" reports backups pmmb.db.dir 2>/dev/null || true

rotate() {
  local f="$1" max=$((20 * 1024 * 1024))
  if [ -f "$f" ] && [ "$(stat -c%s "$f")" -gt "$max" ]; then
    mv "$f" "$f.$(date +%Y%m%d%H%M)"
  fi
}

echo "[$(date -Is)] מתחיל paper ארוך-טווח (interval=${INTERVAL}s, engine=${PMMB_ENGINE:-config})"
while true; do
  rotate "$LOG_DIR/paper.log"
  pmmb paper --interval "$INTERVAL" >> "$LOG_DIR/paper.log" 2>&1 &
  CHILD_PID=$!
  wait "$CHILD_PID"
  code=$?
  CHILD_PID=""
  if (( STOPPING )); then
    break
  fi
  echo "[$(date -Is)] הבוט יצא בקוד $code — מפעיל מחדש בעוד ${RESTART_DELAY}s"
  sleep "$RESTART_DELAY"
done
