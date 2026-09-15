---
sources:
  - "The product catalog: list price per case, updated on each mill price change"
  - "Corporate sales operations: discount authority matrix and the deal desk rule"
  - "Corporate finance: margin floors by line"
owner: Charles Miner
edit: here
review_every: 90d
verified_at: 2026-09-15
---
# Pricing and discounts

The list price structure, who may discount and by how much, and when a quote has
to go to the deal desk before it reaches the client. This file is the single
source for all three, for both branches.

The `client-quote` skill computes quotes by reading the two tables below, so a
correction made here changes what the skill produces. Do not copy these numbers
into another file.

## List price structure

List price is per case, delivered within the branch radius. A case is 10 reams
unless the packaging column in `context/product.md` says otherwise.

| Code | Item | Unit | List price |
|---|---|---|---|
| P-STD-L | Standard copy, 20 lb, letter | case | $38.50 |
| P-STD-G | Standard copy, 20 lb, legal | case | $46.20 |
| P-PRM-L | Premium copy, 24 lb, letter | case | $52.75 |
| P-BND-L | Bond, 24 lb, letter | case | $61.40 |
| P-CVR-65 | Cover stock, 65 lb | pack | $28.90 |
| P-CBL-3 | Carbonless, 3 part | case | $94.10 |
| P-CNT-15 | Continuous forms, 15 lb | case | $71.30 |
| P-REC-30 | Recycled, 20 lb, 30% post-consumer | case | $41.80 |
| P-REC-100 | Recycled, 20 lb, 100% post-consumer | case | $49.60 |

Prices are as of August 2026 and move when mill prices move. Supplies and
printer placements are not priced from this table; they are quoted from the
catalog and the placement agreement.

**The list price is a real price.** It is what an account with no volume
commitment pays, and a quarter of small-business accounts pay it. It is not an
opening position.

## Volume tiers

Tier is set by **committed annual volume in cases across the whole contract**,
not by the size of a single order. The tier discount applies to every paper line
on the quote.

| Tier | Committed annual volume (cases) | Tier discount |
|---|---|---|
| T0 | 0-99 | 0% |
| T1 | 100-499 | 4% |
| T2 | 500-1,999 | 8% |
| T3 | 2,000-4,999 | 12% |
| T4 | 5,000+ | 15% |

A one-time order does not earn a tier. An account that commits to T2 and buys at
T0 volume is repriced at the next quarterly account review, which is what the
review is for.

## Discount authority

Authority is over the **negotiated discount**: anything on top of the tier
discount the account has already earned. The approver must be named on the quote
before it goes to the client.

| Role | Negotiated discount, up to |
|---|---|
| Sales Representative | 5% |
| Assistant to the Regional Manager | 8% |
| Regional Manager | 12% |
| Director of Sales Operations | 18% |
| Vice President, Northeast Sales | above 18% |

Authority does not stack and is not delegated. A representative who needs 7%
takes it to the Assistant to the Regional Manager; they do not take 5% and ask a
colleague for the rest.

## Cost basis

Used to check a quote against the floors below. Cost is landed cost: mill or
supplier price plus inbound freight and warehouse handling.

| Line | Cost as a share of list |
|---|---|
| Paper | 68% |

Paper therefore carries 32% gross margin at list price. The 19.1% paper margin
reported in `context/key-metrics.md` is the achieved figure across the whole
book, after the tier and negotiated discounts actually granted - the two are not
the same number and neither is wrong.

## Margin floors

| Line | Floor |
|---|---|
| Paper | 14% |
| Supplies | 25% |
| Printer placement and service | 30% |
| Blended, whole quote | 18% |

A quote below a floor is not approved by anyone on the authority table. It goes
to the Vice President, Northeast Sales, with a written reason, or it is not sent.

## The deal desk rule

**Any quote that meets one or more of these conditions goes to the deal desk
before it reaches the client:**

| # | Condition | Threshold |
|---|---|---|
| 1 | Total discount - tier plus negotiated - above | 20% |
| 2 | Negotiated discount above the branch approval ceiling | 12% |
| 3 | Blended gross margin below | 18% |
| 4 | Contract term longer than | 24 months |
| 5 | A price held flat for longer than | 12 months |
| 6 | A public bid of any size, because the price cannot be revised after award | always |

The **branch approval ceiling** in condition 2 is the Regional Manager's
authority. Below it, a discount above a representative's own limit is an
ordinary escalation up the authority table, not a deal desk submission. Above
it, no one at the branch can sign.

The deal desk is the Director of Sales Operations, with the Vice President,
Northeast Sales, on anything above 18% negotiated discount. Turnaround is two
business days; a bid deadline inside that window is escalated by phone, not by
waiting.

**What the deal desk is for.** A discount does not expire. It sets the price the
account expects at renewal, and the renewal after that. The review exists so
that a concession made to close one quarter is a decision somebody made on
purpose, with the term and the margin in front of them.

**What it is not for.** It does not second-guess the relationship, it does not
require a representative to justify the account, and it is not a rejection
queue. Most submissions come back approved with the term shortened.

## Working practice

- Compute quotes with the `client-quote` skill rather than by hand. It reads the
  tables above, applies the tiers, and tells you which approver the quote needs
  and whether the deal desk is involved.
- Quote the whole basket. A paper-only quote invites a paper-only comparison,
  which is the frame we lose in - see `context/competition.md`.
- Name the approver on the quote. An unapproved quote in a client's hands is a
  price we have effectively offered.
- Reference accounts by account ID, never by client name, in anything committed
  to this repo. See `.claude/rules/client-identifiers.md`.
