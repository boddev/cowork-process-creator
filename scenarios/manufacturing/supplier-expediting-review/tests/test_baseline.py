"""Owned standard-library tests; all temporary files stay under this scenario."""
from __future__ import annotations

import copy
import importlib.util
import random
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parents[1]))

from _shared.common import file_digest, load_json
from _shared.comparison import compare_json
from _shared.contract import KINDS, baseline_import_audit, load_scenario, validate_result
from _shared.pipeline import check_case_evidence, golden_lock, source_hashes

SPEC = importlib.util.spec_from_file_location("supplier_review_baseline", ROOT / "baseline.py")
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("Cannot load the owned supplier review baseline")
BASELINE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BASELINE)


def line(line_id="T01", quantity=10, due="2026-08-11", supplier="T-S1", state="open"):
    return {
        "line_id": line_id, "supplier_id": supplier, "item_id": "TEST-ITEM",
        "ordered_qty": quantity, "original_requested_receipt": due, "state": state,
    }


def receipt(event_id="T-R1", line_id="T01", quantity=2, posted="2026-08-10", reversal=None):
    return {
        "event_id": event_id, "line_id": line_id, "posted_on": posted,
        "qty": quantity, "reversal_of": reversal,
    }


def confirmation(confirmation_id="T-C1", line_id="T01", quantity=6, eta="2026-08-11", recorded="2026-08-10"):
    return {
        "confirmation_id": confirmation_id, "line_id": line_id,
        "recorded_on": recorded, "confirmed_receipt": eta, "remaining_qty": quantity,
    }


def requirement(requirement_id="T-Q1", line_id="T01", quantity=3, need="2026-08-11", criticality="normal"):
    return {
        "requirement_id": requirement_id, "line_id": line_id, "need_by": need,
        "unmet_qty": quantity, "criticality": criticality,
    }


def payload():
    return {
        "config": {
            "as_of": "2026-08-10", "reporting_month": "2026-08", "horizon_days": 5,
            "tolerance_days": 0, "urgency_days": 2, "low_performance_percent": 90,
        },
        "po_schedule_lines": [line()], "receipt_events": [],
        "confirmations": [], "requirements": [],
        "suppliers": [{"supplier_id": "T-S1", "buyer_role": "Test buyer"}],
    }


class SupplierReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scenario = load_scenario(ROOT)
        golden_lock(cls.scenario)

    def case_input(self, case_id):
        return load_json(self.scenario.file(self.scenario.case(case_id)["input"]))

    def completed(self, value):
        result, events = BASELINE.solve(value)
        validate_result(result)
        self.assertNotEqual("rejected", result["status"], result["exceptions"])
        self.assertEqual(10, len(events))
        return result

    def rejected(self, value, code):
        result, events = BASELINE.solve(value)
        validate_result(result)
        self.assertEqual("rejected", result["status"])
        self.assertEqual({}, result["outputs"])
        self.assertIn(code, {row["code"] for row in result["exceptions"]})
        self.assertEqual("input", events[0]["kind"])
        self.assertEqual("validation", events[-1]["kind"])
        return result

    def test_all_seven_independent_complete_goldens(self):
        for case in self.scenario.cases:
            with self.subTest(case=case["id"]):
                result, _ = BASELINE.solve(load_json(self.scenario.file(case["input"])))
                differences = compare_json(load_json(self.scenario.file(case["expected"])), result)
                self.assertEqual([], differences)

    def test_actual_shared_pipeline_evidence_is_current(self):
        for case in self.scenario.cases:
            with self.subTest(case=case["id"]):
                report = check_case_evidence(self.scenario, case)
                self.assertEqual("baseline_pass", report["state"])
                self.assertEqual("native_creation_blocked", report["native"]["creation"])
                self.assertEqual("not_run", report["native"]["independent_invocation"])

    def test_static_import_audit_and_exact_identity(self):
        audit = baseline_import_audit(ROOT / "baseline.py")
        self.assertEqual("static_import_check_pass", audit["status"])
        self.assertIn("scenario_support", audit["imports"])
        self.assertEqual("manufacturing-02", self.scenario.id)
        self.assertEqual("event-cohort-reconciliation-and-expediting", self.scenario.manifest["workflow_family"])

    def test_completed_runs_have_ten_real_bounded_stages(self):
        documented = [(row["id"], row["kind"]) for row in self.scenario.workflow["steps"]]
        for case in self.scenario.cases:
            value = load_json(self.scenario.file(case["input"]))
            result, events = BASELINE.solve(value)
            if result["status"] == "rejected":
                continue
            with self.subTest(case=case["id"]):
                self.assertEqual(documented, [(row["step_id"], row["kind"]) for row in events])
                self.assertEqual(KINDS, {row["kind"] for row in events})
                for event in events:
                    self.assertNotIn("sequence", event)
                    self.assertTrue(0 < len(event["caption"]) <= 260)
                    self.assertLessEqual(len(event["facts"]), 6)
                    self.assertTrue(1 <= len(event["tables"]) <= 2)
                    for table in event["tables"]:
                        self.assertTrue(1 <= len(table["columns"]) <= 6)
                        self.assertLessEqual(len(table["rows"]), 8)
                        self.assertGreaterEqual(table["total_rows"], len(table["rows"]))
                        for row in table["rows"]:
                            self.assertEqual(len(table["columns"]), len(row))
                            self.assertTrue(all(cell is None or type(cell) in (str, bool, int, float) for cell in row))
                        for index in table["highlight_rows"]:
                            self.assertTrue(0 <= index < len(table["rows"]))
                actual_gap = result["outputs"]["review_closure"]["shortage_qty"]
                demand_event = next(row for row in events if row["step_id"] == "evaluate-demand")
                self.assertEqual(actual_gap, demand_event["facts"]["shortage_qty"])

    def test_shuffle_preserves_complete_result_and_trace(self):
        for case in self.scenario.cases:
            if case["kind"] == "negative":
                continue
            original = self.case_input(case["id"])
            reference = BASELINE.solve(original)
            for seed in range(10):
                with self.subTest(case=case["id"], seed=seed):
                    shuffled = copy.deepcopy(original)
                    generator = random.Random(seed)
                    for key in BASELINE.TABLES:
                        generator.shuffle(shuffled[key])
                    self.assertEqual(reference, BASELINE.solve(shuffled))

    def test_inputs_and_locked_files_are_not_modified(self):
        before_hashes = source_hashes(self.scenario)
        before_lock = file_digest(ROOT / "validation" / "golden-lock.json")
        value = self.case_input("holdout-c")
        before_value = copy.deepcopy(value)
        first = BASELINE.solve(value)
        self.assertEqual(before_value, value)
        self.assertEqual(first, BASELINE.solve(value))
        self.assertEqual(before_hashes, source_hashes(self.scenario))
        self.assertEqual(before_lock, file_digest(ROOT / "validation" / "golden-lock.json"))

    def test_report_reconciliation_and_unsent_boundaries(self):
        for case in self.scenario.cases:
            result, _ = BASELINE.solve(self.case_input(case["id"]))
            if result["status"] == "rejected":
                continue
            with self.subTest(case=case["id"]):
                output = result["outputs"]
                closure = output["review_closure"]
                self.assertEqual(
                    closure["in_scope_unmet_qty"],
                    closure["covered_qty"] + closure["shortage_qty"] + closure["unresolved_unmet_qty"],
                )
                self.assertEqual(closure["queue_count"], len(output["buyer_review_queue"]))
                self.assertEqual(closure["exception_count"], len(result["exceptions"]))
                self.assertEqual(
                    closure["line_count"],
                    output["overall_performance"]["denominator"] + len(output["cohort_exclusions"]),
                )
                self.assertEqual(
                    output["overall_performance"]["denominator"],
                    sum(row["denominator"] for row in output["supplier_performance"]),
                )
                self.assertEqual(
                    output["overall_performance"]["numerator"],
                    sum(row["numerator"] for row in output["supplier_performance"]),
                )
                self.assertEqual(0, closure["messages_sent"])
                self.assertEqual(0, closure["orders_changed"])
                self.assertIs(True, closure["approval_required"])
                for row in output["buyer_review_queue"]:
                    self.assertEqual("unsent", row["send_status"])
                    self.assertIs(True, row["approval_required"])
                    self.assertEqual(len(row["reason_codes"]), len(row["draft_questions"]))

    def test_partial_late_receipts_do_not_inflate_denominator(self):
        result = self.completed(self.case_input("demo"))
        rows = {row["line_id"]: row for row in result["outputs"]["receipt_reconciliation"]}
        self.assertEqual((100, 60, 0, False), (
            rows["P01"]["net_received_qty"], rows["P01"]["on_time_qty"],
            rows["P01"]["open_qty"], rows["P01"]["otif"],
        ))
        self.assertEqual(["P01", "P03"], result["outputs"]["overall_performance"]["line_ids"])
        self.assertEqual("50.00", result["outputs"]["overall_performance"]["percent"])

    def test_as_of_full_void_and_future_void_are_separate(self):
        value = payload()
        value["po_schedule_lines"] = [line(due="2026-08-09")]
        value["receipt_events"] = [
            receipt("R1", quantity=4, posted="2026-08-08"),
            receipt("R2", quantity=6, posted="2026-08-09"),
            receipt("V1", quantity=4, posted="2026-08-10", reversal="R1"),
            receipt("V2", quantity=6, posted="2026-08-11", reversal="R2"),
        ]
        row = self.completed(value)["outputs"]["receipt_reconciliation"][0]
        self.assertEqual((6, 6, 4, False), (row["net_received_qty"], row["on_time_qty"], row["open_qty"], row["otif"]))
        self.assertEqual(["R2"], row["active_receipt_ids"])
        self.assertEqual(["R1"], row["voided_receipt_ids"])
        self.assertEqual(["V1"], row["reversal_event_ids"])
        self.assertEqual(["V2"], row["future_event_ids"])

    def test_same_day_receipt_and_void_remove_receipt_once(self):
        value = payload()
        value["po_schedule_lines"] = [line(due="2026-08-10")]
        value["receipt_events"] = [
            receipt("R1", quantity=10), receipt("V1", quantity=10, reversal="R1"),
        ]
        row = self.completed(value)["outputs"]["receipt_reconciliation"][0]
        self.assertEqual((0, 0, 10, False), (row["net_received_qty"], row["on_time_qty"], row["open_qty"], row["otif"]))

    def test_all_unsupported_reversal_relations_reject(self):
        variants = {
            "partial": [receipt("V1", quantity=1, reversal="R1")],
            "oversized": [receipt("V1", quantity=3, reversal="R1")],
            "missing": [receipt("V1", reversal="ABSENT")],
            "wrong-line": [receipt("V1", line_id="T02", reversal="R1")],
            "before-original": [receipt("V1", posted="2026-08-09", reversal="R1")],
            "self": [receipt("V1", reversal="V1")],
            "reversal-chain": [receipt("V1", reversal="R1"), receipt("V2", reversal="V1")],
            "repeated-future": [receipt("V1", reversal="R1"), receipt("V2", posted="2026-08-11", reversal="R1")],
            "cycle": [receipt("V1", reversal="V2"), receipt("V2", reversal="V1")],
        }
        for name, extra in variants.items():
            with self.subTest(relation=name):
                value = payload()
                value["po_schedule_lines"].append(line("T02"))
                value["receipt_events"] = [receipt("R1"), *extra]
                result = self.rejected(value, "INVALID_REVERSAL")
                self.assertTrue(all(row["code"] == "INVALID_REVERSAL" for row in result["exceptions"]))

    def test_identical_duplicate_reversals_collapse_once(self):
        value = payload()
        original = receipt("R1", quantity=4)
        reversal = receipt("V1", quantity=4, reversal="R1")
        value["receipt_events"] = [original, reversal, copy.deepcopy(reversal)]
        result = self.completed(value)
        row = result["outputs"]["receipt_reconciliation"][0]
        self.assertEqual(0, row["net_received_qty"])
        self.assertEqual(["V1"], row["reversal_event_ids"])
        duplicate = next(row for row in result["exceptions"] if row["code"] == "DUPLICATE_COLLAPSED")
        self.assertEqual(1, duplicate["count"])

    def test_identity_deduplication_in_every_table(self):
        value = payload()
        value["receipt_events"] = [receipt()]
        value["confirmations"] = [confirmation()]
        value["requirements"] = [requirement()]
        for table in BASELINE.TABLES:
            with self.subTest(table=table):
                duplicated = copy.deepcopy(value)
                duplicated[table].append(copy.deepcopy(duplicated[table][0]))
                result = self.completed(duplicated)
                warnings = [row for row in result["exceptions"] if row["code"] == "DUPLICATE_COLLAPSED"]
                self.assertEqual(1, len(warnings))
                self.assertEqual(table, warnings[0]["table"])
                self.assertEqual(1, warnings[0]["count"])
                self.assertEqual(2, result["outputs"]["receipt_reconciliation"][0]["net_received_qty"])
                self.assertEqual(3, result["outputs"]["review_closure"]["covered_qty"])

    def test_same_id_conflicts_in_every_table(self):
        value = payload()
        value["receipt_events"] = [receipt()]
        value["confirmations"] = [confirmation()]
        value["requirements"] = [requirement()]
        modifications = {
            "po_schedule_lines": ("ordered_qty", 11),
            "receipt_events": ("qty", 3),
            "confirmations": ("remaining_qty", 7),
            "requirements": ("unmet_qty", 4),
            "suppliers": ("buyer_role", "Different buyer"),
        }
        for table, (field, replacement) in modifications.items():
            with self.subTest(table=table):
                changed = copy.deepcopy(value)
                conflict = copy.deepcopy(changed[table][0])
                conflict[field] = replacement
                changed[table].append(conflict)
                self.rejected(changed, "CONFLICTING_ID")

    def test_quantity_types_and_ranges_are_not_coerced(self):
        for table, field, row in (
            ("po_schedule_lines", "ordered_qty", line()),
            ("receipt_events", "qty", receipt()),
            ("confirmations", "remaining_qty", confirmation()),
            ("requirements", "unmet_qty", requirement()),
        ):
            for invalid in (True, False, "2", 1.0, 1.5, -1, 1_000_001, None, float("inf"), float("nan")):
                with self.subTest(table=table, invalid=invalid):
                    value = payload()
                    bad_row = copy.deepcopy(row)
                    bad_row[field] = invalid
                    value[table] = [bad_row]
                    self.rejected(value, "MALFORMED_INPUT")
            if field != "remaining_qty":
                value = payload()
                bad_row = copy.deepcopy(row)
                bad_row[field] = 0
                value[table] = [bad_row]
                self.rejected(value, "MALFORMED_INPUT")
        value = payload()
        value["confirmations"] = [confirmation(quantity=0)]
        result = self.completed(value)
        self.assertEqual(0, result["outputs"]["confirmation_review"][0]["remaining_qty"])

    def test_shape_missing_fields_unknown_fields_and_row_limits(self):
        self.rejected([], "MALFORMED_INPUT")
        for key in ("config", *BASELINE.TABLES):
            with self.subTest(missing=key):
                value = payload()
                del value[key]
                self.rejected(value, "MALFORMED_INPUT")
        for table in BASELINE.TABLES:
            for replacement in ({}, None, "not-an-array", [line()] * 201):
                with self.subTest(table=table, shape=type(replacement).__name__):
                    value = payload()
                    value[table] = replacement
                    self.rejected(value, "MALFORMED_INPUT")
        value = payload()
        value["unrecognized"] = []
        self.rejected(value, "MALFORMED_INPUT")
        value = payload()
        value["po_schedule_lines"][0]["receipt_ship_date"] = "2026-08-10"
        self.rejected(value, "MALFORMED_INPUT")
        value = payload()
        value["po_schedule_lines"][0]["state"] = "closed"
        self.rejected(value, "MALFORMED_INPUT")
        value = payload()
        value["requirements"] = [requirement(criticality="urgent")]
        self.rejected(value, "MALFORMED_INPUT")

    def test_date_month_and_derived_date_bounds(self):
        for invalid in ("20260810", "2026-8-10", "2026-02-30", "1999-12-31", "2101-01-01", None, True):
            with self.subTest(date=invalid):
                value = payload()
                value["config"]["as_of"] = invalid
                self.rejected(value, "MALFORMED_INPUT")
        for invalid in ("2026-00", "2026-13", "202608", "2026-8", "1999-12", "2101-01", 202608):
            with self.subTest(month=invalid):
                value = payload()
                value["config"]["reporting_month"] = invalid
                self.rejected(value, "MALFORMED_INPUT")
        value = payload()
        value["config"].update(as_of="2100-12-31", horizon_days=1, urgency_days=0)
        self.rejected(value, "MALFORMED_INPUT")
        value = payload()
        value["po_schedule_lines"][0]["original_requested_receipt"] = "2100-12-31"
        value["config"]["tolerance_days"] = 1
        self.rejected(value, "MALFORMED_INPUT")
        value = payload()
        value["config"].update(horizon_days=1, urgency_days=2)
        self.rejected(value, "MALFORMED_INPUT")
        value = payload()
        value["config"].update(as_of="2000-02-29", reporting_month="2000-02", horizon_days=0, urgency_days=0)
        value["po_schedule_lines"] = [line(due="2000-02-29")]
        self.completed(value)

    def test_policy_integer_bounds_and_identifier_role_limits(self):
        for field, invalid in (
            ("horizon_days", 91), ("horizon_days", -1),
            ("urgency_days", 91), ("tolerance_days", 31),
            ("tolerance_days", True), ("low_performance_percent", 101),
            ("low_performance_percent", -1), ("low_performance_percent", "90"),
        ):
            with self.subTest(field=field, invalid=invalid):
                value = payload()
                value["config"][field] = invalid
                self.rejected(value, "MALFORMED_INPUT")
        for bad_id in ("", "_starts-wrong", "A" * 41, "non ascii \u00c5", True):
            value = payload()
            value["po_schedule_lines"][0]["line_id"] = bad_id
            self.rejected(value, "MALFORMED_INPUT")
        for bad_role in ("", " Buyer", "Buyer ", "Buyer\n", "X" * 81, None):
            value = payload()
            value["suppliers"][0]["buyer_role"] = bad_role
            self.rejected(value, "MALFORMED_INPUT")
        value = payload()
        value["po_schedule_lines"][0]["line_id"] = "A" * 40
        value["suppliers"][0]["buyer_role"] = "X" * 80
        result, events = BASELINE.solve(value)
        self.assertEqual("X" * 80, result["outputs"]["buyer_review_queue"][0]["buyer_role"])
        join_event = next(event for event in events if event["step_id"] == "join-purchase-context")
        self.assertEqual("X" * 69 + "...", join_event["tables"][0]["rows"][0][2])

    def test_maximum_receipts_aggregate_without_float_or_cap_loss(self):
        value = payload()
        value["po_schedule_lines"] = [line(quantity=1_000_000)]
        value["receipt_events"] = [receipt(f"R{index:03}", quantity=1_000_000) for index in range(200)]
        result = self.completed(value)
        row = result["outputs"]["receipt_reconciliation"][0]
        self.assertEqual(200_000_000, row["net_received_qty"])
        self.assertEqual(1_000_000, row["credited_received_qty"])
        self.assertEqual(199_000_000, row["overreceipt_qty"])
        self.assertEqual(0, row["open_qty"])
        self.assertEqual(200, len(row["active_receipt_ids"]))

    def test_two_hundred_line_trace_subsets_are_faithful(self):
        value = payload()
        value["po_schedule_lines"] = [line(f"T{index:03}", supplier=f"S{index:03}") for index in range(200)]
        value["suppliers"] = [{"supplier_id": f"S{index:03}", "buyer_role": "Scale buyer"} for index in range(200)]
        result, events = BASELINE.solve(value)
        self.assertNotEqual("rejected", result["status"])
        self.assertEqual(200, len(result["outputs"]["buyer_review_queue"]))
        for event in events:
            for table in event["tables"]:
                if table["total_rows"] > 8:
                    self.assertEqual(8, len(table["rows"]))
                    self.assertIn(f"first 8 of {table['total_rows']}", table["title"])
                else:
                    self.assertEqual(table["total_rows"], len(table["rows"]))
                    self.assertNotIn("first 8", table["title"])
        performance = next(row for row in events if row["step_id"] == "measure-performance")
        self.assertEqual(201, performance["tables"][0]["total_rows"])

    def test_half_up_rounding_and_exact_threshold_comparison(self):
        value = payload()
        value["po_schedule_lines"] = [line(f"T{index:02}", quantity=1, due="2026-08-10") for index in range(32)]
        value["receipt_events"] = [receipt(line_id="T00", quantity=1)]
        value["config"]["low_performance_percent"] = 3
        result = self.completed(value)["outputs"]["overall_performance"]
        self.assertEqual((1, 32, "3.13", False), (
            result["numerator"], result["denominator"], result["percent"], result["low_performance"],
        ))
        value["config"]["low_performance_percent"] = 4
        self.assertIs(True, self.completed(value)["outputs"]["overall_performance"]["low_performance"])
        value["po_schedule_lines"] = [line("T00", quantity=1, due="2026-08-10"), line("T01", quantity=1, due="2026-08-10")]
        value["config"]["low_performance_percent"] = 50
        self.assertIs(False, self.completed(value)["outputs"]["overall_performance"]["low_performance"])

    def test_tolerance_as_of_and_pending_are_independent_boundaries(self):
        value = payload()
        value["config"].update(as_of="2026-08-12", tolerance_days=2)
        value["po_schedule_lines"] = [line(due="2026-08-10")]
        value["receipt_events"] = [receipt(quantity=10, posted="2026-08-12")]
        self.assertIs(True, self.completed(value)["outputs"]["receipt_reconciliation"][0]["otif"])
        value["config"]["as_of"] = "2026-08-13"
        value["receipt_events"][0]["posted_on"] = "2026-08-13"
        self.assertIs(False, self.completed(value)["outputs"]["receipt_reconciliation"][0]["otif"])
        value["config"]["as_of"] = "2026-08-10"
        value["receipt_events"][0]["posted_on"] = "2026-08-11"
        row = self.completed(value)["outputs"]["receipt_reconciliation"][0]
        self.assertEqual((0, False, True), (row["net_received_qty"], row["otif"], row["performance_pending"]))
        value["receipt_events"][0]["posted_on"] = "2026-08-10"
        row = self.completed(value)["outputs"]["receipt_reconciliation"][0]
        self.assertEqual((10, True, False), (row["net_received_qty"], row["otif"], row["performance_pending"]))

    def test_cohort_exclusion_precedence_and_unused_supplier_history(self):
        value = payload()
        value["po_schedule_lines"] = [
            line("T1", due=None, state="cancelled"),
            line("T2", due=None),
            line("T3", due="2026-09-01"),
            line("T4", due="2026-08-11"),
            line("T5", due="2026-08-10"),
        ]
        value["suppliers"].append({"supplier_id": "UNUSED", "buyer_role": "Unused buyer"})
        result = self.completed(value)["outputs"]
        self.assertEqual(
            ["cancelled", "missing-requested-date", "outside-reporting-month", "future-requested-date", "included"],
            [row["cohort_status"] for row in result["receipt_reconciliation"]],
        )
        self.assertEqual(["T5"], result["overall_performance"]["line_ids"])
        unused = next(row for row in result["supplier_performance"] if row["supplier_id"] == "UNUSED")
        self.assertEqual((0, 0, None, None), (
            unused["numerator"], unused["denominator"], unused["percent"], unused["low_performance"],
        ))

    def test_latest_recorded_confirmation_not_earliest_eta_wins(self):
        value = payload()
        value["confirmations"] = [
            confirmation("C-A", quantity=5, recorded="2026-08-09"),
            confirmation("C-Z", quantity=7, eta="2026-08-13"),
            confirmation("C-F", quantity=10, recorded="2026-08-11"),
        ]
        value["requirements"] = [requirement(quantity=10, criticality="critical")]
        result = self.completed(value)
        row = result["outputs"]["confirmation_review"][0]
        self.assertEqual("C-Z", row["confirmation_id"])
        self.assertEqual(["C-A"], row["superseded_confirmation_ids"])
        self.assertEqual(["C-F"], row["future_confirmation_ids"])
        self.assertEqual(10, result["outputs"]["requirement_coverage"][0]["shortage_qty"])

    def test_equal_value_confirmation_ties_select_one_pool(self):
        value = payload()
        value["confirmations"] = [confirmation("C-Z"), confirmation("C-A")]
        value["requirements"] = [requirement("Q-B", quantity=4), requirement("Q-A", quantity=4)]
        result = self.completed(value)["outputs"]
        self.assertEqual("C-A", result["confirmation_review"][0]["confirmation_id"])
        self.assertEqual(["C-Z"], result["confirmation_review"][0]["superseded_confirmation_ids"])
        self.assertEqual([4, 2], [row["covered_qty"] for row in result["requirement_coverage"]])
        self.assertEqual([0, 2], [row["shortage_qty"] for row in result["requirement_coverage"]])

    def test_conflicting_eligible_dates_reject_even_when_superseded(self):
        value = payload()
        value["confirmations"] = [
            confirmation("C-A", recorded="2026-08-09"),
            confirmation("C-B", eta="2026-08-12", recorded="2026-08-09"),
            confirmation("C-NEW"),
        ]
        self.rejected(value, "CONFLICTING_CONFIRMATION")
        for row in value["confirmations"][:2]:
            row["recorded_on"] = "2026-08-11"
        result = self.completed(value)
        self.assertEqual("C-NEW", result["outputs"]["confirmation_review"][0]["confirmation_id"])
        self.assertEqual(2, sum(row["code"] == "FUTURE_CONFIRMATION" for row in result["exceptions"]))

    def test_missing_stale_and_same_day_eta_policies(self):
        for eta, state, covered, code in (
            (None, "missing-eta", 0, "MISSING_ETA"),
            ("2026-08-09", "stale", 0, "STALE_CONFIRMATION"),
            ("2026-08-10", "current", 3, None),
        ):
            with self.subTest(eta=eta):
                value = payload()
                value["confirmations"] = [confirmation(eta=eta)]
                value["requirements"] = [requirement()]
                result = self.completed(value)
                self.assertEqual(state, result["outputs"]["confirmation_review"][0]["state"])
                self.assertEqual(covered, result["outputs"]["requirement_coverage"][0]["covered_qty"])
                self.assertEqual(0, result["outputs"]["receipt_reconciliation"][0]["net_received_qty"])
                if code is not None:
                    self.assertIn(code, {row["code"] for row in result["exceptions"]})

    def test_allocation_is_single_use_and_late_promises_skip_early_needs(self):
        value = payload()
        value["confirmations"] = [confirmation(quantity=6, eta="2026-08-12")]
        value["requirements"] = [
            requirement("Q-C", quantity=4, need="2026-08-12", criticality="critical"),
            requirement("Q-A", quantity=2, criticality="critical"),
            requirement("Q-B", quantity=4, need="2026-08-12"),
        ]
        rows = self.completed(value)["outputs"]["requirement_coverage"]
        self.assertEqual(["Q-A", "Q-B", "Q-C"], [row["requirement_id"] for row in rows])
        self.assertEqual([0, 4, 2], [row["covered_qty"] for row in rows])
        self.assertEqual([2, 0, 2], [row["shortage_qty"] for row in rows])

    def test_unmet_requirements_are_not_netted_against_receipts(self):
        value = payload()
        value["receipt_events"] = [receipt(quantity=4)]
        value["confirmations"] = [confirmation(quantity=6)]
        value["requirements"] = [requirement(quantity=6)]
        result = self.completed(value)["outputs"]
        self.assertEqual(6, result["receipt_reconciliation"][0]["open_qty"])
        self.assertEqual(6, result["requirement_coverage"][0]["covered_qty"])
        self.assertEqual(0, result["requirement_coverage"][0]["shortage_qty"])

    def test_supply_never_crosses_purchase_lines(self):
        value = payload()
        value["po_schedule_lines"].append(line("T02"))
        value["confirmations"] = [confirmation(quantity=10)]
        value["requirements"] = [requirement(line_id="T02", quantity=10)]
        result = self.completed(value)["outputs"]
        self.assertEqual(0, result["requirement_coverage"][0]["covered_qty"])
        self.assertEqual(10, result["requirement_coverage"][0]["shortage_qty"])
        self.assertEqual(["T02"], [row["line_id"] for row in result["buyer_review_queue"]])

    def test_scope_includes_boundary_and_preserves_outside_nulls(self):
        value = payload()
        value["po_schedule_lines"] = [
            line(due="2026-08-16"), line("T02", due="2026-08-16"), line("T03", due=None),
        ]
        value["confirmations"] = [confirmation(quantity=6, eta="2026-08-15")]
        value["requirements"] = [
            requirement("Q-A", need="2026-08-15"),
            requirement("Q-B", need="2026-08-16"),
        ]
        result = self.completed(value)
        rows = result["outputs"]["requirement_coverage"]
        self.assertEqual([True, False], [row["in_scope"] for row in rows])
        self.assertEqual([3, None], [row["covered_qty"] for row in rows])
        self.assertEqual([0, None], [row["shortage_qty"] for row in rows])
        self.assertEqual([True, False, True], [row["in_scope"] for row in result["outputs"]["confirmation_review"]])
        self.assertEqual(["T03"], [row["line_id"] for row in result["outputs"]["buyer_review_queue"]])
        self.assertNotIn("T02", [row["record_id"] for row in result["exceptions"]])

    def test_capacity_rejects_all_demand_even_beyond_horizon(self):
        value = payload()
        value["po_schedule_lines"] = [line(quantity=5)]
        value["requirements"] = [requirement("Q-A"), requirement("Q-B", need="2026-08-20")]
        self.rejected(value, "DEMAND_EXCEEDS_OPEN")
        value["po_schedule_lines"][0]["state"] = "cancelled"
        self.rejected(value, "CANCELLED_LINE_DEMAND")

    def test_selected_promise_capacity_cannot_be_silently_capped(self):
        for eta, due in (("2026-08-11", "2026-08-11"), ("2026-08-09", "2026-08-20")):
            value = payload()
            value["po_schedule_lines"][0]["original_requested_receipt"] = due
            value["confirmations"] = [confirmation(quantity=11, eta=eta)]
            self.rejected(value, "CONFIRMATION_EXCEEDS_OPEN")
        value = payload()
        value["receipt_events"] = [receipt(quantity=4)]
        value["confirmations"] = [
            confirmation("C-OLD", quantity=11, recorded="2026-08-09"),
            confirmation("C-NOW", quantity=6),
            confirmation("C-FUTURE", quantity=11, recorded="2026-08-11"),
        ]
        result = self.completed(value)
        self.assertEqual(6, result["outputs"]["confirmation_review"][0]["supply_qty"])

    def test_fulfilled_and_cancelled_lines_never_supply_or_queue(self):
        value = payload()
        value["po_schedule_lines"] = [line(due="2026-08-10"), line("T02", state="cancelled")]
        value["receipt_events"] = [receipt(quantity=10)]
        value["confirmations"] = [
            confirmation(quantity=200), confirmation("C-CANCEL", line_id="T02"),
        ]
        result = self.completed(value)["outputs"]
        self.assertEqual(["not-open", "cancelled"], [row["state"] for row in result["confirmation_review"]])
        self.assertEqual([0, 0], [row["supply_qty"] for row in result["confirmation_review"]])
        self.assertEqual([], result["buyer_review_queue"])
        self.assertEqual(0, result["review_closure"]["active_open_qty"])

    def test_orphans_unknown_ownership_and_null_arithmetic(self):
        value = payload()
        value["po_schedule_lines"] = [line(due="2026-08-10", supplier="MISSING")]
        value["receipt_events"] = [receipt(line_id="ABSENT", quantity=10)]
        value["confirmations"] = [confirmation(line_id="ABSENT")]
        value["requirements"] = [
            requirement("Q-KNOWN", quantity=2),
            requirement("Q-UNKNOWN", line_id="ABSENT", quantity=4),
            requirement("Q-FUTURE", line_id="ABSENT", quantity=5, need="2026-08-20"),
        ]
        result = self.completed(value)
        output = result["outputs"]
        self.assertEqual(0, output["receipt_reconciliation"][0]["net_received_qty"])
        self.assertEqual(1, output["overall_performance"]["denominator"])
        self.assertIsNone(output["buyer_review_queue"][0]["buyer_role"])
        orphan = next(row for row in output["requirement_coverage"] if row["requirement_id"] == "Q-UNKNOWN")
        self.assertEqual("unresolved-line", orphan["assessment"])
        self.assertIsNone(orphan["covered_qty"])
        self.assertIsNone(orphan["shortage_qty"])
        self.assertEqual(6, output["review_closure"]["in_scope_unmet_qty"])
        self.assertEqual(2, output["review_closure"]["shortage_qty"])
        self.assertEqual(4, output["review_closure"]["unresolved_unmet_qty"])
        self.assertEqual(1, output["review_closure"]["unresolved_requirement_count"])
        codes = {row["code"] for row in result["exceptions"]}
        self.assertTrue({"ORPHAN_RECEIPT", "ORPHAN_CONFIRMATION", "ORPHAN_REQUIREMENT", "UNKNOWN_SUPPLIER"} <= codes)

    def test_queue_complete_sort_priority_and_urgency_comparator(self):
        value = payload()
        ids = ["T-U0", "T-U1", "T-QA", "T-QB", "T-QC", "T-LATE", "T-OD", "T-DATED", "T-MISS"]
        value["po_schedule_lines"] = [
            line(item, due=None if item == "T-DATED" else "2026-08-09" if item == "T-OD" else "2026-08-11")
            for item in reversed(ids)
        ]
        value["requirements"] = [
            requirement("Q-U0", "T-U0", 2, "2026-08-09", "critical"),
            requirement("Q-U1", "T-U1", 4, "2026-08-12", "critical"),
            requirement("Q-QA", "T-QA", 2, "2026-08-13"),
            requirement("Q-QB", "T-QB", 5, "2026-08-13"),
            requirement("Q-QC", "T-QC", 5, "2026-08-13"),
            requirement("Q-LATE", "T-LATE", 8, "2026-08-13", "critical"),
            requirement("Q-DATED", "T-DATED", 1, "2026-08-11"),
        ]
        value["confirmations"] = [
            confirmation("C-OD", "T-OD", 0, "2026-08-10"),
            confirmation("C-DATED", "T-DATED", 1, "2026-08-11"),
        ]
        queue = self.completed(value)["outputs"]["buyer_review_queue"]
        self.assertEqual(
            ["T-U0", "T-U1", "T-LATE", "T-QB", "T-QC", "T-QA", "T-OD", "T-DATED", "T-MISS"],
            [row["line_id"] for row in queue],
        )
        self.assertEqual(["P1", "P1", "P2", "P2", "P2", "P2", "P2", "P3", "P3"], [row["priority"] for row in queue])
        self.assertEqual(list(range(1, 10)), [row["rank"] for row in queue])

    def test_queue_earliest_need_includes_covered_demand(self):
        value = payload()
        value["confirmations"] = [confirmation(quantity=6)]
        value["requirements"] = [
            requirement("Q-EARLY", quantity=4), requirement("Q-LATER", quantity=6, need="2026-08-13"),
        ]
        queue = self.completed(value)["outputs"]["buyer_review_queue"]
        self.assertEqual("2026-08-11", queue[0]["earliest_need_by"])
        self.assertEqual(4, queue[0]["shortage_qty"])

    def test_history_flags_never_multiply_supply_or_shortage(self):
        original = self.case_input("demo")
        zero_threshold = copy.deepcopy(original)
        zero_threshold["config"]["low_performance_percent"] = 0
        result = self.completed(original)["outputs"]
        changed = self.completed(zero_threshold)["outputs"]
        self.assertEqual(result["receipt_reconciliation"], changed["receipt_reconciliation"])
        self.assertEqual(result["requirement_coverage"], changed["requirement_coverage"])
        self.assertEqual(
            [(row["line_id"], row["priority"], row["shortage_qty"]) for row in result["buyer_review_queue"]],
            [(row["line_id"], row["priority"], row["shortage_qty"]) for row in changed["buyer_review_queue"]],
        )

    def test_public_native_inputs_contain_no_private_case_paths(self):
        texts = [
            (ROOT / "HOW_TO.md").read_text(encoding="utf-8"),
            (ROOT / "workflow.json").read_text(encoding="utf-8"),
            (ROOT / "mock-data" / "demo.json").read_text(encoding="utf-8"),
        ]
        for case in self.scenario.cases:
            for text in texts:
                self.assertNotIn(case["expected"], text)
                if case["kind"] != "demo":
                    self.assertNotIn(case["input"], text)
                    self.assertNotIn(case["id"], text)
        self.assertEqual([], self.scenario.connections["connections"])
        self.assertEqual("mock-exports-only", self.scenario.connections["mode"])
        self.assertEqual("demo/baseline.webm", self.scenario.manifest["video"])

    def test_all_documented_business_keys_are_in_procedure(self):
        procedure = (ROOT / "HOW_TO.md").read_text(encoding="utf-8")
        result = load_json(self.scenario.file(self.scenario.case("demo")["expected"]))

        def inspect(value):
            if isinstance(value, dict):
                for key, child in value.items():
                    self.assertIn(f"`{key}`", procedure, key)
                    inspect(child)
            elif isinstance(value, list):
                for child in value:
                    inspect(child)
        inspect(result)

    def cli(self, source, output, trace):
        return subprocess.run(
            [sys.executable, "-B", "-I", str(ROOT / "baseline.py"), "--input", str(source),
             "--output", str(output), "--trace", str(trace)],
            cwd=ROOT, capture_output=True, text=True, timeout=15, check=False,
        )

    def test_cli_writes_real_artifacts_and_refuses_existing_paths(self):
        with tempfile.TemporaryDirectory(prefix="_scratch-", dir=ROOT / "tests") as name:
            folder = Path(name)
            output, trace = folder / "result.json", folder / "trace.json"
            source = ROOT / "mock-data" / "demo.json"
            run = self.cli(source, output, trace)
            self.assertEqual(0, run.returncode, run.stderr)
            observed = load_json(trace)
            self.assertEqual("manufacturing-02", observed["scenario_id"])
            self.assertEqual(file_digest(source), observed["input_sha256"])
            self.assertEqual(list(range(1, 11)), [row["sequence"] for row in observed["events"]])
            before = (file_digest(output), file_digest(trace))
            rerun = self.cli(source, output, trace)
            self.assertEqual(2, rerun.returncode)
            self.assertIn("refuses existing outputs", rerun.stderr)
            self.assertEqual(before, (file_digest(output), file_digest(trace)))
            alias = self.cli(source, source, folder / "alias-trace.json")
            self.assertEqual(2, alias.returncode)
            self.assertIn("must be distinct", alias.stderr)

    def test_cli_invalid_json_is_infrastructure_failure_not_business_rejection(self):
        for content in ('{"config": NaN}', '{"config": 1, "config": 2}', '{"incomplete":', '[]'):
            with self.subTest(content=content):
                with tempfile.TemporaryDirectory(prefix="_scratch-", dir=ROOT / "tests") as name:
                    folder = Path(name)
                    source, output, trace = folder / "invalid.json", folder / "result.json", folder / "trace.json"
                    source.write_text(content, encoding="utf-8")
                    run = self.cli(source, output, trace)
                    self.assertEqual(2, run.returncode)
                    self.assertIn("Baseline failed:", run.stderr)
                    self.assertFalse(output.exists())
                    self.assertFalse(trace.exists())


if __name__ == "__main__":
    unittest.main()
