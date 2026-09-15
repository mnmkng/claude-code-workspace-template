# Workspace edits

Before making structural changes to this workspace (adding files, moving content, creating skills/agents/rules, editing CLAUDE.md files), read `CONTRIBUTING.md` at the relevant root to understand conventions.

Before editing a context file (anything under `context/`, `references/`, or `agent-references/`), read its maintenance header. `edit: upstream` means the file is produced from its sources: do not edit it, fix the source and re-run the process the `sources` entry names, or tell the user where the fix belongs. `edit: here` means edit in place. Never set or move `verified_at` on your own: an edit, an import, or a rewrite is not verification, and the field is the header's one fact that nothing else can reconstruct. Set it to today only when the user states they checked the content against its sources. The one exception is an export: an agent that writes an `edit: upstream` file whole from its source records the export date, because on that day the file *was* the source. Never remove or reorder the header.

Skip this for files inside any `projects/` folder - those are ephemeral workspaces with no conventions.
