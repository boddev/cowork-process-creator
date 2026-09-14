from __future__ import annotations

import copy
import hashlib
import importlib.util
import io
import json
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import uuid
import zipfile
import zlib
from pathlib import Path
from unittest import mock

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
BUILDER = ROOT / "appPackage" / "skills" / "build-output-plugin" / "scripts" / "creator_builder.py"
CANDIDATE = ROOT / "examples" / "n00" / "candidate"
MODULE_SPEC = importlib.util.spec_from_file_location("creator_builder_tests", BUILDER)
builder = importlib.util.module_from_spec(MODULE_SPEC)
MODULE_SPEC.loader.exec_module(builder)


class BuilderTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="n00-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "candidate"
        shutil.copytree(CANDIDATE, self.source)
        self.skill_dir = self.source / "skills" / "ready-items-report"
        self.skill = self.skill_dir / "SKILL.md"
        self.output = self.root / "plugin.zip"
        self.report = self.root / "report.json"

    def change_spec(self, field, value):
        path = self.source / "plugin-spec.json"
        spec = json.loads(path.read_text(encoding="utf-8"))
        spec[field] = value
        path.write_text(json.dumps(spec), encoding="utf-8")

    def assemble(self):
        return builder.assemble(self.source, "compatible-source")[0]

    def metadata(self):
        # Syntax fixtures only, not an approved publisher. Never exported to dist.
        value = {
            "app_id": str(uuid.uuid4()),
            "developer": {
                "name": "Syntax fixture only",
                "websiteUrl": "https://www.microsoft.com",
                "privacyUrl": "https://privacy.microsoft.com/privacystatement",
                "termsOfUseUrl": "https://www.microsoft.com/servicesagreement",
            },
        }
        path = self.root / "metadata.json"
        path.write_bytes(builder.json_bytes(value))
        return path, value

    def test_bootstrap_bundles_its_own_builder_and_references(self):
        payload, spec = builder.assemble(ROOT / "appPackage", "compatible-source")
        self.assertEqual(len(spec["skills"]), 8)
        self.assertEqual(sum(path.endswith("/SKILL.md") for path in payload), 8)
        self.assertEqual(payload["skills/build-output-plugin/scripts/creator_builder.py"], BUILDER.read_bytes())
        self.assertNotIn("manifest.json", payload)
        self.assertNotIn("plugin-spec.json", payload)
        self.assertFalse(any(path.endswith((".mp4", ".webm")) or "/tests/" in path for path in payload))

    def test_zip_roots_hash_inventory_and_honest_readiness(self):
        result = builder.build(self.source, self.output, self.report, "compatible-source")
        data = self.output.read_bytes()
        self.assertEqual(result["sha256"], hashlib.sha256(data).hexdigest())
        self.assertEqual(result, json.loads(self.report.read_text(encoding="utf-8")))
        self.assertEqual(result["status"], "Draft")
        self.assertEqual(result["host_acceptance"], "unverified")
        self.assertEqual(result["native_execution"], "not_attested_by_builder")
        self.assertEqual(result["scheduling"], "not_exercised")
        with zipfile.ZipFile(self.output) as archive:
            self.assertIsNone(archive.testzip())
            self.assertIn(".claude-plugin/plugin.json", archive.namelist())
            self.assertEqual(archive.namelist(), sorted(archive.namelist()))
            self.assertEqual(set(archive.namelist()), {row["path"] for row in result["files"]})
            for row in result["files"]:
                self.assertEqual(row["sha256"], hashlib.sha256(archive.read(row["path"])).hexdigest())
            self.assertTrue(all(info.date_time == (2020, 1, 1, 0, 0, 0) for info in archive.infolist()))

    def test_reproducible_zip(self):
        first = builder.zip_bytes(self.assemble())
        second = builder.zip_bytes(dict(reversed(list(self.assemble().items()))))
        self.assertEqual(first, second)

    def test_canonical_composer_emits_only_documented_subset(self):
        path, metadata = self.metadata()
        payload, spec = builder.assemble(self.source, "cowork-v1.28", path)
        manifest = json.loads(payload["manifest.json"])
        self.assertEqual(set(manifest), {
            "$schema", "manifestVersion", "version", "id", "developer",
            "name", "description", "icons", "accentColor", "agentSkills",
        })
        self.assertEqual(manifest["manifestVersion"], "1.28")
        self.assertEqual(manifest["$schema"], builder.SCHEMA)
        self.assertEqual(manifest["id"], metadata["app_id"])
        self.assertEqual(manifest["developer"], metadata["developer"])
        self.assertEqual(manifest["version"], spec["version"])
        self.assertEqual(manifest["agentSkills"], [{"folder": "./skills/ready-items-report"}])
        self.assertNotIn(".claude-plugin/plugin.json", payload)
        for name, size in (("color.png", 192), ("outline.png", 32)):
            content = payload[name]
            self.assertEqual(content[:8], b"\x89PNG\r\n\x1a\n")
            self.assertEqual(struct.unpack(">II", content[16:24]), (size, size))
            offset, compressed = 8, bytearray()
            while offset < len(content):
                length = struct.unpack(">I", content[offset:offset + 4])[0]
                kind = content[offset + 4:offset + 8]
                data = content[offset + 8:offset + 8 + length]
                crc = struct.unpack(">I", content[offset + 8 + length:offset + 12 + length])[0]
                self.assertEqual(crc, zlib.crc32(kind + data) & 0xFFFFFFFF)
                if kind == b"IDAT":
                    compressed.extend(data)
                offset += length + 12
            self.assertEqual(len(zlib.decompress(compressed)), size * (1 + size * 4))
        report = builder.build(self.source, self.output, self.report, "cowork-v1.28", path)
        self.assertEqual(report["status"], "Package built")
        self.assertEqual(report["host_acceptance"], "unverified")

    def test_missing_metadata_does_not_create_native_zip(self):
        with self.assertRaisesRegex(builder.BuildError, "requires --metadata"):
            builder.build(self.source, self.output, self.report, "cowork-v1.28")
        self.assertFalse(self.output.exists())
        self.assertFalse(self.report.exists())

    def test_bad_metadata_is_rejected(self):
        path, good = self.metadata()
        variants = []
        for url in (
            "", "http://publisher.com", "https://example.com/privacy", "https://contoso.com",
            "https://publisher.invalid", "https://localhost", "https://127.0.0.1",
            "https://user:password@publisher.com", "https://-broken.com",
            "https://broken..com", "https://publisher.com?token=private",
            "https://publisher.com/#fragment", "https://publisher.com:8443",
            "https://publisher.com\\wrong", "https://publisher.test",
        ):
            item = copy.deepcopy(good)
            item["developer"]["privacyUrl"] = url
            variants.append(item)
        for app_id in ("", "YOUR-GUID-HERE", "00000000-0000-0000-0000-000000000000", 123):
            item = copy.deepcopy(good)
            item["app_id"] = app_id
            variants.append(item)
        for item in variants:
            with self.subTest(metadata=item):
                path.write_bytes(builder.json_bytes(item))
                with self.assertRaises(builder.BuildError):
                    builder.assemble(self.source, "cowork-v1.28", path)
        for field in good["developer"]:
            item = copy.deepcopy(good)
            del item["developer"][field]
            path.write_bytes(builder.json_bytes(item))
            with self.subTest(missing=field), self.assertRaises(builder.BuildError):
                builder.assemble(self.source, "cowork-v1.28", path)

    def test_unexpected_fields_and_connectors_fail(self):
        self.change_spec("agentConnectors", [])
        with self.assertRaisesRegex(builder.BuildError, "unexpected fields"):
            self.assemble()

    def test_source_extras_are_not_silently_packaged(self):
        (self.source / "recording.mp4").write_bytes(b"synthetic")
        with self.assertRaisesRegex(builder.BuildError, "exactly"):
            self.assemble()

    def test_spec_types_names_versions_and_counts(self):
        original = (self.source / "plugin-spec.json").read_bytes()
        cases = [
            ("name", "Bad_Name"), ("name", "bad--name"), ("name", "a" * 65),
            ("name", None), ("title", "x" * 31), ("summary", "x" * 81),
            ("description", ""), ("description", "x" * 4001),
            ("version", "1.2"), ("version", "01.2.3"), ("version", "1.\u0662.3"),
            ("skills", []), ("skills", ["ready-items-report"] * 21),
            ("skills", ["ready-items-report"] * 2), ("skills", [False]),
            ("skills", "ready-items-report"), ("schema_version", "future"),
        ]
        for key, value in cases:
            (self.source / "plugin-spec.json").write_bytes(original)
            self.change_spec(key, value)
            with self.subTest(field=key, value=value), self.assertRaises(builder.BuildError):
                self.assemble()

    def test_duplicate_json_fields_and_parser_failures(self):
        path = self.source / "plugin-spec.json"
        for raw in ('{"name":"one","name":"two"}', '{"value":NaN}', "{oops", '{"value":' + "[" * 1500 + "0" + "]" * 1500 + "}", '{"value":' + "9" * 6000 + "}"):
            path.write_text(raw, encoding="utf-8")
            with self.subTest(prefix=raw[:30]), self.assertRaises(builder.BuildError):
                builder.read_json(path)

    def test_frontmatter_and_body_validation(self):
        original = self.skill.read_text(encoding="utf-8")
        cases = [
            original.replace("name: ready-items-report", "name: other"),
            original.replace('description: "', "description: "),
            '---\nname: ready-items-report\ndescription: ""\n---\nBody\n',
            '---\nname: ready-items-report\ndescription: "' + "x" * 1025 + '"\n---\nBody\n',
            '---\nname: ready-items-report\ndescription: "Valid"\n---\n   \n',
            original.replace("---\n\n#", "license: MIT\n---\n\n#", 1),
        ]
        for content in cases:
            self.skill.write_text(content, encoding="utf-8")
            with self.subTest(frontmatter=content[:100]), self.assertRaises(builder.BuildError):
                self.assemble()

    def test_broken_resource_reference_fails(self):
        (self.skill_dir / "references" / "input-contract.md").unlink()
        with self.assertRaisesRegex(builder.BuildError, "missing referenced companion"):
            self.assemble()

    def test_unsafe_package_paths(self):
        for path in ("../file.py", "/absolute", "a//b", "a/./b", "a\\b", "C:/file",
                     "a/.secret", "a/CON.txt", "a/com9.py", "a/LPT1", "a/end.",
                     "a/end ", "a/colon:x", "a/\0x", "a/x\u00e9", "x" * 257):
            with self.subTest(path=path), self.assertRaises(builder.BuildError):
                builder.validate_path(path)
        for path in ("scripts/helper.py", "references/Rule 1!.md", "assets/config_1.json"):
            builder.validate_path(path)

    def test_hidden_and_media_companions_fail(self):
        for name in (".env", "recording.mp4", "screen.png", "binary.exe"):
            path = self.skill_dir / name
            path.write_bytes(b"not real media")
            with self.subTest(name=name), self.assertRaises(builder.BuildError):
                self.assemble()
            path.unlink()

    def test_symlink_is_rejected_before_file_read(self):
        with mock.patch.object(Path, "lstat") as lstat:
            lstat.return_value.st_mode = 0o120777
            with self.assertRaisesRegex(builder.BuildError, "symlinks"):
                builder.check_regular(self.skill)

    def test_cross_skill_and_external_python_imports_fail(self):
        path = self.skill_dir / "scripts" / "report.py"
        for content in ("from ..other import helper", "import requests", "import subprocess",
                        "from urllib.request import urlopen", "import creator_builder",
                        "exec('pass')", "__import__('os')", "eval('1+1')", "def broken("):
            path.write_text(content, encoding="utf-8")
            with self.subTest(content=content), self.assertRaises(builder.BuildError):
                self.assemble()

    def test_secret_template_and_absolute_path_patterns(self):
        path = self.skill_dir / "references" / "extra.txt"
        for value in ("Bearer " + "a" * 30, "ghp_" + "a" * 36, "${APP_ID}",
                      "{{ app_id }}", "YOUR-GUID", "<REPLACE_THIS>",
                      "C:\\Users\\demo\\source.py", "/home/developer/source.py"):
            path.write_text(value, encoding="utf-8")
            with self.subTest(kind=value[:10]), self.assertRaises(builder.BuildError) as error:
                self.assemble()
            self.assertNotIn(value, str(error.exception))

    def test_companion_count_and_file_size_limits(self):
        for index in range(18):
            (self.skill_dir / "references" / f"extra-{index}.txt").write_bytes(b"x")
        self.assemble()
        (self.skill_dir / "references" / "extra-last.txt").write_bytes(b"x")
        with self.assertRaisesRegex(builder.BuildError, "more than 20"):
            self.assemble()
        (self.skill_dir / "references" / "extra-last.txt").unlink()
        oversized = self.skill_dir / "references" / "extra-0.txt"
        oversized.write_bytes(b"x" * (builder.MAX_COMPANION_BYTES + 1))
        with self.assertRaisesRegex(builder.BuildError, "file exceeds"):
            self.assemble()

    def test_companion_aggregate_and_skill_size_limits(self):
        for index in range(2):
            (self.skill_dir / "references" / f"large-{index}.txt").write_bytes(b"x" * builder.MAX_COMPANION_BYTES)
        with self.assertRaisesRegex(builder.BuildError, "companions exceed 10 MB"):
            self.assemble()
        self.skill.write_bytes(b"x" * (builder.MAX_SKILL_BYTES + 1))
        with self.assertRaisesRegex(builder.BuildError, "file exceeds"):
            self.assemble()

    def test_exact_twenty_skill_limit_with_distinct_folders(self):
        names = ["ready-items-report"]
        original_skill = self.skill.read_text(encoding="utf-8")
        for index in range(19):
            name = f"report-{index:02d}"
            destination = self.source / "skills" / name
            shutil.copytree(self.skill_dir, destination)
            (destination / "SKILL.md").write_text(
                original_skill.replace("name: ready-items-report", "name: " + name, 1),
                encoding="utf-8",
            )
            names.append(name)
        self.change_spec("skills", names)
        payload = self.assemble()
        self.assertEqual(sum(path.endswith("/SKILL.md") for path in payload), 20)
        self.change_spec("skills", names + ["report-over-limit"])
        with self.assertRaisesRegex(builder.BuildError, "1-20"):
            self.assemble()

    def test_exact_ten_mb_companion_aggregate_is_accepted(self):
        self.skill.write_text(
            '---\nname: ready-items-report\ndescription: "Structural limit fixture."\n---\n'
            "# Limit fixture\n\nNo executable behavior is claimed.\n",
            encoding="utf-8",
        )
        (self.skill_dir / "scripts" / "report.py").unlink()
        references = self.skill_dir / "references"
        (references / "input-contract.md").write_bytes(b"x" * builder.MAX_COMPANION_BYTES)
        (references / "second.txt").write_bytes(b"x" * builder.MAX_COMPANION_BYTES)
        payload = self.assemble()
        total = sum(len(data) for path, data in payload.items() if path.startswith("skills/") and not path.endswith("/SKILL.md"))
        self.assertEqual(total, builder.MAX_COMPANION_TOTAL)

    def test_no_overwrite_or_output_inside_source(self):
        self.output.write_bytes(b"existing user artifact")
        with self.assertRaisesRegex(builder.BuildError, "overwrite"):
            builder.build(self.source, self.output, self.report, "compatible-source")
        self.assertEqual(self.output.read_bytes(), b"existing user artifact")
        self.assertFalse(self.report.exists())
        with self.assertRaisesRegex(builder.BuildError, "outside"):
            builder.build(self.source, self.source / "new.zip", self.report, "compatible-source")

    def test_report_failure_removes_only_new_zip(self):
        real_write = builder.write_new_file

        def failing_write(path, content):
            if path == self.report:
                raise OSError("synthetic report write failure")
            real_write(path, content)

        with mock.patch.object(builder, "write_new_file", side_effect=failing_write):
            with self.assertRaisesRegex(OSError, "synthetic"):
                builder.build(self.source, self.output, self.report, "compatible-source")
        self.assertFalse(self.output.exists())
        self.assertFalse(self.report.exists())

    def test_downloaded_builder_runs_without_developer_checkout_imports(self):
        payload, _ = builder.assemble(ROOT / "appPackage", "compatible-source")
        installed = self.root / "installed-creator"
        with zipfile.ZipFile(io.BytesIO(builder.zip_bytes(payload))) as archive:
            archive.extractall(installed)
        script = installed / "skills" / "build-output-plugin" / "scripts" / "creator_builder.py"
        result = subprocess.run(
            [sys.executable, "-I", "-B", str(script), "build", "--source", str(self.source),
             "--output", str(self.output), "--report", str(self.report), "--target", "compatible-source"],
            cwd=self.root, capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["host_acceptance"], "unverified")
        self.assertEqual(self.output.read_bytes(), builder.zip_bytes(self.assemble()))
        self.assertFalse((installed / "examples").exists())

    def test_cli_metadata_blocker_is_nonzero_without_success_artifacts(self):
        result = subprocess.run(
            [sys.executable, "-I", "-B", str(BUILDER), "build", "--source", str(self.source),
             "--output", str(self.output), "--report", str(self.report)],
            cwd=self.root, capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertEqual(json.loads(result.stderr)["status"], "Draft")
        self.assertFalse(self.output.exists())
        self.assertFalse(self.report.exists())


if __name__ == "__main__":
    unittest.main()
