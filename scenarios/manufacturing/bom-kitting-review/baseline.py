"""Synthetic office-only BOM review; no inventory or production operations."""
from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal, Inexact, ROUND_CEILING, localcontext
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "_shared"))
from scenario_support import run_cli


MAX_QUANTITY = 1_000_000
MAX_ROWS = 200
MAX_DEPTH = 8
MAX_PATHS = 5000
MAX_RESULT_BYTES = 8 * 1024 * 1024
IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,39}\Z")
DECIMAL_TEXT = re.compile(r"(?:0|[1-9][0-9]*)(?:\.[0-9]{0,3}[1-9])?\Z")
DATE_TEXT = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}\Z")
TABLE_FIELDS = {
    "work_orders": (
        "order_id", "item_id", "site", "start_date", "quantity", "priority",
        "requested_version_id",
    ),
    "bom_versions": (
        "version_id", "item_id", "site", "valid_from", "valid_to",
        "min_order_qty", "max_order_qty", "approved", "active",
    ),
    "bom_lines": (
        "line_id", "version_id", "component_id", "line_type", "quantity_per",
        "scrap_percent",
    ),
    "items": ("item_id", "unit", "expiry_controlled"),
    "stock_lots": (
        "stock_id", "item_id", "site", "quantity", "reserved_external_qty",
        "status", "expires_on",
    ),
    "inbound": (
        "receipt_id", "item_id", "site", "expected_on", "quantity", "confirmed",
    ),
}
PRIMARY_ID = {table: fields[0] for table, fields in TABLE_FIELDS.items()}
ISSUE_SORT = ("code", "order_id", "source_type", "source_id", "field", "message")
SUPPLY_ORDER = {"stock_lots": 0, "inbound": 1}
REVIEW_ORDER = {
    "unresolved-review": 0,
    "shortage-review": 1,
    "covered-with-expected-receipt-review": 2,
    "covered-now-review": 3,
}
TOTAL_FIELDS = (
    "required_qty", "assigned_now_qty", "assigned_expected_qty",
    "assigned_qty", "gap_qty",
)


def issue(code, message, *, order_id=None, source_type=None, source_id=None, field=None):
    return {
        "code": code, "message": message, "order_id": order_id,
        "source_type": source_type, "source_id": source_id, "field": field,
    }


def sorted_issues(issues):
    unique = {tuple(row[key] for key in ISSUE_SORT): row for row in issues}
    return [unique[key] for key in sorted(
        unique, key=lambda values: tuple(value or "" for value in values),
    )]


def table(title, columns, rows, highlights=()):
    rows = list(rows)
    total = len(rows)
    return {
        "title": f"{title} (first 8 of {total})" if total > 8 else title,
        "columns": columns,
        "rows": rows[:8],
        "total_rows": total,
        "highlight_rows": [index for index in highlights if 0 <= index < min(8, total)],
    }


def event(events, step_id, kind, caption, facts, *tables):
    events.append({
        "step_id": step_id, "kind": kind, "caption": caption,
        "facts": facts, "tables": list(tables),
    })


def issue_table(issues):
    return table(
        "Observed exceptions", ["code", "order_id", "source_id", "field", "message_prefix"],
        [[row["code"], row["order_id"], row["source_id"], row["field"],
          row["message"][:97] + "..." if len(row["message"]) > 100 else row["message"]]
         for row in issues],
        range(len(issues)),
    )


def rejected(events, issues):
    issues = sorted_issues(issues)
    event(
        events, "collect-exceptions", "exception",
        "Fatal business evidence supersedes partial calculations; no material plan is published.",
        {"fatal_errors": len(issues)}, issue_table(issues),
    )
    result = {"schema_version": 1, "status": "rejected", "outputs": {}, "exceptions": issues}
    event(
        events, "close-plan", "output",
        "The input was rejected. No assignments or production authorization were emitted.",
        {"status": result["status"], "output_keys": 0, "exceptions": len(issues)},
        table("Rejected review", ["status", "plan_emitted", "production_authorized"],
              [["rejected", False, False]], [0]),
    )
    return result, events


class BusinessReject(Exception):
    def __init__(self, problem, step_id, kind):
        super().__init__(problem["message"])
        self.problem = problem
        self.step_id = step_id
        self.kind = kind


def is_identifier(value):
    return isinstance(value, str) and IDENTIFIER.fullmatch(value) is not None


def is_date(value):
    if not isinstance(value, str) or not DATE_TEXT.fullmatch(value):
        return False
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return False
    return date(2000, 1, 1) <= parsed <= date(2100, 12, 31)


def strict_equal(left, right):
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(strict_equal(left[key], right[key]) for key in left)
    if isinstance(left, list):
        return len(left) == len(right) and all(strict_equal(a, b) for a, b in zip(left, right))
    return left == right


def field_problem(source_type, row, field):
    value = row[field]
    source_id = row.get(PRIMARY_ID[source_type])
    source_id = source_id if is_identifier(source_id) else None
    context = {
        "source_type": source_type, "source_id": source_id, "field": field,
        "order_id": source_id if source_type == "work_orders" else None,
    }

    def invalid(message, code="MALFORMED_FIELD"):
        return issue(code, message, **context)

    if field == "unit":
        if value != "EA":
            return invalid("Only the EA unit is supported; conversions are not inferred.", "UNSUPPORTED_UNIT")
    elif field == "line_type":
        if not isinstance(value, str) or value not in ("Item", "Phantom"):
            return invalid("Only Item and Phantom lines are supported.", "UNSUPPORTED_LINE_TYPE")
    elif field in ("quantity_per", "scrap_percent"):
        if not isinstance(value, str) or len(value) > 12 or not DECIMAL_TEXT.fullmatch(value):
            return invalid(
                "Expected a canonical decimal string with at most four fractional places.",
                "INVALID_DECIMAL",
            )
        number = Decimal(value)
        if field == "quantity_per" and not 0 < number <= MAX_QUANTITY:
            return invalid("quantity_per must be greater than zero and at most 1000000.", "INVALID_DECIMAL")
        if field == "scrap_percent" and not 0 <= number <= 25:
            return invalid("scrap_percent must be in 0..25.", "INVALID_DECIMAL")
    elif field.endswith("_id") or field == "site":
        if not (field == "requested_version_id" and value is None) and not is_identifier(value):
            return invalid("Expected a case-sensitive ASCII identifier of 1..40 permitted characters.")
    elif field in ("start_date", "valid_from", "valid_to", "expected_on", "expires_on"):
        if not (field == "expires_on" and value is None) and not is_date(value):
            return invalid("Expected a YYYY-MM-DD calendar date in 2000-01-01..2100-12-31.")
    elif field in ("approved", "active", "expiry_controlled", "confirmed"):
        if type(value) is not bool:
            return invalid("Expected a JSON boolean.")
    elif field == "status":
        if not isinstance(value, str) or value not in ("available", "hold", "blocked"):
            return invalid("Expected available, hold, or blocked stock status.")
    elif field in ("quantity", "priority", "min_order_qty", "max_order_qty", "reserved_external_qty"):
        minimum = 1 if field == "priority" or (
            field == "quantity" and source_type in ("work_orders", "inbound")
        ) else 0
        maximum = 100 if field == "priority" else MAX_QUANTITY
        if type(value) is not int or not minimum <= value <= maximum:
            return invalid(f"Expected an integer in {minimum}..{maximum}; booleans are not integers.")
    else:
        raise ValueError(f"No validator is defined for {source_type}.{field}")
    return None


def validate(payload):
    top_fields = set(TABLE_FIELDS) | {"as_of", "horizon_end"}
    if not isinstance(payload, dict) or payload.keys() != top_fields:
        return {}, [], [issue(
            "MALFORMED_INPUT", "Input must contain exactly: " + ", ".join(sorted(top_fields)) + ".",
        )]
    shape_errors = []
    for name in TABLE_FIELDS:
        rows = payload[name]
        minimum = 1 if name == "work_orders" else 0
        if not isinstance(rows, list) or not minimum <= len(rows) <= MAX_ROWS:
            shape_errors.append(issue(
                "MALFORMED_INPUT", f"Expected an array with {minimum}..{MAX_ROWS} rows.",
                source_type=name,
            ))
    if shape_errors:
        return {}, [], sorted_issues(shape_errors)

    errors, notices, data = [], [], {}
    for name in ("as_of", "horizon_end"):
        if not is_date(payload[name]):
            errors.append(issue(
                "MALFORMED_FIELD", "Expected a YYYY-MM-DD calendar date in 2000-01-01..2100-12-31.",
                field=name,
            ))
        data[name] = payload[name]
    if is_date(payload["as_of"]) and is_date(payload["horizon_end"]) and payload["as_of"] > payload["horizon_end"]:
        errors.append(issue("INVALID_RANGE", "horizon_end precedes as_of.", field="horizon_end"))

    for name, fields in TABLE_FIELDS.items():
        unique, duplicate_counts = {}, Counter()
        for index, row in enumerate(payload[name]):
            key = row.get(PRIMARY_ID[name]) if isinstance(row, dict) else None
            key = key if is_identifier(key) else None
            context = {
                "source_type": name, "source_id": key,
                "order_id": key if name == "work_orders" else None,
            }
            if not isinstance(row, dict) or row.keys() != set(fields):
                errors.append(issue(
                    "MALFORMED_FIELD", "Record must contain exactly: " + ", ".join(fields) + ".",
                    field=None if key else f"row[{index}]", **context,
                ))
                continue
            valid_fields = set()
            for field in fields:
                problem = field_problem(name, row, field)
                if problem:
                    errors.append(problem)
                else:
                    valid_fields.add(field)
            if name == "stock_lots" and {"quantity", "reserved_external_qty"} <= valid_fields:
                if row["reserved_external_qty"] > row["quantity"]:
                    errors.append(issue(
                        "RESERVATION_EXCEEDS_STOCK", "External reservations exceed physical stock.",
                        field="reserved_external_qty", **context,
                    ))
            if name == "bom_versions":
                for lower, upper in (("valid_from", "valid_to"), ("min_order_qty", "max_order_qty")):
                    if {lower, upper} <= valid_fields and row[lower] > row[upper]:
                        errors.append(issue(
                            "INVALID_RANGE", f"{lower} exceeds {upper}.", field=upper, **context,
                        ))
            if name == "bom_lines" and {"line_type", "scrap_percent"} <= valid_fields:
                if row["line_type"] == "Phantom" and Decimal(row["scrap_percent"]) != 0:
                    errors.append(issue(
                        "PHANTOM_SCRAP", "Phantom scrap must be zero; scrap applies only to Item leaves.",
                        field="scrap_percent", **context,
                    ))
            if key is not None:
                if key not in unique:
                    unique[key] = row
                elif strict_equal(unique[key], row):
                    duplicate_counts[key] += 1
                else:
                    errors.append(issue(
                        "CONFLICTING_ID", "Conflicting records share the same primary ID.",
                        field=PRIMARY_ID[name], **context,
                    ))
        data[name] = [unique[key] for key in sorted(unique)]
        for key, count in sorted(duplicate_counts.items()):
            notices.append(issue(
                "DUPLICATE_ROW", f"Collapsed {count} identical duplicate row(s).",
                source_type=name, source_id=key,
                order_id=key if name == "work_orders" else None,
            ))
    return data, sorted_issues(notices), sorted_issues(errors)


def decimal_text(value):
    rendered = format(value, "f")
    return rendered.rstrip("0").rstrip(".") if "." in rendered else rendered


class Review:
    def __init__(self, data, notices, events):
        self.data, self.notices, self.events = data, list(notices), events
        self.items = {row["item_id"]: row for row in data["items"]}
        self.versions = {row["version_id"]: row for row in data["bom_versions"]}
        self.versions_by_item = defaultdict(list)
        self.lines_by_version = defaultdict(list)
        for row in data["bom_versions"]:
            self.versions_by_item[row["item_id"]].append(row)
        for row in data["bom_lines"]:
            self.lines_by_version[row["version_id"]].append(row)
        self.orders = sorted(
            (row for row in data["work_orders"] if data["as_of"] <= row["start_date"] <= data["horizon_end"]),
            key=lambda row: (row["start_date"], row["priority"], row["order_id"]),
        )
        self.order_by_id = {row["order_id"]: row for row in self.orders}
        self.rank = {row["order_id"]: index for index, row in enumerate(self.orders)}
        self.unresolved = set()
        self.selected, self.paths, self.requirements = [], [], []
        self.visited_paths = 0
        self.visited_leaves = 0
        self.excluded_orders = []
        self.exclusions, self.allocations, self.sources = [], [], {}

    def fail(self, code, message, *, step_id, kind, **context):
        raise BusinessReject(issue(code, message, **context), step_id, kind)

    def cross_references(self):
        for name in ("work_orders", "bom_versions", "bom_lines", "stock_lots", "inbound"):
            field = "component_id" if name == "bom_lines" else "item_id"
            for row in self.data[name]:
                if row[field] not in self.items:
                    self.notices.append(issue(
                        "UNKNOWN_ITEM", f"Referenced item master is missing: {row[field]}.",
                        source_type=name, source_id=row[PRIMARY_ID[name]], field=field,
                        order_id=row["order_id"] if name == "work_orders" else None,
                    ))
        for row in self.data["bom_lines"]:
            if row["version_id"] not in self.versions:
                self.notices.append(issue(
                    "ORPHAN_BOM_LINE", f"Referenced BOM version is missing: {row['version_id']}.",
                    source_type="bom_lines", source_id=row["line_id"], field="version_id",
                ))
        for row in self.data["work_orders"]:
            if row["order_id"] not in self.rank:
                reason = "before-as-of" if row["start_date"] < self.data["as_of"] else "after-horizon"
                self.excluded_orders.append({"order_id": row["order_id"], "reason": reason})
                self.notices.append(issue(
                    "ORDER_OUT_OF_SCOPE", "Order start_date is outside the inclusive review horizon.",
                    source_type="work_orders", source_id=row["order_id"],
                    order_id=row["order_id"], field="start_date",
                ))

    def select_version(self, order, item_id, quantity, requested, step_id):
        def applicable(version):
            return (
                version["item_id"] == item_id and version["site"] == order["site"]
                and version["approved"]
                and version["valid_from"] <= order["start_date"] <= version["valid_to"]
                and version["min_order_qty"] <= quantity <= version["max_order_qty"]
            )

        if requested is not None:
            candidate = self.versions.get(requested)
            if candidate is not None and applicable(candidate):
                return candidate
            self.notices.append(issue(
                "INVALID_REQUESTED_BOM", f"Requested BOM is missing, unapproved, or outside the demand scope: {requested}.",
                order_id=order["order_id"], source_type="work_orders",
                source_id=order["order_id"], field="requested_version_id",
            ))
            return None
        matches = [v for v in self.versions_by_item[item_id] if v["active"] and applicable(v)]
        if len(matches) > 1:
            self.fail(
                "AMBIGUOUS_BOM",
                "Multiple approved active BOM versions match: " + ", ".join(v["version_id"] for v in matches) + ".",
                step_id=step_id, kind="join", order_id=order["order_id"],
                source_type="items", source_id=item_id, field="version_id",
            )
        if matches:
            return matches[0]
        self.notices.append(issue(
            "NO_VALID_BOM", f"No approved active BOM matches item {item_id} and exact parent quantity {decimal_text(quantity)}.",
            order_id=order["order_id"], source_type="items", source_id=item_id, field="version_id",
        ))
        return None

    def select_roots(self):
        self.cross_references()
        roots, rows = {}, []
        for order in self.orders:
            if order["item_id"] not in self.items:
                roots[order["order_id"]] = None
            else:
                roots[order["order_id"]] = self.select_version(
                    order, order["item_id"], Decimal(order["quantity"]),
                    order["requested_version_id"], "select-bom",
                )
            root = roots[order["order_id"]]
            rows.append([
                order["order_id"], order["item_id"], order["quantity"],
                root["version_id"] if root else None,
                "selected" if root else "unresolved",
            ])
        event(
            self.events, "select-bom", "join",
            "Joined ordered in-scope demand to approved applicable root BOM versions; explicit requests do not fall back.",
            {"in_scope_orders": len(self.orders), "selected_roots": sum(v is not None for v in roots.values()),
             "excluded_orders": len(self.excluded_orders)},
            table("Root version selections", ["order_id", "item_id", "quantity", "version_id", "decision"], rows,
                  [i for i, row in enumerate(rows) if row[-1] == "unresolved"]),
        )
        return roots

    def walk(self, order, version, quantity, ancestors, parent_path, versions, paths):
        lines = self.lines_by_version[version["version_id"]]
        if not lines:
            self.notices.append(issue(
                "EMPTY_BOM", "Selected BOM has no component lines; demand is unresolved.",
                order_id=order["order_id"], source_type="bom_versions",
                source_id=version["version_id"], field="version_id",
            ))
            return False
        complete = True
        for line in lines:
            self.visited_paths += 1
            path = parent_path + [line["line_id"]]
            context = {
                "step_id": "expand-phantoms", "kind": "join",
                "order_id": order["order_id"], "source_type": "bom_lines",
                "source_id": line["line_id"], "field": "component_id",
            }
            if len(path) > MAX_DEPTH:
                self.fail("BOM_DEPTH_LIMIT", "BOM expansion exceeds eight line levels.", **context)
            component = line["component_id"]
            if component in ancestors:
                self.fail("BOM_CYCLE", f"BOM expansion repeats ancestor item {component}.", **context)
            if self.visited_paths > MAX_PATHS:
                self.fail("BOM_PATH_LIMIT", "BOM expansion exceeds 5000 expanded line-path occurrences.", **context)
            if line["line_type"] == "Item":
                self.visited_leaves += 1
                if component not in self.items:
                    complete = False
                    continue
                exact = quantity * Decimal(line["quantity_per"]) * (
                    Decimal(1) + Decimal(line["scrap_percent"]) / Decimal(100)
                )
                paths.append({
                    "order_id": order["order_id"], "path": path,
                    "component_id": component, "exact_qty": decimal_text(exact),
                })
            else:
                if component not in self.items:
                    complete = False
                    continue
                parent_quantity = quantity * Decimal(line["quantity_per"])
                child = self.select_version(order, component, parent_quantity, None, "expand-phantoms")
                if child is None:
                    complete = False
                    continue
                versions.append({
                    "order_id": order["order_id"], "parent_path": path,
                    "item_id": component, "version_id": child["version_id"], "selection": "active-default",
                })
                # Visit other known branches even after unresolved evidence on this branch.
                child_complete = self.walk(
                    order, child, parent_quantity, ancestors + (component,), path, versions, paths,
                )
                complete = child_complete and complete
        return complete

    def expand(self, roots):
        for order in self.orders:
            root = roots[order["order_id"]]
            complete, versions, paths = False, [], []
            if root is not None:
                versions.append({
                    "order_id": order["order_id"], "parent_path": [], "item_id": order["item_id"],
                    "version_id": root["version_id"],
                    "selection": "explicit-approved" if order["requested_version_id"] else "active-default",
                })
                complete = self.walk(
                    order, root, Decimal(order["quantity"]), (order["item_id"],), [], versions, paths,
                )
            if complete:
                self.selected.extend(versions)
                self.paths.extend(paths)
            else:
                self.unresolved.add(order["order_id"])
                self.notices.append(issue(
                    "ORDER_UNRESOLVED", "Material requirements are unresolved; no component assignment was made.",
                    order_id=order["order_id"], source_type="work_orders", source_id=order["order_id"],
                ))
        self.selected.sort(key=lambda row: (self.rank[row["order_id"]], row["parent_path"]))
        self.paths.sort(key=lambda row: (self.rank[row["order_id"]], row["path"]))
        event(
            self.events, "expand-phantoms", "join",
            "Traversed real Item/Phantom paths without intermediate rounding; incomplete orders have no partial ledger.",
            {"line_paths_visited": self.visited_paths, "leaf_paths_visited": self.visited_leaves, "published_paths": len(self.paths),
             "selected_versions": len(self.selected), "unresolved_orders": len(self.unresolved)},
            table("Expanded Item paths", ["order_id", "component_id", "leaf_line_id", "levels", "exact_qty"],
                  [[p["order_id"], p["component_id"], p["path"][-1], len(p["path"]), p["exact_qty"]]
                   for p in self.paths], [0]),
            table("Selected assembly versions", ["order_id", "item_id", "version_id", "selection"],
                  [[v["order_id"], v["item_id"], v["version_id"], v["selection"]] for v in self.selected]),
        )

    def calculate_demand(self):
        sums = defaultdict(Decimal)
        for path in self.paths:
            sums[path["order_id"], path["component_id"]] += Decimal(path["exact_qty"])
        for (order_id, component), exact in sorted(sums.items(), key=lambda pair: (self.rank[pair[0][0]], pair[0][1])):
            required = int(exact.to_integral_value(rounding=ROUND_CEILING))
            if not 1 <= required <= MAX_QUANTITY:
                self.fail(
                    "REQUIREMENT_LIMIT", "Required quantity exceeds the per-order/component limit of 1000000 EA.",
                    step_id="calculate-demand", kind="decision", order_id=order_id,
                    source_type="items", source_id=component, field="required_qty",
                )
            self.requirements.append({
                "order_id": order_id, "component_id": component,
                "exact_qty": decimal_text(exact), "required_qty": required,
            })
        event(
            self.events, "calculate-demand", "decision",
            "Summed exact leaf quantities by order/component and applied one whole-EA ceiling to each sum.",
            {"component_requirements": len(self.requirements), "rounding": "sum-then-ceil"},
            table("Once-rounded demand", ["order_id", "component_id", "exact_qty", "required_qty"],
                  [[r["order_id"], r["component_id"], r["exact_qty"], r["required_qty"]]
                   for r in self.requirements], [0]),
        )

    def exclusion_reason(self, kind, row, order):
        if row["site"] != order["site"]:
            return "wrong-site"
        if kind == "stock_lots":
            if row["status"] != "available":
                return "blocked-status"
            expiry = row["expires_on"]
            if expiry is None and self.items[row["item_id"]]["expiry_controlled"]:
                return "unknown-expiry"
            if expiry is not None and expiry < order["start_date"]:
                return "expired-before-need"
            if row["quantity"] == row["reserved_external_qty"]:
                return "no-unreserved-quantity"
        else:
            if not row["confirmed"]:
                return "unconfirmed"
            if row["expected_on"] <= self.data["as_of"]:
                return "not-future"
            if row["expected_on"] > order["start_date"]:
                return "late"
        return None

    def join_supply(self):
        join_rows = []
        for kind in SUPPLY_ORDER:
            for row in self.data[kind]:
                key = (kind, row[PRIMARY_ID[kind]])
                net = row["quantity"] - row["reserved_external_qty"] if kind == "stock_lots" else row["quantity"]
                self.sources[key] = {"row": row, "net_qty": net, "remaining_qty": net, "assigned_qty": 0}
                if row["item_id"] not in self.items:
                    self.exclusions.append({
                        "order_id": None, "component_id": row["item_id"],
                        "source_type": kind, "source_id": key[1], "reason": "unknown-item",
                    })
                    join_rows.append([None, row["item_id"], kind, key[1], net, "unknown-item"])
        eligible = {}
        for requirement in self.requirements:
            order_id, component = requirement["order_id"], requirement["component_id"]
            order = self.order_by_id[order_id]
            pools = {"stock_lots": [], "inbound": []}
            for key, source in self.sources.items():
                kind, source_id = key
                row = source["row"]
                if row["item_id"] != component:
                    continue
                reason = self.exclusion_reason(kind, row, order)
                join_rows.append([order_id, component, kind, source_id, source["net_qty"], reason or "eligible"])
                if reason:
                    self.exclusions.append({
                        "order_id": order_id, "component_id": component,
                        "source_type": kind, "source_id": source_id, "reason": reason,
                    })
                else:
                    pools[kind].append(key)
            pools["stock_lots"].sort(key=lambda key: (
                self.sources[key]["row"]["expires_on"] is None,
                self.sources[key]["row"]["expires_on"] or "", key[1],
            ))
            pools["inbound"].sort(key=lambda key: (self.sources[key]["row"]["expected_on"], key[1]))
            eligible[order_id, component] = pools
        self.exclusions.sort(key=lambda row: (
            -1 if row["order_id"] is None else self.rank[row["order_id"]],
            row["component_id"], SUPPLY_ORDER[row["source_type"]], row["source_id"], row["reason"],
        ))
        event(
            self.events, "join-supply", "join",
            "Cross-referenced site/status/expiry/reservations and confirmed future dates; nominal source balances are not availability.",
            {"sources": len(self.sources), "source_matches": len(join_rows), "exclusions": len(self.exclusions)},
            table("Source eligibility before shadow consumption",
                  ["order_id", "component_id", "source_type", "source_id", "net_qty", "decision"],
                  join_rows, [i for i, row in enumerate(join_rows) if row[-1] != "eligible"]),
        )
        return eligible

    def allocate(self, eligible):
        for requirement in self.requirements:
            order_id, component = requirement["order_id"], requirement["component_id"]
            pools = eligible[order_id, component]
            current_pool = sum(self.sources[key]["remaining_qty"] for key in pools["stock_lots"])
            future_pool = sum(self.sources[key]["remaining_qty"] for key in pools["inbound"])
            unfilled = requirement["required_qty"]
            assigned = {"stock_lots": 0, "inbound": 0}
            for kind in SUPPLY_ORDER:
                for key in pools[kind]:
                    quantity = min(unfilled, self.sources[key]["remaining_qty"])
                    if quantity == 0:
                        continue
                    self.sources[key]["remaining_qty"] -= quantity
                    self.sources[key]["assigned_qty"] += quantity
                    assigned[kind] += quantity
                    unfilled -= quantity
                    self.allocations.append({
                        "order_id": order_id, "component_id": component,
                        "source_type": kind, "source_id": key[1], "quantity": quantity,
                    })
            requirement.update({
                "available_now_qty": current_pool, "expected_before_need_qty": future_pool,
                "assigned_now_qty": assigned["stock_lots"], "assigned_expected_qty": assigned["inbound"],
                "assigned_qty": assigned["stock_lots"] + assigned["inbound"], "gap_qty": unfilled,
            })
        event(
            self.events, "shadow-allocate", "decision",
            "Consumed only report-local source balances in order/date/priority sequence, stock first; partial kits retain their assignments.",
            {"allocation_rows": len(self.allocations),
             "short_components": sum(r["gap_qty"] > 0 for r in self.requirements)},
            table("Conserved component assignments",
                  ["order_id", "component_id", "required_qty", "assigned_now_qty", "assigned_future_qty", "gap_qty"],
                  [[r["order_id"], r["component_id"], r["required_qty"], r["assigned_now_qty"],
                    r["assigned_expected_qty"], r["gap_qty"]] for r in self.requirements],
                  [i for i, r in enumerate(self.requirements) if r["gap_qty"]]),
            table("Actual shadow source assignments", ["order_id", "component_id", "source_type", "source_id", "quantity"],
                  [[a["order_id"], a["component_id"], a["source_type"], a["source_id"], a["quantity"]]
                   for a in self.allocations]),
        )

    def collect_exceptions(self):
        for row in self.requirements:
            if row["gap_qty"]:
                self.notices.append(issue(
                    "MATERIAL_SHORTAGE", "Required material is not fully assigned.",
                    order_id=row["order_id"], source_type="items", source_id=row["component_id"],
                ))
        if self.exclusions:
            self.notices.append(issue(
                "SUPPLY_EXCLUSIONS", f"{len(self.exclusions)} order/source eligibility exclusion(s) require review.",
            ))
        self.notices = sorted_issues(self.notices)
        event(
            self.events, "collect-exceptions", "exception",
            "Collected actual shortage and evidence exceptions; excluded nominal stock and receipts did not reduce demand gaps.",
            {"exceptions": len(self.notices), "supply_exclusions": len(self.exclusions),
             "unresolved_orders": len(self.unresolved)},
            issue_table(self.notices),
            table("Detailed supply exclusions", ["order_id", "component_id", "source_type", "source_id", "reason"],
                  [[r["order_id"], r["component_id"], r["source_type"], r["source_id"], r["reason"]]
                   for r in self.exclusions], range(len(self.exclusions))),
        )

    def reconcile(self):
        by_order = defaultdict(list)
        totals = {}
        for row in self.requirements:
            by_order[row["order_id"]].append(row)
            if (row["required_qty"] != row["assigned_qty"] + row["gap_qty"]
                    or row["assigned_qty"] != row["assigned_now_qty"] + row["assigned_expected_qty"]):
                raise ArithmeticError("Component assignment failed quantity conservation")
            key = (self.order_by_id[row["order_id"]]["site"], row["component_id"])
            if key not in totals:
                totals[key] = dict(site=key[0], component_id=key[1], **{field: 0 for field in TOTAL_FIELDS})
            for field in TOTAL_FIELDS:
                totals[key][field] += row[field]
        balances = []
        for (kind, source_id), source in self.sources.items():
            if (source["net_qty"] != source["assigned_qty"] + source["remaining_qty"]
                    or source["remaining_qty"] < 0):
                raise ArithmeticError("Source assignment failed quantity conservation")
            balances.append({
                "source_type": kind, "source_id": source_id,
                "item_id": source["row"]["item_id"], "site": source["row"]["site"],
                "net_qty": source["net_qty"], "assigned_qty": source["assigned_qty"],
                "remaining_qty": source["remaining_qty"],
            })
        reviews = []
        for order in self.orders:
            requirements = by_order[order["order_id"]]
            short = [r["component_id"] for r in requirements if r["gap_qty"]]
            if order["order_id"] in self.unresolved:
                state, owners = "unresolved-review", ["Engineering reviewer", "Material planner"]
            elif short:
                state, owners = "shortage-review", ["Material planner", "Stores reviewer", "Production planner"]
            elif any(r["assigned_expected_qty"] for r in requirements):
                state, owners = "covered-with-expected-receipt-review", ["Material planner", "Production planner"]
            else:
                state, owners = "covered-now-review", ["Material planner", "Production planner"]
            reviews.append({
                "order_id": order["order_id"], "item_id": order["item_id"], "site": order["site"],
                "need_by": order["start_date"], "quantity": order["quantity"], "priority": order["priority"],
                "state": state, "short_components": short, "review_owners": owners,
                "approval_required": True, "production_authorized": False,
            })
        counts = Counter(row["state"] for row in reviews)
        summary = {
            "in_scope_orders": len(self.orders), "resolved_orders": len(self.orders) - len(self.unresolved),
            "unresolved_orders": len(self.unresolved), "excluded_orders": len(self.excluded_orders),
            "shortage_orders": counts["shortage-review"],
            "covered_now_orders": counts["covered-now-review"],
            "covered_with_expected_orders": counts["covered-with-expected-receipt-review"],
        }
        queue = [
            row["order_id"] for row in sorted(
                reviews, key=lambda row: (REVIEW_ORDER[row["state"]], self.rank[row["order_id"]]),
            ) if row["state"] != "covered-now-review"
        ]
        component_totals = [totals[key] for key in sorted(totals)]
        event(
            self.events, "reconcile-plan", "decision",
            "Reconciled known component/site demand and every nominal source balance; unresolved demand remains unknown, not zero.",
            {"resolved_orders": summary["resolved_orders"], "unresolved_orders": summary["unresolved_orders"],
             "shortage_orders": summary["shortage_orders"], "source_balances": len(balances)},
            table("Component/site conservation", ["site", "component_id", "required_qty", "assigned_now_qty", "assigned_future_qty", "gap_qty"],
                  [[r["site"], r["component_id"], r["required_qty"], r["assigned_now_qty"],
                    r["assigned_expected_qty"], r["gap_qty"]] for r in component_totals],
                  [i for i, r in enumerate(component_totals) if r["gap_qty"]]),
            table("Nominal source conservation", ["source_type", "source_id", "net_qty", "assigned_qty", "remaining_qty"],
                  [[r["source_type"], r["source_id"], r["net_qty"], r["assigned_qty"], r["remaining_qty"]]
                   for r in balances]),
        )
        return {
            "as_of": self.data["as_of"], "horizon_end": self.data["horizon_end"],
            "order_sequence": [order["order_id"] for order in self.orders],
            "selected_versions": self.selected, "exploded_paths": self.paths,
            "component_requirements": self.requirements, "shadow_allocations": self.allocations,
            "source_balances": balances, "supply_exclusions": self.exclusions,
            "excluded_orders": self.excluded_orders, "order_reviews": reviews,
            "review_queue": queue, "component_totals": component_totals, "summary": summary,
            "closure": {
                "review_only": True, "approval_required": True, "production_authorized": False,
                "inventory_mutated": False, "reservations_created": False,
                "substitutions_made": False, "orders_released": False,
            },
        }

    def run(self):
        roots = self.select_roots()
        self.expand(roots)
        self.calculate_demand()
        eligible = self.join_supply()
        self.allocate(eligible)
        self.collect_exceptions()
        outputs = self.reconcile()
        result = {
            "schema_version": 1, "status": "completed_with_exceptions" if self.notices else "completed",
            "outputs": outputs, "exceptions": self.notices,
        }
        encoded = (json.dumps(result, allow_nan=False, ensure_ascii=True, indent=2, sort_keys=True) + "\n").encode("utf-8")
        if len(encoded) > MAX_RESULT_BYTES:
            self.fail(
                "OUTPUT_LIMIT", "The complete review exceeds the shared 8 MiB result limit; no truncated plan is emitted.",
                step_id="close-plan", kind="output",
            )
        event(
            self.events, "close-plan", "output",
            "Closed the synthetic office review with explicit human approval boundaries, not a reservation, release, or production instruction.",
            {"status": result["status"], "orders": len(outputs["order_reviews"]),
             "queued_reviews": len(outputs["review_queue"]), "production_authorized": False},
            table("Review-only order states", ["order_id", "need_by", "state", "approval_required", "production_authorized"],
                  [[r["order_id"], r["need_by"], r["state"], r["approval_required"], r["production_authorized"]]
                   for r in outputs["order_reviews"]],
                  [i for i, r in enumerate(outputs["order_reviews"]) if r["state"] != "covered-now-review"]),
        )
        return result, self.events


def solve(payload):
    events = []
    rows = [
        [name, len(payload[name]) if isinstance(payload, dict) and isinstance(payload.get(name), list) else None]
        for name in TABLE_FIELDS
    ]
    event(
        events, "intake", "input",
        "Read one synthetic JSON bundle containing six independent logical exports; no live or physical multi-file ingestion.",
        {"logical_exports": len(TABLE_FIELDS), "business_connections": 0},
        table("Received logical export inventory", ["export", "rows_received"], rows),
    )
    data, notices, errors = validate(payload)
    if errors:
        event(
            events, "validate-structure", "validation",
            "Source structure or business values failed validation before material calculation.",
            {"fatal_errors": len(errors)}, issue_table(errors),
        )
        return rejected(events, errors)
    event(
        events, "validate-structure", "validation",
        "Validated strict fields, dates, quantities, supported EA/line types, and source identity; identical duplicates count once.",
        {"fatal_errors": 0, "duplicate_groups": len(notices)},
        table("Validated unique exports", ["export", "received_rows", "unique_rows"],
              [[name, len(payload[name]), len(data[name])] for name in TABLE_FIELDS]),
    )
    try:
        with localcontext() as context:
            context.prec = 128
            context.traps[Inexact] = True
            return Review(data, notices, events).run()
    except BusinessReject as error:
        if error.step_id != "close-plan":
            event(
                events, error.step_id, error.kind,
                f"Execution stopped at {error.step_id}: {error.problem['code']}.",
                {"fatal_errors": 1, "order_id": error.problem["order_id"]},
                issue_table([error.problem]),
            )
        return rejected(events, [error.problem])


if __name__ == "__main__":
    run_cli(solve, scenario_id="manufacturing-03")
