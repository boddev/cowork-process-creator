---
name: review-output-plugin
description: "Review a generated Cowork process plugin for traceable coverage, independence, precise readiness and safe handoff. Use before delivery or when a user corrects evidence, rules or generated files, including source resume, stale results and three-way conflicts that must preserve user edits."
---

# Review, correct and hand off

Read `references\guidance.md` for review gates and correction cases. Route to
`build-output-plugin` for canonical contracts, current project checks,
fingerprints, packaging and source resume/merge. Do not access another
skill's filesystem resources directly.

## Review the actual candidate

1. Read the current evidence, blueprint, decisions, profile, candidate and
   evaluation records. Ask the build skill to check this project, not an old
   source directory or merely the low-level package layout.
2. Trace every material step and output to evidence or actual user decisions,
   native support, actual owned candidate files and meaningful cases.
   Retain missing steps in coverage rather than dropping them to pass checks.
3. Check changed-input behavior, justified defaults/constants, conditions,
   bounded loops, effects and ambiguous-result stopping rules.
4. Verify no fabricated connection/tool/registration/legal metadata, hidden
   external dependency, cross-skill import, Creator dependency, raw source
   recording or visible secret is included.
5. Check all owned resources exist and fit the package limits. Focused
   instructions should use progressive disclosure and exact frontmatter.
6. Review actual permitted synthetic checks, including deep invalid JSON and
   precise failure behavior for applicable helpers. New prompts, source
   inspection and expected outputs are not passed evaluations.

Record evaluation results only for actual executions, tied to the current
blueprint revision/hash and candidate fingerprint. Keep `environment: local`
distinct from `native`, and `not-run` distinct from `passed`. A failed or stale
case remains visible. An agent-authored report is not independent proof.

## Correct without erasing user work

Preserve the current project and a known base checkpoint before proposing
changes. Identify affected evidence, rules, bindings, code and cases; use
targeted regeneration rather than rewriting unrelated resources.

Use the build skill's `merge` for a base source ZIP, current user-edited
project and proposed project. The proposal advances the base revision once.
Do not modify originals. Nonconflicting changes may combine; different
same-file changes produce conflicts and no merged project. Report those
conflicts and seek an actual resolution instead of silently choosing a side.

On resume or merge, treat archived records as history. Current native
availability must be rechecked; changed or uncertain evidence needs actual
reattachment/observation. Reconfirm material decisions for the exact revised
blueprint, and refresh evaluations rather than transferring old pass claims.

## Deliver precise readiness

State the artifact/version, target, checked environment, supported scope,
unanswered questions, connection/setup gaps and unrun native gates.

| Claim | Evidence required |
|---|---|
| Draft | Useful source with unresolved scope/setup, or an explicitly separate source export |
| Package built | Actual ZIP and successful checks for its named emitted target |
| Installed | Actual target host accepted this exact package |
| Manually exercised | Declared inputs executed with verified expected results |
| Schedule exercised | A later native scheduled invocation behaved as declared |

Local checks and an old prototype never promote a new candidate to the last
three states. Canonical packaging needs approved publishing metadata.
Compatible-source remains a Draft source target; conversion is a separate
native observation. Neither target's structural checks are full-schema
validation or a code sandbox.

Return actual downloadable files, the coverage/diagnostic report and a
source-resume bundle that excludes raw media/secrets by default. Explain
which ZIP is the plugin, which is creation source, and whether a Download
All archive is only an outer container.
If the toolkit could not run, return available authored source instead of
claiming a verified resume archive or plugin ZIP exists.

Provide a manual prompt using new inputs, expected outputs and existing
native connection setup. Independent invocation must use only the output
plugin and its declared runtime inputs, not Creator files or the original
recording. Give native-schedule guidance only when supported and safe under
actual native approval rules; do not create a schedule or claim unattended
writes, exactly-once effects or cross-session locks.

Act within the current user's authorization and actual host capabilities.
Delivering a plugin file does not authorize its installation, publication,
sharing, connection/auth/EULA/account changes or production writes. Do not
perform those automatically. Preserve native controls and assess each
artifact's actual state rather than inheriting another session's permissions
or readiness.
