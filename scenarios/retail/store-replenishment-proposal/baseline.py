"""Synthetic, review-only replenishment calculation; no business-system writes."""
from __future__ import annotations

import re
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "_shared"))
from scenario_support import run_cli


ROLES = ("store_stock", "dc_stock", "demand", "inbound", "routes", "capacity")
IDENTIFIER = re.compile(r"SYN-[A-Z0-9]+(?:-[A-Z0-9]+)*\Z")
FILENAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\.json\Z")
MESSAGES = {
    "allocation-limited": "Whole-case request exceeds available DC stock or capacity.",
    "late-inbound": "Receipt is after coverage and contributes no stock.",
    "overdue-inbound": "Overdue in-transit evidence blocks this store/SKU proposal.",
    "lost-demand": "Forecast demand is unfilled on the stated day.",
    "safety-shortfall": "Projected closing stock is below safety policy.",
}


class InvalidInput(ValueError):
    def __init__(self, code: str, message: str, reference: str):
        super().__init__(message)
        self.exception = {"code": code, "message": message, "reference": reference}


def invalid(reference: str, requirement: str) -> None:
    raise InvalidInput("invalid-record", f"{reference} must {requirement}.", reference)


def fields(value, names, reference: str) -> None:
    if not isinstance(value, dict) or set(value) != set(names):
        invalid(reference, "be an object with exactly these fields: " + ", ".join(sorted(names)))


def integer(value, reference: str, *, positive: bool = False) -> None:
    if type(value) is not int or value < (1 if positive else 0):
        invalid(reference, "be a positive integer" if positive else "be a nonnegative integer")


def identifier(value, reference: str) -> None:
    if not isinstance(value, str) or len(value) > 80 or not IDENTIFIER.fullmatch(value):
        invalid(reference, "be a SYN-prefixed uppercase alphanumeric identifier")


def calendar(value, reference: str) -> date:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        invalid(reference, "be a valid YYYY-MM-DD date")
    try:
        return date.fromisoformat(value)
    except ValueError:
        invalid(reference, "be a valid YYYY-MM-DD date")


def key(row: dict) -> tuple[str, str]:
    return row["store_id"], row["sku"]


def reference(pair: tuple[str, str]) -> str:
    return "|".join(pair)


def available(row: dict) -> int:
    return row["on_hand_units"] - row["reserved_units"] - row["blocked_units"]


def validate(payload: dict):
    fields(payload, ("schema_version", "synthetic", "policy", "files"), "input")
    if type(payload["schema_version"]) is not int or payload["schema_version"] != 1:
        invalid("schema_version", "be integer 1")
    if payload["synthetic"] is not True:
        invalid("synthetic", "be true")
    policy = payload["policy"]
    fields(policy, ("policy_id", "as_of", "review_days", "partial_cases_allowed", "source_files"), "policy")
    identifier(policy["policy_id"], "policy.policy_id")
    as_of = calendar(policy["as_of"], "policy.as_of")
    integer(policy["review_days"], "policy.review_days", positive=True)
    if policy["review_days"] > 366:
        invalid("policy.review_days", "not exceed 366 days")
    if type(policy["partial_cases_allowed"]) is not bool:
        invalid("policy.partial_cases_allowed", "be boolean")
    mapping = policy["source_files"]
    fields(mapping, ROLES, "policy.source_files")
    for role in ROLES:
        if not isinstance(mapping[role], str) or not FILENAME.fullmatch(mapping[role]):
            invalid("policy.source_files." + role, "be a portable JSON leaf filename")
    if len(set(mapping.values())) != len(ROLES):
        invalid("policy.source_files", "assign a distinct filename to every role")
    fields(payload["files"], mapping.values(), "files")
    tables = {role: payload["files"][mapping[role]] for role in ROLES}
    specs = {
        "store_stock": ("store_id", "sku", "snapshot_on", "on_hand_units", "reserved_units", "blocked_units"),
        "dc_stock": ("dc_id", "sku", "snapshot_on", "on_hand_units", "reserved_units", "blocked_units"),
        "demand": ("store_id", "sku", "demand_on", "units"),
        "inbound": ("receipt_id", "store_id", "sku", "eta", "status", "remaining_units"),
        "routes": ("store_id", "sku", "dc_id", "lead_days", "case_pack", "safety_units", "priority"),
        "capacity": ("dc_id", "dispatch_on", "remaining_case_capacity"),
    }
    primary = {
        "store_stock": ("store_id", "sku"), "dc_stock": ("dc_id", "sku"),
        "demand": ("store_id", "sku", "demand_on"), "inbound": ("receipt_id",),
        "routes": ("store_id", "sku"), "capacity": ("dc_id", "dispatch_on"),
    }
    dates = {"snapshot_on", "demand_on", "eta", "dispatch_on"}
    indexes = {}
    for role in ROLES:
        rows = tables[role]
        if not isinstance(rows, list) or (role != "inbound" and not rows):
            invalid(role, "be an array" if role == "inbound" else "be a nonempty array")
        index = {}
        for position, row in enumerate(rows):
            label = f"{role}[{position}]"
            fields(row, specs[role], label)
            for name in specs[role]:
                path = f"{label}.{name}"
                if name.endswith("_id") or name == "sku":
                    identifier(row[name], path)
                elif name in dates:
                    calendar(row[name], path)
                elif name == "status":
                    if row[name] not in ("in-transit", "received", "cancelled"):
                        invalid(path, "be in-transit, received, or cancelled")
                else:
                    integer(row[name], path, positive=name == "case_pack")
            row_key = tuple(row[name] for name in primary[role])
            record_reference = role + ":" + "|".join(row_key)
            if row_key in index:
                raise InvalidInput("duplicate-key", f"Duplicate {role} key.", record_reference)
            if role in ("store_stock", "dc_stock"):
                if row["snapshot_on"] != policy["as_of"]:
                    raise InvalidInput("snapshot-date-mismatch", "Inventory snapshot must match as_of.", record_reference)
                if available(row) < 0:
                    raise InvalidInput("contradictory-stock", "Reserved and blocked units exceed physical on-hand.", record_reference)
            if role == "inbound":
                if row["status"] == "in-transit" and row["remaining_units"] == 0:
                    invalid(label + ".remaining_units", "be positive for in-transit receipts")
                if row["status"] != "in-transit" and row["remaining_units"] != 0:
                    raise InvalidInput("contradictory-receipt", "Closed receipts must have zero remaining units.", record_reference)
            if role == "capacity" and row["dispatch_on"] != policy["as_of"]:
                raise InvalidInput("capacity-date-mismatch", "Capacity dispatch date must match as_of.", record_reference)
            if role == "routes" and row["lead_days"] + policy["review_days"] > 366:
                invalid(label + ".lead_days", "keep lead_days plus review_days at most 366")
            index[row_key] = row
        indexes[role] = index
    routes = indexes["routes"]
    if set(routes) != set(indexes["store_stock"]):
        raise InvalidInput("unmatched-route", "Every store/SKU must have exactly one route and stock row.", "store_stock/routes")
    horizons = {}
    required_demand = set()
    for pair, route in sorted(routes.items()):
        dc_key = (route["dc_id"], route["sku"])
        if dc_key not in indexes["dc_stock"] or (route["dc_id"], policy["as_of"]) not in indexes["capacity"]:
            raise InvalidInput("missing-dc-evidence", "Route requires matching DC stock and dispatch capacity.", reference(pair))
        days = route["lead_days"] + policy["review_days"]
        if as_of.toordinal() + days - 1 > date.max.toordinal():
            invalid("policy.as_of", "allow the complete coverage horizon within supported dates")
        end = as_of + timedelta(days=days - 1)
        arrival = as_of + timedelta(days=route["lead_days"])
        horizons[pair] = (arrival, end)
        required_demand.update((*pair, (as_of + timedelta(days=offset)).isoformat()) for offset in range(days))
    missing = required_demand - set(indexes["demand"])
    extra = set(indexes["demand"]) - required_demand
    if missing:
        raise InvalidInput("missing-demand", "Every coverage day requires an explicit residual-demand row.", "|".join(min(missing)))
    if extra:
        raise InvalidInput("out-of-window-demand", "Demand row has no routed store/SKU coverage day.", "|".join(min(extra)))
    for row in sorted(tables["inbound"], key=lambda item: item["receipt_id"]):
        if key(row) not in routes:
            raise InvalidInput("unmatched-inbound", "Receipt requires a routed store/SKU.", row["receipt_id"])
    return policy, tables, indexes, horizons


def event(step_id: str, kind: str, caption: str, facts: dict, title: str, columns: list, rows: list, highlights=()):
    return {
        "step_id": step_id, "kind": kind, "caption": caption, "facts": facts,
        "tables": [{
            "title": title + (" (first 8 rows)" if len(rows) > 8 else ""),
            "columns": columns, "rows": rows[:8], "total_rows": len(rows),
            "highlight_rows": [index for index in highlights if index < min(8, len(rows))],
        }],
    }


def issue(code: str, pair: tuple[str, str], on: str, units: int, *, receipt_id: str | None = None):
    return {
        "code": code, "message": MESSAGES[code], "reference": receipt_id or reference(pair),
        "store_id": pair[0], "sku": pair[1], "on": on, "units": units,
    }


def physical_day(pair, day, arrival, opening, incoming, proposed, demand):
    received = proposed if day == arrival else 0
    fulfilled = min(demand, opening + incoming + received)
    return {
        "store_id": pair[0], "sku": pair[1], "day": day.isoformat(),
        "phase": "before-arrival" if day < arrival else "coverage",
        "opening_units": opening, "inbound_units": incoming, "proposed_units": received,
        "demand_units": demand, "fulfilled_units": fulfilled, "lost_units": demand - fulfilled,
        "closing_units": opening + incoming + received - fulfilled,
    }


def solve(payload):
    raw_files = payload.get("files") if isinstance(payload, dict) else None
    file_count = len(raw_files) if isinstance(raw_files, dict) else 0
    record_count = sum(len(rows) for rows in raw_files.values() if isinstance(rows, list)) if isinstance(raw_files, dict) else 0
    events = [event(
        "load-exports", "input", "Read the supplied synthetic export bundle; no live inventory connection.",
        {"logical_files": file_count, "records": record_count}, "Received bundle",
        ["measure", "count"], [["logical export files", file_count], ["export records", record_count]],
    )]
    try:
        policy, tables, indexes, horizons = validate(payload)
    except InvalidInput as error:
        events.append(event(
            "validate-stock-and-keys", "validation", "Rejected explicit invalid or contradictory export evidence.",
            {"rejected": True}, "Input rejection", ["code", "reference"],
            [[error.exception["code"], error.exception["reference"]]], [0],
        ))
        return {"schema_version": 1, "status": "rejected", "outputs": {}, "exceptions": [error.exception]}, events
    as_of = date.fromisoformat(policy["as_of"])
    routes = indexes["routes"]
    events.append(event(
        "validate-stock-and-keys", "validation", "Validated unique keys, disjoint physical stock and every required demand day.",
        {"pairs": len(routes), "demand_days": len(tables["demand"]), "review_days": policy["review_days"]},
        "Validated logical roles", ["role", "rows"], [[role, len(tables[role])] for role in ROLES],
    ))
    exceptions, inbound_register, blocked = [], [], set()
    inbound_by_day = defaultdict(int)
    for row in sorted(tables["inbound"], key=lambda item: item["receipt_id"]):
        pair = key(row)
        eta = date.fromisoformat(row["eta"])
        disposition = "counted"
        if row["status"] != "in-transit":
            disposition = "ignored-closed"
        elif eta < as_of:
            disposition = "overdue"
            blocked.add(pair)
            exceptions.append(issue("overdue-inbound", pair, row["eta"], row["remaining_units"], receipt_id=row["receipt_id"]))
        elif eta > horizons[pair][1]:
            disposition = "after-coverage"
            exceptions.append(issue("late-inbound", pair, row["eta"], row["remaining_units"], receipt_id=row["receipt_id"]))
        else:
            inbound_by_day[(*pair, row["eta"])] += row["remaining_units"]
        inbound_register.append({
            "receipt_id": row["receipt_id"], "store_id": pair[0], "sku": pair[1],
            "eta": row["eta"], "remaining_units": row["remaining_units"], "disposition": disposition,
        })
    joined = [[*pair, route["dc_id"], available(indexes["store_stock"][pair]), horizons[pair][0].isoformat(), pair in blocked]
              for pair, route in sorted(routes.items())]
    events.append(event(
        "join-store-supply", "join", "Join each store/SKU to its route, opening stock, dated demand and independent receipts.",
        {"matched_pairs": len(routes), "receipts": len(inbound_register), "blocked_pairs": len(blocked)},
        "Joined store/DC supply", ["store", "sku", "dc", "available", "arrival", "blocked"], joined,
        [index for index, row in enumerate(joined) if row[-1]],
    ))
    proposals, pre_projection, balances = {}, [], []
    for pair, route in sorted(routes.items()):
        arrival, end = horizons[pair]
        opening = available(indexes["store_stock"][pair])
        proposal = {
            "store_id": pair[0], "sku": pair[1], "dc_id": route["dc_id"],
            "dispatch_on": policy["as_of"], "arrival_on": arrival.isoformat(), "coverage_end": end.isoformat(),
            "priority": route["priority"], "case_pack": route["case_pack"], "opening_available_units": opening,
            "arrival_opening_units": None, "raw_required_units": None, "requested_units": None,
            "requested_cases": None, "proposed_units": 0, "proposed_cases": 0, "deferred_units": None,
            "rounding_excess_units": None, "closing_units": None, "pre_arrival_lost_units": None,
            "post_arrival_lost_units": None, "safety_shortfall_units": None,
            "status": "blocked", "limits": ["overdue-inbound"] if pair in blocked else [],
        }
        proposals[pair] = proposal
        if pair in blocked:
            continue
        day, stock = as_of, opening
        while day < arrival:
            date_key = (*pair, day.isoformat())
            observed = physical_day(pair, day, arrival, stock, inbound_by_day[date_key], 0, indexes["demand"][date_key]["units"])
            pre_projection.append(observed)
            stock = observed["closing_units"]
            day += timedelta(days=1)
        proposal["arrival_opening_units"] = stock
        balance, prefix_need = stock, 0
        for offset in range(policy["review_days"]):
            day = arrival + timedelta(days=offset)
            date_key = (*pair, day.isoformat())
            balance += inbound_by_day[date_key] - indexes["demand"][date_key]["units"]
            prefix_need = max(prefix_need, -balance)
            balances.append([pair[0], pair[1], day.isoformat(), balance, prefix_need])
        raw = max(0, prefix_need, route["safety_units"] - balance)
        cases = (raw + route["case_pack"] - 1) // route["case_pack"]
        proposal.update(raw_required_units=raw, requested_cases=cases, requested_units=cases * route["case_pack"],
                        rounding_excess_units=cases * route["case_pack"] - raw)
    events.append(event(
        "project-before-arrival", "decision", "Walk pre-arrival physical stock; lost forecast is not carried forward as a backorder.",
        {"pre_arrival_days": len(pre_projection), "lost_units": sum(row["lost_units"] for row in pre_projection)},
        "Physical stock before proposed arrival", ["store", "day", "opening", "inbound", "lost", "closing"],
        [[r["store_id"], r["day"], r["opening_units"], r["inbound_units"], r["lost_units"], r["closing_units"]] for r in pre_projection],
        [index for index, row in enumerate(pre_projection) if row["lost_units"]],
    ))
    request_rows = [[p["store_id"], p["sku"], p["raw_required_units"], p["case_pack"], p["requested_units"], p["requested_cases"]]
                    for p in proposals.values()]
    requirement_event = event(
        "calculate-case-requests", "decision", "Cover the largest post-arrival deficit and final safety need, then round up to whole cases.",
        {"eligible_pairs": len(routes) - len(blocked)}, "Whole-case requests",
        ["store", "sku", "raw units", "case pack", "request units", "cases"], request_rows,
    )
    requirement_event["tables"].extend(event(
        "calculate-case-requests", "decision", "Planning balance, not physical stock.", {},
        "Unconstrained planning balances", ["store", "sku", "day", "balance", "prefix need"], balances,
    )["tables"])
    events.append(requirement_event)
    dc_opening = {pair: available(row) for pair, row in indexes["dc_stock"].items()}
    dc_remaining = dict(dc_opening)
    cap_opening = {row["dc_id"]: row["remaining_case_capacity"] for row in tables["capacity"]}
    cap_remaining = dict(cap_opening)
    allocations = []
    for pair, route in sorted(routes.items(), key=lambda item: (item[1]["priority"], *item[0])):
        proposal = proposals[pair]
        if pair in blocked:
            continue
        dc_key = (route["dc_id"], route["sku"])
        requested = proposal["requested_cases"]
        stock_cases = dc_remaining[dc_key] // route["case_pack"]
        capacity_cases = cap_remaining[route["dc_id"]]
        allotted = min(requested, stock_cases, capacity_cases)
        limits = [name for name, amount in (("dc-stock", stock_cases), ("dc-capacity", capacity_cases)) if amount < requested]
        if not policy["partial_cases_allowed"] and allotted < requested:
            allotted = 0
            limits.append("partial-disabled")
        units = allotted * route["case_pack"]
        dc_remaining[dc_key] -= units
        cap_remaining[route["dc_id"]] -= allotted
        status = "no-need" if requested == 0 else "full" if allotted == requested else "partial" if allotted else "unallocated"
        proposal.update(proposed_units=units, proposed_cases=allotted, deferred_units=proposal["requested_units"] - units,
                        status=status, limits=limits)
        allocations.append({
            "store_id": pair[0], "sku": pair[1], "dc_id": route["dc_id"], "requested_cases": requested,
            "stock_cases_before": stock_cases, "capacity_cases_before": capacity_cases,
            "proposed_cases": allotted, "stock_units_after": dc_remaining[dc_key],
            "capacity_cases_after": cap_remaining[route["dc_id"]],
        })
        if limits:
            exceptions.append(issue("allocation-limited", pair, policy["as_of"], proposal["deferred_units"]))
    events.append(event(
        "allocate-dc-capacity", "decision", "Allocate in priority order and debit shared DC stock and dispatch case capacity once.",
        {"proposed_cases": sum(row["proposed_cases"] for row in allocations)},
        "Hypothetical allocation ledger", ["store", "request cases", "stock cases", "capacity", "proposed", "capacity left"],
        [[r["store_id"], r["requested_cases"], r["stock_cases_before"], r["capacity_cases_before"], r["proposed_cases"], r["capacity_cases_after"]] for r in allocations],
        [index for index, row in enumerate(allocations) if row["proposed_cases"] < row["requested_cases"]],
    ))
    projections = []
    for pair, route in sorted(routes.items()):
        if pair in blocked:
            continue
        proposal = proposals[pair]
        arrival, end = horizons[pair]
        stock, pre_lost, post_lost = proposal["opening_available_units"], 0, 0
        for offset in range((end - as_of).days + 1):
            day = as_of + timedelta(days=offset)
            date_key = (*pair, day.isoformat())
            observed = physical_day(pair, day, arrival, stock, inbound_by_day[date_key],
                                    proposal["proposed_units"], indexes["demand"][date_key]["units"])
            projections.append(observed)
            stock = observed["closing_units"]
            if day < arrival:
                pre_lost += observed["lost_units"]
            else:
                post_lost += observed["lost_units"]
            if observed["lost_units"]:
                exceptions.append(issue("lost-demand", pair, day.isoformat(), observed["lost_units"]))
        shortfall = max(0, route["safety_units"] - stock)
        proposal.update(closing_units=stock, pre_arrival_lost_units=pre_lost, post_arrival_lost_units=post_lost,
                        safety_shortfall_units=shortfall)
        if shortfall:
            exceptions.append(issue("safety-shortfall", pair, end.isoformat(), shortfall))
    exceptions.sort(key=lambda row: (row["code"], row.get("store_id", ""), row.get("sku", ""), row.get("on", ""), row["reference"]))
    events.append(event(
        "surface-shortfalls", "exception", "Re-simulate with actual proposal quantities and expose dated shortages and excluded evidence.",
        {"exceptions": len(exceptions), "blocked_pairs": len(blocked), "lost_units": sum(r["lost_units"] for r in projections)},
        "Review exceptions", ["code", "store", "sku", "day", "units"],
        [[r["code"], r["store_id"], r["sku"], r["on"], r["units"]] for r in exceptions], range(len(exceptions)),
    ))
    rows = list(proposals.values())
    eligible = [row for row in rows if row["status"] != "blocked"]
    totals = {
        "pairs": len(rows), "blocked_pairs": len(blocked),
        **{name: sum(row[name] for row in eligible) for name in
           ("requested_units", "requested_cases", "proposed_units", "proposed_cases", "deferred_units")},
        "lost_units": sum(row["lost_units"] for row in projections),
        "safety_shortfall_units": sum(row["safety_shortfall_units"] for row in eligible),
        "exception_count": len(exceptions),
    }
    outputs = {
        "proposals": rows, "daily_projection": projections, "inbound_register": inbound_register,
        "dc_stock_controls": [
            {"dc_id": pair[0], "sku": pair[1], "opening_available_units": opening,
             "proposed_units": opening - dc_remaining[pair], "remaining_units": dc_remaining[pair]}
            for pair, opening in sorted(dc_opening.items())
        ],
        "dc_capacity_controls": [
            {"dc_id": dc_id, "dispatch_on": policy["as_of"], "opening_case_capacity": opening,
             "proposed_cases": opening - cap_remaining[dc_id], "remaining_case_capacity": cap_remaining[dc_id]}
            for dc_id, opening in sorted(cap_opening.items())
        ],
        "allocation_ledger": allocations,
        "review_packet": {
            "policy_id": policy["policy_id"], "as_of": policy["as_of"], "review_days": policy["review_days"],
            "owner_role": "Replenishment planner", "action_authorized": False, "review_required": bool(exceptions),
            "totals": totals,
            "next_action": "Review proposal quantities, dated shortages, and DC controls before any separate business action.",
        },
    }
    events.append(event(
        "publish-review-packet", "output", "Publish the complete review-only proposal, daily projections and reconciled DC controls.",
        {"proposed_units": totals["proposed_units"], "proposed_cases": totals["proposed_cases"],
         "deferred_units": totals["deferred_units"], "review_required": bool(exceptions), "action_authorized": False},
        "Final review proposals", ["store", "sku", "request", "proposed", "closing", "status"],
        [[r["store_id"], r["sku"], r["requested_units"], r["proposed_units"], r["closing_units"], r["status"]] for r in rows],
    ))
    return {"schema_version": 1, "status": "completed_with_exceptions" if exceptions else "completed",
            "outputs": outputs, "exceptions": exceptions}, events


if __name__ == "__main__":
    run_cli(solve, scenario_id="retail-01")
