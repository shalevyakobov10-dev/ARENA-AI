#!/usr/bin/env bash
# סנכרון בטוח מול GitHub בין שני סוכנים.
#
#   scripts/sync.sh "תיאור השינוי"
#
# סדר הפעולות: stash → fetch → rebase → TEST → push → יומן.
# אם הבדיקות אדומות — לא דוחפים כלום. זו כל המטרה.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1

MSG="${1:-עדכון שוטף}"
AGENT="${PMMB_AGENT:-$(git config user.name 2>/dev/null || echo agent)}"
BRANCH="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo main)"
JOURNAL="docs/journal/${AGENT}.md"

say() { printf '\033[1;36m▸\033[0m %s\n' "$*"; }
die() { printf '\033[1;31m✗\033[0m %s\n' "$*" >&2; exit 1; }

command -v git >/dev/null || die "git לא מותקן"
git rev-parse --git-dir >/dev/null 2>&1 || die "זה לא ריפו git"

if [ -z "$(git remote)" ]; then
  die "אין remote. הרץ: git remote add origin <URL>  (וראה scripts/setup_remote.sh)"
fi

# --- 1. שומרים שינויים מקומיים ---
STASHED=0
if ! git diff --quiet || ! git diff --cached --quiet; then
  say "מאחסן שינויים מקומיים"
  git stash push -u -m "sync-$(date -u +%s)" >/dev/null && STASHED=1
fi

# --- 2. מושכים את האחרון ---
TARGET="${PMMB_BASE:-main}"
say "מושך origin/$TARGET"
git fetch origin "$TARGET" --quiet || die "fetch נכשל (רשת/הרשאות?)"

if [ "$BRANCH" != "$TARGET" ] && git rev-parse --verify "origin/$TARGET" >/dev/null 2>&1; then
  say "rebase על origin/$TARGET"
  if ! git rebase "origin/$TARGET" --quiet 2>/tmp/rebase_err; then
    git rebase --abort 2>/dev/null
    [ "$STASHED" = 1 ] && git stash pop >/dev/null 2>&1
    die "קונפליקט ב-rebase. פתח ידנית (וראה docs/COORDINATION.md §3). לא דחפתי כלום."
  fi
fi

[ "$STASHED" = 1 ] && { say "מחזיר שינויים"; git stash pop >/dev/null 2>&1 || say "⚠️ stash pop נכשל — בדוק ידנית"; }

# --- 3. בדיקות: שער הברזל ---
if [ -d tests ]; then
  say "מריץ בדיקות (שער לפני push)"
  if ! python -m pytest -q >/tmp/pytest_out 2>&1; then
    tail -25 /tmp/pytest_out
    die "בדיקות אדומות — לא דוחף. תקן קודם."
  fi
  tail -1 /tmp/pytest_out
fi

# --- 4. קומיט ודחיפה ---
git add -A
if git diff --cached --quiet; then
  say "אין שינויים לקומיט"
else
  git -c user.name="$AGENT" commit -qm "$MSG" || die "commit נכשל"
  say "קומיט: $MSG"
fi

say "דוחף ל-origin/$BRANCH"
git push -u origin "$BRANCH" --quiet || die "push נכשל (הרשאות/הגנת ענף?)"

# --- 5. יומן ---
mkdir -p docs/journal
{
  printf '\n## %s — %s\n' "$(date -u +%Y-%m-%d\ %H:%M)" "$MSG"
  printf -- '- ענף: `%s` · קומיט: `%s`\n' "$BRANCH" "$(git rev-parse --short HEAD)"
  printf -- '- בדיקות: %s\n' "$(tail -1 /tmp/pytest_out 2>/dev/null || echo 'לא הורצו')"
} >> "$JOURNAL"
git add "$JOURNAL" >/dev/null 2>&1 && \
  git -c user.name="$AGENT" commit -qm "יומן: $MSG" >/dev/null 2>&1 && \
  git push --quiet >/dev/null 2>&1 || true

printf '\033[1;32m✓\033[0m הסתנכרן. ענף %s מעודכן.\n' "$BRANCH"
