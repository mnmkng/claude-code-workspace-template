# How this workspace works

Background on the machinery behind the setup. You don't need any of it to start working - the [README](../README.md) setup sections and (for engineers) [Using the workspace locally with the CLI](using-the-cli-locally.md) are enough. This is for when you want to understand what's happening under the hood.

For the conventions that govern *what goes where* in the repo, see [CONTRIBUTING.md](../CONTRIBUTING.md). For a walkthrough of standing up a team's space, see [Building out your team folder](building-your-team-folder.md).

## Cloud composition

Cloud sessions start at the repo root with no subfolder discovery, so the bootstrap composes your team's content up to the root. It runs in two tiers from one entrypoint:

- **Setup tier** (`cloud --compose-only`, cached, runs as root, ~7-day TTL): composes your team's `.claude/skills`, `agents`, `commands`, `rules` (level-prefixed), and `hooks` up to the root `.claude/`, writes the team `CLAUDE.md` `@import` block into `CLAUDE.local.md`, and mirrors a snapshot to `/opt/claude-workspace/composed/`. The tracked `CLAUDE.md` is never modified.
- **Session tier** (`cloud --apply-only`, every session, sub-second, per user): re-composes the team overlay from the live git checkout, re-injects the `@import` block, and fetches your personal gist into `CLAUDE.local.md`.

The Setup Script line is shaped the way it is for reasons found in real cloud environments:

- **Absolute path** - the setup script's working directory is `/home/user`, not the repo root, and it runs as `root`. A bare `bash scripts/install.sh` fails with exit 127.
- **`--team` inline, not an env var** - environment-config env vars aren't injected into the setup-script process, so `WORKSPACE_TEAM` set there reads empty at setup time.

The setup tier tees its log to `.claude/.bootstrap-log.txt` (it survives into the session) - the place to look when setup misbehaves, since the UI truncates setup stdout.

**Your changes propagate next session.** Because the session tier re-composes from the live checkout, edited or newly added skills, agents, rules, or context appear on the next session - no cache rebuild, no version bump. Two residuals: a **removed** artifact lingers until a cache rebuild or `reset` (re-compose is additive), and a **brand-new skill** has a one-tool-call discovery lag on its first session (available from turn 2). Cache rebuilds still happen on a setup-script change, a network-allowlist change, or the ~7-day TTL, but they're no longer how content reaches users - and changing only an env var does **not** rebuild the cache.

**`reset`** (`python3 tools/bootstrap/bootstrap.py reset [--personal]`) undoes composition: it removes the untracked overlay, the `.git/info/exclude` block, and the team block in `CLAUDE.local.md`. In cloud it cleans the current session's working tree; the next session re-composes from the live checkout. `--personal` also clears the personal-context region.

## Multi-repo cloud sessions

A cloud session can attach more than one repository. The platform clones them as siblings under `/home/user/` and anchors the project root at that parent directory, not at either repo. Root `CLAUDE.md`, rules, root skills, commands, and agents from every attached repo load, but project settings are read only from the primary working directory, so neither repo's `.claude/settings.json` would load there: no deny rules, no hooks, no bootstrap apply tier, and no ACTIVE banner.

The bootstrap closes that gap with a third generator-owned derivative of the root `settings.json`, written to the parent directory (`/home/user/.claude/settings.json` in cloud):

- **Written unconditionally.** Repository selection is per session, but the setup script runs once into a snapshot every later session in the environment shares. So both tiers write the file whatever the current layout is: the setup tier seeds it, the per-session apply tier refreshes it. In a single-repo session the project root is the workspace itself and the parent file is inert; in a multi-repo session it is the only policy that loads. No setup-script flag is needed.
- **Rendered from `origin/main` whenever git can reach it.** The file outlives the session that wrote it, so the branch that last rendered it would otherwise govern every following session. A cloud clone carries only the session branch, and git can authenticate only inside a live session (the platform proxy injects GitHub auth there; the setup tier has no credentials). So the setup tier seeds the file from the working tree and stamps `env.WORKSPACE_PARENT_POLICY_SOURCE` with `working-tree@<sha>`, and every apply-tier run inside a session fetches `main` and re-renders from it, stamping `origin/main`. A multi-repo session therefore converges to the reviewed rendering within seconds of start. A reviewed rendering is never downgraded to a working-tree one by a later fetch failure. `doctor` and `parent-settings --check` report a working-tree source as a problem, never healthy. A single-repo session on a feature branch still loads that branch's own settings directly, as before.
- **Same derivation as the team stamps.** Every top-level key is copied verbatim except `hooks` (rebuilt) and the MCP keys. The hook commands pin the workspace clone's absolute path instead of resolving via `$CLAUDE_PROJECT_DIR`, which is the parent in this layout. `env.CLAUDE_WORKSPACE_ROOT` is set to the clone path.
- **Fails closed without the workspace.** If a session in a workspace environment attaches other repos but not the workspace, the PreToolUse wrappers block file edits, Bash, and WebFetch, the deny rules in the same file still apply, and the banner reports NOT DETECTED so Claude refuses tool use per `security-check.md`. Read, Glob, Grep, and MCP tools have no wrapper (the same guarantee the team-folder stamps give). A workspace environment is for workspace work; use a different environment for anything else.
- **Guarded destination.** The `parent-settings` subcommand is cloud-only, the generator refuses a parent that is the home directory (that target would be `~/.claude/settings.json`), and it never overwrites an existing file it did not write itself.
- **Refresh takes effect in the running session.** Claude Code watches loaded settings files and reloads permissions and hooks on change, so when the apply tier rewrites the parent file the current session picks it up too.

Things that do not change: only the workspace's policy applies, so the other repos' own `settings.json` and hooks stay unloaded; root-level content from every repo loads symmetrically, so two repos defining an agent with the same name shadow each other; nested `departments/**` content still needs composition.

`python3 tools/bootstrap/bootstrap.py parent-settings [--check]` writes or verifies the file by hand, and `doctor` reports it under Security (in sync, missing, or drifted, together with the detected layout).

## Team-folder settings (Desktop local)

Claude Code loads project settings from the folder a session starts in - settings never walk up the tree the way skills and `CLAUDE.md` do. A Desktop local session opened at a team folder therefore used to look fully configured (context and skills present) while silently running with no sandbox, no deny rules, and no hooks. The team-folder stamps close that gap.

`python3 tools/bootstrap/bootstrap.py settings-sync` stamps a **generated** `.claude/settings.json` into every tracked `CLAUDE.md`-bearing department and team folder. The stamp is a derivative of the root `.claude/settings.json` - the root file stays the single source of truth:

| Root settings content | In team copies | Why |
|---|---|---|
| Everything not listed below (`permissions`, `sandbox`, `autoMemoryEnabled`, future keys) | Copied verbatim | Copy-everything-except semantics: a new root key propagates on the next sync instead of going silently stale in 29 folders |
| Script hooks | Rebuilt as inline walk-up wrappers | The root hook commands resolve via `$CLAUDE_PROJECT_DIR`, which in a team-folder session is the team folder. The wrappers walk up to the workspace root at runtime and exec the root's own scripts - and **fail closed** (block the tool call) if the root or its scripts cannot be found |
| MCP keys | Dropped | No `.mcp.json` in team folders |
| - | Added: inline `SessionStart` banner | The security rules treat a missing ACTIVE banner as NOT DETECTED and refuse tool use, so a working-but-silent policy would trip the rule it satisfies. The banner reports `ACTIVE (team-folder policy vN)` when the root is found, NOT DETECTED otherwise |
| - | Added: `env.WORKSPACE_TEAM_POLICY_VERSION` | Lets any hook or probe ask whether the policy is live and which version |

Properties worth knowing:

- **Delivery is `git clone` itself.** Protection exists the moment the repo is on disk - no installer, no per-machine state.
- **All copies are byte-identical** (the walk-up happens at runtime, so depth doesn't matter). `settings-sync --check` verifies presence, byte-identity against fresh generator output, and the absence of stray copies; it runs in CI and is reported by `doctor` and the post-checkout self-heal.
- **Hooks are the robustness floor.** Hooks fire regardless of workspace trust (permission rules can be trust-gated), and the wrappers block rather than no-op when they cannot enforce.
- **Cloud is unaffected.** Cloud sessions anchor at the repo root, and composition copies only skills/agents/commands/rules/hooks - a regression test asserts a team `settings.json` is never composed to the root.
- **CLI double-load is harmless.** A CLI session in a team folder loads the root settings (via the wrapper's `--settings`) plus the team stamp; the content is generator-identical, so the effective policy is unchanged (worst case a duplicate banner).

Team copies are generator-owned: never hand-edit them (they are also edit-protected from Claude). Change the root `.claude/settings.json` via a reviewed PR, re-run `settings-sync`, and commit the regenerated copies in the same PR.

## Security enforcement layers

The security setup is three layers with different strength guarantees. Knowing which layer is deterministic on which surface matters when reasoning about what the config actually prevents:

| Layer | What it inspects | Strength |
|---|---|---|
| `permissions.deny` rules | Tool calls only: `Edit(...)` patterns match the file-editing tools, `Bash(...)` patterns prefix-match the command string | Advisory against processes - a file write performed inside a launched script is invisible to this layer by construction |
| `protect-config.sh` hook | The full Bash command string: shell redirects, write commands in any pipeline position, interpreter one-liners that visibly combine a write call with a protected path | Tamper-evident friction - it cannot see inside a script file, so a write buried in a script it launches passes |
| Sandbox (`filesystem.denyRead` / `denyWrite`) | Every filesystem access of every process the session spawns, at the OS level | Deterministic where enforced |

Sandbox enforcement is surface-dependent:

- **Desktop local and the CLI (macOS)**: enforced via Seatbelt. A script write to a `denyWrite` path fails with `operation not permitted` no matter how the write was launched. This is the deterministic layer, and it is why the team-folder stamps carry the full sandbox block.
- **Cloud (Claude Code on the web)**: the settings' sandbox block is not translated into OS enforcement; the platform's isolated, ephemeral container is the security boundary instead. Inside the container the first two layers provide friction and tamper evidence, and durability comes from process: nothing reaches `main` without a human-reviewed PR, and CI (`settings-sync --check`, `security-lint`) makes any change to tracked security files loud.

The residual, accepted gap: on a surface without OS sandbox enforcement, a session could in principle weaken its own in-container guardrails by writing and running a script. That path is resisted by the always-loaded security rules (`security-check.md` forbids script-mediated writes to protected paths explicitly) and surfaced by git and CI, but it is model-behavioral and review-based rather than deterministic - the same tier of gap as git and gh running outside the sandbox, an accepted trade-off. Documented here so nobody mistakes the deny rules or the hook for the strong layer.

## Context layers

```
Always loaded (lean):
  CLAUDE.local.md   → Personal preferences (gitignored; @imported by CLAUDE.md)
  CLAUDE.md         → Company overview, products, pillars, context index

Team-scoped (CLI: when you cd into the folder; Cloud: composed by the setup script):
  departments/<dept>/CLAUDE.md                         → Department context
  departments/<dept>/teams/<team>/CLAUDE.md            → Team context
  departments/<dept>/.claude/{skills,agents,...}       → Department/team skills, agents, rules

Context index (in CLAUDE.md), read on demand:
  context/customers.md         → Segments, journeys, use cases
  context/competition.md       → Full competitive landscape
  context/product.md           → Platform, pricing, economics
  context/gtm.md               → Cross-functional GTM strategy
  context/job-architecture.md  → Career ladder framework, IC competency definitions
```

The base context is kept lean to preserve your context window. It includes a **context index** - a compressed table that tells Claude what detailed context exists and where, so Claude reads the full files only when the task requires it.

## Agents, skills, and rules

- **Agents** (`.claude/agents/*.md`) are specialized AI personas, scoped to the folder they live in. Company-wide agents include `context-extractor`, `context-import-orchestrator`, `notion-exporter`, and `review-workspace`.
- **Skills** (`.claude/skills/*/SKILL.md`) are workflows loaded automatically when Claude detects a matching task, or invoked via `/skill-name`. Company-wide skills include `who-is`, `setup-workspace`, and `add-team`; teams add their own under their folder.
- **Rules** (`.claude/rules/*.md`) are always-loaded guardrails: `style-core.md` (formatting and terminology), `data-sensitivity.md` (what not to include in prompts), and `security-check.md` (what Claude may not touch).

Two of those skills write the workspace rather than read it. `setup-workspace` runs once on a fresh clone: it drafts the company layer from your public website, interviews you for the org layer, shows you the spec and the full list of paths it would write and delete, and only then replaces the example company - writing the new root `CLAUDE.md` and the new departments *before* deleting the old ones, so the three root markers the bootstrap looks for are never missing mid-run. `add-team` is the same machinery for one folder, any time later: four questions, then the scaffold. Both go through `python3 tools/bootstrap/bootstrap.py scaffold`, which is CONTRIBUTING's folder layout in executable form, and both leave the tree passing `bootstrap.py lint`. Neither edits a protected file: where a company needs a new entry in the security config, the skill prints a diff and a human applies it.

On both surfaces, the team's own skills, agents, commands, rules, and hooks are added to the company-wide set - by cwd-walking on the CLI, and by composition in Cloud.

## Repo layout at a glance

```
<workspace>/
├── CLAUDE.md                # Lean company context (always loaded)
├── CLAUDE.local.example.md  # Template for personal preferences (copy to CLAUDE.local.md)
├── CLAUDE.local.md          # Your personal preferences (gitignored, not committed)
├── CONTRIBUTING.md          # Workspace conventions and standards
├── README.md                # Setup and orientation
├── .claude/                 # Global Claude Code config (agents, rules, skills, hooks, settings.json)
├── context/                 # Cross-functional knowledge (referenced by the index in CLAUDE.md)
├── departments/             # All department and team folders
├── docs-for-humans/         # Human-only tutorials for workspace-wide workflows
├── scripts/                 # Workspace tooling (install.sh shim, claude.sh wrapper, audit)
├── tools/bootstrap/         # The Python bootstrap tool (compose, cloud, install, doctor, reset)
└── tools/maintenance/        # Checks the maintenance header on every context file (CI: maintenance-lint)
```

The canonical layout for a department or team folder, the rule that folder names containing a `CLAUDE.md` must be globally unique, and what the bootstrap composes from a team folder are all documented in [CONTRIBUTING.md](../CONTRIBUTING.md). The how-to walkthrough is [Building out your team folder](building-your-team-folder.md).
