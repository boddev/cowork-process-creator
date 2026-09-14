# Runtime input and output

Input is a UTF-8 JSON object with exactly `items`, a list of 0-10,000 rows.
Each row has exactly these fields:

| Field | Accepted values |
|---|---|
| `id` | Unique, 1-64 ASCII letters/digits/dot/underscore/hyphen; starts with letter/digit |
| `state` | Exactly `ready` or `hold` |
| `quantity` | Integer 1-100,000, excluding Boolean |
| `unit_cost` | Nonnegative decimal string, exactly two fraction digits, at most 999999999.99 |

All fields are validated before any output is created. Reject malformed
JSON, duplicate JSON keys/IDs, missing/extra fields, unknown states, floats,
Boolean quantities, non-finite values and out-of-range values. The helper's
input-file ceiling is 2 MB for this bounded workflow.

The reporting month is supplied separately as `YYYY-MM`, with a real
month 01-12 and a four-digit year 1000-9999. No sample date is built in.
The output is a new `.md` path, not an existing file.

Keep `ready` rows in input order. Compute each line as quantity times
unit_cost with exact decimal arithmetic, then sum all lines. Use two
fractional digits in the Markdown table and total. Include row counts.
An empty collection or all-held collection has total 0.00.

No external system, connector, credential, publishing operation or
additional runtime artifact is required. Native script execution must be
available; the package does not supply or install an interpreter.
