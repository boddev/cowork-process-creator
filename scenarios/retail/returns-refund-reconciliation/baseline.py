"""Review-only original-transaction reconciliation of independent mock exports."""
from __future__ import annotations

import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "_shared"))
from scenario_support import run_cli


ROLES = ("policy", "original_orders", "original_lines", "prior_returns", "requests")
IDENTIFIER = re.compile(r"SYN-[A-Z0-9]+(?:-[A-Z0-9]+)*\Z")
TOKEN = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*\Z")
FILENAME = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*\.json\Z")
RESERVED = {"con", "prn", "aux", "nul"} | {
    f"{prefix}{number}" for prefix in ("com", "lpt") for number in range(1, 10)
}
SUPPLIED_KEYS = ("store_id", "receipt_id", "order_id", "invoice_id", "line_id", "sku")
PRIMARY_KEYS = {
    "original_orders": ("order_id",),
    "original_lines": ("order_id", "line_id"),
    "prior_returns": ("return_event_id",),
    "requests": ("request_id",),
}
SCHEMAS = {
    "policy": {
        "as_of": "date", "period_start": "date", "period_end": "date",
        "window_days": "nonnegative", "allow_partial_requests": "boolean",
        "allowed_reasons": "tokens", "allowed_conditions": "tokens",
    },
    "original_orders": {
        "order_id": "identifier", "store_id": "identifier", "receipt_id": "identifier",
        "invoice_id": "identifier", "purchased_on": "date",
        "currency": ("USD", "EUR", "GBP", "CAD", "AUD"),
        "payment_reference": "identifier", "payment_method": ("card", "gift-card", "mixed", "other"),
        "confirmed": "boolean", "authorized_minor": "nonnegative", "captured_minor": "nonnegative",
    },
    "original_lines": {
        "order_id": "identifier", "line_id": "identifier", "sku": "identifier",
        "fulfilled_qty": "positive", "merchandise_paid_minor": "nonnegative",
        "tax_paid_minor": "nonnegative", "returnable": "boolean",
    },
    "prior_returns": {
        "return_event_id": "identifier", "order_id": "identifier", "line_id": "identifier",
        "posted_on": "date", "state": ("posted", "voided", "pending"), "qty": "positive",
        "merchandise_minor": "nonnegative", "tax_minor": "nonnegative",
    },
    "requests": {
        "request_id": "identifier", "store_id": "identifier", "receipt_id": "identifier",
        "order_id": "identifier", "invoice_id": "identifier", "line_id": "identifier",
        "sku": "identifier", "requested_on": "date", "requested_qty": "positive",
        "reason": "token", "condition": "token",
    },
}
REQUEST_MESSAGES = {
    "unknown-receipt": "No original order matches the exact store/receipt; unresolved, not an accusation.",
    "order-quarantined": "The original order is quarantined; propose zero pending evidence review.",
    "request-outside-period": "Request date is outside the inclusive reporting period.",
    "purchase-after-request": "Request date precedes the original purchase date.",
    "return-window-exceeded": "Request age exceeds the configured inclusive return window.",
    "original-not-returnable": "The original line is not returnable under the sample policy.",
    "reason-not-allowed": "Return reason is not allowed by the sample policy.",
    "condition-not-allowed": "Item condition is not allowed by the sample policy.",
    "quantity-exhausted": "No original fulfilled quantity remains after prior returns and earlier proposals.",
    "partial-not-allowed": "Requested quantity exceeds remaining quantity and partial requests are disabled.",
    "partial-quantity": "Only the remaining quantity is proposed; defer the unfilled requested quantity.",
}
NEXT_ACTIONS = (
    "Verify source completeness and resolve every exception with the original transaction owner.",
    "Review proposals against current authorized return and payment policy; this packet grants no approval.",
    "Use an authorized operational process only after separate approval; no refund, order or stock change was executed.",
)


def _exception(code, message, scope, entity_id):
    return {"code": code, "message": message, "scope": scope, "entity_id": entity_id}


class InputProblem(ValueError):
    def __init__(self, code, message, entity_id):
        super().__init__(message)
        self.exception = _exception(code, message, "input", entity_id)


def _shape(value, fields, label, code, entity_id):
    if not isinstance(value, dict) or set(value) != set(fields):
        names = ", ".join(sorted(fields))
        raise InputProblem(code, f"{label} must be an object with exactly these keys: {names}.", entity_id)


def _valid_identifier(value):
    return isinstance(value, str) and len(value) <= 64 and IDENTIFIER.fullmatch(value) is not None


def _valid_token(value):
    return isinstance(value, str) and len(value) <= 48 and TOKEN.fullmatch(value) is not None


def _check_value(value, domain, field, code, entity_id):
    message = None
    if domain == "identifier":
        if not _valid_identifier(value):
            message = "must be a synthetic SYN- identifier of at most 64 characters."
    elif domain == "date":
        if not isinstance(value, str) or not re.fullmatch(r"2099-\d{2}-\d{2}", value):
            message = "must be a YYYY-MM-DD date in 2099."
        else:
            try:
                parsed = date.fromisoformat(value)
            except ValueError:
                message = "must be a YYYY-MM-DD date in 2099."
            else:
                if parsed.isoformat() != value:
                    message = "must be a YYYY-MM-DD date in 2099."
    elif domain in ("positive", "nonnegative"):
        minimum = 1 if domain == "positive" else 0
        if type(value) is not int or value < minimum:
            message = f"must be a {domain} integer; booleans and fractions are invalid."
    elif domain == "boolean":
        if type(value) is not bool:
            message = "must be a boolean."
    elif domain == "token":
        if not _valid_token(value):
            message = "must be a lowercase kebab-case string of at most 48 characters."
    elif domain == "tokens":
        if (
            not isinstance(value, list) or not value
            or not all(_valid_token(item) for item in value)
            or len(set(value)) != len(value)
        ):
            message = "must be a nonempty array of distinct lowercase kebab-case strings."
    elif isinstance(domain, tuple):
        if not isinstance(value, str) or value not in domain:
            message = f"must be one of: {', '.join(sorted(domain))}."
    else:
        raise AssertionError("Undeclared validation domain")
    if message is not None:
        raise InputProblem(code, f"{field} {message}", entity_id)


def _row_entity(row, role):
    keys = PRIMARY_KEYS[role]
    if isinstance(row, dict) and all(key in row and _valid_identifier(row[key]) for key in keys):
        return "/".join(row[key] for key in keys)
    return role


def _records(value, role):
    if not isinstance(value, list):
        raise InputProblem("invalid-record", f"{role} must be an array of records.", role)
    for row in value:
        entity_id = _row_entity(row, role)
        _shape(row, SCHEMAS[role], role, "invalid-record", entity_id)
        for field, domain in SCHEMAS[role].items():
            _check_value(row[field], domain, f"{role}.{field}", "invalid-record", entity_id)
    return sorted(value, key=lambda row: tuple(row[key] for key in PRIMARY_KEYS[role]))


def _unique(rows, fields, role, *, receipt=False, alternate=False):
    seen = set()
    for row in sorted(rows, key=lambda item: tuple(item[field] for field in fields)):
        key = tuple(row[field] for field in fields)
        if key in seen:
            entity_id = "/".join(key)
            if receipt:
                code = "ambiguous-receipt"
                message = f"original_orders contains multiple orders for store/receipt {entity_id}."
            elif alternate:
                code = "duplicate-key"
                message = f"original_orders repeats {fields[0]} {entity_id}."
            else:
                code = "duplicate-key"
                message = f"{role} repeats primary key {entity_id}."
            raise InputProblem(code, message, entity_id)
        seen.add(key)


def _validate(payload):
    _shape(payload, ("schema_version", "source_files", "files"), "bundle", "invalid-bundle", "bundle")
    if type(payload["schema_version"]) is not int or payload["schema_version"] != 1:
        raise InputProblem("invalid-bundle", "bundle.schema_version must be the integer 1.", "bundle")
    mapping = payload["source_files"]
    _shape(mapping, ROLES, "source_files", "invalid-bundle", "bundle")
    for role in ROLES:
        filename = mapping[role]
        if (
            not isinstance(filename, str) or len(filename) > 80
            or not FILENAME.fullmatch(filename) or filename[:-5] in RESERVED
        ):
            raise InputProblem(
                "invalid-bundle",
                f"source_files.{role} must be a safe lowercase kebab-case JSON filename.", "bundle",
            )
    if len(set(mapping.values())) != len(ROLES):
        raise InputProblem("invalid-bundle", "source_files must map every role to a distinct filename.", "bundle")
    files = payload["files"]
    if not isinstance(files, dict):
        _shape(files, mapping.values(), "files", "invalid-bundle", "bundle")
    if set(files) != set(mapping.values()):
        raise InputProblem("invalid-bundle", "files must contain exactly the mapped logical filenames.", "bundle")
    data = {role: files[mapping[role]] for role in ROLES}
    policy = data["policy"]
    _shape(policy, SCHEMAS["policy"], "policy", "invalid-policy", "policy")
    for field, domain in SCHEMAS["policy"].items():
        _check_value(policy[field], domain, f"policy.{field}", "invalid-policy", "policy")
    if not policy["period_start"] <= policy["period_end"] <= policy["as_of"]:
        raise InputProblem(
            "invalid-policy", "policy dates must satisfy period_start <= period_end <= as_of.", "policy",
        )
    data["original_orders"] = _records(data["original_orders"], "original_orders")
    data["original_lines"] = _records(data["original_lines"], "original_lines")
    history = data["prior_returns"]
    _shape(history, ("complete_before", "is_complete", "records"), "prior_returns", "invalid-record", "prior_returns")
    _check_value(history["complete_before"], "date", "prior_returns.complete_before", "invalid-record", "prior_returns")
    _check_value(history["is_complete"], "boolean", "prior_returns.is_complete", "invalid-record", "prior_returns")
    data["prior_returns"] = dict(history, records=_records(history["records"], "prior_returns"))
    data["requests"] = _records(data["requests"], "requests")
    for role, keys in PRIMARY_KEYS.items():
        rows = data["prior_returns"]["records"] if role == "prior_returns" else data[role]
        _unique(rows, keys, role)
    orders = data["original_orders"]
    _unique(orders, ("store_id", "receipt_id"), "original_orders", receipt=True)
    for field in ("invoice_id", "payment_reference"):
        _unique(orders, (field,), "original_orders", alternate=True)
    order_ids = {row["order_id"] for row in orders}
    for line in data["original_lines"]:
        if line["order_id"] not in order_ids:
            raise InputProblem(
                "unknown-original-order",
                f"original_lines references unknown order {line['order_id']}.",
                _row_entity(line, "original_lines"),
            )
    for event in data["prior_returns"]["records"]:
        if event["order_id"] not in order_ids:
            raise InputProblem(
                "unattributable-history",
                f"History event {event['return_event_id']} references an unknown original order; no safe quarantine boundary exists.",
                event["return_event_id"],
            )
    data["requests"] = sorted(data["requests"], key=lambda row: (row["requested_on"], row["request_id"]))
    return data


def _table(title, columns, rows, highlights=()):
    return {
        "title": f"{title} (first 8 of {len(rows)})" if len(rows) > 8 else title,
        "columns": columns, "rows": rows[:8], "total_rows": len(rows),
        "highlight_rows": [index for index in highlights if index < min(8, len(rows))],
    }


def _event(step_id, kind, caption, facts, *tables):
    return {"step_id": step_id, "kind": kind, "caption": caption, "facts": facts, "tables": list(tables)}


def _input_event(payload):
    counts = []
    policy = None
    for role in ROLES:
        value = None
        if isinstance(payload, dict):
            mapping, files = payload.get("source_files"), payload.get("files")
            if isinstance(mapping, dict) and isinstance(files, dict):
                name = mapping.get(role)
                if isinstance(name, str) and name in files:
                    value = files[name]
        if role == "policy":
            policy = value if isinstance(value, dict) else None
            count = 1 if policy is not None else None
        elif role == "prior_returns":
            rows = value.get("records") if isinstance(value, dict) else None
            count = len(rows) if isinstance(rows, list) else None
        else:
            count = len(value) if isinstance(value, list) else None
        counts.append([role, count])
    facts = {}
    if policy is not None:
        for field in ("as_of", "period_start", "period_end"):
            value = policy.get(field)
            facts[field] = value if isinstance(value, str) and len(value) == 10 else None
        for field, kind in (("window_days", int), ("allow_partial_requests", bool)):
            value = policy.get(field)
            facts[field] = value if type(value) is kind else None
    return _event(
        "load-return-exports", "input",
        "Inspect independently mapped mock exports; null counts mean missing or malformed data, never assumed zero history.",
        facts, _table("Supplied logical exports", ["role", "record_count"], counts),
    )


def _flag(issues, order_id, code, message):
    issues[order_id].add((code, message))


def _join(data, issues):
    orders = {row["order_id"]: row for row in data["original_orders"]}
    receipts = {(row["store_id"], row["receipt_id"]): row for row in orders.values()}
    invoices = {row["invoice_id"]: row["order_id"] for row in orders.values()}
    lines = {(row["order_id"], row["line_id"]): row for row in data["original_lines"]}
    joined = []
    for request in data["requests"]:
        order = receipts.get((request["store_id"], request["receipt_id"]))
        line = None if order is None else lines.get((order["order_id"], request["line_id"]))
        if order is None:
            status = "unknown-receipt"
        elif request["order_id"] != order["order_id"] or request["invoice_id"] != order["invoice_id"]:
            status = "conflicting-identifiers"
        elif line is None:
            status = "missing-line"
        elif request["sku"] != line["sku"]:
            status = "sku-mismatch"
        else:
            status = "matched"
        if status not in ("matched", "unknown-receipt"):
            implicated = {order["order_id"]}
            if request["order_id"] in orders:
                implicated.add(request["order_id"])
            if request["invoice_id"] in invoices:
                implicated.add(invoices[request["invoice_id"]])
            for order_id in sorted(implicated):
                _flag(
                    issues, order_id, "contradictory-request-evidence",
                    f"Request {request['request_id']} has contradictory original identifiers; quarantine the whole order.",
                )
        joined.append({"request": request, "order": order, "line": line, "join_status": status})
    return joined


def _entitlement(line, quantity):
    denominator = line["fulfilled_qty"]
    # Exact nonnegative half-up rationals avoid per-unit and binary-float rounding.
    return {
        "qty": quantity,
        "merchandise_minor": (2 * line["merchandise_paid_minor"] * quantity + denominator) // (2 * denominator),
        "tax_minor": (2 * line["tax_paid_minor"] * quantity + denominator) // (2 * denominator),
    }


def _reconcile(data, issues):
    orders = {row["order_id"]: row for row in data["original_orders"]}
    lines = {(row["order_id"], row["line_id"]): row for row in data["original_lines"]}
    by_order = {order_id: [] for order_id in orders}
    for key in lines:
        by_order[key[0]].append(key)
    raw_prior = {key: [0, 0, 0] for key in lines}
    observed_order = {order_id: 0 for order_id in orders}
    original_money = {order_id: [0, 0] for order_id in orders}
    policy, history = data["policy"], data["prior_returns"]
    for event in history["records"]:
        order_id, event_id = event["order_id"], event["return_event_id"]
        order = orders[order_id]
        key = (order_id, event["line_id"])
        for failed, code, message in (
            (event["state"] == "pending", "pending-history",
             f"History event {event_id} is pending; quarantine the whole order."),
            (event["posted_on"] >= policy["period_start"], "non-opening-history",
             f"History event {event_id} is not strictly before period_start; quarantine the whole order."),
            (event["posted_on"] < order["purchased_on"], "history-before-purchase",
             f"History event {event_id} predates the original purchase; quarantine the whole order."),
            (key not in lines, "unknown-history-line",
             f"History event {event_id} references an unknown original line; quarantine the whole order."),
        ):
            if failed:
                _flag(issues, order_id, code, message)
        if event["state"] == "posted":
            observed_order[order_id] += event["merchandise_minor"] + event["tax_minor"]
            if key in lines:
                raw_prior[key][0] += event["qty"]
                raw_prior[key][1] += event["merchandise_minor"]
                raw_prior[key][2] += event["tax_minor"]
    for order_id, order in orders.items():
        for key in by_order[order_id]:
            line = lines[key]
            original_money[order_id][0] += line["merchandise_paid_minor"]
            original_money[order_id][1] += line["tax_paid_minor"]
            quantity, merchandise, tax = raw_prior[key]
            if quantity > line["fulfilled_qty"]:
                _flag(
                    issues, order_id, "prior-quantity-exceeds-fulfilled",
                    f"Posted quantity exceeds fulfilled quantity on line {line['line_id']}; quarantine the whole order.",
                )
            else:
                entitlement = _entitlement(line, quantity)
                if merchandise != entitlement["merchandise_minor"] or tax != entitlement["tax_minor"]:
                    _flag(
                        issues, order_id, "prior-entitlement-mismatch",
                        f"Posted merchandise or tax disagrees with cumulative entitlement on line {line['line_id']}; quarantine the whole order.",
                    )
        for failed, code, message in (
            (not by_order[order_id], "missing-original-lines",
             "No original lines exist for this order; quarantine the whole order."),
            (order["payment_method"] != "card", "unsupported-payment-method",
             "Original payment method is not a single card; quarantine the whole order."),
            (not order["confirmed"], "payment-not-confirmed",
             "Original payment is not confirmed; quarantine the whole order."),
            (order["captured_minor"] > order["authorized_minor"], "capture-exceeds-authorization",
             "Captured amount exceeds original authorization; quarantine the whole order."),
            (sum(original_money[order_id]) != order["captured_minor"], "original-payment-mismatch",
             "Original line merchandise plus tax does not equal captured amount; quarantine the whole order."),
            (not history["is_complete"] or history["complete_before"] != policy["period_start"], "history-not-closed",
             "Opening history is not certified complete strictly before period_start; quarantine the whole order."),
        ):
            if failed:
                _flag(issues, order_id, code, message)
    return raw_prior, observed_order, original_money, by_order


def _policy_codes(request, line, age, policy):
    checks = (
        (not policy["period_start"] <= request["requested_on"] <= policy["period_end"], "request-outside-period"),
        (age < 0, "purchase-after-request"),
        (age > policy["window_days"], "return-window-exceeded"),
        (not line["returnable"], "original-not-returnable"),
        (request["reason"] not in policy["allowed_reasons"], "reason-not-allowed"),
        (request["condition"] not in policy["allowed_conditions"], "condition-not-allowed"),
    )
    return [code for failed, code in checks if failed]


def _allocate(joined, data, issues, raw_prior):
    reserved = {key: [0, 0, 0] for key in raw_prior}
    proposals, policy_rows, quantity_rows, money_rows = [], [], [], []
    policy = data["policy"]
    for link in joined:
        request, order, line = link["request"], link["order"], link["line"]
        original = None
        age = None
        if order is not None:
            original = {key: order[key] for key in ("order_id", "store_id", "receipt_id", "invoice_id", "currency", "payment_reference")}
            original.update(line_id=None if line is None else line["line_id"], sku=None if line is None else line["sku"])
            age = (date.fromisoformat(request["requested_on"]) - date.fromisoformat(order["purchased_on"])).days
        row = {
            "request_id": request["request_id"], "requested_on": request["requested_on"],
            "supplied_keys": {key: request[key] for key in SUPPLIED_KEYS},
            "reason": request["reason"], "condition": request["condition"], "requested_qty": request["requested_qty"],
            "join_status": link["join_status"], "original": original,
            "disposition": "unresolved", "reason_codes": [], "age_days": age,
            "prior_qty": None, "earlier_proposed_qty": None, "available_qty": None,
            "proposed_qty": 0, "deferred_qty": request["requested_qty"],
            "entitlement_before": None, "entitlement_after": None,
            "proposed_merchandise_minor": 0, "proposed_tax_minor": 0, "proposed_total_minor": 0,
        }
        if order is None:
            row["reason_codes"] = ["unknown-receipt"]
            policy_outcome = "unresolved"
        elif issues[order["order_id"]]:
            row["disposition"] = "quarantined"
            row["reason_codes"] = ["order-quarantined"]
            policy_outcome = "quarantined"
        else:
            if line is None or link["join_status"] != "matched":
                raise AssertionError("Unquarantined original join must be exact")
            key = (order["order_id"], line["line_id"])
            prior_qty = raw_prior[key][0]
            earlier = reserved[key][0]
            available = line["fulfilled_qty"] - prior_qty - earlier
            if available < 0:
                raise AssertionError("Validated quantity reservation cannot be negative")
            codes = _policy_codes(request, line, age, policy)
            policy_outcome = ", ".join(codes) if codes else "eligible"
            proposed = 0
            if codes:
                disposition = "ineligible"
            elif available == 0:
                disposition, codes = "deferred", ["quantity-exhausted"]
            elif request["requested_qty"] > available and not policy["allow_partial_requests"]:
                disposition, codes = "deferred", ["partial-not-allowed"]
            else:
                proposed = min(request["requested_qty"], available)
                disposition = "partial" if proposed < request["requested_qty"] else "proposed"
                codes = ["partial-quantity"] if disposition == "partial" else []
            before = _entitlement(line, prior_qty + earlier)
            after = _entitlement(line, prior_qty + earlier + proposed)
            merchandise = after["merchandise_minor"] - before["merchandise_minor"]
            tax = after["tax_minor"] - before["tax_minor"]
            row.update(
                disposition=disposition, reason_codes=codes, prior_qty=prior_qty,
                earlier_proposed_qty=earlier, available_qty=available,
                proposed_qty=proposed, deferred_qty=request["requested_qty"] - proposed,
                entitlement_before=before, entitlement_after=after,
                proposed_merchandise_minor=merchandise, proposed_tax_minor=tax,
                proposed_total_minor=merchandise + tax,
            )
            reserved[key][0] += proposed
            reserved[key][1] += merchandise
            reserved[key][2] += tax
        proposals.append(row)
        policy_rows.append([row["request_id"], age, policy["window_days"], request["reason"], request["condition"], policy_outcome])
        quantity_rows.append([
            row["request_id"], row["prior_qty"], row["earlier_proposed_qty"], row["available_qty"],
            row["proposed_qty"], row["deferred_qty"],
        ])
        before, after = row["entitlement_before"], row["entitlement_after"]
        money_rows.append([
            row["request_id"], None if before is None else before["merchandise_minor"],
            None if after is None else after["merchandise_minor"],
            None if before is None else before["tax_minor"], None if after is None else after["tax_minor"],
            row["proposed_total_minor"],
        ])
    return proposals, reserved, policy_rows, quantity_rows, money_rows


def _controls(data, issues, raw_prior, observed_order, original_money, by_order, reserved):
    orders = {row["order_id"]: row for row in data["original_orders"]}
    line_controls = []
    for line in data["original_lines"]:
        order_id, line_id = line["order_id"], line["line_id"]
        key = (order_id, line_id)
        quarantined = bool(issues[order_id])
        prior_qty, prior_merchandise, prior_tax = raw_prior[key]
        proposed_qty, proposed_merchandise, proposed_tax = reserved[key]
        line_controls.append({
            "order_id": order_id, "line_id": line_id, "sku": line["sku"], "currency": orders[order_id]["currency"],
            "quarantined": quarantined, "original_qty": line["fulfilled_qty"],
            "original_merchandise_minor": line["merchandise_paid_minor"], "original_tax_minor": line["tax_paid_minor"],
            "observed_posted_qty": prior_qty, "observed_posted_merchandise_minor": prior_merchandise,
            "observed_posted_tax_minor": prior_tax,
            "prior_qty": None if quarantined else prior_qty,
            "prior_merchandise_minor": None if quarantined else prior_merchandise,
            "prior_tax_minor": None if quarantined else prior_tax,
            "proposed_qty": proposed_qty, "proposed_merchandise_minor": proposed_merchandise,
            "proposed_tax_minor": proposed_tax,
            "remaining_qty": None if quarantined else line["fulfilled_qty"] - prior_qty - proposed_qty,
            "remaining_merchandise_minor": None if quarantined else line["merchandise_paid_minor"] - prior_merchandise - proposed_merchandise,
            "remaining_tax_minor": None if quarantined else line["tax_paid_minor"] - prior_tax - proposed_tax,
        })
    order_controls = []
    for order_id, order in orders.items():
        quarantined = bool(issues[order_id])
        merchandise, tax = original_money[order_id]
        proposed_merchandise = sum(reserved[key][1] for key in by_order[order_id])
        proposed_tax = sum(reserved[key][2] for key in by_order[order_id])
        proposed = proposed_merchandise + proposed_tax
        projected = observed_order[order_id] + proposed
        order_controls.append({
            "order_id": order_id, "currency": order["currency"], "payment_reference": order["payment_reference"],
            "payment_method": order["payment_method"], "confirmed": order["confirmed"], "quarantined": quarantined,
            "reason_codes": sorted({code for code, _ in issues[order_id]}),
            "authorized_minor": order["authorized_minor"], "captured_minor": order["captured_minor"],
            "original_merchandise_minor": merchandise, "original_tax_minor": tax, "original_total_minor": merchandise + tax,
            "observed_posted_minor": observed_order[order_id], "prior_minor": None if quarantined else observed_order[order_id],
            "proposed_merchandise_minor": proposed_merchandise, "proposed_tax_minor": proposed_tax, "proposed_minor": proposed,
            "prior_plus_proposed_minor": None if quarantined else projected,
            "remaining_minor": None if quarantined else order["captured_minor"] - projected,
            "cap_ok": None if quarantined else True,
        })
    currency_controls = []
    for currency in sorted({order["currency"] for order in order_controls}):
        all_orders = [order for order in order_controls if order["currency"] == currency]
        safe = [order for order in all_orders if not order["quarantined"]]
        row = {
            "currency": currency, "order_count": len(all_orders),
            "quarantined_order_count": len(all_orders) - len(safe), "reconciled_order_count": len(safe),
            "captured_minor": sum(order["captured_minor"] for order in all_orders),
            "reconciled_captured_minor": sum(order["captured_minor"] for order in safe),
        }
        for field in (
            "prior_minor", "proposed_merchandise_minor", "proposed_tax_minor",
            "proposed_minor", "prior_plus_proposed_minor", "remaining_minor",
        ):
            row[field] = sum(order[field] for order in safe)
        currency_controls.append(row)
    return line_controls, order_controls, currency_controls


def solve(payload):
    events = [_input_event(payload)]
    try:
        data = _validate(payload)
    except InputProblem as problem:
        item = problem.exception
        events.append(_event(
            "validate-return-records", "validation",
            "Structural validation rejected the bundle before any join, quantity reservation or money proposal.",
            {"validation": "rejected", "code": item["code"], "entity_id": item["entity_id"]},
            _table("First invalid evidence", ["scope", "entity_id", "code", "message"],
                   [[item["scope"], item["entity_id"], item["code"], item["message"]]], [0]),
        ))
        return {"schema_version": 1, "status": "rejected", "outputs": {}, "exceptions": [item]}, events

    history, policy = data["prior_returns"], data["policy"]
    record_counts = [
        ["original_orders", len(data["original_orders"]), "order_id"],
        ["original_lines", len(data["original_lines"]), "order_id/line_id"],
        ["prior_returns", len(history["records"]), "return_event_id"],
        ["requests", len(data["requests"]), "request_id"],
    ]
    events.append(_event(
        "validate-return-records", "validation",
        "Exact field sets, synthetic domains, primary keys, receipt uniqueness and order foreign keys passed; business contradictions are checked next.",
        {"schema_version": 1, "validation": "passed", "validated_rows": sum(row[1] for row in record_counts)},
        _table("Validated record domains and unique keys", ["role", "record_count", "primary_key"], record_counts),
    ))
    issues = {order["order_id"]: set() for order in data["original_orders"]}
    joined = _join(data, issues)
    join_rows = [
        [item["request"]["request_id"], item["request"]["receipt_id"],
         None if item["order"] is None else item["order"]["order_id"],
         None if item["line"] is None else item["line"]["line_id"], item["join_status"]]
        for item in joined
    ]
    events.append(_event(
        "link-original-evidence", "join",
        "Resolve store/receipt first, then verify order/invoice and line/SKU; contradictory matches quarantine all implicated originals before allocation.",
        {"matched": sum(item["join_status"] == "matched" for item in joined),
         "unknown_receipts": sum(item["join_status"] == "unknown-receipt" for item in joined),
         "contradictory_requests": sum(item["join_status"] not in ("matched", "unknown-receipt") for item in joined)},
        _table("Actual receipt and line joins", ["request_id", "supplied_receipt", "original_order", "original_line", "join_status"],
               join_rows, [index for index, row in enumerate(join_rows) if row[-1] != "matched"]),
    ))
    raw_prior, observed_order, original_money, by_order = _reconcile(data, issues)
    opening_rows = [
        [f"{line['order_id']}/{line['line_id']}", line["fulfilled_qty"],
         *raw_prior[(line["order_id"], line["line_id"])], bool(issues[line["order_id"]])]
        for line in data["original_lines"]
    ]
    opening_orders = [
        [order["order_id"], sum(original_money[order["order_id"]]), order["captured_minor"],
         order["authorized_minor"], observed_order[order["order_id"]], bool(issues[order["order_id"]])]
        for order in data["original_orders"]
    ]
    events.append(_event(
        "reconcile-opening-ledger", "decision",
        "Reconcile original capture and cumulative posted history. Raw observations remain visible; any order fault makes its authoritative eligibility unknown.",
        {"posted_events": sum(row["state"] == "posted" for row in history["records"]),
         "voided_events": sum(row["state"] == "voided" for row in history["records"]),
         "pending_events": sum(row["state"] == "pending" for row in history["records"]),
         "quarantined_orders": sum(bool(value) for value in issues.values()),
         "certified_opening": history["is_complete"] and history["complete_before"] == policy["period_start"]},
        _table("Observed original-line opening ledger",
               ["order/line", "fulfilled", "posted_qty", "posted_merch", "posted_tax", "quarantined"],
               opening_rows, [index for index, row in enumerate(opening_rows) if row[-1]]),
        _table("Original payment reconciliation",
               ["order_id", "line_paid", "captured", "authorized", "observed_posted", "quarantined"],
               opening_orders, [index for index, row in enumerate(opening_orders) if row[-1]]),
    ))
    proposals, reserved, policy_rows, quantity_rows, money_rows = _allocate(joined, data, issues, raw_prior)
    cap_withdrawals = 0
    for order in data["original_orders"]:
        order_id = order["order_id"]
        if not issues[order_id]:
            proposed = sum(reserved[key][1] + reserved[key][2] for key in by_order[order_id])
            projected = observed_order[order_id] + proposed
            if projected > order["captured_minor"] or projected > order["authorized_minor"]:
                cap_withdrawals += 1
                _flag(
                    issues, order_id, "refund-cap-exceeded",
                    "Prior plus proposed refunds exceed captured or authorized money; quarantine the whole order.",
                )
    if cap_withdrawals:
        proposals, reserved, policy_rows, quantity_rows, money_rows = _allocate(joined, data, issues, raw_prior)
    line_controls, order_controls, currency_controls = _controls(
        data, issues, raw_prior, observed_order, original_money, by_order, reserved,
    )
    events.append(_event(
        "apply-return-policy", "decision",
        "Evaluate inclusive period and age, original returnability, reason and condition before any quantity-dependent decision.",
        {"window_days": policy["window_days"], "ineligible_requests": sum(row["disposition"] == "ineligible" for row in proposals)},
        _table("Actual request policy checks", ["request_id", "age_days", "window", "reason", "condition", "policy_result"],
               policy_rows, [index for index, row in enumerate(policy_rows) if row[-1] != "eligible"]),
    ))
    events.append(_event(
        "reserve-proposed-quantities", "decision",
        "In requested-date/ID order, reserve only new proposed units. Oversized partial-disabled requests and policy exclusions consume nothing.",
        {"partial_requests_allowed": policy["allow_partial_requests"],
         "proposed_qty": sum(row["proposed_qty"] for row in proposals),
         "deferred_qty": sum(row["deferred_qty"] for row in proposals)},
        _table("Ordered hypothetical quantity reservations",
               ["request_id", "posted_prior", "earlier_proposed", "available", "proposed", "deferred"],
               quantity_rows, [index for index, row in enumerate(quantity_rows) if row[-1] > 0]),
    ))
    cap_rows = [
        [order["order_id"], order["prior_minor"], order["proposed_minor"], order["prior_plus_proposed_minor"],
         order["captured_minor"], order["cap_ok"]]
        for order in order_controls
    ]
    events.append(_event(
        "calculate-original-refund", "decision",
        "Subtract separate original merchandise/tax cumulative entitlements; check projected refunds against captured and authorized money before release.",
        {"rounding": "integer ROUND_HALF_UP", "cap_withdrawals": cap_withdrawals,
         "reconciled_orders": sum(not order["quarantined"] for order in order_controls)},
        _table("Actual cumulative pennies per request",
               ["request_id", "merch_before", "merch_after", "tax_before", "tax_after", "new_total"], money_rows),
        _table("Original order refund caps", ["order_id", "prior", "new", "projected", "captured", "cap_ok"],
               cap_rows, [index for index, row in enumerate(cap_rows) if row[-1] is None]),
    ))
    exceptions = [
        _exception(code, message, "order", order_id)
        for order_id in sorted(issues)
        for code, message in sorted(issues[order_id])
    ]
    exceptions.extend(
        _exception(code, REQUEST_MESSAGES[code], "request", row["request_id"])
        for row in proposals for code in row["reason_codes"]
    )
    events.append(_event(
        "quarantine-return-exceptions", "exception",
        "Surface order causes before ordered request exceptions; unknown receipts stay unresolved without accusations or invented payment attribution.",
        {"exceptions": len(exceptions), "quarantined_orders": sum(bool(value) for value in issues.values()),
         "unresolved_requests": sum(row["disposition"] == "unresolved" for row in proposals)},
        _table("Actual review exceptions", ["scope", "entity_id", "code"],
               [[row["scope"], row["entity_id"], row["code"]] for row in exceptions]),
    ))
    review = {
        "action_authorized": False, "owner_role": "Returns reconciliation analyst",
        **{key: policy[key] for key in ("as_of", "period_start", "period_end", "window_days", "allow_partial_requests")},
        "request_count": len(proposals), "proposed_qty": sum(row["proposed_qty"] for row in proposals),
        "deferred_qty": sum(row["deferred_qty"] for row in proposals), "exception_count": len(exceptions),
        "unresolved_request_ids": [row["request_id"] for row in proposals if row["disposition"] == "unresolved"],
        "quarantined_order_ids": [order_id for order_id in sorted(issues) if issues[order_id]],
        "review_request_ids": [row["request_id"] for row in proposals if row["disposition"] != "proposed"],
        "next_actions": list(NEXT_ACTIONS),
    }
    result = {
        "schema_version": 1, "status": "completed_with_exceptions" if exceptions else "completed",
        "outputs": {
            "request_proposals": proposals, "line_eligibility": line_controls,
            "order_money_controls": order_controls, "currency_controls": currency_controls, "review_packet": review,
        },
        "exceptions": exceptions,
    }
    events.append(_event(
        "publish-return-review", "output",
        "Publish every request and original control with a non-authorizing review packet. Currency money below excludes explicitly counted quarantined orders.",
        {"status": result["status"], "request_count": review["request_count"], "proposed_qty": review["proposed_qty"],
         "exception_count": len(exceptions), "quarantined_orders": len(review["quarantined_order_ids"]), "action_authorized": False},
        _table("Reconciled money by currency", ["currency", "prior", "new_merch", "new_tax", "new_total", "remaining"],
               [[row["currency"], row["prior_minor"], row["proposed_merchandise_minor"], row["proposed_tax_minor"],
                 row["proposed_minor"], row["remaining_minor"]] for row in currency_controls]),
        _table("Currency scope disclosure", ["currency", "orders", "quarantined", "reconciled", "all_captured", "reconciled_captured"],
               [[row["currency"], row["order_count"], row["quarantined_order_count"], row["reconciled_order_count"],
                 row["captured_minor"], row["reconciled_captured_minor"]] for row in currency_controls]),
    ))
    return result, events


if __name__ == "__main__":
    run_cli(solve, scenario_id="retail-02")
