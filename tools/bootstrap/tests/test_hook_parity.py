"""Parity between the root hook wiring and the derived policies.

Both generators (settings_sync for team folders, parent_settings for the
multi-repo parent) REBUILD the `hooks` block instead of copying it, with the
wiring hardcoded in Python. If someone adds an event, a matcher, or a hook
script to the real root `.claude/settings.json`, nothing else would notice:
the derived files would silently lack it while `--check` and `doctor` report
"in sync". These tests read the actual root file and fail the moment the root
wiring grows past what the generators know about.

Deliberate exceptions are listed explicitly so the assertion stays exact.
"""

import json
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import parent_settings  # noqa: E402
import settings_sync  # noqa: E402


REPO_ROOT = Path(__file__).resolve().parents[3]
ROOT_SETTINGS_FILE = REPO_ROOT / ".claude" / "settings.json"

# Deliberate differences between the root wiring and each derived policy.
#
# Team stamps (settings_sync):
#   - omit the cloud --apply-only SessionStart hook: cloud sessions anchor at
#     the repo root (or, multi-repo, at its parent), never at a team folder,
#     so composition stays out of the team copies by design;
#   - replace status-banner.sh with an inline banner (walk-up + fail closed),
#     so the script name does not appear in the derived command.
# Parent policy (parent_settings): none - it mirrors the root exactly.
TEAM_OMITS_COMMANDS_MATCHING = (re.compile(r"cloud --apply-only"),)
TEAM_REPLACES_SCRIPTS = {"status-banner.sh"}
PARENT_OMITS_COMMANDS_MATCHING = ()
PARENT_REPLACES_SCRIPTS = set()

_SCRIPT_RE = re.compile(r"\.claude/hooks/([A-Za-z0-9_.-]+\.sh)")
# The script path may be quoted in either template: `.../bootstrap.py cloud`
# at the root, `"$d/tools/bootstrap/bootstrap.py" cloud` in the parent policy.
_TOOL_RE = re.compile(r"tools/bootstrap/bootstrap\.py\"?\s+(\S+(?:\s+--\S+)*)")


def _wiring(hooks):
    """{(event, matcher): [command, ...]} for a hooks block."""
    out = {}
    for event, entries in (hooks or {}).items():
        for entry in entries:
            key = (event, entry.get("matcher", ""))
            out.setdefault(key, []).extend(
                h["command"] for h in entry.get("hooks", []) if h.get("type") == "command"
            )
    return out


def _referenced(commands):
    """Hook scripts and bootstrap subcommands a list of commands runs."""
    scripts, tools = set(), set()
    for c in commands:
        scripts.update(_SCRIPT_RE.findall(c))
        tools.update(m.strip() for m in _TOOL_RE.findall(c))
    return scripts, tools


class HookParityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root_settings = json.loads(ROOT_SETTINGS_FILE.read_text())
        cls.root = _wiring(cls.root_settings["hooks"])
        cls.team = _wiring(settings_sync.team_hooks())
        cls.parent = _wiring(parent_settings.parent_hooks("/home/user/<your-repo>"))

    def _assert_parity(self, derived, omits, replaces, label):
        for key, root_cmds in self.root.items():
            kept = [c for c in root_cmds if not any(p.search(c) for p in omits)]
            if not kept:
                continue
            self.assertIn(
                key, derived,
                f"{label}: root wires {key[0]} / {key[1]!r} but the derived policy does not",
            )
            root_scripts, root_tools = _referenced(kept)
            root_scripts -= replaces
            derived_scripts, derived_tools = _referenced(derived[key])
            self.assertTrue(
                root_scripts <= derived_scripts,
                f"{label}: {key} runs {sorted(root_scripts - derived_scripts)} at the root "
                "but not in the derived policy",
            )
            self.assertTrue(
                root_tools <= derived_tools,
                f"{label}: {key} runs bootstrap {sorted(root_tools - derived_tools)} at the "
                "root but not in the derived policy",
            )
        # No derived wiring the root does not have either (no phantom hooks).
        self.assertEqual(
            set(derived) - set(self.root), set(),
            f"{label}: derived policy wires events/matchers the root does not",
        )

    def test_team_stamps_mirror_root_wiring(self):
        self._assert_parity(self.team, TEAM_OMITS_COMMANDS_MATCHING,
                            TEAM_REPLACES_SCRIPTS, "settings-sync")

    def test_parent_policy_mirrors_root_wiring(self):
        self._assert_parity(self.parent, PARENT_OMITS_COMMANDS_MATCHING,
                            PARENT_REPLACES_SCRIPTS, "parent-settings")

    def test_exception_lists_are_still_needed(self):
        # If the root drops the apply-only hook or the banner script one day,
        # these lists are stale and must be pruned.
        all_root = [c for cmds in self.root.values() for c in cmds]
        for pat in TEAM_OMITS_COMMANDS_MATCHING:
            self.assertTrue(any(pat.search(c) for c in all_root),
                            f"stale omission: {pat.pattern!r} matches no root hook")
        scripts, _ = _referenced(all_root)
        self.assertTrue(TEAM_REPLACES_SCRIPTS <= scripts,
                        f"stale replacement: {TEAM_REPLACES_SCRIPTS - scripts}")

    def test_root_hook_scripts_exist_and_are_executable(self):
        all_root = [c for cmds in self.root.values() for c in cmds]
        scripts, _ = _referenced(all_root)
        self.assertTrue(scripts)
        for name in scripts:
            p = REPO_ROOT / ".claude" / "hooks" / name
            self.assertTrue(p.is_file(), f"root wires {name} but it does not exist")
            self.assertTrue(p.stat().st_mode & 0o111, f"{name} is not executable")


if __name__ == "__main__":
    unittest.main()
