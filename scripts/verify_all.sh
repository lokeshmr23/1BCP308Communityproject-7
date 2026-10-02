#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# One command that reproduces every verification claim in docs/verification.md.
#
#     bash scripts/verify_all.sh
#
# Options
#   --with-ui     also run the headless-Chrome UI test (needs the server running
#                 and `npm install puppeteer` inside tests/)
#   --port 5000   port the app is (or will be) served on for the UI test
#
# Exit code 0 = everything passed.
# ---------------------------------------------------------------------------
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

WITH_UI=0
PORT="${PORT:-5000}"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --with-ui) WITH_UI=1; shift ;;
    --port) PORT="$2"; shift 2 ;;
    *) echo "unknown option: $1"; exit 2 ;;
  esac
done

PASS=0; FAIL=0
step() { # step <name> <command...>
  local name="$1"; shift
  printf '\n\033[1m== %s ==\033[0m\n' "$name"
  if "$@"; then PASS=$((PASS+1)); printf '   \033[32mPASS\033[0m %s\n' "$name";
  else FAIL=$((FAIL+1)); printf '   \033[31mFAIL\033[0m %s\n' "$name"; fi
}

echo "Crop Advisor — full verification (repo: $REPO_ROOT)"

# ---------------------------------------------------------------- static checks
step "front-end JavaScript syntax (node --check)" bash -c '
  fail=0
  for f in frontend/js/*.js; do node --check "$f" || { echo "  broken: $f"; fail=1; }; done
  exit $fail'

step "bilingual i18n coverage (EN + ಕನ್ನಡ)" node scripts/check_i18n.js

step "dataset artefact integrity (2200 x 22, no missing values)" \
  python3 scripts/download_secondary_dataset.py --check

step "model artefacts consistent and small enough to commit" python3 scripts/check_artifacts.py

# ---------------------------------------------------------------- test suites
step "pytest suite (unit + API + ML contracts + CRUD + feedback loop)" \
  python3 -m pytest -q -p no:cacheprovider

step "pytest slow suite (admin retrain end-to-end into a temp dir)" \
  python3 -m pytest -q -m slow -p no:cacheprovider

# ---------------------------------------------------------------- behavioural checks
step "serving-path sanity benchmark (20 DK field profiles)" \
  python3 scripts/evaluate_predictions.py

if [[ "$WITH_UI" == "1" ]]; then
  step "headless-Chrome UI test (needs the app on :$PORT)" \
    bash -c "BASE=http://localhost:$PORT node tests/ui_smoke.js"
else
  echo -e "\n(skipped) headless-Chrome UI test — re-run with --with-ui while the app is running"
fi

# ---------------------------------------------------------------- summary
printf '\n\033[1m== summary ==\033[0m\n'
printf '  steps passed : %d\n  steps failed : %d\n' "$PASS" "$FAIL"
if [[ "$FAIL" -eq 0 ]]; then
  echo -e "  \033[32mALL VERIFICATION STEPS PASSED\033[0m"
  exit 0
fi
echo -e "  \033[31mSOME STEPS FAILED — see the output above\033[0m"
exit 1
