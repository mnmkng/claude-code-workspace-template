# Human resources context

Human resources is a corporate function with one representative sitting in the
Scranton branch. **The branch human resources representative reports to the
Director of Human Resources at corporate, not to the regional manager**, and
sits in the branch office full time.

That split is the single most important fact about this department, and it is
deliberate. A representative who reported to the branch could not investigate a
complaint about the branch. It also means the branch's own chat team and the
department are different things - the `who-is` skill will show a department of
Human Resources and a team of Scranton Branch for the same person.

## Team structure

| Role | Count | Reports to |
|------|-------|------------|
| Director of Human Resources | 1 | Chief Financial Officer |
| Human Resources Representative | 1 | Director of Human Resources |

Counts are as of August 2026. Voluntary attrition is 7% trailing 12 months (as
of August 2026); see `context/key-metrics.md`.

[TODO: record the Utica coverage arrangement - the branch has no resident
representative and is covered from Scranton - and the payroll split with
corporate finance.]

## Key metrics

[TODO: attrition is the only people figure in `context/key-metrics.md` today.
Add time to fill by role family, offer acceptance rate, onboarding completion
within 30 days, and the training budget used against the $2,000 per person
allowance in the accounting expense policy.]

## Processes

[TODO: write up hiring and the approval to open a role; onboarding, including
the day-one checklist and who owns each item; the annual review cycle and its
calendar; the leave and time-off policy; the complaint and investigation
process, with the reporting line that makes it work; and offboarding, including
system access removal.]

[TODO: the complaint process is the one that most needs writing down. Record the
route that does not run through the branch, what confidentiality is actually
promised, and where the record is kept.]

## Tools and systems

[TODO: list the HR system, which is the system of record for name, job title,
department, and manager and the source of the `who-is` org chart data; the
payroll run shared with corporate finance; and the applicant tracking
arrangement, if any.]

## Data sensitivity

Employee personal information - contact details, compensation, performance,
health, and personal circumstances - never enters this repo, in any file, in any
folder. Directory data (name, job title, department, manager, chat display name)
is allowed and lives in the `who-is` skill's data file. The line is in
`.claude/rules/data-sensitivity.md` and this department is the one most likely
to be asked to cross it.
