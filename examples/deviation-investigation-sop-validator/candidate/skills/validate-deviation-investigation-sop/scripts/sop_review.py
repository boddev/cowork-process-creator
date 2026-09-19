"""Deterministic administrative review of a synthetic deviation-investigation export.

Standard library only. Reads one bounded JSON export, validates it against the
documented contract, joins SOP versions, investigations and evidence metadata,
and writes one NEW review-only JSON packet. It never overwrites an existing
file, never authenticates or assesses evidence content, never interprets
free-text narratives, and never approves, closes, notifies or writes anywhere
outside the single declared output path.
"""
from __future__ import annotations

import argparse
import json
import re
import sys

import markdown_review
from datetime import date, timedelta
from pathlib import Path

MAX_INPUT_BYTES = 8 * 1024 * 1024
MAX_DEPTH = 80
MIN_DATE = date(2000, 1, 1)
MAX_DATE = date(2100, 12, 31)
ID_PATTERN = re.compile(r"^SYN(?:-[A-Z0-9]+)+$")
CODE_PATTERN = re.compile(r"^[a-z][a-z0-9-]{0,39}$")
SEVERITY_RANK = {"minor": 0, "major": 1, "critical": 2}
DEVIATION_STATUS = {"open", "under-review", "closed"}
PRIORITY_ORDER = {"high": 0, "medium": 1, "normal": 2}

TOP_LEVEL = (
    "schema_version", "as_of_date", "policy", "sop_versions", "requirements",
    "deviations", "investigations", "evidence", "open_review_tasks",
)
POLICY_FIELDS = (
    "policy_id", "investigation_due_days", "due_soon_days",
    "max_rows_per_table", "max_total_rows",
)
TABLES = (
    ("sop_versions", "sop_version",
     ("sop_version", "effective_from", "effective_to")),
    ("requirements", "requirement_id",
     ("requirement_id", "sop_version", "minimum_severity", "requirement_code", "evidence_type")),
    ("deviations", "deviation_id",
     ("deviation_id", "opened_on", "occurred_on", "department_code", "severity", "owner_role_id", "status")),
    ("investigations", "investigation_id",
     ("investigation_id", "deviation_id", "sop_version", "started_on", "completed_on")),
    ("evidence", "evidence_id",
     ("evidence_id", "investigation_id", "evidence_type", "recorded_on", "source_ref")),
    ("open_review_tasks", "task_id",
     ("task_id", "deviation_id", "reason_code", "opened_on")),
)


class InputError(ValueError):
    """A precise bounded-input failure; never a success-shaped substitute."""

    def __init__(self, message: str, code: str = "invalid-input", subject: str = "packet") -> None:
        super().__init__(message)
        self.code = code
        self.subject = subject


class PacketRejected(InputError):
    """The whole packet is rejected before or during business joins."""


# ---------------------------------------------------------------- JSON intake

def _unique(pairs: list) -> dict:
    result: dict = {}
    for key, value in pairs:
        if key in result:
            raise InputError(f"JSON contains a duplicate object key: {key!r}.")
        result[key] = value
    return result


def _nonfinite(value: str) -> None:
    raise InputError("Non-finite JSON numbers are not supported.")


def load_json(path: Path, max_bytes: int = MAX_INPUT_BYTES, max_depth: int = MAX_DEPTH) -> object:
    path = Path(path)
    if not path.is_file():
        raise InputError(f"Input file not found: {path}.", "missing-input")
    with path.open("rb") as handle:
        content = handle.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise InputError(f"Input exceeds the declared {max_bytes}-byte limit.", "oversized-input")
    try:
        data = json.loads(content.decode("utf-8"), object_pairs_hook=_unique, parse_constant=_nonfinite)
    except UnicodeDecodeError as exc:
        raise InputError("Input JSON must be UTF-8.") from exc
    except json.JSONDecodeError as exc:
        raise InputError(f"Invalid JSON at line {exc.lineno}, column {exc.colno}.") from exc
    except RecursionError as exc:
        raise InputError("JSON nesting exceeds parser limits.") from exc
    except ValueError as exc:
        if isinstance(exc, InputError):
            raise
        raise InputError("JSON number exceeds parser limits.") from exc
    pending = [(data, 0)]
    while pending:
        value, depth = pending.pop()
        if depth > max_depth:
            raise InputError(f"JSON nesting exceeds the declared {max_depth}-level limit.")
        if isinstance(value, dict):
            pending.extend((item, depth + 1) for item in value.values())
        elif isinstance(value, list):
            pending.extend((item, depth + 1) for item in value)
    return data


def write_new_text(path: Path, content: str) -> None:
    try:
        encoded = content.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise InputError("Output contains invalid Unicode and cannot be encoded as UTF-8.") from exc
    path = Path(path)
    stream = path.open("xb")
    try:
        with stream:
            stream.write(encoded)
    except OSError:
        path.unlink(missing_ok=True)
        raise


# ------------------------------------------------------------ field checking

def require(condition: bool, message: str, subject: str = "packet", code: str = "invalid-input") -> None:
    if not condition:
        raise InputError(message, code, subject)


def as_integer(value: object, low: int, high: int, label: str) -> int:
    require(type(value) is int and low <= value <= high,
            f"{label} must be an integer {low}-{high}.", label)
    return int(value)


def as_identifier(value: object, label: str) -> str:
    require(isinstance(value, str) and len(value) <= 64 and bool(ID_PATTERN.fullmatch(value)),
            f"{label} must be an uppercase SYN- identifier of at most 64 characters.", label)
    return str(value)


def as_code(value: object, label: str) -> str:
    require(isinstance(value, str) and bool(CODE_PATTERN.fullmatch(value)),
            label + " must match the lowercase code grammar [a-z][a-z0-9-] of at most 40 characters.", label)
    return str(value)


def as_date(value: object, label: str) -> date:
    require(isinstance(value, str) and bool(re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value)),
            f"{label} must be a YYYY-MM-DD date.", label)
    try:
        parsed = date.fromisoformat(str(value))
    except ValueError as exc:
        raise InputError(f"{label} is not a real Gregorian date.", "invalid-input", label) from exc
    require(MIN_DATE <= parsed <= MAX_DATE,
            f"{label} must fall between 2000-01-01 and 2100-12-31.", label)
    return parsed


def as_choice(value: object, allowed: set, label: str) -> str:
    require(isinstance(value, str) and value in allowed,
            f"{label} must be one of {sorted(allowed)}.", label)
    return str(value)


def exact_object(value: object, fields: tuple, label: str) -> dict:
    require(isinstance(value, dict), f"{label} must be a JSON object.", label)
    require(set(value) == set(fields),
            f"{label} must contain exactly {sorted(fields)}.", label)
    return dict(value)


# ------------------------------------------------------------- packet loading

def validate_packet(raw: object) -> dict:
    require(isinstance(raw, dict), "The export must be a single JSON object.")
    require(set(raw) == set(TOP_LEVEL),
            f"The top level must contain exactly {sorted(TOP_LEVEL)}.", "top-level")
    require(type(raw["schema_version"]) is int and raw["schema_version"] == 1,
            "schema_version must be integer 1.", "schema_version")
    as_of = as_date(raw["as_of_date"], "as_of_date")

    policy_raw = exact_object(raw["policy"], POLICY_FIELDS, "policy")
    policy = {
        "policy_id": as_identifier(policy_raw["policy_id"], "policy.policy_id"),
        "investigation_due_days": as_integer(policy_raw["investigation_due_days"], 0, 3650, "policy.investigation_due_days"),
        "due_soon_days": as_integer(policy_raw["due_soon_days"], 0, 365, "policy.due_soon_days"),
        "max_rows_per_table": as_integer(policy_raw["max_rows_per_table"], 1, 1000, "policy.max_rows_per_table"),
        "max_total_rows": as_integer(policy_raw["max_total_rows"], 1, 5000, "policy.max_total_rows"),
    }
    require(policy["due_soon_days"] <= policy["investigation_due_days"],
            "policy.due_soon_days must not exceed policy.investigation_due_days.", "policy.due_soon_days")

    # Raw ceilings are checked before any duplicate collapse.
    total = 0
    for name, _key, _fields in TABLES:
        rows = raw[name]
        require(isinstance(rows, list), f"{name} must be a JSON array.", name)
        require(len(rows) <= policy["max_rows_per_table"],
                f"{name} has {len(rows)} raw rows, above max_rows_per_table "
                f"({policy['max_rows_per_table']}).", name, "row-ceiling-exceeded")
        total += len(rows)
    require(total <= policy["max_total_rows"],
            f"The packet has {total} raw rows, above max_total_rows ({policy['max_total_rows']}).",
            "packet", "row-ceiling-exceeded")
    return {"as_of_date": as_of, "policy": policy, "raw": raw, "raw_total_rows": total}


def check_row(table: str, row: dict) -> dict:
    label = table
    if table == "sop_versions":
        checked = {
            "sop_version": as_integer(row["sop_version"], 1, 1_000_000, f"{label}.sop_version"),
            "effective_from": as_date(row["effective_from"], f"{label}.effective_from"),
            "effective_to": None if row["effective_to"] is None else as_date(row["effective_to"], f"{label}.effective_to"),
        }
        if checked["effective_to"] is not None:
            require(checked["effective_from"] <= checked["effective_to"],
                    f"{label}.effective_to must not precede effective_from.", label)
        return checked
    if table == "requirements":
        return {
            "requirement_id": as_identifier(row["requirement_id"], f"{label}.requirement_id"),
            "sop_version": as_integer(row["sop_version"], 1, 1_000_000, f"{label}.sop_version"),
            "minimum_severity": as_choice(row["minimum_severity"], set(SEVERITY_RANK), f"{label}.minimum_severity"),
            "requirement_code": as_code(row["requirement_code"], f"{label}.requirement_code"),
            "evidence_type": as_code(row["evidence_type"], f"{label}.evidence_type"),
        }
    if table == "deviations":
        return {
            "deviation_id": as_identifier(row["deviation_id"], f"{label}.deviation_id"),
            "opened_on": as_date(row["opened_on"], f"{label}.opened_on"),
            "occurred_on": as_date(row["occurred_on"], f"{label}.occurred_on"),
            "department_code": as_code(row["department_code"], f"{label}.department_code"),
            "severity": as_choice(row["severity"], set(SEVERITY_RANK), f"{label}.severity"),
            "owner_role_id": as_identifier(row["owner_role_id"], f"{label}.owner_role_id"),
            "status": as_choice(row["status"], DEVIATION_STATUS, f"{label}.status"),
        }
    if table == "investigations":
        return {
            "investigation_id": as_identifier(row["investigation_id"], f"{label}.investigation_id"),
            "deviation_id": as_identifier(row["deviation_id"], f"{label}.deviation_id"),
            "sop_version": as_integer(row["sop_version"], 1, 1_000_000, f"{label}.sop_version"),
            "started_on": as_date(row["started_on"], f"{label}.started_on"),
            "completed_on": None if row["completed_on"] is None else as_date(row["completed_on"], f"{label}.completed_on"),
        }
    if table == "evidence":
        return {
            "evidence_id": as_identifier(row["evidence_id"], f"{label}.evidence_id"),
            "investigation_id": as_identifier(row["investigation_id"], f"{label}.investigation_id"),
            "evidence_type": as_code(row["evidence_type"], f"{label}.evidence_type"),
            "recorded_on": as_date(row["recorded_on"], f"{label}.recorded_on"),
            "source_ref": as_identifier(row["source_ref"], f"{label}.source_ref"),
        }
    return {
        "task_id": as_identifier(row["task_id"], f"{label}.task_id"),
        "deviation_id": as_identifier(row["deviation_id"], f"{label}.deviation_id"),
        "reason_code": as_code(row["reason_code"], f"{label}.reason_code"),
        "opened_on": as_date(row["opened_on"], f"{label}.opened_on"),
    }


def collapse_table(table: str, key: str, fields: tuple, rows: list, exceptions: list) -> dict:
    collected: dict = {}
    for index, row in enumerate(rows):
        exact_object(row, fields, f"{table}[{index}]")
        checked = check_row(table, row)
        identifier = checked[key] if key != "sop_version" else str(checked[key])
        if identifier in collected:
            if collected[identifier] == checked:
                add_exception(exceptions, "duplicate-record", identifier,
                              f"Identical {table} row collapsed into one record.")
                continue
            raise PacketRejected(
                f"Different {table} rows share the primary identifier {identifier}.",
                "contradictory-evidence", identifier)
        collected[identifier] = checked
    return collected


def add_exception(exceptions: list, code: str, subject: str, message: str) -> None:
    entry = {"code": code, "subject": subject, "message": message}
    if entry not in exceptions:
        exceptions.append(entry)


# ------------------------------------------------------------------- analysis

def review_packet(packet: dict) -> dict:
    as_of = packet["as_of_date"]
    policy = packet["policy"]
    raw = packet["raw"]
    exceptions: list = []

    tables = {}
    for name, key, fields in TABLES:
        tables[name] = collapse_table(name, key, fields, raw[name], exceptions)

    sop_versions = tables["sop_versions"]
    requirements = tables["requirements"]
    deviations = tables["deviations"]
    investigations = tables["investigations"]
    evidence = tables["evidence"]
    tasks = tables["open_review_tasks"]

    investigations_by_deviation: dict = {}
    for investigation in investigations.values():
        investigations_by_deviation.setdefault(investigation["deviation_id"], []).append(investigation)
    for deviation_id, joined in investigations_by_deviation.items():
        if len(joined) > 1:
            raise PacketRejected(
                f"Deviation {deviation_id} has {len(joined)} investigations; exactly one may join.",
                "contradictory-evidence", deviation_id)

    for investigation_id in sorted(investigations):
        row = investigations[investigation_id]
        if row["deviation_id"] not in deviations:
            add_exception(exceptions, "unknown-reference", investigation_id,
                          f"Investigation references unknown deviation {row['deviation_id']}; it owns no review row.")

    evidence_by_investigation: dict = {}
    for evidence_id in sorted(evidence):
        row = evidence[evidence_id]
        evidence_by_investigation.setdefault(row["investigation_id"], []).append(row)
        if row["investigation_id"] not in investigations:
            add_exception(exceptions, "unknown-reference", evidence_id,
                          f"Evidence references unknown investigation {row['investigation_id']}; "
                          "it cannot satisfy any requirement and owns no review row.")
        if row["recorded_on"] > as_of:
            add_exception(exceptions, "future-evidence", evidence_id,
                          f"Evidence recorded {row['recorded_on'].isoformat()} is after the as-of date "
                          f"{as_of.isoformat()} and cannot satisfy a requirement.")

    tasks_by_deviation: dict = {}
    for task_id in sorted(tasks):
        task = tasks[task_id]
        tasks_by_deviation.setdefault(task["deviation_id"], []).append(task)
        if task["deviation_id"] not in deviations:
            add_exception(exceptions, "unknown-reference", task_id,
                          f"Open review task references unknown deviation {task['deviation_id']}; "
                          "it suppresses nothing and owns no review row.")

    reviews = []
    queue = []
    for deviation_id in sorted(deviations):
        deviation = deviations[deviation_id]
        opened = deviation["opened_on"]
        reasons: set = set()
        data_review = False

        matches = [row for row in sop_versions.values()
                   if row["effective_from"] <= opened and (row["effective_to"] is None or opened <= row["effective_to"])]
        if len(matches) > 1:
            raise PacketRejected(
                f"Deviation {deviation_id} matches {len(matches)} SOP version intervals; exactly one may apply.",
                "contradictory-evidence", deviation_id)
        selected_version = matches[0]["sop_version"] if matches else None
        if selected_version is None:
            data_review = True
            reasons.add("missing-sop-version")
            add_exception(exceptions, "missing-sop-version", deviation_id,
                          f"No effective SOP interval contains the opened date {opened.isoformat()}.")

        joined = investigations_by_deviation.get(deviation_id, [])
        investigation = joined[0] if joined else None
        if investigation is None:
            reasons.add("missing-investigation")
            add_exception(exceptions, "missing-investigation", deviation_id,
                          "No investigation joins this deviation.")
        elif selected_version is not None and investigation["sop_version"] != selected_version:
            data_review = True
            reasons.add("sop-version-mismatch")
            add_exception(exceptions, "sop-version-mismatch", deviation_id,
                          f"Investigation {investigation['investigation_id']} declares SOP version "
                          f"{investigation['sop_version']} but version {selected_version} applies.")

        due_date = opened + timedelta(days=policy["investigation_due_days"])
        if investigation is not None and investigation["completed_on"] is not None:
            due_state = "completed-late" if investigation["completed_on"] > due_date else "completed-on-time"
        elif as_of > due_date:
            due_state = "overdue"
        elif (due_date - as_of).days <= policy["due_soon_days"]:
            due_state = "due-soon"
        else:
            due_state = "on-track"
        if due_state in {"overdue", "due-soon"}:
            reasons.add(due_state)
        elif due_state == "completed-late":
            # "completed-late" is the due-state value only; the reason code is
            # "late-completion", and a late completion is also an exception.
            reasons.add("late-completion")
            add_exception(exceptions, "late-completion", deviation_id,
                          f"Investigation {investigation['investigation_id']} completed "
                          f"{investigation['completed_on'].isoformat()}, after the due date "
                          f"{due_date.isoformat()}.")

        applicable = sorted(
            (row for row in requirements.values()
             if selected_version is not None
             and row["sop_version"] == selected_version
             and SEVERITY_RANK[row["minimum_severity"]] <= SEVERITY_RANK[deviation["severity"]]),
            key=lambda row: row["requirement_id"])

        checks = []
        gaps = 0
        for requirement in applicable:
            eligible = []
            if investigation is not None:
                eligible = [row for row in evidence_by_investigation.get(investigation["investigation_id"], [])
                            if row["evidence_type"] == requirement["evidence_type"] and row["recorded_on"] <= as_of]
                eligible.sort(key=lambda row: (row["recorded_on"], row["evidence_id"]))
            if not eligible:
                gaps += 1
                reasons.add("missing-" + requirement["requirement_code"])
            checks.append({
                "evidence_ids": [row["evidence_id"] for row in eligible],
                "evidence_type": requirement["evidence_type"],
                "requirement_code": requirement["requirement_code"],
                "requirement_id": requirement["requirement_id"],
                "state": "present" if eligible else "missing",
            })

        if data_review:
            review_state = "data-review"
        elif investigation is None:
            review_state = "missing-investigation"
        elif gaps:
            review_state = "sop-gap"
        else:
            review_state = "administratively-complete"

        reason_codes = sorted(reasons)
        reviews.append({
            "deviation_id": deviation_id,
            "due_date": due_date.isoformat(),
            "due_state": due_state,
            "investigation_id": None if investigation is None else investigation["investigation_id"],
            "opened_on": opened.isoformat(),
            "owner_role_id": deviation["owner_role_id"],
            "reason_codes": reason_codes,
            "requirement_checks": checks,
            "review_state": review_state,
            "selected_sop_version": selected_version,
            "severity": deviation["severity"],
            "source_status": deviation["status"],
        })

        existing = sorted(tasks_by_deviation.get(deviation_id, []), key=lambda row: row["task_id"])
        suppressing = {row["reason_code"] for row in existing if row["opened_on"] <= as_of}
        for row in existing:
            if row["opened_on"] > as_of:
                add_exception(exceptions, "future-task", row["task_id"],
                              f"Open review task opened {row['opened_on'].isoformat()} is after the as-of date "
                              f"and does not suppress a draft reason.")
        suppressed = sorted(suppressing & set(reason_codes))
        drafts = [code for code in reason_codes if code not in suppressing]
        if not drafts:
            continue
        if review_state in {"missing-investigation", "data-review"} or due_state == "overdue":
            priority = "high"
        elif review_state == "sop-gap" or due_state in {"due-soon", "completed-late"}:
            priority = "medium"
        else:
            priority = "normal"
        queue.append({
            "deviation_id": deviation_id,
            "priority": priority,
            "review_state": review_state,
            "due_state": due_state,
            "existing_task_ids": [row["task_id"] for row in existing],
            "suppressed_reason_codes": suppressed,
            "draft_reason_codes": drafts,
            "approval_required": True,
            "deviation_update_authorized": False,
        })

    queue.sort(key=lambda row: (PRIORITY_ORDER[row["priority"]], row["deviation_id"]))
    ranked = []
    for position, row in enumerate(queue, start=1):
        ranked.append({"rank": position, **row})
    exceptions.sort(key=lambda row: (row["code"], row["subject"], row["message"]))

    def tally(field: str, values: tuple) -> dict:
        counts = {value: 0 for value in values}
        for row in reviews:
            counts[row[field]] += 1
        return counts

    totals = {
        "deviations": len(deviations),
        "reviews": len(reviews),
        "review_states": tally("review_state",
                               ("administratively-complete", "sop-gap", "missing-investigation", "data-review")),
        "due_states": tally("due_state",
                            ("on-track", "due-soon", "overdue", "completed-on-time", "completed-late")),
        "queue_rows": len(ranked),
        "queue_priorities": {name: sum(1 for row in ranked if row["priority"] == name)
                             for name in ("high", "medium", "normal")},
        "requirement_checks": sum(len(row["requirement_checks"]) for row in reviews),
        "exceptions": len(exceptions),
    }
    return {
        "schema_version": 1,
        "status": "completed_with_exceptions" if exceptions else "completed",
        "outputs": {
            "as_of_date": as_of.isoformat(),
            "policy_id": policy["policy_id"],
            "packet_state": "review-only",
            "reviews": reviews,
            "draft_review_queue": ranked,
            "totals": totals,
            "investigation_approval_authorized": False,
            "deviation_closure_authorized": False,
        },
        "exceptions": exceptions,
    }


def rejected_packet(error: InputError) -> dict:
    return {
        "schema_version": 1,
        "status": "rejected",
        "outputs": {},
        "exceptions": [{"code": error.code, "subject": error.subject, "message": str(error)}],
    }


def check_new_output(path: Path, suffix: str) -> Path:
    path = Path(path)
    if path.exists() or path.is_symlink():
        raise InputError(f"Output file already exists and must not be overwritten: {path}.",
                         "output-exists", str(path))
    require(path.suffix == suffix, f"The output filename must end with {suffix}.",
            str(path), "invalid-output-path")
    require(path.parent.is_dir(), f"Output directory does not exist: {path.parent}.",
            str(path), "invalid-output-path")
    return path


def run(input_path: Path, output_path: Path, markdown_path: Path) -> tuple[dict, int]:
    # Both destinations are checked before either is written, so a collision on
    # one path never leaves a partial artefact behind at the other.
    output_path = check_new_output(output_path, ".json")
    markdown_path = check_new_output(markdown_path, ".md")
    require(output_path.resolve() != markdown_path.resolve(),
            "The JSON and Markdown outputs must be distinct files.", str(output_path), "invalid-output-path")
    raw = load_json(input_path)
    try:
        packet = review_packet(validate_packet(raw))
        exit_code = 0
    except PacketRejected as exc:
        packet, exit_code = rejected_packet(exc), 2
    except InputError as exc:
        packet, exit_code = rejected_packet(exc), 2
    document = markdown_review.render(packet, str(input_path))
    write_new_text(output_path, json.dumps(packet, indent=2, ensure_ascii=False) + "\n")
    try:
        write_new_text(markdown_path, document)
    except (OSError, InputError):
        output_path.unlink(missing_ok=True)
        raise
    return packet, exit_code


def main(argv: list | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path,
                        help="Path to the structured JSON deviation-investigation export.")
    parser.add_argument("--output", required=True, type=Path,
                        help="New .json filename for the review packet; an existing file is never overwritten.")
    parser.add_argument("--markdown", required=True, type=Path,
                        help="New .md filename for the human-readable administrative review.")
    args = parser.parse_args(argv)
    try:
        packet, exit_code = run(args.input, args.output, args.markdown)
    except InputError as exc:
        json.dump({"schema_version": 1, "status": "rejected", "outputs": {},
                   "exceptions": [{"code": exc.code, "subject": exc.subject, "message": str(exc)}]},
                  sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 2
    except OSError as exc:
        json.dump({"schema_version": 1, "status": "rejected", "outputs": {},
                   "exceptions": [{"code": "io-error", "subject": "packet",
                                   "message": f"Could not complete the run: {exc.strerror}."}]},
                  sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 2
    summary = {
        "status": packet["status"],
        "output_path": str(args.output),
        "markdown_path": str(args.markdown),
        "reviews": packet["outputs"].get("totals", {}).get("reviews", 0),
        "queue_rows": packet["outputs"].get("totals", {}).get("queue_rows", 0),
        "exceptions": len(packet["exceptions"]),
        "packet_state": packet["outputs"].get("packet_state", "rejected"),
        "investigation_approval_authorized": False,
        "deviation_closure_authorized": False,
    }
    json.dump(summary, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
