"""Exact, synthetic unit-price audit; no service, publication or action authority."""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP, localcontext
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "_shared"))
from scenario_support import run_cli


OWNER = "Pricing operations analyst"
ROLES = (
    "stores", "products", "base_prices", "promotions", "promotion_scope",
    "price_exceptions", "observations",
)
KEYS = {
    "stores": ("store_id",),
    "products": ("sku",),
    "base_prices": ("price_id",),
    "promotions": ("promotion_id",),
    "promotion_scope": ("promotion_id", "store_id", "sku", "line_type"),
    "price_exceptions": ("exception_id",),
    "observations": ("observation_id",),
}
FIELDS = {
    "stores": {"store_id", "currency", "date_basis"},
    "products": {"sku", "unit"},
    "base_prices": {
        "price_id", "store_id", "sku", "valid_from", "valid_to", "currency",
        "unit", "price_minor",
    },
    "promotions": {
        "promotion_id", "enabled", "valid_from", "valid_to", "currency", "unit",
        "priority", "mode", "type", "value",
    },
    "promotion_scope": {"promotion_id", "store_id", "sku", "line_type"},
    "price_exceptions": {
        "exception_id", "store_id", "sku", "valid_from", "valid_to", "currency",
        "unit", "approved", "approval_reference", "price_minor",
    },
    "observations": {
        "observation_id", "store_id", "sku", "observed_on", "currency", "unit",
        "observed_minor",
    },
}
POLICY_FIELDS = {
    "as_of", "audit_start", "audit_end", "tolerance_minor", "rounding", "source_files",
}
CURRENCIES = {"USD", "EUR", "GBP", "CAD", "AUD"}
MODES = {"exclusive", "best-price", "compound"}
TYPES = {"amount-off", "percent-off"}
RESERVED_NAMES = {"con", "prn", "aux", "nul"} | {
    f"{prefix}{number}" for prefix in ("com", "lpt") for number in range(1, 10)
}
MESSAGES = {
    "INVALID_SCHEMA": "Fields or container types do not match the documented input schema.",
    "INVALID_IDENTIFIER": "Identifiers must use the SYN- synthetic identifier format.",
    "INVALID_VALUE": "A value has an unsupported type or domain.",
    "INVALID_DATE": "Dates must be real YYYY-MM-DD local-calendar dates in 2099.",
    "INVALID_WINDOW": "Window start must be before its exclusive end.",
    "FUTURE_AUDIT_WINDOW": "The final included audit day must not be after as_of.",
    "INVALID_SOURCE_MAP": "Source roles must map one-to-one to distinct bundled JSON export filenames.",
    "DUPLICATE_KEY": "An export contains a duplicate primary or scope key.",
    "UNKNOWN_REFERENCE": "A required export reference does not resolve exactly.",
    "DIMENSION_MISMATCH": "Currency or unit disagrees with the referenced store or product.",
    "UNSUPPORTED_RULE": "Only exclusive, best-price, compound, amount-off and percent-off rules are supported.",
    "INVALID_RATE": "Percent-off value must be an integer from 1 through 10000 basis points.",
    "UNSUPPORTED_POLICY": "Only ROUND_HALF_UP and store-local-calendar date basis are supported.",
    "MISSING_BASE_PRICE": "No base price matches the observation dimensions and date.",
    "AMBIGUOUS_BASE_PRICE": "More than one base price matches the observation dimensions and date.",
    "AMBIGUOUS_APPROVED_EXCEPTION": "More than one approved price exception matches the observation dimensions and date.",
    "PRICE_MISMATCH": "Absolute observed-minus-expected delta exceeds the configured tolerance.",
    "OUT_OF_AUDIT_WINDOW": "Observation is outside the half-open audit window; no price was evaluated.",
}
ACTIONS = {
    "MISSING_BASE_PRICE": "Obtain the missing dated base-price evidence before evaluating this observation.",
    "AMBIGUOUS_BASE_PRICE": "Resolve overlapping base-price versions; do not choose a price automatically.",
    "AMBIGUOUS_APPROVED_EXCEPTION": "Resolve the competing approvals and retain one authoritative synthetic exception.",
    "PRICE_MISMATCH": "Review the observation, chosen rules and rounding with the pricing reviewer.",
    "OUT_OF_AUDIT_WINDOW": "Confirm the intended audit period; keep this observation outside this review.",
}


class PricingInputError(ValueError):
    def __init__(self, code, path):
        super().__init__(MESSAGES[code])
        self.code = code
        self.path = path


def _require(condition, code, path):
    if not condition:
        raise PricingInputError(code, path)


def _fields(value, fields, path, code="INVALID_SCHEMA"):
    _require(isinstance(value, dict) and set(value) == fields, code, path)


def _identifier(value, path):
    _require(
        isinstance(value, str) and re.fullmatch(r"SYN-[A-Z0-9][A-Z0-9-]{0,63}", value),
        "INVALID_IDENTIFIER", path,
    )


def _integer(value, path, *, minimum=None, maximum=None, code="INVALID_VALUE"):
    _require(
        type(value) is int
        and (minimum is None or value >= minimum)
        and (maximum is None or value <= maximum),
        code, path,
    )


def _date(value, path):
    _require(
        isinstance(value, str) and re.fullmatch(r"2099-[0-9]{2}-[0-9]{2}", value),
        "INVALID_DATE", path,
    )
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise PricingInputError("INVALID_DATE", path) from error


def _canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True)


def _record_path(role, row):
    return role + "." + "|".join(str(row[key]) for key in KEYS[role])


def _validate_record(role, row, path):
    for field in ("store_id", "sku", "price_id", "promotion_id", "exception_id", "observation_id"):
        if field in row:
            _identifier(row[field], path + "." + field)
    if "currency" in row:
        _require(
            isinstance(row["currency"], str) and row["currency"] in CURRENCIES,
            "INVALID_VALUE", path + ".currency",
        )
    if "unit" in row:
        _require(
            isinstance(row["unit"], str) and re.fullmatch(r"[A-Z][A-Z0-9-]{0,15}", row["unit"]),
            "INVALID_VALUE", path + ".unit",
        )
    for field in ("enabled", "approved"):
        if field in row:
            _require(type(row[field]) is bool, "INVALID_VALUE", path + "." + field)
    for field in ("price_minor", "observed_minor"):
        if field in row:
            _integer(row[field], path + "." + field, minimum=0)
    if role == "stores":
        _require(row["date_basis"] == "store-local-calendar", "UNSUPPORTED_POLICY", path + ".date_basis")
    if "valid_from" in row:
        start = _date(row["valid_from"], path + ".valid_from")
        end = _date(row["valid_to"], path + ".valid_to")
        _require(start < end, "INVALID_WINDOW", path + ".valid_to")
    if role == "observations":
        _date(row["observed_on"], path + ".observed_on")
    if role == "promotions":
        _integer(row["priority"], path + ".priority")
        _require(
            isinstance(row["mode"], str) and row["mode"] in MODES,
            "UNSUPPORTED_RULE", path + ".mode",
        )
        _require(
            isinstance(row["type"], str) and row["type"] in TYPES,
            "UNSUPPORTED_RULE", path + ".type",
        )
        if row["type"] == "percent-off":
            _integer(row["value"], path + ".value", minimum=1, maximum=10000, code="INVALID_RATE")
        else:
            _integer(row["value"], path + ".value", minimum=1)
    if role == "promotion_scope":
        _require(row["line_type"] in ("include", "exclude"), "INVALID_VALUE", path + ".line_type")
    if role == "price_exceptions" and (row["approved"] or row["approval_reference"] is not None):
        _identifier(row["approval_reference"], path + ".approval_reference")


def _validate(payload):
    _fields(payload, {"schema_version", "policy", "exports"}, "bundle")
    _integer(payload["schema_version"], "schema_version", minimum=1, maximum=1)
    policy = payload["policy"]
    _fields(policy, POLICY_FIELDS, "policy")
    as_of = _date(policy["as_of"], "policy.as_of")
    start = _date(policy["audit_start"], "policy.audit_start")
    end = _date(policy["audit_end"], "policy.audit_end")
    _require(start < end, "INVALID_WINDOW", "policy.audit_end")
    _require(end - timedelta(days=1) <= as_of, "FUTURE_AUDIT_WINDOW", "policy.audit_end")
    _integer(policy["tolerance_minor"], "policy.tolerance_minor", minimum=0)
    _require(policy["rounding"] == "ROUND_HALF_UP", "UNSUPPORTED_POLICY", "policy.rounding")
    names = policy["source_files"]
    _fields(names, set(ROLES), "policy.source_files", "INVALID_SOURCE_MAP")
    for role in ROLES:
        name = names[role]
        _require(
            isinstance(name, str)
            and re.fullmatch(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*\.json", name)
            and name[:-5] not in RESERVED_NAMES,
            "INVALID_SOURCE_MAP", "policy.source_files." + role,
        )
    _require(len(set(names.values())) == len(ROLES), "INVALID_SOURCE_MAP", "policy.source_files")
    _fields(payload["exports"], set(names.values()), "exports", "INVALID_SOURCE_MAP")
    tables = {}
    for role in ROLES:
        rows = payload["exports"][names[role]]
        _require(isinstance(rows, list), "INVALID_SCHEMA", "exports." + names[role])
        tables[role] = rows
    for role in ROLES:
        rows = tables[role]
        for ordinal, row in enumerate(sorted(rows, key=_canonical)):
            _fields(row, FIELDS[role], f"{role}[{ordinal}]")
        ordered = sorted(
            rows, key=lambda row: (tuple(_canonical(row[key]) for key in KEYS[role]), _canonical(row)),
        )
        seen = set()
        for row in ordered:
            path = _record_path(role, row)
            _validate_record(role, row, path)
            key = tuple(row[field] for field in KEYS[role])
            _require(key not in seen, "DUPLICATE_KEY", path)
            seen.add(key)
        tables[role] = ordered
    stores = {row["store_id"]: row for row in tables["stores"]}
    products = {row["sku"]: row for row in tables["products"]}
    promotions = {row["promotion_id"]: row for row in tables["promotions"]}
    for role in ("base_prices", "promotion_scope", "price_exceptions", "observations"):
        for row in tables[role]:
            path = _record_path(role, row)
            _require(row["store_id"] in stores, "UNKNOWN_REFERENCE", path + ".store_id")
            _require(row["sku"] in products, "UNKNOWN_REFERENCE", path + ".sku")
            if role == "promotion_scope":
                _require(row["promotion_id"] in promotions, "UNKNOWN_REFERENCE", path + ".promotion_id")
            else:
                _require(
                    row["currency"] == stores[row["store_id"]]["currency"],
                    "DIMENSION_MISMATCH", path + ".currency",
                )
                _require(
                    row["unit"] == products[row["sku"]]["unit"],
                    "DIMENSION_MISMATCH", path + ".unit",
                )
    return policy, tables


def _observation_key(row):
    return row["observed_on"], row["store_id"], row["sku"], row["observation_id"]


def _dimensions(row):
    return row["store_id"], row["sku"], row["unit"], row["currency"]


def _active(row, on):
    return row["valid_from"] <= on < row["valid_to"]


def _dimension_index(rows):
    index = {}
    for row in rows:
        index.setdefault(_dimensions(row), []).append(row)
    return index


def _join(observation, base_index, exception_index):
    dimensions = _dimensions(observation)
    on = observation["observed_on"]
    base_versions = base_index.get(dimensions, [])
    exception_versions = exception_index.get(dimensions, [])
    return {
        "observation": observation,
        "base_versions": base_versions,
        "exception_versions": exception_versions,
        "bases": [row for row in base_versions if _active(row, on)],
        "approved_exceptions": [row for row in exception_versions if row["approved"] and _active(row, on)],
        "base_checks": [{"price_id": row["price_id"], "date_match": _active(row, on)} for row in base_versions],
        "exception_checks": [
            {"exception_id": row["exception_id"], "date_match": _active(row, on), "approved": row["approved"]}
            for row in exception_versions
        ],
    }


def _filter_promotions(context, promotions, scope):
    observation = context["observation"]
    filters, eligible, trace_rows = [], [], []
    for promotion in promotions:
        key = promotion["promotion_id"], observation["store_id"], observation["sku"]
        included = (*key, "include") in scope
        excluded = (*key, "exclude") in scope
        date_match = _active(promotion, observation["observed_on"])
        tests = (
            ("disabled", not promotion["enabled"]),
            ("outside-validity", not date_match),
            ("currency-mismatch", promotion["currency"] != observation["currency"]),
            ("unit-mismatch", promotion["unit"] != observation["unit"]),
            ("not-included", not included),
            ("explicit-exclusion", excluded),
        )
        reasons = [reason for reason, failed in tests if failed]
        filters.append({"promotion_id": promotion["promotion_id"], "reasons": reasons})
        if not reasons:
            eligible.append(promotion)
        trace_rows.append([
            observation["observation_id"], promotion["promotion_id"], date_match,
            included, excluded, ", ".join(reasons) if reasons else "eligible",
        ])
    context["promotion_filters"] = filters
    context["eligible"] = eligible
    return trace_rows


def _decimal_text(value):
    # All discount denominators contain only 2s and 5s; render exactly, without a context round.
    denominator = value.denominator
    twos = fives = 0
    while denominator % 2 == 0:
        twos += 1
        denominator //= 2
    while denominator % 5 == 0:
        fives += 1
        denominator //= 5
    if denominator != 1:
        raise ValueError("A pricing fraction unexpectedly has a nonterminating decimal expansion")
    scale = max(twos, fives)
    scaled = value.numerator * 2 ** (scale - twos) * 5 ** (scale - fives)
    digits = str(scaled).zfill(scale + 1)
    if not scale:
        return digits
    return (digits[:-scale] + "." + digits[-scale:]).rstrip("0").rstrip(".")


def _price(base, rules):
    subtotal = max(0, base - sum(rule["value"] for rule in rules if rule["type"] == "amount-off"))
    value = Fraction(subtotal)
    for rule in rules:
        if rule["type"] == "percent-off":
            value *= Fraction(10000 - rule["value"], 10000)
    return value


def _resolve(context):
    observation = context["observation"]
    bases = context["bases"]
    overrides = context["approved_exceptions"]
    eligible = context["eligible"]
    base_ids = [row["price_id"] for row in bases]
    override_ids = [row["exception_id"] for row in overrides]
    audit = dict(
        observation, base_price_ids=base_ids, base_minor=bases[0]["price_minor"] if len(bases) == 1 else None,
        active_exception_ids=override_ids, applied_exception_id=None, selected_promotion_ids=[],
        pricing_basis="not-evaluable", unrounded_minor=None, expected_minor=None,
        delta_minor=None, disposition="not-evaluable",
    )
    selection = {
        "observation_id": observation["observation_id"],
        "base_checks": context["base_checks"],
        "exception_checks": context["exception_checks"],
        "promotion_filters": context["promotion_filters"],
        "winning_priority": None, "candidates": [], "tied_promotion_sets": [], "suppressed_promotions": [],
    }
    errors, suppressed = [], {}
    if not bases:
        errors.append(("MISSING_BASE_PRICE", []))
    elif len(bases) > 1:
        errors.append(("AMBIGUOUS_BASE_PRICE", base_ids))
    if len(overrides) > 1:
        errors.append(("AMBIGUOUS_APPROVED_EXCEPTION", override_ids))
    if errors:
        suppressed = {row["promotion_id"]: "not-evaluable" for row in eligible}
    elif overrides:
        audit.update(
            applied_exception_id=overrides[0]["exception_id"], pricing_basis="approved-exception",
            unrounded_minor=str(overrides[0]["price_minor"]),
        )
        suppressed = {row["promotion_id"]: "approved-exception" for row in eligible}
    elif not eligible:
        audit.update(pricing_basis="base", unrounded_minor=str(audit["base_minor"]))
    else:
        priority = max(row["priority"] for row in eligible)
        selection["winning_priority"] = priority
        highest = [row for row in eligible if row["priority"] == priority]
        suppressed = {row["promotion_id"]: "lower-priority" for row in eligible if row["priority"] < priority}
        exclusive = [row for row in highest if row["mode"] == "exclusive"]
        if exclusive:
            groups = [[row] for row in exclusive]
            suppressed.update({row["promotion_id"]: "exclusive-present" for row in highest if row["mode"] != "exclusive"})
        else:
            groups = [[row] for row in highest if row["mode"] == "best-price"]
            compound = [row for row in highest if row["mode"] == "compound"]
            if compound:
                groups.append(compound)
        priced = sorted(
            (tuple(row["promotion_id"] for row in group), group[0]["mode"], _price(audit["base_minor"], group))
            for group in groups
        )
        winner_ids, mode, value = min(priced, key=lambda item: (item[2], item[0]))
        ties = [list(ids) for ids, _, amount in priced if amount == value]
        selection["tied_promotion_sets"] = ties if len(ties) > 1 else []
        selection["candidates"] = [
            {"promotion_ids": list(ids), "mode": candidate_mode, "unrounded_minor": _decimal_text(amount)}
            for ids, candidate_mode, amount in priced
        ]
        for ids, _, amount in priced:
            if ids != winner_ids:
                for promotion_id in ids:
                    suppressed[promotion_id] = "tie-break" if amount == value else "higher-price"
        audit.update(
            selected_promotion_ids=list(winner_ids), pricing_basis=mode, unrounded_minor=_decimal_text(value),
        )
    selection["suppressed_promotions"] = [
        {"promotion_id": promotion_id, "reason": suppressed[promotion_id]} for promotion_id in sorted(suppressed)
    ]
    return audit, selection, errors


def _round_and_compare(audit, tolerance):
    if audit["unrounded_minor"] is None:
        return
    raw = audit["unrounded_minor"]
    with localcontext() as context:
        context.prec = max(28, len(raw) + 2)
        rounded = int(Decimal(raw).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    delta = audit["observed_minor"] - rounded
    audit.update(
        expected_minor=rounded, delta_minor=delta,
        disposition="mismatch" if abs(delta) > tolerance else "match",
    )


def _exception(code, path, observation_id=None, evidence_ids=()):
    return {
        "code": code, "message": MESSAGES[code], "path": path,
        "observation_id": observation_id, "evidence_ids": sorted(set(evidence_ids)),
    }


def _issue(exception, number, observation=None):
    fields = ("observed_on", "store_id", "sku", "currency")
    return {
        "issue_id": f"SYN-ISSUE-{number:04d}",
        **{key: exception[key] for key in ("code", "message", "observation_id", "evidence_ids")},
        **{key: observation[key] if observation is not None else None for key in fields},
        "owner": OWNER,
        "next_action": ACTIONS.get(exception["code"], "Correct the source export or policy and rerun the audit."),
    }


def _counts(observations, audit, excluded):
    dispositions = Counter(row["disposition"] for row in audit)
    return {
        "input_observations": len(observations), "included_observations": len(audit),
        "matched": dispositions["match"], "mismatched": dispositions["mismatch"],
        "not_evaluable": dispositions["not-evaluable"], "out_of_scope": len(excluded),
    }


def _review_packet(policy, state, counts):
    return {
        "policy": None if policy is None else {
            **{key: policy[key] for key in ("audit_start", "audit_end", "as_of", "tolerance_minor", "rounding")},
            "date_basis": "store-local-calendar",
        },
        "owner_role": OWNER, "review_state": state, "action_authorized": False,
        "counts_by_store_currency": counts,
    }


def _table(title, columns, rows, highlights=()):
    return {
        "title": title, "columns": columns, "rows": rows[:8], "total_rows": len(rows),
        "highlight_rows": [index for index in highlights if index < min(8, len(rows))],
    }


def _event(step_id, kind, caption, facts, *tables):
    return {"step_id": step_id, "kind": kind, "caption": caption, "facts": facts, "tables": list(tables)}


def _input_event(payload):
    policy = payload.get("policy") if isinstance(payload, dict) else None
    names = policy.get("source_files") if isinstance(policy, dict) else None
    exports = payload.get("exports") if isinstance(payload, dict) else None
    rows = []
    for role in ROLES:
        name = names.get(role) if isinstance(names, dict) else None
        value = exports.get(name) if isinstance(exports, dict) and isinstance(name, str) else None
        rows.append([role, name if isinstance(name, str) else None, len(value) if isinstance(value, list) else None])
    facts = {}
    for key in ("audit_start", "audit_end", "as_of", "tolerance_minor"):
        value = policy.get(key) if isinstance(policy, dict) else None
        facts[key] = value if type(value) in (str, int, bool) else None
    return _event(
        "load-price-exports", "input",
        "Loaded the bundled source map and raw export counts. Null metadata means absent or invalid, never a default price or count.",
        facts, _table("Named export tables (all roles)", ["role", "logical_filename", "record_count"], rows),
    )


def _join_event(contexts, excluded_count):
    summaries, versions = [], []
    for context in contexts:
        observation = context["observation"]
        base_ids = [row["price_id"] for row in context["bases"]]
        exception_ids = [row["exception_id"] for row in context["approved_exceptions"]]
        unique = len(base_ids) == 1 and len(exception_ids) <= 1
        summaries.append([
            observation["observation_id"], observation["observed_on"],
            observation["store_id"] + " / " + observation["sku"],
            ", ".join(base_ids), ", ".join(exception_ids), "unique" if unique else "not-evaluable",
        ])
        for kind, records, id_field in (
            ("base", context["base_versions"], "price_id"),
            ("exception", context["exception_versions"], "exception_id"),
        ):
            for record in records:
                active = _active(record, observation["observed_on"])
                if kind == "exception":
                    active = active and record["approved"]
                versions.append([
                    observation["observation_id"], kind, record[id_field],
                    record["valid_from"], record["valid_to"], active,
                ])
    return _event(
        "join-store-sku-prices", "join",
        "Matched exact store/SKU/unit/currency dimensions, then half-open dates. Every matching version remains visible; ambiguous or missing evidence is not guessed.",
        {
            "included": len(contexts), "excluded_before_join": excluded_count,
            "unique_bases": sum(len(item["bases"]) == 1 for item in contexts),
            "missing_bases": sum(not item["bases"] for item in contexts),
            "ambiguous_bases": sum(len(item["bases"]) > 1 for item in contexts),
            "ambiguous_approvals": sum(len(item["approved_exceptions"]) > 1 for item in contexts),
        },
        _table(
            "Observation joins (ordered prefix)",
            ["observation_id", "date", "store / SKU", "active_base_ids", "approved_exception_ids", "evidence_state"],
            summaries, [i for i, row in enumerate(summaries) if row[-1] != "unique"],
        ),
        _table(
            "Dimensional versions and date/approval matches (ordered prefix)",
            ["observation_id", "kind", "reference_id", "valid_from", "valid_to", "active"],
            versions, [i for i, row in enumerate(versions) if not row[-1]],
        ),
    )


def _policy_event(audits, selections):
    candidates, suppressed = [], []
    for audit, selection in zip(audits, selections):
        reasons = {row["promotion_id"]: row["reason"] for row in selection["suppressed_promotions"]}
        if selection["candidates"]:
            for candidate in selection["candidates"]:
                ids = candidate["promotion_ids"]
                chosen = ids == audit["selected_promotion_ids"]
                candidates.append([
                    audit["observation_id"], candidate["mode"], ", ".join(ids),
                    selection["winning_priority"], candidate["unrounded_minor"],
                    "selected" if chosen else reasons[ids[0]],
                ])
        else:
            ids = [audit["applied_exception_id"]] if audit["applied_exception_id"] else audit["base_price_ids"]
            candidates.append([
                audit["observation_id"], audit["pricing_basis"], ", ".join(ids),
                None, audit["unrounded_minor"],
                "not-evaluable" if audit["unrounded_minor"] is None else "selected",
            ])
        suppressed.extend(
            [audit["observation_id"], row["promotion_id"], row["reason"]]
            for row in selection["suppressed_promotions"]
        )
    return _event(
        "resolve-price-policy", "decision",
        "Resolved the unique-evidence gate, approved exceptions and highest-priority competition using exact unrounded amounts. Suppressed rules never stack.",
        {
            "included_rows": len(audits),
            "approved_overrides": sum(row["pricing_basis"] == "approved-exception" for row in audits),
            "base_only_rows": sum(row["pricing_basis"] == "base" for row in audits),
            "tied_rows": sum(bool(row["tied_promotion_sets"]) for row in selections),
            "suppressed_rules": len(suppressed),
        },
        _table(
            "Actual candidate and fallback decisions (ordered prefix)",
            ["observation_id", "basis", "rule_or_reference_ids", "priority", "unrounded_minor", "decision"],
            candidates, [i for i, row in enumerate(candidates) if row[-1] == "selected"],
        ),
        _table("Eligible but suppressed (ordered prefix)", ["observation_id", "promotion_id", "reason"], suppressed),
    )


def solve(payload):
    events = [_input_event(payload)]
    try:
        policy, tables = _validate(payload)
    except PricingInputError as error:
        exception = _exception(error.code, error.path)
        result = {
            "schema_version": 1, "status": "rejected", "exceptions": [exception],
            "outputs": {
                "price_audit": [], "rule_selection": [], "out_of_scope": [],
                "issue_queue": [_issue(exception, 1)], "reconciliation": None,
                "review_packet": _review_packet(None, "input-rejected", []),
            },
        }
        events.append(_event(
            "validate-pricing-records", "validation",
            "Rejected the first deterministic business validation error. No prices, joins or disposition counts were produced.",
            {"valid": False, "validation_errors": 1, "price_evaluation": "not-started"},
            _table("Input correction required", ["code", "path", "message"], [[error.code, error.path, str(error)]], [0]),
        ))
        return result, events

    events.append(_event(
        "validate-pricing-records", "validation",
        "Validated exact schemas, synthetic identifiers, integer domains, supported rules, calendar windows, unique keys and all foreign keys.",
        {"valid": True, "validation_errors": 0, "records_checked": sum(len(rows) for rows in tables.values()), "references_checked": True},
        _table(
            "Validated export keys (all roles)", ["role", "records", "primary_key", "valid"],
            [[role, len(tables[role]), "|".join(KEYS[role]), True] for role in ROLES],
        ),
    ))
    observations = sorted(tables["observations"], key=_observation_key)
    base_index = _dimension_index(tables["base_prices"])
    exception_index = _dimension_index(tables["price_exceptions"])
    contexts, excluded, row_errors = [], [], {}
    for observation in observations:
        on = observation["observed_on"]
        if policy["audit_start"] <= on < policy["audit_end"]:
            contexts.append(_join(observation, base_index, exception_index))
        else:
            excluded.append(dict(
                observation, expected_minor=None, delta_minor=None, disposition="out-of-scope",
                reason="before-audit-start" if on < policy["audit_start"] else "at-or-after-audit-end",
            ))
            row_errors[observation["observation_id"]] = [("OUT_OF_AUDIT_WINDOW", [])]
    events.append(_join_event(contexts, len(excluded)))

    scope = {
        (row["promotion_id"], row["store_id"], row["sku"], row["line_type"])
        for row in tables["promotion_scope"]
    }
    filter_rows = []
    for context in contexts:
        filter_rows.extend(_filter_promotions(context, tables["promotions"], scope))
    eligible_count = sum(len(context["eligible"]) for context in contexts)
    events.append(_event(
        "select-active-promotions", "decision",
        "Tested every promotion against every included observation: enabled, date, currency, unit and explicit include/exclude scope. All failed filters are retained.",
        {"promotion_observation_pairs": len(filter_rows), "eligible_pairs": eligible_count, "filtered_pairs": len(filter_rows) - eligible_count},
        _table(
            "Actual candidate filters (ordered prefix)",
            ["observation_id", "promotion_id", "date_match", "included", "excluded", "eligibility"],
            filter_rows, [i for i, row in enumerate(filter_rows) if row[-1] == "eligible"],
        ),
        _table(
            "Eligible rules by observation (ordered prefix)", ["observation_id", "date", "eligible_ids", "filtered_rules"],
            [
                [
                    context["observation"]["observation_id"], context["observation"]["observed_on"],
                    ", ".join(row["promotion_id"] for row in context["eligible"]),
                    len(tables["promotions"]) - len(context["eligible"]),
                ]
                for context in contexts
            ],
        ),
    ))

    audits, selections = [], []
    for context in contexts:
        audit, selection, errors = _resolve(context)
        audits.append(audit)
        selections.append(selection)
        row_errors[audit["observation_id"]] = errors
    events.append(_policy_event(audits, selections))
    for audit in audits:
        _round_and_compare(audit, policy["tolerance_minor"])
        if audit["disposition"] == "mismatch":
            evidence = audit["base_price_ids"] + audit["selected_promotion_ids"]
            if audit["applied_exception_id"] is not None:
                evidence = evidence + [audit["applied_exception_id"]]
            row_errors[audit["observation_id"]].append(("PRICE_MISMATCH", evidence))
    events.append(_event(
        "round-and-compare", "decision",
        "Rounded each selected unit price exactly once with ROUND_HALF_UP. Delta is observed minus rounded price; equality to tolerance is a match, not an exception.",
        {"rounding": policy["rounding"], "tolerance_minor": policy["tolerance_minor"], "compared_rows": sum(row["expected_minor"] is not None for row in audits)},
        _table(
            "Unit-price comparisons (ordered prefix)",
            ["observation_id", "unrounded_minor", "expected_minor", "observed_minor", "delta_minor", "disposition"],
            [
                [row[key] for key in ("observation_id", "unrounded_minor", "expected_minor", "observed_minor", "delta_minor", "disposition")]
                for row in audits
            ],
            [i for i, row in enumerate(audits) if row["disposition"] != "match"],
        ),
    ))
    exceptions, issues = [], []
    for observation in observations:
        observation_id = observation["observation_id"]
        for code, evidence in sorted(row_errors[observation_id]):
            exception = _exception(code, "observations." + observation_id, observation_id, evidence)
            exceptions.append(exception)
            issues.append(_issue(exception, len(issues) + 1, observation))
    events.append(_event(
        "register-audit-exceptions", "exception",
        "Registered actual discrepancies, missing/ambiguous evidence and out-of-period rows for human review. No issue authorizes a price change.",
        {"issue_count": len(issues), "excluded_count": len(excluded), "action_authorized": False},
        _table(
            "Human issue queue (ordered prefix)", ["observation_id", "code", "evidence_ids", "owner"],
            [[row["observation_id"], row["code"], ", ".join(row["evidence_ids"]), row["owner"]] for row in issues],
            range(len(issues)),
        ),
        _table(
            "Excluded observations (ordered prefix)", ["observation_id", "observed_on", "reason"],
            [[row["observation_id"], row["observed_on"], row["reason"]] for row in excluded],
        ),
    ))
    counts = _counts(observations, audits, excluded)
    counts["reconciled"] = (
        counts["input_observations"] == counts["included_observations"] + counts["out_of_scope"]
        and counts["included_observations"] == counts["matched"] + counts["mismatched"] + counts["not_evaluable"]
    )
    grouped_counts = []
    for store_id, currency in sorted({(row["store_id"], row["currency"]) for row in observations}):
        grouped = [[row for row in rows if (row["store_id"], row["currency"]) == (store_id, currency)] for rows in (observations, audits, excluded)]
        grouped_counts.append({"store_id": store_id, "currency": currency, **_counts(*grouped)})
    state = "review-required" if exceptions else "ready-for-review"
    packet = _review_packet(policy, state, grouped_counts)
    result = {
        "schema_version": 1, "status": "completed_with_exceptions" if exceptions else "completed",
        "outputs": {
            "price_audit": audits, "rule_selection": selections, "out_of_scope": excluded,
            "issue_queue": issues, "reconciliation": counts, "review_packet": packet,
        },
        "exceptions": exceptions,
    }
    events.append(_event(
        "publish-price-review", "output",
        "Published the full audit, rule-selection ledger, excluded register, issue queue and reconciled review packet. This is local synthetic evidence, not native execution.",
        {
            "input_observations": counts["input_observations"], "included_observations": counts["included_observations"],
            "issue_count": len(issues), "reconciled": counts["reconciled"],
            "action_authorized": False, "business_status": result["status"],
        },
        _table(
            "Reconciliation by store and currency (ordered prefix)",
            ["store_id", "currency", "matched", "mismatched", "not_evaluable", "out_of_scope"],
            [[row[key] for key in ("store_id", "currency", "matched", "mismatched", "not_evaluable", "out_of_scope")] for row in grouped_counts],
        ),
        _table("Review packet", ["owner_role", "review_state", "action_authorized"], [[OWNER, state, False]]),
    ))
    return result, events


if __name__ == "__main__":
    run_cli(solve, scenario_id="retail-03")
