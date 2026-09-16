import io
import json
import stat
import struct
import unittest
import zipfile
import zlib
from pathlib import Path
from unittest import mock

from scenarios._shared.common import ContractError, file_digest
from scenarios._shared.contract import load_scenario
from scenarios._shared.native import COWORK_SCHEMA, compare_native_import, inspect_cowork_plugin, inspect_zip
from scenarios._shared.pipeline import run_case
from scenarios._shared.staging import stage_creator_inputs
from scenarios.tests.fixtures import dump, make_scenario, modify_json, temporary_directory


class ZipInspectionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = temporary_directory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "unit-only.zip"

    def test_existing_zip_is_hashed_not_run_or_native_attested(self):
        with zipfile.ZipFile(self.path, "w") as archive:
            archive.writestr("UNIT-TEST-ONLY.txt", "Not a native plugin or actual host observation")
        result = inspect_zip(self.path)
        self.assertEqual(result["sha256"], file_digest(self.path))
        self.assertEqual(result["execution"], "not_run")
        self.assertEqual(result["native_provenance"], "unverified")
        self.assertFalse(result["generated"])
        self.assertFalse(result["installed"])

    def test_bad_zip_paths_and_case_collisions_rejected(self):
        for paths in (
            ["../outside.py"], ["C:/outside.py"], ["a\\outside.py"], ["/absolute.py"],
            ["NUL.txt"], ["a.json", "A.json"], ["parent", "parent/child.json"],
            ["parent/child.json", "parent"],
        ):
            with self.subTest(paths=paths):
                with zipfile.ZipFile(self.path, "w") as archive:
                    for name in paths:
                        archive.writestr(name, "{}")
                for name in paths:
                    if "\\" in name:
                        self.path.write_bytes(self.path.read_bytes().replace(
                            name.replace("\\", "/").encode(), name.encode(),
                        ))
                with self.assertRaises(ContractError):
                    inspect_zip(self.path)

    def test_symlink_and_bomb_rejected(self):
        member = zipfile.ZipInfo("alias")
        member.create_system = 3
        member.external_attr = (stat.S_IFLNK | 0o777) << 16
        with zipfile.ZipFile(self.path, "w") as archive:
            archive.writestr(member, "target")
        with self.assertRaises(ContractError):
            inspect_zip(self.path)
        with zipfile.ZipFile(self.path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("oversized-expansion.txt", b"x" * 2_000_000)
        with self.assertRaisesRegex(ContractError, "expansion ratio"):
            inspect_zip(self.path)

    def test_corrupt_zip_is_explicit(self):
        self.path.write_bytes(b"not a ZIP")
        with self.assertRaises(ContractError):
            inspect_zip(self.path)

    def underdeclare_entry(self, payload, compression, declared_size=6):
        with zipfile.ZipFile(self.path, "w", compression=compression) as archive:
            archive.writestr("data.txt", payload)
        content = bytearray(self.path.read_bytes())
        central = content.index(b"PK\x01\x02")
        prefix_crc = zlib.crc32(payload[:declared_size]) & 0xFFFFFFFF
        struct.pack_into("<I", content, 14, prefix_crc)
        struct.pack_into("<I", content, 22, declared_size)
        struct.pack_into("<I", content, central + 16, prefix_crc)
        struct.pack_into("<I", content, central + 24, declared_size)
        self.path.write_bytes(content)

    def test_underdeclared_stream_cannot_supply_only_a_prefix_hash(self):
        for method in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
            with self.subTest(method=method):
                self.underdeclare_entry(b"PREFIX" + b"x" * 4096, method)
                with self.assertRaises(ContractError):
                    inspect_zip(self.path)

    def test_underdeclared_compressed_bomb_is_rejected_before_expanding_it(self):
        self.underdeclare_entry(b"PREFIX" + b"x" * 2_000_000, zipfile.ZIP_DEFLATED)
        with mock.patch("scenarios._shared.native.ENTRY_LIMIT", 1024):
            with self.assertRaises(ContractError):
                inspect_zip(self.path)

    def test_valid_stored_and_deflated_entries_retain_full_hashes(self):
        import hashlib
        payload = bytes(range(256)) * 13
        for method in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
            with self.subTest(method=method):
                with zipfile.ZipFile(self.path, "w", compression=method) as archive:
                    archive.writestr("data.txt", payload)
                    archive.writestr("empty.txt", b"")
                report = inspect_zip(self.path)
                self.assertEqual(report["expanded_bytes"], len(payload))
                self.assertEqual(report["entries"][0]["sha256"], hashlib.sha256(payload).hexdigest())

    def test_truncated_deflate_stream_is_rejected(self):
        with zipfile.ZipFile(self.path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("data.txt", b"some compressible text" * 100)
        content = bytearray(self.path.read_bytes())
        central = content.index(b"PK\x01\x02")
        declared_compressed = struct.unpack_from("<I", content, 18)[0]
        struct.pack_into("<I", content, 18, declared_compressed - 1)
        struct.pack_into("<I", content, central + 20, declared_compressed - 1)
        self.path.write_bytes(content)
        with self.assertRaisesRegex(ContractError, "incomplete DEFLATE"):
            inspect_zip(self.path)

    def test_zip64_local_sizes_and_data_descriptors_are_supported(self):
        class NonSeeking(io.BytesIO):
            def seek(self, *args):
                raise OSError("Unit-test stream is not seekable")

        for descriptor in (False, True):
            with self.subTest(descriptor=descriptor):
                output = NonSeeking() if descriptor else io.BytesIO()
                with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                    with archive.open("data.txt", "w", force_zip64=True) as member:
                        member.write(b"exact stream bytes")
                self.path.write_bytes(output.getvalue())
                report = inspect_zip(self.path)
                self.assertEqual(report["expanded_bytes"], len(b"exact stream bytes"))


class NativeImportTests(unittest.TestCase):
    def setUp(self):
        self.temporary = temporary_directory()
        self.addCleanup(self.temporary.cleanup)
        self.work = Path(self.temporary.name)
        self.root = make_scenario(self.work / "scenarios")
        self.scenario = load_scenario(self.root)
        for case in self.scenario.cases:
            result = run_case(self.scenario, case)
            self.assertEqual(result["state"], "baseline_pass", result["errors"])
        video = self.root / "demo" / "baseline.webm"
        video.parent.mkdir()
        video.write_bytes(b"UNIT TEST ONLY, media gate explicitly mocked")
        media_gate = mock.patch("scenarios._shared.staging.check_media", return_value={"sha256": file_digest(video)})
        media_gate.start()
        self.addCleanup(media_gate.stop)
        stage_creator_inputs(self.scenario)
        self.output = self.work / "output"
        actual_dir = self.output / "unit-01"
        actual_dir.mkdir(parents=True)
        plugin = actual_dir / "unit-test-only.zip"
        # Syntactic fixture only; not an authorized publisher or a native host run.
        manifest = {
            "$schema": COWORK_SCHEMA, "manifestVersion": "1.28", "version": "1.0.0",
            "id": "9f7a3c20-caaa-4b9b-9f5b-9e0c43f6f101",
            "developer": {"name": "Unit fixture", "websiteUrl": "https://www.microsoft.com",
                          "privacyUrl": "https://privacy.microsoft.com/privacystatement",
                          "termsOfUseUrl": "https://www.microsoft.com/servicesagreement"},
            "name": {"short": "Unit fixture", "full": "Unit fixture"},
            "description": {"short": "Not a native run", "full": "Unit fixture, not a real observed native plugin"},
            "accentColor": "#264669", "icons": {"color": "color.png", "outline": "outline.png"},
            "agentSkills": [{"folder": "./skills/unit-skill"}],
        }

        def icon(size):
            def chunk(kind, data):
                return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
            return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
                    + chunk(b"IDAT", zlib.compress((b"\0" + b"\0\0\0\0" * size) * size)) + chunk(b"IEND", b""))

        with zipfile.ZipFile(plugin, "w") as archive:
            archive.writestr("manifest.json", json.dumps(manifest))
            archive.writestr("color.png", icon(192))
            archive.writestr("outline.png", icon(32))
            archive.writestr("skills/unit-skill/SKILL.md", '---\nname: unit-skill\ndescription: "Unit fixture"\n---\n# Unit only\n')
        evidence = actual_dir / "unit-evidence.txt"
        evidence.write_text("UNIT TEST: not a Cowork capture; only an operator claim fixture", encoding="utf-8")
        files = [{"path": "unit-01/unit-evidence.txt", "sha256": file_digest(evidence)}]
        self.claim = {
            "schema_version": 1, "scenario_id": "unit-01",
            "provenance": "operator-declared-native-export", "host": "Microsoft Copilot Cowork",
            "plugin": {"path": "unit-01/unit-test-only.zip", "sha256": file_digest(plugin)},
            "creation": {
                "evidence_id": "declared-creation", "plugin_sha256": file_digest(plugin),
                "creator_input_manifest_sha256": file_digest(self.root / "validation" / "creator-staging.json"),
                "evidence_files": files,
            },
            "installation": {
                "evidence_id": "declared-installation", "creation_evidence_id": "declared-creation",
                "plugin_sha256": file_digest(plugin), "evidence_files": files,
            },
            "invocations": [],
        }
        for case in self.scenario.cases:
            payload = json.loads((self.root / "baseline-output" / f"{case['id']}.json").read_text(encoding="utf-8"))
            result_path = actual_dir / f"unit-result-{case['id']}.json"
            dump(result_path, payload)
            self.claim["invocations"].append({
                "case_id": case["id"], "evidence_id": "declared-invocation-" + case["id"],
                "installation_evidence_id": "declared-installation",
                "plugin_sha256": file_digest(plugin),
                "input_sha256": file_digest(self.scenario.file(case["input"])),
                "result_path": result_path.relative_to(self.output).as_posix(),
                "result_sha256": file_digest(result_path), "evidence_files": files,
                "independence": {
                    "fresh_task": True, "creator_disabled": True,
                    "baseline_withheld": True, "goldens_withheld": True,
                },
            })
        self.descriptor = actual_dir / "unit-claims.json"
        dump(self.descriptor, self.claim)

    def test_complete_semantic_match_is_not_native_pass(self):
        receipt = compare_native_import(self.scenario, self.descriptor, self.output)
        self.assertTrue(receipt["all_supplied_payloads_match"])
        self.assertTrue(receipt["all_required_cases_supplied"])
        self.assertFalse(receipt["native_pass"])
        self.assertEqual(receipt["native"]["creation"], "native_creation_blocked")
        self.assertEqual(receipt["native"]["installation"], "not_run")
        self.assertEqual(receipt["native"]["observed"], [])
        self.assertEqual(receipt["declared"]["creation"]["evidence_id"], "declared-creation")
        self.assertEqual(receipt["observed_locally"]["plugin_inspection"]["execution"], "not_run")
        self.assertEqual(receipt["observed_locally"]["plugin_inspection"]["package_target"], "cowork-v1.28")

    def test_claude_source_archive_cannot_pass_the_native_plugin_gate(self):
        plugin = self.output / self.claim["plugin"]["path"]
        with zipfile.ZipFile(plugin, "w") as archive:
            archive.writestr(".claude-plugin/plugin.json", '{"name":"unit-fixture","version":"1.0.0"}')
        self.claim["plugin"]["sha256"] = file_digest(plugin)
        dump(self.descriptor, self.claim)
        with self.assertRaisesRegex(ContractError, "root manifest.json"):
            compare_native_import(self.scenario, self.descriptor, self.output)
        with self.assertRaises(ContractError):
            inspect_cowork_plugin(plugin)

    def test_wrong_version_or_missing_native_resources_are_rejected(self):
        plugin = self.output / self.claim["plugin"]["path"]
        with zipfile.ZipFile(plugin) as archive:
            original = {name: archive.read(name) for name in archive.namelist()}
        for variant in ("devPreview", "missing-skill", "missing-icon", "connector-without-tools", "dual-format"):
            contents = dict(original)
            manifest = json.loads(contents["manifest.json"])
            if variant == "devPreview":
                manifest["manifestVersion"] = "devPreview"
            elif variant == "missing-skill":
                del contents["skills/unit-skill/SKILL.md"]
            elif variant == "missing-icon":
                del contents["outline.png"]
            elif variant == "connector-without-tools":
                manifest["agentConnectors"] = [{"id": "unit", "displayName": "Unit",
                    "toolSource": {"remoteMcpServer": {"mcpServerUrl": "https://learn.microsoft.com/api/mcp"}}}]
            else:
                contents["plugin.json"] = b'{"name":"portable-format"}'
            contents["manifest.json"] = json.dumps(manifest).encode("utf-8")
            with zipfile.ZipFile(plugin, "w") as archive:
                for name, content in contents.items():
                    archive.writestr(name, content)
            with self.subTest(variant=variant), self.assertRaises(ContractError):
                inspect_cowork_plugin(plugin)

    def test_missing_case_not_hidden_by_matching_supplied_payload(self):
        self.claim["invocations"].pop()
        dump(self.descriptor, self.claim)
        receipt = compare_native_import(self.scenario, self.descriptor, self.output)
        self.assertTrue(receipt["all_supplied_payloads_match"])
        self.assertFalse(receipt["all_required_cases_supplied"])
        self.assertEqual(receipt["missing_cases"], ["negative-contradictory"])
        self.assertFalse(receipt["native_pass"])

    def test_supplied_status_cannot_upgrade_provenance(self):
        self.claim["provenance"] = "observed-native-pass"
        dump(self.descriptor, self.claim)
        with self.assertRaisesRegex(ContractError, "operator-declared"):
            compare_native_import(self.scenario, self.descriptor, self.output)

    def test_plugin_input_and_evidence_links_are_frozen(self):
        original = json.loads(json.dumps(self.claim))
        for change in (
            lambda item: item["plugin"].update(sha256="0" * 64),
            lambda item: item["invocations"][0].update(input_sha256="0" * 64),
            lambda item: item["installation"].update(creation_evidence_id="missing"),
            lambda item: item["invocations"][0].update(evidence_files=[]),
            lambda item: item["invocations"][0].update(evidence_id="declared-creation"),
            lambda item: item["invocations"][0]["independence"].update(fresh_task=False),
            lambda item: item["invocations"][0].update(result_path="../outside.json"),
        ):
            with self.subTest(change=change):
                altered = json.loads(json.dumps(original))
                change(altered)
                dump(self.descriptor, altered)
                with self.assertRaises(ContractError):
                    compare_native_import(self.scenario, self.descriptor, self.output)

    def test_output_missing_key_is_detected_without_executing_plugin(self):
        invocation = self.claim["invocations"][0]
        result_path = self.output.joinpath(*invocation["result_path"].split("/"))
        modify_json(result_path, lambda item: item["outputs"].clear())
        invocation["result_sha256"] = file_digest(result_path)
        dump(self.descriptor, self.claim)
        receipt = compare_native_import(self.scenario, self.descriptor, self.output)
        self.assertFalse(receipt["all_supplied_payloads_match"])
        self.assertFalse(receipt["native_pass"])
        self.assertEqual(receipt["comparisons"][0]["golden_differences"][0]["path"], "/outputs/doubled")

    def test_comparison_receipt_cannot_overwrite_supplied_evidence(self):
        protected = self.output / "unit-01" / "comparison.json"
        content = b"UNIT TEST: protected supplied observation"
        protected.write_bytes(content)
        self.claim["creation"]["evidence_files"] = [{
            "path": "unit-01/comparison.json", "sha256": file_digest(protected),
        }]
        dump(self.descriptor, self.claim)
        with self.assertRaisesRegex(ContractError, "must not overwrite"):
            compare_native_import(self.scenario, self.descriptor, self.output, replace=True)
        self.assertEqual(protected.read_bytes(), content)


if __name__ == "__main__":
    unittest.main()
