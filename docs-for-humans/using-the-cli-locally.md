# Using the workspace locally with the CLI

This is the engineer path: run Claude Code from your terminal against a local clone. It's the right surface for code-heavy work and anything that needs full local network or local tooling. Most other people should use Cloud instead - see the [README](../README.md).

## Setup

Clone the repo and run the installer once per machine:

```bash
git clone https://github.com/<your-org>/<your-repo> workspace
cd workspace
bash scripts/install.sh
```

`install.sh` is idempotent - re-run it any time, or after moving the clone. Then work from anywhere inside the tree:

```bash
cd departments/marketing/projects && mkdir my-project && cd my-project && claude
# Loads company + Marketing context + team security config
```

The wrapper exists because Claude Code doesn't walk up parent directories to find `settings.json`; launching `claude` directly from a subfolder would miss the team config. A session-start banner reports config status: `ACTIVE` means the team config loaded.

### What the installer writes

`bash scripts/install.sh` on a local machine runs the install workflow, which writes:

- A `claude` shell function in your `~/.zshrc`, `~/.bashrc`, or `~/.config/fish/config.fish` (fish), written in your shell's syntax. It walks up from your current directory to the workspace root, then runs the wrapper (`scripts/claude.sh`) with the cwd unchanged, so team scoping works from anywhere in the tree.
- A user-scope session-start check in `~/.claude/settings.json` that warns if you launch inside the workspace tree without the team config loaded.
- A git `post-checkout` hook (`core.hooksPath`) that self-heals the setup after pulls.

`bash scripts/install.sh --check` reports what would change without changing anything (silent on a no-op); the post-checkout hook uses it to self-heal.

## Personal context

Your personal preferences (role, communication style, expertise) live in `CLAUDE.local.md` at the repo root - gitignored (never committed) and `@import`ed by the root `CLAUDE.md`, so it loads on every session. Author it directly from the template:

```bash
cp CLAUDE.local.example.md CLAUDE.local.md
# edit CLAUDE.local.md with your details
```

Alternatively, use Claude Code's global config at `~/.claude/CLAUDE.md` (applies to all your sessions everywhere), or nest this repo inside a personal wrapper folder with its own `CLAUDE.md`. All three work locally; `CLAUDE.local.md` is simplest and matches the Cloud surface.

If you write content often, a `personal-editor` skill can tune Claude's output to your voice. For published content, run the company style skill first, then `personal-editor`. In any conflict, the company style rules win.

## Project folders

Project folders are ephemeral workspaces for tasks that produce intermediate files - proposals, analyses, cloned repos, research outputs. They're gitignored so work-in-progress doesn't pollute the knowledge base. They're a local-CLI workflow: you `cd` into one and start a session there, so Claude inherits the surrounding context. (In Cloud the whole session VM is the throwaway workspace, so this pattern doesn't apply.)

### When to use

Any time you're doing work that produces files you don't want committed to this repo:
- Customer proposals or analyses
- Cloned code for review
- Research outputs (from `/research` or manual)
- Notion exports before importing
- Draft documents

### Quick start

```bash
cd workspace/departments/sales/projects
mkdir customer-proposal && cd customer-proposal
claude
# Claude now has: Sales context + company context + your personal preferences
```

### How it works

Every department and team folder (and the repo root) can have a `projects/` subfolder. These are gitignored because:
- Projects may be their own git repos (e.g., cloned repositories)
- Work-in-progress doesn't belong in the knowledge base
- Keeps the repo focused on durable context

The key benefit: Claude automatically loads context from the parent folders. Working in `departments/sales/projects/deal-prep/` gives you full Sales + company + personal context without any setup.

### Tips

- **Name folders descriptively**: `2026-02-pricing-update/` beats `temp/`.
- **Clean up when done**: delete project folders after the work is complete. They're ephemeral by design.
- **Use the right department**: start your project folder under the department whose context you need most. If you need cross-functional context, use the root `projects/` folder.
- **Multiple repos are fine**: a project folder can contain cloned git repos. The parent repo's gitignore handles it.

## git and gh policy

`git fetch origin ...` **runs without a prompt**. It only writes to `.git`, never to the working tree, and naming an already-trusted remote means it cannot reach an arbitrary host. It also works inside a compound command, so `git fetch origin main && git checkout main` is fine. Common flags come along: `--prune`, `--tags`, `--depth`, `--force`, and the other read-only ones.

Every other fetch **prompts**: a fetch by URL or local path (`git fetch https://...`, `git fetch git@...`, `git fetch /tmp/repo`), `git fetch --all`, a bare `git fetch`, and any flag not on the vetted list. That last one is an allowlist on purpose - an unrecognized flag prompts rather than being trusted, because some of them change where a fetch reaches (`--upload-pack` names a program to run, and `--recurse-submodules` fetches whatever URLs `.gitmodules` carries). Approve them when you recognize the operation. So do `git pull` and `git clone`, plus `git remote add/set-url/rename` - the fetch allowance keys on the *name* `origin`, so changing what that name points at stays gated.

Why `git pull` still prompts when `git fetch origin` doesn't: pull writes the working tree from remote refs, and git runs outside the sandbox, so a ref carrying an older `.claude/settings.json` could roll the security config back. Use `git fetch origin <branch>` followed by an explicit merge or checkout instead.

Everything else - `git push`, `git status`, `git log`, `git diff`, `git add`, `git commit`, `git checkout`, `git branch`, `git stash`, `gh pr/issue/api` reads, etc. - works inside Claude on all platforms. Both `git` and `gh` run outside the sandbox via `excludedCommands`, which restores Keychain access for credential helpers and TLS trust.

Destructive or history-rewriting operations - `git push --force`, `git reset --hard`, `git rebase`, `git clean -f`, branch/tag deletes, `gh repo delete`, `gh release delete`, `gh api` write methods, secret/workflow/key changes - prompt every time, even after "always allow." Auth-modifying commands (`gh auth token`, `gh auth login/logout/refresh`, `git config --global credential.helper`) are denied entirely.

## Troubleshooting

Run `doctor` to check the current state - it reports mode, repo root, resolved team, composition manifest, personal-context state, and the settings.json security posture, and exits non-zero on a real problem:

```bash
bash scripts/install.sh doctor                # diagnose
python3 tools/bootstrap/bootstrap.py reset    # undo composition (team switch / flush a removed artifact)
```

- **Banner reads `NOT DETECTED`**: the team config didn't load. Restart from the workspace root, or re-run `bash scripts/install.sh`.
- **Agent not appearing**: check you're in the right directory. Agents under `departments/sales/.claude/agents/` only apply when you're in or under `departments/sales/`.
- **Context not loading**: verify the file is named exactly `CLAUDE.md` (case-sensitive). Run `/context` to see what's loaded.

For how composition and context loading actually work, see [How this workspace works](how-it-works.md).
