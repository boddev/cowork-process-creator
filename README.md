# Self-contained Cowork Process Creator

**v0.2.1 is a provisional offline implementation, not a native release claim.**
Eight focused skills guide Cowork from a procedure plus video or ordered
screenshots to a reusable output plugin. A bundled Python-standard-library
toolkit validates authoring contracts, assembles source, composes its supported
package subset, and exports revision-preserving creation-source bundles.

Cowork supplies reasoning, native attachment/media/file facilities, permitted
execution, existing connections and the user experience. There is **no**
authoring backend, custom MCP server, Azure deployment, external model/media
API, browser/desktop runner, gateway, queue, runtime installer or scheduler.
End users do not install Python, wiqd, ATK, FFmpeg or developer tooling.
If the required existing native capability is missing, the workflow stops
with that limitation.

## Download the preview

Get [creator.zip](https://github.com/boddev/cowork-process-creator/releases/download/v0.2.1/creator.zip)
from the [v0.2.1 preview release](https://github.com/boddev/cowork-process-creator/releases/tag/v0.2.1).
This is a **compatible-source preview**, not a canonical v1.28 package or
a claim of native acceptance for this version. See the
[user guide](docs/user-guide.md) for Cowork's native upload/conversion path
and the current limitations.

The ZIP is 230,892 bytes, with SHA-256:

```text
9251dabf6c57e44e2ab77a17982837c584082fccbfb00a3ca42cafa2af136c08
```

## Current native boundary

The original v0.1.0 Creator was installed through native compatible-source
conversion and produced a real output ZIP using its bundled builder in
Cowork's Linux Python 3.12.14 environment. Its limited synthetic video was
observed through an already-present native decoder and three inspected
frames, not universal direct video/narration/all-frame support.

The original native proof did not complete independent output invocation.
Its last observed output-installation result is **unknown**, so N00 and
native N08 remain incomplete. Inspect the actual native installation state
before retrying that operation. The historical details are in
[operator continuation](docs/operator-continuation.md).

The expanded candidate inherits none of those older installation/execution
claims. Direct canonical v1.28 packaging still requires real approved
publisher metadata; none is supplied by default.

## Offline build and checks

The ordinary development path uses only Python's standard library:

```powershell
python -B -m unittest discover -s tests -v
python -B scripts\build_release.py
```

The release builder produces short-name artifacts under `dist\v0.2.1`:
`creator.zip`, its source-only build report, release/inventory JSON, and three
distinct synthetic file-workflow examples with output plugins, source/resume
bundles, real local helper outputs, coverage and expected negative cases.
It also carries a clearly separate real-public-MCP metadata example whose
Cowork availability remains unknown. It performs no network calls.

Existing differing release directories are not overwritten: bump the version
or pass a new `--output` directory. Original v0.1.0/v0.1.1 and native proof
artifacts remain unchanged. Development commands are not end-user runtime
dependencies.

## Toolkit and source layout

The owning `build-output-plugin` skill contains `creator_builder.py`,
`project_contracts.py` and `creator_project.py` together. Same-directory
imports are explicit; no cross-skill installation paths are required.

| Command | Purpose |
|---|---|
| `init` | Create a new draft project without overwriting files |
| `check` | Validate evidence, blueprint, decisions, real bindings and current fingerprints |
| `assemble` | Materialize generated skill bodies/resources into consistent source |
| `build` | Require coherent coverage/evaluations, then create the actual ZIP |
| `checkpoint` | Export a hashed creation-source bundle without raw attachments/secrets |
| `resume` | Verify and restore to a new directory, reset inherited host/evaluation claims |
| `merge` | Preserve separate user/generated edits; fail atomically on conflicting files |

Read the [project contract](appPackage/skills/build-output-plugin/references/project-contract.md)
and [emitted target rules](appPackage/skills/build-output-plugin/references/target-rules.md)
for exact formats and flags. This is an authoring toolkit, not a workflow
interpreter, distributed lock, account permission system or full arbitrary
Microsoft/JSON Schema validator.

## Targets and connections

`compatible-source` is a labeled Draft export for native conversion. The
canonical `cowork-v1.28` target composes only the supported manifest subset
with supplied app identity and approved publisher URLs. No placeholders or
future repository URLs are generated.

Remote connector support preserves real tool metadata, including titles,
multiline descriptions, nullable schemas and default annotations. Canonical
remote connectors require an included `mcpToolDescription.file`. The source
export deliberately rejects remote declarations it cannot preserve
losslessly; reuse a verified existing native connection or use canonical
packaging with actual setup metadata instead.

The optional Microsoft Learn snapshot is real, public and provenance-backed.
It is not a required Creator connection, proof of Cowork availability, or
approved publisher/legal metadata for this project.

## Evidence and continuation

[Native status](docs/native-status.json) records facts per version/step.
[Native output inspection](docs/native-output-inspection.md) records the
unchanged native-generated report plugin's local result (4 included,
1 excluded, 27.78) and its nonblocking deep-invalid-JSON limitation. That
local result is not an independent native invocation.

The new bounded JSON pattern handles deep-invalid input explicitly. The
original native artifact was not patched.

Private session identifiers and local native evidence files are not published.
Public metadata examples contain only public Microsoft Learn definitions
and provenance; process fixtures are synthetic.

The optional developer video producer used already installed encoding/image
tools only to create synthetic test input; it is not shipped as runtime
logic. End-user and extension guidance are in `docs\user-guide.md` and
`docs\extensions.md`. Native install, invocation, connection, broader media
and scheduling exercises must be recorded separately when access returns.
