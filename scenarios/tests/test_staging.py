import unittest
from pathlib import Path
from unittest import mock

from scenarios._shared.common import ContractError, file_digest
from scenarios._shared.contract import load_scenario
from scenarios._shared.staging import CREATOR_INPUTS, check_staging, stage_creator_inputs
from scenarios.tests.fixtures import make_scenario, temporary_directory


class StagingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = temporary_directory()
        self.addCleanup(self.temporary.cleanup)
        self.root = make_scenario(Path(self.temporary.name) / "scenarios")
        self.scenario = load_scenario(self.root)
        video = self.root / "demo" / "baseline.webm"
        video.parent.mkdir()
        video.write_bytes(b"UNIT TEST ONLY; media validation is explicitly mocked")
        self.media = mock.patch(
            "scenarios._shared.staging.check_media",
            return_value={"sha256": file_digest(video)},
        )
        self.media.start()
        self.addCleanup(self.media.stop)

    def test_exact_allowlist_and_no_oracle_leak(self):
        manifest = stage_creator_inputs(self.scenario)
        staged = self.root / "validation" / "creator-input"
        actual = {path.relative_to(staged).as_posix() for path in staged.rglob("*") if path.is_file()}
        self.assertEqual(actual, set(CREATOR_INPUTS))
        self.assertEqual(len(manifest["files"]), 5)
        self.assertFalse((staged / "expected").exists())
        self.assertFalse((staged / "baseline.py").exists())
        self.assertFalse((staged / "mock-data" / "holdout-a.json").exists())
        self.assertEqual(manifest["native"]["creation"], "native_creation_blocked")
        self.assertEqual(check_staging(self.scenario), manifest)

    def test_unexpected_staging_file_is_not_silently_removed_or_shipped(self):
        stage_creator_inputs(self.scenario)
        extra = self.root / "validation" / "creator-input" / "oracle.json"
        extra.write_text('{"UNIT-ONLY": true}', encoding="utf-8")
        with self.assertRaisesRegex(ContractError, "contaminated"):
            stage_creator_inputs(self.scenario, replace=True)
        self.assertTrue(extra.exists())
        with self.assertRaises(ContractError):
            check_staging(self.scenario)

    def test_stale_staged_demo_is_rejected(self):
        stage_creator_inputs(self.scenario)
        staged = self.root / "validation" / "creator-input" / "mock-data" / "demo.json"
        staged.write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(ContractError, "stale or modified"):
            check_staging(self.scenario)

    def test_media_gate_is_mandatory(self):
        self.media.stop()
        with self.assertRaises(ContractError):
            stage_creator_inputs(self.scenario)


if __name__ == "__main__":
    unittest.main()
