# Reusable output patterns

These patterns guide Cowork's authoring. They are not preconfigured business
connections or a hidden workflow interpreter. Select only a pattern that
preserves the confirmed rules, parameters, safeguards and intended output.
Route to author-deterministic-helpers for the bounded JSON I/O pattern and
copy any reused helper into the output skill's own resources.

## Exact cost report

Validate every record, including excluded ones. Model repeated work over the
input collection, not the demonstrated row count. Keep monetary values exact
(integer hundredths or explicitly bounded Decimal precision), preserve input
order unless a confirmed sort rule says otherwise, and render counts plus
line costs and a grand total. Require the data file, period and output name.

Test changed values and record counts, all-excluded/empty input, invalid IDs,
duplicate keys, booleans/fractions where integers are required, malformed
currency strings, extreme declared bounds, oversized and deeply nested JSON,
and existing output destinations. Do not write a purchasing/accounting system.

## Priority checklist

Separate a file-only checklist from actually creating tasks or sending
messages. Confirm category definitions, ordering within/across categories,
unknown-category behavior and title/identifier rules. Preserve original order
within a group when that is the documented rule. Parameterize the input,
period label and output name.

Test reordered priorities, a new category, duplicates, invalid text, empty
input and no-overwrite behavior. A task-system write requires a real native
connection and current native approval, not just this file transformation.

## Signed exception ledger

Confirm which operand is subtracted from which, the allowed input range,
rounding policy, exclusion of zero differences, ordering and net-total
meaning. Use exact signed arithmetic. Negative values must not be formatted
using an incorrect floor-division shortcut. Separate discrepancy reporting
from correcting a source business record.

Test a negative small difference, mixed signs, zero differences, maximum
declared bounds, duplicate IDs, invalid numeric forms and changed input sizes.

## Pattern selection and extension

Read the packaged catalog to select a pattern by confirmed business purpose,
not by incidental keywords from a demonstration. Treat its case names as
suggestions, then create workflow-specific expected results and actual
synthetic runs. Catalog membership is not evidence that native capabilities
or this newly generated output have been exercised.

Add extensions as reviewed packaged resources with IDs, versions, intended
use, native capability requirements, resource paths and evaluation cases.
Do not download executable components at runtime or turn a reference pattern
into a new server, connector implementation or scheduler.
