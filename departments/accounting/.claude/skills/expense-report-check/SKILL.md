---
name: expense-report-check
description: >
  Check an expense report against the company expense policy before it is
  submitted or approved. Use when asked whether an expense is reimbursable, what
  the limit is for a category, who has to approve a report, why a report came
  back, or to review a list of expense lines. Reads the policy file rather than
  answering from memory.
---

# Expense report check

Checks a submitted or draft expense report against
`departments/accounting/context/expense-policy.md` and reports, per line,
whether it passes, and for the report as a whole, who has to approve it.

**Read the policy file every time.** Limits move, and a remembered limit that is
$15 out of date gets a report returned. If the file cannot be read, say so
rather than answering from memory.

## Inputs

An expense report, in whatever form it arrives: a list of lines, a pasted
spreadsheet, a photograph of a form, or a description. Each line needs a
category, a date, an amount, and a business purpose. For client meals, also the
account ID and the number of people.

Ask for what is missing. Do not assume a category: the limits and the receipt
rules differ by category, and guessing produces a confident wrong answer.

## Procedure

1. Read `context/expense-policy.md` in full.
2. For each line, check in this order:
   - Is the category on the table at all, or does it need prior approval from
     the Chief Financial Officer?
   - Is it on the **never reimbursed** list? That check comes before the limit
     check, because an amount under a limit does not make alcohol reimbursable.
   - Is the amount within the limit for that category, on the right basis - per
     person, per day, per night, or per year?
   - Is a receipt required at that amount, and is it an itemized receipt rather
     than a card slip?
   - Is the expense within 90 days?
   - For a client meal or entertainment: is there an account ID, and no
     individual client staff named?
3. Total the report and resolve the approver from the approval chain, including
   the three overrides that apply regardless of total.
4. Report.

## Output

```
Report total:   $412.60
Approver:       Department head
                ($251-$1,000 band; also required - line 3 has no receipt)

Line  Date        Category         Amount   Verdict
1     2026-08-04  Client meal      $118.00  PASS   $59.00/person, 2 people, DM-SCR-0412
2     2026-08-11  Mileage          $ 46.20  PASS   84 miles, log attached
3     2026-08-14  Parking          $ 22.00  RETURN Receipt required over $10, none attached
4     2026-08-19  Client meal      $145.00  RETURN $72.50/person is over the $60 limit
5     2026-08-22  Client meal      $ 96.00  RETURN Itemized receipt shows wine; split it out

Fix before submitting: lines 3, 4, 5.
```

State the rule behind every RETURN, with the limit, so the person can fix it
rather than resubmit and guess.

## Rules

- **Never approve anything.** This skill checks; a named person on the approval
  chain approves. Do not tell someone their report is approved.
- **Never say a line passes when the policy is silent.** A category not on the
  table needs prior approval from the Chief Financial Officer, and that is the
  answer, not a judgement call about whether it seems reasonable.
- **Alcohol is never reimbursable**, in any category, at any amount, including
  buried in an itemized restaurant total. It is split out and removed.
- **Public-sector buyers.** Anything beyond a standard-limit meal for a county
  or school district contact is a compliance problem for them, not a policy
  question for us. Flag it and stop.
- **Account IDs, not client names**, on every client meal and entertainment
  line. Reports are retained for seven years.
- Nobody approves their own report. If the submitter and the approver are the
  same person, say so - the report will be returned unpaid.
