"""Staging dir helpers for the two-tier cloud workflow (#45).

Setup-script tier (cached snapshot) mirrors the composed `.claude/` to a
staging directory outside the repo working tree. SessionStart-tier (per
session, fast) restores from that staging directory.

In production the staging root is `/opt/claude-workspace/composed/`. Tests override
via `WORKSPACE_COMPOSED_DIR` so they don't need write access to `/opt`.
"""

import json
import os
from pathlib import Path


DEFAULT_STAGING_DIR = "/opt/claude-workspace/composed"
META_FILENAME = "bootstrap-meta.json"
STAGED_CLAUDE_REL = ".claude"


def staging_dir():
    return Path(os.environ.get("WORKSPACE_COMPOSED_DIR", DEFAULT_STAGING_DIR))


def staged_claude_dir():
    return staging_dir() / STAGED_CLAUDE_REL


def meta_path():
    return staging_dir() / META_FILENAME


def write_meta(team_input, chain_rel_paths, tool_version, composed_at,
               disable_stop_hook=False):
    """Write the staging meta sidecar.

    `chain_rel_paths` is the list of ancestor level paths (relative to the
    workspace root) that compose collected — apply-only replays them to rebuild
    the CLAUDE.md marker block without re-resolving the team.

    `disable_stop_hook` records whether the setup tier was asked to neutralize
    the platform's stop-hook-git-check.sh. The platform re-installs that hook
    on every session start, so the apply tier reads this flag to re-apply the
    no-op per session (see #72). Absent/false in older metas → never touched.
    """
    p = meta_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({
        "team_input": team_input,
        "chain_rel_paths": [str(x) for x in chain_rel_paths],
        "tool_version": tool_version,
        "composed_at": composed_at,
        "disable_stop_hook": bool(disable_stop_hook),
    }, indent=2) + "\n")


def read_meta():
    p = meta_path()
    if not p.is_file():
        return None
    return json.loads(p.read_text())
