import contextlib
import io
import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

from scenarios._shared.cli import main
from scenarios._shared.common import ContractError, file_digest
from scenarios._shared.contract import load_scenario
from scenarios._shared.pipeline import check_case_evidence, golden_lock, run_case
from scenarios._shared.reporting import build_catalog, write_reports
from scenarios.tests.fixtures import dump, make_scenario, modify_json, temporary_directory


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temporary = temporary_directory()
        self.addCleanup(self.temporary.cleanup)
        self.corpus = Path(self.temporary.name) / "scenarios"
        self.root = make_scenario(self.corpus)
        self.scenario = load_scenario(self.root)

    def test_all_cases_pass_without_any_native_inference(self):
        before = {case["expected"]: file_digest(self.scenario.file(case["expected"])) for case in self.scenario.cases}
        for case in self.scenario.cases:
            report = run_case(self.scenario, case)
            self.assertEqual(report["state"], "baseline_pass", report["errors"])
            checked = check_case_evidence(self.scenario, case)
            self.assertEqual(checked["native"]["creation"], "native_creation_blocked")
            self.assertEqual(checked["native"]["installation"], "not_run")
            self.assertEqual(checked["native"]["observed"], [])
            self.assertEqual(file_digest(self.scenario.file(case["expected"])), before[case["expected"]])

    def test_modified_golden_cannot_turn_failure_into_pass(self):
        case = self.scenario.case("demo")
        self.assertEqual(run_case(self.scenario, case)["state"], "baseline_pass")
        modify_json(self.root / "expected" / "demo.json", lambda item: item["outputs"].update(doubled=99))
        with self.assertRaisesRegex(ContractError, "changed after their lock"):
            check_case_evidence(self.scenario, case)
        result = run_case(self.scenario, case, replace=True)
        self.assertEqual(result["state"], "baseline_failed")
        self.assertIn("lock", " ".join(result["errors"]))

    def test_modification_during_baseline_is_detected(self):
        real_run = subprocess.run

        def modify_after_execution(*args, **kwargs):
            process = real_run(*args, **kwargs)
            modify_json(self.root / "mock-data" / "demo.json", lambda item: item.update(value=100))
            return process

        with mock.patch("scenarios._shared.pipeline.subprocess.run", side_effect=modify_after_execution):
            result = run_case(self.scenario, self.scenario.case("demo"))
        self.assertEqual(result["state"], "baseline_failed")
        self.assertIn("mock-data/demo.json", result["source_mutations"])

    def test_full_result_mismatch_not_just_totals(self):
        modify_json(self.root / "expected" / "demo.json", lambda item: item["outputs"].update(required_rows=["a", "b"]))
        scenario = load_scenario(self.root)
        result = run_case(scenario, scenario.case("demo"))
        self.assertEqual(result["state"], "baseline_failed")
        self.assertEqual(result["local"]["differences"][0]["path"], "/outputs/required_rows")

    def test_process_failure_is_not_a_passed_negative(self):
        path = self.root / "baseline.py"
        path.write_text(path.read_text(encoding="utf-8").replace(
            "value = payload.get", "raise RuntimeError('unit fixture failure')\n    value = payload.get",
        ), encoding="utf-8")
        scenario = load_scenario(self.root)
        result = run_case(scenario, scenario.case("negative-malformed"))
        self.assertEqual(result["state"], "baseline_failed")
        self.assertEqual(result["local"]["comparison"], "not_run")
        self.assertNotEqual(result["execution"]["returncode"], 0)

    def test_timeout_is_not_an_observation(self):
        with mock.patch("scenarios._shared.pipeline.subprocess.run", side_effect=subprocess.TimeoutExpired("baseline", 1)):
            result = run_case(self.scenario, self.scenario.case("demo"))
        self.assertEqual(result["state"], "baseline_failed")
        self.assertEqual(result["observed"]["steps"], [])

    def test_forged_local_report_cannot_claim_native_or_hide_output_change(self):
        case = self.scenario.case("demo")
        report = run_case(self.scenario, case)
        report_path = self.root / "validation" / "demo.json"
        report["native"]["creation"] = "generated"
        dump(report_path, report)
        with self.assertRaisesRegex(ContractError, "must not assert"):
            check_case_evidence(self.scenario, case)
        report["native"]["creation"] = "native_creation_blocked"
        result_path = self.root / "baseline-output" / "demo.json"
        modify_json(result_path, lambda item: item["outputs"].update(doubled=40))
        report["artifacts"]["result_sha256"] = file_digest(result_path)
        dump(report_path, report)
        with self.assertRaisesRegex(ContractError, "semantic"):
            check_case_evidence(self.scenario, case)

    def test_adapter_refuses_invalid_json_and_input_output_aliasing(self):
        bad = self.root / "mock-data" / "invalid-json.json"
        bad.write_bytes(b'{"invalid":')
        for input_path, output_path in ((bad, self.root / "new-result.json"), (bad, bad)):
            process = subprocess.run([
                sys.executable, "-B", str(self.root / "baseline.py"),
                "--input", str(input_path), "--output", str(output_path),
                "--trace", str(self.root / "new-trace.json"),
            ], capture_output=True, check=False)
            self.assertNotEqual(process.returncode, 0)
            self.assertFalse((self.root / "new-trace.json").exists())
        self.assertEqual(bad.read_bytes(), b'{"invalid":')

    def test_empty_catalog_and_pending_output_cannot_pass(self):
        catalog = build_catalog([], full=True)
        self.assertFalse(catalog["local_corpus_ready"])
        self.assertFalse(catalog["native_complete"])
        output = Path(self.temporary.name) / "output"
        write_reports(self.corpus, output, catalog)
        status = json.loads((output / "status.json").read_text(encoding="utf-8"))
        self.assertEqual(status["implemented_scenario_count"], 0)
        self.assertEqual(status["scenarios"], [])
        self.assertFalse(any(output.rglob("*.zip")))
        self.assertEqual(status["native"]["creation"], "native_creation_blocked")

    def test_cli_reports_nonzero_for_incomplete_corpus(self):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(["--root", str(self.corpus), "validate", "--full"]), 1)
            self.assertEqual(main(["--root", str(self.corpus), "run", "--scenario", "missing"]), 2)

    def test_reporting_does_not_overwrite_other_native_lifecycle_facts(self):
        output = Path(self.temporary.name) / "output"
        supplied = {"schema_version": 1, "provenance": "operator-observed-facts", "native_complete": False}
        dump(output / "status.json", supplied)
        with self.assertRaisesRegex(ContractError, "owned by another workflow"):
            write_reports(self.corpus, output, build_catalog([], full=True))
        self.assertFalse((self.corpus / "catalog.json").exists())
        self.assertEqual(json.loads((output / "status.json").read_text(encoding="utf-8")), supplied)


if __name__ == "__main__":
    unittest.main()
