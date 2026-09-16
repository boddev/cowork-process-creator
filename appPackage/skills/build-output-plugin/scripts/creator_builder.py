"""Creator emitted-subset source checker and deterministic ZIP builder (stdlib only)."""
from __future__ import annotations

import argparse
import ast
import hashlib
import io
import json
import re
import stat
import struct
import sys
import uuid
import zipfile
import zlib
from pathlib import Path
from urllib.parse import urlsplit

VERSION = "0.3.0"
TARGET = "cowork-v1.28"
SPEC_VERSION = "creator-plugin-1"
SCHEMA = "https://developer.microsoft.com/json-schemas/teams/v1.28/MicrosoftTeams.schema.json"
MAX_COMPANIONS = 20
MAX_COMPANION_BYTES = 5_000_000
MAX_COMPANION_TOTAL = 10_000_000
MAX_SKILL_BYTES = 1_000_000
MAX_SOURCE_BYTES = 32_000_000
SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
SAFE_COMPONENT = re.compile(r"[A-Za-z0-9_. !-]+\Z")
RESERVED = {"CON", "PRN", "AUX", "NUL"} | {
    prefix + str(number) for prefix in ("COM", "LPT") for number in range(1, 10)
}
PYTHON_MODULES = {
    "__future__", "argparse", "ast", "calendar", "collections", "csv",
    "datetime", "decimal", "hashlib", "io", "itertools", "json", "math",
    "pathlib", "re", "stat", "statistics", "string", "struct", "sys",
    "typing", "urllib.parse", "uuid", "zipfile", "zlib", "tempfile", "contextlib",
}
SECRET_PATTERNS = (
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\b(?:ghp_|github_pat_)[A-Za-z0-9_]{25,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9_.-]{20,}"),
    re.compile(r"(?i)(?:api[_-]?key|client[_-]?secret|password)[\"']?\s*[:=]\s*[\"'][^\"'\s]{8,}[\"']"),
)
UNRESOLVED = re.compile(r"\$\{\{?|\{\{|YOUR[-_](?:GUID|URL|TOKEN|ID|KEY)|<REPL[A]CE", re.I)
ABSOLUTE_USER_PATH = re.compile(r"[A-Za-z]:[\\/](?:Users|home)[\\/]|/(?:Users|home)/[^/\s]+/")


class BuildError(ValueError):
    """An explicit rejected input; diagnostics never echo secret values."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise BuildError(message)


def exact_keys(value: object, keys: set[str], label: str) -> dict:
    require(isinstance(value, dict), f"{label}: expected an object")
    require(set(value) == keys, f"{label}: required fields are {', '.join(sorted(keys))}; unexpected fields are not supported")
    return value


def text(value: object, maximum: int, label: str) -> str:
    require(isinstance(value, str), f"{label}: expected text")
    require(0 < len(value.strip()) <= maximum and len(value) <= maximum, f"{label}: expected 1-{maximum} characters")
    require(not any(ord(char) < 32 for char in value), f"{label}: control characters are not allowed")
    return value


def prose(value: object, maximum: int, label: str) -> str:
    require(isinstance(value, str) and 0 < len(value.strip()) <= maximum and len(value) <= maximum, f"{label}: expected 1-{maximum} characters")
    require(not any(ord(char) < 32 and char not in "\n\r\t" for char in value), f"{label}: invalid control characters")
    return value


def slug(value: object, label: str) -> str:
    value = text(value, 64, label)
    require(SLUG.fullmatch(value) is not None, f"{label}: expected kebab-case")
    return value


def unique_object(pairs: list) -> dict:
    result = {}
    for key, value in pairs:
        require(key not in result, "JSON: duplicate object field")
        result[key] = value
    return result


def reject_constant(value: str) -> None:
    raise BuildError("JSON: non-finite numbers are not supported")


def parse_json(content: bytes, label: str, object_only: bool = True) -> object:
    require(len(content) <= MAX_COMPANION_BYTES, f"{label}: JSON exceeds the 5 MB safety ceiling")
    try:
        value = json.loads(content.decode("utf-8"), object_pairs_hook=unique_object, parse_constant=reject_constant)
    except UnicodeDecodeError as exc:
        raise BuildError(f"{label}: JSON must be UTF-8") from exc
    except json.JSONDecodeError as exc:
        raise BuildError(f"{label}: invalid JSON at line {exc.lineno}, column {exc.colno}") from exc
    except RecursionError as exc:
        raise BuildError(f"{label}: JSON nesting is too deep") from exc
    except ValueError as exc:
        if isinstance(exc, BuildError):
            raise
        raise BuildError(f"{label}: JSON number is outside the parser's supported range") from exc
    require(not object_only or isinstance(value, dict), f"{label}: expected an object")
    pending = [(value, 0)]
    while pending:
        current, depth = pending.pop()
        require(depth <= 32, f"{label}: JSON nesting exceeds the 32-level safety limit")
        if isinstance(current, dict):
            pending.extend((item, depth + 1) for item in current.values())
        elif isinstance(current, list):
            pending.extend((item, depth + 1) for item in current)
    return value


def read_json(path: Path) -> dict:
    check_regular(path)
    require(path.stat().st_size <= MAX_COMPANION_BYTES, f"{path.name}: JSON exceeds the 5 MB safety ceiling")
    with path.open("rb") as handle:
        content = handle.read(MAX_COMPANION_BYTES + 1)
    return parse_json(content, path.name)


def json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=True, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")


def validate_path(relative: str) -> None:
    require(0 < len(relative) <= 256, "Package path: expected 1-256 characters")
    require("\\" not in relative and "\0" not in relative, "Package path: backslash or null byte")
    for component in relative.split("/"):
        require(bool(component) and component not in {".", ".."}, "Package path: empty or traversal segment")
        require(SAFE_COMPONENT.fullmatch(component) is not None, "Package path: unsafe characters")
        require(not component.startswith(".") and not component.endswith((".", " ")), "Package path: hidden or ambiguous name")
        require(component.split(".")[0].rstrip(" ").upper() not in RESERVED, "Package path: Windows reserved name")


def check_regular(path: Path, directory: bool = False) -> None:
    info = path.lstat()
    require(not stat.S_ISLNK(info.st_mode), f"{path.name}: symlinks are not allowed")
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    require(not getattr(info, "st_file_attributes", 0) & reparse_flag, f"{path.name}: reparse points are not allowed")
    valid = stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)
    require(valid, f"{path.name}: expected a {'directory' if directory else 'regular file'}")


def check_text(content: bytes, label: str, allow_templates: bool = False) -> str:
    value = content.decode("utf-8")
    require("\0" not in value, f"{label}: null bytes are not allowed")
    require(allow_templates or not UNRESOLVED.search(value), f"{label}: unresolved template token")
    require(not ABSOLUTE_USER_PATH.search(value), f"{label}: absolute user/developer path")
    require(not any(pattern.search(value) for pattern in SECRET_PATTERNS), f"{label}: possible credential; remove it and use native authentication")
    return value


def check_python(value: str, label: str, local_modules: set[str] | None = None) -> None:
    try:
        tree = ast.parse(value, filename=label)
    except SyntaxError as exc:
        raise BuildError(f"{label}: Python syntax error at line {exc.lineno}") from exc
    except (RecursionError, MemoryError) as exc:
        raise BuildError(f"{label}: Python structure exceeds parser limits") from exc
    allowed = PYTHON_MODULES | (local_modules or set())
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            modules = [alias.name for alias in node.names] if isinstance(node, ast.Import) else [node.module]
            require(not isinstance(node, ast.ImportFrom) or node.level == 0, f"{label}: relative imports are outside the emitted subset")
            require(all(module in allowed for module in modules), f"{label}: import outside the allowed standard-library or same-directory bundled subset")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            require(node.func.id not in {"eval", "exec", "compile", "__import__"}, f"{label}: dynamic execution is outside the emitted subset")


def check_skill(content: bytes, name: str) -> None:
    require(len(content) <= MAX_SKILL_BYTES, f"{name}: SKILL.md exceeds the N00 1 MB ceiling")
    lines = check_text(content, name + "/SKILL.md").splitlines()
    require(len(lines) >= 5 and lines[0] == "---" and lines[3] == "---", f"{name}: expected the documented two-field frontmatter subset")
    require(lines[1] == "name: " + name, f"{name}: frontmatter name must match folder")
    require(lines[2].startswith("description: "), f"{name}: missing description")
    try:
        description = json.loads(lines[2][13:])
    except json.JSONDecodeError as exc:
        raise BuildError(f"{name}: description must be a JSON-quoted single-line YAML string") from exc
    text(description, 1024, f"{name}.description")
    require(bool("\n".join(lines[4:]).strip()), f"{name}: skill body must not be empty")


def check_resource_references(entries: dict[str, bytes], name: str) -> None:
    for path, content in entries.items():
        if not path.endswith(".md"):
            continue
        value = content.decode("utf-8")
        references = re.findall(r"`((?:scripts|references|assets)/[^`\r\n]+)`", value)
        references.extend(re.findall(r"\]\(((?:scripts|references|assets)/[^)\s]+)\)", value))
        for reference in references:
            validate_path(reference)
            require(f"skills/{name}/{reference}" in entries, f"{path}: missing referenced companion {reference}")
        require(not re.search(r"\]\((?:\.\./|/|[A-Za-z]:[\\/])", value), f"{path}: external filesystem links are outside the self-contained subset")


def collect_skills(source: Path, names: list[str]) -> dict[str, bytes]:
    skills_dir = source / "skills"
    check_regular(skills_dir, directory=True)
    require({item.name for item in skills_dir.iterdir()} == set(names), "skills: folders must exactly match the specification")
    payload = {}
    total = 0
    seen_paths = set()

    def collect(directory: Path, collected: dict[str, bytes]) -> None:
        nonlocal total
        for path in sorted(directory.iterdir()):
            relative = path.relative_to(source).as_posix()
            validate_path(relative)
            folded = relative.casefold()
            require(folded not in seen_paths, "Package path: case-insensitive collision")
            seen_paths.add(folded)
            require(path.resolve().is_relative_to(source), "Package path: escapes source")
            check_regular(path, directory=path.is_dir())
            if path.is_dir():
                collect(path, collected)
            else:
                limit = MAX_SKILL_BYTES if path.name == "SKILL.md" else MAX_COMPANION_BYTES
                require(path.stat().st_size <= limit, f"{relative}: file exceeds size ceiling")
                total += path.stat().st_size
                require(total <= MAX_SOURCE_BYTES, "Source exceeds the N00 32 MB safety ceiling")
                content = path.read_bytes()
                require(len(content) <= limit, f"{relative}: file changed beyond size ceiling")
                if path.name != "SKILL.md":
                    require(path.suffix in {".py", ".json", ".md", ".txt"}, f"{relative}: binary/media or unsupported companion")
                value = check_text(content, relative)
                if path.suffix == ".json":
                    parse_json(content, relative, object_only=False)
                collected[relative] = content

    for name in names:
        skill_dir = skills_dir / name
        check_regular(skill_dir, directory=True)
        entries = {}
        collect(skill_dir, entries)
        skill_path = f"skills/{name}/SKILL.md"
        require(skill_path in entries, f"{name}: missing SKILL.md")
        check_skill(entries[skill_path], name)
        check_resource_references(entries, name)
        for relative, content in entries.items():
            if relative.endswith(".py"):
                parent = relative.rsplit("/", 1)[0]
                local_modules = {
                    key.rsplit("/", 1)[1][:-3] for key in entries
                    if key.endswith(".py") and key.rsplit("/", 1)[0] == parent
                }
                require(not local_modules & sys.stdlib_module_names, f"{name}: bundled module shadows the standard library")
                check_python(content.decode("utf-8"), relative, local_modules)
        companions = [content for path, content in entries.items() if path != skill_path]
        require(len(companions) <= MAX_COMPANIONS, f"{name}: more than 20 companions")
        require(sum(map(len, companions)) <= MAX_COMPANION_TOTAL, f"{name}: companions exceed 10 MB")
        payload.update(entries)
    return payload


def read_spec(source: Path) -> dict:
    check_regular(source, directory=True)
    roots = {item.name for item in source.iterdir()}
    require(roots in ({"plugin-spec.json", "skills"}, {"plugin-spec.json", "skills", "tools"}), "Source must contain exactly plugin-spec.json, skills and optionally tools")
    path = source / "plugin-spec.json"
    check_regular(path)
    require(path.stat().st_size <= 20_000, "plugin-spec.json: exceeds the prototype size ceiling")
    check_text(path.read_bytes(), path.name)
    spec = read_json(path)
    require(isinstance(spec.get("schema_version"), str) and spec["schema_version"] in {SPEC_VERSION, "n00-1"}, "plugin-spec.json: unsupported schema_version")
    keys = {"schema_version", "name", "title", "version", "summary", "description", "skills"}
    if spec["schema_version"] == SPEC_VERSION:
        keys.add("connectors")
    exact_keys(spec, keys, "plugin-spec.json")
    slug(spec["name"], "plugin.name")
    text(spec["title"], 30, "plugin.title")
    text(spec["summary"], 80, "plugin.summary")
    prose(spec["description"], 4000, "plugin.description")
    version = text(spec["version"], 30, "plugin.version")
    require(re.fullmatch(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)", version) is not None, "plugin.version: expected three decimal components")
    names = spec["skills"]
    require(isinstance(names, list) and 1 <= len(names) <= 20, "plugin.skills: expected 1-20 skills")
    for name in names:
        slug(name, "plugin.skills item")
    require(len(set(names)) == len(names), "plugin.skills: duplicate name")
    return spec


def https_url(value: object, label: str) -> str:
    value = text(value, 2048, label)
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise BuildError(f"{label}: invalid HTTPS URL") from exc
    require(parsed.scheme == "https" and bool(parsed.hostname), f"{label}: HTTPS URL required")
    require(not parsed.username and not parsed.password and not parsed.query and not parsed.fragment and port in {None, 443}, f"{label}: credentials, query, fragment or nonstandard port not supported")
    require(not any(char.isspace() for char in value) and "\\" not in value, f"{label}: invalid URL characters")
    host = parsed.hostname.lower()
    require("." in host and len(host) <= 253 and all(re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", part) for part in host.split(".")), f"{label}: invalid DNS hostname")
    reserved = {"example.com", "example.org", "example.net", "contoso.com", "localhost"}
    require(not any(host == item or host.endswith("." + item) for item in reserved) and not host.endswith((".invalid", ".example", ".test", ".localhost", ".local")), f"{label}: placeholder/local domains are not real supplied metadata")
    require(not re.fullmatch(r"[0-9.]+", host), f"{label}: numeric addresses are outside the emitted subset")
    return value


def provenance(value: object, label: str) -> dict:
    value = exact_keys(value, {"kind", "reference"}, label)
    require(isinstance(value["kind"], str) and value["kind"] in {"user-supplied", "native-discovery"}, f"{label}: provenance must be user-supplied or native-discovery")
    text(value["reference"], 2048, label + ".reference")
    return value


def local_schema_references(schema: dict, label: str) -> None:
    pending = [schema]
    while pending:
        item = pending.pop()
        if isinstance(item, dict):
            if "$ref" in item:
                require(isinstance(item["$ref"], str) and item["$ref"].startswith("#/"), f"{label}: external schema references are outside the bundled subset")
                pointer = schema
                for part in item["$ref"][2:].split("/"):
                    key = part.replace("~1", "/").replace("~0", "~")
                    if isinstance(pointer, dict):
                        require(key in pointer, f"{label}: unresolved local schema reference")
                        pointer = pointer[key]
                    elif isinstance(pointer, list) and re.fullmatch(r"0|[1-9][0-9]*", key):
                        require(int(key) < len(pointer), f"{label}: unresolved local schema reference")
                        pointer = pointer[int(key)]
                    else:
                        raise BuildError(f"{label}: unresolved local schema reference")
            pending.extend(item.values())
        elif isinstance(item, list):
            pending.extend(item)


def tool_descriptions(value: object, label: str) -> list:
    require(isinstance(value, list) and 1 <= len(value) <= 100, f"{label}: expected 1-100 real tool descriptions")
    names = set()
    for index, tool in enumerate(value):
        here = f"{label}[{index}]"
        require(isinstance(tool, dict), f"{here}: expected an object")
        require({"name", "description", "inputSchema"} <= set(tool) <= {"name", "title", "description", "inputSchema", "outputSchema", "annotations", "execution"}, f"{here}: unsupported tool descriptor fields")
        name = text(tool["name"], 128, here + ".name")
        require(re.fullmatch(r"[A-Za-z0-9_.-]+", name) is not None and name not in names, f"{here}: invalid or duplicate tool name")
        names.add(name)
        prose(tool["description"], 10000, here + ".description")
        if "title" in tool:
            text(tool["title"], 1024, here + ".title")
        schema = tool["inputSchema"]
        require(isinstance(schema, dict) and schema.get("type") == "object", f"{here}: inputSchema must describe an object")
        require(isinstance(schema.get("properties", {}), dict), f"{here}: inputSchema.properties must be an object")
        required = schema.get("required", [])
        require(isinstance(required, list) and all(isinstance(item, str) for item in required), f"{here}: invalid required list")
        require(len(set(required)) == len(required) and set(required) <= set(schema.get("properties", {})), f"{here}: required references missing properties")
        local_schema_references(schema, here + ".inputSchema")
        if "annotations" in tool:
            require(isinstance(tool["annotations"], dict), f"{here}: annotations must be an object")
            if "title" in tool["annotations"]:
                text(tool["annotations"]["title"], 1024, here + ".annotations.title")
            for hint in ("readOnlyHint", "destructiveHint", "idempotentHint", "openWorldHint"):
                if hint in tool["annotations"]:
                    require(type(tool["annotations"][hint]) is bool, f"{here}: annotation hints must be Booleans, not permissions")
        if "outputSchema" in tool:
            require(isinstance(tool["outputSchema"], dict), f"{here}: outputSchema must be an object")
            local_schema_references(tool["outputSchema"], here + ".outputSchema")
        if "execution" in tool:
            require(isinstance(tool["execution"], dict), f"{here}: execution metadata must be an object")
    return value


def connector_payload(source: Path, spec: dict) -> tuple[dict[str, bytes], list]:
    connectors = spec.get("connectors", [])
    require(isinstance(connectors, list) and len(connectors) <= 10, "connectors: maximum 10 entries")
    payload, declarations, ids = {}, [], set()
    for index, connector in enumerate(connectors):
        here = f"connectors[{index}]"
        connector = exact_keys(connector, {"id", "display_name", "description", "server_url", "authorization", "tools_file", "provenance"}, here)
        identifier = slug(connector["id"], here + ".id")
        require(identifier not in ids, "connectors: duplicate id")
        ids.add(identifier)
        text(connector["display_name"], 128, here + ".display_name")
        prose(connector["description"], 4000, here + ".description")
        url = https_url(connector["server_url"], here + ".server_url")
        provenance(connector["provenance"], here + ".provenance")
        file = text(connector["tools_file"], 256, here + ".tools_file")
        validate_path(file)
        require(file.startswith("tools/") and file.endswith(".json"), f"{here}: tools_file must be under tools with .json extension")
        path = source / file
        for parent in (path, *path.parents):
            if parent == source:
                break
            check_regular(parent, directory=parent.is_dir())
        require(path.resolve().is_relative_to(source.resolve()), f"{here}: tools_file escapes source")
        require(path.stat().st_size <= MAX_COMPANION_BYTES, f"{here}: tool descriptor too large")
        content = path.read_bytes()
        check_text(content, file)
        descriptor = exact_keys(parse_json(content, file), {"tools"}, file)
        tool_descriptions(descriptor["tools"], file + ".tools")
        remote = {"mcpServerUrl": url, "mcpToolDescription": {"file": "./" + file}}
        auth = connector["authorization"]
        require(isinstance(auth, dict), f"{here}: authorization must be an object")
        require(isinstance(auth.get("type"), str), f"{here}: authorization.type must be text")
        if auth.get("type") in {"None", "DynamicClientRegistration"}:
            exact_keys(auth, {"type"}, here + ".authorization")
            if auth["type"] == "None":
                remote["authorization"] = {"type": "None"}
        elif auth.get("type") == "OAuthPluginVault":
            exact_keys(auth, {"type", "referenceId"}, here + ".authorization")
            reference = text(auth["referenceId"], 128, here + ".authorization.referenceId")
            require(re.fullmatch(r"[A-Za-z0-9_-]+", reference) is not None, f"{here}: invalid supplied OAuth registration reference")
            require(reference.lower() not in {"none", "unknown", "placeholder", "replace-me"}, f"{here}: missing actual OAuth registration reference")
            remote["authorization"] = dict(auth)
        else:
            raise BuildError(f"{here}: unsupported native auth; API-key availability must not be inferred from its schema enum")
        payload[file] = content
        declarations.append({"id": identifier, "displayName": connector["display_name"], "description": connector["description"], "toolSource": {"remoteMcpServer": remote}})
    tools = source / "tools"
    if tools.exists():
        check_regular(tools, directory=True)
        actual = set()
        for path in tools.rglob("*"):
            check_regular(path, directory=path.is_dir())
            relative = path.relative_to(source).as_posix()
            validate_path(relative)
            if path.is_file():
                actual.add(relative)
        require(actual == set(payload), "tools: every file must be referenced by a declared connector")
    else:
        require(not connectors, "tools: missing connector tool descriptors")
    return payload, sorted(declarations, key=lambda entry: entry["id"])


def source_payload(source: Path) -> tuple[dict[str, bytes], dict, list]:
    check_regular(source, directory=True)
    source = source.resolve(strict=True)
    spec = read_spec(source)
    payload = collect_skills(source, spec["skills"])
    tools, connectors = connector_payload(source, spec)
    payload.update(tools)
    require(sum(map(len, payload.values())) <= MAX_SOURCE_BYTES, "Source exceeds the 32 MB safety ceiling")
    require(len({name.casefold() for name in payload}) == len(payload), "Package path: case-insensitive collision")
    return payload, spec, connectors


def publishing_metadata(path: Path | None) -> dict:
    require(path is not None, "cowork-v1.28 requires --metadata with supplied app_id and approved publisher name/website/privacy/terms URLs; missing metadata blocks packaging, with no alternative-format fallback")
    check_regular(path)
    require(path.stat().st_size <= 20_000, "Publishing metadata exceeds the prototype size ceiling")
    check_text(path.read_bytes(), "Publishing metadata")
    metadata = exact_keys(read_json(path), {"app_id", "developer"}, "Publishing metadata")
    app_id = text(metadata["app_id"], 36, "app_id")
    try:
        parsed = uuid.UUID(app_id)
    except ValueError as exc:
        raise BuildError("app_id: expected a non-nil UUID") from exc
    require(parsed.int != 0 and str(parsed) == app_id, "app_id: expected a canonical lowercase non-nil UUID")
    developer = exact_keys(metadata["developer"], {"name", "websiteUrl", "privacyUrl", "termsOfUseUrl"}, "developer")
    text(developer["name"], 32, "developer.name")
    for field in ("websiteUrl", "privacyUrl", "termsOfUseUrl"):
        https_url(developer[field], "developer." + field)
    return metadata


def png_icon(size: int, outline: bool) -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    rows = bytearray()
    for y in range(size):
        rows.append(0)
        for x in range(size):
            edge = size // 4 <= x < 3 * size // 4 and size // 5 <= y < 4 * size // 5
            inside = size // 4 + 2 <= x < 3 * size // 4 - 2 and size // 5 + 2 <= y < 4 * size // 5 - 2
            mark = edge and not inside
            rows.extend((255, 255, 255, 255) if mark else ((0, 0, 0, 0) if outline else (38, 70, 105, 255)))
    header = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(bytes(rows), level=9)) + chunk(b"IEND", b"")


def assemble(source: Path, target: str = TARGET, metadata_path: Path | None = None) -> tuple[dict[str, bytes], dict]:
    require(target == TARGET, "Only native Microsoft Copilot Cowork packages are supported: use cowork-v1.28 with approved metadata; Claude-compatible source ZIPs are not plugin outputs")
    payload, spec, connectors = source_payload(source)
    metadata = publishing_metadata(metadata_path)
    manifest = {
        "$schema": SCHEMA, "manifestVersion": "1.28", "version": spec["version"],
        "id": metadata["app_id"], "developer": metadata["developer"],
        "name": {"short": spec["title"], "full": spec["title"]},
        "description": {"short": spec["summary"], "full": spec["description"]},
        "icons": {"color": "color.png", "outline": "outline.png"},
        "accentColor": "#264669",
        "agentSkills": [{"folder": "./skills/" + name} for name in sorted(spec["skills"])],
    }
    if connectors:
        manifest["agentConnectors"] = connectors
    payload["manifest.json"] = json_bytes(manifest)
    payload["color.png"] = png_icon(192, outline=False)
    payload["outline.png"] = png_icon(32, outline=True)
    return payload, spec


def zip_bytes(payload: dict[str, bytes]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, data in sorted(payload.items()):
            info = zipfile.ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            archive.writestr(info, data)
    return output.getvalue()


def write_new_file(path: Path, content: bytes) -> None:
    handle = path.open("xb")
    try:
        with handle:
            handle.write(content)
    except OSError:
        path.unlink()
        raise


def build(source: Path, output: Path, report_path: Path, target: str = TARGET, metadata_path: Path | None = None) -> dict:
    require(target == TARGET, "Only native Microsoft Copilot Cowork packages are supported; alternative source ZIPs cannot satisfy a plugin build")
    source_resolved = source.resolve(strict=True)
    for destination in (output, report_path):
        require(not destination.exists() and not destination.is_symlink(), f"{destination.name}: refusing to overwrite existing output")
        require(not destination.resolve().is_relative_to(source_resolved), "Outputs must be outside the candidate source")
        require(metadata_path is None or destination.resolve() != metadata_path.resolve(), "Output collides with publishing metadata")
        require(destination.parent.is_dir(), f"{destination.name}: output parent directory does not exist")
    require(output.resolve() != report_path.resolve(), "ZIP and report paths must be different")
    require(output.suffix.lower() == ".zip" and report_path.suffix.lower() == ".json", "Expected .zip output and .json build report")
    payload, spec = assemble(source, target, metadata_path)
    archive = zip_bytes(payload)
    report = {
        "builder_version": VERSION,
        "target": target,
        "plugin": spec["name"],
        "status": "Package built",
        "artifact_kind": "native-package",
        "validation_scope": "Creator emitted source/manifest/descriptor subset; not the full Microsoft schema or a code sandbox",
        "host_acceptance": "unverified",
        "native_execution": "not_attested_by_builder",
        "manual_invocation": "unverified",
        "scheduling": "not_exercised",
        "publishing_metadata": "supplied; syntax checked only",
        "sha256": hashlib.sha256(archive).hexdigest(),
        "size_bytes": len(archive),
        "files": [{"path": name, "size_bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()} for name, data in sorted(payload.items())],
    }
    write_new_file(output, archive)
    try:
        write_new_file(report_path, json_bytes(report))
    except OSError:
        output.unlink()
        raise
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("probe", help="Report this interpreter; does not attest a native host")
    validate_parser = commands.add_parser("validate", help="Check source only, without process or native acceptance claims")
    validate_parser.add_argument("--source", type=Path, required=True)
    build_parser = commands.add_parser("build")
    build_parser.add_argument("--source", type=Path, required=True)
    build_parser.add_argument("--output", type=Path, required=True)
    build_parser.add_argument("--report", type=Path, required=True)
    build_parser.add_argument("--target", choices=(TARGET,), default=TARGET)
    build_parser.add_argument("--metadata", type=Path)
    args = parser.parse_args()
    try:
        require(sys.version_info >= (3, 10), "Python 3.10 or later is required; do not install a runtime inside Cowork")
        if args.command == "probe":
            result = {
                "builder_version": VERSION, "python_version": sys.version.split()[0],
                "platform": sys.platform, "standard_library_only": True,
                "zip_probe_sha256": hashlib.sha256(zip_bytes({"probe.txt": b"N00\n"})).hexdigest(),
                "host_acceptance": "not_assessed", "native_context": "must_be_observed_by_operator",
            }
        elif args.command == "validate":
            payload, spec, connectors = source_payload(args.source)
            result = {"status": "Draft", "source_valid": True, "plugin": spec["name"], "files": len(payload), "connectors": len(connectors), "host_acceptance": "unverified", "scope": "source subset only; no workflow coverage check"}
        else:
            result = build(args.source, args.output, args.report, args.target, args.metadata)
    except (BuildError, OSError, UnicodeError) as exc:
        print(json.dumps({"status": "Draft", "error": str(exc)}, ensure_ascii=True), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=True, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
