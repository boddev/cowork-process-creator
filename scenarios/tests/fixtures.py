"""Small explicitly nonbusiness test fixtures with manually listed goldens."""
from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

from scenarios._shared.common import json_bytes

REPO = Path(__file__).resolve().parents[2]
KINDS = ("input", "validation", "join", "decision", "exception", "output")
BASELINE = '''import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "_shared"))
from scenario_support import run_cli

KINDS = ("input", "validation", "join", "decision", "exception", "output")

def solve(payload):
    value = payload.get("value")
    exceptions = []
    if type(value) is not int:
        exceptions.append({"code": "invalid-value", "message": "value must be an integer"})
    elif payload.get("contradictory"):
        exceptions.append({"code": "conflict", "message": "the two fixture sources disagree"})
    outputs = {} if exceptions else {"doubled": value * 2}
    result = {"schema_version": 1, "status": "rejected" if exceptions else "completed",
              "outputs": outputs, "exceptions": exceptions}
    events = []
    for kind in KINDS:
        display = value if kind in ("input", "validation") else outputs.get("doubled")
        events.append({
            "step_id": kind, "kind": kind,
            "caption": "Unit-test fixture observation: " + kind,
            "facts": {"stage": kind, "exception_count": len(exceptions)},
            "tables": [{
                "title": "Fixture values, not an enterprise scenario",
                "columns": ["fixture", "value", "stage"],
                "rows": [["UNIT-ONLY", display, kind]],
                "total_rows": 1, "highlight_rows": [0],
            }],
        })
        if exceptions and kind == "validation":
            break
    return result, events

if __name__ == "__main__":
    run_cli(solve, scenario_id="unit-01")
'''


def dump(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(json_bytes(value))


def temporary_directory():
    root = REPO / ".local"
    root.mkdir(exist_ok=True)
    return tempfile.TemporaryDirectory(prefix="scenario-test-", dir=root)


def copy_scenario(source: Path, corpus: Path) -> Path:
    """Copy the scenario and its CLI adapter without changing recorded evidence."""
    root = corpus / source.parent.name / source.name
    shutil.copytree(source, root)
    shared = corpus / "_shared"
    shared.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source.parents[1] / "_shared" / "scenario_support.py", shared / "scenario_support.py")
    return root


def make_scenario(corpus: Path) -> Path:
    root = corpus / "unit-industry" / "fixture"
    root.mkdir(parents=True)
    shared = corpus / "_shared"
    shared.mkdir()
    shutil.copyfile(REPO / "scenarios" / "_shared" / "scenario_support.py", shared / "scenario_support.py")
    (root / "baseline.py").write_text(BASELINE, encoding="utf-8", newline="\n")
    (root / "HOW_TO.md").write_text(
        "# Unit-test fixture only\n\nThis synthetic fixture is not a researched business scenario.\n"
        "Double an integer; reject malformed or contradictory fixture records.\n"
        "The native gate is blocked. This file never claims native execution.\n",
        encoding="utf-8", newline="\n",
    )
    dump(root / "sources.json", {
        "schema_version": 1,
        "sources": [
            {
                "id": f"fixture-source-{index}", "title": "Unit-test URL, not a fetched research citation",
                "url": f"https://example.test/fixture-{index}", "publisher": "Test fixture",
                "accessed": "2026-09-14", "scope": "Test schema shape only",
                "supported_claims": ["No factual enterprise research claim"],
                "limitations": "Not a real source; never counted in the actual corpus",
            }
            for index in (1, 2)
        ],
    })
    dump(root / "workflow.json", {
        "schema_version": 1,
        "rules": [{
            "id": "double-value", "description": "Test arithmetic only; multiply a valid integer by two.",
            "provenance": {"kind": "sample-policy", "source_ids": [], "note": "Invented unit fixture"},
        }],
        "steps": [
            {"id": kind, "kind": kind, "title": kind.title(), "rule_ids": ["double-value"],
             "procedure": "Observe unit fixture stage " + kind}
            for kind in KINDS
        ],
    })
    dump(root / "connections.json", {
        "schema_version": 1, "mode": "mock-exports-only", "availability": "not-required",
        "connections": [], "note": "No external connection or real business data",
    })
    cases = [
        ("demo", "demo", {"value": 2}, "completed", {"doubled": 4}, [], []),
        ("holdout-a", "holdout", {"value": 3}, "completed", {"doubled": 6}, [], []),
        ("holdout-b", "holdout", {"value": 7}, "completed", {"doubled": 14}, [], []),
        ("negative-malformed", "negative", {"value": "invalid"}, "rejected", {},
         [{"code": "invalid-value", "message": "value must be an integer"}], ["malformed-input"]),
        ("negative-contradictory", "negative", {"value": 2, "contradictory": True}, "rejected", {},
         [{"code": "conflict", "message": "the two fixture sources disagree"}], ["contradictory-evidence"]),
    ]
    case_manifests = []
    for case_id, kind, payload, status, outputs, exceptions, failure_modes in cases:
        dump(root / "mock-data" / f"{case_id}.json", payload)
        dump(root / "expected" / f"{case_id}.json", {
            "schema_version": 1, "status": status, "outputs": outputs, "exceptions": exceptions,
        })
        case_manifests.append({
            "id": case_id, "kind": kind,
            "input": f"mock-data/{case_id}.json", "expected": f"expected/{case_id}.json",
            "expected_status": status, "covers": ["double-value"], "failure_modes": failure_modes,
            "derivation": "Manually listed fixture arithmetic/rejection expectation; not generated by solve.",
        })
    dump(root / "scenario.json", {
        "schema_version": 1, "id": "unit-01", "title": "Unit fixture, not a business scenario",
        "industry": "unit-industry", "workflow_family": "fixture-arithmetic",
        "description": "Exercise tool contracts without counting an enterprise scenario",
        "owner_role": "Test fixture", "risk_level": "low",
        "procedure": "HOW_TO.md", "sources": "sources.json", "workflow": "workflow.json",
        "connections": "connections.json", "baseline": "baseline.py", "video": "demo/baseline.webm",
        "sample_policy": {"synthetic_only": True, "no_live_actions": True, "description": "Unit fixture only"},
        "golden_provenance": {
            "method": "independent-manual-derivation", "author": "Unit-test author",
            "description": "Hard-coded fixture expectations independently listed in test source.",
        },
        "cases": case_manifests,
    })
    return root


def modify_json(path: Path, change):
    value = json.loads(path.read_text(encoding="utf-8"))
    change(value)
    dump(path, value)
