import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import install


class DetectShellRcTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        os.environ["NO_COLOR"] = "1"

    def tearDown(self):
        self.tmp.cleanup()

    def _detect(self, shell):
        with (
            patch("install.Path.home", return_value=self.home),
            patch.dict(os.environ, {"SHELL": shell}, clear=False),
        ):
            return install._detect_shell_rc()

    # ---- $SHELL takes priority ----

    def test_shell_env_fish(self):
        rc, kind = self._detect("/opt/homebrew/bin/fish")
        self.assertEqual(kind, "fish")
        self.assertEqual(rc, self.home / ".config" / "fish" / "config.fish")

    def test_shell_env_zsh(self):
        rc, kind = self._detect("/bin/zsh")
        self.assertEqual(kind, "posix")
        self.assertEqual(rc, self.home / ".zshrc")

    def test_shell_env_bash(self):
        rc, kind = self._detect("/bin/bash")
        self.assertEqual(kind, "posix")
        self.assertEqual(rc, self.home / ".bashrc")

    # ---- file-existence fallbacks when $SHELL is unrecognized ----

    def test_fallback_to_existing_fish_config(self):
        fish_rc = self.home / ".config" / "fish" / "config.fish"
        fish_rc.parent.mkdir(parents=True)
        fish_rc.write_text("")
        rc, kind = self._detect("/usr/bin/somethingelse")
        self.assertEqual(kind, "fish")
        self.assertEqual(rc, fish_rc)

    def test_fallback_prefers_posix_over_fish(self):
        (self.home / ".zshrc").write_text("")
        fish_rc = self.home / ".config" / "fish" / "config.fish"
        fish_rc.parent.mkdir(parents=True)
        fish_rc.write_text("")
        rc, kind = self._detect("/usr/bin/somethingelse")
        self.assertEqual(kind, "posix")
        self.assertEqual(rc, self.home / ".zshrc")

    def test_none_when_nothing_matches(self):
        rc, kind = self._detect("/usr/bin/somethingelse")
        self.assertEqual((rc, kind), (None, None))


class ShellFunctionBlockTests(unittest.TestCase):
    def test_fish_block(self):
        block = install._shell_function_block("fish")
        self.assertIn(install.MARKER_START, block)
        self.assertIn(install.MARKER_END, block)
        self.assertIn("function claude", block)
        self.assertIn("\nend\n", block)
        self.assertIn("$argv", block)
        self.assertNotIn("claude()", block)

    def test_posix_block(self):
        block = install._shell_function_block("posix")
        self.assertIn("claude() {", block)
        self.assertIn('"$@"', block)
        self.assertNotIn("function claude", block)

    def test_default_is_posix(self):
        self.assertEqual(
            install._shell_function_block(),
            install._shell_function_block("posix"),
        )


class InstallShellFunctionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        os.environ["NO_COLOR"] = "1"

    def tearDown(self):
        self.tmp.cleanup()

    def _install(self, shell, check_mode=False):
        with (
            patch("install.Path.home", return_value=self.home),
            patch.dict(os.environ, {"SHELL": shell}, clear=False),
        ):
            return install._install_shell_function(check_mode)

    def test_fish_install_creates_config_and_writes_block(self):
        changed = self._install("/opt/homebrew/bin/fish")
        self.assertTrue(changed)
        fish_rc = self.home / ".config" / "fish" / "config.fish"
        self.assertTrue(fish_rc.exists())  # parent dir was created too
        text = fish_rc.read_text()
        self.assertIn("function claude", text)
        self.assertIn(install.MARKER_START, text)

    def test_fish_install_idempotent(self):
        self.assertTrue(self._install("/opt/homebrew/bin/fish"))
        self.assertFalse(self._install("/opt/homebrew/bin/fish"))
        fish_rc = self.home / ".config" / "fish" / "config.fish"
        self.assertEqual(fish_rc.read_text().count(install.MARKER_START), 1)

    def test_fish_reinstall_after_strip(self):
        self.assertTrue(self._install("/opt/homebrew/bin/fish"))
        fish_rc = self.home / ".config" / "fish" / "config.fish"
        stripped, removed = install._strip_block(
            fish_rc.read_text(), install.MARKER_START, install.MARKER_END
        )
        self.assertTrue(removed)
        fish_rc.write_text(stripped)
        self.assertNotIn(install.MARKER_START, fish_rc.read_text())
        self.assertTrue(self._install("/opt/homebrew/bin/fish"))
        self.assertIn("function claude", fish_rc.read_text())

    def test_fish_check_mode_does_not_write_block(self):
        changed = self._install("/opt/homebrew/bin/fish", check_mode=True)
        self.assertTrue(changed)  # reports it would change
        fish_rc = self.home / ".config" / "fish" / "config.fish"
        self.assertFalse(fish_rc.exists())  # but does not actually change anything

    def test_bash_install_writes_posix_block(self):
        changed = self._install("/bin/bash")
        self.assertTrue(changed)
        rc = self.home / ".bashrc"
        self.assertTrue(rc.exists())
        self.assertIn("claude() {", rc.read_text())


if __name__ == "__main__":
    unittest.main()
