#!/usr/bin/env bash
# paper trading ארוך-טווח: watchdog + לוגים מתגלגלים + דוח יומי.
# שימוש:  ./scripts/paper_forever.sh [interval_sec]
set -uo pipefail
cd "$(dirname "$0")/.."

INTERVAL="${1:-60}"
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
  pmmb paper --interval "$INTERVAL" >> "$LOG_DIR/paper.log" 2>&1
  code=$?
  echo "[$(date -Is)] הבוט יצא בקוד $code — מפעיל מחדש בעוד 30s"
  sleep 30
done
