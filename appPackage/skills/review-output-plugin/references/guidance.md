# Output review and correction guidance

Review the whole authored process, not only its ZIP shape. Use
`build-output-plugin` for the canonical records, actual fingerprints,
deterministic checks and checkpoint/resume/merge operations.

## Review gates

| Gate | Review question |
|---|---|
| Evidence | Were material facts actually observed/documented, with current source identifiers and honest locators? |
| Generalization | Do changed inputs work without sample dates, row counts, paths or amounts becoming accidental constants? |
| Semantics | Are every required output, condition, loop, exception and material side effect represented? |
| Decisions | Are material user answers real, current and tied to the exact blueprint revision/hash? |
| Capabilities | Are native support and real connection/tool metadata evidenced in the correct environment? |
| Generated coverage | Is each step bound once to actual candidate files and meaningful declared cases? |
| Helpers | Are inputs bounded, arithmetic/rules precise, failures explicit and held-out checks actually run? |
| Independence | Does the output own every resource it needs, without the Creator or original demonstration? |
| Packaging | Does the actual selected target pass its emitted-subset and resource checks? |
| Handoff | Are source/plugin ZIPs, setup gaps and unrun native gates unmistakably labeled? |

A broken gate should have an actionable explanation. Do not remove a
required step, claim a synthetic native capability, fabricate a user answer
or copy an old passing report to make the check green.

The blueprint is not a runtime execution engine. Successful structural
checking cannot prove the correctness of video interpretation or every
generated branch. Builder heuristics are not a sandbox or full Microsoft
schema validation.

## Distinguish planned and actual evaluations

Blueprint cases and evaluation prompts describe expected behavior.
`evaluation-results.json` describes actual runs, with current
`blueprint_revision`, `blueprint_sha256`, `candidate_sha256`, environment
and case evidence. Obtain hashes from the actual checked source.

Use `local` for local engineering execution and `native` only for actual
target Cowork execution. Record `passed`, `failed` or `not-run` truthfully.
Source inspection, a generated expected output and an agent's assurance
are not execution evidence.

For negative cases, merely exiting nonzero is insufficient if the declared
contract includes precise errors or an error report. Uncaught recursion or
an encoding error that leaves an empty output does not meet a friendly,
no-partial-output contract. Require the applicable helper to demonstrate
its intended rejection.

Review changed inputs and held-out expected outputs, not renamed copies
of one example. Include missing files, malformed data, empty collections,
unsupported capabilities, output collisions and stale source cases where
relevant. Use synthetic data and no production/business writes.

## Correct source without destroying concurrent edits

1. Preserve a known base source checkpoint and the user's current project.
2. Identify the affected observation, rule, helper, binding or case.
3. Create a separate proposal, advancing the base blueprint revision once.
   Leave unrelated source alone.
4. Use the build skill's `merge` with the base ZIP, current project and
   proposed project, writing only to a new project directory.
5. If a file differs on both sides, inspect the reported conflict. The
   deterministic merge is file-level, not line-level: different changes
   to separate lines in the same file can still conflict.
6. Do not overwrite either original or call conflict detection a successful
   merge. Obtain an actual resolution, preserve intended user edits and
   revise the proposal before retrying.
7. Recheck the resulting source and obtain current decisions/evaluations
   rather than merely assigning their old results new hashes.

Example: the user edits a report reference while a proposal fixes a
different helper file. Those nonconflicting changes should both survive.
If both edit that helper differently, return a conflict and no output
project. No automatic last-writer-wins behavior is acceptable.

## Resume means verify and review again

The source bundle holds authored knowledge/code and source identifiers and
hashes, not a separate memory service. Raw recordings, original attachments
and publishing secrets are excluded by default.

Resume verifies the archive's complete inventory, hashes and safe paths
before creating a new project. Tampering, extra files, traversal or
inconsistent revisions should fail rather than be partly restored.
Preserve the original bundle and existing directory.

On successful resume/merge, historical host/input/build/evaluation/coverage
records are preserved byte-for-byte under content-hashed `history`. Live
capability and connection availability are reset to unverified, attached
labels become recorded, prior evaluations are archived, and phase returns
to review. This preserves history without inheriting live access,
permissions or previous execution claims.

Unchanged historical observations can remain useful. Ask for reattachment
when evidence is missing, changed, unclear or needed for a new inference.
Do not imply that source hashes restore a video or prove its unseen content.
An `attached` to `recorded` availability transition alone does not change
the evidence fingerprint. Changed source facts or observation content do;
use the current `evidence_sha256` from `check` and review affected support.

Before packaging, recheck current capabilities and connections, refresh
actual evaluations against the current blueprint revision/hash and candidate
hash, and check again. This is required even when historical notes remain
usable. Do not promote archived test results or metadata provenance into
fresh execution or connection availability evidence.

## Handoff labels and evidence boundaries

- **Draft:** unresolved material rules/support/setup, offline synthetic
  readiness, or an explicitly separate compatible-source export.
- **Package built:** an actual ZIP passed the Creator's subset checks for
  the named target. It is not installed merely because it exists.
- **Installed:** the actual target Cowork host accepted this exact artifact.
- **Manually exercised:** execution on declared inputs met verified expected
  behavior. Record whether independent from the Creator.
- **Schedule exercised:** a later native scheduled invocation met declared
  behavior; a suggested prompt or created schedule alone is insufficient.

Keep observations tied to artifact hashes/versions and environment.
Uncertain publication is not Installed and not proof of failure either.
Inspect actual native state, when separately authorized, before a retry.

Keep artifact/version/session history in the project's evidence records.
Do not treat a prior success, failure, blocked host or uncertain action as
the current user's state. Inspect current authorized native state before
repeating an action whose result is unknown.

## Give instructions without taking unauthorized actions

Return the exact plugin ZIP when built, its check/build diagnostics and the
creation-source bundle through native files. Distinguish the actual plugin
from an outer Download All archive and from the resume archive.

Provide the manual invocation, explicit runtime parameters, expected new
output and any existing native connection setup requirements. The eventual
independent check uses only the output plugin and new runtime input, without
the Creator, original video/procedure or authoring directory.

For supported native schedules, explain parameters, file availability,
approval limits and how a later successful run would be verified. Do not
create an external scheduler or promise unattended writes, serialized
execution, shared-file locks, exactly-once effects or approval inheritance.

The current user's request determines the authorized scope. Do not turn
installation/setup instructions or an authoring request into automatic
publication, account changes or production actions. If a current capability
or authorization is missing, return useful source and the exact limitation;
do not bypass native controls or invent successful execution.
