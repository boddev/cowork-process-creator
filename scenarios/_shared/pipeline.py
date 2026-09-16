"""Run trusted local baselines and bind their observations to immutable inputs."""
from __future__ import annotations

import os
import platform
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from .common import ContractError, file_digest, load_json, no_links, write_bytes, write_json
from .comparison import compare_json
from .contract import Scenario, baseline_import_audit, validate_result, validate_trace

NATIVE_BLOCKER = (
    "Approved Computer Use tools and an unlocked accessible session must both be restored, "
    "then parent-coordinated authorization is required. Do not use substitute channels. "
    "Old N00 was last Publishing... with unknown outcome and Creator disabled; "
    "inspect real Installed state before any retry."
)

_OS_ENVIRONMENT_KEYS = {
    "SYSTEMROOT", "WINDIR", "SYSTEMDRIVE", "USERPROFILE", "LOCALAPPDATA",
    "APPDATA", "PROGRAMDATA", "ALLUSERSPROFILE", "HOMEDRIVE", "HOMEPATH",
    "TEMP", "TMP", "LANG", "LC_ALL",
}


def baseline_environment() -> dict[str, str]:
    """Keep OS directory resolution, but no Python paths, credentials or tokens."""
    return {key: value for key, value in os.environ.items() if key.upper() in _OS_ENVIRONMENT_KEYS}


def native_pending() -> dict:
    return {
        "creation": "native_creation_blocked",
        "installation": "not_run",
        "independent_invocation": "not_run",
        "comparison": "not_run",
        "evidence_ids": {"creation": None, "installation": None, "invocation": None},
        "observed": [],
        "declared": [],
        "reason": NATIVE_BLOCKER,
    }


def source_hashes(scenario: Scenario) -> dict[str, str]:
    names = {
        "scenario.json", "HOW_TO.md", "sources.json", "workflow.json",
        "connections.json", "baseline.py",
    }
    for case in scenario.cases:
        names.update((case["input"], case["expected"]))
    return {name: file_digest(scenario.file(name)) for name in sorted(names)}


def golden_lock(scenario: Scenario, *, create: bool = False) -> dict:
    current = {
        "schema_version": 1,
        "scenario_id": scenario.id,
        "provenance": scenario.manifest["golden_provenance"],
        "cases": {
            case["id"]: {
                "expected_sha256": file_digest(scenario.file(case["expected"])),
                "input_sha256": file_digest(scenario.file(case["input"])),
                "derivation": case["derivation"],
            }
            for case in scenario.cases
        },
        "policy": "Independent author declaration; frozen before the first local baseline execution. Not native proof.",
    }
    path = scenario.file("validation/golden-lock.json", must_exist=False)
    if path.exists():
        existing = load_json(path)
        if compare_json(existing, current):
            raise ContractError(
                f"{scenario.id}: inputs, goldens, or derivations changed after their lock. "
                "An explicit independent review and a documented lock revision are required; "
                "--replace-generated never rewrites golden locks."
            )
    elif create:
        write_json(path, current)
    else:
        raise ContractError(f"{scenario.id}: missing pre-execution golden lock")
    return current


def _case_report(scenario: Scenario, case: dict) -> dict:
    return {
        "schema_version": 1,
        "scenario_id": scenario.id,
        "case_id": case["id"],
        "kind": case["kind"],
        "state": "prepared",
        "provenance": "observed-local-baseline-subprocess",
        "documented": {
            "steps": [
                {"id": step["id"], "kind": step["kind"], "rule_ids": step["rule_ids"]}
                for step in scenario.workflow["steps"]
            ],
            "case_rule_coverage": case["covers"],
            "failure_modes": case["failure_modes"],
            "golden_derivation": case["derivation"],
        },
        "observed": {"steps": [], "business_status": None},
        "local": {"comparison": "not_run", "differences": []},
        "native": native_pending(),
        "errors": [],
    }


def run_case(scenario: Scenario, case: dict, *, replace: bool = False, timeout: int = 30) -> dict:
    report = _case_report(scenario, case)
    started = time.monotonic()
    result_path = scenario.file(f"baseline-output/{case['id']}.json", must_exist=False)
    trace_path = scenario.file(f"baseline-output/{case['id']}.trace.json", must_exist=False)
    report_path = scenario.file(f"validation/{case['id']}.json", must_exist=False)
    before = None
    try:
        golden_lock(scenario, create=True)
        before = source_hashes(scenario)
        report["source_sha256"] = before
        report["baseline_import_audit"] = baseline_import_audit(scenario.file("baseline.py"))
        helper = Path(__file__).with_name("scenario_support.py")
        report["adapter_sha256"] = file_digest(helper)
        result_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".run-", dir=result_path.parent) as temporary:
            staging = no_links(Path(temporary))
            staged_result, staged_trace = staging / "result.json", staging / "trace.json"
            command = [
                sys.executable, "-B", "-I", str(scenario.file("baseline.py")),
                "--input", str(scenario.file(case["input"])),
                "--output", str(staged_result), "--trace", str(staged_trace),
            ]
            report["execution"] = {
                "command": [
                    Path(sys.executable).name, "-B", "-I", "baseline.py",
                    "--input", case["input"], "--output", "<temporary>/result.json",
                    "--trace", "<temporary>/trace.json",
                ],
                "cwd": "scenarios/" + scenario.root.parent.name + "/" + scenario.root.name,
                "path_recording": "Arguments are from the actual subprocess; interpreter basename, scenario-relative inputs and a labeled temporary-output token replace private machine paths.",
                "timeout_seconds": timeout,
                "returncode": None,
                "runtime": "trusted developer Python baseline; not Creator or Cowork",
                "python_version": platform.python_version(),
                "platform": sys.platform,
            }
            process = subprocess.run(
                command, cwd=scenario.root, env=baseline_environment(), stdin=subprocess.DEVNULL,
                capture_output=True, timeout=timeout, check=False,
            )
            substitutions = [
                (str(staging), "<temporary>"),
                (str(scenario.root), "<scenario>"),
                (str(scenario.root.parent.parent.parent), "<repository>"),
                (str(Path.home()), "<home>"),
            ]

            def public_diagnostic(content: bytes) -> str:
                value = content.decode("utf-8", errors="replace")[-8000:]
                for original, replacement in sorted(substitutions, key=lambda item: len(item[0]), reverse=True):
                    value = value.replace(original, replacement).replace(original.replace("\\", "/"), replacement)
                return value

            report["execution"].update({
                "returncode": process.returncode,
                "stdout": public_diagnostic(process.stdout),
                "stderr": public_diagnostic(process.stderr),
            })
            after = source_hashes(scenario)
            mutations = [name for name in before if before[name] != after[name]]
            if mutations:
                report["source_mutations"] = mutations
                raise ContractError(f"Baseline modified protected source/input/golden files: {mutations}")
            if report["adapter_sha256"] != file_digest(helper):
                raise ContractError("Baseline modified the shared CLI adapter")
            if process.returncode != 0:
                raise ContractError(f"Baseline process failed with exit code {process.returncode}; not a passed business negative")
            result = validate_result(load_json(staged_result))
            trace = validate_trace(load_json(staged_trace), scenario, case, before[case["input"]])
            expected = load_json(scenario.file(case["expected"]))
            differences = compare_json(expected, result)
            report["observed"] = {
                "steps": [
                    {"sequence": event["sequence"], "step_id": event["step_id"], "kind": event["kind"]}
                    for event in trace["events"]
                ],
                "business_status": result["status"],
            }
            report["local"] = {
                "comparison": "fail" if differences else "pass",
                "differences": differences,
                "comparison_scope": "all object fields, required artifacts/rows, ordered arrays, exact decimal strings; no ignored fields",
            }
            write_bytes(result_path, staged_result.read_bytes(), replace=replace)
            write_bytes(trace_path, staged_trace.read_bytes(), replace=replace)
            report["artifacts"] = {
                "result": f"baseline-output/{case['id']}.json",
                "trace": f"baseline-output/{case['id']}.trace.json",
                "result_sha256": file_digest(result_path),
                "trace_sha256": file_digest(trace_path),
                "input_sha256": before[case["input"]],
                "golden_sha256": before[case["expected"]],
                "baseline_py_sha256": before["baseline.py"],
            }
            if differences:
                report["errors"].append("Baseline result does not match the independently authored golden")
            else:
                report["state"] = "baseline_pass"
    except (ContractError, OSError, subprocess.TimeoutExpired) as error:
        report["errors"].append(str(error))
    if before is not None:
        try:
            after = source_hashes(scenario)
            mutations = [name for name in before if before[name] != after[name]]
            if mutations:
                report["source_mutations"] = mutations
                message = f"Protected source/input/golden files changed: {mutations}"
                if message not in report["errors"]:
                    report["errors"].append(message)
        except (ContractError, OSError) as error:
            report["errors"].append(f"Post-execution source integrity failed: {error}")
    if report["errors"]:
        report["state"] = "baseline_failed"
    report["execution_duration_seconds"] = round(time.monotonic() - started, 6)
    write_json(report_path, report, replace=True)
    return report


def check_case_evidence(scenario: Scenario, case: dict) -> dict:
    golden_lock(scenario)
    report = load_json(scenario.file(f"validation/{case['id']}.json"))
    if not isinstance(report, dict):
        raise ContractError("Local case report must be an object")
    if report.get("scenario_id") != scenario.id or report.get("case_id") != case["id"]:
        raise ContractError("Local case report belongs to a different scenario or case")
    if report.get("provenance") != "observed-local-baseline-subprocess" or report.get("state") != "baseline_pass":
        raise ContractError("No passing observed local baseline run is recorded")
    if report.get("errors") or report.get("source_sha256") != source_hashes(scenario):
        raise ContractError("Local evidence is failed or stale against current source/input/golden bytes")
    if report.get("adapter_sha256") != file_digest(Path(__file__).with_name("scenario_support.py")):
        raise ContractError("Local evidence is stale against the baseline adapter")
    execution = report.get("execution")
    if not isinstance(execution, dict) or type(execution.get("returncode")) is not int or execution["returncode"] != 0:
        raise ContractError("Local evidence is missing a successful process observation")
    artifacts = report.get("artifacts")
    if not isinstance(artifacts, dict):
        raise ContractError("Local evidence has no artifact fingerprints")
    result_name, trace_name = f"baseline-output/{case['id']}.json", f"baseline-output/{case['id']}.trace.json"
    if artifacts.get("result") != result_name or artifacts.get("trace") != trace_name:
        raise ContractError("Local artifacts must stay in their declared per-case locations")
    expected_hashes = {
        "result_sha256": file_digest(scenario.file(result_name)),
        "trace_sha256": file_digest(scenario.file(trace_name)),
        "input_sha256": file_digest(scenario.file(case["input"])),
        "golden_sha256": file_digest(scenario.file(case["expected"])),
        "baseline_py_sha256": file_digest(scenario.file("baseline.py")),
    }
    if any(artifacts.get(key) != value for key, value in expected_hashes.items()):
        raise ContractError("Local evidence contains stale or modified artifact fingerprints")
    result = validate_result(load_json(scenario.file(result_name)))
    trace = validate_trace(load_json(scenario.file(trace_name)), scenario, case, expected_hashes["input_sha256"])
    differences = compare_json(load_json(scenario.file(case["expected"])), result)
    if differences:
        raise ContractError("Recorded baseline_pass disagrees with actual semantic comparison")
    observed = [
        {"sequence": event["sequence"], "step_id": event["step_id"], "kind": event["kind"]}
        for event in trace["events"]
    ]
    if report.get("observed") != {"steps": observed, "business_status": result["status"]}:
        raise ContractError("Observed step manifest disagrees with the actual trace")
    local = report.get("local")
    if not isinstance(local, dict) or local.get("comparison") != "pass" or local.get("differences") != []:
        raise ContractError("Local comparison is not passing")
    if report.get("native") != native_pending():
        raise ContractError("A local baseline record must not assert generated, installed, or native-pass")
    return report


def run_scenarios(scenarios: list[Scenario], *, replace: bool = False) -> list[dict]:
    return [
        run_case(scenario, case, replace=replace)
        for scenario in scenarios for case in scenario.cases
    ]
