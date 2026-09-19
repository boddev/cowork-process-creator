"""Owned hls-04 rule, boundary, oracle, and safety tests."""

import copy
import importlib.util
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scenarios._shared.comparison import compare_json
from scenarios._shared.contract import baseline_import_audit, load_scenario
from scenarios._shared.pipeline import golden_lock


ROOT = (
    Path(__file__).resolve().parents[1]
    / "health-life-sciences"
    / "deviation-investigation-sop-validator"
)
TABLES = (
    "sop_versions",
    "requirements",
    "deviations",
    "investigations",
    "evidence",
    "open_review_tasks",
)


class DeviationInvestigationReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scenario = load_scenario(ROOT)
        golden_lock(cls.scenario)
        spec = importlib.util.spec_from_file_location(
            "owned_health_deviation_baseline", ROOT / "baseline.py"
        )
        cls.baseline = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.baseline)

    def read_case(self, case_id, directory="mock-data"):
        return json.loads(
            (ROOT / directory / f"{case_id}.json").read_text(encoding="utf-8")
        )

    def test_all_five_locked_manual_oracles_and_input_immutability(self):
        for case in self.scenario.cases:
            with self.subTest(case=case["id"]):
                packet = self.read_case(case["id"])
                before = copy.deepcopy(packet)
                result, _ = self.baseline.solve(packet)
                expected = self.read_case(case["id"], "expected")
                self.assertEqual(compare_json(expected, result), [])
                self.assertEqual(packet, before)
        golden_lock(self.scenario)

    def test_baseline_imports_are_bounded_and_outputs_never_authorize_actions(self):
        audit = baseline_import_audit(ROOT / "baseline.py")
        self.assertEqual(audit["status"], "static_import_check_pass")
        result, _ = self.baseline.solve(self.read_case("demo"))
        outputs = result["outputs"]
        self.assertIs(outputs["investigation_approval_authorized"], False)
        self.assertIs(outputs["deviation_closure_authorized"], False)
        self.assertTrue(
            all(
                row["approval_required"] and not row["deviation_update_authorized"]
                for row in outputs["draft_review_queue"]
            )
        )

    def test_table_order_does_not_change_complete_results(self):
        packet = self.read_case("demo")
        for table in TABLES:
            packet[table].reverse()
        result, _ = self.baseline.solve(packet)
        self.assertEqual(compare_json(self.read_case("demo", "expected"), result), [])

    def test_effective_date_boundary_selects_new_sop_version(self):
        result, _ = self.baseline.solve(self.read_case("holdout-a"))
        review = result["outputs"]["reviews"][0]
        self.assertEqual(review["selected_sop_version"], 2)
        self.assertEqual(review["due_state"], "due-soon")
        self.assertEqual(review["review_state"], "sop-gap")

    def test_overlapping_sop_versions_reject_instead_of_first_match(self):
        packet = self.read_case("holdout-a")
        packet["sop_versions"][0]["effective_to"] = "2026-07-01"
        result, _ = self.baseline.solve(packet)
        self.assertEqual(result["status"], "rejected")
        self.assertEqual(result["outputs"], {})
        self.assertEqual(result["exceptions"][0]["code"], "contradictory-evidence")
        self.assertEqual(result["exceptions"][0]["subject"], "deviations:SYN-DEV-H1")

    def test_investigation_sop_mismatch_is_data_review(self):
        packet = self.read_case("holdout-a")
        packet["investigations"][0]["sop_version"] = 1
        result, _ = self.baseline.solve(packet)
        review = result["outputs"]["reviews"][0]
        self.assertEqual(review["review_state"], "data-review")
        self.assertIn("sop-version-mismatch", review["reason_codes"])
        self.assertEqual(result["outputs"]["draft_review_queue"][0]["priority"], "high")

    def test_future_evidence_never_satisfies_a_requirement(self):
        result, _ = self.baseline.solve(self.read_case("holdout-a"))
        review = result["outputs"]["reviews"][0]
        approval = next(
            row
            for row in review["requirement_checks"]
            if row["evidence_type"] == "approval"
        )
        self.assertEqual(approval["state"], "missing")
        self.assertEqual(approval["evidence_ids"], [])
        self.assertIn("future-evidence", review["reason_codes"])

    def test_existing_task_suppresses_only_its_exact_reason(self):
        result, _ = self.baseline.solve(self.read_case("demo"))
        queue = next(
            row
            for row in result["outputs"]["draft_review_queue"]
            if row["deviation_id"] == "SYN-DEV-002"
        )
        self.assertEqual(queue["existing_task_ids"], ["SYN-TASK-D2-IMPACT"])
        self.assertIn("missing-impact-assessment", queue["reason_codes"])
        self.assertNotIn("missing-impact-assessment", queue["draft_reason_codes"])
        self.assertIn("missing-approval-evidence", queue["draft_reason_codes"])

    def test_queue_omits_a_review_when_every_reason_is_suppressed(self):
        packet = self.read_case("holdout-b")
        packet["open_review_tasks"] = [
            {
                "task_id": "SYN-TASK-H2-LATE",
                "deviation_id": "SYN-DEV-H2",
                "reason_code": "late-completion",
                "opened_on": "2026-02-16",
            }
        ]
        result, _ = self.baseline.solve(packet)
        self.assertEqual(result["outputs"]["reviews"][0]["reason_codes"], ["late-completion"])
        self.assertEqual(result["outputs"]["draft_review_queue"], [])
        self.assertEqual(result["exceptions"][0]["code"], "late-completion")

    def test_late_completed_closed_record_remains_review_only(self):
        result, _ = self.baseline.solve(self.read_case("holdout-b"))
        review = result["outputs"]["reviews"][0]
        self.assertEqual(review["source_status"], "closed")
        self.assertEqual(review["review_state"], "administratively-complete")
        self.assertEqual(review["due_state"], "completed-late")
        self.assertIn("late-completion", review["reason_codes"])
        self.assertIs(result["outputs"]["deviation_closure_authorized"], False)

    def test_public_procedure_labels_sample_policy_and_excludes_holdout_values(self):
        procedure = (ROOT / "HOW_TO.md").read_text(encoding="utf-8")
        self.assertIn("invented sample policy", procedure)
        self.assertIn("does not authenticate evidence", procedure)
        for private_value in ("SYN-DEV-H1", "SYN-DEV-H2", "SYN-POLICY-DEV-02"):
            self.assertNotIn(private_value, procedure)


if __name__ == "__main__":
    unittest.main()
