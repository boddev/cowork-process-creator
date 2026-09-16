import unittest
from pathlib import Path
from types import SimpleNamespace

from scenarios._shared.common import ContractError
from scenarios._shared.contract import load_scenario
from scenarios._shared.reporting import business_industry, build_catalog, coverage, write_reports
from scenarios.tests.fixtures import make_scenario
from scenarios.tests.fixtures import dump, temporary_directory


class IndustryReportingTests(unittest.TestCase):
    def test_cross_pack_labels_are_derived_from_research_not_invented_schema_fields(self):
        with temporary_directory() as directory:
            sector = Path(directory) / "cross-industry"
            sector.mkdir()
            dump(sector / "research.json", {"candidates": [
                {"id": "cross-industry-01", "industry": "logistics"},
                {"id": "cross-industry-02", "industry": "energy-utilities"},
                {"id": "cross-industry-03", "industry": "professional-services"},
            ]})
            for number, expected in ((1, "logistics"), (2, "energy-utilities"), (3, "professional-services")):
                scenario = SimpleNamespace(root=sector / "scenario", id=f"cross-industry-0{number}", manifest={"industry": "cross-industry"})
                self.assertEqual(business_industry(scenario), expected)
            scenario.id = "unknown"
            with self.assertRaises(ContractError):
                business_industry(scenario)

    def test_standard_industry_labels_do_not_require_a_research_override(self):
        scenario = SimpleNamespace(manifest={"industry": "manufacturing"})
        self.assertEqual(business_industry(scenario), "manufacturing")
        metrics = coverage([])
        self.assertEqual(metrics["directory_pack_count"], 0)
        self.assertEqual(metrics["business_industry_count"], 0)

    def test_single_collection_contains_the_complete_original_procedure(self):
        with temporary_directory() as directory:
            root = Path(directory) / "scenarios"
            scenario = load_scenario(make_scenario(root))
            catalog = build_catalog([scenario])
            write_reports(root, Path(directory) / "output", catalog)
            collected = (root / "ALL_SCENARIOS_HOW_TO.md").read_text(encoding="utf-8")
            original = scenario.file("HOW_TO.md").read_text(encoding="utf-8").strip()
            self.assertIn(original, collected)
            self.assertIn(f'id="{scenario.id}"', collected)
            self.assertIn("No native Creator", collected)


if __name__ == "__main__":
    unittest.main()
