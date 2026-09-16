"""Independent penny arithmetic and fail-closed returns reconciliation checks."""
from __future__ import annotations

import copy
import importlib.util
import random
import unittest
from decimal import Decimal, ROUND_HALF_UP, localcontext
from pathlib import Path
from unittest.mock import patch

from scenarios._shared.common import digest, json_bytes, load_json
from scenarios._shared.contract import baseline_import_audit, load_scenario, validate_result, validate_trace
from scenarios._shared.pipeline import check_case_evidence, golden_lock, run_case
from scenarios.tests.fixtures import copy_scenario, temporary_directory


ROOT = Path(__file__).resolve().parents[1] / "retail" / "returns-refund-reconciliation"


class ReturnsReconciliationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scenario = load_scenario(ROOT)
        golden_lock(cls.scenario)
        spec = importlib.util.spec_from_file_location("retail_returns_baseline", ROOT / "baseline.py")
        cls.baseline = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.baseline)

    def payload(self, case_id="demo"):
        return load_json(ROOT / "mock-data" / f"{case_id}.json")

    @staticmethod
    def export(payload, role):
        return payload["files"][payload["source_files"][role]]

    def small_payload(self):
        payload = self.payload("negative-malformed")
        self.export(payload, "requests")[0]["requested_qty"] = 1
        return payload

    def solve(self, payload):
        result, events = self.baseline.solve(payload)
        validate_result(result)
        return result, events

    def assert_rejected(self, payload, code):
        result, events = self.solve(payload)
        self.assertEqual(result["status"], "rejected")
        self.assertEqual(result["outputs"], {})
        self.assertEqual(len(result["exceptions"]), 1)
        self.assertEqual(result["exceptions"][0]["code"], code)
        self.assertEqual([event["kind"] for event in events], ["input", "validation"])
        return result

    @staticmethod
    def rounded(amount, qty, total):
        with localcontext() as context:
            context.prec = 100
            return int((Decimal(amount) * qty / total).quantize(Decimal(1), rounding=ROUND_HALF_UP))

    def assert_invariants(self, result):
        if result["status"] == "rejected":
            return
        output = result["outputs"]
        proposals = output["request_proposals"]
        self.assertEqual(
            [(row["requested_on"], row["request_id"]) for row in proposals],
            sorted((row["requested_on"], row["request_id"]) for row in proposals),
        )
        for row in proposals:
            self.assertEqual(row["proposed_qty"] + row["deferred_qty"], row["requested_qty"])
            self.assertLessEqual(row["proposed_qty"], row["requested_qty"])
            self.assertEqual(row["proposed_merchandise_minor"] + row["proposed_tax_minor"], row["proposed_total_minor"])
            if row["available_qty"] is None:
                self.assertEqual(row["proposed_qty"], 0)
                self.assertEqual(row["proposed_total_minor"], 0)
                self.assertIsNone(row["entitlement_before"])
                self.assertIsNone(row["entitlement_after"])
            else:
                self.assertLessEqual(row["proposed_qty"], row["available_qty"])
                before, after = row["entitlement_before"], row["entitlement_after"]
                self.assertEqual(before["qty"], row["prior_qty"] + row["earlier_proposed_qty"])
                self.assertEqual(before["qty"] + row["proposed_qty"], after["qty"])
                self.assertEqual(after["merchandise_minor"] - before["merchandise_minor"], row["proposed_merchandise_minor"])
                self.assertEqual(after["tax_minor"] - before["tax_minor"], row["proposed_tax_minor"])
            if row["proposed_qty"]:
                self.assertEqual(row["join_status"], "matched")
                for key, supplied in row["supplied_keys"].items():
                    self.assertEqual(row["original"][key], supplied)
        for line in output["line_eligibility"]:
            if line["quarantined"]:
                self.assertEqual(line["proposed_qty"], 0)
                self.assertEqual(line["proposed_merchandise_minor"], 0)
                self.assertEqual(line["proposed_tax_minor"], 0)
                for field in ("prior_qty", "prior_merchandise_minor", "prior_tax_minor",
                              "remaining_qty", "remaining_merchandise_minor", "remaining_tax_minor"):
                    self.assertIsNone(line[field])
            else:
                for suffix in ("qty", "merchandise_minor", "tax_minor"):
                    self.assertEqual(
                        line["original_" + suffix],
                        line["prior_" + suffix] + line["proposed_" + suffix] + line["remaining_" + suffix],
                    )
                    self.assertGreaterEqual(line["remaining_" + suffix], 0)
                q = line["prior_qty"] + line["proposed_qty"]
                for component in ("merchandise", "tax"):
                    self.assertEqual(
                        line[f"prior_{component}_minor"] + line[f"proposed_{component}_minor"],
                        self.rounded(line[f"original_{component}_minor"], q, line["original_qty"]),
                    )
        for order in output["order_money_controls"]:
            if order["quarantined"]:
                self.assertEqual(order["proposed_minor"], 0)
                for field in ("prior_minor", "prior_plus_proposed_minor", "remaining_minor", "cap_ok"):
                    self.assertIsNone(order[field])
            else:
                self.assertTrue(order["cap_ok"])
                self.assertTrue(order["confirmed"])
                self.assertEqual(order["payment_method"], "card")
                self.assertEqual(order["original_total_minor"], order["captured_minor"])
                self.assertEqual(order["prior_minor"] + order["proposed_minor"], order["prior_plus_proposed_minor"])
                self.assertEqual(order["prior_plus_proposed_minor"] + order["remaining_minor"], order["captured_minor"])
                self.assertLessEqual(order["prior_plus_proposed_minor"], order["captured_minor"])
                self.assertLessEqual(order["captured_minor"], order["authorized_minor"])
        for currency in output["currency_controls"]:
            self.assertEqual(currency["order_count"], currency["quarantined_order_count"] + currency["reconciled_order_count"])
            self.assertEqual(currency["prior_minor"] + currency["proposed_minor"], currency["prior_plus_proposed_minor"])
            self.assertEqual(currency["prior_plus_proposed_minor"] + currency["remaining_minor"], currency["reconciled_captured_minor"])
        review = output["review_packet"]
        self.assertIs(review["action_authorized"], False)
        self.assertEqual(review["proposed_qty"], sum(row["proposed_qty"] for row in proposals))
        self.assertEqual(review["deferred_qty"], sum(row["deferred_qty"] for row in proposals))
        self.assertEqual(review["exception_count"], len(result["exceptions"]))

    def test_00_all_frozen_cases_and_fresh_evidence(self):
        lock_bytes = (ROOT / "validation" / "golden-lock.json").read_bytes()
        with temporary_directory() as temporary:
            scenario = load_scenario(copy_scenario(ROOT, Path(temporary) / "scenarios"))
            for case in scenario.cases:
                with self.subTest(case=case["id"]):
                    report = run_case(scenario, case, replace=True)
                    self.assertEqual(report["state"], "baseline_pass", report["errors"] + report["local"]["differences"])
                    self.assertEqual(check_case_evidence(scenario, case)["state"], "baseline_pass")
                    result = load_json(scenario.root / "baseline-output" / f"{case['id']}.json")
                    self.assert_invariants(result)
            self.assertEqual((scenario.root / "validation" / "golden-lock.json").read_bytes(), lock_bytes)
        self.assertEqual((ROOT / "validation" / "golden-lock.json").read_bytes(), lock_bytes)
        self.assertEqual(baseline_import_audit(ROOT / "baseline.py")["status"], "static_import_check_pass")

    def test_approved_demo_and_changed_case_arithmetic(self):
        result, events = self.solve(self.payload())
        rows = result["outputs"]["request_proposals"]
        self.assertEqual([row["proposed_qty"] for row in rows], [1, 1, 0, 0])
        self.assertEqual([row["proposed_total_minor"] for row in rows], [368, 366, 0, 0])
        self.assertEqual(rows[1]["earlier_proposed_qty"], 1)
        self.assertEqual(rows[1]["deferred_qty"], 1)
        self.assertEqual(result["outputs"]["order_money_controls"][0]["prior_plus_proposed_minor"], 1100)
        self.assertEqual(len(events), 9)
        self.assertEqual({event["kind"] for event in events}, {"input", "validation", "join", "decision", "exception", "output"})
        allocation = next(event for event in events if event["step_id"] == "calculate-original-refund")
        self.assertEqual(allocation["tables"][0]["rows"][:2], [
            ["SYN-REQUEST-01", 333, 667, 33, 67, 368],
            ["SYN-REQUEST-02", 667, 1000, 67, 100, 366],
        ])
        result, _ = self.solve(self.payload("holdout-a"))
        row = result["outputs"]["request_proposals"][0]
        self.assertEqual((row["proposed_merchandise_minor"], row["proposed_tax_minor"]), (999, 81))
        self.assertEqual(result["outputs"]["order_money_controls"][0]["remaining_minor"], 540)
        result, _ = self.solve(self.payload("holdout-b"))
        rows = result["outputs"]["request_proposals"]
        self.assertEqual([row["proposed_total_minor"] for row in rows], [0, 500])
        self.assertEqual(rows[1]["available_qty"], 2)
        self.assertEqual(result["outputs"]["order_money_controls"][0]["remaining_minor"], 499)

    def test_all_source_permutations_preserve_result_and_trace(self):
        generator = random.Random(742)
        for case in self.scenario.cases:
            payload = self.payload(case["id"])
            original = self.solve(payload)
            for _ in range(4):
                changed = copy.deepcopy(payload)
                for role in ("original_orders", "original_lines", "requests"):
                    generator.shuffle(self.export(changed, role))
                generator.shuffle(self.export(changed, "prior_returns")["records"])
                for field in ("allowed_reasons", "allowed_conditions"):
                    generator.shuffle(self.export(changed, "policy")[field])
                changed["files"] = dict(reversed(list(changed["files"].items())))
                changed["source_files"] = dict(reversed(list(changed["source_files"].items())))
                with self.subTest(case=case["id"]):
                    self.assertEqual(self.solve(changed), original)

    def test_all_role_filename_remappings_preserve_result_and_trace(self):
        for case in self.scenario.cases:
            payload = self.payload(case["id"])
            original = self.solve(payload)
            files, mapping = {}, {}
            for index, (role, old_name) in enumerate(payload["source_files"].items()):
                filename = f"independent-export-{index}.json"
                files[filename] = payload["files"][old_name]
                mapping[role] = filename
            payload["files"], payload["source_files"] = files, mapping
            with self.subTest(case=case["id"]):
                self.assertEqual(self.solve(payload), original)

    def test_input_nonmutation_and_no_cross_run_state(self):
        for case in self.scenario.cases:
            payload = self.payload(case["id"])
            original = copy.deepcopy(payload)
            first = self.solve(payload)
            self.assertEqual(payload, original)
            self.assertEqual(self.solve(payload), first)
            if first[0]["outputs"]:
                first[0]["outputs"]["review_packet"]["next_actions"].clear()
                self.assertEqual(payload, original)
                self.assertEqual(len(self.solve(payload)[0]["outputs"]["review_packet"]["next_actions"]), 3)

    def test_cumulative_entitlements_exhaustively_conserve_original_pennies(self):
        for total in range(1, 9):
            for merchandise, tax in ((0, 0), (1, 1), (7, 2), (999, 101), (1999, 161)):
                for prior_qty in range(total + 1):
                    with self.subTest(total=total, merchandise=merchandise, tax=tax, prior=prior_qty):
                        payload = self.small_payload()
                        order = self.export(payload, "original_orders")[0]
                        order.update(captured_minor=merchandise + tax, authorized_minor=merchandise + tax + 37)
                        line = self.export(payload, "original_lines")[0]
                        line.update(fulfilled_qty=total, merchandise_paid_minor=merchandise, tax_paid_minor=tax)
                        prior_merchandise = self.rounded(merchandise, prior_qty, total)
                        prior_tax = self.rounded(tax, prior_qty, total)
                        if prior_qty:
                            self.export(payload, "prior_returns")["records"].append({
                                "return_event_id": "SYN-RETURN-ARITHMETIC", "order_id": order["order_id"],
                                "line_id": line["line_id"], "posted_on": "2099-10-02", "state": "posted",
                                "qty": prior_qty, "merchandise_minor": prior_merchandise, "tax_minor": prior_tax,
                            })
                        requests = self.export(payload, "requests")
                        template = requests[0]
                        requests[:] = [
                            dict(template, request_id=f"SYN-REQUEST-ARITHMETIC-{index:03d}")
                            for index in range(total - prior_qty + 2)
                        ]
                        result, _ = self.solve(payload)
                        self.assert_invariants(result)
                        control = result["outputs"]["order_money_controls"][0]
                        self.assertEqual(control["proposed_merchandise_minor"], merchandise - prior_merchandise)
                        self.assertEqual(control["proposed_tax_minor"], tax - prior_tax)
                        self.assertEqual(control["remaining_minor"], 0)
                        proposals = result["outputs"]["request_proposals"]
                        self.assertEqual([row["reason_codes"] for row in proposals[-2:]], [["quantity-exhausted"]] * 2)
                        for index, row in enumerate(proposals[:total - prior_qty]):
                            quantity = prior_qty + index
                            self.assertEqual(
                                row["proposed_merchandise_minor"],
                                self.rounded(merchandise, quantity + 1, total) - self.rounded(merchandise, quantity, total),
                            )
                            self.assertEqual(
                                row["proposed_tax_minor"],
                                self.rounded(tax, quantity + 1, total) - self.rounded(tax, quantity, total),
                            )

    def test_large_integer_half_up_has_no_float_or_decimal_context_loss(self):
        payload = self.small_payload()
        merchandise, tax = 10**40 + 1, 3
        self.export(payload, "original_lines")[0].update(merchandise_paid_minor=merchandise, tax_paid_minor=tax)
        self.export(payload, "original_orders")[0].update(captured_minor=merchandise + tax, authorized_minor=merchandise + tax)
        result, _ = self.solve(payload)
        row = result["outputs"]["request_proposals"][0]
        self.assertEqual(row["proposed_merchandise_minor"], 5 * 10**39 + 1)
        self.assertEqual(row["proposed_tax_minor"], 2)
        self.assert_invariants(result)

    def test_unknown_receipt_never_replaces_receipt_join_with_order_hint(self):
        payload = self.small_payload()
        requests = self.export(payload, "requests")
        requests.append(dict(requests[0], request_id="SYN-REQUEST-Z"))
        requests[0]["receipt_id"] = "SYN-RECEIPT-UNKNOWN"
        result, _ = self.solve(payload)
        first, second = result["outputs"]["request_proposals"]
        self.assertEqual(first["join_status"], "unknown-receipt")
        self.assertIsNone(first["original"])
        self.assertIsNone(first["available_qty"])
        self.assertEqual(second["proposed_qty"], 1)
        self.assertEqual(second["available_qty"], 2)
        self.assertFalse(result["outputs"]["order_money_controls"][0]["quarantined"])
        self.assertIn("not an accusation", result["exceptions"][0]["message"])

    def test_exact_store_receipt_line_and_sku_join_fail_closed(self):
        for field, value, status in (
            ("store_id", "SYN-STORE-OTHER", "unknown-receipt"),
            ("receipt_id", "SYN-RECEIPT-OTHER", "unknown-receipt"),
            ("order_id", "SYN-ORDER-OTHER", "conflicting-identifiers"),
            ("invoice_id", "SYN-INVOICE-OTHER", "conflicting-identifiers"),
            ("line_id", "SYN-LINE-OTHER", "missing-line"),
            ("sku", "SYN-SKU-OTHER", "sku-mismatch"),
        ):
            payload = self.small_payload()
            self.export(payload, "requests")[0][field] = value
            result, _ = self.solve(payload)
            with self.subTest(field=field):
                row = result["outputs"]["request_proposals"][0]
                self.assertEqual(row["join_status"], status)
                self.assertEqual(row["proposed_qty"], 0)
                self.assertEqual(result["outputs"]["order_money_controls"][0]["quarantined"], status != "unknown-receipt")

    def test_late_conflict_quarantines_every_implicated_order_and_earlier_request(self):
        for conflict_field in ("order_id", "invoice_id"):
            payload = self.payload()
            target = self.export(payload, "original_orders")[1]
            self.export(payload, "requests")[1][conflict_field] = target[conflict_field]
            result, _ = self.solve(payload)
            with self.subTest(field=conflict_field):
                self.assertEqual(result["outputs"]["review_packet"]["quarantined_order_ids"], ["SYN-ORDER-01", "SYN-ORDER-02"])
                self.assertEqual([row["proposed_qty"] for row in result["outputs"]["request_proposals"]], [0, 0, 0, 0])
                self.assertTrue(all(row["quarantined"] for row in result["outputs"]["line_eligibility"]))
                self.assertEqual(result["outputs"]["request_proposals"][-1]["disposition"], "unresolved")
                self.assert_invariants(result)

    def test_pending_history_quarantines_whole_order_not_unrelated_order(self):
        payload = self.payload()
        self.export(payload, "prior_returns")["records"][0]["state"] = "pending"
        orders = self.export(payload, "original_orders")
        orders[1]["purchased_on"] = "2099-06-20"
        orders[0].update(captured_minor=1155, authorized_minor=1155)
        lines = self.export(payload, "original_lines")
        lines.append(dict(lines[0], line_id="SYN-LINE-EXTRA", sku="SYN-SKU-EXTRA",
                          fulfilled_qty=1, merchandise_paid_minor=50, tax_paid_minor=5))
        requests = self.export(payload, "requests")
        requests.append(dict(requests[0], request_id="SYN-REQUEST-00",
                             line_id="SYN-LINE-EXTRA", sku="SYN-SKU-EXTRA"))
        result, _ = self.solve(payload)
        affected = [row for row in result["outputs"]["line_eligibility"] if row["order_id"] == orders[0]["order_id"]]
        self.assertEqual(len(affected), 2)
        self.assertTrue(all(row["quarantined"] and row["proposed_qty"] == 0 for row in affected))
        other = result["outputs"]["order_money_controls"][1]
        self.assertFalse(other["quarantined"])
        self.assertEqual(other["proposed_minor"], 2200)
        self.assertEqual(result["outputs"]["currency_controls"][0]["reconciled_captured_minor"], 2200)
        self.assert_invariants(result)

    def test_voided_history_consumes_nothing_but_is_actually_traced(self):
        payload = self.payload()
        before, _ = self.solve(payload)
        history = self.export(payload, "prior_returns")
        history["records"].append(dict(
            history["records"][0], return_event_id="SYN-RETURN-VOID",
            state="voided", qty=999, merchandise_minor=999999, tax_minor=888888,
        ))
        result, events = self.solve(payload)
        self.assertEqual(result, before)
        opening = next(event for event in events if event["step_id"] == "reconcile-opening-ledger")
        self.assertEqual(opening["facts"]["voided_events"], 1)
        history["records"][-1]["posted_on"] = "2099-07-02"
        result, _ = self.solve(payload)
        self.assertIn("non-opening-history", result["outputs"]["order_money_controls"][0]["reason_codes"])

    def test_history_boundaries_completeness_and_mislinks_cannot_be_zero(self):
        for change, code in (
            (lambda history: history.update(is_complete=False), "history-not-closed"),
            (lambda history: history.update(complete_before="2099-07-01"), "history-not-closed"),
            (lambda history: history["records"][0].update(state="pending"), "pending-history"),
            (lambda history: history["records"][0].update(posted_on="2099-07-02"), "non-opening-history"),
            (lambda history: history["records"][0].update(posted_on="2099-12-31"), "non-opening-history"),
            (lambda history: history["records"][0].update(posted_on="2099-06-11"), "history-before-purchase"),
            (lambda history: history["records"][0].update(line_id="SYN-LINE-MISSING"), "unknown-history-line"),
        ):
            payload = self.payload()
            change(self.export(payload, "prior_returns"))
            result, _ = self.solve(payload)
            with self.subTest(code=code):
                control = result["outputs"]["order_money_controls"][0]
                self.assertIn(code, control["reason_codes"])
                self.assertTrue(control["quarantined"])
                self.assertIsNone(control["prior_minor"])
                self.assertIsNone(control["remaining_minor"])
                self.assertEqual(control["proposed_minor"], 0)
                self.assert_invariants(result)
        payload = self.payload()
        self.export(payload, "prior_returns")["records"][0]["order_id"] = "SYN-ORDER-NOT-PRESENT"
        self.assert_rejected(payload, "unattributable-history")

    def test_contradictory_prior_quantity_or_separate_tax_is_not_repaired(self):
        for changes, code in (
            ({"qty": 4, "merchandise_minor": 1333, "tax_minor": 133}, "prior-quantity-exceeds-fulfilled"),
            ({"merchandise_minor": 334, "tax_minor": 32}, "prior-entitlement-mismatch"),
            ({"tax_minor": 34}, "prior-entitlement-mismatch"),
        ):
            payload = self.payload()
            history_row = self.export(payload, "prior_returns")["records"][0]
            history_row.update(changes)
            original = copy.deepcopy(payload)
            result, _ = self.solve(payload)
            with self.subTest(code=code, changes=changes):
                line = result["outputs"]["line_eligibility"][0]
                self.assertTrue(line["quarantined"])
                self.assertEqual(line["observed_posted_qty"], history_row["qty"])
                self.assertEqual(line["observed_posted_merchandise_minor"], history_row["merchandise_minor"])
                self.assertEqual(line["observed_posted_tax_minor"], history_row["tax_minor"])
                self.assertIn(code, result["outputs"]["order_money_controls"][0]["reason_codes"])
                self.assertEqual(payload, original)

    def test_original_payment_caps_and_confirmation_quarantine_without_proposals(self):
        for changes, code in (
            ({"confirmed": False}, "payment-not-confirmed"),
            ({"payment_method": "gift-card"}, "unsupported-payment-method"),
            ({"payment_method": "mixed"}, "unsupported-payment-method"),
            ({"payment_method": "other"}, "unsupported-payment-method"),
            ({"authorized_minor": 1000}, "capture-exceeds-authorization"),
            ({"captured_minor": 1099}, "original-payment-mismatch"),
            ({"captured_minor": 1101, "authorized_minor": 1200}, "original-payment-mismatch"),
        ):
            payload = self.small_payload()
            self.export(payload, "original_orders")[0].update(changes)
            result, _ = self.solve(payload)
            with self.subTest(changes=changes):
                self.assertIn(code, result["outputs"]["order_money_controls"][0]["reason_codes"])
                self.assertEqual(result["outputs"]["request_proposals"][0]["proposed_total_minor"], 0)
                self.assert_invariants(result)

    def test_missing_original_lines_are_not_zero_price_entitlements(self):
        payload = self.small_payload()
        self.export(payload, "original_lines").clear()
        result, _ = self.solve(payload)
        control = result["outputs"]["order_money_controls"][0]
        self.assertIn("missing-original-lines", control["reason_codes"])
        self.assertIn("original-payment-mismatch", control["reason_codes"])
        self.assertEqual(result["outputs"]["request_proposals"][0]["join_status"], "missing-line")
        self.assertIsNone(result["outputs"]["request_proposals"][0]["original"]["line_id"])
        self.assertIsNone(control["prior_minor"])
        payload = self.small_payload()
        self.export(payload, "original_lines")[0]["order_id"] = "SYN-ORDER-MISSING"
        self.assert_rejected(payload, "unknown-original-order")

    def test_duplicate_keys_in_every_role_and_shared_payment_evidence_reject(self):
        for role in ("original_orders", "original_lines", "prior_returns", "requests"):
            payload = self.payload()
            rows = self.export(payload, role)
            if role == "prior_returns":
                rows = rows["records"]
            rows.append(copy.deepcopy(rows[0]))
            with self.subTest(role=role):
                self.assert_rejected(payload, "duplicate-key")
        for field in ("invoice_id", "payment_reference"):
            payload = self.payload()
            orders = self.export(payload, "original_orders")
            orders[1][field] = orders[0][field]
            with self.subTest(field=field):
                self.assert_rejected(payload, "duplicate-key")
        self.assert_rejected(self.payload("negative-ambiguous-receipt"), "ambiguous-receipt")

    def test_quantity_money_and_boolean_domains_never_coerce(self):
        fields = (
            ("original_orders", "authorized_minor"), ("original_orders", "captured_minor"),
            ("original_lines", "fulfilled_qty"), ("original_lines", "merchandise_paid_minor"),
            ("original_lines", "tax_paid_minor"), ("requests", "requested_qty"),
        )
        for role, field in fields:
            for value in (True, False, 1.0, 1.5, "1", -1, None, [], {}, float("nan"), float("inf")):
                payload = self.small_payload()
                self.export(payload, role)[0][field] = value
                with self.subTest(role=role, field=field, value=value):
                    self.assert_rejected(payload, "invalid-record")
        for role, field in (("original_orders", "confirmed"), ("original_lines", "returnable")):
            payload = self.small_payload()
            self.export(payload, role)[0][field] = 1
            self.assert_rejected(payload, "invalid-record")
        for field in ("qty", "merchandise_minor", "tax_minor"):
            payload = self.payload()
            self.export(payload, "prior_returns")["records"][0][field] = True
            self.assert_rejected(payload, "invalid-record")
        for field in ("requested_qty",):
            payload = self.small_payload()
            self.export(payload, "requests")[0][field] = 0
            self.assert_rejected(payload, "invalid-record")

    def test_schema_dates_identifiers_vocabulary_and_metadata_are_strict(self):
        for value in ("2099-2-01", "2099-02-29", "2099-12-32", "2099-10-05T00:00:00", "2026-10-05", None):
            payload = self.small_payload()
            self.export(payload, "requests")[0]["requested_on"] = value
            with self.subTest(date=value):
                self.assert_rejected(payload, "invalid-record")
        for field, value in (("request_id", "REAL-REQUEST"), ("sku", "syn-sku-m"),
                             ("reason", " Wrong Size "), ("condition", ""), ("request_id", "SYN-" + "A" * 64)):
            payload = self.small_payload()
            self.export(payload, "requests")[0][field] = value
            self.assert_rejected(payload, "invalid-record")
        for role, field, value in (
            ("original_orders", "currency", "JPY"), ("original_orders", "payment_method", "cash"),
            ("prior_returns", "state", "settled"),
        ):
            payload = self.payload()
            rows = self.export(payload, role)
            if role == "prior_returns":
                rows = rows["records"]
            rows[0][field] = value
            self.assert_rejected(payload, "invalid-record")
        for field in ("complete_before", "is_complete", "records"):
            payload = self.small_payload()
            del self.export(payload, "prior_returns")[field]
            self.assert_rejected(payload, "invalid-record")
        for field, value in (("window_days", True), ("window_days", -1), ("allow_partial_requests", 1),
                             ("allowed_reasons", []), ("allowed_conditions", ["unworn", "unworn"])):
            payload = self.small_payload()
            self.export(payload, "policy")[field] = value
            self.assert_rejected(payload, "invalid-policy")

    def test_no_missing_exports_extra_fields_or_tokens_are_inferred(self):
        for role in self.baseline.ROLES:
            payload = self.small_payload()
            del payload["files"][payload["source_files"][role]]
            self.assert_rejected(payload, "invalid-bundle")
        for role in ("original_orders", "original_lines", "requests"):
            for change in (lambda row: row.update(card_token="SYN-NOT-A-TOKEN"),
                           lambda row: row.pop(next(iter(row)))):
                payload = self.small_payload()
                change(self.export(payload, role)[0])
                self.assert_rejected(payload, "invalid-record")
        for role in ("original_orders", "original_lines", "requests"):
            payload = self.small_payload()
            payload["files"][payload["source_files"][role]] = None
            self.assert_rejected(payload, "invalid-record")
        payload = self.small_payload()
        self.export(payload, "prior_returns")["records"] = None
        self.assert_rejected(payload, "invalid-record")

    def test_bundle_mapping_does_not_resolve_paths_or_guess_roles(self):
        for filename in ("../orders.json", r"exports\orders.json", "C:\\orders.json", "/orders.json",
                         "con.json", "Orders.json", "original_orders.json", "x" * 81 + ".json", None, []):
            payload = self.small_payload()
            payload["source_files"]["original_orders"] = filename
            with self.subTest(filename=filename):
                self.assert_rejected(payload, "invalid-bundle")
        for value in (True, 1.0, "1", 2):
            payload = self.small_payload()
            payload["schema_version"] = value
            self.assert_rejected(payload, "invalid-bundle")
        for field in ("source_files", "files"):
            for value in (None, [], "file"):
                payload = self.small_payload()
                payload[field] = value
                self.assert_rejected(payload, "invalid-bundle")
        payload = self.small_payload()
        payload["source_files"]["original_lines"] = payload["source_files"]["original_orders"]
        self.assert_rejected(payload, "invalid-bundle")
        payload = self.small_payload()
        payload["files"]["unmapped.json"] = []
        self.assert_rejected(payload, "invalid-bundle")
        self.assert_rejected([], "invalid-bundle")

    def test_inclusive_window_period_and_zero_day_boundary(self):
        payload = self.small_payload()
        policy = self.export(payload, "policy")
        order = self.export(payload, "original_orders")[0]
        policy["window_days"] = 0
        order["purchased_on"] = "2099-10-05"
        self.assertEqual(self.solve(payload)[0]["outputs"]["request_proposals"][0]["proposed_qty"], 1)
        order["purchased_on"] = "2099-10-04"
        self.assertEqual(self.solve(payload)[0]["outputs"]["request_proposals"][0]["reason_codes"], ["return-window-exceeded"])
        payload = self.small_payload()
        policy = self.export(payload, "policy")
        policy.update(period_start="2099-10-04", period_end="2099-10-06", as_of="2099-10-06", window_days=5)
        self.export(payload, "prior_returns")["complete_before"] = "2099-10-04"
        requests = self.export(payload, "requests")
        requests[0]["requested_on"] = "2099-10-04"
        requests.append(dict(requests[0], request_id="SYN-REQUEST-Z", requested_on="2099-10-06"))
        result, _ = self.solve(payload)
        self.assertEqual([row["proposed_total_minor"] for row in result["outputs"]["request_proposals"]], [550, 550])
        self.assert_invariants(result)
        policy["as_of"] = "2099-10-05"
        self.assert_rejected(payload, "invalid-policy")
        policy.update(as_of="2099-10-06", period_start="2099-10-07")
        self.assert_rejected(payload, "invalid-policy")

    def test_policy_exclusion_precedence_and_excluded_requests_consume_nothing(self):
        payload = self.small_payload()
        line = self.export(payload, "original_lines")[0]
        order = self.export(payload, "original_orders")[0]
        request = self.export(payload, "requests")[0]
        order["purchased_on"] = "2099-10-05"
        line["returnable"] = False
        request.update(requested_on="2099-10-04", reason="excluded-reason", condition="excluded-condition")
        result, _ = self.solve(payload)
        self.assertEqual(result["outputs"]["request_proposals"][0]["reason_codes"], [
            "request-outside-period", "purchase-after-request", "original-not-returnable",
            "reason-not-allowed", "condition-not-allowed",
        ])
        self.assertEqual(result["outputs"]["request_proposals"][0]["age_days"], -1)
        self.assert_invariants(result)
        payload = self.small_payload()
        requests = self.export(payload, "requests")
        requests.append(dict(requests[0], request_id="SYN-REQUEST-Z", requested_qty=2))
        requests[0]["requested_on"] = "2099-10-04"
        result, _ = self.solve(payload)
        first, second = result["outputs"]["request_proposals"]
        self.assertEqual(first["disposition"], "ineligible")
        self.assertEqual(second["available_qty"], 2)
        self.assertEqual(second["proposed_total_minor"], 1100)
        self.assert_invariants(result)

    def test_date_then_identifier_not_source_or_identifier_alone_controls_reservation(self):
        payload = self.small_payload()
        self.export(payload, "policy").update(period_start="2099-10-04", window_days=7)
        self.export(payload, "prior_returns")["complete_before"] = "2099-10-04"
        requests = self.export(payload, "requests")
        template = requests[0]
        requests[:] = [
            dict(template, request_id="SYN-REQUEST-A", requested_on="2099-10-05", requested_qty=2),
            dict(template, request_id="SYN-REQUEST-Z", requested_on="2099-10-04", requested_qty=1),
        ]
        result, _ = self.solve(payload)
        rows = result["outputs"]["request_proposals"]
        self.assertEqual([row["request_id"] for row in rows], ["SYN-REQUEST-Z", "SYN-REQUEST-A"])
        self.assertEqual([row["proposed_qty"] for row in rows], [1, 1])
        self.assertEqual(rows[1]["deferred_qty"], 1)
        self.assert_invariants(result)

    def test_partial_disabled_oversized_request_does_not_consume_pennies(self):
        payload = self.small_payload()
        self.export(payload, "policy")["allow_partial_requests"] = False
        requests = self.export(payload, "requests")
        requests.append(dict(requests[0], request_id="SYN-REQUEST-Z", requested_qty=2))
        requests[0]["requested_qty"] = 3
        result, _ = self.solve(payload)
        first, second = result["outputs"]["request_proposals"]
        self.assertEqual(first["proposed_total_minor"], 0)
        self.assertEqual(first["entitlement_before"], first["entitlement_after"])
        self.assertEqual(second["available_qty"], 2)
        self.assertEqual(second["proposed_total_minor"], 1100)
        self.assertEqual(result["outputs"]["order_money_controls"][0]["remaining_minor"], 0)

    def test_multiple_history_events_sum_cumulatively_not_individual_unit_prices(self):
        payload = self.payload()
        history = self.export(payload, "prior_returns")["records"]
        history.append(dict(history[0], return_event_id="SYN-RETURN-02", merchandise_minor=334, tax_minor=34))
        requests = self.export(payload, "requests")
        requests[0]["requested_qty"] = 1
        result, _ = self.solve(payload)
        first, second = result["outputs"]["request_proposals"][:2]
        self.assertEqual(first["prior_qty"], 2)
        self.assertEqual(first["proposed_total_minor"], 366)
        self.assertEqual(second["reason_codes"], ["quantity-exhausted"])
        self.assert_invariants(result)

    def test_multicurrency_totals_and_unrequested_originals_are_separate(self):
        payload = self.payload()
        self.export(payload, "original_orders")[1]["currency"] = "CAD"
        self.export(payload, "requests")[:] = self.export(payload, "requests")[:2]
        result, _ = self.solve(payload)
        currencies = result["outputs"]["currency_controls"]
        self.assertEqual([row["currency"] for row in currencies], ["CAD", "USD"])
        self.assertEqual(currencies[0]["remaining_minor"], 2200)
        self.assertEqual(currencies[0]["proposed_minor"], 0)
        self.assertEqual(currencies[1]["proposed_minor"], 734)
        self.assertEqual(len(result["outputs"]["order_money_controls"]), 2)
        self.assertNotIn("proposed_minor", result["outputs"]["review_packet"])
        self.assert_invariants(result)

    def test_empty_explicit_exports_remain_review_only_not_missing(self):
        payload = self.small_payload()
        for role in ("original_orders", "original_lines", "requests"):
            self.export(payload, role).clear()
        result, events = self.solve(payload)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["outputs"]["currency_controls"], [])
        self.assertEqual(result["outputs"]["review_packet"]["request_count"], 0)
        self.assertIs(result["outputs"]["review_packet"]["action_authorized"], False)
        self.assertEqual(len(events), 9)

    def test_trace_contains_actual_subsets_counts_and_no_extra_result_fields(self):
        payload = self.small_payload()
        self.export(payload, "original_lines")[0]["fulfilled_qty"] = 12
        requests = self.export(payload, "requests")
        template = requests[0]
        requests[:] = [dict(template, request_id=f"SYN-REQUEST-{index:03d}") for index in range(15)]
        result, events = self.solve(payload)
        self.assertEqual(set(result), {"schema_version", "status", "outputs", "exceptions"})
        self.assertEqual(len(result["outputs"]["request_proposals"]), 15)
        self.assertEqual(result["outputs"]["review_packet"]["proposed_qty"], 12)
        quantity = next(event for event in events if event["step_id"] == "reserve-proposed-quantities")["tables"][0]
        self.assertEqual(len(quantity["rows"]), 8)
        self.assertEqual(quantity["total_rows"], 15)
        self.assertIn("first 8 of 15", quantity["title"])
        input_hash = digest(json_bytes(payload))
        trace = {
            "schema_version": 1, "provenance": "synthetic-local-baseline", "scenario_id": self.scenario.id,
            "input_sha256": input_hash,
            "events": [dict(event, sequence=index) for index, event in enumerate(events, 1)],
        }
        validate_trace(trace, self.scenario, self.scenario.case("demo"), input_hash)
        self.assert_invariants(result)

    def test_unexpected_defects_are_not_masked_as_business_rejections(self):
        with patch.object(self.baseline, "_join", side_effect=RuntimeError("synthetic test defect")):
            with self.assertRaisesRegex(RuntimeError, "synthetic test defect"):
                self.baseline.solve(self.small_payload())

    def test_authoring_procedure_contains_schema_messages_and_no_private_answers(self):
        document = (ROOT / "HOW_TO.md").read_text(encoding="utf-8")
        for message in self.baseline.REQUEST_MESSAGES.values():
            self.assertIn(message, document)
        for schema in self.baseline.SCHEMAS.values():
            for field in schema:
                self.assertIn(f"`{field}`", document)
        for field in ("complete_before", "is_complete", "source_files", "files", "action_authorized"):
            self.assertIn(f"`{field}`", document)
        for forbidden in ("holdout", "expected/", "expected\\", "golden-lock", "2099-08-15", "2099-09-11"):
            self.assertNotIn(forbidden, document)
        self.assertIn("UNKNOWN", document)
        self.assertIn("Computer Use tools were removed", document)
        self.assertIn("not Installed", document)


if __name__ == "__main__":
    unittest.main()
