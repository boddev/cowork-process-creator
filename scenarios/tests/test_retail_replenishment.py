"""Independent arithmetic, conservation and changed-input replenishment checks."""
from __future__ import annotations

import copy
import importlib.util
import random
import unittest
from pathlib import Path

from scenarios._shared.common import load_json
from scenarios._shared.contract import load_scenario
from scenarios._shared.pipeline import check_case_evidence, golden_lock, run_case
from scenarios.tests.fixtures import copy_scenario, temporary_directory


ROOT = Path(__file__).resolve().parents[1] / "retail" / "store-replenishment-proposal"


class ReplenishmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scenario = load_scenario(ROOT)
        golden_lock(cls.scenario)
        spec = importlib.util.spec_from_file_location("retail_replenishment_baseline", ROOT / "baseline.py")
        cls.baseline = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.baseline)

    def payload(self, case_id="demo"):
        return load_json(ROOT / "mock-data" / f"{case_id}.json")

    @staticmethod
    def table(payload, role):
        return payload["files"][payload["policy"]["source_files"][role]]

    def small_payload(self):
        payload = self.payload("negative-malformed")
        self.table(payload, "routes")[0]["case_pack"] = 1
        return payload

    def test_00_all_independent_cases_and_evidence(self):
        with temporary_directory() as temporary:
            scenario = load_scenario(copy_scenario(ROOT, Path(temporary) / "scenarios"))
            for case in scenario.cases:
                with self.subTest(case=case["id"]):
                    report = run_case(scenario, case, replace=True)
                    self.assertEqual(report["state"], "baseline_pass", report["errors"] + report["local"]["differences"])
                    self.assertEqual(check_case_evidence(scenario, case)["state"], "baseline_pass")

    def test_demo_arithmetic_and_conservation(self):
        result, events = self.baseline.solve(self.payload())
        output = result["outputs"]
        rows = output["proposals"]
        self.assertEqual([r["raw_required_units"] for r in rows], [4, 6, 8])
        self.assertEqual([r["proposed_units"] for r in rows], [6, 3, 4])
        self.assertEqual([r["closing_units"] for r in rows], [6, 1, 0])
        self.assertEqual([r["remaining_units"] for r in output["dc_stock_controls"]], [0, 36])
        self.assertEqual(output["review_packet"]["totals"]["lost_units"], 4)
        self.assertEqual(len(result["exceptions"]), 7)
        self.assertEqual(len(events), 8)
        self.assertEqual({e["kind"] for e in events}, {"input", "validation", "join", "decision", "exception", "output"})
        for row in output["daily_projection"]:
            self.assertEqual(row["opening_units"] + row["inbound_units"] + row["proposed_units"] - row["fulfilled_units"], row["closing_units"])
            self.assertEqual(row["fulfilled_units"] + row["lost_units"], row["demand_units"])
            self.assertGreaterEqual(row["closing_units"], 0)
        for row in rows:
            self.assertEqual(row["proposed_units"] % row["case_pack"], 0)
            self.assertLessEqual(row["proposed_units"], row["requested_units"])
        for row in output["dc_capacity_controls"]:
            self.assertEqual(row["opening_case_capacity"] - row["proposed_cases"], row["remaining_case_capacity"])

    def test_valid_source_permutations_preserve_result_and_trace(self):
        payload = self.payload()
        original = self.baseline.solve(payload)
        generator = random.Random(193)
        for _ in range(8):
            changed = copy.deepcopy(payload)
            for table in changed["files"].values():
                generator.shuffle(table)
            self.assertEqual(self.baseline.solve(changed), original)

    def test_logical_filename_remapping_preserves_result(self):
        payload = self.payload()
        original = self.baseline.solve(payload)
        changed = copy.deepcopy(payload)
        files = {}
        for index, role in enumerate(changed["policy"]["source_files"]):
            old_name = changed["policy"]["source_files"][role]
            new_name = f"renamed-{index}.json"
            changed["policy"]["source_files"][role] = new_name
            files[new_name] = changed["files"][old_name]
        changed["files"] = files
        self.assertEqual(self.baseline.solve(changed), original)

    def test_input_is_not_mutated(self):
        for case in self.scenario.cases:
            payload = self.payload(case["id"])
            original = copy.deepcopy(payload)
            self.baseline.solve(payload)
            self.assertEqual(payload, original)

    def test_early_deficit_not_hidden_by_late_receipt(self):
        payload = self.small_payload()
        payload["policy"]["review_days"] = 2
        self.table(payload, "store_stock")[0]["on_hand_units"] = 0
        demand = self.table(payload, "demand")
        demand[0]["units"] = 5
        demand.append(dict(demand[0], demand_on="2099-01-02", units=1))
        self.table(payload, "capacity")[0]["remaining_case_capacity"] = 10
        self.table(payload, "inbound").append({
            "receipt_id": "SYN-EARLY-DEFICIT", "store_id": "SYN-STORE-Z", "sku": "SYN-SKU-Z",
            "eta": "2099-01-02", "status": "in-transit", "remaining_units": 6,
        })
        result, _ = self.baseline.solve(payload)
        proposal = result["outputs"]["proposals"][0]
        self.assertEqual(proposal["raw_required_units"], 5)
        self.assertEqual(proposal["proposed_units"], 5)
        self.assertEqual(proposal["post_arrival_lost_units"], 0)
        self.assertEqual(proposal["closing_units"], 5)

    def test_partial_disabled_leaves_capacity_for_later_candidate(self):
        payload = self.small_payload()
        payload["policy"]["partial_cases_allowed"] = False
        route = self.table(payload, "routes")[0]
        route["case_pack"] = 4
        self.table(payload, "demand")[0]["units"] = 10
        self.table(payload, "capacity")[0]["remaining_case_capacity"] = 1
        self.table(payload, "routes").append(dict(route, store_id="SYN-STORE-Y", priority=2))
        self.table(payload, "store_stock").append(dict(self.table(payload, "store_stock")[0], store_id="SYN-STORE-Y", on_hand_units=0))
        self.table(payload, "demand").append(dict(self.table(payload, "demand")[0], store_id="SYN-STORE-Y", units=4))
        result, _ = self.baseline.solve(payload)
        proposals = {r["store_id"]: r for r in result["outputs"]["proposals"]}
        self.assertEqual(proposals["SYN-STORE-Z"]["proposed_units"], 0)
        self.assertEqual(proposals["SYN-STORE-Z"]["limits"], ["dc-capacity", "partial-disabled"])
        self.assertEqual(proposals["SYN-STORE-Y"]["proposed_units"], 4)
        self.assertEqual([r["store_id"] for r in result["outputs"]["allocation_ledger"]], ["SYN-STORE-Z", "SYN-STORE-Y"])
        self.assertEqual(result["outputs"]["dc_stock_controls"][0]["remaining_units"], 6)

    def test_duplicate_keys_in_all_roles_reject(self):
        for role in self.baseline.ROLES:
            payload = self.payload()
            rows = self.table(payload, role)
            rows.append(copy.deepcopy(rows[0]))
            with self.subTest(role=role):
                result, _ = self.baseline.solve(payload)
                self.assertEqual(result["status"], "rejected")
                self.assertEqual(result["exceptions"][0]["code"], "duplicate-key")
                self.assertEqual(result["outputs"], {})

    def test_invalid_quantities_do_not_coerce(self):
        for value in (True, False, 1.5, "2", -1, None):
            payload = self.small_payload()
            self.table(payload, "demand")[0]["units"] = value
            with self.subTest(value=value):
                result, _ = self.baseline.solve(payload)
                self.assertEqual(result["status"], "rejected")
                self.assertEqual(result["exceptions"][0]["code"], "invalid-record")

    def test_missing_or_extra_demand_is_explicit(self):
        payload = self.payload()
        self.table(payload, "demand").pop()
        result, _ = self.baseline.solve(payload)
        self.assertEqual(result["exceptions"][0]["code"], "missing-demand")
        payload = self.small_payload()
        demand = self.table(payload, "demand")
        demand.append(dict(demand[0], demand_on="2099-01-02"))
        result, _ = self.baseline.solve(payload)
        self.assertEqual(result["exceptions"][0]["code"], "out-of-window-demand")

    def test_closed_receipt_cannot_duplicate_stock(self):
        payload = self.small_payload()
        self.table(payload, "inbound").append({
            "receipt_id": "SYN-RECEIVED", "store_id": "SYN-STORE-Z", "sku": "SYN-SKU-Z",
            "eta": "2098-12-31", "status": "received", "remaining_units": 2,
        })
        result, _ = self.baseline.solve(payload)
        self.assertEqual(result["status"], "rejected")
        self.assertEqual(result["exceptions"][0]["code"], "contradictory-receipt")

    def test_overdue_pair_does_not_debit_shared_supply(self):
        payload = self.payload("negative-overdue-inbound")
        result, _ = self.baseline.solve(payload)
        output = result["outputs"]
        self.assertEqual(output["proposals"][0]["status"], "blocked")
        self.assertIsNone(output["proposals"][0]["requested_units"])
        self.assertEqual(output["dc_stock_controls"][0]["remaining_units"], 10)
        self.assertEqual(output["dc_capacity_controls"][0]["remaining_case_capacity"], 2)
        self.assertEqual(output["daily_projection"], [])
        self.assertEqual(output["allocation_ledger"], [])
        self.assertEqual(output["review_packet"]["totals"]["blocked_pairs"], 1)

    def test_leap_day_is_a_real_coverage_day(self):
        payload = self.small_payload()
        payload["policy"].update(as_of="2096-02-28", review_days=2)
        route = self.table(payload, "routes")[0]
        route["lead_days"] = 1
        for role in ("store_stock", "dc_stock"):
            self.table(payload, role)[0]["snapshot_on"] = "2096-02-28"
        self.table(payload, "capacity")[0].update(dispatch_on="2096-02-28", remaining_case_capacity=10)
        demand = self.table(payload, "demand")
        demand[0]["demand_on"] = "2096-02-28"
        demand.extend([dict(demand[0], demand_on="2096-02-29"), dict(demand[0], demand_on="2096-03-01")])
        result, _ = self.baseline.solve(payload)
        self.assertNotEqual(result["status"], "rejected")
        self.assertEqual(result["outputs"]["proposals"][0]["arrival_on"], "2096-02-29")
        self.assertEqual([r["day"] for r in result["outputs"]["daily_projection"]], ["2096-02-28", "2096-02-29", "2096-03-01"])

    def test_invalid_dates_horizons_and_filename_keys_reject(self):
        changes = (
            ("as_of", "2099-02-29"),
            ("as_of", "9999-12-31"),
            ("review_days", 367),
            ("review_days", True),
            ("partial_cases_allowed", "yes"),
        )
        for field, value in changes:
            payload = self.payload()
            payload["policy"][field] = value
            with self.subTest(field=field, value=value):
                self.assertEqual(self.baseline.solve(payload)[0]["status"], "rejected")
        for name in ("..\\outside.json", "../outside.json", "https://example.test/data.json"):
            payload = self.small_payload()
            payload["policy"]["source_files"]["demand"] = name
            self.assertEqual(self.baseline.solve(payload)[0]["status"], "rejected")

    def test_stale_capacity_and_missing_dc_evidence_reject(self):
        payload = self.small_payload()
        self.table(payload, "capacity")[0]["dispatch_on"] = "2099-01-02"
        self.assertEqual(self.baseline.solve(payload)[0]["exceptions"][0]["code"], "capacity-date-mismatch")
        payload = self.small_payload()
        self.table(payload, "routes")[0]["dc_id"] = "SYN-DC-MISSING"
        self.assertEqual(self.baseline.solve(payload)[0]["exceptions"][0]["code"], "missing-dc-evidence")

    def test_added_unused_dc_rows_are_reported(self):
        payload = self.small_payload()
        self.table(payload, "dc_stock").append(dict(self.table(payload, "dc_stock")[0], dc_id="SYN-DC-UNUSED", on_hand_units=17))
        self.table(payload, "capacity").append(dict(self.table(payload, "capacity")[0], dc_id="SYN-DC-UNUSED", remaining_case_capacity=5))
        result, _ = self.baseline.solve(payload)
        stock = {r["dc_id"]: r for r in result["outputs"]["dc_stock_controls"]}
        capacity = {r["dc_id"]: r for r in result["outputs"]["dc_capacity_controls"]}
        self.assertEqual(stock["SYN-DC-UNUSED"]["remaining_units"], 17)
        self.assertEqual(capacity["SYN-DC-UNUSED"]["remaining_case_capacity"], 5)


if __name__ == "__main__":
    unittest.main()
