"""Evaluator-private assertions authored before implementation/execution."""
from __future__ import annotations

import copy
import importlib.util
import json
import random
import subprocess
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parents[1]))
from _shared.common import load_json
from _shared.contract import baseline_import_audit, load_scenario, validate_result
from _shared.pipeline import check_case_evidence, golden_lock


def chain(levels=1):
    """Independent small synthetic graph, not a stored case or baseline builder."""
    return {
        "as_of": "2026-05-01",
        "horizon_end": "2026-05-03",
        "work_orders": [{
            "order_id": "T01", "item_id": "I0", "site": "TEST",
            "start_date": "2026-05-02", "quantity": 1, "priority": 1,
            "requested_version_id": None,
        }],
        "bom_versions": [{
            "version_id": f"V{i}", "item_id": f"I{i}", "site": "TEST",
            "valid_from": "2026-05-01", "valid_to": "2026-05-31",
            "min_order_qty": 0, "max_order_qty": 1000000,
            "approved": True, "active": True,
        } for i in range(levels)],
        "bom_lines": [{
            "line_id": f"L{i}", "version_id": f"V{i}",
            "component_id": f"I{i + 1}" if i < levels - 1 else "LEAF",
            "line_type": "Phantom" if i < levels - 1 else "Item",
            "quantity_per": "1", "scrap_percent": "0",
        } for i in range(levels)],
        "items": [
            {"item_id": f"I{i}", "unit": "EA", "expiry_controlled": False}
            for i in range(levels)
        ] + [{"item_id": "LEAF", "unit": "EA", "expiry_controlled": False}],
        "stock_lots": [{
            "stock_id": "S1", "item_id": "LEAF", "site": "TEST",
            "quantity": 1, "reserved_external_qty": 0,
            "status": "available", "expires_on": None,
        }],
        "inbound": [],
    }


def many_paths(line_count):
    payload = chain()
    payload["work_orders"] = [
        dict(payload["work_orders"][0], order_id=f"T{i:03d}")
        for i in range(200)
    ]
    payload["bom_lines"] = [
        dict(payload["bom_lines"][0], line_id=f"L{i:03d}", quantity_per="0.0001")
        for i in range(line_count)
    ]
    payload["stock_lots"][0]["quantity"] = 200
    return payload


class BaselineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scenario = load_scenario(ROOT)
        golden_lock(cls.scenario)
        spec = importlib.util.spec_from_file_location("bom_kitting_baseline", ROOT / "baseline.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        cls.solve = staticmethod(module.solve)

    def fixture(self, case_id):
        return load_json(self.scenario.file(self.scenario.case(case_id)["input"]))

    def reject(self, payload, code):
        result, events = self.solve(payload)
        self.assertEqual("rejected", result["status"])
        self.assertEqual({}, result["outputs"])
        self.assertIn(code, [issue["code"] for issue in result["exceptions"]])
        self.assertEqual("input", events[0]["kind"])
        self.assertEqual("output", events[-1]["kind"])
        validate_result(result)
        return result, events

    def test_all_complete_independent_goldens(self):
        for case in self.scenario.cases:
            with self.subTest(case=case["id"]):
                result, _ = self.solve(load_json(self.scenario.file(case["input"])))
                self.assertEqual(load_json(self.scenario.file(case["expected"])), result)

    def test_persistent_pipeline_evidence_and_native_blockers(self):
        for case in self.scenario.cases:
            with self.subTest(case=case["id"]):
                report = check_case_evidence(self.scenario, case)
                self.assertEqual("baseline_pass", report["state"])
                self.assertEqual("native_creation_blocked", report["native"]["creation"])
                self.assertEqual("not_run", report["native"]["independent_invocation"])
                self.assertFalse(report["native"]["observed"])

    def test_static_import_boundary(self):
        audit = baseline_import_audit(ROOT / "baseline.py")
        self.assertEqual("static_import_check_pass", audit["status"])
        self.assertTrue(set(audit["imports"]) <= set(sys.stdlib_module_names) | {"scenario_support"})

    def test_shuffled_exports_preserve_results_and_trace(self):
        for case_id in ("demo", "holdout-a", "holdout-b", "holdout-c", "holdout-unknown"):
            payload = self.fixture(case_id)
            original = self.solve(payload)
            for seed in (7, 29, 101):
                shuffled = copy.deepcopy(payload)
                rng = random.Random(seed)
                for value in shuffled.values():
                    if isinstance(value, list):
                        rng.shuffle(value)
                with self.subTest(case=case_id, seed=seed):
                    self.assertEqual(original, self.solve(shuffled))

    def test_input_is_not_mutated_and_repeated_calls_are_isolated(self):
        payload = self.fixture("demo")
        untouched = copy.deepcopy(payload)
        first = self.solve(payload)
        self.assertEqual(untouched, payload)
        self.assertEqual(first, self.solve(payload))
        self.solve(self.fixture("holdout-unknown"))
        self.assertEqual(first, self.solve(payload))

    def test_ten_actual_stages_and_trace_table_bounds(self):
        result, events = self.solve(self.fixture("demo"))
        steps = self.scenario.workflow["steps"]
        self.assertEqual([s["id"] for s in steps], [e["step_id"] for e in events])
        self.assertEqual(10, len(events))
        self.assertEqual(
            {"input", "validation", "join", "decision", "exception", "output"},
            {event["kind"] for event in events},
        )
        for event in events:
            self.assertLessEqual(len(event["caption"]), 260)
            self.assertLessEqual(len(event["facts"]), 6)
            self.assertGreaterEqual(len(event["tables"]), 1)
            self.assertLessEqual(len(event["tables"]), 2)
            for table in event["tables"]:
                self.assertLessEqual(len(table["columns"]), 6)
                self.assertLessEqual(len(table["rows"]), 8)
                self.assertGreaterEqual(table["total_rows"], len(table["rows"]))
                for row in table["rows"]:
                    self.assertEqual(len(table["columns"]), len(row))
                    self.assertTrue(all(value is None or type(value) in (str, int, bool) for value in row))
                self.assertTrue(all(0 <= index < len(table["rows"]) for index in table["highlight_rows"]))
        close = events[-1]
        self.assertEqual(result["status"], close["facts"]["status"])

    def test_trace_changes_with_executed_supply_not_a_storyboard(self):
        payload = self.fixture("demo")
        first, first_events = self.solve(payload)
        for stock in payload["stock_lots"]:
            if stock["stock_id"] == "S-BOLT":
                stock["quantity"] = 12
        changed, changed_events = self.solve(payload)
        self.assertEqual(0, changed["outputs"]["summary"]["shortage_orders"])
        self.assertEqual(1, first["outputs"]["summary"]["shortage_orders"])
        assignment = next(e for e in changed_events if e["step_id"] == "shadow-allocate")
        old_assignment = next(e for e in first_events if e["step_id"] == "shadow-allocate")
        self.assertNotEqual(old_assignment["tables"], assignment["tables"])
        self.assertEqual("covered-with-expected-receipt-review",
                         changed["outputs"]["order_reviews"][1]["state"])

    def test_all_case_quantities_reconcile_by_source_and_component(self):
        for case in self.scenario.cases:
            result, _ = self.solve(load_json(self.scenario.file(case["input"])))
            if result["status"] == "rejected":
                continue
            out = result["outputs"]
            with self.subTest(case=case["id"]):
                for row in out["component_requirements"]:
                    self.assertEqual(row["required_qty"], row["assigned_qty"] + row["gap_qty"])
                    self.assertEqual(row["assigned_qty"], row["assigned_now_qty"] + row["assigned_expected_qty"])
                    self.assertLessEqual(row["assigned_now_qty"], row["available_now_qty"])
                    self.assertLessEqual(row["assigned_expected_qty"], row["expected_before_need_qty"])
                for source in out["source_balances"]:
                    used = sum(a["quantity"] for a in out["shadow_allocations"]
                               if (a["source_type"], a["source_id"]) ==
                               (source["source_type"], source["source_id"]))
                    self.assertEqual(used, source["assigned_qty"])
                    self.assertEqual(source["net_qty"], used + source["remaining_qty"])
                    self.assertGreaterEqual(source["remaining_qty"], 0)
                self.assertTrue(out["closure"]["review_only"])
                self.assertFalse(out["closure"]["production_authorized"])
                self.assertFalse(out["closure"]["reservations_created"])

    def test_once_per_component_ceiling_and_equal_order_tie(self):
        result, _ = self.solve(self.fixture("holdout-b"))
        out = result["outputs"]
        self.assertEqual(["B01", "B02"], out["order_sequence"])
        self.assertEqual(["1.5"] * 4, [p["exact_qty"] for p in out["exploded_paths"]])
        self.assertEqual([3, 3], [r["required_qty"] for r in out["component_requirements"]])
        self.assertEqual([3, 2], [r["assigned_qty"] for r in out["component_requirements"]])
        self.assertEqual([0, 1], [r["gap_qty"] for r in out["component_requirements"]])

    def test_leaf_scrap_explicit_inactive_and_source_id_tie(self):
        result, _ = self.solve(self.fixture("holdout-c"))
        out = result["outputs"]
        self.assertEqual("CASE-ALT", out["selected_versions"][0]["version_id"])
        self.assertEqual("explicit-approved", out["selected_versions"][0]["selection"])
        self.assertEqual("1.75", out["component_requirements"][0]["exact_qty"])
        self.assertEqual(2, out["component_requirements"][0]["required_qty"])
        self.assertEqual(["S-A", "S-B"], [a["source_id"] for a in out["shadow_allocations"]])
        self.assertEqual(2, out["source_balances"][-1]["remaining_qty"])

    def test_effective_change_and_expiry_receipt_inclusive_boundary(self):
        result, _ = self.solve(self.fixture("holdout-a"))
        out = result["outputs"]
        self.assertEqual("WIN-NEW", out["selected_versions"][0]["version_id"])
        self.assertEqual([1, 3], [a["quantity"] for a in out["shadow_allocations"]])
        self.assertEqual({"expired-before-need", "wrong-site"},
                         {x["reason"] for x in out["supply_exclusions"]})
        self.assertEqual("covered-with-expected-receipt-review", out["order_reviews"][0]["state"])

    def test_invalid_explicit_request_never_falls_back(self):
        for change in ("unapproved", "wrong-site", "expired", "quantity", "missing"):
            payload = self.fixture("holdout-c")
            requested = next(v for v in payload["bom_versions"] if v["version_id"] == "CASE-ALT")
            if change == "unapproved":
                requested["approved"] = False
            elif change == "wrong-site":
                requested["site"] = "OTHER"
            elif change == "expired":
                requested["valid_from"] = requested["valid_to"] = "2026-11-03"
            elif change == "quantity":
                requested["min_order_qty"] = requested["max_order_qty"] = 3
            else:
                payload["work_orders"][1]["requested_version_id"] = "ABSENT"
            with self.subTest(change=change):
                result, _ = self.solve(payload)
                self.assertNotEqual("rejected", result["status"])
                self.assertEqual("unresolved-review", result["outputs"]["order_reviews"][0]["state"])
                self.assertEqual([], result["outputs"]["component_requirements"])
                self.assertIn("INVALID_REQUESTED_BOM", [e["code"] for e in result["exceptions"]])

    def test_explicit_selection_disambiguates_only_requested_root(self):
        payload = self.fixture("negative-contradictory")
        payload["work_orders"][0]["requested_version_id"] = "C-V1"
        result, _ = self.solve(payload)
        self.assertNotEqual("rejected", result["status"])
        self.assertEqual("C-V1", result["outputs"]["selected_versions"][0]["version_id"])
        self.assertEqual(1, result["outputs"]["component_requirements"][0]["required_qty"])

    def test_default_requires_approved_and_active(self):
        for field in ("active", "approved"):
            payload = chain()
            payload["bom_versions"][0][field] = False
            result, _ = self.solve(payload)
            self.assertEqual("unresolved-review", result["outputs"]["order_reviews"][0]["state"])
            self.assertIn("NO_VALID_BOM", [e["code"] for e in result["exceptions"]])
            self.assertEqual([], result["outputs"]["selected_versions"])

    def test_phantom_version_uses_exact_unrounded_parent_quantity(self):
        payload = chain(2)
        payload["work_orders"][0]["quantity"] = 3
        payload["bom_lines"][0]["quantity_per"] = "0.5"
        payload["bom_versions"][1]["min_order_qty"] = 2
        payload["bom_versions"][1]["max_order_qty"] = 2
        result, _ = self.solve(payload)
        self.assertEqual("unresolved-review", result["outputs"]["order_reviews"][0]["state"])
        payload["bom_versions"][1]["min_order_qty"] = 1
        result, _ = self.solve(payload)
        row = result["outputs"]["component_requirements"][0]
        self.assertEqual("1.5", row["exact_qty"])
        self.assertEqual(2, row["required_qty"])

    def test_eight_levels_allowed_and_ninth_rejected(self):
        result, _ = self.solve(chain(8))
        self.assertEqual("completed", result["status"])
        self.assertEqual(8, len(result["outputs"]["exploded_paths"][0]["path"]))
        self.reject(chain(9), "BOM_DEPTH_LIMIT")

    def test_5000_leaf_paths_allowed_and_5001_stops_expansion(self):
        result, events = self.solve(many_paths(25))
        self.assertEqual("completed", result["status"])
        self.assertEqual(5000, len(result["outputs"]["exploded_paths"]))
        expansion = next(e for e in events if e["step_id"] == "expand-phantoms")
        self.assertEqual(5000, expansion["tables"][0]["total_rows"])
        self.assertEqual(8, len(expansion["tables"][0]["rows"]))
        self.reject(many_paths(26), "BOM_PATH_LIMIT")

    def test_phantom_paths_count_toward_the_same_5000_limit(self):
        payload = chain(2)
        payload["work_orders"] = [
            dict(payload["work_orders"][0], order_id=f"T{i:03d}")
            for i in range(200)
        ]
        leaf = payload["bom_lines"][-1]
        payload["bom_lines"] = payload["bom_lines"][:1] + [
            dict(leaf, line_id=f"LEAF-{i:02d}", quantity_per="0.0001")
            for i in range(24)
        ]
        payload["stock_lots"][0]["quantity"] = 200
        result, _ = self.solve(payload)
        self.assertEqual("completed", result["status"])
        self.assertEqual(4800, len(result["outputs"]["exploded_paths"]))
        payload["bom_lines"].append(dict(leaf, line_id="LEAF-24", quantity_per="0.0001"))
        self.reject(payload, "BOM_PATH_LIMIT")

    def test_empty_phantom_paths_are_bounded_without_item_leaves(self):
        payload = chain(7)
        payload["bom_lines"] = [
            dict(line, line_id=f"{line['line_id']}-{branch}")
            for line in payload["bom_lines"][:-1] for branch in range(5)
        ]
        self.reject(payload, "BOM_PATH_LIMIT")

    def test_phantom_and_item_ancestor_cycles_reject(self):
        self.reject(self.fixture("negative-cycle"), "BOM_CYCLE")
        payload = chain()
        payload["bom_lines"][0]["component_id"] = "I0"
        self.reject(payload, "BOM_CYCLE")

    def test_unknown_branch_does_not_hide_known_cycle(self):
        payload = self.fixture("negative-cycle")
        payload["bom_lines"].append({
            "line_id": "A-UNKNOWN", "version_id": "CY-V",
            "component_id": "UNKNOWN", "line_type": "Item",
            "quantity_per": "1", "scrap_percent": "0",
        })
        self.reject(payload, "BOM_CYCLE")

    def test_unsupported_lines_units_and_phantom_scrap(self):
        for kind in ("Vendor", "Pegged supply", "Formula", "item", None, []):
            payload = chain()
            payload["bom_lines"][0]["line_type"] = kind
            with self.subTest(kind=kind):
                self.reject(payload, "UNSUPPORTED_LINE_TYPE")
        for unit in ("KG", "UNKNOWN", "ea", "", None):
            payload = chain()
            payload["items"][1]["unit"] = unit
            with self.subTest(unit=unit):
                self.reject(payload, "UNSUPPORTED_UNIT")
        payload = chain(2)
        payload["bom_lines"][0]["scrap_percent"] = "0.0001"
        self.reject(payload, "PHANTOM_SCRAP")

    def test_strict_canonical_decimal_types_and_bounds(self):
        for value in ("NaN", "Infinity", "1.0", ".5", "01", "+1", "-1", "1e2",
                      " 1", "0.00001", "0", "1000000.0001", 1, 0.5, True, None, []):
            payload = chain()
            payload["bom_lines"][0]["quantity_per"] = value
            with self.subTest(value=value):
                self.reject(payload, "INVALID_DECIMAL")
        for value in ("25.0001", "-0.1", "0.00001", False):
            payload = chain()
            payload["bom_lines"][0]["scrap_percent"] = value
            with self.subTest(scrap=value):
                self.reject(payload, "INVALID_DECIMAL")

    def test_small_exact_eight_level_decimal_never_rounds_to_zero(self):
        payload = chain(8)
        for line in payload["bom_lines"]:
            line["quantity_per"] = "0.0001"
        payload["bom_lines"][-1]["scrap_percent"] = "25"
        result, _ = self.solve(payload)
        row = result["outputs"]["component_requirements"][0]
        self.assertEqual(Decimal("1.25e-32"), Decimal(row["exact_qty"]))
        self.assertNotIn("e", row["exact_qty"].lower())
        self.assertEqual(1, row["required_qty"])

    def test_requirement_overflow_is_not_a_partial_plan(self):
        payload = chain()
        payload["work_orders"][0]["quantity"] = 2
        payload["bom_lines"][0]["quantity_per"] = "1000000"
        self.reject(payload, "REQUIREMENT_LIMIT")

    def test_bad_quantities_dates_ranges_and_boolean_types(self):
        for value in (True, False, -1, 0, 1000001, 1.0, "1", None):
            payload = chain()
            payload["work_orders"][0]["quantity"] = value
            with self.subTest(quantity=value):
                self.reject(payload, "MALFORMED_FIELD")
        for value in ("2026-2-01", "2026-02-30", "1999-12-31", "2101-01-01", None):
            payload = chain()
            payload["as_of"] = value
            with self.subTest(date=value):
                self.reject(payload, "MALFORMED_FIELD")
        payload = chain()
        payload["bom_versions"][0]["min_order_qty"] = 3
        payload["bom_versions"][0]["max_order_qty"] = 2
        self.reject(payload, "INVALID_RANGE")
        payload = chain()
        payload["horizon_end"] = "2026-04-30"
        self.reject(payload, "INVALID_RANGE")
        payload = chain()
        payload["stock_lots"][0]["reserved_external_qty"] = 2
        self.reject(payload, "RESERVATION_EXCEEDS_STOCK")
        payload = chain()
        payload["bom_versions"][0]["approved"] = 1
        self.reject(payload, "MALFORMED_FIELD")

    def test_exact_schema_and_row_limits(self):
        for table in ("work_orders", "bom_versions", "bom_lines", "items", "stock_lots", "inbound"):
            missing = chain()
            del missing[table]
            self.reject(missing, "MALFORMED_INPUT")
            wrong = chain()
            wrong[table] = None
            self.reject(wrong, "MALFORMED_INPUT")
        payload = chain()
        payload["stock_lots"] *= 201
        self.reject(payload, "MALFORMED_INPUT")
        payload = chain()
        payload["work_orders"] = []
        self.reject(payload, "MALFORMED_INPUT")
        payload = chain()
        payload["items"][0]["unexpected"] = "not a field"
        self.reject(payload, "MALFORMED_FIELD")
        payload = chain()
        del payload["work_orders"][0]["requested_version_id"]
        self.reject(payload, "MALFORMED_FIELD")
        payload = chain()
        payload["stock_lots"][0]["stock_id"] = "not an ID"
        self.reject(payload, "MALFORMED_FIELD")
        self.reject([], "MALFORMED_INPUT")

    def test_duplicate_identity_not_value_and_conflicting_ids_reject(self):
        payload = chain()
        payload["bom_lines"].append(copy.deepcopy(payload["bom_lines"][0]))
        result, _ = self.solve(payload)
        self.assertEqual(1, result["outputs"]["component_requirements"][0]["required_qty"])
        self.assertEqual(["DUPLICATE_ROW"], [e["code"] for e in result["exceptions"]])
        payload["bom_lines"][-1]["quantity_per"] = "2"
        self.reject(payload, "CONFLICTING_ID")
        payload["bom_lines"][-1]["line_id"] = "OTHER"
        result, _ = self.solve(payload)
        self.assertEqual(3, result["outputs"]["component_requirements"][0]["required_qty"])
        payload = chain()
        duplicate = dict(payload["stock_lots"][0], quantity=True)
        payload["stock_lots"].append(duplicate)
        self.reject(payload, "MALFORMED_FIELD")

    def test_unknown_component_discards_all_partial_order_ledgers(self):
        payload = chain()
        payload["bom_lines"].append(dict(
            payload["bom_lines"][0], line_id="Z-UNKNOWN", component_id="MISSING",
        ))
        result, _ = self.solve(payload)
        out = result["outputs"]
        for key in ("selected_versions", "exploded_paths", "component_requirements", "shadow_allocations"):
            self.assertEqual([], out[key])
        self.assertEqual("unresolved-review", out["order_reviews"][0]["state"])
        self.assertEqual(1, out["source_balances"][0]["remaining_qty"])
        self.assertIn("UNKNOWN_ITEM", [e["code"] for e in result["exceptions"]])

    def test_empty_bom_is_unresolved_not_zero_demand(self):
        payload = chain()
        payload["bom_lines"] = []
        result, _ = self.solve(payload)
        self.assertEqual("unresolved-review", result["outputs"]["order_reviews"][0]["state"])
        self.assertEqual([], result["outputs"]["component_totals"])
        self.assertIn("EMPTY_BOM", [e["code"] for e in result["exceptions"]])

    def test_orphan_line_is_reported_without_inventing_a_join(self):
        payload = chain()
        payload["bom_lines"].append(dict(
            payload["bom_lines"][0], line_id="ORPHAN", version_id="ABSENT",
            quantity_per="100",
        ))
        result, _ = self.solve(payload)
        self.assertEqual(1, result["outputs"]["component_requirements"][0]["required_qty"])
        self.assertIn("ORPHAN_BOM_LINE", [e["code"] for e in result["exceptions"]])

    def test_unknown_master_expiry_and_unreceived_inbound_are_not_supply(self):
        result, _ = self.solve(self.fixture("holdout-unknown"))
        out = result["outputs"]
        self.assertEqual([], out["shadow_allocations"])
        self.assertEqual(["U01", "U02"], out["review_queue"])
        self.assertEqual({"unknown-item", "unknown-expiry", "blocked-status", "unconfirmed", "not-future"},
                         {x["reason"] for x in out["supply_exclusions"]})
        row = out["component_requirements"][0]
        self.assertEqual((0, 0, 1), (row["available_now_qty"], row["expected_before_need_qty"], row["gap_qty"]))

    def test_stock_exclusion_precedence_and_external_reservation(self):
        payload = chain()
        stock = payload["stock_lots"][0]
        stock.update(site="OTHER", status="blocked", expires_on="2026-04-30")
        result, _ = self.solve(payload)
        self.assertEqual("wrong-site", result["outputs"]["supply_exclusions"][0]["reason"])
        stock["site"] = "TEST"
        result, _ = self.solve(payload)
        self.assertEqual("blocked-status", result["outputs"]["supply_exclusions"][0]["reason"])
        stock["status"] = "available"
        result, _ = self.solve(payload)
        self.assertEqual("expired-before-need", result["outputs"]["supply_exclusions"][0]["reason"])
        stock["expires_on"] = None
        stock["reserved_external_qty"] = 1
        result, _ = self.solve(payload)
        self.assertEqual("no-unreserved-quantity", result["outputs"]["supply_exclusions"][0]["reason"])
        self.assertEqual(0, result["outputs"]["source_balances"][0]["net_qty"])

    def test_earliest_expiry_then_null_and_source_id(self):
        payload = chain()
        payload["work_orders"][0]["quantity"] = 3
        base = payload["stock_lots"][0]
        payload["stock_lots"] = [
            dict(base, stock_id="A-UNDATED", expires_on=None),
            dict(base, stock_id="B-LATER", expires_on="2026-05-04"),
            dict(base, stock_id="D-EARLY", expires_on="2026-05-02"),
            dict(base, stock_id="C-EARLY", expires_on="2026-05-02"),
        ]
        result, _ = self.solve(payload)
        self.assertEqual(["C-EARLY", "D-EARLY", "B-LATER"],
                         [a["source_id"] for a in result["outputs"]["shadow_allocations"]])

    def test_inbound_date_source_ties_stock_first_and_conservation(self):
        payload = chain()
        payload["horizon_end"] = "2026-05-04"
        payload["work_orders"][0].update(start_date="2026-05-04", quantity=5)
        payload["stock_lots"][0]["quantity"] = 1
        base = {
            "receipt_id": "I-C", "item_id": "LEAF", "site": "TEST",
            "expected_on": "2026-05-03", "quantity": 2, "confirmed": True,
        }
        payload["inbound"] = [
            base, dict(base, receipt_id="I-B", expected_on="2026-05-02"),
            dict(base, receipt_id="I-A", expected_on="2026-05-02"),
        ]
        result, _ = self.solve(payload)
        self.assertEqual(["S1", "I-A", "I-B"],
                         [a["source_id"] for a in result["outputs"]["shadow_allocations"]])
        self.assertEqual(2, result["outputs"]["source_balances"][-1]["remaining_qty"])

    def test_unconfirmed_overdue_wrong_site_and_late_inbound(self):
        for change, reason in (
            ({"confirmed": False}, "unconfirmed"),
            ({"expected_on": "2026-05-01"}, "not-future"),
            ({"expected_on": "2026-04-30"}, "not-future"),
            ({"expected_on": "2026-05-03"}, "late"),
            ({"site": "OTHER", "confirmed": False}, "wrong-site"),
        ):
            payload = chain()
            payload["stock_lots"] = []
            receipt = {
                "receipt_id": "I1", "item_id": "LEAF", "site": "TEST",
                "expected_on": "2026-05-02", "quantity": 1, "confirmed": True,
            }
            payload["inbound"] = [dict(receipt, **change)]
            with self.subTest(reason=reason, change=change):
                result, _ = self.solve(payload)
                self.assertEqual([], result["outputs"]["shadow_allocations"])
                self.assertEqual(reason, result["outputs"]["supply_exclusions"][0]["reason"])

    def test_start_date_precedes_priority_then_order_id(self):
        payload = chain()
        base = payload["work_orders"][0]
        payload["work_orders"] = [
            dict(base, order_id="A-LATER", start_date="2026-05-03", priority=1),
            dict(base, order_id="Z-FIRST", start_date="2026-05-01", priority=100),
            dict(base, order_id="C-MIDDLE", priority=1),
            dict(base, order_id="B-MIDDLE", priority=2),
        ]
        result, _ = self.solve(payload)
        self.assertEqual(["Z-FIRST", "C-MIDDLE", "B-MIDDLE", "A-LATER"],
                         result["outputs"]["order_sequence"])
        self.assertEqual("Z-FIRST", result["outputs"]["shadow_allocations"][0]["order_id"])

    def test_scope_boundaries_and_no_in_scope_orders(self):
        payload = chain()
        payload["work_orders"][0]["start_date"] = "2026-04-30"
        result, _ = self.solve(payload)
        self.assertEqual([], result["outputs"]["order_sequence"])
        self.assertEqual([{"order_id": "T01", "reason": "before-as-of"}],
                         result["outputs"]["excluded_orders"])
        for start in ("2026-05-01", "2026-05-03"):
            payload["work_orders"][0]["start_date"] = start
            result, _ = self.solve(payload)
            self.assertEqual(["T01"], result["outputs"]["order_sequence"])

    def test_partial_kit_assignment_is_not_backtracked(self):
        result, _ = self.solve(self.fixture("demo"))
        out = result["outputs"]
        self.assertEqual("shortage-review", out["order_reviews"][1]["state"])
        kept = [a for a in out["shadow_allocations"] if a["order_id"] == "W02"]
        self.assertEqual(10, sum(a["quantity"] for a in kept))
        self.assertEqual({"FRAME", "SCREW"}, {a["component_id"] for a in kept})

    def test_oversized_result_rejects_instead_of_truncating(self):
        payload = chain()
        payload["work_orders"] = [
            dict(payload["work_orders"][0], order_id=f"ORDER-{i:03d}-" + "Q" * 30)
            for i in range(200)
        ]
        payload["stock_lots"] = [
            dict(payload["stock_lots"][0], stock_id=f"STOCK-{i:03d}-" + "S" * 30, site="OTHER")
            for i in range(200)
        ]
        self.reject(payload, "OUTPUT_LIMIT")

    def test_cli_invalid_json_and_existing_files_fail_without_overwrite(self):
        with tempfile.TemporaryDirectory(prefix="cli-test-", dir=ROOT / "validation") as directory:
            temporary = Path(directory)
            source = temporary / "input.json"
            result_path = temporary / "result.json"
            trace_path = temporary / "trace.json"
            command = [
                sys.executable, "-B", str(ROOT / "baseline.py"), "--input", str(source),
                "--output", str(result_path), "--trace", str(trace_path),
            ]
            source.write_bytes(b'{"as_of": "2026-01-01", "as_of": "2026-01-02"}')
            process = subprocess.run(command, capture_output=True, check=False, timeout=30)
            self.assertNotEqual(0, process.returncode)
            self.assertFalse(result_path.exists())
            source.write_text(json.dumps(chain()), encoding="utf-8")
            process = subprocess.run(command, capture_output=True, check=False, timeout=30)
            self.assertEqual(0, process.returncode, process.stderr.decode())
            before = result_path.read_bytes(), trace_path.read_bytes(), source.read_bytes()
            process = subprocess.run(command, capture_output=True, check=False, timeout=30)
            self.assertNotEqual(0, process.returncode)
            self.assertEqual(before, (result_path.read_bytes(), trace_path.read_bytes(), source.read_bytes()))


if __name__ == "__main__":
    unittest.main()
