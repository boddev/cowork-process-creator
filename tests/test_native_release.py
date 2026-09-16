import contextlib
import hashlib
import io
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from test_builder import native_metadata

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import build_release as release
import build_n00 as n00


class NativeReleaseTests(unittest.TestCase):
    def test_release_without_approved_metadata_never_falls_back(self):
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "release"
            with self.assertRaisesRegex(release.b.BuildError, "--metadata-dir"):
                release.build_release(destination)
            self.assertFalse(destination.exists())

    def test_all_built_plugin_archives_use_microsoft_manifest_not_claude_layout(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            metadata = root / "metadata"
            metadata.mkdir()
            identities = {}
            for name in ("cowork-process-creator", *release.examples.FAMILIES):
                path = native_metadata(metadata, name + ".json")
                identities[name] = json.loads(path.read_bytes())["app_id"]
            destination = root / "release"
            report = release.build_release(destination, metadata)
            self.assertEqual(report["creator_target"], "cowork-v1.28")
            self.assertEqual(report["native_acceptance"], "unverified")
            packages = {"cowork-process-creator": destination / "creator.zip"}
            packages.update({name: destination / "examples" / name / "plugin.zip" for name in release.examples.FAMILIES})
            for name, package in packages.items():
                with self.subTest(package=name), zipfile.ZipFile(package) as archive:
                    self.assertIsNone(archive.testzip())
                    self.assertTrue({"manifest.json", "color.png", "outline.png"} <= set(archive.namelist()))
                    self.assertFalse(any(".claude-plugin" in path or ".cursor-plugin" in path for path in archive.namelist()))
                    manifest = json.loads(archive.read("manifest.json"))
                    self.assertEqual(manifest["manifestVersion"], "1.28")
                    self.assertEqual(manifest["$schema"], release.b.SCHEMA)
                    self.assertEqual(manifest["id"], identities[name])
                    for skill in manifest["agentSkills"]:
                        self.assertIn(skill["folder"].removeprefix("./") + "/SKILL.md", archive.namelist())
            self.assertEqual(hashlib.sha256(packages["cowork-process-creator"].read_bytes()).hexdigest(), report["creator_sha256"])
            release.build_release(destination, metadata)

    def test_distinct_packages_cannot_share_one_supplied_identity(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            original = native_metadata(root, "cowork-process-creator.json").read_bytes()
            for name in release.examples.FAMILIES:
                (root / (name + ".json")).write_bytes(original)
            with self.assertRaisesRegex(release.b.BuildError, "distinct supplied app_id"):
                release.release_metadata(root)

    def test_n00_entry_point_also_builds_only_native_packages(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            metadata = root / "metadata"
            metadata.mkdir()
            for name in ("cowork-process-creator", "ready-items-report"):
                native_metadata(metadata, name + ".json")
            destination = root / "n00"
            arguments = ["build_n00.py", "--output", str(destination), "--metadata-dir", str(metadata)]
            with mock.patch.object(sys, "argv", arguments), contextlib.redirect_stdout(io.StringIO()):
                n00.main()
            for name in ("creator-n00", "output-n00"):
                with zipfile.ZipFile(destination / (name + ".zip")) as archive:
                    manifest = json.loads(archive.read("manifest.json"))
                    self.assertEqual(manifest["manifestVersion"], "1.28")
                    self.assertEqual(manifest["$schema"], release.b.SCHEMA)
                    self.assertNotIn(".claude-plugin/plugin.json", archive.namelist())
                report = json.loads((destination / (name + ".report.json")).read_bytes())
                self.assertEqual(report["target"], "cowork-v1.28")
                self.assertEqual(report["host_acceptance"], "unverified")

    def test_n00_rejects_missing_or_duplicate_identity_before_creating_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            destination = root / "n00"
            arguments = ["build_n00.py", "--output", str(destination)]
            with mock.patch.object(sys, "argv", arguments), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as raised:
                    n00.main()
            self.assertEqual(raised.exception.code, 2)
            self.assertFalse(destination.exists())
            metadata = root / "metadata"
            metadata.mkdir()
            original = native_metadata(metadata, "cowork-process-creator.json").read_bytes()
            (metadata / "ready-items-report.json").write_bytes(original)
            arguments += ["--metadata-dir", str(metadata)]
            with mock.patch.object(sys, "argv", arguments):
                with self.assertRaisesRegex(ValueError, "distinct supplied app_id"):
                    n00.main()
            self.assertFalse(destination.exists())


if __name__ == "__main__":
    unittest.main()
