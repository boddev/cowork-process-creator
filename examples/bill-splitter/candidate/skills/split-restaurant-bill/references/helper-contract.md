# split_bill.py contract

Standard library only, using an existing Python 3.10+ interpreter. Reads one
JSON file, writes one **new** JSON file, not an XLSX workbook.
It never overwrites, never reaches the network and keeps no state.

Locate the bundled `scripts/split_bill.py` and its sibling `safe_json.py` in
this skill's native resources. Invoke the actual script with `--input` followed
by the meal JSON path and `--output` followed by the new split JSON path. Use
host-correct paths and separate arguments; do not install Python or packages.

Exit 0 on success. Exit 2 with a single `bill-split error: ...` line on
stderr and no newly created output on input or filesystem failure. Existing
files remain unchanged. Invalid CLI arguments use argparse's usage diagnostic.

## Input

A JSON object. Only these fields are accepted; anything else is rejected.

| Field | Required | Type | Rules |
|---|---|---|---|
| `diners` | yes | array of strings | 1-8 unique non-empty names, ≤64 chars. Order sets column order. |
| `lines` | yes | array of objects | 1-20 lines. |
| `lines[].label` | yes | string | Non-empty, ≤120 chars — the line as printed. |
| `lines[].amount` | yes | number | > 0, at most 999999999.99, at most 2 decimals. Booleans and strings are rejected. |
| `lines[].shares` | yes | object | Name → whole number 0-99. Every name must be in `diners`. At least one share per line. |
| `tax` | yes | number | 0-999999999.99, at most 2 decimals. |
| `tip_amount` | one of | number | The gratuity printed on the receipt; 0-999999999.99, at most 2 decimals. |
| `tip_rate` | one of | number | Fraction 0-1, at most 6 decimals, e.g. `0.2`. Supply exactly one of `tip_amount` / `tip_rate`. |
| `meal_label` | no | string | ≤64 chars; echoed back in the result. |
| `printed_subtotal` | no | number | At most 19999999999.80, at most 2 decimals; must equal the sum of the line amounts. |
| `printed_total` | no | number | At most 40999999999.59, at most 2 decimals; must equal subtotal + tax + tip, not a pre-tip total. |

Bounds: at most 200,000 bytes, 8 levels of nesting and 64 characters per JSON
number token. Names and labels are stripped of surrounding whitespace before
validation; share keys must match the resulting diner names exactly. Decimal
JSON numbers are parsed exactly, not through binary floats. Malformed JSON,
non-UTF-8 bytes, duplicate object keys, `NaN`/`Infinity` and over-deep input
are each rejected with their own message.

## Arithmetic

1. Convert each validated monetary amount to integer cents.
   `shares_claimed` is the sum of the line's shares. A person's fraction of a
   line is their shares divided by that sum; do not round each line first.
2. Take the least common multiple of all line share sums as a common
   denominator. Sum each person's integer-weighted fractions of the line
   amounts. This preserves exact shares and ties regardless of receipt order
   or the ambient decimal precision.
3. Allocate the subtotal, tax and tip separately using those same weights.
   When `tip_rate` is given, tip is subtotal times that exact rate rounded
   half-up to cents; when `tip_amount` is given it is used verbatim.
4. Each of the three columns is rounded to whole cents by the
   **largest-remainder** method: round every entry down, then give the
   remaining cents to the entries with the largest discarded fraction, ties
   broken by diner position. Each allocation has fewer remaining cents than
   diners. Each column therefore sums exactly to its total, and
   the per-person totals sum exactly to the grand total.
5. The helper fails rather than emitting a result if that reconciliation does
   not land on zero.

The sheet's formulas keep full precision and round only for display. Separate
rounding of items, tax and tip can change a person's total by more than one
cent relative to the displayed formula total. The helper's reconciled figures
are the amounts to quote.

## Output

```json
{
  "meal_label": "Harbour Grill",
  "items_subtotal": "55.00",
  "tax": "5.00",
  "tip_rate": "20.00",
  "tip": "11.00",
  "grand_total": "71.00",
  "check": "0.00",
  "lines": [
    {"label": "Soup", "amount": "10.00", "shares_claimed": 2,
     "cost_per_share": "5.00", "shares": {"Ana": 1, "Bo": 1}}
  ],
  "people": [
    {"name": "Ana", "items": "16.00", "tax_share": "1.45",
     "tip_share": "3.20", "total_owed": "20.65"}
  ]
}
```

All monetary amounts are strings with exactly two decimal places so no float
re-rounds them. The displayed `cost_per_share` is rounded half-up and must not
be used to reconstruct the calculation. `tip_rate` is a
percentage (e.g. `"20.00"`); when a `tip_amount` was supplied it is the
implied rate rounded for display only, not an authoritative input for
recomputing a printed gratuity. Zero-share entries are omitted from each
line's `shares`.

## Rejections worth knowing

- a line with no shares, naming the line;
- a share for a name that is not a diner;
- more than 8 diners or 20 lines;
- duplicate diner names;
- a boolean, a string, a negative or a sub-cent amount;
- `printed_subtotal` / `printed_total` that disagree, with the difference;
- both or neither of `tip_amount` and `tip_rate`; a rate above 1 or with more than six decimals;
- amounts above the declared bounds, or number tokens longer than 64 characters;
- an unsupported top-level or line field;
- an output path that already exists — the existing file is left untouched.

Relay these to the user as they are. They indicate a receipt or an assignment
that still needs a human answer, not a bug to route around.
