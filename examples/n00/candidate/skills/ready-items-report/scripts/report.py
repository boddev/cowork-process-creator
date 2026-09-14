"""Create an exact, file-only ready-items report; Python standard library."""
from __future__ import annotations

import argparse
import json
import re
import sys
from decimal import Decimal, localcontext
from pathlib import Path


class InputError(ValueError):
    """Invalid report input."""


def unique_object(pairs: list) -> dict:
    value = {}
    for key, item in pairs:
        if key in value:
            raise InputError("Duplicate JSON field")
        value[key] = item
    return value


def reject_constant(value: str) -> None:
    raise InputError("Non-finite JSON values are not supported")


def render(data: object, period: str) -> str:
    if not isinstance(period, str) or not re.fullmatch(r"[1-9][0-9]{3}-(?:0[1-9]|1[0-2])", period):
        raise InputError("Reporting month must be YYYY-MM (year 1000-9999)")
    if not isinstance(data, dict) or set(data) != {"items"}:
        raise InputError("Input must contain exactly an items list")
    items = data["items"]
    if not isinstance(items, list) or len(items) > 10_000:
        raise InputError("items must be a list of at most 10000 rows")
    ids = set()
    kept = []
    with localcontext() as context:
        context.prec = 32
        for index, item in enumerate(items, 1):
            if not isinstance(item, dict) or set(item) != {"id", "state", "quantity", "unit_cost"}:
                raise InputError(f"Row {index}: expected id, state, quantity and unit_cost")
            identifier = item["id"]
            if not isinstance(identifier, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", identifier):
                raise InputError(f"Row {index}: invalid id")
            if identifier in ids:
                raise InputError(f"Row {index}: duplicate id")
            ids.add(identifier)
            if item["state"] not in ("ready", "hold"):
                raise InputError(f"Row {index}: state must be ready or hold")
            quantity = item["quantity"]
            if type(quantity) is not int or not 1 <= quantity <= 100_000:
                raise InputError(f"Row {index}: quantity must be an integer from 1 to 100000")
            cost_text = item["unit_cost"]
            if not isinstance(cost_text, str) or not re.fullmatch(r"(?:0|[1-9][0-9]{0,8})\.[0-9]{2}", cost_text):
                raise InputError(f"Row {index}: unit_cost must be a nonnegative two-decimal string at most 999999999.99")
            cost = Decimal(cost_text)
            if item["state"] == "ready":
                kept.append((identifier, quantity, cost, quantity * cost))
        total = sum((row[3] for row in kept), Decimal("0.00"))
    lines = [
        f"# Ready-items cost report - {period}", "",
        "| ID | Quantity | Unit cost | Line cost |",
        "|---|---:|---:|---:|",
    ]
    lines.extend(f"| {identifier} | {quantity} | {cost:.2f} | {amount:.2f} |" for identifier, quantity, cost, amount in kept)
    lines.extend(["", f"Included rows: {len(kept)}", f"Excluded rows: {len(items) - len(kept)}", f"Grand total: {total:.2f}", ""])
    return "\n".join(lines)


def create_report(input_path: Path, period: str, output_path: Path) -> None:
    if input_path.stat().st_size > 2_000_000:
        raise InputError("Input exceeds the 2 MB workflow limit")
    raw = input_path.read_text(encoding="utf-8")
    try:
        data = json.loads(raw, object_pairs_hook=unique_object, parse_constant=reject_constant)
    except json.JSONDecodeError as exc:
        raise InputError(f"Invalid JSON at line {exc.lineno}, column {exc.colno}") from exc
    except RecursionError as exc:
        raise InputError("JSON nesting is too deep") from exc
    except ValueError as exc:
        if isinstance(exc, InputError):
            raise
        raise InputError("JSON number is outside the parser's supported range") from exc
    content = render(data, period)
    if output_path.suffix.lower() != ".md":
        raise InputError("Output must be a new .md file")
    with output_path.open("x", encoding="utf-8", newline="\n") as output:
        output.write(content)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--period", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        create_report(args.input, args.period, args.output)
    except (InputError, OSError, UnicodeError) as exc:
        print(f"Report not created: {exc}", file=sys.stderr)
        return 2
    print("Report created.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
