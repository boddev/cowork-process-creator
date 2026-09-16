"""Deterministic, synthetic planning review; never operates or authorizes work."""
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "_shared"))
from scenario_support import run_cli


NOTICE = "Planning review only; not safe-to-work clearance or authorization."
TIME_PATTERN = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:Z|[+-][0-9]{2}:[0-9]{2})"
)
SCHEMAS = {
    "work-orders.json": {
        "work_order_id": "id", "priority": "positive", "earliest_start": "time",
        "due_at": "time", "duration_minutes": "duration", "craft_code": "id",
        "area_resource_id": "id", "tool_resource_id": "nullable-id",
        "predecessors": "ids", "plan_approved": "boolean", "owner": "id",
    },
    "requirements.json": {
        "work_order_id": "id", "item_id": "id", "required_quantity": "positive",
    },
    "kit-components.json": {
        "kit_component_id": "id", "work_order_id": "id", "item_id": "id",
        "reserved_quantity": "quantity", "available_at": "time",
    },
    "resources.json": {
        "resource_id": "id", "kind": "resource-kind", "craft_code": "nullable-id",
        "capacity": "capacity",
    },
    "resource-windows.json": {
        "window_id": "id", "resource_id": "id", "start": "minute", "end": "minute",
    },
    "commitments.json": {
        "commitment_id": "id", "resource_id": "id", "start": "minute", "end": "minute",
    },
    "prerequisite-status.json": {
        "prerequisite_id": "id", "state": "prerequisite-state",
        "completed_at": "nullable-time", "recorded_at": "time",
    },
}
KEYS = {
    "work-orders.json": ("work_order_id",),
    "requirements.json": ("work_order_id", "item_id"),
    "kit-components.json": ("kit_component_id",),
    "resources.json": ("resource_id",),
    "resource-windows.json": ("window_id",),
    "commitments.json": ("commitment_id",),
    "prerequisite-status.json": ("prerequisite_id",),
}
REVIEW = {
    "planning-approval-missing": (
        "Administrative planning approval is missing.",
        "Request administrative planning evidence; do not authorize work.",
    ),
    "kit-shortage": (
        "Reserved kit quantity is insufficient.",
        "Review the order-specific reservation shortage with the material planner.",
    ),
    "prerequisite-unresolved": (
        "A prerequisite lacks an eligible completion or contingent proposal.",
        "Clarify predecessor evidence or replan the dependent order.",
    ),
    "no-eligible-crew": (
        "No crew matches the required craft.",
        "Ask the planner to review craft coverage; do not assign unqualified resources.",
    ),
    "no-feasible-window": (
        "No complete resource window fits the order.",
        "Review candidate windows, due time, and resource conflicts.",
    ),
    "search-limit": (
        "The configured search-start limit was reached.",
        "Review the unexamined range or an explicitly revised search limit.",
    ),
}


class InputError(ValueError):
    def __init__(self, code, message, path):
        super().__init__(message)
        self.issue = {"code": code, "message": message, "path": path}


def fields(value, names, path):
    if not isinstance(value, dict) or set(value) != set(names):
        raise InputError("invalid-shape", "Expected exactly: " + ", ".join(names) + ".", path)
    return value


def integer(value, low, high, path, code="invalid-integer"):
    if type(value) is not int or not low <= value <= high:
        raise InputError(
            code, f"Expected an integer from {low} to {high} (booleans are invalid).", path,
        )
    return value


def identifier(value, path):
    if (not isinstance(value, str) or not 1 <= len(value) <= 80
            or value != value.strip() or any(not 32 <= ord(c) < 127 for c in value)):
        raise InputError("invalid-id", "Expected a nonempty printable ASCII ID up to 80 characters.", path)
    return value


def instant(value, path, *, minute=False):
    if not isinstance(value, str) or not TIME_PATTERN.fullmatch(value):
        raise InputError("invalid-time", "Expected a whole-second timestamp with an explicit offset.", path)
    if not value.endswith("Z") and (int(value[-5:-3]) > 23 or int(value[-2:]) > 59):
        raise InputError("invalid-time", "Timestamp offset hours or minutes are invalid.", path)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except (ValueError, OverflowError) as error:
        raise InputError("invalid-time", "Timestamp is outside the supported UTC date range.", path) from error
    if minute and parsed.second:
        raise InputError("invalid-time", "This interval endpoint must be minute-aligned.", path)
    return parsed


def parse_value(value, kind, path):
    if kind.startswith("nullable-"):
        return None if value is None else parse_value(value, kind[9:], path)
    if kind == "id":
        return identifier(value, path)
    if kind in ("time", "minute"):
        return instant(value, path, minute=kind == "minute")
    if kind in ("positive", "quantity", "duration", "capacity"):
        bounds = {"positive": (1, 1000000), "quantity": (0, 1000000),
                  "duration": (1, 44640), "capacity": (1, 1)}
        low, high = bounds[kind]
        return integer(value, low, high, path,
                       "invalid-duration" if kind == "duration" else "invalid-integer")
    if kind == "boolean":
        if type(value) is not bool:
            raise InputError("invalid-value", "Expected a boolean.", path)
        return value
    if kind == "ids":
        if not isinstance(value, list) or len(value) > 5000:
            raise InputError("invalid-shape", "Expected an array of at most 5000 distinct IDs.", path)
        values = [identifier(item, f"{path}[{i}]") for i, item in enumerate(value)]
        if len(set(values)) != len(values):
            raise InputError("duplicate-id", "Predecessor IDs must be distinct.", path)
        return sorted(values)
    enums = {"resource-kind": ("crew", "tool", "area"),
             "prerequisite-state": ("complete", "open")}
    if kind not in enums:
        raise RuntimeError("Undeclared validator kind: " + kind)
    if not isinstance(value, str) or value not in enums[kind]:
        raise InputError("invalid-value", "Expected one of: " + ", ".join(enums[kind]) + ".", path)
    return value


def overlap(start, end, other_start, other_end):
    return start < other_end and other_start < end


def contained(start, end, windows):
    return any(window["start"] <= start and end <= window["end"] for window in windows)


def group(rows, key):
    groups = defaultdict(list)
    for row in rows:
        groups[row[key]].append(row)
    return groups


def validate(payload):
    fields(payload, ("config", "files"), "input")
    raw_config = fields(
        payload["config"],
        ("as_of", "horizon_start", "horizon_end", "slot_minutes", "max_search_starts"),
        "config",
    )
    config = {
        key: instant(raw_config[key], "config." + key, minute=key != "as_of")
        for key in ("as_of", "horizon_start", "horizon_end")
    }
    config["slot_minutes"] = integer(raw_config["slot_minutes"], 1, 1440, "config.slot_minutes")
    config["max_search_starts"] = integer(
        raw_config["max_search_starts"], 1, 10000, "config.max_search_starts",
    )
    if not timedelta(0) < config["horizon_end"] - config["horizon_start"] <= timedelta(days=31):
        raise InputError("invalid-time", "Planning horizon must be positive and at most 31 days.", "config")
    if config["as_of"] > config["horizon_start"]:
        raise InputError("invalid-time", "Snapshot cutoff must not follow horizon start.", "config.as_of")
    raw_tables = fields(payload["files"], tuple(SCHEMAS), "files")
    tables = {}
    for name, schema in SCHEMAS.items():
        rows = raw_tables[name]
        limit = 100 if name == "work-orders.json" else 200 if name == "resources.json" else 5000
        if not isinstance(rows, list) or len(rows) > limit:
            raise InputError("invalid-shape", f"Expected an array with at most {limit} rows.", "files." + name)
        parsed_rows, seen = [], set()
        for index, raw in enumerate(rows):
            path = f"files.{name}[{index}]"
            fields(raw, tuple(schema), path)
            row = {key: parse_value(raw[key], kind, path + "." + key) for key, kind in schema.items()}
            unique = tuple(row[key] for key in KEYS[name])
            if unique in seen:
                raise InputError("duplicate-id", "Duplicate record key.", path)
            seen.add(unique)
            row["_path"] = path
            if name == "work-orders.json" and row["due_at"] <= row["earliest_start"]:
                raise InputError("invalid-time", "Due time must follow earliest start.", path)
            if name in ("resource-windows.json", "commitments.json") and row["end"] <= row["start"]:
                raise InputError("invalid-time", "Interval end must follow start.", path)
            if name == "resources.json" and ((row["kind"] == "crew") != (row["craft_code"] is not None)):
                raise InputError("invalid-value", "Only crews must have a craft code.", path + ".craft_code")
            if name == "prerequisite-status.json":
                if (row["state"] == "complete") != (row["completed_at"] is not None):
                    raise InputError("invalid-value", "Only complete prerequisites must have completed_at.", path)
                if row["completed_at"] is not None and row["completed_at"] > row["recorded_at"]:
                    raise InputError("invalid-time", "Completion must not follow its recording.", path)
            parsed_rows.append(row)
        tables[name] = parsed_rows

    orders = {row["work_order_id"]: row for row in tables["work-orders.json"]}
    resources = {row["resource_id"]: row for row in tables["resources.json"]}
    requirements = {(row["work_order_id"], row["item_id"]) for row in tables["requirements.json"]}
    for row in tables["work-orders.json"]:
        for key, kind in (("area_resource_id", "area"), ("tool_resource_id", "tool")):
            resource_id = row[key]
            if resource_id is None:
                continue
            if resource_id not in resources:
                raise InputError("missing-reference", "Resource ID has no matching export row.", row["_path"] + "." + key)
            if resources[resource_id]["kind"] != kind:
                raise InputError("invalid-value", "Resource has the wrong required kind.", row["_path"] + "." + key)
    for name in ("requirements.json", "kit-components.json"):
        for row in tables[name]:
            if row["work_order_id"] not in orders:
                raise InputError("missing-reference", "Work order ID has no matching export row.", row["_path"])
            if name == "kit-components.json" and (row["work_order_id"], row["item_id"]) not in requirements:
                raise InputError("missing-reference", "Kit component has no order-specific requirement.", row["_path"])
    for name in ("resource-windows.json", "commitments.json"):
        for row in tables[name]:
            if row["resource_id"] not in resources:
                raise InputError("missing-reference", "Resource ID has no matching export row.", row["_path"])
    for row in tables["prerequisite-status.json"]:
        if row["prerequisite_id"] in orders:
            raise InputError("invalid-value", "External prerequisite duplicates an internal work order.", row["_path"])

    remaining = set(orders)
    while remaining:
        ready = {key for key in remaining if not set(orders[key]["predecessors"]) & remaining}
        if not ready:
            raise InputError("cyclic-prerequisite", "Internal prerequisites contain a cycle.", "files.work-orders.json")
        remaining -= ready
    windows = group(tables["resource-windows.json"], "resource_id")
    commitments = group(tables["commitments.json"], "resource_id")
    for resource_id in sorted(commitments):
        ordered = sorted(commitments[resource_id], key=lambda row: (row["start"], row["commitment_id"]))
        for index, row in enumerate(ordered):
            if not contained(row["start"], row["end"], windows[resource_id]):
                raise InputError("invalid-time", "Existing commitment must fit one resource window.", row["_path"])
            if index and overlap(row["start"], row["end"], ordered[index - 1]["start"], ordered[index - 1]["end"]):
                raise InputError(
                    "contradictory-commitments", "Existing capacity-one commitments overlap.", "files.commitments.json",
                )
    return config, tables


def utc(value):
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")


def table(title, columns, rows, highlights=()):
    return {"title": title, "columns": columns, "rows": rows[:8], "total_rows": len(rows),
            "highlight_rows": [index for index in highlights if index < min(len(rows), 8)]}


def event(step_id, kind, caption, facts, *tables):
    return {"step_id": step_id, "kind": kind, "caption": caption, "facts": facts, "tables": list(tables)}


def join_evidence(config, tables):
    orders = {row["work_order_id"]: row for row in tables["work-orders.json"]}
    requirements = group(tables["requirements.json"], "work_order_id")
    kits = defaultdict(list)
    for row in tables["kit-components.json"]:
        kits[(row["work_order_id"], row["item_id"])].append(row)
    external = {row["prerequisite_id"]: row for row in tables["prerequisite-status.json"]}
    joined = {}
    for order_id in sorted(orders):
        order = orders[order_id]
        material_bound = config["horizon_start"]
        shortages = []
        for requirement in sorted(requirements[order_id], key=lambda row: row["item_id"]):
            components = sorted(
                kits[(order_id, requirement["item_id"])],
                key=lambda row: (row["available_at"], row["kit_component_id"]),
            )
            needed = requirement["required_quantity"]
            reserved = sum(component["reserved_quantity"] for component in components)
            if reserved < needed:
                shortages.append({"item_id": requirement["item_id"], "required": needed,
                                  "reserved": reserved, "missing": needed - reserved})
                continue
            available = 0
            for component in components:
                available += component["reserved_quantity"]
                if available >= needed:
                    material_bound = max(material_bound, component["available_at"])
                    break
        external_bound, pending = config["horizon_start"], []
        internal = sorted(predecessor for predecessor in order["predecessors"] if predecessor in orders)
        for predecessor in order["predecessors"]:
            if predecessor in orders:
                continue
            evidence = external.get(predecessor)
            if evidence is None or evidence["state"] != "complete" or evidence["recorded_at"] > config["as_of"]:
                pending.append(predecessor)
            else:
                external_bound = max(external_bound, evidence["completed_at"])
        crews = sorted(resource["resource_id"] for resource in tables["resources.json"]
                       if resource["kind"] == "crew" and resource["craft_code"] == order["craft_code"])
        joined[order_id] = {
            "order": order, "internal": internal, "external_pending": sorted(pending),
            "external_bound": external_bound, "material_bound": material_bound,
            "shortages": shortages, "crews": crews, "requirement_count": len(requirements[order_id]),
        }
    return joined


def grid_ceiling(bound, anchor, slot_minutes):
    seconds = int((bound - anchor).total_seconds())
    quantum = slot_minutes * 60
    try:
        return anchor + timedelta(seconds=((seconds + quantum - 1) // quantum) * quantum)
    except OverflowError as error:
        raise InputError("invalid-time", "Grid-rounded timestamp is outside the supported UTC date range.", "config") from error


def resource_failure(resource_id, start, end, windows, commitments, proposed):
    if not contained(start, end, windows[resource_id]):
        return "outside-window", None
    for booking in commitments[resource_id]:
        if overlap(start, end, booking["start"], booking["end"]):
            return "existing-booking", booking["commitment_id"]
    for booking_start, booking_end, order_id in sorted(proposed[resource_id], key=lambda row: (row[0], row[2])):
        if overlap(start, end, booking_start, booking_end):
            return "proposed-booking", order_id
    return None


def allocate(config, tables, joined):
    windows = group(tables["resource-windows.json"], "resource_id")
    commitments = group(tables["commitments.json"], "resource_id")
    for resource_id in commitments:
        commitments[resource_id].sort(key=lambda row: (row["start"], row["commitment_id"]))
    proposed = defaultdict(list)
    remaining, results, chosen, conflicts = set(joined), {}, {}, []
    while remaining:
        eligible = [key for key in remaining if not set(joined[key]["internal"]) & remaining]
        order_id = min(eligible, key=lambda key: (
            joined[key]["order"]["priority"], joined[key]["order"]["due_at"], key,
        ))
        joined_order = joined[order_id]
        order = joined_order["order"]
        pending = sorted(joined_order["external_pending"] + [
            key for key in joined_order["internal"] if key not in chosen
        ])
        row = {"work_order_id": order_id, "disposition": "deferred", "reason": None, "ready_at": None,
               "missing_materials": joined_order["shortages"], "pending_predecessors": pending, "search_starts": 0}
        if not order["plan_approved"]:
            row["reason"] = "planning-approval-missing"
        elif joined_order["shortages"]:
            row["reason"] = "kit-shortage"
        elif pending:
            row["reason"] = "prerequisite-unresolved"
        else:
            bounds = [config["horizon_start"], order["earliest_start"], joined_order["material_bound"],
                      joined_order["external_bound"]]
            bounds.extend(chosen[key]["end"] for key in joined_order["internal"])
            first = grid_ceiling(max(bounds), config["horizon_start"], config["slot_minutes"])
            row["ready_at"] = utc(first)
            if not joined_order["crews"]:
                row["reason"] = "no-eligible-crew"
            else:
                duration = timedelta(minutes=order["duration_minutes"])
                end_limit = min(config["horizon_end"], order["due_at"])
                seconds_left = int((end_limit - first).total_seconds()) - order["duration_minutes"] * 60
                possible_starts = max(0, seconds_left // (config["slot_minutes"] * 60) + 1)
                fixed = [order["area_resource_id"]]
                if order["tool_resource_id"] is not None:
                    fixed.append(order["tool_resource_id"])
                for index in range(min(possible_starts, config["max_search_starts"])):
                    start = first + timedelta(minutes=index * config["slot_minutes"])
                    end = start + duration
                    row["search_starts"] += 1
                    fixed_failed = False
                    for resource_id in fixed:
                        failure = resource_failure(resource_id, start, end, windows, commitments, proposed)
                        if failure:
                            conflicts.append({"work_order_id": order_id, "candidate_start": utc(start), "crew_id": None,
                                              "resource_id": resource_id, "reason": failure[0], "blocking_id": failure[1]})
                            fixed_failed = True
                            break
                    if fixed_failed:
                        continue
                    for crew_id in joined_order["crews"]:
                        failure = resource_failure(crew_id, start, end, windows, commitments, proposed)
                        if failure:
                            conflicts.append({"work_order_id": order_id, "candidate_start": utc(start), "crew_id": crew_id,
                                              "resource_id": crew_id, "reason": failure[0], "blocking_id": failure[1]})
                            continue
                        chosen[order_id] = {
                            "work_order_id": order_id, "start": start, "end": end,
                            "duration_minutes": order["duration_minutes"], "crew_id": crew_id,
                            "area_id": order["area_resource_id"], "tool_id": order["tool_resource_id"],
                            "contingent_on": joined_order["internal"],
                        }
                        for resource_id in [*fixed, crew_id]:
                            proposed[resource_id].append((start, end, order_id))
                        row["disposition"] = "proposed"
                        break
                    if order_id in chosen:
                        break
                if order_id not in chosen:
                    row["reason"] = "search-limit" if possible_starts > config["max_search_starts"] else "no-feasible-window"
        results[order_id] = row
        remaining.remove(order_id)
    return [results[key] for key in sorted(results)], chosen, conflicts, proposed


def union_minutes(intervals, start, end):
    clipped = sorted((max(a, start), min(b, end)) for a, b in intervals if overlap(a, b, start, end))
    merged = []
    for a, b in clipped:
        if merged and a <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(b, merged[-1][1]))
        else:
            merged.append((a, b))
    return sum(int((b - a).total_seconds()) // 60 for a, b in merged)


def resource_load(config, tables, proposed):
    windows = group(tables["resource-windows.json"], "resource_id")
    commitments = group(tables["commitments.json"], "resource_id")
    rows = []
    for resource in sorted(tables["resources.json"], key=lambda row: row["resource_id"]):
        key = resource["resource_id"]
        available = union_minutes([(row["start"], row["end"]) for row in windows[key]],
                                  config["horizon_start"], config["horizon_end"])
        committed = union_minutes([(row["start"], row["end"]) for row in commitments[key]],
                                  config["horizon_start"], config["horizon_end"])
        proposed_minutes = sum(int((end - start).total_seconds()) // 60 for start, end, _ in proposed[key])
        rows.append({"resource_id": key, "kind": resource["kind"], "available_minutes": available,
                     "committed_minutes": committed, "proposed_minutes": proposed_minutes,
                     "total_booked_minutes": committed + proposed_minutes})
    return rows


def solve(payload):
    raw_files = payload.get("files") if isinstance(payload, dict) else None
    counts = [[name, len(raw_files[name]) if isinstance(raw_files, dict)
               and isinstance(raw_files.get(name), list) else "invalid"] for name in SCHEMAS]
    events = [event(
        "intake-planning-exports", "input", "Read the supplied synthetic planning exports without live connections.",
        {"logical_exports": len(SCHEMAS)}, table("Logical export inventory", ["export", "rows"], counts),
    )]
    try:
        config, tables = validate(payload)
        events.append(event(
            "validate-planning-data", "validation", "Validated schemas, references, acyclic dependencies and existing bookings.",
            {"work_orders": len(tables["work-orders.json"]), "resources": len(tables["resources.json"]),
             "cutoff": utc(config["as_of"])},
            table("Validated intervals", ["start", "end", "grid_minutes", "start_limit"],
                  [[utc(config["horizon_start"]), utc(config["horizon_end"]),
                    config["slot_minutes"], config["max_search_starts"]]]),
        ))
        joined = join_evidence(config, tables)
        events.append(event(
            "join-readiness-evidence", "join", "Joined requirements, order-reserved kits, crews, fixed resources and predecessor evidence.",
            {"joined_orders": len(joined)},
            table("Joined work requirements", ["order", "craft", "crews", "area", "tool", "items"], [
                [key, value["order"]["craft_code"], len(value["crews"]), value["order"]["area_resource_id"],
                 value["order"]["tool_resource_id"], value["requirement_count"]]
                for key, value in joined.items()
            ]),
        ))
        events.append(event(
            "assess-readiness", "decision",
            "Computed administrative, reserved-kit and external evidence gates; internal predecessors remain contingent.",
            {"kit_shortage_orders": sum(bool(value["shortages"]) for value in joined.values()),
             "external_pending_orders": sum(bool(value["external_pending"]) for value in joined.values())},
            table("Preliminary readiness", ["order", "plan_approved", "missing_items", "external_pending", "internal_deps"], [
                [key, value["order"]["plan_approved"], len(value["shortages"]),
                 len(value["external_pending"]), len(value["internal"])]
                for key, value in joined.items()
            ]),
        ))
        orders, chosen, conflicts, proposed = allocate(config, tables, joined)
        proposals = [dict(value, start=utc(value["start"]), end=utc(value["end"]))
                     for value in sorted(chosen.values(), key=lambda row: (row["start"], row["work_order_id"]))]
        events.append(event(
            "search-resource-windows", "decision",
            "Executed dependency-aware grid searches and retained the first feasible crew/resource allocation for each proposed order.",
            {"proposed_orders": len(proposals), "examined_starts": sum(row["search_starts"] for row in orders),
             "rejected_candidates": len(conflicts)},
            table("Actual contingent proposals", ["order", "start", "end", "crew", "area", "tool"], [
                [row["work_order_id"], row["start"], row["end"], row["crew_id"], row["area_id"], row["tool_id"]]
                for row in proposals
            ]),
        ))
        queue, exceptions = [], []
        for row in orders:
            if row["reason"] is None:
                continue
            message, action = REVIEW[row["reason"]]
            queue.append({"work_order_id": row["work_order_id"], "code": row["reason"],
                          "owner": joined[row["work_order_id"]]["order"]["owner"], "next_action": action})
            exceptions.append({"code": row["reason"], "message": message, "work_order_id": row["work_order_id"]})
        events.append(event(
            "record-conflicts", "exception",
            "Recorded real failed candidates and owned planning questions; these are not work instructions or clearance.",
            {"conflict_rows": len(conflicts), "deferred_orders": len(queue)},
            table("Rejected candidates", ["order", "start", "resource", "reason", "blocking_id"], [
                [row["work_order_id"], row["candidate_start"], row["resource_id"], row["reason"], row["blocking_id"]]
                for row in conflicts
            ], range(min(len(conflicts), 8))),
            table("Deferred review queue", ["order", "reason", "owner"], [
                [row["work_order_id"], row["code"], row["owner"]] for row in queue
            ]),
        ))
        load = resource_load(config, tables, proposed)
        events.append(event(
            "summarize-resource-load", "decision",
            "Summed proposed resource minutes separately from existing commitments and unioned available windows for reporting only.",
            {"resources": len(load), "job_minutes": sum(row["duration_minutes"] for row in proposals)},
            table("Resource planning occupancy", ["resource", "kind", "available", "committed", "proposed", "total"], [
                [row["resource_id"], row["kind"], row["available_minutes"], row["committed_minutes"],
                 row["proposed_minutes"], row["total_booked_minutes"]] for row in load
            ]),
        ))
        summary = {"work_orders": len(orders), "proposed": len(proposals), "deferred": len(queue),
                   "job_minutes": sum(row["duration_minutes"] for row in proposals), "rejected_candidates": len(conflicts)}
        result = {
            "schema_version": 1, "status": "completed_with_exceptions" if exceptions else "completed",
            "outputs": {
                "notice": NOTICE,
                "planning_window": {"as_of": utc(config["as_of"]), "start": utc(config["horizon_start"]),
                                    "end": utc(config["horizon_end"]), "slot_minutes": config["slot_minutes"],
                                    "max_search_starts": config["max_search_starts"]},
                "orders": orders, "proposals": proposals, "conflicts": conflicts, "review_queue": queue,
                "resource_load": load, "summary": summary,
            },
            "exceptions": exceptions,
        }
        events.append(event(
            "emit-contingent-plan", "output", "Closed a complete synthetic planning review packet. " + NOTICE,
            summary, table("Final order dispositions", ["order", "disposition", "reason", "examined_starts"], [
                [row["work_order_id"], row["disposition"], row["reason"], row["search_starts"]] for row in orders
            ]),
        ))
        return result, events
    except InputError as error:
        events.append(event(
            "validate-planning-data", "validation",
            "Rejected invalid or contradictory planning input before creating a plan.",
            {"status": "rejected", "code": error.issue["code"]},
            table("Explicit rejection", ["path", "code", "message"],
                  [[error.issue["path"], error.issue["code"], error.issue["message"]]]),
        ))
        return {"schema_version": 1, "status": "rejected", "outputs": {}, "exceptions": [error.issue]}, events


if __name__ == "__main__":
    run_cli(solve, scenario_id="cross-industry-02")
