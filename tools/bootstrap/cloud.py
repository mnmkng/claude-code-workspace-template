"""cloud: orchestrate compose + personal sync for Claude Code Cloud (#45).

Two-tier strategy:

  Setup-script tier (cached snapshot, runs as root, ~7d):
    bootstrap.py cloud --compose-only
      → compose into root .claude/
      → mirror .claude/ → /opt/claude-workspace/composed/.claude/
      → write /opt/claude-workspace/composed/bootstrap-meta.json
      (personal sync skipped — env vars may not be set yet)

  SessionStart tier (per session, sub-second, runs as the session user —
  root in cloud today):
    bootstrap.py cloud --apply-only
      → re-compose the overlay from the LIVE checkout (team from staged meta)
        so a creator's edited or newly-added skills/agents/rules/context
        propagate on the next session — no cache rebuild, no manual step.
        compose rewrites the overlay, the CLAUDE.local.md @import block, the
        manifest, copied-files, and .git/info/exclude. Tracked base files
        (settings.json, base hooks) are never written.
      → on live-compose failure, fall back to the last-known-good staged
        overlay (still never the tracked base files)
      → fetch WORKSPACE_PERSONAL_GIST → CLAUDE.local.md (below the team block)
      → re-apply the stop-hook no-op when the setup tier recorded the intent
        (the platform clobbers it on every session start — see #72)

    Re-compose is additive: adds/edits propagate immediately; a removed team
    artifact lingers until a cache rebuild or `reset`.

  Default (no flag): compose + personal sync (useful for cold-start / ad-hoc runs).

Setup-tier failures raise SystemExit. Apply-tier failures log to
.claude/.bootstrap-log.txt and re-raise; the SessionStart hook wraps
with `|| true` so the session still starts.
"""

import argparse
import os
import shutil
from pathlib import Path

from lib import log
from lib import manifest as manifest_lib
from lib import paths as path_lib
from lib import staging

import compose
import personal


BOOTSTRAP_LOG_REL = ".claude/.bootstrap-log.txt"

# Path of the platform's user-scope stop-hook-git-check.sh script (when present
# in cloud sessions). The hook exits 2 on any dirty/untracked/unpushed state,
# which fires every Stop because our bootstrap intentionally leaves the tree
# dirty (composed .claude/skills/* + CLAUDE.md marker block). --disable-stop-hook
# replaces it with a no-op; the original is preserved at $PATH.original.
# Overridable via WORKSPACE_STOP_HOOK_PATH (parallels staging's WORKSPACE_COMPOSED_DIR)
# for tests and for resilience if the platform ever moves the hook.
STOP_HOOK_PATH = "/root/.claude/stop-hook-git-check.sh"
STOP_HOOK_NOOP_BODY = """#!/bin/bash
# Disabled by claude-code-workspace cloud bootstrap (--disable-stop-hook).
# The bootstrap intentionally leaves a dirty working tree (composed team
# artifacts + CLAUDE.md marker block); the original git-check hook would
# exit 2 on every Stop and prompt the model to auto-commit, polluting the
# branch with bootstrap state. Original preserved as $0.original.
exit 0
"""


def run(args):
    compose_only = bool(getattr(args, "compose_only", False))
    apply_only = bool(getattr(args, "apply_only", False))

    if compose_only and apply_only:
        raise SystemExit("cloud: --compose-only and --apply-only are mutually exclusive")

    workspace_root = path_lib.require_workspace_root()
    log.set_log_file(workspace_root / BOOTSTRAP_LOG_REL)

    mode = "apply-only" if apply_only else ("compose-only" if compose_only else "default")
    log.step(f"cloud: mode={mode}")

    if not apply_only and getattr(args, "disable_stop_hook", False):
        _disable_stop_hook()

    if apply_only:
        _apply_only(workspace_root)
    elif compose_only:
        _compose_and_stage(workspace_root, args)
    else:
        _compose_and_stage(workspace_root, args)
        _sync_personal(workspace_root, args)

    log.ok("cloud: done")
    return 0


def _stop_hook_path():
    """Resolve the stop-hook path, honoring the WORKSPACE_STOP_HOOK_PATH override."""
    return os.environ.get("WORKSPACE_STOP_HOOK_PATH", STOP_HOOK_PATH)


def _disable_stop_hook(hook_path=None):
    """Replace the platform's stop-hook-git-check.sh with a no-op (idempotent).

    Runs as root in cloud sessions — both the setup tier and the per-session
    apply tier write `/root/.claude/`. The original is preserved at
    `${hook_path}.original` for inspection or recovery.

    The no-op does NOT survive on its own: the platform re-installs/updates the
    user-scope hook on every session start, after the snapshot is restored,
    clobbering whatever the setup tier wrote (see #72). That is why
    `_apply_only` re-applies it every session, after the platform's refresh —
    the setup-tier write alone only covers the cold-start session.

    Silently no-ops if the hook isn't present (engineer-local case, or platform
    changed the layout). Permission errors are logged but not fatal — the
    bootstrap shouldn't die because of a hook we don't strictly need to touch.
    """
    hook = Path(hook_path or _stop_hook_path())
    hook_path = str(hook)
    backup = Path(f"{hook_path}.original")

    if not hook.is_file():
        log.dim(f"cloud: stop-hook not present at {hook_path}; skipping disable")
        return

    try:
        if not backup.exists():
            backup.write_bytes(hook.read_bytes())
        hook.write_text(STOP_HOOK_NOOP_BODY)
        hook.chmod(0o755)
        log.change(f"cloud: neutralized {hook_path} (original at {backup})")
    except (PermissionError, OSError) as e:
        log.warn(f"cloud: could not disable stop-hook ({type(e).__name__}: {e}); continuing")


def _compose_and_stage(workspace_root, args):
    """Setup-script tier: compose + mirror to staging."""
    compose_args = argparse.Namespace(team=getattr(args, "team", None))
    compose.run(compose_args)

    src = workspace_root / ".claude"
    dst = staging.staged_claude_dir()
    log.step(f"cloud: staging .claude/ → {dst}")
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst, symlinks=False, ignore_dangling_symlinks=True)

    manifest = manifest_lib.read(workspace_root) or {}
    levels = manifest.get("levels", [])
    chain_rel_paths = [lvl["path"] for lvl in levels if "path" in lvl]
    staging.write_meta(
        team_input=manifest.get("team_input"),
        chain_rel_paths=chain_rel_paths,
        tool_version=manifest_lib.MANIFEST_VERSION,
        composed_at=manifest.get("composed_at"),
        disable_stop_hook=bool(getattr(args, "disable_stop_hook", False)),
    )
    log.ok(f"cloud: staged {len(chain_rel_paths)} chain level(s) to {dst}")


def _apply_only(workspace_root):
    """SessionStart tier: refresh the overlay from the LIVE checkout.

    Re-composes from the current team folders (team identity from the staged
    meta), so a creator's edited or newly-added skills/agents/rules/context
    propagate on the next session — no cache rebuild, no manual step. compose
    writes only the overlay + the CLAUDE.local.md @import block + the bootstrap
    state files, so tracked base files (settings.json, base hooks) are never
    touched. The staged snapshot is kept only as a turn-1 seed (already present
    in the booted filesystem) and a last-known-good fallback.

    Re-compose is additive: adds and edits propagate, but a removed team
    artifact lingers until a cache rebuild or `reset` (#46).
    """
    src = staging.staged_claude_dir()
    if not src.is_dir():
        raise SystemExit(
            f"cloud --apply-only: staging dir {src} not found. "
            "The setup-script tier must run first (cloud --compose-only)."
        )
    meta = staging.read_meta()
    if meta is None:
        raise SystemExit(
            f"cloud --apply-only: staging meta {staging.meta_path()} not found. "
            "Setup-script tier did not complete cleanly; re-run it."
        )

    team = meta.get("team_input")
    log.step(f"cloud: re-composing overlay from the live checkout (team={team!r})")
    try:
        compose.run(argparse.Namespace(team=team))
    except SystemExit as e:
        # Live composition failed against the current checkout (e.g. a team
        # folder mid-rename or a transient ambiguity). Fall back to the
        # last-known-good staged overlay so the session still gets a working
        # composition rather than nothing.
        log.warn(f"cloud: live re-compose failed ({e}); falling back to staged overlay")
        _restore_overlay_from_staging(workspace_root, src, meta)

    # The platform re-installs the user-scope stop hook on every session start,
    # clobbering the setup-tier no-op. Re-apply it here, after that refresh, when
    # the setup tier recorded the intent — the per-session durability the
    # setup-tier write alone can't provide (see #72). Silent no-op when the hook
    # is absent (engineer-local) or the meta predates this field.
    if meta.get("disable_stop_hook"):
        _disable_stop_hook()

    personal.sync(workspace_root, os.environ.get("WORKSPACE_PERSONAL_GIST"))


def _restore_overlay_from_staging(workspace_root, src, meta):
    """Fallback for _apply_only: restore the composed overlay + bootstrap state
    files from the staged snapshot (the previous, copytree-free behavior). Used
    only when live re-composition fails.

    Restores ONLY the untracked artifacts the bootstrap owns — the gitignored
    state files and the overlay listed in the staged copied-files index. NEVER
    the git-tracked base files (settings.json, base hooks, base rules): the
    snapshot may be stale, and restoring them would silently revert committed
    changes, including security fixes.
    """
    dst = workspace_root / ".claude"
    copied = _staged_copied_files(src)
    try:
        for rel in (manifest_lib.MANIFEST_REL, manifest_lib.COPIED_FILES_REL):
            leaf = rel.split("/")[-1]
            s = src / leaf
            if s.is_file():
                d = dst / leaf
                d.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(s, d)
        for s, d in _overlay_pairs(workspace_root, src, copied):
            if s.is_file():
                d.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(s, d)
    except PermissionError as e:
        log.error(
            f"cloud --apply-only: permission denied writing to {dst}: {e}. "
            "Setup-tier writes may be root-owned and the session user cannot "
            "overwrite them. Re-run the setup script or chown the workspace."
        )
        raise

    compose.inject_team_imports(workspace_root, meta.get("chain_rel_paths", []))
    compose.write_git_exclude(workspace_root, copied)


def _staged_copied_files(staged_claude):
    """Read the copied-files index from the STAGED snapshot (authoritative).

    A fresh cloud clone has no copied-files in the working tree, so we read the
    one the setup tier staged. Entries are absolute paths recorded at compose
    time under <root>/.claude/...; _overlay_pairs re-anchors them.
    """
    leaf = manifest_lib.COPIED_FILES_REL.split("/")[-1]
    p = Path(staged_claude) / leaf
    if not p.is_file():
        return []
    return [ln for ln in p.read_text().splitlines() if ln.strip()]


def _overlay_pairs(workspace_root, staged_claude, copied_paths):
    """Map each composed artifact to (staged source, working destination).

    copied_paths are absolute paths under some <root>/.claude/. Re-anchor on the
    '/.claude/' segment so the mapping holds even if the snapshot was produced
    at a different absolute root than the current clone.
    """
    dst_claude = Path(workspace_root) / ".claude"
    marker = "/.claude/"
    pairs = []
    for p in copied_paths:
        s = str(p).replace("\\", "/")
        idx = s.find(marker)
        if idx == -1:
            continue
        rel = s[idx + len(marker):]
        pairs.append((Path(staged_claude) / rel, dst_claude / rel))
    return pairs


def _sync_personal(workspace_root, args):
    gist = getattr(args, "gist", None) or os.environ.get("WORKSPACE_PERSONAL_GIST")
    personal.sync(workspace_root, gist)
