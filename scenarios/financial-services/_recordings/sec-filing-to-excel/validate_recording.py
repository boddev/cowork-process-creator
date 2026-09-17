#!/usr/bin/env python3
"""Standard-library validator for the SAVED final workbook of the SEC-filing-to-Excel pilot.

Reads a .xlsx produced by a real Excel session and checks that the work actually happened:

  * the six reported amounts are present in Statement!B5:C10 and match the source-checked
    reference values,
  * the change, recomputation, margin and control cells contain real formulas that reference
    the expected precedent cells,
  * every one of those formula cells carries a cached value that Excel itself wrote,
  * those cached values agree with an independent recomputation performed here in Python,
  * no cell anywhere in the workbook is an Excel error value.

Design notes:

  * Standard library only: zipfile and xml.etree.ElementTree. openpyxl is NOT imported, so the
    ordinary repository test path gains no third-party dependency.
  * Strictly read-only. The archive is opened for reading, nothing is written back, and no macro
    or embedded code is executed or interpreted. A workbook containing a VBA project is rejected
    rather than inspected.
  * A missing cached value is reported as an explicit failure. This validator never recomputes a
    blank cell and then reports it as though Excel had calculated it.
  * Excel writes filled-down formulas as shared formulas, where only the first cell carries the
    formula text. Those are expanded here by translating the master formula, so a legitimate
    fill-down is not mistaken for a missing formula.

Usage:
    python validate_recording.py --workbook final.xlsx
    python validate_recording.py --workbook final.xlsx --json

Exit codes: 0 all checks passed, 1 at least one check failed, 2 the file could not be read.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET
import zipfile

NS_MAIN = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
NS_PKG_REL = "{http://schemas.openxmlformats.org/package/2006/relationships}"
NS_DOC_REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"

ERROR_VALUES = {"#REF!", "#DIV/0!", "#VALUE!", "#N/A", "#NAME?", "#NULL!", "#NUM!", "#GETTING_DATA"}

REQUIRED_SHEETS = ["Statement", "Raw paste", "Sources", "Review", "Guide"]

# Source-checked reference values, USD millions, from the FY2024 Form 10-K consolidated
# statements of income (accession 0000021344-25-000011, Item 8, printed page 62).
EXPECTED_FACTS = [
    (5, "Net Operating Revenues", 47061.0, 45754.0),
    (6, "Cost of goods sold", 18324.0, 18520.0),
    (7, "Gross Profit", 28737.0, 27234.0),
    (8, "Selling, general and administrative expenses", 14582.0, 13972.0),
    (9, "Other operating charges", 4163.0, 1951.0),
    (10, "Operating Income", 9992.0, 11311.0),
]

CONTROL_CELL = "B20"
CONTROL_EXPECTED = "Ties to filing"

STATUS_CELL = "A22"
# Phrases used by the blank preparation template. If any survives into the saved workbook, the
# status note was never updated after the amounts were entered.
STALE_STATUS_MARKERS = (
    "pending inputs",
    "prepared blank",
    "no amounts or formulas entered yet",
)

REVIEW_ROW = 5
REVIEW_COLUMNS = ("A", "B", "C", "D")
REVIEW_OVERFLOW_COLUMN = "E"

ACCESSION = "0000021344-25-000011"
PRIMARY_URL = "https://www.sec.gov/Archives/edgar/data/21344/000002134425000011/ko-20241231.htm"

RANGE_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_$!:])(\$?[A-Za-z]{1,3}\$?[0-9]{1,7}):(\$?[A-Za-z]{1,3}\$?[0-9]{1,7})"
    r"(?![A-Za-z0-9_])"
)
SINGLE_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_$!:])(\$?)([A-Za-z]{1,3})(\$?)([0-9]{1,7})(?![A-Za-z0-9_(:])"
)
LITERAL_PATTERN = re.compile(r'"(?:[^"]|"")*"')


def column_index(letters: str) -> int:
    value = 0
    for char in letters.upper():
        value = value * 26 + (ord(char) - 64)
    return value


def column_letters(index: int) -> str:
    letters = ""
    while index > 0:
        index, remainder = divmod(index - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


def split_coord(coord: str):
    match = re.fullmatch(r"([A-Za-z]{1,3})([0-9]{1,7})", coord)
    if not match:
        raise ValueError(f"Bad cell reference: {coord}")
    return column_index(match.group(1)), int(match.group(2))


def mask_literals(formula: str):
    """Replace string literals with same-length blanks so references are not found inside them."""
    return LITERAL_PATTERN.sub(lambda m: " " * len(m.group(0)), formula)


def shift_formula(formula: str, row_delta: int, column_delta: int) -> str:
    """Translate relative references of a shared-formula master to a follower cell."""
    pieces = []
    position = 0
    for literal in LITERAL_PATTERN.finditer(formula):
        pieces.append((formula[position:literal.start()], True))
        pieces.append((literal.group(0), False))
        position = literal.end()
    pieces.append((formula[position:], True))

    def replace(match):
        column_absolute, letters, row_absolute, digits = match.groups()
        new_letters = letters
        new_digits = digits
        if not column_absolute:
            index = column_index(letters) + column_delta
            if index < 1:
                return match.group(0)
            new_letters = column_letters(index)
        if not row_absolute:
            row = int(digits) + row_delta
            if row < 1:
                return match.group(0)
            new_digits = str(row)
        return f"{column_absolute}{new_letters}{row_absolute}{new_digits}"

    return "".join(
        SINGLE_PATTERN.sub(replace, text) if translatable else text
        for text, translatable in pieces
    )


def formula_references(formula: str):
    """Return the set of normalised cell and range references used by a formula."""
    masked = mask_literals(formula)
    references = set()
    for match in RANGE_PATTERN.finditer(masked):
        start = match.group(1).replace("$", "").upper()
        end = match.group(2).replace("$", "").upper()
        references.add(f"{start}:{end}")
    without_ranges = RANGE_PATTERN.sub(lambda m: " " * len(m.group(0)), masked)
    for match in SINGLE_PATTERN.finditer(without_ranges):
        references.add(f"{match.group(2)}{match.group(4)}".upper())
    return references


class Cell:
    __slots__ = ("coord", "cell_type", "formula", "value", "has_value")

    def __init__(self, coord, cell_type, formula, value, has_value):
        self.coord = coord
        self.cell_type = cell_type
        self.formula = formula
        self.value = value
        self.has_value = has_value

    @property
    def is_empty(self):
        return self.formula is None and not self.has_value


class WorkbookError(Exception):
    pass


def read_shared_strings(archive):
    try:
        data = archive.read("xl/sharedStrings.xml")
    except KeyError:
        return []
    root = ET.fromstring(data)
    strings = []
    for item in root.findall(f"{NS_MAIN}si"):
        strings.append("".join(node.text or "" for node in item.iter(f"{NS_MAIN}t")))
    return strings


def resolve_sheet_paths(archive):
    workbook = ET.fromstring(archive.read("xl/workbook.xml"))
    relationships = {}
    for relationship in ET.fromstring(archive.read("xl/_rels/workbook.xml.rels")):
        relationships[relationship.get("Id")] = relationship.get("Target")

    names = archive.namelist()
    sheets = {}
    order = []
    for sheet in workbook.iter(f"{NS_MAIN}sheet"):
        name = sheet.get("name")
        target = relationships.get(sheet.get(f"{NS_DOC_REL}id"))
        if target is None:
            continue
        target = target.lstrip("/")
        candidates = [target, f"xl/{target}", target.replace("xl/", "", 1)]
        path = next((candidate for candidate in candidates if candidate in names), None)
        if path is None:
            continue
        sheets[name] = path
        order.append(name)
    return sheets, order


def parse_sheet(archive, path, shared_strings):
    root = ET.fromstring(archive.read(path))
    cells = {}
    masters = {}
    pending = []

    for element in root.iter(f"{NS_MAIN}c"):
        coord = element.get("r")
        if not coord:
            continue
        cell_type = element.get("t") or "n"
        formula_node = element.find(f"{NS_MAIN}f")
        value_node = element.find(f"{NS_MAIN}v")
        inline_node = element.find(f"{NS_MAIN}is")

        formula = None
        if formula_node is not None:
            formula = (formula_node.text or "").strip() or None
            if formula_node.get("t") == "shared":
                index = formula_node.get("si")
                if formula is not None:
                    masters[index] = (coord, formula)
                else:
                    pending.append((coord, index))

        has_value = value_node is not None and value_node.text is not None
        value = None
        if cell_type == "inlineStr":
            texts = [] if inline_node is None else [
                node.text or "" for node in inline_node.iter(f"{NS_MAIN}t")
            ]
            value = "".join(texts)
            has_value = inline_node is not None
        elif has_value:
            raw = value_node.text
            if cell_type == "s":
                try:
                    value = shared_strings[int(raw)]
                except (ValueError, IndexError):
                    value = ""
            elif cell_type in ("str", "e"):
                value = raw
            elif cell_type == "b":
                value = raw not in ("0", "false", "FALSE")
            else:
                try:
                    value = float(raw)
                except ValueError:
                    value = raw

        cells[coord] = Cell(coord, cell_type, formula, value, has_value)

    for coord, index in pending:
        master = masters.get(index)
        if master is None:
            continue
        master_coord, master_formula = master
        master_column, master_row = split_coord(master_coord)
        column, row = split_coord(coord)
        cells[coord].formula = shift_formula(
            master_formula, row - master_row, column - master_column
        )
    return cells


def load_workbook(path: Path):
    if not path.is_file():
        raise WorkbookError(f"Workbook not found: {path}")
    try:
        archive = zipfile.ZipFile(path)
    except zipfile.BadZipFile as error:
        raise WorkbookError(f"Not a readable .xlsx package: {path} ({error})") from error
    with archive:
        names = archive.namelist()
        macros = [name for name in names if name.lower().endswith("vbaproject.bin")]
        if macros:
            raise WorkbookError(
                "Workbook contains a VBA project and is rejected without inspection: "
                + ", ".join(macros)
            )
        shared_strings = read_shared_strings(archive)
        sheet_paths, order = resolve_sheet_paths(archive)
        sheets = {
            name: parse_sheet(archive, path_in_zip, shared_strings)
            for name, path_in_zip in sheet_paths.items()
        }
    return sheets, order


class Report:
    def __init__(self):
        self.checks = []

    def add(self, identifier, passed, detail):
        self.checks.append({"id": identifier, "status": "pass" if passed else "fail",
                            "detail": detail})
        return passed

    @property
    def failed(self):
        return [check for check in self.checks if check["status"] == "fail"]

    def as_dict(self, workbook):
        return {
            "schema_version": 1,
            "validator": "_recordings/sec-filing-to-excel/validate_recording.py",
            "workbook": workbook,
            "status": "fail" if self.failed else "pass",
            "checks_run": len(self.checks),
            "checks_failed": len(self.failed),
            "checks": self.checks,
            "claims": {
                "read_only": True,
                "macros_executed": False,
                "values_recomputed_into_workbook": False,
                "native_execution_evidence": False,
            },
        }


def expected_model():
    """Independently recompute everything the finished workbook should contain."""
    facts = {row: (y2024, y2023) for row, _label, y2024, y2023 in EXPECTED_FACTS}
    revenue_2024, revenue_2023 = facts[5]
    cogs_2024, cogs_2023 = facts[6]
    gross_2024, gross_2023 = facts[7]
    sga_2024, sga_2023 = facts[8]
    other_2024, other_2023 = facts[9]
    operating_2024, operating_2023 = facts[10]

    recomputed_gross_2024 = revenue_2024 - cogs_2024
    recomputed_gross_2023 = revenue_2023 - cogs_2023
    recomputed_operating_2024 = recomputed_gross_2024 - sga_2024 - other_2024
    recomputed_operating_2023 = recomputed_gross_2023 - sga_2023 - other_2023

    values = {
        "B12": recomputed_gross_2024,
        "C12": recomputed_gross_2023,
        "B13": recomputed_gross_2024 - gross_2024,
        "C13": recomputed_gross_2023 - gross_2023,
        "B14": recomputed_operating_2024,
        "C14": recomputed_operating_2023,
        "B15": recomputed_operating_2024 - operating_2024,
        "C15": recomputed_operating_2023 - operating_2023,
        "B17": recomputed_gross_2024 / revenue_2024,
        "C17": recomputed_gross_2023 / revenue_2023,
        "B18": recomputed_operating_2024 / revenue_2024,
        "C18": recomputed_operating_2023 / revenue_2023,
    }
    references = {
        "B12": {"B5", "B6"}, "C12": {"C5", "C6"},
        "B13": {"B12", "B7"}, "C13": {"C12", "C7"},
        "B14": {"B12", "B8", "B9"}, "C14": {"C12", "C8", "C9"},
        "B15": {"B14", "B10"}, "C15": {"C14", "C10"},
        "B17": {"B12", "B5"}, "C17": {"C12", "C5"},
        "B18": {"B14", "B5"}, "C18": {"C14", "C5"},
    }
    for row, _label, y2024, y2023 in EXPECTED_FACTS:
        values[f"D{row}"] = y2024 - y2023
        values[f"E{row}"] = (y2024 - y2023) / y2023
        references[f"D{row}"] = {f"B{row}", f"C{row}"}
    return values, references


def close_enough(actual, expected):
    return math.isclose(actual, expected, rel_tol=1e-9, abs_tol=1e-9)


def check_workbook(sheets, order, report: Report):
    for name in REQUIRED_SHEETS:
        report.add(f"sheet-present:{name}", name in sheets,
                   f"Sheet {name!r} present" if name in sheets
                   else f"Sheet {name!r} is missing; found {sorted(sheets)}")
    if "Statement" not in sheets:
        return
    report.add("active-sheet-first", bool(order) and order[0] == "Statement",
               f"First sheet is {order[0]!r}" if order else "No sheets found")

    statement = sheets["Statement"]
    values, references = expected_model()

    errors = []
    for sheet_name, cells in sheets.items():
        for coord, cell in cells.items():
            if cell.cell_type == "e" or (isinstance(cell.value, str)
                                         and cell.value in ERROR_VALUES):
                errors.append(f"{sheet_name}!{coord}={cell.value}")
    report.add("no-error-cells", not errors,
               "No Excel error values anywhere in the workbook" if not errors
               else f"Excel error values present: {', '.join(sorted(errors)[:12])}")

    for row, label, year_2024, year_2023 in EXPECTED_FACTS:
        actual_label = statement.get(f"A{row}")
        text = "" if actual_label is None or actual_label.value is None else str(actual_label.value)
        matched = " ".join(text.split()).casefold() == label.casefold()
        report.add(f"label:A{row}", matched,
                   f"A{row} is {label!r}" if matched
                   else f"A{row} should read {label!r} but reads {text!r}")
        for coord, expected in ((f"B{row}", year_2024), (f"C{row}", year_2023)):
            cell = statement.get(coord)
            if cell is None or not cell.has_value:
                report.add(f"input:{coord}", False,
                           f"{coord} is empty; the reported amount was never entered")
                continue
            if cell.formula is not None:
                report.add(f"input:{coord}", False,
                           f"{coord} holds a formula; reported amounts must be entered as values")
                continue
            if not isinstance(cell.value, float):
                report.add(f"input:{coord}", False,
                           f"{coord} is not numeric (found {cell.value!r})")
                continue
            report.add(f"input:{coord}", close_enough(cell.value, expected),
                       f"{coord} = {cell.value:,.0f} as reported" if close_enough(cell.value, expected)
                       else f"{coord} = {cell.value!r} but the filing reports {expected:,.0f}")

    for coord in sorted(values, key=lambda item: (split_coord(item)[1], item)):
        cell = statement.get(coord)
        if cell is None or cell.formula is None:
            report.add(f"formula:{coord}", False,
                       f"{coord} contains no formula; it must be entered as a formula, "
                       f"not a typed number")
            continue
        found = formula_references(cell.formula)
        required = references.get(coord, set())
        if coord.startswith("E"):
            row = split_coord(coord)[1]
            guarded = f"C{row}" in found and (f"D{row}" in found or f"B{row}" in found)
            report.add(f"formula-refs:{coord}", guarded,
                       f"{coord} guards on C{row} and uses the change"
                       if guarded else
                       f"{coord} formula {cell.formula!r} does not both guard on C{row} "
                       f"and reference the change")
        else:
            report.add(f"formula-refs:{coord}", required <= found,
                       f"{coord} references {sorted(required)}" if required <= found
                       else f"{coord} formula {cell.formula!r} references {sorted(found)}, "
                            f"missing {sorted(required - found)}")
        if not cell.has_value:
            report.add(f"cached-value:{coord}", False,
                       f"{coord} has a formula but no cached value. Excel never calculated and "
                       f"saved it; this validator will not recompute it on Excel's behalf")
            continue
        if not isinstance(cell.value, float):
            report.add(f"cached-value:{coord}", False,
                       f"{coord} cached value is {cell.value!r}, which is not a number")
            continue
        expected = values[coord]
        report.add(f"cached-value:{coord}", close_enough(cell.value, expected),
                   f"{coord} cached {cell.value:,.6g} agrees with the independent recomputation"
                   if close_enough(cell.value, expected)
                   else f"{coord} cached {cell.value!r} but the independent recomputation gives "
                        f"{expected!r}")

    # Guarded percent-change formulas must not hide unexpected errors behind a blanket IFERROR.
    for row, _label, _y24, _y23 in EXPECTED_FACTS:
        cell = statement.get(f"E{row}")
        if cell is None or cell.formula is None:
            continue
        upper = cell.formula.upper()
        swallows = "IFERROR" in upper or "ISERROR" in upper or "IFNA" in upper
        report.add(f"no-blanket-error-trap:E{row}", not swallows,
                   f"E{row} guards the zero denominator explicitly" if not swallows
                   else f"E{row} uses a blanket error trap ({cell.formula!r}); guard the zero "
                        f"denominator instead of swallowing every error")

    control = statement.get(CONTROL_CELL)
    if control is None or control.formula is None:
        report.add(f"formula:{CONTROL_CELL}", False,
                   f"{CONTROL_CELL} contains no control formula")
    else:
        found = formula_references(control.formula)
        required = {"B5:C10", "B13", "C13", "B15", "C15"}
        report.add(f"formula-refs:{CONTROL_CELL}", required <= found,
                   f"{CONTROL_CELL} references {sorted(required)}" if required <= found
                   else f"{CONTROL_CELL} formula {control.formula!r} is missing "
                        f"{sorted(required - found)}")
        report.add("control-uses-count", "COUNT(" in control.formula.upper(),
                   "Control counts the entered amounts before reporting a tie"
                   if "COUNT(" in control.formula.upper()
                   else f"Control formula {control.formula!r} does not COUNT the input range")
        if not control.has_value:
            report.add(f"cached-value:{CONTROL_CELL}", False,
                       f"{CONTROL_CELL} has a formula but no cached value; Excel never saved a "
                       f"calculated result")
        else:
            actual = str(control.value)
            report.add(f"cached-value:{CONTROL_CELL}", actual == CONTROL_EXPECTED,
                       f"{CONTROL_CELL} reads {actual!r}" if actual == CONTROL_EXPECTED
                       else f"{CONTROL_CELL} reads {actual!r}; the source-checked amounts should "
                            f"produce {CONTROL_EXPECTED!r}")

    status = statement.get(STATUS_CELL)
    status_text = "" if status is None or status.value is None else str(status.value)
    if not status_text.strip():
        report.add("status-note-updated", False,
                   f"Statement!{STATUS_CELL} is empty; the status note should say what state the "
                   f"workbook is actually in")
    else:
        stale = [marker for marker in STALE_STATUS_MARKERS if marker in status_text.casefold()]
        report.add("status-note-updated", not stale,
                   f"Statement!{STATUS_CELL} reflects the populated workbook"
                   if not stale else
                   f"Statement!{STATUS_CELL} still carries the blank preparation template's "
                   f"wording ({', '.join(repr(item) for item in stale)}): {status_text!r}. The "
                   f"amounts were entered but the status note was never updated")

    if "Review" in sheets:
        review = sheets["Review"]

        def review_text(column):
            cell = review.get(f"{column}{REVIEW_ROW}")
            if cell is None or cell.value is None:
                return ""
            return str(cell.value).strip()

        filled = [column for column in REVIEW_COLUMNS if review_text(column)]
        report.add("review-row-complete", len(filled) == len(REVIEW_COLUMNS),
                   f"Review row {REVIEW_ROW} fills {''.join(REVIEW_COLUMNS)}"
                   if len(filled) == len(REVIEW_COLUMNS) else
                   f"Review row {REVIEW_ROW} should fill "
                   f"{REVIEW_COLUMNS[0]}{REVIEW_ROW}:{REVIEW_COLUMNS[-1]}{REVIEW_ROW} but only "
                   f"{filled or 'no'} column(s) carry text")

        overflow = review_text(REVIEW_OVERFLOW_COLUMN)
        report.add("review-row-alignment", not overflow,
                   f"Review row {REVIEW_ROW} stops at column {REVIEW_COLUMNS[-1]} as the headers "
                   f"expect" if not overflow else
                   f"Review!{REVIEW_OVERFLOW_COLUMN}{REVIEW_ROW} holds {overflow!r}, one column "
                   f"past the last header. The review row is shifted and no longer lines up with "
                   f"{'|'.join(REVIEW_COLUMNS)}")

    if "Raw paste" in sheets:
        pasted = [
            coord for coord, cell in sheets["Raw paste"].items()
            if split_coord(coord)[1] >= 5 and (cell.has_value or cell.formula)
        ]
        report.add("raw-paste-present", bool(pasted),
                   f"Raw paste has {len(pasted)} populated cells from row 5" if pasted
                   else "Raw paste is empty from row 5; the original table was never pasted")

    if "Sources" in sheets:
        blob = " ".join(
            str(cell.value) for cell in sheets["Sources"].values() if cell.value is not None
        )
        report.add("sources-accession", ACCESSION in blob,
                   f"Sources cites accession {ACCESSION}" if ACCESSION in blob
                   else f"Sources does not cite accession {ACCESSION}")
        report.add("sources-url", PRIMARY_URL in blob,
                   "Sources cites the primary document URL" if PRIMARY_URL in blob
                   else "Sources does not cite the primary document URL")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Read-only check of the saved recording workbook. Executes nothing and "
                    "modifies nothing."
    )
    parser.add_argument("--workbook", required=True, help="Path of the saved .xlsx to check.")
    parser.add_argument("--json", action="store_true", help="Emit the report as JSON.")
    arguments = parser.parse_args(argv)

    path = Path(arguments.workbook)
    try:
        sheets, order = load_workbook(path)
    except WorkbookError as error:
        if arguments.json:
            print(json.dumps({"schema_version": 1, "status": "error", "detail": str(error)},
                             indent=2))
        else:
            sys.stderr.write(f"{error}\n")
        return 2

    report = Report()
    check_workbook(sheets, order, report)
    payload = report.as_dict(path.name)

    if arguments.json:
        print(json.dumps(payload, indent=2))
    else:
        for check in report.checks:
            marker = "PASS" if check["status"] == "pass" else "FAIL"
            print(f"[{marker}] {check['id']}: {check['detail']}")
        print(f"\n{payload['status'].upper()}: {payload['checks_run']} checks, "
              f"{payload['checks_failed']} failed.")
    return 1 if report.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
