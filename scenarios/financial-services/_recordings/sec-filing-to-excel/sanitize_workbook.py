#!/usr/bin/env python3
"""Produce a sanitized delivery copy of the saved recording workbook.

The delivery copy must be the *same workbook* the person actually saved from the Excel user
interface. Every entered amount, every formula, and every cached result Excel wrote at save time
is carried across byte-for-byte. This script therefore never loads the workbook through openpyxl
or LibreOffice, never rewrites a formula, and never calculates anything in Python: it edits the
OPC package directly with zipfile, and touches only metadata, package plumbing, and one cell
style.

What it changes, and nothing else:

  1. ``xl/workbook.xml``  - removes the ``mc:AlternateContent`` block holding
     ``x15ac:absPath/@url``, which records the private local directory of the machine that saved
     the file, and removes ``xr:revisionPtr``, which carries ``documentId`` and ``uidLastSave``
     identifiers. Root namespace declarations and ``mc:Ignorable`` are left untouched.
  2. ``docProps/core.xml`` - replaces ``cp:lastModifiedBy`` (a personal name) with a neutral role.
  3. ``xl/printerSettings/printerSettings1.bin`` - dropped, together with the ``bin`` content-type
     default, the sheet2 relationship that points at it, and the now-dangling ``r:id`` on that
     sheet's ``pageSetup``.
  4. ``xl/worksheets/sheet4.xml`` - Review!D5 is moved from cell style 73 to cell style 72, the
     style already used by A5:C5. This is a delivery-only cosmetic fix and is disclosed as such.

Sheet cell values, formulas and cached results are never touched. The two sheet edits are single
attribute substitutions matched against exact expected text, and the script fails loudly if a
match count is not exactly what it expects.

Every XML part it rewrites is re-parsed with ``xml.dom.minidom`` afterwards to prove it is still
well formed, and every prefix listed in an ``mc:Ignorable`` attribute is checked to be still
declared on that element. Nothing here is a claim about how the workbook was produced or filmed.

Usage:
    python sanitize_workbook.py --input <saved.xlsx> --output completed.xlsx [--force]
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import re
import sys
from xml.dom import minidom
import zipfile

NEUTRAL_LAST_MODIFIED_BY = "Financial reporting pilot"

PRINTER_SETTINGS_PART = "xl/printerSettings/printerSettings1.bin"
PRINTER_SETTINGS_RELS = "xl/worksheets/_rels/sheet2.xml.rels"
PRINTER_SETTINGS_SHEET = "xl/worksheets/sheet2.xml"
REVIEW_SHEET = "xl/worksheets/sheet4.xml"

ABS_PATH_PATTERN = re.compile(
    r"<mc:AlternateContent\b[^>]*>.*?</mc:AlternateContent>", re.DOTALL
)
REVISION_PTR_PATTERN = re.compile(r"<xr:revisionPtr\b[^>]*/>")
LAST_MODIFIED_BY_PATTERN = re.compile(
    r"(<cp:lastModifiedBy>)(.*?)(</cp:lastModifiedBy>)", re.DOTALL
)
BIN_DEFAULT_PATTERN = re.compile(r'<Default\s+Extension="bin"[^>]*/>')
PRINTER_REL_PATTERN = re.compile(
    r'<Relationship\b[^>]*printerSettings[^>]*/>'
)
PAGE_SETUP_RID_PATTERN = re.compile(r'(<pageSetup\b[^>]*?)\s+r:id="[^"]*"([^>]*/>)')
REVIEW_D5_PATTERN = re.compile(r'(<c r="D5")\s+s="73"')

IDENTITY_PATTERNS = [
    ("windows-drive-path", re.compile(r"[A-Za-z]:\\")),
    ("users-directory", re.compile(r"Users[\\/]", re.IGNORECASE)),
    ("session-state-directory", re.compile(r"session-state")),
    ("file-uri", re.compile(r"file:///")),
    ("absPath-element", re.compile(r"absPath")),
    ("revision-pointer", re.compile(r"revisionPtr")),
]

# Public references that must survive sanitation untouched.
PRESERVE_SUBSTRINGS = [
    "https://www.sec.gov/Archives/edgar/data/21344/000002134425000011/ko-20241231.htm",
    "0000021344-25-000011",
]


class SanitizeError(Exception):
    pass


def require(condition, message):
    if not condition:
        raise SanitizeError(message)


def substitute_once(pattern, replacement, text, label, expected=1):
    result, count = pattern.subn(replacement, text)
    require(
        count == expected,
        f"{label}: expected {expected} match(es) but found {count}. Refusing to guess.",
    )
    return result


def check_well_formed(name, text):
    """Re-parse a rewritten part and confirm mc:Ignorable prefixes are still declared."""
    try:
        document = minidom.parseString(text.encode("utf-8"))
    except Exception as error:  # pragma: no cover - defensive
        raise SanitizeError(f"{name} is not well formed after sanitation: {error}") from error

    stack = [document.documentElement]
    while stack:
        element = stack.pop()
        if element is None:
            continue
        ignorable = element.getAttribute("mc:Ignorable")
        if ignorable:
            declared = {
                attribute.name.split(":", 1)[1]
                for attribute in element.attributes.values()
                if attribute.name.startswith("xmlns:")
            }
            missing = [prefix for prefix in ignorable.split() if prefix not in declared]
            require(
                not missing,
                f"{name}: mc:Ignorable lists prefixes with no namespace declaration: {missing}",
            )
        stack.extend(
            child for child in element.childNodes if child.nodeType == child.ELEMENT_NODE
        )
    document.unlink()


def sanitize_workbook_xml(text, disclosures):
    require(ABS_PATH_PATTERN.search(text) is not None,
            "xl/workbook.xml: expected an mc:AlternateContent absPath block to remove")
    require("absPath" in ABS_PATH_PATTERN.search(text).group(0),
            "xl/workbook.xml: the mc:AlternateContent block does not contain absPath; "
            "refusing to remove an unrelated block")
    text = substitute_once(ABS_PATH_PATTERN, "", text,
                           "xl/workbook.xml mc:AlternateContent/absPath")
    disclosures.append({
        "part": "xl/workbook.xml",
        "change": "removed mc:AlternateContent containing x15ac:absPath/@url",
        "reason": "the url recorded the private local directory of the saving machine",
        "affects_cell_data": False,
    })
    text = substitute_once(REVISION_PTR_PATTERN, "", text, "xl/workbook.xml xr:revisionPtr")
    disclosures.append({
        "part": "xl/workbook.xml",
        "change": "removed xr:revisionPtr",
        "reason": "carried documentId and uidLastSave session identifiers",
        "affects_cell_data": False,
    })
    return text


def sanitize_core_xml(text, disclosures):
    match = LAST_MODIFIED_BY_PATTERN.search(text)
    require(match is not None, "docProps/core.xml: expected cp:lastModifiedBy")
    previous = match.group(2)
    text = substitute_once(
        LAST_MODIFIED_BY_PATTERN,
        lambda m: f"{m.group(1)}{NEUTRAL_LAST_MODIFIED_BY}{m.group(3)}",
        text,
        "docProps/core.xml cp:lastModifiedBy",
    )
    disclosures.append({
        "part": "docProps/core.xml",
        "change": "replaced cp:lastModifiedBy with a neutral role name",
        "reason": "the element held a personal name",
        "replaced_with": NEUTRAL_LAST_MODIFIED_BY,
        "previous_value_redacted": True,
        "previous_value_length": len(previous),
        "affects_cell_data": False,
    })
    return text


def sanitize_content_types(text, disclosures):
    text = substitute_once(BIN_DEFAULT_PATTERN, "", text,
                           '[Content_Types].xml Default Extension="bin"')
    disclosures.append({
        "part": "[Content_Types].xml",
        "change": 'removed <Default Extension="bin"/>',
        "reason": "the only .bin part, printerSettings1.bin, is removed from the delivery copy",
        "affects_cell_data": False,
    })
    return text


def sanitize_printer_rels(text, disclosures):
    text = substitute_once(PRINTER_REL_PATTERN, "", text,
                           f"{PRINTER_SETTINGS_RELS} printerSettings relationship")
    disclosures.append({
        "part": PRINTER_SETTINGS_RELS,
        "change": "removed the rId1 printerSettings relationship",
        "reason": "its target part is removed from the delivery copy",
        "affects_cell_data": False,
    })
    return text


def sanitize_printer_sheet(text, disclosures):
    text = substitute_once(PAGE_SETUP_RID_PATTERN, r"\1\2", text,
                           f"{PRINTER_SETTINGS_SHEET} pageSetup/@r:id")
    disclosures.append({
        "part": PRINTER_SETTINGS_SHEET,
        "change": "removed the dangling r:id attribute from pageSetup",
        "reason": "the printerSettings relationship it referenced no longer exists",
        "affects_cell_data": False,
        "note": "only the r:id attribute was removed; pageSetup and all cell data are unchanged",
    })
    return text


def normalise_review_row(text, disclosures):
    """Give Review!D5 the same cell style as A5:C5 so the row reads as one aligned row."""
    if not REVIEW_D5_PATTERN.search(text):
        return text, False
    text = substitute_once(REVIEW_D5_PATTERN, r'\1 s="72"', text, "Review!D5 cell style")
    disclosures.append({
        "part": REVIEW_SHEET,
        "change": 'Review!D5 cell style changed from s="73" to s="72"',
        "reason": (
            "a real cut and paste of the review row left D5 on a style whose border omits the "
            "top and bottom edges, so the row's box borders did not line up with A5:C5"
        ),
        "observed": (
            "style 73 uses fontId 16 Arial 14 with borderId 7 (left and right edges only); "
            "style 72 uses the same fontId 16 Arial 14 with borderId 2 (all four edges), which "
            "matches the surrounding template rows"
        ),
        "font_was_already_correct": True,
        "delivery_only_cosmetic_change": True,
        "affects_cell_data": False,
        "affects_cell_text": False,
    })
    return text, True


def sanitize(source: Path, destination: Path):
    disclosures = []
    removed_parts = []

    with zipfile.ZipFile(source) as archive:
        entries = archive.infolist()
        payloads = {info.filename: archive.read(info.filename) for info in entries}

    require(PRINTER_SETTINGS_PART in payloads,
            f"{PRINTER_SETTINGS_PART} not present; refusing to guess at a different package")
    for required_part in ("xl/workbook.xml", "docProps/core.xml", "[Content_Types].xml",
                          PRINTER_SETTINGS_RELS, PRINTER_SETTINGS_SHEET):
        require(required_part in payloads,
                f"{required_part} is missing; this does not look like the expected package")

    rewritten = {}

    text = payloads["xl/workbook.xml"].decode("utf-8")
    rewritten["xl/workbook.xml"] = sanitize_workbook_xml(text, disclosures)

    text = payloads["docProps/core.xml"].decode("utf-8")
    rewritten["docProps/core.xml"] = sanitize_core_xml(text, disclosures)

    text = payloads["[Content_Types].xml"].decode("utf-8")
    rewritten["[Content_Types].xml"] = sanitize_content_types(text, disclosures)

    text = payloads[PRINTER_SETTINGS_RELS].decode("utf-8")
    rewritten[PRINTER_SETTINGS_RELS] = sanitize_printer_rels(text, disclosures)

    text = payloads[PRINTER_SETTINGS_SHEET].decode("utf-8")
    rewritten[PRINTER_SETTINGS_SHEET] = sanitize_printer_sheet(text, disclosures)

    review_normalised = False
    if REVIEW_SHEET in payloads:
        text = payloads[REVIEW_SHEET].decode("utf-8")
        rewritten[REVIEW_SHEET], review_normalised = normalise_review_row(text, disclosures)

    removed_parts.append(PRINTER_SETTINGS_PART)
    disclosures.append({
        "part": PRINTER_SETTINGS_PART,
        "change": "part removed from the delivery copy",
        "reason": "printer settings blobs can embed device and environment details",
        "affects_cell_data": False,
    })

    for name, value in rewritten.items():
        check_well_formed(name, value)

    with zipfile.ZipFile(source) as archive, \
            zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as output:
        for info in archive.infolist():
            if info.filename in removed_parts:
                continue
            copy = zipfile.ZipInfo(info.filename, date_time=info.date_time)
            copy.compress_type = info.compress_type
            copy.external_attr = info.external_attr
            copy.internal_attr = info.internal_attr
            copy.create_system = info.create_system
            if info.filename in rewritten:
                output.writestr(copy, rewritten[info.filename].encode("utf-8"))
            else:
                output.writestr(copy, archive.read(info.filename))

    return disclosures, removed_parts, review_normalised


def audit(path: Path):
    """Report any residual identity marker, and confirm public references survived."""
    findings = []
    preserved = {substring: False for substring in PRESERVE_SUBSTRINGS}
    with zipfile.ZipFile(path) as archive:
        for name in archive.namelist():
            text = archive.read(name).decode("utf-8", "replace")
            for label, pattern in IDENTITY_PATTERNS:
                if pattern.search(text):
                    findings.append(f"{name}: {label}")
            for substring in preserved:
                if substring in text:
                    preserved[substring] = True
    return findings, preserved


def compare_cells(source: Path, destination: Path):
    """Confirm every sheet cell, formula and cached value is identical in the delivery copy."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import validate_recording

    before, before_order = validate_recording.load_workbook(source)
    after, after_order = validate_recording.load_workbook(destination)
    differences = []
    if before_order != after_order:
        differences.append(f"sheet order changed: {before_order} -> {after_order}")
    for sheet in sorted(set(before) | set(after)):
        if sheet not in before or sheet not in after:
            differences.append(f"sheet {sheet!r} present in only one workbook")
            continue
        left, right = before[sheet], after[sheet]
        for coord in sorted(set(left) | set(right)):
            a = left.get(coord)
            b = right.get(coord)
            if a is None or b is None:
                if (a or b) and ((a and (a.has_value or a.formula))
                                 or (b and (b.has_value or b.formula))):
                    differences.append(f"{sheet}!{coord} present in only one workbook")
                continue
            if a.formula != b.formula:
                differences.append(f"{sheet}!{coord} formula {a.formula!r} -> {b.formula!r}")
            if a.value != b.value:
                differences.append(f"{sheet}!{coord} value {a.value!r} -> {b.value!r}")
            if a.cell_type != b.cell_type:
                differences.append(f"{sheet}!{coord} type {a.cell_type} -> {b.cell_type}")
    counts = {
        "sheets": len(after),
        "cells_with_values": sum(
            1 for cells in after.values() for cell in cells.values() if cell.has_value
        ),
        "formula_cells": sum(
            1 for cells in after.values() for cell in cells.values() if cell.formula
        ),
    }
    return differences, counts


def sha256(path: Path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Metadata-only sanitation of a saved recording workbook. Never loads or "
                    "resaves the workbook through a spreadsheet library and never recalculates."
    )
    parser.add_argument("--input", required=True, help="Saved .xlsx to sanitize. Read only.")
    parser.add_argument("--output", required=True, help="Delivery copy to write.")
    parser.add_argument("--force", action="store_true", help="Overwrite an existing output.")
    arguments = parser.parse_args(argv)

    source = Path(arguments.input)
    destination = Path(arguments.output)
    if not source.is_file():
        sys.stderr.write(f"Input not found: {source}\n")
        return 2
    if destination.exists() and not arguments.force:
        sys.stderr.write(f"Refusing to overwrite {destination}; pass --force.\n")
        return 2
    if source.resolve() == destination.resolve():
        sys.stderr.write("Input and output must be different files.\n")
        return 2

    try:
        disclosures, removed, review_normalised = sanitize(source, destination)
        findings, preserved = audit(destination)
        differences, counts = compare_cells(source, destination)
    except SanitizeError as error:
        sys.stderr.write(f"Sanitation refused: {error}\n")
        if destination.exists():
            destination.unlink()
        return 2

    ok = True
    if findings:
        ok = False
        print("Residual identity markers found in the delivery copy:")
        for finding in findings:
            print(f"  - {finding}")
    if differences:
        ok = False
        print("Cell-level differences between source and delivery copy:")
        for difference in differences:
            print(f"  - {difference}")
    missing_public = [key for key, seen in preserved.items() if not seen]
    if missing_public:
        ok = False
        print("Public references that should have been preserved are missing:")
        for key in missing_public:
            print(f"  - {key}")

    print(f"input  sha256 {sha256(source)}")
    print(f"output sha256 {sha256(destination)}")
    print(f"removed parts: {removed}")
    print(f"review row style normalised: {review_normalised}")
    print(f"cells with values: {counts['cells_with_values']}, "
          f"formula cells: {counts['formula_cells']}, sheets: {counts['sheets']}")
    print(f"disclosed changes: {len(disclosures)}")
    print("OK" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
