#!/usr/bin/env python3
"""check-maintenance: every context file says where it comes from (issue #178).

Agent context is compiled from somewhere - Notion, the HR system, a data warehouse,
a Slack channel, a colleague's head. Some of it is a verbatim copy that must be
fixed at the source; most of it is hand-maintained here. Either way a reader,
human or agent, needs the same facts at the top of the file: where it comes
from, who answers for it, whether edits belong here or upstream, and when it
was last checked. CONTRIBUTING.md ("Maintenance header") defines the header; this
script enforces it.

Scope: every tracked Markdown file under a `context/`, `references/`, or
`agent-references/` directory, except CLAUDE.md, README.md, SKILL.md, and
anything under docs-for-humans/. Data files in those trees (JSON, CSV, HTML,
XLSX, ...) cannot carry a header, so a sibling Markdown card claims them
through a `files:` list. A card with `edit: upstream` and no `verified_at`
takes the newest commit that changed *only* its files as the verification
date: a sync commit touches the data and nothing else, and is by
construction a check against the source. A hand edit or a refactor that also
touched other files does not count, and a card with no such commit is simply
unverified. Only cards derive: a synced Markdown file can carry a date, so
its exporter writes the export date into the header itself.

Headers are written by people who know the file, never generated. A missing
header is a warning across the tree and an error on any file the PR touches
(--changed-since <base>, compared from the merge base with HEAD so commits
that landed on the base branch meanwhile do not count): every edit is the
moment the header gets written.

Errors (exit 1):
  - in-scope .md changed since --changed-since without a header
  - a header the strict YAML subset below cannot parse, or with unknown keys
  - `edit` missing or not one of here | upstream, or `upstream` without `sources`
  - `review_every` missing or not <n>d
  - `verified_at` present but not YYYY-MM-DD
  - `files` entry that is not a tracked file
  - data file claimed by no card, or by more than one

Warnings (exit 0; errors with --strict):
  - in-scope .md without a header (not changed in this PR)
  - `sources`, `owner`, or `verified_at` missing (recommended fields)
  - `owner` not found in the org chart (who-is data)
  - stale: verified_at (or the derived sync date) + review_every is in the past

The YAML subset: one flat mapping of `key: value` scalars and `- item` or
`[a, b]` lists of scalars, plus `#` comments. Nothing else - no nested
mappings, no block scalars. Everything the subset accepts, a real YAML parser
reads the same way (a bare date stays text here, where YAML would type it);
anything YAML would read differently (an unquoted value containing `: ` or
` #`, ending in `:`, or looking like a number or boolean) is a parse error
here, so quote it.

Usage:
    python3 tools/maintenance/check.py                              # errors fail, warnings print
    python3 tools/maintenance/check.py --changed-since origin/main  # what CI runs on a PR
    python3 tools/maintenance/check.py --strict                     # warnings fail too
    python3 tools/maintenance/check.py --report                     # freshness table per file

Exit codes: 0 clean, 1 findings, 2 could not run (no git, unknown ref).
"""

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

SCOPE_RE = re.compile(r"(^|/)(context|references|agent-references)/")
EXCLUDE_RE = re.compile(r"(^|/)(docs-for-humans|projects)/")
SKIP_NAMES = {"CLAUDE.md", "README.md", "SKILL.md"}
KEYS = ("sources", "owner", "edit", "review_every", "verified_at", "files")
REQUIRED = ("edit", "review_every")
RECOMMENDED = ("sources", "owner", "verified_at")
EDIT_VALUES = ("here", "upstream")
REVIEW_RE = re.compile(r"^(\d+)d$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ORG_CHART = ".claude/skills/who-is/references/org-chart.json"


class Fatal(Exception):
    """The check could not run at all (distinct from findings)."""


class ParseError(Exception):
    pass


# --- YAML subset ------------------------------------------------------------

def _split_inline_list(inner: str):
    parts, cur, quote = [], "", None
    for ch in inner:
        if quote:
            cur += ch
            if ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
            cur += ch
        elif ch == ",":
            parts.append(cur.strip())
            cur = ""
        else:
            cur += ch
    if cur.strip():
        parts.append(cur.strip())
    return parts


def _scalar(v: str):
    v = v.strip()
    if v.startswith("[") and "]" in v:
        head, _, tail = v.rpartition("]")
        if tail.strip() and not tail.strip().startswith("#"):
            raise ParseError(f"text after the closing bracket: {v!r}")
        inner = head[1:].strip()
        return [_scalar(x) for x in _split_inline_list(inner)] if inner else []
    if v[:1] in ("\"", "'"):
        q = v[0]
        end = v.find(q, 1)
        if end == -1:
            raise ParseError(f"unterminated quote: {v!r}")
        rest = v[end + 1:].strip()
        if rest and not rest.startswith("#"):
            raise ParseError(f"text after the closing quote: {v!r}")
        if q == "\"" and "\\" in v[1:end]:
            raise ParseError(f"backslash escapes are not supported, use single quotes: {v!r}")
        return v[1:end]
    v = re.split(r"\s+#", v, maxsplit=1)[0].strip()
    if not v:
        raise ParseError("empty value: write the key alone, or quote an empty string")
    # Anything a YAML parser would not read as this same plain string.
    if ": " in v or v.endswith(":") or v.startswith("#"):
        raise ParseError(f"quote this value, YAML reads it as a nested key or a comment: {v!r}")
    if v[0] in "{}[]&*!|>%@`,?'\"" or v == "-" or v.startswith("- ") or v in ("~", "null", "Null", "NULL", "true", "false",
                                            "True", "False", "TRUE", "FALSE", "yes", "no",
                                            "Yes", "No", "YES", "NO", "on", "off", "On", "Off"):
        raise ParseError(f"quote this value, YAML gives it a special meaning: {v!r}")
    if re.fullmatch(r"[-+]?(\d[\d_]*\.?[\d_]*([eE][-+]?\d+)?|\.\d+|0x[0-9a-fA-F]+|0o[0-7]+|\.inf|\.nan)", v):
        raise ParseError(f"quote this value, YAML reads it as a number: {v!r}")
    return v


def parse_yaml_subset(lines):
    """Parse the frontmatter subset (one flat mapping; list values) into a dict.

    Raises ParseError on anything outside the subset, including constructs a
    real YAML parser would accept but read differently from a naive split.
    """
    items = []
    for raw in lines:
        if "\t" in raw[:len(raw) - len(raw.lstrip())]:
            raise ParseError("tabs are not allowed in YAML indentation")
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        items.append((len(raw) - len(raw.lstrip(" ")), raw.strip()))
    if not items:
        return {}
    d, i, top = {}, 0, items[0][0]
    while i < len(items):
        ind, s = items[i]
        if ind != top:
            raise ParseError(f"unexpected indent: {s!r}")
        m = re.match(r"^([A-Za-z_][\w-]*):(?:\s+(.*))?$", s)
        if not m:
            raise ParseError(f"cannot parse line: {s!r}")
        key, val = m.group(1), (m.group(2) or "").strip()
        if key in d:
            raise ParseError(f"duplicate key `{key}`")
        i += 1
        if val:
            d[key] = _scalar(val)
            continue
        if i < len(items) and items[i][0] > top:
            # A list: every item at one indent, each `- scalar`.
            lind, out = items[i][0], []
            while i < len(items) and items[i][0] > top:
                ind, s = items[i]
                if ind != lind or not s.startswith("- "):
                    raise ParseError(f"expected a '- item' at indent {lind} (nested mappings and "
                                     f"block scalars are not supported): {s!r}")
                out.append(_scalar(s[2:]))
                i += 1
            d[key] = out
        else:
            d[key] = None
    return d


def split_frontmatter(text: str):
    """Return (dict, None) for a header, (None, None) for no header, (None, err) if broken."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None, None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            try:
                return parse_yaml_subset(lines[1:i]), None
            except ParseError as e:
                return None, f"frontmatter: {e}"
    return None, "frontmatter opened with --- on line 1 but never closed"


# --- org chart owner lookup --------------------------------------------------

TRANSLIT = str.maketrans({
    "ł": "l", "Ł": "L", "ø": "o", "Ø": "O", "đ": "d", "Đ": "D",
    "ı": "i", "ħ": "h", "ŧ": "t", "ŋ": "n", "ð": "d", "þ": "th",
    "ß": "ss", "æ": "ae", "Æ": "AE", "œ": "oe", "Œ": "OE",
})


def fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text or "")
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return " ".join(stripped.translate(TRANSLIT).casefold().split())


def load_people(root: Path):
    """Folded names and nicknames from the org chart, or None if unavailable/empty."""
    p = root / ORG_CHART
    if not p.is_file():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    people = data.get("people") or []
    if not people:
        return None
    names = set()
    for person in people:
        for k in ("name", "nickname"):
            if person.get(k):
                names.add(fold(person[k]))
    return names


# --- checks -------------------------------------------------------------------

def tracked_files(root: Path):
    try:
        out = subprocess.run(["git", "-C", str(root), "ls-files", "-z"],
                             capture_output=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError) as e:
        raise Fatal(f"git ls-files failed: {e}")
    return [p.decode("utf-8") for p in out.split(b"\0") if p]


def changed_files(root: Path, ref: str):
    """Paths this branch changed relative to REF: the diff from the merge base
    of REF and HEAD to the working tree, so commits that landed on REF after
    the branch point are not blamed on the branch."""
    try:
        base = subprocess.run(["git", "-C", str(root), "merge-base", ref, "HEAD"],
                              capture_output=True, check=True, text=True).stdout.strip()
        out = subprocess.run(["git", "-C", str(root), "diff", "--name-only", base],
                             capture_output=True, check=True, text=True).stdout
    except (OSError, subprocess.CalledProcessError) as e:
        raise Fatal(f"git diff against the merge base with {ref!r} failed: {e}")
    return set(l.strip() for l in out.splitlines() if l.strip())


def in_scope(path: str) -> bool:
    return bool(SCOPE_RE.search(path)) and not EXCLUDE_RE.search(path)


def validate_header(where: str, h, today: dt.date, people):
    """Return (errors, warnings, claimed_files) for one header dict."""
    errors, warnings, claimed = [], [], []
    if not isinstance(h, dict):
        return [f"{where}: header must be a mapping"], [], []
    for k in h:
        if k not in KEYS:
            errors.append(f"{where}: unknown header key `{k}` (allowed: {', '.join(KEYS)})")
    for k in REQUIRED:
        if h.get(k) in (None, ""):
            errors.append(f"{where}: `{k}` is required")
    edit = h.get("edit")
    if edit not in (None, "") and edit not in EDIT_VALUES:
        errors.append(f"{where}: `edit` must be one of {list(EDIT_VALUES)}, got {edit!r}")
    if edit == "upstream" and h.get("sources") in (None, "", []):
        errors.append(f"{where}: `edit: upstream` requires `sources` - a copy must say what it copies")
    days = None
    rev = h.get("review_every")
    if rev not in (None, ""):
        m = REVIEW_RE.match(str(rev))
        if not m or int(m.group(1)) <= 0:
            errors.append(f"{where}: `review_every` must look like 90d, got {rev!r}")
        else:
            days = int(m.group(1))
    verified = None
    va = h.get("verified_at")
    if va not in (None, ""):
        if not isinstance(va, str) or not DATE_RE.match(va):
            errors.append(f"{where}: `verified_at` must be YYYY-MM-DD, got {va!r}")
        else:
            try:
                verified = dt.date.fromisoformat(va)
            except ValueError:
                errors.append(f"{where}: `verified_at` is not a real date: {va!r}")
    src = h.get("sources")
    if src not in (None, "", []) and not (  # an empty list on upstream is already the error above
        isinstance(src, str) or (isinstance(src, list) and all(isinstance(x, str) and x for x in src) and src)
    ):
        errors.append(f"{where}: `sources` must be a string or a list of strings")
    owner = h.get("owner")
    if owner not in (None, "") and not isinstance(owner, str):
        errors.append(f"{where}: `owner` must be a string")
    files = h.get("files")
    if files is not None:
        if not isinstance(files, list) or not all(isinstance(x, str) and x for x in files):
            errors.append(f"{where}: `files` must be a list of paths")
        else:
            claimed = files

    for k in RECOMMENDED:
        if h.get(k) in (None, "", []) and not (k == "sources" and edit == "upstream"):
            warnings.append(f"{where}: `{k}` not set")  # upstream without sources is already an error
    if isinstance(owner, str) and owner and people is not None and fold(owner) not in people:
        warnings.append(f"{where}: owner {owner!r} is not in the org chart (left the company, or a typo?)")
    if verified and days and verified + dt.timedelta(days=days) < today:
        due = verified + dt.timedelta(days=days)
        warnings.append(f"{where}: stale - verified {verified}, review every {days}d, due {due}")
    return errors, warnings, claimed


def last_sync(root: Path, paths):
    """Date of the newest commit that changed only files in `paths`, or None.

    That is what a sync commit looks like: the data and nothing else. A hand
    edit or a refactor that also touched other files is not a verification.
    Merge commits list no files and are skipped; --full-history keeps a sync
    that a later merge resolved away from being simplified out of the log.
    """
    want = set(paths)
    out = subprocess.run(["git", "-C", str(root), "log", "--full-history", "--full-diff", "--format=%x01%cs",
                          "--name-only", "--", *paths], capture_output=True, text=True).stdout
    for block in out.split("\x01")[1:]:
        lines = [l.strip() for l in block.splitlines() if l.strip()]
        if len(lines) > 1 and set(lines[1:]) <= want:
            try:
                return dt.date.fromisoformat(lines[0])
            except ValueError:
                return None
    return None


def check(root: Path, files, today=None, people=None, changed=None):
    """Return (errors, warnings, rows). rows feed --report.

    `changed` is the set of paths touched by the PR under review: a missing
    header on one of those is an error; elsewhere it is a warning.
    """
    today = today or dt.date.today()
    changed = set(changed or ())
    tracked = set(files)
    errors, warnings, rows = [], [], []
    data_files = [f for f in files if in_scope(f) and not f.endswith(".md")]
    claims = {f: [] for f in data_files}

    def claim(card: str, rel_paths):
        base = Path(card).parent
        for rel in rel_paths:
            target = os.path.normpath((base / rel).as_posix())
            if target not in tracked:
                errors.append(f"{card}: `files` entry {rel!r} is not a tracked file")
                continue
            claims.setdefault(target, []).append(card)

    def row(path, h, errs):
        # str(): a list-valued field is already an error; the report must still print.
        rows.append((path, str(h.get("owner") or "-"), str(h.get("verified_at") or "-"),
                     str(h.get("review_every") or "-"), "error" if errs else
                     ("stale" if any("stale" in w for w in warnings if w.startswith(path + ":")) else
                      ("unverified" if not h.get("verified_at") else "ok"))))

    for f in files:
        if not in_scope(f) or not f.endswith(".md") or Path(f).name in SKIP_NAMES:
            continue
        try:
            text = (root / f).read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            errors.append(f"{f}: cannot read: {e}")
            continue
        h, err = split_frontmatter(text)
        if err:
            errors.append(f"{f}: {err}")
            continue
        if h is None:
            msg = f"{f}: no maintenance header"
            if f in changed:
                errors.append(msg + " - this PR touches the file, so add one (CONTRIBUTING.md, "
                              "Maintenance header; ask the folder's CODEOWNER for sources and owner)")
            else:
                warnings.append(msg)
            rows.append((f, "-", "-", "-", "no header"))
            continue
        errs, warns, claimed = validate_header(f, h, today, people)
        # A card for synced data with no verified_at: the sync commit is the
        # verification, because a data file cannot carry a date. Only cards derive;
        # a synced Markdown file carries the export date in its own header.
        if claimed and h.get("edit") == "upstream" and not h.get("verified_at") and not errs:
            base = Path(f).parent
            derived = last_sync(root, [os.path.normpath((base / rel).as_posix()) for rel in claimed])
            if derived:
                h = dict(h, verified_at=derived.isoformat())
                warns = [w for w in warns if not w.endswith("`verified_at` not set")]
                days = int(REVIEW_RE.match(str(h["review_every"])).group(1))
                if derived + dt.timedelta(days=days) < today:
                    warns.append(f"{f}: stale - last synced {derived}, review every {days}d, "
                                 f"due {derived + dt.timedelta(days=days)}")
            # No commit that touched only these files: the card stays "unverified".
        errors.extend(errs)
        warnings.extend(warns)
        claim(f, claimed)
        row(f, h, errs)

    for d, cards in claims.items():
        if d not in data_files:
            continue
        if not cards:
            errors.append(f"{d}: data file not claimed by any card - add a sibling .md with a "
                          "maintenance header whose `files:` lists it")
        elif len(cards) > 1:
            errors.append(f"{d}: claimed by {len(cards)} cards: {', '.join(cards)}")
    return errors, warnings, rows


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Check maintenance headers on context files.")
    ap.add_argument("--strict", action="store_true", help="treat warnings as errors")
    ap.add_argument("--report", action="store_true", help="print a freshness table")
    ap.add_argument("--verbose", action="store_true",
                    help="list every file behind a summary line instead of a count")
    ap.add_argument("--changed-since", metavar="REF", default=None,
                    help="fail on a missing header only for files this branch changed relative to REF "
                         "(merge base of REF and HEAD; CI passes the PR base branch)")
    ap.add_argument("--root", type=Path, default=None, help=argparse.SUPPRESS)
    ap.add_argument("--today", default=None, help=argparse.SUPPRESS)
    args = ap.parse_args(argv)

    root = (args.root or Path(__file__).resolve().parent.parent.parent).resolve()
    today = dt.date.fromisoformat(args.today) if args.today else dt.date.today()
    try:
        files = tracked_files(root)
        changed = changed_files(root, args.changed_since) if args.changed_since else None
    except Fatal as e:
        print(f"check-maintenance: cannot run: {e}", file=sys.stderr)
        return 2
    people = load_people(root)
    if people is None:
        # Not a finding: the tree may be fine. But say so, or a moved or empty
        # org chart would switch the owner check off without anyone noticing.
        print(f"check-maintenance: note: no org chart at {ORG_CHART}; `owner` names are not checked",
              file=sys.stderr)
    errors, warnings, rows = check(root, files, today, people, changed)

    if args.report:
        w = max((len(r[0]) for r in rows), default=4)
        print(f"{'file':<{w}}  {'owner':<22} {'verified':<11} {'every':<6} status")
        for r in sorted(rows):
            print(f"{r[0]:<{w}}  {r[1][:22]:<22} {r[2]:<11} {r[3]:<6} {r[4]}")
        print()
    for e in errors:
        print(f"ERROR {e}")
    # Recommended-field warnings can run into the hundreds; one line per field
    # keeps CI logs readable. --verbose lists the files.
    not_set = re.compile(r"^(.*): `(\w+)` not set$")
    no_header = re.compile(r"^(.*): no maintenance header$")
    per_field, missing = {}, []
    for wmsg in warnings:
        m = not_set.match(wmsg)
        if m and not args.verbose:
            per_field.setdefault(m.group(2), []).append(m.group(1))
        elif no_header.match(wmsg) and not args.verbose:
            missing.append(no_header.match(wmsg).group(1))
        else:
            print(f"WARN  {wmsg}")
    if missing:
        print(f"WARN  no maintenance header on {len(missing)} files (--verbose lists them; "
              "a PR touching one must add it)")
    for field in RECOMMENDED:
        if field in per_field:
            print(f"WARN  `{field}` not set on {len(per_field[field])} files (--verbose lists them)")
    print(f"check-maintenance: {len(rows)} files, {len(errors)} errors, {len(warnings)} warnings"
          + (" (strict)" if args.strict else ""))
    return 1 if errors or (args.strict and warnings) else 0


if __name__ == "__main__":
    sys.exit(main())
