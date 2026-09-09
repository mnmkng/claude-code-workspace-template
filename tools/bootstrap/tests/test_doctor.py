"""Tests for tools/bootstrap/doctor.py (diagnostics, issue #46)."""

import argparse
import contextlib
import io
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
import doctor  # noqa: E402
import reset  # noqa: E402
from lib import localmd  # noqa: E402


def _settings(sandbox_enabled=True, deny=("Read(~/.ssh/**)",)):
    return json.dumps({
        "permissions": {"deny": list(deny)},
        "sandbox": {"enabled": sandbox_enabled},
    }) + "\n"


def _make_workspace(root: Path, settings=None):
    (root / "CLAUDE.md").write_text("# root\n@CLAUDE.local.md")
    (root / ".claude").mkdir()
    (root / ".claude" / "settings.json").write_text(settings or _settings())
    blog = root / "departments" / "mktg" / "teams" / "blog"
    blog.mkdir(parents=True)
    (root / "departments" / "mktg" / "CLAUDE.md").write_text("# mktg\n")
    (blog / "CLAUDE.md").write_text("# blog\n")
    skill = blog / ".claude" / "skills" / "blog-skill"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("blog skill\n")


class DoctorTests(unittest.TestCase):
    def setUp(self):
        os.environ["NO_COLOR"] = "1"
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()
        _make_workspace(self.root)
        self.local_md = self.root / "CLAUDE.local.md"

        os.environ.pop("WORKSPACE_TEAM", None)
        os.environ.pop("CLAUDE_CODE_REMOTE", None)

        # Pin root detection (doctor uses find_workspace_root; compose/reset use
        # require_workspace_root — both live on lib.paths).
        self._p1 = patch("lib.paths.find_workspace_root", return_value=self.root)
        self._p2 = patch("lib.paths.require_workspace_root", return_value=self.root)
        self._p1.start()
        self._p2.start()

        # Point the user-level hook check at a temp file (absent by default).
        self._user_home = tempfile.TemporaryDirectory()
        self.user_settings = Path(self._user_home.name) / ".claude" / "settings.json"
        self._p3 = patch("doctor._user_settings_path", return_value=self.user_settings)
        self._p3.start()

    def tearDown(self):
        for p in (self._p1, self._p2, self._p3):
            p.stop()
        self._tmp.cleanup()
        self._user_home.cleanup()
        os.environ.pop("WORKSPACE_TEAM", None)
        os.environ.pop("CLAUDE_CODE_REMOTE", None)

    def _run(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = doctor.run(argparse.Namespace())
        return rc, buf.getvalue()

    def _write_user_hook(self, command):
        self.user_settings.parent.mkdir(parents=True, exist_ok=True)
        self.user_settings.write_text(json.dumps({
            "hooks": {"SessionStart": [
                {"hooks": [{"type": "command", "command": command}]}
            ]}
        }))

    # --- exit code / overall health -------------------------------------

    def test_healthy_uncomposed_exits_zero(self):
        rc, out = self._run()
        self.assertEqual(rc, 0)
        self.assertIn("manifest: not composed", out)
        self.assertIn("sandbox enabled", out)
        self.assertIn("doctor: healthy", out)

    def test_root_not_found_is_problem(self):
        with patch("lib.paths.find_workspace_root", return_value=None):
            rc, out = self._run()
        self.assertEqual(rc, 1)
        self.assertIn("workspace root: not found", out)

    # --- mode -----------------------------------------------------------

    def test_mode_cloud(self):
        os.environ["CLAUDE_CODE_REMOTE"] = "true"
        _, out = self._run()
        self.assertIn("mode: cloud", out)

    def test_mode_local(self):
        _, out = self._run()
        self.assertIn("mode: local", out)

    def test_mode_unknown(self):
        os.environ["CLAUDE_CODE_REMOTE"] = "1"
        _, out = self._run()
        self.assertIn("mode: unknown", out)

    # --- settings.json security checks ----------------------------------

    def test_sandbox_disabled_is_problem(self):
        (self.root / ".claude" / "settings.json").write_text(
            _settings(sandbox_enabled=False))
        rc, out = self._run()
        self.assertEqual(rc, 1)
        self.assertIn("sandbox NOT enabled", out)

    def test_no_deny_rules_is_problem(self):
        (self.root / ".claude" / "settings.json").write_text(_settings(deny=()))
        rc, out = self._run()
        self.assertEqual(rc, 1)
        self.assertIn("no deny rules", out)

    def test_missing_settings_is_problem(self):
        (self.root / ".claude" / "settings.json").unlink()
        rc, out = self._run()
        self.assertEqual(rc, 1)
        self.assertIn("settings.json: missing", out)

    # --- team resolution ------------------------------------------------

    def test_team_resolves(self):
        os.environ["WORKSPACE_TEAM"] = "blog"
        rc, out = self._run()
        self.assertEqual(rc, 0)
        self.assertIn("departments/mktg/teams/blog", out)

    def test_team_unresolvable_is_problem(self):
        os.environ["WORKSPACE_TEAM"] = "nope"
        rc, out = self._run()
        self.assertEqual(rc, 1)
        self.assertIn("team (WORKSPACE_TEAM): nope", out)

    def test_team_root_sentinel(self):
        os.environ["WORKSPACE_TEAM"] = "root"
        rc, out = self._run()
        self.assertEqual(rc, 0)
        self.assertIn("root / no-team mode", out)

    def test_team_sourced_from_manifest_when_env_unset(self):
        # Reproduces the cloud case: env started with `--team root` (a flag,
        # not WORKSPACE_TEAM). The Environment line must report the composed team
        # from the manifest, not a misleading "not set".
        compose.run(argparse.Namespace(team="root"))
        rc, out = self._run()
        self.assertEqual(rc, 0)
        self.assertIn("team: root (root / no-team mode)", out)
        self.assertNotIn("team: not set", out)

    def test_env_team_differs_from_composed_warns(self):
        compose.run(argparse.Namespace(team="blog"))
        os.environ["WORKSPACE_TEAM"] = "content"  # differs from composed 'blog'
        rc, out = self._run()
        self.assertEqual(rc, 0)  # a mismatch is a warning, not a failure
        self.assertIn("differs from the composed team", out)

    # --- composed manifest reporting ------------------------------------

    def test_manifest_reported_after_compose(self):
        compose.run(argparse.Namespace(team="blog"))
        rc, out = self._run()
        self.assertEqual(rc, 0)
        self.assertIn("composed for 'blog'", out)
        self.assertIn("level departments/mktg/teams/blog", out)
        self.assertIn("copied files:", out)

    # --- personal context state -----------------------------------------

    def test_personal_missing(self):
        _, out = self._run()
        self.assertIn("personal context (CLAUDE.local.md): missing file", out)

    def test_personal_empty_with_only_team_block(self):
        self.local_md.write_text(localmd.team_block_text(["departments/mktg"]))
        _, out = self._run()
        self.assertIn("personal context (CLAUDE.local.md): empty", out)

    def test_personal_loaded(self):
        self.local_md.write_text("# my notes\nremember\n")
        _, out = self._run()
        self.assertIn("personal context (CLAUDE.local.md): loaded", out)

    # --- user-level hook ------------------------------------------------

    def test_user_hook_present(self):
        self._write_user_hook(f"{self.root}/.claude/hooks/status-banner.sh user")
        rc, out = self._run()
        self.assertEqual(rc, 0)
        self.assertIn("user-level hook: present", out)

    def test_user_hook_absent_is_warning_not_failure(self):
        rc, out = self._run()
        self.assertEqual(rc, 0)
        self.assertIn("user-level hook: absent", out)

    def test_user_hook_stale_is_problem(self):
        self._write_user_hook("/some/other/checkout/.claude/hooks/status-banner.sh user")
        rc, out = self._run()
        self.assertEqual(rc, 1)
        self.assertIn("user-level hook: stale", out)

    def test_user_hook_not_applicable_in_cloud(self):
        # In cloud the user-level hook is irrelevant; never flag its absence.
        os.environ["CLAUDE_CODE_REMOTE"] = "true"
        rc, out = self._run()
        self.assertEqual(rc, 0)
        self.assertIn("user-level hook: not applicable in cloud", out)
        self.assertNotIn("user-level hook: absent", out)

    # --- version pin ----------------------------------------------------

    def test_version_falls_back_to_code_default(self):
        _, out = self._run()
        self.assertIn("bootstrap version:", out)
        self.assertIn("code default", out)

    def test_version_pin_read_from_setup_script(self):
        scripts = self.root / "scripts"
        scripts.mkdir()
        (scripts / "install.sh").write_text("#!/bin/sh\n# bootstrap-version: 2.3.4\n")
        _, out = self._run()
        self.assertIn("bootstrap version: 2.3.4", out)

    # --- integration with reset ----------------------------------------

    @unittest.skipUnless(shutil.which("git"), "git not available")
    def test_doctor_clean_after_reset(self):
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        compose.run(argparse.Namespace(team="blog"))
        reset.run(argparse.Namespace(personal=False))
        rc, out = self._run()
        self.assertEqual(rc, 0)
        self.assertIn("manifest: not composed", out)
        self.assertIn("personal context (CLAUDE.local.md): missing file", out)


if __name__ == "__main__":
    unittest.main()
