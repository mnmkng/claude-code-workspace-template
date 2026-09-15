"""Tests for tools/bootstrap/scaffold.py.

One test per validation rule (each rule refuses the whole spec, so the
"nothing was written" assertion is the important half), the idempotence and
additive-only contracts, the CODEOWNERS insertion points, and an end-to-end
run that scaffolds two departments into a temp git repo and asserts
settings-sync --check and lint pass afterwards.
"""

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import lint            # noqa: E402
import scaffold        # noqa: E402
import settings_sync   # noqa: E402

from test_lint import GITIGNORE, ROOT_SETTINGS, _git, _write  # noqa: E402


CODEOWNERS = """\
# CODEOWNERS for the knowledge workspace.

*                                                                  @acme/workspace-owners

# ---------------------------------------------------------------------------
# Departments
# ---------------------------------------------------------------------------

/departments/sales/                                                @sales-lead

# ---------------------------------------------------------------------------
# Teams - override the dept owner for that team's folder.
# ---------------------------------------------------------------------------

/departments/sales/teams/east-sales/                               @east-lead @sales-lead

# ---------------------------------------------------------------------------
# Workspace-wide files.
# ---------------------------------------------------------------------------

/CLAUDE.md                                                         @acme/workspace-owners
"""

SPEC = {
    "company": {"name": "Acme Paper", "slug": "acme-paper"},
    "departments": [
        {
            "name": "marketing",
            "owner": "@marketing-lead",
            "tools": ["HubSpot", "Slack"],
            "teams": [{"name": "content-marketing", "owner": "@content-lead"}],
        },
        {"name": "finance", "owner": "@finance-lead", "tools": []},
    ],
}


def make_repo(root: Path):
    """A workspace-shaped git repo with one existing department."""
    _write(root / "CLAUDE.md", "# Acme context\n")
    _write(root / ".gitignore", GITIGNORE + DEPARTMENTS_ALLOWLIST)
    _write(root / ".claude" / "settings.json",
           json.dumps(ROOT_SETTINGS, indent=2) + "\n")
    hook = root / ".claude" / "hooks" / "protect-config.sh"
    _write(hook, "#!/bin/sh\nexit 0\n")
    hook.chmod(0o755)
    _write(root / ".github" / "CODEOWNERS", CODEOWNERS)
    _write(root / "departments" / "sales" / "CLAUDE.md", "# Sales context\n")
    _write(root / "departments" / "sales" / "projects" / ".gitkeep", "")
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@example.com")
    _git(root, "config", "user.name", "t")
    _write(root / "departments" / "sales" / ".claude" / "settings.json",
           settings_sync.expected_content(root))
    _git(root, "add", "-A")
    return root


# The real .gitignore's default-deny allowlist for departments/, trimmed to
# what the fixture needs: without it, `git add` of a scaffolded folder is a
# no-op and settings-sync sees nothing.
DEPARTMENTS_ALLOWLIST = """
departments/**
!departments/**/
!departments/*/CLAUDE.md
!departments/*/context/**/*.md
!departments/*/.claude/skills/**
!departments/*/projects/.gitkeep
!departments/**/teams/*/CLAUDE.md
!departments/**/teams/*/projects/.gitkeep
!departments/*/.claude/settings.json
!departments/**/teams/*/.claude/settings.json
departments/**/projects/**
!departments/**/projects/.gitkeep
"""


class ScaffoldBase(unittest.TestCase):
    def setUp(self):
        os.environ["NO_COLOR"] = "1"
        self.tmp = tempfile.TemporaryDirectory()
        self.root = make_repo(Path(self.tmp.name) / "ws")

    def tearDown(self):
        self.tmp.cleanup()

    def spec_file(self, spec):
        p = Path(self.tmp.name) / "spec.json"
        p.write_text(json.dumps(spec), encoding="utf-8")
        return p

    def run_scaffold(self, spec, dry_run=False):
        args = type("A", (), {"spec": str(self.spec_file(spec)),
                              "dry_run": dry_run})()
        cwd = os.getcwd()
        os.chdir(self.root)
        try:
            with contextlib.redirect_stdout(io.StringIO()), \
                    contextlib.redirect_stderr(io.StringIO()):
                return scaffold.run(args)
        finally:
            os.chdir(cwd)


class ValidationTests(ScaffoldBase):
    def assert_refused(self, spec, needle):
        with self.assertRaises(SystemExit) as ctx:
            self.run_scaffold(spec)
        self.assertIn(needle, str(ctx.exception))
        # Nothing may be written when a spec is refused: a half-made tree can
        # break the root markers every other subcommand needs.
        self.assertFalse((self.root / "departments" / "marketing").exists())

    def test_valid_spec_passes_validation(self):
        self.assertEqual(scaffold.validate(SPEC, self.root), [])

    def test_non_kebab_name_is_refused(self):
        bad = json.loads(json.dumps(SPEC))
        bad["departments"][0]["name"] = "Marketing Ops"
        self.assert_refused(bad, "kebab-case")

    def test_owner_without_at_is_refused(self):
        bad = json.loads(json.dumps(SPEC))
        bad["departments"][1]["owner"] = "finance-lead"
        self.assert_refused(bad, "must be a GitHub handle")

    def test_duplicate_basename_within_the_spec_is_refused(self):
        bad = json.loads(json.dumps(SPEC))
        bad["departments"][1]["name"] = "content-marketing"
        self.assert_refused(bad, "appears more than once")

    def test_basename_colliding_with_the_existing_tree_is_refused(self):
        bad = json.loads(json.dumps(SPEC))
        bad["departments"][0]["teams"][0]["name"] = "sales"
        self.assert_refused(bad, "already exists at")

    def test_reserved_folder_name_is_refused(self):
        bad = json.loads(json.dumps(SPEC))
        bad["departments"][1]["name"] = "teams"
        self.assert_refused(bad, "reserved folder name")

    def test_unknown_key_is_refused(self):
        bad = json.loads(json.dumps(SPEC))
        bad["departments"][1]["headcount"] = 4
        self.assert_refused(bad, "unknown key")

    def test_empty_departments_is_refused(self):
        self.assert_refused({"departments": []}, "non-empty list")

    def test_every_problem_is_reported_at_once(self):
        bad = {"departments": [
            {"name": "Bad Name", "owner": "nope"},
        ]}
        problems = scaffold.validate(bad, self.root)
        self.assertEqual(len(problems), 2)

    def test_company_is_optional(self):
        spec = {"departments": [{"name": "legal", "owner": "@legal-lead"}]}
        self.assertEqual(scaffold.validate(spec, self.root), [])

    def test_bad_company_slug_is_refused(self):
        bad = json.loads(json.dumps(SPEC))
        bad["company"]["slug"] = "Acme Paper"
        self.assert_refused(bad, "company.slug")


class RenderingTests(unittest.TestCase):
    def setUp(self):
        self.nodes = scaffold.plan_nodes(SPEC)
        self.by_name = {n["name"]: n for n in self.nodes}

    def test_paths_follow_the_canonical_layout(self):
        self.assertEqual(self.by_name["marketing"]["rel"], "departments/marketing")
        self.assertEqual(self.by_name["content-marketing"]["rel"],
                         "departments/marketing/teams/content-marketing")

    def test_title_is_sentence_case_from_the_folder_name(self):
        self.assertEqual(self.by_name["content-marketing"]["title"],
                         "Content marketing")

    def test_explicit_title_wins(self):
        node = scaffold.plan_nodes(
            {"departments": [{"name": "rev-ops", "owner": "@x",
                              "title": "RevOps"}]})[0]
        self.assertEqual(node["title"], "RevOps")

    def test_claude_md_has_the_four_standard_sections_in_order(self):
        body = scaffold.claude_md(self.by_name["marketing"])
        headings = [ln for ln in body.splitlines() if ln.startswith("## ")]
        self.assertEqual(headings, ["## Team structure", "## Key metrics",
                                    "## Processes", "## Tools and systems"])
        self.assertTrue(body.startswith("# Marketing context\n"))
        # One TODO per section, plus the orientation line.
        self.assertGreaterEqual(body.count("[TODO"), 5)

    def test_tools_are_listed_when_given(self):
        body = scaffold.claude_md(self.by_name["marketing"])
        self.assertIn("| HubSpot | [TODO] |", body)
        self.assertIn("| Slack | [TODO] |", body)

    def test_no_tools_leaves_a_todo(self):
        body = scaffold.claude_md(self.by_name["finance"])
        self.assertNotIn("| System | Used for |", body)
        self.assertIn("[TODO:", body.split("## Tools and systems")[1])

    def test_team_line_carries_team_then_department_owner(self):
        line = scaffold.codeowners_line(self.by_name["content-marketing"])
        self.assertTrue(line.startswith(
            "/departments/marketing/teams/content-marketing/"))
        self.assertTrue(line.rstrip().endswith("@content-lead @marketing-lead"))

    def test_department_line_carries_only_the_department_owner(self):
        line = scaffold.codeowners_line(self.by_name["finance"])
        self.assertTrue(line.rstrip().endswith("@finance-lead"))
        self.assertEqual(line.index("@"), scaffold.OWNER_COLUMN)


class CodeownersInsertionTests(unittest.TestCase):
    def test_new_lines_go_after_their_existing_blocks(self):
        updated, added = scaffold.codeowners_update(
            CODEOWNERS, scaffold.plan_nodes(SPEC))
        self.assertEqual(len(added), 3)
        lines = [ln for ln in updated.splitlines()
                 if ln.startswith("/departments/")]
        self.assertEqual(lines[0].split()[0], "/departments/sales/")
        # Every department line stays above every team line: GitHub applies the
        # last matching pattern, so the reverse would give teams the dept owner.
        last_dept = max(i for i, ln in enumerate(lines) if "/teams/" not in ln)
        first_team = min(i for i, ln in enumerate(lines) if "/teams/" in ln)
        self.assertLess(last_dept, first_team)

    def test_existing_paths_are_not_duplicated(self):
        spec = {"departments": [{"name": "sales", "owner": "@sales-lead"}]}
        _updated, added = scaffold.codeowners_update(
            CODEOWNERS, scaffold.plan_nodes(spec))
        self.assertEqual(added, [])

    def test_file_without_department_lines_gets_them_appended(self):
        text = "*                                  @acme/workspace-owners\n"
        updated, added = scaffold.codeowners_update(
            text, scaffold.plan_nodes(SPEC))
        self.assertEqual(len(added), 3)
        self.assertTrue(updated.startswith("*"))
        self.assertIn("/departments/finance/", updated)


class ApplyTests(ScaffoldBase):
    def test_dry_run_writes_nothing(self):
        rc = self.run_scaffold(SPEC, dry_run=True)
        self.assertEqual(rc, 0)
        self.assertFalse((self.root / "departments" / "marketing").exists())
        self.assertNotIn("/departments/marketing/",
                         (self.root / ".github" / "CODEOWNERS").read_text())

    def test_end_to_end_two_departments(self):
        rc = self.run_scaffold(SPEC)
        self.assertEqual(rc, 0, "scaffold must leave the tree checkable")

        for rel in ("departments/marketing/CLAUDE.md",
                    "departments/marketing/projects/.gitkeep",
                    "departments/marketing/teams/content-marketing/CLAUDE.md",
                    "departments/marketing/teams/content-marketing/projects/.gitkeep",
                    "departments/finance/CLAUDE.md",
                    "departments/finance/projects/.gitkeep"):
            self.assertTrue((self.root / rel).is_file(), rel)

        co = (self.root / ".github" / "CODEOWNERS").read_text()
        self.assertIn("/departments/finance/", co)
        self.assertIn("@content-lead @marketing-lead", co)

        # The two checks the brief names, run from outside scaffold.
        issues, _ = settings_sync.findings(self.root)
        self.assertEqual(issues, [])
        self.assertEqual(lint.findings(self.root), [])

    def test_new_folders_are_stamped_and_staged(self):
        self.run_scaffold(SPEC)
        stamp = (self.root / "departments" / "finance"
                 / ".claude" / "settings.json")
        self.assertTrue(stamp.is_file())
        tracked = _git(self.root, "ls-files").stdout.splitlines()
        self.assertIn("departments/finance/CLAUDE.md", tracked)
        self.assertIn("departments/finance/.claude/settings.json", tracked)

    def test_rerunning_the_same_spec_changes_nothing(self):
        self.run_scaffold(SPEC)
        before = _git(self.root, "status", "--porcelain").stdout
        digest = {p.as_posix(): p.read_bytes()
                  for p in (self.root / "departments").rglob("*") if p.is_file()}
        co_before = (self.root / ".github" / "CODEOWNERS").read_text()

        rc = self.run_scaffold(SPEC)
        self.assertEqual(rc, 0)
        after = {p.as_posix(): p.read_bytes()
                 for p in (self.root / "departments").rglob("*") if p.is_file()}
        self.assertEqual(digest, after)
        self.assertEqual(co_before,
                         (self.root / ".github" / "CODEOWNERS").read_text())
        self.assertEqual(before, _git(self.root, "status", "--porcelain").stdout)

    def test_hand_written_content_is_never_overwritten(self):
        self.run_scaffold(SPEC)
        md = self.root / "departments" / "finance" / "CLAUDE.md"
        md.write_text("# Finance context\n\nReal content.\n", encoding="utf-8")
        self.run_scaffold(SPEC)
        self.assertIn("Real content.", md.read_text())

    def test_adding_one_department_touches_only_it(self):
        self.run_scaffold(SPEC)
        marketing_before = (self.root / "departments" / "marketing"
                            / "CLAUDE.md").read_bytes()
        grown = json.loads(json.dumps(SPEC))
        grown["departments"].append({"name": "legal", "owner": "@legal-lead"})
        rc = self.run_scaffold(grown)
        self.assertEqual(rc, 0)
        self.assertTrue((self.root / "departments" / "legal" / "CLAUDE.md").is_file())
        self.assertEqual(marketing_before,
                         (self.root / "departments" / "marketing"
                          / "CLAUDE.md").read_bytes())
        co = [ln.split()[0] for ln in
              (self.root / ".github" / "CODEOWNERS").read_text().splitlines()
              if ln.startswith("/departments/")]
        self.assertEqual(co.count("/departments/marketing/"), 1)
        self.assertEqual(co.count("/departments/legal/"), 1)

    def test_missing_spec_file_is_a_clear_error(self):
        args = type("A", (), {"spec": str(self.root / "nope.json"),
                              "dry_run": False})()
        cwd = os.getcwd()
        os.chdir(self.root)
        try:
            with self.assertRaises(SystemExit) as ctx:
                scaffold.run(args)
        finally:
            os.chdir(cwd)
        self.assertIn("spec file not found", str(ctx.exception))

    def test_invalid_json_is_a_clear_error(self):
        p = Path(self.tmp.name) / "bad.json"
        p.write_text("{not json", encoding="utf-8")
        args = type("A", (), {"spec": str(p), "dry_run": False})()
        cwd = os.getcwd()
        os.chdir(self.root)
        try:
            with self.assertRaises(SystemExit) as ctx:
                scaffold.run(args)
        finally:
            os.chdir(cwd)
        self.assertIn("not valid JSON", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
