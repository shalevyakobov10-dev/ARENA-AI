#!/usr/bin/env bash
# הרצת paper trading 24/7 עם הפעלה מחדש אוטומטית
set -euo pipefail
cd "$(dirname "$0")/.."

INTERVAL="${INTERVAL:-60}"
LOG="logs/paper.log"
mkdir -p logs

while true; do
  echo "[$(date -Is)] מפעיל paper (interval=${INTERVAL}s)" >> "$LOG"
  if pmmb paper --interval "$INTERVAL" >> "$LOG" 2>&1; then
    echo "[$(date -Is)] הבוט יצא בצורה תקינה" >> "$LOG"
    break
  fi
  echo "[$(date -Is)] קריסה — מפעיל מחדש בעוד 30s" >> "$LOG"
  sleep 30
done
