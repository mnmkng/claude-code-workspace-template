# Sales context

Sales covers both branches. Scranton and Utica run the same process, the same
price list, and the same approval chain; they differ in territory and cadence,
which live in the team folders.

## Team structure

| Role | Count | Reports to |
|------|-------|------------|
| Vice President, Northeast Sales | 1 | Chief Executive Officer |
| Director of Sales Operations | 1 | Vice President, Northeast Sales |
| Regional Manager | 2 | Vice President, Northeast Sales |
| Assistant to the Regional Manager | 1 | Regional Manager, Scranton |
| Sales Representative | 10 | Their Regional Manager |
| Traveling Sales Representative | 2 | Vice President, Northeast Sales |

Counts are as of August 2026. Names and reporting lines come from the `who-is`
skill, not from this table.

The traveling representatives carry no branch territory and no chat team. They
work named prospects across the Northeast and report to corporate, so branch
cadence and territory rules do not apply to them.

## Key metrics

Sales owns two of the four company KPIs - branch revenue and client retention -
plus the operating measures below. Every figure here is the one in
`context/key-metrics.md`; cite it with its as-of date.

| Metric | Current | Target | As of |
|---|---|---|---|
| Revenue, Scranton | $12.4M | +6% year over year | August 2026 |
| Revenue, Utica | $9.1M | +6% year over year | August 2026 |
| Client retention, gross logo | 91% | 93% | August 2026 |
| New accounts won per quarter, Scranton | 27 | 32 | Q2 2026 |
| Average annual account value | $30,700 | $33,000 | August 2026 |
| Gross margin, blended | 27.4% | 28.5% | August 2026 |
| Median sales cycle, small business | 21 days | - | Q2 2026 |
| Median sales cycle, county and school district | 94 days | - | Q2 2026 |

## Processes

Both branches run these unchanged. Branch-specific cadence lives in the team
folders.

### Prospect to quote

1. Qualify on the call: segment, current supplier, approximate annual volume,
   delivery constraints. Use the `cold-call-prep` skill to build the brief
   first.
2. Visit before quoting on anything above $25K a year. Quotes sent without a
   visit close at roughly half the rate.
3. Build the quote with the `client-quote` skill. It reads the tier table and
   returns the approver the quote needs.
4. Get the named approval before the quote leaves. An unapproved quote in a
   client's hands is a price we have offered.
5. Deal desk review if the quote trips any of the six conditions in
   `context/pricing-and-discounts.md`. Two business days.
6. Trial delivery where the client will take one. It is where most deals are
   actually decided.

### Bid response

Public bids are a separate process and a hard calendar. The regional manager
signs off on every bid before submission, and every bid goes to the deal desk
regardless of size, because the price cannot be revised after award. A bid that
misses the deadline or the spec is not a near miss.

### Quarterly account review

Every account over $25K a year, every quarter, run by the owning representative
with their regional manager: volume against commitment, price against tier,
supplies attach, printer placement, and anything the client is buying elsewhere.
This is the control that keeps long-held accounts from going unreviewed - see
the Michael Scott Paper Company section of `context/competition.md` for why it
exists.

### Handover and coverage

An account belongs to Dunder Mifflin, not to a representative. Account history,
pricing, contacts, and open issues live in the CRM. A representative who is out
is covered by name, and coverage is expected to know the account from the record
rather than from a phone call.

### Escalation

Representative, then regional manager. One step. Pricing exceptions go to the
deal desk; service failures go to customer service with the representative
staying on the account.

## Tools and systems

| System | Used for | Notes |
|---|---|---|
| The CRM | Accounts, contacts, pipeline, activity, closed-lost reasons | System of record for everything about an account |
| Infinity | Client ordering, contract pricing, order history | Representatives see what the client sees |
| The BI tool | Order and delivery dashboards, Infinity adoption | Read-only for the branch |
| The product catalog | Stock codes, packaging, availability | Source of the list prices in the pricing file |
| `client-quote` skill | Computing a quote and its approver from the tier table | Reads `context/pricing-and-discounts.md` directly |
| `cold-call-prep` skill | Building a call brief from an account ID | |
| `deal-desk-reviewer` agent | Checking a proposed discount against the rules before submitting | Advisory; it does not approve |

## Teams

| Team | Folder | Scope |
|---|---|---|
| Scranton sales | `teams/scranton-sales/` | Lackawanna County and the Scranton delivery radius |
| Utica sales | Not yet created | Utica delivery radius; runs department process unchanged |

## Context index

| Topic | Key content | File path |
|---|---|---|
| Pricing and discounts | List price structure, volume tiers, discount authority, margin floors, the deal desk rule | `context/pricing-and-discounts.md` |
