# Ready-items cost report

This is a synthetic, file-only procedure for the N00 native proof. All
people, items and amounts in the demonstration are invented test data.

## Goal

Produce a Markdown cost report for a user-supplied reporting month from
an attached JSON inventory. The demonstration shows one month and one
inventory; future runs must accept different values and any supported
number of rows. Do not perform a purchase or update any business system.

## Connection metadata

| Property | Value |
|---|---|
| Business system | None |
| Connection mode | Native attached input file and native generated output file |
| Endpoint, tool names, registration IDs | Not applicable |
| Authentication, scopes, credentials | None required |
| Permitted effects | Read the supplied input and create a new report file |
| Prohibited effects | Sending, publishing, purchasing, or updating production records |

## Runtime inputs

The user supplies an input JSON file, reporting month (`YYYY-MM`), and new
Markdown output filename. There is no default reporting month or input
filename.

The JSON object has exactly one field, `items`, containing zero to 10,000
records. Each record has exactly `id`, `state`, `quantity`, and `unit_cost`.

- `id`: unique identifier, 1-64 ASCII letters/digits, dots, underscores or
  hyphens; the first character must be a letter or digit.
- `state`: exactly `ready` or `hold`.
- `quantity`: an integer from 1 to 100,000, not a Boolean or fraction.
- `unit_cost`: a nonnegative decimal string with exactly two fractional
  digits, at most `999999999.99`. Values are fictional monetary units.

## Confirmed rules

1. Read and validate every row, including rows that will be excluded.
2. Keep only rows whose state is `ready`. A `hold` row is excluded.
3. For each kept row, multiply quantity by unit cost using exact decimal
   arithmetic. Preserve input order.
4. Sum all retained line costs, not a fixed number of sample rows.
5. Produce a Markdown report with reporting month, a table of retained
   IDs/quantities/unit costs/line costs, included and excluded row counts,
   and a two-decimal grand total.
6. An empty inventory or no `ready` rows produces an empty table and total
   `0.00`, not an error.
7. Reject malformed fields, duplicate IDs/JSON keys, unknown states, invalid
   months or non-finite/negative/fractional numeric values. Do not silently
   skip or coerce invalid data.
8. Do not overwrite an existing output file. Report the error and request
   a new destination.

## Demonstration evidence

Read the numbered screenshots in filename order. They show a synthetic
source inventory, the retained rows with repeated calculations, and the
final report. The visible sample values, displayed note and final total
must be obtained from the images, not inferred from this document.

A screenshot-only run does not establish video reading. The recording path
requires a separately attached real video and its own observation evidence.
