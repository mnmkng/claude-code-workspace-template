"""Tests for tools/maintenance/check.py (issue #178).

Covers the strict YAML subset parser (flat mappings, lists, inline lists,
comments, quotes; rejection of what YAML would read differently, with a
PyYAML cross-check when it is installed), header validation (required,
recommended, unknown keys, formats), staleness, the org-chart owner lookup,
data-file cards (sibling .md cards), derived freshness from sync-only commits on
cards,
the merge-base rule for --changed-since, and the exit-code contract.
"""

import datetime as dt
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import check  # noqa: E402

try:
    import yaml  # type: ignore
except ImportError:  # the checker itself is stdlib-only; the cross-check is opportunistic
    yaml = None

REPO = Path(__file__).resolve().parents[3]
TODAY = dt.date(2026, 9, 10)
PEOPLE = {check.fold("Zoë Müller"), check.fold("Zoë M."), check.fold("Óscar Martínez")}


def header(**over):
    h = {"sources": ["Notion: X"], "owner": "Zoë Müller", "edit": "here",
         "review_every": "90d", "verified_at": "2026-09-01"}
    h.update(over)
    return h


def as_yaml_would(value):
    """PyYAML types a bare date; the subset keeps it as text. Normalize for comparison."""
    if isinstance(value, dt.date):
        return value.isoformat()
    if isinstance(value, list):
        return [as_yaml_would(v) for v in value]
    if isinstance(value, dict):
        return {k: as_yaml_would(v) for k, v in value.items()}
    return value


class Parser(unittest.TestCase):
    def parse(self, text):
        return check.parse_yaml_subset(text.splitlines())

    def test_mapping_lists_and_scalars(self):
        d = self.parse('sources:\n  - "Notion: X"\n  - the HR system\nowner: Angela Martin\nedit: here\nreview_every: 90d\n')
        self.assertEqual(d, {"sources": ["Notion: X", "the HR system"], "owner": "Angela Martin",
                             "edit": "here", "review_every": "90d"})

    def test_inline_list_and_quotes(self):
        d = self.parse('files: [a.json, "b, c.csv"]\nowner: "Óscar Martínez"  # cfo\n')
        self.assertEqual(d, {"files": ["a.json", "b, c.csv"], "owner": "Óscar Martínez"})
        self.assertEqual(self.parse("files: [a.json]  # the data\n"), {"files": ["a.json"]})
        with self.assertRaises(check.ParseError):
            self.parse("files: [a.json] b\n")

    def test_comment_stripping_needs_space(self):
        d = self.parse('sources: "Slack: #finances channel"\nowner: Angela Martin # lead\n')
        self.assertEqual(d["sources"], "Slack: #finances channel")
        self.assertEqual(d["owner"], "Angela Martin")

    def test_empty_value_is_none(self):
        self.assertEqual(self.parse("verified_at:\n"), {"verified_at": None})

    def test_dates_stay_text(self):
        self.assertEqual(self.parse("verified_at: 2026-09-01\n"), {"verified_at": "2026-09-01"})

    def test_rejects_what_yaml_reads_differently(self):
        # Each of these is valid YAML that a naive split would read as something else,
        # or a construct outside the subset. All must be parse errors, never silent.
        for bad in [
            "sources:\n  - Notion: X\n",          # YAML: a list of one mapping
            "sources: Slack: #finances\n",         # YAML: scanner error
            "sources: Slack:\n",                   # YAML: nested key
            'owner: "x" y\n',                      # text after the closing quote
            'owner: "a \\"b\\""\n',                # escapes we do not process
            "description: >\n  folded\n",          # block scalar
            "metadata:\n  edit: upstream\n",       # nested mapping
            "owner: yes\n", "owner: ~\n", "review_every: 90\n", "owner: [x\n",
            "sources:\n  -\n",                     # empty list item
            "sources:\n  - - x\n",                 # nested list
        ]:
            with self.assertRaises(check.ParseError, msg=bad):
                self.parse(bad)

    def test_errors(self):
        for bad in ["- item\n", "edit here\n", "a: 1\na: 2\n", "sources:\n  - x\n y: 2\n", 'owner: "open\n',
                    "\tedit: here\n"]:
            with self.assertRaises(check.ParseError, msg=bad):
                self.parse(bad)

    def test_split_frontmatter(self):
        self.assertEqual(check.split_frontmatter("# No header\n"), (None, None))
        self.assertEqual(check.split_frontmatter("---\nedit: here\n---\n# T\n"), ({"edit": "here"}, None))
        h, err = check.split_frontmatter("---\nedit: here\n# T\n")
        self.assertIsNone(h)
        self.assertIn("never closed", err)

    @unittest.skipIf(yaml is None, "PyYAML not installed; the subset is stdlib-only by design")
    def test_subset_agrees_with_pyyaml_on_every_header_in_the_repo(self):
        """The property the subset promises: whatever it accepts, YAML reads identically."""
        samples = [
            'sources:\n  - "Notion: X, https://n.so/1"\n  - the HR system\nowner: Angela Martin\nedit: here\n'
            'review_every: 90d\nverified_at: 2026-09-01\nfiles: [a.json, "b, c.csv"]\n',
            'owner: "Óscar Martínez"  # cfo\nsources: \'Slack: #finances\'\n',
        ]
        if (REPO / "CONTRIBUTING.md").is_file():
            tracked = subprocess.run(["git", "-C", str(REPO), "ls-files", "-z"],
                                     capture_output=True).stdout.decode().split("\0")
            for f in tracked:
                if f.endswith(".md") and check.in_scope(f) and (REPO / f).is_file():
                    text = (REPO / f).read_text(encoding="utf-8", errors="replace")
                    lines = text.splitlines()
                    if lines and lines[0].strip() == "---" and "---" in [l.strip() for l in lines[1:]]:
                        end = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
                        samples.append("\n".join(lines[1:end]) + "\n")
        checked = 0
        for sample in samples:
            try:
                ours = check.parse_yaml_subset(sample.splitlines())
            except check.ParseError:
                continue  # rejected by the subset: no agreement required
            self.assertEqual(ours, as_yaml_would(yaml.safe_load(sample)), sample)
            checked += 1
        self.assertGreaterEqual(checked, 2)


class Validate(unittest.TestCase):
    def v(self, h, **kw):
        return check.validate_header("f.md", h, TODAY, PEOPLE, **kw)

    def test_clean(self):
        errs, warns, claimed = self.v(header())
        self.assertEqual((errs, warns, claimed), ([], [], []))

    def test_required_and_values(self):
        errs, _, _ = self.v({"owner": "x"})
        self.assertTrue(any("`edit` is required" in e for e in errs))
        self.assertTrue(any("`review_every` is required" in e for e in errs))
        errs, _, _ = self.v(header(edit="notion", review_every="3 months", verified_at="Sept 2026"))
        self.assertEqual(len(errs), 3)

    def test_upstream_requires_sources(self):
        errs, warns, _ = self.v({"edit": "upstream", "review_every": "90d"})
        self.assertTrue(any("`edit: upstream` requires `sources`" in e for e in errs))
        self.assertFalse(any("`sources` not set" in w for w in warns))  # reported once, as the error
        errs, _, _ = self.v(header(edit="upstream"))
        self.assertEqual(errs, [])

    def test_unknown_key(self):
        errs, _, _ = self.v(header(updated="2026-01-01"))
        self.assertTrue(any("unknown header key `updated`" in e for e in errs))

    def test_recommended_missing_is_warning(self):
        errs, warns, _ = self.v({"edit": "here", "review_every": "90d"})
        self.assertEqual(errs, [])
        self.assertEqual(sorted(w.split("`")[1] for w in warns), ["owner", "sources", "verified_at"])

    def test_owner_not_in_org_chart(self):
        _, warns, _ = self.v(header(owner="Nobody Here"))
        self.assertTrue(any("not in the org chart" in w for w in warns))
        _, warns, _ = self.v(header(owner="Zoe Muller"))  # accent-insensitive
        self.assertEqual(warns, [])
        _, warns, _ = check.validate_header("f.md", header(owner="Nobody"), TODAY, None)
        self.assertEqual(warns, [])  # no org chart available: skip

    def test_stale(self):
        _, warns, _ = self.v(header(verified_at="2026-01-01", review_every="90d"))
        self.assertTrue(any("stale" in w for w in warns))
        _, warns, _ = self.v(header(verified_at="2026-07-01", review_every="90d"))
        self.assertEqual(warns, [])

    def test_files(self):
        _, _, claimed = self.v(header(files=["a.json"]))
        self.assertEqual(claimed, ["a.json"])
        errs, _, _ = self.v(header(files="a.json"))
        self.assertTrue(any("`files` must be a list" in e for e in errs))


class Tree(unittest.TestCase):
    """End to end against a throwaway git repo."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        subprocess.run(["git", "init", "-q", "-b", "main", str(self.root)], check=True)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, rel, text):
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")

    def add(self):
        subprocess.run(["git", "-C", str(self.root), "add", "-A"], check=True)

    def git(self, *args):
        subprocess.run(["git", "-C", str(self.root), "-c", "user.name=t", "-c", "user.email=t@t",
                        "-c", "commit.gpgsign=false", *args], check=True, capture_output=True)

    def commit(self, msg="c", date=None):
        self.add()
        env_date = {"GIT_COMMITTER_DATE": f"{date}T12:00:00", "GIT_AUTHOR_DATE": f"{date}T12:00:00"} if date else {}
        subprocess.run(["git", "-C", str(self.root), "-c", "user.name=t", "-c", "user.email=t@t",
                        "-c", "commit.gpgsign=false", "commit", "-q", "--allow-empty", "-m", msg],
                       check=True, env={**os.environ, **env_date})

    HDR = "---\nsources:\n  - Notion\nowner: Zoë Müller\nedit: here\nreview_every: 90d\nverified_at: 2026-09-01\n---\n"

    def test_clean_tree(self):
        self.write("context/customers.md", self.HDR + "# Customers\n")
        self.write("departments/legal/context/gtc.md", self.HDR.replace("here", "upstream") + "# GTC\n")
        self.write("departments/legal/CLAUDE.md", "# Legal\n")           # exempt
        self.write("departments/legal/docs-for-humans/x.md", "# Human\n")  # exempt
        self.write("README.md", "# Repo\n")
        self.add()
        self.assertEqual(check.main(["--root", str(self.root), "--today", "2026-09-10", "--strict"]), 0)

    def test_missing_header_is_a_warning_until_touched(self):
        self.write("context/customers.md", "# Customers\n")
        self.write("context/gtm.md", "# GTM\n")
        self.commit("base")
        self.git("branch", "base")
        # Untouched: warnings only; --strict makes them fail.
        self.assertEqual(check.main(["--root", str(self.root)]), 0)
        self.assertEqual(check.main(["--root", str(self.root), "--changed-since", "base"]), 0)
        self.assertEqual(check.main(["--root", str(self.root), "--strict"]), 1)
        # Touch one file without adding a header: error for that file only.
        self.write("context/customers.md", "# Customers\n\nMore.\n")
        self.assertEqual(check.main(["--root", str(self.root), "--changed-since", "base"]), 1)
        errors, warnings, rows = check.check(self.root, check.tracked_files(self.root), TODAY, None,
                                             check.changed_files(self.root, "base"))
        self.assertEqual(len(errors), 1)
        self.assertIn("context/customers.md", errors[0])
        self.assertTrue(any(w.startswith("context/gtm.md: no maintenance header") for w in warnings))
        self.assertIn(("context/customers.md", "-", "-", "-", "no header"), rows)
        # Add the header and the touched file passes.
        self.write("context/customers.md", self.HDR + "# Customers\n\nMore.\n")
        self.assertEqual(check.main(["--root", str(self.root), "--changed-since", "base", "--today", "2026-09-10"]), 0)

    def test_changed_since_uses_the_merge_base(self):
        """A file changed on the base branch after we branched is not this branch's problem."""
        self.write("context/customers.md", "# Customers\n")
        self.write("context/gtm.md", "# GTM\n")
        self.commit("base")
        self.git("checkout", "-q", "-b", "feature")
        self.write("context/customers.md", self.HDR + "# Customers\n")
        self.commit("feature: header on customers")
        self.git("checkout", "-q", "main")
        self.write("context/gtm.md", "# GTM\n\nEdited on main, still headerless.\n")
        self.commit("main moved on")
        self.git("checkout", "-q", "feature")
        self.assertEqual(check.changed_files(self.root, "main"), {"context/customers.md"})
        self.assertEqual(check.main(["--root", str(self.root), "--changed-since", "main", "--today", "2026-09-10"]), 0)

    def test_unknown_ref_exit_2(self):
        self.write("context/customers.md", self.HDR + "# C\n")
        self.commit()
        self.assertEqual(check.main(["--root", str(self.root), "--changed-since", "nope"]), 2)

    def test_warnings_only_fail_in_strict(self):
        self.write("context/customers.md", "---\nedit: here\nreview_every: 90d\n---\n# C\n")
        self.add()
        self.assertEqual(check.main(["--root", str(self.root)]), 0)
        self.assertEqual(check.main(["--root", str(self.root), "--strict"]), 1)

    def test_data_file_needs_a_card(self):
        self.write("departments/sales/context/deals.csv", "a,b\n")
        self.write("departments/sales/context/other.md", self.HDR + "# Other\n")
        self.add()
        self.assertEqual(check.main(["--root", str(self.root)]), 1)
        self.write("departments/sales/context/deals.md", self.HDR.replace("---\n", "---\nfiles: [deals.csv]\n", 1) + "# Deals\n")
        self.add()
        self.assertEqual(check.main(["--root", str(self.root), "--today", "2026-09-10", "--strict"]), 0)

    CARD = ("---\nsources: [the HR system, Slack]\nowner: Zoë Müller\nedit: upstream\nreview_every: 30d\n"
            "files: [org-chart.json]\n---\n# Org chart data\n")
    JSON = ".claude/skills/who-is/references/org-chart.json"

    def test_skill_data_needs_a_sibling_card(self):
        self.write(self.JSON, '{"people": [{"name": "Zoë Müller"}]}\n')
        self.write(".claude/skills/who-is/SKILL.md", "---\nname: who-is\ndescription: >\n  Look up people.\n---\n# Who is\n")
        self.commit("skill and data", date="2026-08-01")
        self.assertEqual(check.main(["--root", str(self.root)]), 1)  # data file, no card
        self.write(".claude/skills/who-is/references/org-chart.md", self.CARD)
        self.commit("card", date="2026-08-02")
        # The data has only ever landed together with other files: no sync commit, so the
        # card is unverified (a warning, not a derived date).
        _, warnings, rows = check.check(self.root, check.tracked_files(self.root), TODAY, {check.fold("Zoë Müller")})
        self.assertTrue(any(w.endswith("`verified_at` not set") for w in warnings))
        self.assertEqual(next(r for r in rows if r[0].endswith("org-chart.md"))[2], "-")
        # A commit that touches only the data file is a sync: it becomes the verification.
        self.write(self.JSON, '{"people": [{"name": "Zoë Müller"}, {"name": "New Hire"}]}\n')
        self.commit("sync", date="2026-09-01")
        errors, warnings, rows = check.check(self.root, check.tracked_files(self.root), TODAY, {check.fold("Zoë Müller")})
        self.assertEqual(errors, [])
        self.assertFalse(any("verified_at" in w for w in warnings))
        self.assertEqual(next(r for r in rows if r[0].endswith("org-chart.md"))[2], "2026-09-01")
        self.assertEqual(check.main(["--root", str(self.root), "--strict", "--today", "2026-09-10"]), 0)
        # A later hand edit that also touches other files is not a sync and does not move the date.
        self.write(self.JSON, '{"people": [{"name": "Zoë Müller"}, {"name": "New Hire"}], "count": 2}\n')
        self.write("README.md", "# Repo\n")
        self.commit("refactor touching the data too", date="2026-09-08")
        _, _, rows = check.check(self.root, check.tracked_files(self.root), TODAY, {check.fold("Zoë Müller")})
        self.assertEqual(next(r for r in rows if r[0].endswith("org-chart.md"))[2], "2026-09-01")
        # Once the data goes longer than its cadence without a sync, the card goes stale.
        _, warnings, _ = check.check(self.root, check.tracked_files(self.root), dt.date(2026, 10, 15),
                                     {check.fold("Zoë Müller")})
        self.assertTrue(any("stale - last synced 2026-09-01" in w for w in warnings))
        # Owner lookup uses that same org chart: an unknown owner warns.
        self.write("context/x.md", self.HDR.replace("Zoë Müller", "Ghost Person") + "# X\n")
        self.commit("x")
        self.assertEqual(check.main(["--root", str(self.root), "--today", "2026-09-10"]), 0)
        self.assertEqual(check.main(["--root", str(self.root), "--today", "2026-09-10", "--strict"]), 1)

    def test_double_claim_and_bad_path(self):
        self.write("context/data.json", "{}\n")
        self.write("context/a.md", self.HDR.replace("---\n", "---\nfiles: [data.json]\n", 1) + "# A\n")
        self.write("context/b.md", self.HDR.replace("---\n", "---\nfiles: [data.json, ghost.csv]\n", 1) + "# B\n")
        self.add()
        errors, _, _ = check.check(self.root, check.tracked_files(self.root), TODAY, None)
        self.assertTrue(any("claimed by 2 cards" in e for e in errors))
        self.assertTrue(any("not a tracked file" in e for e in errors))

    def test_files_paths_are_normalized(self):
        self.write("context/data/deals.csv", "a,b\n")
        self.write("context/cards/deals.md", self.HDR.replace("---\n", "---\nfiles: [../data/deals.csv, ./../data/deals.csv]\n", 1) + "# D\n")
        self.add()
        errors, _, _ = check.check(self.root, check.tracked_files(self.root), TODAY, None)
        self.assertFalse(any("not a tracked file" in e for e in errors), errors)
        self.assertTrue(any("claimed by 2 cards" in e for e in errors))  # the same file twice, normalized

    def test_report_survives_a_list_valued_field(self):
        self.write("context/x.md", "---\nowner: [a, b]\nedit: here\nreview_every: 90d\n---\n# X\n")
        self.add()
        self.assertEqual(check.main(["--root", str(self.root), "--report", "--today", "2026-09-10"]), 1)

    def test_only_cards_derive_a_date(self):
        """A synced Markdown file carries its export date itself; an export commit
        that lands alone does not stand in for it, and `edit: here` never derives."""
        export = "---\nsources:\n  - Notion page X, exported by an agent\nedit: upstream\nreview_every: 90d\n---\n# X\n"
        self.write("context/x.md", export)
        self.commit("export alone", date="2026-09-01")
        self.write("context/z.md", "---\nedit: here\nreview_every: 90d\n---\n# Z\n")
        self.commit("z alone", date="2026-09-02")
        _, warnings, rows = check.check(self.root, check.tracked_files(self.root), TODAY, None)
        self.assertTrue(any(w == "context/x.md: `verified_at` not set" for w in warnings))
        self.assertEqual(next(r for r in rows if r[0] == "context/x.md")[2], "-")
        self.assertEqual(next(r for r in rows if r[0] == "context/z.md")[2], "-")
        # With the export date written by the exporter, the file is verified as of that day.
        self.write("context/x.md", export.replace("review_every: 90d\n", "review_every: 90d\nverified_at: 2026-09-01\n"))
        self.commit("re-export", date="2026-09-03")
        _, warnings, rows = check.check(self.root, check.tracked_files(self.root), TODAY, None)
        self.assertFalse(any("context/x.md" in w and "verified_at" in w for w in warnings))
        self.assertEqual(next(r for r in rows if r[0] == "context/x.md")[2], "2026-09-01")

    def test_report_runs(self):
        self.write("context/customers.md", self.HDR + "# C\n")
        self.add()
        self.assertEqual(check.main(["--root", str(self.root), "--report", "--today", "2026-09-10"]), 0)

    def test_not_a_git_repo_exit_2(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(check.main(["--root", d]), 2)


if __name__ == "__main__":
    unittest.main()
