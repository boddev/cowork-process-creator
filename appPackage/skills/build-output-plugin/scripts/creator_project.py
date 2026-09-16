"""Create/check/package/resume authoring files. Never execute workflow steps."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import stat
import sys
import tempfile
import zipfile
from pathlib import Path

sys.dont_write_bytecode = True
import creator_builder as b
import project_contracts as c

MAX_BUNDLE_FILES = 1000


class MergeConflict(b.BuildError):
    def __init__(self, paths: list[str]):
        self.paths = paths
        super().__init__("Concurrent changes require explicit resolution: " + ", ".join(paths))


def write_tree_new(destination: Path, files: dict[str, bytes]) -> None:
    b.require(not destination.exists() and not destination.is_symlink(), "Destination already exists; originals will not be overwritten")
    b.require(destination.parent.is_dir(), "Destination parent directory must exist")
    for name in files:
        b.validate_path(name)
    with tempfile.TemporaryDirectory(prefix="creator-stage-", dir=destination.parent) as temporary:
        stage = Path(temporary) / "content"
        stage.mkdir()
        for name, content in sorted(files.items()):
            path = stage / name
            path.parent.mkdir(parents=True, exist_ok=True)
            b.write_new_file(path, content)
        b.require(not destination.exists(), "Destination appeared during staging; refusing to overwrite")
        stage.rename(destination)


def init_project(destination: Path, project_id: str, title: str, purpose: str) -> dict:
    b.slug(project_id, "project_id")
    b.text(title, 100, "title")
    b.prose(purpose, 4000, "purpose")
    header = {"format_version": 1, "project_id": project_id}
    blueprint = dict(header, revision=1, status="draft", title=title, purpose=purpose, evidence_sha256=None,
                     invocation_mode="manual", invocation_prompt="Supply the declared runtime inputs and a new output destination.",
                     inputs=[], outputs=[], steps=[], constants=[], bindings=[], evaluation_cases=[])
    documents = {
        "inputs.json": dict(header, sources=[]),
        "observations.json": dict(header, items=[], questions=[]),
        "workflow-blueprint.json": blueprint,
        "decisions.json": dict(header, blueprint_revision=1, blueprint_sha256=None, items=[]),
        "host-profile.json": dict(header, context="unverified", capabilities=[], connections=[]),
        "build-state.json": dict(header, blueprint_revision=1, phase="intake"),
    }
    write_tree_new(destination, {name: b.json_bytes(value) for name, value in documents.items()})
    return {"status": "Draft", "project_id": project_id, "blueprint_revision": 1, "created": str(destination)}


def assemble_candidate(plan_path: Path, destination: Path) -> dict:
    plan = b.read_json(plan_path)
    b.check_text(plan_path.read_bytes(), "candidate plan")
    b.exact_keys(plan, {"format_version", "plugin", "skills", "tools"}, "candidate plan")
    c.integer(plan["format_version"], 1, 1, "plan.format_version")
    b.require(isinstance(plan["plugin"], dict), "plan.plugin must contain a plugin specification")
    files = {"plugin-spec.json": b.json_bytes(plan["plugin"])}
    skill_names = []
    for skill in c.array(plan["skills"], "plan.skills", 20):
        b.exact_keys(skill, {"name", "description", "body", "companions"}, "planned skill")
        name = b.slug(skill["name"], "skill.name")
        b.require(name not in skill_names, "plan.skills: duplicate name")
        skill_names.append(name)
        description = b.text(skill["description"], 1024, "skill.description")
        b.require(isinstance(skill["body"], str) and bool(skill["body"].strip()), "skill.body must be nonempty Markdown")
        content = "---\nname: " + name + "\ndescription: " + json.dumps(description, ensure_ascii=True) + "\n---\n" + skill["body"].strip() + "\n"
        files[f"skills/{name}/SKILL.md"] = content.encode("utf-8")
        for companion in c.array(skill["companions"], "companions", 20):
            b.exact_keys(companion, {"path", "content"}, "companion")
            b.require(isinstance(companion["path"], str), "companion.path must be text")
            b.validate_path(companion["path"])
            b.require(companion["path"].split("/")[0] in {"scripts", "references", "assets"}, "Companions must be under scripts, references or assets")
            relative = f"skills/{name}/" + companion["path"]
            b.require(relative not in files and isinstance(companion["content"], str), "Duplicate companion or non-text content")
            files[relative] = companion["content"].encode("utf-8")
    for item in c.array(plan["tools"], "plan.tools", 10):
        b.exact_keys(item, {"path", "content"}, "tool file")
        b.require(isinstance(item["path"], str), "tool path must be text")
        b.validate_path(item["path"])
        b.require(item["path"].startswith("tools/") and item["path"].endswith(".json"), "Tool descriptions must be tools/*.json")
        b.require(item["path"] not in files and isinstance(item["content"], str), "Duplicate/non-text tool descriptor")
        files[item["path"]] = item["content"].encode("utf-8")
    b.require(plan["plugin"].get("skills") == skill_names, "Planned skill order/names must match the plugin specification")
    b.require(not destination.exists() and not destination.is_symlink(), "Candidate destination already exists")
    b.require(destination.parent.is_dir(), "Candidate destination parent must exist")
    with tempfile.TemporaryDirectory(prefix="creator-assemble-", dir=destination.parent) as temporary:
        stage = Path(temporary) / "candidate"
        write_tree_new(stage, files)
        fingerprint, payload, spec, connectors = c.candidate_fingerprint(stage)
        b.require(not destination.exists(), "Candidate destination appeared during assembly")
        stage.rename(destination)
    return {"status": "Draft", "candidate_sha256": fingerprint, "plugin": spec["name"], "files": len(payload), "connectors": len(connectors), "host_acceptance": "unverified"}


def snapshot_project(project: Path) -> tuple[dict[str, bytes], dict]:
    b.check_regular(project, directory=True)
    project = project.resolve(strict=True)
    roots = {path.name for path in project.iterdir()}
    b.require(c.REQUIRED_FILES <= roots <= c.REQUIRED_FILES | c.OPTIONAL_FILES | c.PROJECT_DIRECTORIES, "Source resume excludes unexpected files/raw attachments; move them outside the project")
    blueprint = b.read_json(project / "workflow-blueprint.json")
    c.integer(blueprint.get("format_version"), 1, 1, "blueprint.format_version")
    project_id = b.slug(blueprint.get("project_id"), "project_id")
    revision = c.integer(blueprint.get("revision"), 1, 1_000_000, "blueprint.revision")
    files, folded, size = {}, set(), 0

    def visit(directory: Path) -> None:
        nonlocal size
        for path in sorted(directory.iterdir()):
            relative = path.relative_to(project).as_posix()
            b.validate_path(relative)
            b.check_regular(path, directory=path.is_dir())
            b.require(path.resolve().is_relative_to(project), "Resume source escapes project")
            b.require(relative.casefold() not in folded, "Resume source contains case-insensitive path collisions")
            folded.add(relative.casefold())
            if path.is_dir():
                visit(path)
                continue
            b.require(path.suffix in {".json", ".md", ".py", ".txt"}, "Resume source excludes binary/raw media")
            b.require(path.stat().st_size <= b.MAX_COMPANION_BYTES, "Resume file exceeds 5 MB")
            with path.open("rb") as handle:
                content = handle.read(b.MAX_COMPANION_BYTES + 1)
            b.require(len(content) <= b.MAX_COMPANION_BYTES, "Resume file grew beyond its size ceiling")
            b.check_text(content, relative, allow_templates=True)
            if relative.startswith("candidate/"):
                inside = relative[len("candidate/"):]
                b.require(inside == "plugin-spec.json" or inside.startswith(("skills/", "tools/")), "Unknown candidate source location")
            if relative.startswith("history/"):
                b.require(path.suffix == ".json", "History stores only authoring JSON records")
            size += len(content)
            b.require(size <= b.MAX_SOURCE_BYTES and len(files) < MAX_BUNDLE_FILES, "Resume source exceeds bundle safety limits")
            files[relative] = content

    visit(project)
    metadata = {"format_version": 1, "kind": "creator-source", "builder_version": b.VERSION,
                "project_id": project_id, "blueprint_revision": revision,
                "status": "Draft", "native_acceptance": "unverified",
                "files": {name: {"sha256": hashlib.sha256(content).hexdigest(), "size_bytes": len(content)} for name, content in sorted(files.items())}}
    return files, metadata


def checkpoint(project: Path, output: Path) -> dict:
    b.require(output.suffix == ".zip", "Creation-source output must be a .zip")
    b.require(not output.resolve().is_relative_to(project.resolve()), "Export the source bundle outside its project")
    files, metadata = snapshot_project(project)
    try:
        checked = c.validate_project(project)
        metadata["blockers"] = checked["blockers"]
    except b.BuildError as exc:
        metadata["validation_error"] = str(exc)
    except FileNotFoundError:
        metadata["validation_error"] = "A referenced candidate file is missing; the source draft is preserved for correction."
    payload = dict(files)
    payload["checkpoint.json"] = b.json_bytes(metadata)
    content = b.zip_bytes(payload)
    b.write_new_file(output, content)
    return {"status": "Draft", "kind": "creation-source", "project_id": metadata["project_id"], "blueprint_revision": metadata["blueprint_revision"], "sha256": hashlib.sha256(content).hexdigest(), "files": len(files), "native_acceptance": "unverified", "raw_media_included": False}


def read_bundle(path: Path) -> tuple[dict[str, bytes], dict, str]:
    b.check_regular(path)
    b.require(path.stat().st_size <= b.MAX_SOURCE_BYTES + 1_000_000, "Source bundle exceeds its byte ceiling")
    content = path.read_bytes()
    try:
        archive = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile as exc:
        raise b.BuildError("Not a valid creation-source ZIP") from exc
    files = {}
    with archive:
        entries = archive.infolist()
        b.require(len(entries) <= MAX_BUNDLE_FILES + 1, "Source bundle contains too many files")
        names = [entry.filename for entry in entries]
        b.require("checkpoint.json" in names, "Not a creation-source bundle: checkpoint.json is absent")
        b.require(len(set(name.casefold() for name in names)) == len(names), "Source bundle has duplicate/colliding paths")
        b.require(sum(entry.file_size for entry in entries) <= b.MAX_SOURCE_BYTES + b.MAX_COMPANION_BYTES, "Source bundle exceeds uncompressed limits")
        for entry in entries:
            b.validate_path(entry.filename)
            b.require(not entry.is_dir() and not stat.S_ISLNK(entry.external_attr >> 16), "Source bundle must contain ordinary files, not links/directories")
            mode = stat.S_IFMT(entry.external_attr >> 16)
            b.require(mode in {0, stat.S_IFREG}, "Source bundle contains a special filesystem entry")
            b.require(entry.compress_type in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}, "Unsupported creation-source compression")
            b.require(not entry.flag_bits & 1 and entry.file_size <= b.MAX_COMPANION_BYTES, "Encrypted/oversized source entry")
            with archive.open(entry) as handle:
                data = handle.read(b.MAX_COMPANION_BYTES + 1)
            b.require(len(data) == entry.file_size and len(data) <= b.MAX_COMPANION_BYTES, "Source entry size mismatch")
            b.check_text(data, entry.filename, allow_templates=True)
            files[entry.filename] = data
    metadata = b.parse_json(files.pop("checkpoint.json"), "checkpoint.json")
    required_metadata = {"format_version", "kind", "builder_version", "project_id", "blueprint_revision", "status", "native_acceptance", "files"}
    b.require(required_metadata <= set(metadata) <= required_metadata | {"blockers", "validation_error"}, "Unsupported checkpoint metadata fields")
    c.integer(metadata.get("format_version"), 1, 1, "checkpoint.format_version")
    b.require(metadata.get("kind") == "creator-source", "Unsupported creation-source format")
    b.require(metadata["status"] == "Draft" and metadata["native_acceptance"] == "unverified", "A source checkpoint cannot confer native acceptance")
    b.text(metadata["builder_version"], 30, "checkpoint.builder_version")
    b.slug(metadata.get("project_id"), "checkpoint.project_id")
    c.integer(metadata.get("blueprint_revision"), 1, 1_000_000, "checkpoint.blueprint_revision")
    inventory = metadata.get("files")
    b.require(isinstance(inventory, dict) and set(inventory) == set(files), "Creation-source inventory does not match all files")
    for name, data in files.items():
        record = b.exact_keys(inventory[name], {"sha256", "size_bytes"}, "checkpoint file")
        c.integer(record["size_bytes"], 0, b.MAX_COMPANION_BYTES, "checkpoint file size")
        b.require(record["sha256"] == hashlib.sha256(data).hexdigest() and record["size_bytes"] == len(data), "Creation-source hash/size mismatch")
    blueprint = b.parse_json(files.get("workflow-blueprint.json", b"{}"), "workflow-blueprint.json")
    b.require(blueprint.get("project_id") == metadata["project_id"] and blueprint.get("revision") == metadata["blueprint_revision"], "Checkpoint/blueprint identity mismatch")
    b.require(c.REQUIRED_FILES <= set(files), "Source bundle lacks required authoring files")
    for name in files:
        root = name.split("/")[0]
        b.require(root in c.REQUIRED_FILES | c.OPTIONAL_FILES | c.PROJECT_DIRECTORIES, "Source bundle includes an unexpected/raw file")
        if "/" in name:
            b.require(root in c.PROJECT_DIRECTORIES, "Invalid nested authoring-file path")
        b.require(Path(name).suffix in {".json", ".md", ".py", ".txt"}, "Source bundle includes binary/raw media")
    return files, metadata, hashlib.sha256(content).hexdigest()


def reset_resume_claims(files: dict[str, bytes]) -> dict[str, bytes]:
    result = dict(files)
    for name in ("host-profile.json", "build-state.json", "inputs.json", "evaluation-results.json"):
        if name not in result:
            continue
        original = result[name]
        history_path = "history/" + hashlib.sha256(original).hexdigest() + ".json"
        b.require(history_path not in result or result[history_path] == original, "History fingerprint collision")
        result[history_path] = original
        if name == "evaluation-results.json":
            del result[name]
            continue
        document = b.parse_json(original, name)
        if name == "host-profile.json":
            b.exact_keys(document, {"format_version", "project_id", "context", "capabilities", "connections"}, name)
            document["context"] = "unverified"
            for entry in c.array(document["capabilities"], "historical capabilities"):
                b.require(isinstance(entry, dict), "Historical capability must be an object")
                entry["status"] = "unverified"
            for entry in c.array(document["connections"], "historical connections"):
                b.require(isinstance(entry, dict), "Historical connection must be an object")
                entry["status"] = "unverified"
        elif name == "build-state.json":
            document["phase"] = "review"
        elif name == "inputs.json":
            b.exact_keys(document, {"format_version", "project_id", "sources"}, name)
            for source in c.array(document["sources"], "historical sources"):
                b.require(isinstance(source, dict), "Historical source must be an object")
                if source.get("availability") == "attached":
                    source["availability"] = "recorded"
        result[name] = b.json_bytes(document)
    if "capability-report.json" in result:
        original = result.pop("capability-report.json")
        result["history/" + hashlib.sha256(original).hexdigest() + ".json"] = original
    return result


def resume(bundle: Path, destination: Path) -> dict:
    files, metadata, digest = read_bundle(bundle)
    restored = reset_resume_claims(files)
    write_tree_new(destination, restored)
    return {"status": "Draft", "project_id": metadata["project_id"], "blueprint_revision": metadata["blueprint_revision"], "source_bundle_sha256": digest, "files": len(restored), "native_acceptance": "unverified", "requires_host_recheck": True, "requires_evaluation_refresh": True, "note": "Original control records are preserved under history; recorded evidence is not a live attachment."}


def merge(base_bundle: Path, current: Path, proposed: Path, destination: Path) -> dict:
    base, base_meta, digest = read_bundle(base_bundle)
    current_files, current_meta = snapshot_project(current)
    proposed_files, proposed_meta = snapshot_project(proposed)
    b.require(base_meta["project_id"] == current_meta["project_id"] == proposed_meta["project_id"], "Cannot merge different creation projects")
    b.require(current_meta["blueprint_revision"] == base_meta["blueprint_revision"], "Current project is not based on this checkpoint revision")
    b.require(proposed_meta["blueprint_revision"] == base_meta["blueprint_revision"] + 1, "Proposed correction must advance the base revision exactly once")
    merged, conflicts = {}, []
    for name in sorted(set(base) | set(current_files) | set(proposed_files)):
        old, edited, generated = base.get(name), current_files.get(name), proposed_files.get(name)
        if edited == old:
            chosen = generated
        elif generated == old or edited == generated:
            chosen = edited
        else:
            conflicts.append(name)
            continue
        if chosen is not None:
            merged[name] = chosen
    if conflicts:
        raise MergeConflict(conflicts)
    restored = reset_resume_claims(merged)
    state = b.parse_json(restored["build-state.json"], "build-state.json")
    state["blueprint_revision"] = proposed_meta["blueprint_revision"]
    restored["build-state.json"] = b.json_bytes(state)
    write_tree_new(destination, restored)
    return {"status": "Draft", "project_id": base_meta["project_id"], "blueprint_revision": proposed_meta["blueprint_revision"], "base_sha256": digest, "files": len(restored), "conflicts": [], "native_acceptance": "unverified", "requires_host_recheck": True, "requires_evaluation_refresh": True}


def build_project(project: Path, output: Path, report_path: Path, target: str = b.TARGET, metadata: Path | None = None) -> dict:
    b.require(target == b.TARGET, "Output plugins must use native Microsoft Cowork manifest v1.28; no Claude-compatible fallback")
    checked = c.validate_project(project)
    b.require(checked["ready"], "Project is not ready to package: " + "; ".join(item["code"] + " at " + item["reference"] for item in checked["blockers"]))
    b.require(not output.resolve().is_relative_to(project.resolve()) and not report_path.resolve().is_relative_to(project.resolve()), "Build outputs must be outside the creation project")
    b.require(not output.exists() and not report_path.exists(), "Output/report already exists")
    b.require(not output.is_symlink() and not report_path.is_symlink(), "Output/report must not be symlinks")
    b.require(output.suffix == ".zip" and report_path.suffix == ".json", "Expected .zip package and .json report filenames")
    b.require(output.resolve() != report_path.resolve(), "Package and report paths must be distinct")
    b.require(output.parent.is_dir() and report_path.parent.is_dir(), "Output/report parent directory must exist")
    with tempfile.TemporaryDirectory(prefix="creator-build-", dir=output.parent) as temporary:
        stage = Path(temporary)
        result = b.build(project / "candidate", stage / "plugin.zip", stage / "build.json", target, metadata)
        result.update({
            "project_id": checked["project_id"], "blueprint_revision": checked["blueprint_revision"],
            "blueprint_sha256": checked["blueprint_sha256"], "candidate_sha256": checked["candidate_sha256"],
            "host_context": checked["host_context"], "coverage": checked["coverage"],
            "process_validation": "declared evidence/reference/capability/evaluation consistency only",
        })
        if checked["host_context"] != "native-observed":
            result["status"] = "Draft"
            result["provisional_offline"] = True
        b.write_new_file(output, (stage / "plugin.zip").read_bytes())
        try:
            b.write_new_file(report_path, b.json_bytes(result))
        except OSError:
            output.unlink()
            raise
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init")
    for flag in ("project", "id", "title", "purpose"):
        init.add_argument("--" + flag, required=True, type=Path if flag == "project" else str)
    check = commands.add_parser("check")
    check.add_argument("--project", type=Path, required=True)
    check.add_argument("--report", type=Path)
    assembly = commands.add_parser("assemble")
    assembly.add_argument("--plan", type=Path, required=True)
    assembly.add_argument("--output", type=Path, required=True)
    build = commands.add_parser("build")
    for flag in ("project", "output", "report"):
        build.add_argument("--" + flag, type=Path, required=True)
    build.add_argument("--target", choices=(b.TARGET,), default=b.TARGET)
    build.add_argument("--metadata", type=Path)
    save = commands.add_parser("checkpoint")
    save.add_argument("--project", type=Path, required=True)
    save.add_argument("--output", type=Path, required=True)
    restore = commands.add_parser("resume")
    restore.add_argument("--bundle", type=Path, required=True)
    restore.add_argument("--output", type=Path, required=True)
    correction = commands.add_parser("merge")
    for flag in ("base", "current", "proposed", "output"):
        correction.add_argument("--" + flag, type=Path, required=True)
    args = parser.parse_args()
    try:
        b.require(sys.version_info >= (3, 10), "Existing Python 3.10+ required; do not install a runtime")
        if args.command == "init":
            result = init_project(args.project, args.id, args.title, args.purpose)
        elif args.command == "check":
            result = c.validate_project(args.project)
            if args.report:
                b.write_new_file(args.report, b.json_bytes(result))
        elif args.command == "assemble":
            result = assemble_candidate(args.plan, args.output)
        elif args.command == "build":
            result = build_project(args.project, args.output, args.report, args.target, args.metadata)
        elif args.command == "checkpoint":
            result = checkpoint(args.project, args.output)
        elif args.command == "resume":
            result = resume(args.bundle, args.output)
        else:
            result = merge(args.base, args.current, args.proposed, args.output)
    except MergeConflict as exc:
        print(json.dumps({"status": "Draft", "error": str(exc), "conflicts": exc.paths}), file=sys.stderr)
        return 2
    except (b.BuildError, OSError, UnicodeError, zipfile.BadZipFile) as exc:
        print(json.dumps({"status": "Draft", "error": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, indent=2))
    return 2 if args.command == "check" and not result["ready"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
