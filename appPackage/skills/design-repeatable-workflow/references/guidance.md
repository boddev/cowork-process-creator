# Repeatable workflow design guidance

Use this checklist while Cowork designs the process. The exact JSON shapes
and checks belong to `build-output-plugin`; this reference does not define
an alternative schema or expression interpreter.

## Start with outcome and scope

Describe the reusable business result before translating the demonstration.
A recording of spreadsheet clicks might mean "filter qualifying records,
calculate totals and create a report." A document review might mean
"evaluate each supplied policy criterion, cite evidence and flag unresolved
items." Neither needs a custom UI runner.

Separate essential behavior from incidental navigation. A proposed native
substitution is acceptable only if it preserves inputs, outputs, material
rules, validations, notifications and approvals. If that is uncertain,
ask a targeted question and retain the original step in coverage.

## Generalize values intentionally

Declare only the contract's input types: `file`, `string`, `integer`,
`decimal`, `date`, `boolean`. For structured records, declare the runtime
file and explain its data contract in the output instructions/helper;
do not invent an unsupported blueprint object or array type.

| Classification | Design action |
|---|---|
| `parameter` | Reference a declared input; use a justified typed default or no default |
| `derived` | Explain the evidence-backed calculation from runtime data |
| `constant` | Record why this value is genuinely invariant and cite evidence |
| `unknown` | Ask if material; retain a readiness blocker until resolved |

Potentially variable values include filenames, reporting periods, category
labels, thresholds, row counts, output names, owners and destination folders.
Do not turn an observed September date into a permanent schedule parameter.
Do not assume the demonstration's three rows limit future input.

For non-null defaults use the canonical `default_evidence` field and correct
type. Explicitly consider rounding, timezone/date interpretation, duplicate
records, blank values, zero values and invalid types. These business choices
are not appropriately resolved by silent parsing defaults.

## Connect data flow and control flow

Declare each expected output and which step produces it. Step consumption
uses `input:ID` or `output:ID`; dependencies include every producer whose
output is consumed. The resulting dependency graph must be acyclic.

Use semantic actions that Cowork or a generated helper can reproduce.
Blueprint `condition.expression` is explained logic, not code executed by
the toolkit. Give condition evidence, distinguish documented versus
observed branches, and ask about inferred consequential rules.

For `repeat`:

1. Reference a real declared `input_id`.
2. Explain the collection represented by that input.
3. Provide `max_items` in the contract's 1-10000 range.
4. Explain `stop_when` and cite its evidence.
5. Define empty input, cap reached and per-item failure behavior.

Do not infer a business maximum merely from a technical bound. Ask when
stopping early would change the outcome. Bounded authoring data is not a
durable scheduler, retry service or general-purpose workflow engine.

## Preserve effects and uncertainty

Classify effects faithfully: `read`, `local-write`, `business-write`.
Creating a local report is not the same as sending it to colleagues or
updating a business record. Do not hide a consequential step under a
read-only label to pass a check.

A business write needs both a current actual user-confirmed authoring
decision and `approval: native-each-run`. Authoring confirmation documents
intent; it grants no later account authority.

Set `on_ambiguous_result` to `stop` or `inspect-before-retry`. Inspect only
through genuinely available native facilities. If an operation may have
completed and its result cannot be established, stop rather than blindly
replay. Do not promise exactly-once effects, atomic shared-file locks or
approval inheritance across conversations.

## Freeze meaningful decisions against real source

Work in a draft while assembling the blueprint, bindings and cases.
Obtain the current evidence fingerprint from the build skill's `check`.
Present the material proposed behavior for actual user confirmation.

Before recording final confirmation, stabilize the exact revision to which
the answers apply, including step bindings and evaluation declarations.
Use the real blueprint byte hash from `check`, not a hash of a summary.
Record actual user answer text, outcome and question reference using the
canonical decision fields. Do not invent `source: user`, interpret silence
as approval, or treat an agent's synthetic fixture answer as a real one.

If the blueprint changes, even its file bytes, old hash-bound decisions can
be stale. Recheck and resolve the changed proposal with the user instead
of automatically retagging old answers. A rejected decision should lead to
an explicit revised proposal or a blocked scope, not an assumed replacement.

`status: confirmed` expresses the confirmed blueprint, not native runtime
readiness. Keep host limitations, unresolved questions and untested behavior
visible independently.

## Design useful evaluations and bindings

Cover more than the demonstrated sample:

- file aggregation with changed periods, values, record count and order;
- document/checklist review with a missing criterion and conflicting text;
- a condition not taken in the demonstration;
- no qualifying data, boundary thresholds and duplicate identifiers;
- malformed/deeply nested input and unavailable output destinations;
- missing native capability or connection;
- an uncertain business effect that must not be replayed.

Each `evaluation_cases` item declares an ID, description, negative flag and
expected outcome. It is not an execution result. Bind each step exactly
once to its actual output skill/files and declared test IDs as generation
materializes. File references are candidate package paths, never Creator
resource locations.

Use `manual` invocation unless actual support justifies `native-schedule`
and the workflow fits the native approval model. Include all needed
parameters and runtime files; an invocation prompt alone is not scheduling.

## Scope partial outcomes without disguising them

Generation may proceed for useful supported portions, but preserve the full
requested workflow and explain unsupported portions. Do not remove a
required business write, lower an approval requirement, or relabel an
unknown constant simply to obtain a build.

Route changes through `review-output-plugin` and the build skill's
checkpoint/merge path. Export authored source and blockers when material
issues remain. That is a Draft, not a failed native installation or a ready
replacement for the missing process.
