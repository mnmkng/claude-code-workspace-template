# How to build out and maintain your team folder

A walkthrough for a team lead standing up and growing a team's space in the workspace - from an empty folder to a rich context that makes Claude genuinely useful, and keeping it that way.

This is the *how-to*. The *rules* it follows - the canonical folder layout, naming, the globally-unique-folder rule, what the bootstrap composes, freshness thresholds - live in [CONTRIBUTING.md](../CONTRIBUTING.md), which is the single source of truth. This guide links to it rather than restating it.

## 1. Bootstrap the folder

Your team's space goes under `departments/` - either `departments/<dept>/` for a department, or `departments/<dept>/teams/<team>/` for a team within one. Use kebab-case. The only required file is `CLAUDE.md`; everything else (`context/`, `docs-for-humans/`, `.claude/skills/`, `.claude/agents/`, a team `README.md`, `projects/`) is optional and added when you need it. See the canonical layout in [CONTRIBUTING.md](../CONTRIBUTING.md#department-and-team-folders).

Two rules to know up front, both enforced in CI:

- **The folder name must be globally unique** among folders that contain a `CLAUDE.md`. Cloud team resolution keys on the folder basename, so two teams both named `content` in different departments would collide. Pick a distinct name.
- **Every `@import` line in a committed `CLAUDE.md` must resolve.** A typo'd import fails silently at runtime, so CI checks them.

Start sparse. Create `CLAUDE.md` with the standard sections and fill the rest with `[TODO]` markers - they show what's missing and invite incremental improvement. The [department/team CLAUDE.md template](../CONTRIBUTING.md#department-claudemd) shows the required sections.

**Register it for Cloud.** When someone wants a Cloud environment scoped to your team, they set the setup script's `--team` to your folder basename (see the [README](../README.md#set-up-cloud)). The bootstrap composes your team's `.claude/skills`, `agents`, `commands`, `rules`, and `hooks` and `@import`s your `CLAUDE.md` chain. Nothing else is required to make a new team folder Cloud-ready.

## 2. Grow it

### Philosophy

1. **Start sparse** - don't fill everything at once. TODOs are fine.
2. **Add as you work** - after a good conversation that surfaces useful context, extract the insight back into the relevant `CLAUDE.md` or context file.
3. **Review periodically** - metrics, targets, and team structure change. Stale context actively hurts quality.
4. **Layer appropriately** - cross-functional context goes in root `context/` files, department- or team-specific stays in the folder. Don't duplicate a parent's content; it's inherited automatically.
5. **Keep CLAUDE.mds lean** - if content is only needed sometimes, move it to a context file and reference it from the context index.

### Importing from Notion

The most common workflow: pull a Notion page and merge its knowledge in, using two agents in sequence.

**Step 1 - export the page.** From a `projects/` folder, use the `notion-exporter` agent:

```bash
cd workspace/projects
mkdir notion-import && cd notion-import
claude
```

```
Use notion-exporter to export https://www.notion.so/your-workspace/Page-Title-abc123 to ./exported-page.md
```

It fetches the page via the Notion MCP, adds a metadata header (source URL, export date), and writes the content verbatim. For pages with subpages, add `--recursive`.

**Step 2 - import into the workspace.** In the same session:

```
Use context-extractor to process exported-page.md
```

The extractor reads and categorizes the content, determines which files it belongs in (`context/gtm.md`, your team's `CLAUDE.md`, etc.), presents the proposed changes for your review, and merges only what you approve - replacing TODOs and adding sections.

Watch for: **data sensitivity** (it flags compensation, specific revenue, PII - generalize when in doubt), **deprecated terminology**, and **duplication** (verify content isn't already in a `context/` file before it lands in a CLAUDE.md too).

### Importing from documents

For markdown, PDFs, chat transcripts, or any document Claude can read, skip the Notion step and go straight to the extractor:

```bash
cd workspace/projects && mkdir strategy-import && cd strategy-import
# copy your files here
claude
```

```
Use context-extractor to process strategy-notes.md
```

### Batch imports

For multiple files at once, use `context-import-orchestrator` instead. It scans all importable files, spawns an extractor per file, collects every proposed change into one review file (`import-review-{timestamp}.md`) with YAML frontmatter where you mark each change approved/modified/rejected, and waits. When ready:

```
Resume the context-import-orchestrator to apply the approved changes
```

This async pattern is useful for reviewing offline or across sessions.

### Adding skills, agents, and human docs

- **Skills and agents** specific to your team go in `<your-folder>/.claude/skills/` and `<your-folder>/.claude/agents/`; they're scoped to your folder (and composed in Cloud). Conventions: [CONTRIBUTING.md](../CONTRIBUTING.md#skill-conventions).
- **Human docs** (team guides, tooling how-tos, onboarding) go in `<your-folder>/docs-for-humans/`, and durable team orientation in a team `README.md`. Keep these out of `CLAUDE.md` and `context/` so they don't bloat what Claude loads - see [agent context vs human docs](../CONTRIBUTING.md#agent-context-vs-human-docs).

## 3. Maintain it

**Review after importing.** Run the `review-workspace` agent to catch issues an import may have introduced:

```
Use review-workspace to review this workspace
```

It checks for duplication between context files and CLAUDE.mds, stale references (renamed files, old department names), structural issues, and sensitivity violations. Fix findings before they compound.

**Keep it fresh.** Content has expected review cadences (root CLAUDE.md and the context index ~30 days; team structure ~90 days; strategy, competitive, and pricing ~90 days). The full table is in [CONTRIBUTING.md](../CONTRIBUTING.md#freshness-expectations). Stale context is worse than missing context, because it reads as confident and wrong.

### Tips

- **One source at a time** - import related documents together rather than dumping everything; context and recency tracking work better with focused batches.
- **Newer wins** - the orchestrator processes older files first so newer content wins conflicts. Put dates in filenames (`2026-02-strategy-update.md`).
- **Check the context index** - after adding context files, verify the index table in the root `CLAUDE.md` still points to the right files with accurate summaries.
- **Don't import everything** - import what Claude needs to do its job (team structure, processes, metrics, domain knowledge). Skip meeting minutes, one-off decisions, and transient updates; those stay in their system of record.
