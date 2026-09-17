import importlib.util
from pathlib import Path
import unittest


SPEC = importlib.util.spec_from_file_location("sec_preview", Path(__file__).with_name("serve_preview.py"))
PREVIEW = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PREVIEW)


class ByteRangeTests(unittest.TestCase):
    def test_explicit_and_open_ended_ranges(self):
        self.assertEqual(PREVIEW.byte_range("bytes=0-99", 1000), (0, 99))
        self.assertEqual(PREVIEW.byte_range("bytes=400-", 1000), (400, 999))

    def test_suffix_ranges(self):
        self.assertEqual(PREVIEW.byte_range("bytes=-25", 1000), (975, 999))
        self.assertEqual(PREVIEW.byte_range("bytes=-2000", 1000), (0, 999))

    def test_clamps_the_end_to_the_actual_file(self):
        self.assertEqual(PREVIEW.byte_range("bytes=900-5000", 1000), (900, 999))

    def test_rejects_invalid_or_unsupported_ranges(self):
        for header in ("bytes=-", "bytes=-0", "bytes=1000-", "bytes=20-10",
                       "bytes=0-10,20-30", "items=0-10", "bytes=a-b"):
            with self.subTest(header=header), self.assertRaises(ValueError):
                PREVIEW.byte_range(header, 1000)

    def test_empty_file_has_no_satisfiable_range(self):
        with self.assertRaises(ValueError):
            PREVIEW.byte_range("bytes=0-", 0)

    def test_private_recordings_and_scripts_are_not_served(self):
        self.assertNotIn("/sec-excel-work.webm", PREVIEW.PUBLIC_PATHS)
        self.assertNotIn("/assemble_recording.py", PREVIEW.PUBLIC_PATHS)
        self.assertNotIn("/../source.json", PREVIEW.PUBLIC_PATHS)
        self.assertIn("/demo/workflow.webm", PREVIEW.PUBLIC_PATHS)


if __name__ == "__main__":
    unittest.main()
