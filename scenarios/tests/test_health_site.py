"""Owned hls-01 rule, boundary, CLI, oracle, and actual-evidence tests."""

import copy
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import unittest
import uuid
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scenarios._shared.comparison import compare_json
from scenarios._shared.contract import baseline_import_audit, load_scenario, validate_trace
from scenarios._shared.pipeline import check_case_evidence, golden_lock


ROOT = Path(__file__).resolve().parents[1] / "health-life-sciences" / "site-essential-document-review"
TABLES = ("trials", "sites", "requirements", "documents", "artifacts", "open_review_tasks")


class SiteDocumentReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scenario = load_scenario(ROOT)
        golden_lock(cls.scenario)
        spec = importlib.util.spec_from_file_location("owned_health_site_baseline", ROOT / "baseline.py")
        cls.baseline = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.baseline)

    def packet(self):
        return {
            "schema_version": 1,
            "as_of_date": "2024-02-29",
            "policy": {
                "policy_id": "SYN-POLICY-UNIT", "warning_days": 7,
                "draft_review_days": 2, "max_rows_per_table": 100,
                "max_total_rows": 500, "max_derived_pairs": 100,
            },
            "trials": [{"trial_id": "SYN-T", "required_protocol_version": 2}],
            "sites": [{
                "site_id": "SYN-S", "trial_id": "SYN-T", "site_kind": "research",
                "owner_role_id": "SYN-ROLE", "in_scope": True,
            }],
            "requirements": [{
                "requirement_id": "SYN-R", "site_kind": "research",
                "document_type": "protocol", "match_protocol_version": True,
                "signature_required": True, "expiry_required": False, "refresh_days": None,
            }],
            "documents": [{
                "document_id": "SYN-D", "site_id": "SYN-S", "document_type": "protocol",
                "version_seq": 1, "protocol_version": 2,
                "issued_on": "2024-02-01", "effective_on": "2024-02-01",
                "recorded_on": "2024-02-01", "expires_on": None,
                "artifact_id": "SYN-A", "signature_recorded": True,
            }],
            "artifacts": [{
                "artifact_id": "SYN-A", "export_available": True,
                "readability_attested": True, "source_ref": "SYN-EXPORT",
            }],
            "open_review_tasks": [],
        }

    def read_case(self, case_id, directory="mock-data"):
        return json.loads((ROOT / directory / f"{case_id}.json").read_text(encoding="utf-8"))

    def evaluate(self, packet):
        result, events = self.baseline.solve(packet)
        self.assertNotEqual(result["status"], "rejected", result["exceptions"])
        return result, events

    def cell(self, result, site_id="SYN-S", requirement_id="SYN-R"):
        return next(
            row for row in result["outputs"]["requirement_matrix"]
            if (row["site_id"], row["requirement_id"]) == (site_id, requirement_id)
        )

    def evidence(self, result, table, record_id):
        return next(
            row for row in result["outputs"]["evidence_register"]
            if (row["table"], row["record_id"]) == (table, record_id)
        )

    def task(self, task_id="SYN-K", reason="missing-signature-evidence", opened="2024-02-29"):
        return {
            "task_id": task_id, "site_id": "SYN-S", "requirement_id": "SYN-R",
            "reason_code": reason, "opened_on": opened,
        }

    def assert_rejected(self, packet, path):
        result, events = self.baseline.solve(packet)
        self.assertEqual(result["schema_version"], 1)
        self.assertEqual(result["status"], "rejected")
        self.assertEqual(result["outputs"], {})
        self.assertIn(path, [item["path"] for item in result["exceptions"]])
        self.assertTrue(all(item["code"] == "invalid-input" for item in result["exceptions"]))
        self.assertEqual([event["kind"] for event in events], ["input", "validation"])
        return result

    def test_all_five_locked_manual_oracles_and_input_immutability(self):
        for case in self.scenario.cases:
            with self.subTest(case=case["id"]):
                packet = self.read_case(case["id"])
                before = copy.deepcopy(packet)
                result, _ = self.baseline.solve(packet)
                self.assertEqual(compare_json(self.read_case(case["id"], "expected"), result), [])
                self.assertEqual(packet, before)
        golden_lock(self.scenario)

    def test_all_persisted_shared_case_evidence_is_current_and_native_blocked(self):
        for case in self.scenario.cases:
            with self.subTest(case=case["id"]):
                report = check_case_evidence(self.scenario, case)
                self.assertEqual(report["execution"]["returncode"], 0)
                self.assertEqual(report["local"]["comparison"], "pass")
                self.assertEqual(report["native"]["creation"], "native_creation_blocked")
                self.assertEqual(report["native"]["independent_invocation"], "not_run")
                self.assertEqual(report["native"]["observed"], [])

    def test_import_audit_and_no_business_authorization_fields(self):
        audit = baseline_import_audit(ROOT / "baseline.py")
        self.assertEqual(audit["status"], "static_import_check_pass")
        self.assertIn("scenario_support", audit["imports"])
        result, _ = self.evaluate(self.packet())
        self.assertEqual(result["status"], "completed")
        self.assertIs(result["outputs"]["human_review_required"], True)
        for key in ("site_activated", "enrollment_approved", "regulatory_compliant", "signature_verified"):
            self.assertNotIn(key, result["outputs"])

    def test_public_procedure_does_not_contain_private_fixture_identifiers(self):
        procedure = (ROOT / "HOW_TO.md").read_text(encoding="utf-8")
        for text in ("holdout-a", "holdout-b", "SYN-POLICY-A", "SYN-POLICY-B", "SYN-POLICY-C", "SYN-POLICY-N"):
            self.assertNotIn(text, procedure)
        self.assertIn('"schema_version": 1', procedure)
        self.assertIn('"exceptions": []', procedure)
        self.assertIn("Appendix C.2", procedure)
        self.assertIn("mock-data/demo.json", procedure)

    def test_input_table_permutations_preserve_business_results(self):
        for case in self.scenario.cases:
            if case["id"] == "negative-malformed":
                continue
            with self.subTest(case=case["id"]):
                packet = self.read_case(case["id"])
                for table in TABLES:
                    packet[table].reverse()
                result, _ = self.evaluate(packet)
                self.assertEqual(compare_json(self.read_case(case["id"], "expected"), result), [])

    def test_complete_actual_demo_trace_uses_eight_documented_stages(self):
        packet = self.read_case("demo")
        result, events = self.evaluate(packet)
        fingerprint = hashlib.sha256(json.dumps(packet, sort_keys=True).encode("utf-8")).hexdigest()
        trace = {
            "schema_version": 1, "scenario_id": "hls-01",
            "provenance": "synthetic-local-baseline", "input_sha256": fingerprint,
            "events": [dict(event, sequence=index) for index, event in enumerate(events, 1)],
        }
        validate_trace(trace, self.scenario, self.scenario.case("demo"), fingerprint)
        self.assertEqual(len(events), 8)
        self.assertEqual([event["step_id"] for event in events], [step["id"] for step in self.scenario.workflow["steps"]])
        self.assertEqual(events[0]["facts"]["array_rows"], 22)
        self.assertEqual(events[2]["facts"]["required_pairs"], 8)
        self.assertEqual(events[5]["facts"]["draft_new"], 4)
        self.assertEqual(events[-1]["facts"]["status"], result["status"])
        self.assertEqual(events[4]["tables"][0]["rows"][1][-1], 0)

    def test_trace_values_change_with_actual_evidence(self):
        packet = self.read_case("demo")
        packet["documents"][1]["expires_on"] = "2026-09-13"
        result, events = self.evaluate(packet)
        assessed = events[4]["tables"][0]["rows"][1]
        self.assertEqual(assessed[2:], ["review", "expired", "2026-09-13", -1])
        self.assertEqual(self.cell(result, "SYN-S1", "SYN-R2")["reason_codes"], ["expired"])
        self.assertTrue(events[6]["facts"]["counts_conserved"])

    def test_trace_truncation_preserves_all_nine_business_cells(self):
        packet = self.packet()
        packet["sites"] = [dict(packet["sites"][0], site_id=f"SYN-S{index}") for index in range(3)]
        packet["requirements"] = [dict(packet["requirements"][0], requirement_id=f"SYN-R{index}") for index in range(3)]
        packet["documents"][0]["site_id"] = "SYN-S0"
        result, events = self.evaluate(packet)
        self.assertEqual(len(result["outputs"]["requirement_matrix"]), 9)
        table = events[2]["tables"][0]
        self.assertEqual((len(table["rows"]), table["total_rows"]), (8, 9))
        self.assertIn("first 8 of 9", table["title"])
        self.assertEqual(sum(row["required_count"] for row in result["outputs"]["site_summary"]), 9)

    def test_expiry_is_inclusive_at_zero_and_warning_boundary(self):
        for warning, offset, state, reasons in (
            (7, -1, "review", ["expired"]),
            (7, 0, "warning", ["expiring-soon"]),
            (7, 7, "warning", ["expiring-soon"]),
            (7, 8, "no-exception", []),
            (0, 0, "warning", ["expiring-soon"]),
            (0, 1, "no-exception", []),
        ):
            with self.subTest(warning=warning, days=offset):
                packet = self.packet()
                packet["policy"]["warning_days"] = warning
                packet["documents"][0]["expires_on"] = (date(2024, 2, 29) + timedelta(days=offset)).isoformat()
                result, _ = self.evaluate(packet)
                cell = self.cell(result)
                self.assertEqual((cell["assessment_state"], cell["reason_codes"], cell["days_to_expiry"]), (state, reasons, offset))

    def test_leap_calendar_earliest_expiry_and_equal_sources(self):
        for explicit, expiry, basis, days in (
            ("2024-02-29", "2024-02-29", "explicit", 0),
            ("2024-03-05", "2024-03-01", "refresh", 1),
            ("2024-03-01", "2024-03-01", "explicit-and-refresh", 1),
            (None, "2024-03-01", "refresh", 1),
        ):
            with self.subTest(explicit=explicit):
                packet = self.packet()
                packet["requirements"][0]["refresh_days"] = 29
                packet["documents"][0]["expires_on"] = explicit
                result, _ = self.evaluate(packet)
                cell = self.cell(result)
                self.assertEqual((cell["effective_expiry"], cell["expiry_basis"], cell["days_to_expiry"]), (expiry, basis, days))

    def test_null_expiry_is_not_an_invented_annual_expiration(self):
        packet = self.packet()
        packet["documents"][0].update(issued_on="2000-01-01", effective_on="2000-01-01", recorded_on="2000-01-01")
        result, _ = self.evaluate(packet)
        self.assertEqual(self.cell(result)["reason_codes"], [])
        self.assertEqual(self.cell(result)["expiry_basis"], "none")
        packet["requirements"][0]["expiry_required"] = True
        result, _ = self.evaluate(packet)
        self.assertEqual(self.cell(result)["reason_codes"], ["missing-expiry-evidence"])
        self.assertIsNone(self.cell(result)["days_to_expiry"])

    def test_supplied_expiry_is_assessed_even_when_not_required(self):
        packet = self.packet()
        packet["documents"][0]["expires_on"] = "2024-02-28"
        result, _ = self.evaluate(packet)
        self.assertEqual(self.cell(result)["reason_codes"], ["expired"])

    def test_effective_and_recorded_filters_are_separate_and_inclusive(self):
        for effective, recorded, flags, selected in (
            ("2024-02-29", "2024-03-01", ["future-recorded"], "SYN-D"),
            ("2024-03-01", "2024-02-29", ["future-effective"], "SYN-D"),
            ("2024-03-01", "2024-03-01", ["future-effective", "future-recorded"], "SYN-D"),
            ("2024-02-29", "2024-02-29", ["selected"], "SYN-D2"),
        ):
            with self.subTest(effective=effective, recorded=recorded):
                packet = self.packet()
                packet["documents"].append(dict(
                    packet["documents"][0], document_id="SYN-D2", version_seq=2,
                    effective_on=effective, recorded_on=recorded, signature_recorded=False,
                ))
                result, _ = self.evaluate(packet)
                self.assertEqual(self.cell(result)["selected_document_id"], selected)
                self.assertEqual(self.evidence(result, "documents", "SYN-D2")["dispositions"], flags)
                reasons = ["missing-signature-evidence"] if selected == "SYN-D2" else []
                self.assertEqual(self.cell(result)["reason_codes"], reasons)

    def test_future_only_evidence_is_missing_not_selected(self):
        packet = self.packet()
        packet["documents"][0]["recorded_on"] = "2024-03-01"
        result, _ = self.evaluate(packet)
        self.assertIsNone(self.cell(result)["selected_document_id"])
        self.assertEqual(self.cell(result)["reason_codes"], ["missing-document"])
        self.assertIn("documents/SYN-D", self.cell(result)["source_refs"])
        self.assertEqual(self.evidence(result, "documents", "SYN-D")["dispositions"], ["future-recorded"])

    def test_future_chronology_anomaly_does_not_replace_current_evidence(self):
        packet = self.packet()
        packet["documents"].append(dict(
            packet["documents"][0], document_id="SYN-FUTURE", version_seq=99,
            issued_on="2024-03-01", effective_on="2024-03-01", recorded_on="2024-03-01",
            expires_on="2024-02-29",
        ))
        result, _ = self.evaluate(packet)
        self.assertEqual(self.cell(result)["assessment_state"], "no-exception")
        self.assertEqual(self.cell(result)["selected_document_id"], "SYN-D")
        self.assertEqual([item["code"] for item in result["exceptions"]], ["impossible-chronology"])
        self.assertNotIn("quarantined", self.evidence(result, "documents", "SYN-FUTURE")["dispositions"])

    def test_latest_unavailable_unsigned_wrong_protocol_never_falls_back(self):
        packet = self.packet()
        packet["artifacts"].append(dict(packet["artifacts"][0], artifact_id="SYN-A2", export_available=False))
        packet["documents"].append(dict(
            packet["documents"][0], document_id="SYN-D2", version_seq=2,
            artifact_id="SYN-A2", signature_recorded=False, protocol_version=None,
            expires_on="2024-02-29",
        ))
        result, _ = self.evaluate(packet)
        self.assertEqual(self.cell(result)["selected_document_id"], "SYN-D2")
        self.assertEqual(self.cell(result)["reason_codes"], [
            "unavailable-evidence", "missing-signature-evidence",
            "protocol-version-mismatch", "expiring-soon",
        ])
        self.assertEqual(self.cell(result)["primary_reason"], "unavailable-evidence")
        self.assertEqual(self.cell(result)["assessment_state"], "review")
        self.assertEqual(self.evidence(result, "documents", "SYN-D")["dispositions"], ["superseded"])
        self.assertEqual(len(result["outputs"]["draft_review_queue"]), 4)

    def test_unavailable_export_and_unreadable_metadata_are_independent(self):
        for available, readable in ((False, True), (True, False), (False, False)):
            with self.subTest(available=available, readable=readable):
                packet = self.packet()
                packet["artifacts"][0].update(export_available=available, readability_attested=readable)
                result, _ = self.evaluate(packet)
                self.assertEqual(self.cell(result)["reason_codes"], ["unavailable-evidence"])
                self.assertIn("unavailable-metadata", self.evidence(result, "artifacts", "SYN-A")["dispositions"])

    def test_missing_artifact_is_not_a_missing_document(self):
        packet = self.packet()
        packet["artifacts"] = []
        result, _ = self.evaluate(packet)
        self.assertEqual(self.cell(result)["selected_document_id"], "SYN-D")
        self.assertEqual(self.cell(result)["reason_codes"], ["unavailable-evidence"])
        missing = [item for item in result["exceptions"] if item["code"] == "unmatched-reference"]
        self.assertEqual([(item["field"], item["ref_id"]) for item in missing], [("artifact_id", "SYN-A")])
        self.assertIn("artifacts/SYN-A", self.cell(result)["source_refs"])

    def test_conflicting_selected_artifact_quarantines_without_fallback(self):
        packet = self.packet()
        packet["artifacts"].append(dict(packet["artifacts"][0], readability_attested=False))
        result, _ = self.evaluate(packet)
        self.assertEqual(self.cell(result)["assessment_state"], "quarantined")
        self.assertIsNone(self.cell(result)["selected_document_id"])
        self.assertEqual(self.cell(result)["reason_codes"], ["conflict"])
        self.assertIn("quarantined", self.evidence(result, "artifacts", "SYN-A")["dispositions"])
        self.assertNotIn("selected-artifact", self.evidence(result, "artifacts", "SYN-A")["dispositions"])

    def test_identical_copies_collapse_in_every_table_with_provenance(self):
        packet = self.packet()
        packet["documents"][0]["signature_recorded"] = False
        packet["open_review_tasks"] = [self.task()]
        for table in TABLES:
            packet[table].append(copy.deepcopy(packet[table][0]))
        result, _ = self.evaluate(packet)
        self.assertEqual(len(result["outputs"]["requirement_matrix"]), 1)
        self.assertEqual(len(result["outputs"]["draft_review_queue"]), 1)
        self.assertEqual(result["outputs"]["draft_review_queue"][0]["existing_task_ids"], ["SYN-K"])
        duplicates = [item for item in result["exceptions"] if item["code"] == "duplicate-evidence"]
        self.assertEqual(len(duplicates), 6)
        self.assertTrue(all(item["duplicate_count"] == 1 for item in duplicates))
        self.assertTrue(all(row["copies"] == 2 and row["distinct_variants"] == 1 for row in result["outputs"]["evidence_register"]))
        self.assertNotIn("duplicate-open-tasks", [item["code"] for item in result["exceptions"]])

    def test_duplicate_and_conflicting_variants_have_separate_counts(self):
        packet = self.packet()
        packet["documents"].extend([
            copy.deepcopy(packet["documents"][0]),
            dict(packet["documents"][0], signature_recorded=False),
        ])
        result, _ = self.evaluate(packet)
        evidence = self.evidence(result, "documents", "SYN-D")
        self.assertEqual((evidence["copies"], evidence["distinct_variants"]), (3, 2))
        self.assertEqual([variant["copies"] for variant in evidence["conflicting_variants"]], [1, 2])
        self.assertEqual([variant["record"]["signature_recorded"] for variant in evidence["conflicting_variants"]], [False, True])
        self.assertEqual(self.cell(result)["reason_codes"], ["conflict"])
        self.assertIsNone(self.cell(result)["selected_document_id"])
        self.assertIn("duplicate-evidence", evidence["dispositions"])
        self.assertIn("conflicting-id", evidence["dispositions"])

    def test_distinct_ids_tied_at_highest_version_are_not_identical_duplicates(self):
        packet = self.packet()
        packet["documents"].append(dict(packet["documents"][0], document_id="SYN-D2"))
        result, _ = self.evaluate(packet)
        self.assertEqual(self.cell(result)["assessment_state"], "quarantined")
        self.assertEqual(self.cell(result)["reason_codes"], ["conflict"])
        self.assertTrue(all(
            self.evidence(result, "documents", record_id)["dispositions"] == ["quarantined"]
            for record_id in ("SYN-D", "SYN-D2")
        ))
        self.assertEqual([item["code"] for item in result["exceptions"]], ["requirement-review"])

    def test_lower_version_ties_are_superseded_when_highest_is_unique(self):
        packet = self.packet()
        packet["documents"].extend([
            dict(packet["documents"][0], document_id="SYN-D2", signature_recorded=False),
            dict(packet["documents"][0], document_id="SYN-D3", version_seq=2),
        ])
        result, _ = self.evaluate(packet)
        self.assertEqual(self.cell(result)["selected_document_id"], "SYN-D3")
        self.assertEqual(self.cell(result)["assessment_state"], "no-exception")
        self.assertEqual(self.evidence(result, "documents", "SYN-D2")["dispositions"], ["superseded"])

    def test_impossible_chronology_predicates_and_reason_suppression(self):
        for changes, violations in (
            ({"issued_on": "2024-02-20", "effective_on": "2024-02-19", "recorded_on": "2024-02-21"}, ["issued-after-effective"]),
            ({"issued_on": "2024-02-20", "effective_on": "2024-02-20", "recorded_on": "2024-02-19"}, ["recorded-before-issued"]),
            ({"issued_on": "2024-02-20", "effective_on": "2024-02-20", "recorded_on": "2024-02-21", "expires_on": "2024-02-19"}, ["expiry-before-issued", "expiry-before-effective"]),
            ({"issued_on": "2024-02-01", "effective_on": "2024-02-20", "recorded_on": "2024-02-21", "expires_on": "2024-02-19"}, ["expiry-before-effective"]),
        ):
            with self.subTest(violations=violations):
                packet = self.packet()
                packet["documents"][0].update(changes)
                result, _ = self.evaluate(packet)
                self.assertEqual(self.cell(result)["reason_codes"], ["conflict"])
                self.assertIsNone(self.cell(result)["effective_expiry"])
                issue = next(item for item in result["exceptions"] if item["code"] == "impossible-chronology")
                self.assertEqual(issue["violations"], violations)

    def test_impossible_eligible_old_version_cannot_be_silently_discarded(self):
        packet = self.packet()
        packet["documents"].append(dict(packet["documents"][0], document_id="SYN-D2", version_seq=2))
        packet["documents"][0]["issued_on"] = "2024-02-02"
        result, _ = self.evaluate(packet)
        self.assertEqual(self.cell(result)["reason_codes"], ["conflict"])
        self.assertIsNone(self.cell(result)["selected_document_id"])
        self.assertEqual(self.evidence(result, "documents", "SYN-D2")["dispositions"], ["quarantined"])

    def test_late_recording_after_expiry_is_not_impossible_chronology(self):
        packet = self.packet()
        packet["documents"][0].update(expires_on="2024-02-10", recorded_on="2024-02-29")
        result, _ = self.evaluate(packet)
        self.assertEqual(self.cell(result)["reason_codes"], ["expired"])
        self.assertNotIn("impossible-chronology", [item["code"] for item in result["exceptions"]])

    def test_conflicting_trial_quarantines_only_its_dependent_site(self):
        packet = self.packet()
        packet["trials"].extend([
            dict(packet["trials"][0], required_protocol_version=3),
            {"trial_id": "SYN-T2", "required_protocol_version": 2},
        ])
        packet["sites"].append(dict(packet["sites"][0], site_id="SYN-S2", trial_id="SYN-T2"))
        packet["documents"].append(dict(packet["documents"][0], document_id="SYN-D2", site_id="SYN-S2"))
        result, _ = self.evaluate(packet)
        self.assertEqual(self.cell(result)["reason_codes"], ["conflict"])
        self.assertEqual(self.cell(result, "SYN-S2")["assessment_state"], "no-exception")

    def test_conflicting_site_kind_expands_union_and_blocks_ambiguous_owner(self):
        packet = self.packet()
        packet["sites"].append(dict(packet["sites"][0], site_kind="satellite", owner_role_id="SYN-ROLE2"))
        packet["requirements"].append(dict(
            packet["requirements"][0], requirement_id="SYN-R2", site_kind="satellite", document_type="qualification",
        ))
        result, _ = self.evaluate(packet)
        self.assertEqual(len(result["outputs"]["requirement_matrix"]), 2)
        self.assertTrue(all(row["reason_codes"] == ["conflict"] for row in result["outputs"]["requirement_matrix"]))
        self.assertTrue(all(
            row["routing"] == "blocked-ambiguous" and row["owner_role_id"] is None and row["draft_review_by"] is None
            for row in result["outputs"]["draft_review_queue"]
        ))
        self.assertEqual(result["outputs"]["site_summary"][0]["quarantined_count"], 2)

    def test_conflicting_requirement_type_is_null_not_first_wins(self):
        packet = self.packet()
        packet["requirements"].append(dict(packet["requirements"][0], document_type="qualification"))
        result, _ = self.evaluate(packet)
        self.assertIsNone(self.cell(result)["document_type"])
        self.assertEqual(self.cell(result)["reason_codes"], ["conflict"])
        self.assertIn("documents/SYN-D", self.cell(result)["source_refs"])

    def test_missing_trial_and_unknown_document_site_are_explicit(self):
        packet = self.packet()
        packet["trials"] = []
        packet["documents"].append(dict(packet["documents"][0], document_id="SYN-ORPHAN", site_id="SYN-UNKNOWN"))
        result, _ = self.evaluate(packet)
        self.assertEqual(self.cell(result)["reason_codes"], ["conflict"])
        self.assertEqual(self.evidence(result, "documents", "SYN-ORPHAN")["dispositions"], ["unmatched"])
        refs = {(item["field"], item["ref_id"]) for item in result["exceptions"] if item["code"] == "unmatched-reference"}
        self.assertEqual(refs, {("trial_id", "SYN-T"), ("site_id", "SYN-UNKNOWN")})

    def test_site_kind_and_scope_control_denominator_not_document_count(self):
        packet = self.packet()
        packet["sites"].extend([
            dict(packet["sites"][0], site_id="SYN-OUT", in_scope=False),
            dict(packet["sites"][0], site_id="SYN-SAT", site_kind="satellite"),
        ])
        packet["requirements"].append(dict(packet["requirements"][0], requirement_id="SYN-RSAT", site_kind="satellite"))
        packet["documents"].append(dict(packet["documents"][0], document_id="SYN-DOUT", site_id="SYN-OUT"))
        result, _ = self.evaluate(packet)
        self.assertEqual([(row["site_id"], row["requirement_id"]) for row in result["outputs"]["requirement_matrix"]], [
            ("SYN-S", "SYN-R"), ("SYN-SAT", "SYN-RSAT"),
        ])
        self.assertEqual(self.evidence(result, "documents", "SYN-DOUT")["dispositions"], ["out-of-scope"])
        self.assertEqual(self.cell(result, "SYN-SAT", "SYN-RSAT")["reason_codes"], ["missing-document"])

    def test_missing_requirements_preserve_zero_count_site_and_unneeded_document(self):
        packet = self.packet()
        packet["requirements"] = []
        result, _ = self.evaluate(packet)
        self.assertEqual(result["outputs"]["requirement_matrix"], [])
        self.assertEqual(result["outputs"]["site_summary"][0]["required_count"], 0)
        self.assertEqual([item["code"] for item in result["exceptions"]], ["missing-requirements"])
        self.assertEqual(self.evidence(result, "documents", "SYN-D")["dispositions"], ["not-required"])

    def test_empty_population_is_completed_without_invented_requirements(self):
        packet = self.packet()
        for table in TABLES:
            packet[table] = []
        result, events = self.evaluate(packet)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["exceptions"], [])
        for key in ("requirement_matrix", "site_summary", "evidence_register", "draft_review_queue"):
            self.assertEqual(result["outputs"][key], [])
        self.assertEqual(len(events), 8)
        self.assertIs(result["outputs"]["human_review_required"], True)

    def test_unused_artifact_metadata_is_retained_without_downgrading_cell(self):
        packet = self.packet()
        packet["artifacts"].append(dict(packet["artifacts"][0], artifact_id="SYN-UNUSED", readability_attested=False))
        result, _ = self.evaluate(packet)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(self.evidence(result, "artifacts", "SYN-UNUSED")["dispositions"], ["unavailable-metadata", "unused"])

    def test_existing_task_asof_join_excludes_future_and_retains_multiple_ids(self):
        packet = self.packet()
        packet["documents"][0]["signature_recorded"] = False
        packet["open_review_tasks"] = [
            self.task("SYN-K1"), self.task("SYN-K2", opened="2024-02-28"),
            self.task("SYN-K3", opened="2024-03-01"),
        ]
        result, _ = self.evaluate(packet)
        queue = result["outputs"]["draft_review_queue"]
        self.assertEqual(len(queue), 1)
        self.assertEqual(queue[0]["existing_task_ids"], ["SYN-K1", "SYN-K2"])
        self.assertEqual(queue[0]["routing"], "existing-task")
        self.assertIsNone(queue[0]["draft_review_by"])
        self.assertIn("duplicate-open-tasks", [item["code"] for item in result["exceptions"]])
        self.assertEqual(self.evidence(result, "open_review_tasks", "SYN-K3")["dispositions"], ["future-task"])

    def test_conflicting_task_variants_block_routing_not_document_assessment(self):
        packet = self.packet()
        packet["documents"][0].update(signature_recorded=False, protocol_version=None)
        packet["open_review_tasks"] = [self.task(), self.task(reason="protocol-version-mismatch")]
        result, _ = self.evaluate(packet)
        self.assertEqual(self.cell(result)["reason_codes"], ["missing-signature-evidence", "protocol-version-mismatch"])
        self.assertTrue(all(row["routing"] == "blocked-ambiguous" for row in result["outputs"]["draft_review_queue"]))
        self.assertTrue(all(row["existing_task_ids"] == ["SYN-K"] for row in result["outputs"]["draft_review_queue"]))
        self.assertEqual(self.evidence(result, "open_review_tasks", "SYN-K")["dispositions"], ["conflicting-id", "quarantined", "task-linked"])

    def test_unmatched_asof_task_is_not_closed_or_silently_dropped(self):
        packet = self.packet()
        packet["open_review_tasks"] = [self.task(reason="expired")]
        result, _ = self.evaluate(packet)
        self.assertEqual(self.cell(result)["reason_codes"], [])
        self.assertEqual(result["outputs"]["draft_review_queue"], [])
        self.assertEqual([item["code"] for item in result["exceptions"]], ["unmatched-task"])
        self.assertEqual(self.evidence(result, "open_review_tasks", "SYN-K")["dispositions"], ["unmatched"])

    def test_missing_task_references_are_not_fuzzy_joined(self):
        packet = self.packet()
        packet["documents"][0]["signature_recorded"] = False
        packet["open_review_tasks"] = [dict(self.task(), site_id="SYN-UNKNOWN", requirement_id="SYN-UNKNOWN-R")]
        result, _ = self.evaluate(packet)
        self.assertEqual(result["outputs"]["draft_review_queue"][0]["routing"], "draft-new")
        refs = [item for item in result["exceptions"] if item["code"] == "unmatched-reference"]
        self.assertEqual({item["field"] for item in refs}, {"site_id", "requirement_id"})

    def test_zero_day_and_year_boundary_drafts_use_calendar_days(self):
        for as_of, days, due in (("2024-02-29", 0, "2024-02-29"), ("2024-12-31", 2, "2025-01-02")):
            with self.subTest(as_of=as_of, days=days):
                packet = self.packet()
                packet["as_of_date"] = as_of
                packet["policy"]["draft_review_days"] = days
                packet["documents"][0]["signature_recorded"] = False
                result, _ = self.evaluate(packet)
                self.assertEqual(result["outputs"]["draft_review_queue"][0]["draft_review_by"], due)

    def test_exact_row_and_grid_limits_allow_boundary_then_reject_excess(self):
        packet = self.packet()
        packet["policy"].update(max_rows_per_table=1, max_total_rows=5, max_derived_pairs=1)
        result, _ = self.evaluate(packet)
        self.assertEqual(result["status"], "completed")
        packet["documents"].append(copy.deepcopy(packet["documents"][0]))
        result = self.assert_rejected(packet, "documents")
        self.assertEqual([item["path"] for item in result["exceptions"]], ["documents", "policy.max_total_rows"])
        packet = self.packet()
        packet["policy"]["max_derived_pairs"] = 1
        packet["sites"].append(dict(packet["sites"][0], site_id="SYN-S2"))
        self.assert_rejected(packet, "policy.max_derived_pairs")

    def test_raw_limit_precedes_record_validation_and_counts_identical_copies(self):
        packet = self.packet()
        packet["policy"]["max_rows_per_table"] = 1
        packet["documents"] = [None, None]
        result = self.assert_rejected(packet, "documents")
        self.assertEqual(len(result["exceptions"]), 1)
        packet = self.packet()
        packet["policy"]["max_rows_per_table"] = 1000
        packet["documents"] *= 1001
        self.assert_rejected(packet, "documents")

    def test_policy_hard_ceilings_and_boolean_numeric_types_are_rejected(self):
        for field, values in {
            "warning_days": (True, -1, 366, "7", 7.0),
            "draft_review_days": (False, -1, 366),
            "max_rows_per_table": (0, 1001, True),
            "max_total_rows": (0, 5001, False),
            "max_derived_pairs": (0, 10001, True),
        }.items():
            for value in values:
                with self.subTest(field=field, value=value):
                    packet = self.packet()
                    packet["policy"][field] = value
                    self.assert_rejected(packet, f"policy.{field}")

    def test_record_types_dates_and_identifiers_are_strict(self):
        for table, field, value in (
            ("documents", "version_seq", True),
            ("documents", "version_seq", 1.0),
            ("documents", "version_seq", "1"),
            ("documents", "version_seq", 0),
            ("documents", "protocol_version", False),
            ("documents", "signature_recorded", 1),
            ("documents", "issued_on", "2023-02-29"),
            ("documents", "recorded_on", "2024-2-29"),
            ("documents", "expires_on", "2024-02-29T00:00:00Z"),
            ("documents", "document_id", "NOT-SYNTHETIC"),
            ("sites", "site_kind", "Research"),
            ("sites", "in_scope", "true"),
            ("artifacts", "source_ref", "https://example.invalid"),
            ("artifacts", "readability_attested", None),
            ("requirements", "refresh_days", 0),
            ("requirements", "refresh_days", True),
            ("requirements", "refresh_days", 3651),
            ("trials", "required_protocol_version", 1000001),
        ):
            with self.subTest(table=table, field=field, value=value):
                packet = self.packet()
                packet[table][0][field] = value
                self.assert_rejected(packet, f"{table}[0].{field}")
        packet = self.packet()
        packet["open_review_tasks"] = [self.task(reason="approve-site")]
        self.assert_rejected(packet, "open_review_tasks[0].reason_code")

    def test_root_policy_and_row_shapes_reject_unsupported_fields(self):
        packet = self.packet()
        packet["extra"] = True
        self.assert_rejected(packet, "packet")
        packet = self.packet()
        packet["policy"]["extra"] = True
        self.assert_rejected(packet, "policy")
        packet = self.packet()
        del packet["documents"][0]["issued_on"]
        packet["documents"][0]["version_seq"] = True
        result = self.assert_rejected(packet, "documents[0]")
        self.assertEqual(len(result["exceptions"]), 1)
        packet = self.packet()
        packet["sites"] = {}
        self.assert_rejected(packet, "sites")
        packet = self.packet()
        packet["schema_version"] = True
        self.assert_rejected(packet, "schema_version")
        self.assert_rejected([], "packet")

    def test_validation_collects_sorts_and_displays_bounded_errors(self):
        packet = self.packet()
        packet["documents"] = [
            dict(packet["documents"][0], document_id=f"SYN-D{index}", version_seq=False)
            for index in range(10)
        ]
        result, events = self.baseline.solve(packet)
        self.assertEqual(result["status"], "rejected")
        self.assertEqual(len(result["exceptions"]), 10)
        self.assertEqual([item["path"] for item in result["exceptions"]], sorted(item["path"] for item in result["exceptions"]))
        table = events[-1]["tables"][0]
        self.assertEqual((table["total_rows"], len(table["rows"])), (10, 8))
        self.assertEqual(table["highlight_rows"], list(range(8)))

    def test_date_addition_overflow_is_business_rejection_not_crash(self):
        packet = self.packet()
        packet["as_of_date"] = "9999-12-31"
        self.assert_rejected(packet, "as_of_date")
        packet["policy"]["draft_review_days"] = 0
        packet["documents"][0].update(issued_on="9999-12-31", effective_on="9999-12-31", recorded_on="9999-12-31")
        packet["requirements"][0]["refresh_days"] = 1
        self.assert_rejected(packet, "documents[0].issued_on")
        packet["requirements"][0]["refresh_days"] = None
        result, _ = self.evaluate(packet)
        self.assertEqual(result["status"], "completed")

    def test_future_refresh_overflow_is_detected_before_selection(self):
        packet = self.packet()
        packet["documents"][0].update(issued_on="9999-12-31", effective_on="9999-12-31", recorded_on="9999-12-31")
        packet["requirements"][0]["refresh_days"] = 1
        self.assert_rejected(packet, "documents[0].issued_on")

    def test_unexpected_implementation_errors_are_not_success_envelopes(self):
        with mock.patch.object(self.baseline, "_expiry", side_effect=RuntimeError("deliberate internal test failure")):
            with self.assertRaisesRegex(RuntimeError, "deliberate internal test failure"):
                self.baseline.solve(self.packet())

    def cli_workspace(self):
        workspace = ROOT / "validation" / ("unit-cli-" + uuid.uuid4().hex)
        workspace.mkdir()
        self.addCleanup(shutil.rmtree, workspace)
        return workspace

    def run_cli(self, input_path, result_path, trace_path):
        return subprocess.run(
            [
                sys.executable, "-B", "-I", str(ROOT / "baseline.py"),
                "--input", str(input_path), "--output", str(result_path), "--trace", str(trace_path),
            ],
            cwd=ROOT, stdin=subprocess.DEVNULL, capture_output=True, text=True,
            encoding="utf-8", timeout=30, check=False,
        )

    def test_shared_cli_rejects_invalid_json_bytes_without_success_artifacts(self):
        workspace = self.cli_workspace()
        for index, content in enumerate((
            b"{", b'{"schema_version":1,"schema_version":1}', b'{"value":NaN}', b"[]",
        )):
            with self.subTest(content=content):
                source = workspace / f"invalid-{index}.json"
                result = workspace / f"result-{index}.json"
                trace = workspace / f"trace-{index}.json"
                source.write_bytes(content)
                process = self.run_cli(source, result, trace)
                self.assertNotEqual(process.returncode, 0)
                self.assertIn("Baseline failed:", process.stderr)
                self.assertFalse(result.exists())
                self.assertFalse(trace.exists())
                self.assertEqual(source.read_bytes(), content)

    def test_shared_cli_business_rejection_exits_zero_with_validation_trace(self):
        workspace = self.cli_workspace()
        result_path, trace_path = workspace / "result.json", workspace / "trace.json"
        process = self.run_cli(ROOT / "mock-data" / "negative-malformed.json", result_path, trace_path)
        self.assertEqual(process.returncode, 0, process.stderr)
        result = json.loads(result_path.read_text(encoding="utf-8"))
        trace = json.loads(trace_path.read_text(encoding="utf-8"))
        self.assertEqual(compare_json(self.read_case("negative-malformed", "expected"), result), [])
        self.assertEqual([event["kind"] for event in trace["events"]], ["input", "validation"])
        self.assertEqual(trace["provenance"], "synthetic-local-baseline")

    def test_shared_cli_refuses_overwriting_input(self):
        workspace = self.cli_workspace()
        source = workspace / "input.json"
        content = json.dumps(self.packet()).encode("utf-8")
        source.write_bytes(content)
        trace = workspace / "trace.json"
        process = self.run_cli(source, source, trace)
        self.assertNotEqual(process.returncode, 0)
        self.assertEqual(source.read_bytes(), content)
        self.assertFalse(trace.exists())


if __name__ == "__main__":
    unittest.main()
