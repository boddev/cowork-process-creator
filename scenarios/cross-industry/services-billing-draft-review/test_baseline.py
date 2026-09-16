"""Owned stdlib tests; fixture oracles are manually authored, never generated here."""
import ast
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import random
import shutil
import subprocess
import sys
import unittest
from unittest import mock
import uuid


ROOT = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("services_billing_baseline", ROOT / "baseline.py")
BASELINE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BASELINE)
CASES = ("demo", "holdout-a", "holdout-b", "negative-malformed", "negative-contradictory")
EXPORTS = (
    "projects.json", "rates.json", "time-entries.json", "expense-entries.json",
    "approval-events.json", "billed-transactions.json", "draft-invoices.json",
    "draft-lines.json", "expense-policies.json",
)


def fixture(case_id, directory="mock-data"):
    return json.loads((ROOT / directory / (case_id + ".json")).read_text(encoding="utf-8"))


def minimal():
    return {
        "config": {"as_of": "2026-10-02T12:00:00Z", "period_start": "2026-09-01", "period_end": "2026-10-01", "draft_tolerance": "0.00"},
        "files": {
            "projects.json": [{"project_id": "PX", "client_id": "CX", "contract_id": "KX", "currency": "USD", "period_cap": "1000.00", "owner": "OWNER-X"}],
            "rates.json": [{"rate_id": "RX", "project_id": "PX", "role_code": "consultant", "currency": "USD", "valid_from": "2026-09-01", "valid_to": "2026-10-01", "hourly_rate": "100.00"}],
            "time-entries.json": [{"time_id": "TX", "project_id": "PX", "person_id": "PERSON-X", "role_code": "consultant", "service_date": "2026-09-15", "minutes": 60, "chargeable": True}],
            "expense-entries.json": [],
            "approval-events.json": [{"approval_event_id": "AX", "entry_type": "time", "entry_id": "TX", "revision": 1, "recorded_at": "2026-10-02T12:00:00Z", "decision": "approved"}],
            "billed-transactions.json": [],
            "draft-invoices.json": [{"draft_id": "DX", "project_id": "PX", "currency": "USD", "period_start": "2026-09-01", "period_end": "2026-10-01", "state": "draft"}],
            "draft-lines.json": [{"line_id": "LX", "draft_id": "DX", "entry_type": "time", "entry_id": "TX", "amount": "100.00"}],
            "expense-policies.json": [{"category": "travel", "currency": "USD", "max_amount": "100.00", "receipt_required_at": "50.00"}],
        },
    }


def add_expense(payload, amount="20.00", receipt=None, currency="USD"):
    payload["files"]["expense-entries.json"].append({
        "expense_id": "EX", "project_id": "PX", "person_id": "PERSON-X",
        "service_date": "2026-09-15", "category": "travel", "amount": amount,
        "currency": currency, "receipt_reference": receipt, "chargeable": True,
    })
    payload["files"]["approval-events.json"].append({
        "approval_event_id": "AX-E", "entry_type": "expense", "entry_id": "EX",
        "revision": 1, "recorded_at": "2026-10-02T12:00:00Z", "decision": "approved",
    })
    return payload["files"]["expense-entries.json"][-1]


def add_prior(payload, amount="50.00", entry_id="HISTORICAL", **changes):
    row = {
        "billed_id": "BX", "entry_type": "time", "entry_id": entry_id, "project_id": "PX",
        "invoice_id": "IX", "service_date": "2026-09-15", "amount": amount,
        "currency": "USD", "billed_at": "2026-10-02T12:00:00Z",
    }
    row.update(changes)
    payload["files"]["billed-transactions.json"].append(row)
    return row


def entry(result, entry_id="TX", entry_type="time"):
    return next(row for row in result["outputs"]["entries"] if (row["entry_type"], row["entry_id"]) == (entry_type, entry_id))


class LockedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lock_path = ROOT / "validation" / "golden-lock.json"
        cls.lock_bytes = cls.lock_path.read_bytes()
        lock = json.loads(cls.lock_bytes)
        if lock["scenario_id"] != "cross-industry-03":
            raise AssertionError("A pre-execution lock for this scenario is required.")
        for case_id in CASES:
            for directory, key in (("expected", "expected_sha256"), ("mock-data", "input_sha256")):
                actual = hashlib.sha256((ROOT / directory / (case_id + ".json")).read_bytes()).hexdigest()
                if actual != lock["cases"][case_id][key]:
                    raise AssertionError("The independently authored input/golden lock changed.")

    @classmethod
    def tearDownClass(cls):
        if cls.lock_path.read_bytes() != cls.lock_bytes:
            raise AssertionError("Tests must not modify the pre-execution golden lock.")

    def solve(self, payload):
        before = copy.deepcopy(payload)
        result, events = BASELINE.solve(payload)
        self.assertEqual(payload, before, "solve must not mutate the supplied exports")
        return result, events


class BillingGoldenTests(LockedTests):
    def test_all_five_independent_complete_envelopes(self):
        for case_id in CASES:
            with self.subTest(case=case_id):
                result, events = self.solve(fixture(case_id))
                self.assertEqual(fixture(case_id, "expected"), result)
                self.assertEqual(len(events), 2 if case_id == "negative-malformed" else 9)

    def test_row_permutation_preserves_results_and_actual_trace(self):
        for case_id in CASES:
            payload = fixture(case_id)
            result, events = self.solve(payload)
            for seed in (3, 19, 271):
                with self.subTest(case=case_id, seed=seed):
                    shuffled = copy.deepcopy(payload)
                    randomizer = random.Random(seed)
                    for rows in shuffled["files"].values():
                        randomizer.shuffle(rows)
                    shuffled["files"] = dict(reversed(list(shuffled["files"].items())))
                    actual_result, actual_events = self.solve(shuffled)
                    self.assertEqual(result, actual_result)
                    self.assertEqual(events, actual_events)

    def test_trace_contract_and_observed_values(self):
        workflow = json.loads((ROOT / "workflow.json").read_text(encoding="utf-8"))
        steps = {row["id"]: row["kind"] for row in workflow["steps"]}
        for case_id in CASES:
            result, events = self.solve(fixture(case_id))
            for event in events:
                self.assertEqual(set(event), {"step_id", "kind", "caption", "facts", "tables"})
                self.assertEqual(steps[event["step_id"]], event["kind"])
                self.assertTrue(0 < len(event["caption"]) <= 260)
                self.assertLessEqual(len(event["facts"]), 6)
                self.assertTrue(all(value is None or type(value) in (str, bool, int, float) for value in event["facts"].values()))
                self.assertIn(len(event["tables"]), (1, 2))
                for table in event["tables"]:
                    self.assertEqual(set(table), {"title", "columns", "rows", "total_rows", "highlight_rows"})
                    self.assertTrue(1 <= len(table["columns"]) <= 6)
                    self.assertLessEqual(len(table["rows"]), 8)
                    self.assertGreaterEqual(table["total_rows"], len(table["rows"]))
                    for row in table["rows"]:
                        self.assertEqual(len(row), len(table["columns"]))
                        self.assertTrue(all(value is None or type(value) in (str, bool, int, float) for value in row))
                    self.assertTrue(all(0 <= index < len(table["rows"]) for index in table["highlight_rows"]))
            if result["status"] != "rejected":
                self.assertEqual(events[0]["kind"], "input")
                self.assertEqual(events[-1]["kind"], "output")
                self.assertEqual(set(row["kind"] for row in events), {"input", "validation", "join", "decision", "exception", "output"})
                self.assertEqual(events[-1]["facts"]["entries"], len(result["outputs"]["entries"]))
        result, events = self.solve(fixture("demo"))
        caps = next(event for event in events if event["step_id"] == "check-project-caps")
        self.assertIn(["P2", "USD", "200.00", "340.00", "500.00", "40.00"], caps["tables"][0]["rows"])
        self.assertEqual(caps["facts"]["cap_held_projects"], 1)
        self.assertTrue(any(row[0] == "B2" and row[1] is False for row in caps["tables"][1]["rows"]))

    def test_mixed_currencies_and_scoped_unknown_totals(self):
        result, _ = self.solve(fixture("holdout-b"))
        buckets = {row["currency"]: row for row in result["outputs"]["currency_totals"]}
        self.assertEqual(set(buckets), {"USD", "EUR"})
        self.assertEqual(buckets["USD"]["eligible_new_amount"], "23.34")
        self.assertEqual(buckets["EUR"]["eligible_new_amount"], "90.00")
        self.assertEqual(buckets["EUR"]["known_entry_hold_amount"], "45.00")
        self.assertIsNone(entry(result, "EB2", "expense")["expected_amount"])
        usd_draft = result["outputs"]["drafts"][0]
        self.assertIsNone(usd_draft["expected_amount"])
        self.assertIsNone(usd_draft["variance"])
        self.assertEqual(buckets["USD"]["computable_variance"], "1.68")
        self.assertNotIn("grand_total", result["outputs"])

    def test_ambiguous_approval_preserves_independent_project(self):
        result, _ = self.solve(fixture("negative-contradictory"))
        self.assertIsNone(entry(result, "C1")["expected_amount"])
        self.assertEqual(entry(result, "C1")["approval_event_ids"], ["AC1-2A", "AC1-2R"])
        self.assertEqual(entry(result, "C2")["expected_amount"], "60.00")
        self.assertEqual(result["outputs"]["draft_details"][0]["action"], "clarify-not-remove")
        bucket = result["outputs"]["currency_totals"][0]
        self.assertEqual(bucket["computable_expected_amount"], "60.00")
        self.assertEqual(bucket["computable_draft_amount"], "60.00")
        self.assertEqual(bucket["quarantined_draft_amount"], "100.00")
        self.assertEqual(bucket["computable_variance"], "0.00")
        self.assertFalse(bucket["comparison_complete"])

    def test_solve_does_not_read_or_write_files(self):
        payload = minimal()
        with mock.patch("builtins.open", side_effect=AssertionError("No solve file access")), mock.patch.object(
            Path, "open", side_effect=AssertionError("No solve file access")
        ):
            result, _ = BASELINE.solve(payload)
        self.assertEqual(result["status"], "completed")

    def test_baseline_imports_are_local_stdlib_and_adapter_only(self):
        tree = ast.parse((ROOT / "baseline.py").read_text(encoding="utf-8"))
        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                self.assertEqual(node.level, 0)
                imports.add(node.module.split(".")[0])
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                normalized = node.value.replace("\\", "/").lower()
                self.assertNotEqual(normalized, "expected")
                self.assertNotIn("expected/", normalized)
        self.assertFalse(imports - set(sys.stdlib_module_names) - {"scenario_support"})
        self.assertFalse(imports & {"socket", "http", "urllib", "subprocess", "ctypes", "webbrowser"})

    def test_public_procedure_documents_all_fields_and_canonical_messages(self):
        procedure = (ROOT / "HOW_TO.md").read_text(encoding="utf-8")
        for filename, (_, fields) in BASELINE.SCHEMAS.items():
            self.assertIn("`" + filename + "`", procedure)
            for field in fields:
                self.assertIn("`" + field + "`", procedure)
        for field in BASELINE.CONFIG_FIELDS:
            self.assertIn("`" + field + "`", procedure)
        for code, message in BASELINE.MESSAGES.items():
            self.assertIn("`" + code + "`", procedure)
            self.assertIn(message, procedure)

        def check_keys(value):
            if isinstance(value, dict):
                for key, child in value.items():
                    self.assertIn("`" + key + "`", procedure)
                    check_keys(child)
            elif isinstance(value, list):
                for child in value:
                    check_keys(child)

        for case_id in CASES:
            check_keys(fixture(case_id, "expected"))
        for private_marker in ("holdout-a", "holdout-b", "P-B1", "EA1", "PC1", "439.99", "560.01"):
            self.assertNotIn(private_marker, procedure)

    def test_every_input_business_entity_is_accounted_for(self):
        for case_id in CASES:
            if case_id == "negative-malformed":
                continue
            payload = fixture(case_id)
            result, _ = self.solve(payload)
            files, outputs = payload["files"], result["outputs"]
            self.assertEqual(
                {(row["entry_type"], row["entry_id"]) for row in outputs["entries"]},
                {("time", row["time_id"]) for row in files["time-entries.json"]}
                | {("expense", row["expense_id"]) for row in files["expense-entries.json"]},
            )
            self.assertEqual(
                sorted(row["line_id"] for row in outputs["draft_details"] if row["line_id"] is not None),
                sorted(row["line_id"] for row in files["draft-lines.json"]),
            )
            for output_name, filename, key in (
                ("projects", "projects.json", "project_id"),
                ("drafts", "draft-invoices.json", "draft_id"),
                ("prior_billing", "billed-transactions.json", "billed_id"),
            ):
                self.assertEqual([row[key] for row in outputs[output_name]], sorted(row[key] for row in files[filename]))


class BillingBoundaryTests(LockedTests):
    def test_cutoff_is_inclusive_future_reapproval_is_ignored(self):
        payload = minimal()
        payload["files"]["approval-events.json"] += [
            {"approval_event_id": "AX2", "entry_type": "time", "entry_id": "TX", "revision": 2, "recorded_at": "2026-10-02T12:00:00Z", "decision": "recalled"},
            {"approval_event_id": "AX3", "entry_type": "time", "entry_id": "TX", "revision": 3, "recorded_at": "2026-10-02T12:00:01Z", "decision": "approved"},
        ]
        result, _ = self.solve(payload)
        self.assertEqual(entry(result)["reason"], "recalled")
        self.assertEqual(entry(result)["approval_revision"], 2)
        self.assertEqual(entry(result)["future_approval_event_ids"], ["AX3"])
        payload["config"]["as_of"] = "2026-10-02T12:00:01Z"
        result, _ = self.solve(payload)
        self.assertEqual(entry(result)["approval_revision"], 3)
        self.assertEqual(entry(result)["expected_amount"], "100.00")

    def test_explicit_offsets_normalize_to_same_snapshot(self):
        payload = minimal()
        original, _ = self.solve(payload)
        payload["config"]["as_of"] = "2026-10-02T14:00:00+02:00"
        payload["files"]["approval-events.json"][0]["recorded_at"] = "2026-10-02T07:00:00-05:00"
        result, _ = self.solve(payload)
        self.assertEqual(result, original)

    def test_revision_not_timestamp_or_input_order_selects_approval(self):
        payload = minimal()
        payload["files"]["approval-events.json"] = [
            {"approval_event_id": "EARLY", "entry_type": "time", "entry_id": "TX", "revision": 8, "recorded_at": "2026-09-20T12:00:00Z", "decision": "approved"},
            {"approval_event_id": "LATE", "entry_type": "time", "entry_id": "TX", "revision": 7, "recorded_at": "2026-10-02T12:00:00Z", "decision": "recalled"},
        ]
        result, _ = self.solve(payload)
        self.assertEqual(entry(result)["approval_event_ids"], ["EARLY"])
        self.assertEqual(entry(result)["status"], "candidate")

    def test_same_decision_top_revision_is_still_not_unique(self):
        payload = minimal()
        other = dict(payload["files"]["approval-events.json"][0], approval_event_id="AX-OTHER")
        payload["files"]["approval-events.json"].append(other)
        result, _ = self.solve(payload)
        self.assertEqual(entry(result)["reason"], "ambiguous-approval")
        self.assertIsNone(entry(result)["expected_amount"])
        self.assertEqual(result["outputs"]["draft_details"][0]["action"], "clarify-not-remove")

    def test_conflicts_precede_nonchargeable_and_out_of_period(self):
        payload = minimal()
        payload["files"]["time-entries.json"][0].update(chargeable=False, service_date="2026-10-01")
        payload["files"]["approval-events.json"].append(dict(
            payload["files"]["approval-events.json"][0], approval_event_id="RECALL", decision="recalled"
        ))
        result, _ = self.solve(payload)
        self.assertEqual(entry(result)["reason"], "contradictory-approval")
        self.assertNotIn("remove", [row["action"] for row in result["outputs"]["draft_details"]])

    def test_service_period_half_open_boundaries(self):
        for service_date, reason in (
            ("2026-08-31", "out-of-period"), ("2026-09-01", "candidate-time"),
            ("2026-09-30", "candidate-time"), ("2026-10-01", "out-of-period"),
        ):
            with self.subTest(date=service_date):
                payload = minimal()
                payload["files"]["time-entries.json"][0]["service_date"] = service_date
                result, _ = self.solve(payload)
                self.assertEqual(entry(result)["reason"], reason)

    def test_effective_rate_half_open_boundary_and_end(self):
        payload = minimal()
        payload["files"]["rates.json"][0]["valid_to"] = "2026-09-15"
        payload["files"]["rates.json"].append(dict(
            payload["files"]["rates.json"][0], rate_id="RY", valid_from="2026-09-15",
            valid_to="2026-09-16", hourly_rate="150.00",
        ))
        for service_date, rate_id, amount in (
            ("2026-09-14", "RX", "100.00"), ("2026-09-15", "RY", "150.00"),
            ("2026-09-16", None, None),
        ):
            with self.subTest(date=service_date):
                payload["files"]["time-entries.json"][0]["service_date"] = service_date
                result, _ = self.solve(payload)
                self.assertEqual(entry(result)["rate_id"], rate_id)
                self.assertEqual(entry(result)["expected_amount"], amount)

    def test_rate_requires_project_role_and_currency(self):
        for field, value in (("project_id", "UNRELATED"), ("role_code", "analyst"), ("currency", "EUR")):
            with self.subTest(field=field):
                payload = minimal()
                payload["files"]["rates.json"].append(dict(
                    payload["files"]["rates.json"][0], rate_id="OTHER", hourly_rate="999.00", **{field: value}
                ))
                result, _ = self.solve(payload)
                self.assertEqual(entry(result)["rate_id"], "RX")
                self.assertEqual(entry(result)["expected_amount"], "100.00")
                payload["files"]["rates.json"] = payload["files"]["rates.json"][1:]
                result, _ = self.solve(payload)
                self.assertEqual(entry(result)["reason"], "missing-rate")

    def test_overlapping_effective_rates_are_uncomputed(self):
        payload = minimal()
        payload["files"]["rates.json"].append(dict(payload["files"]["rates.json"][0], rate_id="OVERLAP", hourly_rate="90.00"))
        result, _ = self.solve(payload)
        self.assertEqual(entry(result)["reason"], "ambiguous-rate")
        self.assertIsNone(entry(result)["rate_id"])
        self.assertIsNone(result["outputs"]["drafts"][0]["variance"])
        self.assertEqual(result["outputs"]["drafts"][0]["quarantined_draft_amount"], "100.00")

    def test_half_up_tie_and_per_entry_not_aggregate_rounding(self):
        payload = minimal()
        payload["files"]["time-entries.json"][0]["minutes"] = 1
        payload["files"]["rates.json"][0]["hourly_rate"] = "0.30"
        result, _ = self.solve(payload)
        self.assertEqual(entry(result)["expected_amount"], "0.01")
        payload["files"]["rates.json"][0]["hourly_rate"] = "100.00"
        payload["files"]["time-entries.json"].append(dict(payload["files"]["time-entries.json"][0], time_id="TY"))
        payload["files"]["approval-events.json"].append(dict(payload["files"]["approval-events.json"][0], approval_event_id="AY", entry_id="TY"))
        result, _ = self.solve(payload)
        self.assertEqual(entry(result)["expected_amount"], "1.67")
        self.assertEqual(entry(result, "TY")["expected_amount"], "1.67")
        self.assertEqual(result["outputs"]["projects"][0]["eligible_new_amount"], "3.34")

    def test_zero_rate_is_candidate_not_an_exclusion(self):
        payload = minimal()
        payload["files"]["rates.json"][0]["hourly_rate"] = "0.00"
        result, _ = self.solve(payload)
        self.assertEqual(entry(result)["status"], "candidate")
        self.assertEqual(entry(result)["expected_amount"], "0.00")
        self.assertEqual(result["outputs"]["draft_details"][0]["action"], "update")

    def test_large_decimal_amounts_do_not_use_binary_float(self):
        payload = minimal()
        payload["files"]["rates.json"][0]["hourly_rate"] = "123456789012345678901234567890.01"
        payload["files"]["projects.json"][0]["period_cap"] = "123456789012345678901234567890.01"
        payload["files"]["draft-lines.json"][0]["amount"] = "123456789012345678901234567890.01"
        result, _ = self.solve(payload)
        self.assertEqual(entry(result)["expected_amount"], "123456789012345678901234567890.01")
        self.assertFalse(result["outputs"]["projects"][0]["cap_hold"])
        self.assertEqual(result["outputs"]["drafts"][0]["variance"], "0.00")

    def test_expense_cap_holds_whole_amount_only_above_boundary(self):
        for amount, status in (("99.99", "candidate"), ("100.00", "candidate"), ("100.01", "held")):
            with self.subTest(amount=amount):
                payload = minimal()
                add_expense(payload, amount, "RECEIPT")
                result, _ = self.solve(payload)
                expense = entry(result, "EX", "expense")
                self.assertEqual(expense["status"], status)
                self.assertEqual(expense["expected_amount"], amount if status == "candidate" else "0.00")
                self.assertEqual(expense["held_amount"], None if status == "candidate" else amount)

    def test_receipt_threshold_is_inclusive(self):
        for amount, receipt, reason in (
            ("49.99", None, "candidate-expense"), ("50.00", None, "receipt-required"),
            ("50.00", "RECEIPT", "candidate-expense"), ("50.01", None, "receipt-required"),
        ):
            with self.subTest(amount=amount, receipt=receipt):
                payload = minimal()
                add_expense(payload, amount, receipt)
                result, _ = self.solve(payload)
                self.assertEqual(entry(result, "EX", "expense")["reason"], reason)

    def test_expense_cap_precedes_missing_receipt(self):
        payload = minimal()
        add_expense(payload, "100.01")
        result, _ = self.solve(payload)
        self.assertEqual(entry(result, "EX", "expense")["reason"], "expense-cap")
        self.assertEqual(entry(result, "EX", "expense")["held_amount"], "100.01")

    def test_zero_receipt_threshold_still_requires_receipt(self):
        payload = minimal()
        add_expense(payload, "0.00")
        payload["files"]["expense-policies.json"][0]["receipt_required_at"] = "0.00"
        result, _ = self.solve(payload)
        self.assertEqual(entry(result, "EX", "expense")["reason"], "receipt-required")
        self.assertEqual(entry(result, "EX", "expense")["held_amount"], "0.00")

    def test_currency_contradiction_not_removed_even_if_nonchargeable(self):
        payload = minimal()
        expense = add_expense(payload, "15.00", currency="EUR")
        expense["chargeable"] = False
        payload["files"]["draft-lines.json"].append({"line_id": "LE", "draft_id": "DX", "entry_type": "expense", "entry_id": "EX", "amount": "15.00"})
        result, _ = self.solve(payload)
        self.assertEqual(entry(result, "EX", "expense")["reason"], "currency-mismatch")
        detail = next(row for row in result["outputs"]["draft_details"] if row["line_id"] == "LE")
        self.assertEqual(detail["action"], "clarify-not-remove")
        self.assertIsNone(detail["delta"])

    def test_raw_source_absent_history_counts_and_cap_equality_is_allowed(self):
        payload = minimal()
        add_prior(payload)
        payload["files"]["projects.json"][0]["period_cap"] = "150.00"
        result, _ = self.solve(payload)
        project = result["outputs"]["projects"][0]
        self.assertEqual(project["prior_billed_amount"], "50.00")
        self.assertEqual(project["proposed_consumption"], "150.00")
        self.assertFalse(project["cap_hold"])
        self.assertFalse(result["outputs"]["prior_billing"][0]["source_present"])
        payload["files"]["projects.json"][0]["period_cap"] = "149.99"
        result, _ = self.solve(payload)
        project = result["outputs"]["projects"][0]
        self.assertTrue(project["cap_hold"])
        self.assertEqual(project["cap_overage"], "0.01")
        self.assertEqual(project["cap_held_amount"], "100.00")
        self.assertEqual(project["reviewable_new_amount"], "0.00")
        self.assertTrue(entry(result)["cap_held"])
        self.assertTrue(result["outputs"]["draft_details"][0]["diagnostic_only"])

    def test_cap_hold_applies_to_missing_line_diagnostic_without_removing_candidate(self):
        payload = minimal()
        add_prior(payload)
        payload["files"]["projects.json"][0]["period_cap"] = "100.00"
        payload["files"]["draft-lines.json"] = []
        result, _ = self.solve(payload)
        row = result["outputs"]["draft_details"][0]
        self.assertEqual((row["action"], row["expected_amount"], row["delta"]), ("add", "100.00", "100.00"))
        self.assertTrue(row["diagnostic_only"])
        self.assertEqual(entry(result)["status"], "candidate")

    def test_prior_service_and_recorded_boundaries(self):
        for service_date, billed_at, disposition in (
            ("2026-09-01", "2026-10-02T12:00:00Z", "counted"),
            ("2026-08-31", "2026-10-02T12:00:00Z", "out-of-period"),
            ("2026-10-01", "2026-10-02T12:00:00Z", "out-of-period"),
            ("2026-09-01", "2026-10-02T12:00:01Z", "future-ignored"),
        ):
            with self.subTest(date=service_date, billed=billed_at):
                payload = minimal()
                add_prior(payload, service_date=service_date, billed_at=billed_at)
                result, _ = self.solve(payload)
                self.assertEqual(result["outputs"]["prior_billing"][0]["disposition"], disposition)
                self.assertEqual(result["outputs"]["projects"][0]["prior_billed_amount"], "50.00" if disposition == "counted" else "0.00")

    def test_future_billing_identity_cannot_poison_snapshot(self):
        payload = minimal()
        add_prior(payload, entry_id="TX", project_id="WRONG", currency="EUR", billed_at="2026-10-02T12:00:01Z")
        result, _ = self.solve(payload)
        self.assertEqual(entry(result)["status"], "candidate")
        self.assertEqual(entry(result)["billed_ids"], [])
        self.assertEqual(result["outputs"]["prior_billing"][0]["disposition"], "future-ignored")

    def test_already_billed_excludes_whole_entry_not_remaining_balance(self):
        for amount in ("0.00", "1.00", "100.00"):
            with self.subTest(amount=amount):
                payload = minimal()
                add_prior(payload, amount=amount, entry_id="TX")
                result, _ = self.solve(payload)
                self.assertEqual(entry(result)["reason"], "already-billed")
                self.assertEqual(entry(result)["expected_amount"], "0.00")
                self.assertIsNone(entry(result)["rate_id"])
                self.assertEqual(result["outputs"]["draft_details"][0]["action"], "remove")

    def test_raw_prior_not_erased_by_contradictory_source_identity(self):
        payload = minimal()
        add_prior(payload, entry_id="TX", service_date="2026-09-14")
        result, _ = self.solve(payload)
        self.assertEqual(entry(result)["reason"], "billed-identity-mismatch")
        self.assertEqual(result["outputs"]["projects"][0]["prior_billed_amount"], "50.00")
        self.assertEqual(result["outputs"]["prior_billing"][0]["cap_amount"], "50.00")
        self.assertIsNone(result["outputs"]["projects"][0]["proposed_consumption"])
        self.assertEqual(result["outputs"]["draft_details"][0]["action"], "clarify-not-remove")

    def test_duplicate_posted_entry_is_ambiguous_but_raw_cap_counts_both(self):
        payload = minimal()
        add_prior(payload, amount="10.00", entry_id="TX")
        add_prior(payload, amount="20.00", entry_id="TX", billed_id="BY", invoice_id="IY")
        result, _ = self.solve(payload)
        self.assertEqual(entry(result)["reason"], "ambiguous-billing")
        self.assertEqual(result["outputs"]["projects"][0]["prior_billed_amount"], "30.00")
        self.assertEqual(result["outputs"]["drafts"][0]["quarantined_draft_amount"], "100.00")

    def test_prior_currency_join_unknown_does_not_become_zero(self):
        payload = minimal()
        add_prior(payload, currency="EUR")
        result, _ = self.solve(payload)
        self.assertIsNone(result["outputs"]["prior_billing"][0]["cap_amount"])
        project = result["outputs"]["projects"][0]
        self.assertEqual(project["known_consumption"], "100.00")
        self.assertIsNone(project["proposed_consumption"])
        self.assertIsNone(project["cap_overage"])
        self.assertFalse(project["calculation_complete"])

    def test_pending_rejected_recalled_missing_and_nonchargeable_are_explicit(self):
        for decision in ("pending", "rejected", "recalled", None):
            with self.subTest(decision=decision):
                payload = minimal()
                if decision:
                    payload["files"]["approval-events.json"][0]["decision"] = decision
                else:
                    payload["files"]["approval-events.json"] = []
                result, _ = self.solve(payload)
                self.assertEqual(entry(result)["reason"], decision or "not-approved")
                self.assertEqual(entry(result)["expected_amount"], "0.00")
                self.assertEqual(result["outputs"]["draft_details"][0]["action"], "remove")
        payload = minimal()
        payload["files"]["time-entries.json"][0]["chargeable"] = False
        result, _ = self.solve(payload)
        self.assertEqual(entry(result)["reason"], "nonchargeable")

    def test_future_only_approval_does_not_establish_approval(self):
        payload = minimal()
        payload["files"]["approval-events.json"][0]["recorded_at"] = "2026-10-02T12:00:01Z"
        result, _ = self.solve(payload)
        self.assertEqual(entry(result)["reason"], "not-approved")
        self.assertIsNone(entry(result)["approval_revision"])
        self.assertEqual(entry(result)["approval_event_ids"], [])
        self.assertEqual(entry(result)["future_approval_event_ids"], ["AX"])

    def test_definite_ineligibility_zero_line_is_still_remove(self):
        payload = minimal()
        payload["files"]["approval-events.json"][0]["decision"] = "pending"
        payload["files"]["draft-lines.json"][0]["amount"] = "0.00"
        result, _ = self.solve(payload)
        self.assertEqual(result["outputs"]["draft_details"][0]["action"], "remove")
        self.assertEqual(result["outputs"]["draft_details"][0]["delta"], "0.00")


class BillingJoinAndLoopTests(LockedTests):
    def test_duplicate_active_drafts_never_choose_one(self):
        payload = minimal()
        payload["files"]["draft-invoices.json"].append(dict(payload["files"]["draft-invoices.json"][0], draft_id="DY"))
        result, _ = self.solve(payload)
        self.assertEqual([row["status"] for row in result["outputs"]["drafts"]], ["clarification", "clarification"])
        self.assertEqual(result["outputs"]["draft_details"][0]["action"], "clarify-not-remove")
        self.assertIsNone(result["outputs"]["draft_details"][0]["expected_amount"])
        self.assertEqual(sum(row["code"] == "duplicate-drafts" for row in result["exceptions"]), 3)

    def test_empty_duplicate_drafts_are_still_reported(self):
        payload = minimal()
        payload["files"]["time-entries.json"] = []
        payload["files"]["approval-events.json"] = []
        payload["files"]["draft-lines.json"] = []
        payload["files"]["draft-invoices.json"].append(dict(payload["files"]["draft-invoices.json"][0], draft_id="DY"))
        result, _ = self.solve(payload)
        self.assertEqual(len(result["outputs"]["drafts"]), 2)
        self.assertEqual(len(result["exceptions"]), 2)
        self.assertTrue(all(not row["comparison_complete"] for row in result["outputs"]["drafts"]))

    def test_missing_candidate_with_duplicate_drafts_has_null_assignment(self):
        payload = minimal()
        payload["files"]["draft-lines.json"] = []
        payload["files"]["draft-invoices.json"].append(dict(payload["files"]["draft-invoices.json"][0], draft_id="DY"))
        result, _ = self.solve(payload)
        detail = result["outputs"]["draft_details"][0]
        self.assertIsNone(detail["draft_id"])
        self.assertEqual(detail["action"], "clarify-not-remove")
        self.assertIsNone(detail["delta"])
        self.assertEqual(result["outputs"]["projects"][0]["eligible_new_amount"], "100.00")
        self.assertEqual(result["outputs"]["currency_totals"][0]["computable_expected_amount"], "0.00")

    def test_duplicate_details_preserve_all_lines_without_double_counting_charge(self):
        payload = minimal()
        payload["files"]["draft-lines.json"].append(dict(payload["files"]["draft-lines.json"][0], line_id="LY"))
        result, _ = self.solve(payload)
        self.assertEqual(entry(result)["expected_amount"], "100.00")
        self.assertEqual(len(result["outputs"]["draft_details"]), 2)
        self.assertTrue(all(row["action"] == "clarify-not-remove" for row in result["outputs"]["draft_details"]))
        draft = result["outputs"]["drafts"][0]
        self.assertEqual(draft["draft_amount"], "200.00")
        self.assertEqual(draft["quarantined_draft_amount"], "200.00")
        self.assertEqual(draft["computable_expected_amount"], "0.00")
        self.assertIsNone(draft["variance"])

    def test_missing_source_draft_entry_is_not_assumed_ineligible(self):
        payload = minimal()
        payload["files"]["draft-lines.json"][0]["entry_id"] = "UNSUPPLIED"
        result, _ = self.solve(payload)
        row = next(row for row in result["outputs"]["draft_details"] if row["line_id"] == "LX")
        self.assertEqual(row["reason"], "missing-draft-entry")
        self.assertEqual(row["action"], "clarify-not-remove")
        self.assertIsNone(row["expected_amount"])
        self.assertEqual(len(result["outputs"]["draft_details"]), 2)

    def test_missing_header_accounts_for_orphan_detail(self):
        payload = minimal()
        payload["files"]["draft-invoices.json"] = []
        result, _ = self.solve(payload)
        self.assertEqual(len(result["outputs"]["draft_details"]), 1)
        self.assertEqual(result["outputs"]["drafts"], [])
        self.assertEqual(result["outputs"]["draft_details"][0]["reason"], "missing-draft-header")
        self.assertIsNone(result["outputs"]["draft_details"][0]["currency"])
        self.assertEqual(result["outputs"]["draft_details"][0]["draft_amount"], "100.00")
        self.assertEqual(result["outputs"]["currency_totals"][0]["draft_amount"], "0.00")
        self.assertFalse(result["outputs"]["currency_totals"][0]["comparison_complete"])

    def test_missing_entry_project_keeps_currency_and_amount_unknown(self):
        payload = minimal()
        payload["files"]["time-entries.json"][0]["project_id"] = "NO-PROJECT"
        result, _ = self.solve(payload)
        self.assertEqual(entry(result)["reason"], "missing-project")
        self.assertIsNone(entry(result)["currency"])
        self.assertIsNone(entry(result)["expected_amount"])
        self.assertEqual(len(result["outputs"]["projects"]), 1)
        self.assertTrue(any(row["owner"] == "data-steward" and row["code"] == "missing-project" for row in result["exceptions"]))

    def test_header_currency_and_project_identity_mismatches_are_clarifications(self):
        for field, value in (("currency", "EUR"), ("project_id", "NO-PROJECT")):
            with self.subTest(field=field):
                payload = minimal()
                payload["files"]["draft-invoices.json"][0][field] = value
                result, _ = self.solve(payload)
                self.assertEqual(entry(result)["reason"], "draft-identity-mismatch")
                self.assertEqual(result["outputs"]["draft_details"][0]["action"], "clarify-not-remove")
                self.assertIsNone(result["outputs"]["drafts"][0]["variance"])

    def test_missing_rate_and_policy_leave_amounts_uncomputed(self):
        payload = minimal()
        add_expense(payload)
        payload["files"]["rates.json"] = []
        payload["files"]["expense-policies.json"] = []
        result, _ = self.solve(payload)
        self.assertEqual(entry(result)["reason"], "missing-rate")
        self.assertEqual(entry(result, "EX", "expense")["reason"], "missing-policy")
        self.assertIsNone(entry(result)["expected_amount"])
        self.assertIsNone(entry(result, "EX", "expense")["expected_amount"])
        self.assertEqual(entry(result, "EX", "expense")["held_amount"], "20.00")

    def test_orphan_asof_approval_and_rate_are_owned_export_issues(self):
        payload = minimal()
        payload["files"]["approval-events.json"].append(dict(payload["files"]["approval-events.json"][0], approval_event_id="ORPHAN", entry_id="ABSENT"))
        payload["files"]["rates.json"].append(dict(payload["files"]["rates.json"][0], rate_id="ORPHAN-RATE", project_id="ABSENT"))
        result, _ = self.solve(payload)
        self.assertEqual({row["code"] for row in result["exceptions"]}, {"orphan-approval", "orphan-rate"})
        self.assertTrue(all(row["owner"] == "data-steward" for row in result["exceptions"]))
        payload["files"]["approval-events.json"][-1]["recorded_at"] = "2026-10-02T12:00:01Z"
        result, _ = self.solve(payload)
        self.assertNotIn("orphan-approval", {row["code"] for row in result["exceptions"]})

    def test_type_id_namespaces_do_not_cross_join(self):
        payload = minimal()
        expense = add_expense(payload)
        expense["expense_id"] = "TX"
        payload["files"]["approval-events.json"][-1]["entry_id"] = "TX"
        payload["files"]["approval-events.json"][-1]["decision"] = "recalled"
        result, _ = self.solve(payload)
        self.assertEqual(entry(result, "TX", "time")["expected_amount"], "100.00")
        self.assertEqual(entry(result, "TX", "expense")["reason"], "recalled")
        self.assertEqual(result["outputs"]["draft_details"][0]["action"], "match")

    def test_missing_draft_creates_only_local_diagnostic(self):
        payload = minimal()
        payload["files"]["draft-invoices.json"] = []
        payload["files"]["draft-lines.json"] = []
        result, _ = self.solve(payload)
        self.assertEqual(result["outputs"]["drafts"], [])
        row = result["outputs"]["draft_details"][0]
        self.assertEqual(row["reason"], "missing-draft")
        self.assertIsNone(row["draft_id"])
        self.assertIsNone(row["line_id"])
        self.assertIsNone(row["draft_amount"])
        self.assertEqual(row["expected_amount"], "100.00")
        self.assertTrue(row["diagnostic_only"])

    def test_old_draft_is_deferred_and_does_not_suppress_current_missing_diagnostic(self):
        payload = minimal()
        payload["files"]["draft-invoices.json"][0].update(period_start="2026-08-01", period_end="2026-09-01")
        result, _ = self.solve(payload)
        self.assertEqual(entry(result)["status"], "candidate")
        self.assertEqual(result["outputs"]["drafts"][0]["status"], "deferred")
        self.assertEqual([row["action"] for row in result["outputs"]["draft_details"]], ["add", "defer"])
        self.assertEqual(result["outputs"]["drafts"][0]["quarantined_draft_amount"], "100.00")
        self.assertIsNone(result["outputs"]["drafts"][0]["variance"])

    def test_zero_one_many_variable_loops_and_trace_subsets(self):
        payload = minimal()
        payload["files"] = {filename: [] for filename in EXPORTS}
        result, events = self.solve(payload)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["outputs"]["closure"], {
            "entry_count": 0, "draft_count": 0, "project_count": 0,
            "prior_billing_count": 0, "diagnostic_count": 0, "exception_count": 0,
        })
        self.assertEqual(len(events), 9)
        for count, amount in ((1, "1.67"), (12, "20.04")):
            with self.subTest(count=count):
                payload = minimal()
                seed_time = payload["files"]["time-entries.json"][0]
                seed_approval = payload["files"]["approval-events.json"][0]
                seed_line = payload["files"]["draft-lines.json"][0]
                payload["files"]["time-entries.json"] = [dict(seed_time, time_id=f"TX-{index:02}", minutes=1) for index in range(count)]
                payload["files"]["approval-events.json"] = [dict(seed_approval, approval_event_id=f"AX-{index:02}", entry_id=f"TX-{index:02}") for index in range(count)]
                payload["files"]["draft-lines.json"] = [dict(seed_line, line_id=f"LX-{index:02}", entry_id=f"TX-{index:02}", amount="1.67") for index in range(count)]
                result, events = self.solve(payload)
                self.assertEqual(result["status"], "completed")
                self.assertEqual(len(result["outputs"]["entries"]), count)
                self.assertEqual(result["outputs"]["projects"][0]["eligible_new_amount"], amount)
                self.assertEqual(result["outputs"]["drafts"][0]["line_count"], count)
                joins = next(event for event in events if event["kind"] == "join")["tables"][0]
                self.assertEqual(joins["total_rows"], count)
                self.assertEqual(len(joins["rows"]), min(8, count))

    def test_project_and_empty_draft_with_no_entries_are_accounted(self):
        payload = minimal()
        for filename in ("time-entries.json", "approval-events.json", "draft-lines.json"):
            payload["files"][filename] = []
        result, _ = self.solve(payload)
        self.assertEqual(result["outputs"]["projects"][0]["entry_count"], 0)
        self.assertEqual(result["outputs"]["drafts"][0]["line_count"], 0)
        self.assertEqual(result["outputs"]["drafts"][0]["variance"], "0.00")
        self.assertEqual(result["status"], "completed")

    def test_all_export_primary_key_duplicates_reject_before_computation(self):
        for filename in EXPORTS:
            with self.subTest(export=filename):
                payload = minimal()
                add_expense(payload)
                add_prior(payload)
                payload["files"][filename].append(copy.deepcopy(payload["files"][filename][0]))
                result, events = self.solve(payload)
                self.assertEqual(result["status"], "rejected")
                self.assertEqual(result["outputs"], {})
                self.assertIn("duplicate-id", {row["code"] for row in result["exceptions"]})
                self.assertEqual(len(events), 2)

    def test_strict_business_schema_errors_do_not_silently_default(self):
        mutations = [
            ("config", "draft_tolerance", "0.01", "unsupported-tolerance"),
            ("config", "as_of", "2026-10-02T12:00:00", "invalid-instant"),
            ("config", "as_of", "2026-10-02T12:00:00.123Z", "invalid-instant"),
            ("config", "as_of", "2026-10-02T12:00:00+01:99", "invalid-instant"),
            ("config", "period_start", "2026-09-31", "invalid-date"),
            ("time-entries.json", "minutes", True, "invalid-integer"),
            ("time-entries.json", "minutes", 0, "invalid-integer"),
            ("time-entries.json", "minutes", 1.0, "invalid-integer"),
            ("time-entries.json", "chargeable", 1, "invalid-boolean"),
            ("time-entries.json", "time_id", " ", "invalid-id"),
            ("time-entries.json", "service_date", "20260915", "invalid-date"),
            ("expense-entries.json", "amount", "-12.00", "invalid-amount"),
            ("expense-entries.json", "amount", "1e2", "invalid-amount"),
            ("expense-entries.json", "amount", "01.00", "invalid-amount"),
            ("expense-entries.json", "amount", 12.00, "invalid-amount"),
            ("expense-entries.json", "amount", "NaN", "invalid-amount"),
            ("expense-entries.json", "receipt_reference", "", "invalid-id"),
            ("expense-entries.json", "receipt_reference", True, "invalid-id"),
            ("projects.json", "currency", "usd", "invalid-currency"),
            ("approval-events.json", "revision", False, "invalid-integer"),
            ("approval-events.json", "decision", "confirm", "invalid-enum"),
            ("draft-invoices.json", "state", "confirmed", "invalid-enum"),
            ("draft-invoices.json", "period_end", "2026-09-01", "invalid-interval"),
            ("rates.json", "valid_to", "2026-09-01", "invalid-interval"),
        ]
        for table, field, value, code in mutations:
            with self.subTest(table=table, field=field, value=value):
                payload = minimal()
                add_expense(payload)
                target = payload["config"] if table == "config" else payload["files"][table][0]
                target[field] = value
                result, events = self.solve(payload)
                self.assertEqual(result["status"], "rejected")
                self.assertEqual(result["outputs"], {})
                self.assertIn(code, {row["code"] for row in result["exceptions"]})
                self.assertEqual(len(events), 2)

    def test_unknown_missing_and_nonobject_fields_reject_whole_bundle(self):
        mutations = (
            lambda p: p.update(extra=True),
            lambda p: p["config"].update(extra=True),
            lambda p: p["files"].update(extra=[]),
            lambda p: p["files"].pop("expense-policies.json"),
            lambda p: p["files"]["time-entries.json"][0].pop("minutes"),
            lambda p: p["files"]["projects.json"][0].update(secret_default=True),
            lambda p: p["files"].update({"rates.json": {}}),
            lambda p: p["files"]["draft-lines.json"].append(None),
            lambda p: p.update(config=None),
        )
        for index, mutate in enumerate(mutations):
            with self.subTest(mutation=index):
                payload = minimal()
                mutate(payload)
                result, _ = self.solve(payload)
                self.assertEqual(result["status"], "rejected")
                self.assertEqual(result["outputs"], {})
                self.assertIn("invalid-schema", {row["code"] for row in result["exceptions"]})


class BillingSharedAdapterTests(LockedTests):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.work = ROOT / "validation" / ("unittest-work-" + uuid.uuid4().hex)
        cls.work.mkdir(parents=True, exist_ok=False)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.work)
        super().tearDownClass()

    def setUp(self):
        self.directory = self.work / self._testMethodName
        self.directory.mkdir()

    def write(self, name, data):
        path = self.directory / name
        with path.open("xb") as handle:
            handle.write(data)
        return path

    def cli(self, input_path, output_path=None, trace_path=None):
        output_path = output_path or self.directory / "result.json"
        trace_path = trace_path or self.directory / "trace.json"
        process = subprocess.run(
            [sys.executable, "-B", "-I", str(ROOT / "baseline.py"), "--input", str(input_path),
             "--output", str(output_path), "--trace", str(trace_path)],
            cwd=ROOT, capture_output=True, text=True, timeout=20, check=False,
        )
        return process, output_path, trace_path

    def test_shared_cli_writes_real_result_and_bound_trace(self):
        content = json.dumps(minimal(), indent=2).encode("utf-8")
        input_path = self.write("input.json", content)
        process, output_path, trace_path = self.cli(input_path)
        self.assertEqual(process.returncode, 0, process.stderr)
        result, trace = json.loads(output_path.read_bytes()), json.loads(trace_path.read_bytes())
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["outputs"]["entries"][0]["expected_amount"], "100.00")
        self.assertEqual(trace["input_sha256"], hashlib.sha256(content).hexdigest())
        self.assertEqual(trace["provenance"], "synthetic-local-baseline")
        self.assertEqual(trace["scenario_id"], "cross-industry-03")
        self.assertEqual([event["sequence"] for event in trace["events"]], list(range(1, 10)))
        self.assertEqual(input_path.read_bytes(), content)

    def test_shared_cli_business_rejection_is_explicit_zero_exit(self):
        input_path = ROOT / "mock-data" / "negative-malformed.json"
        before = input_path.read_bytes()
        process, output_path, trace_path = self.cli(input_path)
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(json.loads(output_path.read_bytes()), fixture("negative-malformed", "expected"))
        self.assertEqual(len(json.loads(trace_path.read_bytes())["events"]), 2)
        self.assertEqual(input_path.read_bytes(), before)

    def test_shared_cli_refuses_existing_result_and_trace_without_overwrite(self):
        input_path = self.write("input.json", json.dumps(minimal()).encode("utf-8"))
        output_path = self.write("result.json", b"existing result")
        trace_path = self.write("trace.json", b"existing trace")
        before = {path: path.read_bytes() for path in (input_path, output_path, trace_path)}
        process, _, _ = self.cli(input_path)
        self.assertEqual(process.returncode, 2)
        self.assertIn("refuses existing outputs", process.stderr)
        self.assertEqual({path: path.read_bytes() for path in before}, before)

    def test_shared_cli_refuses_either_existing_destination_before_writing_other(self):
        for existing in ("result", "trace"):
            with self.subTest(existing=existing):
                input_path = self.write(existing + "-input.json", json.dumps(minimal()).encode("utf-8"))
                output_path = self.directory / (existing + "-result.json")
                trace_path = self.directory / (existing + "-trace.json")
                target = output_path if existing == "result" else trace_path
                target.write_bytes(b"keep")
                process, _, _ = self.cli(input_path, output_path, trace_path)
                self.assertEqual(process.returncode, 2)
                self.assertEqual(target.read_bytes(), b"keep")
                self.assertFalse((trace_path if existing == "result" else output_path).exists())

    def test_shared_cli_refuses_path_aliases_without_modifying_input(self):
        for pair in ("input-result", "input-trace", "result-trace"):
            with self.subTest(pair=pair):
                content = json.dumps(minimal()).encode("utf-8")
                input_path = self.write(pair + "-input.json", content)
                output_path = self.directory / (pair + "-result.json")
                trace_path = self.directory / (pair + "-trace.json")
                if pair == "input-result":
                    output_path = input_path
                elif pair == "input-trace":
                    trace_path = input_path
                else:
                    trace_path = output_path
                process, _, _ = self.cli(input_path, output_path, trace_path)
                self.assertEqual(process.returncode, 2)
                self.assertIn("must be distinct", process.stderr)
                self.assertEqual(input_path.read_bytes(), content)
                self.assertFalse(any(path.exists() for path in (output_path, trace_path) if path != input_path))

    def test_shared_cli_rejects_malformed_deep_duplicate_and_nonfinite_json(self):
        cases = {
            "malformed": b'{"config":',
            "duplicate": b'{"config": {}, "config": {}}',
            "nested-duplicate": b'{"config": {"as_of": 1, "as_of": 2}}',
            "nan": b'{"number": NaN}',
            "infinity": b'{"number": Infinity}',
            "negative-infinity": b'{"number": -Infinity}',
            "overflow-number": b'{"number": 1e999}',
            "nonobject": b"[]",
            "invalid-utf8": b"\xff",
            "deep": (b'{"nested":' * 90) + b"0" + (b"}" * 90),
        }
        for name, content in cases.items():
            with self.subTest(case=name):
                input_path = self.write(name + ".json", content)
                process, output_path, trace_path = self.cli(
                    input_path, self.directory / (name + "-result.json"), self.directory / (name + "-trace.json")
                )
                self.assertEqual(process.returncode, 2, process.stderr)
                self.assertFalse(output_path.exists())
                self.assertFalse(trace_path.exists())
                self.assertEqual(input_path.read_bytes(), content)

    def test_shared_cli_rejects_oversized_input_before_json_parsing(self):
        input_path = self.write("large.json", b" " * (8 * 1024 * 1024 + 1))
        process, output_path, trace_path = self.cli(input_path)
        self.assertEqual(process.returncode, 2)
        self.assertIn("exceeds 8 MiB", process.stderr)
        self.assertFalse(output_path.exists())
        self.assertFalse(trace_path.exists())


if __name__ == "__main__":
    unittest.main()
