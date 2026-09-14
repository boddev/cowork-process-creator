---
name: design-repeatable-workflow
description: "Generalize process evidence into a reusable, revisioned workflow blueprint. Use to identify configurable inputs, justified constants, semantic steps, dependencies, conditions, bounded repetition, approval needs and targeted questions before generating a Cowork output plugin."
---

# Design a repeatable workflow

Read `references\guidance.md` for design checks. Route to
`build-output-plugin` for the exact project-file contract and current
fingerprints. The blueprint is structured authoring data, not a workflow
language, execution engine, permission grant or distributed job plan.

## Define the reusable outcome

1. Read current `inputs.json`, `observations.json` and any actual user
   decisions. Preserve source IDs and distinguish demonstrated behavior,
   document-only rules and inference.
2. State the process purpose and observable outputs. Describe semantic
   actions rather than fixed click coordinates or one demonstration's path.
3. Draft `workflow-blueprint.json` using the canonical fields, a positive
   `revision` and `status: draft`. Obtain `evidence_sha256` from the build
   skill's current check; do not calculate a substitute format.
4. Declare typed inputs, required runtime files and outputs. Make periods,
   paths, thresholds, categories and destinations configurable when they
   vary. Every non-null default needs evidence and the correct type.
5. Classify demonstrated values as `parameter`, `derived`, `constant` or
   `unknown` in `constants`. A parameter references a declared input;
   consequential unknowns stay blockers, not silent defaults.

## Express steps and control flow

- Give each step a semantic action, consumed inputs/outputs, produced
  outputs and dependencies. Use `input:ID` or `output:ID` consumption
  references and include every consumed output's producer in the DAG.
- Give conditions an explained expression and evidence IDs. This text is
  reasoning for Cowork/generated instructions, not executable expressions
  evaluated by the toolkit.
- Repeat over a declared input with an evidence-backed stop rule and
  `max_items` between 1 and 10000. Do not replay the observed sample count
  or introduce indefinite polling.
- Classify effects as `read`, `local-write` or `business-write`. Preserve
  validations, approvals and notifications in any semantic substitution.
- Set ambiguous-result behavior to `stop` or `inspect-before-retry`.
  Uncertain writes are never blindly replayed.
- Use `map-native-capabilities` for actual capability/connection/tool
  mappings. A conceptual capability ID is not a callable tool name.

Default to a configurable manual invocation. Use `native-schedule` only
with justified native support and a workflow that fits actual approval
constraints. An invocation prompt neither configures a schedule nor grants
permission for later business writes.

## Resolve material decisions, not every detail

Ask concise questions about contradictory rules, uncertain thresholds,
repetition, missing exceptions, consequential effects and proposed
substitutions. Keep their evidence links in the questions record.

Record only actual user answers in `decisions.json`, with `source: user`,
the actual outcome and the exact `blueprint_revision`/`blueprint_sha256`.
Confirm the final revision, including declared bindings and cases, rather
than silently retagging an earlier answer after edits. Rejected or
unanswered material decisions leave the affected scope Draft.

A `business-write` requires a current confirmed authoring decision and
`approval: native-each-run`. The decision ledger cannot replace native
sign-in, account permissions or per-run approval.

## Prepare generation and checks

Declare meaningful `evaluation_cases`: changed inputs, boundary cases,
missing/invalid inputs and expected results. These are expectations, not
passed evaluations. Ensure each step has exactly one binding to an output
skill, actual candidate files and declared test IDs before readiness.

Route to `author-output-skills` and, when useful,
`author-deterministic-helpers`. Iterate with project-level checks as files
and bindings become real. Preserve the complete requested scope in coverage;
do not delete blocked steps merely to make packaging pass.

On corrections, route to `review-output-plugin` and the build skill's
revisioned correction path. Keep originals and user edits intact.
