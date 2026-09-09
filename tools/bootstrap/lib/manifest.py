"""Read/write the composition manifest at .claude/.bootstrap-manifest.json.

The manifest records what compose did so reset can undo it and doctor can
inspect state. Also tracks a flat newline-delimited list of every copied
file path in .claude/.bootstrap-copied-files for reset to consume.
"""

import json
from datetime import datetime, timezone
from pathlib import Path


MANIFEST_VERSION = "1.0.0"
MANIFEST_REL = ".claude/.bootstrap-manifest.json"
COPIED_FILES_REL = ".claude/.bootstrap-copied-files"


def manifest_path(workspace_root):
    return Path(workspace_root) / MANIFEST_REL


def copied_files_path(workspace_root):
    return Path(workspace_root) / COPIED_FILES_REL


def read(workspace_root):
    p = manifest_path(workspace_root)
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text())
    except json.JSONDecodeError as e:
        raise SystemExit(f"manifest at {p} is invalid JSON: {e}")


def write(workspace_root, data):
    validate(data)
    p = manifest_path(workspace_root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2) + "\n")


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_copied_files(workspace_root, paths):
    p = copied_files_path(workspace_root)
    p.parent.mkdir(parents=True, exist_ok=True)
    body = "\n".join(str(x) for x in paths)
    p.write_text(body + ("\n" if paths else ""))


def read_copied_files(workspace_root):
    p = copied_files_path(workspace_root)
    if not p.is_file():
        return []
    return [ln for ln in p.read_text().splitlines() if ln.strip()]


REQUIRED_KEYS = {"team_input", "team_resolved_path", "composed_at", "tool_version", "levels"}


def validate(data):
    if not isinstance(data, dict):
        raise ValueError("manifest must be a JSON object")
    missing = REQUIRED_KEYS - data.keys()
    if missing:
        raise ValueError(f"manifest missing keys: {sorted(missing)}")
    if not isinstance(data["levels"], list):
        raise ValueError("manifest.levels must be a list")
    for i, lvl in enumerate(data["levels"]):
        if not isinstance(lvl, dict):
            raise ValueError(f"manifest.levels[{i}] must be an object")
        if "path" not in lvl:
            raise ValueError(f"manifest.levels[{i}] missing 'path'")
