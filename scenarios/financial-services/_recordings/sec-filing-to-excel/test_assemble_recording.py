import copy
import importlib.util
import json
from pathlib import Path
import unittest


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("sec_recording_editor", HERE / "assemble_recording.py")
EDITOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(EDITOR)


class RecordingPlanTests(unittest.TestCase):
    def setUp(self):
        self.plan = json.loads((HERE / "edit.json").read_text(encoding="utf-8"))

    def test_real_edit_plan_has_all_eight_chapters(self):
        EDITOR.check_plan(self.plan)
        self.assertEqual({clip["chapter"] for clip in self.plan["clips"]}, set(range(1, 9)))

    def test_rejects_reverse_source_order(self):
        self.plan["clips"][6]["start"] = 100
        with self.assertRaises(ValueError):
            EDITOR.check_plan(self.plan)

    def test_rejects_nonfinite_source_interval(self):
        self.plan["clips"][-1]["end"] = float("inf")
        with self.assertRaises(ValueError):
            EDITOR.check_plan(self.plan)

    def test_rejects_private_or_traversing_input_paths(self):
        for name in ("..\\capture.webm", "../capture.webm", "C:\\private\\capture.webm"):
            with self.subTest(name=name):
                plan = copy.deepcopy(self.plan)
                plan["sources"]["excel"]["file"] = name
                with self.assertRaises(ValueError):
                    EDITOR.check_plan(plan)

    def test_rejects_profile_area_in_excel_crop(self):
        self.plan["clips"][-1]["crop"][2] = 2888
        with self.assertRaises(ValueError):
            EDITOR.check_plan(self.plan)

    def test_rejects_crop_outside_original_capture(self):
        self.plan["clips"][0]["crop"][2] = 4000
        with self.assertRaises(ValueError):
            EDITOR.check_plan(self.plan)

    def test_webvtt_timecode(self):
        self.assertEqual(EDITOR.timecode(198.2), "00:03:18.200")
        self.assertEqual(EDITOR.timecode(3600), "01:00:00.000")

    def test_public_movie_matches_its_recording_evidence(self):
        evidence = json.loads((HERE / "demo" / "recording-evidence.json").read_text(encoding="utf-8"))
        output = evidence["output"]
        self.assertEqual(EDITOR.digest(HERE / "demo" / output["file"]), output["sha256"])
        self.assertEqual(sum(clip["decoded_frames"] for clip in evidence["timeline"]), output["frames"])
        self.assertEqual(output["frames"] / output["fps"], output["duration_seconds"])
        self.assertEqual(evidence["timeline"][-1]["output_end"], output["duration_seconds"])
        self.assertFalse(evidence["editing"]["generated_application_frames"])
        self.assertEqual(evidence["native_cowork"]["invocation"], "not-attempted")


if __name__ == "__main__":
    unittest.main()
