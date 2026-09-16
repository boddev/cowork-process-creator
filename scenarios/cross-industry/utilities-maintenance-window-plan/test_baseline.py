import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2]))
from scenarios._shared.common import digest
from scenarios._shared.contract import load_scenario, validate_trace
from scenarios._shared.pipeline import golden_lock

SPEC = importlib.util.spec_from_file_location("utilities_planning_baseline", HERE / "baseline.py")
BASELINE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BASELINE)


def read_case(case_id, directory="mock-data"):
    return json.loads((HERE / directory / (case_id + ".json")).read_text(encoding="utf-8"))


def single_order():
    payload = read_case("negative-malformed")
    payload["files"]["work-orders.json"][0].update(work_order_id="ONE", duration_minutes=60)
    return payload


class PlanningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scenario = load_scenario(HERE)
        golden_lock(cls.scenario, create=True)

    def test_five_independent_goldens_and_bound_traces(self):
        for case in self.scenario.cases:
            with self.subTest(case=case["id"]):
                payload = read_case(case["id"])
                before = copy.deepcopy(payload)
                actual, events = BASELINE.solve(payload)
                self.assertEqual(actual, read_case(case["id"], "expected"))
                self.assertEqual(payload, before)
                trace = {
                    "schema_version": 1, "provenance": "synthetic-local-baseline",
                    "scenario_id": self.scenario.id,
                    "input_sha256": digest((HERE / case["input"]).read_bytes()),
                    "events": [dict(item, sequence=index) for index, item in enumerate(events, 1)],
                }
                validate_trace(trace, self.scenario, case, trace["input_sha256"])

    def test_business_output_and_trace_are_row_order_invariant(self):
        for case_id in ("demo", "holdout-a", "holdout-b"):
            payload = read_case(case_id)
            result, events = BASELINE.solve(payload)
            for rows in payload["files"].values():
                rows.reverse()
            reordered, reordered_events = BASELINE.solve(payload)
            self.assertEqual(result, reordered)
            self.assertEqual(events, reordered_events)

    def test_zero_orders_complete_without_inventing_work(self):
        payload = read_case("demo")
        payload["files"] = {name: [] for name in payload["files"]}
        result, events = BASELINE.solve(payload)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["exceptions"], [])
        self.assertEqual(result["outputs"]["summary"], {
            "work_orders": 0, "proposed": 0, "deferred": 0, "job_minutes": 0, "rejected_candidates": 0,
        })
        self.assertEqual(result["outputs"]["resource_load"], [])
        self.assertEqual(len(events), 8)

    def test_single_and_many_orders_use_real_variable_searches(self):
        payload = single_order()
        first, _ = BASELINE.solve(payload)
        self.assertEqual(first["outputs"]["summary"]["job_minutes"], 60)
        original = payload["files"]["work-orders.json"][0]
        payload["files"]["work-orders.json"] = [
            dict(original, work_order_id=f"LOOP-{i:02}", duration_minutes=30) for i in range(8)
        ]
        result, _ = BASELINE.solve(payload)
        self.assertEqual(result["outputs"]["summary"]["proposed"], 8)
        self.assertEqual(result["outputs"]["summary"]["job_minutes"], 240)
        self.assertEqual([row["search_starts"] for row in result["outputs"]["orders"]], list(range(1, 9)))
        self.assertEqual(result["outputs"]["proposals"][-1]["end"], "2026-10-05T12:00:00Z")

    def test_half_open_adjacency_and_due_equality(self):
        payload = single_order()
        payload["files"]["work-orders.json"][0]["due_at"] = "2026-10-05T09:00:00Z"
        payload["files"]["commitments.json"] = [
            {"commitment_id": "AFTER", "resource_id": "NC", "start": "2026-10-05T09:00:00Z",
             "end": "2026-10-05T10:00:00Z"}
        ]
        result, _ = BASELINE.solve(payload)
        self.assertEqual(result["outputs"]["proposals"][0]["end"], "2026-10-05T09:00:00Z")
        self.assertEqual(result["outputs"]["conflicts"], [])

    def test_seconds_round_up_relative_to_horizon_grid(self):
        payload = single_order()
        payload["files"]["work-orders.json"][0]["earliest_start"] = "2026-10-05T08:00:01Z"
        result, _ = BASELINE.solve(payload)
        self.assertEqual(result["outputs"]["orders"][0]["ready_at"], "2026-10-05T08:30:00Z")
        payload["config"]["horizon_start"] = "2026-10-05T08:10:00Z"
        payload["files"]["work-orders.json"][0]["earliest_start"] = "2026-10-05T08:15:00Z"
        result, _ = BASELINE.solve(payload)
        self.assertEqual(result["outputs"]["orders"][0]["ready_at"], "2026-10-05T08:40:00Z")

    def test_crew_tie_and_earlier_start_precedence(self):
        payload = read_case("holdout-a")
        result, _ = BASELINE.solve(payload)
        self.assertEqual(result["outputs"]["proposals"][0]["crew_id"], "CE-A02")
        self.assertEqual(result["outputs"]["proposals"][1]["crew_id"], "CE-A01")
        self.assertEqual(result["outputs"]["orders"][0]["search_starts"], 1)

    def test_dependency_priority_recomputed_after_each_decision(self):
        result, _ = BASELINE.solve(read_case("holdout-b"))
        self.assertEqual([row["work_order_id"] for row in result["outputs"]["proposals"]],
                         ["UT-B01", "UT-B02", "UT-B04"])
        conflict = result["outputs"]["conflicts"][0]
        self.assertEqual((conflict["work_order_id"], conflict["blocking_id"]), ("UT-B03", "UT-B02"))

    def test_deferred_predecessor_blocks_successor(self):
        payload = single_order()
        parent = payload["files"]["work-orders.json"][0]
        parent.update(priority=2, plan_approved=False)
        child = dict(parent, work_order_id="CHILD", priority=1, plan_approved=True, predecessors=["ONE"])
        payload["files"]["work-orders.json"].insert(0, child)
        result, _ = BASELINE.solve(payload)
        child_result = result["outputs"]["orders"][0]
        self.assertEqual(child_result["reason"], "prerequisite-unresolved")
        self.assertEqual(child_result["pending_predecessors"], ["ONE"])
        self.assertEqual(result["outputs"]["proposals"], [])

    def test_equal_priority_uses_due_then_identifier(self):
        payload = single_order()
        base = payload["files"]["work-orders.json"][0]
        payload["files"]["work-orders.json"] = [
            dict(base, work_order_id="A", due_at="2026-10-05T10:00:00Z"),
            dict(base, work_order_id="B", due_at="2026-10-05T09:00:00Z"),
        ]
        result, _ = BASELINE.solve(payload)
        self.assertEqual([row["work_order_id"] for row in result["outputs"]["proposals"]], ["B", "A"])
        payload["files"]["work-orders.json"][1]["due_at"] = "2026-10-05T10:00:00Z"
        result, _ = BASELINE.solve(payload)
        self.assertEqual([row["work_order_id"] for row in result["outputs"]["proposals"]], ["A", "B"])

    def test_external_snapshot_equality_and_future_or_missing(self):
        payload = single_order()
        payload["files"]["work-orders.json"][0]["predecessors"] = ["EXT"]
        payload["files"]["prerequisite-status.json"] = [
            {"prerequisite_id": "EXT", "state": "complete", "completed_at": "2026-10-05T07:00:00Z",
             "recorded_at": "2026-10-05T07:00:00Z"}
        ]
        result, _ = BASELINE.solve(payload)
        self.assertEqual(result["status"], "completed")
        payload["files"]["prerequisite-status.json"][0]["recorded_at"] = "2026-10-05T07:00:01Z"
        result, _ = BASELINE.solve(payload)
        self.assertEqual(result["outputs"]["orders"][0]["pending_predecessors"], ["EXT"])
        payload["files"]["prerequisite-status.json"] = []
        result, _ = BASELINE.solve(payload)
        self.assertEqual(result["outputs"]["orders"][0]["reason"], "prerequisite-unresolved")

    def test_kit_shortage_cumulative_arrival_and_unneeded_surplus(self):
        result, _ = BASELINE.solve(read_case("demo"))
        self.assertEqual(result["outputs"]["orders"][3]["missing_materials"],
                         [{"item_id": "KIT-A", "required": 3, "reserved": 1, "missing": 2}])
        result, _ = BASELINE.solve(read_case("holdout-a"))
        self.assertEqual(result["outputs"]["orders"][0]["ready_at"], "2026-11-02T13:00:00Z")
        late = result["outputs"]["orders"][3]
        self.assertEqual((late["ready_at"], late["search_starts"]), ("2026-11-02T17:30:00Z", 0))
        self.assertEqual(late["reason"], "no-feasible-window")

    def test_adjacent_windows_not_stitched_and_overlap_not_double_counted(self):
        payload = single_order()
        payload["files"]["work-orders.json"][0].update(duration_minutes=120, due_at="2026-10-05T10:00:00Z")
        payload["files"]["resource-windows.json"][1]["end"] = "2026-10-05T09:00:00Z"
        payload["files"]["resource-windows.json"].append({
            "window_id": "SECOND", "resource_id": "NA",
            "start": "2026-10-05T09:00:00Z", "end": "2026-10-05T10:00:00Z",
        })
        result, _ = BASELINE.solve(payload)
        self.assertEqual(result["outputs"]["orders"][0]["reason"], "no-feasible-window")
        self.assertEqual(result["outputs"]["resource_load"][0]["available_minutes"], 120)
        payload["files"]["resource-windows.json"][1]["end"] = "2026-10-05T10:00:00Z"
        payload["files"]["resource-windows.json"][2]["end"] = "2026-10-05T12:00:00Z"
        result, _ = BASELINE.solve(payload)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["outputs"]["resource_load"][0]["available_minutes"], 240)

    def test_commitment_load_is_clipped_to_horizon(self):
        payload = single_order()
        payload["files"]["resource-windows.json"][0]["start"] = "2026-10-05T06:00:00Z"
        payload["files"]["commitments.json"] = [
            {"commitment_id": "EARLY", "resource_id": "NC", "start": "2026-10-05T07:00:00Z",
             "end": "2026-10-05T09:00:00Z"}
        ]
        result, _ = BASELINE.solve(payload)
        load = next(row for row in result["outputs"]["resource_load"] if row["resource_id"] == "NC")
        self.assertEqual((load["available_minutes"], load["committed_minutes"], load["proposed_minutes"]), (240, 60, 60))
        self.assertEqual(result["outputs"]["proposals"][0]["start"], "2026-10-05T09:00:00Z")

    def test_search_limit_does_not_claim_infeasible_unexamined_slots(self):
        payload = single_order()
        payload["config"]["max_search_starts"] = 1
        payload["files"]["commitments.json"] = [
            {"commitment_id": "BLOCK", "resource_id": "NA", "start": "2026-10-05T08:00:00Z",
             "end": "2026-10-05T09:00:00Z"}
        ]
        result, _ = BASELINE.solve(payload)
        self.assertEqual(result["outputs"]["orders"][0]["reason"], "search-limit")
        self.assertEqual(result["outputs"]["orders"][0]["search_starts"], 1)
        payload["files"]["work-orders.json"][0]["due_at"] = "2026-10-05T09:00:00Z"
        result, _ = BASELINE.solve(payload)
        self.assertEqual(result["outputs"]["orders"][0]["reason"], "no-feasible-window")

    def test_missing_craft_has_explicit_deferral_not_silent_drop(self):
        payload = single_order()
        payload["files"]["work-orders.json"][0]["craft_code"] = "UNAVAILABLE"
        result, _ = BASELINE.solve(payload)
        self.assertEqual(result["outputs"]["orders"][0]["reason"], "no-eligible-crew")
        self.assertEqual(result["outputs"]["orders"][0]["ready_at"], "2026-10-05T08:00:00Z")
        self.assertEqual(len(result["exceptions"]), 1)

    def test_duplicate_missing_and_unknown_records_reject_explicitly(self):
        cases = []
        payload = single_order()
        payload["files"]["resource-windows.json"].append(copy.deepcopy(payload["files"]["resource-windows.json"][0]))
        cases.append((payload, "duplicate-id"))
        payload = single_order()
        payload["files"]["work-orders.json"][0]["area_resource_id"] = "UNKNOWN"
        cases.append((payload, "missing-reference"))
        payload = single_order()
        payload["files"]["work-orders.json"][0]["authorize"] = True
        cases.append((payload, "invalid-shape"))
        payload = single_order()
        payload["files"]["resources.json"][0]["capacity"] = True
        cases.append((payload, "invalid-integer"))
        for payload, code in cases:
            with self.subTest(code=code):
                result, _ = BASELINE.solve(payload)
                self.assertEqual(result["status"], "rejected")
                self.assertEqual(result["outputs"], {})
                self.assertEqual(result["exceptions"][0]["code"], code)

    def test_invalid_times_and_offset_normalization(self):
        for value in ("2026-10-05T08:00:00", "2026-10-05T08:00:00+01:99",
                      "2026-10-05T08:00:00.001Z", "2026-02-30T08:00:00Z"):
            with self.subTest(value=value):
                payload = single_order()
                payload["config"]["horizon_start"] = value
                result, _ = BASELINE.solve(payload)
                self.assertEqual(result["exceptions"][0]["code"], "invalid-time")
        payload = single_order()
        payload["files"]["work-orders.json"][0]["earliest_start"] = "2026-10-05T03:00:00-05:00"
        result, _ = BASELINE.solve(payload)
        self.assertEqual(result["outputs"]["orders"][0]["ready_at"], "2026-10-05T08:00:00Z")

    def test_contradictory_existing_bookings_and_external_identity_reject(self):
        payload = single_order()
        payload["files"]["commitments.json"] = [
            {"commitment_id": "C1", "resource_id": "NC", "start": "2026-10-05T08:00:00Z",
             "end": "2026-10-05T10:00:00Z"},
            {"commitment_id": "C2", "resource_id": "NC", "start": "2026-10-05T09:00:00Z",
             "end": "2026-10-05T11:00:00Z"},
        ]
        result, _ = BASELINE.solve(payload)
        self.assertEqual(result["exceptions"][0]["code"], "contradictory-commitments")
        payload = single_order()
        payload["files"]["prerequisite-status.json"] = [
            {"prerequisite_id": "ONE", "state": "open", "recorded_at": "2026-10-05T07:00:00Z", "completed_at": None}
        ]
        result, _ = BASELINE.solve(payload)
        self.assertEqual(result["exceptions"][0]["code"], "invalid-value")

    def test_output_notice_and_queues_cannot_imply_clearance(self):
        result, events = BASELINE.solve(read_case("demo"))
        self.assertEqual(result["outputs"]["notice"], BASELINE.NOTICE)
        self.assertIn("not safe-to-work", events[-1]["caption"])
        self.assertEqual([row["work_order_id"] for row in result["outputs"]["review_queue"]],
                         [row["work_order_id"] for row in result["exceptions"]])


class AdapterTests(unittest.TestCase):
    def invoke(self, input_path, output_path, trace_path):
        return subprocess.run(
            [sys.executable, "-B", "-I", str(HERE / "baseline.py"),
             "--input", str(input_path), "--output", str(output_path), "--trace", str(trace_path)],
            capture_output=True, text=True, check=False, timeout=20,
        )

    def test_existing_output_or_trace_is_not_overwritten(self):
        for existing in ("output.json", "trace.json"):
            with self.subTest(existing=existing), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                source, output, trace = root / "input.json", root / "output.json", root / "trace.json"
                source.write_bytes((HERE / "mock-data" / "demo.json").read_bytes())
                (root / existing).write_bytes(b"prior evidence")
                original = source.read_bytes()
                process = self.invoke(source, output, trace)
                self.assertNotEqual(process.returncode, 0)
                self.assertEqual((root / existing).read_bytes(), b"prior evidence")
                self.assertFalse((trace if existing == "output.json" else output).exists())
                self.assertEqual(source.read_bytes(), original)

    def test_input_output_alias_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "input.json"
            source.write_bytes((HERE / "mock-data" / "demo.json").read_bytes())
            original = source.read_bytes()
            process = self.invoke(source, source, root / "trace.json")
            self.assertNotEqual(process.returncode, 0)
            self.assertEqual(source.read_bytes(), original)
            self.assertFalse((root / "trace.json").exists())

    def test_new_output_trace_alias_is_rejected_before_writing(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "input.json"
            target = root / "same.json"
            source.write_bytes((HERE / "mock-data" / "demo.json").read_bytes())
            process = self.invoke(source, target, target)
            self.assertNotEqual(process.returncode, 0)
            self.assertFalse(target.exists())

    def test_malformed_deep_duplicate_nonfinite_json_is_not_a_business_pass(self):
        documents = [
            b'{"config":', b'{"config":{},"config":{}}', b'{"value":NaN}',
            b'{"value":1e400}', b"\xff", b"[]", b"\xef\xbb\xbf{}",
            ('{"deep":' + "[" * 90 + "0" + "]" * 90 + "}").encode("utf-8"),
            ('{"deep":' + "[" * 3000 + "0" + "]" * 3000 + "}").encode("utf-8"),
        ]
        for index, content in enumerate(documents):
            with self.subTest(document=index), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                source, output, trace = root / "input.json", root / "output.json", root / "trace.json"
                source.write_bytes(content)
                process = self.invoke(source, output, trace)
                self.assertNotEqual(process.returncode, 0, process.stdout)
                self.assertIn("Baseline failed:", process.stderr)
                self.assertFalse(output.exists())
                self.assertFalse(trace.exists())


if __name__ == "__main__":
    unittest.main()
