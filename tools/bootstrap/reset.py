"""reset: undo composition.

Reverses everything `compose` writes so the next `compose` starts from a clean
slate (team switch, cache rebuild, or just recovering from a bad state). The
inverse of compose, step for step:

  1. Delete every file listed in .claude/.bootstrap-copied-files (the composed
     skills/agents/commands/rules/hooks), then prune the now-empty directories
     compose created under .claude/.
  2. Strip the team-context block from CLAUDE.local.md. Per #72 the team
     @import block lives in the gitignored CLAUDE.local.md - NOT the tracked
     root CLAUDE.md - so reset never touches a tracked file. Personal context
     below the block is preserved unless --personal is given.
  3. Remove the bootstrap state files: .claude/.bootstrap-manifest.json and
     .claude/.bootstrap-copied-files.
  4. Clear compose's marker block from .git/info/exclude.

--personal additionally clears the personal-context region of CLAUDE.local.md
(default keeps it). Note `reset` does NOT touch settings.json or base hooks:
compose never modifies them, so there is nothing to restore.

Idempotent: running reset on an already-clean workspace is a successful no-op.
After reset, a fresh `compose` reproduces exactly the same state.
"""

from pathlib import Path

from lib import localmd
from lib import log
from lib import manifest as manifest_lib
from lib import paths as path_lib

import compose


CLAUDE_DIR = ".claude"
PERSONAL_CONTEXT_REL = "CLAUDE.local.md"


def run(args):
    workspace_root = path_lib.require_workspace_root()
    clear_personal = bool(getattr(args, "personal", False))

    log.step(f"reset: undoing composition in {workspace_root}")

    deleted, pruned = _delete_copied_files(workspace_root)
    local_md_changed = _reset_local_md(workspace_root, clear_personal)
    state_removed = _remove_state_files(workspace_root)
    compose.clear_git_exclude(workspace_root)

    changed = bool(deleted or pruned or local_md_changed or state_removed)
    if not changed:
        log.ok("reset: nothing to undo; workspace already clean.")
        return 0

    log.ok(
        f"reset: removed {deleted} composed file(s), pruned {pruned} "
        f"director(ies), cleared bootstrap state."
    )
    if clear_personal:
        log.info("reset: personal context cleared (--personal).")
    return 0


def _delete_copied_files(workspace_root):
    """Delete every path in the copied-files index; prune dirs it leaves empty.

    Returns (deleted_count, pruned_dir_count). Missing entries are skipped
    quietly - reset is best-effort and must converge on a clean state even if a
    composed file was already removed by hand.
    """
    copied = manifest_lib.read_copied_files(workspace_root)
    deleted = 0
    parents = set()
    for entry in copied:
        p = Path(entry)
        if p.is_symlink() or p.exists():
            try:
                p.unlink()
                deleted += 1
                parents.add(p.parent)
            except OSError as e:
                log.warn(f"reset: could not remove {p} ({type(e).__name__}: {e})")
        else:
            log.dim(f"reset: already gone: {p}")
    pruned = _prune_empty_dirs(workspace_root, parents)
    return deleted, pruned


def _prune_empty_dirs(workspace_root, dirs):
    """Remove now-empty directories under .claude/, walking up toward .claude/.

    Only directories strictly below <root>/.claude/ are considered, and only
    while empty - base directories that still hold tracked artifacts (e.g.
    .claude/hooks with base hooks) are left alone. .claude/ itself is never
    removed. This mirrors a fresh checkout, where the composed dirs don't exist.
    """
    claude_dir = (Path(workspace_root) / CLAUDE_DIR).resolve()
    pruned = 0
    # Deepest-first so a child is gone before we test its parent.
    for d in sorted(dirs, key=lambda p: len(p.resolve().parts), reverse=True):
        cur = d.resolve()
        while cur != claude_dir and claude_dir in cur.parents:
            if not cur.is_dir() or any(cur.iterdir()):
                break
            try:
                cur.rmdir()
                pruned += 1
            except OSError:
                break
            cur = cur.parent
    return pruned


def _reset_local_md(workspace_root, clear_personal):
    """Strip compose's team block from CLAUDE.local.md (and personal if asked).

    Returns True when the file changed or was removed. Without --personal the
    personal region below the team block is preserved; with it, the whole file
    goes. A file that ends up empty is removed outright so the workspace matches
    a fresh, never-composed checkout.
    """
    local_md = Path(workspace_root) / PERSONAL_CONTEXT_REL
    if not local_md.is_file():
        return False

    original = local_md.read_text()
    new_text = "" if clear_personal else localmd.strip_team_block(original)

    if new_text.strip():
        if new_text != original:
            local_md.write_text(new_text)
            return True
        return False

    # Nothing meaningful left → remove the file entirely.
    local_md.unlink()
    return True


def _remove_state_files(workspace_root):
    """Remove the bootstrap manifest and copied-files index. Returns True if any existed."""
    removed = False
    for p in (
        manifest_lib.manifest_path(workspace_root),
        manifest_lib.copied_files_path(workspace_root),
    ):
        if p.is_file():
            p.unlink()
            removed = True
    return removed
