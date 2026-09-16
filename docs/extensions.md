# Extending the Process Creator

Extend the Creator with reviewed, packaged references, patterns, helpers and
evaluation cases. Do not add a service or a runtime installation step.
This guide is for maintainers; end users need only Cowork and the resources
shipped in the Creator or generated output.

The v0.3.0 source requires native Microsoft Cowork v1.28 output. New instructions,
fixtures and local checks do not establish native installation, invocation,
video support, business access or scheduling.

## Preserve the architecture boundary

Cowork remains the evidence reader, reasoning engine, execution host,
native tool surface and file interface. Bundled deterministic code checks
and packages authored files; it is not a general workflow execution engine.

An extension must not require:

- a Creator backend/API or new MCP authoring server;
- Azure infrastructure, an external model/media/OCR/transcription API;
- a browser/desktop runner, device agent or custom execution host;
- a database, queue, gateway, daemon or external scheduler;
- wiqd, ATK, Python, FFmpeg, Playwright or package installation by end users;
- remote downloads, auth/EULA/account changes or production data for a
  baseline file-only workflow.

Developer tools used before distribution must not become runtime
prerequisites. If an extension cannot run using existing native facilities
and supported bundled/generated code, describe the limitation or narrow it.

## Choose the smallest extension

| Extension | Appropriate content | Required review |
|---|---|---|
| Domain reference | Terminology, confirmed rule patterns, clarification questions | Provenance, ambiguity, privacy and relevance |
| Generation pattern | Focused report, review/checklist or supported native task design | Parameters, effects, stopping rules and independence |
| Deterministic helper | Bounded parsing, exact calculation, normalization or formatting | Runtime compatibility, imports, precise errors and held-out cases |
| Native capability mapping | Actual supported tools, existing metadata and setup limits | Native evidence, provenance and non-invented identifiers |
| Evaluation pack | Synthetic procedures/demonstrations, expected observations and negative cases | Honest fixture availability, modality and result provenance |

Keep a compact human-readable inventory with component identity/version,
use cases, native requirements, owned resources and evaluation cases in a
packaged reference when useful. This is documentation, not a new runtime
registry or permission file. Do not invent extra fields in the canonical
project or plugin specification to host it.

The running Creator does not download arbitrary extensions, execute code
suggested by attachments or rewrite its trusted instructions without
review. Ship a reviewed source/package revision.

## Put resources in their owning skill

The eight Creator skill names are:

1. `create-process-plugin`
2. `read-process-evidence`
3. `design-repeatable-workflow`
4. `map-native-capabilities`
5. `author-output-skills`
6. `author-deterministic-helpers`
7. `build-output-plugin`
8. `review-output-plugin`

Preserve existing identities when improving a skill. Add another skill only
for a genuinely reusable task that needs its own trigger.

Each skill owns its `SKILL.md`, references, assets and scripts. Keep every
runtime companion packaged with that owner. Other skills route to it **by
name**, not by filesystem traversal or imports across skill folders.

The builder belongs entirely to `build-output-plugin`: its own
`creator_builder.py`, `creator_project.py` and `project_contracts.py` are
sibling modules in that skill's scripts directory. Same-skill sibling
imports are supported; cross-skill installation paths are not.

The safe JSON pattern belongs to `author-deterministic-helpers` as its
`assets\safe_json.py`. When generated output needs it, copy/adapt the small
needed module into that output skill's own resources. The output must not
import the Creator's installed copy.

Locate resources through actual native listings rather than hardcoded
developer or install paths. Use host-correct filesystem paths and the
contract's ZIP-style package paths in JSON. Do not assume the Windows
development checkout is the native Cowork runtime.

## Keep skill instructions focused

Use progressive disclosure:

1. A short, useful trigger description.
2. A nonempty focused body under 500 lines.
3. Deeper rules in actual owned references, loaded when needed.

Frontmatter has exactly four lines: opening `---`, `name: exact-kebab-name`,
`description: JSON-QUOTED-SINGLE-LINE-STRING`, closing `---`.
Use no extra frontmatter keys. Names are 1-64 characters and match folders;
descriptions are 1-1024 characters. Preserve JSON quoting for escaping
rather than ad hoc YAML multiline syntax.

Teach transferable methods rather than one fixture's answer. Parameters,
typed defaults, conditions, bounded repetition, inputs, outputs, effects and
stopping rules should be explicit. Do not generate one skill per click.
Keep a sequential checkpointed authoring path possible without a required
parallel/subagent runtime.

For the complete exact authoring file/CLI contract, maintain
`appPackage\skills\build-output-plugin\references\project-contract.md`.
For the emitted candidate/manifest subset, maintain the owning build skill's
`references\target-rules.md`. Changes to those build-skill-owned contracts need
coordinated implementation and tests, not documentation-only guessed fields.

## Design robust code patterns

Use small standard-library helpers where the actual native runtime supports
them. State input/output contracts and bound reads, nesting, collection
sizes and iteration before processing untrusted data.

For JSON handle malformed UTF-8/JSON, duplicate keys, non-finite or extreme
numbers, parser recursion limits and domain type errors precisely. A depth
check after parsing alone does not handle parser recursion failure. Validate
domain schema and numeric finiteness in addition to reusing a parser pattern.

Use supplied parameters and domain-appropriate exact arithmetic. Avoid
hardcoded demonstration values, blanket exception catches, silent defaults,
arbitrary expression evaluation and success-shaped failure output. Protect
existing files; clean up only partial output created by the invocation.

Do not add runtime installation, network clients, secret-reading code,
service launchers, browser/desktop automation or general scheduling and
execution machinery. Business operations remain native governed tools with
actual metadata and per-run approvals.

The earlier native output's uncaught `RecursionError` on deeply nested
invalid JSON is a specific regression requirement. The new pattern should
demonstrate bounded, useful failure behavior rather than treating any
nonzero exit as sufficient. No code pattern is automatically safe merely
because it is bundled; review it and exercise applicable cases.

## Validate the extension and its integration

Use the repository's existing targeted tests and bundled validators; do not
introduce an evaluation service, new test runtime or browser viewer as a
product dependency. Local engineering checks are allowed in the provisional
phase, with synthetic data and repository-local scratch files.

1. **Structural checks:** exact frontmatter, matching names, existing owned
   references, allowed companion types, safe paths and package limits.
2. **Behavioral checks:** existing relevant builder/project/helper tests
   plus meaningful new cases when code changes require them. Check held-out
   inputs, rejection diagnostics and unchanged unrelated files.
3. **Project integration:** use `creator_project.py check` and the exact
   assembly/project build contract. Do not bypass a failed coverage check
   with low-level source-only packaging.
4. **Correction/resume:** check current source hashes, stale decisions and
   evaluations, verified archive inventory, revision advancement and
   file-level conflict preservation.
5. **Dependency audit:** no new services/runtimes, cross-skill imports,
   unbundled resources, raw media, secrets or Creator runtime dependencies
   in generated output.
6. **Native gates:** record what remains unrun. Only separate authorized
   target-host observation can establish installed resources, native helper
   execution, media understanding, independent output or later scheduling.

Native Microsoft build metadata must be supplied and approved. Do not use
test publisher/URL/registration values as shipping metadata. Only a root
M365 v1.28 `manifest.json` is accepted for plugin output; no Claude-compatible
fallback is generated. Keep missing metadata or semantic coverage as a Draft
source checkpoint, and do not remove required bindings to make packaging pass.

The toolkit checks the specific source/manifest subset it emits. Do not
advertise full Microsoft schema coverage, sandboxing, transactional workflow
execution, global locks or exactly-once business writes.

### Preserve canonical freshness and history semantics

Defer to the build skill's current project contract, not an older example
or a locally invented equivalent schema:

- Obtain blueprint `evidence_sha256` from `check`. Source identifiers,
  hashes, ordering and observations affect support; an access-only change
  between `attached` and `recorded` does not turn unchanged facts stale.
- Actual `evaluation-results.json` records include `blueprint_revision`,
  `blueprint_sha256` and `candidate_sha256`. Recheck changed source and
  refresh applicable runs; do not copy new hashes onto old pass claims.
- Keep tool metadata `provenance` separate from actual target-host
  `availability_evidence`. Supplied real public MCP metadata is not a
  native connection observation, authentication or permission.
- Resume/merge preserve previous host/input/build/evaluation/coverage
  record bytes unchanged under content-hashed `history`. They reset live
  capability/connection availability to unverified, change `attached` to
  `recorded`, archive evaluations and return the project to review.

Preserve usable historical notes without claiming live source reattachment.
Ask for missing/changed/uncertain evidence when actual observation is needed.
Recheck host availability and refresh evaluations before packaging even if
the unchanged authored notes remain valid. Keep the original historical
record bytes rather than normalizing or rewriting them in an extension.

## Resource and complexity limits

| Scope | Limit |
|---|---|
| Plugin | At most 20 skills and 10 connectors |
| Each skill | At most 20 companions |
| Each companion | At most 5 MB |
| Companion aggregate per skill | At most 10 MB |

Count every packaged reference, asset, helper and sibling module. Also obey
the builder's conservative byte ceilings and supported file-type subset.
Do not confuse standalone-skill archive guidance or attachment limits with
the complete plugin's constraints. Check the pinned target rules before
relying on a platform limit.

Reduce duplication or split into independent outputs when necessary.
Moving dependencies outside the owning skill, downloading them later, or
adding a service does not satisfy these limits.

## Add evaluation prompts without fabricating results

`evals\creator-prompts.json` is a proposed varied prompt corpus, not an
execution report. Its fixture requirements describe what an evaluator must
supply; an empty file list is not evidence that attachments were inspected.
All new cases are unrun until actual evaluation evidence exists.

Include file-only aggregation, document/checklist review, contradictory
evidence, real-but-unavailable connections, unsupported desktop work,
missing runtime, deep invalid JSON, corrections preserving user edits and
resume with changed evidence. Keep genuinely changed held-out values and
negative cases, not renamed copies of one demonstration.

Use synthetic inputs and human-reviewed observation references. Keep
video-only evaluations separate from screenshot evaluations. If native
frame extraction is used, record the actual inspected subset and reliable
locators; never equate extracted frames with visually reviewed frames.

Record actual evaluation results only in the canonical hash/revision-bound
project record with `environment: local` or `native`, and honest case states.
Do not open native UI, an evaluation viewer, publish, call remote business
systems or claim a Cowork benchmark in this offline phase.

## Release and handoff conservatively

Ship changed resources as a new candidate version; preserve v0.1.0, v0.1.1
and actual-native proof artifacts unchanged. Export source/resume bundles
without raw attachments or publishing secrets by default.

Review the build target, version, dependencies, provenance and gaps. Use the
separate labels Draft, Package built, Installed, Manually exercised and
Schedule exercised. No new candidate inherits older prototype evidence.

The historical Only-you publication remains unknown after the last
`Publishing...` state, with the Creator disabled and no independent invocation.
Only separately authorized native state inspection can resolve it; do not
retry or alter accounts/plugins as an extension-development step.

For the end-user workflow, see [the user guide](user-guide.md).
