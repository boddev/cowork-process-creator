#!/usr/bin/env python3
"""Standard-library tests for sanitize_workbook.py.

The sanitizer's whole promise is that the delivery copy is the same workbook the person saved
from Excel, with only metadata, package plumbing and one cell style changed. These tests build a
small OPC package by hand that carries the exact structures the sanitizer targets - an
``x15ac:absPath`` inside ``mc:AlternateContent``, an ``xr:revisionPtr``, a personal
``cp:lastModifiedBy``, a printerSettings part with its content-type default, relationship and
``pageSetup/@r:id``, and a Review row whose last cell sits on a mismatched border style - and then
assert both what changed and what did not.

No third-party package is imported, so the ordinary repository test path gains no dependency.

Run only these tests:
    python -m unittest scenarios.financial-services._recordings.sec-filing-to-excel.test_sanitize_workbook -v

or, from inside this folder:
    python test_sanitize_workbook.py -v
"""
import contextlib
import importlib.util
import io
from pathlib import Path
import re
import sys
import tempfile
import unittest
from xml.dom import minidom
import zipfile

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent

_spec = importlib.util.spec_from_file_location(
    "sec_filing_sanitize_workbook", ROOT / "sanitize_workbook.py"
)
sanitize_workbook = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sanitize_workbook)

MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
DOC_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"

PRIVATE_PATH = r"C:\Users\someone\.private\session-state\abc\recording-trial" + "\\"
PERSONAL_NAME = "A Person"
SEC_URL = "https://www.sec.gov/Archives/edgar/data/21344/000002134425000011/ko-20241231.htm"

SHEET_NAMES = ["Statement", "Raw paste", "Sources", "Review", "Guide"]

WORKBOOK_XML = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    f'<workbook xmlns="{MAIN_NS}" xmlns:r="{DOC_REL_NS}" '
    'xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006" '
    'mc:Ignorable="x15 xr xr6 xr10 xr2" '
    'xmlns:x15="http://schemas.microsoft.com/office/spreadsheetml/2010/11/main" '
    'xmlns:xr="http://schemas.microsoft.com/office/spreadsheetml/2014/revision" '
    'xmlns:xr6="http://schemas.microsoft.com/office/spreadsheetml/2016/revision6" '
    'xmlns:xr10="http://schemas.microsoft.com/office/spreadsheetml/2016/revision10" '
    'xmlns:xr2="http://schemas.microsoft.com/office/spreadsheetml/2015/revision2">'
    '<fileVersion appName="xl" lastEdited="7"/><workbookPr/>'
    '<mc:AlternateContent '
    'xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006">'
    '<mc:Choice Requires="x15">'
    f'<x15ac:absPath url="{PRIVATE_PATH}" '
    'xmlns:x15ac="http://schemas.microsoft.com/office/spreadsheetml/2010/11/ac"/>'
    "</mc:Choice></mc:AlternateContent>"
    '<xr:revisionPtr revIDLastSave="44" documentId="11_82E848AF655FDA0420AB045E37" '
    'xr6:coauthVersionLast="47" xr10:uidLastSave="{CBE40BC2-9E88-442E-B285-F6133494A837}"/>'
    "<bookViews><workbookView xWindow=\"-98\" yWindow=\"-98\"/></bookViews><sheets>"
    + "".join(
        f'<sheet name="{name}" sheetId="{index}" r:id="rId{index}"/>'
        for index, name in enumerate(SHEET_NAMES, start=1)
    )
    + '</sheets><calcPr calcId="191029"/></workbook>'
)

CORE_XML = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<cp:coreProperties '
    'xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
    'xmlns:dc="http://purl.org/dc/elements/1.1/">'
    "<dc:title>Recording template</dc:title>"
    "<dc:creator>Financial reporting pilot - workbook preparation script</dc:creator>"
    f"<cp:lastModifiedBy>{PERSONAL_NAME}</cp:lastModifiedBy>"
    "</cp:coreProperties>"
)

CONTENT_TYPES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" '
    'ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Default Extension="bin" ContentType="application/vnd.openxmlformats-officedocument.'
    'spreadsheetml.printerSettings"/>'
    '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-'
    'officedocument.spreadsheetml.sheet.main+xml"/>'
    '<Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-'
    'officedocument.spreadsheetml.sharedStrings+xml"/>'
    + "".join(
        f'<Override PartName="/xl/worksheets/sheet{index}.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        for index in range(1, len(SHEET_NAMES) + 1)
    )
    + "</Types>"
)

PRINTER_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    f'<Relationships xmlns="{PKG_REL_NS}">'
    f'<Relationship Id="rId1" Type="{DOC_REL_NS}/printerSettings" '
    'Target="../printerSettings/printerSettings1.bin"/></Relationships>'
)

ACCESSION = "0000021344-25-000011"

STRINGS = ["Net Operating Revenues", "Control", "Ties to filing",
           "Status: Draft populated from filing; pending human review.",
           "Source scope", "Pending human review", SEC_URL, "Year Ended December 31,",
           ACCESSION]


def sheet(body):
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<worksheet xmlns="{MAIN_NS}" xmlns:r="{DOC_REL_NS}"><sheetData>{body}</sheetData>'
        '<pageMargins left="0.75" right="0.75" top="1" bottom="1"/></worksheet>'
    )


STATEMENT_SHEET = sheet(
    '<row r="5"><c r="A5" s="4" t="s"><v>0</v></c>'
    '<c r="B5" s="5"><v>47061</v></c><c r="C5" s="5"><v>45754</v></c>'
    '<c r="D5" s="6"><f>B5-C5</f><v>1307</v></c></row>'
    '<row r="20"><c r="A20" s="4" t="s"><v>1</v></c>'
    '<c r="B20" s="6" t="str"><f>IF(B5&gt;0,"Ties to filing","Review difference")</f>'
    "<v>Ties to filing</v></c></row>"
    '<row r="22"><c r="A22" s="4" t="s"><v>3</v></c></row>'
)

RAW_PASTE_SHEET = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    f'<worksheet xmlns="{MAIN_NS}" xmlns:r="{DOC_REL_NS}"><sheetData>'
    '<row r="5"><c r="A5" s="2" t="s"><v>7</v></c></row>'
    '</sheetData><pageMargins left="0.75" right="0.75" top="1" bottom="1"/>'
    '<pageSetup orientation="portrait" r:id="rId1"/></worksheet>'
)

SOURCES_SHEET = sheet(
    '<row r="5"><c r="A5" s="2" t="s"><v>6</v></c><c r="B5" s="2" t="s"><v>8</v></c></row>'
)

REVIEW_SHEET = sheet(
    '<row r="5" spans="1:4" ht="30" customHeight="1">'
    '<c r="A5" s="72" t="s"><v>4</v></c><c r="B5" s="72" t="s"><v>4</v></c>'
    '<c r="C5" s="72" t="s"><v>4</v></c><c r="D5" s="73" t="s"><v>5</v></c></row>'
)

GUIDE_SHEET = sheet('<row r="1"><c r="A1" s="2" t="s"><v>1</v></c></row>')

SHEET_BODIES = [STATEMENT_SHEET, RAW_PASTE_SHEET, SOURCES_SHEET, REVIEW_SHEET, GUIDE_SHEET]


def build_source_workbook(path, workbook_xml=WORKBOOK_XML, core_xml=CORE_XML,
                          include_printer=True):
    shared = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<sst xmlns="{MAIN_NS}" count="{len(STRINGS)}" uniqueCount="{len(STRINGS)}">'
        + "".join(f"<si><t>{value}</t></si>" for value in STRINGS)
        + "</sst>"
    )
    workbook_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<Relationships xmlns="{PKG_REL_NS}">'
        + "".join(
            f'<Relationship Id="rId{index}" Type="{DOC_REL_NS}/worksheet" '
            f'Target="worksheets/sheet{index}.xml"/>'
            for index in range(1, len(SHEET_NAMES) + 1)
        )
        + f'<Relationship Id="rId9" Type="{DOC_REL_NS}/sharedStrings" '
        'Target="sharedStrings.xml"/></Relationships>'
    )
    root_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<Relationships xmlns="{PKG_REL_NS}">'
        f'<Relationship Id="rId1" Type="{DOC_REL_NS}/officeDocument" Target="xl/workbook.xml"/>'
        "</Relationships>"
    )
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", CONTENT_TYPES)
        archive.writestr("_rels/.rels", root_rels)
        archive.writestr("docProps/core.xml", core_xml)
        archive.writestr("xl/workbook.xml", workbook_xml)
        archive.writestr("xl/_rels/workbook.xml.rels", workbook_rels)
        for index, body in enumerate(SHEET_BODIES, start=1):
            archive.writestr(f"xl/worksheets/sheet{index}.xml", body)
        archive.writestr("xl/sharedStrings.xml", shared)
        if include_printer:
            archive.writestr("xl/worksheets/_rels/sheet2.xml.rels", PRINTER_RELS)
            archive.writestr("xl/printerSettings/printerSettings1.bin", b"\x00\x01printer blob")
    return path


def read(path, name):
    with zipfile.ZipFile(path) as archive:
        return archive.read(name).decode("utf-8")


def names(path):
    with zipfile.ZipFile(path) as archive:
        return archive.namelist()


class SanitizeWorkbookTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.source = build_source_workbook(self.directory / "working-draft.xlsx")
        self.destination = self.directory / "completed.xlsx"

    def sanitize(self):
        return sanitize_workbook.sanitize(self.source, self.destination)

    def run_main(self, extra=()):
        with contextlib.redirect_stdout(io.StringIO()) as captured, \
                contextlib.redirect_stderr(io.StringIO()):
            code = sanitize_workbook.main(
                ["--input", str(self.source), "--output", str(self.destination), *extra]
            )
        return code, captured.getvalue()

    def test_private_path_and_revision_identity_are_removed(self):
        self.sanitize()
        workbook = read(self.destination, "xl/workbook.xml")
        self.assertNotIn("absPath", workbook)
        self.assertNotIn(PRIVATE_PATH, workbook)
        self.assertNotIn("revisionPtr", workbook)
        self.assertNotIn("uidLastSave", workbook)
        self.assertNotIn("documentId", workbook)

    def test_ignorable_prefixes_remain_declared(self):
        self.sanitize()
        workbook = read(self.destination, "xl/workbook.xml")
        ignorable = re.search(r'mc:Ignorable="([^"]+)"', workbook).group(1)
        self.assertEqual(ignorable, "x15 xr xr6 xr10 xr2")
        root_tag = re.search(r"<workbook\b[^>]*>", workbook).group(0)
        declared = set(re.findall(r'xmlns:([A-Za-z0-9]+)=', root_tag))
        for prefix in ignorable.split():
            self.assertIn(prefix, declared)
        minidom.parseString(workbook.encode("utf-8")).unlink()

    def test_personal_name_is_replaced(self):
        self.sanitize()
        core = read(self.destination, "docProps/core.xml")
        self.assertNotIn(PERSONAL_NAME, core)
        self.assertIn(sanitize_workbook.NEUTRAL_LAST_MODIFIED_BY, core)

    def test_printer_settings_part_relationship_and_rid_are_removed(self):
        self.sanitize()
        self.assertNotIn("xl/printerSettings/printerSettings1.bin", names(self.destination))
        self.assertNotIn('Extension="bin"', read(self.destination, "[Content_Types].xml"))
        self.assertNotIn("printerSettings",
                         read(self.destination, "xl/worksheets/_rels/sheet2.xml.rels"))
        raw_paste = read(self.destination, "xl/worksheets/sheet2.xml")
        self.assertNotIn("r:id", raw_paste)
        self.assertIn('<pageSetup orientation="portrait"/>', raw_paste)

    def test_raw_paste_cell_content_survives_printer_edit(self):
        self.sanitize()
        self.assertIn('<c r="A5" s="2" t="s"><v>7</v></c>',
                      read(self.destination, "xl/worksheets/sheet2.xml"))

    def test_review_row_style_is_normalised(self):
        _disclosures, _removed, normalised = self.sanitize()
        self.assertTrue(normalised)
        review = read(self.destination, "xl/worksheets/sheet4.xml")
        self.assertNotIn('s="73"', review)
        self.assertEqual(review.count('s="72"'), 4)
        self.assertIn('<c r="D5" s="72" t="s"><v>5</v></c>', review)

    def test_cell_values_formulas_and_caches_are_unchanged(self):
        self.sanitize()
        differences, counts = sanitize_workbook.compare_cells(self.source, self.destination)
        self.assertEqual(differences, [])
        self.assertEqual(counts["formula_cells"], 2)
        statement = read(self.destination, "xl/worksheets/sheet1.xml")
        self.assertIn("<f>B5-C5</f><v>1307</v>", statement)
        self.assertIn("<v>Ties to filing</v>", statement)

    def test_public_sec_reference_is_preserved(self):
        self.sanitize()
        findings, preserved = sanitize_workbook.audit(self.destination)
        self.assertTrue(preserved[SEC_URL])

    def test_audit_reports_no_residual_identity(self):
        self.sanitize()
        findings, _preserved = sanitize_workbook.audit(self.destination)
        self.assertEqual(findings, [])

    def test_audit_flags_identity_when_present(self):
        findings, _preserved = sanitize_workbook.audit(self.source)
        self.assertTrue(findings)

    def test_missing_abs_path_block_is_refused_rather_than_guessed(self):
        plain = WORKBOOK_XML.replace(
            WORKBOOK_XML[WORKBOOK_XML.index("<mc:AlternateContent"):
                         WORKBOOK_XML.index("</mc:AlternateContent>") + len("</mc:AlternateContent>")],
            "",
        )
        source = build_source_workbook(self.directory / "no-abspath.xlsx", workbook_xml=plain)
        with self.assertRaises(sanitize_workbook.SanitizeError):
            sanitize_workbook.sanitize(source, self.directory / "out.xlsx")

    def test_missing_printer_part_is_refused(self):
        source = build_source_workbook(self.directory / "no-printer.xlsx", include_printer=False)
        with self.assertRaises(sanitize_workbook.SanitizeError):
            sanitize_workbook.sanitize(source, self.directory / "out2.xlsx")

    def test_cli_succeeds_and_reports_hashes(self):
        code, output = self.run_main()
        self.assertEqual(code, 0)
        self.assertIn("input  sha256", output)
        self.assertIn("output sha256", output)
        self.assertIn("OK", output)

    def test_cli_refuses_to_overwrite_without_force(self):
        self.destination.write_bytes(b"existing")
        code, _output = self.run_main()
        self.assertEqual(code, 2)
        self.assertEqual(self.destination.read_bytes(), b"existing")

    def test_cli_overwrites_with_force(self):
        self.destination.write_bytes(b"existing")
        code, _output = self.run_main(extra=["--force"])
        self.assertEqual(code, 0)
        self.assertNotEqual(self.destination.read_bytes(), b"existing")

    def test_source_workbook_is_never_modified(self):
        before = self.source.read_bytes()
        self.run_main()
        self.assertEqual(self.source.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
