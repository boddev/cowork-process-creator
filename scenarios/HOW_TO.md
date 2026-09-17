# Enterprise scenario how-to

This development-only corpus compares independently specified synthetic
business procedures with locally executed Python baselines, then prepares
strictly limited inputs for a future native Creator comparison.
It is not a plugin runtime, external authoring service, or substitute for
running Creator and the installed output independently in Cowork.

**Native work is blocked.** Both approved Computer Use tools and an unlocked,
accessible session must be restored, followed by parent-coordinated
authorization. No browser, private API, cookie/token, shell, CLI skill, or model
run may bypass that gate. The old N00 publication outcome remains unknown;
inspect actual Installed state before retrying it. Repository publication is
separate from native actions and requires a reviewed, sanitized snapshot,
not the private development branch ancestry.

## Read a scenario

The [single-document how-to collection](ALL_SCENARIOS_HOW_TO.md) includes
every complete procedure in one place. Relative command/data paths inside a
chapter refer to that chapter's explicitly named original scenario directory.

Run every existing Creator, shared-tooling and scenario-local unittest suite
from the repository with `python -B scenarios\run_tests.py`. The opt-in actual
encoder smoke checks additionally require `SCENARIO_MEDIA_SMOKE=1` and the
already installed developer encoder/Pillow; no runtime installation is performed.
See [the validation summary](validation-summary.json) for actual run counts and
the distinction between local corpus completion and blocked native work.

The [machine-readable catalog](catalog.json) and
[validation report](VALIDATION_REPORT.md) enumerate only integrated, implemented
scenarios. Each sector's `HOW_TO.md` is its complete standalone business
procedure, including mock input/output schemas, research, sample policy,
steps, exceptions, and human-review boundaries. The shared
[scenario contract](SCENARIO_CONTRACT.md) defines exact interfaces.

All artifacts remain in root `scenarios`, including generated baseline outputs,
traces, cases, evidence, staging, and actual baseline videos. Root `output`
is reserved for actual native exports and their explicit native status.
Unit-test fixtures never count toward the required 15 scenarios.

## Real-application financial-services pilot

The [SEC filing-to-Excel pilot](financial-services/_recordings/sec-filing-to-excel/HOW_TO.md)
uses actual browser and desktop Excel recordings rather than the synthetic trace renderer
below. The [3:18 video](financial-services/_recordings/sec-filing-to-excel/demo/workflow.webm)
shows a real SEC download, source-table copy/paste, twelve numeric inputs, twenty-five
live formulas, source-scope review and a local save. Its
[viewer](financial-services/_recordings/sec-filing-to-excel/index.html) provides chapters,
captions, provenance and the blank/completed workbooks.

It is an edited, agent-driven UI demonstration of work to automate. It does not generate,
install or invoke a native Cowork plugin. `_recordings` uses the existing corpus exclusion
rule; it neither replaces the three financial-services baselines nor adds a sixteenth case.
Its tests are included separately by `run_tests.py`. Its recording/editor dependencies
are developer-only, not baseline or end-user runtime dependencies.

## Local baseline run

Use the existing developer Python 3.11+ installation with its standard library.
The corpus is exercised on Windows Python 3.13.14; it does not inherit native
execution claims from the older Creator proof or promise a tested 3.10 runtime.
No Creator, generated plugin, live connection, backend, package download,
database, or external service is needed. These commands run from the repository
root in the isolated worktree, never the main checkout.

```powershell
python -B -m scenarios list
python -B -m scenarios validate --all --full
python -B -m scenarios run --all --replace-generated
```

For one case, use its scenario ID from the catalog:

```powershell
python -B -m scenarios run --scenario <id> --case demo --replace-generated
```

The runner executes only trusted sector-authored `baseline.py` processes.
Static import checks reject non-stdlib, networking, dynamic-code, and obvious
Creator/oracle dependencies; they are not a sandbox. Review local baseline code
before running it. Never run an imported/downloaded native plugin blindly.

Goldens are independent author derivations, not baseline output copies.
Before the first run, the runner creates `validation/golden-lock.json`,
fingerprinting every case's input and expected bytes plus its derivation.
Inputs, expected files, procedure, rules, baseline source, and shared adapter
are fingerprinted again after execution. Modified protected files fail.
`--replace-generated` can replace generated outputs and evidence, not goldens
or their lock. A legitimate change to locked fixtures requires a separately
documented independent review and intentional lock revision; no automatic
accept-new-goldens command exists.

Every case produces `baseline-output/<case-id>.json`,
`baseline-output/<case-id>.trace.json`, and `validation/<case-id>.json`.
The per-case manifest separates documented rules/steps, actually observed
trace steps, local comparison, and the blocked native stages. Business
rejections exit successfully with an explicit rejected envelope; infrastructure
failures and invalid JSON cannot masquerade as passed negative cases.

Comparison covers the entire common result envelope: object keys, all rows and
artifact content represented in `outputs`, list order, booleans, and exact
decimal strings. Numeric JSON values compare mathematically without tolerance.
Required external artifact content must be represented canonically in
`outputs`; a filename, headline total, or narrative claim is not a complete
oracle for its unmodeled contents.

## Produce a baseline video

The optional media producer needs the existing developer Pillow installation
and an explicitly supplied, already-present encoder. It never installs either
and neither becomes an end-user or plugin runtime requirement.

```powershell
python -B -m scenarios render --all --replace-generated --ffmpeg "<absolute-path-to-existing-encoder>"
```

The producer reruns each DEMO through the real baseline and independent golden
comparison. It renders actual input, validation, join, decision, exception,
and output trace states as readable tables/facts/captions with highlighting.
The result is a 30-90 second silent WebM under `demo/baseline.webm`, labeled
on every frame as a **synthetic baseline execution visualization, not Cowork
or a live business system**. It is not an ERP recording, mouse-action replay,
narrated clip, or proof that Cowork understands the video.

`demo/baseline.media.json` records source/result/trace/golden hashes, the actual
baseline and encoder commands, encoder identity, timeline, frame count,
decoded fidelity, any display shortening, and the video byte hash.
Public records preserve actual command arguments with interpreter/encoder
basenames, scenario-relative inputs and labeled temporary paths, not personal
machine paths. Runtime versions and binary hashes identify the tools actually
used. The video keeps that command record from its original baseline run. A later
baseline rerun may use a different temporary output directory without
invalidating the video if its input, baseline source, golden, result, trace,
and scenario title are unchanged.
The existing cached encoder uses JPEG image2pipe input and VP8/WebM output;
no H.264 or general PNG-input support is assumed.

## Prepare native Creator input, without accessing Cowork

```powershell
python -B -m scenarios stage --all --replace-generated
python -B -m scenarios report --all --full
```

Staging requires current baseline and media evidence, then creates
`validation/creator-input` with exactly five files: `HOW_TO.md`, `workflow.json`,
`connections.json`, `mock-data/demo.json`, and `demo/baseline.webm`.
The file-hash manifest is saved outside that directory at
`validation/creator-staging.json`.

Only these five files may be provided to Creator. Do not attach the scenario
directory, baseline code, shared tools, `scenario.json`, `sources.json`,
private holdouts, negatives, expected outputs, baseline results, validation
answers, or hidden markers. Public research links belong in the procedure.
Mock export metadata declares no live native connections.

Staging does not generate a plugin and does not count as native creation.
Full local reporting requires at least 15 implemented scenarios across
Manufacturing, Health/Life Sciences, Financial Services, Retail, and another
industry, with at least five workflow families. Each has DEMO, two distinct
holdouts, and malformed/contradictory negative coverage. Exact reuse and
structural similarity are reported; business diversity and citation quality
still need author/coordinator review.

## Future authorized native procedure

After the parent confirms both access conditions, inspect the old installation
state before any retry. Enable/run the real Creator through approved native
interaction, providing only staged files. Download the actual generated plugin
under `output/<scenario-id>`; do not replace it with a locally assembled package.
Record creation observations and the exact downloaded byte hash.

The requested output is a **native Microsoft Copilot Cowork M365 v1.28
package**, with a root `manifest.json`, correct icons, `agentSkills` folders
and any required real connector tool descriptors. Do not use
`.claude-plugin/plugin.json`, `devPreview`, or a host-conversion fallback.
Approved publisher/app metadata must be supplied for each package. Missing
metadata is a packaging blocker; source checkpoints are not plugin ZIPs.

Inspect the downloaded ZIP/source read-only before any bounded execution.
Install the exact output plugin in Cowork and record installation separately.
Disable Creator and start a fresh independent task with only the installed
output plugin and each case's input. Withhold baseline code, goldens, and prior
answers. Record invocation observations and all output artifacts independently
for each case, including held-out and negative inputs. Make no live business
changes, clinical decisions, transfers, releases, equipment actions, or writes.

The following local commands inspect and compare already-supplied files;
they do not access Cowork, install plugins, or execute downloaded code:

```powershell
python -B -m scenarios inspect-plugin --artifact output\<id>\<actual-native-file>.zip
python -B -m scenarios import-native --scenario <id> --observation output\<id>\native-observations.json
```

The import descriptor is schema version 1 with `scenario_id`,
`provenance: "operator-declared-native-export"`, `host: "Microsoft Copilot Cowork"`,
`plugin`, `creation`, `installation`, and `invocations`. Exact fields:

| Object | Fields |
|---|---|
| `plugin` | `path` (under `output/<id>`), `sha256` |
| `creation` | `evidence_id`, `plugin_sha256`, `creator_input_manifest_sha256`, `evidence_files` |
| `installation` | distinct `evidence_id`, `creation_evidence_id`, `plugin_sha256`, `evidence_files` |
| Each invocation | `case_id`, distinct `evidence_id`, `installation_evidence_id`, `plugin_sha256`, `input_sha256`, `result_path`, `result_sha256`, `evidence_files`, `independence` |
| Each evidence file | `path` (output-relative), `sha256`; actual nonempty bytes required |
| `independence` | `fresh_task`, `creator_disabled`, `baseline_withheld`, `goldens_withheld`, all explicitly `true` |

Each `result_path` contains the full canonical result envelope, including every
required output artifact's semantic content. The creation staging hash is the
hash of the actual `validation/creator-staging.json`. All plugin/input/result
hashes are immutable bindings; the importer never repairs them.

The receipt at `output/<id>/comparison.json` separates operator declarations
from locally observed file bytes and full semantic comparisons. All supplied
payloads can match while required cases are still missing. It reports both
facts separately. Neither matching files, a supplied status string, nor a
claimed evidence ID proves native creation/install/invocation. The importer
does not upgrade native lifecycle states or `native_pass`; actual host
observations still require the authorized operator's independent review.

### Native prompt guidance (not executed while blocked)

Use this bounded creation instruction only after the native access gate opens,
alongside the five allowlisted files, never the evaluation corpus:

```text
Create a reusable output plugin for the attached HOW_TO procedure and DEMO.
Target Microsoft Copilot Cowork using its native M365 Unified App Manifest
v1.28: manifest.json at the ZIP root, icons, agentSkills folders and any
required real connector mcpToolDescription.file. Do not create a Claude
Cowork/.claude-plugin source archive or rely on conversion. Use the supplied
approved publisher/app metadata; if absent, return an explicit packaging
blocker and editable source instead of an alternative-format plugin.
Use workflow.json as documented steps, not as an external runtime engine.
Treat the video as a synthetic visualization of an actually executed local
baseline, not a recording of Cowork or a live business system. Keep all
sample policies and no-live-action boundaries explicit.

The plugin must process new inputs conforming to the HOW_TO input contract,
not reproduce hard-coded DEMO answers. Emit the complete JSON result envelope:
schema_version (1), status, outputs (object), and exceptions (objects containing
code and message plus documented business fields). Include every required
business output key, row, artifact content, decimal format, and stable array
order exactly as specified by HOW_TO. Include a human-readable report only
as an addition, not as a substitute for the structured result.

Do not infer native connections from mock exports, invent availability, install
dependencies, use a backend, or take live business actions. Do not request
baseline implementations, private evaluation inputs, goldens, or hidden
markers. Report missing capabilities explicitly. Source assembly alone is
not evidence that a plugin was installed or independently invoked.
```

For each independent invocation after the actual output plugin is installed,
disable Creator, start a fresh task, attach only that case's synthetic input,
and adapt this instruction with the real installed plugin name:

```text
Use the installed output plugin for its documented procedure on the attached
synthetic input. Produce the complete documented JSON result, including all
business fields, ordered rows, exact decimal values, and explicit exceptions.
Do not call Creator, consult a baseline implementation, fetch goldens, reuse
prior task answers, or take live business actions. If the procedure cannot
finish within the existing native capabilities, report the blocker rather
than fabricating completion or substituting a different execution channel.
```

## Developer checks and boundaries

```powershell
python -B -m unittest discover -s scenarios\tests -v
```

Core checks use the existing standard-library unittest runner. Optional media
smoke checks use only already-available developer imaging/encoding tools.
No new lint/build/test framework is installed.

To include actual repeated encoding/decoding and the baseline-to-video-to-staging
CLI round trip, enable the opt-in checks in the same PowerShell process:

```powershell
$env:SCENARIO_MEDIA_SMOKE = "1"
python -B -m unittest discover -s scenarios\tests -v
```

CLI exit code 0 means that command's local operation succeeded, not native
validation. Code 1 means local comparison/coverage is incomplete or failed;
code 2 means invalid input, stale evidence, or an operational error.
`native_complete` and `native_pass` remain explicitly false while the native
gate is blocked, including on successful read-only imports.

The root `appPackage`, `dist/v0.2.1/creator.zip`, historical proofs, native access,
authentication, EULAs, remote branches/releases, and business systems are
outside this tooling's write scope. `scenarios/**` and `output/**` disable
automatic Git newline conversion so committed evidence retains its exact bytes.
