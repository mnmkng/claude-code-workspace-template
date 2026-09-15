# Contributing to the knowledge workspace

This file defines the conventions for adding and maintaining content in this workspace. Both humans and Claude should follow these rules. The `review-workspace` agent audits against these conventions.

## The example company

The content in this template is an example company - Dunder Mifflin, a regional paper distributor - so a reader can see what a finished workspace looks like before running `/setup-workspace` replaces it with their own. It is written **played straight**: every file reads the way a real regional paper distributor would write it for its own Claude workspace. Terse, structured, factual.

The rule for anyone editing it: **if a line would not appear in a real company's `CLAUDE.md`, it does not appear here.** No jokes, no winks, no quotes from the show in agent context. Where the example is funny, it is funny because a reader recognizes the company and because a terminology rule is stated as plain fact, not because the file is performing.

Two constraints that follow from it:

- **Fictional entities only.** Competitors are the category "big-box office retailers" plus named fictional ones. Clients are fictional counties, school districts, and hospital systems. Never name a real company, in any file.
- **Conventions apply in full.** The example content is held to every rule in this file - maintenance headers, the standard `CLAUDE.md` sections, the context index, sentence-case headings, metrics with an "as of" date. An example that cuts corners teaches the corners.

## Directory structure conventions

### Top-level layout

The repo root must contain:
- `CLAUDE.md` - Company-wide context (always loaded)
- `CLAUDE.local.example.md` - Personal preferences template (copy to the gitignored `CLAUDE.local.md`)
- `CONTRIBUTING.md` - This file: workspace conventions
- `README.md` - Setup guide
- `.gitignore`
- `.claude/` - Global Claude Code configuration, skills and agents
- `departments/` - All department and team folders
- `context/` - Cross-functional knowledge files
- `scripts/` - Workspace tooling scripts
- `tools/` - Python tooling: the bootstrap (`tools/bootstrap/`) and the maintenance checker (`tools/maintenance/`)
- `docs-for-humans/` - Human-only docs and step-by-step tutorials for workspace-wide workflows (teams add their own `docs-for-humans/` for team-specific human docs)

Two more files may sit at the root but are personal and gitignored, never tracked: `CLAUDE.local.md` (your preferences) and `.mcp.json` (your MCP server configuration, see the MCP section below).

### Department and team folders

All departments live under `departments/` using **kebab-case**:
- `departments/sales/`, `departments/marketing/`, `departments/dev-rel/`, `departments/legal/`, `departments/professional-services/`, `departments/customer-success/`

Departments with sub-teams contain a `teams/` subfolder:
- `departments/customer-success/teams/expansion/`, `departments/customer-success/teams/rev-ops/`

A team that itself has sub-teams nests them the same way, under its own `teams/` subfolder - e.g. `departments/customer-success/teams/scaled-customer-experience/teams/adoption/`. Sub-teams are never bare subfolders of a team.

Every department and team folder uses the same canonical layout. Only `CLAUDE.md` is required; everything else is optional and added when the team needs it. Nothing outside this list belongs in a team space:

```
departments/<dept>/              # or departments/<dept>/teams/<team>/
├── CLAUDE.md                    # REQUIRED. Agent context: structure, metrics, processes, tools, context index
├── README.md                    # Optional. Human orientation for this space (not loaded by Claude)
├── context/                     # Optional. Team context: .md, plus .html/.csv/.json data. Indexed by CLAUDE.md
├── docs-for-humans/             # Optional. Human-only docs: team guides, repo/tooling how-tos (not agent context)
├── .claude/                     # Optional. Per-level Claude config (composed in Cloud - see below)
│   ├── agents/                  # Optional. Team agents (one .md per agent)
│   ├── commands/                # Optional. Team slash-commands (one .md per command)
│   ├── rules/                   # Optional. Team rules (.md; may be path-scoped)
│   ├── hooks/                   # Optional. Team hook scripts (.sh; hook names must be globally unique)
│   ├── skills/                  # Optional. Team skills (scoped to this directory)
│   ├── settings.json            # GENERATED security policy (settings-sync) - never hand-edited (see below)
│   └── settings.local.json      # Personal local overrides only - gitignored, never committed (see below)
└── projects/                    # Optional. Ephemeral working files (gitignored)
```

**No bespoke content folders.** Don't invent top-level folders inside a team space (`plays/`, `processes/`, `execute-profiles/`, and the like). Every kind of content already has a home in the layout above - see [Agent context vs human docs](#agent-context-vs-human-docs) below. If a piece of content doesn't seem to fit, that's a signal to rethink the content, not to add a folder.

The root `.gitignore` **enforces** this layout as a default-deny allowlist: everything under `departments/` is ignored unless it matches the canonical structure above, so out-of-structure files (stray folders, data dumps, identity tables, personal notes) are dropped automatically and never need a per-file `.gitignore` entry. Files committed before the rule are grandfathered - it only blocks *new* out-of-structure files. Two consequences worth knowing: `CLAUDE.md` is recognized only at a department or team root (never inside `context/`, `docs-for-humans/`, etc.), and any local or sensitive file must carry a `.local.` marker in its name or live in `projects/` (both gitignored) to stay out of git.

### Agent context vs human docs

The repo is primarily **agent context** - files Claude loads to do work. Keep two categories cleanly separated:

- **Agent context** (the default, and most of the repo): consumed by Claude via `CLAUDE.md`, the context index, `.claude/skills/`, or `.claude/rules/`. Terse, structured, written for progressive disclosure.
- **Human docs**: read by people, never loaded into an agent's context. They live in exactly two places - a team `README.md` (orientation) and a `docs-for-humans/` folder (team guides, repo/tooling tutorials, onboarding). Keep them out of `CLAUDE.md` and `context/` so they don't bloat what Claude loads.

**Every agent-context file must be reachable.** A file counts as agent context only if some entry point loads it - it is linked, or transitively linked, from a `CLAUDE.md` (directly or through its context index), a skill, or a rule. A committed file that nothing references is an orphan: wire it in or delete it. Human docs (`README.md`, `docs-for-humans/`) are exempt - they aren't agent context and aren't expected to be reachable from one.

`CLAUDE.md` is the agent's entry point; `README.md` is the human's. Don't copy one into the other - link instead.

`docs-for-humans/` is for documentation about *working in this space* - how to use the team's skills, how to run a workflow, onboarding notes. It is **not** a home for domain knowledge or operating procedures. Durable domain knowledge an agent needs is agent context (`CLAUDE.md` / `context/`).

**Content usable by both humans and agents** (playbooks, SOPs, taxonomies, trackers) is routed by **edit locus** - where the owning team's edits actually land today - not by content category. Three patterns:

1. **Repo is SSOT.** The owning team works through agent sessions in this repo, so edits land in git. The content lives in `context/` (or a skill's references) and is indexed like any agent context. External copies (e.g. Notion pages) are reduced to banners pointing here. Examples: a legal team's contract playbook, a services team's renewal playbook, a sales team's deal taxonomy.
2. **External SSOT + pointer.** Humans edit in an external system (e.g. Notion) and agents need the content rarely. Agent context keeps a link, a fetch instruction, and an "as of" stamp - never a copy. Unmarked copies drift: a committed copy and its source diverge within weeks, and the committed one goes stale silently.
3. **External SSOT + copy.** Humans edit externally but agents need the content often enough that fetching every time is wasteful, so a copy lives in the repo and its [maintenance header](#maintenance-header) says `edit: upstream`. An agent that spots an error proposes the fix in the external source and re-syncs; it never patches the copy, otherwise copies become forks. The copy may be verbatim or an agent-mediated distillation: Notion and this repo are not 1:1, so one repo file can distill several pages and vice versa. Each copy brings its own sync - a sync job, an Action, an export agent, or a person re-pasting on change - and its `sources` entry names it.

**Sensitivity override**, on top of all three patterns: named counterparties, deal specifics, and anything failing `.claude/rules/data-sensitivity.md` never enters the repo, even via a copy. The repo holds the anonymized position; the external system holds specifics.

This rule is transitional: placement is expected to migrate toward repo-SSOT as teams adopt agent workflows. Keying on where edits land lets that happen team by team, without rewriting this rule.

### Maintenance header

Every context file is compiled from somewhere - Notion, the HR system, the data warehouse, a Slack channel, a colleague's head - and some are verbatim copies that must be fixed at the source. A reader, human or agent, needs the same facts at the top of every file: where it comes from, who answers for it, whether edits belong here or upstream, and when it was last checked. The maintenance header is YAML frontmatter that states them:

```yaml
---
sources:
  - "Notion: Sales playbook 2026, https://www.notion.so/..."
  - "HubSpot: closed-lost reason field"
owner: Angela Martin
edit: here
review_every: 90d
verified_at: 2026-09-10
---
# File title
```

#### Fields

| Field | Status | What it says |
|---|---|---|
| `edit` | required | Where a correction goes. `here`: the file is authored, edits land in git. `upstream`: a process produces the file from its sources, so fix the source and re-run the process, never patch the copy. Decision rule below |
| `review_every` | required | How often someone re-checks the file against its sources: `30d`, `90d`, `180d`. On a card for synced data, the longest gap between data changes that is normal, not how often the sync runs (see "Data files") |
| `sources` | recommended; required when `edit: upstream` | Where the content comes from: systems, pages, people, with URLs where they exist. One entry per source. Name the system, not a snapshot: dates belong in `verified_at`. On `edit: upstream`, also name the tool or agent that writes the file, if one does |
| `owner` | recommended | Who answers for the file, by name as it appears in the org chart. The lint warns when the name is not someone who works here |
| `verified_at` | recommended | When a person last confirmed the content against its sources, `YYYY-MM-DD`. Touching this field is the act of verification; an edit, an import, or a rewrite is not one. An agent sets it only when the user says they verified the content, with one exception: an export that writes an `edit: upstream` file whole from its source records the export date |
| `files` | cards only | Data files this Markdown file speaks for, as paths relative to it (see "Data files" below) |

The lint warns about a missing recommended field and, in `--strict` mode, fails on it. The header is one flat mapping of scalars and lists, nothing nested; quote any value that contains ` #` or `: ` or ends in `:`, because YAML would read a comment or a nested key, and the lint rejects the unquoted form rather than guess.

#### Which files carry one

- **Every tracked `.md` under a `context/`, `references/`, or `agent-references/` directory.** A new file always has one.
- **Exempt: `CLAUDE.md`** - an index and crossroads, always loaded; its owner is CODEOWNERS and its freshness is git. Department `CLAUDE.md` files still hold content of their own (team structure, metrics, processes); their freshness expectation is the 30-day and 90-day table under "Freshness expectations", not a header.
- **Exempt: `README.md` and `docs-for-humans/`** - human docs, not agent context.
- **Exempt: `SKILL.md`, agents, and rules** - they keep their own frontmatter and carry no maintenance header. A skill's data files are covered by cards (below).
- **Existing files without a header keep working until someone edits them.** Headers are written by people who know the file, never generated: a skeleton header nobody wrote is a header nobody maintains. So a file with no header is a lint warning across the tree and a lint error on any file a PR touches. Every edit is the moment the header gets written, and an editor who does not know the sources or owner asks the folder's CODEOWNER.

#### Data files

`.json`, `.csv`, `.html`, and `.xlsx` files cannot carry a header, and nothing is ever forced into them: a sync writes the data it writes and touches nothing else. A **sibling Markdown card** carries the header on the data file's behalf:

- One card per data file, or per group of files that share one source. Name it after the file: `org-chart.md` beside `org-chart.json`.
- The card lists the files it speaks for under `files:`, as paths relative to itself. Every data file must be claimed by exactly one card.
- The card's header describes the **data**, not the skill or folder around it: `sources` is where the data comes from, `review_every` is how often the data should be refreshed, `owner` is who runs the refresh.
- The card's body says what the data is and how to use it, or points to the `SKILL.md` that does. The `SKILL.md` or context index that uses the data links the card, like any other context file: an unlinked card is an orphan.
- **Synced data needs no `verified_at`.** On a card with `edit: upstream` and no `verified_at`, the newest commit that changed *only* the card's files is the verification: a sync commit touches the data and nothing else, and is by construction a check against the source. A hand edit or a refactor that also touched other files does not count, and a card whose files have never landed alone is reported unverified. This derivation exists because a data file cannot carry a date; a synced Markdown file can, and its exporter writes the export date into `verified_at` itself.
- **`review_every` on a card is the longest gap between data changes that is normal**, not the sync's run cadence. A sync that finds nothing new leaves no commit, so git can tell you the data has not changed in N days; it cannot tell you the sync stopped running. When the files go longer than `review_every` without a sync commit, the lint reports the card stale, meaning "look at the sync". Whether the sync is alive is the sync's own job to report (the sync tool's run history, a workflow's status), not the header's.

```yaml
---
sources:
  - "the HR system: name, job title, department, manager - exported weekly by the org chart sync"
  - "Slack: display name as nickname, team from the profile title"
owner: Zoë Müller
edit: upstream
review_every: 30d
files:
  - org-chart.json
---
# Org chart data
```

#### Choosing `edit`

The number of sources is irrelevant; what matters is whether a *process* owns the file. Ask: could someone regenerate this file from its sources without reading the current version? If yes, it is `upstream` - a sync, an export, a re-paste, or a fixed agent prompt produces it, so a hand edit is either overwritten on the next run or, if nobody re-runs it, forks the copy from its source. A verbatim copy is always `upstream`, even one somebody pasted once by hand, because "re-paste from the source" is its process. If regenerating the file would take judgment - choosing what to include, summarizing, reconciling sources, adding advice - it is `here`: someone authored it, and when a source changes, someone has to think about how the file changes. A hand-written summary of one Notion page is `here`; a digest an agent rebuilds from six policies on demand is `upstream`. Mixed files (an authored playbook with one pasted table) are `here`, with where the pasted table came from listed in `sources`.

What the flag asks of a reader who finds an error: on `upstream`, fix the source, then re-run the process, and never edit the file itself. On `here`, fix the file in a PR, and if you checked its facts against the sources while you were there, set `verified_at` to today.

On `upstream`, each `sources` entry says where the content lives and, when a tool or agent writes the file, which one: "the HR system - exported weekly by the org chart sync", "Notion page X, exported by <agent name>". When no tool is named, the `owner` refreshes the file by hand: "Slack #finances, request threads, re-summarized by hand". The person never goes into `sources`; that is what `owner` is for. An `upstream` file must name its `sources`; the lint treats a copy without a source as an error.

#### Copies keep no frontmatter of their own

A page fetched from a docs site or exported from Notion arrives with its own `title`/`url` block; the maintenance header replaces it and `sources` names the live URL. A sync process that writes Markdown emits the header as part of the file, with `verified_at` set to the export date, and the lint fails when one drops it. A sync that writes data files emits only the data; the card is hand-written once.

#### The lint

`python3 tools/maintenance/check.py` enforces all of this; the `maintenance-lint` workflow runs it on every PR with `--changed-since` set to the base branch.

- **Errors** (fail the check): a file the PR touches with no header; a malformed header; an unknown key; a bad `edit` or `review_every`; `edit: upstream` without `sources`; a data file no card claims, or two cards claim; a card pointing at a file git does not track.
- **Warnings** (printed, not failing): a file the PR does not touch with no header; a missing `sources`, `owner`, or `verified_at`; an owner not in the org chart; a stale file, meaning `verified_at` (or, for synced content, the last sync commit) plus `review_every` is in the past.
- **Modes**: `--changed-since <ref>` is what CI runs on a PR, with the base branch as `<ref>`; files count as touched when they differ from the merge base of `<ref>` and `HEAD`, so commits that landed on the base branch after the PR branched are not blamed on the PR; `--strict` turns every warning into an error; `--report` prints a freshness table, one row per file, with files that have no header listed as `no header`; `--verbose` lists the files behind each summary line.

What the header does not do: it does not say the content is correct, only when someone last said so. And it cannot stop a sync from overwriting a hand edit - that is what `edit: upstream` is warning you about.

### Cloud composition and the rules it requires

In Cloud, a setup script composes a team's artifacts up to the repo root before Claude launches (on the CLI, Claude discovers them by walking up from the cwd instead). For each `CLAUDE.md`-bearing folder in the chain from the target team up to the root, the bootstrap reads:

- `.claude/skills/` - skill folders (a more-specific level wins on a name clash)
- `.claude/agents/` - agent files or folders
- `.claude/commands/` - command files
- `.claude/rules/` - rule files (copied with a level-name prefix to avoid collisions)
- `.claude/hooks/` - hook scripts (names must be globally unique; a collision is a hard error)
- `CLAUDE.md` - not copied; `@import`ed in place, so its own relative paths and further imports keep working

Two naming rules make this work, both enforced by `security-lint` in CI:

1. **Folder names that contain a `CLAUDE.md` must be globally unique** across the workspace. Cloud team resolution keys on the folder basename, so two teams both named `content` in different departments are rejected. (`tools/bootstrap/**` is excluded.)
2. **Every whole-line `@import` in a committed `CLAUDE.md` must resolve**, relative to that file's own directory. Gitignored targets like `CLAUDE.local.md` are allowed. This closes a silent-failure gap: a typo'd `@import` loads with no error at runtime.

### .claude/ directory

Root `.claude/` contains:
- `agents/` - Company-wide agents
- `rules/` - Always-loaded rules (apply to entire workspace)
- `skills/` - On-demand context loaders and workflows
- `settings.json` - Team-shared security config (sandbox, deny rules, hooks). Committed. Protected from Claude edits.
- `settings.local.json` - Personal permission overrides. Gitignored and **never committed** - it must not appear anywhere in the source tree, for any team or department (enforced by `security-lint`).
- `hooks/` - PreToolUse and SessionStart hook scripts referenced from `settings.json`

The root `settings.json` is the **single source of truth** for security policy. Every tracked `CLAUDE.md`-bearing department/team folder also carries a `.claude/settings.json`, but those are **generator-owned derivatives**, stamped by `python3 tools/bootstrap/bootstrap.py settings-sync` so Desktop-local sessions opened at a team folder load the policy (settings don't walk up - see [how-it-works](docs-for-humans/how-it-works.md#team-folder-settings-desktop-local)). Rules for the team copies:

- **Never hand-edit one** (they are also edit-protected from Claude). A hand-edited copy is drift; CI and `doctor` flag it.
- **Never write a bespoke team `settings.json`.** Team-specific permission needs go in the gitignored `settings.local.json`, or into the root policy via a reviewed PR.
- **To change policy**: edit the root `.claude/settings.json` (protected file - human applies the diff), run `settings-sync`, and commit the regenerated copies in the same PR. `settings-sync --check` must pass in CI.
- A new team folder gets its stamp by running `settings-sync` after adding the `CLAUDE.md`; the generator hard-fails if the `.gitignore` allowlist would ignore the stamp (out-of-structure folders must be restructured or explicitly allowlisted).

Team-level `.claude/` may additionally carry `agents/`, `commands/`, `rules/`, `hooks/`, and `skills/` (all composed per the section above; the stamped `settings.json` is never composed to the root).

A third derivative exists outside the repo: the cloud bootstrap writes a copy of the root policy, rendered from `origin/main`, to the workspace clone's parent directory so multi-repo cloud sessions load it (see [how-it-works](docs-for-humans/how-it-works.md#multi-repo-cloud-sessions)). It is generated by `tools/bootstrap/parent_settings.py`, never committed, and never hand-edited; changing the root policy is enough.

### Protected files

The following files cannot be edited by Claude (enforced by `.claude/hooks/protect-config.sh` returning exit code 2, backed by `permissions.deny` entries in `.claude/settings.json`):

Configuration:
- `**/.claude/settings.json`
- `**/.claude/settings.local.json`
- `**/.mcp.json`

Security enforcement (editing these would let Claude weaken its own guardrails mid-session):
- `**/.claude/hooks/*.sh`
- `**/.claude/rules/security-check.md`
- `**/scripts/claude.sh`
- `**/scripts/install.sh`
- `**/.githooks/post-checkout`
- `**/.github/workflows/security-lint.yml`

The same paths are also guarded against Bash shell redirection (`>`, `>>`) in the hook. If a change to any of these files is needed, Claude should propose the diff in chat and the human applies it manually.

### MCP configuration

`.mcp.json` is personal and gitignored, never committed (`security-lint` fails the build on a tracked copy). If you use one, put it at the repo root, reference tokens with `${VAR}` expansion, and keep the values in environment variables or a gitignored `.env`.

### Knowledge hierarchy depth

Maximum recommended knowledge nesting: 4 levels of CLAUDE.md inheritance.

- Level 1: `<workspace>/CLAUDE.md` (company)
- Level 2: `departments/customer-success/CLAUDE.md` (department)
- Level 3: `departments/customer-success/teams/scaled-customer-experience/CLAUDE.md` (team)
- Level 4: `departments/customer-success/teams/scaled-customer-experience/teams/customer-support/CLAUDE.md` (sub-team)

Level 4 is for teams that contain sub-teams with distinct enough processes, tools, and metrics that folding them into the team CLAUDE.md would make it unwieldy. Don't add a Level 4 just because a team has functional groupings - default to a single team CLAUDE.md.

The `departments/` and `teams/` grouping folders don't have their own CLAUDE.md files, so they don't add inheritance levels. Infrastructure and human-doc paths (`.claude/agents/`, `.claude/skills/`, `context/`, `docs-for-humans/`, `projects/`, `README.md`) also don't count - none of them is a `CLAUDE.md`. The concern is CLAUDE.md inheritance depth: deeper nesting means more context loaded simultaneously and more chances for inheritance confusion.

### Files at root level

Root-level `.md` files beyond CLAUDE.md, CLAUDE.local.example.md, CONTRIBUTING.md, and README.md should be rare. Cross-functional knowledge belongs in `context/`. Team-specific knowledge belongs in department/team folders under `departments/`.

### Projects folders

Every department/team folder (and the repo root) can have a `projects/` subfolder for ephemeral working files. These are **gitignored** to prevent accidentally committing work-in-progress, cloned repos, or sensitive project artifacts. Use `projects/` for any task that produces intermediate files.

## CLAUDE.md file conventions

### Root CLAUDE.md

Purpose: Lean company overview + context index. Always loaded, so every token counts.

Required sections:
- Company overview (brief)
- Products summary
- Strategic pillars or priorities
- Context Index table
- Organization / leadership
- Directory structure reference

The Context Index is a table with columns: Topic, Key content, File path. Each row points to a `context/*.md` file with a summary. This enables progressive disclosure: Claude sees what's available without loading everything.

### Department CLAUDE.md

Purpose: Department-specific context that doesn't apply globally. Only loaded when working in that department's directory.

Standard sections (in this order, all required - use `[TODO]` for empty ones):

```markdown
# [Name] context

## Team structure

| Role | Count | Reports to |
|------|-------|------------|

## Key metrics

## Processes

## Tools and systems

## [Department-specific sections below...]
```

Department-specific sections (e.g. Legal's Contracts/IP, Marketing's Channels) come after the 4 standard sections. CLAUDE.md is for durable context - ephemeral priorities belong in project folders.

Rules:
- **Never duplicate content from parent CLAUDE.md files.** Team files inherit from parents automatically.
- **Never duplicate content from context/ files.** Reference them instead.
- **Use [TODO: description] for incomplete sections.** This is preferred over omitting sections entirely, as it shows what gaps exist and invites incremental improvement.
- **Keep department-specific only.** If content applies to multiple departments, it belongs in `context/` or a parent CLAUDE.md.

### Team CLAUDE.md

Same rules as department CLAUDE.md, plus:
- **Don't restate parent department context.** The department's CLAUDE.md is loaded automatically.
- **Focus on what differentiates this team** from siblings.

### Size guidelines

There is no hard line count limit, but follow these principles:
- Every line should earn its place. No fluff, no verbose explanations.
- Use bullet points and tables over prose paragraphs.
- If content is only needed sometimes, move it to a context file or skill and reference it.
- The root CLAUDE.md should be especially lean since it's always loaded.
- Instruction density matters more than raw size. 100 well-structured lines beats 30 that miss critical context.

## Context files (context/)

### Purpose

- Cross-functional knowledge that multiple teams need. These are the "deep dives" referenced by the Context Index in the root CLAUDE.md.
- Departments and teams may add their own context files using the same principles. Team context files live in `departments/<dept>/context/` (or the team folder's own `context/`) and are indexed from that team's `CLAUDE.md`, not the root one.

### Conventions

- Every file carries the [maintenance header](#maintenance-header) ahead of its H1 (existing files gain one when next edited)
- One file per major knowledge domain: `customers.md`, `competition.md`, `product.md`, `gtm.md`
- Each file should be self-contained: readable without other context files
- Use descriptive H2/H3 headers that tell Claude exactly what's inside
- Tables for structured data (segments, categories, comparisons)
- New context domains: create a new file in `context/` and add a row to the Context Index
- Allowed file types in `context/`: `.md` for knowledge, plus `.html`, `.csv`, and `.json` for supporting data. Anything else (images, PDFs, binaries) is a human doc - put it in `docs-for-humans/`.

### Cross-references

Context files may reference each other, but should not depend on each other for comprehension. Each file should stand alone.

## Agent file conventions

### Structure

Every agent file must have YAML frontmatter:
```yaml
---
name: kebab-case-name
description: >
  Clear trigger conditions. When to use this agent. 1-3 sentences that help
  Claude (and users) decide when to invoke it.
tools: Tool1, Tool2, Tool3
model: opus|sonnet|haiku
---
```

### Body structure

```markdown
## Your role
- Responsibility 1
- Responsibility 2

## [Domain area]
### [Sub-domain]
- Capabilities and guidance

## Boundaries
- What this agent won't do
- When to escalate
```

### Naming

- File: `kebab-case.md`
- Name in frontmatter: matches filename without extension
- Description: starts with a clear trigger/use case, not a generic role description

### Scope

- Company-wide agents: `.claude/agents/`
- Department/team-specific agents: `departments/dept-name/.claude/agents/` or `departments/dept-name/teams/team-name/.claude/agents/`
- Agents should be narrowly scoped to their domain
- Each department/team should have at most 1-2 agents

### Model selection

- `opus`: Strategic, complex reasoning, important decisions
- `sonnet`: Tactical, routine tasks, well-defined workflows
- `haiku`: Quick lookups, simple transformations

## Skill conventions

### Discovery and scoping

Skills follow the same directory scoping as agents and must be placed accordingly:
- **Project-wide skills**: `.claude/skills/` at repo root, available everywhere
- **Department and team-specific skills**: `departments/dept-name/.claude/skills/`, available only when working in that directory or below

### Structure

```
.claude/skills/skill-name/
  SKILL.md           # Required: skill definition
  references/        # Optional: supporting files
  scripts/           # Optional: executable scripts
```

### SKILL.md format

```yaml
---
name: skill-name
description: >
  When to use this skill. Clear trigger conditions.
---
```

Followed by markdown instructions for what Claude should do when the skill is invoked.

### Naming

- Folder: `kebab-case`
- SKILL.md: always uppercase
- Description: actionable trigger conditions

## Rules conventions

### Location

`.claude/rules/*.md` - loaded automatically for all work in the workspace.

### Path scoping

Rules can be scoped to specific paths using frontmatter:
```yaml
---
paths:
  - "departments/sales/**"
---
```

Rules without `paths` apply globally.

## When to use rules vs. skills vs. CLAUDE.md

| Mechanism | Loaded when | Best for | Examples |
|-----------|-------------|----------|----------|
| `.claude/rules/` | Always (or path-scoped) | Constraints, guardrails, formatting standards that must always apply | Data sensitivity, style core (product names, terminology, formatting) |
| CLAUDE.md | Always (at that directory level) | Context, knowledge, team structure | Team roles, metrics, processes, company overview |
| Skills | On demand, when Claude determines relevance or user invokes | Specialized workflows | SQL analysis, copy editor (brand voice), workspace review |

**Key distinction**: Rules are constraints ("always do X, never do Y"). CLAUDE.md is context ("here's what you need to know"). Skills are capabilities ("here's how to do a specific job").

**Voice and tone split:** Core formatting rules (product names, terminology, sentence case, US or UK English, numbers/money/dates) live in `.claude/rules/style-core.md` (always loaded, kept short). A full style guide, if the company has one, lives in `context/` and is loaded on demand by a style skill that checks for conflicts with the core rules on each use.

## Content quality standards

### Single source of truth (SSOT)

Every piece of knowledge must have exactly one authoritative location. For most knowledge that location is in this repo:
- Company-wide knowledge: root `CLAUDE.md` or `context/*.md`
- Department/team-specific knowledge: `departments/dept-name/CLAUDE.md` or `departments/dept-name/teams/team-name/CLAUDE.md`
- Constraints/rules: `.claude/rules/`
- Personal preferences: user's own CLAUDE.md (gitignored)

The authoritative location may also be **external** (e.g. a Notion page) when the owning team's edits land there - see [Agent context vs human docs](#agent-context-vs-human-docs). The repo then holds either a pointer or a copy with `edit: upstream` in its header, and the external system is the SSOT.

Cross-references are fine. Duplication is not. A copy whose [maintenance header](#maintenance-header) says `edit: upstream` is not duplication - it is a visible cache of an external SSOT. A copy without one is.

### Heading hierarchy

- H1 (#): One per file, at the top (the file title); when the file has a maintenance header, the H1 follows it
- H2 (##): Major sections
- H3 (###): Sub-sections within H2s
- H4+ (####): Use sparingly. If you need H4+, consider whether the content should be in a separate file.
- Never skip levels (don't go from H1 to H3)

### TODO conventions

Mark incomplete sections with `[TODO: description]` or `[TODO]`:
- Place at the start of a section, before any placeholder content
- Include a brief description of what's needed
- Placeholder content after a TODO (like `[Tool]` or `[X]`) is fine for showing structure
- TODOs are expected and encouraged during incremental development

### Markdown formatting

- Use tables for structured data (roles, metrics, comparisons)
- Use bullet points for lists of items
- Use bold for emphasis, not ALL CAPS
- Keep paragraphs short (2-4 sentences max)
- Code blocks for commands, file paths, or technical examples

### File naming

- All folders: kebab-case (`expansion/`, `dev-rel/`, `customer-success/`)
- Grouping folders: lowercase (`departments/`, `teams/`, `context/`, `scripts/`, `projects/`)
- Content files: kebab-case (`customer-journey-map.md`)
- Context files: kebab-case (`customers.md`, `competition.md`)
- Agent files: kebab-case (`sales-strategist.md`, `pa-advisor.md`)
- CLAUDE.md: always uppercase
- SKILL.md: always uppercase
- README.md: always uppercase
- CONTRIBUTING.md: always uppercase

## Freshness expectations

Each context file states its own cadence in `review_every`, and `verified_at` records when someone last checked it against its sources. A file is stale when `verified_at` plus `review_every` is in the past; `python3 tools/maintenance/check.py --report` lists every file's status. Defaults when adding a file:

| Content type | `review_every` | Rationale |
|---|---|---|
| Team structure, headcount, strategy, competitive, pricing | 90d | High change velocity in a fast-moving market and a growing startup |
| Rules, technical docs, skill references, product architecture | 180d | More stable, but they evolve with the platform |
| Machine-synced data (the org chart) | the longest normal gap between data changes | A sync commit is the verification; an idle sync leaves no trace, so the cadence is about the data, not the runs |

`CLAUDE.md` files carry no header; keep the root one and every context index current within 30 days, since errors in navigation compound quickly. These are guidelines, not hard limits. A stale file isn't "broken", it's "worth reviewing" - and the review is what moves `verified_at`.
