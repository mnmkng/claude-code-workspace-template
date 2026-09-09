"""compose: copy team artifacts up to the root .claude/.

Composition flow:
  1. Resolve WORKSPACE_TEAM (or --team) to a unique directory whose basename
     matches AND contains CLAUDE.md.
  2. Walk UP from that directory to (but excluding) the workspace root,
     collecting every ancestor that contains a CLAUDE.md.  Order the chain
     outermost-first so deeper levels override.
  3. For each level, copy artifacts from <level>/.claude/{skills,agents,
     commands,rules,hooks} into the root .claude/.  Rules get a level-name
     prefix to avoid collisions; hooks fail loudly on collision because hook
     names are referenced from settings.json.
  4. Write the team-chain @import block into the gitignored CLAUDE.local.md
     (NOT the tracked CLAUDE.md - see #72).  The team CLAUDE.md files are not
     copied; their relative paths and further @imports keep working from their
     original locations.
  5. Write the manifest + the flat copied-files index for reset to undo, and
     list the copied (untracked) artifacts in .git/info/exclude so they don't
     dirty the worktree.

Idempotency: running compose twice with the same WORKSPACE_TEAM is safe — every
write is regenerated from scratch.  Running with a different team after a
prior compose errors with instructions to run `reset` first.

Root mode: the sentinel team name "root" (case-insensitive, via --team root
or WORKSPACE_TEAM=root) stages the base workspace with no team overlay.  Team
resolution is skipped, the chain is empty, no artifacts are copied, no team
block is written to CLAUDE.local.md, and the manifest records root: true with
levels: [].  "root" never collides with a real team folder, so an unset team
stays a loud error rather than silently defaulting to root.
"""

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from lib import localmd
from lib import log
from lib import manifest as manifest_lib
from lib import paths as path_lib


CLAUDE_DIR = ".claude"

# Marker region in .git/info/exclude listing the composed (untracked) artifacts
# so the worktree stays clean. info/exclude only affects untracked files, which
# is exactly what the composed skills/agents/commands/rules/hooks are; a tracked
# base file overwritten by a same-named team artifact would still show (which we
# want to see).
EXCLUDE_START = "# WORKSPACE-BOOTSTRAP:BEGIN - composed artifacts (generated; do not edit)"
EXCLUDE_END = "# WORKSPACE-BOOTSTRAP:END"

# Matches the whole marker block (markers included) so both write_git_exclude
# and reset's clear_git_exclude can find and replace/remove it.
_EXCLUDE_BLOCK_RE = re.compile(
    re.escape(EXCLUDE_START) + r".*?" + re.escape(EXCLUDE_END) + r"[^\n]*\n?",
    re.DOTALL,
)

# Personal context file. Gitignored, root-level; the cloud workflow writes
# fetched gist content here, engineers may author it manually. Path is at
# repo root so it mirrors CLAUDE.md naming and gets `.local.` semantics
# (parity with settings.local.json). @import of a missing file is a silent
# skip (per #41 Q2 finding), so absence is harmless.
PERSONAL_CONTEXT_REL = "CLAUDE.local.md"

# Sentinel team name selecting root / no-team mode: stage the base workspace
# with no team overlay. Case-insensitive. Never collides with a real team
# folder (no team is named "root", and resolve_team skips the repo root), so
# an unset team can stay a hard error instead of silently meaning root.
ROOT_SENTINEL = "root"


def _is_root_sentinel(team_input):
    return team_input.strip().lower() == ROOT_SENTINEL


def run(args):
    raw = (
        getattr(args, "team", None)
        or os.environ.get("WORKSPACE_TEAM")
    )
    if not raw:
        raise SystemExit(
            "compose: --team flag required (or the WORKSPACE_TEAM env var) "
            "(use --team root for the base workspace / no-team mode)."
        )

    root_mode = _is_root_sentinel(raw)
    # Canonicalize the sentinel so re-runs with different casing (root/Root/
    # ROOT) are idempotent and don't trip the manifest "different team" guard.
    team_input = ROOT_SENTINEL if root_mode else raw

    workspace_root = path_lib.require_workspace_root()

    if root_mode:
        target = None
        chain = []
    else:
        # Validate team before checking manifest, so unknown-team errors win
        # over "already composed for a different team" errors.
        target = path_lib.resolve_team(team_input, workspace_root)
        chain = path_lib.team_chain(target, workspace_root)
        if not chain:
            raise SystemExit(
                f"compose: team {team_input!r} resolved to {target}, "
                "but no CLAUDE.md was found in it or any ancestor below the root."
            )

    existing = manifest_lib.read(workspace_root)
    if existing is not None:
        prior = existing.get("team_input")
        if prior != team_input:
            raise SystemExit(
                f"compose: workspace already composed for team {prior!r}. "
                f"Run `python3 tools/bootstrap/bootstrap.py reset` first to "
                f"switch to {team_input!r}."
            )
        log.info(f"compose: re-applying composition for team {team_input!r}")

    if root_mode:
        log.step("Composing root (no team overlay; base workspace only)")
    else:
        log.step(
            f"Composing team {team_input!r} → "
            f"{target.relative_to(workspace_root)}"
        )
        for level in chain:
            log.info(f"  level: {level.relative_to(workspace_root)}")

    copied_paths = []
    levels_summary = []
    state = {
        "skill_owners": {},
        "agent_owners": {},
        "command_owners": {},
        "hook_owners": {},
    }

    for level in chain:
        summary = _compose_level(workspace_root, level, state, copied_paths)
        levels_summary.append(summary)

    chain_rel_paths = [str(level.relative_to(workspace_root)) for level in chain]
    inject_team_imports(workspace_root, chain_rel_paths)

    manifest_lib.write(workspace_root, {
        "team_input": team_input,
        "team_resolved_path": "." if root_mode else str(target.relative_to(workspace_root)),
        "root": root_mode,
        "composed_at": manifest_lib.now_iso(),
        "tool_version": manifest_lib.MANIFEST_VERSION,
        "levels": levels_summary,
    })
    manifest_lib.write_copied_files(workspace_root, copied_paths)
    write_git_exclude(workspace_root, copied_paths)

    if root_mode:
        log.ok("Composition complete. Root mode: no team artifacts copied.")
    else:
        log.ok(
            f"Composition complete. "
            f"{len(copied_paths)} file(s) copied across {len(chain)} level(s)."
        )
    return 0


def _compose_level(workspace_root, level, state, copied_paths):
    """Copy artifacts from one chain level into the root .claude/."""
    dest_claude = workspace_root / CLAUDE_DIR
    level_rel = str(level.relative_to(workspace_root))
    src_claude = level / CLAUDE_DIR

    summary = {
        "path": level_rel,
        "skills_added": [],
        "skills_overridden": [],
        "agents_added": [],
        "agents_overridden": [],
        "commands_added": [],
        "commands_overridden": [],
        "rules_added": [],
        "hooks_added": [],
        "claude_md": (level / "CLAUDE.md").is_file(),
    }

    if not src_claude.is_dir():
        return summary

    _compose_skills(src_claude, dest_claude, level_rel, state, copied_paths, summary)
    _compose_agents(src_claude, dest_claude, level_rel, state, copied_paths, summary)
    _compose_commands(src_claude, dest_claude, level_rel, state, copied_paths, summary)
    _compose_rules(src_claude, dest_claude, level, copied_paths, summary)
    _compose_hooks(src_claude, dest_claude, level_rel, state, copied_paths, summary)

    return summary


def _compose_skills(src_claude, dest_claude, level_rel, state, copied_paths, summary):
    src = src_claude / "skills"
    if not src.is_dir():
        return
    for sk in sorted(src.iterdir()):
        if not sk.is_dir() or sk.name.startswith("."):
            continue
        dest = dest_claude / "skills" / sk.name
        prior = state["skill_owners"].get(sk.name)
        if prior:
            shutil.rmtree(dest, ignore_errors=True)
            summary["skills_overridden"].append(sk.name)
            log.warn(f"  skill {sk.name!r} from {level_rel} overrides {prior}")
        else:
            summary["skills_added"].append(sk.name)
        _copytree(sk, dest, copied_paths)
        state["skill_owners"][sk.name] = level_rel


def _compose_agents(src_claude, dest_claude, level_rel, state, copied_paths, summary):
    src = src_claude / "agents"
    if not src.is_dir():
        return
    for ag in sorted(src.iterdir()):
        if ag.name.startswith("."):
            continue
        if ag.is_file() and ag.suffix == ".md":
            name = ag.stem
            dest = dest_claude / "agents" / ag.name
        elif ag.is_dir():
            name = ag.name
            dest = dest_claude / "agents" / ag.name
        else:
            continue
        prior = state["agent_owners"].get(name)
        if prior:
            if dest.is_dir():
                shutil.rmtree(dest, ignore_errors=True)
            elif dest.is_file():
                dest.unlink()
            summary["agents_overridden"].append(name)
            log.warn(f"  agent {name!r} from {level_rel} overrides {prior}")
        else:
            summary["agents_added"].append(name)
        if ag.is_file():
            _copyfile(ag, dest, copied_paths)
        else:
            _copytree(ag, dest, copied_paths)
        state["agent_owners"][name] = level_rel


def _compose_commands(src_claude, dest_claude, level_rel, state, copied_paths, summary):
    src = src_claude / "commands"
    if not src.is_dir():
        return
    for cmd in sorted(src.iterdir()):
        if not cmd.is_file() or cmd.suffix != ".md":
            continue
        name = cmd.stem
        dest = dest_claude / "commands" / cmd.name
        prior = state["command_owners"].get(name)
        if prior:
            if dest.exists():
                dest.unlink()
            summary["commands_overridden"].append(name)
            log.warn(f"  command {name!r} from {level_rel} overrides {prior}")
        else:
            summary["commands_added"].append(name)
        _copyfile(cmd, dest, copied_paths)
        state["command_owners"][name] = level_rel


def _compose_rules(src_claude, dest_claude, level, copied_paths, summary):
    src = src_claude / "rules"
    if not src.is_dir():
        return
    prefix = level.name
    for rule in sorted(src.iterdir()):
        if not rule.is_file() or rule.suffix != ".md":
            continue
        new_name = f"{prefix}-{rule.name}"
        dest = dest_claude / "rules" / new_name
        _copyfile(rule, dest, copied_paths)
        summary["rules_added"].append(new_name)


def _compose_hooks(src_claude, dest_claude, level_rel, state, copied_paths, summary):
    src = src_claude / "hooks"
    if not src.is_dir():
        return
    for hook in sorted(src.iterdir()):
        if not hook.is_file():
            continue
        dest = dest_claude / "hooks" / hook.name
        if hook.name in state["hook_owners"]:
            raise SystemExit(
                f"compose: hook name collision: {hook.name!r} appears in both "
                f"{state['hook_owners'][hook.name]!r} and {level_rel!r}. "
                "Hook names must be globally unique because they are referenced "
                "from settings.json. Rename one of them."
            )
        # Don't clobber pre-existing root hooks (those are managed by the
        # team config, not by composition).
        if dest.exists():
            raise SystemExit(
                f"compose: hook {hook.name!r} from {level_rel!r} would overwrite "
                f"an existing root hook at {dest}. Rename the team hook."
            )
        _copyfile(hook, dest, copied_paths)
        os.chmod(dest, 0o755)
        summary["hooks_added"].append(hook.name)
        state["hook_owners"][hook.name] = level_rel


def _copyfile(src, dst, copied_paths):
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    copied_paths.append(str(dst))


def _copytree(src, dst, copied_paths):
    """Recursive file copy; records every destination file path."""
    for srcpath in src.rglob("*"):
        if srcpath.is_dir():
            continue
        if srcpath.is_symlink():
            # Skip symlinks defensively; the source tree shouldn't contain
            # any but we don't want to materialize external targets if it does.
            continue
        rel = srcpath.relative_to(src)
        dstpath = dst / rel
        dstpath.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(srcpath, dstpath)
        copied_paths.append(str(dstpath))


def inject_team_imports(workspace_root, chain_rel_paths):
    """Maintain the team-chain @import block in the gitignored CLAUDE.local.md.

    Shared by `compose.run` (full composition) and `cloud._apply_only` (warm
    re-apply from staged meta). Replaces compose's former marker block in the
    tracked CLAUDE.md (see #72): writing the imports into CLAUDE.local.md - which
    is gitignored - keeps composition out of any tracked file, so the worktree
    no longer goes dirty every session.

    Idempotent, and preserves the personal-context region: it rewrites only the
    team block, leaving whatever personal.py (or an engineer) wrote below it.
    Root / no-team mode (empty chain) writes no team block at all.

    Args:
        workspace_root: Path to repo root.
        chain_rel_paths: list[str] of level paths relative to workspace_root, forward
            slashed (e.g. ["departments/marketing", ".../teams/content"]).
    """
    local_md = Path(workspace_root) / PERSONAL_CONTEXT_REL
    existing = local_md.read_text() if local_md.is_file() else ""
    block = localmd.team_block_text([str(r) for r in chain_rel_paths])
    new_text = localmd.join(block, localmd.strip_team_block(existing))
    if new_text != existing:
        local_md.write_text(new_text)


def _exclude_path(workspace_root):
    """Resolve the repo's .git/info/exclude path, or None when git is unavailable.

    Honors worktrees/submodules via `git rev-parse --git-path`. Returns None
    (after a dim log) when git isn't installed or the root isn't a work tree -
    the engineer edge cases and test temps where there's nothing to exclude.
    """
    try:
        out = subprocess.run(
            ["git", "-C", str(workspace_root), "rev-parse", "--git-path", "info/exclude"],
            capture_output=True, text=True, check=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError) as e:
        log.dim(f"compose: skipping .git/info/exclude ({type(e).__name__})")
        return None

    exclude_path = Path(out.stdout.strip())
    if not exclude_path.is_absolute():
        exclude_path = Path(workspace_root) / exclude_path
    return exclude_path


def write_git_exclude(workspace_root, copied_paths):
    """List the composed (untracked) artifacts in .git/info/exclude.

    The composed skills/agents/commands/rules/hooks are untracked additions to
    the worktree; left alone they show up in `git status` and trip the platform's
    Stop hook. Excluding the exact copied files (anchored, repo-relative) hides
    them without touching the tracked base artifacts that live in the same dirs.

    Per-clone and regenerated each run - never committed. Silent no-op when git
    is absent or the root is not a work tree (engineer edge cases, test temps).
    """
    exclude_path = _exclude_path(workspace_root)
    if exclude_path is None:
        return

    root = Path(workspace_root).resolve()
    rels = []
    for p in copied_paths:
        try:
            rel = Path(p).resolve().relative_to(root)
        except ValueError:
            continue  # outside the root (shouldn't happen); never exclude it
        rels.append("/" + str(rel).replace("\\", "/"))

    body_lines = [EXCLUDE_START]
    body_lines.extend(sorted(set(rels)))
    body_lines.append(EXCLUDE_END)
    desired_block = "\n".join(body_lines) + "\n"

    existing = exclude_path.read_text() if exclude_path.is_file() else ""
    match = _EXCLUDE_BLOCK_RE.search(existing)
    if match:
        new_text = existing[:match.start()] + desired_block + existing[match.end():]
    elif rels:
        sep = "" if (not existing or existing.endswith("\n")) else "\n"
        new_text = existing + sep + desired_block
    else:
        return  # nothing composed and no prior block → leave the file untouched

    if new_text != existing:
        exclude_path.parent.mkdir(parents=True, exist_ok=True)
        exclude_path.write_text(new_text)


def clear_git_exclude(workspace_root):
    """Remove the composed-artifacts marker block from .git/info/exclude.

    The inverse of write_git_exclude, used by `reset`: strips the entire block
    (markers included) while preserving any user-authored excludes around it.
    Silent no-op when git is unavailable, the exclude file is missing, or no
    block is present.
    """
    exclude_path = _exclude_path(workspace_root)
    if exclude_path is None or not exclude_path.is_file():
        return
    existing = exclude_path.read_text()
    new_text = _EXCLUDE_BLOCK_RE.sub("", existing, count=1)
    if new_text != existing:
        exclude_path.write_text(new_text)
