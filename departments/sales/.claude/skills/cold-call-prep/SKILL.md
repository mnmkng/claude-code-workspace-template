---
name: cold-call-prep
description: >
  Build a call brief before phoning a prospect or a lapsed account. Use when
  asked to prepare for a call, research a prospect before dialling, plan the
  daily call block, or work out what to say to an account that has gone quiet.
  Takes an account ID, a segment, and the last contact, and produces a one-page
  brief with an opener, the questions to ask, and the likely objection.
---

# Cold call prep

Turns three inputs into a brief a representative can work from on the phone.
Built for the branch's daily call block, where the whole point is getting
through a list rather than researching one name for an hour.

## Inputs

| Input | Required | Notes |
|---|---|---|
| Account ID | Yes | `DM-SCR-0412` form. Never the client's name in anything written down - see `.claude/rules/client-identifiers.md` |
| Segment | Yes | Small business, school or county, or regional hospital. Sets the whole shape of the call |
| Last contact | Yes | Date and what happened, or "none" for a cold prospect |
| Known volume or current supplier | No | Sharpens the qualification questions if available |

Ask for any missing required input. Do not guess a segment: the opener, the
questions, and the objection handling are different for each, and a
small-business opener used on a purchasing officer ends the call.

## Procedure

1. **Read the account record in the CRM** for order history, open issues, the
   previous representative's notes, and the closed-lost reason if this is a
   reactivation. If there is no record, say so - a genuinely cold prospect gets a
   different opener from one who has bought before.
2. **Read `references/call-structure.md`**, beside this file, for the call
   shape, the segment-specific openers, the qualification questions, and the
   standard objections with responses.
3. **Check the segment against `context/customers.md`** for who actually decides
   and what they buy on.
4. **Check `context/competition.md`** if the current supplier is known. Never
   open against a competitor; know what to say when the client raises one.
5. **Write the brief** in the shape below.
6. **Do not compute prices in the brief.** A cold call does not carry a quote.
   If the conversation reaches pricing, that is the `client-quote` skill, after
   the volume is established.

## Brief format

```
Account:        DM-SCR-0412
Segment:        Small business
Last contact:   2026-06-04 - quoted, no decision, went quiet
Goal of call:   Book a visit

Opener:         [one or two sentences, segment-appropriate]
Why now:        [the trigger, if there is one]

Ask:
  1. [qualification question]
  2. [qualification question]
  3. [qualification question]

Likely objection: [the one most probable here]
Response:         [from the reference, adapted to this account]

Next step:        [the specific commitment to ask for]
Do not:           [anything the account record warns against]
```

Keep it to one screen. A brief a representative has to scroll through during a
call is a brief they will not use.

## Rules

- **The goal of a cold call is the next step, not the sale.** For small
  business, that is a visit. For the public segment, it is the bid calendar and
  the name of the purchasing officer. For hospitals, it is usually nothing more
  than confirming we are on the approved vendor list.
- **Never open with a discount.** It concedes the price frame, which is the one
  frame where the big-box retailers beat us.
- **Never name another client.** Not as a reference, not as a boast, not as
  local colour.
- **A lapsed account is not a cold call.** Lead with what went wrong, if the
  record says something did. Reactivation is the cheapest win available, and it
  is lost by pretending the history is not there.
- Log the call outcome in the CRM the same day. Friday CRM hygiene is a
  backstop, not the process.
