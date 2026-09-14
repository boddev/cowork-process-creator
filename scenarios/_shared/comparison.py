"""Semantic JSON comparison, independent of Creator and generated plugins."""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from .common import ContractError, finite_tree


def compare_json(expected: Any, actual: Any, *, limit: int = 100) -> list[dict]:
    if type(limit) is not int or limit < 1:
        raise ContractError("Comparison difference limit must be a positive integer")
    finite_tree(expected)
    finite_tree(actual)
    differences: list[dict] = []

    def record(pointer: str, reason: str, left: Any, right: Any) -> None:
        if len(differences) < limit:
            differences.append({"path": pointer or "/", "reason": reason, "expected": left, "actual": right})

    def visit(left: Any, right: Any, pointer: str) -> None:
        if len(differences) >= limit:
            return
        if type(left) in (int, float) and type(right) in (int, float):
            if Decimal(str(left)) != Decimal(str(right)):
                record(pointer, "number mismatch", left, right)
        elif type(left) is not type(right):
            record(pointer, "JSON type mismatch", left, right)
        elif isinstance(left, dict):
            for key in sorted(left.keys() | right.keys()):
                child = pointer + "/" + key.replace("~", "~0").replace("/", "~1")
                if key not in right:
                    record(child, "missing object field", left[key], None)
                elif key not in left:
                    record(child, "unexpected object field", None, right[key])
                else:
                    visit(left[key], right[key], child)
        elif isinstance(left, list):
            if len(left) != len(right):
                record(pointer, "array length mismatch", len(left), len(right))
            for index, (left_item, right_item) in enumerate(zip(left, right)):
                visit(left_item, right_item, f"{pointer}/{index}")
        elif left != right:
            record(pointer, "value mismatch", left, right)

    visit(expected, actual, "")
    return differences
