"""Deterministic mock receipt, performance, and unsent buyer-review baseline."""
from __future__ import annotations

import re
import sys
from collections import Counter, defaultdict
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP, localcontext
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "_shared"))
from scenario_support import run_cli


ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,39}\Z")
DATE_PATTERN = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}\Z")
MONTH_PATTERN = re.compile(r"[0-9]{4}-[0-9]{2}\Z")
MAX_DATE = "2100-12-31"
MAX_QUANTITY = 1_000_000
MAX_ROWS = 200

MESSAGES = {
    "CONFLICTING_ID": "Rows with the same primary ID disagree.",
    "INVALID_REVERSAL": "Reversal must uniquely void an existing same-line receipt in full on or after its posting date.",
    "CONFLICTING_CONFIRMATION": "Eligible confirmations recorded on the same date disagree.",
    "CANCELLED_LINE_DEMAND": "Unmet requirements on a cancelled line are contradictory.",
    "DEMAND_EXCEEDS_OPEN": "Total unmet requirement quantity exceeds reconciled open quantity.",
    "CONFIRMATION_EXCEEDS_OPEN": "Latest remaining confirmation quantity exceeds reconciled open quantity.",
    "DUPLICATE_COLLAPSED": "Identical rows with one primary ID were counted once.",
    "FUTURE_RECEIPT_EVENT": "Receipt event posted after as-of is excluded from receipt reconciliation.",
    "FUTURE_CONFIRMATION": "Confirmation recorded after as-of is excluded from promise selection.",
    "ORPHAN_RECEIPT": "Receipt references an unknown purchase line; excluded from receipt totals.",
    "ORPHAN_CONFIRMATION": "Confirmation references an unknown purchase line; excluded from promise selection.",
    "ORPHAN_REQUIREMENT": "Requirement references an unknown purchase line; coverage is unresolved.",
    "UNKNOWN_SUPPLIER": "Supplier master is missing; buyer ownership is unresolved.",
    "MISSING_REQUESTED_DATE": "Original requested receipt date is unknown; historical cohort is excluded.",
    "OVERRECEIPT": "Net receipt quantity exceeds ordered quantity; credited receipts are capped.",
    "PENDING_TOLERANCE": "Tolerance deadline is after as-of; the unsuccessful cohort result is provisional.",
    "EMPTY_COHORT": "No eligible purchase lines; performance percentage and low-performance flag are null.",
    "MISSING_CONFIRMATION": "No confirmation recorded by as-of for an in-scope open line.",
    "MISSING_ETA": "Latest confirmation has no receipt date for an in-scope open line.",
    "STALE_CONFIRMATION": "Past confirmed receipt date is not usable remaining supply.",
}
QUESTIONS = {
    "critical-shortage": "Review uncovered critical demand and request a feasible receipt-date plan.",
    "shortage": "Review uncovered demand and request receipt-date evidence.",
    "overdue-original": "Review the overdue original receipt date; any amendment needs buyer approval.",
    "missing-confirmation": "Obtain a dated confirmation of remaining quantity and receipt date.",
    "missing-eta": "Clarify the receipt date on the latest confirmation.",
    "stale-confirmation": "Reconcile the past confirmed receipt date with posted receipts before using supply.",
    "unknown-requested-date": "Resolve the missing original requested receipt date.",
}


def _identifier(value):
    if not isinstance(value, str) or not ID_PATTERN.fullmatch(value):
        return "Expected an ASCII identifier of 1-40 characters."
    return None


def _calendar_date(value):
    message = "Expected YYYY-MM-DD in the range 2000-01-01 through 2100-12-31."
    if not isinstance(value, str) or not DATE_PATTERN.fullmatch(value):
        return message
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return message
    return None if 2000 <= parsed.year <= 2100 else message


def _month(value):
    message = "Expected YYYY-MM in the range 2000-01 through 2100-12."
    if not isinstance(value, str) or not MONTH_PATTERN.fullmatch(value):
        return message
    return None if _calendar_date(value + "-01") is None else message


def _role(value):
    if (
        not isinstance(value, str) or not 1 <= len(value) <= 80
        or value != value.strip() or not all(32 <= ord(char) <= 126 for char in value)
    ):
        return "Expected a printable ASCII role of 1-80 characters without outer whitespace."
    return None


def _integer(lower, upper):
    def validate(value):
        if type(value) is not int or not lower <= value <= upper:
            return f"Expected an integer from {lower} through {upper}."
        return None
    return validate


def _nullable(validate):
    return lambda value: None if value is None else validate(value)


def _one_of(*values):
    def validate(value):
        if not isinstance(value, str) or value not in values:
            return "Expected one of: " + ", ".join(values) + "."
        return None
    return validate


CONFIG_FIELDS = {
    "as_of": _calendar_date,
    "reporting_month": _month,
    "horizon_days": _integer(0, 90),
    "tolerance_days": _integer(0, 30),
    "urgency_days": _integer(0, 90),
    "low_performance_percent": _integer(0, 100),
}
TABLES = {
    "po_schedule_lines": ("line_id", {
        "line_id": _identifier, "supplier_id": _identifier, "item_id": _identifier,
        "ordered_qty": _integer(1, MAX_QUANTITY),
        "original_requested_receipt": _nullable(_calendar_date),
        "state": _one_of("open", "cancelled"),
    }),
    "receipt_events": ("event_id", {
        "event_id": _identifier, "line_id": _identifier, "posted_on": _calendar_date,
        "qty": _integer(1, MAX_QUANTITY), "reversal_of": _nullable(_identifier),
    }),
    "confirmations": ("confirmation_id", {
        "confirmation_id": _identifier, "line_id": _identifier,
        "recorded_on": _calendar_date, "confirmed_receipt": _nullable(_calendar_date),
        "remaining_qty": _integer(0, MAX_QUANTITY),
    }),
    "requirements": ("requirement_id", {
        "requirement_id": _identifier, "line_id": _identifier, "need_by": _calendar_date,
        "unmet_qty": _integer(1, MAX_QUANTITY), "criticality": _one_of("critical", "normal"),
    }),
    "suppliers": ("supplier_id", {"supplier_id": _identifier, "buyer_role": _role}),
}


def _issue(code, table, record_id=None, field=None, *, message=None, **details):
    return {
        "code": code, "message": MESSAGES[code] if message is None else message,
        "table": table, "record_id": record_id, "field": field, **details,
    }


def _issue_order(item):
    return (
        item["code"], item["table"], item["record_id"] or "", item["field"] or "",
        item.get("related_id", ""), item.get("row_index", -1), item["message"],
    )


def _fields(value, validators, table, errors, record_id=None, **details):
    if not isinstance(value, dict):
        errors.append(_issue(
            "MALFORMED_INPUT", table, record_id, message="Expected an object.", **details,
        ))
        return
    for key in sorted(validators.keys() - value.keys()):
        errors.append(_issue(
            "MALFORMED_INPUT", table, record_id, key,
            message="Missing required field.", **details,
        ))
    for key in sorted(value.keys() - validators.keys()):
        errors.append(_issue(
            "MALFORMED_INPUT", table, record_id, key, message="Unknown field.", **details,
        ))
    for key in sorted(validators.keys() & value.keys()):
        message = validators[key](value[key])
        if message is not None:
            errors.append(_issue(
                "MALFORMED_INPUT", table, record_id, key, message=message, **details,
            ))


def _shift(value, days):
    return (date.fromisoformat(value) + timedelta(days=days)).isoformat()


def _validate_shape(payload):
    errors = []
    _fields(payload, {key: lambda value: None for key in ("config", *TABLES)}, "payload", errors)
    if not isinstance(payload, dict):
        return errors
    if "config" in payload:
        _fields(payload["config"], CONFIG_FIELDS, "config", errors)
    for name, (primary, fields) in TABLES.items():
        if name not in payload:
            continue
        rows = payload[name]
        if not isinstance(rows, list) or len(rows) > MAX_ROWS:
            errors.append(_issue(
                "MALFORMED_INPUT", name,
                message="Expected an array with at most 200 rows.",
            ))
            continue
        for index, row in enumerate(rows):
            raw_id = row.get(primary) if isinstance(row, dict) else None
            record_id = raw_id if _identifier(raw_id) is None else None
            details = {"row_index": index} if record_id is None else {}
            _fields(row, fields, name, errors, record_id, **details)
    config = payload.get("config")
    if not isinstance(config, dict):
        return errors
    valid = {key: key in config and check(config[key]) is None for key, check in CONFIG_FIELDS.items()}
    if valid["urgency_days"] and valid["horizon_days"] and config["urgency_days"] > config["horizon_days"]:
        errors.append(_issue(
            "MALFORMED_INPUT", "config", field="urgency_days",
            message="Urgency must not exceed horizon days.",
        ))
    for key in ("horizon_days", "urgency_days"):
        if valid["as_of"] and valid[key] and _shift(config["as_of"], config[key]) > MAX_DATE:
            errors.append(_issue(
                "MALFORMED_INPUT", "config", field=key, message="Derived date exceeds 2100-12-31.",
            ))
    lines = payload.get("po_schedule_lines")
    if valid["tolerance_days"] and isinstance(lines, list) and len(lines) <= MAX_ROWS:
        for index, row in enumerate(lines):
            if not isinstance(row, dict) or _calendar_date(row.get("original_requested_receipt")) is not None:
                continue
            if _shift(row["original_requested_receipt"], config["tolerance_days"]) > MAX_DATE:
                raw_id = row.get("line_id")
                record_id = raw_id if _identifier(raw_id) is None else None
                details = {"row_index": index} if record_id is None else {}
                errors.append(_issue(
                    "MALFORMED_INPUT", "po_schedule_lines", record_id, "original_requested_receipt",
                    message="Derived date exceeds 2100-12-31.", **details,
                ))
    return errors


def _group(rows, key):
    groups = defaultdict(list)
    for row in rows:
        groups[row[key]].append(row)
    return groups


def _deduplicate(payload):
    tables, warnings, errors = {}, [], []
    for name, (primary, _) in TABLES.items():
        groups = _group(payload[name], primary)
        tables[name] = []
        for record_id in sorted(groups):
            rows = groups[record_id]
            if any(row != rows[0] for row in rows[1:]):
                errors.append(_issue("CONFLICTING_ID", name, record_id, primary))
            else:
                tables[name].append(rows[0])
                if len(rows) > 1:
                    warnings.append(_issue(
                        "DUPLICATE_COLLAPSED", name, record_id, primary, count=len(rows) - 1,
                    ))
    return tables, warnings, errors


def _validate_relations(tables, as_of):
    errors = []
    receipts = {row["event_id"]: row for row in tables["receipt_events"]}
    reversals = [row for row in receipts.values() if row["reversal_of"] is not None]
    counts = Counter(row["reversal_of"] for row in reversals)
    for row in reversals:
        target_id = row["reversal_of"]
        target = receipts.get(target_id)
        if (
            target is None or target["reversal_of"] is not None
            or target["line_id"] != row["line_id"] or target["qty"] != row["qty"]
            or row["posted_on"] < target["posted_on"] or counts[target_id] != 1
        ):
            errors.append(_issue(
                "INVALID_REVERSAL", "receipt_events", row["event_id"], "reversal_of",
                related_id=target_id,
            ))
    groups = defaultdict(list)
    for row in tables["confirmations"]:
        if row["recorded_on"] <= as_of:
            groups[(row["line_id"], row["recorded_on"])].append(row)
    for (line_id, _), rows in sorted(groups.items()):
        if len({(row["confirmed_receipt"], row["remaining_qty"]) for row in rows}) > 1:
            errors.append(_issue(
                "CONFLICTING_CONFIRMATION", "confirmations",
                min(row["confirmation_id"] for row in rows), "recorded_on", related_id=line_id,
            ))
    lines = {row["line_id"]: row for row in tables["po_schedule_lines"]}
    for row in tables["requirements"]:
        if row["line_id"] in lines and lines[row["line_id"]]["state"] == "cancelled":
            errors.append(_issue(
                "CANCELLED_LINE_DEMAND", "requirements", row["requirement_id"], "line_id",
                related_id=row["line_id"],
            ))
    return errors


def _display(value):
    return value[:69] + "..." if isinstance(value, str) and len(value) > 72 else value


def _table(title, columns, rows, highlights=()):
    return {
        "title": f"{title} (first 8 of {len(rows)})" if len(rows) > 8 else title,
        "columns": columns, "rows": [[_display(cell) for cell in row] for row in rows[:8]],
        "total_rows": len(rows),
        "highlight_rows": [index for index in highlights if 0 <= index < min(8, len(rows))],
    }


def _event(events, step_id, kind, caption, facts, tables):
    events.append({
        "step_id": step_id, "kind": kind, "caption": caption,
        "facts": facts, "tables": tables,
    })


def _reject(events, errors, phase):
    errors = sorted(errors, key=_issue_order)
    _event(
        events, "validate-events", "validation",
        f"Rejected {phase} with {len(errors)} fatal issue(s); no business report was produced.",
        {"phase": phase, "fatal_errors": len(errors)},
        [_table(
            "Validation failures", ["code", "table", "record_id", "field"],
            [[item["code"], item["table"], item["record_id"], item["field"]] for item in errors],
            range(len(errors)),
        )],
    )
    return {"schema_version": 1, "status": "rejected", "outputs": {}, "exceptions": errors}, events


def _reconcile(lines, receipt_groups, config, warnings):
    result = []
    for line in lines:
        linked = receipt_groups.get(line["line_id"], [])
        posted = [row for row in linked if row["posted_on"] <= config["as_of"]]
        applied = [row for row in posted if row["reversal_of"] is not None]
        voided = {row["reversal_of"] for row in applied}
        active = [row for row in posted if row["reversal_of"] is None and row["event_id"] not in voided]
        original = line["original_requested_receipt"]
        deadline = _shift(original, config["tolerance_days"]) if original is not None else None
        net = sum(row["qty"] for row in active)
        credited = min(net, line["ordered_qty"])
        on_time = None if deadline is None else min(
            line["ordered_qty"], sum(row["qty"] for row in active if row["posted_on"] <= deadline),
        )
        result.append({
            **line, "deadline": deadline, "net_received_qty": net,
            "credited_received_qty": credited, "on_time_qty": on_time,
            "open_qty": line["ordered_qty"] - credited,
            "overreceipt_qty": max(0, net - line["ordered_qty"]),
            "receipt_event_ids": sorted(row["event_id"] for row in linked),
            "active_receipt_ids": sorted(row["event_id"] for row in active),
            "voided_receipt_ids": sorted(voided),
            "reversal_event_ids": sorted(row["event_id"] for row in applied),
            "future_event_ids": sorted(row["event_id"] for row in linked if row["posted_on"] > config["as_of"]),
        })
        if net > line["ordered_qty"]:
            warnings.append(_issue("OVERRECEIPT", "po_schedule_lines", line["line_id"], "ordered_qty"))
        if original is None:
            warnings.append(_issue(
                "MISSING_REQUESTED_DATE", "po_schedule_lines", line["line_id"], "original_requested_receipt",
            ))
    return result


def _cohort_status(row, config):
    original = row["original_requested_receipt"]
    if row["state"] == "cancelled":
        return "cancelled"
    if original is None:
        return "missing-requested-date"
    if original[:7] != config["reporting_month"]:
        return "outside-reporting-month"
    if original > config["as_of"]:
        return "future-requested-date"
    return "included"


def _performance(rows, threshold):
    included = [row for row in rows if row["cohort_status"] == "included"]
    numerator = sum(row["otif"] is True for row in included)
    denominator = len(included)
    percent = None
    if denominator:
        with localcontext() as context:
            context.prec = 28
            percent = format(
                (Decimal(100 * numerator) / Decimal(denominator)).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP,
                ), ".2f",
            )
    return {
        "numerator": numerator, "denominator": denominator, "percent": percent,
        "low_performance": 100 * numerator < threshold * denominator if denominator else None,
        "line_ids": sorted(row["line_id"] for row in included),
        "pending_line_ids": sorted(row["line_id"] for row in included if row["performance_pending"]),
    }


def _select_confirmations(lines, confirmation_groups, requirement_groups, config, horizon_end, warnings):
    reviews, errors = [], []
    for line in lines:
        line_id = line["line_id"]
        linked = confirmation_groups.get(line_id, [])
        eligible = [row for row in linked if row["recorded_on"] <= config["as_of"]]
        selected = None
        if eligible:
            latest_date = max(row["recorded_on"] for row in eligible)
            selected = min(
                (row for row in eligible if row["recorded_on"] == latest_date),
                key=lambda row: row["confirmation_id"],
            )
        active = line["state"] != "cancelled" and line["open_qty"] > 0
        if active and selected is not None and selected["remaining_qty"] > line["open_qty"]:
            errors.append(_issue(
                "CONFIRMATION_EXCEEDS_OPEN", "confirmations",
                selected["confirmation_id"], "remaining_qty", related_id=line_id,
            ))
        original = line["original_requested_receipt"]
        in_scope = active and (
            original is None or original <= horizon_end
            or any(row["need_by"] <= horizon_end for row in requirement_groups.get(line_id, []))
        )
        if line["state"] == "cancelled":
            state = "cancelled"
        elif line["open_qty"] == 0:
            state = "not-open"
        elif selected is None:
            state = "missing"
        elif selected["confirmed_receipt"] is None:
            state = "missing-eta"
        elif selected["confirmed_receipt"] < config["as_of"]:
            state = "stale"
        else:
            state = "current"
        selected_fields = {
            key: selected[key] if selected is not None else None
            for key in ("confirmation_id", "recorded_on", "confirmed_receipt", "remaining_qty")
        }
        reviews.append({
            "line_id": line_id, **selected_fields, "state": state, "in_scope": in_scope,
            "supply_qty": selected["remaining_qty"] if in_scope and state == "current" else 0,
            "future_confirmation_ids": sorted(
                row["confirmation_id"] for row in linked if row["recorded_on"] > config["as_of"]
            ),
            "superseded_confirmation_ids": sorted(
                row["confirmation_id"] for row in eligible
                if row["confirmation_id"] != selected_fields["confirmation_id"]
            ),
        })
        if in_scope and state == "missing":
            warnings.append(_issue("MISSING_CONFIRMATION", "po_schedule_lines", line_id))
        elif in_scope and state in {"missing-eta", "stale"}:
            warnings.append(_issue(
                "MISSING_ETA" if state == "missing-eta" else "STALE_CONFIRMATION",
                "confirmations", selected["confirmation_id"], "confirmed_receipt",
            ))
    return reviews, errors


def _allocate(requirements, confirmation_reviews, config, horizon_end):
    by_line = {row["line_id"]: row for row in confirmation_reviews}
    remaining = {row["line_id"]: row["supply_qty"] for row in confirmation_reviews}
    coverage = []
    for row in sorted(requirements, key=lambda item: (item["line_id"], item["need_by"], item["requirement_id"])):
        line_id = row["line_id"]
        promise = by_line.get(line_id)
        in_scope = row["need_by"] <= horizon_end
        assessment = "unresolved-line" if promise is None else "outside-horizon" if not in_scope else "allocated"
        covered, shortage = None, None
        if assessment == "allocated":
            eta = promise["confirmed_receipt"]
            covered = 0
            if eta is not None and config["as_of"] <= eta <= row["need_by"]:
                covered = min(row["unmet_qty"], remaining[line_id])
                remaining[line_id] -= covered
            shortage = row["unmet_qty"] - covered
        coverage.append({
            **row, "in_scope": in_scope, "assessment": assessment,
            "confirmation_id": promise["confirmation_id"] if promise is not None else None,
            "covered_qty": covered, "shortage_qty": shortage,
        })
    return coverage


def _rank_queue(lines, confirmation_reviews, coverage, supplier_performance, config, urgency_end):
    promises = {row["line_id"]: row for row in confirmation_reviews}
    demand = _group([row for row in coverage if row["assessment"] == "allocated"], "line_id")
    suppliers = {row["supplier_id"]: row for row in supplier_performance}
    queue = []
    for line in lines:
        promise = promises[line["line_id"]]
        if not promise["in_scope"]:
            continue
        work = demand.get(line["line_id"], [])
        shortage = sum(row["shortage_qty"] for row in work)
        urgent = any(
            row["criticality"] == "critical" and row["shortage_qty"] > 0 and row["need_by"] <= urgency_end
            for row in work
        )
        original = line["original_requested_receipt"]
        overdue = original is not None and original < config["as_of"]
        reasons = []
        if shortage:
            reasons.append("critical-shortage" if urgent else "shortage")
        if overdue:
            reasons.append("overdue-original")
        confirmation_reason = {
            "missing": "missing-confirmation", "missing-eta": "missing-eta", "stale": "stale-confirmation",
        }.get(promise["state"])
        if confirmation_reason is not None:
            reasons.append(confirmation_reason)
        if original is None:
            reasons.append("unknown-requested-date")
        if not reasons:
            continue
        supplier = suppliers[line["supplier_id"]]
        queue.append({
            "line_id": line["line_id"], "supplier_id": line["supplier_id"],
            "buyer_role": supplier["buyer_role"],
            "priority": "P1" if urgent else "P2" if shortage or overdue else "P3",
            "earliest_need_by": min(row["need_by"] for row in work) if work else None,
            "open_qty": line["open_qty"], "shortage_qty": shortage,
            "confirmed_receipt": promise["confirmed_receipt"],
            "low_performance": supplier["low_performance"], "reason_codes": reasons,
            "draft_questions": [QUESTIONS[reason] for reason in reasons],
            "send_status": "unsent", "approval_required": True,
        })
    queue.sort(key=lambda row: (
        row["priority"], row["earliest_need_by"] or "9999-12-31", -row["shortage_qty"], row["line_id"],
    ))
    for rank, row in enumerate(queue, 1):
        row["rank"] = rank
    return queue


def solve(payload):
    events = []
    supplied = payload if isinstance(payload, dict) else {}
    config_preview = supplied.get("config")
    config_preview = config_preview if isinstance(config_preview, dict) else {}
    _event(
        events, "intake", "input",
        "Inventoried the supplied logical exports and explicit policy from one synthetic JSON snapshot.",
        {
            "as_of": _display(config_preview.get("as_of")) if isinstance(config_preview.get("as_of"), str) else None,
            "reporting_month": _display(config_preview.get("reporting_month")) if isinstance(config_preview.get("reporting_month"), str) else None,
            "logical_tables_present": sum(name in supplied for name in TABLES),
        },
        [_table("Logical export inventory", ["table", "raw_rows", "shape"], [
            [name, len(supplied[name]) if isinstance(supplied.get(name), list) else None,
             "array" if isinstance(supplied.get(name), list) else "missing" if name not in supplied else "invalid"]
            for name in TABLES
        ])],
    )
    errors = _validate_shape(payload)
    if errors:
        return _reject(events, errors, "input shape")
    config = payload["config"]
    tables, warnings, errors = _deduplicate(payload)
    if errors:
        return _reject(events, errors, "source identity")
    errors = _validate_relations(tables, config["as_of"])
    if errors:
        return _reject(events, errors, "evidence relationships")
    horizon_end = _shift(config["as_of"], config["horizon_days"])
    urgency_end = _shift(config["as_of"], config["urgency_days"])
    _event(
        events, "validate-events", "validation",
        "Validated fields, bounded quantities, unique identities, full reversal relations, and eligible equal-date promises.",
        {
            "unique_rows": sum(len(rows) for rows in tables.values()),
            "duplicate_rows_removed": sum(row.get("count", 0) for row in warnings),
            "reversals_validated": sum(row["reversal_of"] is not None for row in tables["receipt_events"]),
            "eligible_confirmations": sum(row["recorded_on"] <= config["as_of"] for row in tables["confirmations"]),
        },
        [_table("Validated source inventory", ["table", "raw_rows", "unique_rows"], [
            [name, len(payload[name]), len(tables[name])] for name in TABLES
        ])],
    )
    lines = tables["po_schedule_lines"]
    line_ids = {row["line_id"] for row in lines}
    suppliers = {row["supplier_id"]: row for row in tables["suppliers"]}
    groups = {}
    for name, orphan_code in (
        ("receipt_events", "ORPHAN_RECEIPT"),
        ("confirmations", "ORPHAN_CONFIRMATION"),
        ("requirements", "ORPHAN_REQUIREMENT"),
    ):
        groups[name] = _group(tables[name], "line_id")
        primary = TABLES[name][0]
        for row in tables[name]:
            if row["line_id"] not in line_ids:
                warnings.append(_issue(
                    orphan_code, name, row[primary], "line_id", related_id=row["line_id"],
                ))
    for line in lines:
        if line["supplier_id"] not in suppliers:
            warnings.append(_issue(
                "UNKNOWN_SUPPLIER", "po_schedule_lines", line["line_id"], "supplier_id",
                related_id=line["supplier_id"],
            ))
    _event(
        events, "join-purchase-context", "join",
        "Joined source records by exact purchase line and supplier IDs; unmatched identities remain explicit review work.",
        {
            "purchase_lines": len(lines),
            "known_owner_lines": sum(row["supplier_id"] in suppliers for row in lines),
            "orphan_records": sum(item["code"].startswith("ORPHAN_") for item in warnings),
        },
        [_table("Purchase context", ["line_id", "supplier_id", "buyer", "receipts", "confirmations", "requirements"], [
            [line["line_id"], line["supplier_id"], suppliers.get(line["supplier_id"], {}).get("buyer_role"),
             len(groups["receipt_events"].get(line["line_id"], [])),
             len(groups["confirmations"].get(line["line_id"], [])),
             len(groups["requirements"].get(line["line_id"], []))]
            for line in lines
        ])],
    )
    for row in tables["receipt_events"]:
        if row["posted_on"] > config["as_of"]:
            warnings.append(_issue("FUTURE_RECEIPT_EVENT", "receipt_events", row["event_id"], "posted_on"))
    reconciled = _reconcile(lines, groups["receipt_events"], config, warnings)
    _event(
        events, "reconcile-receipts", "decision",
        "Folded as-of posted receipts and full voids; credited quantities are capped without concealing overreceipt.",
        {
            "net_received_qty": sum(row["net_received_qty"] for row in reconciled),
            "credited_received_qty": sum(row["credited_received_qty"] for row in reconciled),
            "voided_receipts": sum(len(row["voided_receipt_ids"]) for row in reconciled),
            "future_events": sum(row["posted_on"] > config["as_of"] for row in tables["receipt_events"]),
        },
        [_table("Receipt reconciliation", ["line_id", "ordered", "net", "on_time", "open", "overreceipt"], [
            [row["line_id"], row["ordered_qty"], row["net_received_qty"],
             row["on_time_qty"], row["open_qty"], row["overreceipt_qty"]] for row in reconciled
        ], [index for index, row in enumerate(reconciled) if row["voided_receipt_ids"] or row["overreceipt_qty"]])],
    )
    errors = [
        _issue("DEMAND_EXCEEDS_OPEN", "po_schedule_lines", row["line_id"], "ordered_qty")
        for row in reconciled if row["state"] != "cancelled"
        and sum(req["unmet_qty"] for req in groups["requirements"].get(row["line_id"], [])) > row["open_qty"]
    ]
    if errors:
        return _reject(events, errors, "unmet demand capacity")
    for row in reconciled:
        row["cohort_status"] = _cohort_status(row, config)
        row["otif"] = row["on_time_qty"] == row["ordered_qty"] if row["cohort_status"] == "included" else None
        row["performance_pending"] = row["otif"] is False and row["deadline"] > config["as_of"]
        if row["performance_pending"]:
            warnings.append(_issue(
                "PENDING_TOLERANCE", "po_schedule_lines", row["line_id"], "original_requested_receipt",
            ))
    overall = _performance(reconciled, config["low_performance_percent"])
    if overall["denominator"] == 0:
        warnings.append(_issue("EMPTY_COHORT", "po_schedule_lines", field="original_requested_receipt"))
    supplier_performance = [
        {
            "supplier_id": supplier_id, "buyer_role": suppliers.get(supplier_id, {}).get("buyer_role"),
            **_performance(
                [row for row in reconciled if row["supplier_id"] == supplier_id],
                config["low_performance_percent"],
            ),
        }
        for supplier_id in sorted(set(suppliers) | {row["supplier_id"] for row in lines})
    ]
    exclusions = [
        {"line_id": row["line_id"], "reason": row["cohort_status"]}
        for row in reconciled if row["cohort_status"] != "included"
    ]
    _event(
        events, "measure-performance", "decision",
        "Measured the fixed original-requested-date cohort; exact denominators, null history, and pending tolerance stay visible.",
        {
            "numerator": overall["numerator"], "denominator": overall["denominator"],
            "percent": overall["percent"], "excluded_lines": len(exclusions),
            "pending_lines": len(overall["pending_line_ids"]),
        },
        [
            _table("Overall and supplier performance", ["scope", "successful", "cohort", "percent", "pending"], [
                ["overall", overall["numerator"], overall["denominator"], overall["percent"], len(overall["pending_line_ids"])],
                *[[row["supplier_id"], row["numerator"], row["denominator"], row["percent"], len(row["pending_line_ids"])]
                  for row in supplier_performance],
            ]),
            _table("Cohort exclusions", ["line_id", "reason"], [[row["line_id"], row["reason"]] for row in exclusions]),
        ],
    )
    for row in tables["confirmations"]:
        if row["recorded_on"] > config["as_of"]:
            warnings.append(_issue("FUTURE_CONFIRMATION", "confirmations", row["confirmation_id"], "recorded_on"))
    reviews, errors = _select_confirmations(
        reconciled, groups["confirmations"], groups["requirements"], config, horizon_end, warnings,
    )
    if errors:
        return _reject(events, errors, "remaining confirmation capacity")
    _event(
        events, "select-confirmations", "join",
        "Selected latest as-of receipt-date promises; missing or stale ETAs supply no prospective coverage.",
        {
            "selected_records": sum(row["confirmation_id"] is not None for row in reviews),
            "in_scope_lines": sum(row["in_scope"] for row in reviews),
            "usable_prospective_qty": sum(row["supply_qty"] for row in reviews),
            "future_records": sum(row["recorded_on"] > config["as_of"] for row in tables["confirmations"]),
        },
        [_table("Selected promises", ["line_id", "confirmation_id", "receipt_date", "state", "in_scope", "supply_qty"], [
            [row["line_id"], row["confirmation_id"], row["confirmed_receipt"], row["state"], row["in_scope"], row["supply_qty"]]
            for row in reviews
        ], [index for index, row in enumerate(reviews) if row["in_scope"] and row["state"] != "current"])],
    )
    coverage = _allocate(tables["requirements"], reviews, config, horizon_end)
    assessed = [row for row in coverage if row["assessment"] == "allocated"]
    unresolved = [row for row in coverage if row["in_scope"] and row["assessment"] == "unresolved-line"]
    covered = sum(row["covered_qty"] for row in assessed)
    shortage = sum(row["shortage_qty"] for row in assessed)
    _event(
        events, "evaluate-demand", "decision",
        "Allocated each current promise pool once by need date and requirement ID; late supply cannot cover earlier demand.",
        {
            "assessed_requirements": len(assessed), "covered_qty": covered,
            "shortage_qty": shortage, "unresolved_in_scope": len(unresolved),
            "outside_horizon": sum(not row["in_scope"] for row in coverage),
        },
        [_table("Requirement coverage", ["line_id", "requirement_id", "need_by", "unmet", "covered", "shortage"], [
            [row["line_id"], row["requirement_id"], row["need_by"], row["unmet_qty"], row["covered_qty"], row["shortage_qty"]]
            for row in coverage
        ], [index for index, row in enumerate(coverage) if row["shortage_qty"] is None or row["shortage_qty"] > 0])],
    )
    warnings.sort(key=_issue_order)
    _event(
        events, "collect-exceptions", "exception",
        f"Collected {len(warnings)} evidence exception(s); unresolved identities and dates remain buyer-owned review work.",
        {
            "exceptions": len(warnings), "unresolved_in_scope": len(unresolved),
            "pending_lines": len(overall["pending_line_ids"]),
        },
        [_table("Evidence exceptions", ["code", "table", "record_id", "field"], [
            [row["code"], row["table"], row["record_id"], row["field"]] for row in warnings
        ], range(len(warnings)))],
    )
    queue = _rank_queue(reconciled, reviews, coverage, supplier_performance, config, urgency_end)
    _event(
        events, "rank-queue", "decision",
        "Ranked buyer questions by priority, earliest need, descending shortage, then line ID; every row is unsent.",
        {
            "queue_rows": len(queue), "p1_rows": sum(row["priority"] == "P1" for row in queue),
            "p2_rows": sum(row["priority"] == "P2" for row in queue),
            "p3_rows": sum(row["priority"] == "P3" for row in queue), "messages_sent": 0,
        },
        [_table("Unsent buyer queue", ["rank", "line_id", "priority", "need_by", "shortage", "buyer"], [
            [row["rank"], row["line_id"], row["priority"], row["earliest_need_by"], row["shortage_qty"], row["buyer_role"]]
            for row in queue
        ], [index for index, row in enumerate(queue) if row["priority"] == "P1"])],
    )
    closure = {
        "as_of": config["as_of"], "reporting_month": config["reporting_month"],
        "horizon_end": horizon_end, "urgency_end": urgency_end,
        "tolerance_days": config["tolerance_days"], "low_performance_percent": config["low_performance_percent"],
        "line_count": len(lines),
        "active_open_qty": sum(row["open_qty"] for row in reconciled if row["state"] != "cancelled"),
        "in_scope_unmet_qty": sum(row["unmet_qty"] for row in coverage if row["in_scope"]),
        "covered_qty": covered, "shortage_qty": shortage, "unresolved_requirement_count": len(unresolved),
        "unresolved_unmet_qty": sum(row["unmet_qty"] for row in unresolved),
        "queue_count": len(queue), "exception_count": len(warnings),
        "state": "review-prepared", "owner_role": "Buyer and material planner",
        "approval_required": True, "messages_sent": 0, "orders_changed": 0,
        "boundary": "Mock calendar-day review; no live purchasing or communication.",
    }
    outputs = {
        "receipt_reconciliation": reconciled, "overall_performance": overall,
        "supplier_performance": supplier_performance, "cohort_exclusions": exclusions,
        "confirmation_review": reviews, "requirement_coverage": coverage,
        "buyer_review_queue": queue, "review_closure": closure,
    }
    _event(
        events, "close-review", "output",
        "Closed the review-prepared report with reconciled quantities and buyer approval required; no purchasing or communication occurred.",
        {
            "unmet_qty": closure["in_scope_unmet_qty"], "covered_qty": covered,
            "shortage_qty": shortage, "unresolved_qty": closure["unresolved_unmet_qty"],
            "queue_rows": len(queue), "approval_required": True,
        },
        [_table("Review closure", ["artifact", "rows", "state"], [
            ["receipt_reconciliation", len(reconciled), "reconciled"],
            ["overall_performance", overall["denominator"], "explicit denominator"],
            ["cohort_exclusions", len(exclusions), "explained"],
            ["requirement_coverage", len(coverage), "assessed or explicitly unresolved"],
            ["buyer_review_queue", len(queue), "unsent; approval required"],
            ["exceptions", len(warnings), "buyer-owned"],
        ])],
    )
    return {
        "schema_version": 1,
        "status": "completed_with_exceptions" if warnings else "completed",
        "outputs": outputs, "exceptions": warnings,
    }, events


if __name__ == "__main__":
    run_cli(solve, scenario_id="manufacturing-02")
