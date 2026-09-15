---
sources:
  - "The CRM: account records, segment field, closed-won and closed-lost reasons"
  - "Quarterly branch account reviews, Scranton and Utica"
  - "Customer service: order support and complaint queue themes"
owner: Jan Levinson
edit: here
review_every: 90d
verified_at: 2026-09-15
---
# Clients

Who buys from Dunder Mifflin, why they buy, and how we serve them after they do.
Figures cited here come from `context/key-metrics.md` with their as-of dates.

## Segments

| Segment | Typical annual spend | Share of revenue | Who decides | Buying rhythm |
|---|---|---|---|---|
| Small business | $5K-$60K | 44% | Owner, office manager | Reorders when stock runs low; no calendar |
| Schools and counties | $40K-$400K | 38% | Purchasing officer, under a bid or contract | Annual bid cycle, heavy August and January |
| Regional hospitals | $80K-$500K | 18% | Supply chain manager, group purchasing agreement | Quarterly schedule, strict on substitutions |

Named clients are never written into committed files. Sales work references
accounts by account ID; see `.claude/rules/client-identifiers.md` under
`departments/sales/`.

### Small business

Law firms, accountants, insurance brokers, medical and dental practices, print
shops, church offices, and light manufacturing across Lackawanna County and the
surrounding area. They are price-aware but not price-driven: what they actually
buy is not running out of paper on a Thursday afternoon.

This is the segment the big-box retailers serve worst - too small for a national
account team, too big to be happy buying by the ream at retail. It is our
highest-margin business and the first pillar of company strategy.

### Schools and counties

Public school districts, Lackawanna County offices, municipal administration,
and community colleges. Buying is formal: an annual bid, a published spec, a
contract term of one to three years, and a purchasing officer who cannot accept
a discount that was not in the bid.

Long cycles (median 94 days, as of Q2 2026) and low churn once won. Renewal risk
is almost entirely a re-bid, not dissatisfaction. Losing one is losing it for the
whole term, which is why bid deadlines are treated as immovable.

### Regional hospitals

Hospital systems in the Scranton and Utica areas, buying under a group
purchasing agreement that sets the price envelope before we are in the
conversation. The work is compliance and reliability: exact stock codes, no
substitutions without written approval, documented delivery windows, and
invoices that match the purchase order line for line.

Lowest margin, highest volume, and the least tolerant of an operational mistake.
One wrong substitution costs the account.

## Buying journey

| Stage | What happens | Who owns it | Typical duration |
|---|---|---|---|
| Trigger | Price rise from an incumbent, a service failure, a new office, or a bid opening | - | - |
| First contact | Cold call, referral, or an inbound Infinity sign-up | Sales representative | 1 call |
| Needs and volume | Establish grades, monthly volume, delivery constraints, current pricing | Sales representative | 1-2 visits |
| Quote | Priced from the volume tiers; deal desk review if it crosses a threshold | Sales representative, deal desk | 2-5 days |
| Sample or trial order | A single delivery at quoted terms; the moment most deals are actually won | Sales representative, warehouse | 1-2 weeks |
| Contract or bid award | Signature, or a bid award for the public segment | Sales representative, regional manager | 1 week to 3 months |
| Onboard | Account set up in the CRM, Infinity login issued, standing order built | Customer service | 1 week |
| Reorder and review | Standing order runs; quarterly check-in on volume and pricing | Sales representative | Ongoing |

Two things decide most deals. The first is the trial delivery arriving complete
and on time. The second is whether the buyer can reach their representative
directly when something goes wrong - which is the difference the big-box
retailers cannot match.

## Personas

### The office manager

Runs a 12-to-40-person office and owns supplies among eight other
responsibilities. Buys on convenience and reliability; will pay a few percent
over retail to stop thinking about paper. Wants one phone number, a standing
order, and no surprises on the invoice.

Reached by phone during business hours. Does not read marketing email. Responds
to a representative who already knows the office's usual order.

### The purchasing officer

Manages public procurement for a district or county. Bound by a bid process and
audited on it. Cannot take a discount outside the published terms and will not
accept a quote that does not match the spec line for line.

Wants compliance, a clean bid response, and delivery that does not generate
complaints from the schools. Personal relationship matters for renewal, but
cannot override the process.

### The supply chain manager

Manages inbound supply for a hospital system under a group purchasing
agreement. Measures vendors on fill rate, substitution rate, and invoice
accuracy, and reports those numbers upward.

Not open to a relationship sale. Open to a vendor who makes their scorecard look
good. Escalates in writing, and expects a written answer.

## Service model

- **Every account has a named representative.** Not a queue, not a pool. The
  representative is on the invoice, the Infinity account, and the delivery note.
- **Customer service owns everything after the order is placed**: order status,
  returns, damaged deliveries, and the Infinity help queue. Sales owns pricing
  and the relationship.
- **Escalation is one step.** Representative, then regional manager. There is no
  tier two to hide behind.
- **Delivery commitment is next day** for stocked items ordered before 3 p.m.
  ET, within the branch's delivery radius. The rate is reported monthly; see
  `context/key-metrics.md`.
- **Quarterly account review** on accounts over $25K a year: volume against
  contract, price against tier, and anything the client is buying elsewhere.
- **Substitutions are never made silently.** Hospitals require written approval;
  every other segment gets a phone call before the truck is loaded.

## Why clients leave

Ranked by closed-lost and churn reasons in the CRM, trailing 12 months (as of
August 2026):

1. Price, after a big-box retailer quoted a headline rate on one grade.
2. A service failure - a missed delivery or a wrong substitution - not
   recovered fast enough.
3. Lost a re-bid on a public contract.
4. The client closed, merged, or moved out of the delivery radius.

Only the first two are ours to fix, and the second is the one that actually
loses accounts we wanted to keep.
