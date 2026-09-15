# Dunder Mifflin Paper Company

## Company overview

Dunder Mifflin is a regional distributor of paper and office supplies to small
and mid-sized organizations in the Northeast United States. Founded 1949.
Corporate is in New York; this workspace covers the **Scranton branch**
(Pennsylvania) and the **Utica branch** (New York), which share a sales
leadership line and a warehouse network.

We are a distributor, not a manufacturer. We buy from paper mills and supply
converters and resell with delivery, service, and account management attached.
That is the whole business model: the paper is a commodity, and everything we
charge a premium for sits around it.

Trailing-twelve-month revenue across the two branches is **$21.5M** (as of
August 2026). Headline figures live in `context/key-metrics.md`.

## What we sell

| Line | What it covers | Share of revenue |
|---|---|---|
| Paper | Cut-sheet copy paper, bond, cover stock, carbonless, continuous forms | 61% |
| Office supplies | Toner, filing, writing instruments, breakroom, janitorial | 24% |
| Printers and service | Multifunction printer placement, supplies contracts, on-site service | 11% |
| Delivery and other | Expedited delivery, custom converting, storage | 4% |

Detail in `context/product.md`. Shares are as of August 2026.

## Strategic pillars

1. **Win the small-business segment the big-box retailers ignore.** Accounts
   spending $5K-$250K a year are too small for a national contract and too big
   to be served well by a retail store. That band is where we win, and it is
   where almost all of our margin comes from.
2. **Personal service is the moat.** Every account has a named representative
   who answers the phone. Price is matchable; a rep who knows the account's
   print schedule is not. We defend deals with service, not discounts.
3. **Move volume to Infinity.** Dunder Mifflin Infinity is the ordering
   platform. Orders placed through it cost us less to process, reorder more
   predictably, and churn less. The goal is to raise the share of orders placed
   through Infinity without removing the phone, which is what the moat is made
   of.

## Strategic KPIs

Reviewed monthly by corporate; each branch is measured on all four.

| KPI | Current | Target | As of |
|---|---|---|---|
| Branch revenue, trailing 12 months | $12.4M Scranton / $9.1M Utica | +6% year over year | August 2026 |
| Client retention, gross logo, trailing 12 months | 91% | 93% | August 2026 |
| Warehouse recordable safety incidents, trailing 12 months | 2 | 0 | August 2026 |
| Infinity order share | 38% | 55% by Q4 2027 | August 2026 |

## Core values

- **Answer the phone.** A client who cannot reach a person has already started
  shopping.
- **Quote what the account is worth, not what the deal is worth.** Discounts are
  permanent; a one-time win at a bad price sets the renewal price.
- **The warehouse is a workplace, not a cost line.** Safety decisions are not
  traded against delivery windows.
- **Say the real number.** Internal forecasts, pipeline, and inventory counts
  are reported as they are, including when they are bad.
- **Small enough to know the client.** Growth that costs us the ability to name
  an account's buyer is growth we do not want.

## Organization

| Function | Where it sits | Leadership |
|---|---|---|
| Sales | Scranton and Utica branches, under corporate sales | Vice President, Northeast Sales |
| Accounting | Scranton branch, plus corporate finance | Chief Financial Officer |
| Warehouse | Scranton and Utica | Branch warehouse managers |
| Customer service | Scranton | Customer Service Manager |
| Human resources | A representative sits in Scranton and reports to corporate | Director of Human Resources |
| Quality assurance | Scranton, covering supplier and inbound stock quality | Quality Assurance Director |

Look up any individual with the `who-is` skill rather than from memory; names,
titles, and reporting lines are in its data file, not in this document.

## Context index

Read these on demand. Do not load them all.

| Topic | Key content | File path |
|---|---|---|
| Clients | Segments, buying journey, personas, service model | `context/customers.md` |
| Competition | Big-box retailers as a category, named regional competitors, positioning | `context/competition.md` |
| Product | Paper grades and stock, supplies, printers, delivery, Infinity, pricing philosophy | `context/product.md` |
| Go to market | Business model, sales motion, channels, growth flywheel, operational KPIs | `context/gtm.md` |
| Metrics | The single source of every headline number, with its as-of date and source | `context/key-metrics.md` |

## Directory structure

All departments live under `departments/`. Teams live under
`departments/<dept>/teams/`. Each folder holds its own `CLAUDE.md`, and
optionally `context/`, `.claude/` (skills, agents, rules), `README.md`,
`docs-for-humans/`, and a gitignored `projects/`.

- **sales/** - Both branches' sales organization; pricing and discount
  authority; the deal desk. Contains **teams/scranton-sales/**.
- **accounting/** - Branch accounting and corporate finance; the expense policy.
- **warehouse/** - Receiving, pick and pack, delivery, and warehouse safety.
- **customer-service/** - Order support, returns, and the Infinity help queue.
- **human-resources/** - Hiring, onboarding, benefits, and employee relations.
- **quality-assurance/** - Supplier and inbound stock quality, and supplier
  relations.
