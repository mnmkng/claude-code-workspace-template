import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import bootstrap


class DispatchTests(unittest.TestCase):
    """Top-level auto-dispatch in bootstrap.main(), incl. the #56 --check fix."""

    def setUp(self):
        self._saved = os.environ.get("CLAUDE_CODE_REMOTE")

    def tearDown(self):
        if self._saved is None:
            os.environ.pop("CLAUDE_CODE_REMOTE", None)
        else:
            os.environ["CLAUDE_CODE_REMOTE"] = self._saved

    def _dispatch(self, argv, remote):
        if remote:
            os.environ["CLAUDE_CODE_REMOTE"] = "true"
        else:
            os.environ.pop("CLAUDE_CODE_REMOTE", None)
        seen = {}

        def fake_install(args):
            seen["cmd"] = "install"
            seen["check"] = getattr(args, "check", False)
            return 0

        def fake_cloud(args):
            seen["cmd"] = "cloud"
            return 0

        with patch("bootstrap.install.run", fake_install), \
             patch("bootstrap.cloud.run", fake_cloud):
            seen["rc"] = bootstrap.main(argv)
        return seen

    # ---- #56: --check is an install dry-run in ANY environment ----

    def test_check_routes_to_install_even_in_cloud(self):
        seen = self._dispatch(["--check"], remote=True)
        self.assertEqual(seen["cmd"], "install")
        self.assertTrue(seen["check"])
        self.assertEqual(seen["rc"], 0)

    def test_check_routes_to_install_local(self):
        seen = self._dispatch(["--check"], remote=False)
        self.assertEqual(seen["cmd"], "install")
        self.assertTrue(seen["check"])

    # ---- unchanged env-based dispatch for the no-flag case ----

    def test_bare_dispatch_cloud_when_remote(self):
        self.assertEqual(self._dispatch([], remote=True)["cmd"], "cloud")

    def test_bare_dispatch_install_when_local(self):
        self.assertEqual(self._dispatch([], remote=False)["cmd"], "install")


if __name__ == "__main__":
    unittest.main()
