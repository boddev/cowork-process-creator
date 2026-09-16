"""Read-only inspection and comparison of future operator-supplied native exports.

No host automation, plugin execution, package generation, or native attestation.
"""
from __future__ import annotations

import hashlib
import re
import stat
import struct
import uuid
import zipfile
import zlib
from pathlib import Path

from .common import (
    ContractError, SHA256, contained_path, file_digest, load_json, no_links,
    object_fields, parse_json, path_parts, text, version, write_json,
)
from .comparison import compare_json
from .contract import Scenario, validate_result
from .pipeline import check_case_evidence, golden_lock, native_pending
from .staging import check_staging

ZIP_LIMIT = 200_000_000
EXPANDED_LIMIT = 256_000_000
ENTRY_LIMIT = 32_000_000
COWORK_SCHEMA = "https://developer.microsoft.com/json-schemas/teams/v1.28/MicrosoftTeams.schema.json"


def _expanded_digest(path: Path, member: zipfile.ZipInfo) -> tuple[int, str]:
    """Measure the actual stream; ZipExtFile clips reads at declared file_size."""
    if member.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
        raise ContractError("Bounded inspection supports only stored or DEFLATE ZIP entries")
    digest, crc, count = hashlib.sha256(), 0, 0

    def consume(data: bytes) -> None:
        nonlocal crc, count
        count += len(data)
        if count > member.file_size or count > ENTRY_LIMIT:
            raise ContractError("ZIP entry expanded beyond its declared bounds")
        digest.update(data)
        crc = zlib.crc32(data, crc)

    with path.open("rb") as raw:
        raw.seek(member.header_offset)
        header = raw.read(30)
        if len(header) != 30:
            raise ContractError("ZIP entry has a truncated local header")
        fields = struct.unpack("<4s5H3I2H", header)
        if fields[0] != b"PK\x03\x04" or fields[2] != member.flag_bits or fields[3] != member.compress_type:
            raise ContractError("ZIP local header disagrees with its directory")
        raw.seek(fields[9] + fields[10], 1)
        remaining = member.compress_size
        decoder = zlib.decompressobj(-zlib.MAX_WBITS) if member.compress_type == zipfile.ZIP_DEFLATED else None
        if decoder is None and member.compress_size != member.file_size:
            raise ContractError("Stored ZIP entry has inconsistent compressed and expanded lengths")
        try:
            while remaining:
                chunk = raw.read(min(64 * 1024, remaining))
                if not chunk:
                    raise ContractError("ZIP entry has a truncated compressed stream")
                remaining -= len(chunk)
                if decoder is None:
                    consume(chunk)
                    continue
                pending = chunk
                while pending:
                    expanded = decoder.decompress(pending, min(64 * 1024, member.file_size - count + 1))
                    consume(expanded)
                    pending = decoder.unconsumed_tail
                    if decoder.unused_data or (decoder.eof and (pending or remaining)):
                        raise ContractError("ZIP entry contains bytes after the DEFLATE stream")
            if decoder is not None:
                while not decoder.eof:
                    expanded = decoder.decompress(b"", min(64 * 1024, member.file_size - count + 1))
                    if not expanded:
                        break
                    consume(expanded)
                if not decoder.eof:
                    raise ContractError("ZIP entry has an incomplete DEFLATE stream")
        except zlib.error as error:
            raise ContractError(f"ZIP entry has an invalid DEFLATE stream: {error}") from error
    if count != member.file_size or crc & 0xFFFFFFFF != member.CRC:
        raise ContractError("ZIP actual expanded length or CRC disagrees with its directory")
    return count, digest.hexdigest()


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
                # Retain zipfile's header/name/overlap checks, but measure raw expansion.
                with archive.open(member):
                    pass
                count, expanded_sha256 = _expanded_digest(path, member)
                entries.append({
                    "path": member.filename,
                    "size_bytes": count,
                    "sha256": expanded_sha256,
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

def inspect_cowork_plugin(path: Path) -> dict:
    """Check the required native package shape, not the full Microsoft schema."""
    inspection = inspect_zip(path)
    files = {entry["path"] for entry in inspection["entries"] if not entry["directory"]}
    if "manifest.json" not in files:
        raise ContractError("Microsoft Cowork requires a root manifest.json (v1.28); a Claude-compatible/source ZIP is not a native plugin")
    if "plugin.json" in files or any(name.startswith((".claude-plugin/", ".cursor-plugin/", ".plugin/")) for name in files):
        raise ContractError("Native Microsoft Cowork output must not include another host's plugin manifest")

    def resource(value, label):
        name = text(value, label, maximum=256).removeprefix("./")
        path_parts(name)
        if name not in files:
            raise ContractError(f"{label}: referenced package file is missing")
        return name

    with zipfile.ZipFile(path) as archive:
        manifest = parse_json(archive.read("manifest.json"), label="manifest.json")
        object_fields(manifest, {
            "$schema", "manifestVersion", "version", "id", "developer", "name",
            "description", "icons", "accentColor", "agentSkills",
        }, "Microsoft manifest", optional={"agentConnectors"})
        if manifest["manifestVersion"] != "1.28" or manifest["$schema"] != COWORK_SCHEMA:
            raise ContractError("Microsoft Cowork plugin must target the official M365 manifest v1.28, not devPreview or a portable source format")
        try:
            identity = uuid.UUID(text(manifest["id"], "manifest.id", maximum=36))
        except ValueError as error:
            raise ContractError("Microsoft manifest.id must be a non-nil UUID") from error
        if identity.int == 0:
            raise ContractError("Microsoft manifest.id must be a non-nil UUID")
        if not re.fullmatch(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)", text(manifest["version"], "manifest.version", maximum=30)):
            raise ContractError("Microsoft manifest.version must have three decimal components")
        developer = object_fields(manifest["developer"], {"name", "websiteUrl", "privacyUrl", "termsOfUseUrl"}, "developer")
        text(developer["name"], "developer.name", maximum=32)
        for key in ("websiteUrl", "privacyUrl", "termsOfUseUrl"):
            if not text(developer[key], "developer." + key, maximum=2048).startswith("https://"):
                raise ContractError("Supplied native publishing metadata must use HTTPS URLs")
        for field, limits in (("name", {"short": 30, "full": 100}), ("description", {"short": 80, "full": 4000})):
            values = object_fields(manifest[field], set(limits), "manifest." + field)
            for key, limit in limits.items():
                text(values[key], "manifest." + field + "." + key, maximum=limit)
        if not re.fullmatch(r"#[0-9A-Fa-f]{6}", text(manifest["accentColor"], "accentColor", maximum=7)):
            raise ContractError("Microsoft manifest accentColor must be a six-digit color")
        icons = object_fields(manifest["icons"], {"color", "outline"}, "icons")
        for key, size in (("color", 192), ("outline", 32)):
            name = resource(icons[key], "icons." + key)
            with archive.open(name) as stream:
                header = stream.read(24)
            if len(header) != 24 or header[:8] != b"\x89PNG\r\n\x1a\n" or struct.unpack(">II", header[16:24]) != (size, size):
                raise ContractError(f"Microsoft {key} icon must be a {size}x{size} PNG")
        skills = manifest["agentSkills"]
        if not isinstance(skills, list) or not 1 <= len(skills) <= 20:
            raise ContractError("Native scenario plugin must declare 1-20 agentSkills")
        folders = set()
        for item in skills:
            object_fields(item, {"folder"}, "agentSkills entry")
            folder = text(item["folder"], "agentSkills.folder", maximum=256).removeprefix("./")
            path_parts(folder)
            if folder in folders:
                raise ContractError("Duplicate native skill folder")
            folders.add(folder)
            resource(folder + "/SKILL.md", "agentSkills SKILL.md")
        connectors = manifest.get("agentConnectors", [])
        if not isinstance(connectors, list) or len(connectors) > 10:
            raise ContractError("Native package supports at most 10 connectors")
        for connector in connectors:
            if not isinstance(connector, dict):
                raise ContractError("Native connector must be an object")
            tool_source = object_fields(connector.get("toolSource"), {"remoteMcpServer"}, "connector.toolSource")
            remote = object_fields(tool_source["remoteMcpServer"], {"mcpServerUrl", "mcpToolDescription"}, "remoteMcpServer", optional={"authorization"})
            if not text(remote["mcpServerUrl"], "mcpServerUrl", maximum=2048).startswith("https://"):
                raise ContractError("Native remote connector requires HTTPS")
            descriptor = object_fields(remote["mcpToolDescription"], {"file"}, "mcpToolDescription")
            tool_file = resource(descriptor["file"], "mcpToolDescription.file")
            tool_data = object_fields(parse_json(archive.read(tool_file), label=tool_file), {"tools"}, "tool descriptor")
            if not isinstance(tool_data["tools"], list) or not tool_data["tools"]:
                raise ContractError("Native connector descriptor must include actual tools")
    if file_digest(path) != inspection["sha256"]:
        raise ContractError("Plugin changed during manifest inspection")
    inspection["package_target"] = "cowork-v1.28"
    inspection["manifest_check"] = "Required native scenario-package shape and resource references only; not full Microsoft schema validation or host acceptance."
    return inspection


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
    inspection = inspect_cowork_plugin(contained_path(output_root, plugin["path"]))
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
