# Using the sales skills

A walkthrough of the two sales skills, with worked examples. This is a human
doc - Claude does not load it. The skills' own `SKILL.md` files are what it
reads.

Both skills load automatically when you work anywhere under
`departments/sales/`. On the CLI that means starting Claude from this folder or
below; in a cloud session it means the environment was set up with
`--team sales` or `--team scranton-sales`.

## Before your call block: `cold-call-prep`

Ask for a brief in plain language. You do not need to invoke the skill by name.

```
Prep me for a call to DM-SCR-0412. Small business, last contact June 4 -
we quoted and they went quiet.
```

Claude reads the account record, the call structure reference, and the segment
notes, and gives you a one-screen brief: opener, three questions, the likely
objection, and the next step to ask for.

**Prepping a whole block at once** works better than one at a time:

```
Here are today's six calls, all small business, all cold:
DM-SCR-0455, DM-SCR-0461, DM-SCR-0462, DM-SCR-0470, DM-SCR-0471, DM-SCR-0478.
Give me one brief each, shortest useful form.
```

Three things to know:

- **Give it the segment.** It will ask if you leave it out, because a
  small-business opener used on a purchasing officer ends the call.
- **A lapsed account is not a cold call.** Say what happened last time. The
  brief will lead with it, which is the whole point of reactivation.
- **No prices.** The brief will not carry a quote and should not. Pricing comes
  after volume is established, which is the other skill.

## Pricing a deal: `client-quote`

Ask in plain language, or run the script yourself:

```
Quote 40 cases of standard letter and 10 of premium letter for an account
committing to 1,200 cases a year. I'm a sales rep, 24-month term, and they
want 6% off.
```

```bash
python3 departments/sales/.claude/skills/client-quote/scripts/quote.py \
  --volume 1200 --negotiated 6 --term 24 --role "Sales Representative" \
  --line P-STD-L:40 --line P-PRM-L:10
```

Both give you the same thing: the tier, the total discount, the blended margin,
the approver the quote needs, and any deal desk condition that fires.

`--list-items` prints the item codes if you do not have them to hand.

### The input people get wrong

`--volume` is **committed annual volume in cases across the whole contract**,
not the quantity on this order.

| Situation | `--volume` |
|---|---|
| One 400-case order, no commitment | `400`, which lands in T1 |
| 400-case order, account commits to 6,000 cases a year | `6000`, which is T4 |
| Renewal at the same volume as last year | Last year's actual, not the contract's optimistic number |

Get this wrong upward and you quote a price the account has not earned, which
you then defend at every renewal.

### Reading the result

- **Approver needed** is the lowest role that can sign. Put that person's name
  on the quote before it leaves. An unapproved quote in a client's hands is a
  price we have effectively offered.
- **Deal desk** fires on the four conditions the script can compute. It always
  prints the two it cannot - a price held flat over 12 months, and a public bid
  - as a by-hand check. **Every public bid goes to the deal desk**, whatever the
  script says.
- **Blended margin below the floor** on a paper-only quote is usually a signal
  to quote the basket, not to ask for an exception.

### Checking a discount before you submit it

The `deal-desk-reviewer` agent runs the same checks and tells you what a
submission is likely to come back with:

```
Use deal-desk-reviewer on this: DM-SCR-0233, 6,000 cases committed,
36-month term, they're asking for 14% off on top of tier.
```

It approves nothing. Approval is a named person on the authority table.

## Changing the pricing

The skill has no numbers of its own. It parses the tables in
`departments/sales/context/pricing-and-discounts.md` every time it runs, so:

- Correcting a list price, a tier, an authority limit, a margin floor, or a deal
  desk threshold is a pull request against that one file.
- The moment it merges, every quote anyone computes uses the new number.
- Do not copy a price into a deck, a skill, or another context file. The point of
  the arrangement is that there is exactly one place to change.

If the script exits with code 2, it could not find or read the pricing file.
Fix that rather than quoting from memory - an unreadable pricing file is
precisely when remembered numbers are most likely to be stale.

## Reminder about client names

Everything committed under `departments/sales/` uses account IDs. Keep your own
ID-to-name mapping in a gitignored file under `departments/sales/projects/`, for
example `account-map.local.md`. Use client names freely in conversation with
Claude; just do not let one get written to a tracked file.
