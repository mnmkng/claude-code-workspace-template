"""workspace-root detection and team-name resolution.

These helpers are shared by every subcommand. Detection mirrors
scripts/claude.sh: walk up from a starting directory looking for the three
markers (.claude/settings.json + CLAUDE.md + departments/).
"""

from pathlib import Path


# All three must be present to count as an workspace root. Avoids false positives
# on unrelated repos that happen to have a .claude/ directory.
WORKSPACE_ROOT_MARKERS = (".claude/settings.json", "CLAUDE.md", "departments")


def _walk_up(start):
    p = Path(start).resolve()
    candidates = [p] + list(p.parents)
    for d in candidates:
        if all((d / m).exists() for m in WORKSPACE_ROOT_MARKERS):
            return d
    return None


def find_workspace_root(start=None):
    """Return the workspace root, or None.

    With `start` explicit: walks up from `start` only.
    With `start=None`: walks up from cwd, then from this module's directory
    (useful when the tool is invoked from outside the tree, e.g. by a setup
    script with a different cwd).
    """
    if start is not None:
        return _walk_up(start)
    for candidate in (Path.cwd(), Path(__file__).resolve().parent):
        result = _walk_up(candidate)
        if result is not None:
            return result
    return None


def require_workspace_root(start=None):
    root = find_workspace_root(start)
    if root is None:
        raise SystemExit(
            "workspace root not found. Run from inside a workspace "
            "(must contain .claude/settings.json, CLAUDE.md, and departments/)."
        )
    return root


# Directories we never descend into when resolving a team name. `projects/` is
# ephemeral/gitignored and may contain anything; .git/ is irrelevant; node_modules
# guards against vendored workspace-like trees in nested projects.
SKIP_DIRS = {".git", "node_modules", "projects"}


def _iter_candidate_dirs(workspace_root, name):
    """Yield directories under workspace_root with basename == name, skipping noise."""
    for path in workspace_root.rglob(name):
        if not path.is_dir():
            continue
        if path == workspace_root:
            continue
        # Skip if any ancestor is in SKIP_DIRS.
        try:
            rel_parts = path.relative_to(workspace_root).parts
        except ValueError:
            continue
        if any(part in SKIP_DIRS for part in rel_parts):
            continue
        yield path


def resolve_team(name, workspace_root):
    """Find the unique directory whose basename matches `name` AND contains CLAUDE.md.

    The CLAUDE.md filter distinguishes real team folders from incidental name
    collisions (e.g., a 'content' folder inside someone's context/ directory).

    Raises SystemExit on no match or ambiguous match, with a helpful message.
    """
    if not name:
        raise SystemExit("Team name required: pass --team (or set the WORKSPACE_TEAM env var).")
    if "/" in name or "\\" in name:
        raise SystemExit(f"Team must be a folder basename, not a path: {name!r}")

    matches = [
        p for p in _iter_candidate_dirs(workspace_root, name)
        if (p / "CLAUDE.md").is_file()
    ]

    if not matches:
        available = sorted({
            md.parent.name
            for md in workspace_root.rglob("CLAUDE.md")
            if md.parent != workspace_root
            and not any(part in SKIP_DIRS for part in md.parent.relative_to(workspace_root).parts)
        })
        raise SystemExit(
            f"Team {name!r} not found. Available teams: {available}"
        )
    if len(matches) > 1:
        rels = [str(m.relative_to(workspace_root)) for m in matches]
        raise SystemExit(
            f"Team name {name!r} is ambiguous. Matches: {rels}. "
            "Folder names that contain a CLAUDE.md must be globally unique."
        )
    return matches[0]


def team_chain(target, workspace_root):
    """Return the ancestor chain of `target` that contain CLAUDE.md.

    Ordered outermost-first; includes `target` itself as the last element.
    Excludes `workspace_root` (its CLAUDE.md is handled separately).
    """
    target = Path(target).resolve()
    workspace_root = Path(workspace_root).resolve()
    try:
        target.relative_to(workspace_root)
    except ValueError as e:
        raise ValueError(
            f"target {target} must be inside workspace_root {workspace_root}"
        ) from e
    if target == workspace_root:
        raise ValueError("target must be a strict subpath of workspace_root")

    chain = []
    cur = target
    while cur != workspace_root:
        if (cur / "CLAUDE.md").is_file():
            chain.append(cur)
        cur = cur.parent
    return list(reversed(chain))
