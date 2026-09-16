import copy
import importlib.util
import json
from pathlib import Path
import unittest

from scenarios._shared.comparison import compare_json
from scenarios._shared.contract import load_scenario, validate_result


ROOT = Path(__file__).resolve().parents[1] / "financial-services" / "bank-ledger-reconciliation"
SPEC = importlib.util.spec_from_file_location("financial_bank_baseline", ROOT / "baseline.py")
BASELINE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BASELINE)


def payload(case="demo"):
    return json.loads((ROOT / "mock-data" / f"{case}.json").read_text(encoding="utf-8"))


def isolated():
    value = payload()
    value["bank_lines"] = value["bank_lines"][:1]
    value["ledger_lines"] = value["ledger_lines"][:1]
    value["batches"] = []
    reclose(value)
    return value


def reclose(value):
    for scope in value["scopes"]:
        for prefix, collection in (("bank", "bank_lines"), ("ledger", "ledger_lines")):
            scope[prefix + "_closing_minor"] = scope[prefix + "_opening_minor"] + sum(
                row["amount_minor"] for row in value[collection] if row["scope_id"] == scope["scope_id"]
            )


class FinancialBankTests(unittest.TestCase):
    def run_payload(self, value):
        before = copy.deepcopy(value)
        result, events = BASELINE.solve(value)
        self.assertEqual(before, value, "baseline must not mutate input")
        validate_result(result)
        return result, events

    def test_complete_golden_rows_not_only_totals(self):
        scenario = load_scenario(ROOT)
        for case in scenario.cases:
            with self.subTest(case=case["id"]):
                result, _ = self.run_payload(payload(case["id"]))
                golden = json.loads((ROOT / "expected" / f"{case['id']}.json").read_text(encoding="utf-8"))
                self.assertEqual(compare_json(golden, result), [])

    def test_actual_eight_stage_trace(self):
        result, events = self.run_payload(payload())
        self.assertEqual(len(events), 8)
        self.assertEqual({event["kind"] for event in events}, {"input", "validation", "join", "decision", "exception", "output"})
        self.assertEqual(events[0]["kind"], "input")
        self.assertEqual(events[-1]["kind"], "output")
        self.assertEqual(events[3]["facts"]["single_edges"], 3)
        self.assertEqual(events[3]["facts"]["batch_edges"], 2)
        self.assertEqual(events[4]["facts"]["candidate_groups"], len(result["outputs"]["matches"]))
        self.assertEqual(events[5]["facts"]["exception_records"], len(result["exceptions"]))
        self.assertEqual(events[6]["tables"][0]["rows"][0][-1], 750)

    def test_source_and_member_permutations(self):
        for case in ("demo", "holdout-a", "holdout-b"):
            with self.subTest(case=case):
                value = payload(case)
                original, trace = self.run_payload(value)
                for name in ("scopes", "bank_lines", "ledger_lines", "mappings", "batches"):
                    value[name].reverse()
                for batch in value["batches"]:
                    batch["member_ledger_ids"].reverse()
                result, reordered_trace = self.run_payload(value)
                self.assertEqual(result, original)
                self.assertEqual(reordered_trace, trace)

    def test_true_integers_not_bool_float_or_string(self):
        for collection, field in (("bank_lines", "amount_minor"), ("ledger_lines", "amount_minor"), ("scopes", "bank_sign")):
            for bad in (True, 1.0, "1", None):
                with self.subTest(collection=collection, field=field, bad=bad):
                    value = payload()
                    value[collection][0][field] = bad
                    result, _ = self.run_payload(value)
                    self.assertEqual(result["status"], "rejected")
                    self.assertEqual(result["exceptions"][0]["code"], "malformed-input")
        for field in ("business_utc_offset_minutes", "max_match_calendar_days", "single_amount_tolerance_minor",
                      "timing_grace_calendar_days", "stale_after_calendar_days", "max_rows_per_source"):
            with self.subTest(field=field):
                value = payload()
                value["config"][field] = True
                result, _ = self.run_payload(value)
                self.assertEqual(result["status"], "rejected")

    def test_duplicate_technical_keys_never_deduplicate(self):
        for name in ("scopes", "bank_lines", "ledger_lines", "mappings", "batches"):
            with self.subTest(name=name):
                value = payload()
                value[name].append(copy.deepcopy(value[name][0]))
                result, _ = self.run_payload(value)
                self.assertEqual(result["status"], "rejected")
                self.assertEqual(result["exceptions"][0]["code"], "duplicate-key")

    def test_unknown_fields_missing_keys_and_unsupported_currency(self):
        for target in ("input", "config", "bank_lines"):
            value = payload()
            if target == "input":
                value["unexpected"] = 1
            elif target == "config":
                value["config"]["allow_fuzzy"] = True
            else:
                del value["bank_lines"][0]["batch_id"]
            result, _ = self.run_payload(value)
            self.assertEqual(result["status"], "rejected")
        value = payload()
        value["scopes"][0]["currency"] = "JPY"
        result, _ = self.run_payload(value)
        self.assertEqual(result["status"], "rejected")

    def test_one_ledger_competing_bank_claims_all_hold(self):
        value = isolated()
        duplicate = dict(value["bank_lines"][0], bank_line_id="SYN-B9")
        value["bank_lines"].append(duplicate)
        reclose(value)
        result, _ = self.run_payload(value)
        self.assertEqual(result["outputs"]["matches"], [])
        self.assertTrue(all(row["disposition"] == "ambiguous" for row in result["outputs"]["bank_reviews"]))
        self.assertEqual(result["outputs"]["ledger_reviews"][0]["candidate_bank_ids"], ["SYN-B1", "SYN-B9"])

    def test_connected_component_is_not_peeled_greedily(self):
        value = isolated()
        value["config"]["single_amount_tolerance_minor"] = 1
        value["bank_lines"][0]["amount_minor"] = 100
        value["ledger_lines"][0]["amount_minor"] = 100
        value["bank_lines"].append(dict(value["bank_lines"][0], bank_line_id="SYN-B9", amount_minor=101))
        value["ledger_lines"].append(dict(value["ledger_lines"][0], ledger_line_id="SYN-L9", amount_minor=102))
        reclose(value)
        result, _ = self.run_payload(value)
        self.assertEqual(result["outputs"]["matches"], [])
        rows = result["outputs"]["bank_reviews"] + result["outputs"]["ledger_reviews"]
        self.assertTrue(all(row["disposition"] == "ambiguous" for row in rows))

    def test_failed_batch_cannot_use_equal_subset_or_fallback(self):
        value = payload()
        value["bank_lines"][1]["amount_minor"] = -5000
        value["bank_lines"].append(dict(
            value["bank_lines"][1], bank_line_id="SYN-B9", reference="SYN-PART-A", batch_id=None,
        ))
        reclose(value)
        result, _ = self.run_payload(value)
        self.assertEqual(len(result["outputs"]["matches"]), 1)
        ledger = {row["ledger_line_id"]: row for row in result["outputs"]["ledger_reviews"]}
        self.assertEqual(ledger["SYN-L2"]["disposition"], "batch-held")
        self.assertEqual(ledger["SYN-L3"]["reason_codes"], ["batch-mismatch"])
        bank = {row["bank_line_id"]: row for row in result["outputs"]["bank_reviews"]}
        self.assertEqual(bank["SYN-B9"]["candidate_ledger_ids"], [])

    def test_missing_manifest_is_explicit_business_hold(self):
        value = payload()
        value["batches"] = []
        result, _ = self.run_payload(value)
        row = next(row for row in result["outputs"]["bank_reviews"] if row["bank_line_id"] == "SYN-B2")
        self.assertEqual(row["reason_codes"], ["batch-incomplete"])
        self.assertEqual(row["candidate_ledger_ids"], [])

    def test_two_claimants_to_manifest_all_hold(self):
        value = payload()
        value["bank_lines"].append(dict(value["bank_lines"][1], bank_line_id="SYN-B9"))
        reclose(value)
        result, _ = self.run_payload(value)
        self.assertEqual(len(result["outputs"]["matches"]), 1)
        rows = result["outputs"]["bank_reviews"] + result["outputs"]["ledger_reviews"]
        for row in rows:
            if row.get("bank_line_id") in ("SYN-B2", "SYN-B9") or row.get("ledger_line_id") in ("SYN-L2", "SYN-L3"):
                self.assertEqual(row["disposition"], "ambiguous")

    def test_unavailable_batch_member_stays_reserved(self):
        value = payload()
        value["ledger_lines"][1]["posted_at"] = "2026-05-31T12:00:00Z"
        value["scopes"][0]["ledger_closing_minor"] += 5000
        result, _ = self.run_payload(value)
        self.assertEqual(result["outputs"]["excluded"][0]["record_id"], "SYN-L2")
        self.assertEqual(result["outputs"]["excluded"][0]["reason"], "outside-period")
        row = next(row for row in result["outputs"]["bank_reviews"] if row["bank_line_id"] == "SYN-B2")
        self.assertEqual(row["candidate_ledger_ids"], ["SYN-L2", "SYN-L3"])
        self.assertEqual(row["reason_codes"], ["batch-incomplete"])

    def test_missing_cross_scope_and_reused_manifest_members_reject(self):
        value = payload()
        value["batches"][0]["member_ledger_ids"][0] = "SYN-NONEXISTENT"
        result, _ = self.run_payload(value)
        self.assertEqual(result["exceptions"][0]["code"], "contradictory-evidence")
        value = payload("holdout-a")
        value["batches"][0]["member_ledger_ids"].append("SYN-B-L1")
        result, _ = self.run_payload(value)
        self.assertEqual(result["exceptions"][0]["code"], "contradictory-evidence")
        value = payload()
        value["batches"].append({"scope_id": "SYN-D", "batch_id": "SYN-SECOND", "member_ledger_ids": ["SYN-L2"]})
        result, _ = self.run_payload(value)
        self.assertEqual(result["exceptions"][0]["code"], "duplicate-key")

    def test_headers_and_lines_normalize_together(self):
        value = payload()
        original, _ = self.run_payload(value)
        scope = value["scopes"][0]
        scope["bank_sign"] = scope["ledger_sign"] = -1
        for field in ("bank_opening_minor", "bank_closing_minor", "prior_bank_closing_minor",
                      "ledger_opening_minor", "ledger_closing_minor"):
            scope[field] *= -1
        for row in value["bank_lines"] + value["ledger_lines"]:
            row["amount_minor"] *= -1
        result, _ = self.run_payload(value)
        self.assertEqual(result, original)
        scope["bank_closing_minor"] *= -1
        result, _ = self.run_payload(value)
        self.assertEqual(result["status"], "rejected")

    def test_no_mapping_or_blank_reference_never_amount_fallback(self):
        value = isolated()
        value["mappings"] = [row for row in value["mappings"] if row["bank_code"] != "DEP"]
        result, _ = self.run_payload(value)
        self.assertEqual(result["outputs"]["matches"], [])
        self.assertEqual(result["outputs"]["bank_reviews"][0]["reason_codes"], ["unmapped-code"])
        value = isolated()
        value["bank_lines"][0]["reference"] = " \t "
        result, _ = self.run_payload(value)
        self.assertEqual(result["outputs"]["matches"], [])
        self.assertEqual(result["outputs"]["bank_reviews"][0]["reason_codes"], ["missing-reference"])

    def test_inclusive_date_and_strict_stale_boundaries(self):
        value = isolated()
        value["bank_lines"][0]["booked_at"] = "2026-06-30T12:00:00Z"
        result, _ = self.run_payload(value)
        self.assertEqual(result["outputs"]["matches"][0]["max_date_gap_days"], 2)
        value["ledger_lines"][0]["posted_at"] = "2026-06-27T12:00:00Z"
        result, _ = self.run_payload(value)
        self.assertEqual(result["outputs"]["matches"], [])
        value = payload("holdout-a")
        result, _ = self.run_payload(value)
        last = next(row for row in result["outputs"]["ledger_reviews"] if row["ledger_line_id"] == "SYN-A-L5")
        self.assertNotIn("stale-ledger", last["reason_codes"])
        value["config"]["stale_after_calendar_days"] = 4
        result, _ = self.run_payload(value)
        last = next(row for row in result["outputs"]["ledger_reviews"] if row["ledger_line_id"] == "SYN-A-L5")
        self.assertEqual(last["reason_codes"], ["date-mismatch", "stale-ledger"])

    def test_timing_needs_explicit_date_inside_grace(self):
        for clearing, disposition in (("2026-07-02", "pending-clearance"), ("2026-07-03", "unmatched"),
                                      ("2026-06-30", "unmatched"), (None, "unmatched")):
            with self.subTest(clearing=clearing):
                value = payload()
                value["ledger_lines"][-1]["expected_bank_date"] = clearing
                result, _ = self.run_payload(value)
                self.assertEqual(result["outputs"]["ledger_reviews"][-1]["disposition"], disposition)

    def test_pending_controls_and_unknown_clock_do_not_authorize(self):
        value = payload()
        value["config"]["approval_state"] = "pending"
        result, _ = self.run_payload(value)
        self.assertEqual(result["exceptions"][0]["code"], "policy-not-approved")
        self.assertEqual(set(result["outputs"]), {"review"})
        for instant in ("2026-07-01T00:00:00", "2026-07-01T00:00:00-00:00", "2026-07-01T00:00:00+14:01",
                        "2026-07-01T00:00:60Z", "2026-02-30T00:00:00Z"):
            with self.subTest(instant=instant):
                value = payload()
                value["config"]["as_of"] = instant
                result, _ = self.run_payload(value)
                self.assertEqual(result["status"], "rejected")

    def test_clean_packet_still_pending_human_review(self):
        result, _ = self.run_payload(isolated())
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["outputs"]["scope_summaries"][0]["disposition"], "no-open-items")
        self.assertEqual(result["outputs"]["review"], {"human_review": "pending", "live_action": "none"})

    def test_zero_gap_does_not_hide_unmatched_items(self):
        value = isolated()
        value["bank_lines"][0]["reference"] = "SYN-OTHER"
        result, _ = self.run_payload(value)
        summary = result["outputs"]["scope_summaries"][0]
        self.assertEqual(summary["closing_difference_minor"], 0)
        self.assertEqual(summary["disposition"], "review-required")
        self.assertEqual(summary["unresolved_bank_count"], 1)

    def test_cancelling_penny_corrections_still_require_review(self):
        value = isolated()
        value["config"]["single_amount_tolerance_minor"] = 1
        value["bank_lines"][0]["amount_minor"] = 12001
        value["bank_lines"].append(dict(value["bank_lines"][0], bank_line_id="SYN-B9", reference="SYN-OTHER", amount_minor=5999))
        value["ledger_lines"].append(dict(value["ledger_lines"][0], ledger_line_id="SYN-L9", reference="SYN-OTHER", amount_minor=6000))
        reclose(value)
        result, _ = self.run_payload(value)
        summary = result["outputs"]["scope_summaries"][0]
        self.assertEqual(summary["match_delta_minor"], 0)
        self.assertEqual(summary["disposition"], "review-required")
        self.assertEqual(len(result["exceptions"]), 4)

    def test_opening_difference_preserved_without_inventing_match(self):
        value = isolated()
        for field in ("bank_opening_minor", "bank_closing_minor", "prior_bank_closing_minor"):
            value["scopes"][0][field] += 100
        result, _ = self.run_payload(value)
        summary = result["outputs"]["scope_summaries"][0]
        self.assertEqual(summary["opening_difference_minor"], 100)
        self.assertEqual(summary["closing_difference_minor"], 100)
        self.assertEqual(result["exceptions"][0]["code"], "opening-difference")
        self.assertEqual(len(result["outputs"]["matches"]), 1)

    def test_source_and_candidate_size_limits_reject_without_truncating(self):
        value = payload()
        value["config"]["max_rows_per_source"] = 2
        result, _ = self.run_payload(value)
        self.assertEqual(result["status"], "rejected")
        value = isolated()
        bank, ledger = value["bank_lines"][0], value["ledger_lines"][0]
        value["bank_lines"] = [dict(bank, bank_line_id=f"SYN-B-{index:03}") for index in range(317)]
        value["ledger_lines"] = [dict(ledger, ledger_line_id=f"SYN-L-{index:03}") for index in range(317)]
        reclose(value)
        result, _ = self.run_payload(value)
        self.assertEqual(result["status"], "rejected")
        self.assertEqual(result["exceptions"][0]["code"], "candidate-limit")
        self.assertEqual(set(result["outputs"]), {"review"})


if __name__ == "__main__":
    unittest.main()
