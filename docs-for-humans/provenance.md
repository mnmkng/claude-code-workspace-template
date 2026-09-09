# Provenance

This repository is a **snapshot** of the framework layer of Apify's internal Claude Code workspace, cut on September 9, 2026 from commit `cf84749` of that private repository. There is no automatic sync in either direction. It is maintained as time permits; issues and pull requests are welcome and triaged when someone gets to them.

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
tools/bootstrap/  (minus research/ and __pycache__/)
scripts/  .githooks/  .github/
docs-for-humans/how-it-works.md  docs-for-humans/using-the-cli-locally.md
docs-for-humans/building-your-team-folder.md
```

Not copied: the source company's `CLAUDE.md`, `context/`, `departments/`, every other skill and agent, its style rule, its `who-is` data, its screenshots, and internal research fixtures.

## What was transformed

Mechanical, ordered substitutions applied to every copied text file:

| From | To |
|---|---|
| `APIFY_*` environment variables and constants | `WORKSPACE_*` |
| `Apify team security config` (the banner the security rule keys on) | `Workspace security config` |
| `/opt/apify/composed` staging directory | `/opt/claude-workspace/composed` |
| `APIFY-BOOTSTRAP`, `APIFY-CLAUDE-CODE-` marker comments | `WORKSPACE-BOOTSTRAP`, `WORKSPACE-CLAUDE-CODE-` |
| Root sentinel `--team apify` | `--team root` |
| `find_apify_root`, `apify_root` identifiers | `find_workspace_root`, `workspace_root` |
| Repo name and setup-script path | `<your-org>/<your-repo>`, `/home/user/<your-repo>` |
| Prose: "Apify root", "Apify tree", company name in docstrings and test fixtures | workspace root, workspace tree, generic wording |

Then a hand pass over prose: README rewritten, CONTRIBUTING examples generalized, `who-is` documentation and script messages made source-system agnostic, the two import agents told to discover the workspace layout at run time instead of from a hardcoded list, CODEOWNERS reduced to `@TODO-` placeholders, the codeowners-fallback workflow made to read its fallback reviewers from the CODEOWNERS default line, private issue references replaced with a sentence of rationale, and the source company's grandfathered paths removed from `.gitignore`.

### The nine files Claude could not transform

The workspace's own PreToolUse hook refuses to let Claude modify any file whose path ends in a protected name, wherever it lives, copies included. So the nine protected files were carried over byte-identical and de-branded by a human, once, with the same substitutions:

```bash
cd <export-dir>
files=".claude/settings.json .claude/hooks/protect-config.sh .claude/hooks/status-banner.sh \
  .claude/hooks/webfetch-audit.sh .claude/rules/security-check.md scripts/claude.sh \
  scripts/install.sh .githooks/post-checkout .github/workflows/security-lint.yml"
sed -i -E \
  -e 's#/opt/apify/composed#/opt/claude-workspace/composed#g' \
  -e 's/APIFY-BOOTSTRAP/WORKSPACE-BOOTSTRAP/g' \
  -e 's/Apify team security config/Workspace security config/g' \
  -e 's/\bAPIFY_/WORKSPACE_/g' \
  -e 's/find_apify_root/find_workspace_root/g' \
  -e 's/\bAPIFY_ROOT\b/WORKSPACE_ROOT/g' \
  -e "s#bash Apify/scripts/install.sh#bash <your-repo>/scripts/install.sh#g" \
  -e 's/Apify root/workspace root/g; s/Apify tree/workspace tree/g' \
  -e 's/an Apify tree/a workspace tree/g; s/any Apify tree/any workspace tree/g' \
  -e 's#Apify/\.claude/settings\.json#<workspace>/.claude/settings.json#g' \
  -e 's/Apify Claude Code workspace/Claude Code workspace/g' \
  -e 's/the Apify root/the workspace root/g; s/Apify workspace/workspace/g' \
  -e 's/apify claude wrapper/workspace claude wrapper/g' \
  $files
grep -n -i apify $files   # must print nothing
```

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
