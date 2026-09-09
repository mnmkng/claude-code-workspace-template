import argparse
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cloud
import compose
from lib import localmd
from lib import manifest as manifest_lib
from lib import staging


def _make_fake_workspace(root: Path):
    """Create a minimal workspace-root-shaped tree for compose to operate on.

    Layout:
        root/CLAUDE.md
        root/.claude/settings.json
        root/departments/foo/CLAUDE.md
        root/departments/foo/.claude/skills/foo-skill/SKILL.md
    """
    (root / "CLAUDE.md").write_text("# root\n")
    (root / ".claude").mkdir()
    (root / ".claude" / "settings.json").write_text("{}\n")
    (root / "departments" / "foo").mkdir(parents=True)
    (root / "departments" / "foo" / "CLAUDE.md").write_text("# foo team\n")
    skill_dir = root / "departments" / "foo" / ".claude" / "skills" / "foo-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("skill body\n")


class CloudOrchestrationTests(unittest.TestCase):
    def setUp(self):
        os.environ["NO_COLOR"] = "1"
        self.tmp_root = tempfile.TemporaryDirectory()
        self.tmp_stage = tempfile.TemporaryDirectory()
        self.tmp_hook = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp_root.name).resolve()
        _make_fake_workspace(self.root)

        os.environ["WORKSPACE_TEAM"] = "foo"
        os.environ["WORKSPACE_COMPOSED_DIR"] = self.tmp_stage.name
        os.environ.pop("WORKSPACE_PERSONAL_GIST", None)
        # Pin the stop-hook path into a temp dir so neither the setup- nor the
        # apply-tier disable can ever touch the real /root/.claude/ hook. The
        # file is absent unless a test creates it (→ silent no-op by default).
        self.hook_path = Path(self.tmp_hook.name) / "stop-hook-git-check.sh"
        os.environ["WORKSPACE_STOP_HOOK_PATH"] = str(self.hook_path)

        # Pin workspace root detection to our temp workspace.
        self._root_patch = patch(
            "cloud.path_lib.require_workspace_root", return_value=self.root
        )
        self._root_patch.start()
        # compose.require_workspace_root resolves via the same lib module.
        self._compose_root_patch = patch(
            "compose.path_lib.require_workspace_root", return_value=self.root
        )
        self._compose_root_patch.start()

    def tearDown(self):
        self._root_patch.stop()
        self._compose_root_patch.stop()
        self.tmp_root.cleanup()
        self.tmp_stage.cleanup()
        self.tmp_hook.cleanup()
        for k in ("WORKSPACE_TEAM", "WORKSPACE_COMPOSED_DIR", "WORKSPACE_PERSONAL_GIST",
                  "WORKSPACE_STOP_HOOK_PATH"):
            os.environ.pop(k, None)

    # ---- compose-only / default mode ----

    def test_compose_only_runs_compose_and_skips_personal(self):
        with patch("cloud.personal.sync") as mock_personal:
            cloud.run(argparse.Namespace(compose_only=True, apply_only=False))
        mock_personal.assert_not_called()
        # Skills landed in root .claude/
        self.assertTrue((self.root / ".claude" / "skills" / "foo-skill" / "SKILL.md").is_file())

    def test_compose_only_stages_to_staging_dir(self):
        cloud.run(argparse.Namespace(compose_only=True, apply_only=False))
        staged = staging.staged_claude_dir()
        self.assertTrue(staged.is_dir())
        self.assertTrue((staged / "skills" / "foo-skill" / "SKILL.md").is_file())
        meta = staging.read_meta()
        self.assertIsNotNone(meta)
        self.assertEqual(meta["team_input"], "foo")
        self.assertIn("departments/foo", meta["chain_rel_paths"])

    # ---- Part A: --team on the cloud subcommand ----

    def test_compose_only_team_flag_forwards_to_compose(self):
        # No WORKSPACE_TEAM env: the flag alone must drive composition.
        os.environ.pop("WORKSPACE_TEAM", None)
        cloud.run(argparse.Namespace(compose_only=True, apply_only=False, team="foo"))
        self.assertTrue(
            (self.root / ".claude" / "skills" / "foo-skill" / "SKILL.md").is_file()
        )
        meta = staging.read_meta()
        self.assertEqual(meta["team_input"], "foo")
        self.assertIn("departments/foo", meta["chain_rel_paths"])

    def test_team_flag_overrides_env(self):
        # WORKSPACE_TEAM points elsewhere; explicit --team foo wins.
        os.environ["WORKSPACE_TEAM"] = "does-not-exist"
        cloud.run(argparse.Namespace(compose_only=True, apply_only=False, team="foo"))
        self.assertEqual(staging.read_meta()["team_input"], "foo")

    def test_compose_only_unset_team_errors_clearly(self):
        # Neither --team nor WORKSPACE_TEAM, and not root → loud error, no silent
        # default to root.
        os.environ.pop("WORKSPACE_TEAM", None)
        with self.assertRaises(SystemExit) as cm:
            cloud.run(argparse.Namespace(compose_only=True, apply_only=False))
        self.assertIn("required", str(cm.exception))

    # ---- Part B: root / no-team mode (sentinel team name "root") ----

    def test_root_mode_stages_base_and_empty_chain(self):
        os.environ.pop("WORKSPACE_TEAM", None)
        cloud.run(argparse.Namespace(compose_only=True, apply_only=False, team="root"))
        staged = staging.staged_claude_dir()
        self.assertTrue(staged.is_dir())
        # Base config is staged; no team overlay was copied.
        self.assertTrue((staged / "settings.json").is_file())
        self.assertFalse((staged / "skills" / "foo-skill").exists())
        meta = staging.read_meta()
        self.assertEqual(meta["team_input"], "root")
        self.assertEqual(meta["chain_rel_paths"], [])

    def test_root_mode_leaves_claude_md_untouched(self):
        os.environ.pop("WORKSPACE_TEAM", None)
        cloud.run(argparse.Namespace(compose_only=True, apply_only=False, team="root"))
        # #72: composition never modifies the tracked CLAUDE.md.
        self.assertEqual((self.root / "CLAUDE.md").read_text(), "# root\n")
        local_md = self.root / "CLAUDE.local.md"
        if local_md.is_file():
            self.assertNotIn(localmd.TEAM_START, local_md.read_text())

    def test_root_mode_apply_only_no_team_block_and_sync(self):
        os.environ.pop("WORKSPACE_TEAM", None)
        cloud.run(argparse.Namespace(compose_only=True, apply_only=False, team="root"))
        with patch("cloud.personal.sync") as mock_personal:
            cloud.run(argparse.Namespace(compose_only=False, apply_only=True))
        mock_personal.assert_called_once()
        # CLAUDE.md never touched; root mode writes no team-context block.
        self.assertEqual((self.root / "CLAUDE.md").read_text(), "# root\n")
        local_md = self.root / "CLAUDE.local.md"
        if local_md.is_file():
            self.assertNotIn(localmd.TEAM_START, local_md.read_text())

    def test_default_runs_compose_and_personal(self):
        with patch("cloud.personal.sync") as mock_personal:
            cloud.run(argparse.Namespace(compose_only=False, apply_only=False))
        mock_personal.assert_called_once()

    # ---- apply-only mode ----

    def _compose_then_clean_for_apply(self):
        """Run a compose+stage pass, then nuke .claude/ to simulate a stale session."""
        cloud.run(argparse.Namespace(compose_only=True, apply_only=False))
        # Simulate stale state: drop the team-composed skill.
        import shutil
        shutil.rmtree(self.root / ".claude" / "skills")

    def test_apply_only_restores_claude_dir_from_staging(self):
        self._compose_then_clean_for_apply()
        with patch("cloud.personal.sync"):
            cloud.run(argparse.Namespace(compose_only=False, apply_only=True))
        self.assertTrue((self.root / ".claude" / "skills" / "foo-skill" / "SKILL.md").is_file())

    def test_apply_only_does_not_revert_tracked_base_files(self):
        """Regression: apply-only must NOT overwrite git-tracked base .claude/
        files from the (possibly stale) snapshot. It previously copytree'd the
        whole staged .claude/, silently reverting committed changes such as the
        #57 deny-bypass guard. apply-only owns only the untracked overlay.
        """
        import shutil
        cloud.run(argparse.Namespace(compose_only=True, apply_only=False))
        # A committed change to a base file lands AFTER the snapshot was taken.
        settings = self.root / ".claude" / "settings.json"
        settings.write_text('{"security_fix": true}\n')
        # And the composed overlay is missing (fresh clone / stale session).
        shutil.rmtree(self.root / ".claude" / "skills")
        with patch("cloud.personal.sync"):
            cloud.run(argparse.Namespace(compose_only=False, apply_only=True))
        # Base file left exactly as committed - NOT reverted to the staged "{}".
        self.assertEqual(settings.read_text(), '{"security_fix": true}\n')
        # The untracked overlay IS restored - that remains the bootstrap's job.
        self.assertTrue(
            (self.root / ".claude" / "skills" / "foo-skill" / "SKILL.md").is_file()
        )

    def test_apply_only_propagates_new_team_artifact(self):
        """Option 3: a team artifact added AFTER the snapshot propagates on the
        next session, because apply-only re-composes from the live checkout
        rather than restoring the (stale) staged overlay.
        """
        cloud.run(argparse.Namespace(compose_only=True, apply_only=False))
        # Creator adds a brand-new skill to the team folder post-snapshot.
        new_skill = self.root / "departments" / "foo" / ".claude" / "skills" / "foo-new"
        new_skill.mkdir(parents=True)
        (new_skill / "SKILL.md").write_text("new skill body\n")
        with patch("cloud.personal.sync"):
            cloud.run(argparse.Namespace(compose_only=False, apply_only=True))
        # Picked up live - no cache rebuild needed. (Under staging-restore it
        # would be absent, since the snapshot predates it.)
        self.assertTrue(
            (self.root / ".claude" / "skills" / "foo-new" / "SKILL.md").is_file()
        )

    def test_apply_only_falls_back_to_staging_when_recompose_fails(self):
        """If live re-composition fails, apply-only restores the last-known-good
        staged overlay so the session still gets a working composition.
        """
        import shutil
        cloud.run(argparse.Namespace(compose_only=True, apply_only=False))
        shutil.rmtree(self.root / ".claude" / "skills")  # overlay gone
        with patch("cloud.compose.run", side_effect=SystemExit("boom")), \
             patch("cloud.personal.sync"):
            cloud.run(argparse.Namespace(compose_only=False, apply_only=True))
        # Fallback restored the overlay from the staged snapshot.
        self.assertTrue(
            (self.root / ".claude" / "skills" / "foo-skill" / "SKILL.md").is_file()
        )

    def test_apply_only_reapplies_team_imports_to_local_md(self):
        cloud.run(argparse.Namespace(compose_only=True, apply_only=False))
        local_md = self.root / "CLAUDE.local.md"
        # Simulate a fresh clone: the gitignored file is gone at session start.
        if local_md.is_file():
            local_md.unlink()
        with patch("cloud.personal.sync"):
            cloud.run(argparse.Namespace(compose_only=False, apply_only=True))
        text = local_md.read_text()
        self.assertIn(localmd.TEAM_START, text)
        self.assertIn("@departments/foo/CLAUDE.md", text)
        self.assertIn(localmd.TEAM_END, text)
        # The tracked CLAUDE.md is left alone.
        self.assertEqual((self.root / "CLAUDE.md").read_text(), "# root\n")

    def test_apply_only_calls_personal(self):
        cloud.run(argparse.Namespace(compose_only=True, apply_only=False))
        with patch("cloud.personal.sync") as mock_personal:
            cloud.run(argparse.Namespace(compose_only=False, apply_only=True))
        mock_personal.assert_called_once()

    def test_apply_only_missing_staging_errors(self):
        # No prior compose → no staging dir.
        with self.assertRaises(SystemExit) as cm:
            cloud.run(argparse.Namespace(compose_only=False, apply_only=True))
        self.assertIn("staging dir", str(cm.exception))

    def test_apply_only_missing_meta_errors(self):
        cloud.run(argparse.Namespace(compose_only=True, apply_only=False))
        staging.meta_path().unlink()
        with self.assertRaises(SystemExit) as cm:
            cloud.run(argparse.Namespace(compose_only=False, apply_only=True))
        self.assertIn("meta", str(cm.exception))

    def test_apply_only_idempotent(self):
        cloud.run(argparse.Namespace(compose_only=True, apply_only=False))
        with patch("cloud.personal.sync"):
            cloud.run(argparse.Namespace(compose_only=False, apply_only=True))
            cloud.run(argparse.Namespace(compose_only=False, apply_only=True))
        # Team-context block appears exactly once in CLAUDE.local.md.
        text = (self.root / "CLAUDE.local.md").read_text()
        self.assertEqual(text.count(localmd.TEAM_START), 1)
        self.assertEqual(text.count(localmd.TEAM_END), 1)

    # ---- stop-hook durability across the apply tier (#72) ----

    def _write_real_hook(self):
        """Drop a real (exit-2) git-check hook at the pinned path."""
        self.hook_path.write_text("#!/bin/bash\necho real-hook\nexit 2\n")
        self.hook_path.chmod(0o755)

    def test_compose_only_records_disable_intent_in_meta(self):
        cloud.run(argparse.Namespace(
            compose_only=True, apply_only=False, disable_stop_hook=True))
        self.assertTrue(staging.read_meta()["disable_stop_hook"])

    def test_compose_only_meta_defaults_disable_false(self):
        # No --disable-stop-hook → recorded as False, so apply never touches it.
        cloud.run(argparse.Namespace(compose_only=True, apply_only=False))
        self.assertFalse(staging.read_meta()["disable_stop_hook"])

    def test_apply_only_reapplies_stop_hook_when_meta_set(self):
        self._write_real_hook()
        cloud.run(argparse.Namespace(
            compose_only=True, apply_only=False, disable_stop_hook=True))
        # Setup tier neutralized it once and backed up the original.
        self.assertEqual(self.hook_path.read_text(), cloud.STOP_HOOK_NOOP_BODY)
        backup = Path(str(self.hook_path) + ".original")
        self.assertTrue(backup.is_file())

        # Simulate the platform clobbering our no-op on session start.
        self._write_real_hook()
        with patch("cloud.personal.sync"):
            cloud.run(argparse.Namespace(compose_only=False, apply_only=True))
        # Apply tier re-neutralized it, and the .original backup is untouched.
        self.assertEqual(self.hook_path.read_text(), cloud.STOP_HOOK_NOOP_BODY)
        self.assertIn("exit 2", backup.read_text())

    def test_apply_only_skips_stop_hook_when_meta_unset(self):
        self._write_real_hook()
        original = self.hook_path.read_text()
        # Composed without the flag → meta disable_stop_hook is False.
        cloud.run(argparse.Namespace(compose_only=True, apply_only=False))
        with patch("cloud.personal.sync"):
            cloud.run(argparse.Namespace(compose_only=False, apply_only=True))
        # Hook left exactly as the platform shipped it; no backup written.
        self.assertEqual(self.hook_path.read_text(), original)
        self.assertFalse((Path(str(self.hook_path) + ".original")).exists())

    def test_apply_only_disable_silent_when_hook_absent(self):
        # Engineer-local shape: meta says disable, but no platform hook on disk.
        cloud.run(argparse.Namespace(
            compose_only=True, apply_only=False, disable_stop_hook=True))
        self.assertFalse(self.hook_path.exists())
        with patch("cloud.personal.sync"):
            cloud.run(argparse.Namespace(compose_only=False, apply_only=True))
        self.assertFalse(self.hook_path.exists())

    def test_apply_only_disable_honors_env_override(self):
        # _apply_only resolves the hook path at call time via WORKSPACE_STOP_HOOK_PATH.
        self.assertEqual(cloud._stop_hook_path(), str(self.hook_path))

    # ---- misc ----

    def test_log_file_written(self):
        with patch("cloud.personal.sync"):
            cloud.run(argparse.Namespace(compose_only=True, apply_only=False))
        log_file = self.root / cloud.BOOTSTRAP_LOG_REL
        self.assertTrue(log_file.is_file())
        text = log_file.read_text()
        self.assertIn("cloud: mode=compose-only", text)

    def test_mutually_exclusive_flags(self):
        with self.assertRaises(SystemExit):
            cloud.run(argparse.Namespace(compose_only=True, apply_only=True))


class DisableStopHookTests(unittest.TestCase):
    def setUp(self):
        os.environ["NO_COLOR"] = "1"
        self.tmp = tempfile.TemporaryDirectory()
        self.hook = Path(self.tmp.name) / "stop-hook-git-check.sh"
        self.original_body = "#!/bin/bash\necho real-hook\nexit 2\n"
        self.hook.write_text(self.original_body)
        self.hook.chmod(0o755)

    def tearDown(self):
        self.tmp.cleanup()

    def test_neutralizes_hook_and_preserves_original(self):
        cloud._disable_stop_hook(hook_path=str(self.hook))
        # New content is the no-op body, original preserved at .original
        self.assertEqual(self.hook.read_text(), cloud.STOP_HOOK_NOOP_BODY)
        self.assertTrue((Path(str(self.hook) + ".original")).is_file())
        self.assertEqual(
            Path(str(self.hook) + ".original").read_text(), self.original_body
        )

    def test_idempotent_does_not_clobber_original(self):
        cloud._disable_stop_hook(hook_path=str(self.hook))
        # Second run must NOT overwrite the .original with the no-op version
        cloud._disable_stop_hook(hook_path=str(self.hook))
        self.assertEqual(
            Path(str(self.hook) + ".original").read_text(), self.original_body
        )

    def test_missing_hook_is_silent_noop(self):
        nonexistent = Path(self.tmp.name) / "no-such-hook.sh"
        # Should not raise; should not create anything
        cloud._disable_stop_hook(hook_path=str(nonexistent))
        self.assertFalse(nonexistent.exists())
        self.assertFalse((Path(str(nonexistent) + ".original")).exists())


if __name__ == "__main__":
    unittest.main()
