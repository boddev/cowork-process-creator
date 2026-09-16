"""Fixture-only renderer tests; no counted scenario, live system, or model API.

The optional real encode/decode test uses only the explicitly known cached
encoder and already-installed Pillow. Set SCENARIO_MEDIA_SMOKE=1 to run it.
All filesystem fixtures and renderer staging stay under scenarios/.local.
"""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
from types import SimpleNamespace
import unittest
from unittest import mock
import uuid

from scenarios._shared import media


_KNOWN_ENCODER = Path(r"C:\Users\bodonnell\AppData\Local\ms-playwright\ffmpeg-1011\ffmpeg-win64.exe")
_INPUT_HASH = hashlib.sha256(b"fixture-only input, not a sector scenario").hexdigest()


def fixture_trace() -> dict:
    captions = {
        "input": "Fixture-only input rows expose two invented source identifiers.",
        "validation": "Fixture-only validation records the two supplied identifiers and scalar values.",
        "join": "Fixture-only cross-reference rows preserve both invented identifiers.",
        "decision": "Fixture-only decision rows show the declared review state.",
        "exception": "Fixture-only exception rows identify the second invented record for review.",
        "output": "Fixture-only completed outputs retain both invented records and their declared states.",
    }
    return {
        "schema_version": 1, "provenance": "synthetic-local-baseline",
        "scenario_id": "fixture-only-trace", "input_sha256": _INPUT_HASH,
        "events": [
            {
                "sequence": index + 1, "step_id": f"fixture-{kind}", "kind": kind,
                "caption": captions[kind], "facts": {"fixture_only": True, "row_count": 2},
                "tables": [{
                    "title": f"{kind.title()} fixture rows", "columns": ["fixture_id", "state", "value"],
                    "rows": [["FIXTURE-01", kind, 1], ["FIXTURE-02", "review", 2]],
                    "total_rows": 2, "highlight_rows": [1],
                }],
            }
            for index, kind in enumerate(media.KINDS)
        ],
    }


def fixture_evidence(trace: dict) -> dict:
    return {
        "scenario_id": trace["scenario_id"], "case_id": "demo", "input_sha256": trace["input_sha256"],
        "result_sha256": hashlib.sha256(b"fixture-only result").hexdigest(),
        "trace_sha256": hashlib.sha256(json.dumps(trace, indent=2).encode("utf-8")).hexdigest(),
        "golden_sha256": hashlib.sha256(b"fixture-only declared golden").hexdigest(),
        "baseline_py_sha256": hashlib.sha256(b"fixture-only declared baseline").hexdigest(),
        "baseline_command": [sys.executable, "-B", "fixture-only-baseline.py", "--input", r"mock-data\demo.json"],
    }


def metrics(style: str, text: str) -> float:
    size = media._STYLES[style][0]
    return sum(size * (0.95 if character in "MW" else 0.5) for character in text)


class TraceValidationTests(unittest.TestCase):
    def test_valid_evidence_is_a_declaration_not_a_canonical_hash_requirement(self):
        trace = fixture_trace()
        evidence = fixture_evidence(trace)
        self.assertNotEqual(evidence["trace_sha256"], hashlib.sha256(media._json_bytes(trace)).hexdigest())
        media._validate_trace(trace)
        media._validate_evidence(evidence, trace)

    def test_bad_trace_shapes_and_values(self):
        mutations = [
            ("extra envelope", lambda t: t.update({"native_proof": True})),
            ("boolean version", lambda t: t.update({"schema_version": True})),
            ("wrong provenance", lambda t: t.update({"provenance": "live-cowork"})),
            ("invalid ID", lambda t: t.update({"scenario_id": "../elsewhere"})),
            ("bad input hash", lambda t: t.update({"input_sha256": "not-a-hash"})),
            ("empty events", lambda t: t.update({"events": []})),
            ("event not an object", lambda t: t["events"].__setitem__(0, None)),
            ("bad sequence", lambda t: t["events"][0].update({"sequence": 2})),
            ("boolean sequence", lambda t: t["events"][0].update({"sequence": True})),
            ("bad step ID", lambda t: t["events"][0].update({"step_id": "Uppercase"})),
            ("unknown kind", lambda t: t["events"][0].update({"kind": "recording"})),
            ("nonstring kind", lambda t: t["events"][0].update({"kind": []})),
            ("empty caption", lambda t: t["events"][0].update({"caption": "  "})),
            ("long caption", lambda t: t["events"][0].update({"caption": "x" * 261})),
            ("invalid Unicode", lambda t: t["events"][0].update({"caption": "\ud800"})),
            ("too many facts", lambda t: t["events"][0].update({"facts": {str(i): i for i in range(7)}})),
            ("nested fact", lambda t: t["events"][0].update({"facts": {"nested": {"x": 1}}})),
            ("nonfinite fact", lambda t: t["events"][0].update({"facts": {"value": float("nan")}})),
            ("blank fact name", lambda t: t["events"][0].update({"facts": {" ": 1}})),
            ("no tables", lambda t: t["events"][0].update({"tables": []})),
            ("too many tables", lambda t: t["events"][0]["tables"].extend(copy.deepcopy(t["events"][0]["tables"]) * 2)),
            ("wrong table keys", lambda t: t["events"][0]["tables"][0].update({"url": "untrusted"})),
            ("empty title", lambda t: t["events"][0]["tables"][0].update({"title": ""})),
            ("empty columns", lambda t: t["events"][0]["tables"][0].update({"columns": []})),
            ("too many columns", lambda t: t["events"][0]["tables"][0].update({"columns": list("abcdefg")})),
            ("empty column name", lambda t: t["events"][0]["tables"][0]["columns"].__setitem__(0, "")),
            ("ragged row", lambda t: t["events"][0]["tables"][0]["rows"].append(["one cell"])),
            ("nested cell", lambda t: t["events"][0]["tables"][0]["rows"][0].__setitem__(0, [])),
            ("infinite cell", lambda t: t["events"][0]["tables"][0]["rows"][0].__setitem__(0, float("inf"))),
            ("too many rows", lambda t: t["events"][0]["tables"][0].update({"rows": [[1, 2, 3]] * 9, "total_rows": 9})),
            ("understated rows", lambda t: t["events"][0]["tables"][0].update({"total_rows": 1})),
            ("boolean total", lambda t: t["events"][0]["tables"][0].update({"total_rows": True})),
            ("out of range highlight", lambda t: t["events"][0]["tables"][0].update({"highlight_rows": [2]})),
            ("negative highlight", lambda t: t["events"][0]["tables"][0].update({"highlight_rows": [-1]})),
            ("boolean highlight", lambda t: t["events"][0]["tables"][0].update({"highlight_rows": [True]})),
            ("duplicate highlight", lambda t: t["events"][0]["tables"][0].update({"highlight_rows": [1, 1]})),
        ]
        for name, mutate in mutations:
            with self.subTest(name=name):
                trace = fixture_trace()
                mutate(trace)
                with self.assertRaises(media.MediaError):
                    media._validate_trace(trace)

    def test_too_few_missing_and_incorrect_boundary_stages(self):
        for mutation in ("five", "missing join", "wrong first", "wrong last"):
            with self.subTest(mutation=mutation):
                trace = fixture_trace()
                if mutation == "five":
                    trace["events"].pop(2)
                    for index, event in enumerate(trace["events"], 1):
                        event["sequence"] = index
                elif mutation == "missing join":
                    trace["events"][2]["kind"] = "validation"
                elif mutation == "wrong first":
                    trace["events"][0]["kind"], trace["events"][1]["kind"] = "validation", "input"
                else:
                    trace["events"][-1]["kind"], trace["events"][-2]["kind"] = "exception", "output"
                with self.assertRaises(media.MediaError):
                    media._validate_trace(trace)

    def test_more_than_six_states_and_empty_exception_table_are_supported(self):
        trace = fixture_trace()
        event = copy.deepcopy(trace["events"][2])
        event["step_id"] = "fixture-second-join"
        trace["events"].insert(3, event)
        for index, event in enumerate(trace["events"], 1):
            event["sequence"] = index
        trace["events"][-2]["tables"][0].update({"rows": [], "total_rows": 0, "highlight_rows": []})
        media._validate_trace(trace)
        self.assertEqual(len(trace["events"]), 7)

    def test_excessive_events_are_rejected_before_rendering(self):
        trace = fixture_trace()
        for _ in range(media.MAX_DISPLAY_PAGES - len(trace["events"]) + 1):
            trace["events"].insert(-1, copy.deepcopy(trace["events"][2]))
        for index, event in enumerate(trace["events"], 1):
            event["sequence"] = index
        with self.assertRaisesRegex(media.MediaError, "too many events"):
            media._validate_trace(trace)

    def test_bad_evidence(self):
        mutations = [
            lambda e: e.pop("golden_sha256"),
            lambda e: e.update({"native_proof": True}),
            lambda e: e.update({"scenario_id": "another-fixture"}),
            lambda e: e.update({"case_id": "holdout-a"}),
            lambda e: e.update({"input_sha256": "0" * 64}),
            lambda e: e.update({"result_sha256": "A" * 64}),
            lambda e: e.update({"trace_sha256": 123}),
            lambda e: e.update({"golden_sha256": "abc"}),
            lambda e: e.update({"baseline_py_sha256": None}),
            lambda e: e.update({"baseline_command": "python baseline.py"}),
            lambda e: e.update({"baseline_command": []}),
            lambda e: e.update({"baseline_command": ["python", ""]}),
            lambda e: e.update({"baseline_command": ["python", None]}),
            lambda e: e.update({"baseline_command": ["python", "bad\0argument"]}),
        ]
        for index, mutate in enumerate(mutations):
            with self.subTest(index=index):
                trace = fixture_trace()
                evidence = fixture_evidence(trace)
                mutate(evidence)
                with self.assertRaises(media.MediaError):
                    media._validate_evidence(evidence, trace)

    def test_import_does_not_load_pillow_or_run_an_encoder(self):
        name = "_fixture_media_without_pillow"
        spec = importlib.util.spec_from_file_location(name, media.__file__)
        module = importlib.util.module_from_spec(spec)
        original_import = __import__

        def guarded_import(package, *args, **kwargs):
            if package == "PIL" or package.startswith("PIL."):
                raise AssertionError("Pillow was imported during core tool discovery")
            return original_import(package, *args, **kwargs)

        sys.modules[name] = module
        try:
            with mock.patch("builtins.__import__", side_effect=guarded_import), mock.patch("subprocess.run") as run:
                spec.loader.exec_module(module)
                run.assert_not_called()
        finally:
            sys.modules.pop(name, None)


class LayoutTests(unittest.TestCase):
    def test_all_rows_are_paged_in_order_without_overlapping_text(self):
        trace = fixture_trace()
        table = trace["events"][0]["tables"][0]
        table.update({
            "columns": [f"column-{index}-" + "W" * 50 for index in range(6)],
            "rows": [[f"fixture-{row}-{column}-" + "W" * 80 for column in range(6)] for row in range(8)],
            "total_rows": 11, "highlight_rows": [0, 7],
        })
        trace["events"][0]["tables"].append(copy.deepcopy(table))
        trace["events"][0]["caption"] = "W" * 260
        trace["events"][0]["facts"] = {f"fact-{index}": "W" * 200 for index in range(6)}
        pages = media._layout_trace(trace, "W" * 300, metrics)
        first_event = [page for page in pages if page["event_index"] == 0]
        self.assertGreaterEqual(len(first_event), 4)
        for table_index in range(2):
            indices = [
                row["index"] for page in first_event if page["table_index"] == table_index
                for row in page["rows"]
            ]
            self.assertEqual(indices, list(range(8)))
        sources = set()
        for page in pages:
            blocks = page["blocks"] + [cell for row in page["rows"] for cell in row["cells"]]
            for block in blocks:
                self.assertGreaterEqual(block.x, 40)
                self.assertLessEqual(block.x + block.width, media.WIDTH - 40)
                self.assertLessEqual(block.bottom, 792)
                for line in block.lines:
                    self.assertLessEqual(metrics(block.style, line), block.width)
                if block.truncated:
                    self.assertTrue(block.lines[-1].endswith(media.TRUNCATION))
                    sources.add(block.source)
            end = page["body_top"]
            for row in page["rows"]:
                self.assertGreaterEqual(row["y"], end)
                end = row["y"] + row["height"]
                self.assertLessEqual(end, 784)
                self.assertTrue(all(cell.bottom <= end for cell in row["cells"]))
        self.assertIn("report:/title", sources)
        self.assertIn("/events/0/caption", sources)
        self.assertIn("/events/0/facts/fact-5", sources)
        self.assertIn("/events/0/tables/1/rows/7/5", sources)

    def test_real_scalar_values_and_subset_labels_are_not_summary_slides(self):
        trace = fixture_trace()
        table = trace["events"][0]["tables"][0]
        table.update({"columns": ["text", "number", "flag", "absent"],
                      "rows": [["FIXTURE-01", 12.5, False, None]], "total_rows": 1, "highlight_rows": []})
        page = media._layout_trace(trace, "Fixture title", metrics)[0]
        self.assertEqual([cell.lines for cell in page["rows"][0]["cells"]],
                         [('"FIXTURE-01"',), ("12.5",), ("false",), ("null",)])
        text = " ".join(line for block in page["blocks"] for line in block.lines)
        self.assertNotIn("not included", text)
        table["total_rows"] = 9
        page = media._layout_trace(trace, "Fixture title", metrics)[0]
        text = " ".join(line for block in page["blocks"] for line in block.lines)
        self.assertIn("9 total, 8 not included in trace", text)

    def test_empty_table_has_one_explicit_page(self):
        trace = fixture_trace()
        trace["events"][0]["tables"][0].update({"rows": [], "total_rows": 0, "highlight_rows": []})
        page = media._layout_trace(trace, "Fixture title", metrics)[0]
        self.assertEqual(page["rows"], [])
        self.assertIn("Empty state", " ".join(line for block in page["blocks"] for line in block.lines))

    def test_control_and_unsupported_font_characters_are_losslessly_escaped(self):
        displayed = media._display_text("row\n\u65e5\u672c\u8a9e\t\\")
        self.assertEqual(displayed, r"row\n\u65e5\u672c\u8a9e\t\\")
        self.assertEqual(json.loads('"' + displayed + '"'), "row\n\u65e5\u672c\u8a9e\t\\")
        self.assertNotIn("\n", displayed)

    def test_short_caption_is_not_truncated_and_long_words_are_explicit(self):
        lines, truncated = media._fit_text("A complete caption.", 200, 3, len)
        self.assertEqual(lines, ("A complete caption.",))
        self.assertFalse(truncated)
        lines, truncated = media._fit_text("X" * 120, 30, 2, len)
        self.assertTrue(truncated)
        self.assertTrue(lines[-1].endswith(media.TRUNCATION))
        self.assertTrue(all(len(line) <= 30 for line in lines))

    def test_legacy_bitmap_font_is_scaled_to_readable_dimensions(self):
        bitmap = SimpleNamespace(getbbox=lambda text: (0, 0, 6 * len(text), 9))

        for failure in (TypeError, ImportError, OSError):
            with self.subTest(failure=failure):
                def load_default(**kwargs):
                    if kwargs:
                        raise failure("scalable default unavailable")
                    return bitmap

                fonts, descriptions = media._load_fonts(SimpleNamespace(load_default=load_default))
                for style, font in fonts.items():
                    self.assertGreaterEqual(font.scale, 2)
                    self.assertGreaterEqual(descriptions[style]["rendered_probe_height"], media._STYLES[style][0] * 0.7)
                    self.assertLessEqual(descriptions[style]["rendered_probe_height"], media._STYLES[style][1])
                self.assertLessEqual(fonts["banner"].measure(media.LABEL), 1520)
        with self.assertRaisesRegex(media.MediaError, "no external fonts"):
            media._load_fonts(SimpleNamespace(load_default=mock.Mock(side_effect=OSError("unavailable"))))

    def test_timeline_is_contiguous_and_supports_many_events(self):
        for extra in (0, 14, media.MAX_DISPLAY_PAGES - 6):
            with self.subTest(extra=extra):
                trace = fixture_trace()
                for index in range(extra):
                    event = copy.deepcopy(trace["events"][2])
                    event["step_id"] = f"fixture-extra-{index}"
                    trace["events"].insert(-1, event)
                for index, event in enumerate(trace["events"], 1):
                    event["sequence"] = index
                pages = media._layout_trace(trace, "Fixture title", metrics)
                timeline, count = media._schedule(trace, pages)
                self.assertGreaterEqual(count / media.FPS, 30)
                self.assertLessEqual(count / media.FPS, 90)
                self.assertEqual(len(timeline), len(trace["events"]))
                self.assertEqual([event["event_sequence"] for event in timeline],
                                 list(range(1, len(trace["events"]) + 1)))
                self.assertEqual(timeline[0]["start_seconds"], 0)
                self.assertEqual(timeline[-1]["end_seconds_exclusive"], count / media.FPS)
                self.assertEqual(sum(page["frame_count"] for page in pages), count)
                for previous, current in zip(timeline, timeline[1:]):
                    self.assertEqual(previous["end_seconds_exclusive"], current["start_seconds"])
                    self.assertEqual(previous["end_frame_exclusive"], current["start_frame"])
                self.assertTrue(all(page["frame_count"] >= 2 for page in pages))

    def test_overfull_timeline_refuses_instead_of_omitting_pages(self):
        with self.assertRaisesRegex(media.MediaError, "every supplied row"):
            media._schedule(fixture_trace(), [{}] * 91)


class DecoderValidationTests(unittest.TestCase):
    def test_correct_header_and_mismatched_metadata(self):
        header = (
            "Input #0, matroska,webm, from 'fixture.webm':\n"
            "  Duration: 00:00:30.00, start: 0.000000, bitrate: 1000 kb/s\n"
            "  Stream #0:0: Video: vp8, yuv420p(progressive), 1600x900, 2 fps, 2 tbr, 1k tbn\n"
        )
        self.assertEqual(media._header_details(header, 60)["duration_seconds"], 30)
        bad_headers = [
            header.replace("30.00", "29.50"), header.replace("2 fps", "3 fps"),
            header.replace("1600x900", "1200x640"), header.replace("vp8", "h264"),
            header.replace("Duration:", "Unknown:"), header + "  Stream #0:1: Audio: opus\n",
            header + "  creation_time: 2026-01-01T00:00:00Z\n",
            header + "  Stream #0:1: Video: vp8, 1600x900, 2 fps\n",
        ]
        for value in bad_headers:
            with self.subTest(header=value), self.assertRaises(media.MediaError):
                media._header_details(value, 60)

    def test_every_frame_has_a_unique_checkable_order_position(self):
        count = 180
        previous = -1
        for index in range(count):
            left = media._cursor_left(index, count)
            pixels = [(213, 224, 235)] * media.WIDTH
            pixels[left:left + media._CURSOR_WIDTH] = [media._CURSOR] * media._CURSOR_WIDTH
            position = media._verify_cursor(pixels, index, count)
            self.assertGreater(position, previous)
            previous = position
            if index:
                with self.assertRaisesRegex(media.MediaError, "frame-order"):
                    media._verify_cursor(pixels, index - 1, count)
        with self.assertRaisesRegex(media.MediaError, "no visible progress cursor"):
            media._verify_cursor([(0, 0, 0)] * media.WIDTH, 0, count)

    def test_encoder_errors_are_actionable_without_fallback_tools(self):
        with mock.patch.object(media.subprocess, "run", return_value=subprocess.CompletedProcess(
            ["explicit-encoder"], 1, b"", b"missing requested codec"
        )) as run:
            with self.assertRaisesRegex(media.MediaError, "missing requested codec"):
                media._run_command(["explicit-encoder", "-version"])
            run.assert_called_once()
            self.assertNotIn("shell", run.call_args.kwargs)
        with mock.patch.object(media.subprocess, "run", side_effect=FileNotFoundError("missing")):
            with self.assertRaisesRegex(media.MediaError, "supplied existing FFmpeg"):
                media._run_command(["explicit-encoder"])
        with mock.patch.object(media.subprocess, "run", side_effect=subprocess.TimeoutExpired(["encoder"], 600)):
            with self.assertRaises(media.MediaError):
                media._run_command(["explicit-encoder"])


class LocalFileTests(unittest.TestCase):
    def setUp(self):
        self.root = media._ROOT / ".local" / ("media-tests-" + uuid.uuid4().hex)
        self.root.mkdir(parents=True)
        self.output = self.root / "fixture-only" / "demo" / "baseline.webm"
        self.report_path = self.output.with_name("baseline.media.json")
        self.stage = self.root / "publish-stage"
        self.stage.mkdir()

    def tearDown(self):
        shutil.rmtree(self.root)

    def staged_pair(self, video: bytes = b"fixture-only new video") -> tuple[Path, Path]:
        staged_video = self.stage / "baseline.webm"
        staged_report = self.stage / "baseline.media.json"
        staged_video.write_bytes(video)
        staged_report.write_bytes(media._json_bytes({
            "schema_version": 1, "producer": media.PRODUCER, "artifact_kind": media.ARTIFACT_KIND,
            "sha256": hashlib.sha256(video).hexdigest(), "fixture_only": True,
        }, pretty=True))
        self.output.parent.mkdir(parents=True, exist_ok=True)
        return staged_video, staged_report

    def test_output_is_exact_and_confined_to_scenarios(self):
        self.assertEqual(media._output_paths(self.output), (self.output, self.report_path))
        invalid = [
            self.output.with_name("other.webm"),
            self.output.with_name("baseline.mp4"),
            self.root / "not-demo" / "baseline.webm",
            self.root / "demo" / ".." / "demo" / "baseline.webm",
            self.root / ".. " / "demo" / "baseline.webm",
            self.root / "alias." / "demo" / "baseline.webm",
            self.root / "stream:alias" / "demo" / "baseline.webm",
            self.root / "NUL" / "demo" / "baseline.webm",
            media._ROOT.parent / "output" / "demo" / "baseline.webm",
        ]
        for path in invalid:
            with self.subTest(path=path), self.assertRaises(media.MediaError):
                media._output_paths(path)
        self.assertFalse(self.output.parent.exists())

    def test_decoding_requires_every_consecutively_numbered_frame(self):
        (self.stage / "decoded-0002.png").write_bytes(b"fixture-only placeholder, not decoded pixels")
        with self.assertRaisesRegex(media.MediaError, "Expected 2 decoded frames, found 1"):
            media._validate_decoded(self.stage, [{}, {}], None)
        with self.assertRaisesRegex(media.MediaError, "numbering is not consecutive"):
            media._validate_decoded(self.stage, [{}], None)

    def test_decoded_fidelity_checks_whole_data_and_label_regions(self):
        (self.stage / "decoded-0001.png").write_bytes(b"fixture-only decoder mock")
        image = mock.MagicMock()
        image.__enter__.return_value = image
        image.size = (media.WIDTH, media.HEIGHT)
        image.convert.return_value = image
        image.tobytes.return_value = b"fixture-only RGB mock"
        difference = mock.Mock()
        difference.crop.return_value = difference
        stats = mock.Mock()
        pillow = SimpleNamespace(
            Image=SimpleNamespace(open=mock.Mock(return_value=image)),
            ImageChops=SimpleNamespace(difference=mock.Mock(return_value=difference)),
            ImageStat=SimpleNamespace(Stat=stats),
        )
        for errors in ((6.01, 0, 0), (0, 6.01, 0), (0, 0, 6.01)):
            with self.subTest(errors=errors):
                stats.side_effect = [SimpleNamespace(mean=[error] * 3) for error in errors]
                records = [{"source_rgb_sha256": hashlib.sha256(b"fixture-only RGB mock").hexdigest()}]
                with mock.patch.object(media, "_verify_cursor") as cursor:
                    with self.assertRaisesRegex(media.MediaError, "RGB fidelity threshold"):
                        media._validate_decoded(self.stage, records, pillow)
                    cursor.assert_not_called()
        with self.assertRaisesRegex(media.MediaError, "Source frame changed"):
            media._validate_decoded(self.stage, [{"source_rgb_sha256": "0" * 64}], pillow)

    def test_missing_encoder_does_not_import_pillow_or_run_any_process(self):
        trace = fixture_trace()
        with mock.patch.object(media, "_run_command") as run:
            with self.assertRaisesRegex(media.MediaError, "no install or download"):
                media.render_trace_video(trace, self.output, title="Fixture-only",
                                         ffmpeg=self.root / "missing-encoder.exe", evidence=fixture_evidence(trace))
            run.assert_not_called()
        self.assertFalse(self.output.parent.exists())

    def test_directories_cannot_be_video_or_encoder_files(self):
        self.output.mkdir(parents=True)
        with self.assertRaisesRegex(media.MediaError, "wrong file type"):
            media._output_paths(self.output)
        with self.assertRaisesRegex(media.MediaError, "wrong file type"):
            media._encoder_path(self.stage)

    def test_reparse_parent_is_rejected_before_following_it(self):
        real_lstat = Path.lstat

        def lstat(path, *args, **kwargs):
            if path == self.root:
                return SimpleNamespace(st_mode=stat.S_IFDIR, st_file_attributes=1024)
            return real_lstat(path, *args, **kwargs)

        with mock.patch.object(Path, "lstat", lstat):
            with self.assertRaisesRegex(media.MediaError, "Symlinks, junctions"):
                media._output_paths(self.output)

    def test_symlink_output_or_parent_is_refused(self):
        target = self.root / "target"
        target.mkdir()
        target_file = target / "baseline.webm"
        target_file.write_bytes(b"fixture-only original")
        self.output.parent.mkdir(parents=True)
        try:
            self.output.symlink_to(target_file)
        except (OSError, NotImplementedError):
            self.skipTest("Creating symlinks is not permitted on this machine")
        with self.assertRaisesRegex(media.MediaError, "Symlinks"):
            media._output_paths(self.output)
        self.output.unlink()
        self.output.parent.rmdir()
        self.output.parent.symlink_to(target, target_is_directory=True)
        with self.assertRaisesRegex(media.MediaError, "Symlinks"):
            media._output_paths(self.output)
        self.assertEqual(target_file.read_bytes(), b"fixture-only original")

    def test_staging_is_local_cleaned_and_never_reuses_existing_directories(self):
        with self.assertRaisesRegex(RuntimeError, "fixture failure"):
            with media._staging(self.output.parent) as staging:
                self.assertEqual(staging.parent, self.output.parent)
                (staging / "frame.png").write_bytes(b"fixture-only staged bytes")
                raise RuntimeError("fixture failure")
        self.assertFalse((self.output.parent / ".baseline-media-staging").exists())
        existing = self.output.parent / ".baseline-media-staging"
        existing.mkdir()
        sentinel = existing / "owned-by-someone-else"
        sentinel.write_text("preserve")
        with self.assertRaisesRegex(media.MediaError, "existing media staging"):
            with media._staging(self.output.parent):
                self.fail("Existing staging must never be entered")
        self.assertEqual(sentinel.read_text(), "preserve")

    def test_publishes_new_pair_and_identical_outputs_are_untouched(self):
        video, report = self.staged_pair()
        media._publish(video, report, self.output, self.report_path, replace=False)
        original = (self.output.read_bytes(), self.report_path.read_bytes())
        timestamps = (self.output.stat().st_mtime_ns, self.report_path.stat().st_mtime_ns)
        video, report = self.staged_pair()
        media._publish(video, report, self.output, self.report_path, replace=False)
        self.assertEqual((self.output.read_bytes(), self.report_path.read_bytes()), original)
        self.assertEqual((self.output.stat().st_mtime_ns, self.report_path.stat().st_mtime_ns), timestamps)

    def test_differing_report_cannot_partially_publish_a_new_video(self):
        video, report = self.staged_pair()
        self.report_path.write_text("fixture-only preexisting report")
        with self.assertRaisesRegex(media.MediaError, "differing"):
            media._publish(video, report, self.output, self.report_path, replace=False)
        self.assertFalse(self.output.exists())
        self.assertEqual(self.report_path.read_text(), "fixture-only preexisting report")

    def test_replace_only_accepts_an_intact_generated_pair(self):
        video, report = self.staged_pair(b"fixture-only old video")
        media._publish(video, report, self.output, self.report_path, replace=False)
        video, report = self.staged_pair(b"fixture-only replacement video")
        with self.assertRaises(media.MediaError):
            media._publish(video, report, self.output, self.report_path, replace=False)
        media._publish(video, report, self.output, self.report_path, replace=True)
        self.assertEqual(self.output.read_bytes(), b"fixture-only replacement video")
        self.output.write_bytes(b"fixture-only hand-edited video")
        video, report = self.staged_pair(b"fixture-only another video")
        with self.assertRaisesRegex(media.MediaError, "intact generated"):
            media._publish(video, report, self.output, self.report_path, replace=True)
        self.assertEqual(self.output.read_bytes(), b"fixture-only hand-edited video")

    def test_replace_never_overwrites_an_unidentified_file(self):
        video, report = self.staged_pair()
        self.output.write_bytes(b"fixture-only unrelated bytes")
        with self.assertRaisesRegex(media.MediaError, "intact generated"):
            media._publish(video, report, self.output, self.report_path, replace=True)
        self.assertFalse(self.report_path.exists())
        self.assertEqual(self.output.read_bytes(), b"fixture-only unrelated bytes")

    def test_failed_pair_publication_restores_old_artifacts(self):
        video, report = self.staged_pair(b"fixture-only old video")
        media._publish(video, report, self.output, self.report_path, replace=False)
        original = self.output.read_bytes(), self.report_path.read_bytes()
        video, report = self.staged_pair()
        original_replace = os.replace

        def fail_report(source, destination):
            if Path(source) == report:
                raise PermissionError("fixture-only simulated publication failure")
            return original_replace(source, destination)

        with mock.patch.object(media.os, "replace", side_effect=fail_report):
            with self.assertRaisesRegex(media.MediaError, "artifact pair"):
                media._publish(video, report, self.output, self.report_path, replace=True)
        self.assertEqual((self.output.read_bytes(), self.report_path.read_bytes()), original)

    @unittest.skipUnless(os.environ.get("SCENARIO_MEDIA_SMOKE") == "1", "Set SCENARIO_MEDIA_SMOKE=1 for the real encoder smoke test")
    def test_real_render_decodes_all_frames_and_repeats_identically(self):
        if importlib.util.find_spec("PIL") is None or not _KNOWN_ENCODER.is_file():
            self.skipTest("Already-installed Pillow and the explicitly known cached encoder are required")
        trace = fixture_trace()
        trace["events"][0]["caption"] = ("Fixture-only wide-caption layout stress: " + "W" * 260)[:260]
        trace["events"][0]["facts"] = {
            "fixture_only": True, "row_count": 8, "source_count": 2,
            "sample_name": "fixture-only", "description": "W" * 150, "no_live_actions": True,
        }
        table = trace["events"][0]["tables"][0]
        table.update({
            "columns": ["fixture_id", "state", "value", "group", "nullable", "description"],
            "rows": [[f"FIXTURE-{index:02d}", "input", index, "primary", None,
                      "fixture-only detail " + "W" * 90] for index in range(8)],
            "total_rows": 8, "highlight_rows": [1, 7],
        })
        second_table = copy.deepcopy(table)
        second_table["title"] = "Fixture-only second source"
        for row in second_table["rows"]:
            row[3] = "secondary"
        trace["events"][0]["tables"].append(second_table)
        trace["events"][1]["tables"][0].update({
            "columns": ["fixture_id", "rule", "observed", "passed"],
            "rows": [["FIXTURE-01", "nonempty-key", "FIXTURE-01", True],
                     ["FIXTURE-02", "nonempty-key", "FIXTURE-02", True]],
        })
        trace["events"][2]["tables"][0].update({
            "columns": ["fixture_id", "source_group", "matched"],
            "rows": [["FIXTURE-01", "primary", True], ["FIXTURE-02", "primary", True]],
        })
        trace["events"][3]["tables"][0].update({
            "columns": ["fixture_id", "rule", "observed_flag", "branch"],
            "rows": [["FIXTURE-01", "fixture-flag", True, "keep"],
                     ["FIXTURE-02", "fixture-flag", False, "review"]],
        })
        trace["events"][4]["tables"][0].update({
            "columns": ["fixture_id", "exception_code", "action"],
            "rows": [["FIXTURE-02", "fixture-review", "needs review"]],
            "total_rows": 1, "highlight_rows": [0],
        })
        trace["events"][4]["facts"]["row_count"] = 1
        trace["events"][5]["tables"][0].update({
            "columns": ["fixture_id", "completed_output", "review_required"],
            "rows": [["FIXTURE-01", "retained", False], ["FIXTURE-02", "review-listed", True]],
        })
        second_join = copy.deepcopy(trace["events"][2])
        second_join.update({"step_id": "fixture-second-join", "caption": "Fixture-only second cross-reference retains both invented identifiers."})
        for row in second_join["tables"][0]["rows"]:
            row[1] = "secondary"
        trace["events"].insert(3, second_join)
        for index, event in enumerate(trace["events"], 1):
            event["sequence"] = index
        title = "Fixture-only pagination and long-text renderer smoke " + "W" * 160
        evidence = fixture_evidence(trace)
        result = media.render_trace_video(trace, self.output, title=title,
                                          ffmpeg=_KNOWN_ENCODER, evidence=evidence)
        video_bytes = self.output.read_bytes()
        report_bytes = self.report_path.read_bytes()
        self.assertEqual(result, json.loads(report_bytes))
        required_keys = {
            "schema_version", "provenance", "evidence", "sha256", "size_bytes", "width", "height",
            "fps", "decoded_frame_count", "duration_seconds", "audio", "timeline",
            "max_mean_pixel_error", "native_video_reading",
        }
        self.assertTrue(required_keys <= result.keys())
        self.assertEqual(result["schema_version"], 1)
        self.assertEqual(result["provenance"], "synthetic-baseline-execution-visualization")
        self.assertTrue(video_bytes.startswith(b"\x1a\x45\xdf\xa3"))
        self.assertEqual(result["sha256"], hashlib.sha256(video_bytes).hexdigest())
        self.assertGreater(result["size_bytes"], 1000)
        self.assertEqual(result["size_bytes"], len(video_bytes))
        self.assertEqual(result["frame_count"], result["decoded_frame_count"])
        self.assertEqual(result["frame_count"], 100)
        self.assertEqual(result["duration_seconds"], 50)
        self.assertEqual((result["width"], result["height"], result["fps"]), (1600, 900, 2))
        self.assertEqual(result["audio"], "none")
        self.assertEqual([event["kind"] for event in result["timeline"]],
                         ["input", "validation", "join", "join", "decision", "exception", "output"])
        self.assertEqual([event["event_sequence"] for event in result["timeline"]], list(range(1, 8)))
        self.assertEqual(result["timeline"][0]["start_seconds"], 0)
        self.assertEqual(result["timeline"][-1]["end_seconds_exclusive"], result["duration_seconds"])
        self.assertEqual(result["display"]["page_count"], 10)
        self.assertIn("report:/title", result["display"]["truncated_source_pointers"])
        self.assertIn("/events/0/caption", result["display"]["truncated_source_pointers"])
        self.assertIn("/events/0/tables/0/rows/0/5", result["display"]["truncated_source_pointers"])
        self.assertTrue(all(
            pointer == "report:/title" or pointer.startswith("/events/0/")
            for pointer in result["display"]["truncated_source_pointers"]
        ), "Rule, branch, exception, and completed-output fields must remain fully readable")
        for table_index in range(2):
            indices = [
                row for page in result["timeline"][0]["pages"] if page["table_index"] == table_index
                for row in page["row_indices"]
            ]
            self.assertEqual(indices, list(range(8)))
        self.assertEqual(result["evidence"], evidence)
        self.assertEqual(result["baseline_command"], evidence["baseline_command"])
        self.assertEqual(result["native_video_reading"], "unverified")
        self.assertFalse(result["provenance_details"]["native_proof"])
        self.assertFalse(result["provenance_details"]["renderer_ran_baseline"])
        self.assertEqual(result["synthetic_label_every_frame"], media.LABEL)
        self.assertEqual(set(result["commands"]), {"version", "encode", "decode", "probe"})
        self.assertTrue(all(command[0] == _KNOWN_ENCODER.name for command in result["commands"].values()))
        self.assertNotIn(str(_KNOWN_ENCODER.parent), json.dumps(result["commands"]))
        self.assertEqual(result["encoder"]["path"], _KNOWN_ENCODER.name)
        self.assertEqual(len(result["fidelity"]["frames"]), result["frame_count"])
        self.assertTrue(result["fidelity"]["all_frames_decoded_and_compared"])
        self.assertLessEqual(result["fidelity"]["max_mean_pixel_error"], 6)
        self.assertLessEqual(result["fidelity"]["max_data_region_mean_pixel_error"], 6)
        self.assertLessEqual(result["fidelity"]["max_label_region_mean_pixel_error"], 6)
        self.assertEqual(len({frame["source_rgb_sha256"] for frame in result["fidelity"]["frames"]}), result["frame_count"])
        self.assertTrue(all(frame["decoded_png_sha256"] for frame in result["fidelity"]["frames"]))
        self.assertEqual(sorted(path.name for path in self.output.parent.iterdir()), ["baseline.media.json", "baseline.webm"])
        with mock.patch.object(media, "_run_command", wraps=media._run_command) as run:
            repeated = media.render_trace_video(trace, self.output, title=title,
                                                ffmpeg=_KNOWN_ENCODER, evidence=evidence)
        staging_path = str(Path(run.call_args_list[1].args[0][-1]).parent)
        recorded = [[argument.replace(str(_KNOWN_ENCODER), _KNOWN_ENCODER.name).replace(staging_path, "<media-staging>")
                     for argument in call.args[0]] for call in run.call_args_list]
        self.assertEqual(recorded,
                         [repeated["commands"][phase] for phase in ("version", "encode", "decode", "probe")])
        self.assertEqual(hashlib.sha256(run.call_args_list[1].args[1]).hexdigest(),
                         repeated["encoder_input"]["sha256"])
        for hash_name in ("source_rgb_sha256", "source_jpeg_sha256", "decoded_png_sha256", "decoded_rgb_sha256"):
            self.assertEqual([frame[hash_name] for frame in repeated["fidelity"]["frames"]],
                             [frame[hash_name] for frame in result["fidelity"]["frames"]], hash_name)
        repeated_bytes = self.output.read_bytes()
        self.assertEqual(hashlib.sha256(repeated_bytes).hexdigest(), repeated["sha256"])
        self.assertEqual(repeated["sha256"], result["sha256"])
        self.assertEqual(repeated, result)
        self.assertEqual(repeated_bytes, video_bytes)
        self.assertEqual(self.report_path.read_bytes(), report_bytes)
        self.assertEqual(sorted(path.name for path in self.output.parent.iterdir()), ["baseline.media.json", "baseline.webm"])


if __name__ == "__main__":
    unittest.main()
