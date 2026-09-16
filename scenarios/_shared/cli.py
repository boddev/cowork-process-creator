"""Development-only entry point; no network, runtime installers, or native UI."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .common import ContractError, load_json, no_links
from .contract import discover
from .native import compare_native_import, inspect_cowork_plugin
from .pipeline import check_case_evidence, run_case
from .reporting import build_catalog, coverage, write_reports
from .staging import media_evidence, stage_creator_inputs

DEFAULT_ROOT = Path(__file__).resolve().parents[1]


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--root", type=Path, default=DEFAULT_ROOT, help="Corpus root (normally repository scenarios)")
    commands = result.add_subparsers(dest="command", required=True)
    for name in ("list", "validate", "run", "render", "stage", "report", "import-native"):
        command = commands.add_parser(name)
        selection = command.add_mutually_exclusive_group()
        selection.add_argument("--scenario", action="append", help="Select a scenario ID; repeat as needed")
        selection.add_argument("--all", action="store_true", help="Select every implemented scenario (default)")
        if name in {"validate", "report"}:
            command.add_argument("--full", action="store_true", help="Require 15 scenarios, named industries, and five workflow families")
        if name in {"run", "render", "stage", "import-native"}:
            command.add_argument("--replace-generated", action="store_true", help="Replace only generated results/evidence, never inputs or goldens")
        if name == "run":
            command.add_argument("--case", action="append", help="Select a case; requires one selected scenario")
        if name == "render":
            command.add_argument("--ffmpeg", type=Path, required=True, help="Explicit existing developer encoder; no download/install")
        if name == "import-native":
            command.add_argument("--observation", type=Path, required=True, help="Operator-declared descriptor already under output")
    command = commands.add_parser("inspect-plugin", help="Read-only bounded ZIP inspection, never execution or native proof")
    command.add_argument("--artifact", type=Path, required=True, help="Actual supplied ZIP already under output")
    return result


def _print(value):
    print(json.dumps(value, ensure_ascii=True, allow_nan=False, indent=2, sort_keys=True))


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        root = no_links(args.root).resolve()
        output_root = root.parent / "output"
        if args.command == "inspect-plugin":
            artifact = no_links(args.artifact).resolve()
            if not artifact.is_relative_to(no_links(output_root).resolve()):
                raise ContractError("Inspect native plugin artifacts already supplied under root output")
            _print(inspect_cowork_plugin(artifact))
            return 0
        scenarios = discover(root)
        if args.scenario:
            requested = set(args.scenario)
            missing = requested - {scenario.id for scenario in scenarios}
            if missing:
                raise ContractError(f"Unknown scenario IDs: {sorted(missing)}")
            scenarios = [scenario for scenario in scenarios if scenario.id in requested]
        if args.command == "list":
            _print([{
                "id": scenario.id, "industry": scenario.manifest["industry"],
                "title": scenario.manifest["title"], "case_count": len(scenario.cases),
            } for scenario in scenarios])
            return 0
        if args.command == "validate":
            metrics = coverage(scenarios, full=args.full)
            _print({"schema_validation": "pass", "coverage": metrics, "native_complete": False})
            return 1 if metrics["errors"] else 0
        if args.command == "report":
            catalog = build_catalog(scenarios, full=args.full)
            if args.scenario:
                raise ContractError("Master reporting requires the entire discovered corpus; omit --scenario")
            write_reports(root, output_root, catalog)
            _print({
                "scenario_count": len(scenarios),
                "local_corpus_ready": catalog["local_corpus_ready"],
                "native_complete": False,
                "catalog": str(root / "catalog.json"),
                "report": str(root / "VALIDATION_REPORT.md"),
            })
            return 0 if catalog["local_corpus_ready"] else 1
        if not scenarios:
            raise ContractError("No implemented scenarios discovered; foundation fixtures are not scenarios")
        if args.command == "run":
            if args.case and len(scenarios) != 1:
                raise ContractError("--case requires exactly one selected scenario")
            reports = []
            for scenario in scenarios:
                cases = [scenario.case(value) for value in args.case] if args.case else scenario.cases
                for case in cases:
                    reports.append(run_case(scenario, case, replace=args.replace_generated))
            _print([{
                "scenario_id": report["scenario_id"], "case_id": report["case_id"],
                "state": report["state"], "errors": report["errors"],
            } for report in reports])
            return 0 if all(report["state"] == "baseline_pass" for report in reports) else 1
        if args.command == "render":
            from .media import MediaError, render_trace_video

            results = []
            for scenario in scenarios:
                report = run_case(scenario, scenario.case("demo"), replace=args.replace_generated)
                if report["state"] != "baseline_pass":
                    raise ContractError(f"Cannot render failed demo {scenario.id}: {report['errors']}")
                check_case_evidence(scenario, scenario.case("demo"))
                trace = load_json(scenario.file("baseline-output/demo.trace.json"))
                try:
                    media = render_trace_video(
                        trace, scenario.file("demo/baseline.webm", must_exist=False),
                        title=scenario.manifest["title"], ffmpeg=args.ffmpeg,
                        evidence=media_evidence(scenario, report), replace=args.replace_generated,
                    )
                except MediaError as error:
                    raise ContractError(f"{scenario.id}: {error}") from error
                results.append({
                    "scenario_id": scenario.id, "sha256": media["sha256"],
                    "duration_seconds": media["duration_seconds"],
                    "decoded_frame_count": media["decoded_frame_count"],
                    "native_video_reading": "unverified",
                })
            _print(results)
            return 0
        if args.command == "stage":
            manifests = [stage_creator_inputs(scenario, replace=args.replace_generated) for scenario in scenarios]
            _print([{"scenario_id": item["scenario_id"], "files": item["files"], "native_creation": "blocked"} for item in manifests])
            return 0
        if args.command == "import-native":
            if len(scenarios) != 1:
                raise ContractError("Native import requires exactly one --scenario")
            receipt = compare_native_import(
                scenarios[0], args.observation, output_root, replace=args.replace_generated,
            )
            _print({
                "scenario_id": receipt["scenario_id"],
                "all_supplied_payloads_match": receipt["all_supplied_payloads_match"],
                "all_required_cases_supplied": receipt["all_required_cases_supplied"],
                "missing_cases": receipt["missing_cases"],
                "native_pass": False,
                "native_review": receipt["native_review"],
            })
            return 0 if receipt["all_supplied_payloads_match"] and receipt["all_required_cases_supplied"] else 1
        raise ContractError(f"Unsupported command: {args.command}")
    except (ContractError, OSError, UnicodeError) as error:
        print(f"Scenario tooling failed: {error}", file=sys.stderr)
        return 2
