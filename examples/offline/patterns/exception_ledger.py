"""Create a file-only nonzero variance ledger using exact signed integer cents."""
import argparse
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True
from safe_json import InputError, load_json, write_new_text


def cents(value):
    if not isinstance(value, str) or not re.fullmatch(r"(?:0|[1-9][0-9]{0,8})\.[0-9]{2}", value):
        raise InputError("Amounts must be canonical nonnegative decimal strings up to 999999999.99.")
    whole, fraction = value.split(".")
    return int(whole) * 100 + int(fraction)


def money(value):
    magnitude = abs(value)
    return ("-" if value < 0 else "") + f"{magnitude // 100}.{magnitude % 100:02d}"


def render(data, period):
    if not isinstance(period, str) or not re.fullmatch(r"[A-Za-z0-9 ._-]{1,40}", period):
        raise InputError("Provide an explicit simple reporting-period label.")
    if not isinstance(data, dict) or set(data) != {"records"} or not isinstance(data["records"], list):
        raise InputError("Expected exactly a records array.")
    if len(data["records"]) > 10000:
        raise InputError("At most 10000 records are supported.")
    lines = [f"# Exception ledger - {period}", "", "| ID | Expected | Actual | Difference |", "|---|---:|---:|---:|"]
    seen, total, count = set(), 0, 0
    for index, row in enumerate(data["records"], 1):
        if not isinstance(row, dict) or set(row) != {"id", "expected", "actual"}:
            raise InputError(f"Row {index}: expected id, expected and actual.")
        identifier = row["id"]
        if not isinstance(identifier, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,39}", identifier) or identifier in seen:
            raise InputError(f"Row {index}: invalid or duplicate ID.")
        seen.add(identifier)
        expected, actual = cents(row["expected"]), cents(row["actual"])
        difference = actual - expected
        if difference:
            lines.append(f"| {identifier} | {money(expected)} | {money(actual)} | {money(difference)} |")
            count += 1
            total += difference
    lines.extend(["", f"Exceptions: {count}", f"Net difference: {money(total)}", ""])
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--period", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        if args.output.suffix != ".md":
            raise InputError("Output must be a new .md file.")
        write_new_text(args.output, render(load_json(args.input), args.period))
    except (InputError, OSError) as exc:
        print(f"Report not created: {exc}", file=sys.stderr)
        return 2
    print("Ledger created.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
