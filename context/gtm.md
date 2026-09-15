---
sources:
  - "The CRM: pipeline stages, activity, closed-won and closed-lost reasons"
  - "The BI tool: order, delivery, and Infinity dashboards"
  - "Corporate finance: monthly close, branch profit-and-loss pack"
  - "Quarterly branch account reviews, Scranton and Utica"
owner: Jan Levinson
edit: here
review_every: 90d
verified_at: 2026-09-15
---
# Go to market

How Dunder Mifflin finds, wins, and keeps accounts. Segment detail is in
`context/customers.md`, competitive positioning in `context/competition.md`, and
every figure in `context/key-metrics.md`.

## Business model

Distribution. We buy paper from mills and supplies from converters and
manufacturers, hold inventory in branch warehouses, and resell to organizations
in a delivery radius around each branch.

| Element | How it works |
|---|---|
| Revenue | Product sale at a contracted or quoted price, recognized on delivery |
| Cost of sales | Mill and supplier cost, inbound freight, warehouse handling, last-mile delivery |
| Gross margin | 27.4% blended; 19.1% on paper, 38.6% on supplies and printer service (as of August 2026) |
| Fixed cost | Branch lease, warehouse, delivery fleet, salaried staff |
| Variable cost | Sales commission, fuel, seasonal warehouse labor |
| Cash cycle | Inventory held ~30 days, receivables 41 days (as of August 2026) |

The economics are volume times spread, with fixed branch cost underneath. That
shape has three consequences that drive every decision here: incremental volume
on an existing delivery route is close to pure margin; a discount is permanent
and compounds across the contract term; and an account lost is a route that
still costs what it cost yesterday.

## Sales motion

Relationship sales, run by a representative who owns a named book of accounts.
No inbound marketing engine, no lead scoring, no marketing department.

| Motion | Segment | What it looks like | Who runs it |
|---|---|---|---|
| Cold call | Small business | Phone prospecting from a territory list; the volume activity of the branch | Sales representatives |
| Client visit | All | In-person, at the client's office; needs discovery and relationship maintenance | Sales representatives |
| Bid response | Schools and counties | Formal response to a published bid, on deadline, to spec | Representative with the regional manager |
| Referral | Small business | An existing client introduces a neighbor, a tenant, or an affiliate | Sales representatives |
| Reactivation | All | A lapsed account, worked from order-history decay in the CRM | Sales representatives |
| Attach and expand | All | Supplies and printer placement into an existing paper account | Sales representatives |

**Cold calling is the engine of the small-business segment.** It is unglamorous,
it is the activity most likely to be skipped, and the branch's new-account
number tracks it directly. The branch expectation is a daily call block; see the
Scranton sales team folder for the local cadence.

**Visits are how deals close.** The median small-business deal takes one or two
visits after the first call. A quote sent without a visit closes at roughly half
the rate - a number worth knowing before deciding a visit is not worth the
drive.

**Bids are won on process, not on selling.** A bid that misses the deadline or
misses the spec is not a near miss; it is not a bid. Public work runs on a
calendar that does not move.

## Channels

| Channel | Role | Share of new accounts |
|---|---|---|
| Outbound calling | Primary acquisition, small business | 46% |
| Referral | Highest-converting; lowest volume | 21% |
| Bid and contract award | Only route into the public segment | 18% |
| Inbound to the branch or Infinity sign-up | Small, growing with Infinity | 11% |
| Reactivation | Cheapest win available | 4% |

Shares are as of Q2 2026 and count new accounts, not revenue; bid awards are a
fifth of the count and considerably more of the dollars.

## Growth flywheel

1. A representative wins a small-business account on service, not price.
2. The trial delivery lands complete and on time, so the account stays.
3. The account gets an Infinity login and a standing order, so reordering stops
   being a decision.
4. Predictable volume raises route density, which lowers delivery cost per
   order on a route we were already driving.
5. The representative attaches supplies and, in the best case, places a printer
   - which is the strongest retention signal in the CRM.
6. A happy account refers a neighbor, and referral is the highest-converting
   channel we have.
7. Higher retention and better route economics fund the headcount to call more
   prospects, and it runs again.

Where it breaks, in order of how often: at step 2, when a delivery goes wrong
and is not recovered; at step 3, when nobody sets up the standing order; and at
step 5, when the representative sells paper and never revisits the basket.

## Operational KPIs

Weekly at branch level, monthly with corporate. These are operating measures;
the four company KPIs are in the root `CLAUDE.md`.

| KPI | Current | Target | As of |
|---|---|---|---|
| New accounts won per quarter, Scranton | 27 | 32 | Q2 2026 |
| Average order value | $1,240 | $1,350 | August 2026 |
| Average annual account value | $30,700 | $33,000 | August 2026 |
| Net revenue retention | 97% | 102% | August 2026 |
| Gross margin, blended | 27.4% | 28.5% | August 2026 |
| Next-day delivery rate, Scranton | 96% | 98% | August 2026 |
| Days sales outstanding | 41 days | 35 days | August 2026 |

## What we do not do

Written down because each one is proposed roughly once a year:

- **No national accounts.** They are bid on price against distributors with a
  cost base we cannot match, and they break the delivery model.
- **No manufacturing or converting in-house**, beyond the custom cutting the
  Scranton warehouse already does.
- **No retail storefront.** It competes with the branch's own delivery business
  at a worse margin.
- **No marketing-led demand generation.** Nothing in the acquisition data says
  it would outperform another representative making calls.
- **No price matching as policy.** A match on request teaches every account to
  request one.
