---
name: author-output-skills
description: "Write standalone Cowork output skills and packaged references from a reviewed workflow blueprint. Use to turn confirmed process rules into focused instructions, configurable input/output contracts and meaningful examples, with complete step coverage and no dependency on the Creator or original recording."
---

# Author standalone output skills

Read `references\guidance.md` for generation patterns and review questions.
Route to `build-output-plugin` for the canonical project and candidate
formats. Do not invent manifest fields or read another Creator skill's
resources through cross-skill paths.

Use `assets\pattern-catalog.json` and `references\patterns.md` for the
packaged cost-report, priority-checklist and signed-exception patterns.
Choose only a pattern that matches confirmed rules; catalog membership is
not evidence that this workflow or its native capabilities were exercised.

## Select coherent skill boundaries

Read the current blueprint, evidence, decisions and host profile. Preserve
material unresolved issues as Draft; do not make generation look like user
confirmation or successful execution.

Use one entry skill for a small process. Split medium or larger processes
into a few reusable business tasks, not one skill per click or an enormous
all-purpose instruction. A sequential path with native file checkpoints
must work without an optional subagent facility.

## Write discoverable, focused instructions

For every generated skill:

- Match the folder to its 1-64 character kebab-case `name`.
- Use exactly four frontmatter lines: opening `---`, `name: NAME`,
  `description: JSON-QUOTED-STRING`, closing `---`. The description is a
  single-line JSON-quoted YAML string, 1-1024 characters. Add no extra keys.
- Explain when to trigger in the description. Keep a nonempty, focused body
  under 500 lines and load deeper owned references only when needed.
- Declare required inputs, justified defaults, expected outputs, semantic
  steps, conditions, bounded repetition and stopping rules.
- Distinguish reads, local writes and business writes. Preserve native
  approvals and inspect-before-retry behavior for uncertain effects.
- Give configurable manual invocation examples and changed-input examples.
  Do not bake in the demonstration's dates, row counts, filenames or amounts.

Use native document editing where it preserves the required behavior.
Route reliable parsing, calculation and file composition to
`author-deterministic-helpers` when an available runtime makes code useful.

## Make the output independent

Package each reference, asset, script and sibling module within the output
skill that uses it. Locate actual native resource paths at runtime rather
than assuming developer or Creator installation paths. Route calls to other
skills by name, not by reading/importing their files.

Do not leave Creator imports, original-evidence requirements, unbundled
templates, demo-only absolute paths, network clients or runtime installers
in the output. Exclude raw recordings, full source documents and secrets by
default; retain only authored workflow knowledge and needed resources.

Stay within 20 skills and 10 connectors per plugin, and per skill at most
20 companions, 5 MB each and 10 MB total. Count every reference and helper;
do not move runtime dependencies outside their owning skill to evade limits.

## Bind and hand off

Use the exact assembly-plan format provided by `build-output-plugin`:
`format_version`, `plugin`, `skills`, `tools`; each skill has `name`,
`description`, `body`, `companions`. Companion and tool contents are text
in the supported format, not instructions to download missing resources.

Have the build skill assemble into a new candidate directory. Ensure each
blueprint step is bound exactly once to the real output skill, actual
candidate package files and meaningful declared test IDs. Bindings describe
generated coverage; they do not execute the process.

Route to `review-output-plugin` for evidence, generalization, limits and
independence checks. A candidate that packages structurally but omits a
requested material step is still incomplete.
