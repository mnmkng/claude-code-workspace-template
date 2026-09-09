"""Tests for tools/bootstrap/lib/paths.py."""

import os
import sys
import tempfile
import unittest
from pathlib import Path

# Make the bootstrap package importable when run from this file's directory or
# from the repo root via `python3 -m unittest discover`.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import paths as path_lib  # noqa: E402


def _make_workspace_root(tmpdir):
    """Create a minimal valid workspace root structure inside tmpdir."""
    root = Path(tmpdir).resolve() / "workspace"
    (root / ".claude").mkdir(parents=True)
    (root / ".claude" / "settings.json").write_text("{}")
    (root / "CLAUDE.md").write_text("# Workspace\n")
    (root / "departments").mkdir()
    return root


def _make_team(root, rel_path):
    """Create a team folder at root/rel_path with a CLAUDE.md placeholder."""
    p = root / rel_path
    p.mkdir(parents=True)
    (p / "CLAUDE.md").write_text(f"# {p.name}\n")
    return p


class FindWorkspaceRootTests(unittest.TestCase):

    def test_finds_root_from_root_itself(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _make_workspace_root(tmp)
            self.assertEqual(
                path_lib.find_workspace_root(root).resolve(),
                root.resolve(),
            )

    def test_finds_root_from_nested_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _make_workspace_root(tmp)
            nested = root / "departments" / "marketing" / "teams" / "content"
            nested.mkdir(parents=True)
            self.assertEqual(
                path_lib.find_workspace_root(nested).resolve(),
                root.resolve(),
            )

    def test_returns_none_outside_tree(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(path_lib.find_workspace_root(tmp))


class ResolveTeamTests(unittest.TestCase):

    def setUp(self):
        self._tmp_ctx = tempfile.TemporaryDirectory()
        self.tmp = self._tmp_ctx.name
        self.root = _make_workspace_root(self.tmp)

    def tearDown(self):
        self._tmp_ctx.cleanup()

    def test_unique_match(self):
        content = _make_team(self.root, "departments/marketing/teams/content")
        result = path_lib.resolve_team("content", self.root)
        self.assertEqual(result.resolve(), content.resolve())

    def test_no_match_lists_available(self):
        _make_team(self.root, "departments/marketing/teams/content")
        _make_team(self.root, "departments/sales")
        with self.assertRaises(SystemExit) as ctx:
            path_lib.resolve_team("nonexistent", self.root)
        msg = str(ctx.exception)
        self.assertIn("not found", msg)
        self.assertIn("content", msg)
        self.assertIn("sales", msg)

    def test_ambiguous_match_lists_paths(self):
        a = _make_team(self.root, "departments/marketing/teams/content")
        b = _make_team(self.root, "departments/customer-success/teams/content")
        with self.assertRaises(SystemExit) as ctx:
            path_lib.resolve_team("content", self.root)
        msg = str(ctx.exception)
        self.assertIn("ambiguous", msg)
        self.assertIn(str(a.relative_to(self.root)), msg)
        self.assertIn(str(b.relative_to(self.root)), msg)

    def test_claude_md_filter_excludes_incidental_names(self):
        # Real team:
        content = _make_team(self.root, "departments/marketing/teams/content")
        # Incidental directory with the same basename but no CLAUDE.md:
        incidental = self.root / "context" / "content"
        incidental.mkdir(parents=True)
        (incidental / "notes.md").write_text("not a team")
        result = path_lib.resolve_team("content", self.root)
        self.assertEqual(result.resolve(), content.resolve())

    def test_rejects_path_separator(self):
        with self.assertRaises(SystemExit) as ctx:
            path_lib.resolve_team("departments/marketing", self.root)
        self.assertIn("basename", str(ctx.exception))

    def test_rejects_empty_name(self):
        with self.assertRaises(SystemExit):
            path_lib.resolve_team("", self.root)

    def test_skips_projects_directory(self):
        # A team-shaped folder inside projects/ must NOT be matched (projects
        # is the ephemeral, gitignored workspace).
        ghost = _make_team(self.root, "projects/scratch/content")
        # Real team elsewhere is unambiguous:
        real = _make_team(self.root, "departments/marketing/teams/content")
        result = path_lib.resolve_team("content", self.root)
        self.assertEqual(result.resolve(), real.resolve())
        self.assertNotEqual(result.resolve(), ghost.resolve())


class TeamChainTests(unittest.TestCase):

    def setUp(self):
        self._tmp_ctx = tempfile.TemporaryDirectory()
        self.root = _make_workspace_root(self._tmp_ctx.name)

    def tearDown(self):
        self._tmp_ctx.cleanup()

    def test_chain_with_department_and_team(self):
        dept = _make_team(self.root, "departments/marketing")
        team = _make_team(self.root, "departments/marketing/teams/content")
        chain = path_lib.team_chain(team, self.root)
        self.assertEqual(
            [str(c.relative_to(self.root)) for c in chain],
            [str(dept.relative_to(self.root)), str(team.relative_to(self.root))],
        )

    def test_chain_at_department_level_only(self):
        dept = _make_team(self.root, "departments/marketing")
        chain = path_lib.team_chain(dept, self.root)
        self.assertEqual(len(chain), 1)
        self.assertEqual(chain[0].resolve(), dept.resolve())

    def test_chain_excludes_workspace_root(self):
        team = _make_team(self.root, "departments/marketing/teams/content")
        chain = path_lib.team_chain(team, self.root)
        for c in chain:
            self.assertNotEqual(c.resolve(), self.root.resolve())

    def test_chain_rejects_outside_root(self):
        with tempfile.TemporaryDirectory() as outside:
            with self.assertRaises(ValueError):
                path_lib.team_chain(Path(outside), self.root)

    def test_chain_rejects_root_itself(self):
        with self.assertRaises(ValueError):
            path_lib.team_chain(self.root, self.root)

    def test_chain_skips_ancestors_without_claude_md(self):
        # If a middle directory has no CLAUDE.md, it's excluded from the chain.
        dept = _make_team(self.root, "departments/marketing")
        # 'teams' has no CLAUDE.md by design; leaf is the team.
        team = _make_team(self.root, "departments/marketing/teams/content")
        chain = path_lib.team_chain(team, self.root)
        self.assertEqual(len(chain), 2)
        self.assertEqual(
            [c.name for c in chain],
            ["marketing", "content"],
        )


if __name__ == "__main__":
    unittest.main()
