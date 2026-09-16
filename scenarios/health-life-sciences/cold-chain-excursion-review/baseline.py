"""Developer-only synthetic export reconciliation; no product disposition."""
from __future__ import annotations

import bisect
import json
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "_shared"))
from scenario_support import run_cli


TABLES = {
    "products": ("product_id", {"product_id": "id", "profile_id": "id"}),
    "profiles": ("profile_id", {
        "profile_id": "id", "lower_tenths_c": "temperature",
        "upper_tenths_c": "temperature", "policy_ref": "id",
    }),
    "inventory": ("lot_id", {
        "lot_id": "id", "product_id": "id", "quantity_units": "quantity",
        "owner_role_id": "id",
    }),
    "placements": ("placement_id", {
        "placement_id": "id", "lot_id": "id", "unit_id": "id",
        "entered_at": "time", "left_at": "nullable-time",
    }),
    "sensor_assignments": ("assignment_id", {
        "assignment_id": "id", "sensor_id": "id", "unit_id": "id",
        "valid_from": "time", "valid_until": "nullable-time",
    }),
    "calibrations": ("calibration_id", {
        "calibration_id": "id", "sensor_id": "id", "valid_from": "time",
        "valid_until": "time", "recorded_at": "time", "attestation_ref": "id",
    }),
    "readings": ("reading_id", {
        "reading_id": "id", "sensor_id": "id", "observed_at": "time",
        "temperature_tenths_c": "temperature",
    }),
    "correspondence": ("correspondence_id", {
        "correspondence_id": "id", "lot_id": "id", "recorded_at": "time",
        "source_role_id": "id", "reference": "id", "note": "note",
    }),
}
REASONS = (
    "conflicting-evidence", "missing-profile", "missing-placement",
    "missing-assignment", "missing-calibration", "temperature-gap", "outside-band",
)
DIAGNOSTICS = {
    "duplicate-evidence": "Repeated identical export evidence.",
    "future-evidence": "Evidence is after the as-of cutoff.",
    "orphan-evidence": "Export evidence has no matching parent.",
    "conflicting-record": "Conflicting variants share a primary key.",
}
ID = re.compile(r"SYN-[A-Z0-9][A-Z0-9-]*\Z")
TIME = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z")


class PacketError(ValueError):
    def __init__(self, location, message, code="invalid-input"):
        super().__init__(message)
        self.exception = {"code": code, "message": message, "entity_ref": location}


def fields(value, names, location):
    if not isinstance(value, dict) or set(value) != set(names):
        raise PacketError(location, f"{location} must contain exactly {', '.join(sorted(names))}.")


def integer(value, minimum, maximum, location):
    if type(value) is not int or not minimum <= value <= maximum:
        raise PacketError(location, f"{location} must be an integer in {minimum}..{maximum}.")


def timestamp(value, location):
    if not isinstance(value, str) or not TIME.fullmatch(value):
        raise PacketError(location, f"{location} must be a whole-second UTC timestamp.")
    try:
        return datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as error:
        raise PacketError(location, f"{location} is not a valid calendar timestamp.") from error


def stamp(value):
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")


def seconds(start, end):
    delta = end - start
    return delta.days * 86400 + delta.seconds


def ref(table, row):
    return f"{table}:{row[TABLES[table][0]]}"


def event(step_id, kind, caption, facts, columns, rows, *, highlights=()):
    return {
        "step_id": step_id, "kind": kind, "caption": caption, "facts": facts,
        "tables": [{
            "title": caption, "columns": columns, "rows": rows[:8],
            "total_rows": len(rows),
            "highlight_rows": [index for index in highlights if index < min(8, len(rows))],
        }],
    }


def validate(payload):
    fields(payload, {"window_start", "as_of", "policy"} | TABLES.keys(), "input")
    start = timestamp(payload["window_start"], "window_start")
    end = timestamp(payload["as_of"], "as_of")
    if start >= end:
        raise PacketError("window_start", "window_start must be before as_of.")
    policy = payload["policy"]
    fields(policy, {
        "policy_id", "max_gap_seconds", "max_rows_per_table",
        "max_total_rows", "max_derived_pairs",
    }, "policy")
    if not isinstance(policy["policy_id"], str) or not ID.fullmatch(policy["policy_id"]) or len(policy["policy_id"]) > 64:
        raise PacketError("policy.policy_id", "policy.policy_id must be a synthetic ID of at most 64 characters.")
    for key, upper in (
        ("max_gap_seconds", 86400), ("max_rows_per_table", 1000),
        ("max_total_rows", 5000), ("max_derived_pairs", 10000),
    ):
        integer(policy[key], 1, upper, f"policy.{key}")
    total = 0
    parsed_times = {}
    for table, (_, schema) in TABLES.items():
        rows = payload[table]
        if not isinstance(rows, list):
            raise PacketError(table, f"{table} must be an array.")
        total += len(rows)
        if len(rows) > policy["max_rows_per_table"]:
            raise PacketError(table, f"{table} exceeds max_rows_per_table.", "limit-exceeded")
        if total > policy["max_total_rows"]:
            raise PacketError("input", "input exceeds max_total_rows.", "limit-exceeded")
        for index, row in enumerate(rows):
            location = f"{table}[{index}]"
            fields(row, schema, location)
            for name, kind in schema.items():
                value, place = row[name], f"{location}.{name}"
                if kind == "id":
                    if not isinstance(value, str) or len(value) > 64 or not ID.fullmatch(value):
                        raise PacketError(place, f"{place} must be a synthetic ID of at most 64 characters.")
                elif kind == "note":
                    if not isinstance(value, str) or not value.strip() or not value.isascii() or len(value) > 160:
                        raise PacketError(place, f"{place} must be nonempty ASCII text of at most 160 characters.")
                elif kind == "temperature":
                    integer(value, -10000, 10000, place)
                elif kind == "quantity":
                    integer(value, 0, 1000000, place)
                elif value is not None or kind == "time":
                    parsed_times[value] = timestamp(value, place)
            if table == "profiles" and row["lower_tenths_c"] > row["upper_tenths_c"]:
                raise PacketError(location, f"{location} has inverted temperature bounds.")
            if table in ("placements", "sensor_assignments", "calibrations"):
                first, last = ("entered_at", "left_at") if table == "placements" else ("valid_from", "valid_until")
                if row[last] is not None and parsed_times[row[first]] >= parsed_times[row[last]]:
                    raise PacketError(location, f"{location} must have its interval end after its start.")
    return start, end, policy, parsed_times


def future(table, row, end, times):
    field = {
        "readings": "observed_at", "calibrations": "recorded_at",
        "correspondence": "recorded_at", "placements": "entered_at",
        "sensor_assignments": "valid_from",
    }.get(table)
    return field is not None and times[row[field]] > end


def group_evidence(payload, end, times):
    groups, active, flattened = {}, {}, {}
    for table, (key, _) in TABLES.items():
        buckets = defaultdict(list)
        for row in payload[table]:
            buckets[row[key]].append(row)
        groups[table], active[table], flattened[table] = {}, {}, []
        for record_id, copies in sorted(buckets.items()):
            variants = {json.dumps(row, sort_keys=True, separators=(",", ":")): row for row in copies}
            ordered = [variants[value] for value in sorted(variants)]
            groups[table][record_id] = ordered
            current = [row for row in ordered if not future(table, row, end, times)]
            active[table][record_id] = current
            flattened[table].extend(current)
    units = {row["unit_id"] for rows in groups["placements"].values() for row in rows}
    sensors = {row["sensor_id"] for rows in groups["sensor_assignments"].values() for row in rows}
    register, diagnostics = [], []
    for table in sorted(TABLES):
        key = TABLES[table][0]
        counts = defaultdict(int)
        for row in payload[table]:
            counts[row[key]] += 1
        for record_id, variants in groups[table].items():
            row = variants[0]
            state = "available"
            if table == "products" and row["profile_id"] not in groups["profiles"]:
                state = "orphan"
            elif table == "inventory" and row["product_id"] not in groups["products"]:
                state = "orphan"
            elif table in ("placements", "correspondence") and row["lot_id"] not in groups["inventory"]:
                state = "orphan"
            elif table == "sensor_assignments" and row["unit_id"] not in units:
                state = "orphan"
            elif table in ("calibrations", "readings") and row["sensor_id"] not in sensors:
                state = "orphan"
            if not active[table][record_id]:
                state = "future"
            if len(variants) > 1:
                state = "conflicting"
            register.append({
                "table": table, "record_id": record_id, "occurrences": counts[record_id],
                "variants": len(variants), "state": state,
            })
            codes = []
            if counts[record_id] > len(variants):
                codes.append("duplicate-evidence")
            if state in ("future", "orphan", "conflicting"):
                codes.append({"future": "future-evidence", "orphan": "orphan-evidence", "conflicting": "conflicting-record"}[state])
            for code in sorted(codes):
                diagnostics.append({"code": code, "message": DIAGNOSTICS[code], "entity_ref": f"{table}:{record_id}"})
    return groups, active, flattened, register, diagnostics


def resolved(active, table, record_id):
    rows = active[table].get(record_id, [])
    return rows[0] if len(rows) == 1 else None


def linked_rows(groups, table, field, values):
    return [row for variants in groups[table].values() for row in variants if row[field] in values]


def clipped(row, start, end, times, first="valid_from", last="valid_until"):
    lower = max(start, times[row[first]])
    upper = min(end, times[row[last]] if row[last] is not None else end)
    return (lower, upper) if lower < upper else None


def union_spans(spans):
    merged = []
    for start, end in sorted(spans):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return merged


class Budget:
    def __init__(self, maximum):
        self.maximum = maximum
        self.used = 0

    def consume(self):
        self.used += 1
        if self.used > self.maximum:
            raise PacketError("policy.max_derived_pairs", "Derived placement/interval pairs exceed max_derived_pairs.", "limit-exceeded")


def lot_contexts(groups, active, flat, start, end, times, budget):
    contexts = []
    for lot_id in sorted(groups["inventory"]):
        inventory = resolved(active, "inventory", lot_id)
        inventory_variants = active["inventory"][lot_id]
        product_ids = {row["product_id"] for row in inventory_variants}
        product_rows = linked_rows(groups, "products", "product_id", product_ids)
        profile_ids = {row["profile_id"] for row in product_rows}
        product = resolved(active, "products", inventory["product_id"]) if inventory else None
        profile = resolved(active, "profiles", product["profile_id"]) if product else None
        source_rows = {
            "inventory": groups["inventory"][lot_id], "products": product_rows,
            "profiles": linked_rows(groups, "profiles", "profile_id", profile_ids),
            "placements": linked_rows(groups, "placements", "lot_id", {lot_id}),
            "correspondence": linked_rows(groups, "correspondence", "lot_id", {lot_id}),
        }
        units = {row["unit_id"] for row in source_rows["placements"]}
        source_rows["sensor_assignments"] = linked_rows(groups, "sensor_assignments", "unit_id", units)
        sensors = {row["sensor_id"] for row in source_rows["sensor_assignments"]}
        for table in ("calibrations", "readings"):
            source_rows[table] = linked_rows(groups, table, "sensor_id", sensors)
        placements = []
        conflict = inventory is None
        for table, identifiers in (("products", product_ids), ("profiles", profile_ids)):
            conflict |= any(len(active[table].get(identifier, [])) > 1 for identifier in identifiers)
        for row in flat["placements"]:
            if row["lot_id"] != lot_id:
                continue
            span = clipped(row, start, end, times, "entered_at", "left_at")
            if span is not None:
                budget.consume()
                placements.append((span[0], span[1], row))
                conflict |= len(active["placements"][row["placement_id"]]) > 1
        contexts.append({
            "lot_id": lot_id, "inventory": inventory, "product": product, "profile": profile,
            "source_refs": sorted({ref(table, row) for table, rows in source_rows.items() for row in rows}),
            "placements": placements, "spans": union_spans([(a, b) for a, b, _ in placements]),
            "conflict": conflict, "segments": [], "points": [], "reasons": set(),
        })
    return contexts


def point_index(flat, times):
    by_sensor = defaultdict(lambda: defaultdict(list))
    for row in flat["readings"]:
        by_sensor[row["sensor_id"]][times[row["observed_at"]]].append(row)
    return {
        sensor: (sorted(points), points)
        for sensor, points in by_sensor.items()
    }


def reconstruct(context, flat, active, start, end, times, points, budget, max_gap):
    placements = context["placements"]
    units = {row["unit_id"] for _, _, row in placements}
    assignments = [row for row in flat["sensor_assignments"] if row["unit_id"] in units]
    sensors = {row["sensor_id"] for row in assignments}
    certificates = [row for row in flat["calibrations"] if row["sensor_id"] in sensors]
    cuts = {value for lower, upper, _ in placements for value in (lower, upper)}
    for row in assignments + certificates:
        span = clipped(row, start, end, times)
        if span:
            cuts.update(span)
    for sensor in sensors:
        if sensor in points:
            cuts.update(value for value in points[sensor][0] if start < value < end)
    ordered = sorted(cuts)
    for lower, upper in zip(ordered, ordered[1:]):
        occupied = [row for a, b, row in placements if a <= lower < upper <= b]
        if not occupied:
            continue
        budget.consume()
        segment = {
            "start": lower, "end": upper, "placement_ids": sorted({row["placement_id"] for row in occupied}),
            "sensor_id": None, "reading_ids": [], "temperature": None, "causes": set(),
        }
        if len(occupied) != 1:
            context["conflict"] = True
        else:
            placement = occupied[0]
            assignments_here = [
                row for row in assignments
                if row["unit_id"] == placement["unit_id"]
                and times[row["valid_from"]] <= lower
                and (row["valid_until"] is None or upper <= times[row["valid_until"]])
            ]
            if not assignments_here:
                segment["causes"].add("missing-assignment")
            elif len(assignments_here) != 1 or len(active["sensor_assignments"][assignments_here[0]["assignment_id"]]) != 1:
                context["conflict"] = True
            else:
                sensor = assignments_here[0]["sensor_id"]
                segment["sensor_id"] = sensor
                certs_here = [
                    row for row in certificates if row["sensor_id"] == sensor
                    and times[row["valid_from"]] <= lower and upper <= times[row["valid_until"]]
                ]
                if not certs_here:
                    segment["causes"].add("missing-calibration")
                elif len(certs_here) != 1 or len(active["calibrations"][certs_here[0]["calibration_id"]]) != 1:
                    context["conflict"] = True
                timestamps, grouped = points.get(sensor, ([], {}))
                position = bisect.bisect_right(timestamps, lower) - 1
                if position < 0:
                    segment["causes"].add("temperature-gap")
                else:
                    prior = timestamps[position]
                    following = timestamps[position + 1] if position + 1 < len(timestamps) else end
                    readings = grouped[prior]
                    values = {row["temperature_tenths_c"] for row in readings}
                    segment["reading_ids"] = sorted(row["reading_id"] for row in readings)
                    if len(values) != 1 or any(len(active["readings"][row["reading_id"]]) != 1 for row in readings):
                        context["conflict"] = True
                    elif seconds(prior, following) > max_gap:
                        segment["causes"].add("temperature-gap")
                    else:
                        segment["temperature"] = next(iter(values))
        context["segments"].append(segment)
    for sensor in sensors:
        timestamps, grouped = points.get(sensor, ([], {}))
        for point_time in timestamps:
            if not start <= point_time < end:
                continue
            occupied = [row for a, b, row in placements if a <= point_time < b]
            if len(occupied) != 1:
                continue
            assigned = [
                row for row in assignments if row["unit_id"] == occupied[0]["unit_id"]
                and times[row["valid_from"]] <= point_time
                and (row["valid_until"] is None or point_time < times[row["valid_until"]])
            ]
            if len(assigned) == 1 and assigned[0]["sensor_id"] == sensor:
                readings = grouped[point_time]
                if len({row["temperature_tenths_c"] for row in readings}) > 1:
                    context["conflict"] = True
                if any(len(active["readings"][row["reading_id"]]) != 1 for row in readings):
                    context["conflict"] = True
                context["points"].extend(readings)


def ledger_row(context, start, end, placements, sensor, state, temperature, readings):
    return {
        "lot_id": context["lot_id"], "placement_ids": placements, "sensor_id": sensor,
        "start": stamp(start), "end": stamp(end), "evidence_state": state,
        "temperature_tenths_c": temperature, "overlap_seconds": seconds(start, end),
        "reading_ids": readings,
    }


def classify(context):
    inventory, product, profile = context["inventory"], context["product"], context["profile"]
    reasons = context["reasons"]
    ledger, temperatures, outside_points = [], [], set()
    covered = outside = 0
    if profile is not None:
        low, high = profile["lower_tenths_c"], profile["upper_tenths_c"]
        for reading in context["points"]:
            value = reading["temperature_tenths_c"]
            temperatures.append(value)
            if not low <= value <= high:
                outside_points.add(reading["reading_id"])
        for segment in context["segments"]:
            reasons.update(segment["causes"])
            value = segment["temperature"]
            state = "unknown"
            if not segment["causes"] and value is not None:
                state = "inside-band" if low <= value <= high else "outside-band"
                duration = seconds(segment["start"], segment["end"])
                covered += duration
                outside += duration if state == "outside-band" else 0
                temperatures.append(value)
            ledger.append(ledger_row(
                context, segment["start"], segment["end"], segment["placement_ids"],
                segment["sensor_id"], state, value if state != "unknown" else None,
                segment["reading_ids"],
            ))
        if outside or outside_points:
            reasons.add("outside-band")
    occupied = sum(seconds(a, b) for a, b in context["spans"])
    context["ledger"] = ledger
    context["result"] = {
        "lot_id": context["lot_id"],
        "product_id": inventory["product_id"] if inventory else None,
        "profile_id": product["profile_id"] if product else None,
        "owner_role_id": inventory["owner_role_id"] if inventory else None,
        "quantity_units": inventory["quantity_units"] if inventory else None,
        "occupied_seconds": occupied, "covered_seconds": covered,
        "modeled_outside_seconds": outside, "unknown_seconds": occupied - covered,
        "observed_outside_reading_ids": sorted(outside_points),
        "temperature_min_tenths_c": min(temperatures) if temperatures else None,
        "temperature_max_tenths_c": max(temperatures) if temperatures else None,
        "review_state": "no-observed-exception", "reason_codes": [],
        "source_refs": context["source_refs"],
    }


def isolate(context):
    reasons = context["reasons"]
    unresolved = context["conflict"] or context["profile"] is None or not context["placements"]
    if unresolved:
        reasons.clear()
        if context["conflict"]:
            reasons.add("conflicting-evidence")
        elif context["profile"] is None:
            reasons.add("missing-profile")
        if not context["placements"]:
            reasons.add("missing-placement")
        context["ledger"] = [
            ledger_row(
                context, lower, upper,
                sorted({row["placement_id"] for a, b, row in context["placements"] if a < upper and lower < b}),
                None, "unknown", None, [],
            )
            for lower, upper in context["spans"]
        ]
        context["result"].update({
            "covered_seconds": 0, "modeled_outside_seconds": None,
            "unknown_seconds": context["result"]["occupied_seconds"],
            "observed_outside_reading_ids": [],
            "temperature_min_tenths_c": None, "temperature_max_tenths_c": None,
        })
    context["result"]["reason_codes"] = [reason for reason in REASONS if reason in reasons]
    context["result"]["review_state"] = "pending-quality-review" if reasons else "no-observed-exception"


def solve(payload):
    events = []
    counts = [
        [table, len(payload[table])]
        for table in TABLES
        if isinstance(payload, dict) and isinstance(payload.get(table), list)
    ]
    events.append(event(
        "load-cold-chain-export", "input", "Load synthetic exports; no live sensor or inventory access.",
        {"tables_observed": len(counts), "raw_rows": sum(row[1] for row in counts)},
        ["table", "raw_rows"], counts,
    ))
    try:
        start, end, policy, times = validate(payload)
        groups, active, flat, register, diagnostics = group_evidence(payload, end, times)
        events.append(event(
            "validate-sensor-evidence", "validation", "Validate fields and retain export multiplicity, conflicts and exclusions.",
            {"source_keys": len(register), "export_diagnostics": len(diagnostics)},
            ["table", "record_id", "copies", "variants", "state"],
            [[row["table"], row["record_id"], row["occurrences"], row["variants"], row["state"]] for row in register],
        ))
        budget = Budget(policy["max_derived_pairs"])
        contexts = lot_contexts(groups, active, flat, start, end, times, budget)
        events.append(event(
            "join-lot-profile-occupancy", "join", "Join lot profiles, whole-lot placements and related sensor evidence.",
            {"lots": len(contexts), "placement_pairs": budget.used},
            ["lot_id", "profile_id", "placements", "sources"],
            [[c["lot_id"], c["product"]["profile_id"] if c["product"] else None, len(c["placements"]), len(c["source_refs"])] for c in contexts],
        ))
        points = point_index(flat, times)
        for context in contexts:
            reconstruct(context, flat, active, start, end, times, points, budget, policy["max_gap_seconds"])
        reconstructed = [
            [c["lot_id"], stamp(s["start"]), stamp(s["end"]), s["sensor_id"], seconds(s["start"], s["end"])]
            for c in contexts for s in c["segments"]
        ]
        events.append(event(
            "reconstruct-covered-intervals", "join", "Intersect half-open occupancy, sensor, calibration and bounded reading intervals.",
            {"elementary_intervals": len(reconstructed), "derived_pairs": budget.used, "max_gap_seconds": policy["max_gap_seconds"]},
            ["lot_id", "start", "end", "sensor_id", "seconds"], reconstructed,
        ))
        for context in contexts:
            classify(context)
        events.append(event(
            "classify-observations", "decision", "Calculate provisional covered and outside seconds before conservative conflict quarantine.",
            {"lots_assessed": len(contexts)},
            ["lot_id", "occupied_s", "covered_s", "outside_s", "unknown_s"],
            [[c["lot_id"], c["result"]["occupied_seconds"], c["result"]["covered_seconds"], c["result"]["modeled_outside_seconds"], c["result"]["unknown_seconds"]] for c in contexts],
        ))
        for context in contexts:
            isolate(context)
        review = [c["result"] for c in contexts]
        events.append(event(
            "isolate-coverage-conflicts", "exception", "Keep unknown coverage distinct from zero; do not infer product viability.",
            {"flagged_lots": sum(bool(row["reason_codes"]) for row in review)},
            ["lot_id", "review_state", "outside_s", "unknown_s", "reasons"],
            [[row["lot_id"], row["review_state"], row["modeled_outside_seconds"], row["unknown_seconds"], ", ".join(row["reason_codes"])] for row in review],
            highlights=[index for index, row in enumerate(review) if row["reason_codes"]],
        ))
        correspondence = [
            row for key in sorted(active["correspondence"])
            if (row := resolved(active, "correspondence", key)) is not None
            and row["lot_id"] in groups["inventory"]
        ]
        requests, exceptions = [], list(diagnostics)
        for row in review:
            if row["reason_codes"]:
                requests.append({
                    "lot_id": row["lot_id"], "owner_role_id": row["owner_role_id"],
                    "reason_codes": list(row["reason_codes"]),
                    "prior_correspondence_ids": [item["correspondence_id"] for item in correspondence if item["lot_id"] == row["lot_id"]],
                    "action": "request-quality-review",
                })
            for reason in row["reason_codes"]:
                exceptions.append({
                    "code": reason, "message": f"Quality review required: {reason}.",
                    "entity_ref": f"inventory:{row['lot_id']}",
                })
        quantities = [row["quantity_units"] for row in review if row["reason_codes"]]
        summary = {
            "total_lots": len(review), "review_lots": len(requests),
            "review_units": None if any(value is None for value in quantities) else sum(quantities),
            "evidence_gap_lots": sum(bool(set(row["reason_codes"]) - {"outside-band"}) for row in review),
            "no_observed_exception_lots": len(review) - len(requests),
        }
        events.append(event(
            "aggregate-quality-review", "decision", "Count each reviewed lot's quantity once; keep correspondence as evidence only.",
            dict(summary),
            ["lot_id", "quantity_units", "review_required"],
            [[row["lot_id"], row["quantity_units"], bool(row["reason_codes"])] for row in review],
        ))
        ledger = sorted(
            [row for c in contexts for row in c["ledger"]],
            key=lambda row: (row["lot_id"], row["start"], row["end"], row["sensor_id"] or ""),
        )
        outputs = {
            "window_start": stamp(start), "as_of": stamp(end), "policy_id": policy["policy_id"],
            "duration_model": "bounded-zero-order-hold", "lot_review": review,
            "interval_ledger": ledger, "inventory_summary": summary,
            "draft_quality_requests": requests, "correspondence": correspondence,
            "evidence_register": register, "physical_actions_performed": False,
            "quality_disposition_required": True,
        }
        status = "completed_with_exceptions" if exceptions else "completed"
        events.append(event(
            "write-excursion-packet", "output", "Write the draft review packet; no physical action or quality disposition performed.",
            {"status": status, "lots": len(review), "intervals": len(ledger), "draft_requests": len(requests), "physical_actions": False},
            ["lot_id", "action", "reasons"],
            [[row["lot_id"], row["action"], ", ".join(row["reason_codes"])] for row in requests],
        ))
        return {"schema_version": 1, "status": status, "outputs": outputs, "exceptions": exceptions}, events
    except PacketError as error:
        events.append(event(
            "validate-sensor-evidence", "validation", "Reject the invalid input packet, not any product.",
            {"status": "rejected", "code": error.exception["code"]},
            ["field", "diagnostic"], [[error.exception["entity_ref"], error.exception["message"]]],
        ))
        return {"schema_version": 1, "status": "rejected", "outputs": {}, "exceptions": [error.exception]}, events


if __name__ == "__main__":
    run_cli(solve, scenario_id="hls-02")
