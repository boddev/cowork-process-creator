from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import re
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

from test_projects import ROOT, b, examples


class PackagedRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="creator-packaged-runtime-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def test_extracted_owning_skill_runs_full_project_file_round_trip(self):
        payload, _ = b.assemble(ROOT / "appPackage", "compatible-source")
        installed = self.root / "installed"
        with zipfile.ZipFile(io.BytesIO(b.zip_bytes(payload))) as archive:
            archive.extractall(installed)
        cli = installed / "skills" / "build-output-plugin" / "scripts" / "creator_project.py"
        project = self.root / "project"
        examples.create_project(project)

        def invoke(*arguments, expected_code=0):
            result = subprocess.run([sys.executable, "-E", "-s", "-B", str(cli), *map(str, arguments)],
                                    cwd=self.root, capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, expected_code, result.stderr)
            return json.loads(result.stdout)

        checked = invoke("check", "--project", project)
        self.assertTrue(checked["ready"])
        package, report = self.root / "output.zip", self.root / "output.json"
        built = invoke("build", "--project", project, "--output", package, "--report", report,
                       "--target", "compatible-source")
        self.assertEqual(built["status"], "Draft")
        self.assertEqual(built["host_acceptance"], "unverified")
        self.assertEqual(built["sha256"], hashlib.sha256(package.read_bytes()).hexdigest())
        expected_payload, _ = b.assemble(project / "candidate", "compatible-source")
        self.assertEqual(package.read_bytes(), b.zip_bytes(expected_payload))
        bundle = self.root / "source.zip"
        invoke("checkpoint", "--project", project, "--output", bundle)
        resumed = self.root / "resumed"
        restored = invoke("resume", "--bundle", bundle, "--output", resumed)
        self.assertTrue(restored["requires_host_recheck"])
        rechecked = invoke("check", "--project", resumed, expected_code=2)
        self.assertFalse(rechecked["ready"])
        self.assertFalse((resumed / "evaluation-results.json").exists())
        self.assertTrue((resumed / "candidate" / "skills" / "cost-report" / "scripts" / "safe_json.py").is_file())
        self.assertFalse((installed / "examples").exists())

    def test_each_declared_creator_resource_pointer_resolves_in_own_skill(self):
        source = ROOT / "appPackage" / "skills"
        for skill in source.iterdir():
            if not skill.is_dir():
                continue
            text = (skill / "SKILL.md").read_text(encoding="utf-8")
            for match in re.findall(r"`((?:references|scripts|assets)[\\/][^`\r\n]+)`", text):
                normalized = match.replace("\\", "/")
                with self.subTest(skill=skill.name, pointer=match):
                    b.validate_path(normalized)
                    self.assertTrue(skill.joinpath(*normalized.split("/")).is_file())

    def test_safe_json_pattern_reports_precise_limits_and_never_overwrites(self):
        path = ROOT / "appPackage" / "skills" / "author-deterministic-helpers" / "assets" / "safe_json.py"
        spec = importlib.util.spec_from_file_location("tested_safe_json_pattern", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        source = self.root / "input.json"
        cases = [
            (b'{"a":1,"a":2}', {}, "duplicate"),
            (b'{"a":NaN}', {}, "Non-finite"),
            (b"\xff", {}, "UTF-8"),
            (b'{"a":[[[[1]]]]}', {"max_depth": 2}, "nesting"),
            (b'{"long":"too much"}', {"max_bytes": 8}, "byte limit"),
            (("[" * 10000 + "0" + "]" * 10000).encode(), {}, "nesting"),
        ]
        for content, options, expected in cases:
            source.write_bytes(content)
            with self.subTest(expected=expected), self.assertRaisesRegex(module.InputError, expected):
                module.load_json(source, **options)
        output = self.root / "report.md"
        module.write_new_text(output, "original\n")
        with self.assertRaises(FileExistsError):
            module.write_new_text(output, "replacement\n")
        self.assertEqual(output.read_text(encoding="utf-8"), "original\n")

    def test_safe_json_encodes_before_creating_any_output(self):
        path = ROOT / "appPackage" / "skills" / "author-deterministic-helpers" / "assets" / "safe_json.py"
        spec = importlib.util.spec_from_file_location("tested_unicode_output", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        invalid = self.root / "invalid.md"
        with self.assertRaisesRegex(module.InputError, "invalid Unicode"):
            module.write_new_text(invalid, chr(0xD800))
        self.assertFalse(invalid.exists(), "Invalid Unicode must not leave an empty result file")
        valid = self.root / "valid.md"
        text = "\u03a9 \u2713\n"
        module.write_new_text(valid, text)
        self.assertEqual(valid.read_bytes(), text.encode("utf-8"))
        with self.assertRaisesRegex(module.InputError, "invalid Unicode"):
            module.write_new_text(valid, chr(0xD800))
        self.assertEqual(valid.read_bytes(), text.encode("utf-8"))
        with self.assertRaises(FileExistsError):
            module.write_new_text(valid, "replacement")
        self.assertEqual(valid.read_bytes(), text.encode("utf-8"))

    def test_runtime_instructions_are_not_the_development_session(self):
        root = ROOT / "appPackage" / "skills"
        forbidden = ("Publishing...", "Creator was disabled", "provisional offline phase",
                     "Native N00/output invocation is still blocked", "current historical N00")
        for path in root.rglob("*.md"):
            content = path.read_text(encoding="utf-8")
            for phrase in forbidden:
                with self.subTest(path=path.name, phrase=phrase):
                    self.assertNotIn(phrase, content)

    def test_authoring_intent_guard_is_before_project_creation(self):
        content = (ROOT / "appPackage" / "skills" / "create-process-plugin" / "SKILL.md").read_text(encoding="utf-8")
        self.assertLess(content.index("## Intent gate"), content.index("## Author in reviewable stages"))
        for phrase in ("run or rerun", "recording summary", "feasibility-only",
                       "schedule an existing output", "ask one focused clarification"):
            self.assertIn(phrase, content)
        self.assertIn("does not automatically authorize", content)

    def test_public_metadata_provenance_is_self_contained_and_unchanged(self):
        assets = ROOT / "appPackage" / "skills" / "map-native-capabilities" / "assets"
        provenance = json.loads((assets / "learn-mcp-provenance.json").read_text(encoding="utf-8"))
        for record in provenance["files"].values():
            path = assets / record["path"]
            with self.subTest(path=record["path"]):
                self.assertTrue(path.is_file())
                content = path.read_bytes()
                self.assertEqual(len(content), record["bytes"])
                self.assertEqual(hashlib.sha256(content).hexdigest(), record["sha256"])
        self.assertEqual(provenance["observation"]["cowork_availability"], "unverified")
        self.assertEqual(provenance["observation"]["tools_call_requests_in_this_probe"], 0)


if __name__ == "__main__":
    unittest.main()
