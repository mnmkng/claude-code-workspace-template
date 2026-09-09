#!/usr/bin/env bash
# PreToolUse hook for WebFetch: append one JSONL line per fetch to the audit log.
# Never blocks (exit 0 always). Failures are swallowed so a broken log never
# breaks the user's session.
#
# Log location: $HOME/.claude/logs/webfetch-audit.jsonl

set -u

INPUT="$(cat || true)"

LOG_DIR="$HOME/.claude/logs"
LOG_FILE="$LOG_DIR/webfetch-audit.jsonl"

mkdir -p "$LOG_DIR" 2>/dev/null || exit 0

INPUT="$INPUT" LOG_FILE="$LOG_FILE" /usr/bin/python3 - <<'PY' || true
import json, os, datetime

raw = os.environ.get("INPUT", "")
log_file = os.environ["LOG_FILE"]

try:
    payload = json.loads(raw) if raw.strip() else {}
except Exception:
    payload = {"parse_error": True, "raw": raw[:500]}

tool_input = payload.get("tool_input", {}) if isinstance(payload, dict) else {}

entry = {
    "ts": datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z",
    "cwd": os.getcwd(),
    "project": os.environ.get("CLAUDE_PROJECT_DIR", ""),
    "session": os.environ.get("CLAUDE_SESSION_ID", ""),
    "url": tool_input.get("url", ""),
    "prompt": (tool_input.get("prompt") or "")[:200],
}

with open(log_file, "a") as f:
    f.write(json.dumps(entry) + "\n")
PY

exit 0