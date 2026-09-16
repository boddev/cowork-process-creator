"""Owned stdlib tests; all writable CLI evidence stays inside this scenario."""
import copy
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import importlib.util
import json
from pathlib import Path
import random
import shutil
import subprocess
import sys
import unittest
import uuid

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parents[2]))
from scenarios._shared.comparison import compare_json
from scenarios._shared.contract import baseline_import_audit, load_scenario, validate_result, validate_trace
from scenarios._shared.pipeline import golden_lock


def read_case(case_id):
    return json.loads((ROOT / "mock-data" / (case_id + ".json")).read_text(encoding="utf-8"))


def one_shipment(case_id="demo", shipment_id="LG-D04"):
    payload = read_case(case_id)
    files = payload["files"]
    shipment = next(row for row in files["shipments.json"] if row["shipment_id"] == shipment_id)
    files["shipments.json"] = [shipment]
    files["pod-events.json"] = [row for row in files["pod-events.json"] if row["shipment_id"] == shipment_id]
    files["invoice-lines.json"] = [row for row in files["invoice-lines.json"] if row["shipment_id"] == shipment_id]
    invoice_ids = {row["invoice_id"] for row in files["invoice-lines.json"]}
    files["carrier-invoices.json"] = [row for row in files["carrier-invoices.json"] if row["invoice_id"] in invoice_ids]
    files["rate-cards.json"] = [
        row for row in files["rate-cards.json"]
        if all(row[key] == shipment[key] for key in ("carrier_id", "lane_id", "currency"))
    ]
    files["review-history.json"] = [row for row in files["review-history.json"] if row["shipment_id"] == shipment_id]
    balance_headers(payload)
    return payload


def balance_headers(payload):
    for invoice in payload["files"]["carrier-invoices.json"]:
        total = sum((Decimal(row["amount"]) for row in payload["files"]["invoice-lines.json"]
                     if row["invoice_id"] == invoice["invoice_id"]), Decimal(0))
        invoice["total"] = format(total, ".2f")


def many_shipments(count):
    payload = one_shipment()
    files = payload["files"]
    shipment, pod = files["shipments.json"][0], files["pod-events.json"][0]
    lines, case = files["invoice-lines.json"], files["review-history.json"][0]
    files["shipments.json"], files["pod-events.json"], files["invoice-lines.json"], files["review-history.json"] = [], [], [], []
    invoice_id = files["carrier-invoices.json"][0]["invoice_id"]
    for index in range(count):
        sid = f"TEST-S-{index:03d}"
        files["shipments.json"].append(dict(shipment, shipment_id=sid))
        files["pod-events.json"].append(dict(pod, pod_id=f"TEST-P-{index:03d}", shipment_id=sid))
        files["review-history.json"].append(dict(case, case_id=f"TEST-C-{index:03d}", shipment_id=sid))
        for line in lines:
            files["invoice-lines.json"].append(dict(
                line, line_id=f"TEST-L-{index:03d}-{line['charge_code']}", shipment_id=sid, invoice_id=invoice_id,
            ))
    balance_headers(payload)
    return payload


def at(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def stamp(value):
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def row_by(result, array, field, identity):
    return next(row for row in result["outputs"][array] if row[field] == identity)


class ScenarioTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scenario = load_scenario(ROOT)
        golden_lock(cls.scenario)
        spec = importlib.util.spec_from_file_location("logistics_owned_baseline", ROOT / "baseline.py")
        cls.baseline = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.baseline)

    @classmethod
    def tearDownClass(cls):
        golden_lock(cls.scenario)

    def review(self, payload):
        before = copy.deepcopy(payload)
        result, events = self.baseline.solve(payload)
        self.assertEqual(payload, before, "solve mutated its input")
        validate_result(result)
        fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        trace = {
            "schema_version": 1, "provenance": "synthetic-local-baseline",
            "scenario_id": self.scenario.id, "input_sha256": fingerprint,
            "events": [dict(event, sequence=index) for index, event in enumerate(events, 1)],
        }
        case = self.scenario.case("negative-malformed" if result["status"] == "rejected" else "demo")
        validate_trace(trace, self.scenario, case, fingerprint)
        self.assertTrue(all("sequence" not in event for event in events))
        return result, events

    def test_five_independent_frozen_cases(self):
        for case in self.scenario.cases:
            with self.subTest(case=case["id"]):
                result, _ = self.review(read_case(case["id"]))
                reference = json.loads(self.scenario.file(case["expected"]).read_text())
                self.assertEqual(compare_json(reference, result), [])

    def test_row_order_invariance_for_all_cases_and_traces(self):
        for case in self.scenario.cases:
            payload = read_case(case["id"])
            original = self.review(payload)
            for seed in (0, 7, 29):
                with self.subTest(case=case["id"], seed=seed):
                    shuffled = copy.deepcopy(payload)
                    rng = random.Random(seed)
                    for rows in shuffled["files"].values():
                        rng.shuffle(rows)
                    shuffled["files"] = dict(reversed(list(shuffled["files"].items())))
                    shuffled["config"] = dict(reversed(list(shuffled["config"].items())))
                    self.assertEqual(original, self.review(shuffled))

    def test_baseline_import_audit_and_lock(self):
        audit = baseline_import_audit(ROOT / "baseline.py")
        self.assertEqual(audit["status"], "static_import_check_pass")
        self.assertLessEqual(set(audit["imports"]), set(sys.stdlib_module_names) | {"scenario_support"})
        self.assertEqual(len(golden_lock(self.scenario)["cases"]), 5)

    def test_observed_trace_contains_real_intermediates(self):
        _, events = self.review(read_case("demo"))
        self.assertEqual(len(events), 9)
        calculation = next(event for event in events if event["step_id"] == "calculate-charges")
        self.assertIn(["LG-D02", "800.00", "80.00", "75.00", "75.00", "955.00"], calculation["tables"][0]["rows"])
        self.assertIn(["LG-D02", 7800, 3600, 4200, 3, "100.00"], calculation["tables"][1]["rows"])
        selection = next(event for event in events if event["step_id"] == "select-evidence")
        self.assertIn(["LG-D03", None, "LG-RATE-D03", "2026-09-12", False, 1], selection["tables"][0]["rows"])
        self.assertEqual(events[0]["kind"], "input")
        self.assertEqual(events[-1]["kind"], "output")

    def test_malformed_business_case_stops_before_joins(self):
        result, events = self.review(read_case("negative-malformed"))
        self.assertEqual(result["status"], "rejected")
        self.assertEqual(result["outputs"], {})
        self.assertEqual([event["kind"] for event in events], ["input", "validation"])
        self.assertEqual(result["exceptions"][0]["code"], "invalid-amount")

    def test_zero_rows_keep_prefix_suffix_and_complete_envelope(self):
        payload = read_case("demo")
        payload["files"] = {name: [] for name in payload["files"]}
        result, events = self.review(payload)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["exceptions"], [])
        self.assertEqual(len(events), 9)
        for key, value in result["outputs"].items():
            if isinstance(value, list):
                self.assertEqual(value, [], key)
        for key, value in result["outputs"]["summary"].items():
            self.assertEqual(value, [] if isinstance(value, list) else 0, key)

    def test_many_rows_all_entities_and_readable_trace_subsets(self):
        payload = many_shipments(33)
        result, events = self.review(payload)
        self.assertEqual(result["status"], "completed")
        summary = result["outputs"]["summary"]
        self.assertEqual((summary["shipment_count"], summary["line_count"], summary["pod_count"],
                          summary["prior_case_count"], summary["ready_shipments"]), (33, 99, 33, 33, 33))
        self.assertEqual(summary["currency_totals"][0]["known_expected"], "14520.00")
        self.assertEqual(summary["currency_totals"][0]["computable_billed"], "14520.00")
        self.assertEqual(len(result["outputs"]["rate_evidence"][0]["selected_for"]), 33)
        self.assertTrue(all(row["proposed_state"] == "closed" for row in result["outputs"]["case_proposals"]))
        tables = [table for event in events for table in event["tables"]]
        self.assertTrue(any(table["total_rows"] == 33 and len(table["rows"]) == 8 for table in tables))
        for table in tables:
            if table["total_rows"] > 8:
                self.assertIn("first 8", table["title"])
        shuffled = copy.deepcopy(payload)
        for rows in shuffled["files"].values():
            random.Random(83).shuffle(rows)
        self.assertEqual((result, events), self.review(shuffled))

    def test_exact_seconds_ceiling_and_cap_reached_or_exceeded(self):
        cases = [
            (3600, 0, "0.00"), (3601, 1, "25.00"),
            (5400, 1, "25.00"), (5401, 2, "50.00"),
            (10800, 4, "100.00"), (10801, 5, "100.00"), (14400, 6, "100.00"),
        ]
        for dwell, blocks, charge in cases:
            with self.subTest(dwell=dwell):
                payload = one_shipment()
                payload["config"]["as_of"] = "2026-09-15T12:00:00Z"
                pod = payload["files"]["pod-events.json"][0]
                start = at(pod["gate_in_at"])
                pod["delivered_at"] = stamp(start)
                pod["gate_out_at"] = stamp(start + timedelta(seconds=dwell))
                pod["recorded_at"] = stamp(start + timedelta(seconds=dwell + 1))
                result, _ = self.review(payload)
                shipment = result["outputs"]["shipments"][0]
                self.assertEqual(shipment["dwell_seconds"], dwell)
                self.assertEqual(shipment["excess_seconds"], max(0, dwell - 3600))
                self.assertEqual(shipment["detention_blocks"], blocks)
                self.assertEqual(shipment["detention"], charge)

    def test_zero_cap_and_zero_prices_are_computable(self):
        payload = one_shipment()
        rate = payload["files"]["rate-cards.json"][0]
        rate.update(linehaul="0.00", fuel_fraction="0", free_wait_minutes=0, detention_cap="0.00")
        for line in payload["files"]["invoice-lines.json"]:
            line["amount"] = "0.00"
        balance_headers(payload)
        result, _ = self.review(payload)
        shipment = result["outputs"]["shipments"][0]
        self.assertEqual(shipment["detention_blocks"], 2)
        self.assertEqual(shipment["expected_amount"], "0.00")
        self.assertEqual(shipment["variance_amount"], "0.00")
        self.assertEqual(result["status"], "completed")
        self.assertTrue(result["outputs"]["summary"]["currency_totals"][0]["comparison_complete"])

    def test_fuel_is_rounded_half_up_per_line_not_after_batch(self):
        payload = many_shipments(2)
        payload["config"].update(absolute_tolerance="0.00", relative_tolerance="0")
        payload["files"]["rate-cards.json"][0].update(linehaul="0.05", fuel_fraction="0.10")
        for line in payload["files"]["invoice-lines.json"]:
            line["amount"] = {"linehaul": "0.05", "fuel": "0.01", "detention": "0.00"}[line["charge_code"]]
        balance_headers(payload)
        result, _ = self.review(payload)
        self.assertEqual(result["status"], "completed")
        self.assertEqual([row["fuel"] for row in result["outputs"]["shipments"]], ["0.01", "0.01"])
        self.assertEqual([row["expected_amount"] for row in result["outputs"]["shipments"]], ["0.06", "0.06"])
        self.assertEqual(result["outputs"]["summary"]["currency_totals"][0]["known_expected"], "0.12")

    def test_absolute_tolerance_is_inclusive_and_symmetric(self):
        for variance, state in [("5.00", "ready-for-review"), ("-5.00", "ready-for-review"),
                                ("5.01", "held"), ("-5.01", "held")]:
            with self.subTest(variance=variance):
                payload = one_shipment()
                for line in payload["files"]["invoice-lines.json"]:
                    if line["charge_code"] == "linehaul":
                        line["amount"] = format(Decimal("400.00") + Decimal(variance), ".2f")
                balance_headers(payload)
                result, _ = self.review(payload)
                shipment = result["outputs"]["shipments"][0]
                self.assertEqual((shipment["tolerance_amount"], shipment["variance_amount"], shipment["disposition"]),
                                 ("5.00", variance, state))

    def test_relative_tolerance_rounds_half_up_and_includes_both_signs(self):
        for variance, state in [("10.33", "ready-for-review"), ("-10.33", "ready-for-review"),
                                ("10.34", "held"), ("-10.34", "held")]:
            with self.subTest(variance=variance):
                payload = one_shipment("holdout-a", "LG-A01")
                for line in payload["files"]["invoice-lines.json"]:
                    if line["charge_code"] == "linehaul":
                        line["amount"] = format(Decimal("900.00") + Decimal(variance), ".2f")
                    elif line["charge_code"] == "detention":
                        line["amount"] = "20.00"
                balance_headers(payload)
                result, _ = self.review(payload)
                shipment = result["outputs"]["shipments"][0]
                self.assertEqual((shipment["tolerance_amount"], shipment["variance_amount"], shipment["disposition"]),
                                 ("10.33", variance, state))

    def test_effective_rate_uses_utc_start_and_exclusive_end(self):
        cases = [
            ("2026-09-30T20:00:00-04:00", "2026-10-01", "LG-RATE-A01-NEW"),
            ("2026-09-30T19:59:59-04:00", "2026-09-30", "LG-RATE-A01-OLD"),
            ("2026-10-31T20:00:00-04:00", "2026-11-01", None),
        ]
        for instant, day, rate in cases:
            with self.subTest(instant=instant):
                payload = one_shipment("holdout-a", "LG-A01")
                payload["files"]["shipments.json"][0]["planned_delivery_at"] = instant
                result, _ = self.review(payload)
                shipment = result["outputs"]["shipments"][0]
                self.assertEqual((shipment["rate_date"], shipment["rate_id"]), (day, rate))
                if rate is None:
                    self.assertIn("missing-rate", shipment["issue_codes"])
                    self.assertIsNone(shipment["expected_amount"])

    def test_cutoff_is_inclusive_and_future_conflict_excluded_independently(self):
        payload = one_shipment("holdout-b", "LG-B01")
        result, _ = self.review(payload)
        self.assertIsNone(result["outputs"]["shipments"][0]["pod_id"])
        pod = payload["files"]["pod-events.json"][0]
        pod["recorded_at"] = "2026-11-04T06:00:00-04:00"
        for revision in (1, 99):
            future = dict(pod, pod_id="TEST-POD-FUTURE", revision=revision, delivered_units=3,
                          recorded_at="2026-11-04T06:00:01-04:00")
            payload["files"]["pod-events.json"] = [pod, future]
            result, _ = self.review(payload)
            shipment = result["outputs"]["shipments"][0]
            self.assertEqual(shipment["pod_id"], "LG-POD-B01-FUTURE")
            self.assertEqual(shipment["expected_amount"], "220.00")
            self.assertEqual(shipment["disposition"], "ready-for-review")
            future_row = row_by(result, "pod_evidence", "pod_id", "TEST-POD-FUTURE")
            self.assertEqual(future_row["disposition"], "future-excluded")
            self.assertEqual(future_row["recorded_at"], "2026-11-04T10:00:01Z")

    def test_future_orphan_pod_is_excluded_not_used_as_a_join_error(self):
        payload = one_shipment()
        future = dict(payload["files"]["pod-events.json"][0], pod_id="TEST-ORPHAN-POD",
                      shipment_id="UNKNOWN-SHIPMENT", recorded_at="2026-09-14T12:00:01Z")
        payload["files"]["pod-events.json"].append(future)
        result, _ = self.review(payload)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(row_by(result, "pod_evidence", "pod_id", "TEST-ORPHAN-POD")["disposition"], "future-excluded")

    def test_highest_revision_not_latest_recording_wins(self):
        payload = one_shipment()
        pod = payload["files"]["pod-events.json"][0]
        pod["revision"] = 2
        old = dict(pod, pod_id="TEST-LOWER-REVISION", revision=1, recorded_at="2026-09-14T11:00:00Z")
        old.update(state="void", delivered_at=None, received_by=None, delivered_units=None, gate_in_at=None, gate_out_at=None)
        payload["files"]["pod-events.json"].append(old)
        result, _ = self.review(payload)
        self.assertEqual(result["outputs"]["shipments"][0]["pod_id"], pod["pod_id"])
        self.assertEqual(row_by(result, "pod_evidence", "pod_id", "TEST-LOWER-REVISION")["disposition"], "superseded")

    def test_identical_highest_revisions_still_ambiguous(self):
        payload = one_shipment()
        payload["files"]["pod-events.json"].append(dict(payload["files"]["pod-events.json"][0], pod_id="TEST-DUPLICATE-POD"))
        result, _ = self.review(payload)
        shipment = result["outputs"]["shipments"][0]
        self.assertEqual(shipment["issue_codes"], ["contradictory-pod"])
        self.assertIsNone(shipment["pod_id"])
        self.assertIsNone(shipment["expected_amount"])
        self.assertTrue(all(row["disposition"] == "ambiguous" for row in result["outputs"]["pod_evidence"]))

    def test_void_and_quantity_mismatch_preserve_selected_id_but_not_price(self):
        for code in ("void-pod", "quantity-mismatch"):
            with self.subTest(code=code):
                payload = one_shipment()
                pod = payload["files"]["pod-events.json"][0]
                if code == "void-pod":
                    pod.update(state="void", delivered_at=None, received_by=None, delivered_units=None,
                               gate_in_at=None, gate_out_at=None)
                else:
                    pod["delivered_units"] += 1
                result, _ = self.review(payload)
                shipment = result["outputs"]["shipments"][0]
                self.assertEqual(shipment["pod_id"], pod["pod_id"])
                self.assertIsNone(shipment["expected_amount"])
                self.assertIsNone(shipment["dwell_seconds"])
                self.assertIsNone(shipment["pod_overdue"])
                self.assertEqual(shipment["issue_codes"], [code])
                self.assertEqual(result["outputs"]["case_proposals"][0]["proposed_state"], "still-open")

    def test_missing_pod_grace_exact_one_second_late_and_future_plan(self):
        for age, overdue in [(86400, False), (86401, True), (-1, False)]:
            with self.subTest(age=age):
                payload = one_shipment()
                payload["files"]["pod-events.json"] = []
                payload["files"]["shipments.json"][0]["planned_delivery_at"] = stamp(
                    at(payload["config"]["as_of"]) - timedelta(seconds=age)
                )
                result, _ = self.review(payload)
                shipment = result["outputs"]["shipments"][0]
                self.assertEqual(shipment["missing_pod_age_seconds"], max(0, age))
                self.assertEqual(shipment["pod_overdue"], overdue)
                self.assertIsNone(shipment["expected_amount"])

    def test_rate_missing_overlap_and_unused_reference_are_distinct(self):
        for mode in ("missing", "overlap", "unused"):
            with self.subTest(mode=mode):
                payload = one_shipment()
                rate = payload["files"]["rate-cards.json"][0]
                if mode == "missing":
                    payload["files"]["rate-cards.json"] = []
                else:
                    extra = dict(rate, rate_id="TEST-EXTRA-RATE")
                    if mode == "unused":
                        extra["carrier_id"] = "UNUSED-CARRIER"
                    payload["files"]["rate-cards.json"].append(extra)
                result, _ = self.review(payload)
                shipment = result["outputs"]["shipments"][0]
                self.assertEqual(shipment["dwell_seconds"], 3600)
                if mode == "unused":
                    self.assertEqual(result["status"], "completed")
                    self.assertEqual(row_by(result, "rate_evidence", "rate_id", "TEST-EXTRA-RATE")["disposition"], "unused")
                else:
                    self.assertIsNone(shipment["rate_id"])
                    self.assertIsNone(shipment["expected_amount"])
                    self.assertIn("missing-rate" if mode == "missing" else "ambiguous-rate", shipment["issue_codes"])

    def test_duplicate_primary_ids_reject_each_export(self):
        for name in read_case("demo")["files"]:
            with self.subTest(export=name):
                payload = one_shipment()
                payload["files"][name].append(copy.deepcopy(payload["files"][name][0]))
                result, _ = self.review(payload)
                self.assertEqual(result["status"], "rejected")
                self.assertEqual([row["code"] for row in result["exceptions"]], ["duplicate-id"])

    def test_duplicate_charge_is_not_deduplicated_or_compared(self):
        payload = one_shipment()
        duplicate = next(row for row in payload["files"]["invoice-lines.json"] if row["charge_code"] == "linehaul")
        payload["files"]["invoice-lines.json"].append(dict(duplicate, line_id="TEST-DUPLICATE-LINE"))
        balance_headers(payload)
        result, _ = self.review(payload)
        shipment = result["outputs"]["shipments"][0]
        self.assertEqual(shipment["billed_amount"], "840.00")
        self.assertEqual(shipment["expected_amount"], "440.00")
        self.assertIsNone(shipment["variance_amount"])
        self.assertEqual(shipment["issue_codes"], ["duplicate-charge"])
        self.assertEqual(len(result["outputs"]["invoice_lines"]), 4)
        totals = result["outputs"]["summary"]["currency_totals"][0]
        self.assertEqual((totals["held_line_amount"], totals["computable_billed"], totals["known_expected"]),
                         ("840.00", "0.00", "0.00"))
        self.assertFalse(totals["comparison_complete"])

    def test_missing_zero_charge_still_blocks_comparison(self):
        payload = one_shipment()
        payload["files"]["invoice-lines.json"] = [row for row in payload["files"]["invoice-lines.json"]
                                                if row["charge_code"] != "detention"]
        result, _ = self.review(payload)
        shipment = result["outputs"]["shipments"][0]
        self.assertEqual(shipment["issue_codes"], ["missing-charge"])
        self.assertEqual(shipment["expected_amount"], "440.00")
        self.assertIsNone(shipment["variance_amount"])
        self.assertEqual(result["outputs"]["invoices"][0]["known_expected"], "0.00")

    def test_split_billing_not_allocated_across_invoices(self):
        payload = one_shipment()
        header = dict(payload["files"]["carrier-invoices.json"][0], invoice_id="TEST-SECOND-INVOICE")
        payload["files"]["carrier-invoices.json"].append(header)
        for line in payload["files"]["invoice-lines.json"]:
            if line["charge_code"] != "linehaul":
                line["invoice_id"] = "TEST-SECOND-INVOICE"
        balance_headers(payload)
        result, _ = self.review(payload)
        shipment = result["outputs"]["shipments"][0]
        self.assertEqual(shipment["issue_codes"], ["split-billing"])
        self.assertEqual(shipment["billed_amount"], "440.00")
        self.assertIsNone(shipment["variance_amount"])
        self.assertTrue(all(row["known_expected"] == "0.00" for row in result["outputs"]["invoices"]))

    def test_missing_header_keeps_all_lines_and_shipment_evidence_price(self):
        payload = one_shipment()
        payload["files"]["carrier-invoices.json"] = []
        result, _ = self.review(payload)
        shipment = result["outputs"]["shipments"][0]
        self.assertEqual(shipment["issue_codes"], ["missing-invoice"])
        self.assertEqual((shipment["billed_amount"], shipment["expected_amount"]), ("440.00", "440.00"))
        self.assertIsNone(shipment["variance_amount"])
        self.assertEqual(result["outputs"]["invoices"], [])
        self.assertEqual(len(result["outputs"]["invoice_lines"]), 3)
        self.assertEqual(result["outputs"]["summary"]["currency_totals"][0]["held_line_amount"], "440.00")

    def test_missing_shipment_accounts_for_orphan_lines_pod_and_case(self):
        payload = one_shipment()
        payload["files"]["shipments.json"] = []
        result, _ = self.review(payload)
        self.assertEqual(result["outputs"]["shipments"], [])
        self.assertEqual(len(result["outputs"]["invoice_lines"]), 3)
        self.assertEqual(result["outputs"]["pod_evidence"][0]["disposition"], "missing-shipment")
        self.assertEqual(result["outputs"]["case_proposals"][0]["proposed_state"], "held")
        self.assertEqual(result["outputs"]["rate_evidence"][0]["disposition"], "unused")
        self.assertEqual(result["outputs"]["invoices"][0]["line_total"], "440.00")
        totals = result["outputs"]["summary"]["currency_totals"][0]
        self.assertEqual((totals["billed_total"], totals["held_line_amount"], totals["computable_billed"]),
                         ("440.00", "440.00", "0.00"))
        self.assertFalse(totals["comparison_complete"])
        self.assertEqual(len(result["exceptions"]), 5)

    def test_orphan_unknown_currency_is_never_summed_into_a_known_currency(self):
        payload = one_shipment()
        for name in payload["files"]:
            payload["files"][name] = []
        payload["files"]["invoice-lines.json"] = [{
            "line_id": "TEST-ORPHAN-LINE", "invoice_id": "UNKNOWN-INVOICE",
            "shipment_id": "UNKNOWN-SHIPMENT", "charge_code": "linehaul", "amount": "7.00",
        }]
        result, _ = self.review(payload)
        self.assertIsNone(result["outputs"]["invoice_lines"][0]["currency"])
        totals = result["outputs"]["summary"]["currency_totals"][0]
        self.assertIsNone(totals["currency"])
        self.assertEqual((totals["billed_total"], totals["held_line_amount"]), ("7.00", "7.00"))
        self.assertFalse(totals["comparison_complete"])
        self.assertEqual({row["code"] for row in result["exceptions"]}, {"missing-invoice", "missing-shipment"})

    def test_header_mismatch_holds_its_invoice_not_other_invoice(self):
        payload = read_case("demo")
        payload["files"]["carrier-invoices.json"][0]["total"] = "2129.00"
        result, _ = self.review(payload)
        first = row_by(result, "shipments", "shipment_id", "LG-D01")
        second = row_by(result, "shipments", "shipment_id", "LG-D02")
        unaffected = row_by(result, "shipments", "shipment_id", "LG-D04")
        self.assertEqual(first["expected_amount"], "1125.00")
        self.assertEqual(second["expected_amount"], "955.00")
        self.assertIsNone(first["variance_amount"])
        self.assertIsNone(second["variance_amount"])
        self.assertEqual(unaffected["disposition"], "ready-for-review")
        self.assertEqual(unaffected["variance_amount"], "0.00")
        invoice = row_by(result, "invoices", "invoice_id", "LG-INV-D1")
        self.assertEqual((invoice["line_total"], invoice["computable_billed"], invoice["known_expected"]),
                         ("2130.00", "0.00", "0.00"))
        self.assertFalse(invoice["header_matches"])
        self.assertEqual(row_by(result, "case_proposals", "case_id", "LG-CASE-D02-VAR")["proposed_state"], "deferred")
        self.assertEqual(sum(row["code"] == "header-mismatch" for row in result["exceptions"]), 1)
        self.assertNotIn("variance", {row["code"] for row in result["exceptions"]})

    def test_future_invoice_is_structural_hold(self):
        payload = one_shipment()
        payload["files"]["carrier-invoices.json"][0]["invoice_date"] = "2026-09-15"
        result, _ = self.review(payload)
        shipment = result["outputs"]["shipments"][0]
        self.assertEqual(shipment["issue_codes"], ["future-invoice"])
        self.assertEqual(shipment["expected_amount"], "440.00")
        self.assertIsNone(shipment["variance_amount"])
        self.assertEqual(result["outputs"]["invoices"][0]["held_line_amount"], "440.00")

    def test_empty_invoice_zero_total_is_held_and_accounted(self):
        payload = one_shipment()
        for name in payload["files"]:
            if name != "carrier-invoices.json":
                payload["files"][name] = []
        payload["files"]["carrier-invoices.json"][0]["total"] = "0.00"
        result, _ = self.review(payload)
        invoice = result["outputs"]["invoices"][0]
        self.assertTrue(invoice["header_matches"])
        self.assertFalse(invoice["comparison_complete"])
        self.assertEqual(invoice["issue_codes"], ["empty-invoice"])
        self.assertEqual(result["outputs"]["summary"]["currency_totals"][0]["billed_total"], "0.00")

    def test_carrier_mismatch_does_not_erase_price(self):
        payload = one_shipment()
        payload["files"]["carrier-invoices.json"][0]["carrier_id"] = "OTHER-CARRIER"
        result, _ = self.review(payload)
        shipment = result["outputs"]["shipments"][0]
        self.assertEqual(shipment["issue_codes"], ["carrier-mismatch"])
        self.assertEqual(shipment["expected_amount"], "440.00")
        self.assertIsNone(shipment["variance_amount"])

    def test_currency_mismatch_is_held_without_mixed_billed_amount(self):
        payload = one_shipment()
        payload["files"]["carrier-invoices.json"][0]["currency"] = "EUR"
        result, _ = self.review(payload)
        shipment = result["outputs"]["shipments"][0]
        self.assertEqual(shipment["issue_codes"], ["currency-mismatch"])
        self.assertIsNone(shipment["billed_amount"])
        self.assertEqual(shipment["expected_amount"], "440.00")
        self.assertIsNone(shipment["variance_amount"])
        currencies = {row["currency"]: row for row in result["outputs"]["summary"]["currency_totals"]}
        self.assertEqual(currencies["EUR"]["billed_total"], "440.00")
        self.assertEqual(currencies["USD"]["billed_total"], "0.00")
        self.assertTrue(all(row["known_expected"] == "0.00" for row in currencies.values()))
        self.assertTrue(all(not row["comparison_complete"] for row in currencies.values()))

    def test_valid_multiple_currencies_have_independent_totals(self):
        payload = many_shipments(2)
        files = payload["files"]
        files["shipments.json"][1]["currency"] = "EUR"
        files["rate-cards.json"].append(dict(files["rate-cards.json"][0], rate_id="TEST-EUR-RATE", currency="EUR"))
        files["carrier-invoices.json"].append(dict(files["carrier-invoices.json"][0], invoice_id="TEST-EUR-INVOICE", currency="EUR"))
        for line in files["invoice-lines.json"]:
            if line["shipment_id"] == "TEST-S-001":
                line["invoice_id"] = "TEST-EUR-INVOICE"
        balance_headers(payload)
        result, _ = self.review(payload)
        self.assertEqual(result["status"], "completed")
        totals = result["outputs"]["summary"]["currency_totals"]
        self.assertEqual([row["currency"] for row in totals], ["EUR", "USD"])
        self.assertTrue(all(row["billed_total"] == row["known_expected"] == "440.00" for row in totals))
        self.assertTrue(all(row["comparison_complete"] for row in totals))

    def test_prior_case_state_matrix_including_insufficient_evidence(self):
        payload = read_case("demo")
        history = payload["files"]["review-history.json"]
        base = dict(history[0], owner="test-review", updated_at="2026-09-14T11:00:00Z")
        history.extend([
            dict(base, case_id="TEST-D03-VAR", shipment_id="LG-D03", issue_code="variance", state="resolved"),
            dict(base, case_id="TEST-D03-POD", shipment_id="LG-D03", issue_code="missing-pod", state="evidence-requested"),
            dict(base, case_id="TEST-D04-VAR", shipment_id="LG-D04", issue_code="variance", state="resolved"),
            dict(base, case_id="TEST-D01-VAR", shipment_id="LG-D01", issue_code="variance", state="open"),
            dict(base, case_id="TEST-D01-FUTURE", shipment_id="LG-D01", issue_code="missing-pod",
                 state="open", updated_at="2026-09-14T12:00:01Z"),
        ])
        result, _ = self.review(payload)
        proposals = {row["case_id"]: (row["proposed_state"], row["reason"]) for row in result["outputs"]["case_proposals"]}
        self.assertEqual(proposals, {
            "LG-CASE-D02-VAR": ("reopened", "condition-present"),
            "LG-CASE-D04-POD": ("closed", "condition-cleared"),
            "TEST-D03-VAR": ("deferred", "insufficient-evidence"),
            "TEST-D03-POD": ("still-open", "condition-present"),
            "TEST-D04-VAR": ("remains-resolved", "condition-cleared"),
            "TEST-D01-VAR": ("closed", "condition-cleared"),
            "TEST-D01-FUTURE": ("deferred", "future-history"),
        })

    def test_unknown_or_ambiguous_history_never_arbitrarily_closes(self):
        payload = one_shipment()
        history = payload["files"]["review-history.json"]
        original = history[0]
        history.extend([
            dict(original, case_id="TEST-DUPLICATE-CASE"),
            dict(original, case_id="TEST-FUTURE-CASE", updated_at="2026-09-14T12:00:01Z"),
            dict(original, case_id="TEST-UNKNOWN-ISSUE", issue_code="not-a-supported-condition"),
            dict(original, case_id="TEST-ORPHAN-CASE", shipment_id="UNKNOWN-SHIPMENT"),
        ])
        result, _ = self.review(payload)
        proposals = {row["case_id"]: (row["proposed_state"], row["reason"]) for row in result["outputs"]["case_proposals"]}
        self.assertEqual(proposals[original["case_id"]], ("held", "ambiguous-history"))
        self.assertEqual(proposals["TEST-DUPLICATE-CASE"], ("held", "ambiguous-history"))
        self.assertEqual(proposals["TEST-FUTURE-CASE"], ("deferred", "future-history"))
        self.assertEqual(proposals["TEST-UNKNOWN-ISSUE"], ("held", "unsupported-issue"))
        self.assertEqual(proposals["TEST-ORPHAN-CASE"], ("held", "missing-shipment"))
        self.assertEqual(result["outputs"]["shipments"][0]["disposition"], "ready-for-review")
        self.assertEqual(len(result["exceptions"]), 4)
        self.assertTrue(all(row["owner"] == original["owner"] for row in result["exceptions"]))

    def test_replaced_evidence_obstacle_does_not_falsely_clear_prior_condition(self):
        payload = one_shipment()
        case = payload["files"]["review-history.json"][0]
        case["issue_code"] = "contradictory-pod"
        payload["files"]["pod-events.json"] = []
        result, _ = self.review(payload)
        self.assertEqual(result["outputs"]["case_proposals"][0]["proposed_state"], "deferred")
        payload = one_shipment()
        payload["files"]["review-history.json"][0]["issue_code"] = "missing-rate"
        rate = payload["files"]["rate-cards.json"][0]
        payload["files"]["rate-cards.json"].append(dict(rate, rate_id="TEST-OVERLAP"))
        result, _ = self.review(payload)
        self.assertEqual(result["outputs"]["case_proposals"][0]["proposed_state"], "deferred")

    def test_invalid_money_forms_reject_including_nonfinite_strings(self):
        for amount in (12, True, 12.0, "12oops", "NaN", "Infinity", "-0.01", "1e2", "1.0", "00.01",
                       "1000000000000.00", " 1.00", "1.00 ", "١.00"):
            with self.subTest(amount=amount):
                payload = one_shipment()
                payload["files"]["invoice-lines.json"][0]["amount"] = amount
                result, _ = self.review(payload)
                self.assertEqual(result["status"], "rejected")
                self.assertEqual(result["exceptions"][0]["code"], "invalid-amount")

    def test_invalid_fields_types_enums_and_boundaries_reject(self):
        edits = [
            ("shipments.json", "shipped_units", True, "invalid-integer"),
            ("shipments.json", "shipped_units", 0, "invalid-integer"),
            ("shipments.json", "shipped_units", 1_000_000_001, "invalid-integer"),
            ("shipments.json", "shipment_id", " leading-space", "invalid-id"),
            ("shipments.json", "currency", "usd", "invalid-currency"),
            ("rate-cards.json", "free_wait_minutes", -1, "invalid-integer"),
            ("rate-cards.json", "detention_block_minutes", 0, "invalid-integer"),
            ("rate-cards.json", "fuel_fraction", "0.1234567890", "invalid-fraction"),
            ("rate-cards.json", "fuel_fraction", "1000000", "invalid-fraction"),
            ("rate-cards.json", "fuel_fraction", "-0.10", "invalid-fraction"),
            ("rate-cards.json", "valid_to", "2026-02-30", "invalid-date"),
            ("pod-events.json", "state", "delivered-ish", "invalid-enum"),
            ("pod-events.json", "delivered_units", None, "invalid-integer"),
            ("invoice-lines.json", "charge_code", "tax", "invalid-enum"),
            ("review-history.json", "state", "paid", "invalid-enum"),
        ]
        for export, field, value, code in edits:
            with self.subTest(export=export, field=field, value=value):
                payload = one_shipment()
                payload["files"][export][0][field] = value
                result, _ = self.review(payload)
                self.assertEqual(result["status"], "rejected")
                self.assertIn(code, [row["code"] for row in result["exceptions"]])

    def test_naive_fractional_invalid_or_unrepresentable_timestamps_reject(self):
        for instant in (
            "2026-09-14T12:00:00", "2026-09-14T12:00:00.001Z", "2026-09-14T12:00:60Z",
            "2026-09-14T12:00:00+24:00", "2026-09-14T12:00:00+01:60",
            "0001-01-01T00:00:00+01:00", "9999-12-31T23:59:59-01:00",
        ):
            with self.subTest(instant=instant):
                payload = one_shipment()
                payload["config"]["as_of"] = instant
                result, _ = self.review(payload)
                self.assertEqual(result["status"], "rejected")
                self.assertEqual(result["exceptions"][0]["code"], "invalid-instant")

    def test_invalid_row_time_order_and_date_ranges_reject(self):
        payload = one_shipment()
        payload["files"]["pod-events.json"][0]["gate_out_at"] = "2026-09-14T11:00:00Z"
        result, _ = self.review(payload)
        self.assertEqual(result["exceptions"][0]["code"], "invalid-time-order")
        payload = one_shipment()
        payload["files"]["rate-cards.json"][0]["valid_to"] = "2026-09-01"
        result, _ = self.review(payload)
        self.assertEqual(result["exceptions"][0]["code"], "invalid-date-range")
        payload = one_shipment()
        payload["files"]["pod-events.json"][0]["state"] = "void"
        result, _ = self.review(payload)
        self.assertTrue(all(row["code"] == "invalid-null" for row in result["exceptions"]))

    def test_unknown_missing_keys_and_nonarray_exports_reject(self):
        variants = []
        payload = one_shipment()
        payload["surprise"] = {}
        variants.append(payload)
        payload = one_shipment()
        payload["config"]["secret-policy"] = 7
        variants.append(payload)
        payload = one_shipment()
        del payload["files"]["shipments.json"][0]["shipped_units"]
        variants.append(payload)
        payload = one_shipment()
        payload["files"]["rate-cards.json"][0]["another-cap"] = "1.00"
        variants.append(payload)
        payload = one_shipment()
        payload["files"]["pod-events.json"] = {}
        variants.append(payload)
        payload = one_shipment()
        del payload["files"]["review-history.json"]
        variants.append(payload)
        for payload in variants:
            with self.subTest(payload=payload):
                result, _ = self.review(payload)
                self.assertEqual(result["status"], "rejected")
                self.assertIn("invalid-schema", [row["code"] for row in result["exceptions"]])

    def test_malformed_future_evidence_is_not_excused_by_snapshot_exclusion(self):
        payload = one_shipment("holdout-b", "LG-B01")
        payload["files"]["pod-events.json"][0]["delivered_units"] = True
        result, _ = self.review(payload)
        self.assertEqual(result["status"], "rejected")
        self.assertIn("invalid-integer", [row["code"] for row in result["exceptions"]])

    def test_zero_amount_hold_is_not_suppressed(self):
        payload = one_shipment()
        payload["files"]["pod-events.json"] = []
        for line in payload["files"]["invoice-lines.json"]:
            line["amount"] = "0.00"
        balance_headers(payload)
        result, _ = self.review(payload)
        self.assertEqual(result["status"], "completed_with_exceptions")
        self.assertEqual(result["outputs"]["shipments"][0]["disposition"], "held")
        self.assertIsNone(result["outputs"]["shipments"][0]["expected_amount"])
        self.assertFalse(result["outputs"]["summary"]["currency_totals"][0]["comparison_complete"])


class SharedAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scenario = load_scenario(ROOT)
        golden_lock(cls.scenario)
        cls.workspace = ROOT / "validation" / ("cli-checks-" + uuid.uuid4().hex)
        cls.workspace.mkdir(parents=True)
        cls.addClassCleanup(shutil.rmtree, cls.workspace)

    def destinations(self):
        folder = self.workspace / uuid.uuid4().hex
        folder.mkdir()
        return folder / "input.json", folder / "result.json", folder / "trace.json"

    def invoke(self, source, output, trace):
        return subprocess.run([
            sys.executable, "-B", "-I", str(ROOT / "baseline.py"),
            "--input", str(source), "--output", str(output), "--trace", str(trace),
        ], cwd=ROOT, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=20, check=False)

    def test_shared_cli_valid_result_and_trace_bind_to_input(self):
        source, output, trace = self.destinations()
        content = (ROOT / "mock-data" / "demo.json").read_bytes()
        source.write_bytes(content)
        process = self.invoke(source, output, trace)
        self.assertEqual(process.returncode, 0, process.stderr)
        result, observed = json.loads(output.read_text()), json.loads(trace.read_text())
        reference = json.loads((ROOT / "expected" / "demo.json").read_text())
        self.assertEqual(compare_json(reference, result), [])
        validate_trace(observed, self.scenario, self.scenario.case("demo"), hashlib.sha256(content).hexdigest())
        self.assertEqual(source.read_bytes(), content)

    def test_existing_result_is_not_overwritten_and_trace_not_created(self):
        source, output, trace = self.destinations()
        source.write_bytes((ROOT / "mock-data" / "demo.json").read_bytes())
        output.write_bytes(b"existing result sentinel")
        process = self.invoke(source, output, trace)
        self.assertEqual(process.returncode, 2)
        self.assertIn("refuses existing outputs", process.stderr)
        self.assertEqual(output.read_bytes(), b"existing result sentinel")
        self.assertFalse(trace.exists())

    def test_existing_trace_is_not_overwritten_and_result_not_created(self):
        source, output, trace = self.destinations()
        source.write_bytes((ROOT / "mock-data" / "demo.json").read_bytes())
        trace.write_bytes(b"existing trace sentinel")
        process = self.invoke(source, output, trace)
        self.assertEqual(process.returncode, 2)
        self.assertIn("refuses existing outputs", process.stderr)
        self.assertEqual(trace.read_bytes(), b"existing trace sentinel")
        self.assertFalse(output.exists())

    def test_input_output_trace_aliases_are_refused(self):
        for alias in ("input-result", "input-trace", "result-trace"):
            with self.subTest(alias=alias):
                source, output, trace = self.destinations()
                content = (ROOT / "mock-data" / "demo.json").read_bytes()
                source.write_bytes(content)
                actual_output = source if alias == "input-result" else output
                actual_trace = source if alias == "input-trace" else output if alias == "result-trace" else trace
                process = self.invoke(source, actual_output, actual_trace)
                self.assertEqual(process.returncode, 2)
                self.assertIn("must be distinct", process.stderr)
                self.assertEqual(source.read_bytes(), content)
                self.assertFalse(output.exists())
                self.assertFalse(trace.exists())

    def test_malformed_deep_duplicate_nonfinite_and_nonobject_json_fail_as_files(self):
        invalid = [
            b'{"config":', b"\xff", b"[]", b"null",
            b'{"config":{},"config":{},"files":{}}',
            b'{"config":{"as_of":"a","as_of":"b"},"files":{}}',
            b'{"value":NaN}', b'{"value":Infinity}', b'{"value":-Infinity}',
            b'{"value":1e999}',
            (b'{"nested":' * 82) + b"0" + (b"}" * 82),
        ]
        for content in invalid:
            with self.subTest(content=content[:70]):
                source, output, trace = self.destinations()
                source.write_bytes(content)
                process = self.invoke(source, output, trace)
                self.assertEqual(process.returncode, 2, process.stderr)
                self.assertIn("Baseline failed:", process.stderr)
                self.assertFalse(output.exists())
                self.assertFalse(trace.exists())
                self.assertEqual(source.read_bytes(), content)

    def test_oversized_json_file_fails_before_business_validation(self):
        source, output, trace = self.destinations()
        source.write_bytes(b"{}" + b" " * (8 * 1024 * 1024))
        process = self.invoke(source, output, trace)
        self.assertEqual(process.returncode, 2)
        self.assertIn("exceeds 8 MiB", process.stderr)
        self.assertFalse(output.exists())
        self.assertFalse(trace.exists())

    def test_shared_cli_business_negative_is_exit_zero_not_infrastructure_failure(self):
        source, output, trace = self.destinations()
        source.write_bytes((ROOT / "mock-data" / "negative-malformed.json").read_bytes())
        process = self.invoke(source, output, trace)
        self.assertEqual(process.returncode, 0, process.stderr)
        result = json.loads(output.read_text())
        reference = json.loads((ROOT / "expected" / "negative-malformed.json").read_text())
        self.assertEqual(compare_json(reference, result), [])
        self.assertEqual([event["kind"] for event in json.loads(trace.read_text())["events"]], ["input", "validation"])


if __name__ == "__main__":
    unittest.main()
