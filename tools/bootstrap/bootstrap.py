#!/usr/bin/env python3
"""Claude Code workspace bootstrap.

Single Python entrypoint for both the engineer-local install path and the
Claude Code Cloud session-setup path.

Auto-dispatch (no subcommand):
  --check passed           → local install dry-run (any environment)
  CLAUDE_CODE_REMOTE=true  → cloud workflow
  unset                    → local install workflow

Explicit subcommands for testing and ops:
  install   --check          Local install (idempotent).
  cloud     --compose-only   Cloud setup script + per-session apply.
            --apply-only
            --team <name>     Team for the cloud setup tier ('root' = no team overlay).
            --disable-stop-hook   Neutralize platform's stop-hook-git-check.sh.
  compose   --team <name>    Team artifact composition (uses WORKSPACE_TEAM by default;
                             --team root = root / no-team mode).
  personal  sync --gist URL  Personal CLAUDE.md gist sync (Phase 2).
  doctor                     Diagnostics: print bootstrap state, exit non-zero
                             on detected problems.
  reset     --personal       Undo composition (delete composed artifacts, strip
                             the team block, remove bootstrap state). --personal
                             also clears the personal context.
  settings-sync --check      Stamp (or with --check, verify) the derived
                             team-folder security settings (issue #141).
  lint                       Workspace structure and security checks (the
                             checks security-lint runs in CI).
  parent-settings --check    Write (or with --check, verify) the derived
                             policy at the clone's parent directory that
                             multi-repo cloud sessions load (issue #195).

Stdlib only.  Target: Python 3.9+.
"""

import argparse
import os
import sys
from pathlib import Path

# Allow sibling imports when invoked as `python3 .../bootstrap.py`.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib import log  # noqa: E402

import install       # noqa: E402
import compose       # noqa: E402
import personal      # noqa: E402
import cloud         # noqa: E402
import doctor        # noqa: E402
import reset         # noqa: E402
import settings_sync  # noqa: E402
import parent_settings  # noqa: E402
import lint             # noqa: E402


SUBCOMMAND_NAMES = {
    "install", "cloud", "compose", "personal", "doctor", "reset",
    "settings-sync", "parent-settings", "lint",
}


def build_parser():
    p = argparse.ArgumentParser(
        prog="bootstrap.py",
        description=(
            "Claude Code workspace bootstrap. "
            "Run with no arguments to auto-dispatch by environment "
            "(CLAUDE_CODE_REMOTE=true → cloud; otherwise → local install)."
        ),
    )
    sub = p.add_subparsers(dest="command")

    p_install = sub.add_parser("install", help="Local engineer install (idempotent).")
    p_install.add_argument(
        "--check", action="store_true",
        help="Report what would change without making changes; silent on no-op.",
    )
    p_install.set_defaults(func=install.run)

    p_cloud = sub.add_parser("cloud", help="Cloud setup + per-session apply (Phase 2).")
    p_cloud.add_argument("--compose-only", action="store_true")
    p_cloud.add_argument("--apply-only", action="store_true")
    p_cloud.add_argument(
        "--team",
        help="Team folder basename (e.g. content). Overrides WORKSPACE_TEAM. "
             "Use 'root' for root mode (base workspace, no team overlay). "
             "Used by the cloud setup tier.",
    )
    p_cloud.add_argument(
        "--disable-stop-hook",
        action="store_true",
        help=(
            "Neutralize Anthropic's /root/.claude/stop-hook-git-check.sh which "
            "blocks Stop on a dirty tree. Our bootstrap intentionally leaves "
            ".claude/skills/* + CLAUDE.md marker block dirty every session. "
            "Set on the setup tier; the intent is recorded in the staging meta "
            "and re-applied every session by --apply-only, since the platform "
            "rewrites the hook on each session start. Original preserved at "
            ".original. Idempotent."
        ),
    )
    p_cloud.set_defaults(func=cloud.run)

    p_compose = sub.add_parser("compose", help="Compose team artifacts into root .claude/.")
    p_compose.add_argument(
        "--team",
        help="Team folder basename (e.g. content, marketing, scaled-customer-experience). "
             "Defaults to the WORKSPACE_TEAM env var; an explicit --team overrides it. "
             "Use 'root' for root mode (base workspace, no team overlay).",
    )
    p_compose.set_defaults(func=compose.run)

    p_personal = sub.add_parser("personal", help="Personal CLAUDE.md sync (Phase 2).")
    psub = p_personal.add_subparsers(dest="personal_command")
    p_sync = psub.add_parser("sync", help="Fetch the personal gist into CLAUDE.local.md.")
    p_sync.add_argument("--gist", help="Gist raw URL. Defaults to WORKSPACE_PERSONAL_GIST env var.")
    p_personal.set_defaults(func=personal.run)

    p_doctor = sub.add_parser(
        "doctor",
        help="Diagnostics: print bootstrap state; exit non-zero on problems.",
    )
    p_doctor.set_defaults(func=doctor.run)

    p_sync = sub.add_parser(
        "settings-sync",
        help="Stamp the derived team-folder security settings into every "
             "CLAUDE.md-bearing department/team folder (issue #141).",
    )
    p_sync.add_argument(
        "--check", action="store_true",
        help="Verify only: exit non-zero if any copy is missing, differs from "
             "fresh generator output, or a stray copy exists.",
    )
    p_sync.set_defaults(func=settings_sync.run)

    p_parent = sub.add_parser(
        "parent-settings",
        help="Write the derived security policy to the workspace clone's parent "
             "directory, the project root of a multi-repo cloud session (issue #195).",
    )
    p_parent.add_argument(
        "--check", action="store_true",
        help="Verify only: exit non-zero if the parent policy is missing or "
             "differs from fresh generator output.",
    )
    p_parent.set_defaults(func=parent_settings.run)

    p_lint = sub.add_parser(
        "lint",
        help="Workspace structure and security checks: unique CLAUDE.md folder "
             "names, resolvable @imports, required .gitignore entries, settings "
             "stamps in sync, executable hooks, no committed secrets.",
    )
    p_lint.set_defaults(func=lint.run)

    p_reset = sub.add_parser("reset", help="Undo composition.")
    p_reset.add_argument(
        "--personal",
        action="store_true",
        help="Also clear the personal-context region of CLAUDE.local.md "
             "(default keeps personal context).",
    )
    p_reset.set_defaults(func=reset.run)

    return p


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)

    # Auto-dispatch: no subcommand → install or cloud based on env. Any flags
    # the user passed (e.g. --check) get forwarded to the chosen path. Top-level
    # --help is a special case: print the umbrella help, not the dispatched
    # path's help.
    wants_top_help = bool(argv) and argv[0] in ("-h", "--help")
    if not wants_top_help and (not argv or argv[0] not in SUBCOMMAND_NAMES):
        # `--check` is the documented local-install dry-run that the
        # .githooks/post-checkout self-heal relies on. It has no meaning for the
        # cloud workflow (`cloud` rejects it), so route it to `install`
        # regardless of environment. Everything else auto-dispatches by env.
        if "--check" in argv:
            argv = ["install"] + argv
        elif os.environ.get("CLAUDE_CODE_REMOTE") == "true":
            argv = ["cloud"] + argv
        else:
            argv = ["install"] + argv

    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help(sys.stderr)
        return 2
    return args.func(args) or 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        log.warn("interrupted")
        sys.exit(130)
