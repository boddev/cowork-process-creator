import copy
import importlib.util
from pathlib import Path
import unittest

from scenarios._shared.common import load_json
from scenarios._shared.comparison import compare_json
from scenarios._shared.contract import load_scenario
from scenarios._shared.pipeline import golden_lock


ROOT = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("manufacturing_quality_baseline", ROOT / "baseline.py")
BASELINE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BASELINE)


class QualityReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scenario = load_scenario(ROOT)
        golden_lock(cls.scenario, create=True)

    def fixture(self, name="demo"):
        return load_json(ROOT / "mock-data" / (name + ".json"))

    def solve(self, payload):
        original = copy.deepcopy(payload)
        result, events = BASELINE.solve(payload)
        self.assertEqual(payload, original, "The baseline mutated its input")
        return result, events

    def row(self, result, lot_id):
        return next(row for row in result["outputs"]["review_queue"] if row["lot_id"] == lot_id)

    def test_five_independent_full_goldens(self):
        for case in self.scenario.cases:
            with self.subTest(case=case["id"]):
                result, _ = self.solve(self.fixture(case["id"]))
                oracle = load_json(ROOT / case["expected"])
                self.assertEqual(compare_json(oracle, result), [])

    def test_actual_nine_stage_trace_and_values(self):
        result, events = self.solve(self.fixture())
        self.assertEqual([event["step_id"] for event in events], [
            "intake", "validate", "join-lot-context", "resolve-evidence", "evaluate-tests",
            "classify-review", "collect-exceptions", "order-review", "close-packet",
        ])
        self.assertEqual({event["kind"] for event in events},
                         {"input", "validation", "join", "decision", "exception", "output"})
        evidence = next(event for event in events if event["step_id"] == "resolve-evidence")
        failed_observation = next(row for row in evidence["tables"][0]["rows"] if row[0] == "MFG-R22")
        self.assertEqual(failed_observation[3:], ["5.13", "active"])
        self.assertEqual(events[-1]["facts"]["received_qty"], 1280)
        self.assertEqual(events[-1]["facts"]["received_qty"], result["outputs"]["totals"]["received_qty"])
        self.assertTrue(all(row["approval_required"] and not row["production_authorized"]
                            for row in result["outputs"]["review_queue"]))

    def test_shuffled_tables_do_not_change_decisions(self):
        for case in ("demo", "holdout-a", "holdout-b"):
            with self.subTest(case=case):
                payload = self.fixture(case)
                before, _ = self.solve(payload)
                for key in BASELINE.TABLES:
                    payload[key].reverse()
                after, _ = self.solve(payload)
                self.assertEqual(compare_json(before, after), [])

    def test_approved_retest_supersedes_but_does_not_release(self):
        payload = self.fixture("holdout-b")
        payload["observations"][1]["supersession_approved"] = True
        result, _ = self.solve(payload)
        row = self.row(result, "MFG-H11")
        self.assertEqual(row["review_state"], "evidence-complete")
        self.assertEqual(row["reason_codes"], [])
        self.assertEqual([r["evidence_state"] for r in row["test_checks"][0]["observations"]],
                         ["superseded", "active"])
        self.assertEqual(row["test_checks"][0]["observed_specimens"], 1)
        self.assertFalse(row["production_authorized"])

    def test_unapproved_ancestor_cannot_be_bypassed(self):
        payload = self.fixture("holdout-b")
        child = dict(payload["observations"][1], result_id="MFG-RB13",
                     supersedes_result_id="MFG-RB12", supersession_approved=True)
        payload["observations"].append(child)
        result, _ = self.solve(payload)
        row = self.row(result, "MFG-H11")
        self.assertEqual(row["review_state"], "nonconformance-review")
        self.assertEqual([r["evidence_state"] for r in row["test_checks"][0]["observations"]],
                         ["active", "pending-retest", "pending-retest"])
        self.assertEqual(row["test_checks"][0]["failed_result_ids"], ["MFG-RB11"])

    def test_future_approved_retest_is_not_active(self):
        payload = self.fixture("holdout-b")
        payload["observations"][1].update(observed_on="2027-01-06", supersession_approved=True)
        result, _ = self.solve(payload)
        row = self.row(result, "MFG-H11")
        self.assertEqual(row["test_checks"][0]["failed_result_ids"], ["MFG-RB11"])
        self.assertEqual(row["test_checks"][0]["observations"][1]["evidence_state"], "future")
        self.assertIn("future-observation", row["reason_codes"])
        self.assertNotIn("pending-retest", row["reason_codes"])

    def test_open_nc_survives_passing_retest(self):
        payload = self.fixture("holdout-b")
        payload["observations"][1]["supersession_approved"] = True
        payload["nonconformances"] = [{"nc_id": "MFG-OPEN", "lot_id": "MFG-H11",
                                      "state": "open", "reason": "Synthetic retained review."}]
        result, _ = self.solve(payload)
        row = self.row(result, "MFG-H11")
        self.assertEqual(row["review_state"], "nonconformance-review")
        self.assertEqual(row["open_nc_ids"], ["MFG-OPEN"])
        payload["nonconformances"][0]["state"] = "closed"
        result, _ = self.solve(payload)
        self.assertEqual(self.row(result, "MFG-H11")["review_state"], "evidence-complete")

    def test_cycle_branch_identity_and_chain_bound_reject(self):
        for variation in ("cycle", "branch", "identity", "length"):
            with self.subTest(variation=variation):
                payload = self.fixture("holdout-b")
                if variation == "cycle":
                    payload["observations"][0].update(
                        observed_on="2027-01-05", supersedes_result_id="MFG-RB12", supersession_approved=True)
                elif variation == "branch":
                    payload["observations"].append(dict(payload["observations"][1], result_id="MFG-FORK"))
                elif variation == "identity":
                    payload["observations"][1]["specimen_id"] = "MFG-DIFFERENT"
                else:
                    for number in range(3, 10):
                        previous = payload["observations"][-1]
                        payload["observations"].append(dict(
                            previous, result_id=f"MFG-LINK{number}", supersedes_result_id=previous["result_id"]))
                result, _ = self.solve(payload)
                self.assertEqual(result["status"], "rejected")
                self.assertEqual(result["outputs"], {})
                self.assertIn(result["exceptions"][0]["code"], {"contradictory-evidence", "input-limit"})

    def test_missing_future_and_partial_physical_hold(self):
        payload = self.fixture()
        payload["hold_snapshot"][0]["snapshot_date"] = "2026-09-15"
        result, _ = self.solve(payload)
        row = self.row(result, "MFG-L01")
        self.assertIsNone(row["physical_held_qty"])
        self.assertEqual(row["review_state"], "evidence-gap")
        self.assertEqual(result["outputs"]["totals"]["known_held_qty"], 280)
        self.assertEqual(result["outputs"]["totals"]["unknown_hold_lot_ids"], ["MFG-L01"])
        payload["hold_snapshot"][0].update(snapshot_date="2026-09-14", physical_held_qty=20, hold_state="partial")
        result, _ = self.solve(payload)
        self.assertEqual(self.row(result, "MFG-L01")["physical_held_qty"], 20)
        self.assertEqual(result["outputs"]["totals"]["known_held_qty"], 300)
        payload["hold_snapshot"][0]["hold_state"] = "held"
        result, _ = self.solve(payload)
        self.assertEqual(result["status"], "rejected")

    def test_certificate_boundary_expiry_null_and_optional_policy(self):
        payload = self.fixture()
        result, _ = self.solve(payload)
        self.assertEqual(self.row(result, "MFG-L01")["certificate_ids"], ["MFG-C01"])
        for validity in ("2026-09-13", None):
            with self.subTest(validity=validity):
                changed = copy.deepcopy(payload)
                changed["certificates"][0]["valid_through"] = validity
                result, _ = self.solve(changed)
                row = self.row(result, "MFG-L01")
                self.assertEqual(row["certificate_ids"], [])
                self.assertEqual(row["review_state"], "evidence-gap")
                self.assertIn("unusable-certificate", row["reason_codes"])
        payload["config"]["certificate_required"] = False
        payload["certificates"] = []
        result, _ = self.solve(payload)
        self.assertNotIn("missing-certificate", self.row(result, "MFG-L01")["reason_codes"])
        self.assertEqual(self.row(result, "MFG-L03")["review_state"], "evidence-gap")

    def test_overdue_equal_threshold_is_not_overdue(self):
        payload = self.fixture()
        payload["config"]["review_age_days"] = 6
        result, _ = self.solve(payload)
        row = self.row(result, "MFG-L01")
        self.assertEqual(row["age_days"], 6)
        self.assertFalse(row["overdue"])
        self.assertNotIn("overdue-review", row["reason_codes"])

    def test_equal_category_and_age_use_lot_id_tie_break(self):
        payload = self.fixture("holdout-a")
        payload["lots"][0]["receipt_date"] = "2026-10-01"
        payload["certificates"].append(dict(
            payload["certificates"][0], certificate_id="MFG-CA02", lot_id="MFG-H02"))
        result, _ = self.solve(payload)
        self.assertEqual([row["lot_id"] for row in result["outputs"]["review_queue"]],
                         ["MFG-H01", "MFG-H02"])
        self.assertEqual([row["rank"] for row in result["outputs"]["review_queue"]], [1, 2])

    def test_multiple_required_tests_are_evaluated_independently(self):
        payload = self.fixture()
        payload["test_requirements"].append(dict(
            payload["test_requirements"][0], requirement_id="MFG-SPEC-FINISH",
            test_id="MFG-FINISH", minimum="0", maximum="1", required_specimens=1))
        payload["observations"].append(dict(
            payload["observations"][0], result_id="MFG-FINISH-RESULT", test_id="MFG-FINISH", value="2"))
        result, _ = self.solve(payload)
        row = self.row(result, "MFG-L01")
        self.assertEqual(row["review_state"], "nonconformance-review")
        self.assertEqual([check["state"] for check in row["test_checks"]], ["complete", "failed"])
        self.assertEqual(row["test_checks"][1]["failed_result_ids"], ["MFG-FINISH-RESULT"])

    def test_unknown_lot_evidence_is_visible_without_invented_join(self):
        payload = self.fixture()
        payload["nonconformances"].append(
            {"nc_id": "MFG-ORPHAN", "lot_id": "MFG-NOLOT", "state": "open", "reason": "Unmatched export."})
        result, _ = self.solve(payload)
        issue = next(item for item in result["exceptions"] if item["subject"] == "nonconformances:MFG-ORPHAN")
        self.assertEqual(issue["code"], "unknown-reference")
        self.assertEqual(result["outputs"]["totals"]["lot_count"], 3)

    def test_ambiguous_requirement_and_conflicting_certificate_reject(self):
        payload = self.fixture()
        payload["test_requirements"].append(dict(payload["test_requirements"][0], requirement_id="MFG-OVERLAP"))
        result, _ = self.solve(payload)
        self.assertEqual(result["status"], "rejected")
        self.assertIn("Multiple requirements", result["exceptions"][0]["message"])
        payload = self.fixture()
        payload["certificates"][0]["item_id"] = "MFG-WRONG"
        result, _ = self.solve(payload)
        self.assertEqual(result["status"], "rejected")
        self.assertIn("Certificate item", result["exceptions"][0]["message"])

    def test_missing_requirements_never_imply_complete(self):
        payload = self.fixture()
        payload["test_requirements"] = []
        result, _ = self.solve(payload)
        self.assertTrue(all(row["review_state"] == "data-review" for row in result["outputs"]["review_queue"]))
        self.assertTrue(all(row["test_checks"] == [] for row in result["outputs"]["review_queue"]))

    def test_strict_types_ranges_and_decimal_rejection(self):
        for value in (True, 0, -1, 1_000_001, 1.0, "1000"):
            with self.subTest(quantity=value):
                payload = self.fixture()
                payload["lots"][0]["received_qty"] = value
                result, _ = self.solve(payload)
                self.assertEqual(result["status"], "rejected")
        for value in (float("nan"), "NaN", "Infinity", "1e2", "01.0", "5.00001", True):
            with self.subTest(decimal=value):
                payload = self.fixture()
                payload["observations"][0]["value"] = value
                result, _ = self.solve(payload)
                self.assertEqual(result["status"], "rejected")

    def test_invalid_boolean_cannot_hide_in_duplicate_row(self):
        payload = self.fixture("holdout-b")
        duplicate = dict(payload["test_requirements"][0], required_specimens=True)
        payload["test_requirements"].append(duplicate)
        result, _ = self.solve(payload)
        self.assertEqual(result["status"], "rejected")
        self.assertEqual(result["exceptions"][0]["code"], "invalid-field")
        self.assertTrue(result["exceptions"][0]["subject"].endswith(".required_specimens"))

    def test_table_bound_and_empty_scope(self):
        payload = self.fixture()
        payload["items"] = payload["items"] * 201
        result, _ = self.solve(payload)
        self.assertEqual(result["status"], "rejected")
        payload = self.fixture()
        for key in BASELINE.TABLES:
            payload[key] = []
        result, events = self.solve(payload)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["outputs"]["review_queue"], [])
        self.assertEqual(result["outputs"]["totals"]["received_qty"], 0)
        self.assertEqual(len(events), 9)


if __name__ == "__main__":
    unittest.main()
