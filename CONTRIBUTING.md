# Contributing to the knowledge workspace

This file defines the conventions for adding and maintaining content in this workspace. Both humans and Claude should follow these rules. The `review-workspace` agent audits against these conventions.

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
- `docs-for-humans/` - Human-only docs and step-by-step tutorials for workspace-wide workflows (teams add their own `docs-for-humans/` for team-specific human docs)
- `.mcp.json` - MCP server configuration, local and gitignored (see MCP section below)

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
3. **External SSOT + marked mirror.** The `who-is` org chart at `.claude/skills/who-is/references/org-chart.json` is the reference implementation: synced from the HR system and the chat tool by a job that opens a PR when the data changes. Follow its header format for new mirrors; each mirror needs its own sync process. Humans edit externally but agents need the content often enough that fetching every time is wasteful, so a sync process mirrors the content into the repo on a cadence. Mirror files carry a header marking them generated: source URL(s), sync date, and "do not hand-edit". An agent that spots an error in a mirror proposes the fix in the external source - it never edits the mirror, otherwise mirrors become forks. The hard part is that Notion and this repo are not 1:1: one repo file can distill several Notion pages and vice versa, so the sync needs an explicit source mapping and, for non-verbatim cases, an agent-mediated transform rather than a mechanical copy (`notion-exporter` covers only one-off verbatim exports today).

**Sensitivity override**, on top of all three patterns: named counterparties, deal specifics, and anything failing `.claude/rules/data-sensitivity.md` never enters the repo, even via a mirror. The repo holds the anonymized position; the external system holds specifics.

This rule is transitional: placement is expected to migrate toward repo-SSOT as teams adopt agent workflows. Keying on where edits land lets that happen team by team, without rewriting this rule.

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

Put `.mcp.json` at the **repo root**. This is where Claude Code looks for it.

It is **local and gitignored** - `security-lint` fails the build if one is committed at any depth, and the sandbox denies Claude read access to it. Each person creates their own:
- Use `${VAR}` expansion syntax for tokens and credentials
- **Store actual secrets in `.env`** (gitignored) or system environment variables
- Claude Code expands `${VAR}` at runtime from the environment

Document which MCP servers the team uses, and the shape of the config, in `README.md` or `docs-for-humans/` - never commit the file itself.

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

The authoritative location may also be **external** (e.g. a Notion page) when the owning team's edits land there - see [Agent context vs human docs](#agent-context-vs-human-docs). The repo then holds either a pointer or a marked mirror, and the external system is the SSOT.

Cross-references are fine. Duplication is not. A marked mirror (generated header with source URL, sync date, and "do not hand-edit") is not duplication - it is a visible cache of an external SSOT. An unmarked copy is duplication.

### Heading hierarchy

- H1 (#): One per file, at the top (the file title)
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

Content types and their expected review cadences:

| Content type | Staleness threshold | Rationale |
|---|---|---|
| Root CLAUDE.md, Context Index | 30 days | Central navigation; errors compound quickly |
| Team structure, headcount | 90 days | Growing startup; reorgs and hiring happen fast |
| Strategy, competitive, pricing | 90 days | High change velocity in fast-moving market |
| Rules, technical docs | 180 days | More stable but need periodic review |
| Product architecture | 180 days | Evolves with platform changes |

Note: These are guidelines, not hard limits. A file modified 91 days ago isn't "broken", it's "worth reviewing."
