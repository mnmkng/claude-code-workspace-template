# Provenance

This repository is a **snapshot** of the framework layer of Apify's internal Claude Code workspace, first cut on September 9, 2026 from commit `cf84749` of that private repository and refreshed on September 15, 2026 from commit `e79a0fd` (which added the maintenance header on context files, its lint under `tools/maintenance/`, and the multi-repo parent policy in the bootstrap). There is no automatic sync in either direction. It is maintained as time permits; issues and pull requests are welcome and triaged when someone gets to them.

Everything below records how the snapshot was produced, so a refresh is an afternoon's work rather than archaeology.

## What was copied

The workspace has three kinds of files. Only the first two are here.

| Class | What | In this repo |
|---|---|---|
| Framework | Security config and hooks, the always-loaded rules, the bootstrap tool and its tests, install and wrapper scripts, git hooks, CI workflows, the default-deny `.gitignore`, conventions, setup docs, the workspace agents, the `who-is` skill | Yes, de-branded |
| Example content | Root `CLAUDE.md`, `context/`, `departments/`, CODEOWNERS, style rule, team skills, `who-is` data | Yes, written fresh for the example company |
| Company content | Everything specific to the source company | No |

Path allowlist used for the copy:

```
CLAUDE.local.example.md  CONTRIBUTING.md  README.md  .gitignore
.claude/settings.json  .claude/hooks/
.claude/rules/security-check.md  .claude/rules/data-sensitivity.md  .claude/rules/workspace-edits.md
.claude/agents/review-workspace.md  .claude/agents/context-extractor.md
.claude/agents/context-import-orchestrator.md  .claude/agents/notion-exporter.md
.claude/skills/who-is/SKILL.md  .claude/skills/who-is/scripts/
.claude/skills/who-is/references/org-chart.md  (card; the data file is rewritten empty)
tools/bootstrap/  (minus research/ and __pycache__/)
tools/maintenance/
scripts/  .githooks/  .github/
docs-for-humans/how-it-works.md  docs-for-humans/using-the-cli-locally.md
docs-for-humans/building-your-team-folder.md
```

Not copied: the source company's `CLAUDE.md`, `context/`, `departments/`, every other skill and agent, its style rule, its `who-is` data, its screenshots, and internal research fixtures.

## What was transformed

Mechanical, ordered substitutions applied to every copied text file (this file and `protected-files.patch` excepted, since both quote the old tokens on purpose):

| From | To |
|---|---|
| `APIFY_CLAUDE_CODE_WORKSPACE_ROOT` | `CLAUDE_WORKSPACE_ROOT` |
| Other `APIFY_*` environment variables and constants | `WORKSPACE_*` |
| `Apify team security config` (the banner the security rule keys on) | `Workspace security config` |
| `/opt/apify/composed` staging directory | `/opt/claude-workspace/composed` |
| `APIFY-BOOTSTRAP`, `APIFY-CLAUDE-CODE-` marker comments | `WORKSPACE-BOOTSTRAP`, `WORKSPACE-CLAUDE-CODE-` |
| Root sentinel `--team apify` | `--team root` |
| `find_apify_root`, `apify_root` identifiers | `find_workspace_root`, `workspace_root` |
| Repo name and setup-script path | `<your-org>/<your-repo>`, `/home/user/<your-repo>` |
| Prose: "Apify root", "Apify tree", company name in docstrings and test fixtures | workspace root, workspace tree, generic wording |
| Real employees named in examples and test fixtures (maintenance-header `owner` examples, lint tests) | Fictional people; the accent-folding tests keep an accented name |
| The source company's HR vendor and automation tool, by name and URL | "the HR system", "the org chart sync" |

Then a hand pass over prose: README rewritten, CONTRIBUTING examples generalized, `who-is` documentation and script messages made source-system agnostic, the two import agents told to discover the workspace layout at run time instead of from a hardcoded list, CODEOWNERS reduced to `@TODO-` placeholders, the codeowners-fallback workflow made to read its fallback reviewers from the CODEOWNERS default line, private issue references replaced with a sentence of rationale, and the source company's grandfathered paths removed from `.gitignore`.

### The nine files Claude could not transform

The workspace's own PreToolUse hook refuses to let Claude modify any file whose path ends in a protected name, wherever it lives, copies included. So the nine protected files were carried over byte-identical, and the de-branding of the seven that mention the source company (plus the removal of the source company's MCP allow entries and MCP keys from the settings file) was written as a proposed diff, `protected-files.patch` at the repo root, for a human to apply once:

```bash
git apply --check protected-files.patch && git apply protected-files.patch
git rm -q protected-files.patch
chmod +x .claude/hooks/*.sh scripts/claude.sh scripts/install.sh   # a patch must never change modes; re-assert them
bash scripts/test-security.sh        # sections 1-5 pass, except the two banner cases and section 6 that cd into departments/ (they pass once the example departments exist)
git commit -am "De-brand protected files"
```

For a refresh, the equivalent substitutions as a one-liner over the protected files:

```bash
cd <export-dir>
files=".claude/settings.json .claude/hooks/protect-config.sh .claude/hooks/status-banner.sh \
  .claude/hooks/webfetch-audit.sh .claude/rules/security-check.md scripts/claude.sh \
  scripts/install.sh .githooks/post-checkout .github/workflows/security-lint.yml"
sed -i -E \
  -e 's#/opt/apify/composed#/opt/claude-workspace/composed#g' \
  -e 's/APIFY-BOOTSTRAP/WORKSPACE-BOOTSTRAP/g' \
  -e 's/Apify team security config/Workspace security config/g' \
  -e 's/APIFY_CLAUDE_CODE_WORKSPACE_ROOT/CLAUDE_WORKSPACE_ROOT/g' \
  -e 's/\bAPIFY_/WORKSPACE_/g' \
  -e 's/find_apify_root/find_workspace_root/g' \
  -e "s#bash Apify/scripts/install.sh#bash <your-repo>/scripts/install.sh#g" \
  -e 's#Apify/\.claude/settings\.json#<workspace>/.claude/settings.json#g' \
  -e 's/`apify_api_\.\.\.`/`ghp_...` (GitHub)/g' \
  -e 's/an Apify tree/a workspace tree/g; s/any Apify tree/any workspace tree/g' \
  -e 's/the Apify root/the workspace root/g; s/Apify root/workspace root/g; s/Apify tree/workspace tree/g' \
  -e 's/Apify Claude Code workspace/Claude Code workspace/g; s/Apify workspace/workspace/g' \
  -e 's/apify claude wrapper/workspace claude wrapper/g' \
  -e 's/\bApify\b/the workspace/g' \
  $files
grep -n -i apify $files   # must print nothing
```

The settings file additionally loses the source company's `mcp__*` allow entries, `Bash(vale:*)`, `Bash(brew list:*)`, and the `enableAllProjectMcpServers` and `enabledMcpjsonServers` keys; the patch does this, the sed does not.

The security rule (`security-check.md`) keys on the banner text, and the banner is emitted by `status-banner.sh`, so both must change together. `scripts/test-security.sh` exercises the hooks and the banner and is the check that the substitutions were consistent.

## Verification gate

The snapshot is done when all of these hold on a fresh clone:

1. `grep -ri apify` over the tree matches only this file, the README attribution, and the optional-Actor mentions in the `setup-workspace` skill.
2. Images reviewed by eye for the source company's variable names.
3. `python3 -m unittest discover -s tools/bootstrap/tests -t tools/bootstrap` passes.
4. `bash scripts/test-security.sh` passes.
5. `python3 tools/bootstrap/bootstrap.py settings-sync --check` is clean.
6. `bash scripts/audit.sh` reports nothing beyond the documented example-freshness warning.
7. CI (`security-lint`, `install-verify`) is green.
8. A Cloud environment with `--team root` and a CLI install both start with the `ACTIVE` banner.

## Refreshing the snapshot

Repeat the copy with the allowlist above from a newer commit of the source, re-run the substitutions, redo the hand pass for anything new, and run the gate. Content files (the example company, the setup skills) are not part of a refresh; they belong to this repo.
