#!/usr/bin/env bash
# הקמת ה-remote של GitHub פעם אחת.
#   scripts/setup_remote.sh git@github.com:USER/polymarket-momentum-bot.git
set -euo pipefail
cd "$(dirname "$0")/.."

URL="${1:-}"
[ -n "$URL" ] || { echo "שימוש: $0 <repo-url>"; exit 1; }

git rev-parse --git-dir >/dev/null 2>&1 || git init -q
if git remote | grep -qx origin; then
  git remote set-url origin "$URL"
  echo "✓ origin עודכן ל-$URL"
else
  git remote add origin "$URL"
  echo "✓ origin נוסף: $URL"
fi

# .gitignore קריטי — לא לדחוף סודות או DB
cat > .gitignore <<'IGN'
.env
*.db
*.db-journal
*.db-wal
state/
logs/
data/
backups/
reports/*.json
!reports/.gitkeep
__pycache__/
*.egg-info/
.venv/
.pytest_cache/
.ruff_cache/
IGN

git add -A
git -c user.name="${PMMB_AGENT:-arena}" -c user.name="${PMMB_AGENT:-arena}" \
    -c user.email="agent@local" commit -qm "baseline: לפני סנכרון עם סוכן נוסף" || true

cat <<'MSG'

הבא:
  git branch -M main
  git push -u origin main

אם הענף remote כבר קיים עם קוד של הסוכן השני:
  git fetch origin && git checkout -b agent/<שם>/<נושא> origin/main

ואז כל מחזור עבודה:  scripts/sync.sh "מה עשית"
MSG
