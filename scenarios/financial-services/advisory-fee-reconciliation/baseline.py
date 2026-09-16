"""Exact, review-only reconciliation of supplied synthetic advisory fee exports."""
from __future__ import annotations

import calendar
import re
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta, timezone
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "_shared"))
from scenario_support import run_cli


MAX_MONEY = 1_000_000_000_000
MAX_ROWS = 5000
ID = re.compile(r"SYN-[A-Z0-9][A-Z0-9-]{0,75}", re.ASCII)
DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", re.ASCII)
INSTANT = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]{1,6})?(?:Z|[+-](?:[01][0-9]|2[0-3]):[0-5][0-9])",
    re.ASCII,
)
SOURCE_KEYS = {
    "engagements": "billing_account_id",
    "schedule_versions": "schedule_id",
    "synthetic_value_intervals": "valuation_id",
    "draft_fee_lines": "draft_id",
}
MESSAGES = {
    "invalid-object": "Expected an object with the documented fields.",
    "invalid-fields": "Object fields do not match the documented contract.",
    "invalid-array": "Expected an array with at most 5000 rows.",
    "invalid-id": "Expected a 5-80 character uppercase ASCII synthetic ID beginning SYN-.",
    "invalid-date": "Expected a valid YYYY-MM-DD calendar date.",
    "invalid-timestamp": "Expected an offset-bearing RFC3339 timestamp with seconds and at most six fractional digits.",
    "invalid-interval": "Interval start must precede its exclusive end.",
    "invalid-period": "Billing period must contain 1 through 366 calendar days.",
    "period-not-closed": "Billing period has not ended at the supplied business offset as of as_of.",
    "policy-not-approved": "Top-level synthetic billing controls are pending; financial decisions are blocked.",
    "duplicate-id": "Technical identifiers must be unique, including identical duplicate rows.",
    "unknown-account": "Authoritative evidence references an unknown billing account.",
    "agreement-mismatch": "Schedule agreement does not match its engagement.",
    "currency-mismatch": "Authoritative currency does not match the billing configuration.",
    "invalid-approval": "Approved schedules require approved_at; pending schedules require null.",
    "invalid-bands": "Marginal bands require strictly increasing positive finite upper bounds and one final unbounded band.",
    "overlapping-approved-schedules": "Approved schedules overlap; no authoritative schedule can be selected.",
    "overlapping-value-intervals": "Authoritative value intervals overlap; no value can be selected.",
    "missing-schedule-coverage": "No eligible approved schedule covers this billable interval; the account is held.",
    "missing-value-coverage": "No explicit value covers this billable interval; the account is held.",
    "pending-approval": "Pending schedule does not override approved evidence; review the request.",
    "approved-after-as-of": "Schedule approval is after as_of and is not eligible; review the excluded version.",
    "missing-draft": "No draft matches the account/period/currency key; no zero draft is inferred.",
    "duplicate-drafts": "Multiple drafts share the account/period/currency key; comparison is held.",
    "orphan-draft": "Draft references an unknown billing account and is excluded.",
    "wrong-period-draft": "Draft period differs from the billing period and is excluded.",
    "wrong-currency-draft": "Draft currency differs from the billing currency and is excluded.",
    "not-billable-draft": "Draft account has no billable days in this period and is excluded.",
    "uncomputed-draft": "Draft cannot be compared because account coverage is incomplete.",
    "draft-overstatement": "Draft exceeds the recomputed fee beyond the inclusive tolerance.",
    "draft-understatement": "Draft is below the recomputed fee beyond the inclusive tolerance.",
}


def _review():
    return {
        "human_review": "pending",
        "live_action": "none",
        "owner_role": "Billing manager or compliance reviewer",
        "summary": "Synthetic review only; no fee invoice, debit, refund, trade, advice, or regulatory opinion.",
    }


def _exception(code, scope=(None, None), *, related=(), start=None, end=None,
               field=None, message=None):
    return {
        "code": code,
        "message": MESSAGES[code] if message is None else message,
        "billing_account_id": scope[0],
        "record_id": scope[1],
        "related_ids": sorted(set(related)),
        "from_date": start.isoformat() if isinstance(start, date) else start,
        "to_date": end.isoformat() if isinstance(end, date) else end,
        "field": field,
    }


class InputRejected(ValueError):
    def __init__(self, diagnostic):
        super().__init__(diagnostic["message"])
        self.diagnostic = diagnostic


def _fail(code, field=None, scope=(None, None), **details):
    raise InputRejected(_exception(code, scope, field=field, **details))


def _fields(value, required, path, scope=(None, None), optional=()):
    if type(value) is not dict:
        _fail("invalid-object", path, scope)
    keys = set(value)
    if set(required) - keys or keys - set(required) - set(optional):
        _fail("invalid-fields", path, scope)


def _integer(value, minimum, maximum, path, scope=(None, None)):
    if type(value) is not int or not minimum <= value <= maximum:
        _fail("invalid-integer", path, scope,
              message=f"Expected an integer from {minimum} through {maximum}.")
    return value


def _enum(value, choices, path, scope=(None, None)):
    if type(value) is not str or value not in choices:
        _fail("invalid-enum", path, scope,
              message=f"Unsupported value; allowed: {', '.join(sorted(choices))}.")
    return value


def _valid_id(value):
    return type(value) is str and ID.fullmatch(value) is not None


def _identifier(value, path, scope=(None, None)):
    if not _valid_id(value):
        _fail("invalid-id", path, scope)
    return value


def _date(value, path, scope=(None, None)):
    if type(value) is not str or DATE.fullmatch(value) is None:
        _fail("invalid-date", path, scope)
    try:
        return date.fromisoformat(value)
    except ValueError:
        _fail("invalid-date", path, scope)


def _instant(value, path, scope=(None, None)):
    if (type(value) is not str or INSTANT.fullmatch(value) is None
            or value.endswith("-00:00")):
        _fail("invalid-timestamp", path, scope)
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except (ValueError, OverflowError):
        _fail("invalid-timestamp", path, scope)


def _array(value, path, scope=(None, None)):
    if type(value) is not list or len(value) > MAX_ROWS:
        _fail("invalid-array", path, scope)


def _context(row, id_key):
    if type(row) is not dict:
        return None, None
    account = row.get("billing_account_id")
    record = row.get(id_key)
    return account if _valid_id(account) else None, record if _valid_id(record) else None


def _source_rows(payload, source, required, optional=()):
    rows = payload[source]
    id_key = SOURCE_KEYS[source]
    _array(rows, source)
    for index, row in enumerate(rows):
        path = f"{source}[{index}]"
        scope = _context(row, id_key)
        _fields(row, required, path, scope, optional)
        _identifier(row[id_key], f"{path}.{id_key}", scope)
    counts = Counter(row[id_key] for row in rows)
    duplicates = sorted(key for key, count in counts.items() if count > 1)
    if duplicates:
        key = duplicates[0]
        contexts = [_context(row, id_key) for row in rows if row[id_key] == key]
        scope = min(contexts, key=lambda item: (item[0] or "", item[1] or ""))
        _fail("duplicate-id", f"{source}.{id_key}", scope, related=[key])
    return [dict(row) for row in sorted(rows, key=lambda item: item[id_key])]


def _interval(row, start_key, end_key, path, scope, *, nullable_end=False):
    start = _date(row[start_key], f"{path}.{start_key}", scope)
    end = None if nullable_end and row[end_key] is None else _date(row[end_key], f"{path}.{end_key}", scope)
    if end is not None and start >= end:
        _fail("invalid-interval", path, scope)
    row["_start"], row["_end"] = start, end


def _check_overlaps(rows, id_key, code):
    ordered = sorted(rows, key=lambda row: (
        row["billing_account_id"], row["_start"], row["_end"], row[id_key],
    ))
    for left, right in zip(ordered, ordered[1:]):
        if left["billing_account_id"] != right["billing_account_id"]:
            continue
        if right["_start"] < left["_end"]:
            ids = sorted([left[id_key], right[id_key]])
            _fail(code, scope=(left["billing_account_id"], ids[0]), related=ids,
                  start=max(left["_start"], right["_start"]), end=min(left["_end"], right["_end"]))


def _validate(payload):
    _fields(payload, {
        "schema_version", "as_of", "business_utc_offset_minutes", "billing_configuration",
        *SOURCE_KEYS,
    }, "$")
    _integer(payload["schema_version"], 1, 1, "schema_version")
    as_of = _instant(payload["as_of"], "as_of")
    offset = _integer(payload["business_utc_offset_minutes"], -840, 840, "business_utc_offset_minutes")
    cfg_path = "billing_configuration"
    _fields(payload[cfg_path], {
        "control_version", "approval_state", "period_start", "period_end",
        "currency", "day_count_basis", "rounding_mode",
    }, cfg_path, optional={"variance_tolerance_minor"})
    cfg = dict(payload[cfg_path])
    _identifier(cfg["control_version"], f"{cfg_path}.control_version")
    _enum(cfg["approval_state"], ("approved", "pending"), f"{cfg_path}.approval_state")
    cfg["_start"] = _date(cfg["period_start"], f"{cfg_path}.period_start")
    cfg["_end"] = _date(cfg["period_end"], f"{cfg_path}.period_end")
    _enum(cfg["currency"], ("USD", "EUR"), f"{cfg_path}.currency")
    _enum(cfg["day_count_basis"], ("actual-calendar-year", "act-365-fixed"), f"{cfg_path}.day_count_basis")
    _enum(cfg["rounding_mode"], ("half-up", "half-even"), f"{cfg_path}.rounding_mode")
    cfg["variance_tolerance_minor"] = _integer(
        cfg.get("variance_tolerance_minor", 1), 0, MAX_MONEY, f"{cfg_path}.variance_tolerance_minor",
    )
    if not 1 <= (cfg["_end"] - cfg["_start"]).days <= 366:
        _fail("invalid-period", cfg_path)
    fixed_offset = timezone(timedelta(minutes=offset))
    try:
        business_as_of = as_of.astimezone(fixed_offset)
    except OverflowError:
        _fail("invalid-timestamp", "as_of")
    if datetime.combine(cfg["_end"], time.min, fixed_offset) > business_as_of:
        _fail("period-not-closed", f"{cfg_path}.period_end")
    if cfg["approval_state"] != "approved":
        _fail("policy-not-approved", f"{cfg_path}.approval_state")

    engagements = _source_rows(payload, "engagements", {
        "billing_account_id", "agreement_id", "currency", "active_from", "active_to",
    })
    for row in engagements:
        scope = _context(row, "billing_account_id")
        path = f"engagements[{row['billing_account_id']}]"
        _identifier(row["agreement_id"], f"{path}.agreement_id", scope)
        _enum(row["currency"], ("USD", "EUR"), f"{path}.currency", scope)
        _interval(row, "active_from", "active_to", path, scope, nullable_end=True)

    schedules = _source_rows(payload, "schedule_versions", {
        "schedule_id", "billing_account_id", "agreement_id", "effective_from",
        "effective_to", "approval_state", "approved_at", "bands",
    })
    for row in schedules:
        scope = _context(row, "schedule_id")
        path = f"schedule_versions[{row['schedule_id']}]"
        _identifier(row["billing_account_id"], f"{path}.billing_account_id", scope)
        _identifier(row["agreement_id"], f"{path}.agreement_id", scope)
        _interval(row, "effective_from", "effective_to", path, scope)
        _enum(row["approval_state"], ("approved", "pending"), f"{path}.approval_state", scope)
        if (row["approval_state"] == "approved") == (row["approved_at"] is None):
            _fail("invalid-approval", f"{path}.approved_at", scope)
        approved = None if row["approved_at"] is None else _instant(row["approved_at"], f"{path}.approved_at", scope)
        row["_excluded_reason"] = (
            "pending-approval" if row["approval_state"] == "pending"
            else "approved-after-as-of" if approved > as_of else None
        )
        band_path = f"{path}.bands"
        _array(row["bands"], band_path, scope)
        if not row["bands"]:
            _fail("invalid-bands", band_path, scope)
        lower = 0
        for index, band in enumerate(row["bands"]):
            item_path = f"{band_path}[{index}]"
            _fields(band, {"upper_value_minor", "annual_rate_bps"}, item_path, scope)
            upper = band["upper_value_minor"]
            if upper is not None:
                _integer(upper, 1, MAX_MONEY, f"{item_path}.upper_value_minor", scope)
            _integer(band["annual_rate_bps"], 0, 10000, f"{item_path}.annual_rate_bps", scope)
            if (upper is None) != (index == len(row["bands"]) - 1):
                _fail("invalid-bands", band_path, scope)
            if upper is not None:
                if upper <= lower:
                    _fail("invalid-bands", band_path, scope)
                lower = upper
        row["bands"] = [dict(band) for band in row["bands"]]

    values = _source_rows(payload, "synthetic_value_intervals", {
        "valuation_id", "billing_account_id", "currency", "from_date", "to_date", "billable_value_minor",
    })
    for row in values:
        scope = _context(row, "valuation_id")
        path = f"synthetic_value_intervals[{row['valuation_id']}]"
        _identifier(row["billing_account_id"], f"{path}.billing_account_id", scope)
        _enum(row["currency"], ("USD", "EUR"), f"{path}.currency", scope)
        _interval(row, "from_date", "to_date", path, scope)
        _integer(row["billable_value_minor"], 0, MAX_MONEY, f"{path}.billable_value_minor", scope)

    drafts = _source_rows(payload, "draft_fee_lines", {
        "draft_id", "billing_account_id", "period_start", "period_end", "currency", "amount_minor",
    }, {"source_schedule_id"})
    for row in drafts:
        scope = _context(row, "draft_id")
        path = f"draft_fee_lines[{row['draft_id']}]"
        _identifier(row["billing_account_id"], f"{path}.billing_account_id", scope)
        _interval(row, "period_start", "period_end", path, scope)
        _enum(row["currency"], ("USD", "EUR"), f"{path}.currency", scope)
        _integer(row["amount_minor"], 0, MAX_MONEY, f"{path}.amount_minor", scope)
        row["source_schedule_id"] = row.get("source_schedule_id")
        if row["source_schedule_id"] is not None:
            _identifier(row["source_schedule_id"], f"{path}.source_schedule_id", scope)

    accounts = {row["billing_account_id"]: row for row in engagements}
    for source, rows in (("schedule_versions", schedules), ("synthetic_value_intervals", values)):
        id_key = SOURCE_KEYS[source]
        for row in rows:
            if row["billing_account_id"] not in accounts:
                _fail("unknown-account", f"{source}[{row[id_key]}].billing_account_id", _context(row, id_key))
    for row in schedules:
        if row["agreement_id"] != accounts[row["billing_account_id"]]["agreement_id"]:
            _fail("agreement-mismatch", f"schedule_versions[{row['schedule_id']}].agreement_id",
                  _context(row, "schedule_id"))
    for source, rows in (("engagements", engagements), ("synthetic_value_intervals", values)):
        id_key = SOURCE_KEYS[source]
        for row in rows:
            if row["currency"] != cfg["currency"]:
                _fail("currency-mismatch", f"{source}[{row[id_key]}].currency", _context(row, id_key))
    eligible = [row for row in schedules if row["_excluded_reason"] is None]
    _check_overlaps(eligible, "schedule_id", "overlapping-approved-schedules")
    _check_overlaps(values, "valuation_id", "overlapping-value-intervals")
    return cfg, engagements, schedules, values, drafts


def _table(title, columns, rows, highlights=()):
    visible = rows[:8]
    return {
        "title": title if len(rows) <= 8 else f"{title} (first 8 of {len(rows)})",
        "columns": columns,
        "rows": visible,
        "total_rows": len(rows),
        "highlight_rows": sorted({index for index in highlights if 0 <= index < len(visible)}),
    }


def _event(step_id, kind, caption, facts, *tables):
    return {"step_id": step_id, "kind": kind, "caption": caption, "facts": facts, "tables": list(tables)}


def _preview(value):
    return value if value is None or type(value) in (str, int, bool) else "invalid"


def _intake(payload):
    root = payload if type(payload) is dict else {}
    config = root.get("billing_configuration")
    config = config if type(config) is dict else {}
    counts = [
        [source, len(root[source]) if type(root.get(source)) is list else "invalid-or-missing"]
        for source in SOURCE_KEYS
    ]
    return _event(
        "intake-billing-exports", "input", "Read the supplied synthetic exports without changing any source row.",
        {
            "as_of": _preview(root.get("as_of")),
            "period_start": _preview(config.get("period_start")),
            "period_end": _preview(config.get("period_end")),
            "synthetic_only": True,
        },
        _table("Observed input source counts", ["source", "rows"], counts),
    )


def _group(rows):
    grouped = defaultdict(list)
    for row in rows:
        grouped[row["billing_account_id"]].append(row)
    return grouped


def _intersection(start, end, row):
    if start is None:
        return None
    lower, upper = max(start, row["_start"]), min(end, row["_end"])
    return (lower, upper) if lower < upper else None


def _join_segments(cfg, engagements, schedules, values):
    eligible = _group([row for row in schedules if row["_excluded_reason"] is None])
    account_values = _group(values)
    reviews, segments, changes, exceptions = [], [], [], []
    active_intervals = {}
    for engagement in engagements:
        account = engagement["billing_account_id"]
        start = max(cfg["_start"], engagement["_start"])
        end = min(cfg["_end"], engagement["_end"]) if engagement["_end"] is not None else cfg["_end"]
        if start >= end:
            start = end = None
        active_intervals[account] = (start, end)
        account_segments = []
        if start is not None:
            boundaries = {start, end}
            for row in eligible[account] + account_values[account]:
                intersection = _intersection(start, end, row)
                if intersection:
                    boundaries.update(intersection)
            if cfg["day_count_basis"] == "actual-calendar-year":
                for year in range(start.year + 1, end.year + 1):
                    boundary = date(year, 1, 1)
                    if start < boundary < end:
                        boundaries.add(boundary)
            points = sorted(boundaries)
            for index, (lower, upper) in enumerate(zip(points, points[1:]), 1):
                schedule = next((row for row in eligible[account]
                                 if row["_start"] <= lower and upper <= row["_end"]), None)
                value = next((row for row in account_values[account]
                              if row["_start"] <= lower and upper <= row["_end"]), None)
                coverage = (
                    "complete" if schedule is not None and value is not None
                    else "missing-schedule-and-value" if schedule is None and value is None
                    else "missing-schedule" if schedule is None else "missing-value"
                )
                denominator = 366 if cfg["day_count_basis"] == "actual-calendar-year" and calendar.isleap(lower.year) else 365
                segment = {
                    "billing_account_id": account,
                    "segment_index": index,
                    "segment_start": lower.isoformat(),
                    "segment_end": upper.isoformat(),
                    "days": (upper - lower).days,
                    "day_count_denominator": denominator,
                    "schedule_id": schedule["schedule_id"] if schedule is not None else None,
                    "valuation_id": value["valuation_id"] if value is not None else None,
                    "coverage": coverage,
                    "calculation_status": "held-account",
                    "billable_value_minor": value["billable_value_minor"] if value is not None else None,
                    "annual_numerator": None,
                    "bands": [],
                    "exact_fee_minor": None,
                }
                account_segments.append(segment)
                evidence = [item for item in (segment["schedule_id"], segment["valuation_id"]) if item is not None]
                for missing, code in ((schedule is None, "missing-schedule-coverage"),
                                      (value is None, "missing-value-coverage")):
                    if missing:
                        exceptions.append(_exception(code, (account, account), related=evidence, start=lower, end=upper))
        status = (
            "not-billable" if not account_segments
            else "computed" if all(row["coverage"] == "complete" for row in account_segments)
            else "held-missing-coverage"
        )
        if status == "computed":
            for segment in account_segments:
                segment["calculation_status"] = "computed"
        segments.extend(account_segments)
        reviews.append({
            "billing_account_id": account,
            "agreement_id": engagement["agreement_id"],
            "currency": engagement["currency"],
            "active_start": start.isoformat() if start is not None else None,
            "active_end": end.isoformat() if end is not None else None,
            "active_days": (end - start).days if start is not None else 0,
            "calculation_status": status,
            "exact_fee_minor": None,
            "computed_fee_minor": None,
            "rounding_decision": None,
            "draft_ids": [],
            "comparison_status": "not-billable" if status == "not-billable" else "uncomputed",
            "draft_fee_minor": None,
            "delta_minor": None,
            "pending_change_ids": [],
            "review_flags": [],
        })
    reviews_by_id = {row["billing_account_id"]: row for row in reviews}
    schedule_order = sorted(schedules, key=lambda row: (row["billing_account_id"], row["schedule_id"]))
    for schedule in schedule_order:
        reason = schedule["_excluded_reason"]
        if reason is None:
            continue
        account = schedule["billing_account_id"]
        intersection = _intersection(*active_intervals[account], schedule)
        changes.append({
            "billing_account_id": account,
            "schedule_id": schedule["schedule_id"],
            "approval_state": schedule["approval_state"],
            "approved_at": schedule["approved_at"],
            "effective_from": schedule["effective_from"],
            "effective_to": schedule["effective_to"],
            "exclusion_reason": reason,
            "intersects_billable_period": intersection is not None,
        })
        if intersection:
            reviews_by_id[account]["pending_change_ids"].append(schedule["schedule_id"])
            exceptions.append(_exception(
                reason, (account, schedule["schedule_id"]), related=[schedule["schedule_id"]],
                start=intersection[0], end=intersection[1],
            ))
    joined_schedules = {row["schedule_id"] for row in segments if row["schedule_id"] is not None}
    joined_values = {row["valuation_id"] for row in segments if row["valuation_id"] is not None}
    dispositions = {
        "engagements": [
            {"billing_account_id": row["billing_account_id"],
             "disposition": "billable" if row["active_days"] else "not-billable"}
            for row in reviews
        ],
        "schedule_versions": [
            {"schedule_id": row["schedule_id"], "billing_account_id": row["billing_account_id"],
             "disposition": row["_excluded_reason"] or ("joined" if row["schedule_id"] in joined_schedules else "outside-billable-period")}
            for row in schedule_order
        ],
        "synthetic_value_intervals": [
            {"valuation_id": row["valuation_id"], "billing_account_id": row["billing_account_id"],
             "disposition": "joined" if row["valuation_id"] in joined_values else "outside-billable-period"}
            for row in sorted(values, key=lambda row: (row["billing_account_id"], row["valuation_id"]))
        ],
    }
    return reviews, segments, changes, dispositions, exceptions


def _calculate_tiers(segments, schedules):
    by_id = {row["schedule_id"]: row for row in schedules}
    for segment in segments:
        if segment["calculation_status"] != "computed":
            continue
        lower, total = 0, 0
        value = segment["billable_value_minor"]
        for index, band in enumerate(by_id[segment["schedule_id"]]["bands"], 1):
            upper = band["upper_value_minor"]
            band_value = max(0, (value if upper is None else min(value, upper)) - lower)
            numerator = band_value * band["annual_rate_bps"]
            segment["bands"].append({
                "band_index": index,
                "lower_value_minor": lower,
                "upper_value_minor": upper,
                "annual_rate_bps": band["annual_rate_bps"],
                "band_value_minor": band_value,
                "annual_numerator": numerator,
            })
            total += numerator
            if upper is not None:
                lower = upper
        segment["annual_numerator"] = total


def _fraction(value):
    return {"numerator": value.numerator, "denominator": value.denominator}


def _round_once(value, mode):
    lower, remainder = divmod(value.numerator, value.denominator)
    twice = 2 * remainder
    if remainder == 0:
        return lower, "exact"
    if twice < value.denominator:
        return lower, "below-half-down"
    if twice > value.denominator:
        return lower + 1, "above-half-up"
    if mode == "half-up":
        return lower + 1, "half-up"
    return (lower, "half-even-down") if lower % 2 == 0 else (lower + 1, "half-even-up")


def _prorate_and_round(cfg, reviews, segments):
    exact_accounts = defaultdict(Fraction)
    for segment in segments:
        if segment["calculation_status"] != "computed":
            continue
        amount = Fraction(
            segment["annual_numerator"] * segment["days"],
            10000 * segment["day_count_denominator"],
        )
        segment["exact_fee_minor"] = _fraction(amount)
        exact_accounts[segment["billing_account_id"]] += amount
    for review in reviews:
        if review["calculation_status"] == "computed":
            exact = exact_accounts[review["billing_account_id"]]
            review["exact_fee_minor"] = _fraction(exact)
            review["computed_fee_minor"], review["rounding_decision"] = _round_once(exact, cfg["rounding_mode"])


def _join_drafts(cfg, reviews, drafts, exceptions):
    by_account = {row["billing_account_id"]: row for row in reviews}
    candidates = defaultdict(list)
    reports = {}

    def draft_exception(code, account, record, related):
        exceptions.append(_exception(
            code, (account, record), related=related, start=cfg["_start"], end=cfg["_end"],
        ))

    for draft in drafts:
        account, draft_id = draft["billing_account_id"], draft["draft_id"]
        reports[draft_id] = {
            key: draft[key] for key in (
                "draft_id", "billing_account_id", "currency", "period_start",
                "period_end", "source_schedule_id", "amount_minor",
            )
        }
        reports[draft_id].update({
            "disposition": "uncomputed-account", "computed_fee_minor": None,
            "delta_minor": None, "comparison_status": None,
        })
        external = None
        if account not in by_account:
            external = ("orphan-account", "orphan-draft")
        elif (draft["period_start"], draft["period_end"]) != (cfg["period_start"], cfg["period_end"]):
            external = ("wrong-period", "wrong-period-draft")
        elif draft["currency"] != cfg["currency"]:
            external = ("wrong-currency", "wrong-currency-draft")
        elif by_account[account]["calculation_status"] == "not-billable":
            external = ("not-billable-account", "not-billable-draft")
        if external:
            reports[draft_id]["disposition"] = external[0]
            draft_exception(external[1], account, draft_id, [draft_id])
        else:
            candidates[account].append(draft)

    for review in reviews:
        account = review["billing_account_id"]
        if review["calculation_status"] == "not-billable":
            continue
        matching = sorted(candidates[account], key=lambda row: row["draft_id"])
        ids = [row["draft_id"] for row in matching]
        review["draft_ids"] = ids
        computed = review["calculation_status"] == "computed"
        if not matching:
            review["comparison_status"] = "missing-draft" if computed else "uncomputed"
            draft_exception("missing-draft", account, account, [])
        elif len(matching) > 1:
            review["comparison_status"] = "duplicate-drafts" if computed else "uncomputed"
            for draft_id in ids:
                reports[draft_id]["disposition"] = "duplicate-draft"
            draft_exception("duplicate-drafts", account, ids[0], ids)
        else:
            draft = matching[0]
            draft_id = draft["draft_id"]
            review["draft_fee_minor"] = draft["amount_minor"]
            if not computed:
                review["comparison_status"] = "uncomputed"
                draft_exception("uncomputed-draft", account, draft_id, [draft_id])
                continue
            delta = draft["amount_minor"] - review["computed_fee_minor"]
            comparison = (
                "matched" if abs(delta) <= cfg["variance_tolerance_minor"]
                else "draft-overstatement" if delta > 0 else "draft-understatement"
            )
            review["delta_minor"], review["comparison_status"] = delta, comparison
            reports[draft_id].update({
                "disposition": "compared", "computed_fee_minor": review["computed_fee_minor"],
                "delta_minor": delta, "comparison_status": comparison,
            })
            if comparison != "matched":
                draft_exception(comparison, account, draft_id, [draft_id])
    return sorted(reports.values(), key=lambda row: (
        row["billing_account_id"], row["period_start"], row["period_end"], row["currency"], row["draft_id"],
    ))


def _populations(cfg, reviews):
    computed = [row for row in reviews if row["calculation_status"] == "computed"]
    comparable = [row for row in computed if row["delta_minor"] is not None]
    missing = [row for row in computed if row["comparison_status"] == "missing-draft"]
    duplicate = [row for row in computed if row["comparison_status"] == "duplicate-drafts"]
    uncomputed = [row["billing_account_id"] for row in reviews if row["calculation_status"] == "held-missing-coverage"]
    inactive = [row["billing_account_id"] for row in reviews if row["calculation_status"] == "not-billable"]
    return {
        "currency": cfg["currency"],
        "account_count": len(reviews),
        "computed": {"account_count": len(computed), "fee_minor": sum(row["computed_fee_minor"] for row in computed)},
        "comparable": {
            "account_count": len(comparable),
            "computed_fee_minor": sum(row["computed_fee_minor"] for row in comparable),
            "draft_fee_minor": sum(row["draft_fee_minor"] for row in comparable),
            "delta_minor": sum(row["delta_minor"] for row in comparable),
        },
        "computed_missing_draft": {
            "account_count": len(missing), "computed_fee_minor": sum(row["computed_fee_minor"] for row in missing),
        },
        "computed_duplicate_drafts": {
            "account_count": len(duplicate), "computed_fee_minor": sum(row["computed_fee_minor"] for row in duplicate),
        },
        "uncomputed": {"account_count": len(uncomputed), "billing_account_ids": uncomputed},
        "not_billable": {"account_count": len(inactive), "billing_account_ids": inactive},
    }


def _fraction_text(value):
    return f"{value['numerator']}/{value['denominator']}" if value is not None else "not-computed"


def solve(payload):
    events = [_intake(payload)]
    try:
        cfg, engagements, schedules, values, drafts = _validate(payload)
    except InputRejected as error:
        diagnostic = error.diagnostic
        events.append(_event(
            "validate-billing-evidence", "validation",
            "Rejected the supplied evidence before any financial calculation.",
            {"accepted": False, "code": diagnostic["code"]},
            _table("Validation diagnostic", ["account", "record", "code", "field"],
                   [[diagnostic["billing_account_id"], diagnostic["record_id"], diagnostic["code"], diagnostic["field"]]], [0]),
        ))
        result = {
            "schema_version": 1, "status": "rejected",
            "outputs": {"validation": {"accepted": False, "rejected_before_calculation": True}, "review": _review()},
            "exceptions": [diagnostic],
        }
        events.append(_event(
            "emit-billing-review", "output", "Returned a rejection diagnostic, pending human review, and no financial totals.",
            {"status": "rejected", "human_review": "pending", "live_action": "none"},
            _table("Rejected review packet", ["code", "message"], [[diagnostic["code"], diagnostic["message"]]], [0]),
        ))
        return result, events

    excluded_count = sum(row["_excluded_reason"] is not None for row in schedules)
    events.append(_event(
        "validate-billing-evidence", "validation",
        "Validated the closed period, strict integers and IDs, marginal ranges, references, and nonoverlapping authoritative intervals.",
        {
            "accepted": True, "currency": cfg["currency"], "period_days": (cfg["_end"] - cfg["_start"]).days,
            "eligible_schedules": len(schedules) - excluded_count,
            "excluded_schedules": excluded_count, "tolerance_minor": cfg["variance_tolerance_minor"],
        },
        _table("Validated sample controls", ["control", "value"], [
            ["approval", cfg["approval_state"]], ["day_count_basis", cfg["day_count_basis"]],
            ["rounding_mode", cfg["rounding_mode"]],
            ["fixed_offset_minutes", payload["business_utc_offset_minutes"]],
        ]),
    ))

    reviews, segments, changes, dispositions, exceptions = _join_segments(cfg, engagements, schedules, values)
    events.append(_event(
        "join-effective-segments", "join",
        "Intersected active dates with eligible schedule/value boundaries and applicable calendar-year boundaries; preserved coverage holds.",
        {
            "segments": len(segments), "billable_accounts": sum(row["active_days"] > 0 for row in reviews),
            "held_accounts": sum(row["calculation_status"] == "held-missing-coverage" for row in reviews),
            "excluded_changes": len(changes),
        },
        _table("Actual effective-date joins", ["account", "start", "end", "days", "schedule", "value_id"], [
            [row["billing_account_id"], row["segment_start"], row["segment_end"], row["days"], row["schedule_id"], row["valuation_id"]]
            for row in segments
        ], [index for index, row in enumerate(segments) if row["coverage"] != "complete"]),
    ))

    _calculate_tiers(segments, schedules)
    band_rows = [
        [row["billing_account_id"], row["segment_index"], band["band_index"],
         band["band_value_minor"], band["annual_rate_bps"], band["annual_numerator"]]
        for row in segments for band in row["bands"]
    ]
    events.append(_event(
        "calculate-marginal-tiers", "decision",
        "Allocated each computed segment's value across every marginal band, including zero slices, and multiplied cents by annual bps.",
        {"band_slices": len(band_rows), "numerator_unit": "cent-basis-points", "cent_rounding_applied": False},
        _table("Observed marginal tier arithmetic", ["account", "segment", "band", "value_minor", "annual_bps", "annual_numerator"], band_rows),
    ))

    _prorate_and_round(cfg, reviews, segments)
    events.append(_event(
        "prorate-and-round", "decision",
        "Computed exact reduced segment fractions; summed them before the sole account-period cent rounding.",
        {"rounding_mode": cfg["rounding_mode"], "basis": cfg["day_count_basis"], "rounding_scope": "account-period"},
        _table("Exact segment fees in cents", ["account", "segment", "days", "year_divisor", "numerator", "denominator"], [
            [row["billing_account_id"], row["segment_index"], row["days"], row["day_count_denominator"],
             row["exact_fee_minor"]["numerator"] if row["exact_fee_minor"] is not None else None,
             row["exact_fee_minor"]["denominator"] if row["exact_fee_minor"] is not None else None]
            for row in segments
        ]),
        _table("One final rounding per account", ["account", "exact_minor", "rounded_minor", "decision"], [
            [row["billing_account_id"], _fraction_text(row["exact_fee_minor"]), row["computed_fee_minor"], row["rounding_decision"]]
            for row in reviews
        ]),
    ))

    draft_reports = _join_drafts(cfg, reviews, drafts, exceptions)
    events.append(_event(
        "join-draft-fees", "join",
        "Classified every draft by the exact account/period/currency key; only a unique draft on a computed account has a signed comparison.",
        {
            "draft_rows": len(draft_reports), "comparable_accounts": sum(row["delta_minor"] is not None for row in reviews),
            "tolerance_minor": cfg["variance_tolerance_minor"],
        },
        _table("Actual account draft comparisons", ["account", "draft_count", "computed_minor", "draft_minor", "delta_minor", "decision"], [
            [row["billing_account_id"], len(row["draft_ids"]), row["computed_fee_minor"],
             row["draft_fee_minor"], row["delta_minor"], row["comparison_status"]]
            for row in reviews
        ], [index for index, row in enumerate(reviews) if row["comparison_status"] != "matched"]),
        _table("Every draft disposition", ["account", "draft", "amount_minor", "source_label", "disposition"], [
            [row["billing_account_id"], row["draft_id"], row["amount_minor"], row["source_schedule_id"], row["disposition"]]
            for row in draft_reports
        ]),
    ))

    exceptions.sort(key=lambda row: (
        row["billing_account_id"] or "", row["record_id"] or "", row["code"],
        row["from_date"] or "", row["to_date"] or "", row["field"] or "", row["related_ids"],
    ))
    flags = defaultdict(set)
    for exception in exceptions:
        flags[exception["billing_account_id"]].add(exception["code"])
    for review in reviews:
        review["review_flags"] = sorted(flags[review["billing_account_id"]])
    events.append(_event(
        "route-billing-exceptions", "exception",
        "Routed actual missing evidence, excluded changes, draft holds, and variances without charging or refunding anyone.",
        {"exceptions": len(exceptions), "flagged_accounts": sum(bool(row["review_flags"]) for row in reviews), "live_action": "none"},
        _table("Sorted billing review queue", ["account", "record", "code", "start", "end"], [
            [row["billing_account_id"], row["record_id"], row["code"], row["from_date"], row["to_date"]]
            for row in exceptions
        ], range(min(8, len(exceptions)))),
    ))

    totals = _populations(cfg, reviews)
    billing_period = {
        key: cfg[key] for key in (
            "period_start", "period_end", "currency", "day_count_basis", "rounding_mode", "variance_tolerance_minor",
        )
    }
    billing_period.update({"as_of": payload["as_of"], "business_utc_offset_minutes": payload["business_utc_offset_minutes"]})
    result = {
        "schema_version": 1,
        "status": "completed_with_exceptions" if exceptions else "completed",
        "outputs": {
            "billing_period": billing_period,
            "account_reviews": reviews, "calculation_segments": segments,
            "draft_comparisons": draft_reports, "pending_changes": changes,
            "evidence_dispositions": dispositions, "population_totals": totals, "review": _review(),
        },
        "exceptions": exceptions,
    }
    population_rows = [
        ["computed", totals["computed"]["account_count"], totals["computed"]["fee_minor"], None, None],
        ["comparable", totals["comparable"]["account_count"], totals["comparable"]["computed_fee_minor"],
         totals["comparable"]["draft_fee_minor"], totals["comparable"]["delta_minor"]],
        ["computed_missing_draft", totals["computed_missing_draft"]["account_count"],
         totals["computed_missing_draft"]["computed_fee_minor"], None, None],
        ["computed_duplicate_drafts", totals["computed_duplicate_drafts"]["account_count"],
         totals["computed_duplicate_drafts"]["computed_fee_minor"], None, None],
        ["uncomputed", totals["uncomputed"]["account_count"], None, None, None],
        ["not_billable", totals["not_billable"]["account_count"], None, None, None],
    ]
    events.append(_event(
        "emit-billing-review", "output",
        "Emitted full account, segment, tier, draft, and source dispositions with separate comparison populations and pending human review.",
        {
            "status": result["status"], "computed_minor": totals["computed"]["fee_minor"],
            "comparable_delta_minor": totals["comparable"]["delta_minor"],
            "human_review": "pending", "live_action": "none",
        },
        _table("Observed population totals in cents", ["population", "accounts", "computed_minor", "draft_minor", "delta_minor"], population_rows),
    ))
    return result, events


if __name__ == "__main__":
    run_cli(solve, scenario_id="financial-services-03")
