"""doctor: diagnostics.

The first command to run when a session looks wrong. Prints a structured,
read-only report of the bootstrap state and exits non-zero when it finds a
genuine problem (so it's usable in scripts and CI), 0 when healthy.

Sections:
  Environment  - mode (cloud/local/unknown), workspace root, resolved team
  Composition  - manifest contents (team, levels, per-level counts), copied files
  Context      - personal CLAUDE.local.md state (loaded/empty/missing)
  Security     - settings.json (sandbox enabled, deny rules), user-level hook
  Version      - bootstrap version pin

Severity model:
  ok      healthy; never affects exit code
  info    neutral fact; never affects exit code
  warn    worth noting but not a failure (e.g. user-level hook absent, which is
          normal in cloud); never affects exit code
  problem a real misconfiguration (root missing, sandbox off, no deny rules,
          stale user hook, unresolvable WORKSPACE_TEAM); forces a non-zero exit

Strictly read-only: doctor never writes or mutates workspace state.
"""

import json
import os
import re
from pathlib import Path

from lib import localmd
from lib import log
from lib import manifest as manifest_lib
from lib import paths as path_lib

import compose
import settings_sync


OK = "ok"
INFO = "info"
WARN = "warn"
PROBLEM = "problem"

PERSONAL_CONTEXT_REL = "CLAUDE.local.md"

# Substrings identifying our user-scope SessionStart hook (current + legacy),
# mirroring install.py's is_ours() detection.
_OUR_HOOK_MARKERS = ("/.claude/hooks/status-banner.sh", "/scripts/check-team-settings.sh")


def run(args):
    report = _Report()

    root = path_lib.find_workspace_root()
    mode = _mode_token()
    report.section("Environment")
    report.line(OK, f"mode: {_mode_display()}")
    if root is None:
        report.line(PROBLEM, "workspace root: not found "
                             "(need .claude/settings.json, CLAUDE.md, departments/)")
        # Nothing else is meaningful without a root.
        return report.finish()
    report.line(OK, f"workspace root: {root}")
    _check_team(report, root)

    report.section("Composition")
    _check_manifest(report, root)

    report.section("Context")
    _check_personal(report, root)

    report.section("Security")
    _check_settings(report, root)
    _check_user_hook(report, root, mode)
    _check_team_policy(report, root)

    report.section("Version")
    _check_version(report, root)

    return report.finish()


def _mode_token():
    """Normalized mode: 'cloud' (CLAUDE_CODE_REMOTE=true), 'local' (unset), else 'unknown'."""
    val = os.environ.get("CLAUDE_CODE_REMOTE")
    if val == "true":
        return "cloud"
    if not val:
        return "local"
    return "unknown"


def _mode_display():
    token = _mode_token()
    if token == "unknown":
        return f"unknown (CLAUDE_CODE_REMOTE={os.environ.get('CLAUDE_CODE_REMOTE')!r})"
    return token


def _safe_manifest(root):
    """Best-effort manifest read; None when absent or unreadable.

    _check_manifest owns surfacing a corrupt manifest as a problem, so here we
    just swallow the error and treat it as 'not composed'.
    """
    try:
        return manifest_lib.read(root)
    except SystemExit:
        return None


def _check_team(report, root):
    """Report the effective team for this session.

    The composed team recorded in the manifest is the source of truth - that is
    what actually shaped the session, whether it came from WORKSPACE_TEAM or the
    setup script's --team flag. WORKSPACE_TEAM being unset is normal in cloud: setup
    scripts pass --team as a flag, and the platform does not inject env-config
    vars into the setup process. So read the manifest first and only fall back
    to the env var when nothing is composed yet.
    """
    env_team = os.environ.get("WORKSPACE_TEAM")
    manifest = _safe_manifest(root)
    composed = manifest.get("team_input") if manifest else None

    if composed:
        if str(composed).strip().lower() == compose.ROOT_SENTINEL:
            report.line(OK, "team: root (root / no-team mode)")
        else:
            report.line(OK, f"team: {composed} (composed)")
        if env_team and env_team.strip().lower() != str(composed).strip().lower():
            report.line(
                WARN,
                f"WORKSPACE_TEAM={env_team!r} differs from the composed team "
                f"{composed!r}; run `reset` then recompose to switch",
            )
        return

    # Not composed yet - report WORKSPACE_TEAM as a configuration hint.
    if not env_team:
        report.line(INFO, "team: not set (WORKSPACE_TEAM unset, nothing composed)")
        return
    if env_team.strip().lower() == compose.ROOT_SENTINEL:
        report.line(OK, "team (WORKSPACE_TEAM): root (root / no-team mode; not composed yet)")
        return
    try:
        target = path_lib.resolve_team(env_team, root)
    except SystemExit as e:
        report.line(PROBLEM, f"team (WORKSPACE_TEAM): {env_team} → {e}")
        return
    report.line(
        OK,
        f"team (WORKSPACE_TEAM): {env_team} → {target.relative_to(root)} (not composed yet)",
    )


def _check_manifest(report, root):
    try:
        manifest = manifest_lib.read(root)
    except SystemExit as e:
        report.line(PROBLEM, f"manifest: {e}")
        return
    if manifest is None:
        report.line(INFO, "manifest: not composed (no .bootstrap-manifest.json)")
        return

    if manifest.get("root"):
        report.line(OK, "manifest: composed in root / no-team mode")
    else:
        report.line(
            OK,
            f"manifest: composed for {manifest.get('team_input')!r} → "
            f"{manifest.get('team_resolved_path')}",
        )
    report.line(
        INFO,
        f"composed at {manifest.get('composed_at')} "
        f"(tool {manifest.get('tool_version')})",
        indent=6,
    )
    for lvl in manifest.get("levels", []):
        report.line(INFO, _level_summary(lvl), indent=6)

    copied = manifest_lib.read_copied_files(root)
    report.line(INFO, f"copied files: {len(copied)} tracked for reset")


def _level_summary(lvl):
    """One-line per-level artifact counts (added, with overridden noted)."""
    def n(added_key, over_key=None):
        added = len(lvl.get(added_key, []))
        over = len(lvl.get(over_key, [])) if over_key else 0
        return f"+{added}" + (f" ({over} overridden)" if over else "")

    return (
        f"level {lvl.get('path')}: "
        f"skills {n('skills_added', 'skills_overridden')}, "
        f"agents {n('agents_added', 'agents_overridden')}, "
        f"commands {n('commands_added', 'commands_overridden')}, "
        f"rules {n('rules_added')}, "
        f"hooks {n('hooks_added')}"
    )


def _check_personal(report, root):
    """Report personal CLAUDE.local.md state below compose's team block."""
    local_md = Path(root) / PERSONAL_CONTEXT_REL
    if not local_md.is_file():
        report.line(INFO, f"personal context ({PERSONAL_CONTEXT_REL}): missing file")
        return
    personal = localmd.strip_team_block(local_md.read_text())
    if personal.strip():
        report.line(
            OK,
            f"personal context ({PERSONAL_CONTEXT_REL}): loaded "
            f"({len(personal)} bytes)",
        )
    else:
        report.line(INFO, f"personal context ({PERSONAL_CONTEXT_REL}): empty")


def _check_settings(report, root):
    settings_path = Path(root) / ".claude" / "settings.json"
    if not settings_path.is_file():
        report.line(PROBLEM, "settings.json: missing")
        return
    try:
        settings = json.loads(settings_path.read_text())
    except json.JSONDecodeError as e:
        report.line(PROBLEM, f"settings.json: invalid JSON ({e})")
        return

    sandbox_on = bool(settings.get("sandbox", {}).get("enabled"))
    deny = settings.get("permissions", {}).get("deny", [])
    deny_ok = isinstance(deny, list) and len(deny) > 0

    if sandbox_on and deny_ok:
        report.line(OK, f"settings.json: sandbox enabled, {len(deny)} deny rule(s)")
    else:
        if not sandbox_on:
            report.line(PROBLEM, "settings.json: sandbox NOT enabled")
        if not deny_ok:
            report.line(PROBLEM, "settings.json: no deny rules present")


def _user_settings_path():
    """Path to the user-scope ~/.claude/settings.json (split out for testability)."""
    return Path.home() / ".claude" / "settings.json"


def _check_user_hook(report, root, mode):
    """Report the user-scope SessionStart hook installed by `install`.

    This is purely a local-CLI safety net: the ~/.claude hook that warns an
    engineer who starts a terminal session inside an workspace tree without the team
    settings loaded. Cloud sessions never use it - they load the repo's own
    SessionStart hook directly - so in cloud we report it as not applicable
    rather than flagging its absence, which would just alarm users for no reason.

    Local/unknown: present (points at THIS root's status-banner.sh), stale (ours
    but a different path - another checkout or the legacy script), or absent
    (run `install`).
    """
    if mode == "cloud":
        report.line(
            INFO,
            "user-level hook: not applicable in cloud "
            "(the repo's own SessionStart hook is used instead)",
        )
        return

    expected = f"{root}/.claude/hooks/status-banner.sh user"
    user_settings = _user_settings_path()
    if not user_settings.is_file():
        report.line(WARN, "user-level hook: absent (run `install` to set up the local CLI)")
        return
    try:
        settings = json.loads(user_settings.read_text())
    except json.JSONDecodeError:
        report.line(PROBLEM, f"user-level hook: {user_settings} is invalid JSON")
        return

    commands = []
    for entry in settings.get("hooks", {}).get("SessionStart", []) or []:
        if not isinstance(entry, dict):
            continue
        for h in entry.get("hooks", []) or []:
            if isinstance(h, dict) and h.get("command"):
                commands.append(h["command"])

    ours = [c for c in commands if any(m in c for m in _OUR_HOOK_MARKERS)]
    if any(c == expected for c in ours):
        report.line(OK, "user-level hook: present")
    elif ours:
        report.line(
            PROBLEM,
            f"user-level hook: stale (points elsewhere: {ours[0]!r}); "
            "re-run `install`",
        )
    else:
        report.line(WARN, "user-level hook: absent (run `install` to set up the local CLI)")


def _check_team_policy(report, root):
    """Report the stamped team-folder security settings (issue #141).

    Healthy = every tracked CLAUDE.md-bearing folder carries a stamp that is
    byte-identical to fresh generator output, and no stray copy exists. Drift
    or a missing/stray copy is a real problem (a team-folder session would run
    under a policy that differs from the root source of truth). Environments
    where git can't enumerate the targets (no repo, no git binary) just skip -
    there is nothing meaningful to verify there.
    """
    try:
        targets = settings_sync.target_folders(root)
    except SystemExit as e:
        report.line(INFO, f"team-folder policy: skipped ({e})")
        return
    if not targets:
        report.line(
            INFO,
            "team-folder policy: no target folders "
            "(no tracked CLAUDE.md outside the root)",
        )
        return

    try:
        issues, _ = settings_sync.findings(root)
    except SystemExit as e:
        # Enumeration worked above, so this is a real finding (e.g. a stamp
        # the .gitignore allowlist would silently drop, or a broken root file).
        report.line(PROBLEM, f"team-folder policy: {e}")
        return

    missing = [rel for kind, rel in issues if kind == "missing"]
    drift = [rel for kind, rel in issues if kind == "drift"]
    strays = [rel for kind, rel in issues if kind == "stray"]
    stamped = len(targets) - len(missing)

    if not issues:
        report.line(
            OK,
            f"team-folder policy: v{settings_sync.TEAM_POLICY_VERSION} "
            f"stamped in {stamped}/{len(targets)} folder(s), no drift",
        )
        return

    report.line(
        PROBLEM,
        f"team-folder policy: {stamped}/{len(targets)} folder(s) stamped, "
        f"{len(missing)} missing, {len(drift)} drifted, {len(strays)} stray - "
        "run `python3 tools/bootstrap/bootstrap.py settings-sync`",
    )
    for rel in (missing + drift + strays)[:5]:
        report.line(INFO, rel, indent=6)


# Setup scripts that may carry a cache-pin version comment. The epic's plan
# called this file "setup-cloud.sh"; the shipped cloud entrypoint is
# scripts/install.sh - check both so the pin is found wherever it lands.
_VERSION_PIN_FILES = ("scripts/setup-cloud.sh", "scripts/install.sh")
_VERSION_PIN_RE = re.compile(r"(?i)bootstrap[ -]?version\s*[:=]\s*v?([0-9][\w.\-]*)")


def _check_version(report, root):
    """Report the bootstrap version pin (cache-invalidation marker).

    Looks for a `# bootstrap-version: X.Y.Z` comment in the cloud setup script;
    falls back to the tool's code-level MANIFEST_VERSION when none is pinned.
    Informational only - an unpinned version is not a failure.
    """
    for rel in _VERSION_PIN_FILES:
        f = Path(root) / rel
        if not f.is_file():
            continue
        m = _VERSION_PIN_RE.search(f.read_text())
        if m:
            report.line(INFO, f"bootstrap version: {m.group(1)} (pinned in {rel})")
            return
    report.line(
        INFO,
        f"bootstrap version: {manifest_lib.MANIFEST_VERSION} "
        "(code default; no cache-pin comment found)",
    )


class _Report:
    """Accumulates and renders doctor output, tracking whether any PROBLEM hit."""

    _GLYPH = {
        OK: (log.GREEN, "✓"),
        INFO: (log.DIM, "·"),
        WARN: (log.YELLOW, "!"),
        PROBLEM: (log.RED, "✗"),
    }

    def __init__(self):
        self._has_problem = False

    def section(self, title):
        print(f"\n{log.BOLD}{title}{log.RESET}")

    def line(self, severity, text, indent=2):
        if severity == PROBLEM:
            self._has_problem = True
        color, glyph = self._GLYPH[severity]
        print(f"{' ' * indent}{color}{glyph}{log.RESET} {text}")

    def finish(self):
        if self._has_problem:
            print(f"\n{log.RED}✗ doctor: problems detected (see above).{log.RESET}")
            return 1
        print(f"\n{log.GREEN}✓ doctor: healthy.{log.RESET}")
        return 0
