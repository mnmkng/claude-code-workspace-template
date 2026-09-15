# Sales

Human orientation for this folder. Claude's entry point is `CLAUDE.md`; this
file is for the person reading the repo.

## What is here

| Path | What it is |
|---|---|
| `CLAUDE.md` | Department context: team structure, metrics, processes, tools, and the context index. Loaded automatically when you work in this folder |
| `context/pricing-and-discounts.md` | List prices, volume tiers, discount authority, margin floors, and the deal desk rule. The single source for all of them |
| `teams/scranton-sales/` | The Scranton branch team: territory, cadence, and local practice |
| `.claude/skills/cold-call-prep/` | Builds a call brief from an account ID |
| `.claude/skills/client-quote/` | Computes a quote and its approver from the pricing tables |
| `.claude/agents/deal-desk-reviewer.md` | Checks a proposed discount before it is submitted |
| `.claude/rules/client-identifiers.md` | Accounts are referenced by ID, never by client name |
| `docs-for-humans/using-the-sales-skills.md` | How to actually use the two skills, with worked examples |
| `projects/` | Your ephemeral working files. Gitignored |

## Start here

- **New to the branch:** read `CLAUDE.md`, then
  `teams/scranton-sales/CLAUDE.md`, then
  `docs-for-humans/using-the-sales-skills.md`.
- **Pricing a deal:** `docs-for-humans/using-the-sales-skills.md` has the
  commands; `context/pricing-and-discounts.md` has the rules behind them.
- **Changing a price or a tier:** open a pull request against
  `context/pricing-and-discounts.md`. The `client-quote` skill reads that file
  at run time, so the change takes effect for everyone the moment it merges.
  Nothing else needs updating, and nothing else should restate those numbers.

## The one rule that bites

**Never write a client's name into a file in this repo.** Use the account ID.
Git keeps history forever, so a name committed once and deleted in the next
commit is still there. The mapping goes in your own gitignored file under
`projects/`. Full rule: `.claude/rules/client-identifiers.md`.

## Who owns what

`context/pricing-and-discounts.md` is owned by the Director of Sales Operations.
The team folders are owned by their regional managers. See `.github/CODEOWNERS`
at the repo root for review routing.
