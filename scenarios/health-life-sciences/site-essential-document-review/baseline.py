"""Deterministic synthetic administrative document review; no live actions."""

import json
import re
import sys
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "_shared"))
from scenario_support import run_cli


REASONS = (
    "conflict",
    "missing-document",
    "unavailable-evidence",
    "missing-signature-evidence",
    "protocol-version-mismatch",
    "missing-expiry-evidence",
    "expired",
    "expiring-soon",
)
REASON_RANK = {reason: index for index, reason in enumerate(REASONS)}
CHRONOLOGY = (
    "issued-after-effective",
    "recorded-before-issued",
    "expiry-before-issued",
    "expiry-before-effective",
)
SCOPE_NOTICE = (
    "Administrative export completeness only; qualified reviewer owns disposition. "
    "No authenticity, site activation, ethics, enrollment, or compliance determination."
)
TABLE_KEYS = {
    "trials": "trial_id",
    "sites": "site_id",
    "requirements": "requirement_id",
    "documents": "document_id",
    "artifacts": "artifact_id",
    "open_review_tasks": "task_id",
}
SCHEMAS = {
    "trials": {"trial_id": "id", "required_protocol_version": "version"},
    "sites": {
        "site_id": "id", "trial_id": "id", "site_kind": "code",
        "owner_role_id": "id", "in_scope": "bool",
    },
    "requirements": {
        "requirement_id": "id", "site_kind": "code", "document_type": "code",
        "match_protocol_version": "bool", "signature_required": "bool",
        "expiry_required": "bool", "refresh_days": "refresh?",
    },
    "documents": {
        "document_id": "id", "site_id": "id", "document_type": "code",
        "version_seq": "version", "protocol_version": "version?",
        "issued_on": "date", "effective_on": "date", "recorded_on": "date",
        "expires_on": "date?", "artifact_id": "id", "signature_recorded": "bool",
    },
    "artifacts": {
        "artifact_id": "id", "export_available": "bool",
        "readability_attested": "bool", "source_ref": "id",
    },
    "open_review_tasks": {
        "task_id": "id", "site_id": "id", "requirement_id": "id",
        "reason_code": "reason", "opened_on": "date",
    },
}
POLICY_SCHEMA = {
    "policy_id": "id",
    "warning_days": (0, 365),
    "draft_review_days": (0, 365),
    "max_rows_per_table": (1, 1000),
    "max_total_rows": (1, 5000),
    "max_derived_pairs": (1, 10000),
}
MESSAGES = {
    "duplicate-evidence": "Identical export rows were collapsed.",
    "conflicting-evidence": "Conflicting values share a record ID; no arbitrary variant was chosen.",
    "impossible-chronology": "Document date order is impossible; eligible dependent requirements are quarantined.",
    "unmatched-reference": "A referenced export record is absent.",
    "missing-requirements": "In-scope site has no applicable configured requirement.",
    "requirement-review": "Configured administrative evidence needs qualified review.",
    "duplicate-open-tasks": "Multiple existing tasks match one review key; no new task was drafted.",
    "unmatched-task": "As-of task does not match a current requirement reason.",
}


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def _error(errors, path, message):
    errors.append({"code": "invalid-input", "path": path, "message": message})


def _fields(value, schema, path, errors):
    if not isinstance(value, dict) or set(value) != set(schema):
        _error(errors, path, "Fields must be exactly: " + ", ".join(sorted(schema)) + ".")
        return False
    return True


def _integer(value, lower, upper, path, errors):
    if type(value) is not int or not lower <= value <= upper:
        _error(errors, path, f"Expected an integer from {lower} through {upper} (not boolean).")


def _field(value, kind, path, errors):
    if isinstance(kind, tuple):
        _integer(value, *kind, path, errors)
        return
    if kind.endswith("?"):
        if value is None:
            return
        kind = kind[:-1]
    if kind == "id":
        if not isinstance(value, str) or len(value) > 64 or not re.fullmatch(r"SYN-[A-Z0-9]+(?:-[A-Z0-9]+)*", value):
            _error(errors, path, "Expected a synthetic SYN- identifier (at most 64 characters).")
    elif kind == "code":
        if not isinstance(value, str) or not re.fullmatch(r"[a-z][a-z0-9-]{0,39}", value):
            _error(errors, path, "Expected a lowercase code (1-40 characters).")
    elif kind == "bool":
        if type(value) is not bool:
            _error(errors, path, "Expected a boolean.")
    elif kind == "date":
        valid = isinstance(value, str) and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value)
        if valid:
            try:
                valid = date.fromisoformat(value).isoformat() == value
            except ValueError:
                valid = False
        if not valid:
            _error(errors, path, "Expected a real Gregorian date in YYYY-MM-DD.")
    elif kind == "version":
        _integer(value, 1, 1000000, path, errors)
    elif kind == "refresh":
        _integer(value, 1, 3650, path, errors)
    elif kind == "reason":
        if not isinstance(value, str) or value not in REASON_RANK:
            _error(errors, path, "Expected a documented requirement reason code.")
    else:
        raise AssertionError("Unrecognized internal schema type")


class RecordGroup:
    def __init__(self, table, record_id, variants):
        self.table = table
        self.record_id = record_id
        self.variants = variants
        self.flags = set()

    @property
    def records(self):
        return [item["record"] for item in self.variants]

    @property
    def copies(self):
        return sum(item["copies"] for item in self.variants)

    @property
    def conflict(self):
        return len(self.variants) > 1


def _groups(payload):
    grouped = {}
    for table, key in TABLE_KEYS.items():
        index = defaultdict(dict)
        for row in payload[table]:
            variants = index[row[key]]
            serialized = _canonical(row)
            if serialized not in variants:
                variants[serialized] = {"record": dict(row), "copies": 0}
            variants[serialized]["copies"] += 1
        grouped[table] = {
            record_id: RecordGroup(table, record_id, [variants[key] for key in sorted(variants)])
            for record_id, variants in sorted(index.items())
        }
    return grouped


def _single(values):
    unique = set(values)
    return next(iter(unique)) if len(unique) == 1 else None


def _grid(groups, limit):
    by_kind = defaultdict(set)
    for requirement_id, group in groups["requirements"].items():
        for row in group.records:
            by_kind[row["site_kind"]].add(requirement_id)
    scoped_sites = {}
    cells = []
    for site_id, group in groups["sites"].items():
        site_rows = [row for row in group.records if row["in_scope"]]
        if not site_rows:
            continue
        scoped_sites[site_id] = site_rows
        kinds = {row["site_kind"] for row in site_rows}
        requirement_ids = set()
        for kind in kinds:
            requirement_ids.update(by_kind.get(kind, ()))
        if len(cells) + len(requirement_ids) > limit:
            return None, None
        for requirement_id in sorted(requirement_ids):
            requirement_rows = [
                row for row in groups["requirements"][requirement_id].records
                if row["site_kind"] in kinds
            ]
            cells.append({
                "site_id": site_id,
                "requirement_id": requirement_id,
                "site_rows": site_rows,
                "requirement_rows": requirement_rows,
                "trial_ids": sorted({row["trial_id"] for row in site_rows}),
                "document_types": sorted({row["document_type"] for row in requirement_rows}),
            })
    return cells, scoped_sites


def _validate(payload):
    errors = []
    root_fields = {"schema_version", "as_of_date", "policy"} | TABLE_KEYS.keys()
    if not _fields(payload, root_fields, "packet", errors):
        return errors, None, None, None
    if type(payload["schema_version"]) is not int or payload["schema_version"] != 1:
        _error(errors, "schema_version", "Expected schema_version integer 1.")
    _field(payload["as_of_date"], "date", "as_of_date", errors)
    if _fields(payload["policy"], POLICY_SCHEMA, "policy", errors):
        for field, kind in POLICY_SCHEMA.items():
            _field(payload["policy"][field], kind, f"policy.{field}", errors)
    for table in TABLE_KEYS:
        if not isinstance(payload[table], list):
            _error(errors, table, "Expected an array.")
    if errors:
        return errors, None, None, None

    policy = payload["policy"]
    for table in TABLE_KEYS:
        if len(payload[table]) > policy["max_rows_per_table"]:
            _error(errors, table, "Raw row count exceeds max_rows_per_table.")
    if sum(len(payload[table]) for table in TABLE_KEYS) > policy["max_total_rows"]:
        _error(errors, "policy.max_total_rows", "Raw row count exceeds max_total_rows.")
    if errors:
        return errors, None, None, None

    for table, schema in SCHEMAS.items():
        for index, row in enumerate(payload[table]):
            path = f"{table}[{index}]"
            if _fields(row, schema, path, errors):
                for field, kind in schema.items():
                    _field(row[field], kind, f"{path}.{field}", errors)
    if errors:
        return errors, None, None, None

    groups = _groups(payload)
    cells, scoped_sites = _grid(groups, policy["max_derived_pairs"])
    if cells is None:
        _error(errors, "policy.max_derived_pairs", "Derived site/requirement pairs exceed max_derived_pairs.")
        return errors, None, None, None
    as_of = date.fromisoformat(payload["as_of_date"])
    if (date.max - as_of).days < policy["draft_review_days"]:
        _error(errors, "as_of_date", "Draft review date exceeds the Gregorian date range.")
    refresh_by_key = defaultdict(set)
    for cell in cells:
        for requirement in cell["requirement_rows"]:
            if requirement["refresh_days"] is not None:
                refresh_by_key[(cell["site_id"], requirement["document_type"])].add(requirement["refresh_days"])
    for index, document in enumerate(payload["documents"]):
        remaining = (date.max - date.fromisoformat(document["issued_on"])).days
        periods = refresh_by_key.get((document["site_id"], document["document_type"]), ())
        if any(period > remaining for period in periods):
            _error(errors, f"documents[{index}].issued_on", "Derived refresh expiry exceeds the Gregorian date range.")
    return errors, groups, cells, scoped_sites


def _event(step_id, kind, caption, facts, title, columns, rows, highlights=()):
    total = len(rows)
    displayed = rows[:8]
    return {
        "step_id": step_id,
        "kind": kind,
        "caption": caption,
        "facts": facts,
        "tables": [{
            "title": f"{title} (first 8 of {total})" if total > 8 else title,
            "columns": columns,
            "rows": displayed,
            "total_rows": total,
            "highlight_rows": sorted({index for index in highlights if 0 <= index < len(displayed)}),
        }],
    }


def _input_event(payload):
    packet = payload if isinstance(payload, dict) else {}
    policy = packet.get("policy")
    policy = policy if isinstance(policy, dict) else {}
    rows = [
        [table, len(packet[table]) if isinstance(packet.get(table), list) else "not-array"]
        for table in TABLE_KEYS
    ]
    observed = {}
    for key, value in (("as_of_date", packet.get("as_of_date")), ("policy_id", policy.get("policy_id"))):
        observed[key] = value if isinstance(value, str) and len(value) <= 64 else None
    observed["array_rows"] = sum(row[1] for row in rows if type(row[1]) is int)
    return _event(
        "load-review-export", "input",
        "Loaded the supplied synthetic metadata packet; the six export counts include repeated rows.",
        observed, "Raw export tables", ["table", "raw_rows"], rows,
    )


def _rejected(errors, events):
    unique = {(item["path"], item["message"]): item for item in errors}
    errors = [unique[key] for key in sorted(unique)]
    events.append(_event(
        "validate-record-evidence", "validation",
        "Rejected the input packet during business validation; no document assessment or task drafting ran.",
        {"status": "rejected", "errors": len(errors)},
        "Input-packet errors", ["path", "code", "message"],
        [[item["path"], item["code"], item["message"]] for item in errors],
        range(len(errors)),
    ))
    return {"schema_version": 1, "status": "rejected", "outputs": {}, "exceptions": errors}, events


def _issue(code, **fields):
    return {"code": code, "message": MESSAGES[code], **fields}


def _violations(document):
    predicates = (
        document["issued_on"] > document["effective_on"],
        document["recorded_on"] < document["issued_on"],
        document["expires_on"] is not None and document["expires_on"] < document["issued_on"],
        document["expires_on"] is not None and document["expires_on"] < document["effective_on"],
    )
    return [name for name, applies in zip(CHRONOLOGY, predicates) if applies]


def _audit(groups, cells, scoped_sites, as_of):
    issues = []
    foreign_keys = {
        "sites": (("trial_id", "trials"),),
        "documents": (("site_id", "sites"), ("artifact_id", "artifacts")),
        "open_review_tasks": (("site_id", "sites"), ("requirement_id", "requirements")),
    }
    for table, records in groups.items():
        for record_id, group in records.items():
            redundant = group.copies - len(group.variants)
            if redundant:
                group.flags.add("duplicate-evidence")
                issues.append(_issue("duplicate-evidence", table=table, record_id=record_id, duplicate_count=redundant))
            if group.conflict:
                group.flags.add("conflicting-id")
                issues.append(_issue(
                    "conflicting-evidence", table=table, record_id=record_id, variant_count=len(group.variants),
                ))
            for row in group.records:
                for field, target in foreign_keys.get(table, ()):
                    if row[field] not in groups[target]:
                        issues.append(_issue(
                            "unmatched-reference", table=table, record_id=record_id, field=field, ref_id=row[field],
                        ))
            if table == "documents":
                violations = {violation for row in group.records for violation in _violations(row)}
                if violations:
                    group.flags.add("impossible-chronology")
                    issues.append(_issue(
                        "impossible-chronology", table=table, record_id=record_id,
                        violations=[name for name in CHRONOLOGY if name in violations],
                    ))
            if table == "open_review_tasks" and any(row["opened_on"] > as_of for row in group.records):
                group.flags.add("future-task")

    trial_refs = {row["trial_id"] for rows in scoped_sites.values() for row in rows}
    for trial_id, group in groups["trials"].items():
        group.flags.add("context" if trial_id in trial_refs else "unused")
    for site_id, group in groups["sites"].items():
        group.flags.add("in-scope" if site_id in scoped_sites else "out-of-scope")
    required_ids = {cell["requirement_id"] for cell in cells}
    for requirement_id, group in groups["requirements"].items():
        group.flags.add("applicable" if requirement_id in required_ids else "not-applicable")
    sites_with_cells = {cell["site_id"] for cell in cells}
    for site_id in scoped_sites:
        if site_id not in sites_with_cells:
            issues.append(_issue("missing-requirements", site_id=site_id))

    required_types = defaultdict(set)
    for cell in cells:
        required_types[cell["site_id"]].update(cell["document_types"])
    artifact_refs = set()
    for group in groups["documents"].values():
        for row in group.records:
            artifact_refs.add(row["artifact_id"])
            site_id = row["site_id"]
            if site_id not in groups["sites"]:
                group.flags.add("unmatched")
            elif site_id not in scoped_sites:
                group.flags.add("out-of-scope")
            elif row["document_type"] not in required_types[site_id]:
                group.flags.add("not-required")
    for artifact_id, group in groups["artifacts"].items():
        group.flags.add("referenced" if artifact_id in artifact_refs else "unused")
        if any(not row["export_available"] or not row["readability_attested"] for row in group.records):
            group.flags.add("unavailable-metadata")
    return issues


def _context_conflict(cell, groups):
    return (
        groups["sites"][cell["site_id"]].conflict
        or groups["requirements"][cell["requirement_id"]].conflict
        or any(trial_id not in groups["trials"] or groups["trials"][trial_id].conflict for trial_id in cell["trial_ids"])
    )


def _select(cell, groups, document_index, as_of):
    references = {
        f"sites/{cell['site_id']}", f"requirements/{cell['requirement_id']}",
        *(f"trials/{trial_id}" for trial_id in cell["trial_ids"]),
    }
    candidates = []
    future_ids = set()
    for document_type in cell["document_types"]:
        for group, row in document_index.get((cell["site_id"], document_type), ()):
            references.update((f"documents/{group.record_id}", f"artifacts/{row['artifact_id']}"))
            future = False
            if row["effective_on"] > as_of:
                group.flags.add("future-effective")
                future = True
            if row["recorded_on"] > as_of:
                group.flags.add("future-recorded")
                future = True
            if future:
                future_ids.add(group.record_id)
            else:
                candidates.append((group, row))

    blocked = _context_conflict(cell, groups) or any(
        group.conflict or _violations(row) for group, row in candidates
    )
    selected = None
    if candidates and not blocked:
        highest = max(row["version_seq"] for _, row in candidates)
        top = [(group, row) for group, row in candidates if row["version_seq"] == highest]
        if len(top) != 1:
            blocked = True
        else:
            selected = top[0][1]
            artifact = groups["artifacts"].get(selected["artifact_id"])
            if artifact is not None and artifact.conflict:
                artifact.flags.add("quarantined")
                blocked = True
                selected = None

    for group, row in candidates:
        if blocked:
            group.flags.add("quarantined")
        elif row is selected:
            group.flags.add("selected")
        else:
            group.flags.add("superseded")
    if selected is not None and selected["artifact_id"] in groups["artifacts"]:
        groups["artifacts"][selected["artifact_id"]].flags.add("selected-artifact")
    return {
        "cell": cell, "selected": selected, "blocked": bool(blocked),
        "references": sorted(references),
        "eligible_count": len({group.record_id for group, _ in candidates}),
        "future_count": len(future_ids),
    }


def _expiry(document, requirement, as_of):
    explicit = date.fromisoformat(document["expires_on"]) if document["expires_on"] is not None else None
    refresh = None
    if requirement["refresh_days"] is not None:
        refresh = date.fromisoformat(document["issued_on"]) + timedelta(days=requirement["refresh_days"])
    if explicit is None and refresh is None:
        return None, "none", None
    if explicit == refresh:
        effective, basis = explicit, "explicit-and-refresh"
    elif refresh is None or explicit is not None and explicit < refresh:
        effective, basis = explicit, "explicit"
    else:
        effective, basis = refresh, "refresh"
    return effective.isoformat(), basis, (effective - as_of).days


def _assess(selection, groups, as_of, warning_days):
    cell, document = selection["cell"], selection["selected"]
    row = {
        "site_id": cell["site_id"],
        "trial_id": _single(cell["trial_ids"]),
        "requirement_id": cell["requirement_id"],
        "document_type": _single(cell["document_types"]),
        "selected_document_id": document["document_id"] if document is not None else None,
        "assessment_state": "no-exception",
        "primary_reason": None,
        "reason_codes": [],
        "effective_expiry": None,
        "expiry_basis": None,
        "days_to_expiry": None,
        "source_refs": selection["references"],
    }
    reasons = []
    if selection["blocked"]:
        reasons.append("conflict")
    elif document is None:
        reasons.append("missing-document")
    else:
        requirement = cell["requirement_rows"][0]
        trial = groups["trials"][row["trial_id"]].records[0]
        artifact = groups["artifacts"].get(document["artifact_id"])
        if artifact is None or not all(
            record["export_available"] and record["readability_attested"] for record in artifact.records
        ):
            reasons.append("unavailable-evidence")
        if requirement["signature_required"] and not document["signature_recorded"]:
            reasons.append("missing-signature-evidence")
        if requirement["match_protocol_version"] and document["protocol_version"] != trial["required_protocol_version"]:
            reasons.append("protocol-version-mismatch")
        expiry, basis, remaining = _expiry(document, requirement, as_of)
        row.update(effective_expiry=expiry, expiry_basis=basis, days_to_expiry=remaining)
        if expiry is None and requirement["expiry_required"]:
            reasons.append("missing-expiry-evidence")
        if remaining is not None:
            if remaining < 0:
                reasons.append("expired")
            elif remaining <= warning_days:
                reasons.append("expiring-soon")
    reasons.sort(key=REASON_RANK.__getitem__)
    row["reason_codes"] = reasons
    row["primary_reason"] = reasons[0] if reasons else None
    if "conflict" in reasons:
        row["assessment_state"] = "quarantined"
    elif reasons == ["expiring-soon"]:
        row["assessment_state"] = "warning"
    elif reasons:
        row["assessment_state"] = "review"
    return row


def _route(matrix, groups, as_of, draft_days, issues):
    task_index = defaultdict(set)
    for task_id, group in groups["open_review_tasks"].items():
        for task in group.records:
            if task["opened_on"] <= as_of:
                task_index[(task["site_id"], task["requirement_id"], task["reason_code"])].add(task_id)
    queue = []
    draft_date = (date.fromisoformat(as_of) + timedelta(days=draft_days)).isoformat()
    for row in matrix:
        owner = groups["sites"][row["site_id"]]
        owner_id = None if owner.conflict else owner.records[0]["owner_role_id"]
        for reason in row["reason_codes"]:
            task_ids = sorted(task_index.get((row["site_id"], row["requirement_id"], reason), ()))
            ambiguous = owner_id is None
            for task_id in task_ids:
                group = groups["open_review_tasks"][task_id]
                group.flags.add("task-linked")
                if group.conflict:
                    group.flags.add("quarantined")
                    ambiguous = True
            if len(task_ids) > 1:
                issues.append(_issue(
                    "duplicate-open-tasks", site_id=row["site_id"], requirement_id=row["requirement_id"],
                    reason_code=reason, task_ids=task_ids,
                ))
            routing = "blocked-ambiguous" if ambiguous else "existing-task" if task_ids else "draft-new"
            queue.append({
                "site_id": row["site_id"], "requirement_id": row["requirement_id"],
                "reason_code": reason, "owner_role_id": owner_id,
                "existing_task_ids": task_ids, "action": "request-evidence-review",
                "routing": routing, "draft_review_by": draft_date if routing == "draft-new" else None,
            })
    for task_id, group in groups["open_review_tasks"].items():
        if "task-linked" not in group.flags and any(task["opened_on"] <= as_of for task in group.records):
            group.flags.add("unmatched")
            issues.append(_issue("unmatched-task", table="open_review_tasks", record_id=task_id))
    return queue


def _exception_key(issue):
    return (
        issue["code"], issue.get("table", ""), issue.get("record_id", ""),
        issue.get("site_id", ""), issue.get("requirement_id", ""),
        REASON_RANK.get(issue.get("reason_code"), -1),
        issue.get("field", ""), issue.get("ref_id", ""),
    )


def _ordered_issues(issues):
    return sorted({_canonical(issue): issue for issue in issues}.values(), key=_exception_key)


def _register(groups):
    return [
        {
            "table": table, "record_id": record_id, "copies": group.copies,
            "distinct_variants": len(group.variants), "dispositions": sorted(group.flags),
            "source_refs": sorted({row["source_ref"] for row in group.records}) if table == "artifacts" else [],
            "conflicting_variants": [
                {"copies": variant["copies"], "record": dict(variant["record"])} for variant in group.variants
            ] if group.conflict else [],
        }
        for table in sorted(groups)
        for record_id, group in groups[table].items()
    ]


def _summaries(matrix, scoped_sites):
    counts = defaultdict(Counter)
    for row in matrix:
        counts[row["site_id"]][row["assessment_state"]] += 1
    summaries = []
    for site_id in scoped_sites:
        counted = counts[site_id]
        summaries.append({
            "site_id": site_id,
            "required_count": sum(counted.values()),
            "no_exception_count": counted["no-exception"],
            "warning_count": counted["warning"],
            "review_count": counted["review"] + counted["quarantined"],
            "quarantined_count": counted["quarantined"],
        })
    return summaries


def solve(payload):
    events = [_input_event(payload)]
    errors, groups, cells, scoped_sites = _validate(payload)
    if errors:
        return _rejected(errors, events)
    as_of_text = payload["as_of_date"]
    as_of = date.fromisoformat(as_of_text)
    policy = payload["policy"]
    issues = _audit(groups, cells, scoped_sites, as_of_text)
    validation_rows = [
        [
            table, len(payload[table]), len(groups[table]),
            sum(group.copies - len(group.variants) for group in groups[table].values()),
            sum(group.conflict for group in groups[table].values()),
        ]
        for table in TABLE_KEYS
    ]
    events.append(_event(
        "validate-record-evidence", "validation",
        "Validated schemas and bounds; retained duplicate copies, competing variants, and chronology issues for explicit review.",
        {
            "raw_rows": sum(row[1] for row in validation_rows),
            "unique_records": sum(row[2] for row in validation_rows),
            "duplicate_copies": sum(row[3] for row in validation_rows),
            "conflicting_keys": sum(row[4] for row in validation_rows),
            "chronology_groups": sum("impossible-chronology" in group.flags for group in groups["documents"].values()),
        },
        "Validated export groups", ["table", "raw_rows", "unique_ids", "duplicate_copies", "conflicting_ids"],
        validation_rows, [index for index, row in enumerate(validation_rows) if row[3] or row[4]],
    ))
    events.append(_event(
        "expand-site-requirements", "join",
        "Expanded the bounded site-kind checklist, retaining cells whose document evidence is missing or ambiguous.",
        {"in_scope_sites": len(scoped_sites), "required_pairs": len(cells), "pair_limit": policy["max_derived_pairs"]},
        "Contextual requirement grid", ["site", "requirement", "document_type", "trial"],
        [[cell["site_id"], cell["requirement_id"], _single(cell["document_types"]), _single(cell["trial_ids"])] for cell in cells],
        [index for index, cell in enumerate(cells) if _context_conflict(cell, groups)],
    ))

    document_index = defaultdict(list)
    for group in groups["documents"].values():
        for document in group.records:
            document_index[(document["site_id"], document["document_type"])].append((group, document))
    selections = [_select(cell, groups, document_index, as_of_text) for cell in cells]
    selection_rows = [
        [
            item["cell"]["site_id"], item["cell"]["requirement_id"],
            item["selected"]["document_id"] if item["selected"] is not None else None,
            item["eligible_count"], item["future_count"],
            "quarantined" if item["blocked"] else "selected" if item["selected"] is not None else "missing",
        ]
        for item in selections
    ]
    events.append(_event(
        "select-as-of-documents", "join",
        "Filtered effective and recorded dates, selected the unique greatest eligible version, and joined artifact metadata without fallback.",
        {
            "selected_cells": sum(item["selected"] is not None for item in selections),
            "quarantined_cells": sum(item["blocked"] for item in selections),
            "future_candidate_ids_per_cell": sum(item["future_count"] for item in selections),
        },
        "As-of version resolution", ["site", "requirement", "selected", "eligible_ids", "future_ids", "resolution"],
        selection_rows, [index for index, row in enumerate(selection_rows) if row[-1] != "selected"],
    ))
    matrix = [_assess(item, groups, as_of, policy["warning_days"]) for item in selections]
    events.append(_event(
        "assess-checklist-gaps", "decision",
        "Assessed all evaluable metadata gaps; expiry is inclusive and company refresh/warning policies remain distinct from source guidance.",
        {
            "warning_days": policy["warning_days"],
            "reason_keys": sum(len(row["reason_codes"]) for row in matrix),
            "selected_without_expiry": sum(row["selected_document_id"] is not None and row["effective_expiry"] is None for row in matrix),
        },
        "Administrative evidence assessment", ["site", "requirement", "state", "primary_reason", "expiry", "days_remaining"],
        [[row["site_id"], row["requirement_id"], row["assessment_state"], row["primary_reason"], row["effective_expiry"], row["days_to_expiry"]] for row in matrix],
        [index for index, row in enumerate(matrix) if row["reason_codes"]],
    ))
    for row in matrix:
        if row["reason_codes"]:
            issues.append(_issue(
                "requirement-review", site_id=row["site_id"], requirement_id=row["requirement_id"],
                primary_reason=row["primary_reason"], reason_codes=list(row["reason_codes"]),
            ))
    queue = _route(matrix, groups, as_of_text, policy["draft_review_days"], issues)
    issues = _ordered_issues(issues)
    events.append(_event(
        "route-evidence-exceptions", "exception",
        "Linked existing as-of tasks or prepared unsent evidence-review requests; no task was transmitted, closed, or scheduled.",
        {
            "exceptions": len(issues), "queue_keys": len(queue),
            "draft_new": sum(row["routing"] == "draft-new" for row in queue),
            "existing_task": sum(row["routing"] == "existing-task" for row in queue),
            "blocked_ambiguous": sum(row["routing"] == "blocked-ambiguous" for row in queue),
        },
        "Evidence-review routing", ["site", "requirement", "reason", "routing", "existing_tasks"],
        [[row["site_id"], row["requirement_id"], row["reason_code"], row["routing"], len(row["existing_task_ids"])] for row in queue],
        [index for index, row in enumerate(queue) if row["routing"] != "draft-new"],
    ))
    summaries = _summaries(matrix, scoped_sites)
    conserved = all(
        row["required_count"] == row["no_exception_count"] + row["warning_count"] + row["review_count"]
        and row["quarantined_count"] <= row["review_count"]
        for row in summaries
    ) and sum(row["required_count"] for row in summaries) == len(cells)
    queue_keys = {(row["site_id"], row["requirement_id"], row["reason_code"]) for row in queue}
    unique_queue = len(queue_keys) == len(queue) == sum(len(row["reason_codes"]) for row in matrix)
    if not conserved or not unique_queue:
        raise AssertionError("Internal grid or queue conservation failed")
    events.append(_event(
        "reconcile-review-counts", "decision",
        "Reconciled every required cell and unique reason key; quarantined cells are a subset of review, not an extra denominator.",
        {"required_pairs": len(cells), "queue_keys": len(queue_keys), "counts_conserved": conserved, "queue_unique": unique_queue},
        "Site-count conservation", ["site", "required", "no_exception", "warning", "review", "quarantined"],
        [[row["site_id"], row["required_count"], row["no_exception_count"], row["warning_count"], row["review_count"], row["quarantined_count"]] for row in summaries],
        [index for index, row in enumerate(summaries) if row["review_count"] or row["warning_count"]],
    ))
    outputs = {
        "as_of_date": as_of_text, "policy_id": policy["policy_id"],
        "human_review_required": True, "scope_notice": SCOPE_NOTICE,
        "requirement_matrix": matrix, "site_summary": summaries,
        "evidence_register": _register(groups), "draft_review_queue": queue,
    }
    result = {
        "schema_version": 1,
        "status": "completed_with_exceptions" if issues else "completed",
        "outputs": outputs,
        "exceptions": issues,
    }
    events.append(_event(
        "write-review-packet", "output",
        "Prepared the ordered administrative export-review packet. Qualified human disposition remains required; no real-record authenticity or approval is established.",
        {"status": result["status"], "human_review_required": True, "exceptions": len(issues)},
        "Completed packet tables", ["output", "rows"],
        [[name, len(outputs[name])] for name in ("requirement_matrix", "site_summary", "evidence_register", "draft_review_queue")],
    ))
    return result, events


if __name__ == "__main__":
    run_cli(solve, scenario_id="hls-01")
