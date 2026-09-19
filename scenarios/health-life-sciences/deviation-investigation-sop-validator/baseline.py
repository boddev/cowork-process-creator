"""Developer-only baseline for a synthetic deviation investigation review."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "_shared"))
from scenario_support import run_cli


TABLE_NAMES = (
    "sop_versions",
    "requirements",
    "deviations",
    "investigations",
    "evidence",
    "open_review_tasks",
)
ROOT_FIELDS = {"schema_version", "as_of_date", "policy", *TABLE_NAMES}
POLICY_FIELDS = {
    "policy_id",
    "investigation_due_days",
    "due_soon_days",
    "max_rows_per_table",
    "max_total_rows",
}
TABLES = {
    "sop_versions": (
        "sop_version",
        {"sop_version": "version", "effective_from": "date", "effective_to": "nullable-date"},
    ),
    "requirements": (
        "requirement_id",
        {
            "requirement_id": "id",
            "sop_version": "version",
            "minimum_severity": "severity",
            "requirement_code": "code",
            "evidence_type": "code",
        },
    ),
    "deviations": (
        "deviation_id",
        {
            "deviation_id": "id",
            "opened_on": "date",
            "occurred_on": "date",
            "department_code": "code",
            "severity": "severity",
            "owner_role_id": "id",
            "status": "deviation-status",
        },
    ),
    "investigations": (
        "investigation_id",
        {
            "investigation_id": "id",
            "deviation_id": "id",
            "sop_version": "version",
            "started_on": "date",
            "completed_on": "nullable-date",
        },
    ),
    "evidence": (
        "evidence_id",
        {
            "evidence_id": "id",
            "investigation_id": "id",
            "evidence_type": "code",
            "recorded_on": "date",
            "source_ref": "id",
        },
    ),
    "open_review_tasks": (
        "task_id",
        {
            "task_id": "id",
            "deviation_id": "id",
            "reason_code": "code",
            "opened_on": "date",
        },
    ),
}
ID_PATTERN = re.compile(r"SYN-[A-Z0-9]+(?:-[A-Z0-9]+)*\Z")
CODE_PATTERN = re.compile(r"[a-z][a-z0-9-]{0,39}\Z")
SEVERITY_RANK = {"minor": 0, "major": 1, "critical": 2}
REVIEW_STATES = ("data-review", "missing-investigation", "sop-gap", "administratively-complete")
DUE_STATES = ("overdue", "due-soon", "on-track", "completed-late", "completed-on-time")
PRIORITY_RANK = {"high": 0, "medium": 1, "normal": 2}


class BusinessError(ValueError):
    def __init__(self, code: str, subject: str, message: str):
        super().__init__(message)
        self.code = code
        self.subject = subject

    def report(self) -> dict:
        return {
            "code": self.code,
            "message": str(self),
            "subject": self.subject,
            "owner_role": None,
        }


def _fail(subject: str, message: str, code: str = "invalid-field") -> None:
    raise BusinessError(code, subject, message)


def _fields(value: object, expected: set[str], subject: str) -> dict:
    if not isinstance(value, dict):
        _fail(subject, "Expected an object.", "invalid-shape")
    if set(value) != expected:
        missing = ", ".join(sorted(expected - set(value))) or "none"
        extra = ", ".join(sorted(set(value) - expected)) or "none"
        _fail(subject, f"Incorrect fields; missing: {missing}; extra: {extra}.", "invalid-shape")
    return value


def _date(value: object, subject: str) -> date:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        _fail(subject, "Expected a real Gregorian date in YYYY-MM-DD.")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as error:
        raise BusinessError(
            "invalid-field", subject, "Expected a real Gregorian date in YYYY-MM-DD."
        ) from error
    if not date(2000, 1, 1) <= parsed <= date(2100, 12, 31):
        _fail(subject, "Expected a date from 2000-01-01 through 2100-12-31.")
    return parsed


def _integer(value: object, low: int, high: int, subject: str) -> int:
    if type(value) is not int or not low <= value <= high:
        _fail(subject, f"Expected an integer from {low} through {high}.")
    return value


def _field(value: object, kind: str, subject: str) -> None:
    if kind.startswith("nullable-"):
        if value is None:
            return
        kind = kind.removeprefix("nullable-")
    if kind == "id":
        if not isinstance(value, str) or len(value) > 64 or ID_PATTERN.fullmatch(value) is None:
            _fail(subject, "Expected a synthetic SYN- identifier of at most 64 characters.")
    elif kind == "code":
        if not isinstance(value, str) or CODE_PATTERN.fullmatch(value) is None:
            _fail(subject, "Expected a lowercase code of 1-40 characters.")
    elif kind == "date":
        _date(value, subject)
    elif kind == "version":
        _integer(value, 1, 1_000_000, subject)
    elif kind == "severity":
        if value not in SEVERITY_RANK:
            _fail(subject, "Expected one of: minor, major, critical.")
    elif kind == "deviation-status":
        if value not in {"open", "under-review", "closed"}:
            _fail(subject, "Expected one of: open, under-review, closed.")
    else:
        raise AssertionError(f"Unknown validator kind: {kind}")


def _issue(
    issues: list[dict],
    code: str,
    subject: str,
    message: str,
    owner_role: str | None = None,
) -> None:
    item = {
        "code": code,
        "message": message,
        "subject": subject,
        "owner_role": owner_role,
    }
    if item not in issues:
        issues.append(item)


def _event(
    events: list[dict],
    step_id: str,
    kind: str,
    caption: str,
    columns: list[str],
    rows: list[list],
    facts: dict | None = None,
) -> None:
    events.append(
        {
            "step_id": step_id,
            "kind": kind,
            "caption": caption,
            "facts": facts or {},
            "tables": [
                {
                    "title": caption,
                    "columns": columns,
                    "rows": rows[:8],
                    "total_rows": len(rows),
                    "highlight_rows": [0] if rows else [],
                }
            ],
        }
    )


def _validate(payload: object, issues: list[dict]) -> tuple[date, dict, dict]:
    payload = _fields(payload, ROOT_FIELDS, "input")
    if type(payload["schema_version"]) is not int or payload["schema_version"] != 1:
        _fail("schema_version", "Expected schema_version integer 1.")
    as_of = _date(payload["as_of_date"], "as_of_date")

    policy = _fields(payload["policy"], POLICY_FIELDS, "policy")
    _field(policy["policy_id"], "id", "policy.policy_id")
    due_days = _integer(policy["investigation_due_days"], 0, 3650, "policy.investigation_due_days")
    due_soon_days = _integer(policy["due_soon_days"], 0, 365, "policy.due_soon_days")
    if due_soon_days > due_days:
        _fail("policy.due_soon_days", "due_soon_days must not exceed investigation_due_days.")
    max_rows = _integer(policy["max_rows_per_table"], 1, 1000, "policy.max_rows_per_table")
    max_total = _integer(policy["max_total_rows"], 1, 5000, "policy.max_total_rows")

    raw_total = 0
    for name in TABLE_NAMES:
        rows = payload[name]
        if not isinstance(rows, list):
            _fail(name, "Expected an array.", "invalid-table")
        if len(rows) > max_rows:
            _fail(name, f"Raw row count exceeds policy.max_rows_per_table ({max_rows}).", "invalid-table")
        raw_total += len(rows)
    if raw_total > max_total:
        _fail(
            "policy.max_total_rows",
            f"Raw table row count {raw_total} exceeds the configured limit {max_total}.",
            "invalid-table",
        )

    tables = {}
    for name, (primary, schema) in TABLES.items():
        indexed = {}
        for index, row in enumerate(payload[name]):
            subject = f"{name}[{index}]"
            row = _fields(row, set(schema), subject)
            for field_name, kind in schema.items():
                _field(row[field_name], kind, f"{subject}.{field_name}")
            key = row[primary]
            primary_subject = f"{name}:{key}"
            if key in indexed:
                if row != indexed[key]:
                    _fail(
                        primary_subject,
                        "Conflicting rows share a primary identifier.",
                        "contradictory-evidence",
                    )
                _issue(
                    issues,
                    "duplicate-record",
                    primary_subject,
                    "Collapsed identical duplicate source row.",
                )
                continue
            indexed[key] = row
        tables[name] = indexed

    _validate_relationships(as_of, tables, issues)
    return as_of, policy, tables


def _validate_relationships(as_of: date, tables: dict, issues: list[dict]) -> None:
    for version, row in tables["sop_versions"].items():
        start = _date(row["effective_from"], f"sop_versions:{version}.effective_from")
        end = (
            _date(row["effective_to"], f"sop_versions:{version}.effective_to")
            if row["effective_to"] is not None
            else None
        )
        if end is not None and end < start:
            _fail(
                f"sop_versions:{version}",
                "effective_to must be on or after effective_from.",
                "contradictory-evidence",
            )

    for requirement in tables["requirements"].values():
        if requirement["sop_version"] not in tables["sop_versions"]:
            _issue(
                issues,
                "unknown-reference",
                f"requirements:{requirement['requirement_id']}",
                "Requirement refers to an SOP version absent from the export.",
            )

    for deviation in tables["deviations"].values():
        if _date(deviation["occurred_on"], "occurred_on") > _date(deviation["opened_on"], "opened_on"):
            _fail(
                f"deviations:{deviation['deviation_id']}",
                "occurred_on must not be after opened_on.",
                "contradictory-evidence",
            )
        if _date(deviation["opened_on"], "opened_on") > as_of:
            _fail(
                f"deviations:{deviation['deviation_id']}",
                "opened_on must not be after as_of_date.",
                "contradictory-evidence",
            )

    by_deviation = defaultdict(list)
    for investigation in tables["investigations"].values():
        deviation_id = investigation["deviation_id"]
        by_deviation[deviation_id].append(investigation)
        if deviation_id not in tables["deviations"]:
            _issue(
                issues,
                "unknown-reference",
                f"investigations:{investigation['investigation_id']}",
                "Investigation refers to a deviation absent from the export.",
            )
            continue
        deviation = tables["deviations"][deviation_id]
        if _date(investigation["started_on"], "started_on") < _date(deviation["opened_on"], "opened_on"):
            _fail(
                f"investigations:{investigation['investigation_id']}",
                "started_on must not be before the deviation opened_on date.",
                "contradictory-evidence",
            )
        if investigation["completed_on"] is not None and _date(
            investigation["completed_on"], "completed_on"
        ) < _date(investigation["started_on"], "started_on"):
            _fail(
                f"investigations:{investigation['investigation_id']}",
                "completed_on must not be before started_on.",
                "contradictory-evidence",
            )
    for deviation_id, rows in by_deviation.items():
        if deviation_id in tables["deviations"] and len(rows) > 1:
            _fail(
                f"deviations:{deviation_id}",
                "More than one investigation refers to the deviation.",
                "contradictory-evidence",
            )

    for evidence in tables["evidence"].values():
        if evidence["investigation_id"] not in tables["investigations"]:
            _issue(
                issues,
                "unknown-reference",
                f"evidence:{evidence['evidence_id']}",
                "Evidence refers to an investigation absent from the export.",
            )

    for task in tables["open_review_tasks"].values():
        if task["deviation_id"] not in tables["deviations"]:
            _issue(
                issues,
                "unknown-reference",
                f"open_review_tasks:{task['task_id']}",
                "Review task refers to a deviation absent from the export.",
            )


def _select_sop(deviation: dict, tables: dict) -> int | None:
    opened = _date(deviation["opened_on"], "opened_on")
    matches = []
    for version, row in tables["sop_versions"].items():
        start = _date(row["effective_from"], "effective_from")
        end = _date(row["effective_to"], "effective_to") if row["effective_to"] is not None else None
        if start <= opened and (end is None or opened <= end):
            matches.append(version)
    if len(matches) > 1:
        _fail(
            f"deviations:{deviation['deviation_id']}",
            "Multiple SOP versions apply to the deviation opened date.",
            "contradictory-evidence",
        )
    return matches[0] if matches else None


def _add_days(start: date, days: int, subject: str) -> date:
    try:
        result = start + timedelta(days=days)
    except OverflowError as error:
        raise BusinessError("invalid-field", subject, "Date addition exceeds supported range.") from error
    if result > date(2100, 12, 31):
        _fail(subject, "Date addition exceeds 2100-12-31.")
    return result


def _due_state(
    deviation: dict,
    investigation: dict | None,
    as_of: date,
    due_days: int,
    due_soon_days: int,
) -> tuple[date, str]:
    due_date = _add_days(
        _date(deviation["opened_on"], "opened_on"),
        due_days,
        f"deviations:{deviation['deviation_id']}.opened_on",
    )
    if investigation is not None and investigation["completed_on"] is not None:
        completed = _date(investigation["completed_on"], "completed_on")
        return due_date, "completed-late" if completed > due_date else "completed-on-time"
    if as_of > due_date:
        return due_date, "overdue"
    if (due_date - as_of).days <= due_soon_days:
        return due_date, "due-soon"
    return due_date, "on-track"


def _review_deviation(
    deviation: dict,
    as_of: date,
    policy: dict,
    tables: dict,
    issues: list[dict],
) -> dict:
    deviation_id = deviation["deviation_id"]
    owner = deviation["owner_role_id"]
    reasons = set()
    data_review = False
    selected_version = _select_sop(deviation, tables)
    if selected_version is None:
        data_review = True
        reasons.add("missing-sop-version")
        _issue(
            issues,
            "missing-sop-version",
            deviation_id,
            "No SOP version applies to the deviation opened date.",
            owner,
        )

    investigation = next(
        (
            row
            for row in tables["investigations"].values()
            if row["deviation_id"] == deviation_id
        ),
        None,
    )
    if investigation is None:
        reasons.add("missing-investigation")
        _issue(
            issues,
            "missing-investigation",
            deviation_id,
            "No investigation record exists for the deviation.",
            owner,
        )
    elif selected_version is not None and investigation["sop_version"] != selected_version:
        data_review = True
        reasons.add("sop-version-mismatch")
        _issue(
            issues,
            "sop-version-mismatch",
            deviation_id,
            "Investigation SOP version does not match the selected version.",
            owner,
        )

    due_date, due_state = _due_state(
        deviation,
        investigation,
        as_of,
        policy["investigation_due_days"],
        policy["due_soon_days"],
    )
    if due_state == "overdue":
        reasons.add("overdue-investigation")
        _issue(
            issues,
            "overdue-investigation",
            deviation_id,
            "Open investigation is past its sample-policy due date.",
            owner,
        )
    elif due_state == "completed-late":
        reasons.add("late-completion")
        _issue(
            issues,
            "late-completion",
            deviation_id,
            "Investigation completed after its sample-policy due date.",
            owner,
        )

    applicable = []
    if selected_version is not None:
        applicable = sorted(
            (
                row
                for row in tables["requirements"].values()
                if row["sop_version"] == selected_version
                and SEVERITY_RANK[row["minimum_severity"]]
                <= SEVERITY_RANK[deviation["severity"]]
            ),
            key=lambda row: row["requirement_id"],
        )

    investigation_evidence = []
    if investigation is not None:
        investigation_evidence = sorted(
            (
                row
                for row in tables["evidence"].values()
                if row["investigation_id"] == investigation["investigation_id"]
            ),
            key=lambda row: row["evidence_id"],
        )
        for item in investigation_evidence:
            if _date(item["recorded_on"], "recorded_on") > as_of:
                reasons.add("future-evidence")
                _issue(
                    issues,
                    "future-evidence",
                    deviation_id,
                    f"Evidence {item['evidence_id']} is after as_of_date and cannot satisfy a requirement.",
                    owner,
                )

    checks = []
    missing = False
    for requirement in applicable:
        evidence_ids = sorted(
            item["evidence_id"]
            for item in investigation_evidence
            if item["evidence_type"] == requirement["evidence_type"]
            and _date(item["recorded_on"], "recorded_on") <= as_of
        )
        state = "present" if evidence_ids else "missing"
        if not evidence_ids:
            missing = True
            reason = f"missing-{requirement['requirement_code']}"
            reasons.add(reason)
            _issue(
                issues,
                reason,
                deviation_id,
                f"Required evidence type {requirement['evidence_type']} is missing.",
                owner,
            )
        checks.append(
            {
                "requirement_id": requirement["requirement_id"],
                "requirement_code": requirement["requirement_code"],
                "evidence_type": requirement["evidence_type"],
                "state": state,
                "evidence_ids": evidence_ids,
            }
        )

    if data_review:
        review_state = "data-review"
    elif investigation is None:
        review_state = "missing-investigation"
    elif missing:
        review_state = "sop-gap"
    else:
        review_state = "administratively-complete"

    return {
        "deviation_id": deviation_id,
        "severity": deviation["severity"],
        "source_status": deviation["status"],
        "owner_role_id": owner,
        "opened_on": deviation["opened_on"],
        "due_date": due_date.isoformat(),
        "due_state": due_state,
        "selected_sop_version": selected_version,
        "investigation_id": investigation["investigation_id"] if investigation else None,
        "review_state": review_state,
        "reason_codes": sorted(reasons),
        "requirement_checks": checks,
    }


def _queue(reviews: list[dict], as_of: date, tables: dict, issues: list[dict]) -> list[dict]:
    eligible_tasks = []
    for task in tables["open_review_tasks"].values():
        if _date(task["opened_on"], "opened_on") <= as_of:
            eligible_tasks.append(task)
        else:
            _issue(
                issues,
                "future-review-task",
                task["deviation_id"],
                f"Review task {task['task_id']} is after as_of_date and cannot suppress draft work.",
            )

    rows = []
    for review in reviews:
        if not review["reason_codes"]:
            continue
        high = review["review_state"] in {"data-review", "missing-investigation"} or review[
            "due_state"
        ] == "overdue"
        medium = review["review_state"] == "sop-gap" or review["due_state"] in {
            "due-soon",
            "completed-late",
        }
        priority = "high" if high else ("medium" if medium else "normal")
        matching = sorted(
            (
                task
                for task in eligible_tasks
                if task["deviation_id"] == review["deviation_id"]
                and task["reason_code"] in review["reason_codes"]
            ),
            key=lambda task: task["task_id"],
        )
        suppressed = {task["reason_code"] for task in matching}
        draft_reasons = [
            reason for reason in review["reason_codes"] if reason not in suppressed
        ]
        if not draft_reasons:
            continue
        rows.append(
            {
                "rank": 0,
                "deviation_id": review["deviation_id"],
                "priority": priority,
                "owner_role_id": review["owner_role_id"],
                "reason_codes": review["reason_codes"],
                "existing_task_ids": [task["task_id"] for task in matching],
                "draft_reason_codes": draft_reasons,
                "approval_required": True,
                "deviation_update_authorized": False,
            }
        )
    rows.sort(key=lambda row: (PRIORITY_RANK[row["priority"]], row["deviation_id"]))
    for rank, row in enumerate(rows, start=1):
        row["rank"] = rank
    return rows


def solve(payload: object) -> tuple[dict, list[dict]]:
    events: list[dict] = []
    issues: list[dict] = []
    inventory_rows = [
        [name, len(payload.get(name, [])) if isinstance(payload, dict) and isinstance(payload.get(name), list) else None]
        for name in TABLE_NAMES
    ]
    _event(events, "intake", "input", "Synthetic export inventory", ["table", "raw_rows"], inventory_rows)

    try:
        as_of, policy, tables = _validate(payload, issues)
        _event(
            events,
            "validate",
            "validation",
            "Validated and deduplicated records",
            ["table", "unique_rows"],
            [[name, len(tables[name])] for name in TABLE_NAMES],
        )

        reviews = [
            _review_deviation(deviation, as_of, policy, tables, issues)
            for deviation in sorted(
                tables["deviations"].values(), key=lambda row: row["deviation_id"]
            )
        ]
        _event(
            events,
            "select-sop",
            "join",
            "Applicable SOP versions",
            ["deviation_id", "sop_version"],
            [[row["deviation_id"], row["selected_sop_version"]] for row in reviews],
        )
        _event(
            events,
            "join-evidence",
            "join",
            "Requirement and evidence matches",
            ["deviation_id", "requirements", "present"],
            [
                [
                    row["deviation_id"],
                    len(row["requirement_checks"]),
                    sum(check["state"] == "present" for check in row["requirement_checks"]),
                ]
                for row in reviews
            ],
        )
        _event(
            events,
            "evaluate-requirements",
            "decision",
            "Requirement decisions",
            ["deviation_id", "due_state", "missing"],
            [
                [
                    row["deviation_id"],
                    row["due_state"],
                    sum(check["state"] == "missing" for check in row["requirement_checks"]),
                ]
                for row in reviews
            ],
        )
        _event(
            events,
            "classify-review",
            "decision",
            "Deviation review classifications",
            ["deviation_id", "review_state"],
            [[row["deviation_id"], row["review_state"]] for row in reviews],
        )

        queue = _queue(reviews, as_of, tables, issues)
        sorted_issues = sorted(issues, key=lambda row: (row["code"], row["subject"], row["message"]))
        _event(
            events,
            "collect-exceptions",
            "exception",
            "Administrative exceptions",
            ["code", "subject"],
            [[row["code"], row["subject"]] for row in sorted_issues],
        )
        _event(
            events,
            "order-review",
            "decision",
            "Draft review queue",
            ["rank", "deviation_id", "priority"],
            [[row["rank"], row["deviation_id"], row["priority"]] for row in queue],
        )

        review_counts = Counter(row["review_state"] for row in reviews)
        due_counts = Counter(row["due_state"] for row in reviews)
        totals = {
            "deviation_count": len(reviews),
            "review_states": {name: review_counts[name] for name in REVIEW_STATES},
            "due_states": {name: due_counts[name] for name in DUE_STATES},
        }
        _event(
            events,
            "close-packet",
            "output",
            "Review-only packet totals",
            ["measure", "value"],
            [["deviations", len(reviews)], ["queue_rows", len(queue)], ["exceptions", len(sorted_issues)]],
            {"packet_state": "review-only"},
        )
        result = {
            "schema_version": 1,
            "status": "completed_with_exceptions" if sorted_issues else "completed",
            "outputs": {
                "as_of_date": as_of.isoformat(),
                "policy_id": policy["policy_id"],
                "packet_state": "review-only",
                "reviews": reviews,
                "draft_review_queue": queue,
                "totals": totals,
                "investigation_approval_authorized": False,
                "deviation_closure_authorized": False,
            },
            "exceptions": sorted_issues,
        }
        return result, events
    except BusinessError as error:
        report = error.report()
        _event(
            events,
            "validate",
            "validation",
            "Rejected invalid synthetic export",
            ["code", "subject"],
            [[report["code"], report["subject"]]],
        )
        _event(
            events,
            "collect-exceptions",
            "exception",
            "Rejection exception",
            ["code", "subject"],
            [[report["code"], report["subject"]]],
        )
        return {
            "schema_version": 1,
            "status": "rejected",
            "outputs": {},
            "exceptions": [report],
        }, events


if __name__ == "__main__":
    run_cli(solve, scenario_id="hls-04")
