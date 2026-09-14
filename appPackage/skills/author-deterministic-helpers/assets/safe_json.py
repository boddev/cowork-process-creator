"""Copy into an output skill's own scripts before importing; standard library only."""
from __future__ import annotations

import json
from pathlib import Path


class InputError(ValueError):
    """A precise bounded-input failure; never a success-shaped substitute."""


def _unique(pairs: list) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise InputError("JSON contains a duplicate object key.")
        result[key] = value
    return result


def _nonfinite(value: str) -> None:
    raise InputError("Non-finite JSON numbers are not supported.")


def load_json(path: Path, max_bytes: int = 2_000_000, max_depth: int = 32) -> object:
    if type(max_bytes) is not int or not 1 <= max_bytes <= 10_000_000:
        raise InputError("Configured input byte limit must be 1-10000000.")
    if type(max_depth) is not int or not 1 <= max_depth <= 128:
        raise InputError("Configured JSON depth limit must be 1-128.")
    with Path(path).open("rb") as handle:
        content = handle.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise InputError(f"Input exceeds the declared {max_bytes}-byte limit.")
    try:
        data = json.loads(content.decode("utf-8"), object_pairs_hook=_unique, parse_constant=_nonfinite)
    except UnicodeDecodeError as exc:
        raise InputError("Input JSON must be UTF-8.") from exc
    except json.JSONDecodeError as exc:
        raise InputError(f"Invalid JSON at line {exc.lineno}, column {exc.colno}.") from exc
    except RecursionError as exc:
        raise InputError("JSON nesting exceeds parser limits.") from exc
    except ValueError as exc:
        if isinstance(exc, InputError):
            raise
        raise InputError("JSON number exceeds parser limits.") from exc
    pending = [(data, 0)]
    while pending:
        value, depth = pending.pop()
        if depth > max_depth:
            raise InputError(f"JSON nesting exceeds the declared {max_depth}-level limit.")
        if isinstance(value, dict):
            pending.extend((item, depth + 1) for item in value.values())
        elif isinstance(value, list):
            pending.extend((item, depth + 1) for item in value)
    return data


def write_new_text(path: Path, content: str) -> None:
    try:
        encoded = content.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise InputError("Output contains invalid Unicode and cannot be encoded as UTF-8.") from exc
    path = Path(path)
    stream = path.open("xb")
    try:
        with stream:
            stream.write(encoded)
    except OSError:
        path.unlink()
        raise
