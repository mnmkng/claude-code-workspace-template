import argparse
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import personal
from lib import localmd


# Realistic-shape gist URLs and bare IDs for the tests.
GIST_ID = "76cee6d64f67f7204f5e8efae5ab6be3"
GIST_PAGE_URL = f"https://gist.github.com/someuser/{GIST_ID}"
GIST_RAW_URL = f"https://gist.githubusercontent.com/someuser/{GIST_ID}/raw/abc/CLAUDE.local.md"


def _fake_clone_factory(files):
    """Return a side_effect function for subprocess.run that simulates `git clone`.

    `files` is a dict of {filename: content}. The mock creates the destination
    directory (last argv) and writes the files into it.
    """
    def fake_run(cmd, **kwargs):
        dest = Path(cmd[-1])
        dest.mkdir(parents=True)
        for name, content in files.items():
            (dest / name).write_text(content)
        result = MagicMock()
        result.returncode = 0
        result.stdout = ""
        result.stderr = ""
        return result
    return fake_run


class SyncTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.dest = self.root / personal.PERSONAL_CONTEXT_REL
        os.environ.pop("WORKSPACE_PERSONAL_GIST", None)
        os.environ["NO_COLOR"] = "1"

    def tearDown(self):
        self.tmp.cleanup()
        os.environ.pop("WORKSPACE_PERSONAL_GIST", None)

    # ---- no-input / malformed paths ----

    def test_no_url_writes_empty_placeholder(self):
        personal.sync(self.root, None)
        self.assertTrue(self.dest.exists())
        self.assertEqual(self.dest.read_text(), "")

    def test_unparseable_url_writes_empty(self):
        # No hex ID in it
        personal.sync(self.root, "https://example.com/not-a-gist")
        self.assertEqual(self.dest.read_text(), "")

    def test_short_url_writes_empty(self):
        # Hex string too short to be a gist ID
        personal.sync(self.root, "https://gist.github.com/u/abc123")
        self.assertEqual(self.dest.read_text(), "")

    # ---- gist-ID extraction ----

    def test_extracts_id_from_page_url(self):
        self.assertEqual(personal._extract_gist_id(GIST_PAGE_URL), GIST_ID)

    def test_extracts_id_from_raw_url(self):
        # Raw URLs contain the gist ID first, then a commit hex; we want the gist ID.
        self.assertEqual(personal._extract_gist_id(GIST_RAW_URL), GIST_ID)

    def test_extracts_id_from_bare_id(self):
        self.assertEqual(personal._extract_gist_id(GIST_ID), GIST_ID)

    def test_extracts_id_from_dotgit_url(self):
        self.assertEqual(
            personal._extract_gist_id(f"https://gist.github.com/{GIST_ID}.git"),
            GIST_ID,
        )

    # ---- successful clone paths ----

    def test_single_file_gist_written_as_is(self):
        with patch("subprocess.run",
                   side_effect=_fake_clone_factory({"CLAUDE.local.md": "# my context\n"})):
            personal.sync(self.root, GIST_PAGE_URL)
        self.assertEqual(self.dest.read_text(), "# my context\n")

    def test_multi_file_gist_concatenated(self):
        files = {"a.md": "alpha", "b.md": "beta"}
        with patch("subprocess.run", side_effect=_fake_clone_factory(files)):
            personal.sync(self.root, GIST_PAGE_URL)
        text = self.dest.read_text()
        self.assertIn("<!-- a.md -->", text)
        self.assertIn("alpha", text)
        self.assertIn("<!-- b.md -->", text)
        self.assertIn("beta", text)

    def test_empty_gist_writes_empty(self):
        with patch("subprocess.run", side_effect=_fake_clone_factory({})):
            personal.sync(self.root, GIST_PAGE_URL)
        self.assertEqual(self.dest.read_text(), "")

    def test_dotfiles_in_gist_skipped(self):
        with patch("subprocess.run",
                   side_effect=_fake_clone_factory({".meta": "hide", "real.md": "keep"})):
            personal.sync(self.root, GIST_PAGE_URL)
        self.assertEqual(self.dest.read_text(), "keep")

    # ---- failure modes ----

    def test_clone_failure_writes_empty(self):
        err = subprocess.CalledProcessError(128, "git clone", "stderr", "fatal: forbidden")
        with patch("subprocess.run", side_effect=err):
            personal.sync(self.root, GIST_PAGE_URL)
        self.assertEqual(self.dest.read_text(), "")

    def test_clone_timeout_writes_empty(self):
        err = subprocess.TimeoutExpired("git clone", 20)
        with patch("subprocess.run", side_effect=err):
            personal.sync(self.root, GIST_PAGE_URL)
        self.assertEqual(self.dest.read_text(), "")

    def test_git_not_installed_writes_empty(self):
        with patch("subprocess.run", side_effect=FileNotFoundError("git")):
            personal.sync(self.root, GIST_PAGE_URL)
        self.assertEqual(self.dest.read_text(), "")

    def test_existing_content_truncated_on_failure(self):
        self.dest.parent.mkdir(parents=True, exist_ok=True)
        self.dest.write_text("STALE")
        with patch("subprocess.run",
                   side_effect=subprocess.CalledProcessError(128, "git clone")):
            personal.sync(self.root, GIST_PAGE_URL)
        self.assertEqual(self.dest.read_text(), "")

    def test_existing_content_overwritten_on_success(self):
        self.dest.parent.mkdir(parents=True, exist_ok=True)
        self.dest.write_text("OLD")
        with patch("subprocess.run",
                   side_effect=_fake_clone_factory({"f.md": "NEW"})):
            personal.sync(self.root, GIST_PAGE_URL)
        self.assertEqual(self.dest.read_text(), "NEW")

    # ---- coexistence with the bootstrap team-context block (#72) ----

    def test_preserves_team_block_and_replaces_personal_region(self):
        self.dest.parent.mkdir(parents=True, exist_ok=True)
        team = localmd.team_block_text(["departments/foo"])
        self.dest.write_text(team + "\nOLD personal\n")
        with patch("subprocess.run",
                   side_effect=_fake_clone_factory({"f.md": "NEW personal"})):
            personal.sync(self.root, GIST_PAGE_URL)
        text = self.dest.read_text()
        self.assertIn(localmd.TEAM_START, text)            # team block kept
        self.assertIn("@departments/foo/CLAUDE.md", text)
        self.assertIn("NEW personal", text)                # gist content applied
        self.assertNotIn("OLD personal", text)             # old personal replaced
        self.assertLess(text.index(localmd.TEAM_START), text.index("NEW personal"))

    def test_team_block_survives_clone_failure(self):
        self.dest.parent.mkdir(parents=True, exist_ok=True)
        team = localmd.team_block_text(["departments/foo"])
        self.dest.write_text(team + "\nOLD\n")
        with patch("subprocess.run",
                   side_effect=subprocess.CalledProcessError(128, "git clone")):
            personal.sync(self.root, GIST_PAGE_URL)
        text = self.dest.read_text()
        self.assertIn(localmd.TEAM_START, text)  # team block kept on failure
        self.assertNotIn("OLD", text)            # stale personal cleared

    # ---- arg vs env vs CLI dispatch ----

    def test_explicit_gist_arg_overrides_env(self):
        os.environ["WORKSPACE_PERSONAL_GIST"] = f"https://gist.github.com/env/{'e' * 32}"
        with patch("subprocess.run",
                   side_effect=_fake_clone_factory({"f.md": "from-arg"})) as mock_run:
            with patch("personal.path_lib.require_workspace_root", return_value=self.root):
                args = argparse.Namespace(gist=GIST_PAGE_URL)
                personal.run(args)
        called_url = mock_run.call_args.args[0][-2]  # second-to-last arg is URL
        self.assertIn(GIST_ID, called_url)
        self.assertEqual(self.dest.read_text(), "from-arg")


if __name__ == "__main__":
    unittest.main()
