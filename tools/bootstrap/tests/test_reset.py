"""Tests for tools/bootstrap/reset.py (undo composition, issue #46)."""

import argparse
import json
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
import reset  # noqa: E402
from lib import localmd  # noqa: E402
from lib import manifest as manifest_lib  # noqa: E402


SETTINGS_JSON = json.dumps({
    "permissions": {"deny": ["Read(~/.ssh/**)"]},
    "sandbox": {"enabled": True},
}) + "\n"


def _make_workspace(root: Path):
    """workspace-root tree with a marketing department + nested blog team.

    Exercises every composed artifact type: skill (dir), agent (file), rule,
    command, and hook, across a two-level chain (mktg → blog).
    """
    (root / "CLAUDE.md").write_text("# root\n@CLAUDE.local.md")
    (root / ".claude").mkdir()
    (root / ".claude" / "settings.json").write_text(SETTINGS_JSON)

    mktg = root / "departments" / "mktg"
    mktg.mkdir(parents=True)
    (mktg / "CLAUDE.md").write_text("# mktg\n")
    (mktg / ".claude" / "skills" / "dept-skill").mkdir(parents=True)
    (mktg / ".claude" / "skills" / "dept-skill" / "SKILL.md").write_text("dept skill\n")
    (mktg / ".claude" / "agents").mkdir()
    (mktg / ".claude" / "agents" / "dept-agent.md").write_text("dept agent\n")
    (mktg / ".claude" / "rules").mkdir()
    (mktg / ".claude" / "rules" / "voice.md").write_text("voice rule\n")

    blog = mktg / "teams" / "blog"
    blog.mkdir(parents=True)
    (blog / "CLAUDE.md").write_text("# blog\n")
    (blog / ".claude" / "skills" / "blog-skill").mkdir(parents=True)
    (blog / ".claude" / "skills" / "blog-skill" / "SKILL.md").write_text("blog skill\n")
    (blog / ".claude" / "commands").mkdir()
    (blog / ".claude" / "commands" / "post.md").write_text("post command\n")
    (blog / ".claude" / "hooks").mkdir()
    (blog / ".claude" / "hooks" / "blog-hook.sh").write_text("#!/bin/sh\necho hi\n")


@unittest.skipUnless(shutil.which("git"), "git not available")
class ResetTests(unittest.TestCase):
    def setUp(self):
        os.environ["NO_COLOR"] = "1"
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()
        _make_workspace(self.root)
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        os.environ.pop("WORKSPACE_TEAM", None)
        self._patch = patch(
            "lib.paths.require_workspace_root", return_value=self.root
        )
        self._patch.start()
        self.claude = self.root / ".claude"
        self.local_md = self.root / "CLAUDE.local.md"

    def tearDown(self):
        self._patch.stop()
        self._tmp.cleanup()
        os.environ.pop("WORKSPACE_TEAM", None)

    def _compose(self, team="blog"):
        compose.run(argparse.Namespace(team=team))

    def _reset(self, personal=False):
        return reset.run(argparse.Namespace(personal=personal))

    # --- copied files + dir pruning -------------------------------------

    def test_deletes_every_copied_file(self):
        self._compose()
        copied = manifest_lib.read_copied_files(self.root)
        self.assertTrue(copied)
        for p in copied:
            self.assertTrue(Path(p).is_file(), f"{p} should exist after compose")
        self._reset()
        for p in copied:
            self.assertFalse(Path(p).exists(), f"{p} should be gone after reset")

    def test_prunes_composed_dirs_but_keeps_base(self):
        self._compose()
        self.assertTrue((self.claude / "skills" / "blog-skill").is_dir())
        self._reset()
        for sub in ("skills", "agents", "rules", "commands", "hooks"):
            self.assertFalse((self.claude / sub).exists(), f".claude/{sub} not pruned")
        # The base .claude/ and its tracked settings.json survive.
        self.assertTrue(self.claude.is_dir())
        self.assertTrue((self.claude / "settings.json").is_file())

    def test_does_not_prune_dirs_with_base_content(self):
        # A pre-existing base skill must survive reset of a composed sibling.
        base = self.claude / "skills" / "base-skill"
        base.mkdir(parents=True)
        (base / "SKILL.md").write_text("base\n")
        self._compose()
        self._reset()
        self.assertTrue((base / "SKILL.md").is_file())
        self.assertFalse((self.claude / "skills" / "blog-skill").exists())

    # --- state files ----------------------------------------------------

    def test_removes_state_files(self):
        self._compose()
        self.assertTrue(manifest_lib.manifest_path(self.root).is_file())
        self.assertTrue(manifest_lib.copied_files_path(self.root).is_file())
        self._reset()
        self.assertFalse(manifest_lib.manifest_path(self.root).is_file())
        self.assertFalse(manifest_lib.copied_files_path(self.root).is_file())

    # --- CLAUDE.local.md handling ---------------------------------------

    def test_strips_team_block_keeps_personal(self):
        self.local_md.write_text("# personal\nkeep me\n")
        self._compose()
        self.assertIn(localmd.TEAM_START, self.local_md.read_text())
        self._reset()
        text = self.local_md.read_text()
        self.assertIn("keep me", text)
        self.assertNotIn(localmd.TEAM_START, text)

    def test_removes_local_md_when_empty_after_strip(self):
        self._compose()  # writes a team block, no personal content
        self.assertTrue(self.local_md.is_file())
        self._reset()
        self.assertFalse(self.local_md.exists())

    def test_personal_flag_clears_everything(self):
        self.local_md.write_text("# personal\nkeep me\n")
        self._compose()
        self._reset(personal=True)
        self.assertFalse(self.local_md.exists())

    # --- git exclude ----------------------------------------------------

    def test_clears_git_exclude_block_preserving_user_excludes(self):
        exclude = self.root / ".git" / "info" / "exclude"
        exclude.parent.mkdir(parents=True, exist_ok=True)
        exclude.write_text("*.log\n")
        self._compose()
        self.assertIn(compose.EXCLUDE_START, exclude.read_text())
        self._reset()
        text = exclude.read_text()
        self.assertNotIn(compose.EXCLUDE_START, text)
        self.assertIn("*.log", text)

    # --- idempotency / no-op --------------------------------------------

    def test_reset_on_clean_workspace_is_noop(self):
        rc = self._reset()
        self.assertEqual(rc, 0)
        self.assertFalse(manifest_lib.manifest_path(self.root).is_file())

    def test_double_reset_is_safe(self):
        self._compose()
        self.assertEqual(self._reset(), 0)
        self.assertEqual(self._reset(), 0)

    # --- compose → reset → compose reproduces the same state ------------

    def test_compose_reset_compose_same_state(self):
        self._compose()
        first = self._snapshot()
        self._reset()
        self._compose()
        second = self._snapshot()
        self.assertEqual(first, second)

    def _snapshot(self):
        """Capture composed state for equality, ignoring the composed_at clock."""
        manifest = manifest_lib.read(self.root)
        manifest.pop("composed_at", None)
        copied = manifest_lib.read_copied_files(self.root)
        contents = {
            str(Path(p).relative_to(self.root)): Path(p).read_text()
            for p in copied
        }
        local = self.local_md.read_text() if self.local_md.is_file() else None
        return {
            "manifest": manifest,
            "copied_rel": sorted(str(Path(p).relative_to(self.root)) for p in copied),
            "contents": contents,
            "local_md": local,
        }


if __name__ == "__main__":
    unittest.main()
