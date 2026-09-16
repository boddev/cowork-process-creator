"""Build a provisional offline Creator release and executable synthetic examples."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True
import example_projects as examples

b, c, p = examples.b, examples.c, examples.p
ROOT = Path(__file__).resolve().parents[1]
PROOF_HASHES = {
    "dist/creator-bootstrap-compatible-source.zip": "357ce0ade8b27143ab7db7fc99068523d998076da9cd14acbf9dacc073998f9f",
    "dist/n00-v0.1.1/creator-n00.zip": "f31dc061a1d55d797c1ea2008d4bb049c3509f1afee921db20ba3ee88158add1",
    ".local/native-output-15d75761c98a/ready-items.zip": "15d75761c98a1a20818a86ae6a1ec2e96bd83de92fdd4d08184ba6647adf7419",
}


def proof_integrity() -> dict:
    result = {}
    for name, expected in PROOF_HASHES.items():
        path = ROOT / name
        if path.is_file():
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
            if actual != expected:
                raise ValueError("An immutable proof artifact changed: " + name)
            result[name] = actual
    return result


def mutate_document(project: Path, name: str, mutation) -> None:
    value = b.read_json(project / name)
    mutation(value)
    (project / name).write_bytes(b.json_bytes(value))


def negative_cases(base: Path, work: Path) -> list:
    cases = [
        ("unconfirmed", "unconfirmed-blueprint", lambda root: mutate_document(root, "workflow-blueprint.json", lambda doc: doc.update(status="draft"))),
        ("conflicting-evidence", "unresolved-question", lambda root: mutate_document(root, "observations.json", lambda doc: doc["questions"].append({"id": "conflict", "text": "The recording contradicts the procedure; which rule is intended?", "evidence_ids": ["document-rules", "visual-example"]}))),
        ("unavailable-runtime", "native-capability-gap", lambda root: mutate_document(root, "host-profile.json", lambda doc: doc["capabilities"][2].update(status="unverified"))),
        ("desktop-only", "native-capability-gap", lambda root: mutate_document(root, "workflow-blueprint.json", lambda doc: doc["steps"][1].update(capability="desktop.arbitrary"))),
        ("missing-connection", "connection-metadata-missing", lambda root: mutate_document(root, "workflow-blueprint.json", lambda doc: doc["steps"][1].update(capability="business.tool"))),
        ("unclassified-value", "unclassified-value", lambda root: mutate_document(root, "workflow-blueprint.json", lambda doc: doc["constants"][0].update(classification="unknown"))),
        ("changed-evidence", "stale-blueprint-evidence", lambda root: mutate_document(root, "observations.json", lambda doc: doc["items"][0].update(text=doc["items"][0]["text"] + " A material rule changed."))),
        ("stale-evaluation", "stale-evaluations", lambda root: mutate_document(root, "evaluation-results.json", lambda doc: doc.update(candidate_sha256="a" * 64))),
        ("missing-passing-case", "evaluation-not-passed", lambda root: mutate_document(root, "evaluation-results.json", lambda doc: doc["cases"][0].update(status="not-run"))),
    ]
    reports = []
    for name, expected, mutation in cases:
        project = work / name
        shutil.copytree(base, project)
        mutation(project)
        result = c.validate_project(project)
        codes = [entry["code"] for entry in result["blockers"]]
        if result["ready"] or expected not in codes:
            raise AssertionError(f"{name}: expected {expected}, got {codes}")
        reports.append({"id": name, "kind": "negative-variant", "outcome": "expected-block", "expected_code": expected, "actual_codes": codes, "native_claim": False})
    for name, content, expected in (
        ("forbidden-helper", "import requests\n", "import outside"),
        ("unresolved-template", "value = '{{unresolved}}'\n", "unresolved template"),
    ):
        project = work / name
        shutil.copytree(base, project)
        helper = project / "candidate" / "skills" / "cost-report" / "scripts" / "main.py"
        helper.write_text(content, encoding="utf-8")
        try:
            c.validate_project(project)
        except b.BuildError as exc:
            if expected not in str(exc):
                raise
            reports.append({"id": name, "kind": "negative-variant", "outcome": "expected-rejection", "diagnostic": str(exc), "native_claim": False})
        else:
            raise AssertionError(name + ": unsafe/unresolved source was not rejected")
    return reports


def public_connection_example(destination: Path) -> dict:
    p.init_project(destination, "learn-reading-list", "Learn reading list", "Find public documentation using an actually available native Microsoft Learn connection and produce a reading list.")
    fixture = ROOT / "examples" / "offline" / "public-learn"
    tools = b.read_json(fixture / "learn-mcp-tools.json")["tools"]
    b.tool_descriptions(tools, "real public metadata")
    header = {"format_version": 1, "project_id": "learn-reading-list"}
    procedure = "Require an explicit documentation query and new Markdown output. Use an existing native Microsoft Learn connection only after availability is observed. Return a cited reading list. Do not create a server, install a client, fetch through a generated network helper or modify business data."
    evidence = destination.parent / (destination.name + "-evidence")
    evidence.mkdir()
    (evidence / "reading-list-procedure.md").write_bytes(procedure.encode("utf-8"))
    inputs = dict(header, sources=[
        {"id": "procedure", "name": "reading-list-procedure.md", "kind": "procedure", "order": None, "sha256": hashlib.sha256(procedure.encode()).hexdigest(), "availability": "recorded"},
        {"id": "public-metadata", "name": "learn-mcp-tools.json", "kind": "reference", "order": None, "sha256": hashlib.sha256((fixture / "learn-mcp-tools.json").read_bytes()).hexdigest(), "availability": "recorded"},
    ])
    observations = dict(header, items=[
        {"id": "procedure-rule", "source_id": "procedure", "source_sha256": inputs["sources"][0]["sha256"], "kind": "documented", "text": procedure, "locator": {"label": "Synthetic optional reading-list procedure", "frame_ordinal": None, "seconds": None}, "confidence": 1},
        {"id": "metadata-fact", "source_id": "public-metadata", "source_sha256": inputs["sources"][1]["sha256"], "kind": "documented", "text": "Actual public metadata lists microsoft_docs_search, microsoft_code_sample_search and microsoft_docs_fetch. No Cowork availability or workflow execution was observed.", "locator": {"label": "Public tools/list metadata snapshot, not a UI demonstration", "frame_ordinal": None, "seconds": None}, "confidence": 1},
    ], questions=[])
    (destination / "inputs.json").write_bytes(b.json_bytes(inputs))
    (destination / "observations.json").write_bytes(b.json_bytes(observations))
    host = b.read_json(destination / "host-profile.json")
    host.update(context="offline-synthetic", capabilities=[
        {"id": "business.tool", "status": "unverified", "evidence": ""},
        {"id": "files.write", "status": "available", "evidence": "Synthetic offline file-output assumption, not a native observation."},
    ])
    host["connections"] = [{
        "id": "microsoft-learn", "mode": "existing-native", "status": "needs-setup",
        "native_id": None, "tools": tools, "availability_evidence": "",
        "provenance": {"kind": "user-supplied", "reference": "Microsoft Learn public MCP tools/list snapshot dated 2026-09-12T01:43:37Z. See supplied provenance; not observed in Cowork."},
    }]
    (destination / "host-profile.json").write_bytes(b.json_bytes(host))
    bp = b.read_json(destination / "workflow-blueprint.json")
    bp.update(evidence_sha256=c.evidence_fingerprint(inputs, observations),
              invocation_prompt="Use the existing native Learn connection, if actually available, for my explicit query and create a new reading-list file.",
              inputs=[{"id": name, "type": "string", "required": True, "description": description, "default": None, "default_evidence": []}
                      for name, description in (("query", "An explicit documentation topic; a workflow requirement, not a changed MCP schema."), ("output-name", "A new Markdown filename."))],
              outputs=[{"id": "search-results", "description": "Actual returned documentation matches."}, {"id": "reading-list", "description": "A new cited Markdown reading list."}],
              steps=[
                  {"id": "search", "action": "Use the actual native microsoft_docs_search tool with the supplied query.", "depends_on": [], "consumes": ["input:query"], "produces": ["search-results"], "capability": "business.tool", "connection_id": "microsoft-learn", "tool_name": "microsoft_docs_search", "effect": "read", "approval": "none", "on_ambiguous_result": "stop", "evidence_ids": ["procedure-rule", "metadata-fact"], "decision_id": None, "condition": None, "repeat": None},
                  {"id": "deliver", "action": "Produce a new cited Markdown file from actual results; never invent results.", "depends_on": ["search"], "consumes": ["output:search-results", "input:output-name"], "produces": ["reading-list"], "capability": "files.write", "connection_id": None, "tool_name": None, "effect": "local-write", "approval": "none", "on_ambiguous_result": "stop", "evidence_ids": ["procedure-rule"], "decision_id": None, "condition": None, "repeat": None},
              ],
              bindings=[{"step_id": name, "skill": "learn-reading-list", "files": ["skills/learn-reading-list/SKILL.md", "skills/learn-reading-list/references/binding.md"], "test_ids": ["native-query", "missing-native-tool"]} for name in ("search", "deliver")],
              evaluation_cases=[
                  {"id": "native-query", "description": "Use a new query with an actually available native connection.", "negative": False, "expected": "Actual cited results in a new file; not exercised offline."},
                  {"id": "missing-native-tool", "description": "Try the workflow without a native connection.", "negative": True, "expected": "Explicit setup/capability blocker, no invented results or server."},
              ])
    (destination / "workflow-blueprint.json").write_bytes(b.json_bytes(bp))
    plan = {"format_version": 1, "plugin": {
        "schema_version": b.SPEC_VERSION, "name": "learn-reading-list", "title": "Learn reading list",
        "version": b.VERSION, "summary": "Draft reading-list workflow using an existing native Learn connection.",
        "description": "Optional real-public-metadata example. Native connection availability and invocation remain unverified; not a Creator dependency.",
        "skills": ["learn-reading-list"], "connectors": [],
    }, "skills": [{
        "name": "learn-reading-list", "description": "Prepare a public documentation reading list for an explicit query, only when the actual native Microsoft Learn connection is available.",
        "body": "# Native Learn reading list\n\nRead `references/binding.md` first. Require a query and new output filename. Confirm that the actual native microsoft_docs_search tool is exposed and usable; if absent, explain the native setup gap. Do not create a server, install a client, write a network helper or invent results. Use the real tool metadata unchanged, then create a cited Markdown reading list from its actual results. The original metadata-only example was not invoked in Cowork and is not a ready connection claim.\n",
        "companions": [{"path": "references/binding.md", "content": "# Binding boundary\n\n" + procedure + "\n\nPublic endpoint: https://learn.microsoft.com/api/mcp. Tools/list metadata alone is not native availability. Service identity/terms are not publisher metadata for this plugin. No direct connector is declared here; reuse a real existing native connection only.\n"}],
    }], "tools": []}
    (destination / "candidate-plan.json").write_bytes(b.json_bytes(plan))
    p.assemble_candidate(destination / "candidate-plan.json", destination / "candidate")
    checked = c.validate_project(destination)
    (destination / "evaluation-results.json").write_bytes(b.json_bytes(dict(header,
        blueprint_revision=1, blueprint_sha256=checked["blueprint_sha256"], candidate_sha256=checked["candidate_sha256"],
        environment="local", cases=[{"id": case["id"], "status": "not-run", "evidence": "No native connection or workflow invocation was performed; the metadata probe made no tools/call requests."} for case in bp["evaluation_cases"]])))
    result = c.validate_project(destination)
    if result["ready"] or "connection-setup" not in {item["code"] for item in result["blockers"]}:
        raise AssertionError("Public metadata must not become a native availability claim")
    return result


def materialize_release(destination: Path, files: dict[str, bytes]) -> None:
    if destination.exists():
        actual = {path.relative_to(destination).as_posix(): path.read_bytes() for path in destination.rglob("*") if path.is_file()}
        if actual != files:
            raise FileExistsError("Release directory differs; use a new version/output directory instead of overwriting artifacts")
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    p.write_tree_new(destination, files)


def release_metadata(directory: Path | None) -> dict[str, Path]:
    b.require(directory is not None, "Native Microsoft Cowork release packaging requires --metadata-dir with approved metadata for each package; no Claude-compatible fallback is produced")
    b.check_regular(directory, directory=True)
    paths = {}
    app_ids = set()
    for name in ("cowork-process-creator", *examples.FAMILIES):
        path = directory / (name + ".json")
        metadata = b.publishing_metadata(path)
        b.require(metadata["app_id"] not in app_ids, "Each independently installed package requires a distinct supplied app_id")
        app_ids.add(metadata["app_id"])
        paths[name] = path
    return paths


def build_release(destination: Path, metadata_dir: Path | None = None) -> dict:
    metadata = release_metadata(metadata_dir)
    preserved = proof_integrity()
    source = ROOT / "appPackage"
    _, spec, _ = b.source_payload(source)
    if spec["version"] != b.VERSION:
        raise ValueError("Creator package and toolkit versions must agree")
    with tempfile.TemporaryDirectory(prefix="creator-release-") as temporary:
        temporary_root = Path(temporary)
        stage, work = temporary_root / "release", temporary_root / "work"
        stage.mkdir()
        work.mkdir()
        creator = b.build(source, stage / "creator.zip", stage / "creator.report.json", b.TARGET, metadata[spec["name"]])
        sample_reports = []
        base = None
        for family in examples.FAMILIES:
            project = work / family
            checked = examples.create_project(project, family)
            if not checked["ready"]:
                raise AssertionError(checked["blockers"])
            sample = stage / "examples" / family
            sample.mkdir(parents=True)
            build = p.build_project(project, sample / "plugin.zip", sample / "build.json", b.TARGET, metadata[family])
            p.checkpoint(project, sample / "source.zip")
            restored = work / (family + "-resumed")
            resume = p.resume(sample / "source.zip", restored)
            refreshed = c.validate_project(restored)
            if refreshed["ready"] or not resume["requires_host_recheck"]:
                raise AssertionError("Resume incorrectly inherited runtime readiness")
            (sample / "coverage.json").write_bytes(b.json_bytes(checked))
            (sample / "resume.json").write_bytes(b.json_bytes(refreshed))
            evidence = project.parent / (project.name + "-evidence")
            for name in ("procedure.md", "01-demo.png", "new-input.json", "actual-report.md"):
                (sample / name).write_bytes((evidence / name).read_bytes())
            sample_reports.append({"id": family, "kind": "distinct-file-workflow", "outcome": "local-helper-and-project-check-passed", "plugin_sha256": build["sha256"], "native_claim": False})
            if family == "cost-report":
                base = project
        sample_reports.extend(negative_cases(base, work))
        public = public_connection_example(work / "public-metadata-only")
        public_dir = stage / "examples" / "public-metadata-only"
        public_dir.mkdir()
        (public_dir / "coverage.json").write_bytes(b.json_bytes(public))
        p.checkpoint(work / "public-metadata-only", public_dir / "source.zip")
        for name in ("learn-mcp-tools.json", "learn-mcp-provenance.json", "learn-mcp-tools-response.txt"):
            (public_dir / name).write_bytes((ROOT / "examples" / "offline" / "public-learn" / name).read_bytes())
        (public_dir / "reading-list-procedure.md").write_bytes((work / "public-metadata-only-evidence" / "reading-list-procedure.md").read_bytes())
        sample_reports.append({"id": "public-metadata-only", "kind": "real-public-metadata-not-native-binding", "outcome": "expected-native-setup-block", "native_claim": False})
        (stage / "offline-cases.json").write_bytes(b.json_bytes({
            "scope": "Deterministic source/helper/contract exercises, not model activation or native evaluation.",
            "cases": sample_reports, "native_claims": "none", "passed": len(sample_reports), "failed": 0,
        }))
        evaluation_dir = stage / "evals"
        evaluation_dir.mkdir()
        for name in ("creator-prompts.json", "creator-intent-cases.json", "intent-case-status.json"):
            (evaluation_dir / name).write_bytes((ROOT / "evals" / name).read_bytes())
        authoring_prompts = b.read_json(ROOT / "evals" / "creator-prompts.json")
        intent_prompts = b.read_json(ROOT / "evals" / "creator-intent-cases.json")
        intent_status = b.read_json(ROOT / "evals" / "intent-case-status.json")
        if authoring_prompts["status"] != "not-run" or intent_prompts["model_runs"] != 0 or intent_status["blind_holdout_for_current_or_later_revisions"]:
            raise ValueError("Prompt corpus readiness/disclosure must be represented honestly")
        budgets = {}
        for row in creator["files"]:
            parts = row["path"].split("/")
            if len(parts) > 2 and parts[0] == "skills":
                entry = budgets.setdefault(parts[1], {"companions": 0, "companion_bytes": 0, "skill_bytes": 0})
                if parts[2:] == ["SKILL.md"]:
                    entry["skill_bytes"] = row["size_bytes"]
                else:
                    entry["companions"] += 1
                    entry["companion_bytes"] += row["size_bytes"]
        report = {
            "version": b.VERSION, "status": "Draft", "kind": "provisional-offline-creator",
            "creator_target": b.TARGET, "creator_sha256": creator["sha256"],
            "skill_count": len(spec["skills"]), "connector_count": len(spec["connectors"]),
            "resource_budgets": budgets, "offline_case_count": len(sample_reports),
            "unrun_authoring_prompts": len(authoring_prompts["evals"]),
            "unrun_disclosed_intent_cases": len(intent_prompts["cases"]),
            "model_activation_runs": 0,
            "native_acceptance": "unverified", "manual_invocation": "unverified", "scheduling": "not-exercised",
            "canonical_target": b.TARGET, "canonical_state": "package-built-with-supplied-metadata; native acceptance unverified",
            "native_gate": "approved native tools and accessible session required; prior publication outcome UNKNOWN; reconcile before retry",
            "claims_inherited_from_proof_versions": False,
            "immutable_proof_artifacts": preserved,
            "readiness_boundaries": [
                "No new backend/service/runner/scheduler/runtime installer.",
                "These are offline deterministic checks, not a native or model-activation benchmark.",
                "Native video proof was limited to an existing native decoder and three inspected frames of a silent synthetic clip.",
                "Real public Learn metadata is optional evidence, not native connection availability or publisher/legal metadata.",
            ],
        }
        (stage / "release.json").write_bytes(b.json_bytes(report))
        for name in ("operator-continuation.md", "user-guide.md", "extensions.md"):
            source_doc = ROOT / "docs" / name
            if not source_doc.is_file():
                raise FileNotFoundError("Finish release documentation before packaging: " + name)
            (stage / name).write_bytes(source_doc.read_bytes())
        files = {path.relative_to(stage).as_posix(): path.read_bytes() for path in stage.rglob("*") if path.is_file()}
        files["inventory.json"] = b.json_bytes({name: {"sha256": hashlib.sha256(content).hexdigest(), "size_bytes": len(content)} for name, content in sorted(files.items())})
        materialize_release(destination, files)
    proof_integrity()
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "dist" / ("v" + b.VERSION))
    parser.add_argument("--metadata-dir", type=Path, help="Approved per-package publishing metadata; required for native packages")
    args = parser.parse_args()
    try:
        report = build_release(args.output.resolve(), args.metadata_dir)
    except (b.BuildError, OSError, UnicodeError) as error:
        print(json.dumps({"status": "Draft", "target": b.TARGET, "error": str(error)}), file=sys.stderr)
        raise SystemExit(2)
    print(json.dumps(report, indent=2, sort_keys=True))
