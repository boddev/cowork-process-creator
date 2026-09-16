"""Targeted stdlib tests for the independently specified AP scenario."""
import importlib.util
import json
import random
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from scenarios._shared.comparison import compare_json
from scenarios._shared.contract import baseline_import_audit, load_scenario
from scenarios._shared.pipeline import check_case_evidence, golden_lock


ROOT = Path(__file__).resolve().parents[1] / "financial-services" / "ap-three-way-match"
SPEC = importlib.util.spec_from_file_location("financial_ap_baseline", ROOT / "baseline.py")
BASELINE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BASELINE)


def fixture(case):
    return json.loads((ROOT / "mock-data" / (case + ".json")).read_text(encoding="utf-8"))


def simple(quantity=1000, price=1000, po_price=None, capacity=None):
    payload = fixture("negative-contradictory")
    payload["historical_invoices"] = []
    payload["prior_allocations"] = []
    invoice = payload["invoices"][0]
    line = invoice["lines"][0]
    # Test setup uses exact integer HALF_UP, independently of any baseline helper.
    net = (quantity * price + 500) // 1000
    invoice["header_net_minor"] = net
    line.update(quantity_milliunits=quantity, unit_price_minor=price, line_net_minor=net)
    payload["po_lines"][0].update(
        ordered_milliunits=quantity if capacity is None else capacity,
        unit_price_minor=price if po_price is None else po_price,
    )
    payload["receipt_lines"][0]["quantity_milliunits"] = quantity if capacity is None else capacity
    return payload


def add_invoice(payload, identifier, quantity=None, number=None, po_id=None, receipt_id=None):
    invoice = deepcopy(payload["invoices"][0])
    invoice.update(invoice_id=identifier, vendor_invoice_number=number or identifier)
    invoice["lines"] = [invoice["lines"][0]]
    line = invoice["lines"][0]
    if quantity is not None:
        line["quantity_milliunits"] = quantity
        line["line_net_minor"] = (quantity * line["unit_price_minor"] + 500) // 1000
    if po_id is not None:
        line["po_id"] = po_id
    line.pop("selected_receipts", None)
    if receipt_id is not None:
        line["selected_receipts"] = [{"receipt_line_id": receipt_id, "quantity_milliunits": line["quantity_milliunits"]}]
    invoice["header_net_minor"] = line["line_net_minor"]
    payload["invoices"].append(invoice)
    return invoice


def add_resource(payload, po_id, receipt_id, capacity=1000, price=1000):
    po = deepcopy(payload["po_lines"][0])
    po.update(po_id=po_id, ordered_milliunits=capacity, unit_price_minor=price)
    receipt = deepcopy(payload["receipt_lines"][0])
    receipt.update(po_id=po_id, receipt_line_id=receipt_id, quantity_milliunits=capacity)
    payload["po_lines"].append(po)
    payload["receipt_lines"].append(receipt)
    return po, receipt


def add_history(payload, quantity=250, number="SYN-PRIOR-01", posted="2026-09-09T09:00:00Z",
                recorded="2026-09-10T09:00:00Z"):
    po = payload["po_lines"][0]
    history = {
        "historical_invoice_id": "SYN-HISTORY-01", "legal_entity_id": po["legal_entity_id"],
        "vendor_id": po["vendor_id"], "currency": po["currency"], "vendor_invoice_number": number,
        "status": "posted", "posted_at": posted,
    }
    allocation = {
        "allocation_id": "SYN-ALLOCATION-01", "historical_invoice_id": history["historical_invoice_id"],
        "legal_entity_id": po["legal_entity_id"], "po_id": po["po_id"], "po_line_id": po["po_line_id"],
        "receipt_line_id": payload["receipt_lines"][0]["receipt_line_id"],
        "quantity_milliunits": quantity, "recorded_at": recorded,
    }
    payload["historical_invoices"].append(history)
    payload["prior_allocations"].append(allocation)
    return history, allocation


class FinancialAPTests(unittest.TestCase):
    def solve(self, payload):
        original = deepcopy(payload)
        result, events = BASELINE.solve(payload)
        # JSON handles NaN fixtures consistently without treating NaN != NaN as mutation.
        self.assertEqual(json.dumps(payload, sort_keys=True), json.dumps(original, sort_keys=True))
        self.assertEqual(result["outputs"]["review"],
                         {"human_review": "pending", "live_action": "none", "owner_role": "AP manager"})
        return result, events

    def rejected(self, payload, code):
        result, events = self.solve(payload)
        self.assertEqual(result["status"], "rejected")
        self.assertEqual(set(result["outputs"]), {"review"})
        self.assertEqual([row["code"] for row in result["exceptions"]], [code])
        self.assertEqual([event["kind"] for event in events], ["input", "validation", "output"])
        return result

    def ready(self, payload):
        result, _ = self.solve(payload)
        self.assertNotEqual(result["status"], "rejected")
        self.assertTrue(all(row["status"] == "ready-for-review" for row in result["outputs"]["invoice_reviews"]))
        return result

    def held(self, payload, code):
        result, _ = self.solve(payload)
        self.assertEqual(result["status"], "completed_with_exceptions")
        review = result["outputs"]["invoice_reviews"][0]
        self.assertEqual(review["status"], "held")
        self.assertIn(code, review["reason_codes"])
        self.assertEqual(review["proposed_net_minor"], 0)
        return result

    def assert_conservation(self, result):
        if result["status"] == "rejected":
            self.assertEqual(set(result["outputs"]), {"review"})
            return
        outputs = result["outputs"]
        allocations = outputs["proposed_allocations"]
        reviews = {row["invoice_id"]: row for row in outputs["invoice_reviews"]}
        for row in outputs["line_comparisons"]:
            assigned = sum(a["quantity_milliunits"] for a in allocations
                           if (a["invoice_id"], a["line_id"]) == (row["invoice_id"], row["line_id"]))
            self.assertEqual(assigned, row["proposed_quantity_milliunits"])
            if reviews[row["invoice_id"]]["status"] == "held":
                self.assertEqual(assigned, 0)
                self.assertEqual(row["status"], "held")
            else:
                self.assertEqual(assigned, row["quantity_milliunits"])
        for row in outputs["remaining_capacity"]["receipts"]:
            assigned = sum(a["quantity_milliunits"] for a in allocations if a["receipt_line_id"] == row["receipt_line_id"])
            self.assertEqual(assigned, row["proposed_milliunits"])
            self.assertEqual(row["before_proposals_milliunits"], assigned + row["remaining_milliunits"])
            if row["available_at_as_of"]:
                self.assertEqual(row["quantity_milliunits"],
                                 row["historical_used_milliunits"] + assigned + row["remaining_milliunits"])
            else:
                self.assertEqual(row["before_proposals_milliunits"], 0)
                self.assertEqual(row["historical_used_milliunits"], 0)
            self.assertGreaterEqual(row["remaining_milliunits"], 0)
        for row in outputs["remaining_capacity"]["po_lines"]:
            assigned = sum(a["quantity_milliunits"] for a in allocations
                           if all(a[key] == row[key] for key in ("legal_entity_id", "po_id", "po_line_id")))
            self.assertEqual(assigned, row["proposed_milliunits"])
            self.assertEqual(row["ordered_milliunits"],
                             row["historical_used_milliunits"] + assigned + row["remaining_milliunits"])
            self.assertGreaterEqual(row["remaining_milliunits"], 0)
        for row in outputs["summary"]:
            self.assertEqual(row["intake_net_minor"], row["ready_net_minor"] + row["held_net_minor"])
            self.assertEqual(row["invoice_count"], row["ready_invoice_count"] + row["held_invoice_count"])
        self.assertEqual(len(allocations), len({(a["invoice_id"], a["line_id"], a["receipt_line_id"]) for a in allocations}))

    def test_all_five_independent_full_envelopes_and_conservation(self):
        scenario = load_scenario(ROOT)
        golden_lock(scenario)
        for case in scenario.cases:
            with self.subTest(case=case["id"]):
                result, _ = self.solve(fixture(case["id"]))
                expected = json.loads(scenario.file(case["expected"]).read_text(encoding="utf-8"))
                self.assertEqual(compare_json(expected, result), [])
                self.assert_conservation(result)

    def test_persisted_case_evidence_and_import_audit(self):
        scenario = load_scenario(ROOT)
        self.assertEqual(baseline_import_audit(ROOT / "baseline.py")["status"], "static_import_check_pass")
        for case in scenario.cases:
            with self.subTest(case=case["id"]):
                self.assertEqual(check_case_evidence(scenario, case)["state"], "baseline_pass")

    def test_bool_float_string_null_and_nonfinite_quantities_rejected(self):
        for value in (True, False, 1000.0, "1000", None, float("nan"), float("inf"), -1, 0, 1_000_000_001):
            with self.subTest(value=value):
                payload = simple()
                payload["invoices"][0]["lines"][0]["quantity_milliunits"] = value
                self.rejected(payload, "invalid-integer")

    def test_true_integer_money_and_control_bounds(self):
        for field in ("unit_price_minor", "line_net_minor"):
            for value in (True, 1.0, "1", None, -1, 1_000_000_000_001):
                with self.subTest(field=field, value=value):
                    payload = simple()
                    payload["invoices"][0]["lines"][0][field] = value
                    self.rejected(payload, "invalid-integer")
        for field, value in (("unit_tolerance_bps", True), ("unit_tolerance_bps", 10001),
                             ("line_amount_cap_minor", "500"), ("max_rows_per_source", 0),
                             ("max_rows_per_source", 5001)):
            with self.subTest(field=field, value=value):
                payload = simple()
                payload["controls"][field] = value
                self.rejected(payload, "invalid-integer")

    def test_finite_maxima_and_positive_minimum_quantity(self):
        for quantity, price in ((1, 0), (1_000_000_000, 0), (1000, 1_000_000_000_000)):
            with self.subTest(quantity=quantity, price=price):
                payload = simple(quantity, price)
                payload["controls"].update(unit_tolerance_bps=10000, line_amount_cap_minor=1_000_000_000_000)
                self.assert_conservation(self.ready(payload))

    def test_half_up_fractional_rounding(self):
        result = self.ready(simple(1250, 1002, 1000))
        line = result["outputs"]["line_comparisons"][0]
        self.assertEqual(line["calculated_line_net_minor"], 1253)
        self.assertEqual(line["price"]["po_line_net_minor"], 1250)
        self.assertEqual(line["price"]["line_difference_minor"], 3)

    def test_round_each_line_not_aggregate_quantity(self):
        payload = simple(500, 1, capacity=1000)
        invoice = payload["invoices"][0]
        line = deepcopy(invoice["lines"][0])
        line["line_id"] = "SYN-LINE-02"
        invoice["lines"].append(line)
        invoice["header_net_minor"] = 2
        result = self.ready(payload)
        self.assertEqual([line["calculated_line_net_minor"] for line in result["outputs"]["line_comparisons"]], [1, 1])
        self.assert_conservation(result)

    def test_symmetric_unit_tolerance_inclusive_and_outside(self):
        for price in (9800, 10200):
            with self.subTest(price=price):
                self.ready(simple(1000, price, 10000))
        for price in (9799, 10201):
            with self.subTest(price=price):
                self.held(simple(1000, price, 10000), "unit-price-out-of-tolerance")

    def test_amount_cap_is_inclusive_and_independent_of_percentage(self):
        self.ready(simple(50000, 1010, 1000))
        result = self.held(simple(50100, 1010, 1000), "line-amount-out-of-tolerance")
        line = result["outputs"]["line_comparisons"][0]
        self.assertTrue(line["price"]["unit_price_pass"])
        self.assertEqual(line["price"]["line_difference_minor"], 501)

    def test_configured_zero_tolerances_and_zero_price(self):
        self.ready(simple(1000, 0))
        result = self.held(simple(1, 1, 0), "zero-price-mismatch")
        self.assertEqual(result["outputs"]["line_comparisons"][0]["individual_reason_codes"], ["zero-price-mismatch"])
        self.assertTrue(result["outputs"]["line_comparisons"][0]["price"]["line_cap_pass"])
        payload = simple(1000, 1001, 1000)
        payload["controls"].update(unit_tolerance_bps=0, line_amount_cap_minor=0)
        result = self.held(payload, "unit-price-out-of-tolerance")
        self.assertIn("line-amount-out-of-tolerance", result["outputs"]["invoice_reviews"][0]["reason_codes"])

    def test_header_and_line_consistency_reject_before_business_holds(self):
        payload = simple()
        payload["invoices"][0]["header_net_minor"] += 1
        self.rejected(payload, "header-net-inconsistent")
        payload["invoices"][0]["lines"][0]["line_net_minor"] += 1
        self.rejected(payload, "line-net-inconsistent")

    def test_each_unsupported_component_preserved_and_formula_skipped(self):
        for location in ("header", "line"):
            for field in ("tax_minor", "charges_minor", "discounts_minor", "freight_minor"):
                with self.subTest(location=location, field=field):
                    payload = simple()
                    invoice = payload["invoices"][0]
                    target = invoice if location == "header" else invoice["lines"][0]
                    target["components"] = {field: 17}
                    invoice["header_net_minor"] = 1017
                    invoice["lines"][0]["line_net_minor"] = 1017
                    result = self.held(payload, "unsupported-components")
                    output = result["outputs"]
                    observed = output["invoice_reviews"][0] if location == "header" else output["line_comparisons"][0]
                    self.assertEqual(observed["components"][field], 17)
                    self.assertIsNone(output["line_comparisons"][0]["calculated_line_net_minor"])
                    self.assertTrue(all(value is None for value in output["line_comparisons"][0]["price"].values()))
                    self.assertEqual(output["summary"][0]["held_net_minor"], 1017)
                    self.assertEqual(output["proposed_allocations"], [])
        payload["invoices"][0]["header_net_minor"] = 1018
        self.rejected(payload, "header-net-inconsistent")

    def test_nonzero_component_skips_formula_for_whole_invoice_not_only_its_line(self):
        payload = simple(capacity=2000)
        invoice = payload["invoices"][0]
        sibling = deepcopy(invoice["lines"][0])
        sibling.update(line_id="SYN-LINE-02", line_net_minor=1020)
        sibling["components"] = {"tax_minor": 20}
        invoice["lines"][0]["line_net_minor"] = 999
        invoice["lines"].append(sibling)
        invoice["header_net_minor"] = 2019
        result = self.held(payload, "unsupported-components")
        self.assertTrue(all(row["calculated_line_net_minor"] is None for row in result["outputs"]["line_comparisons"]))

    def test_duplicate_primary_keys_even_identical_rows(self):
        for source in ("invoices", "po_lines", "receipt_lines", "historical_invoices", "prior_allocations",
                       "invoice-lines", "selected-receipts"):
            with self.subTest(source=source):
                payload = fixture("demo")
                if source == "invoice-lines":
                    rows = payload["invoices"][0]["lines"]
                elif source == "selected-receipts":
                    rows = payload["invoices"][0]["lines"][0]["selected_receipts"]
                else:
                    rows = payload[source]
                rows.append(deepcopy(rows[0]))
                self.rejected(payload, "duplicate-primary-key")

    def test_ascii_canonical_duplicates_hold_all(self):
        payload = simple(capacity=2000)
        payload["invoices"][0]["vendor_invoice_number"] = "\t  syn-00.12/a \r"
        add_invoice(payload, "SYN-SECOND", number="SYN-00.12/A")
        result = self.held(payload, "duplicate-incoming-invoice")
        self.assertEqual([row["canonical_vendor_invoice_number"] for row in result["outputs"]["invoice_reviews"]],
                         ["SYN-00.12/A", "SYN-00.12/A"])
        self.assertTrue(all(row["status"] == "held" for row in result["outputs"]["invoice_reviews"]))
        self.assertEqual(result["outputs"]["capacity_conflicts"], [])
        self.assertEqual(result["outputs"]["proposed_allocations"], [])

    def test_punctuation_and_leading_zeros_are_not_removed(self):
        for other in ("SYN-01", "SYN-0.01", "SYN-00 1"):
            with self.subTest(other=other):
                payload = simple(capacity=2000)
                payload["invoices"][0]["vendor_invoice_number"] = "SYN-001"
                add_invoice(payload, "SYN-SECOND", number=other)
                self.assert_conservation(self.ready(payload))

    def test_duplicate_key_ignores_currency_but_not_vendor_or_entity(self):
        payload = simple(capacity=2000)
        duplicate = add_invoice(payload, "SYN-SECOND", number=payload["invoices"][0]["vendor_invoice_number"])
        duplicate["currency"] = "EUR"
        result = self.held(payload, "duplicate-incoming-invoice")
        self.assertTrue(all("duplicate-incoming-invoice" in row["reason_codes"] for row in result["outputs"]["invoice_reviews"]))
        for field in ("vendor_id", "legal_entity_id"):
            with self.subTest(field=field):
                clone = deepcopy(payload)
                clone["invoices"][1][field] = "SYN-OTHER"
                result, _ = self.solve(clone)
                self.assertTrue(all(not row["duplicate_invoice_ids"] for row in result["outputs"]["invoice_reviews"]))

    def test_posted_history_duplicate_and_technical_vs_business_identity(self):
        payload = simple(capacity=1250)
        add_history(payload, 250, "  syn-cap-001 ")
        result = self.held(payload, "duplicate-posted-invoice")
        self.assertEqual(result["outputs"]["invoice_reviews"][0]["duplicate_historical_invoice_ids"], ["SYN-HISTORY-01"])
        self.assertEqual(result["outputs"]["proposed_allocations"], [])

    def test_strict_synthetic_ids_and_ascii_vendor_numbers(self):
        for value in ("syn-bad", "SYN-X ", "SYN-é", "OTHER", "", "SYN-" + "X" * 61):
            with self.subTest(value=value):
                payload = simple()
                payload["invoices"][0]["vendor_id"] = value
                self.rejected(payload, "invalid-identifier")
        for value in ("SYN-\u00a0A", "\u00a0SYN-A", "SYN-A\tB", True, "", "SYN-"):
            with self.subTest(value=value):
                payload = simple()
                payload["invoices"][0]["vendor_invoice_number"] = value
                self.rejected(payload, "invalid-invoice-number")

    def test_exact_invoice_po_vendor_currency_unit_entity_joins(self):
        for field, value in (("vendor_id", "SYN-OTHER"), ("currency", "EUR"), ("unit", "BOX"),
                             ("legal_entity_id", "SYN-OTHER"), ("po_id", "SYN-MISSING")):
            with self.subTest(field=field):
                payload = simple()
                target = payload["invoices"][0]["lines"][0] if field in ("unit", "po_id") else payload["invoices"][0]
                target[field] = value
                code = "po-not-found" if field in ("legal_entity_id", "po_id") else "po-scope-mismatch"
                result = self.held(payload, code)
                self.assertTrue(all(value is None for value in result["outputs"]["line_comparisons"][0]["price"].values()))
                self.assertEqual(result["outputs"]["proposed_allocations"], [])

    def test_authoritative_receipt_scope_and_time_contradictions(self):
        for field, value in (("vendor_id", "SYN-OTHER"), ("currency", "EUR"), ("unit", "BOX"),
                             ("po_id", "SYN-MISSING")):
            with self.subTest(field=field):
                payload = simple()
                payload["receipt_lines"][0][field] = value
                self.rejected(payload, "receipt-po-inconsistent")
        payload = simple()
        payload["receipt_lines"][0]["received_at"] = "2026-09-08T10:00:00Z"
        self.rejected(payload, "receipt-time-inconsistent")

    def test_multiple_positive_receipts_always_require_selection(self):
        payload = simple(capacity=2000)
        extra = deepcopy(payload["receipt_lines"][0])
        extra.update(receipt_line_id="SYN-EXTRA-R", quantity_milliunits=1)
        payload["receipt_lines"].append(extra)
        result = self.held(payload, "receipt-selection-required")
        self.assertEqual(result["outputs"]["line_comparisons"][0]["receipts"]["shortage_milliunits"], 0)
        self.assertEqual(result["outputs"]["line_comparisons"][0]["receipts"]["selections"], [])

    def test_partial_explicit_receipts_and_leftover_capacity(self):
        payload = simple(capacity=1100)
        payload["receipt_lines"][0]["quantity_milliunits"] = 600
        extra = deepcopy(payload["receipt_lines"][0])
        extra.update(receipt_line_id="SYN-SECOND-R", quantity_milliunits=500)
        payload["receipt_lines"].append(extra)
        payload["invoices"][0]["lines"][0]["selected_receipts"] = [
            {"receipt_line_id": payload["receipt_lines"][0]["receipt_line_id"], "quantity_milliunits": 600},
            {"receipt_line_id": extra["receipt_line_id"], "quantity_milliunits": 400},
        ]
        result = self.ready(payload)
        self.assertEqual([row["quantity_milliunits"] for row in result["outputs"]["proposed_allocations"]], [600, 400])
        self.assertEqual([row["remaining_milliunits"] for row in result["outputs"]["remaining_capacity"]["receipts"]], [0, 100])
        self.assert_conservation(result)

    def test_explicit_selection_sum_missing_mismatch_unavailable_and_shortage(self):
        for mode, code in (
            ("empty", "selection-quantity-mismatch"), ("sum", "selection-quantity-mismatch"),
            ("missing", "selected-receipt-missing"), ("scope", "selected-receipt-scope-mismatch"),
            ("future", "selected-receipt-unavailable"), ("short", "selected-receipt-shortage"),
        ):
            with self.subTest(mode=mode):
                payload = simple()
                rid = payload["receipt_lines"][0]["receipt_line_id"]
                selections = [{"receipt_line_id": rid, "quantity_milliunits": 1000}]
                if mode == "empty":
                    selections = []
                elif mode == "sum":
                    selections[0]["quantity_milliunits"] = 999
                elif mode == "missing":
                    selections[0]["receipt_line_id"] = "SYN-MISSING"
                elif mode == "scope":
                    add_resource(payload, "SYN-OTHER-PO", "SYN-OTHER-R")
                    selections[0]["receipt_line_id"] = "SYN-OTHER-R"
                elif mode == "future":
                    payload["receipt_lines"][0]["posted_at"] = "2026-09-15T00:00:00Z"
                elif mode == "short":
                    payload["receipt_lines"][0]["quantity_milliunits"] = 999
                payload["invoices"][0]["lines"][0]["selected_receipts"] = selections
                result = self.held(payload, code)
                self.assertEqual(result["outputs"]["proposed_allocations"], [])

    def test_exhausted_receipt_not_an_ambiguous_positive_candidate(self):
        payload = simple(capacity=2000)
        payload["receipt_lines"][0]["quantity_milliunits"] = 1000
        extra = deepcopy(payload["receipt_lines"][0])
        extra["receipt_line_id"] = "SYN-REMAINING-R"
        payload["receipt_lines"].append(extra)
        add_history(payload, 1000)
        result = self.ready(payload)
        self.assertEqual(result["outputs"]["line_comparisons"][0]["receipts"]["eligible_ids"], ["SYN-REMAINING-R"])
        self.assert_conservation(result)

    def test_global_receipt_only_conflict_holds_all_participants(self):
        payload = simple(capacity=2000)
        payload["receipt_lines"][0]["quantity_milliunits"] = 1000
        add_invoice(payload, "SYN-SECOND")
        result = self.held(payload, "receipt-capacity-conflict")
        self.assertEqual([row["resource_type"] for row in result["outputs"]["capacity_conflicts"]], ["receipt"])
        self.assertTrue(all(row["status"] == "held" for row in result["outputs"]["invoice_reviews"]))
        self.assertEqual(result["outputs"]["proposed_allocations"], [])
        self.assert_conservation(result)

    def test_global_po_only_conflict_across_different_receipts(self):
        payload = simple()
        extra = deepcopy(payload["receipt_lines"][0])
        extra["receipt_line_id"] = "SYN-SECOND-R"
        payload["receipt_lines"].append(extra)
        payload["invoices"][0]["lines"][0]["selected_receipts"] = [
            {"receipt_line_id": payload["receipt_lines"][0]["receipt_line_id"], "quantity_milliunits": 1000}
        ]
        add_invoice(payload, "SYN-SECOND", receipt_id=extra["receipt_line_id"])
        result = self.held(payload, "po-capacity-conflict")
        self.assertEqual([row["resource_type"] for row in result["outputs"]["capacity_conflicts"]], ["po-line"])
        self.assertEqual(result["outputs"]["capacity_conflicts"][0]["demand_milliunits"], 2000)
        self.assertEqual(result["outputs"]["proposed_allocations"], [])

    def test_multiline_individual_capacity_removed_before_other_invoice_competition(self):
        payload = simple(1500, capacity=2000)
        invoice = payload["invoices"][0]
        other_line = deepcopy(invoice["lines"][0])
        other_line["line_id"] = "SYN-LINE-02"
        invoice["lines"].append(other_line)
        invoice["header_net_minor"] = 3000
        add_invoice(payload, "SYN-SECOND", quantity=1000)
        result = self.held(payload, "invoice-receipt-capacity-exceeded")
        self.assertIn("invoice-po-capacity-exceeded", result["outputs"]["invoice_reviews"][0]["reason_codes"])
        self.assertEqual(result["outputs"]["invoice_reviews"][1]["status"], "ready-for-review")
        self.assertEqual(result["outputs"]["capacity_conflicts"], [])
        self.assert_conservation(result)

    def test_atomic_price_hold_does_not_block_other_invoice(self):
        payload = simple()
        add_resource(payload, "SYN-PRICE-PO", "SYN-PRICE-R")
        invoice = payload["invoices"][0]
        bad_line = deepcopy(invoice["lines"][0])
        bad_line.update(line_id="SYN-LINE-02", po_id="SYN-PRICE-PO", unit_price_minor=1100, line_net_minor=1100)
        invoice["lines"].append(bad_line)
        invoice["header_net_minor"] = 2100
        add_invoice(payload, "SYN-SECOND")
        result = self.held(payload, "unit-price-out-of-tolerance")
        self.assertEqual(result["outputs"]["invoice_reviews"][1]["status"], "ready-for-review")
        self.assertEqual(result["outputs"]["capacity_conflicts"], [])
        retained = result["outputs"]["line_comparisons"][0]
        self.assertTrue(retained["price"]["unit_price_pass"])
        self.assertEqual(retained["status"], "held")
        self.assertEqual(retained["individual_reason_codes"], [])
        self.assert_conservation(result)

    def test_no_same_run_retry_when_other_conflict_would_free_capacity(self):
        payload = simple()
        add_resource(payload, "SYN-PO-Y", "SYN-R-Y")
        invoice = payload["invoices"][0]
        second = deepcopy(invoice["lines"][0])
        second.update(line_id="SYN-LINE-02", po_id="SYN-PO-Y")
        invoice["lines"].append(second)
        invoice["header_net_minor"] = 2000
        add_invoice(payload, "SYN-SECOND")
        add_invoice(payload, "SYN-THIRD", po_id="SYN-PO-Y")
        result = self.held(payload, "receipt-capacity-conflict")
        self.assertTrue(all(row["status"] == "held" for row in result["outputs"]["invoice_reviews"]))
        self.assertEqual(len(result["outputs"]["capacity_conflicts"]), 4)
        self.assertEqual(result["outputs"]["proposed_allocations"], [])
        self.assert_conservation(result)

    def test_po_line_individual_quantity_shortage(self):
        payload = simple(capacity=2000)
        payload["po_lines"][0]["ordered_milliunits"] = 999
        self.held(payload, "po-quantity-shortage")

    def test_pending_controls_reject_while_pending_po_holds(self):
        payload = simple()
        payload["controls"]["approval_state"] = "pending"
        self.rejected(payload, "policy-not-approved")
        payload = simple()
        payload["po_lines"][0].update(approval_state="pending", approved_at=None)
        result = self.held(payload, "po-approval-pending")
        self.assertEqual(result["outputs"]["remaining_capacity"]["po_lines"][0]["remaining_milliunits"], 1000)
        self.assertTrue(result["outputs"]["line_comparisons"][0]["price"]["unit_price_pass"])

    def test_future_po_and_invoice_are_business_holds(self):
        payload = simple()
        payload["po_lines"][0]["approved_at"] = "2026-09-14T12:00:00.000001Z"
        self.held(payload, "po-approval-after-as-of")
        payload = simple()
        payload["invoices"][0]["invoice_at"] = "2026-09-14T12:00:00.000001Z"
        self.held(payload, "invoice-after-as-of")

    def test_cutoff_is_inclusive_and_not_just_business_date(self):
        payload = simple()
        payload["receipt_lines"][0]["posted_at"] = payload["as_of"]
        self.ready(payload)
        payload["receipt_lines"][0]["posted_at"] = "2026-09-14T12:00:00.000001Z"
        result = self.held(payload, "receipt-unavailable")
        self.assertEqual(result["outputs"]["excluded_receipts"][0]["code"], "receipt-posted-after-as-of")
        self.assertEqual(result["outputs"]["excluded_receipts"][0]["posted_business_date"], "2026-09-14")
        self.assert_conservation(result)

    def test_fixed_offset_business_midnight(self):
        result, _ = self.solve(fixture("holdout-b"))
        self.assertEqual(result["outputs"]["context"]["business_date"], "2026-07-31")
        self.assertEqual(result["outputs"]["excluded_receipts"][0]["posted_business_date"], "2026-08-01")
        payload = simple()
        payload["as_of"] = "2026-09-14T12:00:00+14:00"
        payload["business_utc_offset_minutes"] = -840
        self.assertEqual(self.ready(payload)["outputs"]["context"]["business_date"], "2026-09-13")
        payload["business_utc_offset_minutes"] = 840
        self.assertEqual(self.ready(payload)["outputs"]["context"]["business_date"], "2026-09-14")

    def test_timestamp_and_offset_malformed_values_reject(self):
        for value in ("2026-09-14", "2026-09-14T12:00:00", "2026-02-30T00:00:00Z",
                      "2026-09-14t12:00:00z", "2026-09-14T12:00:60Z",
                      "2026-09-14T12:00:00+14:01", "2026-09-14T12:00:00+01:99",
                      "2026-09-14T12:00:00-00:00", "2026-09-14T12:00:00.1234567Z", None):
            with self.subTest(value=value):
                payload = simple()
                payload["as_of"] = value
                self.rejected(payload, "invalid-timestamp")
        for value in (True, 0.0, "-300", None, -841, 841):
            with self.subTest(value=value):
                payload = simple()
                payload["business_utc_offset_minutes"] = value
                self.rejected(payload, "invalid-integer")

    def test_pending_receipt_excluded_and_status_timestamp_consistent(self):
        payload = simple()
        payload["receipt_lines"][0].update(status="pending", posted_at=None)
        result = self.held(payload, "receipt-unavailable")
        self.assertEqual(result["outputs"]["excluded_receipts"][0]["code"], "receipt-not-posted")
        self.assertIsNone(result["outputs"]["excluded_receipts"][0]["posted_business_date"])
        payload["receipt_lines"][0]["posted_at"] = "2026-09-08T09:00:00Z"
        self.rejected(payload, "invalid-status-timestamp")
        payload["receipt_lines"][0].update(status="posted", posted_at=None)
        self.rejected(payload, "invalid-timestamp")

    def test_future_history_and_allocation_are_visible_without_consumption(self):
        payload = simple()
        add_history(payload, 250, payload["invoices"][0]["vendor_invoice_number"],
                    posted="2026-09-15T09:00:00Z", recorded="2026-09-15T10:00:00Z")
        result = self.ready(payload)
        outputs = result["outputs"]
        self.assertFalse(outputs["historical_invoices"][0]["included"])
        self.assertEqual(outputs["historical_invoices"][0]["exclusion_code"], "historical-invoice-posted-after-as-of")
        self.assertFalse(outputs["prior_allocations"][0]["included"])
        self.assertEqual(outputs["prior_allocations"][0]["exclusion_code"], "allocation-recorded-after-as-of")
        self.assertEqual(outputs["invoice_reviews"][0]["duplicate_historical_invoice_ids"], [])
        self.assertEqual(outputs["remaining_capacity"]["receipts"][0]["historical_used_milliunits"], 0)
        self.assertEqual(len(result["exceptions"]), 2)
        self.assert_conservation(result)

    def test_future_allocation_against_current_history_is_excluded(self):
        payload = simple()
        add_history(payload, 250, recorded="2026-09-15T09:00:00Z")
        result = self.ready(payload)
        self.assertTrue(result["outputs"]["historical_invoices"][0]["included"])
        self.assertFalse(result["outputs"]["prior_allocations"][0]["included"])
        self.assertEqual(result["outputs"]["remaining_capacity"]["po_lines"][0]["historical_used_milliunits"], 0)

    def test_pending_history_without_allocations_is_explicit_exclusion(self):
        payload = simple()
        history, _ = add_history(payload, 250)
        history.update(status="pending", posted_at=None)
        payload["prior_allocations"] = []
        result = self.ready(payload)
        self.assertEqual(result["outputs"]["historical_invoices"][0]["exclusion_code"], "historical-invoice-not-posted")
        self.assertEqual(result["status"], "completed_with_exceptions")

    def test_recording_before_invoice_or_receipt_posting_rejects(self):
        for posted, recorded in (("2026-09-15T09:00:00Z", "2026-09-10T09:00:00Z"),
                                 ("2026-09-07T09:00:00Z", "2026-09-07T10:00:00Z")):
            with self.subTest(posted=posted):
                payload = simple()
                add_history(payload, 250, posted=posted, recorded=recorded)
                self.rejected(payload, "allocation-time-inconsistent")

    def test_historical_scope_and_missing_references_reject(self):
        for mode in ("missing-history", "pending-history", "vendor", "currency", "wrong-po", "missing-receipt"):
            with self.subTest(mode=mode):
                payload = simple()
                history, allocation = add_history(payload)
                if mode == "missing-history":
                    allocation["historical_invoice_id"] = "SYN-MISSING"
                elif mode == "pending-history":
                    history.update(status="pending", posted_at=None)
                elif mode == "vendor":
                    history["vendor_id"] = "SYN-OTHER"
                elif mode == "currency":
                    history["currency"] = "EUR"
                elif mode == "wrong-po":
                    allocation["po_id"] = "SYN-MISSING"
                else:
                    allocation["receipt_line_id"] = "SYN-MISSING"
                self.rejected(payload, "allocation-reference-inconsistent")

    def test_included_historical_capacity_subtraction(self):
        payload = simple(750, capacity=1000)
        add_history(payload, 250)
        result = self.ready(payload)
        self.assertEqual(result["outputs"]["remaining_capacity"]["receipts"][0]["before_proposals_milliunits"], 750)
        self.assertEqual(result["outputs"]["remaining_capacity"]["po_lines"][0]["historical_used_milliunits"], 250)
        self.assert_conservation(result)

    def test_contradictory_receipt_and_po_historical_capacity_reject(self):
        self.rejected(fixture("negative-contradictory"), "historical-receipt-overallocated")
        payload = simple()
        _, first = add_history(payload, 700)
        extra = deepcopy(payload["receipt_lines"][0])
        extra["receipt_line_id"] = "SYN-SECOND-R"
        payload["receipt_lines"].append(extra)
        second = deepcopy(first)
        second.update(allocation_id="SYN-ALLOCATION-02", receipt_line_id=extra["receipt_line_id"])
        payload["prior_allocations"].append(second)
        self.rejected(payload, "historical-po-overallocated")
        payload = simple()
        add_history(payload, 1001, recorded="2026-09-15T09:00:00Z")
        self.rejected(payload, "historical-receipt-overallocated")

    def test_unknown_fields_fail_at_every_object_level(self):
        for location in ("root", "controls", "invoice", "line", "components", "selection", "po", "receipt", "history", "allocation"):
            with self.subTest(location=location):
                payload = fixture("demo")
                targets = {
                    "root": payload, "controls": payload["controls"], "invoice": payload["invoices"][0],
                    "line": payload["invoices"][0]["lines"][0],
                    "selection": payload["invoices"][0]["lines"][0]["selected_receipts"][0],
                    "po": payload["po_lines"][0], "receipt": payload["receipt_lines"][0],
                    "history": payload["historical_invoices"][0], "allocation": payload["prior_allocations"][0],
                }
                if location == "components":
                    payload["invoices"][0]["components"] = {"override": 0}
                else:
                    targets[location]["override"] = "ignore checks"
                self.rejected(payload, "unknown-field")

    def test_unknown_enums_and_unsupported_modes_never_succeed(self):
        for source, field, value in (("controls", "approval_state", "auto"),
                                     ("po_lines", "approval_state", "waived"),
                                     ("receipt_lines", "status", "reversed"),
                                     ("invoices", "currency", "GBP")):
            with self.subTest(source=source):
                payload = simple()
                row = payload[source] if source == "controls" else payload[source][0]
                row[field] = value
                self.rejected(payload, "invalid-enum")
        payload = simple()
        payload["controls"]["matching_mode"] = "fifo"
        self.rejected(payload, "unknown-field")

    def test_required_arrays_objects_null_optional_fields_and_row_limits(self):
        payload = simple()
        payload["invoices"] = []
        self.rejected(payload, "invalid-array")
        payload = simple()
        payload.pop("as_of")
        self.rejected(payload, "missing-field")
        payload = simple()
        payload["invoices"][0]["components"] = None
        self.rejected(payload, "invalid-object")
        payload = simple()
        payload["invoices"][0]["lines"][0]["selected_receipts"] = None
        self.rejected(payload, "invalid-array")
        payload = fixture("demo")
        payload["controls"]["max_rows_per_source"] = 3
        self.rejected(payload, "row-limit-exceeded")
        payload = simple(capacity=2000)
        payload["controls"]["max_rows_per_source"] = 1
        add_invoice(payload, "SYN-SECOND")
        self.rejected(payload, "row-limit-exceeded")

    def test_aggregate_nested_source_limit_is_not_per_invoice_only(self):
        payload = simple(capacity=4000)
        invoice = payload["invoices"][0]
        line = deepcopy(invoice["lines"][0])
        line["line_id"] = "SYN-LINE-02"
        invoice["lines"].append(line)
        invoice["header_net_minor"] = 2000
        add_invoice(payload, "SYN-SECOND")
        payload["controls"]["max_rows_per_source"] = 2
        self.rejected(payload, "row-limit-exceeded")

    def test_schema_version_true_is_not_one(self):
        payload = simple()
        payload["schema_version"] = True
        self.rejected(payload, "invalid-version")

    def test_scope_totals_do_not_mix_currency_or_entity(self):
        payload = simple()
        add_resource(payload, "SYN-EUR-PO", "SYN-EUR-R")
        payload["po_lines"][1]["currency"] = "EUR"
        payload["receipt_lines"][1]["currency"] = "EUR"
        invoice = add_invoice(payload, "SYN-EUR-INV", po_id="SYN-EUR-PO")
        invoice["currency"] = "EUR"
        result = self.ready(payload)
        self.assertEqual([row["currency"] for row in result["outputs"]["summary"]], ["EUR", "USD"])
        self.assertEqual([row["intake_net_minor"] for row in result["outputs"]["summary"]], [1000, 1000])
        self.assert_conservation(result)

    def test_all_source_and_selection_permutations_preserve_result_and_trace(self):
        randomizer = random.Random(42)
        for case in ("demo", "holdout-a", "holdout-b", "negative-malformed", "negative-contradictory"):
            original = fixture(case)
            reference = self.solve(original)
            for iteration in range(10):
                with self.subTest(case=case, iteration=iteration):
                    payload = deepcopy(original)
                    for source in ("invoices", "po_lines", "receipt_lines", "historical_invoices", "prior_allocations"):
                        randomizer.shuffle(payload[source])
                    for invoice in payload["invoices"]:
                        randomizer.shuffle(invoice["lines"])
                        for line in invoice["lines"]:
                            if "selected_receipts" in line:
                                randomizer.shuffle(line["selected_receipts"])
                    self.assertEqual(self.solve(payload), reference)

    def test_solve_does_not_read_files_or_mutate_payload(self):
        payload = fixture("demo")
        with patch("builtins.open", side_effect=AssertionError("solve must not read files")), \
                patch.object(Path, "open", side_effect=AssertionError("solve must not read files")):
            result, _ = self.solve(payload)
        result["outputs"]["invoice_reviews"][0]["components"]["tax_minor"] = 99
        self.assertNotIn("components", payload["invoices"][0])

    def test_eight_meaningful_runtime_trace_states_and_bounded_tables(self):
        result, events = self.solve(fixture("demo"))
        self.assertEqual(len(events), 8)
        self.assertEqual(events[0]["kind"], "input")
        self.assertEqual(events[0]["facts"]["batch_id"], "SYN-AP-DEMO")
        self.assertEqual(events[0]["facts"]["as_of"], "2026-09-14T12:00:00Z")
        self.assertEqual(events[-1]["kind"], "output")
        self.assertEqual({event["kind"] for event in events}, {"input", "validation", "join", "decision", "exception", "output"})
        self.assertEqual(events[4]["tables"][0]["rows"][0][2:5], [100000, 200000, 60])
        for event in events:
            self.assertLessEqual(len(event["caption"]), 260)
            self.assertLessEqual(len(event["facts"]), 6)
            self.assertIn(len(event["tables"]), (1, 2))
            for table in event["tables"]:
                self.assertLessEqual(len(table["columns"]), 6)
                self.assertLessEqual(len(table["rows"]), 8)
                self.assertGreaterEqual(table["total_rows"], len(table["rows"]))
                self.assertTrue(all(0 <= index < len(table["rows"]) for index in table["highlight_rows"]))
        self.assertEqual(events[-1]["facts"]["proposal_rows"], len(result["outputs"]["proposed_allocations"]))
        payload = simple()
        first_trace = self.solve(payload)[1]
        payload = simple(1000, 1001, 1000)
        second_trace = self.solve(payload)[1]
        self.assertNotEqual(first_trace[4]["tables"], second_trace[4]["tables"])

    def test_trace_excerpt_labels_and_counts_do_not_truncate_results(self):
        payload = simple(capacity=9000)
        for index in range(2, 10):
            add_invoice(payload, "SYN-INV-" + str(index))
        result, events = self.solve(payload)
        self.assertEqual(len(result["outputs"]["invoice_reviews"]), 9)
        self.assertEqual(len(result["outputs"]["proposed_allocations"]), 9)
        self.assertEqual(events[1]["tables"][0]["total_rows"], 9)
        self.assertEqual(len(events[1]["tables"][0]["rows"]), 8)
        self.assertIn("first 8 of 9", events[1]["tables"][0]["title"])
        self.assert_conservation(result)

    def test_procedure_contains_every_exact_reason_and_message(self):
        procedure = (ROOT / "HOW_TO.md").read_text(encoding="utf-8")
        for code, message in BASELINE.MESSAGES.items():
            with self.subTest(code=code):
                self.assertIn("`" + code + "`", procedure)
                self.assertIn(message, procedure)


if __name__ == "__main__":
    unittest.main()
