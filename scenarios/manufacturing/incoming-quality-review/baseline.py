"""Developer-only, no-Creator preparation of a synthetic QA review packet."""
from collections import defaultdict
from datetime import date
from decimal import Decimal
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "_shared"))
from scenario_support import run_cli


MAX_ROWS = 200
MAX_CHAIN = 8
IDENTIFIER = re.compile(r"[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*\Z")
DECIMAL = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]{1,4})?\Z")
CONFIG = {
    "as_of": "date",
    "review_age_days": "age",
    "certificate_required": "boolean",
    "fallback_reviewer_role": "text",
}
TABLES = {
    "items": ("item_id", {"item_id": "id", "item_group": "id"}),
    "reviewer_routes": ("item_group", {"item_group": "id", "reviewer_role": "text"}),
    "lots": ("lot_id", {
        "lot_id": "id", "item_id": "id", "supplier_id": "id", "receipt_date": "date",
        "received_qty": "positive", "site": "id", "quality_order_id": "id",
    }),
    "test_requirements": ("requirement_id", {
        "requirement_id": "id", "item_id": "id", "test_id": "id",
        "effective_from": "date", "effective_to": "date", "minimum": "decimal",
        "maximum": "decimal", "required_specimens": "specimens",
    }),
    "observations": ("result_id", {
        "result_id": "id", "lot_id": "id", "test_id": "id", "specimen_id": "id",
        "value": "decimal", "observed_on": "date", "supersedes_result_id": "nullable-id",
        "supersession_approved": "boolean",
    }),
    "certificates": ("certificate_id", {
        "certificate_id": "id", "lot_id": "id", "item_id": "id",
        "valid_through": "nullable-date", "status": "certificate-state",
    }),
    "hold_snapshot": ("lot_id", {
        "lot_id": "id", "physical_held_qty": "quantity", "hold_state": "hold-state",
        "snapshot_date": "date",
    }),
    "nonconformances": ("nc_id", {
        "nc_id": "id", "lot_id": "id", "state": "nc-state", "reason": "text",
    }),
}
CATEGORIES = ("data-review", "nonconformance-review", "evidence-gap", "evidence-complete")


class BusinessError(Exception):
    def __init__(self, code, subject, message):
        super().__init__(message)
        self.code = code
        self.subject = subject

    def report(self):
        return {"code": self.code, "message": str(self), "subject": self.subject, "owner_role": None}


def _fail(subject, message, code="invalid-field"):
    raise BusinessError(code, subject, message)


def _fields(value, names, subject):
    if not isinstance(value, dict):
        _fail(subject, "Expected an object.", "invalid-shape")
    if set(value) != set(names):
        missing = ", ".join(sorted(set(names) - set(value))) or "none"
        extra = ", ".join(sorted(set(value) - set(names))) or "none"
        _fail(subject, f"Incorrect fields; missing: {missing}; extra: {extra}.", "invalid-shape")


def _date(value, subject):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        _fail(subject, "Expected an ISO date YYYY-MM-DD.")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as error:
        raise BusinessError("invalid-field", subject, "Expected a valid calendar date.") from error
    if not date(2000, 1, 1) <= parsed <= date(2100, 12, 31):
        _fail(subject, "Date is outside 2000-01-01 through 2100-12-31.")
    return parsed


def _field(value, kind, subject):
    if kind.startswith("nullable-"):
        if value is None:
            return
        kind = kind.removeprefix("nullable-")
    if kind == "date":
        _date(value, subject)
    elif kind == "id":
        if not isinstance(value, str) or len(value) > 48 or not IDENTIFIER.fullmatch(value):
            _fail(subject, "Expected a 1-48 character uppercase ASCII identifier with single hyphens.")
    elif kind == "text":
        if not isinstance(value, str) or not value.strip() or len(value) > 240:
            _fail(subject, "Expected nonempty text of at most 240 characters.")
    elif kind == "boolean":
        if type(value) is not bool:
            _fail(subject, "Expected a JSON boolean.")
    elif kind in {"positive", "quantity", "age", "specimens"}:
        low, high = {"positive": (1, 1_000_000), "quantity": (0, 1_000_000),
                     "age": (0, 3660), "specimens": (1, 100)}[kind]
        if type(value) is not int or not low <= value <= high:
            _fail(subject, f"Expected an integer from {low} through {high}.")
    elif kind == "decimal":
        if (not isinstance(value, str) or len(value) > 24 or not DECIMAL.fullmatch(value)
                or not -Decimal(1_000_000) <= Decimal(value) <= Decimal(1_000_000)):
            _fail(subject, "Expected a finite decimal string within +/-1000000 with at most four decimal places.")
    elif kind in {"certificate-state", "hold-state", "nc-state"}:
        allowed = {
            "certificate-state": ("valid", "withdrawn"),
            "hold-state": ("held", "partial", "none"),
            "nc-state": ("open", "closed"),
        }[kind]
        if not isinstance(value, str) or value not in allowed:
            _fail(subject, "Expected one of: " + ", ".join(allowed) + ".")
    else:
        raise AssertionError("Unknown field validator: " + kind)


def _issue(issues, code, subject, message, owner=None):
    item = {"code": code, "message": message, "subject": subject, "owner_role": owner}
    if item not in issues:
        issues.append(item)


def _record(events, step, kind, caption, columns, rows, facts=None):
    events.append({
        "step_id": step, "kind": kind, "caption": caption, "facts": facts or {},
        "tables": [{
            "title": caption, "columns": columns, "rows": rows[:8],
            "total_rows": len(rows), "highlight_rows": [0] if rows else [],
        }],
    })


def _validate(payload, issues):
    _fields(payload, {"config", *TABLES}, "input")
    config = payload["config"]
    _fields(config, CONFIG, "config")
    for key, kind in CONFIG.items():
        _field(config[key], kind, "config." + key)
    tables = {}
    for name, (primary, schema) in TABLES.items():
        rows = payload[name]
        if not isinstance(rows, list) or len(rows) > MAX_ROWS:
            _fail(name, f"Expected an array with at most {MAX_ROWS} rows.", "invalid-table")
        indexed = {}
        for index, row in enumerate(rows):
            _fields(row, schema, f"{name}[{index}]")
            _field(row[primary], "id", f"{name}[{index}].{primary}")
            subject = name + ":" + row[primary]
            for key, kind in schema.items():
                _field(row[key], kind, subject + "." + key)
            if row[primary] in indexed:
                if row != indexed[row[primary]]:
                    _fail(subject, "Conflicting rows share a primary identifier.", "contradictory-evidence")
                _issue(issues, "duplicate-record", subject, "Collapsed identical duplicate source row.")
                continue
            indexed[row[primary]] = row
        tables[name] = dict(sorted(indexed.items()))
    _validate_relationships(tables, config, issues)
    return config, tables


def _validate_relationships(tables, config, issues):
    as_of = config["as_of"]
    lots = tables["lots"]
    for lot in lots.values():
        if lot["receipt_date"] > as_of:
            _fail("lots:" + lot["lot_id"], "Receipt date is after as_of.", "contradictory-evidence")
    for requirement in tables["test_requirements"].values():
        subject = "test_requirements:" + requirement["requirement_id"]
        if (requirement["effective_from"] > requirement["effective_to"]
                or Decimal(requirement["minimum"]) > Decimal(requirement["maximum"])):
            _fail(subject, "Requirement date or decimal limits are reversed.", "contradictory-evidence")
        if requirement["item_id"] not in tables["items"]:
            _issue(issues, "unknown-reference", subject, "Requirement refers to an item absent from the item export.")
    for name in ("observations", "certificates", "hold_snapshot", "nonconformances"):
        for key, row in tables[name].items():
            subject = name + ":" + key
            lot = lots.get(row["lot_id"])
            if lot is None:
                _issue(issues, "unknown-reference", subject, "Evidence refers to a lot absent from the receipt export.")
                continue
            if name == "observations" and row["observed_on"] < lot["receipt_date"]:
                _fail(subject, "Observation predates the lot receipt.", "contradictory-evidence")
            if name == "certificates" and row["item_id"] != lot["item_id"]:
                _fail(subject, "Certificate item disagrees with the linked lot.", "contradictory-evidence")
            if name == "hold_snapshot":
                quantity, received = row["physical_held_qty"], lot["received_qty"]
                valid_state = (
                    (row["hold_state"] == "held" and quantity == received)
                    or (row["hold_state"] == "partial" and 0 < quantity < received)
                    or (row["hold_state"] == "none" and quantity == 0)
                )
                if quantity > received or not valid_state or row["snapshot_date"] < lot["receipt_date"]:
                    _fail(subject, "Physical hold quantity, state or snapshot date contradicts the lot receipt.", "contradictory-evidence")
    observations = tables["observations"]
    children = defaultdict(list)
    roots = defaultdict(list)
    for key, row in observations.items():
        previous_id = row["supersedes_result_id"]
        group = (row["lot_id"], row["test_id"], row["specimen_id"])
        if previous_id is None:
            roots[group].append(key)
            if row["supersession_approved"]:
                _fail("observations:" + key, "Supersession approval has no predecessor.", "contradictory-evidence")
        else:
            previous = observations.get(previous_id)
            if previous is None:
                _fail("observations:" + key, "Retest predecessor does not exist.", "contradictory-evidence")
            if group != (previous["lot_id"], previous["test_id"], previous["specimen_id"]):
                _fail("observations:" + key, "Retest changes lot, test or specimen identity.", "contradictory-evidence")
            if previous["observed_on"] > row["observed_on"]:
                _fail("observations:" + key, "Retest predates its predecessor.", "contradictory-evidence")
            children[previous_id].append(key)
    for key, successors in children.items():
        if len(successors) > 1:
            _fail("observations:" + key, "Retest lineage branches ambiguously.", "contradictory-evidence")
    for group, members in roots.items():
        if len(members) > 1:
            _fail("observations:" + members[0], "Specimen has multiple original results without a retest link.", "contradictory-evidence")
    counts = defaultdict(int)
    for lot_id, test_id, _ in roots:
        counts[(lot_id, test_id)] += 1
    for (lot_id, test_id), count in sorted(counts.items()):
        if lot_id in lots and count > lots[lot_id]["received_qty"]:
            _fail(lot_id + ":" + test_id, "Distinct specimens exceed physical lot quantity.", "contradictory-evidence")
    for key in observations:
        seen = set()
        current = key
        while current is not None:
            if current in seen:
                _fail("observations:" + key, "Retest lineage contains a cycle.", "contradictory-evidence")
            seen.add(current)
            if len(seen) > MAX_CHAIN:
                _fail("observations:" + key, "Retest lineage exceeds eight observations.", "input-limit")
            current = observations[current]["supersedes_result_id"]


def _contexts(config, tables, issues):
    contexts = []
    for lot_id, lot in tables["lots"].items():
        item = tables["items"].get(lot["item_id"])
        route = tables["reviewer_routes"].get(item["item_group"]) if item else None
        owner = route["reviewer_role"] if route else config["fallback_reviewer_role"]
        context = {
            "lot": lot, "owner": owner, "requirements": {}, "reason_codes": set(),
            "data_problem": False, "gap": False, "nonconforming": False,
        }
        if item is None:
            context["data_problem"] = True
            _lot_issue(context, issues, "unknown-item", f"Item {lot['item_id']} is absent from the item export.")
        else:
            groups = defaultdict(list)
            for requirement in tables["test_requirements"].values():
                if requirement["item_id"] == lot["item_id"]:
                    groups[requirement["test_id"]].append(requirement)
            if not groups:
                context["data_problem"] = True
                _lot_issue(context, issues, "missing-requirements", "No test requirements exist for the item.")
            for test_id, versions in sorted(groups.items()):
                selected = [r for r in versions if r["effective_from"] <= lot["receipt_date"] <= r["effective_to"]]
                if len(selected) > 1:
                    _fail(lot_id + ":" + test_id, "Multiple requirements match the receipt date.", "contradictory-evidence")
                if not selected:
                    context["data_problem"] = True
                    _lot_issue(context, issues, "missing-requirements", f"No {test_id} requirement matches the receipt date.")
                else:
                    context["requirements"][test_id] = selected[0]
        hold = tables["hold_snapshot"].get(lot_id)
        if hold and hold["snapshot_date"] > config["as_of"]:
            _lot_issue(context, issues, "future-hold", "Hold snapshot is after as_of and is not current evidence.")
            hold = None
        if hold is None:
            context["gap"] = True
            _lot_issue(context, issues, "missing-hold", "Physical held quantity is unknown; obtain a current hold snapshot.")
        context["hold"] = hold
        contexts.append(context)
    return contexts


def _lot_issue(context, issues, code, message):
    context["reason_codes"].add(code)
    _issue(issues, code, context["lot"]["lot_id"], message, context["owner"])


def _evidence_states(observations, as_of):
    states, chains = {}, {}
    for key, row in observations.items():
        chain = []
        current = key
        while current is not None:
            chain.append(current)
            current = observations[current]["supersedes_result_id"]
        chains[key] = chain
        states[key] = "future" if row["observed_on"] > as_of else (
            "active" if row["supersedes_result_id"] is None else "pending-retest"
        )
    # Process ancestors before descendants; an unapproved intermediate link cannot be bypassed.
    for key in sorted(observations, key=lambda value: (len(chains[value]), value)):
        if states[key] == "future":
            continue
        chain = chains[key]
        approved = all(observations[child]["supersession_approved"] for child in chain[:-1])
        if approved:
            states[key] = "active"
            for previous in chain[1:]:
                states[previous] = "superseded"
    return states


def _evaluate(context, config, tables, states, issues):
    lot_id = context["lot"]["lot_id"]
    observations = [r for r in tables["observations"].values() if r["lot_id"] == lot_id]
    for row in observations:
        if states[row["result_id"]] == "future":
            _lot_issue(context, issues, "future-observation", f"Result {row['result_id']} is after as_of and is excluded from active evidence.")
        if row["test_id"] not in context["requirements"]:
            context["data_problem"] = True
            _lot_issue(context, issues, "unexpected-test", f"Result {row['result_id']} has no selected requirement for {row['test_id']}.")
    checks = []
    for test_id, requirement in sorted(context["requirements"].items()):
        rows = sorted((r for r in observations if r["test_id"] == test_id),
                      key=lambda row: (row["observed_on"], row["result_id"]))
        active = [r for r in rows if states[r["result_id"]] == "active"]
        failed = sorted(r["result_id"] for r in active
                        if not Decimal(requirement["minimum"]) <= Decimal(r["value"]) <= Decimal(requirement["maximum"]))
        pending = sorted(r["result_id"] for r in rows if states[r["result_id"]] == "pending-retest")
        observed = len({r["specimen_id"] for r in active})
        enough = observed >= requirement["required_specimens"]
        if failed:
            context["nonconforming"] = True
            _lot_issue(context, issues, "failed-test", f"{test_id} has out-of-limit active results: {', '.join(failed)}.")
        if not enough:
            context["gap"] = True
            _lot_issue(context, issues, "insufficient-specimens",
                       f"{test_id} requires {requirement['required_specimens']} distinct specimens; found {observed}.")
        if pending:
            context["gap"] = True
            _lot_issue(context, issues, "pending-retest", f"{test_id} has unapproved retest evidence: {', '.join(pending)}.")
        checks.append({
            "test_id": test_id, "requirement_id": requirement["requirement_id"],
            "minimum": requirement["minimum"], "maximum": requirement["maximum"],
            "required_specimens": requirement["required_specimens"], "observed_specimens": observed,
            "state": "failed" if failed else ("incomplete" if not enough or pending else "complete"),
            "failed_result_ids": failed,
            "observations": [
                {"result_id": row["result_id"], "specimen_id": row["specimen_id"],
                 "value": row["value"], "evidence_state": states[row["result_id"]]} for row in rows
            ],
        })
    certificates = []
    for certificate in tables["certificates"].values():
        if certificate["lot_id"] != lot_id:
            continue
        if (certificate["status"] == "valid" and certificate["valid_through"] is not None
                and certificate["valid_through"] >= config["as_of"]):
            certificates.append(certificate["certificate_id"])
        else:
            _lot_issue(context, issues, "unusable-certificate",
                       f"Certificate {certificate['certificate_id']} is withdrawn, expired or has unknown validity.")
    if config["certificate_required"] and not certificates:
        context["gap"] = True
        _lot_issue(context, issues, "missing-certificate", "No current matching certificate is available.")
    open_nc = sorted(row["nc_id"] for row in tables["nonconformances"].values()
                     if row["lot_id"] == lot_id and row["state"] == "open")
    if open_nc:
        context["nonconforming"] = True
        _lot_issue(context, issues, "open-nonconformance", f"Open nonconformances: {', '.join(open_nc)}.")
    context.update(test_checks=checks, certificate_ids=sorted(certificates), open_nc_ids=open_nc)


def _queue_row(context, config, issues):
    lot = context["lot"]
    age = (_date(config["as_of"], "config.as_of") - _date(lot["receipt_date"], "receipt_date")).days
    overdue = age > config["review_age_days"]
    if overdue:
        _lot_issue(context, issues, "overdue-review",
                   f"Review age {age} exceeds {config['review_age_days']} calendar days.")
    category = ("data-review" if context["data_problem"] else
                "nonconformance-review" if context["nonconforming"] else
                "evidence-gap" if context["gap"] else "evidence-complete")
    hold = context["hold"]
    return {
        "rank": 0, **lot,
        "physical_held_qty": hold["physical_held_qty"] if hold else None,
        "hold_state": hold["hold_state"] if hold else None,
        "hold_snapshot_date": hold["snapshot_date"] if hold else None,
        "age_days": age, "overdue": overdue, "review_state": category,
        "reviewer_role": context["owner"], "approval_required": True, "production_authorized": False,
        "reason_codes": sorted(context["reason_codes"]),
        "certificate_ids": context["certificate_ids"], "open_nc_ids": context["open_nc_ids"],
        "test_checks": context["test_checks"],
    }


def solve(payload):
    events, issues = [], []
    inventory = [[name, len(payload[name]) if isinstance(payload, dict) and isinstance(payload.get(name), list) else None]
                 for name in TABLES]
    _record(events, "intake", "input", "Inventory the actual mock export tables.",
            ["export", "source_rows"], inventory)
    try:
        config, tables = _validate(payload, issues)
        _record(events, "validate", "validation", "Validate keys, typed values, physical holds and retest relationships.",
                ["export", "source_rows", "unique_rows"],
                [[name, len(payload[name]), len(tables[name])] for name in TABLES],
                {"duplicate_groups": sum(item["code"] == "duplicate-record" for item in issues)})
        contexts = _contexts(config, tables, issues)
        _record(events, "join-lot-context", "join", "Match lots to requirements, physical holds and reviewer roles.",
                ["lot_id", "item_id", "tests", "held_qty", "reviewer"],
                [[c["lot"]["lot_id"], c["lot"]["item_id"], len(c["requirements"]),
                  c["hold"]["physical_held_qty"] if c["hold"] else None, c["owner"]] for c in contexts],
                {"as_of": config["as_of"], "lots": len(contexts)})
        states = _evidence_states(tables["observations"], config["as_of"])
        _record(events, "resolve-evidence", "join", "Resolve actual observation dates and approved retest lineage.",
                ["result_id", "lot_id", "specimen", "value", "evidence_state"],
                [[key, row["lot_id"], row["specimen_id"], row["value"], states[key]]
                 for key, row in tables["observations"].items()],
                {"active": sum(value == "active" for value in states.values()),
                 "pending": sum(value == "pending-retest" for value in states.values())})
        for context in contexts:
            _evaluate(context, config, tables, states, issues)
        _record(events, "evaluate-tests", "decision", "Evaluate required specimens, decimal limits and supporting evidence.",
                ["lot_id", "test_id", "required", "observed", "failed", "state"],
                [[c["lot"]["lot_id"], t["test_id"], t["required_specimens"],
                  t["observed_specimens"], len(t["failed_result_ids"]), t["state"]]
                 for c in contexts for t in c["test_checks"]])
        queue = [_queue_row(context, config, issues) for context in contexts]
        _record(events, "classify-review", "decision", "Apply review precedence without authorizing material disposition.",
                ["lot_id", "review_state", "received_qty", "age_days", "reason_codes"],
                [[row["lot_id"], row["review_state"], row["received_qty"], row["age_days"],
                  ", ".join(row["reason_codes"])] for row in queue])
        issues.sort(key=lambda item: (item["code"], item["subject"], item["message"], item["owner_role"] or ""))
        _record(events, "collect-exceptions", "exception", "Preserve evidence gaps, failed observations and review owners.",
                ["code", "subject", "owner", "message"],
                [[item["code"], item["subject"], item["owner_role"], item["message"]] for item in issues],
                {"exception_count": len(issues)})
        queue.sort(key=lambda row: (CATEGORIES.index(row["review_state"]), -row["age_days"], row["lot_id"]))
        for rank, row in enumerate(queue, start=1):
            row["rank"] = rank
        _record(events, "order-review", "decision", "Order the review queue by category, age and stable lot identifier.",
                ["rank", "lot_id", "review_state", "reviewer", "received_qty", "age_days"],
                [[row["rank"], row["lot_id"], row["review_state"], row["reviewer_role"],
                  row["received_qty"], row["age_days"]] for row in queue])
        quantities = {category: sum(row["received_qty"] for row in queue if row["review_state"] == category)
                      for category in CATEGORIES}
        totals = {
            "lot_count": len(queue), "received_qty": sum(row["received_qty"] for row in queue),
            "known_held_qty": sum(row["physical_held_qty"] for row in queue if row["physical_held_qty"] is not None),
            "unknown_hold_lot_ids": sorted(row["lot_id"] for row in queue if row["physical_held_qty"] is None),
            "review_quantities": quantities,
        }
        result = {
            "schema_version": 1, "status": "completed_with_exceptions" if issues else "completed",
            "outputs": {"as_of": config["as_of"], "packet_state": "review-required",
                        "review_queue": queue, "totals": totals},
            "exceptions": issues,
        }
        _record(events, "close-packet", "output", "Close the review-only packet with reconciled physical quantities.",
                ["review_state", "received_qty"], [[key, value] for key, value in quantities.items()],
                {"lot_count": totals["lot_count"], "received_qty": totals["received_qty"],
                 "known_held_qty": totals["known_held_qty"], "unknown_holds": len(totals["unknown_hold_lot_ids"]),
                 "production_authorized": False})
        return result, events
    except BusinessError as error:
        failure = error.report()
        _record(events, "validate", "validation", "Reject contradictory or malformed input; no review packet is issued.",
                ["code", "subject", "message"], [[failure["code"], failure["subject"], failure["message"]]],
                {"status": "rejected"})
        return {"schema_version": 1, "status": "rejected", "outputs": {}, "exceptions": [failure]}, events


if __name__ == "__main__":
    run_cli(solve, scenario_id="manufacturing-01")
