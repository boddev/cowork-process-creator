"""Independent, synthetic bank/ledger review logic; no financial side effects."""
from collections import defaultdict
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "_shared"))
from scenario_support import run_cli


MONEY_LIMIT = 1_000_000_000_000
EDGE_LIMIT = 100_000
ID = re.compile(r"SYN-[A-Z0-9][A-Z0-9-]{0,63}\Z")
CODE = re.compile(r"[A-Z][A-Z0-9-]{0,31}\Z")
DAY = re.compile(r"\d{4}-\d{2}-\d{2}\Z", re.ASCII)
INSTANT = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?"
    r"(?:Z|[+-]\d{2}:\d{2})\Z", re.ASCII
)
REVIEW = {"human_review": "pending", "live_action": "none"}
MESSAGES = {
    "ambiguous-match": "Multiple eligible candidates require manual matching.",
    "batch-incomplete": "Batch evidence is incomplete or unavailable at cutoff.",
    "batch-mismatch": "Batch amount, type, or date constraints are not satisfied.",
    "unmapped-code": "Bank code has no approved mapping.",
    "missing-reference": "A nonempty reference is required for single matching.",
    "no-counterpart": "No eligible same-scope reference counterpart was supplied.",
    "type-mismatch": "Reference candidates have incompatible transaction types.",
    "date-mismatch": "Reference/type candidates exceed the date window.",
    "amount-mismatch": "Reference/type candidates exceed the amount tolerance.",
    "bank-only-fee": "Bank-only fee requires a separate source-owner review.",
    "pending-clearance": "Expected clearing is after cutoff within the configured grace window.",
    "stale-ledger": "Unmatched ledger age exceeds the configured staleness window.",
    "pending-correction": "Candidate penny difference requires controller review; no posting.",
    "opening-difference": "Bank and ledger opening balances differ.",
}
CONFIG_FIELDS = {
    "control_version", "approval_state", "as_of", "business_utc_offset_minutes",
    "cutoff_date", "max_match_calendar_days", "single_amount_tolerance_minor",
    "timing_grace_calendar_days", "stale_after_calendar_days", "max_rows_per_source",
}
SCOPE_FIELDS = {
    "scope_id", "legal_entity_id", "account_id", "statement_id", "currency",
    "from_date", "through_date", "prior_statement_through_date",
    "bank_opening_minor", "bank_closing_minor", "prior_bank_closing_minor",
    "ledger_opening_minor", "ledger_closing_minor", "bank_sign", "ledger_sign",
}
BANK_FIELDS = {
    "bank_line_id", "scope_id", "booked_at", "amount_minor", "bank_code", "reference", "batch_id",
}
LEDGER_FIELDS = {
    "ledger_line_id", "scope_id", "posted_at", "amount_minor", "ledger_type",
    "reference", "expected_bank_date",
}
SOURCES = ("scopes", "bank_lines", "ledger_lines", "mappings", "batches")


class BusinessError(ValueError):
    def __init__(self, code, message, scope_id=None, record_id="input"):
        super().__init__(message)
        self.diagnostic = {
            "scope_id": scope_id, "record_id": record_id, "code": code, "message": message,
        }


def malformed(message):
    raise BusinessError("malformed-input", message)


def shape(value, fields, label):
    if not isinstance(value, dict):
        malformed(f"{label} must be an object.")
    missing = sorted(fields - value.keys())
    extra = sorted(value.keys() - fields)
    if missing or extra:
        malformed(f"{label} fields differ: missing {missing}; unknown {extra}.")


def integer(value, lower, upper, label):
    if type(value) is not int or not lower <= value <= upper:
        malformed(f"{label} must be a true integer in [{lower}, {upper}].")


def identifier(value, label):
    if not isinstance(value, str) or not ID.fullmatch(value):
        malformed(f"{label} must be a synthetic SYN- identifier.")


def code(value, label):
    if not isinstance(value, str) or not CODE.fullmatch(value):
        malformed(f"{label} must be an uppercase ASCII transaction code.")


def calendar_date(value, label):
    if not isinstance(value, str) or not DAY.fullmatch(value):
        malformed(f"{label} must be a YYYY-MM-DD date.")
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise BusinessError("malformed-input", f"{label} must be a valid calendar date.") from error


def timestamp(value, label):
    if not isinstance(value, str) or not INSTANT.fullmatch(value) or value.endswith("-00:00"):
        malformed(f"{label} must be an offset-bearing RFC3339 instant with known offset.")
    if value[-1] != "Z":
        hours, minutes = int(value[-5:-3]), int(value[-2:])
        if hours > 14 or minutes > 59 or (hours == 14 and minutes):
            malformed(f"{label} UTC offset must be at most 14 hours.")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise BusinessError("malformed-input", f"{label} must be a valid calendar instant.") from error


def local_date(instant, zone, label):
    try:
        return instant.astimezone(zone).date()
    except (OverflowError, ValueError) as error:
        raise BusinessError("malformed-input", f"{label} is outside the supported local calendar.") from error


def reference(value, label):
    if not isinstance(value, str) or not value.isascii() or len(value) > 128:
        malformed(f"{label} must be an ASCII string of at most 128 characters.")
    return value.strip(" \t\r\n\v\f").upper()


def unique(key, seen, label):
    if key in seen:
        raise BusinessError("duplicate-key", f"{label} repeats a technical key.")
    seen.add(key)


def integrity(condition, message, scope_id):
    if not condition:
        raise BusinessError("contradictory-evidence", message, scope_id, scope_id)


def event(events, step_id, kind, caption, facts, title, columns, rows):
    display = deepcopy(rows[:8])
    if len(rows) > 8:
        title += " (first 8; total shown)"
    events.append({
        "step_id": step_id, "kind": kind, "caption": caption, "facts": facts,
        "tables": [{
            "title": title, "columns": columns, "rows": display,
            "total_rows": len(rows), "highlight_rows": [0] if display else [],
        }],
    })


def id_preview(values):
    return ", ".join(values[:2]) + (f" (+{len(values) - 2} more)" if len(values) > 2 else "")


def prepare(payload):
    shape(payload, {"schema_version", "synthetic", "config", *SOURCES}, "input")
    integer(payload["schema_version"], 1, 1, "schema_version")
    if payload["synthetic"] is not True:
        malformed("synthetic must be true.")
    config = payload["config"]
    shape(config, CONFIG_FIELDS, "config")
    identifier(config["control_version"], "config.control_version")
    if config["approval_state"] not in ("approved", "pending"):
        malformed("config.approval_state must be approved or pending.")
    integer(config["business_utc_offset_minutes"], -840, 840, "config.business_utc_offset_minutes")
    integer(config["max_rows_per_source"], 1, 5000, "config.max_rows_per_source")
    for field in ("max_match_calendar_days", "timing_grace_calendar_days", "stale_after_calendar_days"):
        integer(config[field], 0, 366, "config." + field)
    integer(config["single_amount_tolerance_minor"], 0, MONEY_LIMIT, "config.single_amount_tolerance_minor")
    as_of = timestamp(config["as_of"], "config.as_of")
    cutoff = calendar_date(config["cutoff_date"], "config.cutoff_date")
    zone = timezone(timedelta(minutes=config["business_utc_offset_minutes"]))
    if cutoff > local_date(as_of, zone, "config.as_of"):
        malformed("config.cutoff_date must not be after the local as_of date.")
    if config["approval_state"] == "pending":
        raise BusinessError("policy-not-approved", "Synthetic control configuration is pending approval.")
    for name in SOURCES:
        rows = payload[name]
        if not isinstance(rows, list) or len(rows) > config["max_rows_per_source"]:
            malformed(f"{name} must be an array within max_rows_per_source.")
    if not payload["scopes"]:
        malformed("scopes must contain at least one scope.")

    scopes, seen, natural = {}, set(), set()
    for index, row in enumerate(payload["scopes"]):
        label = f"scopes[{index}]"
        shape(row, SCOPE_FIELDS, label)
        for field in ("scope_id", "legal_entity_id", "account_id", "statement_id"):
            identifier(row[field], label + "." + field)
        unique(row["scope_id"], seen, label)
        unique(tuple(row[field] for field in ("legal_entity_id", "account_id", "statement_id")), natural, label)
        if row["currency"] not in ("USD", "EUR"):
            malformed(label + ".currency must be USD or EUR.")
        for field in ("bank_sign", "ledger_sign"):
            integer(row[field], -1, 1, label + "." + field)
            if row[field] == 0:
                malformed(label + "." + field + " must be -1 or 1.")
        normalized = dict(row)
        for field in (
            "bank_opening_minor", "bank_closing_minor", "prior_bank_closing_minor",
            "ledger_opening_minor", "ledger_closing_minor",
        ):
            integer(row[field], -MONEY_LIMIT, MONEY_LIMIT, label + "." + field)
            normalized[field] *= row["ledger_sign"] if field.startswith("ledger_") else row["bank_sign"]
        for field in ("from_date", "through_date", "prior_statement_through_date"):
            normalized["_" + field] = calendar_date(row[field], label + "." + field)
        scopes[row["scope_id"]] = normalized

    raw_bank, raw_ledger = [], []
    for name, fields, id_key, time_key, type_key, target in (
        ("bank_lines", BANK_FIELDS, "bank_line_id", "booked_at", "bank_code", raw_bank),
        ("ledger_lines", LEDGER_FIELDS, "ledger_line_id", "posted_at", "ledger_type", raw_ledger),
    ):
        seen = set()
        for index, row in enumerate(payload[name]):
            label = f"{name}[{index}]"
            shape(row, fields, label)
            identifier(row[id_key], label + "." + id_key)
            identifier(row["scope_id"], label + ".scope_id")
            unique(row[id_key], seen, label)
            instant = timestamp(row[time_key], label + "." + time_key)
            integer(row["amount_minor"], -MONEY_LIMIT, MONEY_LIMIT, label + ".amount_minor")
            code(row[type_key], label + "." + type_key)
            canonical = reference(row["reference"], label + ".reference")
            if name == "bank_lines" and row["batch_id"] is not None:
                identifier(row["batch_id"], label + ".batch_id")
            if name == "ledger_lines" and row["expected_bank_date"] is not None:
                calendar_date(row["expected_bank_date"], label + ".expected_bank_date")
            target.append(dict(row, _instant=instant, _date=local_date(instant, zone, label), _reference=canonical))

    mappings, seen = {}, set()
    for index, row in enumerate(payload["mappings"]):
        label = f"mappings[{index}]"
        shape(row, {"scope_id", "bank_code", "ledger_type"}, label)
        identifier(row["scope_id"], label + ".scope_id")
        code(row["bank_code"], label + ".bank_code")
        code(row["ledger_type"], label + ".ledger_type")
        key = row["scope_id"], row["bank_code"]
        unique(key, seen, label)
        mappings[key] = row["ledger_type"]
    batches, seen, reserved = {}, set(), set()
    for index, row in enumerate(payload["batches"]):
        label = f"batches[{index}]"
        shape(row, {"scope_id", "batch_id", "member_ledger_ids"}, label)
        identifier(row["scope_id"], label + ".scope_id")
        identifier(row["batch_id"], label + ".batch_id")
        key = row["scope_id"], row["batch_id"]
        unique(key, seen, label)
        members = row["member_ledger_ids"]
        if not isinstance(members, list) or not 1 <= len(members) <= config["max_rows_per_source"]:
            malformed(label + ".member_ledger_ids must be a nonempty bounded array.")
        for member in members:
            identifier(member, label + ".member_ledger_ids")
            unique(member, reserved, label + ".member_ledger_ids")
        batches[key] = sorted(members)

    for row in [*raw_bank, *raw_ledger, *payload["mappings"], *payload["batches"]]:
        integrity(row["scope_id"] in scopes, "Referenced scope does not exist.", row["scope_id"])
    all_ledger = {row["ledger_line_id"]: row for row in raw_ledger}
    for (scope_id, _), members in batches.items():
        for member in members:
            integrity(member in all_ledger, "Manifest references a missing ledger row.", scope_id)
            integrity(all_ledger[member]["scope_id"] == scope_id, "Manifest member belongs to another scope.", scope_id)

    ordered = sorted(scopes.values(), key=lambda row: (
        row["legal_entity_id"], row["account_id"], row["currency"], row["scope_id"],
    ))
    rank = {row["scope_id"]: index for index, row in enumerate(ordered)}
    accounts = defaultdict(list)
    for row in ordered:
        scope_id = row["scope_id"]
        integrity(row["_from_date"] <= row["_through_date"] == cutoff, "Statement period must be ordered and end at cutoff.", scope_id)
        integrity((row["_from_date"] - row["_prior_statement_through_date"]).days == 1, "Previous statement must end one day before this period.", scope_id)
        integrity(row["bank_opening_minor"] == row["prior_bank_closing_minor"], "Bank opening does not equal the previous bank close.", scope_id)
        key = row["legal_entity_id"], row["account_id"]
        for previous in accounts[key]:
            integrity(previous["currency"] == row["currency"], "Account currency is contradictory across scopes.", scope_id)
            integrity(
                row["_through_date"] < previous["_from_date"] or row["_from_date"] > previous["_through_date"],
                "Statement periods overlap for an account.", scope_id,
            )
        accounts[key].append(row)

    bank, ledger, excluded = [], [], []
    for row in raw_bank:
        scope = scopes[row["scope_id"]]
        integrity(scope["_from_date"] <= row["_date"] <= scope["_through_date"], "Bank line date is outside its statement period.", row["scope_id"])
        integrity(row["_instant"] <= as_of, "Bank line is after as_of.", row["scope_id"])
        row["amount_minor"] *= scope["bank_sign"]
        row["_type"] = mappings.get((row["scope_id"], row["bank_code"]))
        bank.append(row)
    for row in raw_ledger:
        scope = scopes[row["scope_id"]]
        row["amount_minor"] *= scope["ledger_sign"]
        reason = None
        if row["_instant"] > as_of:
            reason = "after-as-of"
        elif not scope["_from_date"] <= row["_date"] <= scope["_through_date"]:
            reason = "outside-period"
        if reason:
            excluded.append({
                "scope_id": row["scope_id"], "source": "ledger", "record_id": row["ledger_line_id"],
                "local_date": row["_date"].isoformat(), "amount_minor": row["amount_minor"], "reason": reason,
            })
        else:
            row["_type"] = row["ledger_type"]
            ledger.append(row)
    for scope in ordered:
        sid = scope["scope_id"]
        integrity(
            scope["bank_opening_minor"] + sum(row["amount_minor"] for row in bank if row["scope_id"] == sid) == scope["bank_closing_minor"],
            "Normalized bank opening plus included lines does not equal closing.", sid,
        )
        integrity(
            scope["ledger_opening_minor"] + sum(row["amount_minor"] for row in ledger if row["scope_id"] == sid) == scope["ledger_closing_minor"],
            "Normalized ledger opening plus included lines does not equal closing.", sid,
        )
    bank.sort(key=lambda row: (rank[row["scope_id"]], row["bank_line_id"]))
    ledger.sort(key=lambda row: (rank[row["scope_id"]], row["ledger_line_id"]))
    excluded.sort(key=lambda row: (rank[row["scope_id"]], row["record_id"]))
    return config, cutoff, ordered, rank, bank, ledger, excluded, batches, reserved


def assign(row, disposition, reasons=()):
    row["disposition"] = disposition
    row["reason_codes"] = sorted(reasons)


def unmatched_reason(row, opposite, config, *, bank):
    if bank and row["_type"] is None:
        return "unmapped-code"
    if not row["_reference"]:
        return "missing-reference"
    related = [
        other for other in opposite
        if other["scope_id"] == row["scope_id"] and other["_reference"] == row["_reference"]
    ]
    if not related:
        return "bank-only-fee" if bank and row["_type"] == "FEE" else "no-counterpart"
    typed = [other for other in related if row["_type"] is not None and row["_type"] == other["_type"]]
    if not typed:
        return "type-mismatch"
    dated = [other for other in typed if abs((row["_date"] - other["_date"]).days) <= config["max_match_calendar_days"]]
    return "amount-mismatch" if dated else "date-mismatch"


def process(payload, events):
    config, cutoff, scopes, rank, bank, ledger, excluded, batches, reserved = prepare(payload)
    event(events, "validate-close", "validation", "Both normalized source closes agree with their included rows.", {
        "scopes": len(scopes), "bank_rows": len(bank), "ledger_rows": len(ledger),
    }, "Validated source closes (minor units)", ["scope", "currency", "bank_close", "bank_sum", "ledger_close", "ledger_sum"], [
        [scope["scope_id"], scope["currency"], scope["bank_closing_minor"],
         scope["bank_opening_minor"] + sum(row["amount_minor"] for row in bank if row["scope_id"] == scope["scope_id"]),
         scope["ledger_closing_minor"],
         scope["ledger_opening_minor"] + sum(row["amount_minor"] for row in ledger if row["scope_id"] == scope["scope_id"])]
        for scope in scopes
    ])
    event(events, "normalize-cutoff", "validation", "Signs and fixed-offset business dates are normalized; ledger exclusions stay visible.", {
        "offset_minutes": config["business_utc_offset_minutes"], "cutoff": config["cutoff_date"],
        "excluded_ledger": len(excluded),
    }, "Normalized bank rows", ["bank_id", "scope", "local_date", "amount_minor", "reference", "mapped_type"], [
        [row["bank_line_id"], row["scope_id"], row["_date"].isoformat(), row["amount_minor"], row["_reference"], row["_type"]]
        for row in bank
    ])
    by_ledger = {row["ledger_line_id"]: row for row in ledger}
    for row in bank:
        row["candidate_ledger_ids"] = []
        assign(row, None)
    for row in ledger:
        row["candidate_bank_ids"] = []
        assign(row, None)

    claims = defaultdict(list)
    for row in bank:
        if row["batch_id"] is not None:
            claims[row["scope_id"], row["batch_id"]].append(row)
    plans = []
    batch_edges = 0
    for key, member_ids in sorted(batches.items(), key=lambda item: (rank[item[0][0]], item[0][1])):
        claimants = claims[key]
        batch_edges += len(claimants) * len(member_ids)
        if batch_edges > EDGE_LIMIT:
            raise BusinessError("candidate-limit", "Candidate graph exceeds 100000 edges; reduce the supplied batch.")
        members = [by_ledger[member] for member in member_ids if member in by_ledger]
        for row in claimants:
            row["candidate_ledger_ids"] = list(member_ids)
        for row in members:
            row["candidate_bank_ids"] = sorted(claim["bank_line_id"] for claim in claimants)
        if len(claimants) > 1:
            reason = "ambiguous-match"
        elif not claimants or len(members) != len(member_ids):
            reason = "batch-incomplete"
        else:
            claim = claimants[0]
            valid = (
                claim["_type"] is not None
                and all(member["_type"] == claim["_type"] for member in members)
                and all(abs((member["_date"] - claim["_date"]).days) <= config["max_match_calendar_days"] for member in members)
                and sum(member["amount_minor"] for member in members) == claim["amount_minor"]
            )
            reason = None if valid else "batch-mismatch"
        plans.append((claimants, members, reason))
    for key, claimants in claims.items():
        if key not in batches:
            plans.append((claimants, [], "batch-incomplete"))

    free_bank = [row for row in bank if row["batch_id"] is None]
    free_ledger = [row for row in ledger if row["ledger_line_id"] not in reserved]
    references = defaultdict(list)
    for row in free_ledger:
        if row["_reference"]:
            references[row["scope_id"], row["_reference"]].append(row)
    edges = 0
    for row in free_bank:
        if row["_type"] is None or not row["_reference"]:
            continue
        for other in references[row["scope_id"], row["_reference"]]:
            if (row["_type"] == other["_type"]
                    and abs((row["_date"] - other["_date"]).days) <= config["max_match_calendar_days"]
                    and abs(row["amount_minor"] - other["amount_minor"]) <= config["single_amount_tolerance_minor"]):
                edges += 1
                if edges + batch_edges > EDGE_LIMIT:
                    raise BusinessError("candidate-limit", "Candidate graph exceeds 100000 edges; reduce the supplied batch.")
                row["candidate_ledger_ids"].append(other["ledger_line_id"])
                other["candidate_bank_ids"].append(row["bank_line_id"])
    event(events, "join-candidates", "join", "Full single-candidate graph and exact batch members are available before any pair is selected.", {
        "single_edges": edges, "batch_edges": batch_edges, "reserved_members": len(reserved), "batch_manifests": len(batches),
        "date_window_days": config["max_match_calendar_days"], "tolerance_minor": config["single_amount_tolerance_minor"],
    }, "Candidate evidence (ID previews counted)", ["bank_id", "scope", "batch", "candidate_count", "ledger_ids"], [
        [row["bank_line_id"], row["scope_id"], row["batch_id"], len(row["candidate_ledger_ids"]), id_preview(row["candidate_ledger_ids"])]
        for row in bank
    ])

    matches = []

    def match(row, members, kind):
        if row["disposition"] is not None or any(member["disposition"] is not None for member in members):
            raise RuntimeError("Attempted to reuse an assigned reconciliation row")
        total = sum(member["amount_minor"] for member in members)
        delta = row["amount_minor"] - total
        decision = "candidate-with-correction" if delta else "candidate-match"
        reasons = ["pending-correction"] if delta else []
        assign(row, decision, reasons)
        for member in members:
            assign(member, decision, reasons)
        matches.append({
            "scope_id": row["scope_id"], "bank_line_id": row["bank_line_id"],
            "ledger_line_ids": sorted(member["ledger_line_id"] for member in members), "kind": kind,
            "bank_minor": row["amount_minor"], "ledger_minor": total, "delta_minor": delta,
            "max_date_gap_days": max(abs((row["_date"] - member["_date"]).days) for member in members),
            "decision": decision,
        })

    for claimants, members, reason in plans:
        if reason is None:
            match(claimants[0], members, "batch")
        else:
            disposition = "ambiguous" if reason == "ambiguous-match" else "batch-held"
            for row in [*claimants, *members]:
                assign(row, disposition, [reason])
    for row in free_bank:
        candidates = row["candidate_ledger_ids"]
        if len(candidates) == 1 and len(by_ledger[candidates[0]]["candidate_bank_ids"]) == 1:
            match(row, [by_ledger[candidates[0]]], "single")
        elif candidates:
            assign(row, "ambiguous", ["ambiguous-match"])
    for row in free_ledger:
        if row["disposition"] is None and row["candidate_bank_ids"]:
            assign(row, "ambiguous", ["ambiguous-match"])
    matches.sort(key=lambda row: (rank[row["scope_id"]], row["bank_line_id"]))
    event(events, "decide-matches", "decision", "Only exact complete batches and isolated single pairs are candidate matches; nothing is posted.", {
        "candidate_groups": len(matches), "pending_corrections": sum(row["delta_minor"] != 0 for row in matches),
    }, "Candidate groups (minor units)", ["bank_id", "ledger_ids", "kind", "bank", "ledger", "delta"], [
        [row["bank_line_id"], id_preview(row["ledger_line_ids"]), row["kind"], row["bank_minor"], row["ledger_minor"], row["delta_minor"]]
        for row in matches
    ])
    for row in free_bank:
        if row["disposition"] is None:
            assign(row, "unmatched", [unmatched_reason(row, free_ledger, config, bank=True)])
    for row in free_ledger:
        if row["disposition"] is not None:
            continue
        clearing = calendar_date(row["expected_bank_date"], "expected_bank_date") if row["expected_bank_date"] is not None else None
        if clearing is not None and 0 < (clearing - cutoff).days <= config["timing_grace_calendar_days"]:
            assign(row, "pending-clearance", ["pending-clearance"])
        else:
            reasons = [unmatched_reason(row, free_bank, config, bank=False)]
            if (cutoff - row["_date"]).days > config["stale_after_calendar_days"]:
                reasons.append("stale-ledger")
            assign(row, "unmatched", reasons)
    exceptions = []
    for rows, id_key in ((bank, "bank_line_id"), (ledger, "ledger_line_id")):
        for row in rows:
            if row["disposition"] is None:
                raise RuntimeError("An included row has no disposition")
            for reason in row["reason_codes"]:
                exceptions.append({
                    "scope_id": row["scope_id"], "record_id": row[id_key], "code": reason, "message": MESSAGES[reason],
                })
    for scope in scopes:
        if scope["bank_opening_minor"] != scope["ledger_opening_minor"]:
            exceptions.append({
                "scope_id": scope["scope_id"], "record_id": scope["scope_id"],
                "code": "opening-difference", "message": MESSAGES["opening-difference"],
            })
    exceptions.sort(key=lambda row: (rank[row["scope_id"]], row["record_id"], row["code"]))
    event(events, "route-unresolved", "exception", "Every unresolved row and candidate correction is routed to review with a concrete reason.", {
        "exception_records": len(exceptions), "live_action": "none",
    }, "Review queue", ["scope", "record_id", "reason"], [
        [row["scope_id"], row["record_id"], row["code"]] for row in exceptions
    ])
    summaries = []
    for scope in scopes:
        sid = scope["scope_id"]
        bank_rows = [row for row in bank if row["scope_id"] == sid]
        ledger_rows = [row for row in ledger if row["scope_id"] == sid]
        groups = [row for row in matches if row["scope_id"] == sid]
        unmatched_bank = [row for row in bank_rows if not row["disposition"].startswith("candidate-")]
        unmatched_ledger = [row for row in ledger_rows if not row["disposition"].startswith("candidate-")]
        summary = {field: scope[field] for field in (
            "scope_id", "legal_entity_id", "account_id", "statement_id", "currency", "from_date", "through_date",
        )}
        summary.update({
            "opening_bank_minor": scope["bank_opening_minor"], "opening_ledger_minor": scope["ledger_opening_minor"],
            "closing_bank_minor": scope["bank_closing_minor"], "closing_ledger_minor": scope["ledger_closing_minor"],
            "included_bank_count": len(bank_rows), "included_ledger_count": len(ledger_rows),
            "matched_group_count": len(groups), "matched_bank_count": len(groups),
            "matched_ledger_count": sum(len(group["ledger_line_ids"]) for group in groups),
            "unresolved_bank_count": len(unmatched_bank), "unresolved_ledger_count": len(unmatched_ledger),
            "unmatched_bank_minor": sum(row["amount_minor"] for row in unmatched_bank),
            "unmatched_ledger_minor": sum(row["amount_minor"] for row in unmatched_ledger),
            "match_delta_minor": sum(group["delta_minor"] for group in groups),
            "opening_difference_minor": scope["bank_opening_minor"] - scope["ledger_opening_minor"],
            "closing_difference_minor": scope["bank_closing_minor"] - scope["ledger_closing_minor"],
        })
        summary["bridge_minor"] = (
            summary["opening_difference_minor"] + summary["unmatched_bank_minor"]
            - summary["unmatched_ledger_minor"] + summary["match_delta_minor"]
        )
        if summary["bridge_minor"] != summary["closing_difference_minor"]:
            raise RuntimeError("Reconciliation bridge does not conserve signed amounts")
        if (summary["matched_bank_count"] + summary["unresolved_bank_count"] != len(bank_rows)
                or summary["matched_ledger_count"] + summary["unresolved_ledger_count"] != len(ledger_rows)):
            raise RuntimeError("Reconciliation partitions do not conserve row counts")
        summary["disposition"] = "review-required" if (
            unmatched_bank or unmatched_ledger or summary["opening_difference_minor"]
            or any(group["delta_minor"] for group in groups)
        ) else "no-open-items"
        summaries.append(summary)
    event(events, "bridge-balances", "decision", "The signed opening/unmatched/delta bridge equals the closing difference for every scope.", {
        "scopes": len(scopes), "bridges_equal": True,
    }, "Signed bridges (minor units; never cross-currency netted)", ["scope", "opening_diff", "unmatched_bank", "unmatched_ledger", "match_delta", "close_diff"], [
        [row["scope_id"], row["opening_difference_minor"], row["unmatched_bank_minor"], row["unmatched_ledger_minor"],
         row["match_delta_minor"], row["closing_difference_minor"]] for row in summaries
    ])

    def public_row(row, bank_row):
        id_key = "bank_line_id" if bank_row else "ledger_line_id"
        candidate_key = "candidate_ledger_ids" if bank_row else "candidate_bank_ids"
        value = {field: deepcopy(row[field]) for field in (
            "scope_id", id_key, "amount_minor", candidate_key, "disposition", "reason_codes",
        )}
        value["local_date"] = row["_date"].isoformat()
        value["canonical_reference"] = row["_reference"]
        if bank_row:
            value["mapped_type"] = row["_type"]
        else:
            value["ledger_type"] = row["ledger_type"]
            value["expected_bank_date"] = row["expected_bank_date"]
        return value

    result = {
        "schema_version": 1, "status": "completed_with_exceptions" if exceptions else "completed",
        "outputs": {
            "controls": deepcopy(config), "matches": matches,
            "bank_reviews": [public_row(row, True) for row in bank],
            "ledger_reviews": [public_row(row, False) for row in ledger],
            "excluded": excluded, "scope_summaries": summaries, "review": dict(REVIEW),
        },
        "exceptions": exceptions,
    }
    event(events, "emit-review-packet", "output", "Complete synthetic controller packet: all rows accounted for, human review pending, no financial action.", {
        "status": result["status"], "groups": len(matches), "exceptions": len(exceptions),
        "human_review": "pending", "live_action": "none",
    }, "Controller packet", ["scope", "groups", "unresolved_bank", "unresolved_ledger", "difference_minor", "disposition"], [
        [row["scope_id"], row["matched_group_count"], row["unresolved_bank_count"],
         row["unresolved_ledger_count"], row["closing_difference_minor"], row["disposition"]]
        for row in summaries
    ])
    return result


def solve(payload):
    events = []
    counts = [
        [name, len(payload[name]) if isinstance(payload, dict) and isinstance(payload.get(name), list) else None]
        for name in SOURCES
    ]
    event(events, "intake-exports", "input", "Load supplied synthetic export rows; no live system or financial action.", {
        "synthetic_input": isinstance(payload, dict) and payload.get("synthetic") is True,
    }, "Supplied source counts (null means invalid collection)", ["source", "rows"], counts)
    try:
        result = process(payload, events)
    except BusinessError as error:
        result = {
            "schema_version": 1, "status": "rejected",
            "outputs": {"review": dict(REVIEW)}, "exceptions": [error.diagnostic],
        }
        event(events, "validate-close", "validation", "Input rejected explicitly; no trusted financial totals or matches emitted.", {
            "status": "rejected", "code": error.diagnostic["code"],
        }, "Rejection diagnostic", ["scope", "record", "code"], [[
            error.diagnostic["scope_id"], error.diagnostic["record_id"], error.diagnostic["code"],
        ]])
    return result, events


if __name__ == "__main__":
    run_cli(solve, scenario_id="financial-services-01")
