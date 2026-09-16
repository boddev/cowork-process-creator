"""Deterministic synthetic administrative reconciliation; no clinical actions."""
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "_shared"))
from scenario_support import run_cli


SCHEMAS = {
    "orders": {
        "order_id": "token", "subject_token": "?token", "ordered_at": "utc",
        "owner_role_id": "?token",
    },
    "order_lines": {
        "order_line_id": "token", "order_id": "token", "test_code": "token",
        "requested_specimen_kind": "?token",
    },
    "order_events": {
        "event_id": "token", "order_id": "token", "event_seq": "sequence",
        "effective_at": "utc", "recorded_at": "utc",
        "state": ("active", "cancelled"),
    },
    "receipts": {
        "receipt_id": "token", "specimen_id": "token", "order_id": "?token",
        "subject_token": "?token", "specimen_kind": "?token",
        "collected_at": "?utc", "received_at": "utc",
    },
    "accessions": {
        "accession_id": "token", "specimen_id": "token", "order_line_id": "token",
        "subject_token": "?token", "test_code": "token",
        "accessioned_at": "utc", "recorded_at": "utc",
    },
    "test_catalog": {
        "test_code": "token", "expected_specimen_kind": "?token", "policy_ref": "token",
    },
    "clarifications": {
        "clarification_id": "token",
        "entity_kind": ("order", "order-line", "specimen", "accession"),
        "entity_id": "token", "recorded_at": "utc", "reference": "token", "note": "note",
    },
}
PRIMARY_KEYS = {table: next(iter(fields)) for table, fields in SCHEMAS.items()}
POLICY_LIMITS = {
    "accession_sla_minutes": (60, 0, 10080),
    "max_rows_per_table": (1000, 1, 1000),
    "max_total_rows": (5000, 1, 5000),
    "max_derived_pairs": (10000, 1, 10000),
}
AVAILABILITY = {
    "orders": ("ordered_at",),
    "order_events": ("effective_at", "recorded_at"),
    "receipts": ("received_at",),
    "accessions": ("accessioned_at", "recorded_at"),
    "clarifications": ("recorded_at",),
}
REASONS = (
    "conflicting-evidence", "impossible-chronology", "missing-link",
    "missing-order-state", "missing-identity", "identity-mismatch", "cancelled-order",
    "test-code-mismatch", "missing-test-metadata", "specimen-label-mismatch",
    "missing-collection-time", "missing-receipt", "accession-overdue",
)
PRIORITY = {reason: index for index, reason in enumerate(REASONS)}
TOKEN = re.compile(r"SYN-[A-Z0-9]+(?:-[A-Z0-9]+)*\Z")
UTC = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z\Z")
REVIEW_MESSAGE = "Administrative evidence requires qualified review; no clinical action."
DUPLICATE_MESSAGE = "Identical export rows collapsed without changing evidence."


def instant(value):
    return datetime.fromisoformat(value[:-1] + "+00:00")


def diagnostic(path, message):
    return {
        "code": "malformed-input",
        "message": "Input packet rejected: " + message,
        "path": path,
    }


def shape(value, required, path, errors, optional=()):
    if not isinstance(value, dict) or not set(required) <= value.keys() or (
        value.keys() - set(required) - set(optional)
    ):
        errors.append(diagnostic(path, "object with exactly the documented fields required."))
        return False
    return True


def integer(value, lower, upper, path, errors):
    if type(value) is not int or not lower <= value <= upper:
        errors.append(diagnostic(
            path, f"integer in {lower}..{upper} required (boolean is not an integer).",
        ))
        return False
    return True


def field(value, kind, path, errors):
    if isinstance(kind, tuple):
        if not isinstance(value, str) or value not in kind:
            errors.append(diagnostic(path, "one of " + ", ".join(kind) + " required."))
        return
    if kind.startswith("?"):
        if value is None:
            return
        kind = kind[1:]
    if kind == "token":
        if not isinstance(value, str) or len(value) > 64 or not TOKEN.fullmatch(value):
            errors.append(diagnostic(path, "synthetic SYN- token of at most 64 characters required."))
    elif kind == "utc":
        valid = isinstance(value, str) and UTC.fullmatch(value)
        if valid:
            try:
                instant(value)
            except ValueError:
                valid = False
        if not valid:
            errors.append(diagnostic(
                path, "real whole-second UTC timestamp YYYY-MM-DDTHH:MM:SSZ required.",
            ))
    elif kind == "sequence":
        integer(value, 1, 1000000, path, errors)
    elif kind == "note":
        if (
            not isinstance(value, str) or not value.strip() or len(value) > 240
            or any(ord(char) < 32 or ord(char) == 127 for char in value)
        ):
            errors.append(diagnostic(path, "nonblank plain note of 1..240 characters without controls required."))
    else:
        raise ValueError(f"Unsupported local schema type: {kind}")


def validate(payload):
    errors = []
    required = {"schema_version", "as_of", "policy"} | SCHEMAS.keys()
    if not shape(payload, required, "packet", errors):
        return None, errors
    integer(payload["schema_version"], 1, 1, "schema_version", errors)
    field(payload["as_of"], "utc", "as_of", errors)
    policy = {}
    if shape(payload["policy"], {"policy_id"}, "policy", errors, POLICY_LIMITS):
        supplied = payload["policy"]
        field(supplied["policy_id"], "token", "policy.policy_id", errors)
        policy["policy_id"] = supplied["policy_id"]
        for name, (default, lower, upper) in POLICY_LIMITS.items():
            value = supplied.get(name, default)
            if integer(value, lower, upper, "policy." + name, errors):
                policy[name] = value
    raw_count = 0
    for table, schema in SCHEMAS.items():
        rows = payload[table]
        if not isinstance(rows, list):
            errors.append(diagnostic(table, "array of documented row objects required."))
            continue
        raw_count += len(rows)
        # Hard ceilings bound diagnostics even if the supplied policy is invalid.
        limit = policy.get("max_rows_per_table", 1000)
        if len(rows) > limit:
            errors.append(diagnostic(table, f"raw rows exceed max_rows_per_table ({limit})."))
            continue
        for index, row in enumerate(rows, 1):
            path = f"{table}[{index}]"
            if shape(row, schema, path, errors):
                for name, kind in schema.items():
                    field(row[name], kind, f"{path}.{name}", errors)
    total_limit = policy.get("max_total_rows", 5000)
    if raw_count > total_limit:
        errors.append(diagnostic("packet", f"raw table rows exceed max_total_rows ({total_limit})."))
    return (None if errors else policy), errors


def table_snapshot(title, columns, rows, highlights=()):
    return {
        "title": title,
        "columns": columns,
        "rows": rows[:8],
        "total_rows": len(rows),
        "highlight_rows": [index for index in highlights if 0 <= index < min(8, len(rows))],
    }


def event(step_id, kind, caption, facts, *tables):
    return {
        "step_id": step_id, "kind": kind, "caption": caption,
        "facts": facts, "tables": list(tables),
    }


def rejected(errors, events):
    errors = sorted(errors, key=lambda item: (item["path"], item["message"]))
    events.append(event(
        "validate-reconciliation-records", "validation",
        "Input packet rejected with explicit diagnostics; no specimen decision or partial ledger.",
        {"diagnostics": len(errors), "packet_rejected": True},
        table_snapshot(
            "Packet diagnostics", ["path", "code", "message"],
            [[item["path"], item["code"], item["message"]] for item in errors],
            range(len(errors)),
        ),
    ))
    return {"schema_version": 1, "status": "rejected", "outputs": {}, "exceptions": errors}, events


@dataclass
class Record:
    table: str
    data: dict
    source_rows: list[int]

    @property
    def key(self):
        return self.data[PRIMARY_KEYS[self.table]]

    @property
    def refs(self):
        return [f"{self.table}:{self.key}@{index}" for index in self.source_rows]


def source_refs(records):
    return sorted({reference for record in records for reference in record.refs})


def ranked(reasons):
    return sorted(set(reasons), key=PRIORITY.__getitem__)


def index_records(records, *fields):
    grouped = defaultdict(list)
    for record in records:
        values = tuple(record.data[name] for name in fields)
        key = values[0] if len(fields) == 1 else values
        grouped[key].append(record)
    return grouped


def prepare_records(payload):
    eligible = {}
    duplicates, excluded = [], []
    logical_counts = {}
    for table in SCHEMAS:
        unique = {}
        for index, row in enumerate(payload[table], 1):
            signature = json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
            if signature in unique:
                unique[signature].source_rows.append(index)
            else:
                unique[signature] = Record(table, row, [index])
        logical_counts[table] = len(unique)
        eligible[table] = []
        for record in sorted(unique.values(), key=lambda item: (item.key, item.source_rows[0])):
            if len(record.source_rows) > 1:
                duplicates.append({
                    "table": table, "record_id": record.key,
                    "source_rows": list(record.source_rows),
                })
            future = [
                "future-" + name.replace("_", "-")
                for name in AVAILABILITY.get(table, ())
                if record.data[name] > payload["as_of"]
            ]
            if future:
                excluded.append({
                    "table": table, "record_id": record.key,
                    "source_refs": sorted(record.refs), "reason_codes": future,
                })
            else:
                eligible[table].append(record)
    duplicates.sort(key=lambda item: (item["table"], item["record_id"], item["source_rows"][0]))
    excluded.sort(key=lambda item: (
        item["table"], item["record_id"],
        min(int(reference.rsplit("@", 1)[1]) for reference in item["source_refs"]),
    ))
    return eligible, duplicates, excluded, logical_counts


class Evidence:
    def __init__(self, tables):
        self.tables = tables
        self.by_key = {
            table: index_records(records, PRIMARY_KEYS[table])
            for table, records in tables.items()
        }
        self.conflicts = {
            (table, key)
            for table, groups in self.by_key.items()
            for key, records in groups.items() if len(records) > 1
        }
        self.lines_by_order = index_records(tables["order_lines"], "order_id")
        self.events_by_order = index_records(tables["order_events"], "order_id")
        self.receipts_by_order = index_records(tables["receipts"], "order_id")
        self.receipts_by_specimen = index_records(tables["receipts"], "specimen_id")
        self.accessions_by_line = index_records(tables["accessions"], "order_line_id")
        self.accessions_by_pair = index_records(tables["accessions"], "specimen_id", "order_line_id")
        self.targets = {
            "order": set(self.by_key["orders"]),
            "order-line": set(self.by_key["order_lines"]),
            "specimen": set(self.receipts_by_specimen),
            "accession": set(self.by_key["accessions"]),
        }
        self.clarifications = index_records([
            record for record in tables["clarifications"] if self.valid_clarification(record)
        ], "entity_kind", "entity_id")
        self.states = {
            key: self.resolve_state(key) for key in self.by_key["orders"]
        }

    def valid_clarification(self, record):
        return record.data["entity_id"] in self.targets[record.data["entity_kind"]]

    def resolve_state(self, order_id):
        history = self.events_by_order.get(order_id, [])
        result = {"state": "unknown", "event_ids": [], "conflict": False, "chronology": False}
        if not history:
            return result
        maximum = max(record.data["event_seq"] for record in history)
        latest = [record for record in history if record.data["event_seq"] == maximum]
        result["conflict"] = len(latest) != 1 or any(
            ("order_events", record.key) in self.conflicts for record in history
        )
        headers = self.by_key["orders"].get(order_id, [])
        if not result["conflict"] and headers:
            result["state"] = latest[0].data["state"]
            result["event_ids"] = [latest[0].key]
        latest_order = max((record.data["ordered_at"] for record in headers), default="")
        result["chronology"] = any(
            record.data["recorded_at"] < record.data["effective_at"]
            or record.data["effective_at"] < latest_order for record in history
        )
        by_sequence = index_records(history, "event_seq")
        prior_effective, prior_recorded = "", ""
        for sequence in sorted(by_sequence):
            records = by_sequence[sequence]
            if any(
                record.data["effective_at"] < prior_effective
                or record.data["recorded_at"] < prior_recorded for record in records
            ):
                result["chronology"] = True
            prior_effective = max(prior_effective, *(record.data["effective_at"] for record in records))
            prior_recorded = max(prior_recorded, *(record.data["recorded_at"] for record in records))
        return result

    def triples(self, limit):
        triples = set()
        for record in self.tables["order_lines"]:
            order_id, line_id = record.data["order_id"], record.key
            candidates = {
                receipt.data["specimen_id"] for receipt in self.receipts_by_order.get(order_id, [])
            } | {
                accession.data["specimen_id"] for accession in self.accessions_by_line.get(line_id, [])
            }
            for specimen_id in candidates or {None}:
                triples.add((order_id, line_id, specimen_id))
                if len(triples) > limit:
                    return None
        for record in self.tables["accessions"]:
            line_id, specimen_id = record.data["order_line_id"], record.data["specimen_id"]
            if line_id not in self.by_key["order_lines"]:
                orders = {
                    receipt.data["order_id"]
                    for receipt in self.receipts_by_specimen.get(specimen_id, [])
                    if receipt.data["order_id"] is not None
                }
                order_id = next(iter(orders)) if len(orders) == 1 else None
                triples.add((order_id, line_id, specimen_id))
                if len(triples) > limit:
                    return None
        represented = {specimen_id for _, _, specimen_id in triples}
        for specimen_id, records in self.receipts_by_specimen.items():
            if specimen_id not in represented:
                for order_id in {record.data["order_id"] for record in records}:
                    triples.add((order_id, None, specimen_id))
                    if len(triples) > limit:
                        return None
        return sorted(triples, key=lambda triple: tuple(value or "" for value in triple))

    def unmatched(self):
        issues = defaultdict(set)
        for table, records in self.tables.items():
            for record in records:
                data = record.data
                reasons = set()
                if (table, record.key) in self.conflicts:
                    reasons.add("conflicting-evidence")
                if table == "orders":
                    if not self.lines_by_order.get(record.key):
                        reasons.add("missing-link")
                elif table == "order_events":
                    if data["order_id"] not in self.by_key["orders"]:
                        reasons.add("missing-link")
                elif table == "order_lines":
                    if data["order_id"] not in self.by_key["orders"]:
                        reasons.add("missing-link")
                    if data["test_code"] not in self.by_key["test_catalog"]:
                        reasons.add("missing-test-metadata")
                    if not self.receipts_by_order.get(data["order_id"]):
                        reasons.add("missing-receipt")
                elif table == "receipts":
                    if (
                        data["order_id"] not in self.by_key["orders"]
                        or not self.lines_by_order.get(data["order_id"])
                    ):
                        reasons.add("missing-link")
                elif table == "accessions":
                    lines = self.by_key["order_lines"].get(data["order_line_id"], [])
                    receipts = self.receipts_by_specimen.get(data["specimen_id"], [])
                    receipt_orders = {receipt.data["order_id"] for receipt in receipts}
                    if not lines or not any(line.data["order_id"] in receipt_orders for line in lines):
                        reasons.add("missing-link")
                    if not receipts:
                        reasons.update(("missing-link", "missing-receipt"))
                elif table == "clarifications" and not self.valid_clarification(record):
                    reasons.add("missing-link")
                if reasons:
                    issues[(table, record.key)].update(reasons)
        return [
            {
                "table": table, "record_id": key,
                "source_refs": source_refs(self.by_key[table][key]),
                "reason_codes": ranked(reasons),
            }
            for (table, key), reasons in sorted(issues.items())
        ]

    def attach(self, triple):
        order_id, line_id, specimen_id = triple
        headers = self.by_key["orders"].get(order_id, [])
        lines = self.by_key["order_lines"].get(line_id, [])
        receipts = self.receipts_by_specimen.get(specimen_id, [])
        accessions = self.accessions_by_pair.get((specimen_id, line_id), [])
        history = self.events_by_order.get(order_id, [])
        catalog = [
            record for code in sorted({line.data["test_code"] for line in lines})
            for record in self.by_key["test_catalog"].get(code, [])
        ]
        targets = {("order", order_id), ("order-line", line_id), ("specimen", specimen_id)}
        targets.update(("accession", record.key) for record in accessions)
        clarifications = [
            record for target in sorted(targets, key=lambda pair: (pair[0], pair[1] or ""))
            for record in self.clarifications.get(target, [])
        ]
        if order_id not in self.states:
            self.states[order_id] = self.resolve_state(order_id)
        state = self.states[order_id]
        attached = headers + lines + receipts + accessions + history + catalog + clarifications
        row = {
            "order_id": order_id, "order_line_id": line_id, "specimen_id": specimen_id,
            "receipt_ids": sorted({record.key for record in receipts}),
            "accession_ids": sorted({record.key for record in accessions}),
            "state_event_ids": list(state["event_ids"]),
            "imported_order_state": state["state"],
            "administrative_state": "review", "reason_codes": [], "age_seconds": None,
            "source_refs": source_refs(attached),
        }
        return {
            "row": row, "headers": headers, "lines": lines, "receipts": receipts,
            "accessions": accessions, "history": history, "catalog": catalog,
            "clarifications": clarifications, "state": state, "attached": attached,
        }

    def assess(self, item, line_specimens):
        row = item["row"]
        headers, lines, receipts = item["headers"], item["lines"], item["receipts"]
        accessions, catalog, state = item["accessions"], item["catalog"], item["state"]
        reasons = set()
        if (
            any((record.table, record.key) in self.conflicts for record in item["attached"])
            or state["conflict"] or len(receipts) > 1
            or len(line_specimens.get(row["order_line_id"], set())) > 1
            or len(row["accession_ids"]) > 1
        ):
            reasons.add("conflicting-evidence")
        latest_order = max((record.data["ordered_at"] for record in headers), default="")
        latest_receipt = max((record.data["received_at"] for record in receipts), default="")
        chronology = state["chronology"] or any(
            record.data["recorded_at"] < record.data["effective_at"]
            for record in item["history"]
        )
        for record in receipts:
            received, collected = record.data["received_at"], record.data["collected_at"]
            if received < latest_order or (
                collected is not None and (received < collected or collected < latest_order)
            ):
                chronology = True
        if any(
            record.data["accessioned_at"] < latest_receipt
            or record.data["accessioned_at"] < latest_order
            or record.data["recorded_at"] < record.data["accessioned_at"]
            for record in accessions
        ):
            chronology = True
        if chronology:
            reasons.add("impossible-chronology")
        if (
            not headers or not lines
            or any(line.data["order_id"] != row["order_id"] for line in lines)
            or any(
                receipt.data["order_id"] is None or receipt.data["order_id"] != row["order_id"]
                for receipt in receipts
            )
            or (accessions and not receipts)
        ):
            reasons.add("missing-link")
        if headers and not item["history"]:
            reasons.add("missing-order-state")
        identities = [record.data["subject_token"] for record in headers + receipts + accessions]
        if None in identities:
            reasons.add("missing-identity")
        if len({value for value in identities if value is not None}) > 1:
            reasons.add("identity-mismatch")
        if state["state"] == "cancelled":
            reasons.add("cancelled-order")
        line_codes = {record.data["test_code"] for record in lines}
        accession_codes = {record.data["test_code"] for record in accessions}
        if line_codes and accession_codes and len(line_codes | accession_codes) > 1:
            reasons.add("test-code-mismatch")
        if lines:
            labels = (
                [record.data["requested_specimen_kind"] for record in lines]
                + [record.data["specimen_kind"] for record in receipts]
                + [record.data["expected_specimen_kind"] for record in catalog]
            )
            if None in labels or any(code not in self.by_key["test_catalog"] for code in line_codes):
                reasons.add("missing-test-metadata")
            if len({value for value in labels if value is not None}) > 1:
                reasons.add("specimen-label-mismatch")
        if any(record.data["collected_at"] is None for record in receipts):
            reasons.add("missing-collection-time")
        if not receipts:
            reasons.add("missing-receipt")
        row["reason_codes"] = ranked(reasons)


def draft(entity_key, reasons, owner=None, references=()):
    return {
        "entity_key": entity_key, "reason_codes": list(reasons),
        "owner_role_id": owner, "existing_clarification_refs": sorted(set(references)),
        "action": "request-administrative-review",
    }


def build_queue(items, unmatched):
    queue = []
    for item in items:
        row = item["row"]
        if not row["reason_codes"]:
            continue
        key = "row:" + "|".join(row[name] or "-" for name in ("order_id", "order_line_id", "specimen_id"))
        owner = item["headers"][0].data["owner_role_id"] if len(item["headers"]) == 1 else None
        queue.append(draft(
            key, row["reason_codes"], owner,
            [record.data["reference"] for record in item["clarifications"]],
        ))
    for record in unmatched:
        if record["table"] in {"orders", "order_events", "test_catalog", "clarifications"}:
            queue.append(draft(f"{record['table']}:{record['record_id']}", record["reason_codes"]))
    return sorted(queue, key=lambda item: (PRIORITY[item["reason_codes"][0]], item["entity_key"]))


def solve(payload):
    raw_counts = {
        table: len(payload[table]) if (
            isinstance(payload, dict) and isinstance(payload.get(table), list)
        ) else None
        for table in SCHEMAS
    }
    as_of = payload.get("as_of") if isinstance(payload, dict) else None
    events = [event(
        "load-accession-export", "input",
        "Load the supplied synthetic exports and record raw counts before any filtering or joins.",
        {"as_of": as_of if isinstance(as_of, str) else None,
         "raw_rows": sum(count for count in raw_counts.values() if count is not None)},
        table_snapshot("Raw input tables", ["table", "raw_rows"], [list(pair) for pair in raw_counts.items()]),
    )]
    policy, errors = validate(payload)
    if errors:
        return rejected(errors, events)
    tables, duplicates, excluded, logical_counts = prepare_records(payload)
    evidence = Evidence(tables)
    duplicate_rows = sum(len(record["source_rows"]) - 1 for record in duplicates)
    events.append(event(
        "validate-reconciliation-records", "validation",
        "Validated the schema and bounds; collapsed exact copies, retained provenance, and isolated unavailable evidence.",
        {"errors": 0, "raw_rows": sum(raw_counts.values()),
         "logical_records": sum(logical_counts.values()), "duplicate_rows_collapsed": duplicate_rows,
         "excluded_records": len(excluded), "conflicting_keys": len(evidence.conflicts)},
        table_snapshot(
            "Validation and availability", ["table", "raw", "logical", "eligible", "conflicting_keys"],
            [[table, raw_counts[table], logical_counts[table], len(tables[table]),
              sum(1 for kind, _ in evidence.conflicts if kind == table)] for table in SCHEMAS],
        ),
    ))
    state_rows = [
        [order_id, state["state"], ",".join(state["event_ids"]),
         len(evidence.events_by_order.get(order_id, [])), state["conflict"]]
        for order_id, state in sorted(evidence.states.items())
    ]
    events.append(event(
        "resolve-as-of-orders", "join",
        "Joined eligible dated events to headers; unique highest sequence selects imported state, never testing authorization.",
        {"orders": len(state_rows),
         "active": sum(state["state"] == "active" for state in evidence.states.values()),
         "cancelled": sum(state["state"] == "cancelled" for state in evidence.states.values()),
         "unknown": sum(state["state"] == "unknown" for state in evidence.states.values()),
         "excluded_records": len(excluded)},
        table_snapshot(
            "Imported as-of state", ["order_id", "state", "selected_events", "eligible_events", "ambiguous"],
            state_rows, [index for index, row in enumerate(state_rows) if row[1] != "active"],
        ),
    ))
    triples = evidence.triples(policy["max_derived_pairs"])
    if triples is None:
        return rejected([diagnostic(
            "policy.max_derived_pairs",
            f"derived triples exceed max_derived_pairs ({policy['max_derived_pairs']}).",
        )], events)
    items = [evidence.attach(triple) for triple in triples]
    unmatched = evidence.unmatched()
    events.append(event(
        "join-receipts-accessions", "join",
        "Constructed exact order/line/specimen triples and retained unmatched links; no fuzzy repair or candidate selection.",
        {"ledger_triples": len(triples), "unmatched_groups": len(unmatched)},
        table_snapshot(
            "Exact candidate triples", ["order_id", "line_id", "specimen_id", "receipts", "accessions", "source_refs"],
            [[*triple, len(item["row"]["receipt_ids"]), len(item["row"]["accession_ids"]),
              len(item["row"]["source_refs"])] for triple, item in zip(triples, items)],
            [index for index, item in enumerate(items) if not item["headers"] or not item["receipts"]],
        ),
    ))
    line_specimens = defaultdict(set)
    for _, line_id, specimen_id in triples:
        if line_id is not None and specimen_id is not None:
            line_specimens[line_id].add(specimen_id)
    for item in items:
        evidence.assess(item, line_specimens)
    events.append(event(
        "assess-record-consistency", "decision",
        "Compared all present identities, labels, cardinality and linked chronology; retained every administrative reason.",
        {"rows_with_reasons": sum(bool(item["row"]["reason_codes"]) for item in items),
         "conflicting_rows": sum("conflicting-evidence" in item["row"]["reason_codes"] for item in items),
         "chronology_rows": sum("impossible-chronology" in item["row"]["reason_codes"] for item in items)},
        table_snapshot(
            "Consistency assessment", ["line_id", "specimen_id", "primary_reason", "reason_count", "imported_state"],
            [[item["row"]["order_line_id"], item["row"]["specimen_id"],
              next(iter(item["row"]["reason_codes"]), None), len(item["row"]["reason_codes"]),
              item["row"]["imported_order_state"]] for item in items],
            [index for index, item in enumerate(items) if item["row"]["reason_codes"]],
        ),
    ))
    sla_seconds = policy["accession_sla_minutes"] * 60
    for item in items:
        row = item["row"]
        if row["reason_codes"]:
            continue
        if row["accession_ids"]:
            row["administrative_state"] = "reconciled"
        else:
            if row["imported_order_state"] != "active" or len(item["receipts"]) != 1:
                raise ValueError("Unclassified non-active or ambiguous administrative pair")
            difference = instant(as_of) - instant(item["receipts"][0].data["received_at"])
            row["age_seconds"] = difference.days * 86400 + difference.seconds
            if row["age_seconds"] > sla_seconds:
                row["reason_codes"] = ["accession-overdue"]
            else:
                row["administrative_state"] = "pending-within-window"
    rows = [item["row"] for item in items]
    summary = {
        "unique_received_specimens": len(evidence.receipts_by_specimen),
        "unique_order_lines": len(evidence.by_key["order_lines"]),
        "ledger_rows": len(rows),
        "reconciled": sum(row["administrative_state"] == "reconciled" for row in rows),
        "pending_within_window": sum(row["administrative_state"] == "pending-within-window" for row in rows),
        "review": sum(row["administrative_state"] == "review" for row in rows),
        "unmatched_records": len(unmatched), "excluded_records": len(excluded),
        "duplicate_rows_collapsed": duplicate_rows,
    }
    events.append(event(
        "age-and-reconcile-backlog", "decision",
        "Aged only clean active pairs without accessions; strict greater-than SLA flags backlog, not clinical urgency.",
        {"eligible_ages": sum(row["age_seconds"] is not None for row in rows),
         "sla_seconds": sla_seconds, "ledger_rows": len(rows), "reconciled": summary["reconciled"],
         "pending": summary["pending_within_window"], "review": summary["review"]},
        table_snapshot(
            "Administrative receipt window", ["line_id", "specimen_id", "age_seconds", "sla_seconds", "state"],
            [[row["order_line_id"], row["specimen_id"], row["age_seconds"], sla_seconds,
              row["administrative_state"]] for row in rows],
            [index for index, row in enumerate(rows) if "accession-overdue" in row["reason_codes"]],
        ),
    ))
    queue = build_queue(items, unmatched)
    exceptions = [
        {"code": item["reason_codes"][0], "message": REVIEW_MESSAGE,
         "entity_key": item["entity_key"], "reason_codes": list(item["reason_codes"])}
        for item in queue
    ]
    exceptions.extend(
        {"code": "duplicate-export", "message": DUPLICATE_MESSAGE,
         "entity_key": f"{record['table']}:{record['record_id']}", "reason_codes": ["duplicate-export"]}
        for record in duplicates
    )
    events.append(event(
        "route-accession-exceptions", "exception",
        "Prepared priority-ordered clarification drafts and copy warnings; notes remain references and nothing is sent.",
        {"drafts": len(queue), "duplicate_warnings": len(duplicates), "unmatched_groups": len(unmatched)},
        table_snapshot(
            "Unsent administrative clarification queue", ["entity_key", "primary_reason", "owner_role", "references"],
            [[item["entity_key"], item["reason_codes"][0], item["owner_role_id"],
              len(item["existing_clarification_refs"])] for item in queue],
            range(len(queue)),
        ),
    ))
    result = {
        "schema_version": 1,
        "status": "completed_with_exceptions" if exceptions else "completed",
        "outputs": {
            "as_of": as_of, "policy_id": policy["policy_id"], "sla_seconds": sla_seconds,
            "reconciliation_rows": rows, "unmatched_records": unmatched,
            "excluded_evidence": excluded, "duplicate_records": duplicates,
            "summary": summary, "draft_clarification_queue": queue,
            "clinical_disposition_performed": False, "qualified_review_required": True,
        },
        "exceptions": exceptions,
    }
    events.append(event(
        "write-accession-report", "output",
        "Returned the evidence-preserving report with separate specimen and line counts; no clinical disposition performed.",
        {"status": result["status"], "unique_received_specimens": summary["unique_received_specimens"],
         "unique_order_lines": summary["unique_order_lines"], "ledger_rows": len(rows),
         "review": summary["review"], "clinical_disposition_performed": False},
        table_snapshot(
            "Ledger partition", ["administrative_state", "rows"],
            [["reconciled", summary["reconciled"]], ["pending-within-window", summary["pending_within_window"]],
             ["review", summary["review"]]],
            [2] if summary["review"] else [],
        ),
        table_snapshot(
            "Evidence register counts", ["register", "groups"],
            [["unmatched", len(unmatched)], ["future exclusions", len(excluded)], ["duplicate groups", len(duplicates)]],
        ),
    ))
    return result, events


if __name__ == "__main__":
    run_cli(solve, scenario_id="hls-03")
