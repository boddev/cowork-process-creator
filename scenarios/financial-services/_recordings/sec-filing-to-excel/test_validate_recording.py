#!/usr/bin/env python3
"""Standard-library tests for validate_recording.py.

These tests build tiny .xlsx packages by writing the sheet XML directly with zipfile, so the
ordinary repository test path gains no openpyxl dependency. Writing the XML by hand is also the
point: it lets the tests reproduce the exact shapes real Excel emits, including shared formulas
from a fill-down and formula cells with no cached value.

Run only these tests:
    python -m unittest scenarios.financial-services._recordings.sec-filing-to-excel.test_validate_recording -v

or, from inside this folder:
    python test_validate_recording.py -v

These tests sit one level deeper than run_tests.py's discovery globs, so they are not picked up by
the ordinary suite and are run explicitly.
"""
import contextlib
import importlib.util
import io
from pathlib import Path
import sys
import tempfile
import unittest
from xml.sax.saxutils import escape
import zipfile

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent

_spec = importlib.util.spec_from_file_location(
    "sec_filing_validate_recording", ROOT / "validate_recording.py"
)
validate_recording = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(validate_recording)

FACTS = {
    5: ("Net Operating Revenues", 47061.0, 45754.0),
    6: ("Cost of goods sold", 18324.0, 18520.0),
    7: ("Gross Profit", 28737.0, 27234.0),
    8: ("Selling, general and administrative expenses", 14582.0, 13972.0),
    9: ("Other operating charges", 4163.0, 1951.0),
    10: ("Operating Income", 9992.0, 11311.0),
}

CONTROL_FORMULA = (
    'IF(COUNT(B5:C10)<12,"Pending inputs",'
    'IF(AND(B13=0,C13=0,B15=0,C15=0),"Ties to filing","Review difference"))'
)

CONTENT_TYPES_HEAD = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" '
    'ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-'
    'officedocument.spreadsheetml.sheet.main+xml"/>'
    '<Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-'
    'officedocument.spreadsheetml.sharedStrings+xml"/>'
)

MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
DOC_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"


def text(value):
    return {"kind": "text", "value": value}


def number(value):
    return {"kind": "number", "value": value}


def formula(expression, cached, cached_kind="number"):
    return {"kind": "formula", "formula": expression, "cached": cached,
            "cached_kind": cached_kind}


def shared_master(expression, cached, si, ref):
    return {"kind": "shared_master", "formula": expression, "cached": cached, "si": si,
            "ref": ref}


def shared_follower(cached, si):
    return {"kind": "shared_follower", "cached": cached, "si": si}


def formula_without_cache(expression):
    return {"kind": "formula_no_cache", "formula": expression}


def error_cell(value):
    return {"kind": "error", "value": value}


def _coord_parts(coord):
    letters = "".join(character for character in coord if character.isalpha())
    digits = int("".join(character for character in coord if character.isdigit()))
    return letters, digits


def _sheet_xml(cells, strings):
    rows = {}
    for coord, spec in cells.items():
        rows.setdefault(_coord_parts(coord)[1], []).append((coord, spec))

    chunks = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        f'<worksheet xmlns="{MAIN_NS}"><sheetData>',
    ]
    for row_number in sorted(rows):
        chunks.append(f'<row r="{row_number}">')
        for coord, spec in sorted(rows[row_number],
                                  key=lambda item: _coord_parts(item[0])[0]):
            kind = spec["kind"]
            if kind == "text":
                if spec["value"] not in strings:
                    strings.append(spec["value"])
                chunks.append(
                    f'<c r="{coord}" t="s"><v>{strings.index(spec["value"])}</v></c>'
                )
            elif kind == "number":
                chunks.append(f'<c r="{coord}"><v>{spec["value"]!r}</v></c>')
            elif kind == "formula":
                cached = spec["cached"]
                if spec["cached_kind"] == "string":
                    chunks.append(
                        f'<c r="{coord}" t="str"><f>{escape(spec["formula"])}</f>'
                        f"<v>{escape(str(cached))}</v></c>"
                    )
                else:
                    chunks.append(
                        f'<c r="{coord}"><f>{escape(spec["formula"])}</f><v>{cached!r}</v></c>'
                    )
            elif kind == "formula_no_cache":
                chunks.append(f'<c r="{coord}"><f>{escape(spec["formula"])}</f></c>')
            elif kind == "shared_master":
                chunks.append(
                    f'<c r="{coord}"><f t="shared" ref="{spec["ref"]}" si="{spec["si"]}">'
                    f'{escape(spec["formula"])}</f><v>{spec["cached"]!r}</v></c>'
                )
            elif kind == "shared_follower":
                chunks.append(
                    f'<c r="{coord}"><f t="shared" si="{spec["si"]}"/>'
                    f'<v>{spec["cached"]!r}</v></c>'
                )
            elif kind == "error":
                chunks.append(f'<c r="{coord}" t="e"><v>{escape(spec["value"])}</v></c>')
            else:  # pragma: no cover - guards test authoring mistakes
                raise AssertionError(f"Unknown cell kind {kind}")
        chunks.append("</row>")
    chunks.append("</sheetData></worksheet>")
    return "".join(chunks)


def build_xlsx(path, sheets, include_macro=False):
    """sheets: ordered list of (sheet_name, {coord: spec})."""
    strings = []
    rendered = [(name, _sheet_xml(cells, strings)) for name, cells in sheets]

    content_types = [CONTENT_TYPES_HEAD]
    for index in range(1, len(rendered) + 1):
        content_types.append(
            f'<Override PartName="/xl/worksheets/sheet{index}.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.'
            'worksheet+xml"/>'
        )
    content_types.append("</Types>")

    sheet_entries = "".join(
        f'<sheet name="{escape(name)}" sheetId="{index}" r:id="rId{index}"/>'
        for index, (name, _xml) in enumerate(rendered, start=1)
    )
    workbook_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<workbook xmlns="{MAIN_NS}" xmlns:r="{DOC_REL_NS}">'
        f"<sheets>{sheet_entries}</sheets></workbook>"
    )
    relationship_entries = "".join(
        f'<Relationship Id="rId{index}" Type="{DOC_REL_NS}/worksheet" '
        f'Target="worksheets/sheet{index}.xml"/>'
        for index in range(1, len(rendered) + 1)
    )
    relationship_entries += (
        f'<Relationship Id="rId{len(rendered) + 1}" Type="{DOC_REL_NS}/sharedStrings" '
        'Target="sharedStrings.xml"/>'
    )
    workbook_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<Relationships xmlns="{PKG_REL_NS}">{relationship_entries}</Relationships>'
    )
    root_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<Relationships xmlns="{PKG_REL_NS}">'
        f'<Relationship Id="rId1" Type="{DOC_REL_NS}/officeDocument" Target="xl/workbook.xml"/>'
        "</Relationships>"
    )
    shared_strings = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<sst xmlns="{MAIN_NS}" count="{len(strings)}" uniqueCount="{len(strings)}">'
        + "".join(f"<si><t>{escape(value)}</t></si>" for value in strings)
        + "</sst>"
    )

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "".join(content_types))
        archive.writestr("_rels/.rels", root_rels)
        archive.writestr("xl/workbook.xml", workbook_xml)
        archive.writestr("xl/_rels/workbook.xml.rels", workbook_rels)
        archive.writestr("xl/sharedStrings.xml", shared_strings)
        for index, (_name, sheet_xml) in enumerate(rendered, start=1):
            archive.writestr(f"xl/worksheets/sheet{index}.xml", sheet_xml)
        if include_macro:
            archive.writestr("xl/vbaProject.bin", b"\x00not executed by this validator")
    return path


def completed_statement_cells(use_shared_fill=False):
    cells = {}
    for row, (label, year_2024, year_2023) in FACTS.items():
        cells[f"A{row}"] = text(label)
        cells[f"B{row}"] = number(year_2024)
        cells[f"C{row}"] = number(year_2023)

    changes = {row: FACTS[row][1] - FACTS[row][2] for row in FACTS}
    if use_shared_fill:
        cells["D5"] = shared_master("B5-C5", changes[5], si=0, ref="D5:D10")
        for row in range(6, 11):
            cells[f"D{row}"] = shared_follower(changes[row], si=0)
    else:
        for row in FACTS:
            cells[f"D{row}"] = formula(f"B{row}-C{row}", changes[row])
    for row in FACTS:
        cells[f"E{row}"] = formula(
            f'IF(C{row}=0,"Not meaningful",D{row}/C{row})',
            changes[row] / FACTS[row][2],
        )

    revenue_2024, revenue_2023 = FACTS[5][1], FACTS[5][2]
    gross_2024 = FACTS[5][1] - FACTS[6][1]
    gross_2023 = FACTS[5][2] - FACTS[6][2]
    operating_2024 = gross_2024 - FACTS[8][1] - FACTS[9][1]
    operating_2023 = gross_2023 - FACTS[8][2] - FACTS[9][2]

    cells["A12"] = text("Recomputed gross profit")
    cells["B12"] = formula("B5-B6", gross_2024)
    cells["C12"] = formula("C5-C6", gross_2023)
    cells["A13"] = text("Gross profit difference")
    cells["B13"] = formula("B12-B7", gross_2024 - FACTS[7][1])
    cells["C13"] = formula("C12-C7", gross_2023 - FACTS[7][2])
    cells["A14"] = text("Recomputed operating income")
    cells["B14"] = formula("B12-B8-B9", operating_2024)
    cells["C14"] = formula("C12-C8-C9", operating_2023)
    cells["A15"] = text("Operating income difference")
    cells["B15"] = formula("B14-B10", operating_2024 - FACTS[10][1])
    cells["C15"] = formula("C14-C10", operating_2023 - FACTS[10][2])
    cells["A17"] = text("Gross margin")
    cells["B17"] = formula("B12/B5", gross_2024 / revenue_2024)
    cells["C17"] = formula("C12/C5", gross_2023 / revenue_2023)
    cells["A18"] = text("Operating margin")
    cells["B18"] = formula("B14/B5", operating_2024 / revenue_2024)
    cells["C18"] = formula("C14/C5", operating_2023 / revenue_2023)
    cells["A20"] = text("Control")
    cells["B20"] = formula(CONTROL_FORMULA, "Ties to filing", cached_kind="string")
    cells["A22"] = text("Status: Draft populated from filing; pending human review.")
    return cells


STALE_STATUS_NOTE = (
    "Status: Pending inputs. Workbook prepared blank; no amounts or formulas entered yet."
)


def review_sheet_cells(shifted=False, missing_disposition=False):
    """Review sheet with the single review row the recorded session actually fills in."""
    cells = {"A4": text("Issue"), "B4": text("Evidence"), "C4": text("Disposition"),
             "D4": text("Reviewer status")}
    row = ["Source scope",
           "FY2024 10-K, Item 8, p. 62; USD millions",
           "Company statement used; investee summary excluded",
           "Pending human review"]
    columns = ["B", "C", "D", "E"] if shifted else ["A", "B", "C", "D"]
    for column, value in zip(columns, row):
        cells[f"{column}5"] = text(value)
    if missing_disposition:
        cells.pop("C5", None)
    return cells


def supporting_sheets(review_cells=None):
    return [
        ("Raw paste", {"A1": text("Raw paste"), "A5": text("Year Ended December 31,"),
                       "B5": text("2024"), "C5": text("2023")}),
        ("Sources", {
            "A5": text("Accession number"),
            "B5": text(validate_recording.ACCESSION),
            "A6": text("Primary document URL"),
            "B6": text(validate_recording.PRIMARY_URL),
        }),
        ("Review", review_sheet_cells() if review_cells is None else review_cells),
        ("Guide", {"A1": text("Guide")}),
    ]


def workbook_with(statement_cells, include_macro=False, review_cells=None):
    return [("Statement", statement_cells)] + supporting_sheets(review_cells), include_macro


class ValidatorHelperTests(unittest.TestCase):
    def test_shift_formula_translates_only_relative_references(self):
        self.assertEqual(validate_recording.shift_formula("B5-C5", 1, 0), "B6-C6")
        self.assertEqual(validate_recording.shift_formula("B$5-C5", 3, 0), "B$5-C8")
        self.assertEqual(validate_recording.shift_formula("$B5-C5", 0, 2), "$B5-E5")

    def test_shift_formula_leaves_string_literals_alone(self):
        self.assertEqual(
            validate_recording.shift_formula('IF(C5=0,"A1 not B2",D5/C5)', 1, 0),
            'IF(C6=0,"A1 not B2",D6/C6)',
        )

    def test_formula_references_reads_ranges_and_ignores_literals(self):
        references = validate_recording.formula_references(CONTROL_FORMULA)
        self.assertLessEqual({"B5:C10", "B13", "C13", "B15", "C15"}, references)
        self.assertNotIn("A1", validate_recording.formula_references('IF(A2=0,"A1",1)'))


class ValidatorWorkbookTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)

    def run_validator(self, statement_cells, include_macro=False, name="final.xlsx"):
        sheets, macro = workbook_with(statement_cells, include_macro)
        path = build_xlsx(self.directory / name, sheets, include_macro=macro)
        with contextlib.redirect_stdout(io.StringIO()):
            return validate_recording.main(["--workbook", str(path), "--json"])

    def report_for(self, statement_cells, review_cells=None):
        sheets, _macro = workbook_with(statement_cells, review_cells=review_cells)
        path = build_xlsx(self.directory / "final.xlsx", sheets)
        loaded, order = validate_recording.load_workbook(path)
        report = validate_recording.Report()
        validate_recording.check_workbook(loaded, order, report)
        return report

    def failed_ids(self, statement_cells, review_cells=None):
        return {check["id"] for check in self.report_for(statement_cells, review_cells).failed}

    def test_completed_workbook_passes(self):
        report = self.report_for(completed_statement_cells())
        self.assertEqual(report.failed, [], f"unexpected failures: {report.failed}")
        self.assertEqual(self.run_validator(completed_statement_cells()), 0)

    def test_filled_down_shared_formulas_are_expanded_not_rejected(self):
        report = self.report_for(completed_statement_cells(use_shared_fill=True))
        self.assertEqual(report.failed, [], f"unexpected failures: {report.failed}")

    def test_missing_cached_value_is_rejected_explicitly(self):
        cells = completed_statement_cells()
        cells["D5"] = formula_without_cache("B5-C5")
        failures = self.report_for(cells).failed
        identifiers = {check["id"] for check in failures}
        self.assertIn("cached-value:D5", identifiers)
        detail = next(check["detail"] for check in failures if check["id"] == "cached-value:D5")
        self.assertIn("no cached value", detail)
        self.assertIn("will not recompute", detail)

    def test_error_cell_anywhere_is_rejected(self):
        cells = completed_statement_cells()
        cells["E5"] = error_cell("#DIV/0!")
        self.assertIn("no-error-cells", self.failed_ids(cells))

    def test_typed_number_instead_of_formula_is_rejected(self):
        cells = completed_statement_cells()
        cells["B12"] = number(28737.0)
        self.assertIn("formula:B12", self.failed_ids(cells))

    def test_formula_in_an_input_cell_is_rejected(self):
        cells = completed_statement_cells()
        cells["B5"] = formula("B12+B6", 47061.0)
        self.assertIn("input:B5", self.failed_ids(cells))

    def test_wrong_reported_amount_is_rejected(self):
        cells = completed_statement_cells()
        cells["B5"] = number(47060.0)
        self.assertIn("input:B5", self.failed_ids(cells))

    def test_equity_method_investee_amounts_are_rejected(self):
        cells = completed_statement_cells()
        cells["B5"] = number(99043.0)
        cells["C5"] = number(93862.0)
        failures = self.failed_ids(cells)
        self.assertIn("input:B5", failures)
        self.assertIn("input:C5", failures)

    def test_cached_value_disagreeing_with_recomputation_is_rejected(self):
        cells = completed_statement_cells()
        cells["B12"] = formula("B5-B6", 28738.0)
        self.assertIn("cached-value:B12", self.failed_ids(cells))

    def test_blanket_error_trap_is_rejected(self):
        cells = completed_statement_cells()
        cells["E5"] = formula("IFERROR(D5/C5,\"Not meaningful\")", 1307.0 / 45754.0)
        self.assertIn("no-blanket-error-trap:E5", self.failed_ids(cells))

    def test_control_must_reference_inputs_and_differences(self):
        cells = completed_statement_cells()
        cells["B20"] = formula('IF(B13=0,"Ties to filing","Review difference")',
                               "Ties to filing", cached_kind="string")
        self.assertIn("formula-refs:B20", self.failed_ids(cells))

    def test_control_cached_status_must_say_it_ties(self):
        cells = completed_statement_cells()
        cells["B20"] = formula(CONTROL_FORMULA, "Review difference", cached_kind="string")
        self.assertIn("cached-value:B20", self.failed_ids(cells))

    def test_unpasted_source_table_is_reported(self):
        sheets = [("Statement", completed_statement_cells()),
                  ("Raw paste", {"A1": text("Raw paste")})] + supporting_sheets()[1:]
        path = build_xlsx(self.directory / "final.xlsx", sheets)
        loaded, order = validate_recording.load_workbook(path)
        report = validate_recording.Report()
        validate_recording.check_workbook(loaded, order, report)
        self.assertIn("raw-paste-present", {check["id"] for check in report.failed})

    def test_macro_workbook_is_rejected_without_inspection(self):
        self.assertEqual(self.run_validator(completed_statement_cells(), include_macro=True), 2)

    def test_stale_blank_template_status_note_is_rejected(self):
        cells = completed_statement_cells()
        cells["A22"] = text(STALE_STATUS_NOTE)
        failures = self.report_for(cells).failed
        identifiers = {check["id"] for check in failures}
        self.assertIn("status-note-updated", identifiers)
        detail = next(c["detail"] for c in failures if c["id"] == "status-note-updated")
        self.assertIn("blank preparation template", detail)

    def test_missing_status_note_is_rejected(self):
        cells = completed_statement_cells()
        cells.pop("A22")
        self.assertIn("status-note-updated", self.failed_ids(cells))

    def test_shifted_review_row_is_rejected(self):
        failures = self.failed_ids(completed_statement_cells(),
                                   review_cells=review_sheet_cells(shifted=True))
        self.assertIn("review-row-alignment", failures)
        self.assertIn("review-row-complete", failures)

    def test_partially_filled_review_row_is_rejected(self):
        failures = self.failed_ids(completed_statement_cells(),
                                   review_cells=review_sheet_cells(missing_disposition=True))
        self.assertIn("review-row-complete", failures)
        self.assertNotIn("review-row-alignment", failures)

    def test_missing_file_reports_an_io_error(self):
        with contextlib.redirect_stdout(io.StringIO()):
            exit_code = validate_recording.main(
                ["--workbook", str(self.directory / "absent.xlsx"), "--json"]
            )
        self.assertEqual(exit_code, 2)


if __name__ == "__main__":
    unittest.main()
