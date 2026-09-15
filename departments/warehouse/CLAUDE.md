# Warehouse context

The warehouse receives inbound stock from the mills and suppliers, holds roughly
600 stock-keeping units in Scranton, and runs the delivery fleet that serves the
branch radius. Delivery is our own drivers in our own trucks, which is half of
what clients are actually buying - see the service model in
`context/customers.md`.

Warehouse safety incidents are one of the four company KPIs. Safety decisions
are not traded against delivery windows.

## Team structure

| Role | Count | Reports to |
|------|-------|------------|
| Warehouse Manager | 1 | Regional Manager, Scranton |
| Warehouse Foreman | 2 | Warehouse Manager (Scranton); Regional Manager, Utica (Utica) |
| Warehouse Associate | 7 | Warehouse Foreman |

Counts are as of August 2026.

[TODO: split the table by branch, add the seasonal labor arrangement for the
August and January peaks, and record which roles are covered by the shift
rotation.]

## Key metrics

The warehouse owns one company KPI - recordable safety incidents - and the
delivery and accuracy measures below. Figures come from `context/key-metrics.md`.

| Metric | Current | Target | As of |
|---|---|---|---|
| Warehouse recordable safety incidents, trailing 12 months | 2 | 0 | August 2026 |
| Days since last recordable incident, Scranton | 138 | - | August 31, 2026 |
| Next-day delivery rate, Scranton | 96% | 98% | August 2026 |
| Order accuracy, lines shipped correct | 99.2% | 99.7% | August 2026 |

[TODO: add pick rate per hour, inbound dock turnaround, stock-out rate on the
warehoused stock-keeping units, and a Utica delivery measure once Utica is
instrumented - it currently reports no delivery rate at all.]

## Processes

[TODO: write up the six that matter, in this order - inbound receiving and the
three-way match that accounts payable depends on; put-away and cycle counting;
pick, pack, and the accuracy check; route building and the daily load; the
expedited and same-day exception, which sales has to coordinate through the
warehouse; and returns and damaged-delivery recovery.]

[TODO: the safety process is its own section and comes first - the daily check,
the incident report, the stop-work authority, and who is notified when.]

## Tools and systems

[TODO: list the inventory and warehouse system, the delivery routing tool, the
handheld scanners, the safety log, and which of them the branch can write to
versus read. Note where each one is the system of record, because the
three-way match in accounts payable depends on knowing that.]
