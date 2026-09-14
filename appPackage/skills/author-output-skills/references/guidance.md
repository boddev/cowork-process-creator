# Output skill authoring guidance

Use this reference for reusable instruction design. Ask `build-output-plugin`
for the canonical candidate/assembly plan and target rules; do not invent a
second source format here.

## Choose task-shaped skills

Small file-only processes often need one skill and one compact helper.
Document review may need only an entry skill and a checklist reference.
A larger workflow can use an entry skill and a few reusable phase skills.
Split for meaningful reuse and focused activation, not every screen/click.

Keep a sequential path viable. Optional native subagent or parallel
facilities must not become required services or hidden orchestration.
If the process exceeds native limits, propose a narrower useful scope or
separate independently usable outputs; do not add a workflow server.

## Use the emitted frontmatter subset

Every output `SKILL.md` has exactly these four frontmatter lines:

```yaml
---
name: review-policy-checklist
description: "Review a supplied document against a confirmed checklist and produce cited findings, missing items and unresolved questions. Use for repeatable policy or procedure reviews with new documents."
---
```

This is an illustrative skill identity, not a preinstalled resource.
Use the real output skill's own name, matching its folder. Names are
1-64 character kebab-case; descriptions are single-line JSON-quoted YAML
strings of 1-1024 characters. Use no unsupported frontmatter keys.

Put the trigger in the description and working instructions in the body.
Keep the body nonempty and under 500 lines. For deeper rules, add an actual
reference within the output skill that owns it and explain when to read it.
Do not cite nonexistent files, another skill's installation path, or a
resource left only in the Creator.

## A focused body should answer these questions

1. **Inputs:** What must the user supply each run? What is optional? Which
   defaults are justified, and how are invalid inputs reported?
2. **Outcome:** Which files or observable results should exist at the end?
3. **Method:** What semantic steps, conditions, dependencies and bounded
   repetition reproduce the confirmed process?
4. **Capabilities:** Which native functions or real existing connection
   tools are required, and what happens when they are unavailable?
5. **Effects:** Which operations are reads, local writes or business writes?
   What approvals and ambiguous-result stops apply?
6. **Verification:** Which expected outputs, counts or invariants can be
   checked without inventing a successful run?
7. **Handoff:** How does a fresh user invoke the process with changed inputs?

Keep parameters visible rather than embedding the demonstration's names,
dates, paths, amounts, destination IDs or sample count. Explain calculation
and validation rules precisely. Code is preferable to approximate arithmetic
when a supplied runtime and deterministic helper fit the task.

## Two reusable patterns

### File-only aggregation

Accept a structured input file, reporting period and new output filename.
Validate the declared schema, select qualifying records using confirmed
rules, apply explicit arithmetic/rounding, and write an ordered report.
Handle no qualifying records, duplicate IDs and malformed data explicitly.

The demonstration is supporting evidence, not runtime input. Held-out cases
should change periods, record counts, values and order. A helper should not
need the original recording to recover a business constant.

### Document review and checklist

Accept a new document and the confirmed criteria. Read material content
through native document facilities; report findings with document locators.
Separate a missing required element from unclear or conflicting evidence.
Preserve the source document unless an explicit output contract requests an
edited copy. Do not fabricate citations or treat a checklist item as passed
when its evidence cannot be read.

Use native editing rather than downloading a document library if the host
already provides the required operation. Missing editing support can still
allow a clearly scoped review report; it cannot prove an edited document
was produced.

## Own every runtime resource

Each output skill packages the references, assets, scripts and sibling
modules it requires. Same-skill sibling imports are supported; cross-skill
filesystem/import assumptions are not. Route another skill by its name.
Resolve actual native resource locations instead of hardcoded paths.

Generated output must not import the Creator's toolkit or fetch its
templates after installation. Copy only the small necessary authored
pattern into the output's own resources and review it as output code.

Respect the limits: 20 skills and 10 connectors per plugin; per skill,
20 companions, at most 5 MB each and 10 MB aggregate. Every helper, module,
reference and asset counts. Use only the file types and source subset
accepted by the build skill; platform limits are not permission to emit
unsupported binary companions.

Exclude raw recordings, full source procedures, source scripts/macros,
visible secrets and incidental private values by default. Include authored
knowledge, explicit contracts and benign examples needed for independent
execution. Do not bundle credentials, install commands, general network
clients, service launchers or desktop automation fallbacks.

## Tie output to actual coverage

In the assembly plan, use `format_version: 1`, the supported `plugin`
specification, `skills` and `tools`. Skill entries hold `name`,
`description`, `body`, `companions`; companions/tool files hold `path` and
text `content`. Read all path/metadata restrictions from the build skill.

After assembly, each blueprint binding names the real output skill, actual
candidate package files and declared test IDs for exactly one step.
Review those files for actual behavior: a binding to a file that merely
mentions the step is not meaningful coverage.

Do not generate plausible tests and call them passed. Test expectations
belong to the blueprint; actual results belong to the hash/revision-bound
evaluation record. Preserve local versus native provenance and failed or
unrun cases.

End with a configurable manual prompt. Native-schedule text is optional
guidance only where supported, never a new manifest field, created schedule
or guarantee of unattended approval. Route final review and correction to
`review-output-plugin`.
