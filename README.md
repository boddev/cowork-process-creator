# Self-contained Cowork Process Creator

**Current source v0.3.0 targets native Microsoft Copilot Cowork packages only.**
Generated plugins require a root M365 v1.28 `manifest.json`, icons and declared
skills/resources. Missing approved publisher metadata blocks packaging;
Claude-compatible manifests and conversion are no longer an output option.
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

## Historical preview, not the current native package

The preserved [v0.2.1 preview release](https://github.com/boddev/cowork-process-creator/releases/tag/v0.2.1)
uses a **Claude-compatible source layout** and relies on Microsoft host
conversion. It is not the native Microsoft manifest package now required.
It remains historical evidence and has not been silently replaced.
No new native release ZIP is available until approved publisher metadata is
supplied. See [Microsoft packaging](docs/MICROSOFT_PACKAGING.md) and the
[user guide](docs/user-guide.md).

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
python -B scripts\build_release.py --metadata-dir .local\publishing
```

With valid supplied metadata, the release builder produces native packages
under `dist\v0.3.0`: `creator.zip`, its build report, release/inventory JSON, and three
distinct synthetic file-workflow examples with output plugins, source/resume
bundles, real local helper outputs, coverage and expected negative cases.
It also carries a clearly separate real-public-MCP metadata example whose
Cowork availability remains unknown. Without the metadata directory, the
command fails explicitly and produces no release directory or fallback ZIP.
It performs no network calls.

Existing differing release directories are not overwritten: bump the version
or pass a new `--output` directory. Original v0.1.0/v0.1.1 and native proof
artifacts remain unchanged. Development commands are not end-user runtime
dependencies.

## Contributed examples

[Restaurant bill splitter](examples/bill-splitter/README.md) adapts a
contributor-generated skill into the existing candidate-and-fixtures layout.
Its current v1.1.0 candidate targets native Microsoft manifest v1.28 only;
packaging is blocked until approved app/publisher metadata is supplied.
The arithmetic helper, workbook layout, procedure and independent fixtures
are preserved. The earlier v1.0.1 ZIP and report are retained unchanged under
the example's `archive` directory, not offered as a current native package.
Native installation, independent invocation and workbook creation remain
unverified. The original recording, workbook and Creator are not runtime
dependencies.

## Enterprise scenarios

The [enterprise corpus](scenarios/HOW_TO.md) includes 15 implemented synthetic
scenarios, 96 independent-golden baseline cases, 15 baseline-trace videos and
15 input-only staging bundles across five directory packs and seven business
industries. Read the [complete how-to collection](scenarios/ALL_SCENARIOS_HOW_TO.md)
and [local evidence catalog](scenarios/catalog.json). These are local baseline
artifacts, not native Creator outputs: no scenario plugin has been generated,
installed or independently invoked in Cowork. Root [output](output/README.md)
contains only the blocked native status.

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

The only package target, `cowork-v1.28`, composes Microsoft's supported
manifest subset with supplied app identity and approved publisher URLs.
No placeholders, guessed legal URLs or alternative host manifests are generated.

Remote connector support preserves real tool metadata, including titles,
multiline descriptions, nullable schemas and default annotations. Canonical
remote connectors require an included `mcpToolDescription.file`. The native
package preserves remote declarations and their actual supplied tool metadata;
reuse a verified existing native connection or provide its real supported
configuration. Missing setup stays visible.

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
