"""Tests for who_is.py --import.

    python3 -m unittest .claude/skills/who-is/scripts/test_who_is.py
    python3 -m unittest discover -s .claude/skills/who-is/scripts

The import rewrites the file the whole skill reads, so the cases that matter
are the ones where it must refuse: an unknown manager or a duplicate name
would produce a chart that looks fine and answers wrongly.
"""

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import who_is  # noqa: E402


VALID_CSV = """\
name,title,department,manager,nickname,team
Alan Brand,Chief Executive Officer,Corporate,,,Corporate Executive
Jan Levinson,"Vice President, Northeast Sales",Corporate,Alan Brand,,Corporate Executive
Dwight K. Schrute,Regional Manager,Sales,Jan Levinson,Dwight,Scranton Sales
Óscar Martínez,Accountant,Accounting,Jan Levinson,Óscar Martínez,Scranton Accounting
"""


class ImportBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.out = self.dir / "references" / "org-chart.json"

    def tearDown(self):
        self.tmp.cleanup()

    def write_csv(self, text, name="people.csv"):
        p = self.dir / name
        p.write_text(text, encoding="utf-8")
        return p

    def run_import(self, text):
        with contextlib.redirect_stdout(io.StringIO()):
            return who_is.import_csv(self.write_csv(text), self.out)

    def refuse(self, text):
        with self.assertRaises(SystemExit) as ctx:
            self.run_import(text)
        self.assertFalse(self.out.exists(),
                         "a refused import must write nothing")
        return str(ctx.exception)


class ValidImportTests(ImportBase):
    def setUp(self):
        super().setUp()
        self.run_import(VALID_CSV)
        self.data = json.loads(self.out.read_text(encoding="utf-8"))

    def test_file_shape(self):
        self.assertEqual(list(self.data), ["note", "source", "updated",
                                           "count", "people"])
        self.assertEqual(self.data["count"], 4)
        self.assertEqual(len(self.data["people"]), 4)

    def test_source_names_the_import_file(self):
        self.assertEqual(self.data["source"], "import:people.csv")

    def test_updated_is_today(self):
        import datetime as dt
        self.assertEqual(self.data["updated"], dt.date.today().isoformat())

    def test_team_becomes_slack_team(self):
        dwight = next(p for p in self.data["people"]
                      if p["name"] == "Dwight K. Schrute")
        self.assertEqual(dwight["slack_team"], "Scranton Sales")
        self.assertEqual(dwight["manager"], "Jan Levinson")

    def test_nickname_kept_only_when_it_differs(self):
        by_name = {p["name"]: p for p in self.data["people"]}
        self.assertEqual(by_name["Dwight K. Schrute"]["nickname"], "Dwight")
        # Same as the formal name: the field would say nothing.
        self.assertNotIn("nickname", by_name["Óscar Martínez"])
        self.assertNotIn("nickname", by_name["Alan Brand"])

    def test_root_has_no_manager_key(self):
        root = next(p for p in self.data["people"] if p["name"] == "Alan Brand")
        self.assertNotIn("manager", root)

    def test_the_result_is_queryable(self):
        # The point of the import: the skill's own loader reads what it wrote.
        who_is.DATA_PATH = self.out
        data, people, by_name, reports = who_is.load()
        self.assertEqual(len(people), 4)
        self.assertEqual([p["name"] for p in reports["Jan Levinson"]],
                         ["Dwight K. Schrute", "Óscar Martínez"])

    def test_rerunning_is_idempotent_apart_from_the_date(self):
        first = self.out.read_text(encoding="utf-8")
        self.run_import(VALID_CSV)
        self.assertEqual(first, self.out.read_text(encoding="utf-8"))


class RefusalTests(ImportBase):
    def test_unknown_manager(self):
        bad = VALID_CSV.replace("Dwight K. Schrute,Regional Manager,Sales,Jan Levinson",
                                "Dwight K. Schrute,Regional Manager,Sales,Jan Levenson")
        message = self.refuse(bad)
        self.assertIn("is not a name in this file", message)
        self.assertIn("row 4", message)

    def test_unknown_manager_suggests_a_near_miss(self):
        bad = VALID_CSV.replace(",Jan Levinson,Dwight,", ",jan levinson,Dwight,")
        self.assertIn("did you mean 'Jan Levinson'?", self.refuse(bad))

    def test_duplicate_name(self):
        dup = VALID_CSV + "Dwight K. Schrute,Sales Representative,Sales,Jan Levinson,,\n"
        message = self.refuse(dup)
        self.assertIn("duplicate name", message)
        self.assertIn("row 6", message)

    def test_missing_required_column(self):
        headerless = VALID_CSV.replace("name,title,department,manager,nickname,team",
                                       "name,title,department,nickname,team")
        self.assertIn("missing required column(s): manager",
                      self.refuse(headerless))

    def test_no_root(self):
        rooted = VALID_CSV.replace(
            "Alan Brand,Chief Executive Officer,Corporate,,,Corporate Executive",
            "Alan Brand,Chief Executive Officer,Corporate,Jan Levinson,,Corporate Executive")
        self.assertIn("no root", self.refuse(rooted))

    def test_empty_name(self):
        blank = VALID_CSV + ",Sales Representative,Sales,Jan Levinson,,\n"
        self.assertIn("name is empty", self.refuse(blank))

    def test_header_only_file(self):
        self.assertIn("no rows",
                      self.refuse("name,title,department,manager\n"))

    def test_every_problem_is_reported_at_once(self):
        bad = VALID_CSV + "Dwight K. Schrute,Rep,Sales,Nobody Here,,\n"
        message = self.refuse(bad)
        self.assertIn("duplicate name", message)
        self.assertIn("is not a name in this file", message)

    def test_missing_file(self):
        with self.assertRaises(SystemExit) as ctx:
            who_is.import_csv(self.dir / "nope.csv", self.out)
        self.assertIn("CSV not found", str(ctx.exception))


class CsvQuirkTests(ImportBase):
    def test_bom_and_padding_are_tolerated(self):
        # An export opened in Excel once comes back with a BOM and stray spaces.
        text = "﻿" + VALID_CSV.replace("name,title", " name , title ")
        self.run_import(text)
        data = json.loads(self.out.read_text(encoding="utf-8"))
        self.assertEqual(data["count"], 4)

    def test_optional_columns_may_be_absent(self):
        minimal = """\
name,title,department,manager
Alan Brand,Chief Executive Officer,Corporate,
Jan Levinson,VP Sales,Corporate,Alan Brand
"""
        self.run_import(minimal)
        data = json.loads(self.out.read_text(encoding="utf-8"))
        self.assertEqual(data["count"], 2)
        self.assertNotIn("slack_team", data["people"][0])


if __name__ == "__main__":
    unittest.main()
