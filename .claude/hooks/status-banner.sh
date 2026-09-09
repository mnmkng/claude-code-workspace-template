#!/usr/bin/env bash
# Unified SessionStart hook. Same script fires from two scopes:
#
#   team mode (referenced by Apify/.claude/settings.json):
#     Runs whenever team settings are loaded.
#       - Local CLI  : emits ACTIVE (settings path).
#       - Cloud      : emits ACTIVE (cloud, team=NAME) when the bootstrap
#                      manifest is present; emits NOT DETECTED when running in
#                      cloud (CLAUDE_CODE_REMOTE=true) with no manifest, i.e.
#                      the setup script never composed the team artifacts.
#
#   user mode (installed into ~/.claude/settings.json by scripts/install.sh):
#     Runs on every session. Inside an Apify tree with team settings loaded,
#     stays silent (team hook handles ACTIVE). Also silent when the session is
#     anchored at a stamped department/team folder, whose own settings.json
#     emits the team-folder banner (issue #141). Inside an Apify tree without
#     any of those - or in a cloud session with no bootstrap manifest - emits
#     NOT DETECTED, the canonical string the rule in
#     .claude/rules/security-check.md keys off of. Outside any Apify tree,
#     silent.
#
# Usage: status-banner.sh [team|user]  (defaults to user)

set -u

MODE="${1:-user}"

# Find the Apify root. Walk up from cwd looking for the three markers:
# .claude/settings.json + CLAUDE.md + departments/. Defensive — each hook
# invocation verifies for itself rather than trusting env vars.
find_apify_root() {
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

APIFY_ROOT="$(find_apify_root || true)"
PROJECT_DIR="${CLAUDE_PROJECT_DIR:-}"

# Read team_input from the bootstrap manifest; prints "?" on any problem.
manifest_team() {
  /usr/bin/python3 -c '
import json, sys
try:
    print(json.load(open(sys.argv[1])).get("team_input") or "?")
except Exception:
    print("?")
' "$1" 2>/dev/null || printf '?'
}

emit() {
  local msg="$1" detail="$2"
  # systemMessage must be a TOP-LEVEL sibling of hookSpecificOutput to be shown
  # to the user; nested inside hookSpecificOutput it is ignored for display, and
  # additionalContext only reaches the model (confirmed against the Claude Code
  # hooks output schema). additionalContext still feeds the model so the
  # security-check.md NOT-DETECTED rule keeps working.
  /usr/bin/python3 -c '
import json, sys
msg, detail = sys.argv[1], sys.argv[2]
print(json.dumps({
  "hookSpecificOutput": {
    "hookEventName": "SessionStart",
    "additionalContext": f"{msg}\n  {detail}"
  },
  "systemMessage": f"{msg} - {detail}"
}))
' "$msg" "$detail"
}

ACTIVE_DETAIL="sandbox enabled, credential reads denied, WebFetch audited, protected config files enforced"

case "$MODE" in
  team)
    ROOT="${APIFY_ROOT:-$PROJECT_DIR}"

    # Cloud: the bootstrap manifest is the signal that the setup script ran and
    # composed the team artifacts. CLAUDE_CODE_REMOTE=true is set by cloud
    # sessions. No manifest in cloud means the security/composition setup did
    # not happen, so surface NOT DETECTED to trigger the security-check.md rule.
    if [ "${CLAUDE_CODE_REMOTE:-}" = "true" ]; then
      MANIFEST="$ROOT/.claude/.bootstrap-manifest.json"
      if [ -f "$MANIFEST" ]; then
        emit \
          "Apify team security config: ACTIVE (cloud, team=$(manifest_team "$MANIFEST"))" \
          "$ACTIVE_DETAIL"
      else
        emit \
          "Apify team security config: NOT DETECTED" \
          "cloud session (CLAUDE_CODE_REMOTE=true) but no bootstrap manifest at $MANIFEST. The setup script ('bash Apify/scripts/install.sh') did not run or failed, so team artifacts are not composed. Recreate the cloud environment or re-run its setup script."
      fi
      exit 0
    fi

    # Local CLI: the team hook only fires when the team settings.json loaded in
    # this session, so we emit ACTIVE. If we can't locate the root (cwd outside
    # Apify), fall back to whatever we can describe.
    emit \
      "Apify team security config: ACTIVE ($ROOT/.claude/settings.json)" \
      "$ACTIVE_DETAIL"
    ;;

  user)
    # Not inside an Apify tree — nothing to say.
    [ -z "$APIFY_ROOT" ] && exit 0

    # Cloud safety: a cloud session with no bootstrap manifest means the setup
    # never ran. Surface NOT DETECTED even if it's a stray user-scope hook that
    # fired (the team hook normally handles cloud, but don't rely on ordering).
    if [ "${CLAUDE_CODE_REMOTE:-}" = "true" ] \
        && [ ! -f "$APIFY_ROOT/.claude/.bootstrap-manifest.json" ]; then
      emit \
        "Apify team security config: NOT DETECTED" \
        "cloud session (CLAUDE_CODE_REMOTE=true) without a bootstrap manifest at $APIFY_ROOT/.claude/.bootstrap-manifest.json; the setup script did not run."
      exit 0
    fi

    # Inside an Apify tree. If team settings loaded correctly,
    # CLAUDE_PROJECT_DIR will match the Apify root (desktop app), OR the
    # session was launched via scripts/claude.sh which sets
    # APIFY_CLAUDE_CODE_WORKSPACE_ROOT. Either way, stay silent — the team
    # hook emits ACTIVE for those cases.
    if [ "$PROJECT_DIR" = "$APIFY_ROOT" ] \
        || [ "${APIFY_CLAUDE_CODE_WORKSPACE_ROOT:-}" = "$APIFY_ROOT" ]; then
      exit 0
    fi

    # Team-folder policy (issue #141): a session anchored at a stamped
    # department/team folder loads that folder's generated settings.json,
    # whose inline SessionStart hook emits its own ACTIVE (or NOT DETECTED)
    # banner. Stay silent so this user-scope hook does not contradict it.
    if [ -n "$PROJECT_DIR" ] && [ "$PROJECT_DIR" != "$APIFY_ROOT" ] \
        && [ -f "$PROJECT_DIR/.claude/settings.json" ]; then
      exit 0
    fi

    # Inside Apify but team settings did NOT load.
    emit \
      "Apify team security config: NOT DETECTED" \
      "cwd: $(pwd); Apify root: $APIFY_ROOT; CLAUDE_PROJECT_DIR: ${PROJECT_DIR:-<unset>}. Restart via the 'claude' shell function, or run $APIFY_ROOT/scripts/claude.sh."
    ;;

  *)
    exit 0
    ;;
esac

exit 0