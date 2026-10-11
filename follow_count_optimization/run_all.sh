#!/usr/bin/env bash
# End-to-end: X export -> who doesn't follow back -> their follower counts -> unfollow small accounts.
#
#   ./run_all.sh                     # full run (threshold 4500)
#   ./run_all.sh --fresh             # new X export: clear old results first
#   ./run_all.sh --threshold 3000    # unfollow accounts under 3,000 followers
#   ./run_all.sh --limit 20          # unfollow at most 20 this run
#   ./run_all.sh --dry-run           # do everything except unfollowing; show who would go
#   ./run_all.sh --skip-counts       # reuse the follower counts you already have
#   ./run_all.sh --cookies           # log in to X by pasting cookies (if the login page hangs)
#   ./run_all.sh --help
#
# Needs following.js and follower.js (from your X data export) in this folder.

set -euo pipefail
cd "$(dirname "$0")"

THRESHOLD=4500
LIMIT=""
FRESH=0
DRY_RUN=0
SKIP_COUNTS=0
SKIP_UNFOLLOW=0
COOKIES=0

usage() { sed -n '2,13p' "$0" | sed 's/^# \{0,1\}//'; exit 0; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --threshold)     THRESHOLD="$2"; shift 2 ;;
    --limit)         LIMIT="$2"; shift 2 ;;
    --fresh)         FRESH=1; shift ;;
    --dry-run)       DRY_RUN=1; shift ;;
    --skip-counts)   SKIP_COUNTS=1; shift ;;
    --skip-unfollow) SKIP_UNFOLLOW=1; shift ;;
    --cookies)       COOKIES=1; shift ;;
    -h|--help)       usage ;;
    *) echo "Unknown option: $1  (try --help)"; exit 1 ;;
  esac
done

step() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }

# Keep a Mac awake while the long steps run (no-op elsewhere).
AWAKE=()
command -v caffeinate >/dev/null 2>&1 && AWAKE=(caffeinate -i)

# ---------------------------------------------------------------- 0. setup
step "0/3  Setting up Python environment"
command -v python3 >/dev/null 2>&1 || { echo "python3 not found. Install Python 3.9+ first."; exit 1; }

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
python -c "import playwright" 2>/dev/null || pip install --quiet playwright
# Chromium for the follower-count step (the unfollow step prefers your installed Google Chrome)
python -m playwright install chromium >/dev/null

for f in following.js follower.js; do
  [[ -f "$f" ]] || { echo "Missing $f — copy it here from your X data export (data/ folder)."; exit 1; }
done

if [[ $FRESH -eq 1 ]]; then
  echo "Clearing results from the previous run..."
  rm -f not_following_back.csv not_following_back.html \
        follower_counts.csv follower_counts_sorted.csv
fi

# ---------------------------------------------------------------- 1. who doesn't follow back
step "1/3  Finding accounts that don't follow you back"
python x_not_following_back.py | grep -E "^(You follow|Your followers|Don't follow|Saved)"

# ---------------------------------------------------------------- 2. follower counts
if [[ $SKIP_COUNTS -eq 1 ]]; then
  step "2/3  Skipping follower counts (--skip-counts)"
  [[ -f follower_counts_sorted.csv ]] || { echo "No follower_counts_sorted.csv yet — run without --skip-counts."; exit 1; }
else
  step "2/3  Looking up follower counts (~6 s per account; resumes if interrupted)"
  ${AWAKE[@]+"${AWAKE[@]}"} python x_follower_counts.py
fi

# ---------------------------------------------------------------- 3. unfollow
if [[ $SKIP_UNFOLLOW -eq 1 ]]; then
  step "3/3  Skipping unfollow (--skip-unfollow)"
  exit 0
fi

UNF_ARGS=(--threshold "$THRESHOLD")
[[ -n "$LIMIT" ]] && UNF_ARGS+=(--limit "$LIMIT")

if [[ $DRY_RUN -eq 1 ]]; then
  step "3/3  Dry run — accounts under $THRESHOLD followers that WOULD be unfollowed"
  python x_unfollow.py "${UNF_ARGS[@]}" --dry-run
  exit 0
fi

[[ $COOKIES -eq 1 ]] && UNF_ARGS+=(--cookies)
step "3/3  Unfollowing accounts under $THRESHOLD followers (~65 s each; you'll confirm first)"
${AWAKE[@]+"${AWAKE[@]}"} python x_unfollow.py "${UNF_ARGS[@]}"

step "Done. Results: unfollow_log.csv"
