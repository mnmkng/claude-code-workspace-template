"""Tests for tools/bootstrap/settings_sync.py (issue #141).

Covers the derivation contract (copy-everything-except), stamping and
--check semantics, the git-ignored hard-fail, stray detection, and the
runtime behavior of the inline hook commands (banner ACTIVE/NOT DETECTED,
wrapper exec pass-through, and the fail-closed floor).
"""

import argparse
import json
import os
import subprocess
import sys
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import settings_sync  # noqa: E402


ROOT_SETTINGS = {
    "autoMemoryEnabled": False,
    "someFutureKey": {"nested": True},
    "permissions": {
        "defaultMode": "acceptEdits",
        "allow": ["WebFetch"],
        "deny": ["Read(~/.ssh/**)", "Edit(**/.claude/settings.json)"],
    },
    "sandbox": {
        "enabled": True,
        "filesystem": {"denyRead": ["~/.ssh/**", "**/.env", "**/.mcp.json"]},
    },
    "hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": []}]},
    "enableAllProjectMcpServers": True,
    "enabledMcpjsonServers": ["redash"],
}


def _git(root, *argv):
    return subprocess.run(
        ["git", "-C", str(root)] + list(argv), capture_output=True, text=True,
    )


def _make_workspace(root: Path):
    """Git-backed workspace-root-shaped tree: two team levels + an excluded fixture."""
    (root / "CLAUDE.md").write_text("# root\n")
    (root / ".claude").mkdir()
    (root / ".claude" / "settings.json").write_text(
        json.dumps(ROOT_SETTINGS, indent=2) + "\n"
    )
    (root / "departments").mkdir()
    foo = root / "departments" / "foo"
    foo.mkdir()
    (foo / "CLAUDE.md").write_text("# foo dept\n")
    bar = root / "departments" / "foo" / "teams" / "bar"
    bar.mkdir(parents=True)
    (bar / "CLAUDE.md").write_text("# bar team\n")
    fixture = root / "tools" / "bootstrap" / "research" / "q2-fixtures"
    fixture.mkdir(parents=True)
    (fixture / "CLAUDE.md").write_text("# fixture, never a target\n")

    _git(root, "init", "-q")
    _git(root, "add", "-A")


class DerivationTests(unittest.TestCase):
    def setUp(self):
        os.environ["NO_COLOR"] = "1"
        self.team = settings_sync.derive_team_settings(ROOT_SETTINGS)

    def test_dropped_keys_not_copied(self):
        # MCP keys vanish entirely; hooks are rebuilt, never copied.
        self.assertNotIn("enableAllProjectMcpServers", self.team)
        self.assertNotIn("enabledMcpjsonServers", self.team)
        self.assertNotEqual(self.team["hooks"], ROOT_SETTINGS["hooks"])
        self.assertEqual(self.team["hooks"], settings_sync.team_hooks())

    def test_policy_sections_copied_verbatim(self):
        self.assertEqual(self.team["permissions"], ROOT_SETTINGS["permissions"])
        self.assertEqual(self.team["sandbox"], ROOT_SETTINGS["sandbox"])

    def test_unlisted_top_level_keys_propagate(self):
        # Copy-everything-except: a new root key (the #139 class) must reach
        # team copies without a generator change.
        self.assertEqual(self.team["autoMemoryEnabled"], False)
        self.assertEqual(self.team["someFutureKey"], {"nested": True})

    def test_derivation_does_not_mutate_root(self):
        self.team["permissions"]["deny"].append("mutated")
        self.assertNotIn("mutated", ROOT_SETTINGS["permissions"]["deny"])

    def test_env_version_marker(self):
        self.assertEqual(
            self.team["env"]["WORKSPACE_TEAM_POLICY_VERSION"],
            settings_sync.TEAM_POLICY_VERSION,
        )

    def test_root_env_merged_not_clobbered(self):
        root = dict(ROOT_SETTINGS, env={"EXISTING": "1"})
        team = settings_sync.derive_team_settings(root)
        self.assertEqual(team["env"]["EXISTING"], "1")
        self.assertIn("WORKSPACE_TEAM_POLICY_VERSION", team["env"])

    def test_hooks_rebuilt_with_expected_shape(self):
        hooks = self.team["hooks"]
        matchers = [e["matcher"] for e in hooks["PreToolUse"]]
        self.assertEqual(matchers, ["Write|Edit|MultiEdit", "Bash", "WebFetch"])
        self.assertEqual(len(hooks["SessionStart"]), 1)
        for event in hooks.values():
            for entry in event:
                for h in entry["hooks"]:
                    self.assertEqual(h["type"], "command")
                    # Self-contained: never references a path inside the team
                    # folder via $CLAUDE_PROJECT_DIR directly.
                    self.assertNotIn('"$CLAUDE_PROJECT_DIR"/', h["command"])

    def test_banner_version_matches_env_version(self):
        banner = self.team["hooks"]["SessionStart"][0]["hooks"][0]["command"]
        self.assertIn(
            f"team-folder policy v{settings_sync.TEAM_POLICY_VERSION}", banner
        )

    def test_render_deterministic(self):
        a = settings_sync.render(settings_sync.derive_team_settings(ROOT_SETTINGS))
        b = settings_sync.render(settings_sync.derive_team_settings(ROOT_SETTINGS))
        self.assertEqual(a, b)
        self.assertTrue(a.endswith("\n"))


class StampTests(unittest.TestCase):
    def setUp(self):
        os.environ["NO_COLOR"] = "1"
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()
        _make_workspace(self.root)
        self._patch = patch(
            "settings_sync.path_lib.require_workspace_root", return_value=self.root
        )
        self._patch.start()

    def tearDown(self):
        self._patch.stop()
        self._tmp.cleanup()

    def _run(self, check=False):
        return settings_sync.run(argparse.Namespace(check=check))

    def _stamp(self, folder):
        return self.root / folder / ".claude" / "settings.json"

    def test_target_folders(self):
        self.assertEqual(
            settings_sync.target_folders(self.root),
            ["departments/foo", "departments/foo/teams/bar"],
        )

    def test_stamp_writes_byte_identical_copies(self):
        self.assertEqual(self._run(), 0)
        a = self._stamp("departments/foo").read_text()
        b = self._stamp("departments/foo/teams/bar").read_text()
        self.assertEqual(a, b)
        self.assertEqual(a, settings_sync.expected_content(self.root))
        # Excluded locations stay clean.
        self.assertFalse(
            (self.root / "tools/bootstrap/research/q2-fixtures/.claude").exists()
        )

    def test_check_green_after_stamp_and_red_on_missing_or_drift(self):
        self._run()
        self.assertEqual(self._run(check=True), 0)

        self._stamp("departments/foo").unlink()
        self.assertEqual(self._run(check=True), 1)

        self._run()
        with open(self._stamp("departments/foo/teams/bar"), "a") as f:
            f.write("\n")
        self.assertEqual(self._run(check=True), 1)

    def test_rerun_idempotent_and_repairs_drift(self):
        self._run()
        expected = self._stamp("departments/foo").read_text()
        self._stamp("departments/foo").write_text("{}\n")
        self.assertEqual(self._run(), 0)
        self.assertEqual(self._stamp("departments/foo").read_text(), expected)

    def test_root_settings_change_propagates(self):
        self._run()
        root_file = self.root / ".claude" / "settings.json"
        s = json.loads(root_file.read_text())
        s["brandNewKey"] = 7
        root_file.write_text(json.dumps(s, indent=2) + "\n")

        self.assertEqual(self._run(check=True), 1)  # drift detected
        self.assertEqual(self._run(), 0)            # repaired
        stamped = json.loads(self._stamp("departments/foo").read_text())
        self.assertEqual(stamped["brandNewKey"], 7)

    def test_stray_copy_fails_check(self):
        self._run()
        stray_dir = self.root / "departments" / "no-claude-md" / ".claude"
        stray_dir.mkdir(parents=True)
        (stray_dir / "settings.json").write_text("{}\n")
        self.assertEqual(self._run(check=True), 1)
        issues, _ = settings_sync.findings(self.root)
        self.assertIn(
            ("stray", "departments/no-claude-md/.claude/settings.json"), issues
        )

    def test_settings_local_json_is_not_a_stray(self):
        self._run()
        local = self.root / "departments" / "foo" / ".claude" / "settings.local.json"
        local.write_text("{}\n")
        self.assertEqual(self._run(check=True), 0)

    def test_gitignored_stamp_hard_fails(self):
        (self.root / ".gitignore").write_text(
            "departments/foo/.claude/settings.json\n"
        )
        with self.assertRaises(SystemExit) as ctx:
            self._run()
        self.assertIn("git-ignored", str(ctx.exception))
        # Nothing was written for any target - the failure is atomic.
        self.assertFalse(self._stamp("departments/foo").exists())
        self.assertFalse(self._stamp("departments/foo/teams/bar").exists())


class InlineHookBehaviorTests(unittest.TestCase):
    """Run the generated commands under a real shell.

    CLI proxy for the Desktop-subfolder behavior: the same command strings
    fire there (the harness-probe covers the Desktop side manually).
    """

    def setUp(self):
        os.environ["NO_COLOR"] = "1"
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()
        _make_workspace(self.root)
        self.team = self.root / "departments" / "foo"
        stamp = settings_sync.derive_team_settings(ROOT_SETTINGS)
        self.banner = stamp["hooks"]["SessionStart"][0]["hooks"][0]["command"]
        self.bash_wrap = stamp["hooks"]["PreToolUse"][1]["hooks"][0]["command"]

    def tearDown(self):
        self._tmp.cleanup()

    def _sh(self, command, project_dir, stdin=""):
        env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": os.environ.get("HOME", "/tmp"),
            "CLAUDE_PROJECT_DIR": str(project_dir),
        }
        return subprocess.run(
            ["bash", "-c", command], input=stdin, env=env,
            capture_output=True, text=True,
        )

    def test_banner_active_inside_tree(self):
        r = self._sh(self.banner, self.team)
        payload = json.loads(r.stdout)
        self.assertIn(
            f"ACTIVE (team-folder policy v{settings_sync.TEAM_POLICY_VERSION})",
            payload["hookSpecificOutput"]["additionalContext"],
        )
        # systemMessage must be top-level to be displayed (the #86 bug).
        self.assertIn("systemMessage", payload)
        self.assertNotIn("systemMessage", payload["hookSpecificOutput"])

    def test_banner_not_detected_outside_tree(self):
        outside = Path(tempfile.mkdtemp())
        r = self._sh(self.banner, outside)
        payload = json.loads(r.stdout)
        self.assertIn(
            "NOT DETECTED", payload["hookSpecificOutput"]["additionalContext"]
        )

    def test_wrapper_execs_root_hook_with_stdin(self):
        hooks_dir = self.root / ".claude" / "hooks"
        hooks_dir.mkdir()
        capture = self.root / "captured.txt"
        hook = hooks_dir / "protect-config.sh"
        hook.write_text(f'#!/bin/sh\ncat > "{capture}"\nexit 3\n')
        hook.chmod(0o755)

        payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": "ls"}})
        r = self._sh(self.bash_wrap, self.team, stdin=payload)
        self.assertEqual(r.returncode, 3)  # the fake hook's own exit code
        self.assertEqual(capture.read_text(), payload)

    def test_wrapper_fails_closed_without_root_hook(self):
        # Workspace root resolvable, but no protect-config.sh -> block.
        payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": "ls"}})
        r = self._sh(self.bash_wrap, self.team, stdin=payload)
        self.assertEqual(r.returncode, 2)
        self.assertIn("failing closed", r.stderr)

    def test_wrapper_fails_closed_outside_tree(self):
        outside = Path(tempfile.mkdtemp())
        payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": "ls"}})
        r = self._sh(self.bash_wrap, outside, stdin=payload)
        self.assertEqual(r.returncode, 2)
        self.assertIn("failing closed", r.stderr)


class InstallDriftReportTests(unittest.TestCase):
    """install's read-only drift report (the post-checkout self-heal path)."""

    def setUp(self):
        os.environ["NO_COLOR"] = "1"
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()
        _make_workspace(self.root)
        self._patch = patch(
            "settings_sync.path_lib.require_workspace_root", return_value=self.root
        )
        self._patch.start()
        import install
        self.install = install

    def tearDown(self):
        self._patch.stop()
        self._tmp.cleanup()

    def test_silent_and_false_when_in_sync(self):
        settings_sync.run(argparse.Namespace(check=False))
        self.assertFalse(self.install._report_team_stamp_drift(self.root))

    def test_reports_drift_without_writing(self):
        settings_sync.run(argparse.Namespace(check=False))
        stamp = self.root / "departments/foo/.claude/settings.json"
        stamp.write_text("{}\n")
        self.assertTrue(self.install._report_team_stamp_drift(self.root))
        # Report only - never repairs (that's a reviewed settings-sync PR).
        self.assertEqual(stamp.read_text(), "{}\n")

    def test_silent_without_git(self):
        import shutil
        shutil.rmtree(self.root / ".git")
        self.assertFalse(self.install._report_team_stamp_drift(self.root))


class DoctorTeamPolicyTests(unittest.TestCase):
    """doctor's team-folder policy section against a git-backed workspace."""

    def setUp(self):
        os.environ["NO_COLOR"] = "1"
        os.environ.pop("WORKSPACE_TEAM", None)
        os.environ.pop("CLAUDE_CODE_REMOTE", None)
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()
        _make_workspace(self.root)
        self._patches = [
            patch("lib.paths.find_workspace_root", return_value=self.root),
            patch("lib.paths.require_workspace_root", return_value=self.root),
        ]
        for p in self._patches:
            p.start()
        # Keep the user-hook check away from the real ~/.claude.
        import doctor
        self._user_home = tempfile.TemporaryDirectory()
        self._patches.append(patch(
            "doctor._user_settings_path",
            return_value=Path(self._user_home.name) / "settings.json",
        ))
        self._patches[-1].start()
        self.doctor = doctor

    def tearDown(self):
        for p in self._patches:
            p.stop()
        self._tmp.cleanup()
        self._user_home.cleanup()

    def _doctor(self):
        import contextlib
        import io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = self.doctor.run(argparse.Namespace())
        return rc, buf.getvalue()

    def test_doctor_reports_stamped_and_healthy(self):
        settings_sync.run(argparse.Namespace(check=False))
        rc, out = self._doctor()
        self.assertEqual(rc, 0)
        self.assertIn(
            f"team-folder policy: v{settings_sync.TEAM_POLICY_VERSION} "
            "stamped in 2/2 folder(s), no drift",
            out,
        )

    def test_doctor_flags_missing_and_drift(self):
        settings_sync.run(argparse.Namespace(check=False))
        (self.root / "departments/foo/.claude/settings.json").unlink()
        with open(self.root / "departments/foo/teams/bar/.claude/settings.json",
                  "a") as f:
            f.write("\n")
        rc, out = self._doctor()
        self.assertEqual(rc, 1)
        self.assertIn("1 missing, 1 drifted", out)
        self.assertIn("settings-sync", out)

    def test_doctor_skips_cleanly_without_git(self):
        # Non-repo root: nothing to verify, must not fail the whole doctor.
        import shutil
        git_dir = self.root / ".git"
        if git_dir.exists():
            shutil.rmtree(git_dir)
        rc, out = self._doctor()
        self.assertEqual(rc, 0)
        self.assertIn("team-folder policy: skipped", out)


if __name__ == "__main__":
    unittest.main()
