"""Read-only inspection and comparison of future operator-supplied native exports.

No host automation, plugin execution, package generation, or native attestation.
"""
from __future__ import annotations

import hashlib
import stat
import zipfile
from pathlib import Path

from .common import (
    ContractError, SHA256, contained_path, file_digest, load_json, no_links,
    object_fields, path_parts, text, version, write_json,
)
from .comparison import compare_json
from .contract import Scenario, validate_result
from .pipeline import check_case_evidence, golden_lock, native_pending
from .staging import check_staging

ZIP_LIMIT = 200_000_000
EXPANDED_LIMIT = 256_000_000
ENTRY_LIMIT = 32_000_000


def inspect_zip(path: Path) -> dict:
    path = no_links(path)
    if not path.is_file() or path.suffix.lower() != ".zip":
        raise ContractError("Inspect an existing operator-supplied ZIP; this command never creates one")
    if not 0 < path.stat().st_size < ZIP_LIMIT:
        raise ContractError("Plugin ZIP is empty or exceeds the bounded inspection limit")
    starting_sha256 = file_digest(path)
    entries, names, files, directories = [], set(), set(), set()
    total = 0
    try:
        with zipfile.ZipFile(path) as archive:
            if not archive.infolist() or len(archive.infolist()) > 2000:
                raise ContractError("Plugin ZIP must contain between 1 and 2000 entries")
            for member in archive.infolist():
                if member.orig_filename != member.filename:
                    raise ContractError("ZIP entry contains a path normalized or truncated by the ZIP reader")
                name = member.filename[:-1] if member.is_dir() else member.filename
                parts = path_parts(name)
                normalized = "/".join(parts).casefold()
                if normalized in names:
                    raise ContractError(f"Duplicate or case-colliding ZIP entry: {name}")
                names.add(normalized)
                if member.flag_bits & 1 or stat.S_ISLNK(member.external_attr >> 16):
                    raise ContractError("Encrypted ZIP entries and symbolic links are not supported")
                mode = stat.S_IFMT(member.external_attr >> 16)
                if mode not in (0, stat.S_IFREG, stat.S_IFDIR):
                    raise ContractError("Special-device ZIP entries are not supported")
                ancestors = {"/".join(parts[:index]).casefold() for index in range(1, len(parts))}
                if ancestors & files or (not member.is_dir() and normalized in directories):
                    raise ContractError("ZIP contains file/directory path collisions")
                directories.update(ancestors)
                (directories if member.is_dir() else files).add(normalized)
                if member.file_size > ENTRY_LIMIT or member.file_size < 0:
                    raise ContractError(f"ZIP entry exceeds the bounded inspection limit: {name}")
                total += member.file_size
                if total > EXPANDED_LIMIT:
                    raise ContractError("ZIP expanded content exceeds the inspection limit")
                if member.file_size > 1_000_000 and member.file_size / max(member.compress_size, 1) > 200:
                    raise ContractError("ZIP expansion ratio exceeds the bounded inspection limit")
                digest = hashlib.sha256()
                count = 0
                with archive.open(member) as handle:
                    for chunk in iter(lambda: handle.read(64 * 1024), b""):
                        count += len(chunk)
                        if count > member.file_size or count > ENTRY_LIMIT:
                            raise ContractError("ZIP entry expanded beyond its declared bounds")
                        digest.update(chunk)
                if count != member.file_size:
                    raise ContractError("ZIP entry length does not match its directory")
                entries.append({
                    "path": member.filename,
                    "size_bytes": count,
                    "sha256": digest.hexdigest(),
                    "directory": member.is_dir(),
                })
    except (zipfile.BadZipFile, NotImplementedError, RuntimeError) as error:
        raise ContractError(f"Cannot inspect plugin ZIP: {error}") from error
    if starting_sha256 != file_digest(path):
        raise ContractError("Plugin ZIP changed during read-only inspection")
    return {
        "schema_version": 1,
        "provenance": "observed-local-file-bytes",
        "sha256": starting_sha256,
        "size_bytes": path.stat().st_size,
        "expanded_bytes": total,
        "entries": entries,
        "inspection": "bounded ZIP paths, sizes, CRCs and content hashes only; not package compatibility or code safety",
        "execution": "not_run",
        "native_provenance": "unverified",
        "generated": False,
        "installed": False,
    }


def _hash(value, label):
    if not isinstance(value, str) or not SHA256.fullmatch(value):
        raise ContractError(f"{label}: expected a SHA-256 hex digest")
    return value


def _evidence_files(root: Path, value, scenario_id: str) -> list[dict]:
    if not isinstance(value, list) or not value:
        raise ContractError("Each declared native stage requires actual nonempty local evidence files")
    observed = []
    seen = set()
    for item in value:
        object_fields(item, {"path", "sha256"}, "native evidence file")
        if not isinstance(item["path"], str) or not item["path"].startswith(scenario_id + "/"):
            raise ContractError("Native evidence must belong to this scenario under output")
        path = contained_path(root, item["path"])
        fingerprint = file_digest(path)
        if not 0 < path.stat().st_size < ZIP_LIMIT or _hash(item["sha256"], "evidence.sha256") != fingerprint:
            raise ContractError("Native evidence file is empty, oversized, or has a stale hash")
        if item["path"] in seen:
            raise ContractError("Duplicate evidence file in the same declared stage")
        seen.add(item["path"])
        observed.append({"path": item["path"], "sha256": fingerprint, "size_bytes": path.stat().st_size})
    return observed


def compare_native_import(scenario: Scenario, observation_path: Path, output_root: Path, *, replace: bool = False) -> dict:
    output_root = no_links(output_root).resolve()
    observation_path = no_links(observation_path).resolve()
    if not observation_path.is_relative_to(output_root):
        raise ContractError("Native import descriptors must live under root output")
    golden_lock(scenario)
    check_staging(scenario)
    descriptor_sha256 = file_digest(observation_path)
    claim = load_json(observation_path)
    object_fields(claim, {
        "schema_version", "scenario_id", "provenance", "host", "plugin",
        "creation", "installation", "invocations",
    }, "native import")
    version(claim["schema_version"], "native import")
    if claim["scenario_id"] != scenario.id or claim["provenance"] != "operator-declared-native-export":
        raise ContractError("Native imports require explicit operator-declared provenance and scenario identity")
    if claim["host"] != "Microsoft Copilot Cowork":
        raise ContractError("A substitute CLI, skill, model run, or other host cannot be labeled Cowork")
    plugin = object_fields(claim["plugin"], {"path", "sha256"}, "native plugin")
    if not isinstance(plugin["path"], str) or not plugin["path"].startswith(scenario.id + "/"):
        raise ContractError("Native plugin must be a supplied file under output/<scenario-id>")
    inspection = inspect_zip(contained_path(output_root, plugin["path"]))
    plugin_sha = _hash(plugin["sha256"], "plugin.sha256")
    if plugin_sha != inspection["sha256"]:
        raise ContractError("Downloaded plugin bytes differ from the frozen declared plugin hash")
    creation = object_fields(claim["creation"], {
        "evidence_id", "plugin_sha256", "creator_input_manifest_sha256", "evidence_files",
    }, "native creation")
    installation = object_fields(claim["installation"], {
        "evidence_id", "creation_evidence_id", "plugin_sha256", "evidence_files",
    }, "native installation")
    seen_ids = {text(creation["evidence_id"], "creation.evidence_id", maximum=200)}
    install_id = text(installation["evidence_id"], "installation.evidence_id", maximum=200)
    if install_id in seen_ids or installation["creation_evidence_id"] != creation["evidence_id"]:
        raise ContractError("Creation and installation need distinct, correctly linked evidence IDs")
    seen_ids.add(install_id)
    if creation["plugin_sha256"] != plugin_sha or installation["plugin_sha256"] != plugin_sha:
        raise ContractError("Creation and installation must bind to the same exact plugin bytes")
    staging_manifest = scenario.file("validation/creator-staging.json")
    if creation["creator_input_manifest_sha256"] != file_digest(staging_manifest):
        raise ContractError("Creation evidence does not bind to the actual allowlisted Creator input manifest")
    observed = {
        "plugin_inspection": inspection,
        "creation_evidence_files": _evidence_files(output_root, creation["evidence_files"], scenario.id),
        "installation_evidence_files": _evidence_files(output_root, installation["evidence_files"], scenario.id),
        "invocation_evidence_files": {},
    }
    invocations = claim["invocations"]
    if not isinstance(invocations, list):
        raise ContractError("Native invocation claims must be an array")
    comparisons, case_ids = [], set()
    for invocation in invocations:
        object_fields(invocation, {
            "case_id", "evidence_id", "installation_evidence_id", "plugin_sha256",
            "input_sha256", "result_path", "result_sha256", "evidence_files", "independence",
        }, "native invocation")
        case = scenario.case(text(invocation["case_id"], "invocation.case_id"))
        evidence_id = text(invocation["evidence_id"], "invocation.evidence_id", maximum=200)
        if evidence_id in seen_ids or case["id"] in case_ids:
            raise ContractError("Each native invocation needs a distinct evidence ID and case ID")
        seen_ids.add(evidence_id)
        case_ids.add(case["id"])
        if invocation["installation_evidence_id"] != install_id or invocation["plugin_sha256"] != plugin_sha:
            raise ContractError("Invocation must bind to the independently installed exact plugin")
        if invocation["input_sha256"] != file_digest(scenario.file(case["input"])):
            raise ContractError("Invocation input does not match the locked private case bytes")
        independence = object_fields(invocation["independence"], {
            "fresh_task", "creator_disabled", "baseline_withheld", "goldens_withheld",
        }, "native invocation independence")
        if any(value is not True for value in independence.values()):
            raise ContractError("Invocation lacks the required declared independent-task boundaries")
        if not isinstance(invocation["result_path"], str) or not invocation["result_path"].startswith(scenario.id + "/"):
            raise ContractError("Invocation results must be supplied under output/<scenario-id>")
        result_path = contained_path(output_root, invocation["result_path"])
        if _hash(invocation["result_sha256"], "result.sha256") != file_digest(result_path):
            raise ContractError("Invocation result bytes differ from their frozen hash")
        actual = validate_result(load_json(result_path), "native supplied result")
        local = check_case_evidence(scenario, case)
        baseline = load_json(scenario.file(local["artifacts"]["result"]))
        expected = load_json(scenario.file(case["expected"]))
        golden_differences = compare_json(expected, actual)
        baseline_differences = compare_json(baseline, actual)
        comparisons.append({
            "case_id": case["id"],
            "evidence_id": evidence_id,
            "result_sha256": file_digest(result_path),
            "input_sha256": invocation["input_sha256"],
            "golden_sha256": file_digest(scenario.file(case["expected"])),
            "baseline_result_sha256": local["artifacts"]["result_sha256"],
            "semantic_match": not golden_differences and not baseline_differences,
            "golden_differences": golden_differences,
            "baseline_differences": baseline_differences,
        })
        observed["invocation_evidence_files"][case["id"]] = _evidence_files(
            output_root, invocation["evidence_files"], scenario.id,
        )
    missing_cases = sorted({case["id"] for case in scenario.cases} - case_ids)
    receipt = {
        "schema_version": 1,
        "scenario_id": scenario.id,
        "import_descriptor_sha256": descriptor_sha256,
        "declared": claim,
        "observed_locally": observed,
        "comparisons": comparisons,
        "missing_cases": missing_cases,
        "all_supplied_payloads_match": bool(comparisons) and all(item["semantic_match"] for item in comparisons),
        "all_required_cases_supplied": not missing_cases,
        "native": native_pending(),
        "native_review": "required; file bytes and operator declarations do not attest native creation, installation, or invocation",
        "native_pass": False,
        "comparison_scope": "Entire canonical result envelopes; any required external artifact content must be represented in outputs, not only a filename or headline total.",
        "limitations": [
            "This tool did not observe the host and cannot restore or bypass the native access gate.",
            "Creation, installation and invocation declarations retain separate evidence IDs.",
            "Matching local bytes or supplied status strings never upgrade native lifecycle states.",
            "No plugin content was extracted to runnable source or executed.",
        ],
    }
    receipt_path = contained_path(output_root, f"{scenario.id}/comparison.json", must_exist=False)
    referenced = {
        observation_path, contained_path(output_root, plugin["path"]),
        *(contained_path(output_root, item["result_path"]) for item in invocations),
    }
    evidence_sets = [creation["evidence_files"], installation["evidence_files"]]
    evidence_sets.extend(item["evidence_files"] for item in invocations)
    for files in evidence_sets:
        for item in files:
            path = contained_path(output_root, item["path"])
            referenced.add(path)
            if file_digest(path) != item["sha256"]:
                raise ContractError("A declared evidence file changed during import")
    if receipt_path in referenced:
        raise ContractError("Comparison receipt must not overwrite an import descriptor, result, or evidence file")
    if file_digest(observation_path) != descriptor_sha256 or file_digest(contained_path(output_root, plugin["path"])) != plugin_sha:
        raise ContractError("Import descriptor or plugin changed during comparison")
    for invocation in invocations:
        if file_digest(contained_path(output_root, invocation["result_path"])) != invocation["result_sha256"]:
            raise ContractError("Invocation result changed during comparison")
    golden_lock(scenario)
    write_json(receipt_path, receipt, replace=replace)
    return receipt
