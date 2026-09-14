---
name: author-deterministic-helpers
description: "Author small deterministic helpers for supported Cowork process workflows. Use for exact calculations, bounded JSON parsing, filtering, normalization, validation or file composition, with explicit inputs, precise errors and held-out synthetic tests rather than hardcoded demonstration values or new runtime dependencies."
---

# Author bounded deterministic helpers

Read `references\guidance.md` for contracts and negative cases. Use the
bundled `assets\safe_json.py` as a reviewed JSON-handling pattern when
appropriate. Copy the needed pattern into the generated output skill's
own resources; never import it from the installed Creator at runtime.

Route project-contract questions and packaging to `build-output-plugin`.
Do not use cross-skill filesystem paths to obtain its code.

## Decide whether code improves the workflow

Prefer native document facilities when sufficient. Use small helpers for
repeatable calculations, filtering, joins, validation and file assembly
that benefit from deterministic results.

Confirm the needed interpreter and standard-library facilities in the
actual native environment through `map-native-capabilities`. A local
developer test is not native-runtime evidence. If the runtime is missing,
use a genuinely equivalent available native operation or keep this scope
Draft. Do not require an end-user-installed interpreter, FFmpeg or package
manager. Cowork's already-provided Python is allowed when actually available.
Do not add network clients, external executables, model/media services or
automation runners as substitutes for missing native capabilities.

## Implement an explicit bounded contract

1. Take declared filenames and business parameters as supplied inputs.
   Validate types and required fields before processing; do not substitute
   sample dates, totals, row counts or silent defaults.
2. Bound input reads, collection sizes, nesting and repetition. Reject
   oversized data without reading it all into memory.
3. For JSON reject malformed UTF-8/JSON, duplicate keys, non-finite numbers,
   excessive nesting and parser numeric limits with precise errors.
   Distinguish booleans from integers when validating numeric fields.
4. Use exact domain-appropriate arithmetic, explicit dates/timezones and
   stated ordering/rounding rules. Ask about material ambiguity.
5. Write only intended new local output files after validation. Do not
   overwrite unrelated files or leave success-shaped output after failure.
6. Handle expected failures specifically. Emit a bounded useful diagnostic
   and nonzero failure status; if the helper declares an error-report
   artifact, honor that contract when its destination is writable.
   Do not use blanket catches, raw secret-bearing input dumps or empty
   default results to hide failures.

Keep all helper imports within the standard library or packaged sibling
modules in that same output skill. Do not introduce a general workflow
interpreter, scheduler, queue, permission store or transaction coordinator.

## Test what the helper promises

Use synthetic inputs and held-out values not copied from the demonstration.
Cover normal results, empty input, boundaries, type errors, duplicates,
missing files, malformed/deep JSON, oversized input and output collisions.
Test both declared diagnostics and the absence of a misleading result.

An uncaught `RecursionError` is not a successful friendly-error result.
Include deep-input rejection and invalid-Unicode output cases when applicable;
encoding must succeed before a new output file is created. A stated
requirement is not proof that the generated helper has passed it.

Record only actual test results, scoped to `local` or `native`, against the
current blueprint revision/hash and candidate fingerprint from the build
skill's check. Leave unexecuted cases `not-run`; source inspection is not a
substitute for execution.

Return owned code, its documented contract, cases and actual diagnostics to
`author-output-skills` and `review-output-plugin`. Structural checks are
limited subset checks, not a code sandbox or full behavioral proof.
