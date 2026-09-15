#!/usr/bin/env python3
"""Compute a client quote from the tables in pricing-and-discounts.md.

The list prices, the volume tiers, the discount authority matrix, the cost
basis, the margin floors, and the deal desk thresholds are all read out of
`departments/sales/context/pricing-and-discounts.md` at run time. That file is the single source; nothing here restates a number from
it, so a correction made there changes what this script produces and the two can
never disagree.

What it does:
  - resolves the volume tier from committed annual volume in cases
  - applies the tier discount, then the negotiated discount, to every line
  - reports the total discount, the line and blended margin, the approver the
    quote needs, and every deal desk condition that fires

Usage:
    quote.py --volume 1200 --role "Sales Representative" \\
             --line P-STD-L:40 --line P-PRM-L:10
    quote.py --volume 300 --negotiated 6 --term 36 --line P-STD-L:25
    quote.py --list-items

Exit codes: 0 quote produced, 1 bad input, 2 the pricing file could not be read.
"""

import argparse
import os
import re
import sys
from pathlib import Path

PRICING_REL = "departments/sales/context/pricing-and-discounts.md"

# Deal desk conditions 5 and 6 are about contract history and bid status, which
# are not quote inputs. The script reports them so nobody forgets them.
UNCHECKABLE_CONDITIONS = (5, 6)


class PricingError(Exception):
    """The pricing file is missing, or a table in it could not be read."""


# --- locating the pricing file ----------------------------------------------

def find_pricing() -> Path:
    """The pricing file, wherever this script was launched from.

    Four candidates, because the script runs from three different places: a CLI
    session anywhere in the tree, a cloud session at the repo root after the
    bootstrap has composed .claude/skills/ up from the department folder, and a
    direct invocation by path.
    """
    override = os.environ.get("PRICING_FILE")
    if override:
        p = Path(override)
        if p.is_file():
            return p
        raise PricingError(f"PRICING_FILE is set to {override}, which is not a file")

    here = Path(__file__).resolve()
    candidates = []
    # Inside the department folder: skills/client-quote/scripts -> departments/sales
    if len(here.parents) > 4:
        candidates.append(here.parents[4] / "context" / "pricing-and-discounts.md")
    # Walk up from the script and from the working directory looking for the repo.
    for start in (here.parent, Path.cwd().resolve()):
        for d in [start, *start.parents]:
            candidates.append(d / PRICING_REL)

    for c in candidates:
        if c.is_file():
            return c
    raise PricingError(
        f"Could not find {PRICING_REL}. Run this from inside the workspace, or set "
        "PRICING_FILE to the file's path."
    )


# --- reading the tables -----------------------------------------------------

def read_rows(text: str, header_contains: str):
    """Rows of the first Markdown table whose header row contains the string."""
    rows, in_table, matched = [], False, False
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            if matched and in_table:
                break
            in_table = False
            continue
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if not in_table:
            in_table = True
            matched = header_contains.lower() in stripped.lower()
            continue
        if not matched or set("".join(cells)) <= set("-: "):
            continue
        rows.append(cells)
    return rows


def money(cell: str) -> float:
    return float(cell.replace("$", "").replace(",", "").strip())


def percent(cell: str) -> float:
    return float(cell.replace("%", "").strip())


def parse_pricing(path: Path):
    text = path.read_text(encoding="utf-8")

    items = {}
    for cells in read_rows(text, "List price"):
        if len(cells) >= 4 and cells[0]:
            items[cells[0]] = {"item": cells[1], "unit": cells[2], "price": money(cells[3])}
    if not items:
        raise PricingError(f"{path}: no list price table found")

    tiers = []
    for cells in read_rows(text, "Tier discount"):
        if len(cells) < 3:
            continue
        nums = [int(n.replace(",", "")) for n in re.findall(r"[\d,]+", cells[1])]
        if not nums:
            continue
        low = nums[0]
        high = nums[1] if len(nums) > 1 else None
        tiers.append({"tier": cells[0], "low": low, "high": high, "discount": percent(cells[2])})
    if not tiers:
        raise PricingError(f"{path}: no volume tier table found")

    authority = []
    for cells in read_rows(text, "Negotiated discount"):
        if len(cells) < 2:
            continue
        nums = re.findall(r"[\d.]+", cells[1])
        # "above 18%" is the unbounded top of the matrix.
        limit = float(nums[0]) if nums else 0.0
        authority.append({"role": cells[0], "limit": limit,
                          "unbounded": cells[1].lower().startswith("above")})
    if not authority:
        raise PricingError(f"{path}: no discount authority table found")

    floors = {}
    for cells in read_rows(text, "Floor"):
        if len(cells) >= 2 and "%" in cells[1]:
            floors[cells[0].lower()] = percent(cells[1])
    if not floors:
        raise PricingError(f"{path}: no margin floor table found")

    costs = {}
    for cells in read_rows(text, "Cost as a share of list"):
        if len(cells) >= 2 and "%" in cells[1]:
            costs[cells[0].lower()] = percent(cells[1]) / 100
    if "paper" not in costs:
        raise PricingError(f"{path}: no cost basis table found")

    conditions = {}
    for cells in read_rows(text, "| Threshold |"):
        if len(cells) < 3:
            continue
        try:
            n = int(cells[0])
        except ValueError:
            continue
        nums = re.findall(r"[\d.]+", cells[2])
        conditions[n] = {"text": cells[1],
                         "value": float(nums[0]) if nums else None}
    if not conditions:
        raise PricingError(f"{path}: no deal desk condition table found")
    for n in (1, 2, 3, 4):
        if conditions.get(n, {}).get("value") is None:
            raise PricingError(f"{path}: deal desk condition {n} has no threshold")

    return items, tiers, authority, floors, costs, conditions


# --- the quote --------------------------------------------------------------

def resolve_tier(tiers, volume: int):
    for t in tiers:
        if volume >= t["low"] and (t["high"] is None or volume <= t["high"]):
            return t
    return tiers[0]


def required_approver(authority, negotiated: float):
    """The lowest role on the matrix that can sign this negotiated discount."""
    if negotiated <= 0:
        return None
    for a in authority:
        if a["unbounded"] or negotiated <= a["limit"]:
            return a
    return authority[-1]


def build_quote(items, tiers, authority, floors, costs, conditions, lines,
                volume, negotiated, term, role):
    tier = resolve_tier(tiers, volume)
    total_discount = tier["discount"] + negotiated
    factor = 1 - total_discount / 100

    priced, list_total, net_total, cost_total = [], 0.0, 0.0, 0.0
    for code, qty in lines:
        if code not in items:
            raise PricingError(f"unknown item code {code!r} (--list-items shows them all)")
        item = items[code]
        gross = item["price"] * qty
        net = gross * factor
        cost = gross * costs["paper"]
        priced.append({"code": code, "item": item["item"], "unit": item["unit"],
                       "qty": qty, "list": item["price"], "gross": gross,
                       "net": net, "cost": cost})
        list_total += gross
        net_total += net
        cost_total += cost

    margin = (net_total - cost_total) / net_total * 100 if net_total else 0.0
    approver = required_approver(authority, negotiated)

    triggers = []
    if total_discount > conditions[1]["value"]:
        triggers.append(f"1. total discount {total_discount:.1f}% is above "
                        f"{conditions[1]['value']:.0f}%")
    if negotiated > conditions[2]["value"]:
        triggers.append(f"2. negotiated {negotiated:.1f}% is above the branch approval "
                        f"ceiling of {conditions[2]['value']:.0f}%")
    if margin < conditions[3]["value"]:
        triggers.append(f"3. blended margin {margin:.1f}% is below the "
                        f"{conditions[3]['value']:.0f}% floor")
    if term > conditions[4]["value"]:
        triggers.append(f"4. term of {term} months is longer than "
                        f"{conditions[4]['value']:.0f}")

    return {"tier": tier, "lines": priced, "list_total": list_total,
            "net_total": net_total, "margin": margin, "negotiated": negotiated,
            "total_discount": total_discount, "approver": approver,
            "triggers": triggers, "term": term, "volume": volume,
            "paper_floor": floors.get("paper"), "role": role,
            "own": next((a for a in authority
                         if role and a["role"].lower() == role.lower()), None),
            "conditions": conditions}


def render(q, source: Path):
    out = []
    out.append(f"Quote - {q['volume']:,} cases committed annually, "
               f"{q['term']}-month term")
    out.append(f"Tier {q['tier']['tier']} ({q['tier']['low']:,}"
               + (f"-{q['tier']['high']:,}" if q["tier"]["high"] else "+")
               + f" cases): {q['tier']['discount']:.0f}% tier discount")
    if q["negotiated"]:
        out.append(f"Negotiated discount: {q['negotiated']:.1f}%")
    out.append(f"Total discount: {q['total_discount']:.1f}%")
    out.append("")
    out.append(f"{'Code':<11} {'Qty':>5} {'Unit':<6} {'List':>10} {'Net':>10}")
    for l in q["lines"]:
        out.append(f"{l['code']:<11} {l['qty']:>5} {l['unit']:<6} "
                   f"{'$' + format(l['gross'], ',.2f'):>10} "
                   f"{'$' + format(l['net'], ',.2f'):>10}")
    out.append("")
    out.append(f"List total:      ${q['list_total']:,.2f}")
    out.append(f"Quoted total:    ${q['net_total']:,.2f}")
    out.append(f"Blended margin:  {q['margin']:.1f}%"
               + (f"  (paper floor {q['paper_floor']:.0f}%)" if q["paper_floor"] else ""))
    out.append("")
    if q["approver"]:
        a = q["approver"]
        limit = "above 18%" if a["unbounded"] else f"up to {a['limit']:.0f}%"
        out.append(f"Approver needed: {a['role']} ({limit} negotiated discount)")
        if q["role"] and q["own"] is None:
            out.append(f"  {q['role']!r} is not a role on the discount authority table.")
        elif q["own"] and not q["own"]["unbounded"] and q["negotiated"] > q["own"]["limit"]:
            out.append(f"  Above {q['role']}'s own {q['own']['limit']:.0f}%, so it "
                       "escalates. Authority does not stack.")
    else:
        out.append("Approver needed: none - the quote is at tier price")
    out.append("")
    if q["triggers"]:
        out.append("DEAL DESK REVIEW REQUIRED. Conditions that fire:")
        for t in q["triggers"]:
            out.append(f"  - {t}")
        out.append("Submit to the Director of Sales Operations. Two business days.")
    else:
        out.append("Deal desk: not required on the inputs given.")
    out.append("")
    out.append("Check by hand, because they are not quote inputs:")
    for n in UNCHECKABLE_CONDITIONS:
        c = q["conditions"].get(n)
        if c:
            suffix = f" ({c['value']:.0f} months)" if c["value"] else ""
            out.append(f"  - {n}. {c['text']}{suffix}")
    out.append("")
    out.append(f"Priced from {source}")
    return "\n".join(out)


def parse_line(spec: str):
    if ":" not in spec:
        raise PricingError(f"--line wants CODE:QUANTITY, got {spec!r}")
    code, _, qty = spec.partition(":")
    try:
        n = int(qty)
    except ValueError:
        raise PricingError(f"--line quantity must be a whole number, got {qty!r}")
    if n <= 0:
        raise PricingError(f"--line quantity must be positive, got {n}")
    return code.strip().upper(), n


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--line", action="append", default=[], metavar="CODE:QTY",
                    help="a quote line, repeatable (e.g. P-STD-L:40)")
    ap.add_argument("--volume", type=int, default=0, metavar="CASES",
                    help="committed annual volume in cases, which sets the tier")
    ap.add_argument("--negotiated", type=float, default=0.0, metavar="PCT",
                    help="negotiated discount on top of the tier discount")
    ap.add_argument("--term", type=int, default=12, metavar="MONTHS",
                    help="contract term in months (default 12)")
    ap.add_argument("--role", default=None,
                    help="the quoting representative's role, to check their authority")
    ap.add_argument("--list-items", action="store_true", help="print the item codes and exit")
    args = ap.parse_args(argv)

    try:
        source = find_pricing()
        items, tiers, authority, floors, costs, conditions = parse_pricing(source)
    except (PricingError, OSError) as e:
        print(f"quote: {e}", file=sys.stderr)
        return 2

    if args.list_items:
        print(f"Item codes, from {source}:")
        for code, item in items.items():
            print(f"  {code:<11} {item['item']:<42} {item['unit']:<6} ${item['price']:.2f}")
        return 0

    if not args.line:
        ap.print_help()
        return 1
    if args.volume < 0 or args.negotiated < 0 or args.term <= 0:
        print("quote: --volume and --negotiated cannot be negative, --term must be positive",
              file=sys.stderr)
        return 1

    try:
        lines = [parse_line(s) for s in args.line]
        q = build_quote(items, tiers, authority, floors, costs, conditions, lines,
                        args.volume, args.negotiated, args.term, args.role)
    except PricingError as e:
        print(f"quote: {e}", file=sys.stderr)
        return 1

    print(render(q, source))
    return 0


if __name__ == "__main__":
    sys.exit(main())
