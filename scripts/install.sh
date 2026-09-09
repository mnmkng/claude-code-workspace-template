#!/usr/bin/env bash
# Apify Claude Code workspace bootstrap (Bash shim).
#
# Self-locating: works no matter the cwd. Cloud setup-script cwd is /home/user,
# not the repo root — the previous `cd "$(dirname "$0")/.."` form fails when
# invoked as `bash scripts/install.sh` from /home/user because there's no
# `scripts/` directory there. BASH_SOURCE + `cd -P` resolves the script's own
# absolute directory regardless of invocation style.
#
# Delegates to tools/bootstrap/bootstrap.py which auto-dispatches by
# CLAUDE_CODE_REMOTE.
#
# Usage:
#   bash scripts/install.sh                           # auto-dispatch by env
#   bash scripts/install.sh --check                   # local install dry-run
#   bash scripts/install.sh compose --team content    # explicit subcommand
#   bash scripts/install.sh cloud --compose-only      # cloud setup-script tier
#
# Re-runnable any time; the Python tool is idempotent.

set -e

SOURCE="${BASH_SOURCE[0]:-$0}"
while [ -L "$SOURCE" ]; do
  DIR="$(cd -P "$(dirname "$SOURCE")" >/dev/null 2>&1 && pwd)"
  SOURCE="$(readlink "$SOURCE")"
  [[ "$SOURCE" != /* ]] && SOURCE="$DIR/$SOURCE"
done
SCRIPT_DIR="$(cd -P "$(dirname "$SOURCE")" >/dev/null 2>&1 && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

if ! command -v python3 >/dev/null 2>&1; then
  echo "Error: python3 not found." >&2
  echo "  Install with: brew install python3 (macOS) | apt install python3 (Linux)" >&2
  exit 1
fi
exec python3 "$ROOT/tools/bootstrap/bootstrap.py" "$@"