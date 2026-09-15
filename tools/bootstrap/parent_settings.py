"""parent-settings: the derived security policy for multi-repo cloud sessions (#195).

A cloud session created with more than one repository clones them as siblings
under `/home/user/` and anchors the project root at that parent directory.
Claude Code reads project settings only from the primary working directory,
so neither repo's `.claude/settings.json` loads there: no sandbox block, no
deny rules, no hooks, no bootstrap apply tier, and no ACTIVE banner. A
settings file at the parent itself does load (verified in #195), and files
written outside the repos at setup time survive in the environment snapshot
across sessions.

This module derives a policy file from the root `.claude/settings.json` and
writes it to `<parent>/.claude/settings.json`. It is generator-owned, the
same way the team-folder stamps from settings-sync are. Contract:

  - Written unconditionally by the cloud setup tier and refreshed by the
    per-session apply tier. Repository selection is per session, not per
    environment, and every session in an environment shares the setup
    snapshot, so the file must be correct whatever the next session attaches.
    In a single-repo session the project root is the workspace itself and the
    parent file is inert; in a multi-repo session it is the only policy that
    loads.
  - Rendered from the root settings on `origin/main` whenever git can reach
    it, fetched first because a cloud clone carries only the session branch.
    Git can authenticate only inside a live session (the platform proxy
    injects GitHub auth there; the setup tier has none, verified in #197),
    so the setup tier seeds from the WORKING TREE with the source stamped
    into the file, and every in-session apply run re-renders from
    origin/main. The file outlives the session that wrote it, so whichever
    branch last rendered it would otherwise govern every following session;
    converging to the reviewed branch at every session start, never
    downgrading a reviewed rendering, and flagging a working-tree seed in
    doctor/--check bounds that persistence vector to the window before the
    first in-session apply run. A single-repo session on a feature branch
    still loads that branch's own settings directly.
  - Copy-everything-except derivation (parity with settings-sync): every
    top-level key is copied verbatim except `hooks` (rebuilt) and the MCP keys
    (the parent has no `.mcp.json`).
  - `hooks` are rebuilt with the workspace clone's absolute path pinned in
    every command. `$CLAUDE_PROJECT_DIR` is the parent directory in this
    layout, so the root template's `${CLAUDE_WORKSPACE_ROOT:-
    $CLAUDE_PROJECT_DIR}` resolution cannot work. The wrappers FAIL CLOSED:
    when the workspace clone is not attached to the session, the PreToolUse
    wrappers block file edits, Bash, and WebFetch (exit 2), the deny rules in
    the same file still apply, and the SessionStart banner reports NOT
    DETECTED so Claude refuses tool use per security-check.md. Read, Glob,
    Grep, and MCP tools have no wrapper, same as the team-folder stamps. A
    workspace environment is for workspace work; a session in it without the
    workspace attached is a misconfiguration, not a use case.
  - Destination guards: the subcommand is cloud-only, the parent may never
    be the home directory (that would be `~/.claude/settings.json`), and an
    existing file without this generator's marker is never overwritten.
  - `env.CLAUDE_WORKSPACE_ROOT` is set to the clone path (the
    same variable scripts/claude.sh exports) and
    `env.WORKSPACE_PARENT_POLICY_VERSION` marks the policy as live.

The parent file is already covered by the existing protections: the deny
rule `Edit(**/.claude/settings.json)` and protect-config.sh's
`*/.claude/settings.json` pattern match it, so Claude cannot edit it from
inside a session.

Tests override the parent directory via WORKSPACE_PARENT_SETTINGS_DIR (parallel to
WORKSPACE_COMPOSED_DIR) so they never write next to a real checkout.
"""

import json
import os
import shlex
import subprocess
from copy import deepcopy
from pathlib import Path

from lib import log
from lib import paths as path_lib

import settings_sync


# Bumped whenever the derived template changes shape. Appears in
# env.WORKSPACE_PARENT_POLICY_VERSION and in the fail-closed messages.
PARENT_POLICY_VERSION = "1"

# The branch the policy is rendered from. See the module docstring for why
# this is not the working tree.
POLICY_REF = "origin/main"

# Source label prefix when origin/main could not be obtained (setup time).
WORKING_TREE_SOURCE = "working-tree"

SETTINGS_REL = settings_sync.SETTINGS_REL
DROPPED_KEYS = settings_sync.DROPPED_KEYS

PARENT_DIR_ENV = "WORKSPACE_PARENT_SETTINGS_DIR"


# --- location ----------------------------------------------------------------

def parent_dir(workspace_root):
    """The directory the parent policy is written under.

    Production: the workspace clone's parent (`/home/user` in cloud). Tests
    override via WORKSPACE_PARENT_SETTINGS_DIR.
    """
    override = os.environ.get(PARENT_DIR_ENV)
    if override:
        return Path(override)
    return Path(workspace_root).resolve().parent


def parent_settings_path(workspace_root):
    return parent_dir(workspace_root) / SETTINGS_REL


def _is_ours(text):
    """True when `text` is a policy this generator wrote (carries the marker)."""
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return False
    env = data.get("env") if isinstance(data, dict) else None
    return isinstance(env, dict) and "WORKSPACE_PARENT_POLICY_VERSION" in env


def guard_cloud_only():
    """The subcommand is a cloud fix; refuse to run it anywhere else.

    A local clone at `~/workspace` has the home directory as its parent, so the
    destination would be the engineer's own user-level Claude Code settings.
    The test override bypasses this (tests pin the destination explicitly).
    """
    if os.environ.get(PARENT_DIR_ENV):
        return
    if os.environ.get("CLAUDE_CODE_REMOTE") != "true":
        raise SystemExit(
            "parent-settings: cloud-only (the parent policy exists for multi-repo "
            "cloud sessions; it has no purpose on a local clone and its target "
            "could be your own user-level Claude Code settings)."
        )


def guard_destination(workspace_root):
    """Refuse a destination that is not ours to write. Always enforced.

    - Never the home directory: the target would be `~/.claude/settings.json`,
      the user's personal Claude Code config.
    - Never an existing file this generator did not write (no policy marker):
      a hand-written settings file at the parent is somebody's config, not
      drift to repair.
    """
    if not os.environ.get(PARENT_DIR_ENV):
        if parent_dir(workspace_root) == Path.home().resolve():
            raise SystemExit(
                "parent-settings: refusing to write - the clone's parent is your "
                "home directory, so the target would be your user-level Claude "
                "Code settings. Move the clone into a subdirectory."
            )
    p = parent_settings_path(workspace_root)
    if p.is_file() and not _is_ours(p.read_text()):
        raise SystemExit(
            f"parent-settings: refusing to overwrite {p} - it exists but was not "
            "written by this generator (no WORKSPACE_PARENT_POLICY_VERSION marker). "
            "Remove or rename it by hand if it is not wanted."
        )


def sibling_repos(workspace_root):
    """Other git checkouts next to the workspace clone (the multi-repo signal).

    Informational: the file is written regardless. Used for the setup log and
    for doctor, so a person can tell which layout the current session has.
    """
    root = Path(workspace_root).resolve()
    parent = parent_dir(workspace_root)
    if not parent.is_dir():
        return []
    out = []
    for d in sorted(parent.iterdir()):
        if not d.is_dir() or d.resolve() == root:
            continue
        if (d / ".git").exists():
            out.append(d)
    return out


# --- source -------------------------------------------------------------------

FETCH_TIMEOUT_SECONDS = 30


def _git(root, *argv, timeout=None):
    try:
        return subprocess.run(
            ["git", "-C", str(root)] + list(argv),
            capture_output=True, text=True, timeout=timeout,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None


def fetch_policy_ref(workspace_root):
    """Make `origin/main` available in the clone. Returns True on success.

    A cloud clone carries only the session branch (verified in #197: no
    `origin/main` unless the session happened to start from main), so the
    ref has to be fetched before it can be read. Shallow clones stay shallow
    (`--depth=1`); a complete clone is fetched normally so its history is
    not truncated. Failures are logged, never raised; the caller decides.
    """
    root = Path(workspace_root)
    shallow = _git(root, "rev-parse", "--is-shallow-repository")
    args = ["fetch", "--quiet"]
    if shallow is not None and shallow.stdout.strip() == "true":
        args.append("--depth=1")
    args += ["origin", POLICY_REF.split("/", 1)[1]]
    res = _git(root, *args, timeout=FETCH_TIMEOUT_SECONDS)
    if res is None:
        log.warn(f"parent-settings: git fetch of {POLICY_REF} failed (git missing or "
                 f"timed out after {FETCH_TIMEOUT_SECONDS}s)")
        return False
    if res.returncode != 0:
        log.warn(f"parent-settings: git fetch of {POLICY_REF} failed: "
                 f"{res.stderr.strip() or 'unknown error'}")
        return False
    return True


def _read_ref_settings(root):
    """Parsed root settings from origin/main, or None when the ref is absent."""
    res = _git(root, "show", f"{POLICY_REF}:{SETTINGS_REL}")
    if res is None or res.returncode != 0 or not res.stdout.strip():
        return None
    try:
        data = json.loads(res.stdout)
    except json.JSONDecodeError as e:
        raise SystemExit(f"parent-settings: {POLICY_REF}:{SETTINGS_REL} is invalid JSON: {e}")
    if not isinstance(data, dict):
        raise SystemExit(f"parent-settings: {POLICY_REF}:{SETTINGS_REL} is not a JSON object")
    return data


def _working_tree_source_label(root):
    res = _git(root, "rev-parse", "--short", "HEAD")
    sha = res.stdout.strip() if res is not None and res.returncode == 0 else ""
    return f"{WORKING_TREE_SOURCE}@{sha}" if sha else WORKING_TREE_SOURCE


def load_root_settings(workspace_root, fetch=True):
    """Return (settings_dict, source_label) for the root policy.

    Preferred source: `origin/main:.claude/settings.json`, fetched first when
    `fetch` is set. A cloud clone carries only the session branch, and git
    can authenticate only inside a live session (the platform proxy injects
    GitHub auth there; the setup tier and the snapshot build have no
    credentials, verified in #197). So:

      - inside a session the fetch succeeds and the source is origin/main;
      - at setup time it fails and the WORKING TREE is used, labeled
        `working-tree@<sha>`, so a fresh environment still gets a policy
        for its first multi-repo session. The apply tier re-renders from
        origin/main as soon as it runs inside a session, and doctor/--check
        report a working-tree source as a problem until then.

    Raises SystemExit only when no source is readable at all.
    """
    root = Path(workspace_root)
    if fetch:
        fetch_policy_ref(root)
    settings = _read_ref_settings(root)
    if settings is not None:
        return settings, POLICY_REF

    log.warn(f"parent-settings: {POLICY_REF} not available in the clone; rendering from "
             "the working tree (a live session re-renders from origin/main)")
    root_file = root / SETTINGS_REL
    if not root_file.is_file():
        raise SystemExit(f"parent-settings: root settings not found at {root_file}")
    try:
        data = json.loads(root_file.read_text())
    except json.JSONDecodeError as e:
        raise SystemExit(f"parent-settings: root settings invalid JSON: {e}")
    if not isinstance(data, dict):
        raise SystemExit("parent-settings: root settings is not a JSON object")
    return data, _working_tree_source_label(root)


# --- inline hook command construction ----------------------------------------
#
# Same conventions as settings_sync: single self-contained POSIX-sh strings,
# no single quotes inside embedded JSON, exec preserves stdin so the root
# scripts receive the tool payload unchanged. The difference is root
# resolution: pinned to the clone's absolute path instead of walking up.

def _pin(abs_root):
    return "d=" + shlex.quote(str(abs_root)) + "; "


def _not_attached_msg(abs_root):
    return (
        f"Workspace parent policy v{PARENT_POLICY_VERSION}: workspace clone not found at "
        f"{abs_root} (multi-repo session without <your-org>/<your-repo> "
        "attached). Attach the workspace to the session, or use an environment "
        "that is not set up for the workspace."
    )


def _script_wrapper(abs_root, script_rel, tool_label):
    """Pinned wrapper that execs a root hook script, failing closed."""
    return (
        _pin(abs_root)
        + 'h="$d/' + script_rel + '"; '
        + 'if [ -x "$h" ]; then CLAUDE_WORKSPACE_ROOT="$d" exec "$h"; fi; '
        + 'echo ' + shlex.quote(_not_attached_msg(abs_root)
                                + f" Failing closed ({tool_label} blocked).")
        + ' >&2; exit 2'
    )


def _not_detected_json(abs_root):
    msg = "Workspace security config: NOT DETECTED"
    detail = (
        f"the parent policy loaded but the workspace clone is not at {abs_root}, "
        "so the security hook scripts cannot run. Refuse tool use per "
        ".claude/rules/security-check.md and tell the user to attach "
        "<your-org>/<your-repo> to this session."
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


def _banner_command(abs_root):
    """SessionStart banner: delegate to the root status-banner.sh from inside
    the clone (it locates the root by walking up from the cwd), NOT DETECTED
    when the clone is absent."""
    return (
        _pin(abs_root)
        + "if " + settings_sync._ROOT_TEST + "; then "
        + 'cd "$d" && CLAUDE_WORKSPACE_ROOT="$d" '
        + 'exec "$d/.claude/hooks/status-banner.sh" team; '
        + "else "
        + "printf '%s' '" + _not_detected_json(abs_root) + "'; "
        + "fi"
    )


def _apply_command(abs_root):
    """Per-session bootstrap apply tier, mirroring the root settings.json hook.

    Silent when the clone is absent: the banner already reports NOT DETECTED
    and the PreToolUse wrappers block, so there is nothing to add here.
    """
    return (
        'if [ "$CLAUDE_CODE_REMOTE" = "true" ]; then '
        + _pin(abs_root)
        + 'cd "$d" 2>/dev/null && python3 "$d/tools/bootstrap/bootstrap.py" cloud --apply-only '
        + ">/dev/null 2>&1 || true; fi"
    )


def parent_hooks(abs_root):
    """The rebuilt hooks block: the root wiring with the clone path pinned."""
    protect = ".claude/hooks/protect-config.sh"
    audit = ".claude/hooks/webfetch-audit.sh"
    return {
        "PreToolUse": [
            {
                "matcher": "Write|Edit|MultiEdit",
                "hooks": [{"type": "command",
                           "command": _script_wrapper(abs_root, protect, "file edit")}],
            },
            {
                "matcher": "Bash",
                "hooks": [{"type": "command",
                           "command": _script_wrapper(abs_root, protect, "Bash")}],
            },
            {
                "matcher": "WebFetch",
                "hooks": [{"type": "command",
                           "command": _script_wrapper(abs_root, audit, "WebFetch")}],
            },
        ],
        "SessionStart": [
            {
                "matcher": "startup|resume|clear|compact",
                "hooks": [{"type": "command", "command": _banner_command(abs_root)}],
            },
            {
                "matcher": "startup|resume|clear|compact",
                "hooks": [{"type": "command", "command": _apply_command(abs_root)}],
            },
        ],
    }


def derive_parent_settings(root_settings, workspace_root, source=POLICY_REF):
    """Derive the parent policy dict from the parsed root settings.

    `source` is stamped into env.WORKSPACE_PARENT_POLICY_SOURCE so doctor and
    --check can tell a main-rendered file from a working-tree seed.
    """
    abs_root = str(Path(workspace_root).resolve())
    parent = {k: deepcopy(v) for k, v in root_settings.items()
              if k not in DROPPED_KEYS}
    env = dict(parent.get("env") or {})
    env["CLAUDE_WORKSPACE_ROOT"] = abs_root
    env["WORKSPACE_PARENT_POLICY_VERSION"] = PARENT_POLICY_VERSION
    env["WORKSPACE_PARENT_POLICY_SOURCE"] = source
    parent["env"] = env
    parent["hooks"] = parent_hooks(abs_root)
    return parent


def render(settings):
    return json.dumps(settings, indent=2) + "\n"


def expected_content(workspace_root, fetch=True):
    """Return (rendered_text, source_label)."""
    root_settings, source = load_root_settings(workspace_root, fetch=fetch)
    return render(derive_parent_settings(root_settings, workspace_root, source)), source


def recorded_source(text):
    """The source label a written policy carries, or None if it is not ours."""
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None
    env = data.get("env") if isinstance(data, dict) else None
    if not isinstance(env, dict) or "WORKSPACE_PARENT_POLICY_VERSION" not in env:
        return None
    return env.get("WORKSPACE_PARENT_POLICY_SOURCE") or "unknown"


# --- status / write ------------------------------------------------------------

def status(workspace_root):
    """Read-only comparison for doctor and --check. Never fetches.

    Returns a dict:
      path, exists, siblings
      file_source  the source the existing file records (None when absent
                   or not ours)
      verified     True when origin/main is in the clone, so the file could
                   be compared against the reviewed rendering
      in_sync      byte-identical to the rendering from origin/main
                   (meaningful only when verified)
    """
    root = Path(workspace_root)
    p = parent_settings_path(root)
    exists = p.is_file()
    file_source = recorded_source(p.read_text()) if exists else None
    ref_settings = _read_ref_settings(root)
    verified = ref_settings is not None
    in_sync = False
    if verified and exists:
        expected = render(derive_parent_settings(ref_settings, root, POLICY_REF))
        in_sync = p.read_text() == expected
    return {
        "path": p,
        "exists": exists,
        "file_source": file_source,
        "verified": verified,
        "in_sync": in_sync,
        "siblings": sibling_repos(root),
    }


def check_problem(st):
    """Return a one-line problem description for a status() dict, or ''.

    Shared by --check and doctor so the two never disagree. A missing file is
    left to the caller (its severity depends on the layout).
    """
    if not st["exists"]:
        return ""
    if st["file_source"] is None:
        return f"{st['path']} exists but was not written by this generator"
    if st["file_source"] != POLICY_REF:
        return (f"{st['path']} was rendered from {st['file_source']}, not {POLICY_REF}; "
                "the apply tier re-renders at the next session start that can fetch main")
    if st["verified"] and not st["in_sync"]:
        return f"{st['path']} drifted from the {POLICY_REF} rendering"
    return ""


def write(workspace_root):
    """Render and write the parent policy.

    Returns 'written', 'unchanged', or 'kept'. 'kept' means origin/main could
    not be obtained but the existing file was rendered from it earlier: a
    reviewed rendering is never downgraded to a working-tree one because of
    a transient fetch failure.

    Raises SystemExit when no root policy source is readable or the
    destination is not ours to write (see guard_destination), and OSError
    when the parent directory is not writable. Callers in the cloud tiers
    catch everything: a failure here must never take a session down.
    """
    guard_destination(workspace_root)
    p = parent_settings_path(workspace_root)
    expected, source = expected_content(workspace_root)
    if source != POLICY_REF and p.is_file() and recorded_source(p.read_text()) == POLICY_REF:
        log.warn(f"parent-settings: keeping the existing {POLICY_REF} rendering at {p} "
                 "rather than replacing it with a working-tree one")
        return "kept"
    if p.is_file() and p.read_text() == expected:
        log.dim(f"parent-settings: {p} in sync (source {source})")
        return "unchanged"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(expected)
    log.change(f"parent-settings: wrote {p} (policy v{PARENT_POLICY_VERSION}, source {source})")
    return "written"


def run(args):
    """`parent-settings [--check]` subcommand. Cloud-only (see guard_cloud_only)."""
    guard_cloud_only()
    workspace_root = path_lib.require_workspace_root()
    if getattr(args, "check", False):
        st = status(workspace_root)
        if not st["exists"]:
            log.error(f"parent-settings --check: missing: {st['path']}")
            return 1
        problem = check_problem(st)
        if problem:
            log.error(f"parent-settings --check: {problem}")
            return 1
        if not st["verified"]:
            log.warn(f"parent-settings --check: {st['path']} records {POLICY_REF} as its "
                     "source but that ref is not in this clone; byte-identity not verified")
            return 0
        log.ok(f"parent-settings --check: {st['path']} in sync "
               f"(policy v{PARENT_POLICY_VERSION}, source {POLICY_REF})")
        return 0
    write(workspace_root)
    n = len(sibling_repos(workspace_root))
    log.info(f"parent-settings: {n} sibling repo(s) next to the workspace "
             f"({'multi-repo layout' if n else 'single-repo layout'})")
    return 0
