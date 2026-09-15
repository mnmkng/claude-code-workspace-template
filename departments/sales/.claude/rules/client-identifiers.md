---
paths:
  - "departments/sales/**"
---

# Client identifiers

**Reference every client by account ID in anything committed to this repo.
Never by client name.**

Account IDs look like `DM-SCR-0412` (branch prefix, then the CRM account
number): `SCR` for Scranton, `UTC` for Utica.

## What this means in practice

| Instead of | Write |
|---|---|
| "Lackawanna County Clerk's Office is up for re-bid" | "`DM-SCR-0118` is up for re-bid" |
| "the dental practice on Adams Avenue" | "`DM-SCR-0407`" |
| "Prince Family Paper took the Riverside district" | "we lost `DM-SCR-0233` to Prince Family Paper" |

The rule covers everything tracked in git under `departments/sales/`: context
files, `CLAUDE.md`, skill references, agent files, notes, and commit messages.
It also covers derived detail that identifies an account as surely as its name
would - a street address, a named contact, or a description specific enough that
one account matches it.

## Where the mapping lives

Account ID to client name is in the CRM, which is the system of record.

For local work, keep a scratch mapping in your own gitignored file under
`departments/sales/projects/` - for example
`departments/sales/projects/account-map.local.md`. Everything under `projects/`
is gitignored, and the `.local.` marker is ignored a second way, so the file
cannot be committed by accident.

**Never move that file out of `projects/`**, never commit it, and never paste
its contents into a file that is tracked.

## Why

Two reasons, and the second is the one that bites:

1. This repo is read by people who do not work these accounts. Client names,
   contract terms, and buying patterns are confidential to the client
   relationship - see `.claude/rules/data-sensitivity.md`.
2. Git keeps everything. A client name committed once and deleted in the next
   commit is still in the history, permanently, and removing it means rewriting
   the history of a shared branch.

## Working with a named account

Named clients come up constantly in a session - that is fine and expected. Use
the name in conversation, and write the account ID when something is written to
a tracked file. If the account ID is not known, ask for it rather than
substituting the name.

Competitors are not clients: `context/competition.md` names fictional
competitors on purpose. This rule is about accounts we sell to.
