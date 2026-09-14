import json
import unittest
from pathlib import Path

from scenarios._shared.common import ContractError, contained_path, parse_json, path_parts
from scenarios._shared.comparison import compare_json
from scenarios._shared.contract import baseline_import_audit, discover, load_scenario, validate_result, validate_trace
from scenarios._shared.pipeline import run_case
from scenarios.tests.fixtures import dump, make_scenario, modify_json, temporary_directory


class JsonAndPathTests(unittest.TestCase):
    def test_invalid_json_is_explicit(self):
        for content in (b'{"a":1,"a":2}', b'{"n":NaN}', b'{"n":1e400}', b'{"a":', b"\xff", b"[] trailing", b"\xef\xbb\xbf{}"):
            with self.subTest(content=content), self.assertRaises(ContractError):
                parse_json(content)
        with self.assertRaises(ContractError):
            parse_json(("[" * 82 + "0" + "]" * 82).encode())

    def test_nonportable_or_escaping_paths(self):
        for path in ("../outside", "/absolute", "C:/outside", "a\\b", "//server/share", "a//b", "a/./b",
                     "a/../b", "file:stream", "NUL.txt", "COM1", "a/b.", "a/b ", "a/\x00b"):
            with self.subTest(path=path), self.assertRaises(ContractError):
                path_parts(path)
        self.assertEqual(path_parts("mock-data/demo.json"), ["mock-data", "demo.json"])

    def test_missing_path_and_link_rejected(self):
        with temporary_directory() as temporary:
            root = Path(temporary)
            with self.assertRaises(ContractError):
                contained_path(root, "missing.json")
            target = root / "target.json"
            target.write_text("{}", encoding="utf-8")
            try:
                (root / "alias.json").symlink_to(target)
            except OSError as error:
                self.skipTest(f"OS does not allow symlink creation: {error}")
            with self.assertRaises(ContractError):
                contained_path(root, "alias.json")

    def test_semantic_comparison_all_keys_and_order(self):
        self.assertEqual(compare_json({"b": [2, 3], "a": 1}, {"a": 1.0, "b": [2, 3]}), [])
        for expected, actual in (
            (True, 1), ({"a": 1}, {"a": 1, "extra": 2}),
            ({"rows": ["a", "b"]}, {"rows": ["b", "a"]}),
            ({"money": "1.00"}, {"money": "1.0"}),
            ({"fee": {"minor": 99}}, {"fee": {"minor": 98}}),
        ):
            with self.subTest(expected=expected, actual=actual):
                self.assertTrue(compare_json(expected, actual))
        difference = compare_json({"a/b~c": 1}, {"a/b~c": 2})
        self.assertEqual(difference[0]["path"], "/a~1b~0c")
        with self.assertRaises(ContractError):
            compare_json(1, 2, limit=0)

    def test_result_status_and_schema_cannot_be_faked(self):
        for result in (
            {"schema_version": True, "status": "completed", "outputs": {}, "exceptions": []},
            {"schema_version": 1, "status": "native_pass", "outputs": {}, "exceptions": []},
            {"schema_version": 1, "status": "rejected", "outputs": {}, "exceptions": []},
            {"schema_version": 1, "status": "completed", "outputs": [], "exceptions": []},
        ):
            with self.subTest(result=result), self.assertRaises(ContractError):
                validate_result(result)


class ScenarioContractTests(unittest.TestCase):
    def setUp(self):
        self.temporary = temporary_directory()
        self.addCleanup(self.temporary.cleanup)
        self.corpus = Path(self.temporary.name) / "scenarios"
        self.root = make_scenario(self.corpus)

    def test_fixture_discovery_and_required_cases(self):
        scenarios = discover(self.corpus)
        self.assertEqual([item.id for item in scenarios], ["unit-01"])
        self.assertEqual(len(scenarios[0].cases), 5)
        modify_json(self.root / "scenario.json", lambda item: item["cases"].pop())
        with self.assertRaises(ContractError):
            load_scenario(self.root)

    def test_independent_goldens_and_source_rules(self):
        modify_json(self.root / "scenario.json", lambda item: item["golden_provenance"].update(method="baseline-generated"))
        with self.assertRaisesRegex(ContractError, "independently"):
            load_scenario(self.root)

    def test_unsupported_mock_native_connection_claim(self):
        modify_json(self.root / "connections.json", lambda item: item.update(availability="installed"))
        with self.assertRaisesRegex(ContractError, "native connection"):
            load_scenario(self.root)

    def test_identical_inputs_are_not_held_out(self):
        demo = (self.root / "mock-data" / "demo.json").read_bytes()
        (self.root / "mock-data" / "holdout-a.json").write_bytes(demo)
        with self.assertRaisesRegex(ContractError, "duplicates"):
            load_scenario(self.root)

    def test_rule_provenance_requires_real_source_reference(self):
        modify_json(self.root / "workflow.json", lambda item: item["rules"][0]["provenance"].update(kind="source-backed"))
        with self.assertRaisesRegex(ContractError, "at least one source"):
            load_scenario(self.root)

    def test_native_or_golden_baseline_dependencies_rejected(self):
        baseline = self.root / "baseline.py"
        for source in ("import requests\n", "import subprocess\n", "import creator_builder\n",
                       "data = __import__('json')\n", "file = 'expected/demo.json'\n"):
            with self.subTest(source=source):
                baseline.write_text(source, encoding="utf-8")
                with self.assertRaises(ContractError):
                    baseline_import_audit(baseline)

    def test_case_path_traversal_rejected(self):
        modify_json(self.root / "scenario.json", lambda item: item["cases"][0].update(input="../secret.json"))
        with self.assertRaises(ContractError):
            load_scenario(self.root)

    def test_malformed_field_types_are_contract_errors(self):
        modify_json(self.root / "scenario.json", lambda item: item["cases"][0].update(expected_status={}))
        with self.assertRaises(ContractError):
            load_scenario(self.root)

    def test_trace_must_be_actual_local_demo_bound_to_input(self):
        scenario = load_scenario(self.root)
        report = run_case(scenario, scenario.case("demo"))
        self.assertEqual(report["state"], "baseline_pass", report["errors"])
        trace = json.loads((self.root / "baseline-output" / "demo.trace.json").read_text(encoding="utf-8"))
        for change in (
            lambda item: item.update(provenance="native"),
            lambda item: item.update(input_sha256="0" * 64),
            lambda item: item["events"].pop(),
            lambda item: item["events"][0].update(sequence=True),
            lambda item: item["events"][0]["tables"][0].update(highlight_rows=[9]),
        ):
            altered = json.loads(json.dumps(trace))
            change(altered)
            with self.assertRaises(ContractError):
                validate_trace(altered, scenario, scenario.case("demo"), report["artifacts"]["input_sha256"])


if __name__ == "__main__":
    unittest.main()
