"""Validate media evidence and copy only the five public Creator inputs."""
from __future__ import annotations

import hashlib
import math
from pathlib import Path

from .common import ContractError, SHA256, file_digest, load_json, no_links, write_bytes, write_json
from .contract import Scenario
from .pipeline import check_case_evidence, native_pending

CREATOR_INPUTS = (
    "HOW_TO.md", "workflow.json", "connections.json", "mock-data/demo.json",
    "demo/baseline.webm",
)


def media_evidence(scenario: Scenario, baseline_report: dict) -> dict:
    artifacts = baseline_report["artifacts"]
    return {
        "scenario_id": scenario.id,
        "case_id": "demo",
        "input_sha256": artifacts["input_sha256"],
        "result_sha256": artifacts["result_sha256"],
        "trace_sha256": artifacts["trace_sha256"],
        "golden_sha256": artifacts["golden_sha256"],
        "baseline_py_sha256": artifacts["baseline_py_sha256"],
        "baseline_command": baseline_report["execution"]["command"],
    }


def check_media(scenario: Scenario) -> dict:
    baseline = check_case_evidence(scenario, scenario.case("demo"))
    video_path = scenario.file("demo/baseline.webm")
    report = load_json(scenario.file("demo/baseline.media.json"))
    if not isinstance(report, dict) or type(report.get("schema_version")) is not int or report["schema_version"] != 1:
        raise ContractError("Media report is not a schema_version 1 object")
    if report.get("provenance") != "synthetic-baseline-execution-visualization":
        raise ContractError("Media must be labeled as a synthetic baseline visualization")
    recorded_evidence = report.get("evidence")
    expected_evidence = media_evidence(scenario, baseline)
    if not isinstance(recorded_evidence, dict) or recorded_evidence.keys() != expected_evidence.keys():
        raise ContractError("Media report is missing the complete local baseline evidence bindings")
    if any(recorded_evidence[key] != value for key, value in expected_evidence.items() if key != "baseline_command"):
        raise ContractError("Media does not bind to the currently recorded actual demo baseline run")
    command = recorded_evidence["baseline_command"]
    if not isinstance(command, list) or not command or any(not isinstance(argument, str) or not argument for argument in command):
        raise ContractError("Media must retain the exact baseline command used for its original rendering")
    if report.get("baseline_command") != command or report.get("title") != scenario.manifest["title"]:
        raise ContractError("Media command or scenario title does not match its recorded source")
    if report.get("producer") != "scenarios._shared.media" or report.get("artifact_kind") != "synthetic-local-baseline-trace-video":
        raise ContractError("Media lacks the identified local producer and artifact kind")
    if report.get("synthetic_label_every_frame") != "Synthetic baseline execution visualization - not Cowork or a live system":
        raise ContractError("Media lacks the mandatory synthetic-not-native label")
    if report.get("not_a_recording_of_a_real_business_system") is not True:
        raise ContractError("Media must explicitly disclaim live business-system recording")
    if report.get("sha256") != file_digest(video_path) or report.get("size_bytes") != video_path.stat().st_size:
        raise ContractError("Media video bytes are stale or do not match their recorded fingerprints")
    with video_path.open("rb") as handle:
        if handle.read(4) != b"\x1a\x45\xdf\xa3":
            raise ContractError("Media artifact is not an EBML/WebM file")
    if not 0 < video_path.stat().st_size < 200_000_000:
        raise ContractError("Media is empty or exceeds the documented native attachment size bound")
    for field in ("duration_seconds", "fps", "max_mean_pixel_error"):
        value = report.get(field)
        if type(value) not in (int, float) or not math.isfinite(value):
            raise ContractError(f"Media report lacks a finite {field}")
    if not 30 <= report["duration_seconds"] <= 90 or not 0 < report["fps"] <= 30:
        raise ContractError("Media must last 30-90 seconds with an explicit positive frame rate")
    frame_count = report.get("decoded_frame_count")
    if type(frame_count) is not int or abs(frame_count - report["duration_seconds"] * report["fps"]) > 0.00001:
        raise ContractError("Decoded frame count does not match declared media duration and rate")
    if not 0 <= report["max_mean_pixel_error"] <= 6:
        raise ContractError("Media does not meet the decoded fidelity threshold")
    fidelity = report.get("fidelity")
    if not isinstance(fidelity, dict) or fidelity.get("passed") is not True or fidelity.get("all_frames_decoded_and_compared") is not True:
        raise ContractError("Media lacks a successful every-frame decode and fidelity record")
    frames = fidelity.get("frames")
    if not isinstance(frames, list) or len(frames) != frame_count:
        raise ContractError("Media must record fidelity and hashes for every decoded frame")
    source_order, decoded_order = hashlib.sha256(), hashlib.sha256()
    errors = []
    for sequence, frame in enumerate(frames, 1):
        if not isinstance(frame, dict) or type(frame.get("frame")) is not int or frame["frame"] != sequence:
            raise ContractError("Media decoded-frame records must be contiguous and one-based")
        for key in ("source_rgb_sha256", "source_jpeg_sha256", "decoded_png_sha256", "decoded_rgb_sha256"):
            value = frame.get(key)
            if not isinstance(value, str) or not SHA256.fullmatch(value):
                raise ContractError("Media frame is missing a complete source/decoded byte hash")
        for key in ("mean_pixel_error", "data_region_mean_pixel_error", "label_region_mean_pixel_error"):
            value = frame.get(key)
            if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 6:
                raise ContractError("Media frame has missing or excessive decoded fidelity error")
        errors.append(frame["mean_pixel_error"])
        source_order.update(bytes.fromhex(frame["source_rgb_sha256"]))
        decoded_order.update(bytes.fromhex(frame["decoded_rgb_sha256"]))
    if not errors or max(errors) != report["max_mean_pixel_error"] or fidelity.get("max_mean_pixel_error") != max(errors):
        raise ContractError("Media aggregate fidelity does not match its per-frame observations")
    if fidelity.get("source_frames_ordered_sha256") != source_order.hexdigest() or fidelity.get("decoded_frames_ordered_sha256") != decoded_order.hexdigest():
        raise ContractError("Media ordered frame hashes do not match its decoded sequence")
    if report.get("audio") != "none" or report.get("native_video_reading") != "unverified":
        raise ContractError("Synthetic silent media cannot assert narration or native understanding")
    if type(report.get("width")) is not int or type(report.get("height")) is not int:
        raise ContractError("Media dimensions must be integer pixels")
    if report["width"] < 1280 or report["height"] < 720:
        raise ContractError("Media dimensions are below the readable evidence canvas minimum")
    timeline = report.get("timeline")
    trace = load_json(scenario.file("baseline-output/demo.trace.json"))
    if not isinstance(timeline, list) or len(timeline) != len(trace["events"]):
        raise ContractError("Media timeline must include every actual demo trace event")
    end = 0
    for item, event in zip(timeline, trace["events"]):
        if not isinstance(item, dict):
            raise ContractError("Media timeline items must be objects")
        if item.get("event_sequence") != event["sequence"] or item.get("step_id") != event["step_id"] or item.get("kind") != event["kind"]:
            raise ContractError("Media timeline event order does not match the actual trace")
        start, finish = item.get("start_seconds"), item.get("end_seconds_exclusive")
        if type(start) not in (int, float) or type(finish) not in (int, float):
            raise ContractError("Media timeline timestamps must be finite numeric seconds")
        if not math.isfinite(start) or not math.isfinite(finish) or start != end or finish <= start:
            raise ContractError("Media timeline must be continuous, ordered, and nonempty")
        end = finish
    if abs(end - report["duration_seconds"]) > 0.00001:
        raise ContractError("Media timeline does not cover the complete declared duration")
    return report


def _tree_files(root: Path) -> list[Path]:
    files = []
    no_links(root)
    for child in sorted(root.iterdir()):
        no_links(child)
        if child.is_dir():
            files.extend(_tree_files(child))
        elif child.is_file():
            files.append(child)
        else:
            raise ContractError(f"Nonregular staging entry: {child}")
        if len(files) > 100:
            raise ContractError("Creator staging unexpectedly contains too many files")
    return files


def check_staging(scenario: Scenario) -> dict:
    check_media(scenario)
    manifest = load_json(scenario.file("validation/creator-staging.json"))
    if not isinstance(manifest, dict) or manifest.get("scenario_id") != scenario.id:
        raise ContractError("Creator staging manifest has the wrong scenario identity")
    root = no_links(scenario.root / "validation" / "creator-input")
    if not root.is_dir():
        raise ContractError("Creator staging directory does not exist")
    actual_files = {path.relative_to(root).as_posix() for path in _tree_files(root)}
    if actual_files != set(CREATOR_INPUTS):
        raise ContractError(f"Creator input is not the exact five-file allowlist: {sorted(actual_files)}")
    expected_entries = []
    for name in CREATOR_INPUTS:
        source = scenario.file(name)
        target = root.joinpath(*name.split("/"))
        if file_digest(source) != file_digest(target):
            raise ContractError(f"Creator staged input is stale or modified: {name}")
        expected_entries.append({"path": name, "sha256": file_digest(source), "size_bytes": source.stat().st_size})
    if manifest.get("files") != expected_entries or manifest.get("native") != native_pending():
        raise ContractError("Creator staging manifest is stale or asserts unsupported native states")
    return manifest


def stage_creator_inputs(scenario: Scenario, *, replace: bool = False) -> dict:
    media = check_media(scenario)
    root = no_links(scenario.root / "validation" / "creator-input")
    if root.exists():
        if not root.is_dir():
            raise ContractError("Creator staging target must be a directory")
        existing = {path.relative_to(root).as_posix() for path in _tree_files(root)}
        if existing - set(CREATOR_INPUTS):
            raise ContractError("Refusing contaminated Creator staging; unexpected files must be reviewed separately")
    files = []
    for name in CREATOR_INPUTS:
        source = scenario.file(name)
        target = root.joinpath(*name.split("/"))
        write_bytes(target, source.read_bytes(), replace=replace)
        files.append({"path": name, "sha256": file_digest(source), "size_bytes": source.stat().st_size})
    manifest = {
        "schema_version": 1,
        "scenario_id": scenario.id,
        "provenance": "local-allowlisted-synthetic-demo-inputs",
        "state": "prepared",
        "input_directory": "validation/creator-input",
        "files": files,
        "media_sha256": media["sha256"],
        "withheld": [
            "scenario.json", "sources.json", "baseline.py", "shared tooling",
            "expected", "baseline-output", "holdout cases", "negative cases",
            "validation answers", "hidden evaluation markers",
        ],
        "native": native_pending(),
    }
    write_json(scenario.file("validation/creator-staging.json", must_exist=False), manifest, replace=replace)
    check_staging(scenario)
    return manifest
