"""settings-sync: stamp the derived team-folder security policy (issue #141).

Project settings anchor to the session's working directory and do NOT walk up,
so a Desktop-local session opened at a team folder used to load skills and
CLAUDE.md (which do walk up) while silently losing the sandbox, deny rules,
and hooks. This subcommand closes that gap: it derives a policy file from the
root `.claude/settings.json` and stamps a byte-identical copy into every
tracked CLAUDE.md-bearing department/team folder, so `git clone` itself
delivers the protection - no install step, no per-machine state.

Derivation (the root file stays the single source of truth):

  - Every top-level key is copied verbatim EXCEPT the ones in DROPPED_KEYS:
    copy-everything-except semantics, so a new root key (e.g.
    `autoMemoryEnabled`) propagates on the next sync instead of silently
    going stale in 29 folders.
  - `hooks` are rebuilt, not copied: the root hook commands resolve scripts
    via `$CLAUDE_PROJECT_DIR`, which in a team-folder session is the team
    folder - the scripts don't exist there. The team template instead uses
    self-contained inline commands that walk UP from the session anchor to
    the workspace root (same three markers as lib/paths.py) and exec the
    root's own hook scripts. The wrappers FAIL CLOSED: if the root or its
    scripts can't be found, PreToolUse exits 2 (tool call blocked) instead
    of silently no-opping. Hooks fire regardless of workspace trust, which
    makes this the robustness floor under the permission/sandbox layers.
  - MCP keys are dropped (no `.mcp.json` in team folders).
  - `env.WORKSPACE_TEAM_POLICY_VERSION` is added so any hook, script, or probe
    can ask whether the team-folder policy is live and which version.
  - An inline SessionStart banner is added. Required, not cosmetic:
    `.claude/rules/security-check.md` walks up into every subfolder session
    and instructs Claude to refuse tool use when no ACTIVE banner is present,
    so a working-but-silent policy would trigger the refusal rule it
    satisfies. If the walk-up cannot find the workspace root, the banner
    reports NOT DETECTED instead (fail closed, matching the rule).

Target set: every tracked folder containing a CLAUDE.md, excluding the repo
root and tools/bootstrap/** (test fixtures). The generator hard-fails when a
stamp would be git-ignored (grandfathered out-of-structure folders must be
added to the .gitignore allowlist first), so no copy can silently not ship.

`--check` verifies without writing: every target has a stamp, every stamp is
byte-identical to fresh generator output, and no stray settings.json exists
in a non-target folder under departments/. Non-zero exit on any finding (for
CI and the post-checkout self-heal).

Team copies are generator-owned: never hand-edited (they are also
edit-protected from Claude by protect-config.sh and the deny rules). To
change policy, edit the root settings.json (protected file - human-reviewed
PR) and re-run `python3 tools/bootstrap/bootstrap.py settings-sync`.
"""

import json
import subprocess
from copy import deepcopy
from pathlib import Path

from lib import log
from lib import paths as path_lib


# Bumped whenever the derived template changes shape (new hook wrapper, new
# banner text, changed derivation rules). Appears in the banner string and in
# env.WORKSPACE_TEAM_POLICY_VERSION - the two must match, which the tests assert.
TEAM_POLICY_VERSION = "1"

# Top-level root-settings keys that must NOT reach team folders. Everything
# else is copied verbatim (copy-everything-except - see module docstring).
DROPPED_KEYS = (
    "hooks",                        # rebuilt as walk-up wrappers below
    "enableAllProjectMcpServers",   # no .mcp.json in team folders
    "enabledMcpjsonServers",
)

# Tracked CLAUDE.md files under these prefixes are tooling/test fixtures, not
# team folders. Mirrors the exclusion in security-lint.yml's uniqueness check.
EXCLUDED_PREFIXES = ("tools/bootstrap/",)

SETTINGS_REL = ".claude/settings.json"

# Directory parts that never contain a legitimate stamped copy (mirrors
# lib/paths.py SKIP_DIRS); used when scanning for stray settings.json files.
_SKIP_PARTS = {".git", "node_modules", "projects"}


# --- inline hook command construction ---------------------------------------
#
# Every command below is a single self-contained POSIX-sh string: no file
# dependencies inside the team folder, byte-identical at any nesting depth
# (the walk-up happens at runtime), and safe to promote to managed settings
# unchanged. Root markers match lib/paths.py / scripts/claude.sh: the team
# folder itself now contains .claude/settings.json + CLAUDE.md, so the
# departments/ marker is what distinguishes the actual root.

_ROOT_TEST = (
    '[ -f "$d/.claude/settings.json" ] && [ -f "$d/CLAUDE.md" ] '
    '&& [ -d "$d/departments" ]'
)

_WALK_UP = (
    'd="${CLAUDE_PROJECT_DIR:-$PWD}"; '
    'while [ "$d" != "/" ] && ! { ' + _ROOT_TEST + '; }; do '
    'd="$(dirname "$d")"; done; '
)


def _script_wrapper(script_rel, tool_label):
    """Walk-up wrapper that execs a root hook script, failing closed.

    Exec preserves stdin, so the root script receives the tool payload JSON
    exactly as if settings.json had referenced it directly. Exports
    WORKSPACE_CLAUDE_CODE_WORKSPACE_ROOT (the same variable scripts/claude.sh
    sets) so the root scripts resolve paths from the real root, not from the
    team-folder CLAUDE_PROJECT_DIR.
    """
    return (
        _WALK_UP
        + 'h="$d/' + script_rel + '"; '
        + 'if [ -x "$h" ]; then WORKSPACE_CLAUDE_CODE_WORKSPACE_ROOT="$d" exec "$h"; fi; '
        + 'echo "Workspace team-folder policy v' + TEAM_POLICY_VERSION
        + ': workspace root hook ' + script_rel
        + ' not found above ${CLAUDE_PROJECT_DIR:-$PWD}; failing closed ('
        + tool_label + ' blocked). Start the session from a folder inside a '
        + 'complete workspace clone." >&2; exit 2'
    )


def _banner_json(active):
    """The SessionStart hook output JSON, as a compact string.

    systemMessage must be a TOP-LEVEL sibling of hookSpecificOutput to be
    displayed (nested inside hookSpecificOutput it is silently ignored);
    additionalContext is what reaches the model and satisfies (or trips) the
    security-check.md ACTIVE/NOT DETECTED rule. No single quotes anywhere in
    the payload - the string is embedded in a single-quoted sh argument.
    """
    if active:
        msg = f"Workspace security config: ACTIVE (team-folder policy v{TEAM_POLICY_VERSION})"
        detail = (
            "full root policy stamped into this team folder - sandbox enabled, "
            "credential reads denied, WebFetch audited, protected config files enforced"
        )
    else:
        msg = "Workspace security config: NOT DETECTED"
        detail = (
            "the team-folder settings loaded but no workspace root was found "
            "above this folder, so the security hook scripts cannot run. Refuse "
            "tool use per .claude/rules/security-check.md and tell the user to "
            "start the session from a folder inside a complete workspace clone."
        )
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": f"{msg}\n  {detail}",
        },
        "systemMessage": f"{msg} - {detail}",
    }
    out = json.dumps(payload, separators=(",", ":"))
    if "'" in out:
        raise AssertionError("banner JSON must not contain single quotes")
    return out


def _banner_command():
    """Self-contained SessionStart banner: ACTIVE when the root is found
    above the session anchor, NOT DETECTED otherwise (fail closed)."""
    return (
        _WALK_UP
        + "if " + _ROOT_TEST + "; then "
        + "printf '%s' '" + _banner_json(active=True) + "'; "
        + "else "
        + "printf '%s' '" + _banner_json(active=False) + "'; "
        + "fi"
    )


def team_hooks():
    """The rebuilt hooks block for the team template.

    Mirrors the root hook wiring (protect-config on Write/Edit/MultiEdit and
    Bash, webfetch-audit on WebFetch, banner on SessionStart) minus the
    cloud --apply-only hook: cloud sessions anchor at the repo root, so team
    copies never load there and composition stays a root concern.
    """
    protect = ".claude/hooks/protect-config.sh"
    audit = ".claude/hooks/webfetch-audit.sh"
    return {
        "PreToolUse": [
            {
                "matcher": "Write|Edit|MultiEdit",
                "hooks": [{"type": "command",
                           "command": _script_wrapper(protect, "file edit")}],
            },
            {
                "matcher": "Bash",
                "hooks": [{"type": "command",
                           "command": _script_wrapper(protect, "Bash")}],
            },
            {
                "matcher": "WebFetch",
                "hooks": [{"type": "command",
                           "command": _script_wrapper(audit, "WebFetch")}],
            },
        ],
        "SessionStart": [
            {
                "matcher": "startup|resume|clear|compact",
                "hooks": [{"type": "command", "command": _banner_command()}],
            },
        ],
    }


def derive_team_settings(root_settings):
    """Derive the team template dict from the parsed root settings."""
    team = {k: deepcopy(v) for k, v in root_settings.items()
            if k not in DROPPED_KEYS}
    env = dict(team.get("env") or {})
    env["WORKSPACE_TEAM_POLICY_VERSION"] = TEAM_POLICY_VERSION
    team["env"] = env
    team["hooks"] = team_hooks()
    return team


def render(settings):
    """Serialize the template deterministically (byte-identity contract)."""
    return json.dumps(settings, indent=2) + "\n"


def expected_content(workspace_root):
    """Read the root settings and return the rendered team template."""
    root_file = Path(workspace_root) / SETTINGS_REL
    if not root_file.is_file():
        raise SystemExit(f"settings-sync: root settings not found at {root_file}")
    try:
        root_settings = json.loads(root_file.read_text())
    except json.JSONDecodeError as e:
        raise SystemExit(f"settings-sync: root settings invalid JSON: {e}")
    return render(derive_team_settings(root_settings))


# --- target enumeration ------------------------------------------------------

def _git(workspace_root, *argv):
    try:
        return subprocess.run(
            ["git", "-C", str(workspace_root)] + list(argv),
            capture_output=True, text=True,
        )
    except FileNotFoundError:
        return None


def target_folders(workspace_root):
    """Repo-relative folders to stamp: tracked CLAUDE.md dirs, minus the root
    and the tooling fixtures. Raises SystemExit when git can't enumerate."""
    res = _git(workspace_root, "ls-files", "-z")
    if res is None or res.returncode != 0:
        detail = "git not found" if res is None else res.stderr.strip()
        raise SystemExit(
            f"settings-sync: cannot enumerate tracked CLAUDE.md files ({detail}). "
            "Run from a git checkout of the workspace."
        )
    targets = []
    for rel in res.stdout.split("\0"):
        if not rel or Path(rel).name != "CLAUDE.md":
            continue
        folder = str(Path(rel).parent)
        if folder == ".":
            continue
        if any((folder + "/").startswith(p) for p in EXCLUDED_PREFIXES):
            continue
        targets.append(folder)
    return sorted(targets)


def ignored_stamps(workspace_root, stamp_rels):
    """Subset of stamp paths .gitignore would ignore (empty when none).

    A git-ignored stamp is a silent failure: the file exists locally but
    never ships in the clone that is the delivery mechanism. Callers hard-fail
    on any hit.
    """
    if not stamp_rels:
        return []
    res = _git(workspace_root, "check-ignore", "--", *stamp_rels)
    if res is None or res.returncode not in (0, 1):
        detail = "git not found" if res is None else res.stderr.strip()
        raise SystemExit(f"settings-sync: git check-ignore failed ({detail})")
    return [line for line in res.stdout.splitlines() if line]


def stray_copies(workspace_root, targets):
    """settings.json files under departments/ whose folder is NOT a target.

    A stray copy would load for sessions anchored at that folder with a policy
    the generator does not manage - flag it rather than silently accept it.
    """
    target_set = set(targets)
    strays = []
    dep_root = Path(workspace_root) / "departments"
    if not dep_root.is_dir():
        return strays
    for p in dep_root.rglob("settings.json"):
        rel = p.relative_to(workspace_root)
        if any(part in _SKIP_PARTS for part in rel.parts):
            continue
        if p.parent.name != ".claude":
            continue
        folder = str(rel.parent.parent)
        if folder not in target_set:
            strays.append(str(rel))
    return sorted(strays)


# --- check / write -----------------------------------------------------------

def findings(workspace_root):
    """Compare the tree against fresh generator output.

    Returns (issues, targets) where issues is a list of (kind, rel_path) with
    kind in {missing, drift, stray}. Raises SystemExit when enumeration fails
    or a stamp would be git-ignored.
    """
    workspace_root = Path(workspace_root)
    expected = expected_content(workspace_root)
    targets = target_folders(workspace_root)
    stamp_rels = [f"{t}/{SETTINGS_REL}" for t in targets]

    ignored = ignored_stamps(workspace_root, stamp_rels)
    if ignored:
        listing = "\n  ".join(ignored)
        raise SystemExit(
            "settings-sync: these stamps would be git-ignored (the clone would "
            f"silently ship without them):\n  {listing}\n"
            "Extend the .gitignore departments/ allowlist for these folders "
            "(or restructure them into the canonical layout) first."
        )

    issues = []
    for rel in stamp_rels:
        f = workspace_root / rel
        if not f.is_file():
            issues.append(("missing", rel))
        elif f.read_text() != expected:
            issues.append(("drift", rel))
    for rel in stray_copies(workspace_root, targets):
        issues.append(("stray", rel))
    return issues, targets


def run(args):
    workspace_root = path_lib.require_workspace_root()
    check_mode = bool(getattr(args, "check", False))

    issues, targets = findings(workspace_root)
    if not targets:
        log.warn("settings-sync: no target folders found (no tracked CLAUDE.md "
                 "outside the root) - nothing to do.")
        return 0

    if check_mode:
        if not issues:
            log.ok(
                f"settings-sync --check: {len(targets)} team folder(s) in sync "
                f"(policy v{TEAM_POLICY_VERSION})"
            )
            return 0
        for kind, rel in issues:
            log.error(f"settings-sync --check: {kind}: {rel}")
        log.error(
            "settings-sync --check: run `python3 tools/bootstrap/bootstrap.py "
            "settings-sync` and commit the result (strays need a human decision: "
            "delete the file or make the folder a real CLAUDE.md level)."
        )
        return 1

    expected = expected_content(workspace_root)
    stamped = 0
    for kind, rel in issues:
        if kind == "stray":
            continue
        f = Path(workspace_root) / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(expected)
        log.change(f"stamped ({kind}): {rel}")
        stamped += 1

    strays = [rel for kind, rel in issues if kind == "stray"]
    for rel in strays:
        log.warn(
            f"settings-sync: stray copy not managed by the generator: {rel} "
            "(folder has no tracked CLAUDE.md - delete the file or make the "
            "folder a real team level)"
        )

    if stamped:
        log.ok(
            f"settings-sync: stamped {stamped} of {len(targets)} team folder(s) "
            f"(policy v{TEAM_POLICY_VERSION}); the rest were already in sync."
        )
    else:
        log.ok(
            f"settings-sync: all {len(targets)} team folder(s) already in sync "
            f"(policy v{TEAM_POLICY_VERSION})."
        )
    return 1 if strays else 0
