---
name: who-is
description: >
  Look up who someone at the company is, what they do, and where they sit in
  the org. Use when you need to verify the spelling of a colleague's name, find
  out someone's job title, department, manager, or direct reports, work out who
  leads or belongs to a team, or resolve a partial, misspelled, or nickname
  reference to a real person. Also use before writing a colleague's name into
  any text. Queries one person at a time from the skill's own data file instead
  of loading the whole directory.
---

# Who is

`references/org-chart.json`, beside this file, holds everyone in the company,
regenerated from the HR system and the chat tool. Even a mid-size company is a
few hundred records, so **do not read it directly** - query it with the script
and you spend a few hundred tokens instead of several thousand.

If a query reports that the chart has no people yet, the data file in this
checkout is an empty placeholder: nothing has populated it. Say so rather than
reporting the person as unverified. Populate it with `--import` (below) or the
company's sync process. Its maintenance header (sources, owner, cadence) is the
sibling card `references/org-chart.md`.

```bash
python3 .claude/skills/who-is/scripts/who_is.py "Jane Doe"          # person card
python3 .claude/skills/who-is/scripts/who_is.py --dept "sales"      # everyone in a department
python3 .claude/skills/who-is/scripts/who_is.py --tree "Jane"       # everyone beneath a person
python3 .claude/skills/who-is/scripts/who_is.py --chain "Sam"       # management chain upward
python3 .claude/skills/who-is/scripts/who_is.py --team "Scranton"   # everyone in a chat team
python3 .claude/skills/who-is/scripts/who_is.py --title "manager"   # everyone whose title matches
python3 .claude/skills/who-is/scripts/who_is.py --stats             # departments and headcount
```

## What is in the data

| Field | Source |
|---|---|
| `name` | HR system. The formal name, as configured there. |
| `nickname` | Chat display name. Stored only when it differs from the formal name. |
| `title`, `department`, `manager` | HR system. |
| `slack_team` | Best-effort team signal from the chat profile, for example the text after "@" in a profile title such as `Sales Representative @ Scranton Sales`. |

`manager` is what makes the reporting tree: every other view (`--tree`,
`--chain`) is derived from it rather than stored. A record without a manager is
a root of the tree, normally the CEO.

No nickname means the person's chat display name is already their real name,
not that they do not have one.

## Teams, and why they are awkward

`department` is usually a level too coarse to be a team. HR systems record the
function (Sales, Accounting) and often put a whole branch or region into one
value that nobody uses in conversation. **Never present `department` as
someone's team.**

Many HR systems record the real team as a sub-department that their export or
API does not expose. Two partial answers exist instead:

```bash
python3 .claude/skills/who-is/scripts/who_is.py --team "Scranton Sales"   # chat team
python3 .claude/skills/who-is/scripts/who_is.py --tree "Jane Doe"        # = the team she leads
```

`slack_team` is the better answer where it exists, because people maintain it
themselves. It is also free text, so values are not standardized. Treat it as a
hint, say where it came from, and fall back to `--tree` on a team lead when it
is missing.

## Matching

Accent- and case-insensitive, across both the formal name and the nickname,
with fallbacks to partial and surname-token matches. So `"Jose Garcia"` finds
José García, `"Michal Olender"` finds Michał Olender, and a nickname finds the
person who uses it. Type the name as you have it and let the script do the
work.

Matching runs in tiers, most precise first: exact on either form, then
substring, then token overlap. An exact match wins outright, so a nickname that
exactly matches one person returns that person even when other people's names
contain the same letters.

When a query is genuinely ambiguous the script lists candidates rather than
guessing. A bare first name shared by two people returns both. Adding a surname
disambiguates through the token tier.

An exact hit that is *nearly* ambiguous still warns: if two other people go by
a variant of the same nickname, the script returns the exact match and then
names the others. Read the warning before using the answer; the right move is
usually to ask which one was meant.

Output shows both name forms when they differ: `Jane Doe (JD)`. Only the part
of the nickname that is not already in the name is shown, so a person signing
with a shortened first name and the same surname renders as
`Barbara Smith (Barb)`, not with a duplicated surname. The stored value keeps
the full chat string and remains searchable.

List lines follow one shape:

```
<name> (<nickname>) - <title> @ <team> - <department>
```

The nickname appears only when there is one, and the department only when it
differs from the team. Both team and department are shown because they answer
different questions and often disagree. Where no chat team exists, the
department takes the `@` slot.

`--dept` works for the departments that are present; run `--stats` to see the
list of them with headcounts.

A bare query does not need the right flag. If it matches no person, the script
searches department, chat team, and job title, and reports every one that hit -
not just the first, since a word can legitimately be a department and a team at
once. Abbreviations are not in the data; expand them first.

Every field is searchable: name and nickname through a bare query, and
`department`, `slack_team`, and `title` through both a bare query and their own
flag. `manager` is searched through `--tree` and `--chain`.

The job title match is what makes team names findable when `slack_team` is
missing: a team lead usually carries the team name in their title, so the query
lands on the lead and `--tree` on that name gives the whole team.

## Using what you get back

- **Address people by their nickname where there is one.** That is what the
  field is for. Use the formal name only where a formal name belongs, such as a
  contract or a review document.
- **A name typed without diacritics is not a mistake.** People routinely type on
  a keyboard that lacks them. Never flag them, and never rewrite them in someone
  else's text. Use the full form when composing new text yourself.
- **No match is not proof of an error.** It may be a contractor, a new joiner
  ahead of the next sync, someone outside the company, or a nickname nobody has
  set in the chat tool. Say the name is unverified rather than silently
  rewriting it.

## How the data gets here

The file is generated. Its `note` field names the source systems and the sync
date; `updated` is the date of the last data *change*. Two ways to keep it
current:

- **Import an export from the HR system.** `who_is.py --import people.csv`
  reads a CSV with the columns `name, title, department, manager, nickname,
  team` (the last two optional) and rewrites the data file. Commit the result
  through a pull request like any other change.
- **Automate it.** A scheduled job that pulls from the HR system and the chat
  tool, compares against the committed copy ignoring the timestamp, and opens a
  pull request when something changed. Keep `main` protected so nothing lands
  unreviewed.

Wrong data belongs fixed in the source system, or in the chat tool for a
nickname or team. Edits to this file are overwritten by the next sync.

This is directory data - name, title, department, manager, chat handle - and the
data-sensitivity rule allows it in the internal workspace only. Do not publish
it or copy it into anything that leaves the company.
