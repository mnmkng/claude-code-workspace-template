"""personal sync: clone personal CLAUDE.md from a gist via the platform git proxy.

Public API:
  run(args)                       — `personal sync --gist URL` subcommand entry.
  sync(workspace_root, gist_url)      — programmatic entry used by cloud.py.

Writes to `<workspace_root>/CLAUDE.local.md` (gitignored, root-level — parity with
settings.local.json convention).

Why git clone instead of HTTP fetch: in Claude Code Cloud, all git operations
flow through Anthropic's GitHub proxy which transparently auths against the
session user's GitHub identity. This means private gists Just Work without any
PAT in env vars (which the platform UI explicitly warns against). The clone
URL form `https://gist.github.com/<gist-id>.git` is what the proxy expects.

Locally (no proxy), the same clone uses whatever git credentials the engineer
has — typically also fine for their own gists.

Failure policy: any failure (no URL, unparseable URL, git not installed, clone
fails, timeout) → warn + truncate to empty file. Never crash the caller.
@import of a missing or empty file is a silent skip (per #41 Q2), so a
fetched-empty file is indistinguishable from "no personal context" — exactly
what we want.

Truncate-on-failure is deliberate: a stale gist value from a prior session
must not silently persist if the user's gist URL is now unset or broken.
"""

import os
import re
import subprocess
import tempfile
from pathlib import Path

from lib import localmd
from lib import log
from lib import paths as path_lib


PERSONAL_CONTEXT_REL = "CLAUDE.local.md"
CLONE_TIMEOUT_SECONDS = 20
GIST_ID_RE = re.compile(r"\b([0-9a-fA-F]{20,40})\b")


def run(args):
    workspace_root = path_lib.require_workspace_root()
    gist_url = getattr(args, "gist", None) or os.environ.get("WORKSPACE_PERSONAL_GIST")
    sync(workspace_root, gist_url)
    return 0


def sync(workspace_root, gist_url):
    """Clone `gist_url` into the personal region of `workspace_root/CLAUDE.local.md`.

    Always returns cleanly. No URL → empty personal region. Unparseable URL →
    warn + empty. Clone failure → warn + empty. Success → the gist's content.

    The file may also hold a bootstrap team-context block (written by compose);
    that block is preserved verbatim - sync only owns the personal region below
    it. With no team block present the file is exactly the personal body, which
    is the historical contract.
    """
    dest = Path(workspace_root) / PERSONAL_CONTEXT_REL
    team_block = localmd.extract_team_block(dest.read_text()) if dest.is_file() else ""
    body = _fetch_personal_body(gist_url, dest.name)
    dest.write_text(localmd.join(team_block, body))


def _fetch_personal_body(gist_url, dest_name):
    """Return the personal-context body for CLAUDE.local.md, or '' on any miss."""
    if not gist_url:
        log.dim("personal: WORKSPACE_PERSONAL_GIST not set; personal context left empty")
        return ""

    gist_id = _extract_gist_id(gist_url)
    if not gist_id:
        log.warn(
            f"personal: cannot parse gist ID from {gist_url!r}; "
            "expected a gist URL or 20-40 char hex ID; writing empty placeholder"
        )
        return ""

    log.step(f"personal: cloning gist {gist_id[:8]}… → {dest_name}")
    try:
        body = _clone_and_read(gist_id)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired,
            FileNotFoundError, OSError) as e:
        log.warn(
            f"personal: clone failed ({type(e).__name__}); writing empty placeholder"
        )
        return ""

    log.ok(f"personal: fetched {len(body)} bytes of personal context")
    return body


def _extract_gist_id(url_or_id):
    """Pull the gist ID out of any reasonable URL form, or accept a bare ID.

    Accepts:
      https://gist.github.com/<user>/<id>
      https://gist.github.com/<user>/<id>.git
      https://gist.github.com/<id>
      https://gist.githubusercontent.com/<user>/<id>/raw/<commit>/<file>
      <id>   (bare hex)

    The regex matches the FIRST 20-40 char hex run — for gist URLs that's
    always the gist ID, since any subsequent hex (commit SHA, etc.) follows
    in the path.
    """
    m = GIST_ID_RE.search(url_or_id)
    return m.group(1) if m else None


def _clone_and_read(gist_id):
    """Shallow-clone the gist via git (platform proxy handles auth); return contents.

    For single-file gists, return that file's text as-is. For multi-file
    gists, concatenate sorted files with comment-style file-name dividers
    so the assistant can tell them apart.
    """
    with tempfile.TemporaryDirectory() as tmp:
        dest_dir = Path(tmp) / "gist"
        subprocess.run(
            ["git", "clone", "--depth", "1", "--quiet",
             f"https://gist.github.com/{gist_id}.git", str(dest_dir)],
            check=True,
            capture_output=True,
            text=True,
            timeout=CLONE_TIMEOUT_SECONDS,
        )
        files = sorted(
            p for p in dest_dir.iterdir()
            if p.is_file() and not p.name.startswith(".")
        )
        if not files:
            return ""
        if len(files) == 1:
            return files[0].read_text()
        return "\n\n".join(
            f"<!-- {f.name} -->\n{f.read_text()}" for f in files
        )
