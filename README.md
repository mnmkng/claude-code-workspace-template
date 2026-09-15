# Claude Code workspace template

A structured, security-hardened workspace for running Claude Code across a whole company. It gives Claude lean company context, per-department and per-team knowledge that loads only when you work in that team's folder, a context index for on-demand deep dives, and a team security config that is active on every session.

Built by [Apify](https://apify.com) for its own ~200-person organization and published as a snapshot so other companies can start from it. The example company in this repo is Dunder Mifflin, played straight: the org structure and canon are real to the show, the content is written the way a real company would write it. Run the setup skill and it is replaced by yours.

**This is a snapshot, maintained as time permits.** See [`docs-for-humans/provenance.md`](docs-for-humans/provenance.md) for what it was cut from and how.

## What you get

- **Progressive disclosure.** A root `CLAUDE.md` that is always loaded and stays lean, `context/` files it indexes and Claude reads on demand, and `departments/<dept>/teams/<team>/` folders whose `CLAUDE.md`, skills, agents, and rules load only when you work there.
- **Ownership separation.** Each department and team owns its folder; CODEOWNERS routes reviews; a default-deny `.gitignore` keeps out-of-structure files from ever being committed.
- **A security config that cannot be turned off from inside a session.** Sandbox, credential-read denials, a hook that blocks edits to the config itself, an audited WebFetch, a git and gh policy, and a session-start banner the rules key on. Three enforcement layers with different strength on different surfaces, documented honestly in [How this workspace works](docs-for-humans/how-it-works.md#security-enforcement-layers).
- **Two surfaces, one bootstrap.** Claude Code on the web composes a team's artifacts to the repo root before the session starts; the CLI walks up from your folder. Same Python tool, no dependencies beyond Python 3.9.
- **Workspace skills and agents.** `who-is` (org chart lookup that never loads the whole directory), `review-workspace` (audits conventions), `context-extractor` and `context-import-orchestrator` (import knowledge from documents), `notion-exporter`.
- **Conventions written down.** [CONTRIBUTING.md](CONTRIBUTING.md) is the single source of truth for what goes where, and the tooling and CI enforce the parts that can be enforced.

## Set it up for your company

Clone the template, open it in Claude Code, and run:

```
/setup-workspace
```

The skill reads your public website (and, optionally, your LinkedIn company page and any documents you give it) to draft the company layer, interviews you for the org layer - departments, teams, owners, tools, terminology - shows you everything before writing a byte, then replaces the example company with yours, stamps the team security settings, and validates the result. Later, `/add-team` scaffolds a new department or team folder in one step. Full walkthrough: [Building out your team folder](docs-for-humans/building-your-team-folder.md).

Requires a current Claude Code (hooks, skills, and the `sandbox` settings block) and Python 3.9 or later.

## Choosing your surface: web or CLI

| | Claude Code on the web | Terminal CLI |
|---|---|---|
| **Who it's for** | Everyone, especially non-engineers | Engineers comfortable in a terminal |
| **Where it runs** | An ephemeral, isolated cloud VM | Your machine |
| **Network** | Selectable: **Trusted** (allowlisted default) or **Full** (general web, wider exfiltration surface). No headless browser either way | Full internet |
| **How team scoping works** | A setup script composes your team's skills, agents, rules, and context up to the repo root before Claude launches | The `claude` wrapper walks up from your folder so Claude discovers nested `.claude/` and `CLAUDE.md` on its own |
| **Best for** | People not on a dev machine, and any cloud-suitable workload | Code-heavy work, anything needing full local network or local tooling |

Both surfaces share the same repo, the same Python bootstrap tool, and the same skill/agent/rule/CLAUDE.md hierarchy. They differ only in how your team's content reaches the session.

### Desktop app (local): open your team folder

Every tracked folder with a `CLAUDE.md` carries a generated `.claude/settings.json` derived from the root security config, so the policy is live the moment the repo is cloned. Claude Code settings do not walk up from the session folder, which is why the copies exist; skills and `CLAUDE.md` context do walk up, so those load as always. Open the repo root for the full config, or a department or team folder for that team's stamped policy. A `projects/` folder or any other folder without a stamp loads no settings, shows no `ACTIVE` banner, and Claude refuses tool use per the security rules - start from your team folder instead.

## Set up Claude Code on the web

Cloud environments are **per-user**: each person creates their own.

1. **Create an environment** pointed at your fork of this repo, on its default branch. Leave **Network access** on **Trusted** unless you need general web access in-session.

2. **Set the Setup Script** to exactly this, with your repo's folder name:

   ```bash
   #!/bin/bash
   bash /home/user/<your-repo>/scripts/install.sh cloud --compose-only --team root
   ```

   `--team root` loads company-wide context with no team overlay. To scope the session to one team, replace `root` with that team's folder basename. Paste the line as-is; its exact shape matters (see [Cloud composition](docs-for-humans/how-it-works.md#cloud-composition)).

3. **Set the `WORKSPACE_PERSONAL_GIST` environment variable** to a private gist with your personal preferences, so they load each session. See [Add your personal context](#add-your-personal-context).

4. **Start a session.** Your team's skills and context load automatically. If the bootstrap didn't run, Claude will tell you the team config is missing and refuse to work; see [Troubleshooting](#troubleshooting).

You can attach additional repositories to a session (a private repo with your own skills and context, or a repo you are developing) alongside the workspace with no change to the setup script. The workspace's security config and bootstrap still apply; the other repos' root `CLAUDE.md`, rules, skills, commands, and agents load next to the workspace's. This is also how a company can keep this template's framework public and its own context private: fork the template, put the company content in a second private repo, attach both. Details and limits in [Multi-repo cloud sessions](docs-for-humans/how-it-works.md#multi-repo-cloud-sessions).

## Set up the CLI (engineers)

Clone the repo, run `bash scripts/install.sh` once, then run `claude` from anywhere in the tree. Full setup, project folders, local personalization, the git and gh policy, and troubleshooting live in [Using the workspace locally with the CLI](docs-for-humans/using-the-cli-locally.md).

## Add your personal context

Personal preferences (your role, communication style, expertise) tell Claude how to calibrate its responses for you. The repo works without them, but you'll get generic answers.

On the web, store your context in a **private GitHub gist** and point your environment at it:

1. Create a **private** gist with your personal context. Start from [`CLAUDE.local.example.md`](CLAUDE.local.example.md). A single-file gist is used as-is; a multi-file gist is concatenated with file-name dividers.
2. Set `WORKSPACE_PERSONAL_GIST` in your environment config to the gist URL - any form works (page URL, raw URL, `.git` URL, or bare ID). Private gists work without a token.
3. **Never put a personal access token in an env var.** Env vars are visible to anyone who can edit the environment, and you don't need one.
4. To update, edit the gist and start a new session.

On the CLI, copy the example to `CLAUDE.local.md` at the repo root instead; it is gitignored.

## Troubleshooting

On the web you drive everything through Claude. To check the setup, ask Claude to run the bootstrap doctor (`python3 tools/bootstrap/bootstrap.py doctor`) and read back what it reports: mode, resolved team, the composition manifest, personal-context state, and the security posture. If setup looks like it failed, ask Claude to show `.claude/.bootstrap-log.txt`.

| `doctor` shows | Meaning | Fix |
|---|---|---|
| `manifest: not composed` | team artifacts were never composed | Re-save the Setup Script or recreate the env |
| `personal context: empty` / `missing file` | your gist didn't load | Check `WORKSPACE_PERSONAL_GIST` - bad URL, or your GitHub login can't see the gist |
| `manifest: composed for 'X'` (not your team) | a different team is composed | Ask Claude to run `reset`, then recompose with the right `--team` |
| a deleted skill is still listed | re-compose is additive | Ask Claude to run `reset` |
| `sandbox NOT enabled` / no deny rules | security config is degraded | Restore `.claude/settings.json` from git |

`audit.sh` warns that the example company's `CLAUDE.md` is stale. That is expected until `/setup-workspace` replaces it.

## git and gh

`git pull`, `fetch`, and `clone` prompt for approval; destructive or history-rewriting operations prompt every time; auth-modifying commands are denied. Everything else - status, diff, add, commit, push, and read-only `gh` - just works. Full detail in [Using the workspace locally with the CLI](docs-for-humans/using-the-cli-locally.md#git-and-gh-policy).

## More

- [How this workspace works](docs-for-humans/how-it-works.md) - composition, context layers, security layers, repo layout
- [Using the workspace locally with the CLI](docs-for-humans/using-the-cli-locally.md) - engineer setup, project folders, personalization, git policy
- [Building out your team folder](docs-for-humans/building-your-team-folder.md) - bootstrap and grow a team's space
- [CONTRIBUTING.md](CONTRIBUTING.md) - workspace conventions (the rules)
- [Provenance](docs-for-humans/provenance.md) - what this snapshot was cut from and how to refresh it

Claude Code docs: https://docs.anthropic.com/en/docs/claude-code
Claude Code on the web: https://code.claude.com/docs/en/claude-code-on-the-web

## License

Apache-2.0. See [LICENSE](LICENSE).
