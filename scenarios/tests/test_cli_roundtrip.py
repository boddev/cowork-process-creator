"""One real local baseline -> video -> staging -> catalog smoke, never native."""
import contextlib
import importlib.util
import io
import json
import os
import tempfile
import unittest
from pathlib import Path

from scenarios._shared.cli import main
from scenarios._shared.common import ContractError, file_digest
from scenarios._shared.contract import discover, load_scenario
from scenarios._shared.staging import check_media, check_staging
from scenarios.tests.fixtures import REPO, dump, make_scenario

ENCODER = Path(r"C:\Users\bodonnell\AppData\Local\ms-playwright\ffmpeg-1011\ffmpeg-win64.exe")


class CliRoundtripTests(unittest.TestCase):
    @unittest.skipUnless(os.environ.get("SCENARIO_MEDIA_SMOKE") == "1", "Set SCENARIO_MEDIA_SMOKE=1 for actual local media")
    def test_actual_baseline_media_staging_and_catalog(self):
        if importlib.util.find_spec("PIL") is None or not ENCODER.is_file():
            self.skipTest("Already-installed Pillow and the known cached encoder are required")
        local = REPO / "scenarios" / ".local"
        local.mkdir(exist_ok=True)
        before_ids = [scenario.id for scenario in discover(REPO / "scenarios")]
        with tempfile.TemporaryDirectory(prefix="cli-fixture-only-", dir=local) as temporary:
            corpus = Path(temporary) / "scenarios"
            root = make_scenario(corpus)
            scenario = load_scenario(root)
            prefix = ["--root", str(corpus)]
            expected_hashes = {case["id"]: file_digest(scenario.file(case["expected"])) for case in scenario.cases}
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(prefix + ["validate", "--all"]), 0)
                self.assertEqual(main(prefix + ["run", "--all", "--replace-generated"]), 0)
                self.assertEqual(main(prefix + ["render", "--all", "--replace-generated", "--ffmpeg", str(ENCODER)]), 0)
                self.assertEqual(main(prefix + ["stage", "--all", "--replace-generated"]), 0)
                self.assertEqual(main(prefix + ["report", "--all"]), 0)
            media = check_media(scenario)
            self.assertEqual(media["duration_seconds"], 30)
            self.assertEqual(media["decoded_frame_count"], 60)
            self.assertEqual(len(media["timeline"]), 6)
            self.assertEqual(media["display"]["truncated_source_pointers"], [])
            self.assertEqual(len(check_staging(scenario)["files"]), 5)
            catalog = json.loads((corpus / "catalog.json").read_text(encoding="utf-8"))
            self.assertTrue(catalog["local_corpus_ready"])
            self.assertFalse(catalog["native_complete"])
            self.assertEqual(catalog["coverage"]["scenario_count"], 1)
            self.assertEqual(catalog["coverage"]["case_count"], 5)
            output = corpus.parent / "output"
            status = json.loads((output / "status.json").read_text(encoding="utf-8"))
            self.assertFalse(status["native_complete"])
            self.assertIsNone(status["scenarios"][0]["plugin"])
            self.assertFalse(any(output.rglob("*.zip")))
            for case in scenario.cases:
                self.assertEqual(file_digest(scenario.file(case["expected"])), expected_hashes[case["id"]])
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(prefix + ["run", "--all", "--replace-generated"]), 0)
            self.assertEqual(check_media(scenario)["sha256"], media["sha256"])
            media_path = root / "demo" / "baseline.media.json"
            altered = json.loads(media_path.read_text(encoding="utf-8"))
            altered["fidelity"]["frames"][0]["mean_pixel_error"] = 100
            dump(media_path, altered)
            with self.assertRaisesRegex(ContractError, "fidelity error"):
                check_media(scenario)
        self.assertEqual([scenario.id for scenario in discover(REPO / "scenarios")], before_ids)


if __name__ == "__main__":
    unittest.main()
