"""scaffold: create department and team folders from a JSON spec.

CONTRIBUTING.md describes what a department or team folder must contain; this
is that description in executable form. The `setup-workspace` and `add-team`
skills both build a spec and hand it here rather than writing folders by hand,
so a folder created in a session and a folder created by a human follow the
same conventions and pass the same checks.

Spec shape (`company` is optional; `title` and `tools` are optional per node):

  {
    "company": {"name": "Acme Paper", "slug": "acme-paper"},
    "departments": [
      {"name": "sales", "owner": "@east-lead", "tools": ["HubSpot", "Slack"],
       "teams": [{"name": "east-sales", "owner": "@east-lead"}]},
      {"name": "finance", "owner": "@finance-lead", "tools": []}
    ]
  }

Per node it writes `CLAUDE.md` (the four standard sections, `[TODO: ...]` in
each) and `projects/.gitkeep`, and appends a CODEOWNERS line. Then it stages
the new paths, runs `settings-sync` to stamp the security policy into each new
folder, and runs `lint`.

Three properties the callers depend on:

  - **Validate everything, then write.** A spec with one bad name writes no
    files at all, so a refusal never leaves a half-made tree that fails the
    root-marker check or CI.
  - **Idempotent and additive.** Re-running the same spec changes nothing; a
    spec with one new department adds only that department. Nothing is ever
    deleted or overwritten - an existing CLAUDE.md is left exactly as it is,
    because by the second run it holds someone's content.
  - **Never leaves CI red.** settings-sync and lint run at the end; their
    findings are the command's exit code.

Staging: settings-sync and lint both enumerate *tracked* files, so a folder
git does not know about gets no stamp and is invisible to the uniqueness
check. scaffold therefore `git add`s what it writes (staging only - it never
commits).

Stdlib only.  Target: Python 3.9+.
"""

import json
import re
import subprocess
from pathlib import Path

from lib import log
from lib import paths as path_lib

import lint
import settings_sync


KEBAB_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")

DEPT_KEYS = {"name", "title", "owner", "tools", "teams"}
TEAM_KEYS = {"name", "title", "owner", "tools", "teams"}
COMPANY_KEYS = {"name", "slug"}

CODEOWNERS_REL = ".github/CODEOWNERS"

# Column the owner list starts at in CODEOWNERS, matching the existing lines.
OWNER_COLUMN = 67

# Names that would collide with the canonical layout if used as a folder name.
RESERVED_NAMES = {"teams", "context", "projects", "docs-for-humans", "claude"}


class SpecError(SystemExit):
    """Raised with every problem found, so one run reports the whole list."""

    def __init__(self, problems):
        self.problems = list(problems)
        body = "\n".join(f"  - {p}" for p in self.problems)
        super().__init__(f"scaffold: the spec was not applied:\n{body}")


# --- spec -> plan ------------------------------------------------------------

def title_for(node):
    """`# <Title> context` for the H1. Sentence case from the folder name
    ('human-resources' -> 'Human resources'), or the spec's own `title`."""
    explicit = node.get("title")
    if explicit:
        return str(explicit)
    words = str(node.get("name", "")).split("-")
    return " ".join([words[0].capitalize()] + words[1:]) if words else ""


def plan_nodes(spec):
    """Flatten the spec into a list of nodes, outermost first.

    Each node: kind, name, title, rel (repo-relative folder), owners (the
    CODEOWNERS owner list for its line), tools.
    """
    nodes = []

    def walk(entry, parent_rel, parent_owner, kind):
        name = entry.get("name")
        rel = (f"{parent_rel}/teams/{name}" if parent_rel
               else f"departments/{name}")
        owner = entry.get("owner")
        # A team line carries the team owner then the department owner: GitHub
        # never requests a review from the PR author and never falls back to an
        # earlier pattern, so a team lead's own PR would otherwise request
        # nobody (see the CODEOWNERS header).
        owners = [o for o in (owner, parent_owner) if o]
        nodes.append({
            "kind": kind,
            "name": name,
            "title": title_for(entry),
            "rel": rel,
            "owner": owner,
            "owners": owners,
            "tools": list(entry.get("tools") or []),
        })
        for team in entry.get("teams") or []:
            walk(team, rel, owner, "team")

    for dept in spec.get("departments") or []:
        walk(dept, None, None, "department")
    return nodes


def _existing_basenames(workspace_root):
    """basename -> [folder] for every CLAUDE.md-bearing folder on disk.

    The filesystem, not git: a folder scaffolded a minute ago and not yet
    committed still collides with one in the spec.
    """
    out = {}
    for md in Path(workspace_root).rglob("CLAUDE.md"):
        folder = md.parent
        if folder == Path(workspace_root):
            continue
        rel = folder.relative_to(workspace_root).as_posix()
        if any(part in ("projects", ".git", "node_modules") for part in rel.split("/")):
            continue
        if any(rel.startswith(p) for p in lint.EXCLUDED_PREFIXES):
            continue
        out.setdefault(folder.name, []).append(rel)
    return out


def validate(spec, workspace_root):
    """Return every problem with the spec. Empty list means it can be applied."""
    problems = []
    if not isinstance(spec, dict):
        return ["the spec must be a JSON object"]

    unknown_top = set(spec) - {"company", "departments"}
    if unknown_top:
        problems.append(f"unknown top-level key(s): {sorted(unknown_top)}")

    company = spec.get("company")
    if company is not None:
        if not isinstance(company, dict):
            problems.append("company must be an object with a name and a slug")
        else:
            unknown = set(company) - COMPANY_KEYS
            if unknown:
                problems.append(f"unknown company key(s): {sorted(unknown)}")
            if not str(company.get("name") or "").strip():
                problems.append("company.name must not be empty")
            slug = company.get("slug")
            if slug is not None and not KEBAB_RE.match(str(slug)):
                problems.append(f"company.slug must be kebab-case: {slug!r}")

    departments = spec.get("departments")
    if not isinstance(departments, list) or not departments:
        problems.append("departments must be a non-empty list")
        return problems

    def check_entry(entry, kind, allowed):
        if not isinstance(entry, dict):
            problems.append(f"each {kind} must be an object, got {entry!r}")
            return
        unknown = set(entry) - allowed
        if unknown:
            problems.append(
                f"{kind} {entry.get('name')!r}: unknown key(s) {sorted(unknown)}")
        name = entry.get("name")
        if not isinstance(name, str) or not KEBAB_RE.match(name):
            problems.append(
                f"{kind} name must be kebab-case (lowercase, digits, single "
                f"hyphens): {name!r}")
        elif name in RESERVED_NAMES:
            problems.append(
                f"{kind} name {name!r} is a reserved folder name in the "
                "canonical layout")
        owner = entry.get("owner")
        if not isinstance(owner, str) or not owner.startswith("@") or len(owner) < 2:
            problems.append(
                f"{kind} {name!r}: owner must be a GitHub handle starting with "
                f"'@', got {owner!r}")
        tools = entry.get("tools")
        if tools is not None and (not isinstance(tools, list)
                                  or any(not isinstance(t, str) for t in tools)):
            problems.append(f"{kind} {name!r}: tools must be a list of strings")
        for team in entry.get("teams") or []:
            check_entry(team, "team", TEAM_KEYS)

    for dept in departments:
        check_entry(dept, "department", DEPT_KEYS)

    if problems:
        # Name and shape problems make the uniqueness pass meaningless.
        return problems

    nodes = plan_nodes(spec)
    seen = {}
    for node in nodes:
        seen.setdefault(node["name"], []).append(node["rel"])
    for name, rels in sorted(seen.items()):
        if len(rels) > 1:
            problems.append(
                f"folder name {name!r} appears more than once in the spec "
                f"({sorted(rels)}); folder names containing a CLAUDE.md must be "
                "globally unique")

    existing = _existing_basenames(workspace_root)
    for node in nodes:
        elsewhere = [r for r in existing.get(node["name"], []) if r != node["rel"]]
        if elsewhere:
            problems.append(
                f"folder name {node['name']!r} already exists at {elsewhere} - "
                "folder names containing a CLAUDE.md must be globally unique "
                "(cloud team resolution keys on the basename)")
    return problems


# --- rendering ---------------------------------------------------------------

def claude_md(node):
    """The four standard sections from CONTRIBUTING 'Department CLAUDE.md',
    with a TODO in each. Department-specific sections come after them, which
    is why nothing else is written here."""
    kind = node["kind"]
    lines = [
        f"# {node['title']} context",
        "",
        f"[TODO: one line on what this {kind} owns - where its work starts and "
        "where it stops.]",
        "",
        "## Team structure",
        "",
        "[TODO: one row per role. Roles and counts, never names: names change "
        "faster than the file does and live in the `who-is` skill's data.]",
        "",
        "| Role | Count | Reports to |",
        "|------|-------|------------|",
        "|      |       |            |",
        "",
        "## Key metrics",
        "",
        f"[TODO: the numbers this {kind} is measured on, each with its source "
        "and an \"as of\" month. Company-wide figures belong in "
        "`context/key-metrics.md`; cite them from there rather than repeating "
        "them here.]",
        "",
        "## Processes",
        "",
        f"[TODO: the durable processes this {kind} runs - what happens, in what "
        "order, and who decides. Ephemeral priorities belong in `projects/`.]",
        "",
        "## Tools and systems",
        "",
    ]
    if node["tools"]:
        lines += [
            "[TODO: for each system, what it is used for and what this "
            f"{kind} can change in it. Say which one is the system of record.]",
            "",
            "| System | Used for |",
            "|---|---|",
        ]
        lines += [f"| {tool} | [TODO] |" for tool in node["tools"]]
    else:
        lines.append(
            f"[TODO: the systems this {kind} works in day to day, what each is "
            "used for, and which one is the system of record.]")
    lines.append("")
    if kind == "team":
        lines += [
            "[TODO: add the sections that differentiate this team from its "
            "siblings. Do not restate the department's context - it is loaded "
            "automatically.]",
            "",
        ]
    else:
        lines += [
            f"[TODO: add the sections specific to this {kind} after the four "
            "above - see CONTRIBUTING.md \"Department CLAUDE.md\".]",
            "",
        ]
    return "\n".join(lines)


def codeowners_line(node):
    path = f"/{node['rel']}/"
    owners = " ".join(node["owners"])
    return f"{path:<{OWNER_COLUMN}}{owners}".rstrip() + "\n"


_DEPT_LINE_RE = re.compile(r"^/departments/[^/]+/\s+@")
_TEAM_LINE_RE = re.compile(r"^/departments/.+/teams/[^/]+/\s+@")


def codeowners_update(text, nodes):
    """Insert the new lines after the existing department and team blocks.

    GitHub applies the last matching pattern, so a team line must stay below
    every department line. Department lines go after the last existing
    department line, team lines after the last existing team line (falling
    back to the end of the file when the block is not there yet).
    """
    lines = text.splitlines(keepends=True)
    present = {ln.split()[0] for ln in lines if ln.strip() and not ln.startswith("#")}

    new_dept = [codeowners_line(n) for n in nodes if n["kind"] == "department"]
    new_team = [codeowners_line(n) for n in nodes if n["kind"] != "department"]
    new_dept = [ln for ln in new_dept if ln.split()[0] not in present]
    new_team = [ln for ln in new_team if ln.split()[0] not in present]
    if not new_dept and not new_team:
        return text, []

    def last_index(pattern):
        found = None
        for i, ln in enumerate(lines):
            if pattern.match(ln):
                found = i
        return found

    dept_at = last_index(_DEPT_LINE_RE)
    team_at = last_index(_TEAM_LINE_RE)
    # Insert the lower block first so the upper block's index stays valid.
    if new_team:
        at = team_at if team_at is not None else dept_at
        if at is None:
            lines.extend(new_team)
        else:
            lines[at + 1:at + 1] = new_team
    if new_dept:
        if dept_at is None:
            lines.extend(new_dept)
        else:
            lines[dept_at + 1:dept_at + 1] = new_dept
    return "".join(lines), new_dept + new_team


# --- writing -----------------------------------------------------------------

def _git(workspace_root, *argv):
    try:
        return subprocess.run(
            ["git", "-C", str(workspace_root)] + list(argv),
            capture_output=True, text=True,
        )
    except FileNotFoundError:
        return None


def apply(spec, workspace_root, dry_run=False):
    """Write every planned file that does not exist yet.

    Returns (changes, created_paths): changes is a list of human-readable
    lines, created_paths the repo-relative paths written (empty on dry run).
    """
    workspace_root = Path(workspace_root)
    nodes = plan_nodes(spec)
    changes, created = [], []

    for node in nodes:
        folder = workspace_root / node["rel"]
        md = folder / "CLAUDE.md"
        keep = folder / "projects" / ".gitkeep"
        for target, content in ((md, claude_md(node)), (keep, "")):
            rel = target.relative_to(workspace_root).as_posix()
            if target.exists():
                changes.append(f"exists, left alone: {rel}")
                continue
            changes.append(f"create: {rel}")
            if not dry_run:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")
                created.append(rel)

    co_path = workspace_root / CODEOWNERS_REL
    if co_path.is_file():
        updated, added = codeowners_update(co_path.read_text(encoding="utf-8"), nodes)
        for ln in added:
            changes.append(f"CODEOWNERS: {ln.rstrip()}")
        if added and not dry_run:
            co_path.write_text(updated, encoding="utf-8")
            created.append(CODEOWNERS_REL)
        if not added:
            changes.append("CODEOWNERS: already lists every folder in the spec")
    else:
        changes.append(f"CODEOWNERS: {CODEOWNERS_REL} not found, no lines added")

    return changes, created


def _stage(workspace_root, rels):
    """Stage what we wrote so settings-sync and lint can see it.

    Both enumerate tracked files: an unstaged folder gets no security stamp
    and is invisible to the uniqueness check, which is exactly the state a
    caller must not be left in. Staging only - scaffold never commits.
    """
    if not rels:
        return
    res = _git(workspace_root, "add", "--", *rels)
    if res is None or res.returncode != 0:
        detail = "git not found" if res is None else res.stderr.strip()
        log.warn(f"scaffold: could not stage the new files ({detail}); "
                 "settings-sync and lint will not see them until you `git add`.")


def run(args):
    workspace_root = path_lib.require_workspace_root()
    spec_path = Path(args.spec)
    if not spec_path.is_file():
        raise SystemExit(f"scaffold: spec file not found: {spec_path}")
    try:
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise SystemExit(f"scaffold: spec is not valid JSON: {e}")

    problems = validate(spec, workspace_root)
    if problems:
        raise SpecError(problems)

    dry_run = bool(getattr(args, "dry_run", False))
    changes, created = apply(spec, workspace_root, dry_run=dry_run)

    if dry_run:
        log.header("scaffold --dry-run: planned changes")
        for line in changes:
            log.info(f"  {line}")
        log.info("")
        log.info("  then: settings-sync (stamp the security policy) and lint")
        return 0

    for line in changes:
        (log.change if line.startswith("create") or line.startswith("CODEOWNERS: /")
         else log.dim)(f"  {line}")

    _stage(workspace_root, created)

    log.step("settings-sync")
    sync_rc = settings_sync.run(_Args(check=False))
    stamps = [f"{n['rel']}/{settings_sync.SETTINGS_REL}" for n in plan_nodes(spec)]
    _stage(workspace_root, [s for s in stamps
                            if (workspace_root / s).is_file()])

    log.step("lint")
    lint_rc = lint.run(None)

    if sync_rc or lint_rc:
        log.error("scaffold: the folders were written but the checks are not "
                  "clean - fix the findings above before committing.")
        return 1
    log.ok("scaffold: done. Fill the [TODO] sections in each new CLAUDE.md.")
    return 0


class _Args:
    """settings_sync.run reads attributes off an argparse namespace."""

    def __init__(self, check=False):
        self.check = check
