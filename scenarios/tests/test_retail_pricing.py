"""Scoped standard-library checks; verify the prewritten oracle lock before importing solve."""
import copy
import importlib.util
import random
import unittest
from decimal import localcontext
from pathlib import Path
from unittest.mock import patch

from scenarios._shared.common import file_digest, load_json
from scenarios._shared.comparison import compare_json
from scenarios._shared.contract import baseline_import_audit, load_scenario, validate_result, validate_trace
from scenarios._shared.pipeline import golden_lock


ROOT = Path(__file__).resolve().parents[1] / "retail" / "promotion-price-audit"


def source(payload, role):
    return payload["exports"][payload["policy"]["source_files"][role]]


def replace_source(payload, role, rows):
    payload["exports"][payload["policy"]["source_files"][role]] = rows


class RetailPricingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scenario = load_scenario(ROOT)
        cls.lock = golden_lock(cls.scenario)
        cls.oracles = {
            case["id"]: load_json(cls.scenario.file(case["expected"])) for case in cls.scenario.cases
        }
        specification = importlib.util.spec_from_file_location("retail_pricing_baseline", ROOT / "baseline.py")
        cls.baseline = importlib.util.module_from_spec(specification)
        specification.loader.exec_module(cls.baseline)

    def payload(self, case_id="demo"):
        return load_json(self.scenario.file(self.scenario.case(case_id)["input"]))

    def single(self, base=1000, observed=None):
        payload = self.payload("negative-contradictory")
        row = next(row for row in source(payload, "base_prices") if row["price_id"] == "SYN-BASE-N1")
        row["price_minor"] = base
        replace_source(payload, "base_prices", [row])
        source(payload, "observations")[0]["observed_minor"] = base if observed is None else observed
        return payload

    def promotion(self, payload, promotion_id, mode, rule_type, value, priority=10):
        observation = source(payload, "observations")[0]
        row = {
            "promotion_id": promotion_id, "enabled": True,
            "valid_from": "2099-09-01", "valid_to": "2099-09-02",
            "currency": observation["currency"], "unit": observation["unit"],
            "priority": priority, "mode": mode, "type": rule_type, "value": value,
        }
        source(payload, "promotions").append(row)
        source(payload, "promotion_scope").append({
            "promotion_id": promotion_id, "store_id": observation["store_id"],
            "sku": observation["sku"], "line_type": "include",
        })
        return row

    def override(self, payload, exception_id="SYN-EX-TEST", amount=800, approved=True):
        observation = source(payload, "observations")[0]
        row = {
            "exception_id": exception_id, "store_id": observation["store_id"], "sku": observation["sku"],
            "valid_from": "2099-09-01", "valid_to": "2099-09-02",
            "currency": observation["currency"], "unit": observation["unit"], "approved": approved,
            "approval_reference": "SYN-APPROVAL-TEST" if approved else None, "price_minor": amount,
        }
        source(payload, "price_exceptions").append(row)
        return row

    def run_payload(self, payload):
        result, events = self.baseline.solve(payload)
        validate_result(result)
        self.assertFalse(result["outputs"]["review_packet"]["action_authorized"])
        return result, events

    def assert_rejected(self, payload, code):
        result, events = self.run_payload(payload)
        self.assertEqual(result["status"], "rejected")
        self.assertEqual([issue["code"] for issue in result["exceptions"]], [code])
        self.assertIsNone(result["outputs"]["reconciliation"])
        self.assertIsNone(result["outputs"]["review_packet"]["policy"])
        for key in ("price_audit", "rule_selection", "out_of_scope"):
            self.assertEqual(result["outputs"][key], [])
        self.assertEqual([event["kind"] for event in events], ["input", "validation"])
        self.assertEqual(events[-1]["tables"][0]["rows"][0][0], code)

    def test_frozen_independent_case_results_and_trace_contract(self):
        self.assertEqual(len(self.lock["cases"]), 10)
        for case in self.scenario.cases:
            with self.subTest(case=case["id"]):
                result, events = self.run_payload(self.payload(case["id"]))
                self.assertEqual(compare_json(self.oracles[case["id"]], result), [])
                trace = {
                    "schema_version": 1, "provenance": "synthetic-local-baseline", "scenario_id": "retail-03",
                    "input_sha256": file_digest(self.scenario.file(case["input"])),
                    "events": [dict(event, sequence=number) for number, event in enumerate(events, 1)],
                }
                validate_trace(trace, self.scenario, case, trace["input_sha256"])
        self.assertEqual(golden_lock(self.scenario), self.lock)

    def test_all_case_inputs_are_unchanged(self):
        for case in self.scenario.cases:
            with self.subTest(case=case["id"]):
                payload = self.payload(case["id"])
                before = copy.deepcopy(payload)
                self.run_payload(payload)
                self.assertEqual(payload, before)

    def test_row_permutations_preserve_results_and_events(self):
        for case in self.scenario.cases:
            original = self.payload(case["id"])
            _, original_events = self.run_payload(original)
            for seed in range(6):
                with self.subTest(case=case["id"], seed=seed):
                    payload = copy.deepcopy(original)
                    generator = random.Random(seed)
                    for rows in payload["exports"].values():
                        generator.shuffle(rows)
                    payload["exports"] = dict(reversed(list(payload["exports"].items())))
                    payload["policy"]["source_files"] = dict(reversed(list(payload["policy"]["source_files"].items())))
                    result, events = self.run_payload(payload)
                    self.assertEqual(compare_json(self.oracles[case["id"]], result), [])
                    self.assertEqual(events, original_events)

    def test_source_filename_remapping_is_not_business_logic(self):
        for case_id in ("demo", "holdout-a", "holdout-b", "negative-contradictory"):
            with self.subTest(case=case_id):
                payload = self.payload(case_id)
                names = {role: f"remapped-{role.replace('_', '-')}.json" for role in payload["policy"]["source_files"]}
                exports = {names[role]: source(payload, role) for role in names}
                payload["policy"]["source_files"] = names
                payload["exports"] = exports
                before = copy.deepcopy(payload)
                result, events = self.run_payload(payload)
                self.assertEqual(compare_json(self.oracles[case_id], result), [])
                self.assertEqual(payload, before)
                self.assertEqual({row[1] for row in events[0]["tables"][0]["rows"]}, set(names.values()))

    def test_outputs_do_not_alias_inputs_or_subsequent_runs(self):
        payload = self.payload()
        before = copy.deepcopy(payload)
        result, events = self.run_payload(payload)
        result["outputs"]["price_audit"][0]["observed_minor"] = -1
        result["outputs"]["rule_selection"][0]["base_checks"].clear()
        events[0]["tables"][0]["rows"].clear()
        self.assertEqual(payload, before)
        fresh, _ = self.run_payload(payload)
        self.assertEqual(compare_json(self.oracles["demo"], fresh), [])

    def test_exclusive_suppresses_same_priority_best_and_compound(self):
        payload = self.single(1999, 1699)
        self.promotion(payload, "SYN-PROMO-EX", "exclusive", "amount-off", 300, 20)
        self.promotion(payload, "SYN-PROMO-BEST", "best-price", "percent-off", 5000, 20)
        self.promotion(payload, "SYN-PROMO-COMPOUND", "compound", "percent-off", 10000, 20)
        self.promotion(payload, "SYN-PROMO-LOW", "exclusive", "percent-off", 9000, 10)
        result, _ = self.run_payload(payload)
        audit = result["outputs"]["price_audit"][0]
        ledger = result["outputs"]["rule_selection"][0]
        self.assertEqual((audit["expected_minor"], audit["selected_promotion_ids"]), (1699, ["SYN-PROMO-EX"]))
        self.assertEqual(ledger["candidates"], [{"promotion_ids": ["SYN-PROMO-EX"], "mode": "exclusive", "unrounded_minor": "1699"}])
        self.assertEqual({row["promotion_id"]: row["reason"] for row in ledger["suppressed_promotions"]}, {
            "SYN-PROMO-BEST": "exclusive-present", "SYN-PROMO-COMPOUND": "exclusive-present",
            "SYN-PROMO-LOW": "lower-priority",
        })

    def test_priority_is_numeric_and_precedes_price_competition(self):
        payload = self.single(1000, 950)
        self.promotion(payload, "SYN-PROMO-LOW", "best-price", "percent-off", 9000, -10)
        self.promotion(payload, "SYN-PROMO-HIGH", "best-price", "amount-off", 50, -2)
        result, _ = self.run_payload(payload)
        self.assertEqual(result["outputs"]["price_audit"][0]["expected_minor"], 950)
        self.assertEqual(result["outputs"]["rule_selection"][0]["winning_priority"], -2)
        self.assertEqual(result["outputs"]["price_audit"][0]["selected_promotion_ids"], ["SYN-PROMO-HIGH"])

    def test_exclusive_compares_unrounded_values_not_rounded_ties(self):
        payload = self.single(1005, 754)
        self.promotion(payload, "SYN-PROMO-A", "exclusive", "amount-off", 251)
        self.promotion(payload, "SYN-PROMO-Z", "exclusive", "percent-off", 2500)
        result, _ = self.run_payload(payload)
        row = result["outputs"]["price_audit"][0]
        self.assertEqual((row["unrounded_minor"], row["expected_minor"]), ("753.75", 754))
        self.assertEqual(row["selected_promotion_ids"], ["SYN-PROMO-Z"])
        ledger = result["outputs"]["rule_selection"][0]
        self.assertEqual(ledger["tied_promotion_sets"], [])
        self.assertEqual(ledger["suppressed_promotions"], [{"promotion_id": "SYN-PROMO-A", "reason": "higher-price"}])

    def test_best_single_competes_against_entire_compound_tuple_with_exact_tie(self):
        payload = self.single(1000, 800)
        self.promotion(payload, "SYN-PROMO-B", "best-price", "amount-off", 200)
        self.promotion(payload, "SYN-PROMO-A2", "compound", "amount-off", 100)
        self.promotion(payload, "SYN-PROMO-A1", "compound", "amount-off", 100)
        result, _ = self.run_payload(payload)
        audit = result["outputs"]["price_audit"][0]
        selection = result["outputs"]["rule_selection"][0]
        self.assertEqual((audit["expected_minor"], audit["pricing_basis"]), (800, "compound"))
        self.assertEqual(audit["selected_promotion_ids"], ["SYN-PROMO-A1", "SYN-PROMO-A2"])
        self.assertEqual(selection["tied_promotion_sets"], [["SYN-PROMO-A1", "SYN-PROMO-A2"], ["SYN-PROMO-B"]])
        self.assertEqual(selection["suppressed_promotions"], [{"promotion_id": "SYN-PROMO-B", "reason": "tie-break"}])

    def test_best_single_can_beat_compounding(self):
        payload = self.single(1000, 500)
        self.promotion(payload, "SYN-PROMO-A", "compound", "percent-off", 1000)
        self.promotion(payload, "SYN-PROMO-B", "compound", "percent-off", 2000)
        self.promotion(payload, "SYN-PROMO-C", "best-price", "percent-off", 5000)
        result, _ = self.run_payload(payload)
        audit = result["outputs"]["price_audit"][0]
        self.assertEqual((audit["expected_minor"], audit["pricing_basis"]), (500, "best-price"))
        self.assertEqual(audit["selected_promotion_ids"], ["SYN-PROMO-C"])
        self.assertEqual(result["outputs"]["rule_selection"][0]["candidates"][0]["unrounded_minor"], "720")

    def test_amount_sum_is_floored_before_all_percent_factors(self):
        payload = self.single(1000, 0)
        self.promotion(payload, "SYN-PROMO-A", "compound", "amount-off", 600)
        self.promotion(payload, "SYN-PROMO-B", "compound", "amount-off", 700)
        self.promotion(payload, "SYN-PROMO-C", "compound", "percent-off", 1250)
        result, _ = self.run_payload(payload)
        audit = result["outputs"]["price_audit"][0]
        self.assertEqual((audit["unrounded_minor"], audit["expected_minor"], audit["disposition"]), ("0", 0, "match"))
        self.assertEqual(audit["selected_promotion_ids"], ["SYN-PROMO-A", "SYN-PROMO-B", "SYN-PROMO-C"])

    def test_compound_uses_no_intermediate_rounding_or_ambient_decimal_precision(self):
        payload = self.single(1, 0)
        self.promotion(payload, "SYN-PROMO-A", "compound", "percent-off", 5000)
        self.promotion(payload, "SYN-PROMO-B", "compound", "percent-off", 5000)
        with localcontext() as context:
            context.prec = 2
            result, _ = self.run_payload(payload)
        audit = result["outputs"]["price_audit"][0]
        self.assertEqual((audit["unrounded_minor"], audit["expected_minor"]), ("0.25", 0))
        payload = self.single(1, 0)
        for number in range(20):
            self.promotion(payload, f"SYN-PROMO-{number:02d}", "compound", "percent-off", 5000)
        with localcontext() as context:
            context.prec = 2
            result, _ = self.run_payload(payload)
        self.assertEqual(result["outputs"]["price_audit"][0]["unrounded_minor"], "0.00000095367431640625")
        self.assertEqual(result["outputs"]["price_audit"][0]["expected_minor"], 0)

    def test_half_up_and_rate_endpoints(self):
        for base, rate, raw, rounded in (
            (1, 5000, "0.5", 1), (3, 5000, "1.5", 2), (1999, 5000, "999.5", 1000),
            (10000, 1, "9999", 9999), (999, 10000, "0", 0),
        ):
            with self.subTest(base=base, rate=rate):
                payload = self.single(base, rounded)
                self.promotion(payload, "SYN-PROMO-TEST", "best-price", "percent-off", rate)
                result, _ = self.run_payload(payload)
                audit = result["outputs"]["price_audit"][0]
                self.assertEqual((audit["unrounded_minor"], audit["expected_minor"], audit["disposition"]), (raw, rounded, "match"))

    def test_tolerance_is_inclusive_for_both_delta_signs(self):
        for observed, delta, disposition in ((904, -1, "match"), (906, 1, "match"), (903, -2, "mismatch"), (907, 2, "mismatch")):
            with self.subTest(observed=observed):
                payload = self.single(1005, observed)
                payload["policy"]["tolerance_minor"] = 1
                self.promotion(payload, "SYN-PROMO-TEST", "best-price", "percent-off", 1000)
                result, _ = self.run_payload(payload)
                row = result["outputs"]["price_audit"][0]
                self.assertEqual((row["expected_minor"], row["delta_minor"], row["disposition"]), (905, delta, disposition))

    def test_observed_price_never_selects_the_rule_or_expected_price(self):
        for observed in (0, 800, 900, 100000):
            with self.subTest(observed=observed):
                payload = self.single(1000, observed)
                self.promotion(payload, "SYN-PROMO-A", "best-price", "percent-off", 2000)
                self.promotion(payload, "SYN-PROMO-B", "best-price", "amount-off", 100)
                result, _ = self.run_payload(payload)
                audit = result["outputs"]["price_audit"][0]
                self.assertEqual((audit["expected_minor"], audit["selected_promotion_ids"]), (800, ["SYN-PROMO-A"]))

    def test_every_promotion_filter_and_exclusion_override(self):
        mutations = (
            (lambda p, r: r.update(enabled=False), ["disabled"]),
            (lambda p, r: r.update(valid_from="2099-09-02", valid_to="2099-09-03"), ["outside-validity"]),
            (lambda p, r: r.update(valid_from="2099-08-31", valid_to="2099-09-01"), ["outside-validity"]),
            (lambda p, r: r.update(currency="EUR"), ["currency-mismatch"]),
            (lambda p, r: r.update(unit="CASE"), ["unit-mismatch"]),
            (lambda p, r: replace_source(p, "promotion_scope", []), ["not-included"]),
            (lambda p, r: source(p, "promotion_scope")[0].update(line_type="exclude"), ["not-included", "explicit-exclusion"]),
            (lambda p, r: source(p, "promotion_scope").append(dict(source(p, "promotion_scope")[0], line_type="exclude")), ["explicit-exclusion"]),
        )
        for mutate, reasons in mutations:
            with self.subTest(reasons=reasons):
                payload = self.single()
                promotion = self.promotion(payload, "SYN-PROMO-FILTER", "exclusive", "percent-off", 9000, 99)
                mutate(payload, promotion)
                result, _ = self.run_payload(payload)
                self.assertEqual(result["outputs"]["price_audit"][0]["expected_minor"], 1000)
                self.assertEqual(result["outputs"]["rule_selection"][0]["promotion_filters"], [{"promotion_id": "SYN-PROMO-FILTER", "reasons": reasons}])

    def test_base_promotion_and_approval_windows_are_all_half_open(self):
        payload = self.single()
        payload["policy"].update(audit_end="2099-09-04", as_of="2099-09-03")
        first = source(payload, "base_prices")[0]
        first["valid_to"] = "2099-09-02"
        source(payload, "base_prices").append(dict(first, price_id="SYN-BASE-N2", valid_from="2099-09-02", valid_to="2099-09-04", price_minor=1200))
        self.promotion(payload, "SYN-PROMO-ONE-DAY", "exclusive", "amount-off", 100)
        override = self.override(payload, amount=800)
        override.update(valid_from="2099-09-02", valid_to="2099-09-03")
        observation = source(payload, "observations")[0]
        replace_source(payload, "observations", [
            dict(observation, observation_id="SYN-OBS-1", observed_on="2099-09-01", observed_minor=900),
            dict(observation, observation_id="SYN-OBS-2", observed_on="2099-09-02", observed_minor=800),
            dict(observation, observation_id="SYN-OBS-3", observed_on="2099-09-03", observed_minor=1200),
        ])
        result, _ = self.run_payload(payload)
        self.assertEqual([row["expected_minor"] for row in result["outputs"]["price_audit"]], [900, 800, 1200])
        self.assertEqual([row["pricing_basis"] for row in result["outputs"]["price_audit"]], ["exclusive", "approved-exception", "base"])
        self.assertEqual([row["base_price_ids"] for row in result["outputs"]["price_audit"]], [["SYN-BASE-N1"], ["SYN-BASE-N2"], ["SYN-BASE-N2"]])
        self.assertEqual(result["status"], "completed")

    def test_unapproved_exception_does_not_apply(self):
        payload = self.single(1000, 900)
        self.promotion(payload, "SYN-PROMO-TEST", "best-price", "amount-off", 100)
        self.override(payload, approved=False)
        result, _ = self.run_payload(payload)
        self.assertEqual(result["outputs"]["price_audit"][0]["expected_minor"], 900)
        self.assertIsNone(result["outputs"]["price_audit"][0]["applied_exception_id"])
        self.assertEqual(result["outputs"]["rule_selection"][0]["exception_checks"], [{"exception_id": "SYN-EX-TEST", "date_match": True, "approved": False}])

    def test_unique_base_gate_cannot_be_bypassed_by_approval(self):
        for case_id, code in (("negative-contradictory", "AMBIGUOUS_BASE_PRICE"), ("negative-missing-base", "MISSING_BASE_PRICE")):
            with self.subTest(case=case_id):
                payload = self.payload(case_id)
                self.override(payload)
                self.promotion(payload, "SYN-PROMO-TEST", "best-price", "amount-off", 100)
                result, _ = self.run_payload(payload)
                audit = result["outputs"]["price_audit"][0]
                for key in ("expected_minor", "unrounded_minor", "delta_minor", "applied_exception_id"):
                    self.assertIsNone(audit[key])
                self.assertEqual([row["code"] for row in result["exceptions"]], [code])
                self.assertEqual(result["outputs"]["rule_selection"][0]["suppressed_promotions"], [{"promotion_id": "SYN-PROMO-TEST", "reason": "not-evaluable"}])

    def test_all_ambiguities_are_reported_even_when_amounts_agree(self):
        payload = self.payload("negative-contradictory")
        for row in source(payload, "base_prices"):
            row["price_minor"] = 1000
        self.override(payload, "SYN-EX-A", 900)
        self.override(payload, "SYN-EX-B", 900)
        result, events = self.run_payload(payload)
        audit = result["outputs"]["price_audit"][0]
        self.assertIsNone(audit["expected_minor"])
        self.assertEqual([row["code"] for row in result["exceptions"]], ["AMBIGUOUS_APPROVED_EXCEPTION", "AMBIGUOUS_BASE_PRICE"])
        self.assertEqual(result["outputs"]["reconciliation"]["not_evaluable"], 1)
        self.assertEqual(len(result["outputs"]["issue_queue"]), 2)
        self.assertEqual(events[2]["tables"][0]["rows"][0][-1], "not-evaluable")
        self.assertIsNone(events[5]["tables"][0]["rows"][0][2])

    def test_before_start_and_at_end_exclusions_are_reconciled_once(self):
        payload = self.single()
        observation = source(payload, "observations")[0]
        replace_source(payload, "base_prices", [])
        replace_source(payload, "observations", [
            dict(observation, observation_id="SYN-OBS-BEFORE", observed_on="2099-08-31"),
            dict(observation, observation_id="SYN-OBS-END", observed_on="2099-09-02"),
        ])
        result, _ = self.run_payload(payload)
        self.assertEqual(result["outputs"]["price_audit"], [])
        self.assertEqual(result["outputs"]["rule_selection"], [])
        self.assertEqual([row["reason"] for row in result["outputs"]["out_of_scope"]], ["before-audit-start", "at-or-after-audit-end"])
        self.assertEqual([row["code"] for row in result["exceptions"]], ["OUT_OF_AUDIT_WINDOW", "OUT_OF_AUDIT_WINDOW"])
        self.assertEqual(result["outputs"]["reconciliation"], {"input_observations": 2, "included_observations": 0, "matched": 0, "mismatched": 0, "not_evaluable": 0, "out_of_scope": 2, "reconciled": True})

    def test_invalid_and_future_windows_reject(self):
        for start, end, as_of, code in (
            ("2099-09-02", "2099-09-01", "2099-09-02", "INVALID_WINDOW"),
            ("2099-09-01", "2099-09-01", "2099-09-01", "INVALID_WINDOW"),
            ("2099-09-01", "2099-09-03", "2099-09-01", "FUTURE_AUDIT_WINDOW"),
            ("2099-02-29", "2099-03-01", "2099-03-01", "INVALID_DATE"),
            ("2099-9-01", "2099-09-02", "2099-09-01", "INVALID_DATE"),
            ("2026-09-01", "2099-09-02", "2099-09-01", "INVALID_DATE"),
        ):
            with self.subTest(start=start, end=end):
                payload = self.single()
                payload["policy"].update(audit_start=start, audit_end=end, as_of=as_of)
                self.assert_rejected(payload, code)

    def test_invalid_unused_rules_and_outside_observations_still_reject(self):
        payload = self.single()
        promotion = self.promotion(payload, "SYN-PROMO-UNUSED", "best-price", "percent-off", 1000)
        promotion.update(enabled=False, valid_to="2099-09-01")
        self.assert_rejected(payload, "INVALID_WINDOW")
        payload = self.payload("negative-out-of-window")
        source(payload, "observations")[0]["observed_minor"] = True
        self.assert_rejected(payload, "INVALID_VALUE")

    def test_unsupported_discount_types_modes_and_policy_reject(self):
        for field, value in (("type", "buy-one-get-one"), ("type", "coupon"), ("type", "loyalty"), ("type", "threshold"), ("type", "percentage"), ("mode", "stack-all"), ("mode", None)):
            with self.subTest(field=field, value=value):
                payload = self.single()
                promotion = self.promotion(payload, "SYN-PROMO-UNSUPPORTED", "best-price", "percent-off", 1000)
                promotion[field] = value
                self.assert_rejected(payload, "UNSUPPORTED_RULE")
        payload = self.single()
        payload["policy"]["rounding"] = "ROUND_HALF_EVEN"
        self.assert_rejected(payload, "UNSUPPORTED_POLICY")
        payload = self.single()
        source(payload, "stores")[0]["date_basis"] = "UTC"
        self.assert_rejected(payload, "UNSUPPORTED_POLICY")

    def test_numeric_fields_are_strict_no_boolean_or_float_coercion(self):
        for field, value, code in (
            ("value", True, "INVALID_RATE"), ("value", 1.0, "INVALID_RATE"),
            ("value", "1000", "INVALID_RATE"), ("value", 0, "INVALID_RATE"),
            ("value", -1, "INVALID_RATE"), ("value", 10001, "INVALID_RATE"),
            ("priority", True, "INVALID_VALUE"), ("priority", "20", "INVALID_VALUE"),
            ("enabled", 1, "INVALID_VALUE"),
        ):
            with self.subTest(field=field, value=value):
                payload = self.single()
                promotion = self.promotion(payload, "SYN-PROMO-TYPE", "best-price", "percent-off", 1000)
                promotion[field] = value
                self.assert_rejected(payload, code)
        for value in (True, 1.0, "999", None, -1):
            with self.subTest(money=value):
                payload = self.single()
                source(payload, "base_prices")[0]["price_minor"] = value
                self.assert_rejected(payload, "INVALID_VALUE")
                payload = self.single()
                payload["policy"]["tolerance_minor"] = value
                self.assert_rejected(payload, "INVALID_VALUE")
        for value in (0, True, 1.0, -1):
            with self.subTest(amount_off=value):
                payload = self.single()
                self.promotion(payload, "SYN-PROMO-AMOUNT", "exclusive", "amount-off", value)
                self.assert_rejected(payload, "INVALID_VALUE")

    def test_exact_foreign_keys_dimensions_and_approval_references(self):
        for role, field, value, code in (
            ("observations", "store_id", "SYN-STORE-UNKNOWN", "UNKNOWN_REFERENCE"),
            ("base_prices", "sku", "SYN-SKU-UNKNOWN", "UNKNOWN_REFERENCE"),
            ("base_prices", "currency", "EUR", "DIMENSION_MISMATCH"),
            ("observations", "unit", "CASE", "DIMENSION_MISMATCH"),
            ("observations", "currency", "JPY", "INVALID_VALUE"),
            ("products", "sku", "live-sku", "INVALID_IDENTIFIER"),
        ):
            with self.subTest(role=role, field=field):
                payload = self.single()
                source(payload, role)[0][field] = value
                self.assert_rejected(payload, code)
        payload = self.single()
        self.promotion(payload, "SYN-PROMO-KNOWN", "best-price", "amount-off", 100)
        source(payload, "promotion_scope")[0]["promotion_id"] = "SYN-PROMO-UNKNOWN"
        self.assert_rejected(payload, "UNKNOWN_REFERENCE")
        payload = self.single()
        self.override(payload)["approval_reference"] = None
        self.assert_rejected(payload, "INVALID_IDENTIFIER")
        payload = self.single()
        self.override(payload)["currency"] = "EUR"
        self.assert_rejected(payload, "DIMENSION_MISMATCH")

    def test_duplicate_keys_reject_in_every_export(self):
        for role in ("stores", "products", "base_prices", "promotions", "promotion_scope", "price_exceptions", "observations"):
            with self.subTest(role=role):
                payload = self.single()
                self.promotion(payload, "SYN-PROMO-TEST", "best-price", "amount-off", 100)
                self.override(payload)
                source(payload, role).append(copy.deepcopy(source(payload, role)[0]))
                self.assert_rejected(payload, "DUPLICATE_KEY")

    def test_source_map_rejects_missing_aliasing_extra_and_nonportable_names(self):
        for invalid in ("..\\outside.json", "../outside.json", "C:\\outside.json", "/outside.json", "con.json", "MyExports.json", "https://example.com/data.json", "nested/data.json"):
            with self.subTest(filename=invalid):
                payload = self.single()
                old_name = payload["policy"]["source_files"]["observations"]
                payload["exports"][invalid] = payload["exports"].pop(old_name)
                payload["policy"]["source_files"]["observations"] = invalid
                self.assert_rejected(payload, "INVALID_SOURCE_MAP")
        payload = self.single()
        del payload["exports"][payload["policy"]["source_files"]["observations"]]
        self.assert_rejected(payload, "INVALID_SOURCE_MAP")
        payload = self.single()
        payload["exports"]["unused.json"] = []
        self.assert_rejected(payload, "INVALID_SOURCE_MAP")
        payload = self.single()
        payload["policy"]["source_files"]["observations"] = payload["policy"]["source_files"]["stores"]
        self.assert_rejected(payload, "INVALID_SOURCE_MAP")
        payload = self.single()
        del payload["policy"]["source_files"]["observations"]
        self.assert_rejected(payload, "INVALID_SOURCE_MAP")

    def test_missing_unknown_and_malformed_shapes_reject(self):
        for mutate in (
            lambda p: p.update(extra=True),
            lambda p: p["policy"].pop("tolerance_minor"),
            lambda p: source(p, "base_prices")[0].pop("price_minor"),
            lambda p: source(p, "products")[0].update(extra=True),
            lambda p: replace_source(p, "observations", {}),
            lambda p: replace_source(p, "observations", [None]),
        ):
            payload = self.single()
            mutate(payload)
            self.assert_rejected(payload, "INVALID_SCHEMA")
        self.assert_rejected([], "INVALID_SCHEMA")

    def test_empty_observation_table_is_explicit_not_missing_evidence(self):
        payload = self.single()
        replace_source(payload, "observations", [])
        result, events = self.run_payload(payload)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["outputs"]["reconciliation"], {"input_observations": 0, "included_observations": 0, "matched": 0, "mismatched": 0, "not_evaluable": 0, "out_of_scope": 0, "reconciled": True})
        self.assertEqual(result["outputs"]["review_packet"]["counts_by_store_currency"], [])
        self.assertEqual(len(events), 8)

    def test_multi_store_currency_counts_do_not_mix_money_or_scope(self):
        payload = self.single(1000, 1000)
        observation = source(payload, "observations")[0]
        source(payload, "stores").append({"store_id": "SYN-STORE-EUR", "currency": "EUR", "date_basis": "store-local-calendar"})
        source(payload, "base_prices").append(dict(source(payload, "base_prices")[0], price_id="SYN-BASE-EUR", store_id="SYN-STORE-EUR", currency="EUR", price_minor=2000))
        source(payload, "observations").append(dict(observation, observation_id="SYN-OBS-EUR", store_id="SYN-STORE-EUR", currency="EUR", observed_minor=2001))
        result, _ = self.run_payload(payload)
        rows = result["outputs"]["review_packet"]["counts_by_store_currency"]
        self.assertEqual([(row["store_id"], row["currency"], row["matched"], row["mismatched"]) for row in rows], [("SYN-STORE-EUR", "EUR", 0, 1), ("SYN-STORE-N", "USD", 1, 0)])
        self.assertEqual([row["expected_minor"] for row in result["outputs"]["price_audit"]], [2000, 1000])
        self.assertEqual(result["outputs"]["reconciliation"]["input_observations"], 2)

    def test_trace_is_bounded_and_counts_actual_rows_not_visible_sample(self):
        result, events = self.run_payload(self.payload())
        self.assertEqual(len(events), 8)
        self.assertEqual(events[0]["kind"], "input")
        self.assertEqual(events[-1]["kind"], "output")
        self.assertEqual({event["kind"] for event in events}, {"input", "validation", "join", "decision", "exception", "output"})
        self.assertEqual(events[3]["tables"][0]["total_rows"], 32)
        self.assertEqual(len(events[3]["tables"][0]["rows"]), 8)
        self.assertEqual(events[6]["facts"]["issue_count"], len(result["exceptions"]))
        self.assertEqual([row[2] for row in events[5]["tables"][0]["rows"]], [1699, 719, 1000, 1550])
        payload = self.single()
        observation = source(payload, "observations")[0]
        replace_source(payload, "observations", [dict(observation, observation_id=f"SYN-OBS-{index:02d}") for index in range(12)])
        result, events = self.run_payload(payload)
        self.assertEqual(result["outputs"]["reconciliation"]["matched"], 12)
        self.assertEqual(events[2]["tables"][0]["total_rows"], 12)
        self.assertEqual(events[5]["tables"][0]["total_rows"], 12)
        self.assertEqual(len(events[5]["tables"][0]["rows"]), 8)
        for event in events:
            self.assertLessEqual(len(event["facts"]), 6)
            self.assertLessEqual(len(event["caption"]), 260)
            self.assertIn(len(event["tables"]), (1, 2))
            for table in event["tables"]:
                self.assertGreaterEqual(table["total_rows"], len(table["rows"]))
                self.assertLessEqual(len(table["rows"]), 8)
                self.assertLessEqual(len(table["columns"]), 6)
                self.assertTrue(all(cell is None or type(cell) in (str, bool, int, float) for row in table["rows"] for cell in row))

    def test_unexpected_implementation_failure_is_not_a_business_rejection(self):
        payload = self.single()
        self.promotion(payload, "SYN-PROMO-TEST", "best-price", "percent-off", 1000)
        with patch.object(self.baseline, "_price", side_effect=RuntimeError("unexpected calculation failure")):
            with self.assertRaisesRegex(RuntimeError, "unexpected calculation failure"):
                self.baseline.solve(payload)

    def test_baseline_import_boundary_and_complete_public_error_documentation(self):
        audit = baseline_import_audit(ROOT / "baseline.py")
        self.assertEqual(audit["status"], "static_import_check_pass")
        procedure = (ROOT / "HOW_TO.md").read_text(encoding="utf-8")
        for code, message in self.baseline.MESSAGES.items():
            with self.subTest(code=code):
                self.assertIn(f"`{code}`", procedure)
                self.assertIn(message, procedure)
        for action in self.baseline.ACTIONS.values():
            self.assertIn(action, procedure)
        for answer in ("holdout-a", "holdout-b", "2099-11-", "2099-12-", "904.5", "879.2", "expected/"):
            self.assertNotIn(answer, procedure)
        self.assertIn("UNKNOWN, not Installed", procedure)
        self.assertIn("October 2023", procedure)


if __name__ == "__main__":
    unittest.main()
