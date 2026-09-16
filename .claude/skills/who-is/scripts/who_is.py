#!/usr/bin/env python3
"""Look up people in references/org-chart.json without loading the whole file.

The data is regenerated weekly: names, titles, departments, and reporting lines
come from the HR system, and "nickname" is the person's Slack display name, present
only where it differs from the formal name. The "manager" field is what encodes
the reporting tree.

It does not contain team or area. The HR system may keep both, as sub-department
and area, but its API exposes neither, so a team cannot be looked up by name -
resolve it through its lead's subtree with --tree instead.

Matching is accent- and case-insensitive and covers the nickname as well as the
formal name, so "Oscar Martinez" finds "Óscar Martínez" and "Hide" finds
"Hidetoshi Hasagawa". That is the point: the caller usually does not know the
correct spelling or which form the person goes by, which is why they are looking
it up.

Usage:
    who_is.py <query>            person lookup; partial names and nicknames work
    who_is.py --dept <name>      everyone in a department (partial match)
    who_is.py --tree <name>      reporting subtree beneath a person
    who_is.py --chain <name>     management chain from a person up to the top
    who_is.py --stats            departments and headcount
    who_is.py --import <csv>     rebuild the data file from an HR export
"""

import argparse
import csv
import datetime as dt
import json
import os
import signal
import sys
import unicodedata
from pathlib import Path

# Callers pipe this into head, and Python's default SIGPIPE handling turns the
# closed pipe into a BrokenPipeError traceback. Restore the shell default so the
# script just stops when the reader goes away.
try:
    signal.signal(signal.SIGPIPE, signal.SIG_DFL)
except (AttributeError, ValueError):  # no SIGPIPE on Windows
    pass

# The data lives beside the script inside the skill, so the pair travels as one
# unit - including when the Cloud bootstrap copies .claude/skills/ to the root.
DATA_PATH = Path(__file__).resolve().parent.parent / "references" / "org-chart.json"


def data_path() -> Path:
    """Where the data file lives, whether or not it exists yet."""
    return Path(os.environ.get("ORG_CHART_PATH") or DATA_PATH)


def find_data() -> Path:
    candidate = data_path()
    if candidate.is_file():
        return candidate
    sys.exit(
        f"Org chart data not found at {candidate}.\n"
        "The file is written by the org chart sync, or by hand with\n"
        "`who_is.py --import people.csv` from an HR export. If this is a fresh\n"
        "checkout, the sync's pull request may not have merged yet."
    )


# Letters that NFKD does not decompose, because the stroke or slash is part of
# the letter rather than a combining accent. Without this, "Michal Olender" fails
# to match "Michał Olender".
TRANSLIT = str.maketrans({
    "ł": "l", "Ł": "L", "ø": "o", "Ø": "O", "đ": "d", "Đ": "D",
    "ı": "i", "ħ": "h", "ŧ": "t", "ŋ": "n", "ð": "d", "þ": "th",
    "ß": "ss", "æ": "ae", "Æ": "AE", "œ": "oe", "Œ": "OE",
})


def fold(text: str) -> str:
    """Strip accents and case so 'Müller' and 'Muller' compare equal."""
    if not text:
        return ""
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return stripped.translate(TRANSLIT).casefold()


# --- import ------------------------------------------------------------------
#
# The data file is normally written by a sync. `--import` is the other way in:
# a CSV exported from the HR system, for a company that has no sync yet or is
# populating the file for the first time. It rewrites the file whole - the
# export is the source, so a merge would silently keep people who have left.

REQUIRED_COLUMNS = ("name", "title", "department", "manager")
OPTIONAL_COLUMNS = ("nickname", "team")

NOTE = (
    "Generated file, do not hand-edit; the next sync or import overwrites it. "
    "Source: the HR system (name, job title, department, manager) and the chat "
    "tool (nickname from display name, slack_team from the team column, both "
    "best effort). Populate it with `who_is.py --import people.csv` or a "
    "scheduled sync that opens a pull request when the data changes; "
    "\"updated\" is the date of the last data change, not the last run. Fix "
    "data in the source systems, not here. Query it with the who-is skill "
    "rather than reading it whole. Directory data: internal workspace only, "
    "never publish."
)


def read_csv(path: Path):
    """Rows as dicts with stripped values, plus the header list.

    utf-8-sig: HR exports opened in Excel once carry a BOM, which would
    otherwise become part of the first column's name and make `name` missing.
    """
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        # Strip the header too: an export round-tripped through a spreadsheet
        # comes back with padded column names, which would read as missing.
        header = [(h or "").strip() for h in reader.fieldnames or []]
        rows = []
        for row in reader:
            rows.append({(k or "").strip(): (v or "").strip()
                         for k, v in row.items() if k is not None})
    return header, rows


def build_people(rows):
    """CSV rows -> the person records the data file stores.

    A nickname equal to the formal name carries no information - the field
    exists to say "this person goes by something else" - so it is dropped,
    folded, which also drops a chat display name that differs only in accents
    or case.
    """
    people = []
    for row in rows:
        person = {"name": row["name"]}
        nickname = row.get("nickname", "")
        if nickname and fold(nickname) != fold(row["name"]):
            person["nickname"] = nickname
        for key in ("title", "department", "manager"):
            if row.get(key):
                person[key] = row[key]
        if row.get("team"):
            person["slack_team"] = row["team"]
        people.append(person)
    return people


def validate_rows(header, rows):
    """Every reason the import cannot be trusted, in one list.

    Reporting them one at a time would mean one export, one fix, one re-run
    per problem; an HR export with three bad manager cells has three.
    """
    problems = []
    missing = [c for c in REQUIRED_COLUMNS if c not in header]
    if missing:
        problems.append(
            f"missing required column(s): {', '.join(missing)} "
            f"(expected {', '.join(REQUIRED_COLUMNS)}; "
            f"{', '.join(OPTIONAL_COLUMNS)} are optional)")
        return problems
    if not rows:
        problems.append("the file has a header but no rows")
        return problems

    names, seen = [], {}
    for i, row in enumerate(rows, 2):  # row 1 is the header
        name = row.get("name", "")
        if not name:
            problems.append(f"row {i}: name is empty")
            continue
        if name in seen:
            problems.append(
                f"row {i}: duplicate name {name!r} (already on row {seen[name]}) - "
                "the reporting tree is keyed on the name, so it must be unique")
        else:
            seen[name] = i
        names.append(name)

    known = set(names)
    folded = {fold(n): n for n in names}
    for i, row in enumerate(rows, 2):
        manager = row.get("manager", "")
        if not manager or manager in known:
            continue
        near = folded.get(fold(manager))
        hint = f" - did you mean {near!r}?" if near else ""
        problems.append(
            f"row {i}: manager {manager!r} is not a name in this file{hint}")

    if names and not any(not row.get("manager") for row in rows if row.get("name")):
        problems.append(
            "no root: every row has a manager, so the reporting tree has no top. "
            "Leave the manager cell empty for the person at the top.")
    return problems


def import_csv(csv_path, out_path):
    """Validate and rewrite the data file. Writes nothing on any problem."""
    path = Path(csv_path)
    if not path.is_file():
        sys.exit(f"CSV not found: {path}")
    try:
        header, rows = read_csv(path)
    except (OSError, UnicodeDecodeError, csv.Error) as e:
        sys.exit(f"Could not read {path}: {e}")

    problems = validate_rows(header, rows)
    if problems:
        sys.exit(
            f"{path.name}: {len(problems)} problem(s), nothing was written:\n"
            + "\n".join(f"  - {p}" for p in problems)
            + "\n\nFix them in the export (or in the HR system and re-export) "
              "and run the import again."
        )

    people = build_people(rows)
    data = {
        "note": NOTE,
        "source": f"import:{path.name}",
        "updated": dt.date.today().isoformat(),
        "count": len(people),
        "people": people,
    }
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    roots = [p["name"] for p in people if not p.get("manager")]
    depts = {p.get("department") for p in people if p.get("department")}
    print(f"Imported {len(people)} people from {path.name} into {out}.")
    print(f"  {len(depts)} department(s), {len(roots)} root(s): "
          f"{', '.join(sorted(roots)[:3])}"
          + (" ..." if len(roots) > 3 else ""))
    print("  The card references/org-chart.md carries this data's maintenance")
    print("  header: set its `owner` to whoever runs the import by hand.")
    print("  Commit the result through a pull request like any other change.")


def load():
    data = json.loads(find_data().read_text(encoding="utf-8"))
    people = data.get("people", [])
    by_name = {p["name"]: p for p in people}
    reports = {}
    for p in people:
        mgr = p.get("manager")
        if mgr and mgr in by_name:
            reports.setdefault(mgr, []).append(p)
    for kids in reports.values():
        kids.sort(key=lambda p: p["name"])
    return data, people, by_name, reports


def label(p) -> str:
    """Name, plus only the part of the nickname that is not already in the name.

    Chat display names often restate the surname - "Barbora Čelechovská" signs as
    "Bára Čelechovská" - and echoing it reads as a duplication bug. Comparison is
    folded, so "Vlada Dusek" drops against "Vladimír Dušek". The stored value keeps
    the full chat string; only the rendering is trimmed.
    """
    nick = p.get("nickname")
    if not nick:
        return p["name"]
    in_name = {t for t in fold(p["name"]).split() if t}
    kept = " ".join(t for t in nick.split() if fold(t) not in in_name).strip()
    return f"{p['name']} ({kept or nick})"


def describe(p) -> str:
    """Compact role line, used in every list, tree, and candidate set.

    Shape: "<title> @ <team> - <department>", where the department is appended
    only when it differs from the team. Both are shown because they answer
    different questions and often disagree: Josef Jetmar's department is
    "Web Automation Engineering" while his team is "Pro-Services Pod B". Where no
    chat team exists the department takes the "@" slot, so the line never ends
    up empty on the right.
    """
    title = p.get("title") or "Unknown role"
    team = p.get("slack_team")
    dept = p.get("department")
    unit = team or dept
    out = f"{title} @ {unit}" if unit else title
    if team and dept and fold(team) != fold(dept):
        out += f" - {dept}"
    return out


def find_people(people, query):
    """Three tiers, most precise first.

    The token tier matters more than it looks: a caller who types a nickname plus
    a real surname ("Jim Halpert" for "James Halpert") misses both the exact and
    substring tiers, but still matches on the surname token.
    """
    q = fold(query)

    def haystacks(p):
        """Formal name and nickname are both valid ways to refer to someone."""
        return [fold(p["name"]), fold(p.get("nickname") or "")]

    exact = [p for p in people if q in [h for h in haystacks(p) if h]]
    substring = [p for p in people if any(h and q in h for h in haystacks(p))]

    # An exact hit wins, but never silently. Three Josefs go by a Pepa variant and
    # only Válek is exactly "Pepa"; returning him alone with no signal is the one
    # failure a name-verification tool must not have.
    if exact:
        others = [p for p in substring if p not in exact]
        return exact, others

    if substring:
        return substring, []

    q_tokens = [t for t in q.split() if t]
    if not q_tokens:
        return [], []
    scored = []
    for p in people:
        name_tokens = fold(p["name"]).split() + fold(p.get("nickname") or "").split()
        hits = sum(
            1 for qt in q_tokens
            if any(nt.startswith(qt) or qt.startswith(nt) for nt in name_tokens)
        )
        if hits:
            scored.append((hits, p))
    if not scored:
        return [], []
    best = max(h for h, _ in scored)
    return [p for h, p in scored if h == best], []


def chain_of(p, by_name):
    """Walk up the management chain, guarding against a cycle in the data."""
    chain, seen, cur = [], set(), p
    while cur:
        if cur["name"] in seen:
            break
        seen.add(cur["name"])
        chain.append(cur)
        cur = by_name.get(cur.get("manager") or "")
    return list(reversed(chain))


def print_card(p, by_name, reports):
    print(label(p))
    print(f"  Title:      {p.get('title') or 'Unknown role'}")
    print(f"  Department: {p.get('department') or '-'}")
    if p.get("slack_team"):
        print(f"  Team:       {p['slack_team']} (from their chat profile)")

    mgr = by_name.get(p.get("manager") or "")
    if mgr:
        print(f"  Manager:    {label(mgr)} - {describe(mgr)}")
    elif p.get("manager"):
        print(f"  Manager:    {p['manager']} (not in the directory)")
    else:
        print("  Manager:    - (top of the chart)")

    kids = reports.get(p["name"], [])
    if kids:
        print(f"  Reports ({len(kids)}):")
        for k in kids:
            print(f"    - {label(k)} - {describe(k)}")
        total = subtree_size(p["name"], reports)
        if total != len(kids):
            print(f"  Total beneath: {total}")
    else:
        print("  Reports:    none")

    chain = chain_of(p, by_name)
    if len(chain) > 1:
        print("  Chain:      " + " > ".join(label(c) for c in chain))


GROUP_LIMIT = 40


def print_group(heading, hits):
    shown = sorted(hits, key=lambda x: x["name"])[:GROUP_LIMIT]
    print(f"{heading} - {len(hits)} people:")
    for p in shown:
        print(f"  - {label(p)} - {describe(p)}")
    if len(hits) > len(shown):
        print(f"  ... and {len(hits) - len(shown)} more")


def field_hits(people, query, field):
    q = fold(query)
    return [p for p in people if q in fold(p.get(field) or "")]


def subtree_size(name, reports):
    return sum(1 + subtree_size(k["name"], reports) for k in reports.get(name, []))


TREE_LIMIT = 200


def print_tree(name, reports, depth=0, limit=TREE_LIMIT):
    for k in reports.get(name, []):
        if limit <= 0:
            return limit
        print("  " * depth + f"- {label(k)} - {describe(k)}")
        limit = print_tree(k["name"], reports, depth + 1, limit - 1)
    return limit


def main():
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("query", nargs="*", help="person name, full or partial")
    ap.add_argument("--dept", help="list everyone in a department")
    ap.add_argument("--tree", help="print the reporting subtree beneath a person")
    ap.add_argument("--chain", help="print the management chain above a person")
    ap.add_argument("--team", help="everyone whose chat team matches (best effort)")
    ap.add_argument("--title", help="everyone whose job title matches")
    ap.add_argument("--stats", action="store_true", help="departments and headcount")
    ap.add_argument("--import", dest="import_csv", metavar="CSV",
                    help="rebuild the data file from an HR export (columns: "
                         "name, title, department, manager, and optionally "
                         "nickname, team)")
    args = ap.parse_args()

    # Import first: it is the one mode that does not read the data file, and
    # the one that works when the file is still an empty placeholder.
    if args.import_csv:
        import_csv(args.import_csv, data_path())
        return

    data, people, by_name, reports = load()

    # The committed file starts as an empty placeholder so the skill can land
    # before the first sync. Say so plainly: otherwise every query returns
    # "no match" and reads like the person does not exist.
    if not people:
        print("The org chart has not been synced yet - the data file is an empty placeholder.")
        print("Fill it with `who_is.py --import people.csv` from an HR export, or with")
        print("the company's sync; nothing can be looked up until one of those lands.")
        return

    stamp = f"{data.get('count', len(people))} people, updated {data.get('updated', 'unknown')}"

    if args.stats:
        counts = {}
        for p in people:
            counts[p.get("department") or "(none)"] = counts.get(p.get("department") or "(none)", 0) + 1
        print(stamp)
        for dept, n in sorted(counts.items(), key=lambda kv: -kv[1]):
            print(f"  {n:>3}  {dept}")
        return

    if args.title:
        hits = field_hits(people, args.title, "title")
        if not hits:
            print(f"No job title matching '{args.title}'.")
            return
        print_group(f'Job title containing "{args.title}"', hits)
        return

    if args.team:
        hits = field_hits(people, args.team, "slack_team")
        if not hits:
            teams = sorted({p["slack_team"] for p in people if p.get("slack_team")})
            print(f"No chat team matching '{args.team}'. Known teams:")
            for t in teams:
                print(f"  - {t}")
            return
        teams = sorted({p.get("slack_team") for p in hits if p.get("slack_team")})
        print_group(f'Chat team "{", ".join(teams)}"', hits)
        print("\nBest effort: teams come from free-text Slack titles, not the HR system.")
        return

    if args.dept:
        hits = field_hits(people, args.dept, "department")
        if not hits:
            depts = sorted({p.get("department") or "(none)" for p in people})
            print(f"No department matching '{args.dept}'. Known departments:")
            for d in depts:
                print(f"  - {d}")
            return
        depts = sorted({p.get("department") for p in hits if p.get("department")})
        print_group(f'Department "{", ".join(depts) or args.dept}"', hits)
        return

    target = args.tree or args.chain or " ".join(args.query)
    if not target:
        ap.print_help()
        return

    hits, also = find_people(people, target)
    if not hits:
        # Not a person. Search every other field and report all of them: a bare
        # query like "data" can legitimately be a department and a chat team at
        # once, and showing only the first would hide the rest.
        def values(hits, field):
            return ", ".join(sorted({p[field] for p in hits if p.get(field)}))

        dept = field_hits(people, target, "department")
        team = field_hits(people, target, "slack_team")
        title = field_hits(people, target, "title")
        groups = []
        if dept:
            groups.append(("department", f'Department: {values(dept, "department")}', dept))
        if team:
            groups.append(("Chat team", f'Chat team: {values(team, "slack_team")}', team))
        if title:
            groups.append(("job title", f'Job title matching "{target}"', title))

        if groups:
            where = ", ".join(w for w, _, _ in groups[:-1])
            where = f"{where} and {groups[-1][0]}" if where else groups[-1][0]
            print(f"'{target}' is not a person. Matched on {where}.\n")
            for i, (_, heading, hits) in enumerate(groups):
                if i:
                    print()
                print_group(heading, hits)
            if title:
                print("\nA team lead usually carries the team name in their title, so --tree")
                print("on a name above gives that whole team.")
            return

        print(f"No match for '{target}' as a person, department, chat team, or job "
              f"title ({stamp}).")
        print("Not necessarily an error: could be a contractor, a new joiner ahead of")
        print("the weekly sync, someone outside the workspace, or a team or area - neither is")
        print("in the data. Try --stats for the department list, or --tree with a lead's")
        print("name.")
        return
    if len(hits) > 1:
        print(f"{len(hits)} matches for '{target}':")
        for p in sorted(hits, key=lambda p: p["name"]):
            print(f"  - {label(p)} - {describe(p)}")
        return

    p = hits[0]
    if args.tree:
        print(f"{label(p)} - {describe(p)}")
        total = subtree_size(p["name"], reports)
        print(f"({total} people beneath)")
        remaining = print_tree(p["name"], reports, 1)
        if remaining <= 0:
            print(f"\n... output stopped at {TREE_LIMIT} lines of {total}. Narrow the")
            print("query with --tree on someone further down.")
    elif args.chain:
        for i, c in enumerate(chain_of(p, by_name)):
            print("  " * i + f"- {label(c)} - {describe(c)}")
    else:
        print_card(p, by_name, reports)
        if also:
            print()
            print(f"  Careful: {len(also)} other person(s) also match '{target}'. This is an")
            print("  exact hit, but confirm it is who you meant:")
            for o in sorted(also, key=lambda x: x["name"]):
                print(f"    - {label(o)} - {describe(o)}")


if __name__ == "__main__":
    main()
