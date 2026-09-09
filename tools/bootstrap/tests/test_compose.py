"""Tests for tools/bootstrap/compose.py, focused on root / no-team mode (#64)."""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import compose  # noqa: E402
from lib import localmd  # noqa: E402
from lib import manifest as manifest_lib  # noqa: E402


def _make_workspace(root: Path):
    """Minimal workspace-root-shaped tree with one team (foo) that has a skill."""
    (root / "CLAUDE.md").write_text("# root\n")
    (root / ".claude").mkdir()
    (root / ".claude" / "settings.json").write_text("{}\n")
    foo = root / "departments" / "foo"
    foo.mkdir(parents=True)
    (foo / "CLAUDE.md").write_text("# foo team\n")
    skill = foo / ".claude" / "skills" / "foo-skill"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("skill body\n")


class ComposeRootModeTests(unittest.TestCase):
    def setUp(self):
        os.environ["NO_COLOR"] = "1"
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()
        _make_workspace(self.root)
        os.environ.pop("WORKSPACE_TEAM", None)
        self._patch = patch(
            "compose.path_lib.require_workspace_root", return_value=self.root
        )
        self._patch.start()

    def tearDown(self):
        self._patch.stop()
        self._tmp.cleanup()
        os.environ.pop("WORKSPACE_TEAM", None)

    def _run(self, team):
        return compose.run(argparse.Namespace(team=team))

    def test_root_sentinel_short_circuits_resolution(self):
        with patch("compose.path_lib.resolve_team") as mock_resolve:
            self._run("root")
        mock_resolve.assert_not_called()
        manifest = manifest_lib.read(self.root)
        self.assertEqual(manifest["levels"], [])
        self.assertTrue(manifest["root"])
        self.assertEqual(manifest["team_input"], "root")
        self.assertEqual(manifest["team_resolved_path"], ".")

    def test_root_sentinel_case_insensitive(self):
        with patch("compose.path_lib.resolve_team") as mock_resolve:
            self._run("Root")
        mock_resolve.assert_not_called()
        manifest = manifest_lib.read(self.root)
        # Canonicalized to lowercase so re-runs stay idempotent.
        self.assertEqual(manifest["team_input"], "root")
        self.assertTrue(manifest["root"])

    def test_root_copies_no_team_artifacts(self):
        self._run("root")
        self.assertFalse((self.root / ".claude" / "skills" / "foo-skill").exists())
        self.assertEqual(manifest_lib.read_copied_files(self.root), [])

    def test_root_mode_leaves_claude_md_untouched(self):
        self._run("root")
        # #72: composition never modifies the tracked CLAUDE.md.
        self.assertEqual((self.root / "CLAUDE.md").read_text(), "# root\n")
        # Root mode has no team chain → no team-context block is written.
        local_md = self.root / "CLAUDE.local.md"
        if local_md.is_file():
            self.assertNotIn(localmd.TEAM_START, local_md.read_text())

    def test_root_via_env_var(self):
        os.environ["WORKSPACE_TEAM"] = "root"
        with patch("compose.path_lib.resolve_team") as mock_resolve:
            compose.run(argparse.Namespace())
        mock_resolve.assert_not_called()
        self.assertTrue(manifest_lib.read(self.root)["root"])

    def test_team_flag_overrides_env_root(self):
        # WORKSPACE_TEAM=root (root) but an explicit --team foo composes foo.
        os.environ["WORKSPACE_TEAM"] = "root"
        compose.run(argparse.Namespace(team="foo"))
        manifest = manifest_lib.read(self.root)
        self.assertFalse(manifest["root"])
        self.assertEqual(manifest["team_input"], "foo")
        self.assertTrue(
            (self.root / ".claude" / "skills" / "foo-skill" / "SKILL.md").is_file()
        )

    def test_unset_team_errors(self):
        with self.assertRaises(SystemExit) as cm:
            compose.run(argparse.Namespace(team=None))
        self.assertIn("required", str(cm.exception))

    def test_switch_from_root_requires_reset(self):
        self._run("root")
        with self.assertRaises(SystemExit) as cm:
            compose.run(argparse.Namespace(team="foo"))
        self.assertIn("reset", str(cm.exception))

    def test_root_reapply_idempotent(self):
        self._run("root")
        # Re-running root (even with different casing) must not raise and must
        # not accumulate state in CLAUDE.md or a team block.
        self._run("Root")
        self.assertEqual((self.root / "CLAUDE.md").read_text(), "# root\n")
        local_md = self.root / "CLAUDE.local.md"
        if local_md.is_file():
            self.assertEqual(local_md.read_text().count(localmd.TEAM_START), 0)


class ComposeTeamSettingsRegressionTests(unittest.TestCase):
    """Issue #141: a team-folder settings.json must NEVER be composed to root.

    compose copies only skills/agents/commands/rules/hooks, so it skips
    settings.json naturally today - these tests lock that in so a future
    artifact-list extension can't let a stamped team copy clobber the root
    security settings in cloud sessions.
    """

    def setUp(self):
        os.environ["NO_COLOR"] = "1"
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()
        _make_workspace(self.root)
        foo_claude = self.root / "departments" / "foo" / ".claude"
        (foo_claude / "settings.json").write_text('{"stamped": "team copy"}\n')
        hooks = foo_claude / "hooks"
        hooks.mkdir()
        (hooks / "foo-hook.sh").write_text("#!/bin/sh\nexit 0\n")
        os.environ.pop("WORKSPACE_TEAM", None)
        self._patch = patch(
            "compose.path_lib.require_workspace_root", return_value=self.root
        )
        self._patch.start()

    def tearDown(self):
        self._patch.stop()
        self._tmp.cleanup()
        os.environ.pop("WORKSPACE_TEAM", None)

    def test_team_settings_json_never_composed_to_root(self):
        compose.run(argparse.Namespace(team="foo"))
        # Root settings untouched, byte for byte.
        self.assertEqual(
            (self.root / ".claude" / "settings.json").read_text(), "{}\n"
        )
        # And no settings.json anywhere in the copied-files index.
        copied = manifest_lib.read_copied_files(self.root)
        self.assertFalse(
            [p for p in copied if p.endswith("settings.json")],
            f"compose copied a settings.json: {copied}",
        )
        # Sanity: composition itself ran (the sibling hook artifact copied).
        self.assertIn(
            str(self.root / ".claude" / "hooks" / "foo-hook.sh"), copied
        )


class InjectTeamImportsTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()
        # The committed CLAUDE.md ends with @CLAUDE.local.md; keep a stand-in so
        # we can assert it is never modified.
        self.claude_md_text = "# root\n@CLAUDE.local.md"
        (self.root / "CLAUDE.md").write_text(self.claude_md_text)
        self.local = self.root / "CLAUDE.local.md"

    def tearDown(self):
        self._tmp.cleanup()

    def test_empty_chain_writes_no_team_block(self):
        compose.inject_team_imports(self.root, [])
        # Nothing to import → no CLAUDE.local.md created, CLAUDE.md untouched.
        self.assertFalse(self.local.is_file())
        self.assertEqual((self.root / "CLAUDE.md").read_text(), self.claude_md_text)

    def test_team_chain_lands_in_local_md_not_claude_md(self):
        compose.inject_team_imports(self.root, ["departments/foo"])
        text = self.local.read_text()
        self.assertIn(localmd.TEAM_START, text)
        self.assertIn("@departments/foo/CLAUDE.md", text)
        self.assertIn(localmd.TEAM_END, text)
        # The tracked CLAUDE.md must not be touched (the whole point of #72).
        self.assertEqual((self.root / "CLAUDE.md").read_text(), self.claude_md_text)

    def test_preserves_personal_content_below_block(self):
        self.local.write_text("# personal notes\nremember X\n")
        compose.inject_team_imports(self.root, ["departments/foo"])
        text = self.local.read_text()
        self.assertIn("remember X", text)
        # Team block sits above the personal content.
        self.assertLess(text.index(localmd.TEAM_START), text.index("personal notes"))

    def test_idempotent_single_block(self):
        compose.inject_team_imports(self.root, ["departments/foo"])
        compose.inject_team_imports(self.root, ["departments/foo"])
        text = self.local.read_text()
        self.assertEqual(text.count(localmd.TEAM_START), 1)
        self.assertEqual(text.count(localmd.TEAM_END), 1)

    def test_rechain_replaces_block_without_stacking(self):
        compose.inject_team_imports(self.root, ["departments/foo"])
        compose.inject_team_imports(
            self.root, ["departments/bar", "departments/bar/teams/baz"])
        text = self.local.read_text()
        self.assertEqual(text.count(localmd.TEAM_START), 1)
        self.assertNotIn("@departments/foo/CLAUDE.md", text)
        self.assertIn("@departments/bar/CLAUDE.md", text)
        self.assertIn("@departments/bar/teams/baz/CLAUDE.md", text)


@unittest.skipUnless(shutil.which("git"), "git not available")
class WriteGitExcludeTests(unittest.TestCase):
    def setUp(self):
        os.environ["NO_COLOR"] = "1"
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        self.exclude = self.root / ".git" / "info" / "exclude"

    def tearDown(self):
        self._tmp.cleanup()

    def _make_artifact(self, relpath):
        f = self.root / relpath
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("x")
        return f

    def _status(self):
        return subprocess.run(
            ["git", "-C", str(self.root), "status", "--porcelain"],
            capture_output=True, text=True, check=True,
        ).stdout

    def test_writes_anchored_repo_relative_paths(self):
        f = self._make_artifact(".claude/skills/t/SKILL.md")
        compose.write_git_exclude(self.root, [str(f)])
        text = self.exclude.read_text()
        self.assertIn(compose.EXCLUDE_START, text)
        self.assertIn("/.claude/skills/t/SKILL.md", text)
        self.assertIn(compose.EXCLUDE_END, text)

    def test_excluded_artifact_drops_out_of_git_status(self):
        f = self._make_artifact(".claude/skills/t/SKILL.md")
        # git collapses an all-untracked dir to a single `?? .claude/` entry.
        self.assertIn(".claude/", self._status())  # untracked before
        compose.write_git_exclude(self.root, [str(f)])
        self.assertNotIn(".claude/", self._status())  # excluded after

    def test_idempotent_single_region(self):
        f = self._make_artifact(".claude/skills/t/SKILL.md")
        compose.write_git_exclude(self.root, [str(f)])
        compose.write_git_exclude(self.root, [str(f)])
        self.assertEqual(self.exclude.read_text().count(compose.EXCLUDE_START), 1)

    def test_preserves_pre_existing_user_excludes(self):
        self.exclude.write_text("*.log\n")
        f = self._make_artifact(".claude/skills/t/SKILL.md")
        compose.write_git_exclude(self.root, [str(f)])
        text = self.exclude.read_text()
        self.assertIn("*.log", text)
        self.assertIn(compose.EXCLUDE_START, text)

    def test_rechain_regenerates_region(self):
        a = self._make_artifact(".claude/skills/a/SKILL.md")
        compose.write_git_exclude(self.root, [str(a)])
        b = self._make_artifact(".claude/skills/b/SKILL.md")
        compose.write_git_exclude(self.root, [str(b)])
        text = self.exclude.read_text()
        self.assertNotIn("/.claude/skills/a/SKILL.md", text)
        self.assertIn("/.claude/skills/b/SKILL.md", text)

    def test_ignores_paths_outside_root(self):
        compose.write_git_exclude(self.root, ["/etc/passwd"])
        # No anchored entry for an out-of-tree path; region stays empty/clean.
        text = self.exclude.read_text() if self.exclude.is_file() else ""
        self.assertNotIn("/etc/passwd", text)

    def test_non_git_dir_is_silent_noop(self):
        with tempfile.TemporaryDirectory() as plain:
            proot = Path(plain)
            compose.write_git_exclude(proot, [str(proot / ".claude" / "x")])
            self.assertFalse((proot / ".git" / "info" / "exclude").exists())


if __name__ == "__main__":
    unittest.main()
