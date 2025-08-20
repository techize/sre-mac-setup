#!/usr/bin/env bash
set -euo pipefail

# Nightly Bitbucket repo sync wrapper
# - Sources credentials from ~/.bitbucket_env
# - Ensures venv and dependencies
# - Runs sync/report; optionally emails report if MAIL_TO is set

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV="$REPO_ROOT/.venv"

# Defaults (override via env)
: "${DEST:=$HOME/repos}"
: "${PROJECTS:=DEVOPS}"

# Optional: path to env file with BB_WORKSPACE, BITBUCKET_USERNAME, BITBUCKET_API_TOKEN
: "${BITBUCKET_ENV_FILE:=$HOME/.bitbucket_env}"

if [[ -f "$BITBUCKET_ENV_FILE" ]]; then
  # shellcheck disable=SC1090
  source "$BITBUCKET_ENV_FILE"
fi

missing=()
[[ -z "${BB_WORKSPACE:-}" ]] && missing+=(BB_WORKSPACE)
[[ -z "${BITBUCKET_USERNAME:-}" ]] && missing+=(BITBUCKET_USERNAME)
[[ -z "${BITBUCKET_API_TOKEN:-}" ]] && missing+=(BITBUCKET_API_TOKEN)
if (( ${#missing[@]} > 0 )); then
  echo "Missing required env vars: ${missing[*]}" >&2
  echo "Set them in $BITBUCKET_ENV_FILE or the environment before running." >&2
  exit 2
fi

# Bootstrap venv if needed
if [[ ! -d "$VENV" ]]; then
  python3 -m venv "$VENV"
fi
# shellcheck disable=SC1090
source "$VENV/bin/activate"
pip -q install -r "$SCRIPT_DIR/requirements.txt"

CMD=(python "$SCRIPT_DIR/clone_bitbucket_projects.py" --projects "$PROJECTS" --dest "$DEST" --sync-default --report text)

# Allow DRY_RUN=1 to pass through to the script
if [[ "${DRY_RUN:-0}" == "1" ]]; then
  CMD+=(--dry-run)
fi

export BB_WORKSPACE BITBUCKET_USERNAME BITBUCKET_API_TOKEN

REPORT=
if REPORT=$("${CMD[@]}"); then
  :
else
  # Preserve non-zero output for email
  REPORT="$REPORT"
fi

# Save to daily log
LOG_DIR="$HOME/Library/Logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/repo-sync-$(date +%F).log"
{
  echo "=== $(date -u) ==="
  echo "$REPORT"
  echo
} >> "$LOG_FILE"

# Optional email if MAIL_TO is set and mail command is available
if [[ -n "${MAIL_TO:-}" ]] && command -v mail >/dev/null 2>&1; then
  printf "%s\n" "$REPORT" | mail -s "Bitbucket repo sync report" "$MAIL_TO"
else
  # Fallback to stdout so cron captures it
  printf "%s\n" "$REPORT"
fi
