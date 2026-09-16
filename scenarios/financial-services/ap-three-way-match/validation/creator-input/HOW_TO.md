# AP three-way matching: a synthetic, review-only procedure

## Purpose, operator and limits

An AP analyst supplies one immutable export batch for the fictional **SYN-FIN
Demonstration Company**. Compare incoming invoice prices and quantities with
purchase-order (PO) lines, receipt lines, posted invoice history and prior
quantity allocations. Return a complete AP manager review packet: every
invoice and line, proposed receipt allocations, remaining PO/receipt
capacities, exclusions and owned holds.

**No posting, payment, real approval, permission grant, PO change or receipt
consumption occurs.** Every result, including a rejected batch, has
`human_review: "pending"` and `live_action: "none"`. “Ready” means ready for
human review, not ready to pay. Approved controls and POs are synthetic
metadata, not authentication or real authority.

The operator supplies `as_of`; this is not a scheduled process. Inputs are
synthetic JSON exports only, not a Finance import format. No PDFs, OCR, Excel,
CSV adapters, credit notes, returns, reversals, FX, unit conversions, tax
calculation or cumulative last-invoice price-total matching are supported.
Nonzero tax, charges, discounts or freight are preserved and held explicitly.
Never invent missing records, normalize entity/vendor IDs, fuzzy-match text,
or change the input to make an invoice match.

## Verified primary sources versus sample policy

These Microsoft primary pages were retrieved in full and their relevant
sections read on **2026-09-14**:

1. [Accounts payable invoice matching overview](https://learn.microsoft.com/dynamics365/finance/accounts-payable/accounts-payable-invoice-matching)
   (`ms-ap-invoice-matching`): **Three-way matching** compares invoice/PO
   prices and invoice/selected-receipt quantities. **Two-way, price totals
   matching** describes percentage and amount limits where either exceeded
   limit is a discrepancy. **Related functionality** describes discrepancy
   review. This is product behavior, not regulation.
2. [Vendor invoices overview](https://learn.microsoft.com/dynamics365/finance/accounts-payable/vendor-invoices-overview)
   (`ms-vendor-invoices`): **Preventing invoice submission to workflow**
   documents a configured duplicate posted-number check. **Matching vendor
   invoices to product receipts** supports partial receipt quantities and
   receipts available through the current date.

Those concepts motivate the comparison and review workflow. All field names,
synthetic identifiers, duplicate-key normalization, all-competitor holds,
fixed-offset clock, approval labels, bounds, HALF_UP rule, diagnostic
precedence, **200 bps** tolerance and **500-cent** line cap below are
**invented sample policies**. In particular, the symmetric unit-price plus
per-line-cap combination is not Microsoft's complete cumulative price-total
calculation. No regulatory-compliance conclusion or successful Finance/native
execution follows from these sources.

## Input contract

Read a UTF-8 JSON object with no duplicate object keys, nonfinite numbers or
byte-order mark. The local CLI bounds input to 8 MiB and nesting to 80. Unknown
fields at **every object level**, unsupported enum values or modes, missing
required fields, and invalid scalar types reject the entire batch. Optional
means absent, not null. Do not coerce booleans, floats, numeric strings or null
to integers. A valid JSON file containing an invalid business record is a
business rejection, not a successful match.

### Primitive types

| Type | Exact meaning |
| --- | --- |
| ID | String of at most 64 ASCII characters matching `SYN-[A-Z0-9]+(?:-[A-Z0-9]+)*`. Case-sensitive, never trimmed or changed. |
| Currency | Exact string `USD` or `EUR`; both have exponent 2. There is no default currency and no conversion. |
| Unit | Exact uppercase ASCII string matching `[A-Z][A-Z0-9]{0,15}`, e.g. `EA`. No conversion. |
| Money | True integer from 0 through 1,000,000,000,000 inclusive, in currency minor units (cents), including unit prices per **whole** unit. |
| Quantity | True integer from 1 through 1,000,000,000 inclusive, in thousandths of a unit. Computed remaining capacity can be zero. |
| Timestamp | Exact `YYYY-MM-DDTHH:MM:SS[.ffffff]Z` or that form with `+HH:MM` / `-HH:MM`. Optional fraction has 1–6 digits. Valid calendar date, uppercase T/Z, no leap seconds, offset at most 14:00, minutes at most 59; `-00:00` (unknown offset) is unsupported. The instant and its configured business-date conversion must be representable in years 1–9999. |
| Vendor number | ASCII string of at most 128 characters before trim, 5–64 after trim; canonical text starts `SYN-`, has a non-space printable first suffix character, and otherwise contains printable ASCII including internal spaces and punctuation. Trim only ASCII space/tab/CR/LF/form-feed/vertical-tab at the ends, then uppercase ASCII letters. Preserve punctuation, internal spaces and leading zeros. Reject non-ASCII or internal control characters. |
| Components | Optional object with only `tax_minor`, `charges_minor`, `discounts_minor`, `freight_minor`. Each optional key is Money defaulting to 0; absent object means all four are 0. Discounts are a nonnegative magnitude. Nonzero values are unsupported-scope evidence, not amounts to reinterpret. |

### Root fields (all required)

| Field | Type and requirement |
| --- | --- |
| `schema_version` | True integer exactly 1. |
| `batch_id` | ID. |
| `as_of` | Timestamp, not the wall clock. |
| `business_utc_offset_minutes` | True integer from -840 through 840 inclusive. Convert instants to this **fixed** offset when deriving business dates; no local-machine, IANA-zone or DST inference. |
| `controls` | Object described below. |
| `invoices` | Nonempty array of invoice header objects with nested lines. |
| `po_lines`, `receipt_lines`, `historical_invoices`, `prior_allocations` | Arrays of the records below; may be empty. |

Controls require `control_version` (ID) and `approval_state` (`approved` or
`pending`). Optional true-integer fields are `unit_tolerance_bps` (0–10,000,
default 200), `line_amount_cap_minor` (Money, default 500), and
`max_rows_per_source` (1–5,000, default 5,000). A pending controls object
rejects with `policy-not-approved` before any financial classification.
Unknown approval states are malformed, not equivalent to pending.

Apply the source-row limit independently to invoice headers, all invoice
lines combined, PO lines, receipt lines, historical headers, prior
allocations, and all explicit receipt-selection rows combined. Each nested
array also respects this limit. Overflow rejects; never truncate decisions.

### Invoice and line records

An invoice requires `invoice_id`, `legal_entity_id`, `vendor_id` (IDs),
`currency`, `vendor_invoice_number`, `invoice_at` (Timestamp),
`header_net_minor` (Money), and nonempty `lines` (array). `components` is the
only optional header field.

Each invoice line requires `line_id`, `po_id`, `po_line_id` (IDs), `unit`,
`quantity_milliunits` (Quantity), `unit_price_minor` (Money per whole unit),
and `line_net_minor` (Money). Its only optional fields are `components` and
`selected_receipts`.

`selected_receipts`, when present, is an array of objects containing exactly
`receipt_line_id` (ID) and `quantity_milliunits` (Quantity). Empty selection
is an explicit zero selection, **not** permission to guess; it fails the
exact-sum test for a positive invoice quantity. Null is malformed.

Primary keys are `invoice_id` for headers, `(invoice_id, line_id)` for lines,
and `(invoice_id, line_id, receipt_line_id)` for selections. Every repeated
primary key rejects, even if the repeated rows are identical.

### PO lines

Required fields: `legal_entity_id`, `po_id`, `po_line_id`, `vendor_id` (IDs),
`currency`, `unit`, `ordered_milliunits` (Quantity), `unit_price_minor`
(Money), `approval_state` (`approved` or `pending`), and `approved_at`.
The last is a Timestamp for approved POs and **must be null** for pending POs.
The primary key is `(legal_entity_id, po_id, po_line_id)`.
Pending approval and approval after `as_of` are invoice business holds, not
malformed PO records. The numeric PO capacity still remains visible.

### Receipt lines

Required fields: `receipt_line_id`, `legal_entity_id`, `po_id`, `po_line_id`,
`vendor_id` (IDs), `currency`, `unit`, `quantity_milliunits` (Quantity),
`received_at` (Timestamp), `status` (`posted` or `pending`), and `posted_at`.
`posted_at` is a Timestamp for posted rows and must be null for pending rows.
The primary key is `receipt_line_id`. Every receipt must reference an existing
PO line and exactly match its vendor, currency and unit, even when future or
unused. Posted time cannot precede physical receipt time.

### Historical invoices and prior allocations

A historical invoice requires `historical_invoice_id`, `legal_entity_id`,
`vendor_id` (IDs), `currency`, `vendor_invoice_number`, `status` (`posted` or
`pending`) and `posted_at` (Timestamp if posted; otherwise null). Primary key:
`historical_invoice_id`. Multiple allocation rows refer to one header; do not
repeat the header. A header is allowed to have no allocation rows.

A prior allocation requires `allocation_id`, `historical_invoice_id`,
`legal_entity_id`, `po_id`, `po_line_id`, `receipt_line_id` (IDs),
`quantity_milliunits` (Quantity) and `recorded_at` (Timestamp). Primary key:
`allocation_id`. All three referenced records must exist; the historical
invoice and receipt must have posted status. The allocation, receipt and PO
must have the same exact PO key. The historical invoice entity/vendor/currency
must match the PO. Recording cannot precede either historical invoice posting
or receipt posting. These integrity checks apply even to future records.

Do not infer missing historical consumption from invoice numbers, amount
similarity or physical receipts. The operator is responsible for supplying
complete, trustworthy exports; this procedure does not establish their real
completeness or approval identity.

## Ordered decisions and arithmetic

The eight step IDs below are the corresponding `workflow.json` states.
Perform checks against immutable input evidence. Array order never selects a
winner. Keep ordinary business holds separate from whole-batch integrity
rejections.

### 1. `intake-documents` — input

Read the batch, explicit clock, controls and source counts. Preserve all IDs
and declared money/quantity values. Label any demonstration synthetic.

### 2. `validate-documents` — validation

Use predictable rejection precedence:

1. Root object shape/unknown fields/missing fields, schema version, batch ID,
   `as_of`, business offset; then controls shape, ID, enum, numeric bounds,
   and pending-control rejection.
2. Top-level array shape and row limits in order: invoices, PO lines,
   receipt lines, historical invoices, prior allocations.
3. Invoice headers in scope/ID order: shape, IDs, currency, vendor number,
   invoice timestamp, header net, components, lines-array shape and header
   primary key. Lines in line-ID order: shape, IDs, unit, quantity, unit price,
   line net, components, line primary key, then explicit selection shape,
   receipt IDs, quantities and selection keys. After each invoice's scalar
   checks, validate its header sum and then its applicable line calculations.
   The combined nested-source limits are checked before financial joins.
4. PO records, then receipt records, then historical headers, then prior
   allocations: shapes, scalars, dates, status/null consistency and keys.
5. Authoritative receipt-to-PO references and receipt chronology; allocation
   references/scope/chronology; total historical receipt use, then PO use.

Within a row, unknown or missing field names are checked lexically; scalar
checks follow the field order listed in this procedure. Use the first
diagnostic only; emit no partial trustworthy financial totals. For malformed
records that cannot supply a valid identity, report a null identity. Stable
sorting puts absent/non-string sort fields before valid string keys, breaking
ties by sorted-key ASCII JSON serialization. PO, receipt and historical rows
use their output scope/ID order. Prior allocations initially validate by
legal entity and allocation ID; their final output order uses the joined PO
scope. The procedure does not promise a meaningful row identity for an
invalid key.

Always require `header_net_minor = sum(declared line_net_minor)`, including
unsupported-component invoices. If **any** header or line component is
nonzero, hold the whole invoice as `unsupported-components` and skip the
zero-component arithmetic checks and price tests for **all its lines**.
Preserve declared header/line/component amounts unchanged. This does not
excuse malformed fields, broken header sums or contradictory history.

Otherwise, for each line use exact nonnegative integer arithmetic:

```text
calculated_line_net_minor = floor((quantity_milliunits * unit_price_minor + 500) / 1000)
```

The declared net must equal this value. This is HALF_UP to a cent, once per
line, not once at the invoice total and not binary floating-point rounding.
Invoice quantity, PO quantity, receipt quantity and allocation quantity are
all true integer milliunits.

Only posted historical headers with `posted_at <= as_of` contribute duplicate
keys. Pending/future headers remain output rows with explicit exclusion codes.
Only prior allocations with `recorded_at <= as_of` consume historical capacity;
future rows remain explicit exclusions. An allocation recorded by the cutoff
against an invoice or receipt posted after that cutoff is contradictory,
never usable consumption. All historical allocation rows, including future
rows, must form a coherent capacity history: their aggregate consumption
cannot exceed either receipt quantity or ordered PO quantity. Reject
over-allocation; never clamp a negative remainder. The as-of capacity
worksheet subtracts **only** included history after this integrity check.

### 3. `join-duplicates-and-pos` — join

Build the complete incoming duplicate-key ledger before holding anything.
The business key is `(legal_entity_id, vendor_id,
canonical_vendor_invoice_number)`; **currency is intentionally not part of
the duplicate key**. Retain every other matching incoming ID and every
included matching historical ID. Hold **all** incoming duplicates, including
future-dated or otherwise held invoices; no arbitrary first winner. A
duplicate business document is a hold, unlike a repeated technical key.
Independently hold incoming invoices with `invoice_at > as_of`.

For each line join the invoice entity plus `po_id` and `po_line_id` exactly.
A missing PO is `po-not-found`. A PO with different vendor, currency or unit
is `po-scope-mismatch`; retain the found PO's evidence but do not treat it as
a usable join. If the join matches, test approved state and approval time.
Keep pending/future approval holds while still evaluating price/receipt
evidence for diagnostics. Missing/scope-mismatched joins cannot support price
or receipt comparisons.

### 4. `join-receipt-evidence` — join

A receipt is available only when posted and `posted_at <= as_of`.
`received_at <= as_of` alone is not enough. Explicitly list pending and
future-posted receipts, their full raw quantities and local posting dates;
they provide zero as-of capacity. Eligible candidate IDs for a line require
an exact usable PO join and a **positive** receipt capacity after included
historical consumption. Exhausted receipts are not positive candidates.

If selection is explicit, preserve every requested receipt ID/quantity and
check the sum equals the line quantity. For each selected ID, diagnose in
order: absent receipt, different PO scope/unit, not posted by cutoff, or
requested quantity above that receipt's as-of capacity. Record all applicable
distinct codes, never infer a substitute. A quantity mismatch may coexist
with selected-row diagnostics. Capacity and availability are not changed by
another incoming line at this stage.

If selection is absent:

- No positive eligible receipt: `receipt-unavailable`, no selection.
- More than one: `receipt-selection-required`, no selection, even if only
  one could individually satisfy the line.
- Exactly one but too small: `receipt-shortage`, no partial selection.
- Exactly one and sufficient: select the entire line quantity from it,
  with `selection_mode = "sole-receipt"`.

Explicit selections have mode `explicit` even when invalid. An absent
selection that cannot be resolved has mode `none`. Also hold a line whose
quantity exceeds the historical-net PO capacity (`po-quantity-shortage`).
Do not perform FIFO, latest-receipt selection, amount matching or subset
search. The receipt shortage field measures quantity minus **all** positive
eligible capacity, floored at zero; zero shortage does not resolve ambiguity
or prove an explicit selection valid.

### 5. `evaluate-price-and-quantity` — decision

For a usable PO join and zero-component invoice, set:

```text
po_line_net_minor = floor((quantity_milliunits * po_unit_price_minor + 500) / 1000)
unit_difference_minor = abs(invoice_unit_price_minor - po_unit_price_minor)
unit_test_left = unit_difference_minor * 10000
unit_test_right = po_unit_price_minor * unit_tolerance_bps
line_difference_minor = abs(line_net_minor - po_line_net_minor)
```

Both `unit_test_left <= unit_test_right` and
`line_difference_minor <= line_amount_cap_minor` must pass, **inclusively**.
This is symmetric: both higher and lower invoice prices can fail. At a zero
PO price, require invoice price **and** invoice net to be zero. Show the same
cross-products and line-cap result, but use only `zero-price-mismatch` for a
nonzero invoice price/net, not additional percentage/cap codes. Never divide
by zero. For a positive PO price, emit either or both tolerance codes.

Retain all original line evaluations even if a header or another line is
held. For each invoice with no existing individual hold, aggregate its own
proposed selections across all lines by receipt and by PO key. If its combined
demand exceeds either resource, add the corresponding
`invoice-receipt-capacity-exceeded` / `invoice-po-capacity-exceeded` header
hold. A multi-line invoice cannot evade a resource cap by splitting lines.

For example, the demo's 6,000 milliunits at 1,010 cents computes 6,060 cents.
The PO-priced net is 6,000; cross-products are 100,000 and 200,000, with a
60-cent net difference. Explicit 3,000 + 3,000 receipt quantities can support
the whole line after recorded historical use. This example is synthetic.

### 6. `resolve-capacity-conflicts` — decision

First remove **every invoice with any individual header or line hold**,
including its otherwise valid lines. On the remaining invoices, aggregate
all requested receipt quantities and all requested PO quantities globally.
Compute **both** resource types from the same pre-conflict candidate set.
For every resource whose total exceeds its historical-net capacity, record
the available quantity, total demand and **all** participating invoice IDs.
Hold every participant. A conflict can be PO-only (different receipts on the
same PO) or receipt-only (ample PO but a shared receipt), or both.

Apply all conflicts simultaneously. Never choose the first invoice, accept a
maximal subset, free and retry capacity in the same run, or partially release
an invoice. Lines that directly demand a conflicting resource carry the
corresponding conflict code; sibling lines are still held atomically even
when their own conflict-code arrays are empty.

### 7. `route-invoice-holds` — exception

An invoice is `held` if any header, line or conflict reason exists; every
line is then `held` and all its proposed quantities/net amounts are zero.
Otherwise the invoice is `ready-for-review` and every line is `proposed`.
Keep selected-row diagnostics as evidence, not real allocations.

Emit one diagnostic per distinct `(source, record_id, line_id, code)` and
source exclusion, with an owner from the catalog below. Invoice reason codes
are the sorted union of its own and its lines' codes. Header-level holds
need not be duplicated in each line's individual-code array.

### 8. `emit-ap-review` — output

Emit quantity proposals only for complete ready invoices. Never mutate prior
allocations, PO quantities or receipts. For every available receipt:

```text
quantity_milliunits = historical_used_milliunits + proposed_milliunits + remaining_milliunits
```

For every PO, replace `quantity_milliunits` with `ordered_milliunits`.
Unavailable receipts instead preserve their original quantities in the
receipt/exclusion rows and have zero as-of before/proposed/remaining
capacities. Verify proposals do not exceed either capacity and every proposed
line's allocations sum to its full quantity. Each invoice belongs exactly
once to the ready or held partition. Per entity/vendor/currency:

```text
invoice_count = ready_invoice_count + held_invoice_count
intake_net_minor = ready_net_minor + held_net_minor
```

Do not aggregate money across currencies or sum incomparable units. Summary
amounts use declared header net only; held components remain separate
evidence, not hidden “ready” money.

## Complete output contract

Every result has exactly:

| Key | Type / meaning |
| --- | --- |
| `schema_version` | True integer 1. |
| `status` | `completed` if there are no holds or source exclusions; `completed_with_exceptions` if integrity is valid but at least one hold or exclusion exists; `rejected` on the first integrity/configuration diagnostic. |
| `outputs` | Object below. |
| `exceptions` | Ordered array of diagnostic objects below; empty only for `completed`. |

For `rejected`, `outputs` contains **only** `review`; no plausible partial
financial rows or totals. For either non-rejected status, it contains exactly
`context`, `invoice_reviews`, `line_comparisons`, `proposed_allocations`,
`remaining_capacity`, `historical_invoices`, `prior_allocations`,
`excluded_receipts`, `capacity_conflicts`, `summary`, and `review`.

All counts/quantities/cents/cross-products below are true integers; computed
sums and products may exceed a single input-field bound, using exact integer
arithmetic. All strings retain input spelling except explicitly canonical
vendor numbers. All booleans are JSON booleans. No output key below is
optional; use the documented null or empty-array value.

### Context and review

`context` contains `batch_id`, `as_of`, `business_utc_offset_minutes` (copied
input), `business_date` (derived strict `YYYY-MM-DD`), `control_version`,
effective integer `unit_tolerance_bps`, `line_amount_cap_minor`,
`max_rows_per_source`, and `source_counts`.

`source_counts` has integer counts for `invoices`, `invoice_lines`,
`po_lines`, `receipt_lines`, `historical_invoices`, `prior_allocations`,
`selected_receipts`. The last counts supplied selection rows only, not
automatically proposed sole-receipt selections.

`review` always has exactly `human_review: "pending"`, `live_action: "none"`,
`owner_role: "AP manager"`.

### `invoice_reviews[]`

Each row contains:

- Copied `invoice_id`, `legal_entity_id`, `vendor_id`, `currency`,
  `vendor_invoice_number`, `invoice_at`, `header_net_minor`.
- `canonical_vendor_invoice_number`: canonical string.
- `declared_line_net_minor`: integer sum of declared line nets.
- `components`: all four explicit Money keys, including zeros.
- `line_ids`: all input line IDs.
- `duplicate_invoice_ids`: **other** matching incoming IDs, excluding self.
- `duplicate_historical_invoice_ids`: matching included historical IDs.
- `status`: `ready-for-review` or `held`.
- `reason_codes`: distinct union of invoice, line and conflict code strings.
- `proposed_net_minor`: full declared header net if ready; otherwise 0.

### `line_comparisons[]`

Each row contains copied `invoice_id`, `line_id`, `legal_entity_id`,
`vendor_id`, `currency`, `po_id`, `po_line_id`, `unit`,
`quantity_milliunits`, `unit_price_minor`, `line_net_minor`, plus:

| Key | Type / exact meaning |
| --- | --- |
| `calculated_line_net_minor` | HALF_UP integer net, or null when any component on the invoice is nonzero. |
| `components` | All four component Money keys for this line, including zeros. |
| `po` | PO-evidence object below, or null when the exact entity/PO/line key is absent. |
| `price` | Price object below, always present. |
| `receipts` | Receipt-comparison object below, always present. |
| `individual_reason_codes` | Distinct line-specific reason strings; does not duplicate header holds. |
| `conflict_reason_codes` | `po-capacity-conflict` / `receipt-capacity-conflict` when this line directly uses those oversubscribed resources. |
| `status` | `proposed` only when its entire invoice is ready; otherwise `held`. |
| `proposed_quantity_milliunits` | Full input line quantity when proposed; otherwise 0. |

`po` has copied PO `vendor_id`, `currency`, `unit`, `ordered_milliunits`,
`unit_price_minor`, `approval_state`, `approved_at`; also integer
`available_milliunits` (ordered less included historical use),
`shortage_milliunits` (line quantity minus availability, floored at zero),
and boolean `join_matches` (vendor/currency/unit all exact). Even a
scope-mismatched found PO retains its true evidence; its numeric shortage
does not establish a trusted join.

`price` has exactly `po_line_net_minor`, `unit_difference_minor`,
`unit_test_left`, `unit_test_right`, `unit_price_pass`,
`line_difference_minor`, `line_cap_pass`. The two `*_pass` values are
booleans; the other five are integers. **All seven are null** if the PO join
is absent/mismatched or the invoice has nonzero components. Pending approval,
duplicates and ordinary quantity holds do not suppress otherwise valid
price evidence.

`receipts` has:

- `eligible_ids`: positive-capacity, exact-scope, posted-by-cutoff receipt IDs.
- `available_milliunits`: sum of those capacities; null for an unusable PO join.
- `selection_mode`: `explicit`, `sole-receipt`, or `none`.
- `selections`: rows with `receipt_line_id`, `quantity_milliunits`,
  `available_milliunits` (actual as-of remaining capacity for an existing
  receipt, even if mismatched; null only if missing), and `eligible` (boolean
  for exact usable scope and posted availability; an exhausted but posted
  exact-scope receipt can be eligible here with zero capacity).
- `total_selected_milliunits`: sum of selected quantities, 0 for no selection.
- `shortage_milliunits`: line quantity less all positive eligible capacity,
  floored at 0; null for an unusable PO join.

Preserve explicit selections even for an unusable PO join, with
`eligible: false`; do not guess. In that situation the PO hold is primary:
the selection sum check remains applicable but selected-row receipt
diagnostics are suppressed because their line scope cannot be trusted.

### `proposed_allocations[]`

Each row contains `invoice_id`, `line_id`, `legal_entity_id`, `vendor_id`,
`currency`, `po_id`, `po_line_id`, `receipt_line_id`, `unit` (strings), and
`quantity_milliunits` (positive integer). Composite identity is
`(invoice_id, line_id, receipt_line_id)`. These are **quantity-only proposals**,
not a posting ID or split monetary allocations. Held invoices have no rows.

### `remaining_capacity`

This object contains exactly `receipts` and `po_lines`, arrays with **every**
input resource including unused, pending and future records.

Each `receipts[]` row contains all input receipt fields unchanged and:
`posted_business_date` (`YYYY-MM-DD` or null only for pending/unposted),
`available_at_as_of` (boolean), `historical_used_milliunits` (included use),
`before_proposals_milliunits`, `proposed_milliunits`, `remaining_milliunits`
(nonnegative integers). Unavailable receipts have zeros for the four
quantities. An exhausted available receipt still has `available_at_as_of:
true`. The before value is the available receipt quantity less history.

Each `po_lines[]` row contains all input PO fields unchanged and:
`available_for_proposals` (boolean: approved by cutoff), plus the same four
integer use/before/proposed/remaining quantities. Before equals ordered less
included history even for an unapproved PO; the availability flag prevents
using it. Approved means synthetic evidence, not actual authorization.

### Historical rows and receipt exclusions

`historical_invoices[]` has all input historical-header fields,
`canonical_vendor_invoice_number` (string), `included` (boolean), and
`exclusion_code` (null when included; otherwise a historical-invoice exclusion
code below).

`prior_allocations[]` has all input allocation fields, `included` (boolean),
and `exclusion_code` (null when included; otherwise
`allocation-recorded-after-as-of`).

`excluded_receipts[]` contains only unavailable receipts, one row each:
`receipt_line_id`, `code`, `message`, `quantity_milliunits` (full raw quantity),
`posted_at` (original string or null), and `posted_business_date` (string or
null). The full receipt still appears in remaining capacity; do not count
this explanatory reference as another input receipt.

### Conflicts and summaries

Each `capacity_conflicts[]` row has `resource_type` (`po-line` or `receipt`),
`legal_entity_id`, `vendor_id`, `currency`, `po_id`, `po_line_id`, `unit`,
`receipt_line_id` (ID only for receipt resources; otherwise null),
`available_milliunits`, `demand_milliunits` (integers), and
`competing_invoice_ids` (all candidate invoice IDs using that resource).
Demand is the original, pre-conflict candidate demand, not a retry total.
Individual invoice shortages are holds, not global-conflict rows.

Each `summary[]` row is one incoming `(legal_entity_id, vendor_id, currency)`
scope with those three strings and integer `invoice_count`,
`ready_invoice_count`, `held_invoice_count`, `intake_net_minor`,
`ready_net_minor`, `held_net_minor`. Never produce cross-currency totals.

### Diagnostic shape, messages and owners

Every `exceptions[]` entry contains exactly `code`, `message`, `source`,
`record_id`, `line_id`, `field`, `owner_role`. Code/message/source/owner are
nonempty strings. `record_id` is the applicable source ID (invoice ID for
line diagnostics, PO ID for PO diagnostics, control version for controls)
or null if unavailable. `line_id` is the invoice/PO line ID when applicable,
otherwise null. `field` is the invalid input field for rejection diagnostics,
otherwise null. Sources are `payload`, `controls`, `invoices`,
`invoice-lines`, `selected-receipts`, `po-lines`, `receipt-lines`,
`historical-invoices`, `prior-allocations`. Fields for a repeated composite
key join its component names with `/`.

The following are **whole-batch rejection** codes; owner is always
`Source data owner`. Messages are exact:

| Code | Message |
| --- | --- |
| `invalid-object` | Expected an object with the documented fields. |
| `unknown-field` | Undocumented input field is not supported. |
| `missing-field` | Required input field is missing. |
| `invalid-version` | schema_version must be the integer 1. |
| `invalid-identifier` | Expected an uppercase ASCII SYN- identifier. |
| `invalid-invoice-number` | Expected a printable ASCII synthetic vendor invoice number. |
| `invalid-unit` | Expected a supported uppercase ASCII unit. |
| `invalid-enum` | Value is not a supported enum member. |
| `invalid-integer` | Expected a true integer within the documented bounds. |
| `invalid-array` | Expected an array with the documented minimum length. |
| `row-limit-exceeded` | Source row count exceeds max_rows_per_source. |
| `invalid-timestamp` | Expected a supported offset-bearing RFC 3339 timestamp. |
| `invalid-status-timestamp` | Timestamp must be null for pending status. |
| `duplicate-primary-key` | A primary key is repeated, including identical rows. |
| `policy-not-approved` | Synthetic controls must be approved before financial classification. |
| `header-net-inconsistent` | Header net does not equal the sum of declared line nets. |
| `line-net-inconsistent` | Declared line net does not equal the HALF_UP quantity-price calculation. |
| `receipt-po-inconsistent` | Receipt must reference an existing PO with matching vendor, currency and unit. |
| `receipt-time-inconsistent` | Receipt posting precedes physical receipt. |
| `allocation-reference-inconsistent` | Prior allocation must reference an existing posted historical invoice, posted receipt and exact matching PO scope. |
| `allocation-time-inconsistent` | Prior allocation recording precedes invoice or receipt posting. |
| `historical-receipt-overallocated` | Historical allocations exceed receipt quantity. |
| `historical-po-overallocated` | Historical allocations exceed ordered PO quantity. |

These are **invoice hold** codes. “AP” means `AP manager`, “Procurement” means
`Procurement owner`, “Receiving” means `Receiving owner`:

| Code | Exact message | Owner |
| --- | --- | --- |
| `duplicate-incoming-invoice` | All incoming invoices with this canonical business key are held. | AP |
| `duplicate-posted-invoice` | The canonical business key matches posted history available by as_of. | AP |
| `invoice-after-as-of` | Invoice timestamp is after as_of. | AP |
| `unsupported-components` | Nonzero tax, charges, discounts, or freight are outside this sample's scope. | AP |
| `po-not-found` | No PO line has the invoice's exact legal-entity, PO, and PO-line key. | Procurement |
| `po-scope-mismatch` | PO vendor, currency, and unit must exactly match the invoice line. | Procurement |
| `po-approval-pending` | The PO line is not approved. | Procurement |
| `po-approval-after-as-of` | PO approval occurred after as_of. | Procurement |
| `po-quantity-shortage` | Requested line quantity exceeds historical-net PO capacity. | Procurement |
| `zero-price-mismatch` | A zero-price PO requires zero invoice unit price and line net. | Procurement |
| `unit-price-out-of-tolerance` | The symmetric unit-price difference exceeds the inclusive basis-point limit. | Procurement |
| `line-amount-out-of-tolerance` | The line-net difference exceeds the inclusive minor-unit cap. | Procurement |
| `receipt-selection-required` | Multiple eligible positive-capacity receipts require explicit selection. | Receiving |
| `receipt-unavailable` | No eligible positive-capacity receipt is available by as_of. | Receiving |
| `receipt-shortage` | Available receipt capacity is less than the requested quantity. | Receiving |
| `selection-quantity-mismatch` | Explicit receipt quantities must sum exactly to the invoice line quantity. | Receiving |
| `selected-receipt-missing` | A selected receipt ID is not present in the export. | Receiving |
| `selected-receipt-scope-mismatch` | A selected receipt does not belong to the exact PO scope and unit. | Receiving |
| `selected-receipt-unavailable` | A selected receipt is not posted by as_of. | Receiving |
| `selected-receipt-shortage` | An explicit receipt selection exceeds that receipt's remaining capacity. | Receiving |
| `invoice-receipt-capacity-exceeded` | This invoice's combined line demand exceeds a receipt's remaining capacity. | Receiving |
| `invoice-po-capacity-exceeded` | This invoice's combined line demand exceeds a PO line's remaining capacity. | Procurement |
| `receipt-capacity-conflict` | All otherwise eligible invoices competing for an oversubscribed receipt are held. | Receiving |
| `po-capacity-conflict` | All otherwise eligible invoices competing for an oversubscribed PO line are held. | Procurement |

These are **source exclusions**, not automatic invoice holds. They still make
the packet `completed_with_exceptions`. An invoice is held separately if it
needs unavailable evidence:

| Code | Exact message | Owner |
| --- | --- | --- |
| `receipt-posted-after-as-of` | Receipt posting is after as_of; its quantity is excluded. | Receiving owner |
| `receipt-not-posted` | Receipt is not posted; its quantity is excluded. | Receiving owner |
| `historical-invoice-posted-after-as-of` | Historical invoice posting is after as_of; its business key is excluded. | Source data owner |
| `historical-invoice-not-posted` | Historical invoice is not posted; its business key is excluded. | Source data owner |
| `allocation-recorded-after-as-of` | Prior allocation recording is after as_of; its quantity is excluded. | Source data owner |

### Exact array ordering

Use ordinary case-sensitive lexical string ordering. Scope order throughout
is `(legal_entity_id, vendor_id, currency)`.

- Invoice reviews: scope, invoice ID. Line comparisons: same, then line ID.
- Proposals: scope, invoice ID, line ID, receipt ID.
- PO capacities: scope, PO ID, PO-line ID. Receipt capacities and exclusions:
  scope, receipt ID.
- Historical headers: scope, historical ID. Prior allocations: scope from
  their joined PO, then allocation ID.
- Conflict rows: scope, resource type (`po-line` before `receipt`), PO ID,
  PO-line ID, receipt ID (null treated as empty).
- Summaries: scope. All ID arrays, selection rows and reason-code arrays:
  lexical ID/code order, distinct where described.
- Exceptions: joined scope (empty for unknown), record ID, line ID, code,
  source, field; null sort components are empty strings. Header exceptions
  sort before line exceptions on the same invoice. Validation emits just
  its first diagnostic, not a partially sorted financial queue.

These orders include empty arrays and are part of the output contract.

## Local demonstration and actual-trace video

The development baseline is a separate standard-library comparison
implementation, not the Creator-produced skill and not a native test.
With existing Python, from this scenario directory, use unused output paths:

```powershell
python -B baseline.py --input mock-data\demo.json --output baseline-output\demo.json --trace baseline-output\demo.trace.json
```

The shared CLI refuses overwriting existing output files; the parent-owned
validation runner controls deliberate refreshes. No dependency installation
is needed. Native execution must implement this procedure independently,
not invoke or copy the development baseline.

An actual successful local execution emits the eight states above, with
observed source counts, header checks, exact joins, receipt-capacity evidence,
price cross-products, global conflicts, holds and final summaries. Rejection
emits input, diagnostic validation, and a rejected output state. Events must
be captured from runtime rows/intermediates, not invented narration.
Trace tables are labeled excerpts with at most eight displayed rows and six
columns, accurate `total_rows` and row highlights.

The shared foundation centrally produces `demo/baseline.webm` from the
actual validated demonstration trace. **A missing video is not a fabricated
recording or permission to stage an incomplete demonstration.** It is a
roughly 30–90 second silent visualization, not a Finance application or
Cowork recording. It must carry the on-frame label **Synthetic baseline
execution visualization - not Cowork or a live system**, and central media
metadata binds source/result/trace hashes and fidelity evidence. This
scenario owner supplies the meaningful trace, not screenshots or a video
generation service.

## Native Creator procedure and present gate

**Native creation, installation and independent execution: NOT RUN /
BLOCKED.** The historical N00 attempt was last seen at **Publishing...**;
its outcome is **UNKNOWN**, not success, and Creator was disabled. Do not
invent an Installed state, passed native result or native plugin ZIP.

Proceed only after **all three** conditions are established: restored
approved Computer Use tools, an unlocked accessible native session, and
parent-coordinated authorization. Do not substitute browser/Playwright,
private API, cookies, tokens, shell automation, model/skill routes, or an
installer. Inspect the real Installed state before any retry of N00.

After the parent confirms those gates and central video is ready:

1. Use the approved native Creator UI procedure. Supply exactly this
   allowlist: `HOW_TO.md`, `workflow.json`, `connections.json`,
   `mock-data/demo.json`, `demo/baseline.webm`. These provide the full public
   procedure, eight-step workflow, mock connection metadata, synthetic export
   example and actual-trace demonstration. Stage nothing else. Keep research,
   development implementations/shared code, answer material, private
   evaluation inputs, comparison results and validation evidence withheld.
2. Request a file-based review skill implementing this procedure, its exact
   schemas, integer/date semantics, ordering, exclusions and no-live-action
   boundary. The workflow JSON is a procedure description, not a request to
   build or deploy a workflow engine.
3. Use only existing host reasoning, files, media understanding and permitted
   execution. Verify those capabilities in the approved UI; they are not
   established by an offline Python pass. If unavailable, record the genuine
   blocker. No backend, custom MCP, Azure/model/media service, database, queue,
   gateway, scheduler, runner, device agent or runtime installer is allowed.
4. Observe actual generation/publishing, save native evidence, and separately
   verify the real installed skill in the approved UI. A local source/ZIP
   inspection is not execution, installation or provenance. Never label a
   merely declared step observed.
5. In a new independent native invocation, attach only the parent-authorized
   synthetic input and ask the installed skill to return the documented
   review files. It must not consult the local baseline or private answers.
   Preserve the real result and evidence IDs; a human/parent comparison must
   check complete rows, ordering, amounts, exclusions and all safety flags.
6. Report generation, installation, invocation and comparison separately.
   Failed/blocked/unknown phases stay failed/blocked/unknown. No posting,
   payment or real capacity update is part of this test.

`connections.json` is exactly `mode: "mock-exports-only"`,
`availability: "not-required"`, `connections: []`, with a note about synthetic
export files and outputs. No endpoint or authentication exists here.
Named real integration gaps remain: actual ERP invoice/PO/receipt/history
export access, trustworthy allocation history, real approval identity,
vendor-master mapping and a verified approved Finance connection. Resolving
those gaps requires a separately approved scope, not invented credentials
or additional runtime infrastructure.
