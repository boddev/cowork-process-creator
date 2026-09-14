"""Strict JSON, byte-addressed evidence, and bounded local path handling."""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import stat
import tempfile
from pathlib import Path
from typing import Any

JSON_LIMIT = 8 * 1024 * 1024
SLUG = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*\Z")
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
RESERVED = {"CON", "PRN", "AUX", "NUL"} | {
    f"{prefix}{number}" for prefix in ("COM", "LPT") for number in range(1, 10)
}


class ContractError(ValueError):
    """An explicit malformed-input or evidence-integrity failure."""


def no_links(path: Path) -> Path:
    absolute = path.absolute()
    for item in (*reversed(absolute.parents), absolute):
        try:
            info = item.lstat()
        except FileNotFoundError:
            continue
        attributes = getattr(info, "st_file_attributes", 0)
        if stat.S_ISLNK(info.st_mode) or attributes & 0x400:
            raise ContractError(f"Links and reparse points are not allowed: {item}")
    return absolute


def path_parts(value: str) -> list[str]:
    if not isinstance(value, str) or not value or len(value) > 512:
        raise ContractError("Expected a nonempty relative path of at most 512 characters")
    if "\\" in value or any(ord(char) < 32 for char in value):
        raise ContractError(f"Nonportable or control characters in path: {value!r}")
    parts = value.split("/")
    for part in parts:
        if part in {"", ".", ".."} or part.endswith((" ", ".")):
            raise ContractError(f"Ambiguous or escaping relative path: {value!r}")
        if any(char in part for char in '<>:"|?*'):
            raise ContractError(f"Reserved characters in path: {value!r}")
        if part.split(".")[0].upper() in RESERVED:
            raise ContractError(f"Reserved device name in path: {value!r}")
    return parts


def contained_path(root: Path, value: str, *, must_exist: bool = True) -> Path:
    root = no_links(root).resolve()
    candidate = no_links(root.joinpath(*path_parts(value)))
    resolved = candidate.resolve()
    if not resolved.is_relative_to(root) or resolved == root:
        raise ContractError(f"Path is outside its allowed root: {value!r}")
    if must_exist and not candidate.is_file():
        raise ContractError(f"Required regular file is missing: {candidate}")
    if candidate.exists() and not candidate.is_file():
        raise ContractError(f"Expected a regular file, not a directory: {candidate}")
    return candidate


def _unique_object(pairs: list[tuple[str, Any]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ContractError(f"Duplicate JSON key: {key!r}")
        result[key] = value
    return result


def _invalid_constant(value: str) -> None:
    raise ContractError(f"Nonfinite JSON number: {value}")


def finite_tree(value: Any, depth: int = 0) -> None:
    if depth > 80:
        raise ContractError("JSON nesting exceeds the supported depth of 80")
    if isinstance(value, float) and not math.isfinite(value):
        raise ContractError("JSON numbers must be finite")
    if isinstance(value, dict):
        for item in value.values():
            finite_tree(item, depth + 1)
    elif isinstance(value, list):
        for item in value:
            finite_tree(item, depth + 1)


def parse_json(content: bytes, *, label: str = "JSON") -> Any:
    if len(content) > JSON_LIMIT:
        raise ContractError(f"{label}: JSON exceeds {JSON_LIMIT} bytes")
    try:
        value = json.loads(
            content.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_invalid_constant,
        )
        finite_tree(value)
        return value
    except (UnicodeError, ValueError, RecursionError) as error:
        raise ContractError(f"{label}: {error}") from error


def load_json(path: Path) -> Any:
    path = no_links(path)
    try:
        if path.stat().st_size > JSON_LIMIT:
            raise ContractError(f"{path.name}: JSON exceeds {JSON_LIMIT} bytes")
        return parse_json(path.read_bytes(), label=str(path))
    except OSError as error:
        raise ContractError(f"Cannot read JSON {path}: {error}") from error


def json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=True, allow_nan=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def file_digest(path: Path) -> str:
    path = no_links(path)
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def write_bytes(path: Path, content: bytes, *, replace: bool = False) -> None:
    path = no_links(path)
    if path.exists():
        if not path.is_file():
            raise ContractError(f"Cannot replace a non-file artifact: {path}")
        if path.read_bytes() == content:
            return
        if not replace:
            raise ContractError(f"Refusing to replace changed artifact without --replace-generated: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".writing-", delete=False) as handle:
        temporary = Path(handle.name)
        handle.write(content)
    try:
        no_links(path)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def write_json(path: Path, value: Any, *, replace: bool = False) -> None:
    write_bytes(path, json_bytes(value), replace=replace)


def object_fields(value: Any, required: set[str], label: str, *, optional: set[str] | None = None) -> dict:
    if not isinstance(value, dict):
        raise ContractError(f"{label}: expected an object")
    missing = required - value.keys()
    extra = value.keys() - required - (optional or set())
    if missing or extra:
        raise ContractError(f"{label}: missing fields {sorted(missing)}; unknown fields {sorted(extra)}")
    return value


def text(value: Any, label: str, *, maximum: int = 10000) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ContractError(f"{label}: expected nonempty text of at most {maximum} characters")
    return value


def slug(value: Any, label: str) -> str:
    if not isinstance(value, str) or not SLUG.fullmatch(value):
        raise ContractError(f"{label}: expected a lowercase kebab-case identifier")
    return value


def string_list(value: Any, label: str, *, nonempty: bool = False) -> list[str]:
    if not isinstance(value, list) or (nonempty and not value):
        raise ContractError(f"{label}: expected {'nonempty ' if nonempty else ''}array")
    for item in value:
        text(item, label)
    if len(value) != len(set(value)):
        raise ContractError(f"{label}: duplicate values")
    return value


def version(value: Any, label: str) -> None:
    if type(value) is not int or value != 1:
        raise ContractError(f"{label}: only schema_version 1 is supported")


def scalar(value: Any) -> bool:
    return value is None or type(value) in (bool, int, str) or (
        type(value) is float and math.isfinite(value)
    )
