"""Honest corpus catalog, per-case stage matrix, and pending native output index."""
from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path

from .common import ContractError, digest, file_digest, json_bytes, load_json, no_links, write_bytes, write_json
from .contract import Scenario
from .pipeline import NATIVE_BLOCKER, check_case_evidence, native_pending
from .staging import check_media

REQUIRED_INDUSTRIES = {"manufacturing", "health-life-sciences", "financial-services", "retail"}


def business_industry(scenario: Scenario) -> str:
    directory_label = scenario.manifest["industry"]
    if directory_label != "cross-industry":
        return directory_label
    research = load_json(scenario.root.parent / "research.json")
    candidates = research.get("candidates") if isinstance(research, dict) else None
    if not isinstance(candidates, list):
        raise ContractError("Cross-industry classification requires its approved research catalog")
    matches = [item for item in candidates if isinstance(item, dict) and item.get("id") == scenario.id]
    if len(matches) != 1 or matches[0].get("industry") not in {"logistics", "energy-utilities", "professional-services"}:
        raise ContractError("Scenario lacks a unique source-backed business-industry label")
    return matches[0]["industry"]


def coverage(scenarios: list[Scenario], *, full: bool = False) -> dict:
    industries = Counter(scenario.manifest["industry"] for scenario in scenarios)
    business_industries = Counter(business_industry(scenario) for scenario in scenarios)
    families = Counter(scenario.manifest["workflow_family"] for scenario in scenarios)
    case_kinds = Counter(case["kind"] for scenario in scenarios for case in scenario.cases)
    procedure_groups, demo_groups, mechanics_groups = defaultdict(list), defaultdict(list), defaultdict(list)
    for scenario in scenarios:
        procedure_groups[file_digest(scenario.file("HOW_TO.md"))].append(scenario.id)
        demo_groups[digest(json_bytes(load_json(scenario.file("mock-data/demo.json"))))].append(scenario.id)
        mechanics = [
            {"kind": step["kind"], "rule_count": len(step["rule_ids"])}
            for step in scenario.workflow["steps"]
        ]
        mechanics_groups[digest(json_bytes(mechanics))].append(scenario.id)
    errors = []
    if not scenarios:
        errors.append("No implemented scenarios discovered; foundation fixtures do not count")
    if full:
        if len(scenarios) < 15:
            errors.append(f"Need at least 15 implemented scenarios; found {len(scenarios)}")
        if len(industries) < 5 or not REQUIRED_INDUSTRIES.issubset(industries):
            errors.append("Need Manufacturing, Health/Life Sciences, Financial Services, Retail, and at least one other industry")
        if len(families) < 5:
            errors.append("Need at least five distinct workflow families, not sector relabelings")
    repeated_procedures = [values for values in procedure_groups.values() if len(values) > 1]
    repeated_demos = [values for values in demo_groups.values() if len(values) > 1]
    if repeated_procedures or repeated_demos:
        errors.append("Identical procedures or demo payloads occur across scenarios")
    return {
        "scenario_count": len(scenarios),
        "case_count": sum(case_kinds.values()),
        "industry_counts": dict(sorted(industries.items())),
        "directory_pack_count": len(industries),
        "business_industry_counts": dict(sorted(business_industries.items())),
        "business_industry_count": len(business_industries),
        "industry_label_provenance": "Directory packs retain schema identity; cross-industry business labels come from the approved sector research catalog.",
        "workflow_family_counts": dict(sorted(families.items())),
        "case_kind_counts": dict(sorted(case_kinds.items())),
        "identical_procedure_groups": repeated_procedures,
        "identical_demo_groups": repeated_demos,
        "shared_step_shape_groups": [values for values in mechanics_groups.values() if len(values) > 1],
        "diversity_limit": "Counts and exact/structural reuse signals are observed; business diversity, research quality and golden independence still require review.",
        "full_corpus_required": full,
        "errors": errors,
    }


def build_catalog(scenarios: list[Scenario], *, full: bool = False) -> dict:
    metrics = coverage(scenarios, full=full)
    entries = []
    for scenario in scenarios:
        cases = []
        for case in scenario.cases:
            item = {
                "id": case["id"], "kind": case["kind"],
                "state": "prepared",
                "documented_rule_coverage": case["covers"],
                "failure_modes": case["failure_modes"],
                "observed_steps": [],
                "local_comparison": "not_run",
                "native": native_pending(),
                "issue": None,
            }
            if scenario.file(f"validation/{case['id']}.json", must_exist=False).exists():
                try:
                    evidence = check_case_evidence(scenario, case)
                    item.update({
                        "state": "baseline_pass",
                        "observed_steps": evidence["observed"]["steps"],
                        "local_comparison": "pass",
                    })
                except (ContractError, OSError) as error:
                    item.update({"state": "baseline_failed_or_stale", "local_comparison": "fail", "issue": str(error)})
            cases.append(item)
        media = {"state": "not_rendered", "issue": None}
        if scenario.file("demo/baseline.webm", must_exist=False).exists():
            try:
                evidence = check_media(scenario)
                media = {
                    "state": "baseline_visualization_ready",
                    "sha256": evidence["sha256"],
                    "duration_seconds": evidence["duration_seconds"],
                    "decoded_frame_count": evidence["decoded_frame_count"],
                    "native_video_reading": "unverified",
                    "issue": None,
                }
            except (ContractError, OSError) as error:
                media = {"state": "failed_or_stale", "issue": str(error)}
        entries.append({
            "id": scenario.id,
            "title": scenario.manifest["title"],
            "industry": scenario.manifest["industry"],
            "business_industry": business_industry(scenario),
            "workflow_family": scenario.manifest["workflow_family"],
            "path": scenario.root.parent.name + "/" + scenario.root.name,
            "procedure": "HOW_TO.md",
            "source_count": len(scenario.sources["sources"]),
            "research_provenance": "Sector-author supplied public citations; not fetched by the offline validator",
            "golden_provenance": scenario.manifest["golden_provenance"],
            "cases": cases,
            "media": media,
            "native": native_pending(),
        })
    baseline_ready = bool(entries) and all(case["state"] == "baseline_pass" for entry in entries for case in entry["cases"])
    media_ready = bool(entries) and all(entry["media"]["state"] == "baseline_visualization_ready" for entry in entries)
    return {
        "schema_version": 1,
        "provenance": "foundation-observed-local-corpus",
        "required_plugin_target": "cowork-v1.28",
        "required_plugin_manifest": "manifest.json",
        "coverage": metrics,
        "local_baselines_ready": baseline_ready,
        "local_media_ready": media_ready,
        "local_corpus_ready": not metrics["errors"] and baseline_ready and media_ready,
        "native_complete": False,
        "native": native_pending(),
        "scenarios": entries,
    }


def _cell(value) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def write_reports(root: Path, output_root: Path, catalog: dict) -> None:
    root, output_root = no_links(root), no_links(output_root)
    metrics = catalog["coverage"]
    lines = [
        "# Enterprise corpus validation",
        "",
        "**Native validation is blocked.** No local baseline, synthetic video, ZIP inspection,",
        "or matching imported payload is evidence of native generation or independent invocation.",
        "",
        f"Implemented scenarios: **{metrics['scenario_count']}**. Cases: **{metrics['case_count']}**.",
        f"Directory packs: **{metrics['directory_pack_count']}**; business industries: **{metrics['business_industry_count']}**.",
        f"Local baselines ready: **{str(catalog['local_baselines_ready']).lower()}**.",
        f"Local media ready: **{str(catalog['local_media_ready']).lower()}**.",
        f"Local corpus ready: **{str(catalog['local_corpus_ready']).lower()}**.",
        "",
        "## Scenario catalog",
        "",
        "| Scenario | Industry | Workflow family | Baseline cases | Demo video | Native |",
        "|---|---|---|---|---|---|",
    ]
    for entry in catalog["scenarios"]:
        passed = sum(case["state"] == "baseline_pass" for case in entry["cases"])
        link = f"[{_cell(entry['title'])}]({entry['path']}/HOW_TO.md)"
        lines.append(
            f"| {link} | {_cell(entry['business_industry'])} | {_cell(entry['workflow_family'])} | "
            f"{passed}/{len(entry['cases'])} | {_cell(entry['media']['state'])} | creation blocked; install/invoke not run |"
        )
    if not catalog["scenarios"]:
        lines.extend(["", "No sector scenarios are integrated yet. Shared unit fixtures are not counted."])
    lines.extend(["", "## Coverage and evidence limits", ""])
    for error in metrics["errors"]:
        lines.append(f"- {error}")
    lines.extend([
        "",
        metrics["diversity_limit"],
        "",
        "Research URLs and rule provenance are supplied by sector authors. The offline tool",
        "does not claim to have fetched those pages or independently reviewed their conclusions.",
        "Goldens are author-declared independent derivations, locked before execution; local",
        "integrity checks do not prove independent human review.",
        "",
        "The machine-readable [catalog](catalog.json) separates documented rules, observed",
        "baseline steps, local semantic comparison, media evidence, and native states per case.",
        "",
        "## Native gate",
        "",
        NATIVE_BLOCKER,
        "",
        "The pending matrix is [output/status.json](../output/status.json). No native ZIP is",
        "produced by this pipeline. Actual native outputs must be supplied by the authorized",
        "operator later; read-only imports retain declared versus locally observed provenance.",
        "",
    ])
    pending = {
        "schema_version": 1,
        "provenance": "foundation-generated-pending-matrix",
        "native_gate_as_of": "2026-09-14",
        "native_complete": False,
        "required_plugin_target": "cowork-v1.28",
        "required_plugin_manifest": "manifest.json",
        "alternative_manifest_fallback": False,
        "publishing_metadata": "approved per-package app/publisher metadata required; not supplied by this corpus",
        "native": native_pending(),
        "implemented_scenario_count": metrics["scenario_count"],
        "required_scenario_count": 15,
        "local_corpus_ready": catalog["local_corpus_ready"],
        "scenarios": [
            {
                "id": entry["id"], "title": entry["title"],
                "native": native_pending(),
                "plugin": None,
                "cases": [
                    {"id": case["id"], "baseline": case["state"], "native_invocation": "not_run", "native_result": None}
                    for case in entry["cases"]
                ],
            }
            for entry in catalog["scenarios"]
        ],
    }
    status_path = output_root / "status.json"
    if status_path.exists():
        existing = load_json(status_path)
        if not isinstance(existing, dict) or existing.get("provenance") != pending["provenance"]:
            raise ContractError("Refusing to replace native status owned by another workflow")
        if existing.get("native_complete") is not False or existing.get("native") != native_pending():
            raise ContractError("Existing native lifecycle facts need operator review; not overwritten by pending tooling")
    write_json(root / "catalog.json", catalog, replace=True)
    write_bytes(root / "VALIDATION_REPORT.md", "\n".join(lines).encode("utf-8"), replace=True)
    write_json(status_path, pending, replace=True)
    guide = [
        "# Enterprise scenarios: complete how-to collection", "",
        "This single document collects the complete procedures for the implemented",
        "synthetic scenarios. Each chapter identifies its original scenario directory;",
        "relative command/data paths refer to that directory, not this collection.",
        "Use [the corpus how-to](HOW_TO.md) for baseline execution, video creation,",
        "native input staging and the blocked native comparison protocol.", "",
        "**All data and processes are mock, review-only workflows.** No native Creator",
        "generation or independent Cowork invocation is implied by these procedures.", "",
        "## Contents", "",
    ]
    for entry in catalog["scenarios"]:
        guide.append(f"- [{entry['title']}](#{entry['id']}) - {entry['business_industry']}")
    for entry in catalog["scenarios"]:
        procedure = root / entry["path"] / "HOW_TO.md"
        guide.extend([
            "", "---", "", f'<a id="{entry["id"]}"></a>', "",
            f"## {entry['title']}", "",
            f"Scenario ID: `{entry['id']}`. Directory: `{entry['path']}`.",
            f"[Original single-scenario how-to]({entry['path']}/HOW_TO.md)", "",
            procedure.read_text(encoding="utf-8").strip(), "",
        ])
    write_bytes(root / "ALL_SCENARIOS_HOW_TO.md", "\n".join(guide).encode("utf-8"), replace=True)
