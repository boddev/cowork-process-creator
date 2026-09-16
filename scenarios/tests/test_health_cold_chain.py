"""Targeted stdlib checks for the synthetic cold-chain evidence workflow."""
from __future__ import annotations

import copy
import importlib.util
import unittest
from pathlib import Path

from scenarios._shared.common import file_digest, load_json
from scenarios._shared.comparison import compare_json
from scenarios._shared.contract import load_scenario, validate_result, validate_trace
from scenarios._shared.pipeline import golden_lock


ROOT = Path(__file__).resolve().parents[1] / "health-life-sciences" / "cold-chain-excursion-review"
SPEC = importlib.util.spec_from_file_location("health_cold_chain_baseline", ROOT / "baseline.py")
BASELINE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BASELINE)


class ColdChainTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scenario = load_scenario(ROOT)
        golden_lock(cls.scenario)

    def payload(self, case="demo"):
        return load_json(ROOT / "mock-data" / f"{case}.json")

    def solve(self, payload):
        before = copy.deepcopy(payload)
        result, events = BASELINE.solve(payload)
        self.assertEqual(before, payload, "The solver must not change supplied evidence.")
        validate_result(result)
        return result, events

    def lot(self, result, lot_id="SYN-LOT-A"):
        return next(row for row in result["outputs"]["lot_review"] if row["lot_id"] == lot_id)

    def test_five_complete_manual_goldens_and_actual_stage_contract(self):
        for case in self.scenario.cases:
            with self.subTest(case=case["id"]):
                result, events = self.solve(load_json(ROOT / case["input"]))
                self.assertEqual([], compare_json(load_json(ROOT / case["expected"]), result))
                digest = file_digest(ROOT / case["input"])
                validate_trace({
                    "schema_version": 1, "provenance": "synthetic-local-baseline",
                    "scenario_id": self.scenario.id, "input_sha256": digest,
                    "events": [dict(item, sequence=index) for index, item in enumerate(events, 1)],
                }, self.scenario, case, digest)

    def test_reversing_input_row_order_preserves_all_results(self):
        for case in ("demo", "holdout-a", "holdout-b", "negative-contradictory"):
            with self.subTest(case=case):
                payload = self.payload(case)
                first, _ = self.solve(payload)
                for value in payload.values():
                    if isinstance(value, list):
                        value.reverse()
                second, _ = self.solve(payload)
                self.assertEqual(first, second)

    def test_gap_is_wholly_unknown_without_partial_bridge(self):
        result, _ = self.solve(self.payload("holdout-a"))
        lot = self.lot(result, "SYN-LOT-U")
        self.assertEqual((1200, 300, 900, 300), tuple(lot[k] for k in (
            "occupied_seconds", "covered_seconds", "unknown_seconds", "modeled_outside_seconds",
        )))
        self.assertEqual(0, self.lot(result, "SYN-LOT-V")["modeled_outside_seconds"])
        self.assertEqual(900, self.lot(result, "SYN-LOT-V")["unknown_seconds"])

    def test_calibration_end_is_exclusive_and_no_release_from_note(self):
        result, _ = self.solve(self.payload("holdout-b"))
        lot = self.lot(result, "SYN-LOT-M")
        self.assertEqual(600, lot["covered_seconds"])
        self.assertEqual(600, lot["unknown_seconds"])
        self.assertEqual(["missing-calibration", "outside-band"], lot["reason_codes"])
        self.assertFalse(result["outputs"]["physical_actions_performed"])
        self.assertTrue(result["outputs"]["quality_disposition_required"])
        self.assertEqual("request-quality-review", result["outputs"]["draft_quality_requests"][0]["action"])

    def test_missing_profile_is_null_not_default_band(self):
        result, _ = self.solve(self.payload("holdout-b"))
        lot = self.lot(result, "SYN-LOT-N")
        self.assertIsNone(lot["modeled_outside_seconds"])
        self.assertEqual(1200, lot["unknown_seconds"])
        self.assertEqual(["missing-profile"], lot["reason_codes"])

    def test_missing_calibration_preserves_outside_point_observation(self):
        payload = self.payload()
        payload["calibrations"] = [row for row in payload["calibrations"] if row["sensor_id"] != "SYN-SENSOR-R"]
        result, _ = self.solve(payload)
        lot = self.lot(result)
        self.assertEqual((0, 1800, 0), (lot["covered_seconds"], lot["unknown_seconds"], lot["modeled_outside_seconds"]))
        self.assertEqual(["SYN-R10", "SYN-R15"], lot["observed_outside_reading_ids"])
        self.assertEqual(["missing-calibration", "outside-band"], lot["reason_codes"])

    def test_missing_assignment_is_not_normal(self):
        payload = self.payload()
        payload["sensor_assignments"] = [row for row in payload["sensor_assignments"] if row["unit_id"] != "SYN-UNIT-R"]
        result, _ = self.solve(payload)
        self.assertEqual(["missing-assignment"], self.lot(result)["reason_codes"])
        self.assertEqual(1800, self.lot(result)["unknown_seconds"])

    def test_unknown_placement_has_no_zero_exposure_claim(self):
        payload = self.payload()
        payload["placements"] = [row for row in payload["placements"] if row["lot_id"] != "SYN-LOT-A"]
        result, _ = self.solve(payload)
        lot = self.lot(result)
        self.assertEqual(["missing-placement"], lot["reason_codes"])
        self.assertIsNone(lot["modeled_outside_seconds"])

    def test_conflicting_quantity_is_not_arbitrarily_summed(self):
        payload = self.payload()
        conflicting = dict(payload["inventory"][0], quantity_units=11)
        payload["inventory"].append(conflicting)
        result, _ = self.solve(payload)
        lot = self.lot(result)
        self.assertIsNone(lot["quantity_units"])
        self.assertIsNone(lot["modeled_outside_seconds"])
        self.assertIsNone(result["outputs"]["inventory_summary"]["review_units"])
        self.assertEqual(["conflicting-evidence"], lot["reason_codes"])

    def test_overlapping_placements_count_union_not_sum(self):
        result, _ = self.solve(self.payload("negative-contradictory"))
        lot = self.lot(result, "SYN-LOT-X")
        self.assertEqual(1200, lot["occupied_seconds"])
        self.assertIsNone(lot["modeled_outside_seconds"])
        self.assertEqual([], lot["observed_outside_reading_ids"])
        self.assertEqual(1200, self.lot(result, "SYN-LOT-Y")["covered_seconds"])

    def test_same_time_different_value_conflict_without_placement_overlap(self):
        payload = self.payload()
        payload["readings"].append(dict(payload["readings"][0], reading_id="SYN-CONFLICT", temperature_tenths_c=999))
        result, _ = self.solve(payload)
        self.assertEqual(["conflicting-evidence"], self.lot(result)["reason_codes"])
        self.assertEqual(["outside-band"], self.lot(result, "SYN-LOT-B")["reason_codes"])
        self.assertIsNone(self.lot(result)["modeled_outside_seconds"])

    def test_same_time_equal_readings_do_not_multiply_duration(self):
        payload = self.payload()
        payload["readings"].append(dict(payload["readings"][2], reading_id="SYN-R10-COPY"))
        result, _ = self.solve(payload)
        self.assertEqual(600, self.lot(result)["modeled_outside_seconds"])
        self.assertEqual(["SYN-R10", "SYN-R10-COPY", "SYN-R15"], self.lot(result)["observed_outside_reading_ids"])

    def test_window_end_point_does_not_flag_occupancy(self):
        payload = self.payload()
        payload["readings"][6]["temperature_tenths_c"] = 999
        result, _ = self.solve(payload)
        self.assertEqual(["SYN-R10", "SYN-R15"], self.lot(result)["observed_outside_reading_ids"])
        self.assertEqual(90, self.lot(result)["temperature_max_tenths_c"])

    def test_predecessor_supports_partial_first_interval(self):
        payload = self.payload()
        payload["window_start"] = "2026-09-14T09:02:00Z"
        result, _ = self.solve(payload)
        lot = self.lot(result)
        self.assertEqual(1680, lot["occupied_seconds"])
        self.assertEqual(1680, lot["covered_seconds"])
        self.assertEqual(600, lot["modeled_outside_seconds"])
        first = result["outputs"]["interval_ledger"][0]
        self.assertEqual(180, first["overlap_seconds"])
        self.assertEqual(["SYN-R00"], first["reading_ids"])

    def test_future_recorded_certificate_cannot_repair_coverage(self):
        payload = self.payload()
        payload["calibrations"][0]["recorded_at"] = "2026-09-15T00:00:00Z"
        result, _ = self.solve(payload)
        self.assertEqual(1800, self.lot(result)["unknown_seconds"])
        self.assertIn("future-evidence", [row["code"] for row in result["exceptions"]])

    def test_future_primary_variant_cannot_change_as_of_temperature(self):
        payload = self.payload()
        payload["readings"].append(dict(payload["readings"][2], observed_at="2026-09-15T09:10:00Z", temperature_tenths_c=999))
        result, _ = self.solve(payload)
        self.assertEqual(600, self.lot(result)["modeled_outside_seconds"])
        self.assertEqual(["outside-band"], self.lot(result)["reason_codes"])
        self.assertIn("conflicting-record", [row["code"] for row in result["exceptions"]])

    def test_limits_reject_without_partial_output(self):
        for name, value in (("max_rows_per_table", 2), ("max_total_rows", 2), ("max_derived_pairs", 3)):
            with self.subTest(limit=name):
                payload = self.payload()
                payload["policy"][name] = value
                result, _ = self.solve(payload)
                self.assertEqual("rejected", result["status"])
                self.assertEqual({}, result["outputs"])
                self.assertEqual("limit-exceeded", result["exceptions"][0]["code"])

    def test_derived_pair_limit_is_inclusive_at_exact_fifteen(self):
        payload = self.payload()
        payload["policy"]["max_derived_pairs"] = 15
        result, _ = self.solve(payload)
        self.assertEqual("completed_with_exceptions", result["status"])
        self.assertEqual(12, len(result["outputs"]["interval_ledger"]))
        payload["policy"]["max_derived_pairs"] = 14
        result, _ = self.solve(payload)
        self.assertEqual("rejected", result["status"])
        self.assertEqual("limit-exceeded", result["exceptions"][0]["code"])

    def test_touching_certificates_cover_without_overlap_or_gap(self):
        payload = self.payload()
        payload["calibrations"][0]["valid_until"] = "2026-09-14T09:10:00Z"
        payload["calibrations"].append(dict(
            payload["calibrations"][0], calibration_id="SYN-C-R-NEXT",
            valid_from="2026-09-14T09:10:00Z", valid_until="2026-10-01T00:00:00Z",
        ))
        result, _ = self.solve(payload)
        self.assertEqual(1800, self.lot(result)["covered_seconds"])
        self.assertEqual(["outside-band"], self.lot(result)["reason_codes"])

    def test_overlapping_certificates_do_not_choose_one(self):
        payload = self.payload()
        payload["calibrations"].append(dict(payload["calibrations"][0], calibration_id="SYN-C-R-OTHER"))
        result, _ = self.solve(payload)
        self.assertEqual(["conflicting-evidence"], self.lot(result)["reason_codes"])
        self.assertIsNone(self.lot(result)["modeled_outside_seconds"])

    def test_gap_limit_equality_and_one_second_beyond(self):
        payload = self.payload()
        result, _ = self.solve(payload)
        self.assertEqual(1800, self.lot(result, "SYN-LOT-F")["covered_seconds"])
        payload["policy"]["max_gap_seconds"] = 599
        result, _ = self.solve(payload)
        lot = self.lot(result, "SYN-LOT-F")
        self.assertEqual(1800, lot["unknown_seconds"])
        self.assertEqual(["temperature-gap"], lot["reason_codes"])

    def test_malformed_types_dates_and_fields(self):
        cases = [
            ("boolean-temperature", lambda p: p["readings"][0].update(temperature_tenths_c=True)),
            ("boolean-quantity", lambda p: p["inventory"][0].update(quantity_units=True)),
            ("fractional-temperature", lambda p: p["readings"][0].update(temperature_tenths_c=20.5)),
            ("bad-calendar", lambda p: p.update(as_of="2026-02-30T09:00:00Z")),
            ("offset-not-canonical", lambda p: p.update(as_of="2026-09-14T09:30:00+00:00")),
            ("unknown-field", lambda p: p["readings"][0].update(released=True)),
            ("reversed-interval", lambda p: p["placements"][0].update(left_at="2026-09-14T08:00:00Z")),
            ("inverted-profile", lambda p: p["profiles"][0].update(lower_tenths_c=99)),
        ]
        for name, mutate in cases:
            with self.subTest(case=name):
                payload = self.payload()
                mutate(payload)
                result, _ = self.solve(payload)
                self.assertEqual("rejected", result["status"])
                self.assertEqual({}, result["outputs"])
                self.assertEqual("invalid-input", result["exceptions"][0]["code"])

    def test_all_review_intervals_conserve_duration(self):
        for case in ("demo", "holdout-a", "holdout-b", "negative-contradictory"):
            result, _ = self.solve(self.payload(case))
            for row in result["outputs"]["lot_review"]:
                self.assertEqual(row["occupied_seconds"], row["covered_seconds"] + row["unknown_seconds"])
                if row["modeled_outside_seconds"] is not None:
                    self.assertLessEqual(row["modeled_outside_seconds"], row["covered_seconds"])


if __name__ == "__main__":
    unittest.main()
