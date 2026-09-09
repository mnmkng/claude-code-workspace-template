import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import log


class SetLogFileTests(unittest.TestCase):
    def setUp(self):
        # Disable color so tee assertions don't have to strip on the way in;
        # we still verify ANSI is stripped from any escape sequences that
        # leak in via the constants.
        log.set_log_file(None)

    def tearDown(self):
        log.set_log_file(None)

    def test_log_file_receives_tee_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "subdir" / "log.txt"
            log.set_log_file(log_path)
            log.info("hello info")
            log.step("doing the thing")
            log.ok("done")
            log.warn("watch out")
            log.error("nope")
            text = log_path.read_text()
            for needle in ("hello info", "doing the thing", "done", "watch out", "nope"):
                self.assertIn(needle, text)

    def test_ansi_escapes_stripped_from_log_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "log.txt"
            log.set_log_file(log_path)
            # Force a synthetic ANSI sequence through the tee by writing
            # something containing escape codes directly.
            log._tee("\x1b[31mred text\x1b[0m around \x1b[1mbold\x1b[0m")
            text = log_path.read_text()
            self.assertNotIn("\x1b[", text)
            self.assertIn("red text around bold", text)

    def test_set_log_file_swallows_write_errors(self):
        # Pointing at a path whose parent cannot be created (a file, not a dir)
        # should disable the tee silently, not raise.
        with tempfile.TemporaryDirectory() as tmp:
            blocker = Path(tmp) / "blocker"
            blocker.write_text("")
            bad_path = blocker / "log.txt"
            log.set_log_file(bad_path)  # must not raise
            log.info("should not crash")  # also must not raise


if __name__ == "__main__":
    unittest.main()
