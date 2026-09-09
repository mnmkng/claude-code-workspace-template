"""install: engineer local CLI setup.

Three idempotent steps (matches the prior scripts/install.sh behavior):

  1. Shell function in ~/.zshrc or ~/.bashrc.  Wraps `claude` so that, when
     invoked inside an workspace tree, it routes through scripts/claude.sh (which
     loads team settings).  Outside the tree, falls through to the system
     `claude`.

  2. User-scope SessionStart hook in ~/.claude/settings.json.  Uses
     status-banner.sh in "user" mode to warn if a session starts inside an
     workspace tree without team settings loaded.

  3. git config core.hooksPath .githooks  — enables the self-healing
     post-checkout hook for this repo.

Run with --check to report what would change without making any changes.
Useful for the post-checkout self-heal: silent on no-op, prints only when
something needs to be repaired.
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

from lib import log
from lib import paths as path_lib

import settings_sync


MARKER_START = "# WORKSPACE-CLAUDE-CODE-START"
MARKER_END = "# WORKSPACE-CLAUDE-CODE-END"

# Legacy markers used by the prior Bash-only install.sh. Detected and stripped
# so re-running install on an old shell rc cleans up automatically.
LEGACY_MARKER_PAIRS = [
    ("# >>> workspace claude wrapper >>>", "# <<< workspace claude wrapper <<<"),
]


def _shell_function_block(kind="posix"):
    """Return the shell function block bracketed by the canonical markers.

    The function walks up from PWD looking for an workspace tree, then dispatches
    to scripts/claude.sh inside it. Outside the tree, falls through to the
    system claude.

    `kind` selects the syntax: "posix" for bash/zsh, "fish" for fish (which
    has its own function syntax and uses $argv instead of "$@").
    """
    header = (
        f"{MARKER_START}\n"
        "# Auto-installed by tools/bootstrap (Claude Code workspace).\n"
        "# Safe to remove the block between these markers to uninstall.\n"
    )
    if kind == "fish":
        body = (
            "function claude\n"
            "    set -l dir $PWD\n"
            '    while test "$dir" != "/"; and test -n "$dir"\n'
            '        if test -f "$dir/.claude/settings.json"; and test -f "$dir/CLAUDE.md"; '
            'and test -d "$dir/departments"; and test -x "$dir/scripts/claude.sh"\n'
            '            "$dir/scripts/claude.sh" $argv\n'
            "            return\n"
            "        end\n"
            '        set dir (dirname "$dir")\n'
            "    end\n"
            "    command claude $argv\n"
            "end\n"
        )
    else:
        body = (
            "claude() {\n"
            '  local dir="$PWD"\n'
            '  while [ "$dir" != "/" ] && [ -n "$dir" ]; do\n'
            '    if [ -f "$dir/.claude/settings.json" ] \\\n'
            '        && [ -f "$dir/CLAUDE.md" ] \\\n'
            '        && [ -d "$dir/departments" ] \\\n'
            '        && [ -x "$dir/scripts/claude.sh" ]; then\n'
            '      "$dir/scripts/claude.sh" "$@"\n'
            "      return\n"
            "    fi\n"
            '    dir="$(dirname "$dir")"\n'
            "  done\n"
            '  command claude "$@"\n'
            "}\n"
        )
    return f"{header}{body}{MARKER_END}\n"


def _detect_shell_rc():
    """Return (rc_path, kind) for the current shell, or (None, None).

    kind is "posix" for bash/zsh or "fish". $SHELL takes priority; otherwise
    fall back to whichever rc file already exists.
    """
    shell = os.environ.get("SHELL", "")
    home = Path.home()
    fish_rc = home / ".config" / "fish" / "config.fish"
    if shell.endswith("/zsh"):
        return home / ".zshrc", "posix"
    if shell.endswith("/bash"):
        return home / ".bashrc", "posix"
    if shell.endswith("/fish"):
        return fish_rc, "fish"
    if (home / ".zshrc").exists():
        return home / ".zshrc", "posix"
    if (home / ".bashrc").exists():
        return home / ".bashrc", "posix"
    if fish_rc.exists():
        return fish_rc, "fish"
    return None, None


def _strip_block(text, start_marker, end_marker):
    """Remove the first inclusive block between start_marker and end_marker.

    Returns (new_text, removed_bool).
    """
    pattern = re.compile(
        r"(?:^|\n)" + re.escape(start_marker) + r".*?" + re.escape(end_marker) + r"[^\n]*\n?",
        re.DOTALL,
    )
    new_text, n = pattern.subn("\n", text, count=1)
    if n == 0:
        return text, False
    # Collapse the leading newline we kept as a separator if the file now
    # starts with one.
    if new_text.startswith("\n"):
        new_text = new_text[1:]
    return new_text, True


def _ensure_block(text, start_marker, end_marker, desired_block):
    """Replace or append the marker-bracketed block; idempotent on identical content."""
    pattern = re.compile(
        re.escape(start_marker) + r".*?" + re.escape(end_marker) + r"[^\n]*\n?",
        re.DOTALL,
    )
    match = pattern.search(text)
    if match:
        if match.group(0) == desired_block:
            return text, False
        new_text = text[:match.start()] + desired_block + text[match.end():]
        return new_text, True
    # Append.
    if text and not text.endswith("\n"):
        text += "\n"
    if text and not text.endswith("\n\n"):
        text += "\n"
    return text + desired_block, True


def _install_shell_function(check_mode):
    rc, kind = _detect_shell_rc()
    if rc is None:
        log.warn(
            "No ~/.zshrc, ~/.bashrc, or ~/.config/fish/config.fish found. "
            "Skipping shell function. If you use a different shell, set up a "
            "manual wrapper."
        )
        return False

    if not check_mode:
        rc.parent.mkdir(parents=True, exist_ok=True)
        rc.touch(exist_ok=True)
        text = rc.read_text()
    else:
        text = rc.read_text() if rc.exists() else ""

    legacy_removed = False
    for ls, le in LEGACY_MARKER_PAIRS:
        text, did = _strip_block(text, ls, le)
        legacy_removed = legacy_removed or did

    had_modern_block = MARKER_START in text
    desired = _shell_function_block(kind)
    new_text, block_changed = _ensure_block(text, MARKER_START, MARKER_END, desired)

    if not block_changed and not legacy_removed:
        return False

    if check_mode:
        log.change(f"shell function: would update {rc}")
        return True

    rc.write_text(new_text)
    if had_modern_block:
        log.change(f"shell function: updated in {rc}")
    elif legacy_removed:
        log.change(f"shell function: migrated legacy markers in {rc}")
    else:
        log.change(f"shell function: installed in {rc}")
    return True


def _install_user_settings(workspace_root, check_mode):
    """Merge user-scope SessionStart hook into ~/.claude/settings.json."""
    user_settings = Path.home() / ".claude" / "settings.json"
    hook_command = f"{workspace_root}/.claude/hooks/status-banner.sh user"
    desired_entry = {
        "matcher": "startup|resume|clear|compact",
        "hooks": [
            {"type": "command", "command": hook_command}
        ],
    }

    if user_settings.is_file():
        try:
            settings = json.loads(user_settings.read_text())
        except json.JSONDecodeError:
            log.warn(f"{user_settings} is not valid JSON; rewriting with an empty base.")
            settings = {}
    else:
        settings = {}

    hooks = settings.setdefault("hooks", {})
    sessionstart = hooks.setdefault("SessionStart", [])

    def is_ours(entry):
        if not isinstance(entry, dict):
            return False
        for h in entry.get("hooks", []) or []:
            if not isinstance(h, dict):
                continue
            cmd = h.get("command", "")
            # Match both the legacy script and the canonical one.
            if "/scripts/check-team-settings.sh" in cmd:
                return True
            if "/.claude/hooks/status-banner.sh" in cmd:
                return True
        return False

    ours = [e for e in sessionstart if is_ours(e)]
    others = [e for e in sessionstart if not is_ours(e)]

    if len(ours) == 1 and ours[0] == desired_entry:
        return False

    hooks["SessionStart"] = others + [desired_entry]

    if check_mode:
        log.change(f"user settings: would update {user_settings}")
    else:
        user_settings.parent.mkdir(parents=True, exist_ok=True)
        user_settings.write_text(json.dumps(settings, indent=2) + "\n")
        log.change(f"user settings: installed SessionStart hook in {user_settings}")
    return True


def _install_git_hooks(workspace_root, check_mode):
    try:
        result = subprocess.run(
            ["git", "-C", str(workspace_root), "config", "--local", "--get", "core.hooksPath"],
            capture_output=True, text=True, check=False,
        )
    except FileNotFoundError:
        log.warn("git not found on PATH. Skipping core.hooksPath setup.")
        return False
    current = result.stdout.strip()
    if current == ".githooks":
        return False
    if check_mode:
        current_repr = repr(current) if current else "<unset>"
        log.change(
            f"git hooks path: would set to .githooks (currently {current_repr})"
        )
    else:
        subprocess.run(
            ["git", "-C", str(workspace_root), "config", "core.hooksPath", ".githooks"],
            check=True,
        )
        log.change("git hooks path: set to .githooks")
    return True


def _report_team_stamp_drift(workspace_root):
    """Surface team-folder policy drift (issue #141); never writes.

    The stamped team `.claude/settings.json` copies are tracked files owned by
    the settings-sync generator and changed via reviewed PRs - not per-machine
    state - so install (and the post-checkout self-heal that runs it with
    --check) only reports drift and points at the fix. Silent when everything
    is in sync, and silent when git can't enumerate targets (nothing to verify
    locally there).
    """
    try:
        settings_sync.target_folders(workspace_root)
    except SystemExit:
        return False
    try:
        issues, _ = settings_sync.findings(workspace_root)
    except SystemExit as e:
        # Enumeration works, so this is a real finding (e.g. a stamp the
        # .gitignore allowlist would silently drop).
        log.warn(f"team-folder settings: {e}")
        return True
    if not issues:
        return False
    kinds = ", ".join(sorted({k for k, _ in issues}))
    log.change(
        f"team-folder settings: {len(issues)} issue(s) ({kinds}) - run "
        "`python3 tools/bootstrap/bootstrap.py settings-sync` and commit the "
        "result via a PR"
    )
    return True


def run(args):
    check_mode = bool(getattr(args, "check", False))
    workspace_root = path_lib.require_workspace_root()

    if not check_mode:
        log.step(f"Installing Claude Code workspace setup ({workspace_root})")

    any_changed = False
    any_changed |= _install_shell_function(check_mode)
    any_changed |= _install_user_settings(workspace_root, check_mode)
    any_changed |= _install_git_hooks(workspace_root, check_mode)
    _report_team_stamp_drift(workspace_root)

    if check_mode:
        # Silent on no-op so the post-checkout hook doesn't spam.
        return 0

    print()
    if not any_changed:
        log.ok("Setup already complete; no changes needed.")
    else:
        log.ok("Setup complete.")
        rc, _ = _detect_shell_rc()
        if rc:
            log.info(f"  Restart your shell, or run: source {rc}")
    return 0
