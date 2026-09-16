"""File-only Logistics evidence and charge review of an explicit synthetic snapshot."""
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP, localcontext
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "_shared"))
from scenario_support import run_cli


CENT = Decimal("0.01")
ZERO = Decimal("0")
CHARGES = {"linehaul", "fuel", "detention"}
CONFIG_FIELDS = {
    "as_of": "instant", "absolute_tolerance": "amount",
    "relative_tolerance": "fraction", "missing_pod_grace_hours": "nonnegative",
    "review_owner": "id",
}
SCHEMAS = {
    "shipments.json": ("shipment_id", {
        "shipment_id": "id", "carrier_id": "id", "lane_id": "id",
        "currency": "currency", "planned_delivery_at": "instant", "shipped_units": "positive",
    }),
    "pod-events.json": ("pod_id", {
        "pod_id": "id", "shipment_id": "id", "revision": "positive",
        "recorded_at": "instant", "state": ("delivered", "void"),
        "delivered_at": "pod-instant", "received_by": "pod-id",
        "delivered_units": "pod-positive", "gate_in_at": "pod-instant",
        "gate_out_at": "pod-instant",
    }),
    "rate-cards.json": ("rate_id", {
        "rate_id": "id", "carrier_id": "id", "lane_id": "id", "currency": "currency",
        "valid_from": "date", "valid_to": "date", "linehaul": "amount",
        "fuel_fraction": "fraction", "free_wait_minutes": "nonnegative",
        "detention_block_minutes": "positive", "detention_block_amount": "amount",
        "detention_cap": "amount",
    }),
    "carrier-invoices.json": ("invoice_id", {
        "invoice_id": "id", "carrier_id": "id", "currency": "currency",
        "invoice_date": "date", "total": "amount",
    }),
    "invoice-lines.json": ("line_id", {
        "line_id": "id", "invoice_id": "id", "shipment_id": "id",
        "charge_code": ("linehaul", "fuel", "detention"), "amount": "amount",
    }),
    "review-history.json": ("case_id", {
        "case_id": "id", "shipment_id": "id", "issue_code": "id",
        "state": ("open", "evidence-requested", "resolved"),
        "updated_at": "instant", "owner": "id",
    }),
}
BILLING_CODES = {
    "missing-billing", "missing-charge", "duplicate-charge", "split-billing",
    "missing-invoice", "carrier-mismatch", "currency-mismatch",
    "empty-invoice", "future-invoice", "header-mismatch",
}
POD_CODES = {"contradictory-pod", "void-pod", "quantity-mismatch"}
RATE_CODES = {"missing-rate", "ambiguous-rate"}
CASE_CODES = BILLING_CODES | POD_CODES | RATE_CODES | {"missing-pod", "variance"}
ISSUES = {
    "missing-pod": (
        "No POD revision is eligible at the snapshot cutoff.",
        "Request POD evidence from the export owner.",
    ),
    "contradictory-pod": (
        "Multiple POD rows share the highest eligible revision.",
        "Resolve the conflicting POD revisions in a new synthetic export.",
    ),
    "void-pod": (
        "The highest eligible POD revision is void.",
        "Request usable delivery evidence from the export owner.",
    ),
    "quantity-mismatch": (
        "Delivered units do not match shipped units.",
        "Clarify the delivered quantity in a new synthetic export.",
    ),
    "missing-rate": (
        "No rate is effective for the shipment's UTC delivery date.",
        "Request an effective synthetic rate row.",
    ),
    "ambiguous-rate": (
        "Multiple rates are effective for the shipment's UTC delivery date.",
        "Resolve overlapping synthetic rate rows.",
    ),
    "variance": (
        "Billed total is outside the symmetric inclusive tolerance.",
        "Review the calculated and billed charges; do not authorize payment.",
    ),
    "missing-billing": (
        "The shipment has no invoice lines.",
        "Supply the complete charge lines in a new synthetic export.",
    ),
    "missing-charge": (
        "A billed shipment is missing a required charge code.",
        "Supply all three charge codes, including zero charges, in a new synthetic export.",
    ),
    "duplicate-charge": (
        "Multiple lines bill the same shipment and charge code.",
        "Clarify duplicate business billings in a new synthetic export.",
    ),
    "split-billing": (
        "The shipment is associated with more than one invoice.",
        "Clarify the shipment's single invoice assignment in a new synthetic export.",
    ),
    "missing-invoice": (
        "An invoice line references a missing invoice header.",
        "Supply or correct the invoice reference in a new synthetic export.",
    ),
    "missing-shipment": (
        "The record references a missing shipment.",
        "Supply or correct the shipment reference in a new synthetic export.",
    ),
    "carrier-mismatch": (
        "Invoice and shipment carrier identifiers disagree.",
        "Clarify the carrier association in a new synthetic export.",
    ),
    "currency-mismatch": (
        "Invoice and shipment currencies disagree.",
        "Clarify the currency association without FX in a new synthetic export.",
    ),
    "header-mismatch": (
        "Invoice header total does not equal its complete line sum.",
        "Reconcile the header and all charge lines in a new synthetic export.",
    ),
    "empty-invoice": (
        "The invoice header has no charge lines.",
        "Supply or clarify the invoice lines in a new synthetic export.",
    ),
    "future-invoice": (
        "Invoice date is after the snapshot's UTC date.",
        "Clarify the snapshot's invoice scope in a new synthetic export.",
    ),
    "ambiguous-history": (
        "Multiple eligible prior cases address the same shipment and issue.",
        "Clarify the prior-case records in a new synthetic export.",
    ),
    "unsupported-issue": (
        "The prior case uses an unsupported issue code.",
        "Clarify the prior-case issue code in a new synthetic export.",
    ),
}
VALIDATION_MESSAGES = {
    "id": "Value must be nonempty trimmed printable ASCII text of at most 80 characters.",
    "currency": "Currency must contain exactly three uppercase ASCII letters.",
    "amount": "Amount must be a nonnegative decimal string with exactly two fractional digits.",
    "fraction": "Fraction must be a bounded nonnegative plain decimal string.",
    "integer": "Value must be an integer within its documented bounds, excluding booleans.",
    "date": "Date must be a real calendar date in YYYY-MM-DD form.",
    "instant": "Instant must be a whole-second timestamp with an explicit offset, representable in UTC.",
    "enum": "Value must be one of the documented string alternatives.",
    "null": "Void POD delivery fields must all be null.",
}


def _text(value):
    return (
        isinstance(value, str) and 0 < len(value) <= 80
        and value == value.strip() and all(" " <= char <= "~" for char in value)
    )


def _instant(value):
    if not isinstance(value, str) or not re.fullmatch(
        r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
        r"(Z|[+-][0-9]{2}:[0-9]{2})", value
    ):
        raise ValueError("Invalid instant syntax")
    if value[-1] != "Z" and (int(value[-5:-3]) >= 24 or int(value[-2:]) >= 60):
        raise ValueError("Invalid UTC offset")
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _utc(value):
    return _instant(value).isoformat().replace("+00:00", "Z")


def _seconds(delta):
    return delta.days * 86400 + delta.seconds


def _money(value):
    rounded = value.quantize(CENT, rounding=ROUND_HALF_UP)
    return format(ZERO if rounded == ZERO else rounded, ".2f")


def _amount_sum(rows, key="amount"):
    return sum((Decimal(row[key]) for row in rows), ZERO)


def _issue(code, entity_type, entity_id, shipment_id, owner, *, overdue=False):
    message, action = ISSUES[code]
    if code == "missing-pod" and overdue:
        action = "Request overdue POD evidence from the export owner."
    return {
        "code": code, "message": message, "entity_type": entity_type,
        "entity_id": entity_id, "shipment_id": shipment_id, "owner": owner,
        "next_action": action,
    }


def _ordered_issues(issues):
    return sorted(issues, key=lambda row: (
        row["shipment_id"] or "", row["code"], row["entity_type"], row["entity_id"]
    ))


def _table(title, columns, rows, highlights=()):
    return {
        "title": title + (f" (first 8 of {len(rows)} rows)" if len(rows) > 8 else ""),
        "columns": columns,
        "rows": [
            [cell[:69] + "..." if isinstance(cell, str) and len(cell) > 72 else cell for cell in row]
            for row in rows[:8]
        ],
        "total_rows": len(rows),
        "highlight_rows": sorted(set(index for index in highlights if 0 <= index < min(8, len(rows)))),
    }


def _event(step_id, kind, caption, facts, *tables):
    return {
        "step_id": step_id, "kind": kind, "caption": caption,
        "facts": facts, "tables": list(tables),
    }


def _validate(payload, owner):
    errors = {}

    def error(code, location, message):
        errors[(code, location)] = {
            "code": code, "message": message, "entity_type": "input",
            "entity_id": location, "shipment_id": None, "owner": owner,
            "next_action": "Correct the input bundle and rerun the review.",
        }

    def shape(value, keys, location):
        if not isinstance(value, dict) or set(value) != set(keys):
            error("invalid-schema", location, "Object keys must match the documented schema.")
            return False
        return True

    def scalar(value, rule, location):
        valid = False
        code = rule if isinstance(rule, str) else "enum"
        if isinstance(rule, tuple):
            valid = isinstance(value, str) and value in rule
        elif rule == "id":
            valid = _text(value)
        elif rule == "currency":
            valid = isinstance(value, str) and re.fullmatch(r"[A-Z]{3}", value) is not None
        elif rule == "amount":
            valid = isinstance(value, str) and re.fullmatch(r"(0|[1-9][0-9]{0,11})\.[0-9]{2}", value) is not None
        elif rule == "fraction":
            valid = isinstance(value, str) and re.fullmatch(r"(0|[1-9][0-9]{0,5})(\.[0-9]{1,9})?", value) is not None
        elif rule in ("positive", "nonnegative"):
            code = "integer"
            valid = type(value) is int and (1 if rule == "positive" else 0) <= value <= 1_000_000_000
        elif rule == "date":
            try:
                valid = (
                    isinstance(value, str)
                    and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value) is not None
                    and date.fromisoformat(value).isoformat() == value
                )
            except ValueError:
                valid = False
        elif rule == "instant":
            try:
                _instant(value)
                valid = True
            except (ValueError, OverflowError):
                valid = False
        elif rule == "null":
            valid = value is None
        if not valid:
            error("invalid-" + code, location, VALIDATION_MESSAGES[code])
        return valid

    if not shape(payload, {"config", "files"}, "payload"):
        return _ordered_issues(errors.values())
    if shape(payload["config"], CONFIG_FIELDS, "config"):
        for field, rule in CONFIG_FIELDS.items():
            scalar(payload["config"][field], rule, "config." + field)
    if not shape(payload["files"], SCHEMAS, "files"):
        return _ordered_issues(errors.values())
    for filename, (primary, schema) in SCHEMAS.items():
        rows = payload["files"][filename]
        if not isinstance(rows, list):
            error("invalid-schema", filename, "Logical exports must be row arrays.")
            continue
        ids = Counter()
        for index, row in enumerate(rows):
            identity = row.get(primary) if isinstance(row, dict) else None
            location = f"{filename}:{identity}" if _text(identity) else f"{filename}[{index}]"
            if _text(identity):
                ids[identity] += 1
            if not shape(row, schema, location):
                continue
            valid = True
            for field, rule in schema.items():
                if isinstance(rule, str) and rule.startswith("pod-"):
                    if row["state"] == "void":
                        rule = "null"
                    elif row["state"] == "delivered":
                        rule = rule[4:]
                    else:
                        continue
                if not scalar(row[field], rule, location + "." + field):
                    valid = False
            if valid and filename == "pod-events.json" and row["state"] == "delivered":
                times = [_instant(row[key]) for key in (
                    "gate_in_at", "delivered_at", "gate_out_at", "recorded_at"
                )]
                if times != sorted(times):
                    error("invalid-time-order", location, "POD times must follow gate-in, delivery, gate-out, then recording.")
            if valid and filename == "rate-cards.json" and row["valid_from"] >= row["valid_to"]:
                error("invalid-date-range", location, "Rate valid_from must precede exclusive valid_to.")
        for identity, count in ids.items():
            if count > 1:
                error("duplicate-id", f"{filename}:{identity}.{primary}", "Primary IDs must be unique within each logical export.")
    return _ordered_issues(errors.values())


def _condition(code, shipment, usable_pod):
    issues = shipment["issue_codes"]
    if code == "missing-pod":
        return not usable_pod
    if code in POD_CODES:
        return True if code in issues else (False if usable_pod else None)
    if code in RATE_CODES:
        return True if code in issues else (False if shipment["rate_id"] is not None else None)
    if code == "variance":
        return None if shipment["variance_amount"] is None else code in issues
    return code in issues


def _review(files, config, events):
    sources = {
        filename: sorted(rows, key=lambda row: row[SCHEMAS[filename][0]])
        for filename, rows in files.items()
    }
    shipments = {row["shipment_id"]: row for row in sources["shipments.json"]}
    invoices = {row["invoice_id"]: row for row in sources["carrier-invoices.json"]}
    lines = sources["invoice-lines.json"]
    pods = sources["pod-events.json"]
    rates = {row["rate_id"]: row for row in sources["rate-cards.json"]}
    history = sources["review-history.json"]
    cutoff, owner = _instant(config["as_of"]), config["review_owner"]
    queue = []
    by_shipment, by_invoice, pod_groups, rate_groups = (defaultdict(list) for _ in range(4))
    for line in lines:
        by_shipment[line["shipment_id"]].append(line)
        by_invoice[line["invoice_id"]].append(line)
    for pod in pods:
        pod_groups[pod["shipment_id"]].append(pod)
    for rate in rates.values():
        rate_groups[(rate["carrier_id"], rate["lane_id"], rate["currency"])].append(rate)

    invoice_faults = {}
    invoice_line_totals = {}
    for iid, invoice in invoices.items():
        total = _amount_sum(by_invoice[iid])
        faults = set()
        if not by_invoice[iid]:
            faults.add("empty-invoice")
        if Decimal(invoice["total"]) != total:
            faults.add("header-mismatch")
        if date.fromisoformat(invoice["invoice_date"]) > cutoff.date():
            faults.add("future-invoice")
        invoice_faults[iid], invoice_line_totals[iid] = faults, total
        for code in sorted(faults):
            queue.append(_issue(code, "invoice", iid, None, owner))

    line_currency, line_faults = {}, {}
    for line in lines:
        invoice, shipment = invoices.get(line["invoice_id"]), shipments.get(line["shipment_id"])
        line_currency[line["line_id"]] = (
            invoice["currency"] if invoice is not None
            else shipment["currency"] if shipment is not None else None
        )
        faults = set()
        if invoice is None:
            faults.add("missing-invoice")
        if shipment is None:
            faults.add("missing-shipment")
            for code in sorted(faults):
                queue.append(_issue(code, "line", line["line_id"], line["shipment_id"], owner))
        line_faults[line["line_id"]] = faults

    ship_rows, ship_issues, billing_issues, rate_candidates = {}, {}, {}, {}
    for sid, shipment in shipments.items():
        related = by_shipment[sid]
        invoice_ids = sorted({row["invoice_id"] for row in related})
        own = set()
        if not related:
            own.add("missing-billing")
        else:
            charges = Counter(row["charge_code"] for row in related)
            if set(charges) != CHARGES:
                own.add("missing-charge")
            if any(count > 1 for count in charges.values()):
                own.add("duplicate-charge")
            if len(invoice_ids) > 1:
                own.add("split-billing")
        inherited = set()
        for iid in invoice_ids:
            if iid not in invoices:
                own.add("missing-invoice")
                continue
            invoice = invoices[iid]
            inherited.update(invoice_faults[iid])
            if invoice["carrier_id"] != shipment["carrier_id"]:
                own.add("carrier-mismatch")
            if invoice["currency"] != shipment["currency"]:
                own.add("currency-mismatch")
        for code in sorted(own):
            queue.append(_issue(code, "shipment", sid, sid, owner))
        billing_issues[sid] = own | inherited
        ship_issues[sid] = set(billing_issues[sid])
        rate_day = _instant(shipment["planned_delivery_at"]).date().isoformat()
        rate_candidates[sid] = [
            row for row in rate_groups[(shipment["carrier_id"], shipment["lane_id"], shipment["currency"])]
            if row["valid_from"] <= rate_day < row["valid_to"]
        ]
        ship_rows[sid] = {
            "shipment_id": sid, "currency": shipment["currency"], "invoice_ids": invoice_ids,
            "pod_id": None, "rate_id": None, "rate_date": rate_day,
            "billed_amount": _money(_amount_sum(related)) if all(
                line_currency[row["line_id"]] == shipment["currency"] for row in related
            ) else None,
            "linehaul": None, "fuel": None, "detention": None, "expected_amount": None,
            "tolerance_amount": None, "variance_amount": None, "dwell_seconds": None,
            "excess_seconds": None, "detention_blocks": None,
            "missing_pod_age_seconds": None, "pod_overdue": None,
            "disposition": "held", "issue_codes": [],
        }

    events.append(_event(
        "join-exports", "join",
        "Joined every line without deduplication; structural billing holds are retained separately from evidence pricing.",
        {"shipments": len(shipments), "invoices": len(invoices),
         "orphan_lines": sum(row["shipment_id"] not in shipments for row in lines),
         "missing_header_lines": sum(row["invoice_id"] not in invoices for row in lines),
         "prior_cases": len(history)},
        _table("Shipment join counts",
               ["shipment_id", "line_rows", "invoice_ids", "POD_rows", "rate_candidates", "billing_holds"],
               [[sid, len(by_shipment[sid]), len(row["invoice_ids"]), len(pod_groups[sid]),
                 len(rate_candidates[sid]), len(billing_issues[sid])] for sid, row in ship_rows.items()]),
        _table("Exact invoice header checks",
               ["invoice_id", "currency", "header_total", "line_total", "matches", "faults"],
               [[iid, row["currency"], row["total"], _money(invoice_line_totals[iid]),
                 Decimal(row["total"]) == invoice_line_totals[iid], ", ".join(sorted(invoice_faults[iid]))]
                for iid, row in invoices.items()]),
    ))

    pod_rows, eligible, usable_pods = {}, defaultdict(list), {}
    for pod in pods:
        sid = pod["shipment_id"]
        disposition = "superseded"
        if _instant(pod["recorded_at"]) > cutoff:
            disposition = "future-excluded"
        elif sid not in shipments:
            disposition = "missing-shipment"
            queue.append(_issue("missing-shipment", "pod", pod["pod_id"], sid, owner))
        else:
            eligible[sid].append(pod)
        pod_rows[pod["pod_id"]] = {
            "pod_id": pod["pod_id"], "shipment_id": sid, "revision": pod["revision"],
            "recorded_at": _utc(pod["recorded_at"]), "disposition": disposition,
        }
    rate_rows = {
        rid: {"rate_id": rid, "candidate_for": [], "selected_for": [], "disposition": "unused"}
        for rid in rates
    }

    def shipment_issue(sid, code, overdue=False):
        if code not in ship_issues[sid]:
            ship_issues[sid].add(code)
            queue.append(_issue(code, "shipment", sid, sid, owner, overdue=overdue))

    for sid, row in ship_rows.items():
        candidates = eligible[sid]
        if not candidates:
            age = max(0, _seconds(cutoff - _instant(shipments[sid]["planned_delivery_at"])))
            row["missing_pod_age_seconds"] = age
            row["pod_overdue"] = age > config["missing_pod_grace_hours"] * 3600
            shipment_issue(sid, "missing-pod", row["pod_overdue"])
        else:
            top_revision = max(pod["revision"] for pod in candidates)
            top = [pod for pod in candidates if pod["revision"] == top_revision]
            if len(top) > 1:
                shipment_issue(sid, "contradictory-pod")
                for pod in top:
                    pod_rows[pod["pod_id"]]["disposition"] = "ambiguous"
            else:
                pod = top[0]
                row["pod_id"] = pod["pod_id"]
                if pod["state"] == "void":
                    pod_rows[pod["pod_id"]]["disposition"] = "void"
                    shipment_issue(sid, "void-pod")
                elif pod["delivered_units"] != shipments[sid]["shipped_units"]:
                    pod_rows[pod["pod_id"]]["disposition"] = "quantity-mismatch"
                    shipment_issue(sid, "quantity-mismatch")
                else:
                    pod_rows[pod["pod_id"]]["disposition"] = "selected"
                    usable_pods[sid] = pod
                    row["dwell_seconds"] = _seconds(_instant(pod["gate_out_at"]) - _instant(pod["gate_in_at"]))
        candidates = rate_candidates[sid]
        for rate in candidates:
            rate_rows[rate["rate_id"]]["candidate_for"].append(sid)
        if not candidates:
            shipment_issue(sid, "missing-rate")
        elif len(candidates) > 1:
            shipment_issue(sid, "ambiguous-rate")
        else:
            row["rate_id"] = candidates[0]["rate_id"]
            rate_rows[row["rate_id"]]["selected_for"].append(sid)
    for row in rate_rows.values():
        row["disposition"] = (
            "selected" if row["selected_for"] else "ambiguous-only" if row["candidate_for"] else "unused"
        )
    events.append(_event(
        "select-evidence", "decision",
        "Excluded future POD independently, then resolved unique eligible revisions and half-open UTC-date rate matches.",
        {"cutoff": _utc(config["as_of"]), "usable_POD": len(usable_pods),
         "future_POD_rows": sum(row["disposition"] == "future-excluded" for row in pod_rows.values()),
         "ambiguous_POD_rows": sum(row["disposition"] == "ambiguous" for row in pod_rows.values()),
         "selected_rates": sum(row["rate_id"] is not None for row in ship_rows.values())},
        _table("Selected evidence",
               ["shipment_id", "POD_id", "rate_id", "rate_date", "usable_POD", "rate_matches"],
               [[sid, row["pod_id"], row["rate_id"], row["rate_date"], sid in usable_pods,
                 len(rate_candidates[sid])] for sid, row in ship_rows.items()]),
        _table("All POD revision dispositions",
               ["pod_id", "shipment_id", "revision", "recorded_at", "disposition"],
               [[row[key] for key in ("pod_id", "shipment_id", "revision", "recorded_at", "disposition")]
                for row in pod_rows.values()],
               [index for index, row in enumerate(pod_rows.values()) if row["disposition"] != "selected"]),
    ))

    uncapped = {}
    for sid, row in ship_rows.items():
        if sid not in usable_pods or row["rate_id"] is None:
            continue
        rate = rates[row["rate_id"]]
        linehaul = Decimal(rate["linehaul"])
        fuel = (linehaul * Decimal(rate["fuel_fraction"])).quantize(CENT, rounding=ROUND_HALF_UP)
        excess = max(0, row["dwell_seconds"] - rate["free_wait_minutes"] * 60)
        block_seconds = rate["detention_block_minutes"] * 60
        blocks = (excess + block_seconds - 1) // block_seconds
        uncapped[sid] = Decimal(rate["detention_block_amount"]) * blocks
        detention = min(Decimal(rate["detention_cap"]), uncapped[sid])
        computed_total = linehaul + fuel + detention
        tolerance = max(
            Decimal(config["absolute_tolerance"]),
            (computed_total * Decimal(config["relative_tolerance"])).quantize(CENT, rounding=ROUND_HALF_UP),
        )
        row.update({
            "linehaul": _money(linehaul), "fuel": _money(fuel), "detention": _money(detention),
            "expected_amount": _money(computed_total), "tolerance_amount": _money(tolerance),
            "excess_seconds": excess, "detention_blocks": blocks,
        })
    events.append(_event(
        "calculate-charges", "decision",
        "Rounded each fuel charge half-up and priced exact-second ceiling blocks; caps limit detention money, never block counts.",
        {"computed_shipments": len(uncapped), "uncomputed_shipments": len(shipments) - len(uncapped),
         "fuel_rounding": "ROUND_HALF_UP",
         "cap_reductions": sum(value > Decimal(rates[ship_rows[sid]["rate_id"]]["detention_cap"])
                               for sid, value in uncapped.items())},
        _table("Actual charge components",
               ["shipment_id", "linehaul", "fuel", "uncapped_detention", "detention", "expected_amount"],
               [[sid, row["linehaul"], row["fuel"], _money(uncapped[sid]) if sid in uncapped else None,
                 row["detention"], row["expected_amount"]] for sid, row in ship_rows.items()]),
        _table("Actual detention arithmetic",
               ["shipment_id", "dwell_seconds", "free_seconds", "excess_seconds", "blocks", "cap"],
               [[sid, row["dwell_seconds"],
                 rates[row["rate_id"]]["free_wait_minutes"] * 60 if sid in uncapped else None,
                 row["excess_seconds"], row["detention_blocks"],
                 rates[row["rate_id"]]["detention_cap"] if sid in uncapped else None]
                for sid, row in ship_rows.items()]),
    ))

    for sid, row in ship_rows.items():
        if row["expected_amount"] is not None and not billing_issues[sid]:
            variance = Decimal(row["billed_amount"]) - Decimal(row["expected_amount"])
            row["variance_amount"] = _money(variance)
            if abs(variance) > Decimal(row["tolerance_amount"]):
                shipment_issue(sid, "variance")
        row["issue_codes"] = sorted(ship_issues[sid])
        row["disposition"] = "held" if ship_issues[sid] else "ready-for-review"
    events.append(_event(
        "compare-charges", "decision",
        "Compared only priceable, structurally supported billings with the symmetric inclusive tolerance; other variances stay null.",
        {"comparable_shipments": sum(row["variance_amount"] is not None for row in ship_rows.values()),
         "ready_shipments": sum(row["disposition"] == "ready-for-review" for row in ship_rows.values()),
         "held_shipments": sum(row["disposition"] == "held" for row in ship_rows.values())},
        _table("Shipment charge comparison",
               ["shipment_id", "currency", "billed_amount", "expected_amount", "variance", "tolerance"],
               [[sid, row["currency"], row["billed_amount"], row["expected_amount"],
                 row["variance_amount"], row["tolerance_amount"]] for sid, row in ship_rows.items()],
               [index for index, row in enumerate(ship_rows.values()) if row["disposition"] == "held"]),
        _table("Observed review branches", ["shipment_id", "disposition", "issue_codes"],
               [[sid, row["disposition"], ", ".join(row["issue_codes"])] for sid, row in ship_rows.items()]),
    ))
    events.append(_event(
        "triage-exceptions", "exception",
        "Assigned synthetic review owners and strict missing-POD grace decisions; no carrier contact or business action occurs.",
        {"queue_items_before_history": len(queue),
         "overdue_shipments": sum(row["pod_overdue"] is True for row in ship_rows.values()),
         "null_prices": sum(row["expected_amount"] is None for row in ship_rows.values())},
        _table("Owned review queue before history", ["shipment_id", "entity_id", "code", "owner", "next_action"],
               [[row[key] for key in ("shipment_id", "entity_id", "code", "owner", "next_action")]
                for row in _ordered_issues(queue)]),
        _table("Missing-POD age decisions", ["shipment_id", "age_seconds", "grace_seconds", "overdue"],
               [[sid, row["missing_pod_age_seconds"], config["missing_pod_grace_hours"] * 3600, row["pod_overdue"]]
                for sid, row in ship_rows.items() if row["missing_pod_age_seconds"] is not None]),
    ))

    case_rows = []
    eligible_cases = Counter(
        (row["shipment_id"], row["issue_code"]) for row in history if _instant(row["updated_at"]) <= cutoff
    )
    for case in history:
        sid, code = case["shipment_id"], case["issue_code"]
        if _instant(case["updated_at"]) > cutoff:
            proposed, reason = "deferred", "future-history"
        elif sid not in shipments:
            proposed, reason = "held", "missing-shipment"
        elif eligible_cases[(sid, code)] > 1:
            proposed, reason = "held", "ambiguous-history"
        elif code not in CASE_CODES:
            proposed, reason = "held", "unsupported-issue"
        else:
            present = _condition(code, ship_rows[sid], sid in usable_pods)
            if present is None:
                proposed, reason = "deferred", "insufficient-evidence"
            elif present:
                proposed = "reopened" if case["state"] == "resolved" else "still-open"
                reason = "condition-present"
            else:
                proposed = "remains-resolved" if case["state"] == "resolved" else "closed"
                reason = "condition-cleared"
        if proposed == "held":
            queue.append(_issue(reason, "case", case["case_id"], sid, case["owner"]))
        case_rows.append({
            "case_id": case["case_id"], "shipment_id": sid, "issue_code": code,
            "previous_state": case["state"], "proposed_state": proposed,
            "owner": case["owner"], "reason": reason,
        })
    events.append(_event(
        "revisit-prior-cases", "decision",
        "Re-evaluated every prior case without editing history; unresolved evidence cannot establish that a variance has cleared.",
        {"prior_cases": len(history),
         "closed_proposals": sum(row["proposed_state"] == "closed" for row in case_rows),
         "reopened_proposals": sum(row["proposed_state"] == "reopened" for row in case_rows),
         "deferred_proposals": sum(row["proposed_state"] == "deferred" for row in case_rows),
         "held_proposals": sum(row["proposed_state"] == "held" for row in case_rows)},
        _table("Proposed prior-case transitions",
               ["case_id", "shipment_id", "issue_code", "previous_state", "proposed_state", "reason"],
               [[row[key] for key in ("case_id", "shipment_id", "issue_code", "previous_state", "proposed_state", "reason")]
                for row in case_rows]),
        _table("History clarification queue", ["case_id", "code", "owner"],
               [[row["entity_id"], row["code"], row["owner"]] for row in _ordered_issues(queue)
                if row["entity_type"] == "case"]),
    ))

    line_rows, output_by_invoice = [], defaultdict(list)
    for line in lines:
        faults = set(line_faults[line["line_id"]])
        faults.update(ship_issues.get(line["shipment_id"], ()))
        faults.update(invoice_faults.get(line["invoice_id"], ()))
        row = dict(line, currency=line_currency[line["line_id"]],
                   disposition="held" if faults else "ready-for-review", issue_codes=sorted(faults))
        line_rows.append(row)
        output_by_invoice[row["invoice_id"]].append(row)

    def comparable_line(row):
        shipment = ship_rows.get(row["shipment_id"])
        return (
            shipment is not None and shipment["variance_amount"] is not None
            and shipment["invoice_ids"] == [row["invoice_id"]]
            and row["invoice_id"] in invoices and row["currency"] == shipment["currency"]
        )

    invoice_rows = []
    for iid, invoice in invoices.items():
        related = output_by_invoice[iid]
        shipment_ids = sorted({row["shipment_id"] for row in related})
        paired = [
            ship_rows[sid] for sid in shipment_ids
            if sid in ship_rows and ship_rows[sid]["variance_amount"] is not None
            and ship_rows[sid]["invoice_ids"] == [iid]
        ]
        billed, computed = _amount_sum(paired, "billed_amount"), _amount_sum(paired, "expected_amount")
        faults = set(invoice_faults[iid])
        for line in related:
            faults.update(line["issue_codes"])
        invoice_rows.append({
            "invoice_id": iid, "currency": invoice["currency"], "shipment_ids": shipment_ids,
            "header_total": invoice["total"], "line_total": _money(invoice_line_totals[iid]),
            "header_matches": Decimal(invoice["total"]) == invoice_line_totals[iid],
            "computable_billed": _money(billed), "known_expected": _money(computed),
            "computable_variance": _money(billed - computed),
            "comparison_complete": bool(related) and not invoice_faults[iid] and all(comparable_line(row) for row in related),
            "ready_line_amount": _money(_amount_sum(row for row in related if row["disposition"] == "ready-for-review")),
            "held_line_amount": _money(_amount_sum(row for row in related if row["disposition"] == "held")),
            "disposition": "held" if faults else "ready-for-review", "issue_codes": sorted(faults),
        })
    currencies = (
        {row["currency"] for row in ship_rows.values()}
        | {row["currency"] for row in invoices.values()}
        | {row["currency"] for row in line_rows}
    )
    currency_rows = []
    for currency in sorted(currencies, key=lambda value: value or ""):
        related = [row for row in line_rows if row["currency"] == currency]
        currency_shipments = [row for row in ship_rows.values() if row["currency"] == currency]
        currency_invoices = [row for row in invoice_rows if row["currency"] == currency]
        paired = [row for row in currency_shipments if row["variance_amount"] is not None]
        billed, computed = _amount_sum(paired, "billed_amount"), _amount_sum(paired, "expected_amount")
        currency_rows.append({
            "currency": currency, "billed_total": _money(_amount_sum(related)),
            "ready_line_amount": _money(_amount_sum(row for row in related if row["disposition"] == "ready-for-review")),
            "held_line_amount": _money(_amount_sum(row for row in related if row["disposition"] == "held")),
            "computable_billed": _money(billed), "known_expected": _money(computed),
            "computable_variance": _money(billed - computed),
            "comparison_complete": (
                currency is not None and len(paired) == len(currency_shipments)
                and all(comparable_line(row) for row in related)
                and all(row["comparison_complete"] for row in currency_invoices)
            ),
        })
    summary = {
        "shipment_count": len(shipments), "invoice_count": len(invoices), "line_count": len(lines),
        "pod_count": len(pods), "rate_count": len(rates), "prior_case_count": len(history),
        "ready_shipments": sum(row["disposition"] == "ready-for-review" for row in ship_rows.values()),
        "held_shipments": sum(row["disposition"] == "held" for row in ship_rows.values()),
        "uncomputed_shipment_ids": [sid for sid, row in ship_rows.items() if row["expected_amount"] is None],
        "noncomparable_shipment_ids": [sid for sid, row in ship_rows.items() if row["variance_amount"] is None],
        "currency_totals": currency_rows,
    }
    result = {
        "schema_version": 1, "status": "completed_with_exceptions" if queue else "completed",
        "outputs": {
            "as_of": _utc(config["as_of"]), "shipments": list(ship_rows.values()),
            "invoices": invoice_rows, "invoice_lines": line_rows,
            "pod_evidence": list(pod_rows.values()), "rate_evidence": list(rate_rows.values()),
            "case_proposals": case_rows, "summary": summary,
        },
        "exceptions": _ordered_issues(queue),
    }
    events.append(_event(
        "emit-review-packet", "output",
        "Emitted every entity and owned issue; currency totals preserve ready/held amounts and compare only paired computed charges.",
        {"status": result["status"], "ready_shipments": summary["ready_shipments"],
         "held_shipments": summary["held_shipments"], "uncomputed_shipments": len(summary["uncomputed_shipment_ids"]),
         "invoices": len(invoice_rows), "queue_items": len(queue)},
        _table("Final currency-isolated review totals",
               ["currency", "billed_total", "ready_lines", "held_lines", "computable_billed", "known_expected"],
               [[row[key] for key in ("currency", "billed_total", "ready_line_amount", "held_line_amount",
                                      "computable_billed", "known_expected")] for row in currency_rows]),
        _table("Final artifact row accounting", ["artifact", "rows"],
               [[key, len(value)] for key, value in result["outputs"].items() if isinstance(value, list)]
               + [["exceptions", len(queue)]]),
    ))
    return result, events


def solve(payload):
    config = payload.get("config") if isinstance(payload, dict) else None
    files = payload.get("files") if isinstance(payload, dict) else None
    owner = config.get("review_owner") if isinstance(config, dict) else None
    owner = owner if _text(owner) else "freight-review"
    inventory = [
        [filename, len(files[filename]) if isinstance(files, dict) and isinstance(files.get(filename), list) else None]
        for filename in SCHEMAS
    ]
    supplied_count = sum(row[1] for row in inventory if row[1] is not None)
    cutoff = config.get("as_of") if isinstance(config, dict) else None
    events = [_event(
        "intake-exports", "input",
        "Inventoried the supplied synthetic attachment; no external files or services were read.",
        {"as_of": cutoff if isinstance(cutoff, str) and len(cutoff) <= 80 else None,
         "logical_arrays": sum(row[1] is not None for row in inventory), "supplied_records": supplied_count,
         "boundary": "synthetic file review only"},
        _table("Logical export inventory", ["export_label", "rows"], inventory),
    )]
    issues = _validate(payload, owner)
    events.append(_event(
        "validate-records", "validation",
        "Rejected malformed records before joining or pricing." if issues else
        "Validated exact schemas, primary IDs, decimal strings, and row-local temporal constraints.",
        {"validation_issues": len(issues), "supplied_records": supplied_count,
         "outcome": "rejected" if issues else "validated"},
        _table("Validation issues", ["location", "code", "message"],
               [[row["entity_id"], row["code"], row["message"]] for row in issues],
               range(len(issues))) if issues else
        _table("Validated export rows", ["export_label", "rows", "schema"],
               [[filename, count, "valid"] for filename, count in inventory]),
    ))
    if issues:
        return {"schema_version": 1, "status": "rejected", "outputs": {}, "exceptions": issues}, events
    with localcontext() as context:
        context.prec = 60
        return _review(files, config, events)


if __name__ == "__main__":
    run_cli(solve, scenario_id="cross-industry-01")
