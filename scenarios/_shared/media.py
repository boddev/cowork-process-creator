"""Development-only, silent visualization of caller-validated local baseline traces.

Pillow is imported only when rendering. An explicitly supplied, existing FFmpeg
does the encoding and decoding; this module neither runs a baseline nor installs
tools, accesses a live system, or supplies an executable command-line interface.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import io
import json
import math
import os
from pathlib import Path
import platform
import re
import shutil
import stat
import subprocess
from types import SimpleNamespace
from typing import Callable


class MediaError(ValueError):
    """A trace cannot be safely rendered or its encoded output did not validate."""


WIDTH, HEIGHT, FPS = 1600, 900, 2
MIN_FRAMES, MAX_FRAMES = 60, 180
MAX_DISPLAY_PAGES = MAX_FRAMES // FPS
MAX_MEAN_ERROR = 6.0
LABEL = "Synthetic baseline execution visualization - not Cowork or a live system"
TRUNCATION = "[truncated]"
TRACE_SOURCE = "baseline-output/demo.trace.json"
PRODUCER = "scenarios._shared.media"
ARTIFACT_KIND = "synthetic-local-baseline-trace-video"
PROVENANCE = "synthetic-baseline-execution-visualization"
KINDS = ("input", "validation", "join", "decision", "exception", "output")
_ROOT = Path(__file__).absolute().parent.parent
_ID = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_EVIDENCE_KEYS = {
    "scenario_id", "case_id", "input_sha256", "result_sha256", "trace_sha256",
    "baseline_command", "golden_sha256", "baseline_py_sha256",
}
_STYLES = {
    "banner": (22, 28), "title": (34, 43), "stage": (25, 32),
    "caption": (25, 31), "table": (24, 31), "body": (22, 28),
    "fact": (21, 27), "small": (18, 24),
}
_INK = (29, 43, 58)
_BLUE = (27, 89, 145)
_CURSOR = (250, 194, 66)
_PROGRESS_LEFT, _PROGRESS_RIGHT, _PROGRESS_Y = 40, 1560, 880
_CURSOR_WIDTH = 8


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise MediaError(message)


def _keys(value: object, keys: set[str], location: str) -> None:
    _require(type(value) is dict and set(value) == keys,
             f"{location} must have exactly these keys: {', '.join(sorted(keys))}")


def _text(value: object, location: str) -> None:
    _require(type(value) is str and bool(value.strip()), f"{location} must be nonempty text")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as error:
        raise MediaError(f"{location} must be valid UTF-8 text") from error


def _scalar(value: object, location: str) -> None:
    _require(type(value) in (str, int, float, bool, type(None)),
             f"{location} must be a scalar JSON value")
    if type(value) is float:
        _require(math.isfinite(value), f"{location} must be finite")
    if type(value) is str:
        try:
            value.encode("utf-8")
        except UnicodeEncodeError as error:
            raise MediaError(f"{location} must be valid UTF-8 text") from error


def _sha(value: object, location: str) -> None:
    _require(type(value) is str and _HASH.fullmatch(value) is not None,
             f"{location} must be a lowercase SHA-256 hex digest")


def _validate_trace(trace: dict) -> None:
    _keys(trace, {"schema_version", "provenance", "scenario_id", "input_sha256", "events"}, "trace")
    _require(type(trace["schema_version"]) is int and trace["schema_version"] == 1,
             "trace.schema_version must be 1")
    _require(trace["provenance"] == "synthetic-local-baseline",
             "Only synthetic-local-baseline traces can be visualized")
    _require(type(trace["scenario_id"]) is str and _ID.fullmatch(trace["scenario_id"]) is not None,
             "trace.scenario_id must be a lowercase kebab-case ID")
    _sha(trace["input_sha256"], "trace.input_sha256")
    events = trace["events"]
    _require(type(events) is list and len(events) >= 6, "DEMO needs at least six meaningful trace states")
    _require(len(events) <= MAX_DISPLAY_PAGES,
             f"DEMO has too many events: at most {MAX_DISPLAY_PAGES} can receive one second each within 90 seconds")
    for index, event in enumerate(events, 1):
        where = f"trace.events[{index - 1}]"
        _keys(event, {"sequence", "step_id", "kind", "caption", "facts", "tables"}, where)
        _require(type(event["sequence"]) is int and event["sequence"] == index,
                 f"{where}.sequence must be the consecutive one-based event index")
        _require(type(event["step_id"]) is str and _ID.fullmatch(event["step_id"]) is not None,
                 f"{where}.step_id must be a lowercase kebab-case ID")
        _require(type(event["kind"]) is str and event["kind"] in KINDS,
                 f"{where}.kind is not a supported trace stage")
        _text(event["caption"], f"{where}.caption")
        _require(len(event["caption"]) <= 260, f"{where}.caption exceeds 260 characters")
        facts = event["facts"]
        _require(type(facts) is dict and len(facts) <= 6, f"{where}.facts must have at most six fields")
        for name, value in facts.items():
            _text(name, f"{where}.facts key")
            _scalar(value, f"{where}.facts[{name!r}]")
        tables = event["tables"]
        _require(type(tables) is list and 1 <= len(tables) <= 2, f"{where}.tables must have one or two tables")
        for table_index, table in enumerate(tables):
            location = f"{where}.tables[{table_index}]"
            _keys(table, {"title", "columns", "rows", "total_rows", "highlight_rows"}, location)
            _text(table["title"], f"{location}.title")
            columns, rows = table["columns"], table["rows"]
            _require(type(columns) is list and 1 <= len(columns) <= 6,
                     f"{location}.columns must have one to six names")
            for column in columns:
                _text(column, f"{location}.columns item")
            _require(type(rows) is list and len(rows) <= 8, f"{location}.rows must have at most eight rows")
            for row in rows:
                _require(type(row) is list and len(row) == len(columns),
                         f"{location}.rows must match the column width")
                for cell in row:
                    _scalar(cell, f"{location}.rows cell")
            _require(type(table["total_rows"]) is int and table["total_rows"] >= len(rows),
                     f"{location}.total_rows must be an integer at least the supplied row count")
            highlights = table["highlight_rows"]
            _require(type(highlights) is list and all(
                type(row) is int and 0 <= row < len(rows) for row in highlights
            ), f"{location}.highlight_rows must contain valid zero-based row indices")
            _require(len(set(highlights)) == len(highlights), f"{location}.highlight_rows has duplicate indices")
    _require(events[0]["kind"] == "input" and events[-1]["kind"] == "output",
             "DEMO must begin with input and end with completed output")
    _require({event["kind"] for event in events} == set(KINDS), "DEMO must show all six trace stage kinds")


def _validate_evidence(evidence: dict, trace: dict) -> None:
    _keys(evidence, _EVIDENCE_KEYS, "evidence")
    _require(evidence["scenario_id"] == trace["scenario_id"], "Evidence scenario_id does not match the trace")
    _require(evidence["case_id"] == "demo", "Only DEMO evidence can be rendered")
    for name in sorted(_EVIDENCE_KEYS):
        if name.endswith("_sha256"):
            _sha(evidence[name], f"evidence.{name}")
    _require(evidence["input_sha256"] == trace["input_sha256"], "Evidence input_sha256 does not match the trace")
    command = evidence["baseline_command"]
    _require(type(command) is list and bool(command), "evidence.baseline_command must be a nonempty argument array")
    for argument in command:
        _text(argument, "evidence.baseline_command argument")
        _require("\0" not in argument, "evidence.baseline_command cannot contain NUL")


def _json_bytes(value: object, *, pretty: bool = False) -> bytes:
    try:
        return (json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True,
                           indent=2 if pretty else None,
                           separators=None if pretty else (",", ":")) + "\n").encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as error:
        raise MediaError("Media inputs must be finite, UTF-8 JSON") from error


def _digest(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def _plain_path(path: Path, *, file: bool = False) -> None:
    for entry in reversed((path, *path.parents)):
        try:
            details = entry.lstat()
        except FileNotFoundError:
            continue
        except OSError as error:
            raise MediaError(f"Cannot inspect media path: {entry}") from error
        reparse = getattr(details, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 1024)
        _require(not stat.S_ISLNK(details.st_mode) and not reparse,
                 f"Symlinks, junctions, and reparse points are not allowed: {entry}")
        expected_type = stat.S_ISREG if entry == path and file else stat.S_ISDIR
        _require(expected_type(details.st_mode), f"Media path has the wrong file type: {entry}")


def _unambiguous_path(path: Path) -> None:
    _require(not path.drive or path.is_absolute(), "Drive-relative media paths are not allowed")
    for part in path.parts:
        if part == path.anchor:
            continue
        _require(part not in (".", "..") and not part.endswith((" ", ".")) and
                 ":" not in part and not any(ord(character) < 32 for character in part),
                 "Media paths cannot contain traversal, alternate streams, or ambiguous Windows components")
        device = part.partition(".")[0].upper()
        _require(device not in {"CON", "PRN", "AUX", "NUL"} and
                 re.fullmatch(r"(COM|LPT)[1-9\u00b9\u00b2\u00b3]", device) is None,
                 "Windows device names are not media paths")


def _output_paths(output: Path) -> tuple[Path, Path]:
    output = Path(output)
    _unambiguous_path(output)
    _require(output.name == "baseline.webm" and output.parent.name == "demo",
             "Media output must be <scenario>\\demo\\baseline.webm")
    output = output.absolute()
    _require(output.is_relative_to(_ROOT) and len(output.relative_to(_ROOT).parts) >= 3,
             "Media outputs must stay inside a scenario under this repository's scenarios directory")
    report = output.with_name("baseline.media.json")
    _plain_path(output, file=True)
    _plain_path(report, file=True)
    return output, report


def _encoder_path(ffmpeg: Path) -> Path:
    ffmpeg = Path(ffmpeg)
    _unambiguous_path(ffmpeg)
    ffmpeg = ffmpeg.absolute()
    _plain_path(ffmpeg, file=True)
    _require(ffmpeg.is_file(), f"Supply an existing FFmpeg file; no install or download is attempted: {ffmpeg}")
    return ffmpeg


@contextmanager
def _staging(parent: Path):
    _plain_path(parent)
    parent.mkdir(parents=True, exist_ok=True)
    _plain_path(parent)
    staging = parent / ".baseline-media-staging"
    try:
        staging.mkdir()
    except FileExistsError as error:
        raise MediaError(f"Refusing an existing media staging path (possibly another render): {staging}") from error
    try:
        yield staging
    finally:
        shutil.rmtree(staging)


def _display_text(text: str) -> str:
    return json.dumps(text, ensure_ascii=True)[1:-1]


def _display_scalar(value: object) -> str:
    return json.dumps(value, ensure_ascii=True, allow_nan=False, separators=(",", ":"))


def _fit_text(text: str, width: int, max_lines: int, measure: Callable[[str], float]) -> tuple[tuple[str, ...], bool]:
    _require(max_lines >= 1 and width >= measure(TRUNCATION), "Text box cannot fit a legible truncation marker")
    remaining, lines = text, []
    while remaining and len(lines) < max_lines:
        if measure(remaining) <= width:
            lines.append(remaining)
            remaining = ""
            break
        low, high = 1, len(remaining)
        while low < high:
            middle = (low + high + 1) // 2
            if measure(remaining[:middle]) <= width:
                low = middle
            else:
                high = middle - 1
        _require(measure(remaining[:low]) <= width, "A display character exceeds its text box")
        boundary = remaining.rfind(" ", 0, low + 1)
        split = boundary if boundary > 0 else low
        lines.append(remaining[:split].rstrip())
        remaining = remaining[split:].lstrip()
    truncated = bool(remaining)
    if truncated:
        last = lines[-1]
        while last and measure(last + " " + TRUNCATION) > width:
            last = last[:-1].rstrip()
        lines[-1] = (last + " " if last else "") + TRUNCATION
    return tuple(lines or [""]), truncated


@dataclass(frozen=True)
class _Block:
    lines: tuple[str, ...]
    x: int
    y: int
    width: int
    style: str
    source: str
    truncated: bool

    @property
    def bottom(self) -> int:
        return self.y + len(self.lines) * _STYLES[self.style][1]


def _block(text: str, x: int, y: int, width: int, style: str, max_lines: int,
           source: str, measure: Callable[[str, str], float]) -> _Block:
    lines, truncated = _fit_text(text, width, max_lines, lambda value: measure(style, value))
    return _Block(lines, x, y, width, style, source, truncated)


def _layout_trace(trace: dict, title: str, measure: Callable[[str, str], float]) -> list[dict]:
    pages = []
    for event_index, event in enumerate(trace["events"]):
        source = f"/events/{event_index}"
        common = [
            _block(_display_text(title), 40, 64, 1520, "title", 2, "report:/title", measure),
            _block(f'{event["sequence"]}/{len(trace["events"])}  {event["kind"].upper()}  |  {event["step_id"]}',
                   40, 156, 1520, "stage", 1, source + "/step_id", measure),
            _block(_display_text(event["caption"]), 40, 199, 1520, "caption", 3, source + "/caption", measure),
            _block("Observed facts", 1216, 326, 328, "table", 1, "", measure),
        ]
        for fact_index, (key, value) in enumerate(event["facts"].items()):
            common.append(_block(f"{_display_text(key)}: {_display_scalar(value)}", 1216,
                                 370 + fact_index * 66, 328, "fact", 2,
                                 source + "/facts/" + key.replace("~", "~0").replace("/", "~1"), measure))
        if not event["facts"]:
            common.append(_block("No scalar facts supplied.", 1216, 370, 328, "fact", 2, "", measure))
        for table_index, table in enumerate(event["tables"]):
            table_source = source + f"/tables/{table_index}"
            width = 1056 // len(table["columns"])
            column_blocks = [
                _block(_display_text(name), 96 + column * width, 399, width - 16, "body", 2,
                       table_source + f"/columns/{column}", measure)
                for column, name in enumerate(table["columns"])
            ]
            body_top = max(block.bottom for block in column_blocks) + 12
            groups, rows, y = [], [], body_top
            for row_index, row in enumerate(table["rows"]):
                cells = [
                    _block(_display_scalar(cell), 96 + column * width, y + 8, width - 16, "body", 2,
                           table_source + f"/rows/{row_index}/{column}", measure)
                    for column, cell in enumerate(row)
                ]
                height = max(len(cell.lines) for cell in cells) * _STYLES["body"][1] + 16
                if rows and y + height > 784:
                    groups.append(rows)
                    rows, y = [], body_top
                    cells = [
                        _Block(cell.lines, cell.x, y + 8, cell.width, cell.style, cell.source, cell.truncated)
                        for cell in cells
                    ]
                _require(y + height <= 784, "A table row cannot fit at the minimum readable font size")
                rows.append({"index": row_index, "y": y, "height": height, "cells": cells})
                y += height
            groups.append(rows)
            for table_page, group in enumerate(groups):
                shown, total = len(table["rows"]), table["total_rows"]
                range_text = f'Rows {group[0]["index"] + 1}-{group[-1]["index"] + 1} of {shown} in trace' if group else "0 rows in trace"
                if total > shown:
                    range_text += f"; {total} total, {total - shown} not included in trace"
                range_text += f" | Table {table_index + 1}/{len(event['tables'])}, page {table_page + 1}/{len(groups)}"
                blocks = common + [
                    _block(_display_text(table["title"]), 56, 326, 1096, "table", 1, table_source + "/title", measure),
                    _block(range_text, 56, 366, 1096, "small", 1, table_source + "/total_rows", measure),
                ] + column_blocks
                if not group:
                    blocks.append(_block("Empty state: the trace supplies no table rows.", 96, body_top + 22,
                                         1040, "body", 2, "", measure))
                pages.append({
                    "event_index": event_index, "table_index": table_index, "table_page": table_page + 1,
                    "table_page_count": len(groups), "blocks": blocks, "rows": group,
                    "highlight_rows": table["highlight_rows"], "body_top": body_top,
                })
    return pages


def _schedule(trace: dict, pages: list[dict]) -> tuple[list[dict], int]:
    _require(6 <= len(pages) <= MAX_DISPLAY_PAGES,
             "Trace needs too many display pages to show every supplied row for at least one second within 90 seconds")
    count = max(MIN_FRAMES, min(MAX_FRAMES, len(pages) * 10))
    each, extra = divmod(count, len(pages))
    timeline, start = [], 0
    for page_index, page in enumerate(pages):
        frames = each + (page_index < extra)
        page.update({"start_frame": start + 1, "frame_count": frames, "page_index": page_index + 1})
        event = trace["events"][page["event_index"]]
        if not timeline or timeline[-1]["event_sequence"] != event["sequence"]:
            timeline.append({
                "event_sequence": event["sequence"], "step_id": event["step_id"], "kind": event["kind"],
                "caption": event["caption"], "start_frame": start + 1,
                "start_seconds": start / FPS, "pages": [],
            })
        timeline[-1]["pages"].append({
            "page": page_index + 1, "table_index": page["table_index"],
            "table_page": page["table_page"], "row_indices": [row["index"] for row in page["rows"]],
            "start_frame": start + 1, "end_frame_exclusive": start + frames + 1,
            "start_seconds": start / FPS, "end_seconds_exclusive": (start + frames) / FPS,
        })
        start += frames
        timeline[-1].update({"end_frame_exclusive": start + 1, "end_seconds_exclusive": start / FPS})
    return timeline, count


@dataclass
class _Font:
    font: object
    scale: int

    def measure(self, text: str) -> int:
        bounds = self.font.getbbox(text)
        return (bounds[2] - bounds[0]) * self.scale


def _load_fonts(image_font) -> tuple[dict[str, _Font], dict]:
    fonts, description = {}, {}
    for style, (size, line_height) in _STYLES.items():
        try:
            font = image_font.load_default(size=size)
        except (TypeError, ImportError, OSError):
            try:
                font = image_font.load_default()
            except (TypeError, ImportError, OSError) as error:
                raise MediaError("Pillow's bundled default font is unavailable; no external fonts are searched") from error
        bounds = font.getbbox("Ag|0123[]")
        height = bounds[3] - bounds[1]
        _require(height > 0, "Pillow's bundled default font has no visible glyphs")
        scale = max(1, math.ceil(size * 0.8 / height)) if height < size * 0.7 else 1
        _require(size * 0.7 <= height * scale <= line_height,
                 "Pillow's bundled default font cannot meet the rendered legibility bounds")
        fonts[style] = _Font(font, scale)
        description[style] = {
            "requested_size": size, "scale": scale, "rendered_probe_height": height * scale,
            "line_height": line_height, "provider": "Pillow bundled ImageFont.load_default",
        }
    return fonts, description


def _draw_text(image, draw, text: str, x: int, y: int, font: _Font, color: tuple, pillow) -> None:
    if not text:
        return
    bounds = font.font.getbbox(text)
    if font.scale == 1:
        draw.text((x - bounds[0], y - bounds[1]), text, font=font.font, fill=color)
        return
    tile = pillow.Image.new("RGBA", (max(1, bounds[2] - bounds[0]), max(1, bounds[3] - bounds[1])))
    try:
        pillow.ImageDraw.Draw(tile).text((-bounds[0], -bounds[1]), text, font=font.font, fill=color + (255,))
        resized = tile.resize((tile.width * font.scale, tile.height * font.scale),
                              getattr(pillow.Image, "Resampling", pillow.Image).NEAREST)
        try:
            image.paste(resized, (x, y), resized)
        finally:
            resized.close()
    finally:
        tile.close()


def _cursor_left(frame_index: int, frame_count: int) -> int:
    return _PROGRESS_LEFT + round(frame_index * (_PROGRESS_RIGHT - _PROGRESS_LEFT - _CURSOR_WIDTH) / (frame_count - 1))


def _draw_frame(trace: dict, page: dict, frame_index: int, frame_count: int,
                active_row: int | None, fonts: dict[str, _Font], pillow):
    image = pillow.Image.new("RGB", (WIDTH, HEIGHT), (245, 248, 251))
    draw = pillow.ImageDraw.Draw(image)
    draw.rectangle((0, 0, WIDTH, 47), fill=(32, 57, 80))
    _draw_text(image, draw, LABEL, 40, 11, fonts["banner"], (255, 255, 255), pillow)
    draw.rectangle((40, 310, 1168, 792), fill=(255, 255, 255), outline=(205, 216, 227), width=2)
    draw.rectangle((1200, 310, 1560, 792), fill=(233, 240, 247))
    draw.rectangle((42, 389, 1166, page["body_top"] - 4), fill=(224, 234, 244))
    for row in page["rows"]:
        highlighted = row["index"] in page["highlight_rows"]
        fill = (255, 240, 205) if highlighted else (245, 249, 253) if row["index"] % 2 else (255, 255, 255)
        draw.rectangle((43, row["y"], 1165, row["y"] + row["height"] - 1), fill=fill)
        draw.line((43, row["y"] + row["height"] - 1, 1165, row["y"] + row["height"] - 1), fill=(221, 230, 238))
        if row["index"] == active_row:
            draw.rectangle((44, row["y"] + 1, 1164, row["y"] + row["height"] - 2), outline=_BLUE, width=3)
            draw.rectangle((44, row["y"] + 1, 50, row["y"] + row["height"] - 2), fill=_BLUE)
        if highlighted:
            draw.rectangle((1158, row["y"] + 3, 1163, row["y"] + row["height"] - 4), fill=(181, 116, 12))
        _draw_text(image, draw, str(row["index"] + 1), 60, row["y"] + 10, fonts["small"], _INK, pillow)
    blocks = page["blocks"] + [cell for row in page["rows"] for cell in row["cells"]]
    for block in blocks:
        for line_index, line in enumerate(block.lines):
            _draw_text(image, draw, line, block.x, block.y + line_index * _STYLES[block.style][1],
                       fonts[block.style], _INK, pillow)
    notes = [
        f"{TRUNCATION} = shortened display; full values: {TRACE_SOURCE}. Amber = trace-highlighted row; blue = active row.",
        "Text uses JSON escapes. Full title: baseline.media.json. Caller-provided local trace; native reading unverified.",
        f'Frame {frame_index + 1}/{frame_count} | Event {page["event_index"] + 1}/{len(trace["events"])}'
        f' | Page {page["page_index"]} | {frame_index / FPS:.1f}-{(frame_index + 1) / FPS:.1f}s / {frame_count / FPS:.1f}s'
        + (f" | Active trace row {active_row + 1}" if active_row is not None else " | Empty table"),
    ]
    for index, note in enumerate(notes):
        _require(fonts["small"].measure(note) <= 1520, "A required display note would be clipped")
        _draw_text(image, draw, note, 40, 801 + index * 24, fonts["small"], _INK, pillow)
    left = _cursor_left(frame_index, frame_count)
    draw.rectangle((_PROGRESS_LEFT, 873, _PROGRESS_RIGHT - 1, 887), fill=(213, 224, 235))
    draw.rectangle((_PROGRESS_LEFT, 873, left, 887), fill=_BLUE)
    draw.rectangle((left, 873, left + _CURSOR_WIDTH - 1, 887), fill=_CURSOR)
    return image


def _run_command(arguments: list[str], content: bytes | None = None) -> subprocess.CompletedProcess:
    try:
        result = subprocess.run(arguments, input=content, capture_output=True, timeout=600, check=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise MediaError(f"Could not run the supplied existing FFmpeg: {error}") from error
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace")[-4000:]
        raise MediaError(f"Existing FFmpeg failed with exit code {result.returncode}:\n{detail}")
    return result


def _header_details(header: str, frame_count: int) -> dict:
    header = header.split("Output #", 1)[0]
    duration = re.search(r"Duration:\s+(\d+):(\d+):(\d+\.\d+)", header)
    video_lines = [line for line in header.splitlines() if re.search(r"Stream #0:\d+.*Video:", line)]
    _require(duration is not None and len(video_lines) == 1, "FFmpeg probe did not expose one video and its duration")
    hours, minutes, seconds = duration.groups()
    duration_seconds = int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    rate = re.search(r"\b(\d+(?:\.\d+)?) fps\b", video_lines[0])
    _require(rate is not None and float(rate.group(1)) == FPS, "Encoded frame rate does not match the explicit timeline")
    _require(abs(duration_seconds - frame_count / FPS) < 0.001, "Encoded duration does not match the explicit timeline")
    _require(re.search(r"\bVideo: vp8\b", video_lines[0]) is not None and
             re.search(rf"\b{WIDTH}x{HEIGHT}\b", video_lines[0]) is not None,
             "Encoded stream must be VP8 at the declared dimensions")
    _require("Audio:" not in header, "The trace video must be silent")
    _require(re.search(r"creation_time\s*:", header, re.IGNORECASE) is None,
             "The container contains an unexpected creation timestamp")
    return {"duration_seconds": duration_seconds, "fps": FPS, "width": WIDTH, "height": HEIGHT, "audio": "none"}


def _verify_cursor(pixels: list[tuple], frame_index: int, frame_count: int) -> float:
    positions = [
        index for index in range(_PROGRESS_LEFT, _PROGRESS_RIGHT)
        if sum(abs(pixels[index][channel] - _CURSOR[channel]) for channel in range(3)) <= 70
    ]
    _require(bool(positions), f"Decoded frame {frame_index + 1} has no visible progress cursor")
    _require(3 <= len(positions) <= _CURSOR_WIDTH + 4 and positions[-1] - positions[0] <= _CURSOR_WIDTH + 3,
             f"Decoded frame {frame_index + 1} has an ambiguous progress cursor")
    actual = (positions[0] + positions[-1]) / 2
    expected = _cursor_left(frame_index, frame_count) + (_CURSOR_WIDTH - 1) / 2
    _require(abs(actual - expected) <= 2, f"Decoded frame {frame_index + 1} failed visible frame-order validation")
    return actual


def _validate_decoded(staging: Path, records: list[dict], pillow) -> dict:
    paths = sorted(staging.glob("decoded-*.png"))
    _require(len(paths) == len(records), f"Expected {len(records)} decoded frames, found {len(paths)}")
    source_order, decoded_order = hashlib.sha256(), hashlib.sha256()
    for index, (path, record) in enumerate(zip(paths, records)):
        _require(path.name == f"decoded-{index + 1:04d}.png", "Decoded frame numbering is not consecutive")
        with pillow.Image.open(path) as decoded_file, pillow.Image.open(staging / f"source-{index + 1:04d}.png") as source_file:
            _require(decoded_file.size == source_file.size == (WIDTH, HEIGHT), "Decoded frame dimensions changed")
            actual, expected = decoded_file.convert("RGB"), source_file.convert("RGB")
            try:
                source_hash = hashlib.sha256(expected.tobytes()).hexdigest()
                _require(source_hash == record["source_rgb_sha256"], "Source frame changed during encoding")
                difference = pillow.ImageChops.difference(actual, expected)
                try:
                    error = sum(pillow.ImageStat.Stat(difference).mean) / 3
                    data_region = difference.crop((40, 199, 1560, 792))
                    try:
                        data_error = sum(pillow.ImageStat.Stat(data_region).mean) / 3
                    finally:
                        data_region.close()
                    label_region = difference.crop((0, 0, WIDTH, 48))
                    try:
                        label_error = sum(pillow.ImageStat.Stat(label_region).mean) / 3
                    finally:
                        label_region.close()
                finally:
                    difference.close()
                _require(error <= MAX_MEAN_ERROR and data_error <= MAX_MEAN_ERROR and label_error <= MAX_MEAN_ERROR,
                         f"Decoded frame {index + 1} exceeds the mean RGB fidelity threshold of {MAX_MEAN_ERROR}")
                position = _verify_cursor([actual.getpixel((x, _PROGRESS_Y)) for x in range(WIDTH)], index, len(records))
                decoded_hash = hashlib.sha256(actual.tobytes()).hexdigest()
            finally:
                actual.close()
                expected.close()
        record.update({
            "decoded_png_sha256": _digest(path), "decoded_rgb_sha256": decoded_hash,
            "mean_pixel_error": round(error, 6), "data_region_mean_pixel_error": round(data_error, 6),
            "label_region_mean_pixel_error": round(label_error, 6),
            "decoded_progress_cursor_center": position,
        })
        source_order.update(bytes.fromhex(record["source_rgb_sha256"]))
        decoded_order.update(bytes.fromhex(decoded_hash))
    return {
        "passed": True, "all_frames_decoded_and_compared": True,
        "mean_error_threshold": MAX_MEAN_ERROR,
        "max_mean_pixel_error": max(record["mean_pixel_error"] for record in records),
        "max_data_region_mean_pixel_error": max(record["data_region_mean_pixel_error"] for record in records),
        "max_label_region_mean_pixel_error": max(record["label_region_mean_pixel_error"] for record in records),
        "comparison": "Mean absolute 8-bit RGB error against each original Pillow frame, including MJPEG and VP8 losses",
        "order_validation": "Every decoded frame's visible progress cursor matches its expected source position within 2 pixels",
        "ordered_digest_algorithm": "SHA-256 of concatenated binary SHA-256 RGB frame digests in one-based frame order",
        "source_frames_ordered_sha256": source_order.hexdigest(),
        "decoded_frames_ordered_sha256": decoded_order.hexdigest(),
        "frames": records,
    }


def _generated_report(report: Path, video: Path) -> bool:
    try:
        value = json.loads(report.read_text(encoding="utf-8"))
        return (
            type(value) is dict and value.get("producer") == PRODUCER and
            value.get("artifact_kind") == ARTIFACT_KIND and type(value.get("schema_version")) is int and
            value["schema_version"] == 1 and type(value.get("sha256")) is str and
            _HASH.fullmatch(value["sha256"]) is not None and
            (not video.exists() or value["sha256"] == _digest(video))
        )
    except (OSError, ValueError):
        return False


def _publish(staged_video: Path, staged_report: Path, output: Path, report_path: Path, *, replace: bool) -> None:
    artifacts = [(staged_video, output), (staged_report, report_path)]
    changed = []
    for staged, destination in artifacts:
        _plain_path(destination, file=True)
        if not destination.exists() or _digest(destination) != _digest(staged):
            changed.append((staged, destination))
    replacing = any(destination.exists() for _, destination in changed)
    _require(not replacing or replace, "Refusing existing differing media artifacts; use replace only for generated files")
    _require(not replacing or _generated_report(report_path, output),
             "Refusing to replace files not identified by an intact generated media report")
    backups, published = {}, []
    try:
        for _, destination in changed:
            if destination.exists():
                backup = staged_video.parent / ("previous-" + destination.name)
                shutil.copyfile(destination, backup)
                backups[destination] = backup
        for staged, destination in changed:
            _plain_path(destination, file=True)
            os.replace(staged, destination)
            published.append(destination)
    except OSError as error:
        for destination in reversed(published):
            if destination in backups:
                os.replace(backups[destination], destination)
            else:
                destination.unlink()
        raise MediaError("Could not publish the validated media artifact pair") from error


def render_trace_video(trace: dict, output: Path, *, title: str, ffmpeg: Path,
                       evidence: dict, replace: bool = False) -> dict:
    """Render and fully decode-check a caller-validated DEMO trace before publishing.

    Evidence hashes are shape-checked caller declarations, not independently
    checked baseline/golden files or native proof. The trace's input hash and
    scenario ID must agree with those declarations. Only the fixed generated
    artifact pair below this repository's ``scenarios`` directory is writable.
    """
    _validate_trace(trace)
    _validate_evidence(evidence, trace)
    _text(title, "title")
    _require(type(replace) is bool, "replace must be a boolean")
    output, report_path = _output_paths(output)
    encoder = _encoder_path(ffmpeg)
    trace_bytes = _json_bytes(trace)
    trace, evidence = json.loads(trace_bytes), json.loads(_json_bytes(evidence))
    try:
        from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageStat, __version__ as pillow_version
    except ImportError as error:
        raise MediaError("Rendering needs already-installed Pillow; core scenario tools do not require it") from error
    pillow = SimpleNamespace(Image=Image, ImageChops=ImageChops, ImageDraw=ImageDraw, ImageStat=ImageStat)
    fonts, font_description = _load_fonts(ImageFont)
    _require(fonts["banner"].measure(LABEL) <= 1520, "The mandatory synthetic label would be clipped")
    pages = _layout_trace(trace, title, lambda style, text: fonts[style].measure(text))
    timeline, frame_count = _schedule(trace, pages)
    encoder_hash = _digest(encoder)
    commands = {"version": [str(encoder), "-version"]}
    version_lines = _run_command(commands["version"]).stdout.decode("utf-8", errors="replace").splitlines()
    _require(bool(version_lines) and version_lines[0].startswith("ffmpeg version "), "Supplied executable is not FFmpeg")
    with _staging(output.parent) as staging:
        staged_video, staged_report = staging / "baseline.webm", staging / "baseline.media.json"
        records, jpeg_input = [], io.BytesIO()
        for page in pages:
            for local_frame in range(page["frame_count"]):
                index = len(records)
                rows = page["rows"]
                active_row = rows[min(len(rows) - 1, local_frame * len(rows) // page["frame_count"])]["index"] if rows else None
                image = _draw_frame(trace, page, index, frame_count, active_row, fonts, pillow)
                try:
                    image.save(staging / f"source-{index + 1:04d}.png", format="PNG")
                    buffer = io.BytesIO()
                    image.save(buffer, format="JPEG", quality=98, subsampling=0, optimize=False, progressive=False)
                    jpeg = buffer.getvalue()
                    jpeg_input.write(jpeg)
                    records.append({
                        "frame": index + 1, "event_sequence": page["event_index"] + 1, "page": page["page_index"],
                        "active_trace_row": active_row, "source_rgb_sha256": hashlib.sha256(image.tobytes()).hexdigest(),
                        "source_jpeg_sha256": hashlib.sha256(jpeg).hexdigest(),
                        "expected_progress_cursor_center": _cursor_left(index, frame_count) + (_CURSOR_WIDTH - 1) / 2,
                    })
                finally:
                    image.close()
        payload = jpeg_input.getvalue()
        jpeg_input.close()
        commands["encode"] = [
            str(encoder), "-hide_banner", "-loglevel", "error", "-n", "-fflags", "+bitexact",
            "-filter_threads", "1", "-threads", "1",
            "-f", "image2pipe", "-framerate", str(FPS), "-c:v", "mjpeg", "-i", "pipe:0",
            "-map", "0:v:0", "-an", "-sn", "-dn", "-c:v", "libvpx", "-pix_fmt", "yuv420p",
            "-b:v", "4M", "-crf", "4", "-deadline", "good", "-cpu-used", "0",
            "-g", "10", "-auto-alt-ref", "0", "-lag-in-frames", "0", "-threads", "1",
            "-r", str(FPS), "-frames:v", str(frame_count), "-fflags", "+bitexact", "-flags:v", "+bitexact",
            "-map_metadata", "-1", "-metadata", "creation_time=", "-f", "webm", str(staged_video),
        ]
        _run_command(commands["encode"], payload)
        _require(staged_video.is_file() and 0 < staged_video.stat().st_size < 200_000_000,
                 "Encoder did not produce a nonempty video below 200 MB")
        commands["decode"] = [
            str(encoder), "-hide_banner", "-loglevel", "error", "-n", "-filter_threads", "1", "-threads", "1",
            "-i", str(staged_video), "-map", "0:v:0", "-an", "-sn", "-dn", "-vsync", "0",
            "-c:v", "png", "-pix_fmt", "rgb24", "-threads", "1", "-start_number", "1",
            "-f", "image2", str(staging / "decoded-%04d.png"),
        ]
        _run_command(commands["decode"])
        commands["probe"] = [
            str(encoder), "-hide_banner", "-i", str(staged_video), "-map", "0:v:0",
            "-c:v", "copy", "-an", "-frames:v", "1", "-fflags", "+bitexact",
            "-map_metadata", "-1", "-f", "webm", "pipe:1",
        ]
        header = _header_details(_run_command(commands["probe"]).stderr.decode("utf-8", errors="replace"), frame_count)
        fidelity = _validate_decoded(staging, records, pillow)
        _require(_digest(encoder) == encoder_hash, "Encoder bytes changed during rendering")
        truncations = sorted({
            block.source for page in pages
            for block in page["blocks"] + [cell for row in page["rows"] for cell in row["cells"]]
            if block.truncated
        })
        report = {
            "schema_version": 1, "producer": PRODUCER, "artifact_kind": ARTIFACT_KIND,
            "provenance": PROVENANCE,
            "title": title, "scenario_id": trace["scenario_id"], "case_id": "demo",
            "format": "WebM/VP8", **header,
            "frame_count": frame_count, "decoded_frame_count": len(records),
            "sha256": _digest(staged_video), "size_bytes": staged_video.stat().st_size,
            "synthetic_label_every_frame": LABEL, "not_a_recording_of_a_real_business_system": True,
            "evidence": evidence, "baseline_command": evidence["baseline_command"],
            "provenance_details": {
                "kind": "caller-provided-local-baseline", "native_proof": False,
                "renderer_ran_baseline": False, "native_video_reading": "unverified",
                "checks": "Exact evidence fields, SHA-256 shapes, DEMO ID, matching trace scenario and input hash",
                "caller_hashes_recomputed_from_original_files": False,
                "canonical_trace_sha256": hashlib.sha256(trace_bytes).hexdigest(),
                "canonical_trace_serialization": "UTF-8, sorted keys, compact separators, ensure_ascii=false, LF terminator",
                "full_trace_source": TRACE_SOURCE,
            },
            "encoder": {"path": str(encoder), "version": version_lines[0], "sha256": encoder_hash},
            "commands": commands,
            "encoder_input": {"format": "concatenated MJPEG on stdin", "sha256": hashlib.sha256(payload).hexdigest()},
            "timeline": timeline, "fidelity": fidelity, "max_mean_pixel_error": fidelity["max_mean_pixel_error"],
            "display": {
                "page_count": len(pages), "all_supplied_rows_paged_in_order": True,
                "max_display_pages": MAX_DISPLAY_PAGES, "minimum_page_duration_seconds": 1,
                "truncation_marker": TRUNCATION, "truncated_source_pointers": truncations,
                "text_encoding": "JSON scalar notation; non-ASCII/control characters escaped, not replaced by missing glyphs",
                "fonts": font_description,
            },
            "reproducibility": {
                "scope": "Video bytes require identical trace, title, renderer, Python/Pillow/fonts, encoder bytes and options on the same platform. Reports additionally include exact absolute local command paths.",
                "python_version": platform.python_version(), "pillow_version": pillow_version,
                "renderer_sha256": _digest(Path(__file__)),
                "ordered_frames": True, "encoder_threads": 1, "bitexact_flags": True,
                "container_creation_timestamp": "stripped; no wall-clock timestamps added",
            },
            "runtime_dependency": "none; this optional developer producer and its dependencies are not shipped in plugins",
            "native_video_reading": "unverified",
            "limitations": [
                "Caller-supplied evidence is local provenance, not proof of independent goldens, native creation, installation, or execution.",
                "The caller must rerun and validate DEMO against its independent golden before invoking this renderer.",
                "Trace table snapshots with synthetic progress/active-row motion, not a screen recording, live interaction, or actual execution timing.",
                "Silent video: no narration or audio-understanding claim.",
                "Shortened text is explicitly marked; full supplied values remain in the trace, and the full title is in this report.",
                "Rows absent from the source trace cannot be reconstructed; declared subsets are labeled separately from display pagination.",
            ],
        }
        staged_report.write_bytes(_json_bytes(report, pretty=True))
        _publish(staged_video, staged_report, output, report_path, replace=replace)
    return report
