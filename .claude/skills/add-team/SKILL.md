---
name: add-team
description: >
  Create a new department or team folder in this workspace, with its CLAUDE.md,
  projects folder, CODEOWNERS line, and security settings stamp. Use when asked
  to add a department, add a team, create a team folder, set up a space for a
  new function, or when the user runs /add-team. Asks for the name, the owner,
  and the tools, then runs the scaffold and reports the paths it created.
---

# Add a team

Four questions, then one command. Use AskUserQuestion for the first; the rest
are free text. Write nothing until the dry run has passed.

## 1. Department or team

> Is this a new department, or a team inside an existing one?

Options: **Department** (`departments/<name>/`) / **Team inside a department**
(`departments/<dept>/teams/<name>/`).

If team: ask which department, and check it exists. Offer the list from
`ls departments/`.

A team gets its own folder only when its processes, tools, and metrics differ
enough from its department's that folding them into the department's
`CLAUDE.md` would make it unwieldy. If they do not, the department's folder
already covers it - say so and stop. CONTRIBUTING "Knowledge hierarchy depth".

## 2. Name

> What should the folder be called? Kebab-case, lowercase - "Customer Success"
> becomes `customer-success`.

The name must be **globally unique** among folders that contain a `CLAUDE.md`,
anywhere in the workspace: cloud team resolution keys on the basename, so two
teams called `content` in different departments cannot both exist. Check
before going further:

```bash
git ls-files '*CLAUDE.md' | xargs -n1 dirname | xargs -n1 basename | sort | uniq -d
git ls-files '*CLAUDE.md' | grep -i '/<name>/CLAUDE.md$'
```

If the name is taken, say where, and ask for one that is not. A qualified name
(`east-sales` rather than `east`) is usually the fix.

## 3. Owner

> Which GitHub handle reviews changes to this folder? It goes in CODEOWNERS.

For a team, the department's own owner is added as a second owner
automatically - GitHub never requests a review from the PR author, so a team
lead's own pull request would otherwise request nobody.

A handle without write access on the repo is silently ignored by GitHub. So is
a `@TODO-...` placeholder, which is a fine answer when the real one is not
settled.

## 4. Tools

> Which systems does this team work in day to day?

Optional. They become a table in the "Tools and systems" section with a
`[TODO]` against each; an empty answer leaves a `[TODO]` for the whole section.

## Run it

Write the spec to a gitignored `projects/` path, dry-run it, then apply:

```bash
cat > projects/add-team-spec.json <<'JSON'
{
  "departments": [
    {"name": "<dept>", "owner": "@<dept-owner>", "tools": [],
     "teams": [{"name": "<team>", "owner": "@<team-owner>", "tools": ["<tool>"]}]}
  ]
}
JSON
python3 tools/bootstrap/bootstrap.py scaffold --spec projects/add-team-spec.json --dry-run
python3 tools/bootstrap/bootstrap.py scaffold --spec projects/add-team-spec.json
```

For a new **department**, the spec has one entry and no `teams`. For a **team**
inside an existing department, the entry names the existing department with the
new team under it: the scaffold leaves the department's own files alone and
adds only the team. It never overwrites and never deletes.

If the dry run refuses, fix the spec and run it again - it refuses before
writing anything, so there is nothing to undo.

## Report back

Print the created paths, then:

- The `[TODO]` sections in the new `CLAUDE.md` are the next job. A folder of
  empty headings is context Claude loads and learns nothing from.
- How to grow the folder - context files, skills, agents, human docs:
  `docs-for-humans/building-your-team-folder.md`.
- The new folder carries its own security settings stamp, so a Desktop session
  opened there loads the policy. For a Cloud environment scoped to this team,
  the setup script's `--team` is the folder's basename.
- The change is staged, not committed. Offer to commit it on a branch.
