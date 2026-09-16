"""Scoped advisory-fee tests; never rewrite independent inputs, goldens, or locks."""
import copy
import hashlib
import importlib.util
import json
import random
import unittest
from pathlib import Path
from unittest.mock import patch

from scenarios._shared.comparison import compare_json
from scenarios._shared.contract import baseline_import_audit, load_scenario, validate_result, validate_trace
from scenarios._shared.pipeline import check_case_evidence, golden_lock


ROOT = Path(__file__).resolve().parents[1] / "financial-services" / "advisory-fee-reconciliation"
SPEC = importlib.util.spec_from_file_location("advisory_fee_baseline", ROOT / "baseline.py")
BASELINE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BASELINE)
SOURCES = ("engagements", "schedule_versions", "synthetic_value_intervals", "draft_fee_lines")


def fixture(case_id="demo"):
    return json.loads((ROOT / "mock-data" / f"{case_id}.json").read_text(encoding="utf-8"))


def one_account():
    payload = fixture("holdout-b")
    for source in SOURCES:
        payload[source] = [row for row in payload[source] if row["billing_account_id"] == "SYN-TIE-A"]
    return payload


def period(payload, start, end, as_of, *, offset=0, basis="actual-calendar-year"):
    payload["as_of"] = as_of
    payload["business_utc_offset_minutes"] = offset
    payload["billing_configuration"].update(period_start=start, period_end=end, day_count_basis=basis)
    for row in payload["engagements"]:
        row.update(active_from=start, active_to=None)
    for row in payload["schedule_versions"]:
        row.update(effective_from=start, effective_to=end, approved_at=f"{start}T00:00:00Z")
    for row in payload["synthetic_value_intervals"]:
        row.update(from_date=start, to_date=end)
    for row in payload["draft_fee_lines"]:
        row.update(period_start=start, period_end=end)
    return payload


class FeeTestCase(unittest.TestCase):
    def solve(self, payload):
        result, events = BASELINE.solve(payload)
        validate_result(result)
        self.assertEqual(result["outputs"]["review"]["human_review"], "pending")
        self.assertEqual(result["outputs"]["review"]["live_action"], "none")
        return result, events

    def rejected(self, payload, code, field=None):
        result, events = self.solve(payload)
        self.assertEqual(result["status"], "rejected")
        self.assertEqual(set(result["outputs"]), {"validation", "review"})
        self.assertEqual(result["outputs"]["validation"], {
            "accepted": False, "rejected_before_calculation": True,
        })
        self.assertEqual(len(result["exceptions"]), 1)
        self.assertEqual(result["exceptions"][0]["code"], code)
        if field is not None:
            self.assertEqual(result["exceptions"][0]["field"], field)
        self.assertEqual([event["kind"] for event in events], ["input", "validation", "output"])
        return result

    def account(self, result, account_id):
        return next(row for row in result["outputs"]["account_reviews"] if row["billing_account_id"] == account_id)

    def assert_population_conservation(self, result):
        totals = result["outputs"]["population_totals"]
        self.assertEqual(totals["computed"]["account_count"], sum(
            totals[name]["account_count"]
            for name in ("comparable", "computed_missing_draft", "computed_duplicate_drafts")
        ))
        self.assertEqual(totals["computed"]["fee_minor"], sum(
            totals[name]["computed_fee_minor"]
            for name in ("comparable", "computed_missing_draft", "computed_duplicate_drafts")
        ))
        self.assertEqual(totals["account_count"], sum(
            totals[name]["account_count"] for name in ("computed", "uncomputed", "not_billable")
        ))
        self.assertEqual(totals["comparable"]["delta_minor"],
                         totals["comparable"]["draft_fee_minor"] - totals["comparable"]["computed_fee_minor"])
        self.assertNotIn("computed_fee_minor", totals["uncomputed"])
        self.assertNotIn("computed_fee_minor", totals["not_billable"])


class ApprovedCaseAndEvidenceTests(FeeTestCase):
    def test_five_full_manually_authored_envelopes_and_traces(self):
        scenario = load_scenario(ROOT)
        golden_lock(scenario)
        for case in scenario.cases:
            with self.subTest(case=case["id"]):
                payload = fixture(case["id"])
                pristine = copy.deepcopy(payload)
                result, events = self.solve(payload)
                manual = json.loads((ROOT / case["expected"]).read_text(encoding="utf-8"))
                self.assertEqual(compare_json(manual, result), [])
                self.assertEqual(payload, pristine)
                input_hash = hashlib.sha256((ROOT / case["input"]).read_bytes()).hexdigest()
                trace = {
                    "schema_version": 1, "scenario_id": scenario.id,
                    "provenance": "synthetic-local-baseline", "input_sha256": input_hash,
                    "events": [dict(event, sequence=index) for index, event in enumerate(events, 1)],
                }
                validate_trace(trace, scenario, case, input_hash)
                if result["status"] != "rejected":
                    self.assert_population_conservation(result)

    def test_recorded_subprocess_evidence_is_current(self):
        scenario = load_scenario(ROOT)
        for case in scenario.cases:
            with self.subTest(case=case["id"]):
                report = check_case_evidence(scenario, case)
                self.assertEqual(report["state"], "baseline_pass")
                self.assertEqual(report["local"]["comparison"], "pass")
                self.assertEqual(report["native"]["creation"], "native_creation_blocked")
                self.assertEqual(report["native"]["installation"], "not_run")
                self.assertEqual(report["native"]["independent_invocation"], "not_run")

    def test_static_import_audit_is_stdlib_and_adapter_only(self):
        audit = baseline_import_audit(ROOT / "baseline.py")
        self.assertEqual(audit["status"], "static_import_check_pass")
        self.assertIn("fractions", audit["imports"])
        self.assertIn("scenario_support", audit["imports"])

    def test_every_valid_source_permutation_preserves_result_and_events(self):
        for case_id in ("demo", "holdout-a", "holdout-b", "negative-contradictory"):
            original = fixture(case_id)
            reference = self.solve(original)
            for seed in range(8):
                with self.subTest(case=case_id, seed=seed):
                    payload = copy.deepcopy(original)
                    generator = random.Random(seed)
                    for source in SOURCES:
                        generator.shuffle(payload[source])
                    pristine = copy.deepcopy(payload)
                    self.assertEqual(self.solve(payload), reference)
                    self.assertEqual(payload, pristine)

    def test_solve_needs_no_file_access(self):
        payloads = [fixture(name) for name in (
            "demo", "holdout-a", "holdout-b", "negative-malformed", "negative-contradictory",
        )]
        with patch("builtins.open", side_effect=AssertionError("solve must not read files")):
            for payload in payloads:
                self.solve(payload)

    def test_unexpected_implementation_error_is_not_a_business_rejection(self):
        with patch.object(BASELINE, "_calculate_tiers", side_effect=RuntimeError("test failure")):
            with self.assertRaisesRegex(RuntimeError, "test failure"):
                BASELINE.solve(fixture())

    def test_demo_has_eight_actual_meaningful_steps(self):
        result, events = self.solve(fixture())
        self.assertEqual([event["step_id"] for event in events], [
            "intake-billing-exports", "validate-billing-evidence", "join-effective-segments",
            "calculate-marginal-tiers", "prorate-and-round", "join-draft-fees",
            "route-billing-exceptions", "emit-billing-review",
        ])
        self.assertEqual({event["kind"] for event in events}, {
            "input", "validation", "join", "decision", "exception", "output",
        })
        self.assertEqual(events[0]["tables"][0]["rows"], [
            ["engagements", 3], ["schedule_versions", 5],
            ["synthetic_value_intervals", 3], ["draft_fee_lines", 2],
        ])
        self.assertEqual(events[2]["tables"][0]["total_rows"], 4)
        self.assertEqual(events[3]["tables"][0]["total_rows"], 7)
        self.assertIn(["SYN-A", 1, 2, 5000000, 50, 250000000], events[3]["tables"][0]["rows"])
        self.assertIn(["SYN-A", 1, 15, 365, 375000, 73], events[4]["tables"][0]["rows"])
        self.assertIn(["SYN-A", "675000/73", 9247, "above-half-up"], events[4]["tables"][1]["rows"])
        self.assertEqual(events[6]["facts"]["exceptions"], len(result["exceptions"]))
        self.assertEqual(events[-1]["facts"]["computed_minor"], 18836)
        self.assertEqual(events[-1]["facts"]["comparable_delta_minor"], 1027)


class StrictInputTests(FeeTestCase):
    def test_root_and_source_types_are_strict(self):
        self.rejected([], "invalid-object", "$")
        for source in SOURCES:
            for invalid in (None, {}, "rows", 0, False):
                with self.subTest(source=source, value=invalid):
                    payload = fixture()
                    payload[source] = invalid
                    self.rejected(payload, "invalid-array", source)
        for invalid in (None, [], "account", 2):
            payload = fixture()
            payload["engagements"][0] = invalid
            self.rejected(payload, "invalid-object", "engagements[0]")

    def test_unknown_fields_rejected_at_every_object_level(self):
        for target in ("root", "configuration", "engagement", "schedule", "band", "value", "draft"):
            with self.subTest(target=target):
                payload = fixture()
                obj = {
                    "root": payload,
                    "configuration": payload["billing_configuration"],
                    "engagement": payload["engagements"][0],
                    "schedule": payload["schedule_versions"][0],
                    "band": payload["schedule_versions"][0]["bands"][0],
                    "value": payload["synthetic_value_intervals"][0],
                    "draft": payload["draft_fee_lines"][0],
                }[target]
                obj["unsupported"] = "must not be ignored"
                self.rejected(payload, "invalid-fields")

    def test_unsupported_financial_extensions_are_not_silent_settings(self):
        for setting in ("household", "performance_fees", "flat_fee", "tax", "minimum_fee", "market_price", "quantity"):
            payload = fixture()
            payload["billing_configuration"][setting] = 1
            self.rejected(payload, "invalid-fields", "billing_configuration")

    def test_required_fields_and_explicit_null_rules(self):
        for field in ("as_of", "business_utc_offset_minutes", "schema_version"):
            payload = fixture()
            del payload[field]
            self.rejected(payload, "invalid-fields", "$")
        for field in ("rounding_mode", "day_count_basis", "approval_state", "control_version"):
            payload = fixture()
            del payload["billing_configuration"][field]
            self.rejected(payload, "invalid-fields", "billing_configuration")
        payload = fixture()
        del payload["engagements"][0]["active_to"]
        self.rejected(payload, "invalid-fields")
        payload = fixture()
        payload["schedule_versions"][0]["effective_to"] = None
        self.rejected(payload, "invalid-date")

    def test_schema_version_rejects_boolean_float_and_string(self):
        for invalid in (True, False, 1.0, "1", None, 0, 2):
            payload = fixture()
            payload["schema_version"] = invalid
            self.rejected(payload, "invalid-integer", "schema_version")

    def test_money_values_and_draft_amounts_reject_coercion_and_bounds(self):
        for source, key in (("synthetic_value_intervals", "billable_value_minor"), ("draft_fee_lines", "amount_minor")):
            for invalid in (True, False, 1.0, "1", None, -1, 1000000000001):
                with self.subTest(source=source, value=invalid):
                    payload = fixture()
                    payload[source][0][key] = invalid
                    self.rejected(payload, "invalid-integer")

    def test_bps_rejects_boolean_and_out_of_range(self):
        for invalid in (True, False, 100.0, "100", None, -1, 10001):
            payload = fixture()
            payload["schedule_versions"][0]["bands"][0]["annual_rate_bps"] = invalid
            self.rejected(payload, "invalid-integer",
                          "schedule_versions[SYN-SCH-A1].bands[0].annual_rate_bps")

    def test_tolerance_default_is_explicit_and_null_is_not_default(self):
        payload = fixture()
        del payload["billing_configuration"]["variance_tolerance_minor"]
        result, _ = self.solve(payload)
        self.assertEqual(result["outputs"]["billing_period"]["variance_tolerance_minor"], 1)
        for invalid in (True, False, 1.0, "1", None, -1, 1000000000001):
            payload["billing_configuration"]["variance_tolerance_minor"] = invalid
            self.rejected(payload, "invalid-integer", "billing_configuration.variance_tolerance_minor")

    def test_fixed_offset_requires_a_true_integer_within_bounds(self):
        for invalid in (True, False, 0.0, "-300", None, -841, 841):
            payload = fixture()
            payload["business_utc_offset_minutes"] = invalid
            self.rejected(payload, "invalid-integer", "business_utc_offset_minutes")

    def test_malformed_timestamp_is_not_defaulted_or_truncated(self):
        for invalid in (
            None, True, {}, "2026-05-01", "2026-05-01T00:00:00",
            "2026-05-01t00:00:00z", "2026-05-01T00:00:00-00:00",
            "2026-05-01T00:00:00+24:00", "2026-05-01T00:00:00+01:60",
            "2026-02-30T00:00:00Z", "2026-05-01T24:00:00Z",
            "2026-05-01T00:00:60Z", "2026-05-01T00:00:00.1234567Z",
            "0001-01-01T00:00:00+14:00",
        ):
            with self.subTest(value=invalid):
                payload = fixture()
                payload["as_of"] = invalid
                self.rejected(payload, "invalid-timestamp", "as_of")

    def test_date_only_fields_are_strict(self):
        for invalid in ("2026-4-01", "2026-02-30", "2026-04-01T00:00:00Z", "", 20260401, None):
            payload = fixture()
            payload["billing_configuration"]["period_start"] = invalid
            self.rejected(payload, "invalid-date", "billing_configuration.period_start")

    def test_synthetic_ids_are_exact_ascii_not_normalized(self):
        for invalid in (" SYN-A", "SYN-A ", "syn-a", "A", "SYN-", "SYN-É", "SYN-" + "A" * 77, True):
            payload = fixture()
            payload["engagements"][0]["billing_account_id"] = invalid
            self.rejected(payload, "invalid-id")

    def test_every_technical_source_id_is_strictly_unique(self):
        for source in SOURCES:
            for identical in (True, False):
                with self.subTest(source=source, identical=identical):
                    payload = fixture()
                    duplicate = copy.deepcopy(payload[source][0])
                    if not identical:
                        if source == "engagements":
                            duplicate["agreement_id"] = "SYN-ANOTHER"
                        elif source == "schedule_versions":
                            duplicate["bands"][0]["annual_rate_bps"] = 77
                        elif source == "synthetic_value_intervals":
                            duplicate["billable_value_minor"] = 5
                        else:
                            duplicate["amount_minor"] = 0
                    payload[source].append(duplicate)
                    self.rejected(payload, "duplicate-id")

    def test_source_caps_reject_before_duplicate_processing(self):
        for source in SOURCES:
            payload = fixture()
            payload[source] = [copy.deepcopy(payload[source][0])] * 5001
            self.rejected(payload, "invalid-array", source)

    def test_unknown_enums_reject_without_unhashable_type_errors(self):
        for key in ("approval_state", "currency", "day_count_basis", "rounding_mode"):
            for invalid in ("unknown", {}, [], True, None):
                payload = fixture()
                payload["billing_configuration"][key] = invalid
                self.rejected(payload, "invalid-enum", f"billing_configuration.{key}")

    def test_top_level_pending_control_rejects_before_financial_decisions(self):
        payload = fixture()
        payload["billing_configuration"]["approval_state"] = "pending"
        self.rejected(payload, "policy-not-approved", "billing_configuration.approval_state")

    def test_authoritative_unknown_accounts_agreements_and_currencies_reject(self):
        for source in ("schedule_versions", "synthetic_value_intervals"):
            payload = fixture()
            payload[source][0]["billing_account_id"] = "SYN-UNKNOWN"
            self.rejected(payload, "unknown-account")
        payload = fixture()
        payload["schedule_versions"][0]["agreement_id"] = "SYN-WRONG-AGREEMENT"
        self.rejected(payload, "agreement-mismatch")
        for source in ("engagements", "synthetic_value_intervals"):
            payload = fixture()
            payload[source][0]["currency"] = "EUR"
            self.rejected(payload, "currency-mismatch")

    def test_approval_fields_and_pending_records_are_validated(self):
        payload = fixture()
        payload["schedule_versions"][0]["approved_at"] = None
        self.rejected(payload, "invalid-approval")
        payload = fixture()
        payload["schedule_versions"][3]["approved_at"] = "2026-04-01T00:00:00Z"
        self.rejected(payload, "invalid-approval")
        payload = fixture()
        payload["schedule_versions"][3]["bands"][0]["annual_rate_bps"] = True
        self.rejected(payload, "invalid-integer")

    def test_empty_export_set_is_valid_and_has_no_invented_accounts(self):
        payload = fixture()
        for source in SOURCES:
            payload[source] = []
        result, events = self.solve(payload)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["outputs"]["account_reviews"], [])
        self.assertEqual(result["outputs"]["calculation_segments"], [])
        self.assertEqual(result["outputs"]["population_totals"]["account_count"], 0)
        self.assertEqual(len(events), 8)
        self.assert_population_conservation(result)


class TemporalAndCoverageTests(FeeTestCase):
    def test_offset_closure_is_inclusive_and_not_utc_calendar_midnight(self):
        payload = fixture("holdout-b")
        result, _ = self.solve(payload)
        self.assertNotEqual(result["status"], "rejected")
        payload["as_of"] = "2026-01-02T04:59:59.999999Z"
        self.rejected(payload, "period-not-closed", "billing_configuration.period_end")
        for offset, instant in ((840, "2026-01-01T10:00:00Z"), (-840, "2026-01-02T14:00:00Z")):
            payload = fixture("holdout-b")
            payload["business_utc_offset_minutes"] = offset
            payload["as_of"] = instant
            result, _ = self.solve(payload)
            self.assertEqual(result["outputs"]["population_totals"]["computed"]["fee_minor"], 275)

    def test_approved_at_as_of_equality_and_offset_equivalence(self):
        payload = fixture()
        payload["schedule_versions"][1]["approved_at"] = "2026-04-30T19:00:00-05:00"
        result, _ = self.solve(payload)
        self.assertEqual(self.account(result, "SYN-A")["computed_fee_minor"], 9247)
        self.assertNotIn("SYN-SCH-A2", [row["schedule_id"] for row in result["outputs"]["pending_changes"]])

    def test_future_approval_does_not_fill_missing_schedule(self):
        payload = fixture()
        payload["schedule_versions"][1]["approved_at"] = "2026-05-01T00:00:00.000001Z"
        result, _ = self.solve(payload)
        account = self.account(result, "SYN-A")
        self.assertEqual(account["calculation_status"], "held-missing-coverage")
        self.assertEqual(account["comparison_status"], "uncomputed")
        self.assertIsNone(account["computed_fee_minor"])
        self.assertEqual(account["draft_fee_minor"], 10274)
        self.assertIn("SYN-SCH-A2", account["pending_change_ids"])
        self.assertEqual(account["review_flags"], [
            "approved-after-as-of", "missing-schedule-coverage", "uncomputed-draft",
        ])
        self.assertEqual(result["outputs"]["population_totals"]["computed"]["fee_minor"], 9589)
        self.assertEqual(result["outputs"]["population_totals"]["comparable"]["computed_fee_minor"], 5479)
        self.assert_population_conservation(result)

    def test_ineligible_overlap_is_visible_but_not_authoritative(self):
        payload = fixture()
        future = copy.deepcopy(payload["schedule_versions"][0])
        future.update(schedule_id="SYN-SCH-A-FUTURE", effective_to="2026-05-01",
                      approved_at="2026-05-02T00:00:00Z")
        payload["schedule_versions"].append(future)
        result, _ = self.solve(payload)
        self.assertEqual(self.account(result, "SYN-A")["computed_fee_minor"], 9247)
        self.assertIn("approved-after-as-of", self.account(result, "SYN-A")["review_flags"])
        self.assertNotEqual(result["status"], "rejected")

    def test_pending_rate_never_changes_a_complete_approved_calculation(self):
        payload = fixture()
        reference, _ = self.solve(payload)
        payload["schedule_versions"][3]["bands"][0]["annual_rate_bps"] = 10000
        result, _ = self.solve(payload)
        self.assertEqual(result, reference)
        self.assertEqual(self.account(result, "SYN-B")["computed_fee_minor"], 5479)
        self.assertEqual(self.account(result, "SYN-B")["comparison_status"], "matched")
        self.assertEqual(self.account(result, "SYN-B")["review_flags"], ["pending-approval"])

    def test_approved_overlap_rejects_even_equal_rates(self):
        payload = fixture()
        duplicate = copy.deepcopy(payload["schedule_versions"][0])
        duplicate["schedule_id"] = "SYN-SCH-A0"
        payload["schedule_versions"].append(duplicate)
        result = self.rejected(payload, "overlapping-approved-schedules")
        self.assertEqual(result["exceptions"][0]["related_ids"], ["SYN-SCH-A0", "SYN-SCH-A1"])

    def test_value_overlap_rejects_even_equal_values(self):
        payload = fixture()
        duplicate = copy.deepcopy(payload["synthetic_value_intervals"][0])
        duplicate.update(valuation_id="SYN-VAL-A2", from_date="2026-04-30")
        payload["synthetic_value_intervals"].append(duplicate)
        result = self.rejected(payload, "overlapping-value-intervals")
        self.assertEqual(result["exceptions"][0]["from_date"], "2026-04-30")
        self.assertEqual(result["exceptions"][0]["to_date"], "2026-05-01")

    def test_authoritative_overlap_outside_billable_period_still_rejects(self):
        for source, id_key, start_key, end_key, code in (
            ("schedule_versions", "schedule_id", "effective_from", "effective_to", "overlapping-approved-schedules"),
            ("synthetic_value_intervals", "valuation_id", "from_date", "to_date", "overlapping-value-intervals"),
        ):
            payload = fixture()
            first = copy.deepcopy(payload[source][0])
            second = copy.deepcopy(first)
            first.update({id_key: "SYN-OUTSIDE-1", start_key: "2026-06-01", end_key: "2026-06-10"})
            second.update({id_key: "SYN-OUTSIDE-2", start_key: "2026-06-05", end_key: "2026-06-15"})
            payload[source].extend([first, second])
            self.rejected(payload, code)

    def test_adjacent_value_intervals_split_without_overlap_or_rerounding(self):
        payload = fixture()
        value = payload["synthetic_value_intervals"][2]
        following = copy.deepcopy(value)
        value["to_date"] = "2026-04-16"
        following.update(valuation_id="SYN-VAL-C2", from_date="2026-04-16")
        payload["synthetic_value_intervals"].append(following)
        result, _ = self.solve(payload)
        segments = [row for row in result["outputs"]["calculation_segments"] if row["billing_account_id"] == "SYN-C"]
        self.assertEqual([row["days"] for row in segments], [15, 15])
        self.assertEqual(self.account(result, "SYN-C")["computed_fee_minor"], 4110)
        self.assertEqual(self.account(result, "SYN-C")["exact_fee_minor"], {"numerator": 300000, "denominator": 73})

    def test_missing_value_day_holds_whole_account_without_partial_fees(self):
        payload = fixture()
        payload["synthetic_value_intervals"][2]["from_date"] = "2026-04-02"
        result, _ = self.solve(payload)
        account = self.account(result, "SYN-C")
        self.assertEqual(account["calculation_status"], "held-missing-coverage")
        self.assertEqual(account["review_flags"], ["missing-draft", "missing-value-coverage"])
        segments = [row for row in result["outputs"]["calculation_segments"] if row["billing_account_id"] == "SYN-C"]
        self.assertEqual([row["coverage"] for row in segments], ["missing-value", "complete"])
        for row in segments:
            self.assertEqual(row["calculation_status"], "held-account")
            self.assertEqual(row["bands"], [])
            self.assertIsNone(row["exact_fee_minor"])
            self.assertIsNone(row["annual_numerator"])
        self.assertIsNone(account["computed_fee_minor"])
        self.assertEqual(result["outputs"]["population_totals"]["computed"]["fee_minor"], 14726)
        self.assertEqual(result["outputs"]["population_totals"]["uncomputed"], {
            "account_count": 1, "billing_account_ids": ["SYN-C"],
        })
        self.assert_population_conservation(result)

    def test_missing_schedule_day_never_selects_latest_or_forward_fills(self):
        payload = fixture()
        payload["schedule_versions"][0]["effective_to"] = "2026-04-15"
        result, _ = self.solve(payload)
        segments = [row for row in result["outputs"]["calculation_segments"] if row["billing_account_id"] == "SYN-A"]
        self.assertEqual([row["coverage"] for row in segments], ["complete", "missing-schedule", "complete"])
        self.assertEqual([row["days"] for row in segments], [14, 1, 15])
        self.assertTrue(all(row["exact_fee_minor"] is None for row in segments))
        self.assertEqual(self.account(result, "SYN-A")["comparison_status"], "uncomputed")

    def test_both_missing_sources_produce_two_gap_diagnostics_not_zero(self):
        payload = one_account()
        payload["schedule_versions"] = []
        payload["synthetic_value_intervals"] = []
        payload["draft_fee_lines"] = []
        result, _ = self.solve(payload)
        segment = result["outputs"]["calculation_segments"][0]
        self.assertEqual(segment["coverage"], "missing-schedule-and-value")
        self.assertIsNone(segment["billable_value_minor"])
        self.assertEqual([row["code"] for row in result["exceptions"]], [
            "missing-draft", "missing-schedule-coverage", "missing-value-coverage",
        ])
        self.assertEqual(result["outputs"]["population_totals"]["computed"]["account_count"], 0)

    def test_engagement_start_is_included_and_termination_is_excluded(self):
        demo, _ = self.solve(fixture())
        leap, _ = self.solve(fixture("holdout-a"))
        self.assertEqual(self.account(demo, "SYN-B")["active_days"], 20)
        self.assertEqual(self.account(leap, "SYN-LEAP-B")["active_days"], 10)
        self.assertEqual(self.account(leap, "SYN-LEAP-B")["active_end"], "2024-02-11")

    def test_inactive_accounts_and_outside_changes_have_complete_dispositions(self):
        payload = fixture()
        payload["engagements"][2]["active_from"] = "2026-05-01"
        pending = copy.deepcopy(payload["schedule_versions"][4])
        pending.update(schedule_id="SYN-SCH-C-PENDING", approval_state="pending", approved_at=None)
        payload["schedule_versions"].append(pending)
        result, _ = self.solve(payload)
        account = self.account(result, "SYN-C")
        self.assertEqual(account["calculation_status"], "not-billable")
        self.assertEqual(account["active_days"], 0)
        self.assertIsNone(account["active_start"])
        self.assertIsNone(account["active_end"])
        self.assertIsNone(account["computed_fee_minor"])
        self.assertEqual(account["review_flags"], [])
        change = next(row for row in result["outputs"]["pending_changes"] if row["schedule_id"] == "SYN-SCH-C-PENDING")
        self.assertFalse(change["intersects_billable_period"])
        self.assertIn({"valuation_id": "SYN-VAL-C", "billing_account_id": "SYN-C", "disposition": "outside-billable-period"},
                      result["outputs"]["evidence_dispositions"]["synthetic_value_intervals"])
        self.assert_population_conservation(result)

    def test_invalid_source_intervals_reject(self):
        for source, start_key, end_key in (
            ("engagements", "active_from", "active_to"),
            ("schedule_versions", "effective_from", "effective_to"),
            ("synthetic_value_intervals", "from_date", "to_date"),
            ("draft_fee_lines", "period_start", "period_end"),
        ):
            payload = fixture()
            payload[source][0][end_key] = payload[source][0][start_key]
            self.rejected(payload, "invalid-interval")

    def test_period_bounds_zero_reversed_and_more_than_366_reject(self):
        for start, end in (("2026-01-01", "2026-01-01"), ("2026-01-02", "2026-01-01"),
                           ("2023-12-31", "2025-01-01")):
            payload = period(one_account(), start, end, "2026-01-02T00:00:00Z")
            self.rejected(payload, "invalid-period", "billing_configuration")

    def test_full_366_day_period_is_allowed(self):
        payload = period(one_account(), "2024-01-01", "2025-01-01", "2025-01-01T00:00:00Z")
        result, _ = self.solve(payload)
        account = result["outputs"]["account_reviews"][0]
        self.assertEqual(account["active_days"], 366)
        self.assertEqual(account["exact_fee_minor"], {"numerator": 365, "denominator": 2})
        self.assertEqual(account["computed_fee_minor"], 183)


class MarginalAndRoundingTests(FeeTestCase):
    def test_half_even_changes_only_the_exact_half_cent_account(self):
        payload = fixture("holdout-b")
        payload["billing_configuration"]["rounding_mode"] = "half-even"
        result, _ = self.solve(payload)
        self.assertEqual(self.account(result, "SYN-TIE-A")["computed_fee_minor"], 0)
        self.assertEqual(self.account(result, "SYN-TIE-A")["rounding_decision"], "half-even-down")
        self.assertEqual(self.account(result, "SYN-TIE-B")["computed_fee_minor"], 274)
        self.assertEqual(result["outputs"]["population_totals"]["computed"]["fee_minor"], 274)
        self.assertEqual(result["status"], "completed")

    def test_half_even_odd_lower_cent_rounds_up(self):
        payload = one_account()
        payload["billing_configuration"]["rounding_mode"] = "half-even"
        payload["synthetic_value_intervals"][0]["billable_value_minor"] = 109500
        result, _ = self.solve(payload)
        account = result["outputs"]["account_reviews"][0]
        self.assertEqual(account["exact_fee_minor"], {"numerator": 3, "denominator": 2})
        self.assertEqual(account["computed_fee_minor"], 2)
        self.assertEqual(account["rounding_decision"], "half-even-up")

    def test_round_once_after_summing_two_half_cent_segments(self):
        payload = period(one_account(), "2026-01-01", "2026-01-03", "2026-01-03T00:00:00Z",
                         basis="act-365-fixed")
        first = payload["synthetic_value_intervals"][0]
        following = copy.deepcopy(first)
        first["to_date"] = "2026-01-02"
        following.update(valuation_id="SYN-SECOND-VALUE", from_date="2026-01-02")
        payload["synthetic_value_intervals"].append(following)
        result, _ = self.solve(payload)
        self.assertEqual([row["exact_fee_minor"] for row in result["outputs"]["calculation_segments"]], [
            {"numerator": 1, "denominator": 2}, {"numerator": 1, "denominator": 2},
        ])
        account = result["outputs"]["account_reviews"][0]
        self.assertEqual(account["exact_fee_minor"], {"numerator": 1, "denominator": 1})
        self.assertEqual(account["computed_fee_minor"], 1)
        self.assertEqual(account["rounding_decision"], "exact")

    def test_actual_calendar_year_splits_365_and_366_exactly(self):
        payload = period(one_account(), "2023-12-31", "2024-01-02", "2024-01-02T00:00:00Z")
        result, _ = self.solve(payload)
        segments = result["outputs"]["calculation_segments"]
        self.assertEqual([row["day_count_denominator"] for row in segments], [365, 366])
        self.assertEqual([row["days"] for row in segments], [1, 1])
        self.assertEqual([row["exact_fee_minor"] for row in segments], [
            {"numerator": 1, "denominator": 2}, {"numerator": 365, "denominator": 732},
        ])
        self.assertEqual(result["outputs"]["account_reviews"][0]["exact_fee_minor"],
                         {"numerator": 731, "denominator": 732})
        self.assertEqual(result["outputs"]["account_reviews"][0]["computed_fee_minor"], 1)
        payload["billing_configuration"]["day_count_basis"] = "act-365-fixed"
        fixed, _ = self.solve(payload)
        self.assertEqual(len(fixed["outputs"]["calculation_segments"]), 1)
        self.assertEqual(fixed["outputs"]["account_reviews"][0]["rounding_decision"], "exact")
        self.assertEqual(fixed["outputs"]["account_reviews"][0]["exact_fee_minor"],
                         {"numerator": 1, "denominator": 1})

    def test_gregorian_century_leap_rules(self):
        for year, divisor, days, rounded in ((1900, 365, 1, 1), (2000, 366, 2, 1), (2100, 365, 1, 1)):
            payload = period(one_account(), f"{year}-02-28", f"{year}-03-01", f"{year}-03-01T00:00:00Z")
            result, _ = self.solve(payload)
            segment = result["outputs"]["calculation_segments"][0]
            self.assertEqual(segment["day_count_denominator"], divisor)
            self.assertEqual(segment["days"], days)
            self.assertEqual(result["outputs"]["account_reviews"][0]["computed_fee_minor"], rounded)

    def test_exact_tier_breakpoint_and_one_cent_above_are_marginal(self):
        for value, second_slice, annual in ((10000000, 0, 1000000000), (10000001, 1, 1000000050)):
            payload = fixture("holdout-b")
            payload["synthetic_value_intervals"][1]["billable_value_minor"] = value
            result, _ = self.solve(payload)
            segment = next(row for row in result["outputs"]["calculation_segments"] if row["billing_account_id"] == "SYN-TIE-B")
            self.assertEqual([band["band_value_minor"] for band in segment["bands"]], [10000000, second_slice])
            self.assertEqual(segment["annual_numerator"], annual)
            self.assertEqual(sum(band["band_value_minor"] for band in segment["bands"]), value)
            self.assertEqual(self.account(result, "SYN-TIE-B")["computed_fee_minor"], 274)

    def test_multiple_finite_tiers_preserve_contiguous_slice_conservation(self):
        payload = one_account()
        payload["synthetic_value_intervals"][0]["billable_value_minor"] = 250
        payload["schedule_versions"][0]["bands"] = [
            {"upper_value_minor": 100, "annual_rate_bps": 10000},
            {"upper_value_minor": 200, "annual_rate_bps": 5000},
            {"upper_value_minor": None, "annual_rate_bps": 0},
        ]
        result, _ = self.solve(payload)
        segment = result["outputs"]["calculation_segments"][0]
        self.assertEqual([row["lower_value_minor"] for row in segment["bands"]], [0, 100, 200])
        self.assertEqual([row["band_value_minor"] for row in segment["bands"]], [100, 100, 50])
        self.assertEqual(segment["annual_numerator"], 1500000)
        self.assertEqual(segment["exact_fee_minor"], {"numerator": 30, "denominator": 73})
        self.assertEqual(result["outputs"]["account_reviews"][0]["computed_fee_minor"], 0)

    def test_invalid_tier_order_coverage_and_types_reject(self):
        invalid_bands = (
            ([], "invalid-bands"),
            ([{"upper_value_minor": 100, "annual_rate_bps": 100}], "invalid-bands"),
            ([{"upper_value_minor": None, "annual_rate_bps": 100},
              {"upper_value_minor": None, "annual_rate_bps": 50}], "invalid-bands"),
            ([{"upper_value_minor": 100, "annual_rate_bps": 100},
              {"upper_value_minor": 100, "annual_rate_bps": 50},
              {"upper_value_minor": None, "annual_rate_bps": 0}], "invalid-bands"),
            ([{"upper_value_minor": 200, "annual_rate_bps": 100},
              {"upper_value_minor": 100, "annual_rate_bps": 50},
              {"upper_value_minor": None, "annual_rate_bps": 0}], "invalid-bands"),
            ([{"upper_value_minor": 0, "annual_rate_bps": 100},
              {"upper_value_minor": None, "annual_rate_bps": 50}], "invalid-integer"),
            ([{"upper_value_minor": True, "annual_rate_bps": 100},
              {"upper_value_minor": None, "annual_rate_bps": 50}], "invalid-integer"),
            ([{"upper_value_minor": None, "annual_rate_bps": 100, "lower_value_minor": 1}], "invalid-fields"),
        )
        for bands, code in invalid_bands:
            with self.subTest(bands=bands):
                payload = one_account()
                payload["schedule_versions"][0]["bands"] = bands
                self.rejected(payload, code)

    def test_zero_value_and_zero_rate_are_real_computed_zero_fees(self):
        for zero_value in (True, False):
            payload = one_account()
            if zero_value:
                payload["synthetic_value_intervals"][0]["billable_value_minor"] = 0
            else:
                payload["schedule_versions"][0]["bands"][0]["annual_rate_bps"] = 0
            result, _ = self.solve(payload)
            account = result["outputs"]["account_reviews"][0]
            self.assertEqual(account["calculation_status"], "computed")
            self.assertEqual(account["computed_fee_minor"], 0)
            self.assertEqual(account["exact_fee_minor"], {"numerator": 0, "denominator": 1})
            self.assertEqual(account["comparison_status"], "matched")
            self.assertEqual(result["status"], "completed")

    def test_maximum_value_and_rate_use_unbounded_exact_intermediates(self):
        payload = one_account()
        payload["synthetic_value_intervals"][0]["billable_value_minor"] = 1000000000000
        payload["schedule_versions"][0]["bands"][0]["annual_rate_bps"] = 10000
        result, _ = self.solve(payload)
        segment = result["outputs"]["calculation_segments"][0]
        self.assertEqual(segment["annual_numerator"], 10000000000000000)
        self.assertEqual(segment["exact_fee_minor"], {"numerator": 200000000000, "denominator": 73})
        self.assertEqual(result["outputs"]["account_reviews"][0]["computed_fee_minor"], 2739726027)
        period(payload, "2024-01-01", "2025-01-01", "2025-01-01T00:00:00Z", basis="act-365-fixed")
        full_year, _ = self.solve(payload)
        self.assertEqual(full_year["outputs"]["account_reviews"][0]["computed_fee_minor"], 1002739726027)


class DraftAndClosureTests(FeeTestCase):
    def test_missing_draft_is_not_a_zero_draft(self):
        payload = one_account()
        zero, _ = self.solve(payload)
        payload["draft_fee_lines"] = []
        missing, _ = self.solve(payload)
        self.assertEqual(zero["outputs"]["account_reviews"][0]["delta_minor"], -1)
        self.assertEqual(zero["outputs"]["account_reviews"][0]["draft_fee_minor"], 0)
        self.assertIsNone(missing["outputs"]["account_reviews"][0]["delta_minor"])
        self.assertIsNone(missing["outputs"]["account_reviews"][0]["draft_fee_minor"])
        self.assertEqual(missing["outputs"]["draft_comparisons"], [])
        self.assertEqual(missing["outputs"]["population_totals"]["comparable"]["account_count"], 0)
        self.assertEqual(missing["outputs"]["population_totals"]["computed_missing_draft"]["computed_fee_minor"], 1)

    def test_duplicate_business_key_is_held_not_summed_or_selected(self):
        result, _ = self.solve(fixture("holdout-a"))
        account = self.account(result, "SYN-LEAP-B")
        self.assertEqual(account["computed_fee_minor"], 1366)
        self.assertEqual(account["comparison_status"], "duplicate-drafts")
        self.assertIsNone(account["draft_fee_minor"])
        self.assertIsNone(account["delta_minor"])
        duplicate_rows = [row for row in result["outputs"]["draft_comparisons"] if row["billing_account_id"] == "SYN-LEAP-B"]
        self.assertEqual(len(duplicate_rows), 2)
        self.assertTrue(all(row["disposition"] == "duplicate-draft" for row in duplicate_rows))
        self.assertTrue(all(row["computed_fee_minor"] is None for row in duplicate_rows))
        self.assertEqual(result["outputs"]["population_totals"]["comparable"]["draft_fee_minor"], 5205)
        self.assert_population_conservation(result)

    def test_uncomputed_duplicate_precedence_and_population_partition(self):
        payload = fixture("holdout-a")
        payload["synthetic_value_intervals"] = [
            row for row in payload["synthetic_value_intervals"] if row["billing_account_id"] != "SYN-LEAP-B"
        ]
        result, _ = self.solve(payload)
        account = self.account(result, "SYN-LEAP-B")
        self.assertEqual(account["comparison_status"], "uncomputed")
        self.assertEqual(account["review_flags"], ["duplicate-drafts", "missing-value-coverage"])
        self.assertEqual(result["outputs"]["population_totals"]["computed_duplicate_drafts"]["account_count"], 0)
        self.assertEqual(result["outputs"]["population_totals"]["uncomputed"]["account_count"], 1)
        self.assert_population_conservation(result)

    def test_orphan_wrong_period_wrong_currency_precedence_and_row_closure(self):
        payload = fixture("holdout-b")
        base = payload["draft_fee_lines"][0]
        orphan = dict(base, draft_id="SYN-EXTRA-ORPHAN", billing_account_id="SYN-NO-ACCOUNT",
                      period_start="2025-12-31", period_end="2026-01-01", currency="EUR")
        wrong_period = dict(base, draft_id="SYN-EXTRA-PERIOD", period_start="2025-12-31",
                            period_end="2026-01-01", currency="EUR")
        wrong_currency = dict(base, draft_id="SYN-EXTRA-CURRENCY", currency="EUR")
        payload["draft_fee_lines"].extend([orphan, wrong_period, wrong_currency])
        result, _ = self.solve(payload)
        rows = {row["draft_id"]: row for row in result["outputs"]["draft_comparisons"]}
        self.assertEqual(len(rows), 5)
        self.assertEqual(rows["SYN-EXTRA-ORPHAN"]["disposition"], "orphan-account")
        self.assertEqual(rows["SYN-EXTRA-PERIOD"]["disposition"], "wrong-period")
        self.assertEqual(rows["SYN-EXTRA-CURRENCY"]["disposition"], "wrong-currency")
        for row in (orphan, wrong_period, wrong_currency):
            self.assertIsNone(rows[row["draft_id"]]["delta_minor"])
            self.assertIsNone(rows[row["draft_id"]]["computed_fee_minor"])
        self.assertEqual(self.account(result, "SYN-TIE-A")["draft_ids"], ["SYN-DFT-TIE-A"])
        self.assertEqual(result["outputs"]["population_totals"]["comparable"]["computed_fee_minor"], 275)
        self.assertEqual(result["outputs"]["population_totals"]["comparable"]["draft_fee_minor"], 274)
        period_exception = next(row for row in result["exceptions"] if row["code"] == "wrong-period-draft")
        self.assertEqual((period_exception["from_date"], period_exception["to_date"]), ("2026-01-01", "2026-01-02"))
        self.assert_population_conservation(result)

    def test_nonbillable_draft_is_excluded_with_no_zero_fee(self):
        payload = one_account()
        payload["engagements"][0]["active_from"] = "2026-01-02"
        result, _ = self.solve(payload)
        account = result["outputs"]["account_reviews"][0]
        self.assertEqual(account["comparison_status"], "not-billable")
        self.assertEqual(account["review_flags"], ["not-billable-draft"])
        self.assertEqual(account["draft_ids"], [])
        self.assertIsNone(account["computed_fee_minor"])
        self.assertIsNone(account["draft_fee_minor"])
        self.assertEqual(result["outputs"]["draft_comparisons"][0]["disposition"], "not-billable-account")
        self.assert_population_conservation(result)

    def test_tolerance_is_inclusive_for_both_signs(self):
        for draft_minor, expected_status, delta in ((0, "matched", -1), (2, "matched", 1),
                                                   (3, "draft-overstatement", 2)):
            payload = one_account()
            payload["billing_configuration"]["variance_tolerance_minor"] = 1
            payload["draft_fee_lines"][0]["amount_minor"] = draft_minor
            result, _ = self.solve(payload)
            account = result["outputs"]["account_reviews"][0]
            self.assertEqual(account["comparison_status"], expected_status)
            self.assertEqual(account["delta_minor"], delta)
            self.assertEqual(result["status"], "completed" if expected_status == "matched" else "completed_with_exceptions")

    def test_draft_schedule_label_is_context_never_authority(self):
        payload = one_account()
        payload["draft_fee_lines"][0]["source_schedule_id"] = "SYN-NOT-A-SCHEDULE"
        result, _ = self.solve(payload)
        self.assertEqual(result["outputs"]["account_reviews"][0]["computed_fee_minor"], 1)
        self.assertEqual(result["outputs"]["draft_comparisons"][0]["source_schedule_id"], "SYN-NOT-A-SCHEDULE")
        self.assertEqual([row["code"] for row in result["exceptions"]], ["draft-understatement"])
        payload["draft_fee_lines"][0]["source_schedule_id"] = "not synthetic"
        self.rejected(payload, "invalid-id")

    def test_eur_is_supported_without_conversion_or_cross_currency_netting(self):
        payload = one_account()
        payload["billing_configuration"]["currency"] = "EUR"
        for source in ("engagements", "synthetic_value_intervals", "draft_fee_lines"):
            payload[source][0]["currency"] = "EUR"
        result, _ = self.solve(payload)
        self.assertEqual(result["outputs"]["population_totals"]["currency"], "EUR")
        self.assertEqual(result["outputs"]["population_totals"]["computed"]["fee_minor"], 1)

    def test_every_source_row_has_one_explicit_disposition(self):
        for case_id in ("demo", "holdout-a", "holdout-b"):
            payload = fixture(case_id)
            result, _ = self.solve(payload)
            evidence = result["outputs"]["evidence_dispositions"]
            for source, key in (("engagements", "billing_account_id"), ("schedule_versions", "schedule_id"),
                                ("synthetic_value_intervals", "valuation_id")):
                self.assertEqual(sorted(row[key] for row in evidence[source]),
                                 sorted(row[key] for row in payload[source]))
            self.assertEqual(sorted(row["draft_id"] for row in result["outputs"]["draft_comparisons"]),
                             sorted(row["draft_id"] for row in payload["draft_fee_lines"]))

    def test_5000_rows_are_not_truncated_and_trace_subsets_are_honest(self):
        payload = one_account()
        draft = payload["draft_fee_lines"][0]
        for source in SOURCES:
            payload[source] = []
        payload["draft_fee_lines"] = [
            dict(draft, draft_id=f"SYN-ORPHAN-{index:04}", billing_account_id="SYN-NO-ACCOUNT")
            for index in range(5000)
        ]
        result, events = self.solve(payload)
        self.assertEqual(len(result["outputs"]["draft_comparisons"]), 5000)
        self.assertEqual(len(result["exceptions"]), 5000)
        self.assertEqual(events[0]["tables"][0]["rows"][-1], ["draft_fee_lines", 5000])
        self.assertEqual(events[5]["tables"][1]["total_rows"], 5000)
        self.assertEqual(events[6]["tables"][0]["total_rows"], 5000)
        self.assertIn("first 8 of 5000", events[6]["tables"][0]["title"])
        for event in events:
            self.assertLessEqual(len(event["caption"]), 260)
            self.assertLessEqual(len(event["facts"]), 6)
            self.assertTrue(1 <= len(event["tables"]) <= 2)
            for table in event["tables"]:
                self.assertTrue(1 <= len(table["columns"]) <= 6)
                self.assertLessEqual(len(table["rows"]), 8)
                self.assertGreaterEqual(table["total_rows"], len(table["rows"]))
        self.assert_population_conservation(result)


if __name__ == "__main__":
    unittest.main()
