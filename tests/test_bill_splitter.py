from __future__ import annotations

import copy
import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from decimal import Decimal, localcontext
from itertools import permutations
from pathlib import Path

from test_builder import ROOT, builder

EXAMPLE = ROOT / "examples" / "bill-splitter"
CANDIDATE = EXAMPLE / "candidate"
SKILL = CANDIDATE / "skills" / "split-restaurant-bill"
MODULE_SPEC = importlib.util.spec_from_file_location("bill_splitter_tests", SKILL / "scripts" / "split_bill.py")
split_bill = importlib.util.module_from_spec(MODULE_SPEC)
sys.path.insert(0, str(SKILL / "scripts"))
try:
    MODULE_SPEC.loader.exec_module(split_bill)
finally:
    sys.path.remove(str(SKILL / "scripts"))


class BillSplitterTests(unittest.TestCase):
    def setUp(self):
        self.meal = json.loads((EXAMPLE / "input-new.json").read_text(encoding="utf-8"))
        self.expected = json.loads((EXAMPLE / "expected-new-split.json").read_text(encoding="utf-8"))
        self.temporary = tempfile.TemporaryDirectory(prefix="bill-splitter-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def invoke(self, content, *, script=None, output=None):
        source = self.root / "meal.json"
        source.write_bytes(content if isinstance(content, bytes) else content.encode("utf-8"))
        target = output if output is not None else self.root / "split.json"
        result = subprocess.run(
            [sys.executable, "-E", "-s", "-B", str(script or SKILL / "scripts" / "split_bill.py"),
             "--input", str(source), "--output", str(target)],
            cwd=self.root, capture_output=True, text=True, timeout=30,
        )
        return result, target

    def assert_reconciles(self, result):
        for field, total in (("items", "items_subtotal"), ("tax_share", "tax"),
                             ("tip_share", "tip"), ("total_owed", "grand_total")):
            self.assertEqual(sum(Decimal(person[field]) for person in result["people"]),
                             Decimal(result[total]))
        for person in result["people"]:
            self.assertEqual(sum(Decimal(person[key]) for key in ("items", "tax_share", "tip_share")),
                             Decimal(person["total_owed"]))
        self.assertEqual(result["check"], "0.00")

    def test_held_out_input_matches_complete_independent_expected_output(self):
        self.assertEqual(split_bill.compute(self.meal), self.expected)
        result, target = self.invoke(json.dumps(self.meal))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(target.read_text(encoding="utf-8")), self.expected)

    def test_receipt_order_does_not_change_diner_amounts(self):
        for lines in permutations(self.meal["lines"]):
            meal = dict(self.meal, lines=list(lines))
            with self.subTest(order=[line["label"] for line in lines]):
                self.assertEqual(split_bill.compute(meal)["people"], self.expected["people"])

    def test_even_split_and_zero_share_diner(self):
        meal = {
            "diners": ["Ana", "Bo", "Cleo", "Dev", "Eli"],
            "lines": [{"label": "Platter", "amount": 16,
                       "shares": {"Ana": 1, "Bo": 1, "Cleo": 1, "Dev": 1}}],
            "tax": 4, "tip_rate": 0.25,
        }
        result = split_bill.compute(meal)
        self.assertEqual([person["total_owed"] for person in result["people"]],
                         ["6.00", "6.00", "6.00", "6.00", "0.00"])
        self.assert_reconciles(result)

    def test_remainder_ties_follow_diner_order(self):
        meal = {
            "diners": ["Ana", "Bo", "Cleo"],
            "lines": [{"label": "Cake", "amount": 9.50, "shares": {"Ana": 1, "Bo": 1, "Cleo": 1}}],
            "tax": 0, "tip_amount": 0,
        }
        result = split_bill.compute(meal)
        self.assertEqual([person["total_owed"] for person in result["people"]], ["3.17", "3.17", "3.16"])
        self.assert_reconciles(result)
        meal["diners"].reverse()
        reversed_result = split_bill.compute(meal)
        self.assertEqual(reversed_result["people"][0]["name"], "Cleo")
        self.assertEqual(reversed_result["people"][0]["total_owed"], "3.17")

    def test_printed_gratuity_is_not_recomputed_from_displayed_rate(self):
        meal = {
            "diners": ["Ana", "Bo"],
            "lines": [{"label": "Set menu x2", "amount": 40, "shares": {"Ana": 1, "Bo": 1}}],
            "tax": 3, "tip_amount": 7.77, "printed_total": 50.77,
        }
        result = split_bill.compute(meal)
        self.assertEqual(result["tip"], "7.77")
        self.assertEqual([person["total_owed"] for person in result["people"]], ["25.39", "25.38"])
        self.assert_reconciles(result)

    def test_different_share_denominators_reconcile_each_component_independently(self):
        meal = {
            "diners": ["Ana", "Bo", "Cleo"],
            "lines": [
                {"label": "First sample", "amount": 0.01, "shares": {"Ana": 1, "Bo": 1, "Cleo": 1}},
                {"label": "Second sample", "amount": 0.02, "shares": {"Ana": 1, "Bo": 2, "Cleo": 4}},
            ],
            "tax": 0.04, "tip_amount": 0.05,
        }
        # Exact items in cents are 13/21, 19/21 and 31/21, not rounded line costs.
        expected = [
            {"name": "Ana", "items": "0.01", "tax_share": "0.01", "tip_share": "0.01", "total_owed": "0.03"},
            {"name": "Bo", "items": "0.01", "tax_share": "0.01", "tip_share": "0.02", "total_owed": "0.04"},
            {"name": "Cleo", "items": "0.01", "tax_share": "0.02", "tip_share": "0.02", "total_owed": "0.05"},
        ]
        for lines in permutations(meal["lines"]):
            result = split_bill.compute(dict(meal, lines=list(lines)))
            self.assertEqual(result["people"], expected)
            self.assert_reconciles(result)

    def test_tip_rounds_half_up_and_does_not_depend_on_global_decimal_context(self):
        meal = {"diners": ["Ana"], "lines": [{"label": "Snack", "amount": 0.05, "shares": {"Ana": 1}}],
                "tax": 0, "tip_rate": 0.1}
        with localcontext() as context:
            context.prec = 2
            result = split_bill.compute(meal)
            normal = split_bill.compute(self.meal)
        self.assertEqual(result["tip"], "0.01")
        self.assertEqual(result["grand_total"], "0.06")
        self.assertEqual(normal, self.expected)

    def test_maximum_sheet_amounts_and_shares_remain_exact(self):
        diners = [f"P{index}" for index in range(8)]
        meal = {
            "diners": diners,
            "lines": [{"label": f"Line {index}", "amount": 999999999.99,
                       "shares": {name: 99 for name in diners}} for index in range(20)],
            "tax": 999999999.99, "tip_rate": 1,
            "printed_subtotal": 19999999999.80, "printed_total": 40999999999.59,
        }
        result = split_bill.compute(meal)
        self.assertEqual(result["grand_total"], "40999999999.59")
        self.assertEqual(result["lines"][0]["shares_claimed"], 792)
        self.assert_reconciles(result)

    def test_invalid_top_level_values_and_required_fields(self):
        invalid = [None, [], False, {}, dict(self.meal, unexpected=True)]
        for field in ("diners", "lines", "tax"):
            value = copy.deepcopy(self.meal)
            del value[field]
            invalid.append(value)
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(split_bill.InputError):
                split_bill.compute(value)

    def test_invalid_diners_and_labels(self):
        for diners in (None, "Ana", [], ["Ana"] * 2, ["Ana", " Ana "],
                       ["P" + str(index) for index in range(9)], [""], [" "], [False], ["x" * 65]):
            with self.subTest(diners=diners), self.assertRaises(split_bill.InputError):
                split_bill.compute(dict(self.meal, diners=diners))
        for field, values in (("meal_label", ("", " ", None, 3, "x" * 65)),
                              ("line_label", ("", " ", None, False, "x" * 121))):
            for value in values:
                meal = copy.deepcopy(self.meal)
                if field == "meal_label":
                    meal[field] = value
                else:
                    meal["lines"][0]["label"] = value
                with self.subTest(field=field, value=value), self.assertRaises(split_bill.InputError):
                    split_bill.compute(meal)

    def test_invalid_line_shapes_and_share_counts(self):
        line = self.meal["lines"][0]
        for lines in ([], None, "Soup", [line] * 21, [False], [{}],
                      [dict(line, extra=True)], [dict(line, shares={})],
                      [dict(line, shares={"Ana": 0})], [dict(line, shares={"Unknown": 1})]):
            with self.subTest(lines=lines), self.assertRaises(split_bill.InputError):
                split_bill.compute(dict(self.meal, lines=lines))
        for shares in (None, [], "Ana", {"Ana": True}, {"Ana": 1.5}, {"Ana": "1"},
                       {"Ana": -1}, {"Ana": 100}):
            meal = copy.deepcopy(self.meal)
            meal["lines"][0]["shares"] = shares
            with self.subTest(shares=shares), self.assertRaises(split_bill.InputError):
                split_bill.compute(meal)

    def test_money_and_rate_bounds(self):
        invalid_money = [True, False, None, "3.00", -1, 3.005, 1e-300,
                         float("nan"), float("inf"), 1000000000, 10 ** 80]
        for field in ("amount", "tax", "tip_amount", "printed_subtotal", "printed_total"):
            for value in invalid_money:
                meal = copy.deepcopy(self.meal)
                if field == "amount":
                    meal["lines"][0]["amount"] = value
                else:
                    meal[field] = value
                if field == "tip_amount":
                    del meal["tip_rate"]
                with self.subTest(field=field, value=value), self.assertRaises(split_bill.InputError):
                    split_bill.compute(meal)
        for rate in (True, None, "0.2", -0.1, 1.01, float("nan"), float("inf"), 1e-300):
            with self.subTest(rate=rate), self.assertRaises(split_bill.InputError):
                split_bill.compute(dict(self.meal, tip_rate=rate))
        meal = copy.deepcopy(self.meal)
        meal["lines"][0]["amount"] = 0
        with self.assertRaises(split_bill.InputError):
            split_bill.compute(meal)

    def test_tip_selection_and_receipt_cross_checks(self):
        missing_tip = dict(self.meal)
        del missing_tip["tip_rate"]
        for meal, message in (
            (missing_tip, "supply either"),
            (dict(self.meal, tip_amount=11), "supply only one"),
            (dict(self.meal, printed_subtotal=54), "printed_subtotal"),
            (dict(self.meal, printed_total=70), "printed_total"),
        ):
            with self.subTest(message=message), self.assertRaisesRegex(split_bill.InputError, message):
                split_bill.compute(meal)

    def test_json_failures_are_concise_and_leave_no_output(self):
        cases = [
            (b"\xff", "UTF-8"),
            ("{broken", "Invalid JSON"),
            ('{"diners":[],"diners":[]}', "duplicate"),
            ('{"tax":NaN}', "Non-finite"),
            ('{"tax":Infinity}', "Non-finite"),
            ("[" * 40 + "]" * 40, "nesting"),
            ("[" * 10000, "nesting|Invalid JSON"),
            ('{"tax":' + "9" * 6000 + "}", "number"),
            (" " * 200001, "byte limit"),
            ("[]", "top level"),
            ('{"tax":1e9999999999999999999}', "number"),
        ]
        for content, diagnostic in cases:
            with self.subTest(diagnostic=diagnostic):
                result, target = self.invoke(content)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertRegex(result.stderr, diagnostic)
                self.assertNotIn("Traceback", result.stderr)
                self.assertEqual(len(result.stderr.splitlines()), 1)
                self.assertFalse(target.exists())

    def test_raw_json_numbers_do_not_hide_fractional_cents_or_overflow(self):
        for number in ("0.0100000000000000001", "1e100", "1e-1000000"):
            content = ('{"diners":["Ana"],"lines":[{"label":"Tea","amount":' + number +
                       ',"shares":{"Ana":1}}],"tax":0,"tip_amount":0}')
            with self.subTest(number=number):
                result, target = self.invoke(content)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn("bill-split error:", result.stderr)
                self.assertNotIn("Traceback", result.stderr)
                self.assertFalse(target.exists())

    def test_invalid_unicode_does_not_create_empty_output(self):
        meal = dict(self.meal, meal_label="\ud800")
        result, target = self.invoke(json.dumps(meal))
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("Unicode", result.stderr)
        self.assertFalse(target.exists())

    def test_existing_output_and_input_are_preserved(self):
        target = self.root / "split.json"
        target.write_bytes(b"keep me")
        result, _ = self.invoke(json.dumps(self.meal), output=target)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertEqual(target.read_bytes(), b"keep me")
        content = json.dumps(self.meal)
        result, source = self.invoke(content, output=self.root / "meal.json")
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertEqual(source.read_text(encoding="utf-8"), content)

    def test_missing_output_directory_is_not_reported_as_missing_input(self):
        result, target = self.invoke(json.dumps(self.meal), output=self.root / "absent" / "split.json")
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertNotIn("input file not found", result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertFalse(target.exists())

    def test_missing_input_is_an_explicit_failure(self):
        source, target = self.root / "absent.json", self.root / "split.json"
        result = subprocess.run(
            [sys.executable, "-E", "-s", "-B", str(SKILL / "scripts" / "split_bill.py"),
             "--input", str(source), "--output", str(target)],
            cwd=self.root, capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("bill-split error:", result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertFalse(target.exists())

    def test_owned_references_resolve_and_source_packages_without_original_assets(self):
        payload, spec = builder.assemble(CANDIDATE, "compatible-source")
        self.assertEqual(spec["schema_version"], "creator-plugin-1")
        self.assertEqual(set(payload), {
            ".claude-plugin/plugin.json",
            "skills/split-restaurant-bill/SKILL.md",
            "skills/split-restaurant-bill/references/helper-contract.md",
            "skills/split-restaurant-bill/references/template-layout.md",
            "skills/split-restaurant-bill/scripts/safe_json.py",
            "skills/split-restaurant-bill/scripts/split_bill.py",
        })
        text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        for pointer in ("references/helper-contract.md", "references/template-layout.md", "scripts/split_bill.py"):
            self.assertIn(pointer, text)
            self.assertTrue(SKILL.joinpath(*pointer.split("/")).is_file())

    def test_extracted_package_runs_without_creator_or_creation_evidence(self):
        payload, _ = builder.assemble(CANDIDATE, "compatible-source")
        installed = self.root / "installed"
        with zipfile.ZipFile(io.BytesIO(builder.zip_bytes(payload))) as archive:
            archive.extractall(installed)
        script = installed / "skills" / "split-restaurant-bill" / "scripts" / "split_bill.py"
        result, target = self.invoke(json.dumps(self.meal), script=script)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(target.read_text(encoding="utf-8")), self.expected)
        self.assertFalse((installed / "examples").exists())
        self.assertFalse((installed / "skills" / "create-process-plugin").exists())


if __name__ == "__main__":
    unittest.main()
