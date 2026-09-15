---
sources:
  - "HR system: name, job title, department, manager - exported by the org chart sync (or by hand with who_is.py --import)"
  - "Chat tool: display name as nickname, team from the text after @ in the profile title"
owner: Holly Flax
edit: upstream
review_every: 30d
files:
  - org-chart.json
---
# Org chart data

`org-chart.json` is the who-is skill's data file: everyone in the company, rebuilt from the HR system by a sync that opens a pull request only when the data changed, or imported by hand with `who_is.py --import people.csv`. The commit that lands such a change touches this one file and is the verification, so this card carries no `verified_at`. `review_every: 30d` is the longest gap between data changes that is normal for the company's size, not the sync's run cadence: a quiet month is not a dead sync. When the lint reports this card stale, check the sync's own run history; whether it is alive is visible there, not in git.

What the fields mean and how to query the file without loading it whole: `../SKILL.md`. Wrong data is fixed in the HR system, or in the chat tool for a nickname or team, never in the JSON.
