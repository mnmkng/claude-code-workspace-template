#!/usr/bin/env bash
# Wrapper called by the shell function `claude()` installed by install.sh.
# Detects the workspace root by walking up from $PWD, then invokes `command claude`
# with the team settings file explicitly loaded and workspace root added as a
# writeable directory. Preserves original cwd so subfolder CLAUDE.md loads.
#
# Safe to invoke directly (`./scripts/claude.sh`) if the shell function is not
# installed.

set -euo pipefail

# Walk up from current directory to find an workspace root.
# Markers: settings.json + CLAUDE.md + departments/ — all three required to
# avoid false positives on unrelated repos.
find_workspace_root() {
  local dir
  dir="$(pwd)"
  while [ "$dir" != "/" ] && [ -n "$dir" ]; do
    if [ -f "$dir/.claude/settings.json" ] \
        && [ -f "$dir/CLAUDE.md" ] \
        && [ -d "$dir/departments" ]; then
      printf '%s\n' "$dir"
      return 0
    fi
    dir="$(dirname "$dir")"
  done
  return 1
}

ROOT="$(find_workspace_root)" || {
  # Not in an workspace tree — pass through to system claude.
  exec command claude "$@"
}

# Export so the team SessionStart hook in settings.json can reference the
# workspace root without depending on $CLAUDE_PROJECT_DIR, which Claude Code
# sets to the session cwd (the user's subfolder) — not to the directory
# containing the active settings.json.
export CLAUDE_WORKSPACE_ROOT="$ROOT"

exec command claude \
  --settings "$ROOT/.claude/settings.json" \
  --add-dir "$ROOT" \
  "$@"