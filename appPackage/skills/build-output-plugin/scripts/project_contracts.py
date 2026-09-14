"""Closed authoring contracts and coverage checks, not a workflow interpreter."""
from __future__ import annotations

import hashlib
import re
from datetime import date
from pathlib import Path

import creator_builder as b

CAPABILITIES = {
    "files.read", "files.write", "python.stdlib", "media.images",
    "media.video-frames", "documents.edit", "browser.native", "business.tool",
    "schedule.native", "desktop.arbitrary",
}
REQUIRED_FILES = {
    "inputs.json", "observations.json", "workflow-blueprint.json",
    "decisions.json", "host-profile.json", "build-state.json",
}
OPTIONAL_FILES = {"evaluation-results.json", "candidate-plan.json", "capability-report.json", "creation-report.md"}
PROJECT_DIRECTORIES = {"candidate", "history"}
INPUT_TYPES = {"file", "string", "integer", "decimal", "date", "boolean"}


def choice(value: object, allowed: set[str], label: str) -> str:
    b.require(isinstance(value, str) and value in allowed, f"{label}: expected one of {', '.join(sorted(allowed))}")
    return value


def integer(value: object, low: int, high: int, label: str) -> int:
    b.require(type(value) is int and low <= value <= high, f"{label}: expected integer {low}-{high}")
    return value


def boolean(value: object, label: str) -> bool:
    b.require(type(value) is bool, f"{label}: expected a Boolean")
    return value


def array(value: object, label: str, maximum: int = 500) -> list:
    b.require(isinstance(value, list) and len(value) <= maximum, f"{label}: expected an array of at most {maximum} items")
    return value


def identifiers(value: object, label: str) -> list[str]:
    values = array(value, label)
    for item in values:
        b.slug(item, label + " item")
    b.require(len(set(values)) == len(values), f"{label}: duplicate reference")
    return values


def sha(value: object, label: str, nullable: bool = False) -> str | None:
    if nullable and value is None:
        return None
    b.require(isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value) is not None, f"{label}: expected an actual lowercase SHA256")
    return value


def indexed(items: object, keys: set[str], label: str) -> dict[str, dict]:
    result = {}
    for index, item in enumerate(array(items, label)):
        item = b.exact_keys(item, keys, f"{label}[{index}]")
        identifier = b.slug(item["id"], label + ".id")
        b.require(identifier not in result, f"{label}: duplicate id")
        result[identifier] = item
    return result


def document(path: Path, project_id: str, fields: set[str]) -> dict:
    data = b.read_json(path)
    b.check_text(path.read_bytes(), path.name, allow_templates=True)
    b.exact_keys(data, {"format_version", "project_id"} | fields, path.name)
    integer(data["format_version"], 1, 1, path.name + ".format_version")
    b.require(data["project_id"] == project_id, f"{path.name}: project_id mismatch")
    return data


def candidate_fingerprint(source: Path) -> tuple[str, dict[str, bytes], dict, list]:
    payload, spec, connectors = b.source_payload(source)
    files = dict(payload)
    files["plugin-spec.json"] = (source / "plugin-spec.json").read_bytes()
    inventory = {name: hashlib.sha256(content).hexdigest() for name, content in sorted(files.items())}
    return hashlib.sha256(b.json_bytes(inventory)).hexdigest(), payload, spec, connectors


def evidence_fingerprint(inputs: dict, observations: dict) -> str:
    normalized = dict(inputs, sources=[
        {key: value for key, value in source.items() if key != "availability"}
        for source in inputs["sources"]
    ])
    return hashlib.sha256(b.json_bytes({"inputs": normalized, "observations": observations})).hexdigest()


def validate_project(project: Path) -> dict:
    b.check_regular(project, directory=True)
    project = project.resolve(strict=True)
    roots = {path.name for path in project.iterdir()}
    b.require(REQUIRED_FILES <= roots <= REQUIRED_FILES | OPTIONAL_FILES | PROJECT_DIRECTORIES, "Project must contain the required authoring files and no unrecognized/raw attachments")
    for name in roots - PROJECT_DIRECTORIES:
        b.check_regular(project / name)
        b.require((project / name).stat().st_size <= b.MAX_COMPANION_BYTES, f"{name}: authoring file exceeds 5 MB")
    raw_blueprint = (project / "workflow-blueprint.json").read_bytes()
    initial = b.parse_json(raw_blueprint, "workflow-blueprint.json")
    project_id = b.slug(initial.get("project_id"), "project_id")
    blueprint = document(project / "workflow-blueprint.json", project_id, {
        "revision", "status", "title", "purpose", "evidence_sha256", "invocation_mode", "invocation_prompt",
        "inputs", "outputs", "steps", "constants", "bindings", "evaluation_cases",
    })
    revision = integer(blueprint["revision"], 1, 1_000_000, "blueprint.revision")
    blueprint_sha = hashlib.sha256(raw_blueprint).hexdigest()
    sha(blueprint["evidence_sha256"], "blueprint.evidence_sha256", nullable=True)
    choice(blueprint["status"], {"draft", "confirmed"}, "blueprint.status")
    b.text(blueprint["title"], 100, "blueprint.title")
    b.prose(blueprint["purpose"], 4000, "blueprint.purpose")
    choice(blueprint["invocation_mode"], {"manual", "native-schedule"}, "blueprint.invocation_mode")
    b.prose(blueprint["invocation_prompt"], 4000, "blueprint.invocation_prompt")
    blockers = []

    def block(code: str, detail: str, reference: str = "project") -> None:
        entry = {"code": code, "detail": detail, "reference": reference}
        if entry not in blockers:
            blockers.append(entry)

    if blueprint["status"] != "confirmed":
        block("unconfirmed-blueprint", "Blueprint remains a draft.")
    inputs_doc = document(project / "inputs.json", project_id, {"sources"})
    sources = indexed(inputs_doc["sources"], {"id", "name", "kind", "order", "sha256", "availability"}, "sources")
    screenshot_orders = []
    for identifier, source in sources.items():
        b.text(source["name"], 256, identifier + ".name")
        b.require("/" not in source["name"] and "\\" not in source["name"], f"{identifier}: store a source filename/identifier, not a machine path")
        choice(source["kind"], {"procedure", "video", "screenshot", "reference", "runtime-example"}, identifier + ".kind")
        choice(source["availability"], {"attached", "recorded", "missing"}, identifier + ".availability")
        sha(source["sha256"], identifier + ".sha256", nullable=True)
        if source["kind"] == "screenshot":
            screenshot_orders.append(integer(source["order"], 1, 10000, identifier + ".order"))
        else:
            b.require(source["order"] is None, f"{identifier}: order is only for screenshot sequences")
        if source["availability"] == "missing" and source["kind"] in {"procedure", "video", "screenshot"}:
            block("missing-evidence", "Required source must be reattached or its omission explicitly resolved.", identifier)
    b.require(len(screenshot_orders) == len(set(screenshot_orders)), "sources: screenshot ordering must be unique")
    if screenshot_orders:
        b.require(sorted(screenshot_orders) == list(range(1, len(screenshot_orders) + 1)), "sources: screenshot order must be contiguous from 1")
    if not any(item["kind"] == "procedure" for item in sources.values()):
        block("missing-procedure", "A process description is required.")
    if not any(item["kind"] in {"video", "screenshot"} for item in sources.values()):
        block("missing-demonstration", "Provide a video or ordered screenshots; do not invent observation.")

    observations_doc = document(project / "observations.json", project_id, {"items", "questions"})
    evidence_sha = evidence_fingerprint(inputs_doc, observations_doc)
    if blueprint["status"] == "confirmed" and blueprint["evidence_sha256"] != evidence_sha:
        block("stale-blueprint-evidence", "Evidence changed or has not been reviewed against this blueprint; update the revision and support links.")
    observations = indexed(observations_doc["items"], {"id", "source_id", "source_sha256", "kind", "text", "locator", "confidence"}, "observations")
    questions = indexed(observations_doc["questions"], {"id", "text", "evidence_ids"}, "questions")
    stale_observations = set()
    for identifier, observation in observations.items():
        b.require(isinstance(observation["source_id"], str) and observation["source_id"] in sources, f"{identifier}: unknown source_id")
        source = sources[observation["source_id"]]
        sha(observation["source_sha256"], identifier + ".source_sha256", nullable=True)
        if observation["source_sha256"] != source["sha256"]:
            stale_observations.add(identifier)
            block("stale-observation", "Source fingerprint changed; re-observe before relying on it.", identifier)
        choice(observation["kind"], {"observed", "documented", "inferred"}, identifier + ".kind")
        b.prose(observation["text"], 10000, identifier + ".text")
        b.require(type(observation["confidence"]) in {int, float} and 0 <= observation["confidence"] <= 1, f"{identifier}: confidence must be 0-1, independent of support status")
        locator = b.exact_keys(observation["locator"], {"label", "frame_ordinal", "seconds"}, identifier + ".locator")
        b.text(locator["label"], 1000, identifier + ".locator.label")
        if source["kind"] != "video":
            b.require(locator["frame_ordinal"] is None and locator["seconds"] is None, f"{identifier}: video timing cannot be attached to non-video evidence")
        if locator["frame_ordinal"] is not None:
            integer(locator["frame_ordinal"], 1, 1_000_000, identifier + ".frame_ordinal")
        if locator["seconds"] is not None:
            b.require(type(locator["seconds"]) in {int, float} and 0 <= locator["seconds"] <= 10_000_000, f"{identifier}: invalid observed time")
    if not any(item["kind"] == "observed" and sources[item["source_id"]]["kind"] in {"video", "screenshot"} for item in observations.values()):
        block("unobserved-demonstration", "No actual visual observation is recorded.")

    def evidence(value: object, label: str, required: bool = True) -> list[str]:
        refs = identifiers(value, label)
        b.require(set(refs) <= set(observations), f"{label}: unknown evidence reference")
        if required and not refs:
            block("missing-support", "Consequential rules need observed/documented evidence or a current user decision.", label)
        if set(refs) & stale_observations:
            block("stale-support", "The rule references changed evidence.", label)
        return refs

    for identifier, question in questions.items():
        b.prose(question["text"], 4000, identifier + ".text")
        evidence(question["evidence_ids"], identifier + ".evidence_ids", required=False)
    decisions_doc = document(project / "decisions.json", project_id, {"blueprint_revision", "blueprint_sha256", "items"})
    integer(decisions_doc["blueprint_revision"], 1, 1_000_000, "decisions.blueprint_revision")
    sha(decisions_doc["blueprint_sha256"], "decisions.blueprint_sha256", nullable=True)
    decisions = indexed(decisions_doc["items"], {"id", "question_id", "answer", "outcome", "source"}, "decisions")
    current_decisions = decisions_doc["blueprint_revision"] == revision and decisions_doc["blueprint_sha256"] == blueprint_sha
    if decisions and not current_decisions:
        block("stale-decisions", "User decisions refer to a different blueprint revision or byte hash.")
    resolved_questions = set()
    for identifier, decision in decisions.items():
        b.require(isinstance(decision["question_id"], str) and decision["question_id"] in questions, f"{identifier}: unknown question")
        b.prose(decision["answer"], 4000, identifier + ".answer")
        choice(decision["source"], {"user"}, identifier + ".source")
        choice(decision["outcome"], {"confirmed", "rejected"}, identifier + ".outcome")
        if current_decisions and decision["outcome"] == "confirmed":
            resolved_questions.add(decision["question_id"])
    for identifier in questions.keys() - resolved_questions:
        block("unresolved-question", questions[identifier]["text"], identifier)

    host = document(project / "host-profile.json", project_id, {"context", "capabilities", "connections"})
    choice(host["context"], {"native-observed", "offline-synthetic", "unverified"}, "host.context")
    capabilities = {}
    if host["context"] == "unverified":
        block("host-context-unverified", "Recheck the current native environment; historical or missing availability is not current support.")
    for item in array(host["capabilities"], "capabilities", 20):
        b.exact_keys(item, {"id", "status", "evidence"}, "capability")
        identifier = choice(item["id"], CAPABILITIES, "capability.id")
        b.require(identifier not in capabilities, "capabilities: duplicate id")
        choice(item["status"], {"available", "unverified", "unsupported"}, identifier + ".status")
        b.require(isinstance(item["evidence"], str) and len(item["evidence"]) <= 4000, f"{identifier}: invalid evidence")
        if item["status"] != "unverified":
            b.prose(item["evidence"], 4000, identifier + ".evidence")
        capabilities[identifier] = item
    connections = indexed(host["connections"], {"id", "mode", "status", "native_id", "tools", "provenance", "availability_evidence"}, "connections")
    for identifier, connection in connections.items():
        choice(connection["mode"], {"existing-native", "packaged-remote"}, identifier + ".mode")
        choice(connection["status"], {"available", "needs-setup", "unverified", "unsupported"}, identifier + ".status")
        if connection["native_id"] is not None:
            b.text(connection["native_id"], 1024, identifier + ".native_id")
        b.provenance(connection["provenance"], identifier + ".provenance")
        b.require(isinstance(connection["availability_evidence"], str) and len(connection["availability_evidence"]) <= 4000, f"{identifier}: invalid availability evidence")
        if connection["tools"]:
            b.tool_descriptions(connection["tools"], identifier + ".tools")
        else:
            array(connection["tools"], identifier + ".tools")
        if connection["status"] == "available":
            b.require(bool(connection["tools"]), f"{identifier}: available connections require real exposed tool metadata")
            b.prose(connection["availability_evidence"], 4000, identifier + ".availability_evidence")

    declared_inputs = indexed(blueprint["inputs"], {"id", "type", "required", "description", "default", "default_evidence"}, "inputs")
    outputs = indexed(blueprint["outputs"], {"id", "description"}, "outputs")
    for identifier, item in declared_inputs.items():
        choice(item["type"], INPUT_TYPES, identifier + ".type")
        boolean(item["required"], identifier + ".required")
        b.prose(item["description"], 4000, identifier + ".description")
        refs = evidence(item["default_evidence"], identifier + ".default_evidence", required=False)
        default = item["default"]
        if default is not None:
            valid = (
                (item["type"] in {"file", "string"} and isinstance(default, str))
                or (item["type"] == "integer" and type(default) is int)
                or (item["type"] == "boolean" and type(default) is bool)
                or (item["type"] == "decimal" and isinstance(default, str) and re.fullmatch(r"-?[0-9]+(?:\.[0-9]+)?", default))
                or (item["type"] == "date" and isinstance(default, str) and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", default))
            )
            if valid and item["type"] == "date":
                try:
                    date.fromisoformat(default)
                except ValueError:
                    valid = False
            b.require(bool(valid), f"{identifier}: default does not match its declared type")
            if not refs:
                block("unjustified-default", "Default values need source evidence, not incidental demonstration values.", identifier)
            elif not any(observations[ref]["kind"] in {"observed", "documented"} for ref in refs):
                block("inferred-default", "An inferred sample value must not become a default without confirmed supporting evidence.", identifier)
    for identifier, output in outputs.items():
        b.prose(output["description"], 4000, identifier + ".description")
    if not outputs:
        block("missing-output", "Declare the intended observable output.")
    steps = indexed(blueprint["steps"], {
        "id", "action", "depends_on", "consumes", "produces", "capability",
        "connection_id", "tool_name", "effect", "approval", "on_ambiguous_result",
        "evidence_ids", "decision_id", "condition", "repeat",
    }, "steps")
    if not steps:
        block("missing-steps", "No repeatable workflow steps have been described.")
    coverage, producers, dependencies = [], {}, {}
    for identifier, step in steps.items():
        b.prose(step["action"], 4000, identifier + ".action")
        deps = identifiers(step["depends_on"], identifier + ".depends_on")
        b.require(set(deps) <= set(steps) and identifier not in deps, f"{identifier}: unknown or self dependency")
        dependencies[identifier] = set(deps)
        consumes = array(step["consumes"], identifier + ".consumes")
        for ref in consumes:
            b.require(isinstance(ref, str) and ":" in ref, f"{identifier}: consumes must use input:ID or output:ID")
            kind, target = ref.split(":", 1)
            b.require((kind == "input" and target in declared_inputs) or (kind == "output" and target in outputs), f"{identifier}: unknown consumed value")
        for output in identifiers(step["produces"], identifier + ".produces"):
            b.require(output in outputs and output not in producers, f"{identifier}: unknown or multiply produced output")
            producers[output] = identifier
        capability = choice(step["capability"], CAPABILITIES, identifier + ".capability")
        effect = choice(step["effect"], {"read", "local-write", "business-write"}, identifier + ".effect")
        choice(step["approval"], {"none", "native-each-run"}, identifier + ".approval")
        choice(step["on_ambiguous_result"], {"stop", "inspect-before-retry"}, identifier + ".on_ambiguous_result")
        refs = evidence(step["evidence_ids"], identifier + ".evidence_ids", required=False)
        decision_id = step["decision_id"]
        b.require(decision_id is None or isinstance(decision_id, str) and decision_id in decisions, f"{identifier}: unknown decision")
        confirmed = bool(decision_id and current_decisions and decisions[decision_id]["outcome"] == "confirmed")
        support = sorted({observations[ref]["kind"] for ref in refs})
        if not confirmed and not ({"observed", "documented"} & set(support)):
            block("unconfirmed-rule", "Step has only inferred or absent support and no current user confirmation.", identifier)
        if effect == "business-write":
            if not confirmed:
                block("unconfirmed-business-write", "Business writes require a current user-confirmed authoring decision.", identifier)
            b.require(step["approval"] == "native-each-run", f"{identifier}: business writes must retain native per-run approvals")
        status = capabilities.get(capability, {}).get("status", "unverified")
        if capability == "desktop.arbitrary":
            status = "unsupported"
        if status != "available":
            block("native-capability-gap", f"{capability} is {status}; do not add a runner/service/installer.", identifier)
        connection_id, tool_name = step["connection_id"], step["tool_name"]
        if capability == "business.tool":
            if connection_id is None:
                b.require(tool_name is None, f"{identifier}: a tool cannot exist without a real connection binding")
                block("connection-metadata-missing", "Discover/reuse a real supported connection; do not invent its tools or deploy a server.", identifier)
            else:
                b.require(isinstance(connection_id, str) and connection_id in connections, f"{identifier}: unknown real connection binding")
                connection = connections[connection_id]
                if connection["status"] != "available":
                    block("connection-setup", f"Connection is {connection['status']}; no fictitious binding or new server is allowed.", identifier)
                if tool_name is None:
                    block("tool-metadata-missing", "No actual tool name/descriptor was supplied; do not guess it.", identifier)
                else:
                    b.require(isinstance(tool_name, str) and tool_name in {tool["name"] for tool in connection["tools"]}, f"{identifier}: tool name is absent from supplied/discovered metadata")
                    tool = next(item for item in connection["tools"] if item["name"] == tool_name)
                    if effect != "business-write" and tool.get("annotations", {}).get("readOnlyHint") is False:
                        block("effect-mismatch", "A known non-read-only business tool requires explicit business-write classification and its confirmation/native-approval safeguards, not read or local-write.", identifier)
        else:
            b.require(connection_id is None and tool_name is None, f"{identifier}: conceptual capabilities are not invented callable tool names")
        for field in ("condition", "repeat"):
            value = step[field]
            if value is None:
                continue
            if field == "condition":
                b.exact_keys(value, {"expression", "evidence_ids"}, identifier + ".condition")
                b.text(value["expression"], 4000, identifier + ".condition.expression")
            else:
                b.exact_keys(value, {"input_id", "max_items", "stop_when", "evidence_ids"}, identifier + ".repeat")
                b.require(isinstance(value["input_id"], str) and value["input_id"] in declared_inputs, f"{identifier}: repeat refers to an unknown input")
                integer(value["max_items"], 1, 10000, identifier + ".repeat.max_items")
                b.text(value["stop_when"], 2000, identifier + ".repeat.stop_when")
            control_refs = evidence(value["evidence_ids"], identifier + "." + field + ".evidence_ids", required=not confirmed)
            if not confirmed and not any(observations[ref]["kind"] in {"observed", "documented"} for ref in control_refs):
                block("inferred-control-flow", "Conditions and loops need documented/observed support or a current user confirmation.", identifier)
        coverage.append({"step_id": identifier, "capability": capability, "support": support, "user_confirmed": confirmed, "native_status": status, "effect": effect})
    order, pending = [], set(steps)
    while pending:
        ready = [identifier for identifier in steps if identifier in pending and dependencies[identifier] <= set(order)]
        b.require(bool(ready), "steps: dependency cycle")
        order.extend(ready)
        pending.difference_update(ready)
    for output in outputs.keys() - producers.keys():
        block("unproduced-output", "Declared output has no producing step.", output)
    for identifier, step in steps.items():
        ancestors, pending_deps = set(), list(dependencies[identifier])
        while pending_deps:
            dependency = pending_deps.pop()
            if dependency not in ancestors:
                ancestors.add(dependency)
                pending_deps.extend(dependencies[dependency])
        for ref in step["consumes"]:
            if ref.startswith("output:"):
                producer = producers.get(ref[7:])
                b.require(producer is not None and producer in ancestors, f"{identifier}: consumed output must be produced by a prerequisite")
    constants = indexed(blueprint["constants"], {"id", "value", "classification", "input_id", "evidence_ids", "reason"}, "constants")
    for identifier, constant in constants.items():
        choice(constant["classification"], {"parameter", "derived", "constant", "unknown"}, identifier + ".classification")
        b.require(constant["value"] is None or type(constant["value"]) in {str, int, float, bool}, f"{identifier}: sample values must be scalars")
        b.prose(constant["reason"], 4000, identifier + ".reason")
        evidence(constant["evidence_ids"], identifier + ".evidence_ids")
        if constant["classification"] == "unknown":
            block("unclassified-value", "Resolve whether the demonstrated value is a parameter, derived value or deliberate constant.", identifier)
        elif constant["classification"] == "parameter":
            b.require(isinstance(constant["input_id"], str) and constant["input_id"] in declared_inputs, f"{identifier}: parameter value must reference a declared input")
        else:
            b.require(constant["input_id"] is None, f"{identifier}: non-parameter value must not alias an input")
    cases = indexed(blueprint["evaluation_cases"], {"id", "description", "negative", "expected"}, "evaluation_cases")
    for identifier, case in cases.items():
        b.prose(case["description"], 4000, identifier + ".description")
        b.prose(case["expected"], 4000, identifier + ".expected")
        boolean(case["negative"], identifier + ".negative")
    if not cases or not any(not case["negative"] for case in cases.values()):
        block("missing-positive-case", "Include a held-out or changed-input expected result.")
    if not any(case["negative"] for case in cases.values()):
        block("missing-negative-case", "Include a meaningful failure/rejection case.")

    candidate_sha, payload, spec, emitted_connectors = None, {}, None, []
    if (project / "candidate").exists():
        candidate_sha, payload, spec, emitted_connectors = candidate_fingerprint(project / "candidate")
    else:
        block("missing-candidate", "Author/assemble the independent output source.")
    bindings, helper_steps = {}, set()
    for item in array(blueprint["bindings"], "bindings"):
        b.exact_keys(item, {"step_id", "skill", "files", "test_ids"}, "binding")
        identifier = item["step_id"]
        b.require(isinstance(identifier, str) and identifier in steps and identifier not in bindings, "bindings: unknown/duplicate step")
        b.slug(item["skill"], "binding.skill")
        files = array(item["files"], "binding.files")
        b.require(all(isinstance(path, str) for path in files), "binding.files: expected paths")
        b.require(len(set(files)) == len(files), "binding.files: duplicate paths")
        for path in files:
            b.validate_path(path)
            b.require(path.startswith("skills/" + item["skill"] + "/"), f"{identifier}: binding cannot depend on another skill's filesystem")
            if candidate_sha and path not in payload:
                block("missing-implementation", "Binding points to a missing candidate resource.", identifier)
            if path.endswith(".py"):
                helper_steps.add(identifier)
        if candidate_sha and (spec is None or item["skill"] not in spec["skills"]):
            block("missing-skill", "Binding points to an absent output skill.", identifier)
        test_ids = identifiers(item["test_ids"], "binding.test_ids")
        b.require(set(test_ids) <= set(cases), "binding.test_ids: unknown evaluation case")
        if (identifier in helper_steps or steps[identifier]["effect"] == "business-write") and not test_ids:
            block("untested-implementation", "Helpers and consequential effects need declared synthetic cases.", identifier)
        if identifier in helper_steps and test_ids and not any(cases[case]["negative"] for case in test_ids):
            block("helper-negative-case", "A deterministic helper needs a linked rejection/error case.", identifier)
        if not files:
            block("missing-implementation", "Bind the actual entry skill/resource, not just a label.", identifier)
        bindings[identifier] = item
    for identifier in steps.keys() - bindings.keys():
        block("unbound-step", "Every step needs an output implementation binding.", identifier)
    connector_ids = {item["id"] for item in emitted_connectors}
    for identifier, connection in connections.items():
        used = any(step["connection_id"] == identifier for step in steps.values())
        if used and connection["mode"] == "packaged-remote" and candidate_sha:
            if identifier not in connector_ids:
                block("missing-connector", "Candidate must include the supplied remote connector and tool descriptor.", identifier)
            else:
                declared = next(item for item in spec["connectors"] if item["id"] == identifier)
                actual_tools = b.parse_json(payload[declared["tools_file"]], declared["tools_file"])["tools"]
                if b.json_bytes(actual_tools) != b.json_bytes(connection["tools"]):
                    block("connector-metadata-mismatch", "Candidate tool metadata differs from the binding used for feasibility.", identifier)
    for identifier in connector_ids:
        b.require(identifier in connections and connections[identifier]["mode"] == "packaged-remote", "Candidate connector has no declared real host binding")
    evaluation_path = project / "evaluation-results.json"
    if evaluation_path.exists():
        evaluation = document(evaluation_path, project_id, {"blueprint_revision", "blueprint_sha256", "candidate_sha256", "environment", "cases"})
        integer(evaluation["blueprint_revision"], 1, 1_000_000, "evaluations.blueprint_revision")
        sha(evaluation["candidate_sha256"], "evaluations.candidate_sha256")
        sha(evaluation["blueprint_sha256"], "evaluations.blueprint_sha256")
        choice(evaluation["environment"], {"local", "native"}, "evaluations.environment")
        evaluated = indexed(evaluation["cases"], {"id", "status", "evidence"}, "evaluations.cases")
        b.require(set(evaluated) <= set(cases), "evaluations: unknown case")
        stale = evaluation["candidate_sha256"] != candidate_sha or evaluation["blueprint_revision"] != revision or evaluation["blueprint_sha256"] != blueprint_sha
        if stale:
            block("stale-evaluations", "Candidate source or blueprint changed; old results do not cover the revision.")
        for identifier, result in evaluated.items():
            choice(result["status"], {"passed", "failed", "not-run"}, identifier + ".status")
            b.prose(result["evidence"], 4000, identifier + ".evidence")
        for identifier in cases:
            if evaluated.get(identifier, {}).get("status") != "passed":
                block("evaluation-not-passed", "Declared case has no passing result.", identifier)
    elif cases:
        block("missing-evaluations", "Exercise declared cases and record results against this candidate fingerprint.")
    state = document(project / "build-state.json", project_id, {"blueprint_revision", "phase"})
    integer(state["blueprint_revision"], 1, 1_000_000, "state.blueprint_revision")
    choice(state["phase"], {"intake", "observation", "design", "generation", "review", "packaged"}, "state.phase")
    if state["blueprint_revision"] != revision:
        block("stale-checkpoint", "Authoring checkpoint refers to a different blueprint revision.")
    if blueprint["invocation_mode"] == "native-schedule":
        if capabilities.get("schedule.native", {}).get("status") != "available":
            block("schedule-gap", "Native scheduling availability is not established; use manual invocation.")
        if any(step["effect"] == "business-write" for step in steps.values()):
            block("scheduled-approval-gap", "This subset does not promise unattended business writes or inherited approvals; retain manual/approval-required use.")
    return {
        "format_version": 1, "project_id": project_id, "blueprint_revision": revision,
        "blueprint_sha256": blueprint_sha, "candidate_sha256": candidate_sha,
        "evidence_sha256": evidence_sha,
        "ready": not blockers, "status": "Draft", "host_context": host["context"],
        "coverage": coverage, "blockers": blockers, "step_order": order,
        "native_acceptance": "unverified", "manual_invocation": "unverified",
        "scheduling": "not-exercised",
        "scope": "Checks declared structures, references, support and fingerprints; does not attest media understanding, user authority, actual tool availability or test execution.",
    }
