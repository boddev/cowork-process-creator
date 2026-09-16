"""Cross-scenario contract and provenance checks for the owned HLS pack."""
from __future__ import annotations

import copy
import importlib.util
import sys
import unittest
from pathlib import Path

from scenarios._shared.common import file_digest, load_json
from scenarios._shared.comparison import compare_json
from scenarios._shared.contract import load_scenario, validate_result, validate_trace
from scenarios._shared.pipeline import golden_lock


ROOT = Path(__file__).resolve().parents[1] / "health-life-sciences"
SCENARIOS = (
    ("hls-01", "site-essential-document-review"),
    ("hls-02", "cold-chain-excursion-review"),
    ("hls-03", "specimen-accession-reconciliation"),
)


class HealthLifeSciencesPackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.prepared = []
        for scenario_id, directory in SCENARIOS:
            scenario = load_scenario(ROOT / directory)
            golden_lock(scenario)
            name = "hls_pack_" + scenario_id.replace("-", "_")
            specification = importlib.util.spec_from_file_location(name, scenario.file("baseline.py"))
            module = importlib.util.module_from_spec(specification)
            sys.modules[name] = module
            specification.loader.exec_module(module)
            cases = []
            for case in scenario.cases:
                payload = load_json(scenario.file(case["input"]))
                before = copy.deepcopy(payload)
                result, events = module.solve(payload)
                cases.append((case, payload, before, result, events))
            cls.prepared.append((scenario_id, scenario, cases))

    def test_three_contracts_fifteen_distinct_cases_and_families(self):
        families = set()
        for scenario_id, scenario, _ in self.prepared:
            with self.subTest(scenario=scenario_id):
                self.assertEqual(scenario_id, scenario.id)
                self.assertEqual("health-life-sciences", scenario.manifest["industry"])
                self.assertGreaterEqual(len(scenario.cases), 5)
                self.assertEqual("independent-manual-derivation", scenario.manifest["golden_provenance"]["method"])
                self.assertEqual([], scenario.connections["connections"])
                families.add(scenario.manifest["workflow_family"])
        self.assertEqual(3, len(families))

    def test_all_manual_goldens_match_actual_pure_results_and_stages(self):
        for scenario_id, scenario, cases in self.prepared:
            for case, payload, before, result, events in cases:
                with self.subTest(scenario=scenario_id, case=case["id"]):
                    self.assertEqual(before, payload)
                    validate_result(result)
                    self.assertEqual([], compare_json(load_json(scenario.file(case["expected"])), result))
                    digest = file_digest(scenario.file(case["input"]))
                    validate_trace({
                        "schema_version": 1,
                        "provenance": "synthetic-local-baseline",
                        "scenario_id": scenario_id,
                        "input_sha256": digest,
                        "events": [dict(event, sequence=index) for index, event in enumerate(events, 1)],
                    }, scenario, case, digest)
            golden_lock(scenario)

    def test_public_procedures_do_not_reveal_private_cases_or_oracles(self):
        for scenario_id, scenario, _ in self.prepared:
            with self.subTest(scenario=scenario_id):
                text = scenario.file("HOW_TO.md").read_text(encoding="utf-8")
                for withheld in (
                    "holdout-a", "holdout-b", "negative-malformed",
                    "negative-contradictory", "expected/", "expected\\",
                    "golden-lock.json",
                ):
                    self.assertNotIn(withheld, text)
                for envelope_key in ("schema_version", "status", "outputs", "exceptions"):
                    self.assertIn(envelope_key, text)
                self.assertIn("blocked", text.lower())
                self.assertIn("synthetic", text.lower())

    def test_both_holdouts_change_cardinality_and_time_or_policy(self):
        for scenario_id, scenario, _ in self.prepared:
            demo = load_json(scenario.file(scenario.case("demo")["input"]))
            counts = {name: len(value) for name, value in demo.items() if isinstance(value, list)}
            for case in scenario.cases:
                if case["kind"] != "holdout":
                    continue
                with self.subTest(scenario=scenario_id, case=case["id"]):
                    payload = load_json(scenario.file(case["input"]))
                    changed_counts = {name: len(value) for name, value in payload.items() if isinstance(value, list)}
                    self.assertNotEqual(counts, changed_counts)
                    keys = {name for name in set(demo) | set(payload) if name in (
                        "as_of", "as_of_date", "window_start", "policy",
                    )}
                    self.assertTrue(any(demo.get(name) != payload.get(name) for name in keys))

    def test_outputs_never_authorize_clinical_or_physical_actions(self):
        forbidden = {
            "released", "safe_to_use", "discard_authorized", "specimen_accepted",
            "specimen_rejected", "test_authorized", "enrollment_approved",
            "site_activated", "regulatory_compliant", "physical_quarantine_completed",
        }

        def inspect(value):
            if isinstance(value, dict):
                self.assertFalse(forbidden & value.keys())
                for item in value.values():
                    inspect(item)
            elif isinstance(value, list):
                for item in value:
                    inspect(item)

        for scenario_id, _, cases in self.prepared:
            for case, _, _, result, _ in cases:
                with self.subTest(scenario=scenario_id, case=case["id"]):
                    inspect(result["outputs"])


if __name__ == "__main__":
    unittest.main()
