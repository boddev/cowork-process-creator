"""Read-only synthetic Professional Services billing-draft reconciliation."""
from collections import defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP, localcontext
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "_shared"))
from scenario_support import run_cli


CENT = Decimal("0.01")
ZERO = Decimal("0.00")
SCHEMAS = {
    "projects.json": (("project_id",), {
        "project_id": "id", "client_id": "id", "contract_id": "id",
        "currency": "currency", "period_cap": "money", "owner": "id",
    }),
    "rates.json": (("rate_id",), {
        "rate_id": "id", "project_id": "id", "role_code": "id", "currency": "currency",
        "valid_from": "date", "valid_to": "date", "hourly_rate": "money",
    }),
    "time-entries.json": (("time_id",), {
        "time_id": "id", "project_id": "id", "person_id": "id", "role_code": "id",
        "service_date": "date", "minutes": "integer", "chargeable": "boolean",
    }),
    "expense-entries.json": (("expense_id",), {
        "expense_id": "id", "project_id": "id", "person_id": "id",
        "service_date": "date", "category": "id", "amount": "money",
        "currency": "currency", "receipt_reference": "nullable-id", "chargeable": "boolean",
    }),
    "approval-events.json": (("approval_event_id",), {
        "approval_event_id": "id", "entry_type": "entry-type", "entry_id": "id",
        "revision": "integer", "recorded_at": "instant", "decision": "decision",
    }),
    "billed-transactions.json": (("billed_id",), {
        "billed_id": "id", "entry_type": "entry-type", "entry_id": "id",
        "project_id": "id", "invoice_id": "id", "service_date": "date",
        "amount": "money", "currency": "currency", "billed_at": "instant",
    }),
    "draft-invoices.json": (("draft_id",), {
        "draft_id": "id", "project_id": "id", "currency": "currency",
        "period_start": "date", "period_end": "date", "state": "draft-state",
    }),
    "draft-lines.json": (("line_id",), {
        "line_id": "id", "draft_id": "id", "entry_type": "entry-type",
        "entry_id": "id", "amount": "money",
    }),
    "expense-policies.json": (("category", "currency"), {
        "category": "id", "currency": "currency", "max_amount": "money",
        "receipt_required_at": "money",
    }),
}
CONFIG_FIELDS = {
    "as_of": "instant", "period_start": "date", "period_end": "date",
    "draft_tolerance": "money",
}
MESSAGES = {
    "candidate-time": "Approved time priced at the unique effective rate.",
    "candidate-expense": "Approved expense satisfies currency, cap, and receipt policy.",
    "expense-cap": "Expense exceeds its per-entry policy cap; hold the entire amount.",
    "receipt-required": "Expense meets the inclusive receipt threshold but has no receipt reference.",
    "currency-mismatch": "Expense currency differs from its project currency; hold without conversion.",
    "out-of-period": "Service date is outside the half-open billing period.",
    "nonchargeable": "Entry is explicitly nonchargeable; exclude from new charges.",
    "already-billed": "Entry has a prior as-of billed transaction; exclude the entire entry.",
    "not-approved": "No approval event is available at the cutoff; exclude from new charges.",
    "pending": "Latest as-of approval is pending; exclude from new charges.",
    "rejected": "Latest as-of approval is rejected; exclude from new charges.",
    "recalled": "Latest as-of approval is recalled; exclude from new charges.",
    "contradictory-approval": "Highest as-of approval revision conflicts; clarification is required.",
    "ambiguous-approval": "Highest as-of approval revision is not unique; clarification is required.",
    "missing-project": "Entry has no matching project; amount remains uncomputed.",
    "billed-identity-mismatch": "Prior billing identity conflicts with this entry; clarification is required.",
    "ambiguous-billing": "Multiple as-of billed transactions reference this entry; no partial billing is inferred.",
    "draft-identity-mismatch": "Current draft identity conflicts with this entry; clarification is required.",
    "missing-rate": "No effective project-role-currency rate matches; amount remains uncomputed.",
    "ambiguous-rate": "Multiple effective project-role-currency rates match; amount remains uncomputed.",
    "missing-policy": "No category-currency expense policy matches; amount remains uncomputed.",
    "in-period-prior": "As-of billed amount consumes this project's period cap.",
    "future-billing": "Billing was recorded after the cutoff; ignore it for this snapshot.",
    "prior-out-of-period": "Billed service date is outside this period; it does not consume this period's cap.",
    "prior-project-missing": "Billed transaction has no matching project; its cap contribution is uncomputed.",
    "prior-currency-mismatch": "Billed transaction currency differs from its project; no cap conversion is inferred.",
    "draft-add": "Eligible entry is missing from the active draft.",
    "draft-update": "Draft amount differs from the computed entry amount.",
    "draft-remove": "Draft contains a definitively ineligible entry.",
    "draft-match": "Draft amount matches the computed entry amount.",
    "missing-draft": "No active draft is available; this is a diagnostic candidate only.",
    "duplicate-drafts": "Multiple active drafts reference this project and period; do not choose one.",
    "duplicate-details": "Multiple active draft details reference this entry; do not choose or remove a line.",
    "missing-draft-header": "Draft line has no matching header; clarify its identity instead of removing it.",
    "missing-draft-entry": "Draft line has no matching source entry; absence does not establish ineligibility.",
    "draft-project-missing": "Draft header has no matching project; clarify the export.",
    "draft-currency-mismatch": "Draft currency differs from its project currency; no conversion is inferred.",
    "draft-out-of-period": "Draft belongs to another service period; defer it without changes.",
    "project-cap": "Prior billed plus new candidate charges exceed the project period cap; hold all new candidate charges.",
}


def _instant(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _valid(value, kind):
    if kind == "nullable-id" and value is None:
        return True
    if kind in ("id", "nullable-id"):
        return isinstance(value, str) and bool(value) and value.strip() == value
    if kind == "boolean":
        return type(value) is bool
    if kind == "integer":
        return type(value) is int and value > 0
    if not isinstance(value, str):
        return False
    if kind == "money":
        return re.fullmatch(r"(?:0|[1-9][0-9]*)\.[0-9]{2}", value) is not None
    if kind == "currency":
        return re.fullmatch(r"[A-Z]{3}", value) is not None
    if kind == "date":
        try:
            return re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value) is not None and date.fromisoformat(value).isoformat() == value
        except ValueError:
            return False
    if kind == "instant":
        if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(Z|[+-][0-9]{2}:[0-9]{2})", value):
            return False
        try:
            if value[-1] != "Z" and (int(value[-5:-3]) > 23 or int(value[-2:]) > 59):
                return False
            _instant(value)
            return True
        except (ValueError, OverflowError):
            return False
    enums = {
        "entry-type": ("time", "expense"),
        "decision": ("approved", "pending", "rejected", "recalled"),
        "draft-state": ("draft",),
    }
    return value in enums[kind]


def _object_fields(value, names, label, issues):
    if not isinstance(value, dict):
        issues.append(("invalid-schema", f"{label} must be an object."))
        return False
    missing = sorted(set(names) - value.keys())
    extra = sorted(set(value) - set(names), key=str)
    if missing:
        issues.append(("invalid-schema", f"{label} is missing fields: {', '.join(missing)}."))
    if extra:
        issues.append(("invalid-schema", f"{label} has unsupported fields: {', '.join(map(str, extra))}."))
    return True


def _validate_fields(row, fields, label, issues):
    if not _object_fields(row, fields, label, issues):
        return
    descriptions = {
        "id": ("invalid-id", "a nonempty trimmed string"),
        "nullable-id": ("invalid-id", "a nonempty trimmed string or null"),
        "money": ("invalid-amount", "a nonnegative fixed-two-decimal string"),
        "integer": ("invalid-integer", "a positive JSON integer, not a boolean"),
        "boolean": ("invalid-boolean", "a JSON boolean"),
        "currency": ("invalid-currency", "three uppercase ASCII letters"),
        "date": ("invalid-date", "a canonical valid YYYY-MM-DD date"),
        "instant": ("invalid-instant", "a whole-second ISO timestamp with an explicit valid offset"),
        "entry-type": ("invalid-enum", "time or expense"),
        "decision": ("invalid-enum", "approved, pending, rejected, or recalled"),
        "draft-state": ("invalid-enum", "draft"),
    }
    for field, kind in fields.items():
        if field in row and not _valid(row[field], kind):
            code, description = descriptions[kind]
            issues.append((code, f"{label}.{field} must be {description}."))
    for start, end in (("period_start", "period_end"), ("valid_from", "valid_to")):
        if start in fields and all(_valid(row.get(key), "date") for key in (start, end)):
            if row[start] >= row[end]:
                issues.append(("invalid-interval", f"{label}.{end} must be later than {start}."))


def _validate(payload):
    issues = []
    if not _object_fields(payload, ("config", "files"), "input", issues):
        return issues
    if "config" in payload:
        _validate_fields(payload["config"], CONFIG_FIELDS, "config", issues)
        config = payload["config"]
        if isinstance(config, dict) and _valid(config.get("draft_tolerance"), "money"):
            if config["draft_tolerance"] != "0.00":
                issues.append(("unsupported-tolerance", 'config.draft_tolerance must be "0.00".'))
    files = payload.get("files")
    if not _object_fields(files, SCHEMAS, "files", issues):
        return issues
    for filename, (keys, fields) in SCHEMAS.items():
        if filename not in files:
            continue
        rows = files[filename]
        if not isinstance(rows, list):
            issues.append(("invalid-schema", f"{filename} must be an array."))
            continue
        seen, duplicates = set(), set()
        for row in rows:
            valid_key = isinstance(row, dict) and all(_valid(row.get(key), fields[key]) for key in keys)
            identity = tuple(row[key] for key in keys) if valid_key else None
            label = f"{filename}[{'/'.join(identity) if identity else 'invalid-key'}]"
            _validate_fields(row, fields, label, issues)
            if identity is not None:
                if identity in seen:
                    duplicates.add(identity)
                seen.add(identity)
        for identity in sorted(duplicates):
            issues.append(("duplicate-id", f"Duplicate primary key in {filename}: {'/'.join(identity)}."))
    return sorted(issues)


def _money(value):
    rounded = value.quantize(CENT, rounding=ROUND_HALF_UP)
    return "0.00" if rounded == 0 else format(rounded, ".2f")


def _sum(rows, field):
    return sum((Decimal(row[field]) for row in rows if row[field] is not None), ZERO)


def _key(row):
    return row["entry_type"], row["entry_id"]


def _group(rows, key):
    grouped = defaultdict(list)
    for row in rows:
        grouped[key(row)].append(row)
    return grouped


def _cell(value):
    if isinstance(value, str) and len(value) > 96:
        return value[:93] + "..."
    return value


def _table(title, columns, rows, highlights=()):
    return {
        "title": title + (" (first 8 rows)" if len(rows) > 8 else ""),
        "columns": columns,
        "rows": [[_cell(value) for value in row] for row in rows[:8]],
        "total_rows": len(rows),
        "highlight_rows": [index for index in highlights if index < min(8, len(rows))],
    }


def _event(step_id, kind, caption, facts, *tables):
    return {"step_id": step_id, "kind": kind, "caption": caption, "facts": facts, "tables": list(tables)}


def _exception(code, message, *, project_id=None, entry_type=None, entry_id=None,
               draft_id=None, line_id=None, owner="data-steward",
               action="clarify-evidence", diagnostic_only=True):
    return {
        "code": code, "message": message, "owner": owner, "project_id": project_id,
        "entry_type": entry_type, "entry_id": entry_id, "draft_id": draft_id,
        "line_id": line_id, "action": action, "diagnostic_only": diagnostic_only,
    }


def _exception_key(row):
    return tuple(row[field] or "" for field in (
        "project_id", "entry_type", "entry_id", "draft_id", "line_id", "code", "message",
    ))


def _intake(payload):
    config = payload.get("config", {}) if isinstance(payload, dict) else {}
    config = config if isinstance(config, dict) else {}
    files = payload.get("files", {}) if isinstance(payload, dict) else {}
    files = files if isinstance(files, dict) else {}
    rows = [[name, len(value) if isinstance(value, list) else None] for name, value in sorted(files.items(), key=lambda item: str(item[0]))]
    return _event(
        "intake-billing-exports", "input", "Inventory the supplied synthetic exports and frozen service period; no other files or systems are read.",
        {"logical_exports": len(files), "as_of": _cell(config.get("as_of")) if isinstance(config.get("as_of"), str) else None,
         "period_start": config.get("period_start") if isinstance(config.get("period_start"), str) else None,
         "period_end": config.get("period_end") if isinstance(config.get("period_end"), str) else None},
        _table("Supplied logical exports", ["export", "rows"], rows),
    )


def solve(payload):
    events = [_intake(payload)]
    issues = _validate(payload)
    if issues:
        exceptions = [_exception(code, message, owner="input-provider", action="fix-input") for code, message in issues]
        exceptions.sort(key=_exception_key)
        events.append(_event(
            "validate-billing-data", "validation", "Reject the entire malformed business bundle before joining or computing charges.",
            {"valid": False, "errors": len(issues), "business_outputs": 0},
            _table("Offending fields", ["code", "message"], [[item["code"], item["message"]] for item in exceptions], range(len(issues))),
        ))
        return {"schema_version": 1, "status": "rejected", "outputs": {}, "exceptions": exceptions}, events
    files = payload["files"]
    events.append(_event(
        "validate-billing-data", "validation", "All nine export schemas, types, intervals and primary keys passed validation.",
        {"valid": True, "records": sum(map(len, files.values())), "duplicate_primary_keys": 0, "tolerance": payload["config"]["draft_tolerance"]},
        _table("Validated exports", ["export", "validated_rows"], [[name, len(files[name])] for name in sorted(files)]),
    ))
    money_digits = max([1] + [
        len(row[field]) for filename, (_, fields) in SCHEMAS.items()
        for row in files[filename] for field, kind in fields.items() if kind == "money"
    ])
    minute_digits = max([1] + [len(str(row["minutes"])) for row in files["time-entries.json"]])
    # Keep exact large input amounts and per-entry division well above the cent boundary.
    with localcontext() as context:
        context.prec = max(28, money_digits + minute_digits + len(str(sum(map(len, files.values())))) + 16)
        return _reconcile(payload, events)


def _reconcile(payload, events):
    files, config = payload["files"], payload["config"]
    cutoff = _instant(config["as_of"])
    start, end = config["period_start"], config["period_end"]
    projects = {row["project_id"]: row for row in files["projects.json"]}
    raw_entries = {
        (entry_type, row[id_field]): row
        for entry_type, filename, id_field in (
            ("expense", "expense-entries.json", "expense_id"),
            ("time", "time-entries.json", "time_id"),
        )
        for row in files[filename]
    }
    rates = sorted(files["rates.json"], key=lambda row: row["rate_id"])
    policies = {(row["category"], row["currency"]): row for row in files["expense-policies.json"]}
    approvals = _group(sorted(files["approval-events.json"], key=lambda row: row["approval_event_id"]), _key)
    billed = sorted(files["billed-transactions.json"], key=lambda row: row["billed_id"])
    posted = _group([row for row in billed if _instant(row["billed_at"]) <= cutoff], _key)
    headers = {row["draft_id"]: row for row in files["draft-invoices.json"]}
    lines = sorted(files["draft-lines.json"], key=lambda row: row["line_id"])
    lines_by_draft = _group(lines, lambda row: row["draft_id"])
    active = {draft_id for draft_id, row in headers.items() if (row["period_start"], row["period_end"]) == (start, end)}
    active_by_project = _group([headers[draft_id] for draft_id in sorted(active)], lambda row: row["project_id"])
    current_lines = _group([row for row in lines if row["draft_id"] in active or row["draft_id"] not in headers], _key)
    exceptions = []

    def owner(project_id):
        return projects.get(project_id, {}).get("owner", "data-steward")

    def issue(code, project_id=None, **fields):
        exceptions.append(_exception(code, MESSAGES[code], project_id=project_id, owner=owner(project_id), **fields))

    def effective_rates(raw):
        project = projects.get(raw["project_id"])
        return [
            row for row in rates
            if project is not None and row["project_id"] == raw["project_id"]
            and row["role_code"] == raw["role_code"] and row["currency"] == project["currency"]
            and row["valid_from"] <= raw["service_date"] < row["valid_to"]
        ]

    header_reasons = {}
    for draft_id in sorted(headers):
        header = headers[draft_id]
        project = projects.get(header["project_id"])
        if draft_id not in active:
            reason = "draft-out-of-period"
        elif project is None:
            reason = "draft-project-missing"
        elif header["currency"] != project["currency"]:
            reason = "draft-currency-mismatch"
        elif len(active_by_project[header["project_id"]]) > 1:
            reason = "duplicate-drafts"
        else:
            reason = None
        header_reasons[draft_id] = reason
        if reason:
            issue(reason, header["project_id"], draft_id=draft_id,
                  action="review-export" if reason == "draft-out-of-period" else "clarify-not-remove")

    selected, future, matched_rates, join_rows = {}, {}, {}, []
    for identity, raw in sorted(raw_entries.items()):
        entry_type, entry_id = identity
        available = [row for row in approvals[identity] if _instant(row["recorded_at"]) <= cutoff]
        revision = max((row["revision"] for row in available), default=None)
        selected[identity] = [row for row in available if row["revision"] == revision]
        future[identity] = [row["approval_event_id"] for row in approvals[identity] if _instant(row["recorded_at"]) > cutoff]
        matched_rates[identity] = effective_rates(raw) if entry_type == "time" else []
        join_rows.append([
            f"{entry_type}:{entry_id}", raw["project_id"] if raw["project_id"] in projects else None,
            ",".join(row["approval_event_id"] for row in selected[identity]) or None,
            len(posted[identity]), len(current_lines[identity]),
            len(matched_rates[identity]) if entry_type == "time" else None,
        ])
    events.append(_event(
        "join-billing-evidence", "join", "Join current entries to projects, as-of approval revisions, raw prior billing and current draft details.",
        {"entries": len(raw_entries), "projects": len(projects),
         "matched_projects": sum(row[1] is not None for row in join_rows),
         "prior_rows": len(billed), "source_absent_prior": sum(_key(row) not in raw_entries for row in billed)},
        _table("Actual evidence joins", ["entry", "project", "approval_ids", "prior_rows", "active_lines", "rate_matches"], join_rows),
    ))

    prior_billing = []
    for row in billed:
        project = projects.get(row["project_id"])
        if _instant(row["billed_at"]) > cutoff:
            disposition, reason, cap_amount = "future-ignored", "future-billing", "0.00"
        elif project is None:
            disposition, reason, cap_amount = "quarantined", "prior-project-missing", None
        elif row["currency"] != project["currency"]:
            disposition, reason, cap_amount = "quarantined", "prior-currency-mismatch", None
        elif not start <= row["service_date"] < end:
            disposition, reason, cap_amount = "out-of-period", "prior-out-of-period", "0.00"
        else:
            disposition, reason, cap_amount = "counted", "in-period-prior", row["amount"]
        prior_billing.append({
            "billed_id": row["billed_id"], "entry_type": row["entry_type"], "entry_id": row["entry_id"],
            "project_id": row["project_id"], "currency": row["currency"], "amount": row["amount"],
            "source_present": _key(row) in raw_entries, "cap_amount": cap_amount,
            "disposition": disposition, "reason": reason, "message": MESSAGES[reason],
        })
        if disposition == "quarantined":
            exceptions.append(_exception(
                reason, MESSAGES[reason] + f" Billed row {row['billed_id']}.",
                project_id=row["project_id"], entry_type=row["entry_type"], entry_id=row["entry_id"],
                owner=owner(row["project_id"]),
            ))
    for row in files["approval-events.json"]:
        if _instant(row["recorded_at"]) <= cutoff and _key(row) not in raw_entries:
            exceptions.append(_exception(
                "orphan-approval", f"Approval event {row['approval_event_id']} has no matching current entry.",
                entry_type=row["entry_type"], entry_id=row["entry_id"], action="review-export",
            ))
    for row in rates:
        if row["project_id"] not in projects:
            exceptions.append(_exception(
                "orphan-rate", f"Rate {row['rate_id']} has no matching project.",
                project_id=row["project_id"], action="review-export",
            ))

    entries = []
    for identity, raw in sorted(raw_entries.items()):
        entry_type, entry_id = identity
        project = projects.get(raw["project_id"])
        currency = raw["currency"] if entry_type == "expense" else project["currency"] if project else None
        top = selected[identity]
        reason, status, amount, rate_id, policy_key = None, "quarantined", None, None, None
        billed_conflict = any(
            row["project_id"] != raw["project_id"] or row["currency"] != currency
            or row["service_date"] != raw["service_date"]
            for row in posted[identity]
        )
        draft_conflict = any(
            line["draft_id"] in headers and (
                headers[line["draft_id"]]["project_id"] != raw["project_id"]
                or headers[line["draft_id"]]["currency"] != currency
            )
            for line in current_lines[identity]
        )
        if project is None:
            reason = "missing-project"
        elif entry_type == "expense" and currency != project["currency"]:
            reason = "currency-mismatch"
        elif billed_conflict:
            reason = "billed-identity-mismatch"
        elif len(posted[identity]) > 1:
            reason = "ambiguous-billing"
        elif draft_conflict:
            reason = "draft-identity-mismatch"
        elif len(top) > 1:
            reason = "contradictory-approval" if len({row["decision"] for row in top}) > 1 else "ambiguous-approval"
        elif not start <= raw["service_date"] < end:
            reason, status, amount = "out-of-period", "excluded", "0.00"
        elif not raw["chargeable"]:
            reason, status, amount = "nonchargeable", "excluded", "0.00"
        elif posted[identity]:
            reason, status, amount = "already-billed", "excluded", "0.00"
        elif not top or top[0]["decision"] != "approved":
            reason = top[0]["decision"] if top else "not-approved"
            status, amount = "excluded", "0.00"
        elif entry_type == "time":
            matches = matched_rates[identity]
            if len(matches) != 1:
                reason = "missing-rate" if not matches else "ambiguous-rate"
            else:
                rate_id = matches[0]["rate_id"]
                amount = _money(Decimal(raw["minutes"]) * Decimal(matches[0]["hourly_rate"]) / Decimal(60))
                reason, status = "candidate-time", "candidate"
        else:
            policy = policies.get((raw["category"], currency))
            if policy is None:
                reason = "missing-policy"
            else:
                policy_key = f"{raw['category']}/{currency}"
                if Decimal(raw["amount"]) > Decimal(policy["max_amount"]):
                    reason, status, amount = "expense-cap", "held", "0.00"
                elif Decimal(raw["amount"]) >= Decimal(policy["receipt_required_at"]) and raw["receipt_reference"] is None:
                    reason, status, amount = "receipt-required", "held", "0.00"
                else:
                    reason, status, amount = "candidate-expense", "candidate", raw["amount"]
        entry = {
            "entry_type": entry_type, "entry_id": entry_id, "project_id": raw["project_id"], "currency": currency,
            "approval_revision": top[0]["revision"] if top else None,
            "approval_event_ids": [row["approval_event_id"] for row in top],
            "future_approval_event_ids": future[identity], "rate_id": rate_id, "policy_key": policy_key,
            "billed_ids": [row["billed_id"] for row in posted[identity]],
            "status": status, "reason": reason, "message": MESSAGES[reason], "expected_amount": amount,
            "held_amount": raw["amount"] if entry_type == "expense" and status in ("held", "quarantined") else None,
            "cap_held": False,
        }
        entries.append(entry)
        if status in ("held", "quarantined"):
            issue(reason, raw["project_id"], entry_type=entry_type, entry_id=entry_id,
                  action="hold-entry" if status == "held" else "clarify-evidence")
    entry_map = {_key(row): row for row in entries}
    events.append(_event(
        "resolve-entry-eligibility", "decision", "Resolve unique highest as-of revisions and explicit exclusions; contradictions are never turned into removal decisions.",
        {"entries": len(entries), "excluded": sum(row["status"] == "excluded" for row in entries),
         "uncomputed": sum(row["expected_amount"] is None for row in entries),
         "future_approvals_ignored": sum(map(len, future.values()))},
        _table("Actual revision and eligibility outcomes", ["entry", "revision", "event_ids", "future_events", "status", "reason"], [
            [f"{row['entry_type']}:{row['entry_id']}", row["approval_revision"], ",".join(row["approval_event_ids"]) or None,
             len(row["future_approval_event_ids"]), row["status"], row["reason"]] for row in entries
        ], [index for index, row in enumerate(entries) if row["status"] != "candidate"]),
    ))
    time_rows, expense_rows = [], []
    for row in entries:
        raw = raw_entries[_key(row)]
        if row["entry_type"] == "time":
            matches = matched_rates[_key(row)]
            time_rows.append([row["entry_id"], raw["minutes"], row["rate_id"],
                              matches[0]["hourly_rate"] if row["rate_id"] else None,
                              row["expected_amount"], row["status"]])
        else:
            policy = policies.get((raw["category"], raw["currency"])) if row["policy_key"] else None
            expense_rows.append([row["entry_id"], raw["amount"],
                                 policy["max_amount"] if policy else None,
                                 policy["receipt_required_at"] if policy else None,
                                 raw["receipt_reference"] is not None, row["status"]])
    events.append(_event(
        "price-candidate-entries", "decision", "Price time half-up per entry; enforce whole-expense caps and inclusive receipt thresholds without FX or truncation.",
        {"time_entries": len(time_rows), "expense_entries": len(expense_rows),
         "candidates": sum(row["status"] == "candidate" for row in entries),
         "policy_holds": sum(row["status"] == "held" for row in entries)},
        _table("Time pricing", ["entry_id", "minutes", "rate_id", "hourly_rate", "amount", "status"], time_rows),
        _table("Expense evidence", ["entry_id", "amount", "cap", "receipt_at", "receipt", "status"], expense_rows),
    ))

    details = []

    def detail(draft_id, line_id, identity, raw_amount, reason, action, amount=None):
        header, entry = headers.get(draft_id), entry_map.get(identity)
        return {
            "draft_id": draft_id, "line_id": line_id,
            "project_id": header["project_id"] if header else entry["project_id"] if entry else None,
            "currency": header["currency"] if header else entry["currency"] if entry and line_id is None else None,
            "entry_type": identity[0], "entry_id": identity[1], "draft_amount": raw_amount,
            "expected_amount": amount,
            "delta": _money(Decimal(amount) - (Decimal(raw_amount) if raw_amount is not None else ZERO)) if amount is not None else None,
            "action": action, "diagnostic_only": action in ("clarify-not-remove", "defer") or draft_id is None,
            "reason": reason, "message": MESSAGES[reason],
        }

    for line in lines:
        identity, draft_id = _key(line), line["draft_id"]
        entry, header = entry_map.get(identity), headers.get(draft_id)
        amount, action = None, "clarify-not-remove"
        if header is None:
            reason = "missing-draft-header"
        elif draft_id not in active:
            reason, action = "draft-out-of-period", "defer"
        elif header_reasons[draft_id]:
            reason = header_reasons[draft_id]
        elif entry is None:
            reason = "missing-draft-entry"
        elif entry["expected_amount"] is None:
            reason = entry["reason"]
        elif len(current_lines[identity]) > 1:
            reason = "duplicate-details"
        else:
            amount = entry["expected_amount"]
            if entry["status"] != "candidate":
                reason, action = "draft-remove", "remove"
            elif Decimal(line["amount"]) == Decimal(amount):
                reason, action = "draft-match", "match"
            else:
                reason, action = "draft-update", "update"
        details.append(detail(draft_id, line["line_id"], identity, line["amount"], reason, action, amount))
    for entry in entries:
        identity = _key(entry)
        if entry["status"] != "candidate" or current_lines[identity]:
            continue
        candidates = active_by_project[entry["project_id"]]
        if not candidates:
            details.append(detail(None, None, identity, None, "missing-draft", "add", entry["expected_amount"]))
        elif len(candidates) > 1:
            details.append(detail(None, None, identity, None, "duplicate-drafts", "clarify-not-remove"))
        else:
            draft_id = candidates[0]["draft_id"]
            reason = header_reasons[draft_id]
            details.append(detail(
                draft_id, None, identity, None, reason or "draft-add",
                "clarify-not-remove" if reason else "add", None if reason else entry["expected_amount"],
            ))
    details.sort(key=lambda row: tuple(row[field] or "" for field in ("draft_id", "entry_type", "entry_id", "line_id")))
    events.append(_event(
        "compare-draft-details", "decision", "Compare actual draft lines and missing candidates before project cap gating; ambiguous evidence stays uncomputed.",
        {"actual_lines": len(lines), "comparison_rows": len(details),
         "nonmatch_rows": sum(row["action"] != "match" for row in details),
         "uncomputed_rows": sum(row["expected_amount"] is None for row in details)},
        _table("Actual detail comparisons", ["draft", "entry", "draft_amount", "computed_amount", "delta", "action"], [
            [row["draft_id"], f"{row['entry_type']}:{row['entry_id']}", row["draft_amount"],
             row["expected_amount"], row["delta"], row["action"]] for row in details
        ], [index for index, row in enumerate(details) if row["action"] != "match"]),
    ))

    project_rows = []
    raw_billed = {row["billed_id"]: row for row in billed}
    for project_id, project in sorted(projects.items()):
        project_entries = [row for row in entries if row["project_id"] == project_id]
        prior_rows = [row for row in prior_billing if row["project_id"] == project_id]
        candidates = [row for row in project_entries if row["status"] == "candidate"]
        new_amount = _sum(candidates, "expected_amount")
        prior_amount = _sum(prior_rows, "cap_amount")
        known = new_amount + prior_amount
        complete = all(row["expected_amount"] is not None for row in project_entries) and not any(
            row["cap_amount"] is None and start <= raw_billed[row["billed_id"]]["service_date"] < end
            for row in prior_rows
        )
        hold = known > Decimal(project["period_cap"])
        project_rows.append({
            "project_id": project_id, "currency": project["currency"], "owner": project["owner"],
            "entry_count": len(project_entries), "eligible_new_amount": _money(new_amount),
            "prior_billed_amount": _money(prior_amount), "period_cap": project["period_cap"],
            "known_consumption": _money(known), "proposed_consumption": _money(known) if complete else None,
            "cap_overage": _money(known - Decimal(project["period_cap"])) if hold else "0.00" if complete else None,
            "cap_hold": hold, "cap_held_amount": _money(new_amount) if hold else "0.00",
            "reviewable_new_amount": "0.00" if hold else _money(new_amount), "calculation_complete": complete,
            "draft_ids": sorted(row["draft_id"] for row in headers.values() if row["project_id"] == project_id),
        })
        if hold:
            issue("project-cap", project_id, action="hold-project")
            for entry in candidates:
                entry["cap_held"] = True
            for row in details:
                if row["project_id"] == project_id:
                    row["diagnostic_only"] = True
    project_map = {row["project_id"]: row for row in project_rows}
    events.append(_event(
        "check-project-caps", "decision", "Add raw as-of period billing to rounded candidates; equality is allowed and proven excess holds the whole project's new candidates.",
        {"projects": len(project_rows), "cap_held_projects": sum(row["cap_hold"] for row in project_rows),
         "incomplete_projects": sum(not row["calculation_complete"] for row in project_rows),
         "counted_prior_rows": sum(row["disposition"] == "counted" for row in prior_billing)},
        _table("Project cap arithmetic", ["project", "currency", "prior", "new", "cap", "overage"], [
            [row["project_id"], row["currency"], row["prior_billed_amount"], row["eligible_new_amount"],
             row["period_cap"], row["cap_overage"]] for row in project_rows
        ], [index for index, row in enumerate(project_rows) if row["cap_hold"]]),
        _table("Raw ledger cap contributions", ["billed_id", "source_present", "currency", "amount", "cap_amount", "disposition"], [
            [row["billed_id"], row["source_present"], row["currency"], row["amount"], row["cap_amount"], row["disposition"]]
            for row in prior_billing
        ]),
    ))

    draft_rows = []
    for draft_id, header in sorted(headers.items()):
        draft_details = [row for row in details if row["draft_id"] == draft_id]
        comparable = [row for row in draft_details if row["expected_amount"] is not None]
        raw_total = _sum(lines_by_draft[draft_id], "amount")
        comp_total = _sum(comparable, "draft_amount")
        charge_total = _sum(comparable, "expected_amount")
        project = project_map.get(header["project_id"])
        complete = (
            header_reasons[draft_id] is None and project is not None and project["calculation_complete"]
            and len(comparable) == len(draft_details)
        )
        if draft_id not in active:
            status = "deferred"
        elif project is not None and project["cap_hold"]:
            status = "held"
        elif not complete:
            status = "clarification"
        elif any(row["action"] != "match" for row in draft_details):
            status = "corrections"
        else:
            status = "reconciled"
        draft_rows.append({
            "draft_id": draft_id, "project_id": header["project_id"], "currency": header["currency"],
            "status": status, "line_count": len(lines_by_draft[draft_id]),
            "draft_amount": _money(raw_total), "computable_draft_amount": _money(comp_total),
            "quarantined_draft_amount": _money(raw_total - comp_total),
            "computable_expected_amount": _money(charge_total),
            "expected_amount": _money(charge_total) if complete else None,
            "variance": _money(charge_total - raw_total) if complete else None,
            "comparison_complete": bool(complete),
        })
    for row in details:
        if row["action"] == "match":
            continue
        action = "review-" + row["action"] if row["action"] in ("add", "update", "remove") else (
            "review-export" if row["action"] == "defer" else "clarify-not-remove"
        )
        issue(row["reason"], row["project_id"], entry_type=row["entry_type"], entry_id=row["entry_id"],
              draft_id=row["draft_id"], line_id=row["line_id"], action=action, diagnostic_only=row["diagnostic_only"])
    exceptions.sort(key=_exception_key)
    events.append(_event(
        "triage-billing-exceptions", "exception", "Assign actual entry holds, project holds and draft correction or clarification items to human reviewers; no financial action is taken.",
        {"exceptions": len(exceptions), "diagnostic_only": sum(row["diagnostic_only"] for row in exceptions),
         "clarifications": sum(row["action"] in ("clarify-not-remove", "clarify-evidence") for row in exceptions)},
        _table("Owned review packet", ["project", "entry", "draft", "owner", "action", "reason"], [
            [row["project_id"], row["entry_id"], row["draft_id"], row["owner"], row["action"], row["code"]]
            for row in exceptions
        ], range(len(exceptions))),
    ))

    currencies = sorted({
        row["currency"] for rows in (entries, prior_billing, project_rows, draft_rows, details)
        for row in rows if row["currency"] is not None
    })
    currency_rows = []
    for currency in currencies:
        currency_entries = [row for row in entries if row["currency"] == currency]
        currency_projects = [row for row in project_rows if row["currency"] == currency]
        currency_prior = [row for row in prior_billing if row["currency"] == currency]
        currency_drafts = [row for row in draft_rows if row["currency"] == currency]
        currency_details = [row for row in details if row["currency"] == currency]
        comparable = [row for row in currency_details if row["expected_amount"] is not None]
        comp_draft = _sum(comparable, "draft_amount")
        comp_charge = _sum(comparable, "expected_amount")
        raw_total = _sum(currency_details, "draft_amount")
        uncomputed = sum(row["expected_amount"] is None for row in currency_entries)
        unknown_currency_links = any(
            row["currency"] is None and (
                entry_map.get(_key(row), {}).get("currency") == currency
                or projects.get(row["project_id"], {}).get("currency") == currency
            )
            for row in details
        )
        complete = (
            uncomputed == 0 and all(row["calculation_complete"] for row in currency_projects)
            and all(row["comparison_complete"] for row in currency_drafts)
            and all(row["cap_amount"] is not None for row in currency_prior)
            and all(row["draft_id"] in headers and row["action"] not in ("clarify-not-remove", "defer") for row in currency_details)
            and not unknown_currency_links
        )
        currency_rows.append({
            "currency": currency,
            "eligible_new_amount": _money(_sum([row for row in currency_entries if row["status"] == "candidate"], "expected_amount")),
            "prior_billed_amount": _money(_sum(currency_prior, "cap_amount")),
            "cap_held_amount": _money(_sum(currency_projects, "cap_held_amount")),
            "reviewable_new_amount": _money(_sum(currency_projects, "reviewable_new_amount")),
            "known_entry_hold_amount": _money(_sum(currency_entries, "held_amount")),
            "uncomputed_entry_count": uncomputed, "draft_amount": _money(raw_total),
            "computable_draft_amount": _money(comp_draft), "quarantined_draft_amount": _money(raw_total - comp_draft),
            "computable_expected_amount": _money(comp_charge),
            "computable_variance": _money(comp_charge - comp_draft), "comparison_complete": complete,
        })
    status = "completed_with_exceptions" if exceptions else "completed"
    outputs = {
        "snapshot": {"as_of": cutoff.isoformat(timespec="seconds").replace("+00:00", "Z"),
                     "period_start": start, "period_end": end, "review_only": True},
        "entries": entries, "prior_billing": prior_billing, "draft_details": details,
        "drafts": draft_rows, "projects": project_rows, "currency_totals": currency_rows,
        "closure": {"entry_count": len(entries), "draft_count": len(draft_rows),
                    "project_count": len(project_rows), "prior_billing_count": len(prior_billing),
                    "diagnostic_count": sum(row["action"] != "match" for row in details),
                    "exception_count": len(exceptions)},
    }
    events.append(_event(
        "emit-billing-review", "output", "Emit the complete synthetic review-only packet with separate currency subtotals, explicit null comparisons and no invoice or posting actions.",
        {"entries": len(entries), "drafts": len(draft_rows), "projects": len(project_rows),
         "currencies": len(currency_rows), "exceptions": len(exceptions), "status": status},
        _table("Final currency-separated facts", ["currency", "candidates", "cap_held", "reviewable", "raw_draft", "complete"], [
            [row["currency"], row["eligible_new_amount"], row["cap_held_amount"], row["reviewable_new_amount"],
             row["draft_amount"], row["comparison_complete"]] for row in currency_rows
        ]),
    ))
    return {"schema_version": 1, "status": status, "outputs": outputs, "exceptions": exceptions}, events


if __name__ == "__main__":
    run_cli(solve, scenario_id="cross-industry-03")
