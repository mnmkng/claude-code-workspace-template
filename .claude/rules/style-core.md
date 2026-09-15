# Style core

Formatting and terminology that apply to everything written in this workspace:
agent context, client-facing copy, quotes, Slack, and commit messages. Short on
purpose - it is always loaded. Anything longer belongs in a context file.

## Company and product names

| Write | Never write |
|---|---|
| Dunder Mifflin | Dunder-Mifflin, DunderMifflin, DM (in client-facing text) |
| Dunder Mifflin Paper Company, Inc. (contracts, invoices, first page of a proposal) | Dunder Mifflin Inc., The Dunder Mifflin Company |
| Infinity (the ordering platform; "Dunder Mifflin Infinity" on first mention in client-facing copy) | infinity, DM Infinity, the Infinity system, Infinity.com |
| the Scranton branch, the Utica branch | Scranton Branch, DM Scranton, the Scranton office |
| corporate (the New York office, lowercase, a common noun) | Corporate, Corporate HQ, the mothership |

"Infinity" is the platform clients order through. It is not the website, not the
portal, and not an app. A client "orders through Infinity" or "places an Infinity
order".

## Job titles

- **"Assistant to the Regional Manager"** is the title. It is never shortened to
  "Assistant Regional Manager", which is a different and more senior job that
  does not exist here. Write it in full every time, including in email
  signatures, org charts, and quotes.
- Titles are capitalized when they name a specific role ("Regional Manager,
  Scranton") and lowercase when used generically ("every regional manager in the
  Northeast").
- Get the spelling of a colleague's name from the `who-is` skill before writing
  it down. Do not guess.

## Trade terms

- A **ream** is 500 sheets. A **case** is 10 reams. Quote and invoice in cases;
  clients who ask for reams get a case count with the ream equivalent in
  parentheses.
- **Client** is an account we sell to. **Customer** is for the market in
  general ("small-business customers buy on price"). Never "user".
- **Account** is the record; **client** is the company. An account has an ID; a
  client has a name.

## Headings and prose

- Sentence case for every heading: "Key metrics", not "Key Metrics".
- US English spelling and punctuation: organize, color, catalog, inventory.
- Serial comma.
- Short paragraphs, two to four sentences. Tables for anything structured.
- Bold for emphasis. Never all caps.

## Numbers, money, and dates

| Kind | Format | Example |
|---|---|---|
| Money | US dollars, `$` prefix, no currency code | `$1,240` |
| Money, large | One decimal place, `K`/`M` suffix | `$12.4M` |
| Money, exact | Cents only on quotes, invoices, and expense lines | `$38.50` |
| Thousands | Comma separator | `2,000 cases` |
| Decimals | Period, one place unless precision matters | `27.4%` |
| Percentages | `%` with no space | `91%` |
| Dates, prose | Month and year, or month day, year | `August 2026`, `August 31, 2026` |
| Dates, data | ISO 8601 in frontmatter, file names, and data files | `2026-08-31` |
| Quarters | `Q3 2026` | `Q3 2026` |
| Time | 12-hour with periods, plus the time zone | `4:30 p.m. ET` |

Every metric written anywhere carries an "as of" month and year, because a
number without a date reads as current forever. The headline figures live in
`context/key-metrics.md`; cite the figure and its date from there rather than
repeating a number from memory.
