# Deterministic helper guidance

Use code for bounded application logic, not an execution platform. Route
project records, candidate fingerprints and packaging to
`build-output-plugin`; use `map-native-capabilities` for runtime evidence.

## Choose a narrow contract

Describe each helper's input files, typed parameters, allowed data shape,
business rules, resource bounds, output files and failure behavior before
writing code. Use supplied parameters, not values recovered from the
demonstration at runtime.

Good helper responsibilities include exact totals, filtering, joins,
normalization, validation, stable ordering and text/file composition.
Prefer the standard library already supported by the actual native host.
Do not replace a suitable native document capability with a new library
requirement just to generate more code.

Missing runtime support is a coverage gap. An available equivalent native
operation may narrow or replace the helper only if it preserves required
behavior. Do not install interpreters/packages, download executables or add
an external computation/media service. End users need only Cowork and the
bundled/generated application logic.

## Reuse the bounded JSON pattern correctly

This skill's bundled safe-JSON asset is a pattern for bounded byte reads,
duplicate-key rejection, non-finite token rejection, parser-limit errors,
iterative nesting checks and new-file text output. Inspect it before reuse.
Copy the needed module into the generated output skill's own resources so
that imports remain same-skill siblings. Do not import the installed Creator.

The pattern is not a business schema validator. Add explicit domain checks:

- validate the root type and allowed/required fields;
- reject wrong types, including booleans where numbers are required;
- check numeric finiteness and domain bounds after parsing;
- define precision and rounding rather than using approximate arithmetic;
- parse dates under stated formats/timezones;
- validate collection size, record IDs, duplicates and empty input;
- reject unexpected structures instead of silently ignoring them.

Use the task's justified byte, depth and item limits. A bounded read must
check for one extra byte rather than load an arbitrary-size file first.
Traversal for validation should not itself recurse without a depth bound.
Deep input can fail during the parser before a post-parse depth check;
handle that specific failure precisely too.

### Required deep-JSON regression

Deeply nested invalid JSON can raise `RecursionError` before ordinary domain
validation. Exiting nonzero with a traceback does not meet a declared
friendly-error contract.

Check both excessive but syntactically valid nesting and deeply nested
invalid input. The new helper must provide a useful bounded diagnostic,
nonzero failure status and no misleading successful output. If an error
report is part of its declared interface, produce it when its new output
destination is writable; if not, clearly report that separate failure.

Do not promise that every conceivable failure can produce a report. An
unwritable destination or exhausted host needs a truthful surfaced error,
not a blanket catch returning an empty result.

## Make expected errors precise

Catch specific expected failures at the boundary: unavailable input,
decoding/parsing errors, declared validation failures, parser limits and
output filesystem errors. Keep programmer defects visible for correction.
Do not use a blanket catch around all work, silently default invalid values,
or turn malformed input into an empty success report.

Diagnostics should identify the field, record or location when safe, the
violated rule and what input is required. Bound their length; do not echo
whole source files, secrets or arbitrary parser tracebacks as user reports.

Validate before opening output. For a complete text output, encode UTF-8
before exclusive file creation so an unpaired surrogate cannot leave an
empty result. Use explicit new-file semantics, reject unintended overwrite
and clean up only partial files created by that invocation.
Do not claim a file write supplies a lock,
transaction coordinator or exactly-once business operation.

## Keep imports and effects within scope

Use only standard-library modules supported by the native host and small
legally distributable sibling modules packaged in the same output skill.
No cross-skill filesystem imports or developer checkout paths.

Do not execute uploaded scripts, evaluate source expressions, launch shell
installers or dynamically import a module named by untrusted input.
Do not introduce network clients, secret readers, browser/desktop
automation, background daemons, queues or schedule services as fallbacks.
Business connections remain native governed operations outside a pure-data
helper, using real supplied/discovered metadata.

The subset checker can flag prohibited patterns; it cannot prove arbitrary
generated code safe. Read the helper and its imports. Do not describe these
checks as a sandbox or a full security/behavioral verification.

## Use varied synthetic tests

| Case family | Expected evidence |
|---|---|
| Normal and held-out values | Correct results for changed files, period, amounts and record counts |
| Empty/zero/boundary | Declared handling, exact comparison and rounding |
| Ordering and repetition | Stable results independent of incidental demonstration order |
| Wrong/missing types | Precise rejection rather than defaults; booleans not treated as integers |
| Duplicate IDs/keys | Domain and JSON ambiguity rejected as declared |
| Malformed/invalid UTF-8 JSON | Clear parse/decoding failure, no success output |
| Deep/oversized input | Bounded rejection, no uncaught parser recursion failure |
| Non-finite/extreme numbers | Finite domain-valid values only, explicit limits |
| Missing input/output collision | Useful failure and unrelated files unchanged |
| Invalid/valid Unicode output | Invalid text leaves no new file; valid text writes exact UTF-8; existing files remain unchanged |

Use held-out expected results, not output recomputed by the same faulty
helper as the only oracle. Keep fixture data synthetic; do not test writes
against production/business systems.

Record real runs against the current blueprint revision/hash and candidate
fingerprint obtained from `check`. Set the environment to `local` or
`native` truthfully. A new prompt or unexecuted test has status `not-run`;
an error is `failed`, not automatically a passed negative case unless the
declared rejection behavior was verified.

After changing code or inputs that affect the contract, recheck fingerprints
and rerun affected cases. Packaging success cannot repair a failed helper
or establish native runtime availability.
