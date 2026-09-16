"""Tests for tools/bootstrap/lint.py.

Each check gets a temp-repo fixture: one case where the tree is clean and one
where it is broken, so a check that silently stops finding anything fails a
test rather than turning CI green.
"""

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import lint            # noqa: E402
import settings_sync   # noqa: E402


ROOT_SETTINGS = {
    "permissions": {
        "defaultMode": "acceptEdits",
        "deny": ["Read(~/.ssh/**)"],
    },
    "sandbox": {
        "enabled": True,
        "filesystem": {
            "denyRead": ["~/.ssh/**", "~/.aws/**", "**/.env", "**/.mcp.json"],
        },
    },
    "hooks": {"PreToolUse": []},
}

GITIGNORE = """\
**/projects/**
!**/projects/.gitkeep
**/settings.local.json
.env*
!.env.example
.mcp.json
CLAUDE.local.md
"""


def _git(root, *argv):
    return subprocess.run(
        ["git", "-C", str(root)] + list(argv), capture_output=True, text=True,
    )


def _write(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def make_workspace(root: Path):
    """A minimal tree that passes every check: root markers, one department
    with a stamp, a clean .gitignore, and an executable hook."""
    _write(root / "CLAUDE.md", "# Acme context\n")
    _write(root / ".gitignore", GITIGNORE)
    _write(root / ".claude" / "settings.json",
           json.dumps(ROOT_SETTINGS, indent=2) + "\n")
    hook = root / ".claude" / "hooks" / "protect-config.sh"
    _write(hook, "#!/bin/sh\nexit 0\n")
    hook.chmod(0o755)
    _write(root / "departments" / "sales" / "CLAUDE.md", "# Sales context\n")
    _write(root / "departments" / "sales" / "projects" / ".gitkeep", "")

    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@example.com")
    _git(root, "config", "user.name", "t")
    stamp(root)
    _git(root, "add", "-A")
    return root


def stamp(root: Path):
    """Write the derived team settings for every department folder."""
    expected = settings_sync.expected_content(root)
    for claude_md in (root / "departments").rglob("CLAUDE.md"):
        _write(claude_md.parent / ".claude" / "settings.json", expected)


def labels(findings):
    return sorted({label for label, _ in findings})


class LintFixtureBase(unittest.TestCase):
    def setUp(self):
        os.environ["NO_COLOR"] = "1"
        self.tmp = tempfile.TemporaryDirectory()
        self.root = make_workspace(Path(self.tmp.name) / "ws")

    def tearDown(self):
        self.tmp.cleanup()

    def findings_for(self, label):
        return [f for lbl, f in lint.findings(self.root) if lbl == label]


class CleanTreeTests(LintFixtureBase):
    def test_clean_fixture_has_no_findings(self):
        self.assertEqual(lint.findings(self.root), [])

    def test_run_exits_zero_on_a_clean_tree(self):
        cwd = os.getcwd()
        os.chdir(self.root)
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(lint.run(None), 0)
        finally:
            os.chdir(cwd)

    def test_run_exits_non_zero_on_a_finding(self):
        _write(self.root / "departments" / "sales" / "teams" / "sales" / "CLAUDE.md",
               "# duplicate basename\n")
        stamp(self.root)
        _git(self.root, "add", "-A")
        cwd = os.getcwd()
        os.chdir(self.root)
        try:
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(lint.run(None), 1)
        finally:
            os.chdir(cwd)


class UniqueFolderNameTests(LintFixtureBase):
    LABEL = "unique-folder-names"

    def test_unique_basenames_pass(self):
        _write(self.root / "departments" / "finance" / "CLAUDE.md", "# Finance\n")
        stamp(self.root)
        _git(self.root, "add", "-A")
        self.assertEqual(self.findings_for(self.LABEL), [])

    def test_duplicate_basename_is_a_finding(self):
        _write(
            self.root / "departments" / "finance" / "teams" / "sales" / "CLAUDE.md",
            "# collides with departments/sales\n",
        )
        stamp(self.root)
        _git(self.root, "add", "-A")
        found = self.findings_for(self.LABEL)
        self.assertEqual(len(found), 1)
        self.assertIn("'sales'", found[0])

    def test_tooling_fixtures_are_excluded(self):
        _write(self.root / "tools" / "bootstrap" / "tests" / "sales" / "CLAUDE.md",
               "# fixture, not a team\n")
        _git(self.root, "add", "-A")
        self.assertEqual(self.findings_for(self.LABEL), [])


class ImportTests(LintFixtureBase):
    LABEL = "claude-md-imports"

    def test_resolvable_import_passes(self):
        _write(self.root / "departments" / "sales" / "context" / "pricing.md", "# p\n")
        _write(self.root / "departments" / "sales" / "CLAUDE.md",
               "# Sales context\n\n@context/pricing.md\n")
        _git(self.root, "add", "-A")
        self.assertEqual(self.findings_for(self.LABEL), [])

    def test_gitignored_target_passes(self):
        _write(self.root / "CLAUDE.md", "# Acme context\n\n@CLAUDE.local.md\n")
        _git(self.root, "add", "-A")
        self.assertEqual(self.findings_for(self.LABEL), [])

    def test_broken_import_is_a_finding(self):
        _write(self.root / "departments" / "sales" / "CLAUDE.md",
               "# Sales context\n\n@context/typo.md\n")
        _git(self.root, "add", "-A")
        found = self.findings_for(self.LABEL)
        self.assertEqual(len(found), 1)
        self.assertIn("context/typo.md", found[0])

    def test_at_mention_in_prose_is_not_an_import(self):
        _write(self.root / "departments" / "sales" / "CLAUDE.md",
               "# Sales context\n\nAsk @someone about context/typo.md\n")
        _git(self.root, "add", "-A")
        self.assertEqual(self.findings_for(self.LABEL), [])


class GitignoreTests(LintFixtureBase):
    LABEL = "gitignore-entries"

    def test_required_entries_present(self):
        self.assertEqual(self.findings_for(self.LABEL), [])

    def test_missing_entry_is_a_finding(self):
        text = (self.root / ".gitignore").read_text().replace(".mcp.json\n", "")
        _write(self.root / ".gitignore", text)
        _git(self.root, "add", "-A")
        found = self.findings_for(self.LABEL)
        self.assertEqual(len(found), 1)
        self.assertIn(".mcp.json", found[0])


class SettingsSyncTests(LintFixtureBase):
    LABEL = "settings-sync"

    def test_stamps_in_sync(self):
        self.assertEqual(self.findings_for(self.LABEL), [])

    def test_drifted_stamp_is_a_finding(self):
        stamp_file = (self.root / "departments" / "sales"
                      / ".claude" / "settings.json")
        _write(stamp_file, json.dumps({"permissions": {}}, indent=2) + "\n")
        found = self.findings_for(self.LABEL)
        self.assertEqual(len(found), 1)
        self.assertIn("drift", found[0])

    def test_missing_stamp_is_a_finding(self):
        (self.root / "departments" / "sales" / ".claude" / "settings.json").unlink()
        found = self.findings_for(self.LABEL)
        self.assertEqual(len(found), 1)
        self.assertIn("missing", found[0])


class HookExecutableTests(LintFixtureBase):
    LABEL = "hooks-executable"

    def test_executable_hook_passes(self):
        self.assertEqual(self.findings_for(self.LABEL), [])

    def test_non_executable_hook_is_a_finding(self):
        (self.root / ".claude" / "hooks" / "protect-config.sh").chmod(0o644)
        found = self.findings_for(self.LABEL)
        self.assertEqual(len(found), 1)
        self.assertIn("protect-config.sh", found[0])


class CommittedSecretTests(LintFixtureBase):
    LABEL = "no-secrets-committed"

    def test_clean_tree_passes(self):
        _write(self.root / ".env.example", "TOKEN=\n")
        _git(self.root, "add", "-f", ".env.example")
        self.assertEqual(self.findings_for(self.LABEL), [])

    def test_committed_settings_local_is_a_finding(self):
        _write(self.root / ".claude" / "settings.local.json", "{}\n")
        _git(self.root, "add", "-f", ".claude/settings.local.json")
        found = self.findings_for(self.LABEL)
        self.assertEqual(len(found), 1)
        self.assertIn("settings.local.json", found[0])

    def test_settings_local_inside_projects_is_allowed(self):
        _write(self.root / "departments" / "sales" / "projects" / "x"
               / ".claude" / "settings.local.json", "{}\n")
        _git(self.root, "add", "-f",
             "departments/sales/projects/x/.claude/settings.local.json")
        self.assertEqual(self.findings_for(self.LABEL), [])

    def test_committed_env_is_a_finding(self):
        _write(self.root / ".env", "SECRET=1\n")
        _git(self.root, "add", "-f", ".env")
        found = self.findings_for(self.LABEL)
        self.assertEqual(len(found), 1)
        self.assertIn(".env", found[0])

    def test_committed_mcp_json_is_a_finding(self):
        _write(self.root / ".mcp.json", "{}\n")
        _git(self.root, "add", "-f", ".mcp.json")
        found = self.findings_for(self.LABEL)
        self.assertEqual(len(found), 1)
        self.assertIn(".mcp.json", found[0])


class RootSettingsTests(LintFixtureBase):
    LABEL = "root-settings"

    def test_valid_policy_passes(self):
        self.assertEqual(self.findings_for(self.LABEL), [])

    def test_sandbox_disabled_is_a_finding(self):
        bad = json.loads(json.dumps(ROOT_SETTINGS))
        bad["sandbox"]["enabled"] = False
        _write(self.root / ".claude" / "settings.json",
               json.dumps(bad, indent=2) + "\n")
        stamp(self.root)
        found = self.findings_for(self.LABEL)
        self.assertEqual(len(found), 1)
        self.assertIn("sandbox.enabled", found[0])

    def test_missing_deny_read_is_a_finding(self):
        bad = json.loads(json.dumps(ROOT_SETTINGS))
        bad["sandbox"]["filesystem"]["denyRead"] = ["~/.ssh/**"]
        _write(self.root / ".claude" / "settings.json",
               json.dumps(bad, indent=2) + "\n")
        stamp(self.root)
        found = self.findings_for(self.LABEL)
        self.assertEqual(len(found), 1)
        self.assertIn("denyRead", found[0])


class TeamSettingsTests(LintFixtureBase):
    LABEL = "team-settings"

    def test_stamped_copies_pass(self):
        self.assertEqual(self.findings_for(self.LABEL), [])

    def test_stamp_without_policy_version_is_a_finding(self):
        stamp_file = (self.root / "departments" / "sales"
                      / ".claude" / "settings.json")
        data = json.loads(stamp_file.read_text())
        data["env"].pop("WORKSPACE_TEAM_POLICY_VERSION")
        _write(stamp_file, json.dumps(data, indent=2) + "\n")
        _git(self.root, "add", "-A")
        found = self.findings_for(self.LABEL)
        self.assertEqual(len(found), 1)
        self.assertIn("WORKSPACE_TEAM_POLICY_VERSION", found[0])

    def test_mcp_keys_in_a_stamp_are_a_finding(self):
        stamp_file = (self.root / "departments" / "sales"
                      / ".claude" / "settings.json")
        data = json.loads(stamp_file.read_text())
        data["enableAllProjectMcpServers"] = True
        _write(stamp_file, json.dumps(data, indent=2) + "\n")
        _git(self.root, "add", "-A")
        found = self.findings_for(self.LABEL)
        self.assertEqual(len(found), 1)
        self.assertIn("MCP keys", found[0])


class InfrastructureTests(unittest.TestCase):
    def test_no_git_checkout_raises_rather_than_reporting_clean(self):
        os.environ["NO_COLOR"] = "1"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "ws"
            (root / "departments").mkdir(parents=True)
            _write(root / "CLAUDE.md", "# x\n")
            _write(root / ".claude" / "settings.json", "{}\n")
            with self.assertRaises(SystemExit):
                lint.findings(root)


if __name__ == "__main__":
    unittest.main()
