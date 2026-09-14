"""Use bounded JSON I/O around the reusable exact cost-report transformation."""
import argparse
import sys
from pathlib import Path

sys.dont_write_bytecode = True
from safe_json import InputError, load_json, write_new_text
from report_logic import InputError as ReportError, render


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
    except (InputError, ReportError, OSError) as exc:
        print(f"Report not created: {exc}", file=sys.stderr)
        return 2
    print("Cost report created.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
