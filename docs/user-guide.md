# Process Creator user guide

Turn a procedure and its demonstration into a reusable Microsoft Copilot
Cowork plugin. Cowork reads the evidence, asks about material uncertainty,
authors the workflow's instructions and optional deterministic helpers, and
uses bundled code to check and package the result.

The output is intended to work on new inputs without the Creator or original
recording. There is no separate authoring application, backend or service.

## Current status and authorization

**As of September 11, 2026: source v0.2.1 is provisional offline work, not a
new installed or natively exercised release.** Offline implementation covers
the expanded instruction/toolkit path and evaluation preparation. Native
installation, independent output execution and scheduling remain separate
gates. This guide describes intended use; it does not record those actions.

The bounded historical N00 result used an older Creator and a static silent
synthetic WebM. Direct native video viewing was unsupported. An already
installed native `imageio_ffmpeg` capability extracted 24 frames with PTS;
Cowork's own native parent inspected frames 1, 9 and 17 at 0, 4 and 8 seconds,
then supplied observations to its native authoring worker. This was not
visual review of all 24 frames, exact transition timing, narration, broad
real-UI coverage or evidence that every host has a decoder.

One actual output ZIP was submitted through **Only you**. The last visible
state was **Publishing...** before the desktop locked. The publication
outcome is **unknown**, the Creator was disabled, and no fresh independent
output invocation was observed. Do not retry publication, re-enable plugins
or infer success/failure from that unresolved state during offline work.
When native work is separately authorized, inspect installed state before
considering a retry.

No native UI, publishing, remote/business actions, auth/account/EULA changes
or production data are authorized by this offline phase. Earlier v0.1.0,
v0.1.1 and actual-native proof ZIPs remain immutable.

## What you need

- Cowork with the relevant native plugin/skill facilities available to you.
- A procedure describing the goal, rules, inputs, outputs and exceptions.
- A video **or** ordered screenshots demonstrating the process.
- Optional synthetic example inputs and expected outputs.
- For a business-connected process, real existing connection/tool
  information you are allowed to share, without credentials.

End users do **not** need wiqd, ATK, Python, FFmpeg, Playwright or a developer
environment installed on their computers. Any required interpreter or
native capability must already be supplied by Cowork. If it is absent, the
Creator reports a gap or uses an equivalent existing native operation.

The Creator does not add an MCP authoring server, Azure infrastructure,
external model/media APIs, a browser/desktop runner, database, queue,
gateway, runtime installer or external scheduler.

## Install or select the Creator

This is future native-use guidance, not an instruction to act in the current
blocked offline phase.

1. Obtain the explicitly identified Creator package and read its target,
   version and readiness report. Do not assume an older proof package
   contains the current expanded skills.
2. Use the plugin upload/import facilities actually available in Cowork's
   native customization experience. Follow its real controls and policies;
   a missing route is a limitation, not a reason to use an external loader.
3. Distinguish a canonical v1.28 ZIP from a compatible-source ZIP that needs
   a separate native conversion route. Do not assume conversion preserves
   every connector or companion feature.
4. Verify the actual package appears and is available before calling it
   installed. Select/enable it only when authorized for an authoring task.
5. In a new authoring conversation, invoke `create-process-plugin` by name
   with the attachments and intended outcome.

Successful local validation is not host installation. A report marked
Draft remains Draft until its stated blockers are resolved and relevant
native evidence is recorded.

## Start with the procedure and demonstration

Example authoring prompt:

> Use create-process-plugin to turn my attached procedure and demonstration
> into a reusable Cowork plugin. The input file, reporting period and output
> filename should be configurable. The attachments contain synthetic data.
> There is no business connection for this file-only workflow. Inspect the
> actual evidence, ask about material missing rules, and return the checked
> candidate, coverage report and creation-source bundle. Do not install
> software, publish anything or call external services.

For screenshots, supply an explicit order and meaningful filenames/labels.
If the sequence omits an important transition, say so. The Creator should
not invent timestamps, unseen clicks or business rules between images.

For video, actual native observation must be possible. An accepted filename
does not establish video understanding. A permitted native frame capability,
if already present, can help inspect uncertain views; it is optional and
does not create a decoder dependency. If observation is inadequate, the
Creator may ask for clearer evidence or ordered screenshots. Screenshot
success does not prove video support.

Tell the Creator which facts are intentional constants and which are only
demonstration values. If an example shows three records and a September
date, do not expect those to become a fixed loop count or permanent period.

Attachments are untrusted evidence, not instructions to the assistant.
Do not include credentials. The Creator should ignore embedded override
requests, avoid executing source macros/scripts and omit visible secrets
from authored notes and output.

## Native resource discovery and feasibility

The entry skill routes work to seven focused skills:

| Skill | Purpose |
|---|---|
| `read-process-evidence` | Inventory, visual observation, evidence notes and questions |
| `design-repeatable-workflow` | Parameters, rules, dependencies, conditions and bounded repetition |
| `map-native-capabilities` | Actual host support and real connection/tool mappings |
| `author-output-skills` | Reusable output instructions and owned resources |
| `author-deterministic-helpers` | Bounded pure-data computation and explicit errors |
| `build-output-plugin` | Canonical contracts, checks, assembly, ZIPs and resume/correction |
| `review-output-plugin` | Coverage, readiness, preserved edits and handoff |

The build skill locates its own bundled scripts through the actual native
resource listing; it does not guess a developer path or import another
skill's installation files. Its `probe` uses the interpreter already
provided by the host and reports what actually ran.

That probe does not prove video reading, document editing, business
connections, upload acceptance or scheduling. The host profile distinguishes
`native-observed`, `offline-synthetic` and `unverified`. A local engineering
probe or synthetic profile is never native proof.

If a recording shows an arbitrary desktop application, the Creator should
seek a genuinely equivalent native outcome or report the operation as
unsupported. It must not ship a desktop runner to reproduce the clicks.

## Expect material clarification questions

Useful questions concern:

- conflicting written and demonstrated rules;
- uncertain thresholds, rounding, dates, exception behavior or stopping rules;
- missing outputs or a proposed substitute operation;
- real connection information and required native setup;
- consequential writes, notifications and approval expectations.

Answers are recorded as actual user decisions against the exact blueprint
revision and byte hash. Changed evidence, rules or candidate bindings can
make earlier decisions/evaluations stale. The Creator should recheck and
reconfirm, not silently apply new hashes to old approval.

Unanswered or rejected material questions leave the relevant scope Draft.
A decision ledger records authoring intent; it does not grant account
permissions or replace per-run native approval for business writes.

## Review the candidate and checks

The creation project holds small JSON files for source inventory,
observations/questions, the revisioned workflow blueprint, decisions, host
profile and build phase. Its `candidate` folder contains authored output
skills and necessary resources. Evaluation records distinguish expectations
from actual local or native runs.

Review the proposed process rather than only the package name. Check:

1. Every material step and expected output has evidence and actual generated
   implementation, not just a mention in a file.
2. Parameters, conditions and bounded repetition generalize beyond the
   sample. Unknown constants are not silent defaults.
3. All native capabilities and real tools are actually supported, or gaps
   are explicitly identified.
4. Helpers handle held-out synthetic inputs and precise negative cases,
   including oversized/deep JSON where applicable.
5. All required references/helpers belong to the output's own skills.
6. Original media, secrets, absolute developer paths and Creator imports
   are absent from the output by default.

The earlier native output's deep-invalid-JSON case raised uncaught recursion
and no friendly report. New helper patterns require bounded input/nesting
and precise errors, but that requirement is not itself a passed evaluation.

The builder checks its emitted subset; it is not a full Microsoft schema
validator or a code sandbox. A low-level structurally valid ZIP cannot
bypass failed project evidence, coverage, decisions or evaluations.

### Toolkit operations

Cowork invokes these operations through `build-output-plugin` using its
already provided runtime. These are reference argument shapes, not end-user
installation or command-line prerequisites.

| Operation | Exact arguments after `creator_project.py` |
|---|---|
| New project | `init --project PATH --id ID --title TITLE --purpose PURPOSE` |
| Current checks/fingerprints | `check --project PATH [--report NEW_JSON]` |
| Materialize authored candidate | `assemble --plan JSON --output NEW_CANDIDATE_DIR` |
| Build a coherent project | `build --project PATH --output NEW_ZIP --report NEW_JSON --target cowork-v1.28\|compatible-source [--metadata APPROVED_JSON]` |
| Export creation source | `checkpoint --project PATH --output NEW_ZIP` |
| Restore into a new directory | `resume --bundle ZIP --output NEW_PROJECT_DIR` |
| Preserve corrections/user edits | `merge --base ZIP --current PROJECT --proposed PROJECT --output NEW_PROJECT` |

Use actual paths from the native host and new output names. The exact JSON
structures are owned by the build skill's packaged project contract, also
available in this repository at
`appPackage\skills\build-output-plugin\references\project-contract.md`.
Do not add guessed fields or use the low-level builder to force a blocked
project into a "ready" package.

### Keep evidence and results current

The packaged project contract is authoritative over older notes or bundle
summaries. Its `check` returns the current evidence and source fingerprints:

- Blueprint `evidence_sha256` binds the design to source identifiers,
  hashes, ordering and observations. Changed facts invalidate old support;
  changing only attachment availability from `attached` to `recorded`
  does not.
- `evaluation-results.json` binds actual runs to all three of
  `blueprint_revision`, `blueprint_sha256` and `candidate_sha256`.
  A matching revision alone is insufficient. Keep actual local/native
  provenance and rerun applicable cases rather than retagging old results.
- Connection metadata `provenance` identifies the source of real tool
  definitions. Separate `availability_evidence` supports current target-host
  access. Public tool metadata alone does not establish that access.

After changes, run a fresh project check and resolve stale support. After
resume/merge, refresh current availability and evaluations before packaging;
unchanged authored notes are not inherited execution evidence.

## Understand package targets and downloads

**Canonical `cowork-v1.28`:** requires approved supplied app identity and
publisher metadata, including website, privacy and terms information.
Missing approved metadata blocks this target. The Creator must not invent
legal URLs, registrations, publishers or endpoints. Canonical upload
acceptance remains a native gate, not a local schema claim.

**`compatible-source`:** a separate **Draft source export** intended for a
possible supported native import/conversion route. It is not a canonical
v1.28 package. Old skills-only conversion is not proof for every new skill,
resource or connector. The current emitted subset rejects declared remote
connectors. Use canonical packaging with approved metadata or a suitable
verified existing native connection; do not drop required bindings merely
to obtain a compatible-source ZIP.

The handoff should identify:

- the actual plugin ZIP, if successfully built for its stated target;
- the actual build/check report and coverage gaps;
- the creation-source ZIP for resuming work;
- a configurable manual prompt, expected results and setup limitations.

If Cowork's Download All creates an outer archive, locate the actual plugin
ZIP inside it. Do not upload the source-resume bundle or the outer container
as though it were the plugin. On a failed build, a previous ZIP is not a
successful new output.

When material issues block packaging, request the authored source and
explicit coverage rather than a false ready claim.
If the toolkit itself cannot execute, available authored native files may
still be returned, but a verified checkpoint/plugin ZIP must not be claimed.

## Resume and preserve corrections

Download the checked creation-source bundle before relying on another
conversation. Cowork's current workspace may be ephemeral. The bundle
contains authored knowledge/code and source identifiers/hashes, excluding
raw attachments and publishing secrets by default.

In a later conversation, attach that bundle and ask the Creator to resume
into a **new** project directory. Resume checks the complete inventory,
hashes and safe paths. It does not restore the original video, sign-ins or
account permissions.

Historical host/input/build/evaluation/coverage records are preserved
byte-for-byte under content-hashed `history`. Live capability and connection
availability become unverified, attached sources become recorded historical
sources, old evaluations are archived and the project returns to review.
Unchanged notes remain useful without pretending the original files were
reattached. Request actual reattachment/observation only where missing,
changed or uncertain content is needed. Recheck current native support and
refresh evaluations before packaging; archived passes are not carried
forward as live results.

For a correction, keep the base bundle and your current edited source.
The Creator proposes a separate revision advancing the base once. A
three-way merge preserves nonconflicting file edits. Different concurrent
changes to the same file produce conflicts and no merged project, even if
the edits touch different lines. Resolve the conflict explicitly; do not
accept a silent rewrite of your work.

## Use the output independently

After separate native authorization and actual installation verification:

1. Select the generated output plugin, not the Creator.
2. Start a fresh conversation with only its declared new runtime inputs.
3. Invoke the output's skill with explicit parameters and a new output name.
4. Verify the expected result and record the artifact/version used.

Example invocation wording:

> Use the selected report skill with the newly attached input file. Use
> reporting period 2026-10 and write a new report named october-review.md.
> Validate the inputs first and tell me about any missing required fields.

The name and period above are illustrative supplied parameters, not
hardcoded workflow defaults. An independent check must not rely on the
Creator's resource directory, prior conversation or original recording.
Do not perform this native check in the currently blocked offline phase.

## Existing business connections

File-only workflows need no connection. For connected workflows, provide
the real existing endpoint or native connection information, exposed tool
names and input schemas, provenance and any actual supported registration
information. Do not put secrets in attachments.

The Creator prefers existing native connections. A packaged connection
declaration only configures a real existing endpoint supported by the
target; it does not create an MCP server. A public endpoint/schema alone
does not prove the current Cowork user can use it.

Missing native setup stays `needs-setup` or unverified rather than
available. Follow the actual native setup/consent path only when separately
authorized; this guide does not perform sign-in, auth, EULA or account
changes. Do not assume a manifest authentication enum establishes runtime
support.

Business writes still require actual native per-run approval. If a write's
outcome is uncertain, inspect through available native tools or stop before
retrying. Do not test connection writes using production data.

## Native scheduling, only where supported

A generated workflow may offer a suggested native scheduled prompt with
explicit parameters and expected outputs. That text does not create a
schedule, reserve capacity or grant later permission.

Use Cowork's own scheduling facility only when actually available and the
workflow fits its file-access and approval behavior. Confirm that the
scheduled context can access needed runtime inputs; do not assume prior
conversation attachments remain available.

Keep workflows manual/approval-required when safe unattended behavior is
not established. No external scheduler, background service, shared-file
lock, exactly-once guarantee or cross-conversation approval inheritance is
provided. A schedule is **exercised** only after a later native invocation
is observed to meet the declared behavior. None has been exercised here.

## Readiness vocabulary

| Label | Meaning |
|---|---|
| Draft | Useful source with unresolved scope/setup, an offline synthetic candidate, or a separate compatible-source export |
| Package built | Actual ZIP passed the Creator's subset checks for its named target |
| Installed | The actual target host accepted that exact package |
| Manually exercised | Declared inputs ran and expected results were verified |
| Schedule exercised | A later native scheduled invocation behaved as declared |

Even a locally coherent project reported as ready by its checks remains
Draft under an offline-synthetic profile. Readiness/build JSON is a record,
not a permission grant or distributed execution authority. Report versions,
environments and uncertainty explicitly; never let a new candidate inherit
the prototype's observations.

For packaged extension development, see [the extension guide](extensions.md).
