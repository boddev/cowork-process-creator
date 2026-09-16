from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

from test_builder import CANDIDATE, ROOT, builder, native_metadata

sys.dont_write_bytecode = True
REPORT_PATH = CANDIDATE / "skills" / "ready-items-report" / "scripts" / "report.py"
MODULE_SPEC = importlib.util.spec_from_file_location("ready_items_report_tests", REPORT_PATH)
report = importlib.util.module_from_spec(MODULE_SPEC)
MODULE_SPEC.loader.exec_module(report)


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.data = json.loads((ROOT / "examples" / "n00" / "input-new.json").read_text(encoding="utf-8"))
        self.temporary = tempfile.TemporaryDirectory(prefix="n00-report-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def test_changed_inputs_and_changed_loop_count(self):
        result = report.render(self.data, "2026-09")
        expected = (ROOT / "examples" / "n00" / "expected-new-report.md").read_text(encoding="utf-8")
        self.assertEqual(result, expected)
        self.assertIn("Included rows: 4\nExcluded rows: 1\nGrand total: 27.78\n", result)
        self.assertIn("| N903 | 3 | 0.10 | 0.30 |", result)
        self.assertNotIn("N902", result)
        self.assertNotIn("50.65", result)
        self.assertNotIn("2026-08", result)
        self.assertLess(result.index("N901"), result.index("N903"))

    def test_empty_and_all_hold(self):
        self.assertIn("Included rows: 0\nExcluded rows: 0\nGrand total: 0.00", report.render({"items": []}, "2026-01"))
        data = {"items": [dict(self.data["items"][0], state="hold")]}
        self.assertIn("Included rows: 0\nExcluded rows: 1\nGrand total: 0.00", report.render(data, "2026-12"))

    def test_numeric_and_type_errors_including_excluded_rows(self):
        variants = {
            "quantity": [True, False, 0, -1, 1.5, "2", 100001, None],
            "unit_cost": ["-1.00", "NaN", "Infinity", "1.1", "1.000", "1e2", 1.25, None,
                          "1000000000.00", " 1.00", "01.00", "1.\u0660\u0660"],
            "state": ["READY", "unknown", None, False, []],
            "id": ["", "space name", "../outside", "x|y", "x" * 65, None, 123],
        }
        for field, values in variants.items():
            for value in values:
                data = copy.deepcopy(self.data)
                data["items"][1][field] = value
                with self.subTest(field=field, value=value), self.assertRaises(report.InputError):
                    report.render(data, "2026-09")

    def test_duplicate_ids_fields_and_collection_limits(self):
        invalid = [
            None, [], {"items": "wrong"}, {"items": [], "extra": 1},
            {"items": [False]}, {"items": [dict(self.data["items"][0], extra=1)]},
            {"items": [self.data["items"][0], self.data["items"][0]]},
            {"items": [self.data["items"][0]] * 10001},
        ]
        for value in invalid:
            with self.subTest(kind=type(value)), self.assertRaises(report.InputError):
                report.render(value, "2026-09")

    def test_period_is_required_and_validated(self):
        for period in ("", "2026-00", "2026-13", "26-09", "0000-01", "2026-9",
                       "2026-09-01", "2026-09\n", "2\u0660\u0662\u0666-09", None):
            with self.subTest(period=period), self.assertRaises(report.InputError):
                report.render(self.data, period)

    def test_maximum_bounded_arithmetic_remains_exact(self):
        items = [{"id": str(index), "state": "ready", "quantity": 100000, "unit_cost": "999999999.99"} for index in range(10000)]
        self.assertIn("Grand total: 999999999990000000.00", report.render({"items": items}, "9999-12"))

    def test_existing_output_is_preserved(self):
        input_path, output_path = self.root / "input.json", self.root / "report.md"
        input_path.write_text(json.dumps(self.data), encoding="utf-8")
        output_path.write_text("keep this", encoding="utf-8")
        with self.assertRaises(FileExistsError):
            report.create_report(input_path, "2026-09", output_path)
        self.assertEqual(output_path.read_text(encoding="utf-8"), "keep this")

    def test_bad_json_or_large_file_creates_no_output(self):
        input_path, output_path = self.root / "input.json", self.root / "report.md"
        for raw in ('{"items":[],"items":[]}', '{"items":NaN}', "{broken",
                    '{"items":' + "[" * 1500 + "0" + "]" * 1500 + "}",
                    '{"items":' + "9" * 6000 + "}", " " * 2_000_001):
            input_path.write_text(raw, encoding="utf-8")
            with self.subTest(prefix=raw[:30]), self.assertRaises(report.InputError):
                report.create_report(input_path, "2026-09", output_path)
            self.assertFalse(output_path.exists())

    def test_installed_output_runs_on_new_input_without_creator_or_evidence(self):
        payload, _ = builder.assemble(CANDIDATE, builder.TARGET, native_metadata(self.root))
        archive_path = self.root / "output.zip"
        archive_path.write_bytes(builder.zip_bytes(payload))
        installed = self.root / "installed-output"
        with zipfile.ZipFile(archive_path) as archive:
            self.assertEqual(len(archive.namelist()), 6)
            archive.extractall(installed)
        input_path, output_path = self.root / "runtime.json", self.root / "new-report.md"
        input_path.write_text(json.dumps(self.data), encoding="utf-8")
        script = installed / "skills" / "ready-items-report" / "scripts" / "report.py"
        result = subprocess.run(
            [sys.executable, "-I", "-B", str(script), "--input", str(input_path),
             "--period", "2026-09", "--output", str(output_path)],
            cwd=self.root, capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        expected = (ROOT / "examples" / "n00" / "expected-new-report.md").read_text(encoding="utf-8")
        self.assertEqual(output_path.read_text(encoding="utf-8"), expected)
        self.assertFalse((installed / "skills" / "create-process-plugin").exists())
        self.assertFalse((installed / "examples").exists())
        self.assertFalse(any(path.suffix in {".png", ".mp4"} for path in (installed / "skills").rglob("*")))


if __name__ == "__main__":
    unittest.main()
