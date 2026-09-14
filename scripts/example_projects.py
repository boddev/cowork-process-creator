"""Development-only synthetic projects and package plans; no native claims."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
TOOLKIT = ROOT / "appPackage" / "skills" / "build-output-plugin" / "scripts"
sys.path.insert(0, str(TOOLKIT))
import creator_builder as b
import creator_project as p
import project_contracts as c
from make_fixtures import png

FAMILIES = {
    "cost-report": {
        "title": "Ready item costs",
        "purpose": "Validate inventory, retain ready items and write an exact monthly cost report.",
        "procedure": "Input is exactly an items array of up to 10000 rows, each with id, state, quantity, unit_cost. IDs are unique, 1-64 ASCII alphanumeric/dot/underscore/hyphen, starting alphanumeric. State is ready or hold. Quantity is integer 1-100000, not Boolean. Unit cost is a canonical nonnegative decimal string with exactly two fractional digits, no redundant leading zeros, at most999999999.99. Validate every row, including held rows. Retain ready rows in order; multiply quantity by unit cost exactly and sum every retained row. Require explicit YYYY-MM period (year1000-9999, month01-12) and new Markdown output. Input is at most2MB and nesting32; reject malformed, duplicated or invalid data. No external systems.",
        "period": "2026-09", "max_items": 10000, "pattern": "cost_entry.py",
        "input": {"items": [
            {"id": "A1", "state": "ready", "quantity": 3, "unit_cost": "0.10"},
            {"id": "A2", "state": "hold", "quantity": 5, "unit_cost": "99.00"},
            {"id": "A3", "state": "ready", "quantity": 2, "unit_cost": "4.20"},
        ]},
        "screen": ["A1 READY 3 X 0.10 = 0.30", "A2 HOLD EXCLUDED", "A3 READY 2 X 4.20 = 8.40", "TOTAL 8.70"],
    },
    "priority-checklist": {
        "title": "Priority checklist",
        "purpose": "Group supplied requests into urgent and normal checklist sections without creating tasks.",
        "procedure": "Input is exactly a requests array of up to500 rows, each with id, priority and title. ID is unique ASCII alphanumeric/underscore/hyphen, starts alphanumeric, at most40chars. Title is1-120 ASCII letters/digits/spaces or . , ; : ( ) _ -. Priority is urgent or normal. List urgent before normal, preserving order within each group. Require explicit period label (1-40 ASCII alphanumeric/space/dot/underscore/hyphen) and new Markdown output. Reject unknown priorities, invalid text, duplicates, input over2MB or JSON nesting over32. Do not create tasks or send messages.",
        "period": "Sprint 4", "max_items": 500, "pattern": "priority_checklist.py",
        "input": {"requests": [
            {"id": "C1", "priority": "normal", "title": "Archive notes"},
            {"id": "C2", "priority": "urgent", "title": "Review inventory"},
            {"id": "C3", "priority": "urgent", "title": "Prepare checklist"},
        ]},
        "screen": ["URGENT C2 REVIEW INVENTORY", "URGENT C3 PREPARE CHECKLIST", "NORMAL C1 ARCHIVE NOTES", "TOTAL REQUESTS 3"],
    },
    "exception-ledger": {
        "title": "Exception ledger",
        "purpose": "Report nonzero differences between supplied expected and actual values using exact signed cents.",
        "procedure": "Input is exactly a records array of up to10000 rows, each with id, expected and actual. ID is unique ASCII alphanumeric/underscore/hyphen, starts alphanumeric, at most40chars. Amounts are canonical nonnegative two-decimal strings with no redundant leading zeros, at most999999999.99. Compute actual minus expected exactly. Retain nonzero differences in order, including negatives; sum signed differences. Require explicit period label (1-40 ASCII alphanumeric/space/dot/underscore/hyphen) and new Markdown output. Reject malformed/duplicate data, input over2MB or JSON nesting over32. Never write business records.",
        "period": "Batch 7", "max_items": 10000, "pattern": "exception_ledger.py",
        "input": {"records": [
            {"id": "E1", "expected": "1.00", "actual": "0.80"},
            {"id": "E2", "expected": "5.00", "actual": "5.00"},
            {"id": "E3", "expected": "2.00", "actual": "2.35"},
        ]},
        "screen": ["E1 DIFFERENCE -0.20", "E2 MATCH EXCLUDED", "E3 DIFFERENCE 0.35", "NET DIFFERENCE 0.15"],
    },
}


def write_document(path: Path, data: dict) -> None:
    path.write_bytes(b.json_bytes(data))


def candidate_plan(family: str) -> dict:
    config = FAMILIES[family]
    companions = [
        {"path": "scripts/main.py", "content": (ROOT / "examples" / "offline" / "patterns" / config["pattern"]).read_text(encoding="utf-8")},
        {"path": "scripts/safe_json.py", "content": (ROOT / "appPackage" / "skills" / "author-deterministic-helpers" / "assets" / "safe_json.py").read_bytes().decode("utf-8")},
        {"path": "references/rules.md", "content": "# Confirmed synthetic rules\n\n" + config["procedure"] + "\n"},
    ]
    if family == "cost-report":
        companions.append({"path": "scripts/report_logic.py", "content": (ROOT / "examples" / "n00" / "candidate" / "skills" / "ready-items-report" / "scripts" / "report.py").read_text(encoding="utf-8")})
    body = f"""# {config['title']}

Require the selected new input JSON, explicit reporting period and a new
Markdown output filename. Do not infer values from the demonstration.
Read `references/rules.md` for the exact bounded data contract.

Locate this skill's own `scripts/main.py` and its sibling modules using the
native resource mechanism. Invoke it with --input, --period and --output
using actual paths/values as separate arguments in the existing native
Python environment. No packages, services, network clients or runners.
If native execution is unavailable, stop with that precise limitation.

Return the actual new Markdown file only after success. Respect validation
errors and do not overwrite existing output. Do not send, publish or update
business systems. This output needs no Creator or original procedure/media.

This is an offline synthetic example, not evidence of native installation
or scheduling. Platform approvals and capabilities are never granted by
these instructions or a local report.
"""
    spec = {"schema_version": b.SPEC_VERSION, "name": family, "title": config["title"],
            "version": b.VERSION, "summary": config["title"] + " from explicit new file inputs.",
            "description": config["purpose"] + " Offline synthetic example; native use remains unverified.",
            "skills": [family], "connectors": []}
    return {"format_version": 1, "plugin": spec,
            "skills": [{"name": family, "description": config["purpose"] + " Use for this file-only workflow on new supplied data.", "body": body, "companions": companions}],
            "tools": []}


def create_project(destination: Path, family: str = "cost-report", exercise: bool = True) -> dict:
    destination = destination.resolve()
    config = FAMILIES[family]
    p.init_project(destination, family, config["title"], config["purpose"])
    header = {"format_version": 1, "project_id": family}
    doc_bytes = ("# " + config["title"] + "\n\nSynthetic offline procedure.\n\n" + config["procedure"] + "\n").encode("utf-8")
    image = png([(32, 165, "PERIOD " + config["period"].upper(), (35, 47, 61))] +
                [(32, 210 + index * 65, line, (35, 47, 61)) for index, line in enumerate(config["screen"])], "OFFLINE SYNTHETIC FIXTURE")
    fixture_dir = destination.parent / (destination.name + "-evidence")
    fixture_dir.mkdir()
    (fixture_dir / "procedure.md").write_bytes(doc_bytes)
    (fixture_dir / "01-demo.png").write_bytes(image)
    inputs = dict(header, sources=[
        {"id": "procedure", "name": "procedure.md", "kind": "procedure", "order": None, "sha256": hashlib.sha256(doc_bytes).hexdigest(), "availability": "attached"},
        {"id": "demonstration", "name": "01-demo.png", "kind": "screenshot", "order": 1, "sha256": hashlib.sha256(image).hexdigest(), "availability": "attached"},
    ])
    observations = dict(header, items=[
        {"id": "document-rules", "source_id": "procedure", "source_sha256": inputs["sources"][0]["sha256"], "kind": "documented", "text": config["procedure"], "locator": {"label": "Synthetic procedure, all rules", "frame_ordinal": None, "seconds": None}, "confidence": 1},
        {"id": "visual-example", "source_id": "demonstration", "source_sha256": inputs["sources"][1]["sha256"], "kind": "observed", "text": "Controlled offline fixture, NOT native model observation: period " + config["period"] + "; " + "; ".join(config["screen"]), "locator": {"label": "Rendered synthetic screenshot, ordinal 1", "frame_ordinal": None, "seconds": None}, "confidence": 1},
    ], questions=[])
    write_document(destination / "inputs.json", inputs)
    write_document(destination / "observations.json", observations)
    write_document(destination / "host-profile.json", dict(header, context="offline-synthetic", capabilities=[
        {"id": capability, "status": "available", "evidence": "Synthetic offline capability fixture only; not actual Cowork availability."}
        for capability in ("files.read", "files.write", "python.stdlib")
    ], connections=[]))
    blueprint = b.read_json(destination / "workflow-blueprint.json")
    blueprint.update(status="confirmed", evidence_sha256=c.evidence_fingerprint(inputs, observations),
                     invocation_prompt="Use this workflow with explicitly supplied new input, reporting period and output filename.")
    blueprint["inputs"] = [
        {"id": identifier, "type": kind, "required": True, "description": description, "default": None, "default_evidence": []}
        for identifier, kind, description in (
            ("inventory", "file", "Selected new JSON data following the declared bounded contract."),
            ("period", "string", "Explicit reporting month or period label, never the demonstrated default."),
            ("output-name", "string", "A new Markdown output filename."),
        )
    ]
    blueprint["outputs"] = [{"id": identifier, "description": description} for identifier, description in (
        ("records", "Validated input records."), ("report", "Deterministically generated Markdown."),
        ("delivery", "Native downloadable new report; not a simulated file link."),
    )]
    blueprint["steps"] = []
    for identifier, capability, depends, consumes, produces, action, effect in (
        ("read-input", "files.read", [], ["input:inventory"], ["records"], "Read and validate every supplied record.", "read"),
        ("transform", "python.stdlib", ["read-input"], ["output:records", "input:period"], ["report"], config["purpose"], "local-write"),
        ("deliver", "files.write", ["transform"], ["output:report", "input:output-name"], ["delivery"], "Deliver the actual new file without overwriting or business-system effects.", "local-write"),
    ):
        blueprint["steps"].append({
            "id": identifier, "action": action, "depends_on": depends, "consumes": consumes, "produces": produces,
            "capability": capability, "connection_id": None, "tool_name": None, "effect": effect,
            "approval": "none", "on_ambiguous_result": "stop", "evidence_ids": ["document-rules", "visual-example"],
            "decision_id": None, "condition": None,
            "repeat": {"input_id": "inventory", "max_items": config["max_items"], "stop_when": "After every input record has been validated/processed exactly once within this helper call.", "evidence_ids": ["document-rules"]} if identifier == "transform" else None,
        })
    blueprint["constants"] = [{"id": "demonstration-period", "value": config["period"], "classification": "parameter", "input_id": "period", "evidence_ids": ["visual-example"], "reason": "An explicit runtime input; the example period is not a default."}]
    blueprint["evaluation_cases"] = [
        {"id": "changed-input", "description": "Run the helper on supplied changed records and explicit period.", "negative": False, "expected": "Exact independently specified rows/counts/result."},
        {"id": "invalid-input", "description": "Reject malformed JSON/schema without a new report.", "negative": True, "expected": "Nonzero exit, explicit error and no report."},
        {"id": "deep-json", "description": "Reject deeply nested invalid JSON with a concise InputError, not a traceback.", "negative": True, "expected": "Exit 2, concise nesting error, no output."},
    ]
    plan = candidate_plan(family)
    resource_paths = [f"skills/{family}/" + item["path"] for item in plan["skills"][0]["companions"]]
    blueprint["bindings"] = [
        {"step_id": identifier, "skill": family,
         "files": [f"skills/{family}/SKILL.md"] + (resource_paths if identifier != "deliver" else []),
         "test_ids": ["changed-input", "invalid-input", "deep-json"]}
        for identifier in ("read-input", "transform", "deliver")
    ]
    write_document(destination / "workflow-blueprint.json", blueprint)
    write_document(destination / "build-state.json", dict(header, blueprint_revision=1, phase="review"))
    plan_path = destination / "candidate-plan.json"
    write_document(plan_path, plan)
    p.assemble_candidate(plan_path, destination / "candidate")
    if exercise:
        run_examples(destination, fixture_dir, config)
    return c.validate_project(destination)


def run_examples(project: Path, fixture_dir: Path, config: dict) -> None:
    family = b.read_json(project / "workflow-blueprint.json")["project_id"]
    helper = project / "candidate" / "skills" / family / "scripts" / "main.py"
    input_path, output_path = fixture_dir / "new-input.json", fixture_dir / "actual-report.md"
    input_path.write_bytes(b.json_bytes(config["input"]))
    result = subprocess.run([sys.executable, "-E", "-s", "-B", str(helper), "--input", str(input_path), "--period", config["period"], "--output", str(output_path)], cwd=fixture_dir, capture_output=True, text=True, timeout=30)
    if result.returncode:
        raise RuntimeError("Synthetic helper failed: " + result.stderr)
    expected = {
        "cost-report": "Grand total: 8.70",
        "priority-checklist": "Total requests: 3",
        "exception-ledger": "Net difference: 0.15",
    }[family]
    report = output_path.read_text(encoding="utf-8")
    if expected not in report:
        raise AssertionError("Synthetic result did not meet the independent expected result")
    if family == "priority-checklist" and not report.index("C2:") < report.index("C3:") < report.index("C1:"):
        raise AssertionError("Checklist priority/order rule did not hold")
    if family == "exception-ledger" and ("-0.20" not in report or "| E2 |" in report):
        raise AssertionError("Signed variance/filtering rule did not hold")
    for name, content in (("invalid-input", b'{"unexpected":true}'), ("deep-json", ('{"data":' + "[" * 10000 + "0" + "]" * 10000 + "}").encode("utf-8"))):
        bad_input, bad_output = fixture_dir / (name + ".json"), fixture_dir / (name + ".md")
        bad_input.write_bytes(content)
        failure = subprocess.run([sys.executable, "-E", "-s", "-B", str(helper), "--input", str(bad_input), "--period", config["period"], "--output", str(bad_output)], cwd=fixture_dir, capture_output=True, text=True, timeout=30)
        if failure.returncode != 2 or bad_output.exists() or "Traceback" in failure.stderr:
            raise AssertionError(f"{name}: expected a concise explicit failure and no output")
    checked = c.validate_project(project)
    write_document(project / "evaluation-results.json", {
        "format_version": 1, "project_id": family, "blueprint_revision": 1,
        "blueprint_sha256": checked["blueprint_sha256"], "candidate_sha256": checked["candidate_sha256"],
        "environment": "local", "cases": [
            {"id": name, "status": "passed", "evidence": "Actual developer-only subprocess execution on synthetic inputs; see sibling evidence files. Not native Cowork invocation."}
            for name in ("changed-input", "invalid-input", "deep-json")
        ],
    })
