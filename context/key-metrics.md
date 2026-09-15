---
sources:
  - "Corporate finance: monthly close, branch profit-and-loss pack"
  - "The CRM: account and pipeline counts"
  - "The BI tool: order, delivery, and Infinity dashboards"
  - "Warehouse safety log, both branches"
owner: David Wallace
edit: here
review_every: 90d
verified_at: 2026-09-15
---
# Key metrics

The single source of every headline number used anywhere in this workspace. A
figure quoted in another file, a quote, a deck, or a client email comes from
this table, with its as-of date attached.

## How to use this file

- **Cite the figure and its date together.** "Client retention is 91% (as of
  August 2026)." A number without a date reads as current forever, and these
  numbers move every month.
- **Cite, do not copy.** A department `CLAUDE.md` may carry a scorecard of the
  metrics it owns, and a file may quote a figure in an argument - always with
  the as-of date, which is what makes a stale copy visible. What no other file
  does is become a second source: when a figure here changes, the citation
  changes with it, and a citation without a date is the bug.
- **Do not compute a new headline number from these.** Ratios of ratios go
  wrong quietly. If a number is needed often enough to matter, it gets its own
  row here, sourced.
- **A number not in this table is not a company figure.** It is an estimate, and
  is labelled as one wherever it appears.
- Figures are refreshed after the monthly close, normally in the second week.

## Revenue and margin

| Metric | Value | As of | Source |
|---|---|---|---|
| Revenue, both branches, trailing 12 months | $21.5M | August 2026 | Monthly close |
| Revenue, Scranton branch, trailing 12 months | $12.4M | August 2026 | Monthly close |
| Revenue, Utica branch, trailing 12 months | $9.1M | August 2026 | Monthly close |
| Revenue growth, year over year, both branches | 4.2% | August 2026 | Monthly close |
| Gross margin, blended | 27.4% | August 2026 | Monthly close |
| Gross margin, paper only | 19.1% | August 2026 | Monthly close |
| Gross margin, supplies and printer service | 38.6% | August 2026 | Monthly close |
| Days sales outstanding | 41 days | August 2026 | Accounts receivable aging |

## Clients and pipeline

| Metric | Value | As of | Source |
|---|---|---|---|
| Active accounts, Scranton | 412 | August 2026 | The CRM |
| Active accounts, Utica | 288 | August 2026 | The CRM |
| Client retention, gross logo, trailing 12 months | 91% | August 2026 | The CRM |
| Net revenue retention, trailing 12 months | 97% | August 2026 | Monthly close and the CRM |
| New accounts won per quarter, Scranton | 27 | Q2 2026 | The CRM |
| Average annual account value | $30,700 | August 2026 | Monthly close and the CRM |
| Average order value | $1,240 | August 2026 | The BI tool |
| Median sales cycle, small business | 21 days | Q2 2026 | The CRM |
| Median sales cycle, county and school district | 94 days | Q2 2026 | The CRM |

## Operations

| Metric | Value | As of | Source |
|---|---|---|---|
| Infinity order share, both branches | 38% | August 2026 | The BI tool |
| Infinity order share, accounts under $25K a year | 51% | August 2026 | The BI tool |
| Next-day delivery rate, Scranton | 96% | August 2026 | The BI tool |
| Order accuracy, lines shipped correct | 99.2% | August 2026 | The BI tool |
| Warehouse recordable safety incidents, trailing 12 months | 2 | August 2026 | Warehouse safety log |
| Days since last recordable incident, Scranton | 138 | August 31, 2026 | Warehouse safety log |
| Inbound stock rejected on quality inspection | 1.4% | Q2 2026 | Quality assurance log |

## People

| Metric | Value | As of | Source |
|---|---|---|---|
| Headcount, both branches and corporate | 40 | August 2026 | The HR system |
| Sales representatives, Scranton | 7 | August 2026 | The HR system |
| Sales representatives, Utica | 4 | August 2026 | The HR system |
| Voluntary attrition, trailing 12 months | 7% | August 2026 | The HR system |

## Known gaps

- Utica has no delivery-rate instrumentation; its next-day figure is not
  reported and must not be inferred from Scranton's.
- Sales-cycle medians exclude renewals, which are not opportunities in the CRM.
- Gross margin by line is allocated, not directly measured; the allocation
  method has not changed since 2024.
