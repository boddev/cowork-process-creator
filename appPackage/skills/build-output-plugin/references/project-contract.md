# Creator project contract v1

This is a small authoring-file contract, not a workflow execution engine.
All documents use UTF-8 JSON, `format_version: 1`, and the same kebab-case
`project_id`. Unknown fields, duplicate keys, non-finite numbers, excessive
nesting and unsafe paths fail explicitly. Package paths below use ZIP-style
slashes; native filesystem arguments use the actual host's path syntax.

## Files and fields

`inputs.json` has `format_version`, `project_id`, and `sources`.
Each source has `id`, `name`, `kind`, `order`, `sha256`, `availability`.
Kinds: `procedure`, `video`, `screenshot`, `reference`, `runtime-example`.
Availability: `attached`, `recorded` (historical metadata/notes, not a live
attachment), or `missing`. `order` is a positive unique ordinal
for screenshots, otherwise null. `sha256` is an actually obtained lowercase
64-character hash, or null if unavailable. Do not fabricate it.

`observations.json` has `format_version`, `project_id`, `items`, `questions`.
An item has `id`, `source_id`, `source_sha256`, `kind`, `text`, `locator`,
`confidence`. Kind is `observed`, `documented` or `inferred`; confidence is
0 through 1 and is independent of support status. Locator has `label`,
`frame_ordinal`, `seconds`; the last two are null unless actually available
for a video observation. A question has `id`, `text`, `evidence_ids`.
Source hashes must correspond; changing evidence invalidates old observations.

`workflow-blueprint.json` has `format_version`, `project_id`, `revision`,
`status`, `title`, `purpose`, `evidence_sha256`, `invocation_mode`, `invocation_prompt`, `inputs`,
`outputs`, `steps`, `constants`, `bindings`, `evaluation_cases`.
Revision is a positive integer. Status is `draft` or `confirmed`.
Use the current `evidence_sha256` returned by check when confirming evidence.
Changed source identifiers, hashes, ordering or observation content invalidate
the old blueprint support; mere attached/recorded access state does not.
Invocation mode is `manual` or `native-schedule`; a prompt does not configure
a schedule or grant permissions.

- Input: `id`, `type`, `required`, `description`, `default`, `default_evidence`.
  Types are `file`, `string`, `integer`, `decimal`, `date`, `boolean`.
  Null means no default. Any non-null default needs evidence and correct type.
- Output: `id`, `description`.
- Step: `id`, `action`, `depends_on`, `consumes`, `produces`, `capability`,
  `connection_id`, `tool_name`, `effect`, `approval`, `on_ambiguous_result`,
  `evidence_ids`, `decision_id`, `condition`, `repeat`.
  Consumes are `input:ID` or `output:ID`; produces are declared output IDs.
  Dependencies form a DAG and include every consumed output's producer.
  Effect: `read`, `local-write`, `business-write`. Approval: `none` or
  `native-each-run`. Ambiguous result: `stop` or `inspect-before-retry`.
  A business write needs a current user-confirmed authoring decision AND
  native-each-run approval; one does not replace the other.
- Condition is null or `{expression, evidence_ids}`. This is explained
  semantic logic, not an expression language that the toolkit executes.
- Repeat is null or `{input_id, max_items, stop_when, evidence_ids}`.
  A declared repeat is bounded (1-10000 items) and references a real input.
- Constant: `id`, `value`, `classification`, `input_id`, `evidence_ids`, `reason`.
  Classification: `parameter`, `derived`, `constant`, `unknown`. Parameter
  classification references a declared input. Unknown values block readiness.
- Binding: `step_id`, `skill`, `files`, `test_ids`. Files are actual candidate
  package paths within that skill, not Creator paths. Every step is bound once.
- Evaluation case: `id`, `description`, `negative`, `expected`. Include changed
  inputs and meaningful rejection cases, not only the demonstrated sample.

`decisions.json` has `format_version`, `project_id`, `blueprint_revision`,
`blueprint_sha256`, `items`. The hash is obtained from the actual blueprint
file bytes. Items have `id`, `question_id`, `answer`, `outcome`, `source`.
Outcome is `confirmed` or `rejected`; source must be `user`. An agent must not
invent a user answer. Revision/hash mismatches make answers stale. The ledger
records authoring decisions, never future native account/approval authority.

`host-profile.json` has `format_version`, `project_id`, `context`,
`capabilities`, `connections`. Context is `native-observed`,
`offline-synthetic`, or `unverified`. A synthetic profile is never native proof.
Capabilities have `id`, `status`, `evidence`. IDs are conceptual categories,
NOT callable tool names: `files.read`, `files.write`, `python.stdlib`,
`media.images`, `media.video-frames`, `documents.edit`, `browser.native`,
`business.tool`, `schedule.native`, `desktop.arbitrary`.
Status: `available`, `unverified`, `unsupported`; non-unverified claims require
actual supporting evidence, scoped to this host and task.

Connection entries have `id`, `mode`, `status`, `native_id`, `tools`,
`provenance`, `availability_evidence`. `id` is a local alias, not an invented registration ID.
Mode is `existing-native` or `packaged-remote`; status is `available`,
`needs-setup`, `unverified`, `unsupported`. `native_id` is a real exposed
identifier or null if none is exposed. Tools contain real `name`,
`description`, `inputSchema` metadata. Provenance has `kind`
(`user-supplied` or `native-discovery`) and `reference`.
These records cannot authenticate, provision a server or prove permissions.
An available connection also needs nonempty actual `availability_evidence`;
knowing a public URL/tool schema alone does not prove native availability.

`candidate` is a source folder containing `plugin-spec.json`, `skills` and
optionally `tools`. The emitted source format is documented in
`references/target-rules.md`. Cowork authors the business instructions and
code. The toolkit checks and packages them, rather than interpreting steps.

`evaluation-results.json`, when present, has `format_version`, `project_id`,
`blueprint_revision`, `blueprint_sha256`, `candidate_sha256`, `environment`, `cases`.
Environment is `local` or `native`. Cases have `id`, `status`, `evidence`;
status is `passed`, `failed`, or `not-run`. Use the actual candidate
fingerprint from the check command. A changed source/revision invalidates the
record. Claimed case results are records, not cryptographic proof of execution.

`build-state.json` has `format_version`, `project_id`, `blueprint_revision`,
`phase`. Phases: `intake`, `observation`, `design`, `generation`, `review`,
`packaged`. It is a conversational checkpoint, not a job queue or approval gate.

## Toolkit commands

Locate `scripts/creator_project.py` in THIS build skill's resources. Its
siblings are packaged in this same directory; no cross-skill imports are used.

- `init --project PATH --id ID --title TITLE --purpose PURPOSE`: create a new
  draft skeleton; never overwrite an existing project.
- `check --project PATH [--report NEW_JSON_PATH]`: validate structure and
  compute coverage, blockers, blueprint hash and candidate fingerprint.
  Missing capabilities, unanswered questions, stale evaluations or drafts
  stay explicit; they never silently become supported.
- `assemble --plan JSON_PATH --output NEW_CANDIDATE_DIRECTORY`: materialize
  generated skill text/resources. The plan has `format_version: 1`, `plugin`
  (the plugin specification), `skills`, `tools`. A skill has `name`,
  `description`, `body`, `companions`; companions have `path`, `content`.
  Tool files have `path`, `content` (JSON text). No downloads or installations.
- `build --project PATH --output NEW_ZIP --report NEW_JSON --target
  cowork-v1.28 --metadata APPROVED_JSON`: require coherent
  evidence/coverage/evaluations, then invoke the bundled package builder.
  Microsoft publishing metadata is mandatory. No alternative manifest target
  is supported. Synthetic profiles remain Draft and do not inherit old
  installation claims; missing metadata allows a source checkpoint only.
- `checkpoint --project PATH --output NEW_ZIP`: export a hash-inventoried
  creation-source bundle, excluding raw attachments and publishing secrets.
- `resume --bundle ZIP --output NEW_PROJECT_DIRECTORY`: verify the complete
  archive inventory/hashes/paths and create a new directory. Reattach missing
  evidence as needed; this does not restore access, sign-ins or permissions.
- `merge --base ZIP --current PROJECT --proposed PROJECT --output NEW_PROJECT`:
  conservative file-level three-way correction. The proposal advances the
  base revision once. Different concurrent changes to the same file produce
  conflicts and no output project. Original trees are never changed.

The low-level `scripts/creator_builder.py` retains `probe`, `validate`,
and `build`. Its source-only validation cannot substitute for project-level
evidence/coverage checks. All reports distinguish Draft/Package built from
actual host installation, independent invocation and scheduled execution.

## Resume and correction details

Resume and successful three-way merge create a new project without altering
the originals. Prior host/input/build/evaluation/coverage JSON records are
preserved byte-for-byte under `history` by content hash. Live host availability
is reset to unverified, attached source labels become recorded, old evaluation
results are archived rather than inherited, and the phase returns to review.
Recheck current native capabilities and refresh evaluations before packaging.
Historical notes may be reused for unchanged evidence; uncertain or changed
spans require reattachment and actual observation, not invented access.
