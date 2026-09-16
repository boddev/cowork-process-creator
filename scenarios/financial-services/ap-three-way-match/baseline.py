"""Deterministic, synthetic AP review; no posting or real allocation mutation."""
from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "_shared"))
from scenario_support import run_cli


MONEY_MAX = 1_000_000_000_000
QUANTITY_MAX = 1_000_000_000
ID_PATTERN = re.compile(r"SYN-[A-Z0-9]+(?:-[A-Z0-9]+)*", re.ASCII)
UNIT_PATTERN = re.compile(r"[A-Z][A-Z0-9]{0,15}", re.ASCII)
TIME_PATTERN = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]{1,6})?(?:Z|[+-][0-9]{2}:[0-9]{2})",
    re.ASCII,
)
COMPONENTS = ("tax_minor", "charges_minor", "discounts_minor", "freight_minor")
SCOPE = ("legal_entity_id", "vendor_id", "currency")
PO_KEY = ("legal_entity_id", "po_id", "po_line_id")
SOURCE_ARRAYS = ("invoices", "po_lines", "receipt_lines", "historical_invoices", "prior_allocations")
PRICE_KEYS = (
    "po_line_net_minor", "unit_difference_minor", "unit_test_left",
    "unit_test_right", "unit_price_pass", "line_difference_minor", "line_cap_pass",
)
REVIEW = {"human_review": "pending", "live_action": "none", "owner_role": "AP manager"}

MESSAGES = {
    "invalid-object": "Expected an object with the documented fields.",
    "unknown-field": "Undocumented input field is not supported.",
    "missing-field": "Required input field is missing.",
    "invalid-version": "schema_version must be the integer 1.",
    "invalid-identifier": "Expected an uppercase ASCII SYN- identifier.",
    "invalid-invoice-number": "Expected a printable ASCII synthetic vendor invoice number.",
    "invalid-unit": "Expected a supported uppercase ASCII unit.",
    "invalid-enum": "Value is not a supported enum member.",
    "invalid-integer": "Expected a true integer within the documented bounds.",
    "invalid-array": "Expected an array with the documented minimum length.",
    "row-limit-exceeded": "Source row count exceeds max_rows_per_source.",
    "invalid-timestamp": "Expected a supported offset-bearing RFC 3339 timestamp.",
    "invalid-status-timestamp": "Timestamp must be null for pending status.",
    "duplicate-primary-key": "A primary key is repeated, including identical rows.",
    "policy-not-approved": "Synthetic controls must be approved before financial classification.",
    "header-net-inconsistent": "Header net does not equal the sum of declared line nets.",
    "line-net-inconsistent": "Declared line net does not equal the HALF_UP quantity-price calculation.",
    "receipt-po-inconsistent": "Receipt must reference an existing PO with matching vendor, currency and unit.",
    "receipt-time-inconsistent": "Receipt posting precedes physical receipt.",
    "allocation-reference-inconsistent": "Prior allocation must reference an existing posted historical invoice, posted receipt and exact matching PO scope.",
    "allocation-time-inconsistent": "Prior allocation recording precedes invoice or receipt posting.",
    "historical-receipt-overallocated": "Historical allocations exceed receipt quantity.",
    "historical-po-overallocated": "Historical allocations exceed ordered PO quantity.",
    "duplicate-incoming-invoice": "All incoming invoices with this canonical business key are held.",
    "duplicate-posted-invoice": "The canonical business key matches posted history available by as_of.",
    "invoice-after-as-of": "Invoice timestamp is after as_of.",
    "unsupported-components": "Nonzero tax, charges, discounts, or freight are outside this sample's scope.",
    "po-not-found": "No PO line has the invoice's exact legal-entity, PO, and PO-line key.",
    "po-scope-mismatch": "PO vendor, currency, and unit must exactly match the invoice line.",
    "po-approval-pending": "The PO line is not approved.",
    "po-approval-after-as-of": "PO approval occurred after as_of.",
    "po-quantity-shortage": "Requested line quantity exceeds historical-net PO capacity.",
    "zero-price-mismatch": "A zero-price PO requires zero invoice unit price and line net.",
    "unit-price-out-of-tolerance": "The symmetric unit-price difference exceeds the inclusive basis-point limit.",
    "line-amount-out-of-tolerance": "The line-net difference exceeds the inclusive minor-unit cap.",
    "receipt-selection-required": "Multiple eligible positive-capacity receipts require explicit selection.",
    "receipt-unavailable": "No eligible positive-capacity receipt is available by as_of.",
    "receipt-shortage": "Available receipt capacity is less than the requested quantity.",
    "selection-quantity-mismatch": "Explicit receipt quantities must sum exactly to the invoice line quantity.",
    "selected-receipt-missing": "A selected receipt ID is not present in the export.",
    "selected-receipt-scope-mismatch": "A selected receipt does not belong to the exact PO scope and unit.",
    "selected-receipt-unavailable": "A selected receipt is not posted by as_of.",
    "selected-receipt-shortage": "An explicit receipt selection exceeds that receipt's remaining capacity.",
    "invoice-receipt-capacity-exceeded": "This invoice's combined line demand exceeds a receipt's remaining capacity.",
    "invoice-po-capacity-exceeded": "This invoice's combined line demand exceeds a PO line's remaining capacity.",
    "receipt-capacity-conflict": "All otherwise eligible invoices competing for an oversubscribed receipt are held.",
    "po-capacity-conflict": "All otherwise eligible invoices competing for an oversubscribed PO line are held.",
    "receipt-posted-after-as-of": "Receipt posting is after as_of; its quantity is excluded.",
    "receipt-not-posted": "Receipt is not posted; its quantity is excluded.",
    "historical-invoice-posted-after-as-of": "Historical invoice posting is after as_of; its business key is excluded.",
    "historical-invoice-not-posted": "Historical invoice is not posted; its business key is excluded.",
    "allocation-recorded-after-as-of": "Prior allocation recording is after as_of; its quantity is excluded.",
}
AP_CODES = {
    "duplicate-incoming-invoice", "duplicate-posted-invoice",
    "invoice-after-as-of", "unsupported-components",
}
PROCUREMENT_CODES = {
    "po-not-found", "po-scope-mismatch", "po-approval-pending", "po-approval-after-as-of",
    "po-quantity-shortage", "zero-price-mismatch", "unit-price-out-of-tolerance",
    "line-amount-out-of-tolerance", "invoice-po-capacity-exceeded", "po-capacity-conflict",
}
RECEIVING_CODES = {
    "receipt-selection-required", "receipt-unavailable", "receipt-shortage",
    "selection-quantity-mismatch", "selected-receipt-missing", "selected-receipt-scope-mismatch",
    "selected-receipt-unavailable", "selected-receipt-shortage",
    "invoice-receipt-capacity-exceeded", "receipt-capacity-conflict",
    "receipt-posted-after-as-of", "receipt-not-posted",
}


def diagnostic(code, context, field=None):
    owner = "Source data owner"
    if code in AP_CODES:
        owner = "AP manager"
    elif code in PROCUREMENT_CODES:
        owner = "Procurement owner"
    elif code in RECEIVING_CODES:
        owner = "Receiving owner"
    source, record_id, line_id = context
    return {
        "code": code, "message": MESSAGES[code], "source": source,
        "record_id": record_id, "line_id": line_id, "field": field, "owner_role": owner,
    }


class InvalidEvidence(Exception):
    def __init__(self, code, context, field=None):
        self.diagnostic = diagnostic(code, context, field)
        super().__init__(self.diagnostic["message"])


def reject(code, context, field=None):
    raise InvalidEvidence(code, context, field)


def identity(row, field):
    value = row.get(field) if type(row) is dict else None
    return value if type(value) is str and len(value) <= 64 and ID_PATTERN.fullmatch(value) else None


def shape(value, required, optional, context):
    if type(value) is not dict or any(type(key) is not str for key in value):
        reject("invalid-object", context)
    unknown = set(value) - set(required) - set(optional)
    if unknown:
        reject("unknown-field", context, min(unknown))
    missing = set(required) - set(value)
    if missing:
        reject("missing-field", context, min(missing))


def integer(value, low, high, context, field):
    if type(value) is not int or not low <= value <= high:
        reject("invalid-integer", context, field)
    return value


def identifier(value, context, field):
    if type(value) is not str or len(value) > 64 or not ID_PATTERN.fullmatch(value):
        reject("invalid-identifier", context, field)


def enum(value, values, context, field):
    if type(value) is not str or value not in values:
        reject("invalid-enum", context, field)


def unit(value, context):
    if type(value) is not str or not UNIT_PATTERN.fullmatch(value):
        reject("invalid-unit", context, "unit")


def canonical(value, context):
    if type(value) is not str or len(value) > 128 or not value.isascii():
        reject("invalid-invoice-number", context, "vendor_invoice_number")
    value = value.strip(" \t\r\n\f\v").upper()
    if (
        not 5 <= len(value) <= 64 or not value.startswith("SYN-")
        or not "!" <= value[4] <= "~"
        or any(not " " <= char <= "~" for char in value)
    ):
        reject("invalid-invoice-number", context, "vendor_invoice_number")
    return value


def timestamp(value, context, field, zone=timezone.utc):
    if type(value) is not str or not TIME_PATTERN.fullmatch(value) or value.endswith("-00:00"):
        reject("invalid-timestamp", context, field)
    if not value.endswith("Z"):
        hours, minutes = int(value[-5:-3]), int(value[-2:])
        if minutes > 59 or hours > 14 or (hours == 14 and minutes != 0):
            reject("invalid-timestamp", context, field)
    try:
        instant = datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
        instant.astimezone(zone)
    except (ValueError, OverflowError):
        reject("invalid-timestamp", context, field)
    return instant


def status_time(row, state_field, time_field, active_state, context, zone):
    enum(row[state_field], (active_state, "pending"), context, state_field)
    if row[state_field] == "pending":
        if row[time_field] is not None:
            reject("invalid-status-timestamp", context, time_field)
        return None
    return timestamp(row[time_field], context, time_field, zone)


def array(value, minimum, limit, context, field):
    if type(value) is not list or len(value) < minimum:
        reject("invalid-array", context, field)
    if len(value) > limit:
        reject("row-limit-exceeded", context, field)


def ordered(rows, fields):
    def key(row):
        values = tuple(
            row.get(field) if type(row) is dict and type(row.get(field)) is str else ""
            for field in fields
        )
        return values, json.dumps(row, sort_keys=True, ensure_ascii=True)
    return sorted(rows, key=key)


def key_of(row, fields):
    return tuple(row[field] for field in fields)


def unique(row, fields, seen, context):
    key = key_of(row, fields)
    if key in seen:
        reject("duplicate-primary-key", context, "/".join(fields))
    seen.add(key)


def components(value, context):
    shape(value, (), COMPONENTS, context)
    return {field: integer(value.get(field, 0), 0, MONEY_MAX, context, field) for field in COMPONENTS}


def half_up(quantity, price):
    return (quantity * price + 500) // 1000


def raw_counts(payload):
    rows = payload if type(payload) is dict else {}
    counts = {name: len(rows[name]) if type(rows.get(name)) is list else 0 for name in SOURCE_ARRAYS}
    counts["invoice_lines"] = 0
    counts["selected_receipts"] = 0
    if type(rows.get("invoices")) is list:
        for invoice in rows["invoices"]:
            if type(invoice) is dict and type(invoice.get("lines")) is list:
                counts["invoice_lines"] += len(invoice["lines"])
                for line in invoice["lines"]:
                    if type(line) is dict and type(line.get("selected_receipts")) is list:
                        counts["selected_receipts"] += len(line["selected_receipts"])
    return counts


def validate(payload):
    root = ("payload", None, None)
    shape(payload, (*SOURCE_ARRAYS, "schema_version", "batch_id", "as_of",
                    "business_utc_offset_minutes", "controls"), (), root)
    if type(payload["schema_version"]) is not int or payload["schema_version"] != 1:
        reject("invalid-version", root, "schema_version")
    identifier(payload["batch_id"], root, "batch_id")
    timestamp(payload["as_of"], root, "as_of")
    offset = integer(payload["business_utc_offset_minutes"], -840, 840, root, "business_utc_offset_minutes")
    zone = timezone(timedelta(minutes=offset))
    cutoff = timestamp(payload["as_of"], root, "as_of", zone)
    control = payload["controls"]
    ctx = ("controls", identity(control, "control_version"), None)
    shape(control, ("control_version", "approval_state"),
          ("unit_tolerance_bps", "line_amount_cap_minor", "max_rows_per_source"), ctx)
    identifier(control["control_version"], ctx, "control_version")
    enum(control["approval_state"], ("approved", "pending"), ctx, "approval_state")
    settings = {
        "unit_tolerance_bps": integer(control.get("unit_tolerance_bps", 200), 0, 10000, ctx, "unit_tolerance_bps"),
        "line_amount_cap_minor": integer(control.get("line_amount_cap_minor", 500), 0, MONEY_MAX, ctx, "line_amount_cap_minor"),
        "max_rows_per_source": integer(control.get("max_rows_per_source", 5000), 1, 5000, ctx, "max_rows_per_source"),
    }
    if control["approval_state"] != "approved":
        reject("policy-not-approved", ctx, "approval_state")
    limit = settings["max_rows_per_source"]
    for name in SOURCE_ARRAYS:
        array(payload[name], 1 if name == "invoices" else 0, limit, root, name)

    invoices, seen_invoices, invoice_times, unsupported = [], set(), {}, set()
    counts = raw_counts(payload)
    for raw in ordered(payload["invoices"], (*SCOPE, "invoice_id")):
        ctx = ("invoices", identity(raw, "invoice_id"), None)
        shape(raw, ("invoice_id", *SCOPE, "vendor_invoice_number", "invoice_at",
                    "header_net_minor", "lines"), ("components",), ctx)
        for field in ("invoice_id", "legal_entity_id", "vendor_id"):
            identifier(raw[field], ctx, field)
        enum(raw["currency"], ("USD", "EUR"), ctx, "currency")
        canonical(raw["vendor_invoice_number"], ctx)
        invoice_times[raw["invoice_id"]] = timestamp(raw["invoice_at"], ctx, "invoice_at", zone)
        integer(raw["header_net_minor"], 0, MONEY_MAX, ctx, "header_net_minor")
        header_components = components(raw.get("components", {}), ctx)
        array(raw["lines"], 1, limit, ctx, "lines")
        unique(raw, ("invoice_id",), seen_invoices, ctx)
        invoice = {key: value for key, value in raw.items() if key not in ("lines", "components")}
        invoice.update(components=header_components, lines=[])
        seen_lines = set()
        for raw_line in ordered(raw["lines"], ("line_id",)):
            line_ctx = ("invoice-lines", raw["invoice_id"], identity(raw_line, "line_id"))
            shape(raw_line, ("line_id", "po_id", "po_line_id", "unit", "quantity_milliunits",
                             "unit_price_minor", "line_net_minor"), ("components", "selected_receipts"), line_ctx)
            for field in ("line_id", "po_id", "po_line_id"):
                identifier(raw_line[field], line_ctx, field)
            unit(raw_line["unit"], line_ctx)
            integer(raw_line["quantity_milliunits"], 1, QUANTITY_MAX, line_ctx, "quantity_milliunits")
            integer(raw_line["unit_price_minor"], 0, MONEY_MAX, line_ctx, "unit_price_minor")
            integer(raw_line["line_net_minor"], 0, MONEY_MAX, line_ctx, "line_net_minor")
            line = dict(raw_line, components=components(raw_line.get("components", {}), line_ctx))
            unique({"invoice_id": raw["invoice_id"], **raw_line}, ("invoice_id", "line_id"), seen_lines, line_ctx)
            if "selected_receipts" in line:
                array(line["selected_receipts"], 0, limit, line_ctx, "selected_receipts")
                selections, seen_selections = [], set()
                selection_ctx = ("selected-receipts", raw["invoice_id"], raw_line["line_id"])
                for selection in ordered(line["selected_receipts"], ("receipt_line_id",)):
                    shape(selection, ("receipt_line_id", "quantity_milliunits"), (), selection_ctx)
                    identifier(selection["receipt_line_id"], selection_ctx, "receipt_line_id")
                    integer(selection["quantity_milliunits"], 1, QUANTITY_MAX, selection_ctx, "quantity_milliunits")
                    unique({"invoice_id": raw["invoice_id"], "line_id": raw_line["line_id"], **selection},
                           ("invoice_id", "line_id", "receipt_line_id"), seen_selections, selection_ctx)
                    selections.append(dict(selection))
                line["selected_receipts"] = selections
            invoice["lines"].append(line)
        if sum(line["line_net_minor"] for line in invoice["lines"]) != invoice["header_net_minor"]:
            reject("header-net-inconsistent", ctx, "header_net_minor")
        has_components = any(header_components.values()) or any(
            any(line["components"].values()) for line in invoice["lines"]
        )
        if has_components:
            unsupported.add(invoice["invoice_id"])
        else:
            for line in invoice["lines"]:
                if half_up(line["quantity_milliunits"], line["unit_price_minor"]) != line["line_net_minor"]:
                    reject("line-net-inconsistent", ("invoice-lines", invoice["invoice_id"], line["line_id"]),
                           "line_net_minor")
        invoices.append(invoice)
    for name in ("invoice_lines", "selected_receipts"):
        if counts[name] > limit:
            reject("row-limit-exceeded", root, name)

    pos, seen, po_times = {}, set(), {}
    for row in ordered(payload["po_lines"], (*SCOPE, "po_id", "po_line_id")):
        ctx = ("po-lines", identity(row, "po_id"), identity(row, "po_line_id"))
        shape(row, (*PO_KEY, "vendor_id", "currency", "unit", "ordered_milliunits",
                    "unit_price_minor", "approval_state", "approved_at"), (), ctx)
        for field in (*PO_KEY, "vendor_id"):
            identifier(row[field], ctx, field)
        enum(row["currency"], ("USD", "EUR"), ctx, "currency")
        unit(row["unit"], ctx)
        integer(row["ordered_milliunits"], 1, QUANTITY_MAX, ctx, "ordered_milliunits")
        integer(row["unit_price_minor"], 0, MONEY_MAX, ctx, "unit_price_minor")
        time = status_time(row, "approval_state", "approved_at", "approved", ctx, zone)
        unique(row, PO_KEY, seen, ctx)
        po_key = key_of(row, PO_KEY)
        pos[po_key], po_times[po_key] = dict(row), time

    receipts, seen, receipt_times, received_times = {}, set(), {}, {}
    for row in ordered(payload["receipt_lines"], (*SCOPE, "receipt_line_id")):
        ctx = ("receipt-lines", identity(row, "receipt_line_id"), None)
        shape(row, ("receipt_line_id", *PO_KEY, "vendor_id", "currency", "unit",
                    "quantity_milliunits", "received_at", "status", "posted_at"), (), ctx)
        for field in ("receipt_line_id", *PO_KEY, "vendor_id"):
            identifier(row[field], ctx, field)
        enum(row["currency"], ("USD", "EUR"), ctx, "currency")
        unit(row["unit"], ctx)
        integer(row["quantity_milliunits"], 1, QUANTITY_MAX, ctx, "quantity_milliunits")
        received = timestamp(row["received_at"], ctx, "received_at", zone)
        posted = status_time(row, "status", "posted_at", "posted", ctx, zone)
        unique(row, ("receipt_line_id",), seen, ctx)
        rid = row["receipt_line_id"]
        receipts[rid], receipt_times[rid], received_times[rid] = dict(row), posted, received

    history, seen, history_times = {}, set(), {}
    for row in ordered(payload["historical_invoices"], (*SCOPE, "historical_invoice_id")):
        ctx = ("historical-invoices", identity(row, "historical_invoice_id"), None)
        shape(row, ("historical_invoice_id", *SCOPE, "vendor_invoice_number", "status", "posted_at"), (), ctx)
        for field in ("historical_invoice_id", "legal_entity_id", "vendor_id"):
            identifier(row[field], ctx, field)
        enum(row["currency"], ("USD", "EUR"), ctx, "currency")
        canonical(row["vendor_invoice_number"], ctx)
        posted = status_time(row, "status", "posted_at", "posted", ctx, zone)
        unique(row, ("historical_invoice_id",), seen, ctx)
        hid = row["historical_invoice_id"]
        history[hid], history_times[hid] = dict(row), posted

    allocations, seen, allocation_times = [], set(), {}
    for row in ordered(payload["prior_allocations"], ("legal_entity_id", "allocation_id")):
        ctx = ("prior-allocations", identity(row, "allocation_id"), None)
        shape(row, ("allocation_id", "historical_invoice_id", *PO_KEY, "receipt_line_id",
                    "quantity_milliunits", "recorded_at"), (), ctx)
        for field in ("allocation_id", "historical_invoice_id", *PO_KEY, "receipt_line_id"):
            identifier(row[field], ctx, field)
        integer(row["quantity_milliunits"], 1, QUANTITY_MAX, ctx, "quantity_milliunits")
        recorded = timestamp(row["recorded_at"], ctx, "recorded_at", zone)
        unique(row, ("allocation_id",), seen, ctx)
        allocations.append(dict(row))
        allocation_times[row["allocation_id"]] = recorded

    for rid, row in receipts.items():
        ctx = ("receipt-lines", rid, None)
        po = pos.get(key_of(row, PO_KEY))
        if po is None or any(row[field] != po[field] for field in ("vendor_id", "currency", "unit")):
            reject("receipt-po-inconsistent", ctx, "po_id")
        if receipt_times[rid] is not None and receipt_times[rid] < received_times[rid]:
            reject("receipt-time-inconsistent", ctx, "posted_at")

    total_receipt, total_po = defaultdict(int), defaultdict(int)
    prior_receipt, prior_po = defaultdict(int), defaultdict(int)
    for row in allocations:
        aid, rid, hid = row["allocation_id"], row["receipt_line_id"], row["historical_invoice_id"]
        po_key = key_of(row, PO_KEY)
        po, receipt, historical = pos.get(po_key), receipts.get(rid), history.get(hid)
        ctx = ("prior-allocations", aid, None)
        if (
            po is None or receipt is None or historical is None
            or receipt["status"] != "posted" or historical["status"] != "posted"
            or key_of(receipt, PO_KEY) != po_key or key_of(historical, SCOPE) != key_of(po, SCOPE)
        ):
            reject("allocation-reference-inconsistent", ctx, "historical_invoice_id")
        if allocation_times[aid] < history_times[hid] or allocation_times[aid] < receipt_times[rid]:
            reject("allocation-time-inconsistent", ctx, "recorded_at")
        quantity = row["quantity_milliunits"]
        total_receipt[rid] += quantity
        total_po[po_key] += quantity
        if allocation_times[aid] <= cutoff:
            prior_receipt[rid] += quantity
            prior_po[po_key] += quantity
    for rid, row in receipts.items():
        if total_receipt[rid] > row["quantity_milliunits"]:
            reject("historical-receipt-overallocated", ("receipt-lines", rid, None), "quantity_milliunits")
    for po_key, row in pos.items():
        if total_po[po_key] > row["ordered_milliunits"]:
            reject("historical-po-overallocated", ("po-lines", row["po_id"], row["po_line_id"]), "ordered_milliunits")
    allocations.sort(key=lambda row: (*key_of(pos[key_of(row, PO_KEY)], SCOPE), row["allocation_id"]))
    return {
        "invoices": invoices, "pos": pos, "receipts": receipts, "history": history, "allocations": allocations,
        "cutoff": cutoff, "zone": zone, "settings": settings, "counts": counts,
        "invoice_times": invoice_times, "po_times": po_times, "receipt_times": receipt_times,
        "history_times": history_times, "allocation_times": allocation_times,
        "prior_receipt": prior_receipt, "prior_po": prior_po, "unsupported": unsupported,
    }


def table(title, columns, rows, highlights=()):
    return {
        "title": title if len(rows) <= 8 else f"{title} (first 8 of {len(rows)})",
        "columns": columns, "rows": rows[:8], "total_rows": len(rows),
        "highlight_rows": [index for index in highlights if index < min(len(rows), 8)],
    }


def event(step, kind, caption, facts, *tables):
    return {"step_id": step, "kind": kind, "caption": caption, "facts": facts, "tables": list(tables)}


def solve(payload):
    counts = raw_counts(payload)
    intake = payload if type(payload) is dict else {}
    batch = identity(intake, "batch_id")
    as_of = intake.get("as_of")
    displayed_as_of = as_of if type(as_of) is str and len(as_of) <= 40 else None
    events = [event(
        "intake-documents", "input", "Read the supplied synthetic invoice, PO, receipt and history exports; no live systems are connected.",
        {"synthetic": True, "batch_id": batch, "as_of": displayed_as_of, "source_sets": len(counts)},
        table("Supplied source rows", ["source", "rows"], [[name, counts[name]] for name in sorted(counts)]),
    )]
    try:
        data = validate(payload)
    except InvalidEvidence as error:
        item = error.diagnostic
        events.append(event(
            "validate-documents", "validation", "Input evidence failed validation; no financial classification or partial totals were produced.",
            {"valid": False, "diagnostics": 1},
            table("Validation diagnostic", ["source", "record", "line", "field", "code"],
                  [[item["source"], item["record_id"], item["line_id"], item["field"], item["code"]]], [0]),
        ))
        result = {"schema_version": 1, "status": "rejected", "outputs": {"review": dict(REVIEW)}, "exceptions": [item]}
        events.append(event(
            "emit-ap-review", "output", "Emitted a rejected, review-only packet with the observed diagnostic and no trusted financial outputs.",
            {"status": "rejected", "human_review": "pending", "live_action": "none"},
            table("Rejected packet", ["code", "owner"], [[item["code"], item["owner_role"]]], [0]),
        ))
        return result, events

    invoices, pos, receipts = data["invoices"], data["pos"], data["receipts"]
    cutoff, zone = data["cutoff"], data["zone"]
    settings = data["settings"]
    diagnostics = {}

    def note(code, source, record_id, scope, line_id=None):
        key = (*scope, record_id, line_id or "", code, source, "")
        diagnostics[key] = diagnostic(code, (source, record_id, line_id))

    receipt_rows, po_rows, excluded = {}, {}, []
    for rid, receipt in receipts.items():
        posted = data["receipt_times"][rid]
        available = posted is not None and posted <= cutoff
        prior = data["prior_receipt"][rid]
        before = receipt["quantity_milliunits"] - prior if available else 0
        row = dict(
            receipt, posted_business_date=posted.astimezone(zone).date().isoformat() if posted else None,
            available_at_as_of=available, historical_used_milliunits=prior,
            before_proposals_milliunits=before, proposed_milliunits=0, remaining_milliunits=before,
        )
        receipt_rows[rid] = row
        if not available:
            code = "receipt-not-posted" if posted is None else "receipt-posted-after-as-of"
            excluded.append({
                "receipt_line_id": rid, "code": code, "message": MESSAGES[code],
                "quantity_milliunits": receipt["quantity_milliunits"], "posted_at": receipt["posted_at"],
                "posted_business_date": row["posted_business_date"],
            })
            note(code, "receipt-lines", rid, key_of(receipt, SCOPE))
    for po_key, po in pos.items():
        prior = data["prior_po"][po_key]
        approved = data["po_times"][po_key]
        before = po["ordered_milliunits"] - prior
        po_rows[po_key] = dict(
            po, available_for_proposals=approved is not None and approved <= cutoff,
            historical_used_milliunits=prior, before_proposals_milliunits=before,
            proposed_milliunits=0, remaining_milliunits=before,
        )

    history_rows, allocation_rows, history_keys = [], [], defaultdict(list)
    for hid, historical in data["history"].items():
        posted = data["history_times"][hid]
        included = posted is not None and posted <= cutoff
        code = None if included else (
            "historical-invoice-not-posted" if posted is None else "historical-invoice-posted-after-as-of"
        )
        number = canonical(historical["vendor_invoice_number"], ("historical-invoices", hid, None))
        history_rows.append(dict(historical, canonical_vendor_invoice_number=number, included=included, exclusion_code=code))
        if included:
            history_keys[(historical["legal_entity_id"], historical["vendor_id"], number)].append(hid)
        else:
            note(code, "historical-invoices", hid, key_of(historical, SCOPE))
    for row in data["allocations"]:
        included = data["allocation_times"][row["allocation_id"]] <= cutoff
        code = None if included else "allocation-recorded-after-as-of"
        allocation_rows.append(dict(row, included=included, exclusion_code=code))
        if not included:
            note(code, "prior-allocations", row["allocation_id"], key_of(pos[key_of(row, PO_KEY)], SCOPE))

    events.append(event(
        "validate-documents", "validation", "Validated strict fields, exact header/line arithmetic and authoritative historical receipt/PO capacity without clamping.",
        {"valid": True, "included_prior_allocations": sum(row["included"] for row in allocation_rows)},
        table("Validated invoice net checks", ["invoice", "header_net", "declared_line_sum", "formula_checked"], [
            [row["invoice_id"], row["header_net_minor"], sum(line["line_net_minor"] for line in row["lines"]),
             row["invoice_id"] not in data["unsupported"]] for row in invoices
        ]),
        table("Historical receipt worksheet", ["receipt", "quantity", "included_prior", "as_of_available"], [
            [rid, row["quantity_milliunits"], row["historical_used_milliunits"], row["before_proposals_milliunits"]]
            for rid, row in receipt_rows.items()
        ]),
    ))

    current_keys = defaultdict(list)
    for invoice in invoices:
        number = canonical(invoice["vendor_invoice_number"], ("invoices", invoice["invoice_id"], None))
        current_keys[(invoice["legal_entity_id"], invoice["vendor_id"], number)].append(invoice["invoice_id"])
    reviews, lines, line_inputs, invoice_lines, header_holds = {}, [], {}, defaultdict(list), defaultdict(set)

    def header_hold(iid, code):
        header_holds[iid].add(code)
        note(code, "invoices", iid, key_of(reviews[iid], SCOPE))

    def line_hold(row, code):
        row["individual_reason_codes"].add(code)
        note(code, "invoice-lines", row["invoice_id"], key_of(row, SCOPE), row["line_id"])

    for invoice in invoices:
        iid = invoice["invoice_id"]
        number = canonical(invoice["vendor_invoice_number"], ("invoices", iid, None))
        business_key = (invoice["legal_entity_id"], invoice["vendor_id"], number)
        duplicate_current = sorted(other for other in current_keys[business_key] if other != iid)
        duplicate_history = sorted(history_keys[business_key])
        reviews[iid] = {
            key: invoice[key] for key in (
                "invoice_id", *SCOPE, "vendor_invoice_number", "invoice_at", "header_net_minor", "components"
            )
        }
        reviews[iid].update(
            canonical_vendor_invoice_number=number,
            declared_line_net_minor=sum(line["line_net_minor"] for line in invoice["lines"]),
            line_ids=[line["line_id"] for line in invoice["lines"]],
            duplicate_invoice_ids=duplicate_current, duplicate_historical_invoice_ids=duplicate_history,
        )
        if duplicate_current:
            header_hold(iid, "duplicate-incoming-invoice")
        if duplicate_history:
            header_hold(iid, "duplicate-posted-invoice")
        if data["invoice_times"][iid] > cutoff:
            header_hold(iid, "invoice-after-as-of")
        if iid in data["unsupported"]:
            header_hold(iid, "unsupported-components")
        for source_line in invoice["lines"]:
            row = {
                "invoice_id": iid, **{key: invoice[key] for key in SCOPE},
                **{key: source_line[key] for key in (
                    "line_id", "po_id", "po_line_id", "unit", "quantity_milliunits",
                    "unit_price_minor", "line_net_minor", "components"
                )},
                "calculated_line_net_minor": None if iid in data["unsupported"] else half_up(
                    source_line["quantity_milliunits"], source_line["unit_price_minor"]
                ),
                "po": None, "price": dict.fromkeys(PRICE_KEYS),
                "receipts": {"eligible_ids": [], "available_milliunits": None, "selection_mode": "none",
                             "selections": [], "total_selected_milliunits": 0, "shortage_milliunits": None},
                "individual_reason_codes": set(), "conflict_reason_codes": set(),
            }
            po_key = key_of(row, PO_KEY)
            po = po_rows.get(po_key)
            if po is None:
                line_hold(row, "po-not-found")
            else:
                matches = all(row[field] == po[field] for field in ("vendor_id", "currency", "unit"))
                row["po"] = {
                    key: po[key] for key in (
                        "vendor_id", "currency", "unit", "ordered_milliunits", "unit_price_minor",
                        "approval_state", "approved_at"
                    )
                }
                row["po"].update(
                    available_milliunits=po["before_proposals_milliunits"],
                    shortage_milliunits=max(0, row["quantity_milliunits"] - po["before_proposals_milliunits"]),
                    join_matches=matches,
                )
                if not matches:
                    line_hold(row, "po-scope-mismatch")
                elif po["approval_state"] == "pending":
                    line_hold(row, "po-approval-pending")
                elif not po["available_for_proposals"]:
                    line_hold(row, "po-approval-after-as-of")
            lines.append(row)
            line_inputs[(iid, row["line_id"])] = source_line
            invoice_lines[iid].append(row)

    events.append(event(
        "join-duplicates-and-pos", "join", "Compared every canonical invoice key with the complete batch and available posted history, then joined exact PO evidence.",
        {"incoming_duplicate_invoices": sum(bool(row["duplicate_invoice_ids"]) for row in reviews.values()),
         "historical_duplicate_invoices": sum(bool(row["duplicate_historical_invoice_ids"]) for row in reviews.values())},
        table("Exact PO joins", ["invoice", "line", "po", "join_matches", "approval"], [
            [row["invoice_id"], row["line_id"], row["po_id"], row["po"]["join_matches"] if row["po"] else False,
             row["po"]["approval_state"] if row["po"] else None] for row in lines
        ]),
        table("Canonical document-key ledger", ["invoice", "canonical_number", "incoming_matches", "history_matches"], [
            [row["invoice_id"], row["canonical_vendor_invoice_number"], len(row["duplicate_invoice_ids"]),
             len(row["duplicate_historical_invoice_ids"])] for row in reviews.values()
        ]),
    ))

    candidates_by_po = defaultdict(list)
    for rid, row in receipt_rows.items():
        if row["available_at_as_of"] and row["before_proposals_milliunits"] > 0:
            candidates_by_po[key_of(row, PO_KEY)].append(rid)
    for row in lines:
        source = line_inputs[(row["invoice_id"], row["line_id"])]
        po_key = key_of(row, PO_KEY)
        usable = row["po"] is not None and row["po"]["join_matches"]
        comparison = row["receipts"]
        ids = sorted(candidates_by_po[po_key]) if usable else []
        if usable:
            available = sum(receipt_rows[rid]["before_proposals_milliunits"] for rid in ids)
            comparison.update(eligible_ids=ids, available_milliunits=available,
                              shortage_milliunits=max(0, row["quantity_milliunits"] - available))
            if row["po"]["shortage_milliunits"]:
                line_hold(row, "po-quantity-shortage")
        selections = []
        if "selected_receipts" in source:
            comparison["selection_mode"] = "explicit"
            selections = source["selected_receipts"]
            if sum(item["quantity_milliunits"] for item in selections) != row["quantity_milliunits"]:
                line_hold(row, "selection-quantity-mismatch")
        elif usable:
            if not ids:
                line_hold(row, "receipt-unavailable")
            elif len(ids) > 1:
                line_hold(row, "receipt-selection-required")
            elif receipt_rows[ids[0]]["before_proposals_milliunits"] < row["quantity_milliunits"]:
                line_hold(row, "receipt-shortage")
            else:
                comparison["selection_mode"] = "sole-receipt"
                selections = [{"receipt_line_id": ids[0], "quantity_milliunits": row["quantity_milliunits"]}]
        for selection in selections:
            rid, quantity = selection["receipt_line_id"], selection["quantity_milliunits"]
            receipt = receipt_rows.get(rid)
            same_scope = receipt is not None and key_of(receipt, PO_KEY) == po_key and receipt["unit"] == row["unit"]
            eligible = bool(usable and same_scope and receipt["available_at_as_of"])
            available = receipt["before_proposals_milliunits"] if receipt is not None else None
            comparison["selections"].append({
                "receipt_line_id": rid, "quantity_milliunits": quantity,
                "available_milliunits": available, "eligible": eligible,
            })
            if usable:
                if receipt is None:
                    line_hold(row, "selected-receipt-missing")
                elif not same_scope:
                    line_hold(row, "selected-receipt-scope-mismatch")
                elif not receipt["available_at_as_of"]:
                    line_hold(row, "selected-receipt-unavailable")
                elif quantity > available:
                    line_hold(row, "selected-receipt-shortage")
        comparison["total_selected_milliunits"] = sum(item["quantity_milliunits"] for item in selections)

    events.append(event(
        "join-receipt-evidence", "join", "Resolved explicit partial selections or a sole sufficient receipt using only posted-by-cutoff capacity net of history.",
        {"excluded_receipts": len(excluded), "line_selections": sum(len(row["receipts"]["selections"]) for row in lines)},
        table("Receipt capacity at cutoff", ["receipt", "quantity", "prior", "available", "posted_date", "eligible_time"], [
            [rid, row["quantity_milliunits"], row["historical_used_milliunits"], row["before_proposals_milliunits"],
             row["posted_business_date"], row["available_at_as_of"]] for rid, row in receipt_rows.items()
        ], [index for index, row in enumerate(receipt_rows.values()) if not row["available_at_as_of"]]),
        table("Receipt selection evidence", ["invoice", "line", "mode", "requested", "selected", "shortage"], [
            [row["invoice_id"], row["line_id"], row["receipts"]["selection_mode"], row["quantity_milliunits"],
             row["receipts"]["total_selected_milliunits"], row["receipts"]["shortage_milliunits"]] for row in lines
        ]),
    ))

    for row in lines:
        po = row["po"]
        if po is None or not po["join_matches"] or row["invoice_id"] in data["unsupported"]:
            continue
        po_net = half_up(row["quantity_milliunits"], po["unit_price_minor"])
        unit_delta = abs(row["unit_price_minor"] - po["unit_price_minor"])
        left, right = unit_delta * 10000, po["unit_price_minor"] * settings["unit_tolerance_bps"]
        line_delta = abs(row["line_net_minor"] - po_net)
        unit_pass = left <= right
        cap_pass = line_delta <= settings["line_amount_cap_minor"]
        if po["unit_price_minor"] == 0:
            unit_pass = row["unit_price_minor"] == 0 and row["line_net_minor"] == 0
            if not unit_pass:
                line_hold(row, "zero-price-mismatch")
        else:
            if not unit_pass:
                line_hold(row, "unit-price-out-of-tolerance")
            if not cap_pass:
                line_hold(row, "line-amount-out-of-tolerance")
        row["price"] = dict(zip(PRICE_KEYS, (po_net, unit_delta, left, right, unit_pass, line_delta, cap_pass)))

    def individually_held(iid):
        return bool(header_holds[iid] or any(row["individual_reason_codes"] for row in invoice_lines[iid]))

    def demands(rows):
        receipt_demand, po_demand = defaultdict(int), defaultdict(int)
        for row in rows:
            po_demand[key_of(row, PO_KEY)] += row["quantity_milliunits"]
            for selected in row["receipts"]["selections"]:
                receipt_demand[selected["receipt_line_id"]] += selected["quantity_milliunits"]
        return receipt_demand, po_demand

    for iid in reviews:
        if individually_held(iid):
            continue
        own_receipts, own_pos = demands(invoice_lines[iid])
        if any(quantity > receipt_rows[rid]["before_proposals_milliunits"] for rid, quantity in own_receipts.items()):
            header_hold(iid, "invoice-receipt-capacity-exceeded")
        if any(quantity > po_rows[key]["before_proposals_milliunits"] for key, quantity in own_pos.items()):
            header_hold(iid, "invoice-po-capacity-exceeded")

    events.append(event(
        "evaluate-price-and-quantity", "decision", "Computed exact HALF_UP nets and both inclusive price limits; removed complete invoices with any individual hold before competition.",
        {"individually_held_invoices": sum(individually_held(iid) for iid in reviews),
         "unit_tolerance_bps": settings["unit_tolerance_bps"], "line_amount_cap_minor": settings["line_amount_cap_minor"]},
        table("Exact price cross-products", ["invoice", "line", "unit_left", "unit_right", "net_delta", "unit_pass"], [
            [row["invoice_id"], row["line_id"], row["price"]["unit_test_left"], row["price"]["unit_test_right"],
             row["price"]["line_difference_minor"], row["price"]["unit_price_pass"]] for row in lines
        ]),
        table("Line calculation and individual holds", ["invoice", "line", "calculated_net", "line_cap_pass", "line_holds"], [
            [row["invoice_id"], row["line_id"], row["calculated_line_net_minor"], row["price"]["line_cap_pass"],
             len(row["individual_reason_codes"])] for row in lines
        ]),
    ))

    eligible_invoices = {iid for iid in reviews if not individually_held(iid)}
    eligible_lines = [row for row in lines if row["invoice_id"] in eligible_invoices]
    receipt_demand, po_demand = demands(eligible_lines)
    conflicts, demand_rows = [], []
    # Both resource sets use the same immutable pre-conflict candidate population.
    for resource_type, demand, resources in (
        ("po-line", po_demand, po_rows), ("receipt", receipt_demand, receipt_rows)
    ):
        for resource_key, quantity in demand.items():
            resource = resources[resource_key]
            available = resource["before_proposals_milliunits"]
            oversubscribed = quantity > available
            display_id = resource["po_id"] + ":" + resource["po_line_id"] if resource_type == "po-line" else resource_key
            demand_rows.append([resource_type, display_id, available, quantity, oversubscribed])
            if not oversubscribed:
                continue
            if resource_type == "po-line":
                affected_lines = [row for row in eligible_lines if key_of(row, PO_KEY) == resource_key]
                code = "po-capacity-conflict"
            else:
                affected_lines = [
                    row for row in eligible_lines
                    if any(item["receipt_line_id"] == resource_key for item in row["receipts"]["selections"])
                ]
                code = "receipt-capacity-conflict"
            participants = sorted({row["invoice_id"] for row in affected_lines})
            conflicts.append({
                "resource_type": resource_type, **{key: resource[key] for key in SCOPE},
                "po_id": resource["po_id"], "po_line_id": resource["po_line_id"],
                "receipt_line_id": resource_key if resource_type == "receipt" else None, "unit": resource["unit"],
                "available_milliunits": available, "demand_milliunits": quantity,
                "competing_invoice_ids": participants,
            })
            for row in affected_lines:
                row["conflict_reason_codes"].add(code)
            for iid in participants:
                header_hold(iid, code)
    conflicts.sort(key=lambda row: (*key_of(row, SCOPE), row["resource_type"], row["po_id"],
                                   row["po_line_id"], row["receipt_line_id"] or ""))
    demand_rows.sort(key=lambda row: (row[0], row[1]))
    events.append(event(
        "resolve-capacity-conflicts", "decision", "Aggregated all otherwise eligible invoice demand across receipts and POs together; every oversubscribed-resource participant is held without retry.",
        {"candidate_invoices": len(eligible_invoices), "oversubscribed_resources": len(conflicts)},
        table("Pre-conflict resource demand", ["type", "resource", "available", "demand", "conflict"], demand_rows,
              [index for index, row in enumerate(demand_rows) if row[4]]),
        table("All competitor evidence", ["type", "resource", "available", "demand", "invoice_count"], [
            [row["resource_type"], row["receipt_line_id"] or row["po_id"], row["available_milliunits"],
             row["demand_milliunits"], len(row["competing_invoice_ids"])] for row in conflicts
        ], range(len(conflicts))),
    ))

    proposals, summaries = [], {}
    for iid, review in reviews.items():
        reasons = set(header_holds[iid])
        for row in invoice_lines[iid]:
            reasons.update(row["individual_reason_codes"])
            reasons.update(row["conflict_reason_codes"])
        held = bool(reasons)
        review.update(status="held" if held else "ready-for-review", reason_codes=sorted(reasons),
                      proposed_net_minor=0 if held else review["header_net_minor"])
        for row in invoice_lines[iid]:
            row["individual_reason_codes"] = sorted(row["individual_reason_codes"])
            row["conflict_reason_codes"] = sorted(row["conflict_reason_codes"])
            row.update(status="held" if held else "proposed",
                       proposed_quantity_milliunits=0 if held else row["quantity_milliunits"])
            if held:
                continue
            selected_sum = sum(item["quantity_milliunits"] for item in row["receipts"]["selections"])
            if selected_sum != row["quantity_milliunits"] or any(not item["eligible"] for item in row["receipts"]["selections"]):
                raise RuntimeError("Internal proposal quantity or eligibility conservation failure")
            for selection in row["receipts"]["selections"]:
                proposal = {key: row[key] for key in ("invoice_id", "line_id", *SCOPE, "po_id", "po_line_id", "unit")}
                proposal.update(receipt_line_id=selection["receipt_line_id"], quantity_milliunits=selection["quantity_milliunits"])
                proposals.append(proposal)
                receipt_rows[selection["receipt_line_id"]]["proposed_milliunits"] += selection["quantity_milliunits"]
            po_rows[key_of(row, PO_KEY)]["proposed_milliunits"] += row["quantity_milliunits"]
        scope = key_of(review, SCOPE)
        if scope not in summaries:
            summaries[scope] = dict(zip(SCOPE, scope))
            summaries[scope].update(invoice_count=0, ready_invoice_count=0, held_invoice_count=0,
                                    intake_net_minor=0, ready_net_minor=0, held_net_minor=0)
        summary = summaries[scope]
        summary["invoice_count"] += 1
        summary["held_invoice_count" if held else "ready_invoice_count"] += 1
        summary["intake_net_minor"] += review["header_net_minor"]
        summary["held_net_minor" if held else "ready_net_minor"] += review["header_net_minor"]
    for resource in (*receipt_rows.values(), *po_rows.values()):
        remaining = resource["before_proposals_milliunits"] - resource["proposed_milliunits"]
        if remaining < 0:
            raise RuntimeError("Internal resource capacity conservation failure")
        resource["remaining_milliunits"] = remaining
    proposals.sort(key=lambda row: (*key_of(row, SCOPE), row["invoice_id"], row["line_id"], row["receipt_line_id"]))
    summary_rows = [summaries[key] for key in sorted(summaries)]
    exception_rows = [diagnostics[key] for key in sorted(diagnostics)]

    events.append(event(
        "route-invoice-holds", "exception", "Retained all original line evaluations and source exclusions; any held invoice has zero proposed net and no allocation rows.",
        {"held_invoices": sum(row["status"] == "held" for row in reviews.values()), "diagnostics": len(exception_rows)},
        table("Atomic invoice dispositions", ["invoice", "status", "reason_count", "header_net"], [
            [row["invoice_id"], row["status"], len(row["reason_codes"]), row["header_net_minor"]]
            for row in reviews.values()
        ], [index for index, row in enumerate(reviews.values()) if row["status"] == "held"]),
        table("Owned holds and exclusions", ["source", "record", "code", "owner"], [
            [row["source"], row["record_id"], row["code"], row["owner_role"]] for row in exception_rows
        ], range(len(exception_rows))),
    ))
    result = {
        "schema_version": 1, "status": "completed_with_exceptions" if exception_rows else "completed",
        "outputs": {
            "context": {
                "batch_id": payload["batch_id"], "as_of": payload["as_of"],
                "business_utc_offset_minutes": payload["business_utc_offset_minutes"],
                "business_date": cutoff.astimezone(zone).date().isoformat(),
                "control_version": payload["controls"]["control_version"],
                **settings, "source_counts": data["counts"],
            },
            "invoice_reviews": list(reviews.values()), "line_comparisons": lines,
            "proposed_allocations": proposals,
            "remaining_capacity": {"receipts": list(receipt_rows.values()), "po_lines": list(po_rows.values())},
            "historical_invoices": history_rows, "prior_allocations": allocation_rows,
            "excluded_receipts": excluded, "capacity_conflicts": conflicts, "summary": summary_rows, "review": dict(REVIEW),
        },
        "exceptions": exception_rows,
    }
    events.append(event(
        "emit-ap-review", "output", "Emitted full review rows, non-overlapping quantity proposals and remaining capacities. Ready and held nets conserve intake within each currency scope.",
        {"status": result["status"], "human_review": "pending", "live_action": "none",
         "ready_invoices": sum(row["ready_invoice_count"] for row in summary_rows),
         "held_invoices": sum(row["held_invoice_count"] for row in summary_rows), "proposal_rows": len(proposals)},
        table("Per-scope review totals in minor units", ["entity", "vendor", "currency", "intake", "ready", "held"], [
            [row["legal_entity_id"], row["vendor_id"], row["currency"],
             row["intake_net_minor"], row["ready_net_minor"], row["held_net_minor"]] for row in summary_rows
        ]),
        table("Proposed receipt quantities only", ["invoice", "line", "receipt", "milliunits"], [
            [row["invoice_id"], row["line_id"], row["receipt_line_id"], row["quantity_milliunits"]] for row in proposals
        ], range(len(proposals))),
    ))
    return deepcopy(result), events


if __name__ == "__main__":
    run_cli(solve, scenario_id="financial-services-02")
