---
sources:
  - "CONTRIBUTING.md: the conventions every answer here has to satisfy"
  - "README.md: the surfaces and personal-context setup the last questions refer to"
owner: Gabe Lewis
edit: here
review_every: 180d
---
# Setup interview

The org-layer questions for step 3 of `SKILL.md`, in order, with wording. Ask
one at a time. Use AskUserQuestion wherever the options are listed; everything
else is free text. Carry the answers into the spec and the files step 6 writes.

Two habits that matter more than the wording:

- **Offer a default and say what it costs.** "Most companies start with one
  `CLAUDE.md` per department" moves faster than an open question.
- **`[TODO]` is a valid answer.** Every question here can be answered later by
  editing a file. Never invent a plausible answer to keep the flow going, and
  never let a question block the run.

## 1. Departments

> Here are the departments your website and job postings suggest, with how much
> evidence sits behind each one. Which of these are real departments in your
> company, what is missing, and what should each one be called? Folder names are
> kebab-case, so "Customer Success" becomes `customer-success`.

Show the seeded list as a table: proposed name, evidence, count. A node backed
by two job titles is a guess; one backed by twenty is a fact. Say which is
which rather than presenting them alike.

Say what the list is built on before they answer it: a bounded sample of pages
and profiles, not a directory. **Ask what is missing before asking what is
wrong** - a department with no public footprint (legal, finance, and internal
IT are the usual ones) will simply not be in the seeded list, and a user
reading a confident table tends to edit it rather than add to it.

Rules to apply to the answer, and to say out loud when they bite:

- Kebab-case, lowercase, no spaces.
- Every folder name that contains a `CLAUDE.md` must be **globally unique**
  across the workspace - two teams called `content` in different departments
  cannot both exist. Cloud team resolution keys on the basename.
- A department the company does not have yet is not scaffolded "for later". An
  empty folder is context Claude loads and learns nothing from.

## 2. Teams

Per department:

> Does <department> have teams that work differently enough from each other to
> need their own context - different processes, tools, and metrics? Most
> departments do not.

Options: **No teams** (default) / **Teams, one shared context** / **Teams, each
with its own `CLAUDE.md`**.

The middle option is the common one: teams exist on the org chart but share the
department's processes, so they get no folder. Only the third option adds a
level. When the user is unsure, cite CONTRIBUTING "Knowledge hierarchy depth":
more levels mean more context loaded at once and more chances for inheritance
confusion, and the fix later is one `/add-team` run.

## 3. Owners

> Who reviews changes to <department>'s folder? I need a GitHub handle - it
> goes in CODEOWNERS, which routes the review.

Then once:

> And a default handle for the workspace as a whole - the reviewer for the root
> `CLAUDE.md`, the rules, and the tooling. A GitHub team like
> `@your-org/workspace-owners` works too.

Say plainly: a handle that has no write access on the repo is silently ignored
by GitHub, and a `@TODO-...` placeholder is a valid answer that is also
silently ignored, so an unfinished line is safe to land but does nothing.

## 4. Tools per department

> Which systems does <department> work in day to day? Name the ones someone
> would have to know about to do the work - the CRM, the ticketing system, the
> warehouse system, the data warehouse.

Tools land in the department's "Tools and systems" section as a table with a
`[TODO]` against each, not as a finished description. If any tool has an MCP
server the company wants Claude to reach, note it: it becomes part of the
proposed `.claude/settings.json` diff in step 6 (j), never an edit.

## 5. Terminology and product names

> What does your company call its products, and what do people get wrong? I am
> after the pairs: write this, never that. Capitalization, internal shorthand
> that must not reach a client, a word for your customers that you do not use.

Also ask:

> Is there a word you use for the people you sell to - client, customer,
> member, partner - and one you avoid?

These become `.claude/rules/style-core.md`. That file is always loaded, so keep
it to the rules that actually get broken. A full style guide, if the company
has one, is a context file loaded on demand, not a rule.

## 6. Locale

Ask as one question with options:

| Question | Options |
|---|---|
| Spelling | US English (organize, color) / UK English (organise, colour) |
| Currency | The symbol and how amounts are written: `$1,240`, `€1.240`, `1 240 Kč` |
| Dates in prose | `August 31, 2026` / `31 August 2026` |

Data files and frontmatter use ISO 8601 (`2026-08-31`) whatever the answer -
that is not a preference, it is what the tooling parses.

## 7. Industry sensitivity categories

> `.claude/rules/data-sensitivity.md` already blocks PII, credentials, and
> compensation. What does your industry add? Health information, client
> identities, material non-public information, export-controlled detail,
> anything under an NDA by default?

Append the confirmed categories under the existing headings. Do not rewrite the
categories that are already there.

## 8. People (step 4 of the skill)

> Do you have an HR export handy - a CSV with name, title, department, and
> manager? I can load it into the `who-is` skill so Claude can check who someone
> is before writing their name down. Optional, and just as easy later.

If yes, ask for the path and mention the optional `nickname` and `team`
columns. If no, the data file becomes an empty placeholder and the skill says
so when queried.

Say once: this is internal directory data. The data-sensitivity rule allows it
in the workspace and nowhere else - never in published content.
