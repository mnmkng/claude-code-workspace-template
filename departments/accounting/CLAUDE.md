# Accounting context

Accounting runs in two places: a branch team in Scranton that owns receivables,
payables, and billing for both branches, and a corporate finance function in New
York that owns the close, reporting, and policy. Utica has a receivables clerk
who reports to its regional manager.

## Team structure

| Role | Count | Reports to |
|------|-------|------------|
| Chief Financial Officer | 1 | - |
| Financial Analyst | 1 | Chief Financial Officer |
| Senior Accountant | 1 | Regional Manager, Scranton |
| Accountant | 2 | Senior Accountant |
| Accounts Receivable Clerk | 1 | Regional Manager, Utica |

Counts are as of August 2026. The branch accounting team reports through the
branch, not through corporate finance; corporate owns policy and the close, the
branch owns the ledger it feeds.

## Key metrics

Every figure here is the one in `context/key-metrics.md`; cite it with its
as-of date.

| Metric | Current | Target | As of |
|---|---|---|---|
| Days sales outstanding | 41 days | 35 days | August 2026 |
| Gross margin, blended | 27.4% | 28.5% | August 2026 |
| Revenue, both branches, trailing 12 months | $21.5M | +6% year over year | August 2026 |
| Monthly close, business days to complete | 6 | 4 | August 2026 |
| Expense reports returned for correction | 18% | under 10% | Q2 2026 |

Days sales outstanding is the number this department is actually measured on.
It is 6 days above target, and the gap is concentrated in the public segment,
where payment terms are set by the contract and cannot be renegotiated
mid-term.

## Processes

Corporate finance owns the close and the policy; branch accounting owns the
ledger that feeds it.

### Monthly close

Runs on the first six business days. Branch accounting books and reconciles;
corporate finance consolidates, reviews margin by line, and publishes the branch
profit-and-loss pack. Headline figures in `context/key-metrics.md` are refreshed
after publication, normally in the second week.

Nothing is reported as final before the pack is published. A figure quoted from
a partially closed month is how a wrong number gets into a deck.

### Accounts receivable

Invoices go out on delivery. Statements monthly. The collection ladder is a
reminder at 30 days, a call from branch accounting at 45, and escalation to the
account's sales representative at 60 - the representative, because the
relationship is the leverage, and because a receivable that surprises a client
is usually a billing error rather than a refusal to pay.

Nothing goes to collections without the regional manager's sign-off.

### Accounts payable

Mill and supplier invoices are matched three ways against the purchase order and
the receiving record before payment. A mismatch goes to the warehouse for a
receiving check and to quality assurance if stock was rejected on inspection.

### Expense reports

Submitted monthly, reimbursed with the following month's payroll run. Checked
against `departments/accounting/context/expense-policy.md` before approval. Use
the `expense-report-check` skill rather than reading the policy each time.

Nearly a fifth of reports come back for correction, almost always for a missing
receipt or a meal over the limit. That number is a target, not a fact of life.

### Bid and contract support

Public bids need cost support and a margin check before submission. Branch
accounting supplies landed cost; the deal desk owns the pricing decision. See
the sales department's pricing file for the margin floors.

## Tools and systems

| System | Used for | Notes |
|---|---|---|
| The accounting system | General ledger, receivables, payables, invoicing | System of record |
| The BI tool | Margin by line, receivables aging, close dashboards | Read-only |
| The CRM | Account terms, contract pricing, the owning representative | Read-only for accounting |
| The HR system | Payroll input, headcount | Corporate finance only |
| `expense-report-check` skill | Checking a submitted report against the policy | Reads `departments/accounting/context/expense-policy.md` |

## Context index

| Topic | Key content | File path |
|---|---|---|
| Expense policy | Categories, limits, approval chain, receipts, reimbursement cadence, what is never reimbursed | `departments/accounting/context/expense-policy.md` |
