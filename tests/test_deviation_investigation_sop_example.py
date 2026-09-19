"""Tests for the contributed deviation-investigation SOP validator example."""

from __future__ import annotations

import importlib.util
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "deviation-investigation-sop-validator"
SCRIPTS = (
    EXAMPLE
    / "candidate"
    / "skills"
    / "validate-deviation-investigation-sop"
    / "scripts"
)


def load_module(name: str, path: Path):
    sys.path.insert(0, str(path.parent))
    try:
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.pop(0)


def stable_markdown(value: str) -> str:
    return "\n".join(
        "- **Source:** `<input>`" if line.startswith("- **Source:**") else line
        for line in value.splitlines()
    )


class DeviationInvestigationSopExampleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sop_review = load_module("example_sop_review", SCRIPTS / "sop_review.py")

    def test_candidate_manifest_and_owned_resources(self):
        spec = json.loads(
            (EXAMPLE / "candidate" / "plugin-spec.json").read_text(encoding="utf-8")
        )
        self.assertEqual(spec["schema_version"], "creator-plugin-1")
        self.assertEqual(spec["version"], "2.2.0")
        self.assertEqual(spec["skills"], ["validate-deviation-investigation-sop"])
        self.assertEqual(spec["connectors"], [])
        for relative in (
            "SKILL.md",
            "references/contract.md",
            "references/document-mode.md",
            "scripts/extraction_to_packet.py",
            "scripts/markdown_review.py",
            "scripts/sop_review.py",
        ):
            self.assertTrue(
                (
                    EXAMPLE
                    / "candidate"
                    / "skills"
                    / "validate-deviation-investigation-sop"
                    / relative
                ).is_file(),
                relative,
            )

    def test_archived_preview_matches_its_build_report(self):
        archive = (
            EXAMPLE
            / "archive"
            / "v2.2.0"
            / "deviation-investigation-sop-2.2.0-source.zip"
        )
        report = json.loads(
            (
                EXAMPLE
                / "archive"
                / "v2.2.0"
                / "deviation-investigation-sop-2.2.0.report.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(archive.stat().st_size, report["size_bytes"])
        self.assertEqual(hashlib.sha256(archive.read_bytes()).hexdigest(), report["sha256"])
        self.assertEqual(report["artifact_kind"], "compatible-source-export")
        self.assertEqual(report["status"], "Draft")

    def test_structured_fixture_matches_both_expected_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            packet_path = Path(directory) / "packet.json"
            markdown_path = Path(directory) / "review.md"
            input_path = EXAMPLE.relative_to(ROOT) / "input-new.json"
            code = self.sop_review.main(
                [
                    "--input",
                    str(input_path),
                    "--output",
                    str(packet_path),
                    "--markdown",
                    str(markdown_path),
                ]
            )
            self.assertEqual(code, 0)
            actual_packet = json.loads(packet_path.read_text(encoding="utf-8"))
            expected_packet = json.loads(
                (EXAMPLE / "expected-new-packet.json").read_text(encoding="utf-8")
            )
            self.assertEqual(actual_packet, expected_packet)
            self.assertEqual(
                stable_markdown(markdown_path.read_text(encoding="utf-8")),
                stable_markdown(
                    (EXAMPLE / "expected-new-review.md").read_text(encoding="utf-8")
                ),
            )

    def test_helper_refuses_to_overwrite_either_output(self):
        with tempfile.TemporaryDirectory() as directory:
            packet_path = Path(directory) / "packet.json"
            markdown_path = Path(directory) / "review.md"
            packet_path.write_text("keep", encoding="utf-8")
            code = self.sop_review.main(
                [
                    "--input",
                    str(EXAMPLE / "input-new.json"),
                    "--output",
                    str(packet_path),
                    "--markdown",
                    str(markdown_path),
                ]
            )
            self.assertEqual(code, 2)
            self.assertEqual(packet_path.read_text(encoding="utf-8"), "keep")
            self.assertFalse(markdown_path.exists())

    def test_word_fixtures_are_valid_synthetic_open_xml_packages(self):
        for name in ("sample-deviation-report.docx", "sample-sop-checklist.docx"):
            with self.subTest(name=name), ZipFile(EXAMPLE / "documents" / name) as archive:
                document = archive.read("word/document.xml").decode("utf-8")
                self.assertIn("SYNTHETIC TRAINING RECORD", document)
                self.assertIn("SYN-", document)


if __name__ == "__main__":
    unittest.main()
