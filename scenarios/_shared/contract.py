"""Executable checks for SCENARIO_CONTRACT.md, not a business workflow engine."""
from __future__ import annotations

import ast
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

from .common import (
    ContractError, SHA256, contained_path, digest, json_bytes, load_json, no_links,
    object_fields, scalar, slug, string_list, text, version,
)

KINDS = {"input", "validation", "join", "decision", "exception", "output"}
STATUSES = {"completed", "completed_with_exceptions", "rejected"}
FIXED_PATHS = {
    "procedure": "HOW_TO.md",
    "sources": "sources.json",
    "workflow": "workflow.json",
    "connections": "connections.json",
    "baseline": "baseline.py",
    "video": "demo/baseline.webm",
}
MANIFEST_FIELDS = {
    "schema_version", "id", "title", "industry", "workflow_family", "description",
    "owner_role", "risk_level", "sample_policy", "golden_provenance", "cases",
} | FIXED_PATHS.keys()
CASE_FIELDS = {"id", "kind", "input", "expected", "expected_status", "covers", "failure_modes", "derivation"}


@dataclass(frozen=True)
class Scenario:
    root: Path
    manifest: dict
    workflow: dict
    sources: dict
    connections: dict

    @property
    def id(self) -> str:
        return self.manifest["id"]

    @property
    def cases(self) -> list[dict]:
        return self.manifest["cases"]

    def file(self, relative: str, *, must_exist: bool = True) -> Path:
        return contained_path(self.root, relative, must_exist=must_exist)

    def case(self, case_id: str) -> dict:
        for item in self.cases:
            if item["id"] == case_id:
                return item
        raise ContractError(f"{self.id}: unknown case {case_id!r}")


def _array(value, label, minimum=0):
    if not isinstance(value, list) or len(value) < minimum:
        raise ContractError(f"{label}: expected an array with at least {minimum} items")
    return value


def _unique_ids(items, label):
    result = set()
    for item in items:
        if not isinstance(item, dict):
            raise ContractError(f"{label}: every item must be an object")
        item_id = slug(item.get("id"), label + ".id")
        if item_id in result:
            raise ContractError(f"{label}: duplicate id {item_id!r}")
        result.add(item_id)
    return result


def validate_result(value: dict, label: str = "result") -> dict:
    object_fields(value, {"schema_version", "status", "outputs", "exceptions"}, label)
    version(value["schema_version"], label)
    if not isinstance(value["status"], str) or value["status"] not in STATUSES:
        raise ContractError(f"{label}: unsupported business status")
    if not isinstance(value["outputs"], dict):
        raise ContractError(f"{label}.outputs: expected an object")
    for exception in _array(value["exceptions"], label + ".exceptions"):
        if not isinstance(exception, dict):
            raise ContractError(f"{label}: exceptions must be objects")
        text(exception.get("code"), label + ".exception.code")
        text(exception.get("message"), label + ".exception.message")
    if value["status"] == "completed" and value["exceptions"]:
        raise ContractError(f"{label}: completed results must not hide exceptions")
    if value["status"] != "completed" and not value["exceptions"]:
        raise ContractError(f"{label}: rejected or exception status requires explicit exceptions")
    return value


def _sources(value: dict) -> set[str]:
    object_fields(value, {"schema_version", "sources"}, "sources")
    version(value["schema_version"], "sources")
    sources = _array(value["sources"], "sources.sources", 2)
    ids = _unique_ids(sources, "sources.sources")
    urls = set()
    for source in sources:
        object_fields(source, {
            "id", "title", "url", "publisher", "accessed", "scope",
            "supported_claims", "limitations",
        }, "source")
        for key in ("title", "publisher", "scope", "limitations"):
            text(source[key], "source." + key)
        try:
            url = urlparse(text(source["url"], "source.url"))
        except ValueError as error:
            raise ContractError(f"Invalid public source URL: {error}") from error
        if url.scheme not in {"https", "http"} or not url.hostname or url.username or url.password:
            raise ContractError("Sources must use public HTTP(S) URLs without credentials")
        urls.add(source["url"])
        accessed = text(source["accessed"], "source.accessed")
        try:
            if date.fromisoformat(accessed).isoformat() != accessed:
                raise ValueError("Use YYYY-MM-DD")
        except ValueError as error:
            raise ContractError(f"Invalid source accessed date: {accessed}") from error
        string_list(source["supported_claims"], "source.supported_claims", nonempty=True)
    if len(urls) < 2:
        raise ContractError("At least two distinct research source URLs are required")
    return ids


def _workflow(value: dict, source_ids: set[str]) -> set[str]:
    object_fields(value, {"schema_version", "rules", "steps"}, "workflow")
    version(value["schema_version"], "workflow")
    rules = _array(value["rules"], "workflow.rules", 1)
    rule_ids = _unique_ids(rules, "workflow.rules")
    for rule in rules:
        object_fields(rule, {"id", "description", "provenance"}, "rule")
        text(rule["description"], "rule.description")
        provenance = object_fields(rule["provenance"], {"kind", "source_ids", "note"}, "rule.provenance")
        if provenance["kind"] not in ("source-backed", "sample-policy"):
            raise ContractError("Rule provenance must distinguish source-backed and sample-policy")
        references = string_list(provenance["source_ids"], "rule.provenance.source_ids")
        if set(references) - source_ids:
            raise ContractError("Rule cites a nonexistent research source")
        if provenance["kind"] == "source-backed" and not references:
            raise ContractError("Source-backed rules require at least one source")
        text(provenance["note"], "rule.provenance.note")
    steps = _array(value["steps"], "workflow.steps", 6)
    _unique_ids(steps, "workflow.steps")
    kinds, used_rules = set(), set()
    for step in steps:
        object_fields(step, {"id", "kind", "title", "rule_ids", "procedure"}, "step")
        if not isinstance(step["kind"], str) or step["kind"] not in KINDS:
            raise ContractError("Unsupported workflow step kind")
        kinds.add(step["kind"])
        text(step["title"], "step.title")
        text(step["procedure"], "step.procedure")
        references = string_list(step["rule_ids"], "step.rule_ids")
        if set(references) - rule_ids:
            raise ContractError("Workflow step cites a nonexistent rule")
        used_rules.update(references)
    if kinds != KINDS:
        raise ContractError(f"Workflow is missing step kinds: {sorted(KINDS - kinds)}")
    if used_rules != rule_ids:
        raise ContractError(f"Rules are not wired into a workflow step: {sorted(rule_ids - used_rules)}")
    return rule_ids


def baseline_import_audit(path: Path) -> dict:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (SyntaxError, UnicodeError) as error:
        raise ContractError(f"Baseline source is not valid Python: {error}") from error
    imports = set()
    prohibited = {
        "socket", "http", "urllib", "ftplib", "smtplib", "webbrowser", "subprocess",
        "multiprocessing", "ctypes", "ensurepip", "venv",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                raise ContractError("Baseline relative imports are not supported")
            imports.add((node.module or "").split(".")[0])
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in {"eval", "exec", "compile", "__import__"}:
                raise ContractError("Dynamic code execution is not permitted in a baseline")
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            value = node.value.replace("\\", "/").lower()
            if value == "expected" or "expected/" in value or "creator_builder" in value or "apppackage/" in value:
                raise ContractError("Baseline source references a withheld golden or Creator runtime")
    unsupported = imports - set(sys.stdlib_module_names) - {"scenario_support", "__future__"}
    if unsupported or imports & prohibited:
        raise ContractError(f"Baseline imports unsupported or prohibited modules: {sorted(unsupported | (imports & prohibited))}")
    return {
        "imports": sorted(imports),
        "status": "static_import_check_pass",
        "limitation": "Trusted local code only; this is not a sandbox or proof of oracle independence.",
    }


def load_scenario(root: Path) -> Scenario:
    root = no_links(root).resolve()
    manifest = load_json(contained_path(root, "scenario.json"))
    object_fields(manifest, MANIFEST_FIELDS, "scenario")
    version(manifest["schema_version"], "scenario")
    for key in ("id", "industry", "workflow_family"):
        slug(manifest[key], "scenario." + key)
    if root.parent.name != manifest["industry"]:
        raise ContractError("Scenario industry must match its containing industry directory")
    slug(root.name, "scenario directory")
    for key in ("title", "description", "owner_role"):
        text(manifest[key], "scenario." + key)
    if manifest["risk_level"] not in ("low", "medium", "high"):
        raise ContractError("Invalid scenario risk_level")
    for key, value in FIXED_PATHS.items():
        if manifest[key] != value:
            raise ContractError(f"scenario.{key} must be {value!r}")
        contained_path(root, value, must_exist=key != "video")
    policy = object_fields(manifest["sample_policy"], {"synthetic_only", "no_live_actions", "description"}, "sample_policy")
    if policy["synthetic_only"] is not True or policy["no_live_actions"] is not True:
        raise ContractError("Only synthetic, no-live-action scenarios are allowed")
    text(policy["description"], "sample_policy.description")
    golden = object_fields(manifest["golden_provenance"], {"method", "author", "description"}, "golden_provenance")
    if golden["method"] != "independent-manual-derivation":
        raise ContractError("Goldens must be independently manually derived, never baseline-generated")
    text(golden["author"], "golden_provenance.author")
    text(golden["description"], "golden_provenance.description")
    sources = load_json(contained_path(root, "sources.json"))
    workflow = load_json(contained_path(root, "workflow.json"))
    rule_ids = _workflow(workflow, _sources(sources))
    connections = load_json(contained_path(root, "connections.json"))
    object_fields(connections, {"schema_version", "mode", "availability", "connections", "note"}, "connections")
    version(connections["schema_version"], "connections")
    if connections["mode"] != "mock-exports-only" or connections["availability"] != "not-required" or connections["connections"] != []:
        raise ContractError("No native connection availability or metadata may be invented for mock exports")
    text(connections["note"], "connections.note")
    procedure = contained_path(root, "HOW_TO.md").read_text(encoding="utf-8")
    text(procedure, "HOW_TO.md", maximum=1_000_000)
    baseline_import_audit(contained_path(root, "baseline.py"))
    cases = _array(manifest["cases"], "scenario.cases", 5)
    _unique_ids(cases, "scenario.cases")
    counts, covered, failures, inputs = Counter(), set(), set(), {}
    for case in cases:
        object_fields(case, CASE_FIELDS, "case")
        if case["kind"] not in ("demo", "holdout", "negative"):
            raise ContractError("Case kind must be demo, holdout, or negative")
        counts[case["kind"]] += 1
        if (case["id"] == "demo") != (case["kind"] == "demo"):
            raise ContractError("The sole demo case must have id demo")
        for key, directory in (("input", "mock-data"), ("expected", "expected")):
            if case[key] != f"{directory}/{case['id']}.json":
                raise ContractError(f"Case {key} must follow {directory}/<case-id>.json")
        if not isinstance(case["expected_status"], str) or case["expected_status"] not in STATUSES:
            raise ContractError("Invalid expected business status")
        references = string_list(case["covers"], "case.covers", nonempty=True)
        if set(references) - rule_ids:
            raise ContractError("Case covers a nonexistent rule")
        covered.update(references)
        modes = string_list(case["failure_modes"], "case.failure_modes")
        if case["kind"] == "negative":
            failures.update(modes)
        text(case["derivation"], "case.derivation")
        payload = load_json(contained_path(root, case["input"]))
        if not isinstance(payload, dict):
            raise ContractError(f"{case['input']}: inputs must be JSON objects, including business negatives")
        fingerprint = digest(json_bytes(payload))
        if fingerprint in inputs:
            raise ContractError(f"Input case {case['id']} duplicates {inputs[fingerprint]}; use genuinely different data")
        inputs[fingerprint] = case["id"]
        expected = validate_result(load_json(contained_path(root, case["expected"])), case["expected"])
        if expected["status"] != case["expected_status"]:
            raise ContractError("Case expected_status disagrees with its independent golden")
    if counts["demo"] != 1 or counts["holdout"] < 2 or counts["negative"] < 2:
        raise ContractError("Require exactly one demo, at least two holdouts, and at least two negatives")
    if not {"malformed-input", "contradictory-evidence"}.issubset(failures):
        raise ContractError("Negative cases must cover malformed-input and contradictory-evidence")
    if covered != rule_ids:
        raise ContractError(f"Rules have no evaluation case: {sorted(rule_ids - covered)}")
    return Scenario(root, manifest, workflow, sources, connections)


def validate_trace(trace: dict, scenario: Scenario, case: dict, input_sha256: str) -> dict:
    object_fields(trace, {"schema_version", "provenance", "scenario_id", "input_sha256", "events"}, "trace")
    version(trace["schema_version"], "trace")
    if trace["provenance"] != "synthetic-local-baseline" or trace["scenario_id"] != scenario.id:
        raise ContractError("Trace has incorrect synthetic baseline provenance or scenario identity")
    if not isinstance(input_sha256, str) or trace["input_sha256"] != input_sha256 or not SHA256.fullmatch(input_sha256):
        raise ContractError("Trace does not bind to the actual input bytes")
    events = _array(trace["events"], "trace.events", 1)
    steps = {step["id"]: step for step in scenario.workflow["steps"]}
    for sequence, event in enumerate(events, start=1):
        object_fields(event, {"sequence", "step_id", "kind", "caption", "facts", "tables"}, "trace.event")
        if type(event["sequence"]) is not int or event["sequence"] != sequence:
            raise ContractError("Trace sequence must be contiguous and one-based")
        step_id = text(event["step_id"], "trace.step_id")
        if step_id not in steps or event["kind"] != steps[step_id]["kind"]:
            raise ContractError("Trace event must refer to a documented step of the same kind")
        text(event["caption"], "trace.caption", maximum=260)
        facts = event["facts"]
        if not isinstance(facts, dict) or len(facts) > 6:
            raise ContractError("Trace facts must be an object with at most six named values")
        for key, value in facts.items():
            text(key, "trace.fact name")
            if not scalar(value):
                raise ContractError("Trace facts must be scalar JSON values")
        tables = _array(event["tables"], "trace.tables", 1)
        if len(tables) > 2:
            raise ContractError("Trace supports at most two readable tables per event")
        for table in tables:
            object_fields(table, {"title", "columns", "rows", "total_rows", "highlight_rows"}, "trace.table")
            text(table["title"], "trace.table.title")
            columns = string_list(table["columns"], "trace.columns", nonempty=True)
            if len(columns) > 6:
                raise ContractError("Trace tables support at most six columns")
            rows = _array(table["rows"], "trace.rows")
            if len(rows) > 8:
                raise ContractError("Trace tables support at most eight displayed rows")
            for row in rows:
                if not isinstance(row, list) or len(row) != len(columns) or not all(scalar(value) for value in row):
                    raise ContractError("Trace rows must have one scalar value per column")
            if type(table["total_rows"]) is not int or table["total_rows"] < len(rows):
                raise ContractError("Trace total_rows must include every displayed row")
            highlights = _array(table["highlight_rows"], "trace.highlight_rows")
            if any(type(index) is not int or not 0 <= index < len(rows) for index in highlights):
                raise ContractError("Trace highlight rows must refer to displayed zero-based indices")
            if len(set(highlights)) != len(highlights):
                raise ContractError("Duplicate trace row highlight")
    if case["kind"] == "demo":
        kinds = {event["kind"] for event in events}
        if len(events) < 6 or kinds != KINDS or events[0]["kind"] != "input" or events[-1]["kind"] != "output":
            raise ContractError("Demo requires all six meaningful step kinds, starting at input and ending at output")
    return trace


def discover(root: Path) -> list[Scenario]:
    root = no_links(root).resolve()
    if not root.is_dir():
        raise ContractError(f"Scenario root does not exist: {root}")
    scenarios = []
    ids = set()
    for industry in sorted(root.iterdir()):
        no_links(industry)
        if not industry.is_dir() or industry.name.startswith(("_", ".")) or industry.name == "tests":
            continue
        for directory in sorted(industry.iterdir()):
            no_links(directory)
            if not directory.is_dir() or directory.name.startswith(("_", ".")):
                continue
            if not (directory / "scenario.json").exists():
                raise ContractError(f"Unexpected scenario directory without scenario.json: {directory}")
            scenario = load_scenario(directory)
            if scenario.id in ids:
                raise ContractError(f"Duplicate corpus scenario id: {scenario.id}")
            ids.add(scenario.id)
            scenarios.append(scenario)
    return scenarios
