"""Build a local priority checklist; no task-system writes or external dependencies."""
import argparse
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True
from safe_json import InputError, load_json, write_new_text


def render(data, period):
    if not isinstance(period, str) or not re.fullmatch(r"[A-Za-z0-9 ._-]{1,40}", period):
        raise InputError("Provide an explicit simple reporting-period label (1-40 characters).")
    if not isinstance(data, dict) or set(data) != {"requests"} or not isinstance(data["requests"], list):
        raise InputError("Expected exactly a requests array.")
    if len(data["requests"]) > 500:
        raise InputError("At most 500 requests are supported.")
    groups, seen = {"urgent": [], "normal": []}, set()
    for index, row in enumerate(data["requests"], 1):
        if not isinstance(row, dict) or set(row) != {"id", "priority", "title"}:
            raise InputError(f"Row {index}: expected id, priority and title.")
        identifier, title, priority = row["id"], row["title"], row["priority"]
        if not isinstance(identifier, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,39}", identifier) or identifier in seen:
            raise InputError(f"Row {index}: invalid or duplicate ID.")
        seen.add(identifier)
        if not isinstance(priority, str) or priority not in groups:
            raise InputError(f"Row {index}: priority must be urgent or normal.")
        if not isinstance(title, str) or not re.fullmatch(r"[A-Za-z0-9 .,;:()_-]{1,120}", title):
            raise InputError(f"Row {index}: title must be simple text (1-120 characters).")
        groups[priority].append((identifier, title))
    lines = [f"# Priority checklist - {period}", ""]
    for priority, rows in groups.items():
        lines.extend(["## " + priority.title(), ""])
        lines.extend(f"- [ ] {identifier}: {title}" for identifier, title in rows)
        lines.append("")
    lines.extend([f"Total requests: {len(seen)}", ""])
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
    print("Checklist created.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
