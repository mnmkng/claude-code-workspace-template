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

        # Multi-repo parent policy (#195): a temp parent dir, empty by default.
        self._parent = tempfile.TemporaryDirectory()
        os.environ["WORKSPACE_PARENT_SETTINGS_DIR"] = self._parent.name
        self.parent_file = Path(self._parent.name) / ".claude" / "settings.json"

    def tearDown(self):
        for p in (self._p1, self._p2, self._p3):
            p.stop()
        self._tmp.cleanup()
        self._user_home.cleanup()
        self._parent.cleanup()
        os.environ.pop("WORKSPACE_TEAM", None)
        os.environ.pop("CLAUDE_CODE_REMOTE", None)
        os.environ.pop("WORKSPACE_PARENT_SETTINGS_DIR", None)

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
        self._origin_main()  # keep the parent-policy line healthy
        rc, out = self._run()
        self.assertEqual(rc, 0)
        self.assertIn("user-level hook: not applicable in cloud", out)
        self.assertNotIn("user-level hook: absent", out)

    # --- multi-repo parent policy (#195) --------------------------------

    def _origin_main(self):
        """Commit only the root settings.json and point origin/main at it.

        The parent policy is rendered from origin/main and fails closed
        without it. Tracking only that file keeps the team-folder stamp check
        at "no targets", so the other doctor lines are unaffected.
        """
        g = ["git", "-C", str(self.root), "-c", "user.email=t@t", "-c", "user.name=t"]
        subprocess.run(g + ["init", "-q"], check=True)
        subprocess.run(g + ["add", ".claude/settings.json"], check=True)
        subprocess.run(g + ["commit", "-q", "-m", "main"], check=True)
        subprocess.run(g + ["update-ref", "refs/remotes/origin/main", "HEAD"], check=True)

    def test_parent_policy_not_applicable_locally(self):
        rc, out = self._run()
        self.assertEqual(rc, 0)
        self.assertIn("multi-repo parent policy: not applicable outside cloud", out)

    def test_parent_policy_working_tree_seed_is_problem(self):
        # No origin/main anywhere: the writer seeds from the working tree. By
        # the time doctor runs in a session the apply tier should have
        # upgraded it, so a working-tree source still in place is a problem.
        os.environ["CLAUDE_CODE_REMOTE"] = "true"
        import parent_settings
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            parent_settings.write(self.root)
        rc, out = self._run()
        self.assertEqual(rc, 1)
        self.assertIn("was rendered from working-tree", out)
        self.assertIn("not origin/main", out)

    def test_parent_policy_unverifiable_is_warning(self):
        # Rendered from origin/main, but the ref is gone from the clone:
        # cannot compare, do not fail.
        os.environ["CLAUDE_CODE_REMOTE"] = "true"
        self._origin_main()
        import parent_settings
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            parent_settings.write(self.root)
        subprocess.run(["git", "-C", str(self.root), "update-ref", "-d",
                        "refs/remotes/origin/main"], check=True)
        rc, out = self._run()
        self.assertEqual(rc, 0)
        self.assertIn("byte-identity was not verified", out)

    def test_parent_policy_missing_single_repo_is_warning(self):
        os.environ["CLAUDE_CODE_REMOTE"] = "true"
        self._origin_main()
        rc, out = self._run()
        self.assertEqual(rc, 0)
        self.assertIn("multi-repo parent policy: missing", out)
        self.assertIn("layout: single-repo", out)

    def test_parent_policy_missing_multi_repo_is_problem(self):
        os.environ["CLAUDE_CODE_REMOTE"] = "true"
        self._origin_main()
        (Path(self._parent.name) / "other-repo" / ".git").mkdir(parents=True)
        rc, out = self._run()
        self.assertEqual(rc, 1)
        self.assertIn("multi-repo parent policy: missing", out)
        self.assertIn("layout: multi-repo, 1 sibling repo(s)", out)

    def test_parent_policy_in_sync(self):
        os.environ["CLAUDE_CODE_REMOTE"] = "true"
        self._origin_main()
        import parent_settings
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            parent_settings.write(self.root)
        rc, out = self._run()
        self.assertEqual(rc, 0)
        self.assertIn("multi-repo parent policy:", out)
        self.assertIn("in sync", out)

    def test_parent_policy_foreign_file_is_problem(self):
        os.environ["CLAUDE_CODE_REMOTE"] = "true"
        self._origin_main()
        self.parent_file.parent.mkdir(parents=True)
        self.parent_file.write_text("{}\n")
        rc, out = self._run()
        self.assertEqual(rc, 1)
        self.assertIn("was not written by this generator", out)

    def test_parent_policy_drift_is_problem(self):
        os.environ["CLAUDE_CODE_REMOTE"] = "true"
        self._origin_main()
        import parent_settings
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            parent_settings.write(self.root)
        data = json.loads(self.parent_file.read_text())
        data["permissions"]["deny"] = []  # weakened, marker intact
        self.parent_file.write_text(json.dumps(data, indent=2) + "\n")
        rc, out = self._run()
        self.assertEqual(rc, 1)
        self.assertIn("drifted from the origin/main rendering", out)

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
