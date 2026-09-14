"""Regress the reviewed native artifact, never the developer baseline.

Run explicitly with: python -B -m unittest discover -s tests\\native -v
The exact ZIP must first be inspected and staged in the documented .local area.
"""
from __future__ import annotations

import ast
import copy
import hashlib
import importlib.util
import json
import random
import subprocess
import sys
import tempfile
import unittest
import zipfile
from decimal import Decimal
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
STAGE = ROOT / ".local" / "native-output-15d75761c98a"
ARCHIVE = STAGE / "ready-items.zip"
HELPER = STAGE / "source" / "skills" / "ready-items-report" / "scripts" / "ready_items_report.py"
ARCHIVE_SHA = "15d75761c98a1a20818a86ae6a1ec2e96bd83de92fdd4d08184ba6647adf7419"
HELPER_SHA = "aa4fdbe508526e6b3ce881f8c94779f1c80d8b7ba0b3af886adb83e61a125ee6"
EXPECTED_ROWS = [
    "| N901 | 4 | 1.25 | 5.00 |",
    "| N903 | 3 | 0.10 | 0.30 |",
    "| N904 | 2 | 9.99 | 19.98 |",
    "| N905 | 1 | 2.50 | 2.50 |",
]


class NativeGeneratedOutputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not ARCHIVE.is_file() or not HELPER.is_file():
            raise unittest.SkipTest("Stage and inspect the exact native artifact before running these tests")
        if hashlib.sha256(ARCHIVE.read_bytes()).hexdigest() != ARCHIVE_SHA:
            raise AssertionError("Native ZIP differs from the inspected artifact; do not execute it")
        if hashlib.sha256(HELPER.read_bytes()).hexdigest() != HELPER_SHA:
            raise AssertionError("Native helper differs from the inspected source; do not execute it")
        module_spec = importlib.util.spec_from_file_location("reviewed_native_ready_items", HELPER)
        cls.helper = importlib.util.module_from_spec(module_spec)
        module_spec.loader.exec_module(cls.helper)
        cls.runs = STAGE / "test-runs"
        cls.runs.mkdir(exist_ok=True)

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="case-", dir=self.runs)
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.input = self.root / "runtime.json"
        self.output = self.root / "new-report.md"
        self.data = json.loads((ROOT / "examples" / "n00" / "input-new.json").read_text(encoding="utf-8"))

    def run_cli(self, raw=None, month="2026-09", input_path=None, output_path=None):
        selected_input = input_path or self.input
        if raw is not None:
            selected_input.write_bytes(raw if isinstance(raw, bytes) else raw.encode("utf-8"))
        return subprocess.run(
            [sys.executable, "-I", "-B", str(HELPER), "--input", str(selected_input),
             "--month", month, "--output", str(output_path or self.output)],
            cwd=self.root, capture_output=True, text=True, timeout=30,
        )

    def render(self, data, month="2026-09"):
        self.helper.validate_month(month)
        return self.helper.render(month, self.helper.validate_items(data))

    def test_reviewed_archive_identity_and_dependencies(self):
        with zipfile.ZipFile(ARCHIVE) as archive:
            self.assertIsNone(archive.testzip())
            self.assertEqual(set(archive.namelist()), {
                ".claude-plugin/plugin.json", "skills/ready-items-report/SKILL.md",
                "skills/ready-items-report/scripts/ready_items_report.py",
            })
            self.assertEqual(archive.read("skills/ready-items-report/scripts/ready_items_report.py"), HELPER.read_bytes())
            plugin = json.loads(archive.read(".claude-plugin/plugin.json"))
            self.assertEqual(plugin["name"], "ready-items")
            self.assertEqual(plugin["version"], "0.1.0")
        tree = ast.parse(HELPER.read_text(encoding="utf-8"))
        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                self.assertEqual(node.level, 0)
                imports.add(node.module)
        self.assertEqual(imports, {"argparse", "json", "re", "sys", "pathlib"})

    def test_actual_cli_produces_all_new_rows_counts_and_total(self):
        result = self.run_cli(json.dumps(self.data))
        self.assertEqual(result.returncode, 0, result.stderr)
        actual = self.output.read_text(encoding="utf-8")
        rows = [line for line in actual.splitlines() if line.startswith("| N")]
        self.assertEqual(rows, EXPECTED_ROWS)
        self.assertIn("Reporting month: 2026-09", actual)
        self.assertIn("Included rows: 4\nExcluded rows: 1\nGrand total: 27.78\n", actual)
        self.assertNotIn("N902", actual)
        self.assertNotIn("50.65", actual)
        self.assertNotIn("R101", actual)
        self.assertNotIn("2026-08", actual)
        self.assertEqual(result.stderr, "")

    def test_preserves_input_order_and_exact_fractional_values(self):
        data = {"items": [
            {"id": "Z", "state": "ready", "quantity": 3, "unit_cost": "0.10"},
            {"id": "A", "state": "ready", "quantity": 1, "unit_cost": "0.20"},
        ]}
        actual = self.render(data)
        self.assertLess(actual.index("| Z |"), actual.index("| A |"))
        self.assertIn("Grand total: 0.50", actual)

    def test_empty_and_all_hold(self):
        for data, excluded in (({"items": []}, 0), ({"items": [self.data["items"][1]]}, 1)):
            with self.subTest(excluded=excluded):
                actual = self.render(data)
                self.assertIn(f"Included rows: 0\nExcluded rows: {excluded}\nGrand total: 0.00", actual)

    def test_invalid_values_are_rejected_even_for_hold_rows(self):
        invalid = {
            "quantity": [True, False, 0, -1, 100001, 1.0, "1", None],
            "unit_cost": ["", "-1.00", "+1.00", "1", "1.0", "1.000", "1e2",
                          "NaN", "Infinity", " 1.00", "1000000000.00", "1.\u0660\u0660", 1, None],
            "state": ["READY", "unknown", False, None, [], {}],
            "id": ["", "x" * 65, "space name", "../outside", "|markup|", "\u00e9", None, 1],
        }
        for field, values in invalid.items():
            for value in values:
                data = copy.deepcopy(self.data)
                data["items"][1][field] = value
                with self.subTest(field=field, value=value), self.assertRaises(self.helper.ValidationError):
                    self.render(data)

    def test_leading_zero_prices_are_valid_nonnegative_decimal_strings(self):
        data = {"items": [{"id": "A", "state": "ready", "quantity": 2, "unit_cost": "00012.50"}]}
        self.assertIn("| A | 2 | 12.50 | 25.00 |", self.render(data))
        data["items"][0]["unit_cost"] = "0000000000000000000000000000000000000.00"
        self.assertIn("Grand total: 0.00", self.render(data))

    def test_invalid_shapes_duplicate_ids_and_case_sensitive_identity(self):
        for value in (None, [], {"items": {}}, {"items": [], "extra": 1},
                      {"items": [False]}, {"items": [dict(self.data["items"][0], extra=1)]},
                      {"items": [self.data["items"][0], self.data["items"][0]]}):
            with self.subTest(value_type=type(value)), self.assertRaises(self.helper.ValidationError):
                self.render(value)
        data = {"items": [dict(self.data["items"][0], id="a"), dict(self.data["items"][0], id="A")]}
        self.assertIn("Included rows: 2", self.render(data))

    def test_month_boundaries_and_ascii_format(self):
        for month in ("0001-01", "9999-12", "2024-02"):
            with self.subTest(month=month):
                self.assertIn("Reporting month: " + month, self.render({"items": []}, month))
        for month in ("0000-01", "2026-00", "2026-13", "26-09", "2026-9",
                      "2026-09-01", "2026-09\n", "2\u0660\u0662\u0666-09", ""):
            with self.subTest(month=month), self.assertRaises(self.helper.ValidationError):
                self.render(self.data, month)

    def test_duplicate_json_keys_and_numeric_forms_fail_without_output(self):
        bad_inputs = [
            '{"items":[],"items":[]}',
            '{"items":[{"id":"a","id":"b","state":"ready","quantity":1,"unit_cost":"1.00"}]}',
            '{"items":[{"id":"a","state":"ready","quantity":1e0,"unit_cost":"1.00"}]}',
            '{"items":[{"id":"a","state":"hold","quantity":1.0,"unit_cost":"1.00"}]}',
            '{"items":NaN}', '{"items":Infinity}', "{broken",
        ]
        for raw in bad_inputs:
            with self.subTest(raw=raw):
                result = self.run_cli(raw)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertEqual(result.stdout, "")
                self.assertTrue(result.stderr.startswith("Error:"))
                self.assertFalse(self.output.exists())

    def test_existing_output_is_not_overwritten(self):
        self.output.write_text("existing user content", encoding="utf-8")
        result = self.run_cli(json.dumps(self.data))
        self.assertEqual(result.returncode, 2)
        self.assertIn("destination already exists", result.stderr)
        self.assertEqual(self.output.read_text(encoding="utf-8"), "existing user content")

    def test_required_cli_arguments_have_no_defaults(self):
        result = subprocess.run([sys.executable, "-I", "-B", str(HELPER)], cwd=self.root,
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 2)
        self.assertIn("--input", result.stderr)
        self.assertIn("--month", result.stderr)
        self.assertIn("--output", result.stderr)
        self.assertFalse(self.output.exists())

    def test_missing_or_invalid_utf8_input_fails_without_output(self):
        missing = self.run_cli()
        self.assertEqual(missing.returncode, 2)
        self.assertFalse(self.output.exists())
        invalid = self.run_cli(b"\xff\xfeinvalid")
        self.assertEqual(invalid.returncode, 2)
        self.assertFalse(self.output.exists())

    def test_exact_maximum_rows_and_arithmetic_then_over_limit(self):
        data = {"items": [
            {"id": str(index), "state": "ready", "quantity": 100000, "unit_cost": "999999999.99"}
            for index in range(10000)
        ]}
        self.assertIn("Grand total: 999999999990000000.00", self.render(data))
        data["items"].append(dict(data["items"][0], id="10000"))
        with self.assertRaises(self.helper.ValidationError):
            self.render(data)

    def test_varied_inputs_match_independent_decimal_reference(self):
        rng = random.Random(8401)
        for case in range(100):
            rows = []
            expected = Decimal("0.00")
            included = 0
            for index in range(rng.randrange(21)):
                cost = f"{rng.randrange(1000)}.{rng.randrange(100):02d}"
                quantity = rng.randrange(1, 100001)
                state = rng.choice(("ready", "hold"))
                rows.append({"id": f"C{case}R{index}", "state": state, "quantity": quantity, "unit_cost": cost})
                if state == "ready":
                    expected += Decimal(cost) * quantity
                    included += 1
            with self.subTest(case=case):
                actual = self.render({"items": rows})
                self.assertIn(f"Grand total: {expected:.2f}", actual)
                self.assertIn(f"Included rows: {included}\nExcluded rows: {len(rows) - included}", actual)

    def test_paths_with_spaces_and_shell_characters_are_literal_arguments(self):
        input_path = self.root / "inventory & data.json"
        output_path = self.root / "report with spaces.md"
        result = self.run_cli(json.dumps(self.data), input_path=input_path, output_path=output_path)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Grand total: 27.78", output_path.read_text(encoding="utf-8"))
        self.assertEqual(set(path.name for path in self.root.iterdir()), {input_path.name, output_path.name})


if __name__ == "__main__":
    unittest.main()
