"""ANSI-aware logging helpers for the bootstrap tool.

No external deps. Color is auto-disabled when stdout is not a TTY or when the
NO_COLOR env var is set.

Optional file tee: `set_log_file(path)` mirrors every log call to a plain-text
log file (ANSI stripped) for in-session inspection. Used by the cloud workflow
(#45) because the cloud setup-script stdout is truncated/easy to miss.
"""

import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path


def _use_color():
    if os.environ.get("NO_COLOR"):
        return False
    return sys.stdout.isatty()


_COLOR = _use_color()


def _c(code):
    return code if _COLOR else ""


RESET = _c("\033[0m")
BOLD = _c("\033[1m")
DIM = _c("\033[2m")
RED = _c("\033[31m")
GREEN = _c("\033[32m")
YELLOW = _c("\033[33m")
BLUE = _c("\033[34m")


_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
_log_file = None  # type: Path | None


def _iso_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def set_log_file(path):
    """Configure subsequent log calls to also append plain text to `path`.

    Best-effort: write failures are swallowed so logging never crashes setup.
    Pass None to disable the tee.
    """
    global _log_file
    if path is None:
        _log_file = None
        return
    p = Path(path)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a") as f:
            f.write(f"---- {_iso_now()} cloud-bootstrap log ----\n")
        _log_file = p
    except OSError:
        _log_file = None


def _strip_ansi(s):
    return _ANSI_RE.sub("", s)


def _tee(line):
    if _log_file is None:
        return
    try:
        with _log_file.open("a") as f:
            f.write(f"{_iso_now()} {_strip_ansi(line)}\n")
    except OSError:
        pass


def info(msg):
    print(msg)
    _tee(msg)


def step(msg):
    print(f"{BOLD}» {msg}{RESET}")
    _tee(f"» {msg}")


def ok(msg):
    print(f"{GREEN}✓{RESET} {msg}")
    _tee(f"✓ {msg}")


def change(msg):
    print(f"{YELLOW}~{RESET} {msg}")
    _tee(f"~ {msg}")


def warn(msg):
    print(f"{YELLOW}!{RESET} {msg}", file=sys.stderr)
    _tee(f"! {msg}")


def error(msg):
    print(f"{RED}✗{RESET} {msg}", file=sys.stderr)
    _tee(f"✗ {msg}")


def dim(msg):
    print(f"{DIM}{msg}{RESET}")
    _tee(msg)


def header(title, body=None):
    print(f"{BOLD}{title}{RESET}")
    _tee(title)
    if body:
        for line in body.splitlines():
            print(f"  {line}")
            _tee(f"  {line}")
