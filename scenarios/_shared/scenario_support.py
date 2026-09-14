"""Small standalone CLI adapter for trusted sector-owned baseline functions.

Only this adapter and the Python standard library are needed by a baseline.
It never reads goldens, calls Creator, or supplies business decisions.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON input key: {key!r}")
        result[key] = value
    return result


def _constant(value):
    raise ValueError(f"Nonfinite JSON input number: {value}")


def _finite(value, depth=0):
    if depth > 80:
        raise ValueError("Input JSON nesting exceeds 80")
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("Input JSON numbers must be finite")
    if isinstance(value, dict):
        for item in value.values():
            _finite(item, depth + 1)
    elif isinstance(value, list):
        for item in value:
            _finite(item, depth + 1)


def _no_links(path):
    for item in (*reversed(path.absolute().parents), path.absolute()):
        try:
            info = item.lstat()
        except FileNotFoundError:
            continue
        if item.is_symlink() or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ValueError(f"Links and reparse points are not allowed: {item}")


def run_cli(solve, *, scenario_id):
    parser = argparse.ArgumentParser(description="Run the documented synthetic baseline without Creator.")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--trace", required=True, type=Path)
    args = parser.parse_args()
    try:
        for path in (args.input, args.output, args.trace):
            _no_links(path)
        paths = [path.resolve() for path in (args.input, args.output, args.trace)]
        if len(set(paths)) != 3:
            raise ValueError("Input, output, and trace paths must be distinct")
        if args.output.exists() or args.trace.exists():
            raise ValueError("Baseline adapter refuses existing outputs; use fresh output paths")
        if args.input.stat().st_size > 8 * 1024 * 1024:
            raise ValueError("Input JSON exceeds 8 MiB")
        content = args.input.read_bytes()
        payload = json.loads(content.decode("utf-8"), object_pairs_hook=_object, parse_constant=_constant)
        _finite(payload)
        if not isinstance(payload, dict):
            raise ValueError("Baseline input must be a JSON object")
        result, events = solve(payload)
        if not isinstance(result, dict) or not isinstance(events, list):
            raise ValueError("solve must return (result object, event array)")
        if any(not isinstance(event, dict) or "sequence" in event for event in events):
            raise ValueError("Events must be objects without helper-owned sequence fields")
        trace = {
            "schema_version": 1,
            "provenance": "synthetic-local-baseline",
            "scenario_id": scenario_id,
            "input_sha256": hashlib.sha256(content).hexdigest(),
            "events": [dict(event, sequence=index) for index, event in enumerate(events, start=1)],
        }
        result_bytes = (json.dumps(result, allow_nan=False, ensure_ascii=True, indent=2, sort_keys=True) + "\n").encode("utf-8")
        trace_bytes = (json.dumps(trace, allow_nan=False, ensure_ascii=True, indent=2, sort_keys=True) + "\n").encode("utf-8")
        for path, data in ((args.output, result_bytes), (args.trace, trace_bytes)):
            _no_links(path)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("xb") as handle:
                handle.write(data)
    except (OSError, ValueError, TypeError, RecursionError) as error:
        print(f"Baseline failed: {error}", file=sys.stderr)
        raise SystemExit(2) from error
