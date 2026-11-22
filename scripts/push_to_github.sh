#!/usr/bin/env bash
# דחיפה/מיזוג מול GitHub — בלי לשמור טוקן על הדיסק.
#
#   GITHUB_TOKEN=ghp_xxx scripts/push_to_github.sh git@github.com:USER/REPO.git
#   GITHUB_TOKEN=ghp_xxx scripts/push_to_github.sh https://github.com/USER/REPO.git merge
#
#   מצב 1 (ברירת מחדל): דוחף את הענף המקומי.
#   מצב 2 (merge):       מושך קוד של הסוכן השני, ממזג, מריץ בדיקות, ואז דוחף.
#
# הטוקן מועבר דרך כותרת HTTP זמנית, לא נכתב ל-.git/config ולא ל-.env.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1

URL="${1:-}"; MODE="${2:-push}"
AGENT="${PMMB_AGENT:-arena}"
say() { printf '\033[1;36m▸\033[0m %s\n' "$*"; }
die() { printf '\033[1;31m✗\033[0m %s\n' "$*" >&2; exit 1; }

[ -n "$URL" ] || die "שימוש: GITHUB_TOKEN=... $0 <repo-url> [push|merge]"
[ -n "${GITHUB_TOKEN:-}" ] || die "חסר GITHUB_TOKEN (fine-grained PAT עם Contents: write)"
git rev-parse --git-dir >/dev/null 2>&1 || git init -q

# --- remote (בלי טוקן ב-URL!) ---
if git remote | grep -qx origin; then
  git remote set-url origin "$URL"
else
  git remote add origin "$URL"
fi
say "remote: $URL"

# --- אימות עם כותרת זמנית ---
AUTH_HEADER="AUTHORIZATION: basic $(printf 'x-access-token:%s' "$GITHUB_TOKEN" | base64 | tr -d '\n')"
GIT_AUTH=(git -c "http.extraheader=$AUTH_HEADER")

MAIN="${PMMB_BASE:-main}"
BRANCH="$(git rev-parse --abbrev-ref HEAD)"

say "בודק גישה לריפו"
"${GIT_AUTH[@]}" ls-remote --heads origin >/dev/null 2>&1 \
  || die "אין גישה — בדוק את ה-URL והטוקן (הרשאות Contents: read/write?)"

# --- מצב merge: לאחד עם העבודה של הסוכן השני ---
if [ "$MODE" = "merge" ]; then
  say "מושך origin/$MAIN"
  "${GIT_AUTH[@]}" fetch origin "$MAIN" --quiet || die "fetch נכשל"
  if git rev-parse --verify "origin/$MAIN" >/dev/null 2>&1; then
    BASE="$(git merge-base HEAD "origin/$MAIN" 2>/dev/null || true)"
    if [ -z "$BASE" ]; then
      say "היסטוריות לא קשורות — ממזג עם --allow-unrelated-histories"
      MERGE_OPTS=(--allow-unrelated-histories --no-commit)
    else
      MERGE_OPTS=(--no-commit)
    fi
    if ! git merge "${MERGE_OPTS[@]}" "origin/$MAIN" >/tmp/merge_out 2>&1; then
      echo
      echo "קונפליקטים:"
      git diff --name-only --diff-filter=U | sed 's/^/  · /'
      git merge --abort 2>/dev/null
      die "המיזוג בוטל. פתח ידנית לפי docs/COORDINATION.md §3 — לא דחפתי כלום."
    fi
    say "המיזוג נקי — מריץ בדיקות"
    if ! python -m pytest -q >/tmp/pytest_merge 2>&1; then
      tail -25 /tmp/pytest_merge
      git merge --abort 2>/dev/null
      die "הבדיקות נכשלו אחרי המיזוג — ביטלתי. קוד הסוכן השני לא תואם."
    fi
    tail -1 /tmp/pytest_merge
    git add -A
    git -c user.name="$AGENT" -c user.email="agent@local" \
        commit -qm "merge: איחוד עם origin/$MAIN (בדיקות ירוקות)" || true
    say "קומיט מיזוג נוצר"
  fi
fi

# --- שער בדיקות לפני דחיפה ---
if [ -d tests ]; then
  say "בדיקות לפני push"
  python -m pytest -q >/tmp/pytest_push 2>&1 || { tail -20 /tmp/pytest_push; die "בדיקות אדומות — לא דוחף"; }
  tail -1 /tmp/pytest_push
fi

# --- קומיט אם יש מה ---
git add -A
git diff --cached --quiet || git -c user.name="$AGENT" -c user.email="agent@local" \
  commit -qm "sync: עדכון מ-$AGENT"

say "דוחף $BRANCH → origin"
"${GIT_AUTH[@]}" push -u origin "$BRANCH" --quiet || die "push נכשל (הגנת ענף? הרשאות?)"

printf '\033[1;32m✓\033[0m נדחף: %s (ענף %s)\n' "$URL" "$BRANCH"
say "הטוקן לא נשמר בשום מקום — אפשר לבטל אותו ב-GitHub"
