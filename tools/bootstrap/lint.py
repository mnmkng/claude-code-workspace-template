"""lint: the workspace structure and security checks, runnable outside CI.

`.github/workflows/security-lint.yml` used to carry these checks as inline
shell and heredoc'd Python. That made them CI-only: a contributor (or a skill
like `scaffold`, which must not leave the tree in a state CI rejects) could not
run them locally, and the workflow file is a protected file, so the checks
could not be fixed from inside a session either. They live here instead; the
workflow calls this subcommand.

Checks, each one a function returning a list of one-line findings:

  1. folder basenames containing a CLAUDE.md are globally unique
  2. every whole-line @import in a committed CLAUDE.md resolves or is gitignored
  3. .gitignore carries the required entries
  4. the derived team-folder settings stamps are in sync (settings-sync --check)
  5. .claude/hooks/*.sh are executable
  6. no committed settings.local.json, .env, or .mcp.json
  7. the root settings.json exists, parses, and carries the required policy keys
  8. every team-folder settings stamp carries the required policy keys

Checks 7 and 8 are not in the "move these" list of the brief that asked for
this subcommand, but the workflow ran them inline and the point of the
subcommand is that the workflow can call it *instead of* its inline steps.
Dropping them would quietly weaken CI, so they moved too.

Exit code: 0 clean, 1 on any finding. Infrastructure failures (no git, no
workspace root) raise SystemExit with a message instead of being reported as
findings - "the checker could not run" is not "the tree is clean".

Stdlib only.  Target: Python 3.9+.
"""

import collections
import json
import os
import re
import subprocess
from pathlib import Path

from lib import log
from lib import paths as path_lib

import settings_sync


# Tracked CLAUDE.md files under these prefixes are tooling and test fixtures,
# not team content: the bootstrap's own tests build workspace-shaped trees with
# deliberately broken imports and colliding folder names. Shared with
# settings-sync so the two subcommands can never disagree about what counts as
# a team folder (a folder lint ignored but settings-sync stamped would drift
# silently).
EXCLUDED_PREFIXES = settings_sync.EXCLUDED_PREFIXES

# Whole-line @import only: `@path` alone on a line. An @mention inside prose
# does not load anything, so it is not checked.
IMPORT_RE = re.compile(r"^\s*@(\S+)\s*$")

REQUIRED_GITIGNORE_ENTRIES = (
    "**/settings.local.json",
    ".env*",
    ".mcp.json",
)

REQUIRED_DENY_READ = ("~/.ssh/**", "~/.aws/**", "**/.env", "**/.mcp.json")

SETTINGS_REL = settings_sync.SETTINGS_REL


# --- git helpers -------------------------------------------------------------

def _git(workspace_root, *argv):
    try:
        return subprocess.run(
            ["git", "-C", str(workspace_root)] + list(argv),
            capture_output=True, text=True,
        )
    except FileNotFoundError:
        return None


def tracked_files(workspace_root):
    """Every path git tracks, repo-relative, POSIX separators."""
    res = _git(workspace_root, "ls-files", "-z")
    if res is None or res.returncode != 0:
        detail = "git not found" if res is None else res.stderr.strip()
        raise SystemExit(
            f"lint: cannot enumerate tracked files ({detail}). "
            "Run from a git checkout of the workspace."
        )
    return [p for p in res.stdout.split("\0") if p]


def _is_ignored(workspace_root, rel_path):
    res = _git(workspace_root, "check-ignore", "-q", "--", rel_path)
    return res is not None and res.returncode == 0


def _excluded(rel_path):
    return any(rel_path.startswith(p) for p in EXCLUDED_PREFIXES)


# --- checks ------------------------------------------------------------------

def check_unique_claude_md_folders(root, tracked):
    """Cloud team resolution keys on a folder's basename (lib/paths.py
    resolve_team), so two teams named `content` in different departments are
    unresolvable. The repo-root CLAUDE.md is not a team."""
    dirs = collections.defaultdict(list)
    for rel in tracked:
        if os.path.basename(rel) != "CLAUDE.md" or _excluded(rel):
            continue
        folder = os.path.dirname(rel)
        if not folder:
            continue
        dirs[os.path.basename(folder)].append(folder)
    out = []
    for basename, folders in sorted(dirs.items()):
        if len(folders) > 1:
            out.append(
                f"folder name '{basename}' contains a CLAUDE.md in multiple places: "
                f"{sorted(folders)} - folder names containing a CLAUDE.md must be "
                "globally unique (cloud team resolution keys on the basename)"
            )
    return out


def check_claude_md_imports(root, tracked):
    """A broken @import loads with no error at runtime, so the typo is
    invisible until someone notices the missing context. Resolve every one
    relative to the importing file's own directory; a gitignored target
    (CLAUDE.local.md) is intentionally absent and allowed."""
    out = []
    for rel in tracked:
        if os.path.basename(rel) != "CLAUDE.md" or _excluded(rel):
            continue
        f = Path(root) / rel
        if not f.is_file():
            continue
        base = os.path.dirname(rel)
        for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            m = IMPORT_RE.match(line)
            if not m:
                continue
            target = m.group(1)
            resolved = (target.lstrip("/") if target.startswith("/")
                        else os.path.normpath(os.path.join(base, target)))
            if (Path(root) / resolved).exists():
                continue
            if _is_ignored(root, resolved):
                continue
            out.append(
                f"{rel}:{n}: @import '{target}' -> '{resolved}' does not exist and "
                "is not gitignored (broken imports fail silently at load time)"
            )
    return out


def check_gitignore_entries(root, tracked):
    """The default-deny allowlist depends on these three whole lines; a
    reformat that drops one re-opens the path it closed."""
    f = Path(root) / ".gitignore"
    if not f.is_file():
        return [".gitignore is missing at the workspace root"]
    lines = {ln.strip() for ln in f.read_text(encoding="utf-8").splitlines()}
    return [f".gitignore missing required entry: {e}"
            for e in REQUIRED_GITIGNORE_ENTRIES if e not in lines]


def check_settings_sync(root, tracked):
    """Team-folder stamps byte-identical to fresh generator output."""
    try:
        issues, _targets = settings_sync.findings(root)
    except SystemExit as e:
        return [f"settings-sync: {e}"]
    return [
        f"settings-sync: {kind}: {rel} - run `python3 tools/bootstrap/bootstrap.py "
        "settings-sync` and commit the result" for kind, rel in issues
    ]


def check_hooks_executable(root, tracked):
    """Hooks fire regardless of workspace trust, which makes them the floor
    under the permission and sandbox layers. A non-executable hook script is a
    silently absent guardrail."""
    hooks = sorted((Path(root) / ".claude" / "hooks").glob("*.sh"))
    return [f".claude/hooks/{h.name} is not executable (chmod +x it)"
            for h in hooks if not os.access(h, os.X_OK)]


def check_no_secrets_committed(root, tracked):
    """Personal settings, environment files, and MCP configuration are
    gitignored by policy; a tracked copy means someone forced it in."""
    out = []
    for rel in tracked:
        name = os.path.basename(rel)
        parts = rel.split("/")
        if name == "settings.local.json" and "projects" not in parts:
            out.append(f"settings.local.json committed outside projects/: {rel}")
        if (name == ".env" or name.startswith(".env.")) and name != ".env.example":
            out.append(f".env file committed (only .env.example is allowed): {rel}")
        if name == ".mcp.json":
            out.append(
                f".mcp.json committed: {rel} (should be gitignored; use .env + "
                "${VAR} expansion for secrets)"
            )
    return out


def _policy_problems(where, s):
    problems = []
    if s.get("permissions", {}).get("defaultMode") != "acceptEdits":
        problems.append(f"{where}: permissions.defaultMode must be 'acceptEdits'")
    if s.get("sandbox", {}).get("enabled") is not True:
        problems.append(f"{where}: sandbox.enabled must be true")
    deny_read = set(s.get("sandbox", {}).get("filesystem", {}).get("denyRead", []))
    missing = set(REQUIRED_DENY_READ) - deny_read
    if missing:
        problems.append(
            f"{where}: sandbox.filesystem.denyRead missing {sorted(missing)}")
    return problems


def check_root_settings(root, tracked):
    """The root policy is the single source of truth; everything else derives
    from it, so a degraded root degrades every copy."""
    f = Path(root) / SETTINGS_REL
    if not f.is_file():
        return [f"{SETTINGS_REL} is missing"]
    try:
        s = json.loads(f.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return [f"{SETTINGS_REL} is not valid JSON: {e}"]
    return _policy_problems(SETTINGS_REL, s)


def check_team_settings(root, tracked):
    """Every stamp carries the policy, the version marker, and no MCP keys.

    settings-sync already proves byte-identity with the generator; this proves
    the generator's own output is a policy worth shipping.
    """
    copies = [rel for rel in tracked
              if rel.startswith("departments/") and rel.endswith("/" + SETTINGS_REL)]
    if not copies:
        return ["no tracked team-folder settings.json found (expected stamps "
                "from settings-sync)"]
    out = []
    for rel in copies:
        f = Path(root) / rel
        try:
            s = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            out.append(f"{rel}: unreadable or invalid JSON: {e}")
            continue
        out.extend(_policy_problems(rel, s))
        if not s.get("env", {}).get("WORKSPACE_TEAM_POLICY_VERSION"):
            out.append(f"{rel}: env.WORKSPACE_TEAM_POLICY_VERSION missing")
        if s.get("enableAllProjectMcpServers") or s.get("enabledMcpjsonServers"):
            out.append(f"{rel}: MCP keys must not be present in team copies")
    return out


# Ordered: structure first, then policy. Each entry is (label, function).
CHECKS = (
    ("unique-folder-names", check_unique_claude_md_folders),
    ("claude-md-imports", check_claude_md_imports),
    ("gitignore-entries", check_gitignore_entries),
    ("settings-sync", check_settings_sync),
    ("hooks-executable", check_hooks_executable),
    ("no-secrets-committed", check_no_secrets_committed),
    ("root-settings", check_root_settings),
    ("team-settings", check_team_settings),
)


def findings(workspace_root):
    """Run every check. Returns a list of (label, finding) pairs."""
    workspace_root = Path(workspace_root)
    tracked = tracked_files(workspace_root)
    out = []
    for label, fn in CHECKS:
        for finding in fn(workspace_root, tracked):
            out.append((label, finding))
    return out


def run(args=None):
    workspace_root = path_lib.require_workspace_root()
    found = findings(workspace_root)
    if not found:
        log.ok(f"lint: {len(CHECKS)} checks clean")
        return 0
    for label, finding in found:
        log.error(f"lint [{label}]: {finding}")
    log.error(f"lint: {len(found)} finding(s)")
    return 1
