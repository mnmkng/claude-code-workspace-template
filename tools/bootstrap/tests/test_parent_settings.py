"""Tests for tools/bootstrap/parent_settings.py (issue #195).

Covers the derivation contract (copy-everything-except, pinned hook paths,
env markers), the origin/main-first source rule with working-tree fallback,
idempotent write/status, sibling-repo detection, the subcommand, and the
runtime behavior of the pinned hook commands (exec pass-through with stdin,
fail-closed without the clone, banner delegation and NOT DETECTED).
"""

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

import parent_settings  # noqa: E402


ROOT_SETTINGS = {
    "autoMemoryEnabled": False,
    "someFutureKey": {"nested": True},
    "env": {"EXISTING": "keep"},
    "permissions": {
        "defaultMode": "acceptEdits",
        "deny": ["Read(~/.ssh/**)", "Edit(**/.claude/settings.json)"],
    },
    "sandbox": {"enabled": True, "filesystem": {"denyRead": ["~/.ssh/**"]}},
    "hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": []}]},
    "enableAllProjectMcpServers": True,
    "enabledMcpjsonServers": ["redash"],
}

MAIN_SETTINGS = dict(ROOT_SETTINGS, autoMemoryEnabled=True)  # distinguishable


def _git(root, *argv):
    return subprocess.run(
        ["git", "-C", str(root)] + list(argv), capture_output=True, text=True,
    )


def _make_workspace(root: Path, settings=ROOT_SETTINGS):
    (root / "CLAUDE.md").write_text("# root\n")
    (root / ".claude").mkdir(parents=True)
    (root / ".claude" / "settings.json").write_text(json.dumps(settings, indent=2) + "\n")
    (root / "departments").mkdir()


def _fake_origin_main(root: Path, settings):
    """Commit `settings` and point refs/remotes/origin/main at that commit, then
    leave the working tree free to diverge."""
    _git(root, "init", "-q")
    _git(root, "-c", "user.email=t@t", "-c", "user.name=t", "add", "-A")
    (root / ".claude" / "settings.json").write_text(json.dumps(settings, indent=2) + "\n")
    _git(root, "add", "-A")
    _git(root, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "main")
    _git(root, "update-ref", "refs/remotes/origin/main", "HEAD")


class _Base(unittest.TestCase):
    def setUp(self):
        os.environ["NO_COLOR"] = "1"
        # Layout: <home>/claude-code-workspace with <home> as the parent.
        self._home = tempfile.TemporaryDirectory()
        self.home = Path(self._home.name).resolve()
        self.root = self.home / "claude-code-workspace"
        self.root.mkdir()
        _make_workspace(self.root)
        # The policy is rendered from origin/main and fails closed without it,
        # so every fixture carries the ref (pointing at ROOT_SETTINGS).
        _fake_origin_main(self.root, ROOT_SETTINGS)
        os.environ.pop(parent_settings.PARENT_DIR_ENV, None)

    def tearDown(self):
        self._home.cleanup()
        os.environ.pop(parent_settings.PARENT_DIR_ENV, None)


class DerivationTests(_Base):
    def setUp(self):
        super().setUp()
        self.parent = parent_settings.derive_parent_settings(ROOT_SETTINGS, self.root)

    def test_dropped_keys_not_copied_hooks_rebuilt(self):
        self.assertNotIn("enableAllProjectMcpServers", self.parent)
        self.assertNotIn("enabledMcpjsonServers", self.parent)
        self.assertNotEqual(self.parent["hooks"], ROOT_SETTINGS["hooks"])
        self.assertEqual(self.parent["hooks"], parent_settings.parent_hooks(str(self.root)))

    def test_everything_else_copied_verbatim(self):
        for key in ("autoMemoryEnabled", "someFutureKey", "permissions", "sandbox"):
            self.assertEqual(self.parent[key], ROOT_SETTINGS[key])

    def test_env_markers_added_existing_env_kept(self):
        env = self.parent["env"]
        self.assertEqual(env["EXISTING"], "keep")
        self.assertEqual(env["CLAUDE_WORKSPACE_ROOT"], str(self.root))
        self.assertEqual(env["WORKSPACE_PARENT_POLICY_VERSION"],
                         parent_settings.PARENT_POLICY_VERSION)

    def test_every_hook_command_pins_the_clone_path(self):
        # No hook may fall back to $CLAUDE_PROJECT_DIR: in the multi-repo
        # layout it is the parent, where the scripts do not exist.
        for event, entries in self.parent["hooks"].items():
            for entry in entries:
                for h in entry["hooks"]:
                    self.assertIn(f"d={self.root}", h["command"], (event, h))
                    self.assertNotIn("CLAUDE_PROJECT_DIR", h["command"], (event, h))

    def test_hook_wiring_mirrors_root(self):
        pre = {e["matcher"] for e in self.parent["hooks"]["PreToolUse"]}
        self.assertEqual(pre, {"Write|Edit|MultiEdit", "Bash", "WebFetch"})
        start = self.parent["hooks"]["SessionStart"]
        self.assertEqual(len(start), 2)
        self.assertIn("status-banner.sh", start[0]["hooks"][0]["command"])
        self.assertIn("cloud --apply-only", start[1]["hooks"][0]["command"])
        self.assertIn('"$CLAUDE_CODE_REMOTE" = "true"', start[1]["hooks"][0]["command"])

    def test_render_deterministic(self):
        a = parent_settings.render(parent_settings.derive_parent_settings(ROOT_SETTINGS, self.root))
        b = parent_settings.render(parent_settings.derive_parent_settings(ROOT_SETTINGS, self.root))
        self.assertEqual(a, b)
        self.assertTrue(a.endswith("\n"))

    def test_derivation_does_not_mutate_input(self):
        before = json.dumps(ROOT_SETTINGS, sort_keys=True)
        parent_settings.derive_parent_settings(ROOT_SETTINGS, self.root)
        self.assertEqual(json.dumps(ROOT_SETTINGS, sort_keys=True), before)


class LocationTests(_Base):
    def test_parent_is_clone_parent_by_default(self):
        self.assertEqual(parent_settings.parent_dir(self.root), self.home)
        self.assertEqual(parent_settings.parent_settings_path(self.root),
                         self.home / ".claude" / "settings.json")

    def test_env_override(self):
        other = tempfile.mkdtemp()
        os.environ[parent_settings.PARENT_DIR_ENV] = other
        self.assertEqual(parent_settings.parent_dir(self.root), Path(other))

    def test_sibling_repos_detects_only_git_checkouts(self):
        (self.home / "other-repo" / ".git").mkdir(parents=True)
        (self.home / "not-a-repo").mkdir()
        (self.home / "loose-file").write_text("x")
        sibs = parent_settings.sibling_repos(self.root)
        self.assertEqual([p.name for p in sibs], ["other-repo"])

    def test_sibling_repos_single_layout_empty(self):
        self.assertEqual(parent_settings.sibling_repos(self.root), [])


@unittest.skipUnless(shutil.which("git"), "git not available")
class SourceTests(_Base):
    def test_prefers_origin_main_over_working_tree(self):
        _fake_origin_main(self.root, MAIN_SETTINGS)
        # Working tree diverges from origin/main.
        (self.root / ".claude" / "settings.json").write_text(
            json.dumps(ROOT_SETTINGS, indent=2) + "\n")
        settings, source = parent_settings.load_root_settings(self.root)
        self.assertEqual(source, parent_settings.POLICY_REF)
        self.assertTrue(settings["autoMemoryEnabled"])  # MAIN_SETTINGS marker

    def test_falls_back_to_working_tree_without_ref(self):
        # The setup-tier condition (#197 verification): no origin/main, nowhere
        # to fetch it from (no credentials). Seed from the working tree and
        # say so in the source label.
        _git(self.root, "update-ref", "-d", "refs/remotes/origin/main")
        (self.root / ".claude" / "settings.json").write_text(
            json.dumps(MAIN_SETTINGS, indent=2) + "\n")
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            settings, source = parent_settings.load_root_settings(self.root)
        self.assertTrue(source.startswith(parent_settings.WORKING_TREE_SOURCE + "@"), source)
        self.assertTrue(settings["autoMemoryEnabled"])  # the working tree's content
        self.assertIn("git fetch of origin/main failed", err.getvalue())
        self.assertIn("rendering from the working tree", err.getvalue())

    def test_falls_back_outside_git(self):
        shutil.rmtree(self.root / ".git")
        with contextlib.redirect_stderr(io.StringIO()):
            settings, source = parent_settings.load_root_settings(self.root)
        self.assertEqual(source, parent_settings.WORKING_TREE_SOURCE)
        self.assertEqual(settings, ROOT_SETTINGS)

    def test_no_source_at_all_is_fatal(self):
        _git(self.root, "update-ref", "-d", "refs/remotes/origin/main")
        (self.root / ".claude" / "settings.json").unlink()
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                parent_settings.load_root_settings(self.root)

    def test_working_tree_settings_irrelevant_when_ref_present(self):
        # Even a missing or broken working-tree file does not matter: the
        # source is the ref, nothing else.
        (self.root / ".claude" / "settings.json").write_text("{not json")
        settings, source = parent_settings.load_root_settings(self.root, fetch=False)
        self.assertEqual(source, parent_settings.POLICY_REF)
        self.assertEqual(settings, ROOT_SETTINGS)

    def test_invalid_ref_content_is_fatal(self):
        (self.root / ".claude" / "settings.json").write_text("{not json")
        _git(self.root, "add", "-A")
        _git(self.root, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "bad")
        _git(self.root, "update-ref", "refs/remotes/origin/main", "HEAD")
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as cm:
                parent_settings.load_root_settings(self.root, fetch=False)
        self.assertIn("invalid JSON", str(cm.exception))

    def test_fetches_ref_from_remote_when_absent_locally(self):
        # The cloud layout (#197 verification): the clone has only the session
        # branch, main exists on the remote. The writer must fetch it.
        bare = self.home / "remote.git"
        subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
        _git(self.root, "remote", "add", "origin", str(bare))
        _git(self.root, "push", "-q", "origin", "HEAD:refs/heads/main")
        _git(self.root, "update-ref", "-d", "refs/remotes/origin/main")
        self.assertNotEqual(_git(self.root, "rev-parse", "--verify", "origin/main").returncode, 0)

        settings, source = parent_settings.load_root_settings(self.root)
        self.assertEqual(source, parent_settings.POLICY_REF)
        self.assertEqual(settings, ROOT_SETTINGS)
        self.assertEqual(_git(self.root, "rev-parse", "--verify", "origin/main").returncode, 0)

    def test_status_does_not_fetch(self):
        bare = self.home / "remote.git"
        subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
        _git(self.root, "remote", "add", "origin", str(bare))
        _git(self.root, "push", "-q", "origin", "HEAD:refs/heads/main")
        _git(self.root, "update-ref", "-d", "refs/remotes/origin/main")
        with contextlib.redirect_stderr(io.StringIO()):
            st = parent_settings.status(self.root)
        self.assertFalse(st["verified"])
        self.assertNotEqual(_git(self.root, "rev-parse", "--verify", "origin/main").returncode, 0)


class SourceConvergenceTests(_Base):
    """Setup seeds from the working tree; a live session converges to main."""

    def _quiet(self, fn, *a):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return fn(*a)

    def _remote_main(self):
        bare = self.home / "remote.git"
        subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
        _git(self.root, "remote", "add", "origin", str(bare))
        _git(self.root, "push", "-q", "origin", "HEAD:refs/heads/main")

    def test_seed_from_working_tree_is_stamped_and_flagged(self):
        _git(self.root, "update-ref", "-d", "refs/remotes/origin/main")
        self.assertEqual(self._quiet(parent_settings.write, self.root), "written")
        text = parent_settings.parent_settings_path(self.root).read_text()
        src = parent_settings.recorded_source(text)
        self.assertTrue(src.startswith("working-tree@"), src)
        st = self._quiet(parent_settings.status, self.root)
        self.assertFalse(st["verified"])
        self.assertIn("not origin/main", parent_settings.check_problem(st))

    def test_seed_is_upgraded_to_main_once_fetchable(self):
        # Setup tier: no credentials -> working-tree seed.
        _git(self.root, "update-ref", "-d", "refs/remotes/origin/main")
        self._quiet(parent_settings.write, self.root)
        # Live session: the remote is reachable -> re-render from origin/main.
        self._remote_main()
        self.assertEqual(self._quiet(parent_settings.write, self.root), "written")
        text = parent_settings.parent_settings_path(self.root).read_text()
        self.assertEqual(parent_settings.recorded_source(text), parent_settings.POLICY_REF)
        st = self._quiet(parent_settings.status, self.root)
        self.assertTrue(st["verified"] and st["in_sync"])
        self.assertEqual(parent_settings.check_problem(st), "")

    def test_main_rendering_is_never_downgraded(self):
        # Rendered from origin/main earlier; now the ref is gone and cannot be
        # fetched. Keep the reviewed file rather than overwrite it with the
        # working tree.
        self._quiet(parent_settings.write, self.root)
        before = parent_settings.parent_settings_path(self.root).read_text()
        _git(self.root, "update-ref", "-d", "refs/remotes/origin/main")
        (self.root / ".claude" / "settings.json").write_text(
            json.dumps(MAIN_SETTINGS, indent=2) + "\n")
        self.assertEqual(self._quiet(parent_settings.write, self.root), "kept")
        self.assertEqual(parent_settings.parent_settings_path(self.root).read_text(), before)

    def test_check_fails_on_working_tree_source_and_passes_after_upgrade(self):
        _git(self.root, "update-ref", "-d", "refs/remotes/origin/main")
        with patch("parent_settings.path_lib.require_workspace_root", return_value=self.root), \
                patch.dict(os.environ, {"CLAUDE_CODE_REMOTE": "true"}):
            self.assertEqual(self._quiet(parent_settings.run, argparse.Namespace(check=False)), 0)
            self.assertEqual(self._quiet(parent_settings.run, argparse.Namespace(check=True)), 1)
            self._remote_main()
            self.assertEqual(self._quiet(parent_settings.run, argparse.Namespace(check=False)), 0)
            self.assertEqual(self._quiet(parent_settings.run, argparse.Namespace(check=True)), 0)

    def test_check_warns_but_passes_when_ref_absent_after_main_render(self):
        self._quiet(parent_settings.write, self.root)
        _git(self.root, "update-ref", "-d", "refs/remotes/origin/main")
        err = io.StringIO()
        with patch("parent_settings.path_lib.require_workspace_root", return_value=self.root), \
                patch.dict(os.environ, {"CLAUDE_CODE_REMOTE": "true"}), \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
            rc = parent_settings.run(argparse.Namespace(check=True))
        self.assertEqual(rc, 0)
        self.assertIn("not verified", err.getvalue())


class WriteAndStatusTests(_Base):
    def _quiet(self, fn, *a):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return fn(*a)

    def test_write_creates_then_is_idempotent(self):
        p = parent_settings.parent_settings_path(self.root)
        self.assertFalse(p.exists())
        self.assertEqual(self._quiet(parent_settings.write, self.root), "written")
        self.assertTrue(p.is_file())
        self.assertEqual(self._quiet(parent_settings.write, self.root), "unchanged")
        expected, _ = self._quiet(parent_settings.expected_content, self.root)
        self.assertEqual(p.read_text(), expected)

    def test_write_repairs_drift(self):
        self._quiet(parent_settings.write, self.root)
        p = parent_settings.parent_settings_path(self.root)
        p.write_text('{"env": {"WORKSPACE_PARENT_POLICY_VERSION": "0"}, "permissions": {}}\n')
        self.assertFalse(self._quiet(parent_settings.status, self.root)["in_sync"])
        self.assertEqual(self._quiet(parent_settings.write, self.root), "written")
        self.assertTrue(self._quiet(parent_settings.status, self.root)["in_sync"])

    def test_status_missing(self):
        st = self._quiet(parent_settings.status, self.root)
        self.assertFalse(st["exists"])
        self.assertFalse(st["in_sync"])
        self.assertEqual(st["siblings"], [])

    def test_written_file_is_valid_json_with_pinned_hooks(self):
        self._quiet(parent_settings.write, self.root)
        data = json.loads(parent_settings.parent_settings_path(self.root).read_text())
        self.assertEqual(data["env"]["CLAUDE_WORKSPACE_ROOT"], str(self.root))
        self.assertIn("PreToolUse", data["hooks"])

    def test_run_check_reports_missing_then_ok(self):
        with patch("parent_settings.path_lib.require_workspace_root", return_value=self.root), \
                patch.dict(os.environ, {"CLAUDE_CODE_REMOTE": "true"}):
            self.assertEqual(self._quiet(parent_settings.run, argparse.Namespace(check=True)), 1)
            self.assertEqual(self._quiet(parent_settings.run, argparse.Namespace(check=False)), 0)
            self.assertEqual(self._quiet(parent_settings.run, argparse.Namespace(check=True)), 0)


class DestinationGuardTests(_Base):
    """The generator must never be able to clobber a user's own settings."""

    def _quiet(self, fn, *a):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return fn(*a)

    def _no_remote(self):
        env = dict(os.environ)
        env.pop("CLAUDE_CODE_REMOTE", None)
        env.pop(parent_settings.PARENT_DIR_ENV, None)
        return patch.dict(os.environ, env, clear=True)

    def test_subcommand_refuses_outside_cloud(self):
        with self._no_remote(), \
                patch("parent_settings.path_lib.require_workspace_root", return_value=self.root):
            with self.assertRaises(SystemExit) as cm:
                self._quiet(parent_settings.run, argparse.Namespace(check=False))
        self.assertIn("cloud-only", str(cm.exception))
        self.assertFalse(parent_settings.parent_settings_path(self.root).exists())

    def test_subcommand_check_also_refuses_outside_cloud(self):
        with self._no_remote(), \
                patch("parent_settings.path_lib.require_workspace_root", return_value=self.root):
            with self.assertRaises(SystemExit):
                self._quiet(parent_settings.run, argparse.Namespace(check=True))

    def test_override_bypasses_cloud_only(self):
        with self._no_remote(), \
                patch.dict(os.environ, {parent_settings.PARENT_DIR_ENV: str(self.home)}), \
                patch("parent_settings.path_lib.require_workspace_root", return_value=self.root):
            self.assertEqual(self._quiet(parent_settings.run, argparse.Namespace(check=False)), 0)

    def test_write_refuses_home_directory_even_in_cloud(self):
        # Clone at ~/workspace: the parent IS the home dir, the target would be
        # ~/.claude/settings.json. Refuse regardless of CLAUDE_CODE_REMOTE.
        with patch.dict(os.environ, {"CLAUDE_CODE_REMOTE": "true"}), \
                patch("parent_settings.Path.home", return_value=self.home):
            with self.assertRaises(SystemExit) as cm:
                self._quiet(parent_settings.write, self.root)
        self.assertIn("home directory", str(cm.exception))
        self.assertFalse((self.home / ".claude" / "settings.json").exists())

    def test_write_refuses_foreign_existing_file(self):
        # A hand-written settings file at the parent is somebody's config.
        p = parent_settings.parent_settings_path(self.root)
        p.parent.mkdir(parents=True)
        original = '{"model": "opus", "permissions": {"allow": ["Bash(ls:*)"]}}\n'
        p.write_text(original)
        with self.assertRaises(SystemExit) as cm:
            self._quiet(parent_settings.write, self.root)
        self.assertIn("not written by this generator", str(cm.exception))
        self.assertEqual(p.read_text(), original)

    def test_write_refuses_unparseable_existing_file(self):
        p = parent_settings.parent_settings_path(self.root)
        p.parent.mkdir(parents=True)
        p.write_text("{not json")
        with self.assertRaises(SystemExit):
            self._quiet(parent_settings.write, self.root)
        self.assertEqual(p.read_text(), "{not json")

    def test_write_repairs_our_own_stale_file(self):
        # A file carrying the marker is ours: drift in it is repaired.
        p = parent_settings.parent_settings_path(self.root)
        p.parent.mkdir(parents=True)
        p.write_text('{"env": {"WORKSPACE_PARENT_POLICY_VERSION": "0"}, "permissions": {}}\n')
        self.assertEqual(self._quiet(parent_settings.write, self.root), "written")
        self.assertTrue(parent_settings._is_ours(p.read_text()))

    def test_cloud_tier_swallows_guard_refusal(self):
        # cloud._write_parent_settings must log, not raise, when the guard fires.
        import cloud
        p = parent_settings.parent_settings_path(self.root)
        p.parent.mkdir(parents=True)
        p.write_text('{"model": "opus"}\n')
        err = io.StringIO()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
            cloud._write_parent_settings(self.root)  # must not raise
        self.assertIn("could not write the parent policy", err.getvalue())
        self.assertEqual(p.read_text(), '{"model": "opus"}\n')


class HookRuntimeTests(_Base):
    """Execute the generated sh commands against a fake clone."""

    def setUp(self):
        super().setUp()
        self.hooks = parent_settings.parent_hooks(str(self.root))
        self.bash_wrap = self.hooks["PreToolUse"][1]["hooks"][0]["command"]
        self.banner = self.hooks["SessionStart"][0]["hooks"][0]["command"]
        self.apply = self.hooks["SessionStart"][1]["hooks"][0]["command"]
        self.hooks_dir = self.root / ".claude" / "hooks"
        self.hooks_dir.mkdir()

    def _sh(self, cmd, cwd, stdin="", env=None):
        e = dict(os.environ)
        e.pop("CLAUDE_WORKSPACE_ROOT", None)
        e.update(env or {})
        return subprocess.run(["sh", "-c", cmd], cwd=str(cwd), input=stdin,
                              capture_output=True, text=True, env=e)

    def _install(self, name, body):
        h = self.hooks_dir / name
        h.write_text(body)
        h.chmod(0o755)
        return h

    def test_wrapper_execs_root_hook_with_stdin_and_env(self):
        capture = self.root / "captured.txt"
        envcap = self.root / "env.txt"
        self._install("protect-config.sh",
                      f'#!/bin/sh\ncat > "{capture}"\n'
                      f'printf "%s" "$CLAUDE_WORKSPACE_ROOT" > "{envcap}"\nexit 3\n')
        payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": "ls"}})
        # cwd is the PARENT, as in a real multi-repo session.
        r = self._sh(self.bash_wrap, self.home, stdin=payload)
        self.assertEqual(r.returncode, 3)
        self.assertEqual(capture.read_text(), payload)
        self.assertEqual(envcap.read_text(), str(self.root))

    def test_wrapper_fails_closed_without_clone(self):
        shutil.rmtree(self.root)
        payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": "ls"}})
        r = self._sh(self.bash_wrap, self.home, stdin=payload)
        self.assertEqual(r.returncode, 2)
        self.assertIn("Failing closed (Bash blocked)", r.stderr)
        self.assertIn(str(self.root), r.stderr)

    def test_wrapper_fails_closed_without_script(self):
        payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": "ls"}})
        r = self._sh(self.bash_wrap, self.home, stdin=payload)
        self.assertEqual(r.returncode, 2)

    def test_banner_delegates_from_inside_clone(self):
        # The root banner locates the workspace by walking up from its cwd, so
        # the wrapper must cd into the clone before exec'ing it.
        self._install("status-banner.sh",
                      '#!/bin/sh\nprintf "%s|%s|%s" "$PWD" "$1" "$CLAUDE_WORKSPACE_ROOT"\n')
        r = self._sh(self.banner, self.home)
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout, f"{self.root}|team|{self.root}")

    def test_banner_not_detected_without_clone(self):
        shutil.rmtree(self.root)
        r = self._sh(self.banner, self.home)
        self.assertEqual(r.returncode, 0)
        payload = json.loads(r.stdout)
        self.assertIn("NOT DETECTED", payload["hookSpecificOutput"]["additionalContext"])
        self.assertIn("systemMessage", payload)
        self.assertNotIn("systemMessage", payload["hookSpecificOutput"])

    def test_apply_hook_runs_bootstrap_from_clone_only_in_cloud(self):
        tools = self.root / "tools" / "bootstrap"
        tools.mkdir(parents=True)
        marker = self.root / "ran.txt"
        (tools / "bootstrap.py").write_text(
            f'import os, sys\nopen("{marker}", "w").write(os.getcwd() + " " + " ".join(sys.argv[1:]))\n')
        r = self._sh(self.apply, self.home, env={"CLAUDE_CODE_REMOTE": "false"})
        self.assertEqual(r.returncode, 0)
        self.assertFalse(marker.exists())
        r = self._sh(self.apply, self.home, env={"CLAUDE_CODE_REMOTE": "true"})
        self.assertEqual(r.returncode, 0)
        self.assertEqual(marker.read_text(), f"{self.root} cloud --apply-only")

    def test_apply_hook_silent_without_clone(self):
        shutil.rmtree(self.root)
        r = self._sh(self.apply, self.home, env={"CLAUDE_CODE_REMOTE": "true"})
        self.assertEqual(r.returncode, 0)
        # Silent means silent: no stray `sh: cd: can't cd to ...` at session start.
        self.assertEqual(r.stderr, "")
        self.assertEqual(r.stdout, "")


if __name__ == "__main__":
    unittest.main()
