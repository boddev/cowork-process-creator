"""Read-only retail pack integration and artifact-boundary checks."""
from __future__ import annotations

import unittest
from pathlib import Path

from scenarios._shared.common import load_json
from scenarios._shared.contract import load_scenario
from scenarios._shared.pipeline import check_case_evidence


RETAIL = Path(__file__).resolve().parents[1] / "retail"
SLUGS = (
    "store-replenishment-proposal",
    "returns-refund-reconciliation",
    "promotion-price-audit",
)


class RetailPackTests(unittest.TestCase):
    def test_sources_and_procedures_preserve_approved_research(self):
        research = load_json(RETAIL / "research.json")
        sources = {item["url"]: item for item in research["sources"]}
        families = set()
        for slug in SLUGS:
            scenario = load_scenario(RETAIL / slug)
            families.add(scenario.manifest["workflow_family"])
            procedure = scenario.file("HOW_TO.md").read_text(encoding="utf-8")
            for source in scenario.sources["sources"]:
                with self.subTest(scenario=scenario.id, source=source["id"]):
                    self.assertIn(source["url"], sources)
                    self.assertEqual(source["accessed"], sources[source["url"]]["accessed"])
                    self.assertIn(source["url"], procedure)
            self.assertEqual(scenario.connections["connections"], [])
            self.assertEqual(scenario.connections["mode"], "mock-exports-only")
            self.assertTrue(scenario.manifest["sample_policy"]["no_live_actions"])
        self.assertEqual(len(families), 3)

    def test_every_case_has_fresh_local_not_native_evidence(self):
        for slug in SLUGS:
            scenario = load_scenario(RETAIL / slug)
            for case in scenario.cases:
                with self.subTest(scenario=scenario.id, case=case["id"]):
                    report = check_case_evidence(scenario, case)
                    self.assertEqual(report["state"], "baseline_pass")
                    self.assertEqual(report["native"]["creation"], "native_creation_blocked")
                    self.assertEqual(report["native"]["installation"], "not_run")
                    self.assertEqual(report["native"]["independent_invocation"], "not_run")
                    self.assertEqual(report["native"]["comparison"], "not_run")

    def test_no_incidental_os_cache_files_in_scenario_folders(self):
        for slug in SLUGS:
            root = RETAIL / slug
            for path in root.rglob("*"):
                if path.is_file():
                    with self.subTest(path=str(path.relative_to(root))):
                        self.assertNotIn("%SystemDrive%", path.parts)
                        self.assertNotEqual(path.suffix.lower(), ".db")


if __name__ == "__main__":
    unittest.main()
