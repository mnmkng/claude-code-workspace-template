---
name: client-quote
description: >
  Compute a client quote from the published volume tiers and report which
  approver it needs. Use when asked to price an order or a contract, work out a
  discount, check whether a proposed price clears the margin floors, or find out
  who has to sign a quote off and whether it goes to the deal desk. Reads the
  live pricing tables rather than remembered numbers.
---

# Client quote

Produces a priced quote from `departments/sales/context/pricing-and-discounts.md`:
the tier discount for the account's committed volume, the negotiated discount on
top of it, the blended margin, the approver the quote needs, and every deal desk
condition that fires.

**Always run the script. Never price a quote by hand.** The list prices move
when mill prices move and the tiers change with the authority matrix; the script
reads both out of the pricing file at run time, so it cannot drift from the
published tables the way a remembered number does.

## Running it

```bash
python3 departments/sales/.claude/skills/client-quote/scripts/quote.py \
  --volume 1200 --negotiated 6 --term 24 --role "Sales Representative" \
  --line P-STD-L:40 --line P-PRM-L:10
```

| Flag | Meaning |
|---|---|
| `--line CODE:QTY` | One quote line, repeatable. `--list-items` prints the codes |
| `--volume CASES` | **Committed annual volume in cases**, which sets the tier |
| `--negotiated PCT` | Negotiated discount on top of the tier discount. Default 0 |
| `--term MONTHS` | Contract term. Default 12 |
| `--role` | The quoting representative's role, to check it against their authority |
| `--list-items` | Print the item codes, units, and list prices |

Exit codes: 0 a quote was produced, 1 bad input, 2 the pricing file could not be
read. On 2, stop and say so - do not fall back to quoting from memory.

## Gathering the inputs

Ask for anything missing rather than assuming it. Two inputs are got wrong
often:

- **`--volume` is committed annual volume across the whole contract, not the
  quantity on this order.** A single 400-case order from an account that commits
  to 6,000 cases a year is T4. An account placing one 400-case order and
  committing to nothing is T0. Getting this wrong is the most common way a quote
  goes out at a price we then have to defend at renewal.
- **`--role` is the role of the person quoting**, so the script can say whether
  the discount is inside their own authority or escalates. Look the role up with
  the `who-is` skill if only a name is known.

Supplies and printer placements are not in the list price table. They are quoted
from the catalog and the placement agreement, and are added to the quote outside
this script.

## Reading the output

- **Approver needed** is the lowest role on the authority table that can sign
  the negotiated discount. Name that person on the quote before it goes out. An
  unapproved quote in a client's hands is a price we have effectively offered.
- **Deal desk** fires on conditions 1 to 4, which the script can compute.
  Conditions 5 and 6 - a price held flat over 12 months, and any public bid -
  depend on contract history and bid status, so the script prints them as a
  by-hand check every time. **Every public bid goes to the deal desk regardless
  of what the script says.**
- **Blended margin** is computed across the whole quote. A paper-only quote has
  nowhere to recover paper margin from, which is why quoting the whole basket is
  a pricing decision and not just an upsell.

## After the quote

- Reference the account by account ID, never by client name, in anything written
  to a tracked file. See `.claude/rules/client-identifiers.md`.
- For a discount that needs a second opinion before submission, the
  `deal-desk-reviewer` agent checks it against the same rules and says what is
  likely to come back. It is advisory and approves nothing.
- If a price in the pricing file looks wrong, raise it with the Director of
  Sales Operations, who owns the file. Do not edit the table to make a quote
  work.
