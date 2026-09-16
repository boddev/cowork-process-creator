# Supplier delivery performance and shortage expediting review

## Purpose, actors, and boundary

A buyer/material planner prepares a daily or manually requested **review-only**
packet from a frozen synthetic snapshot. Procurement reviewers resolve source
questions; the named buyer approves any subsequent communication or PO change
outside this process. Start with all five logical exports and explicit policy.
End with reconciled receipt evidence, an explained historical denominator,
prospective requirement coverage, an ordered **unsent** buyer queue, explicit
exceptions, and report closure. A completed report is not a delivery commitment,
purchase approval, inventory reservation, or permission to contact a supplier.

All companies, roles, items, quantities, thresholds, and examples are fictional.
The implementation is a bounded whole-EA/calendar-day sample, **not D365 OTIF
parity**, an ERP posting engine, workday/transport calendar, carrier ETA check,
supplier qualification, or financial-return accounting.

The one input JSON object contains **separately named logical export tables**.
Their identities and joins are preserved; this is not a claim of native
physical multi-file ingestion. No network, mail, ERP, database, Power BI,
authentication, credentials, package install, or external runner is required.
`connections.json` declares mock-exports-only, not-required, and no connections.
Source text is inert data, never executable instructions.

## Research basis and limits

These official pages were actually fetched for the approved manufacturing
research on **2026-09-14**. No additional research or approval is required for
this local sample build.

| Reference | Source-backed concept | Sample-only limit |
| --- | --- | --- |
| [Power BI reports for risks analysis and performance ranking](https://learn.microsoft.com/en-us/dynamics365/supply-chain/procurement/supply-risk-assessment-reports) | Receipt-based OT/IF/OTIF and historical versus planned supplier risk are distinct evidence. | Our cohort, full-void model, formula details, rounding, uncertainty, and priorities are not asserted to reproduce D365. |
| [Procurement and sourcing overview](https://learn.microsoft.com/en-us/dynamics365/supply-chain/procurement/procurement-sourcing-overview) | Purchase confirmation, delivery schedules, arrival registration, and product receipts differ. | Only mock exported posted receipts count here; invoices, arrival-only registrations, and promises are not receipt events. No ERP operation occurs. |
| [Calculate requested ship dates for purchase orders](https://learn.microsoft.com/en-us/dynamics365/supply-chain/master-planning/supplier-requested-confirmed-dates) | Requested/confirmed ship and receipt dates differ; transport and calendars affect ERP dates. | Use explicit receipt dates and calendar days only. Never infer receipt from ship date or reconstruct a workday calendar. |

## Exact input contract

The top-level object has exactly `config`, `po_schedule_lines`,
`receipt_events`, `confirmations`, `requirements`, and `suppliers`.
Every field below is required; unknown fields reject. Empty arrays are valid.
No default policy, inferred table, implicit zero, or field coercion is allowed.

Common types:

| Type | Exact meaning |
| --- | --- |
| ID | Case-sensitive ASCII string matching `[A-Za-z0-9][A-Za-z0-9_-]{0,39}`; maximum 40 characters. Joins use exact equality, with no case folding or trimming. |
| date | Canonical valid `YYYY-MM-DD` calendar date, inclusive range 2000-01-01 through 2100-12-31. No timestamps/time zones or compact ISO variants. |
| month | Canonical valid `YYYY-MM`, inclusive 2000-01 through 2100-12. A valid future reporting month is allowed and can have no included lines. |
| quantity | JSON integer whole EA, not boolean, decimal, string, null, negative, or float. Positive fields are 1-1,000,000; remaining confirmation allows 0-1,000,000. |
| nullable | Only the explicitly listed fields accept JSON `null`; empty text is not null. |
| role | Printable ASCII text, 1-80 characters, no leading/trailing whitespace. An internal role, not an email/address or authorization credential. |

All five export arrays are limited to **200 raw rows each, before deduplication**.
Distinct primary IDs are scoped to their own table; identical strings in
different tables do not join unless an explicit foreign key says so.
Each individual input quantity is bounded; aggregated exact integer totals
may exceed 1,000,000 (at most 200,000,000 within a table).
The shared CLI additionally requires UTF-8, no duplicate JSON object keys,
finite numbers, at most 8 MiB input, and nesting no deeper than 80.

### Config object

| Key | Type and policy |
| --- | --- |
| `as_of` | date; the snapshot boundary, inclusive. No wall clock is read. |
| `reporting_month` | month; cohort follows original requested receipt date, not posting or promise month. |
| `horizon_days` | Integer 0-90. `horizon_end = as_of + horizon_days` calendar days. |
| `tolerance_days` | Integer 0-30. `deadline = original_requested_receipt + tolerance_days`. |
| `urgency_days` | Integer 0-90, also at most `horizon_days`. `urgency_end = as_of + urgency_days`. |
| `low_performance_percent` | Integer 0-100; flag only an exact performance ratio strictly below this threshold. |

Derived horizon, urgency, and known receipt deadlines must also remain in the
supported date range. An overflow is malformed input, not a clamped date.

### Logical exports

| Table | Required keys and types |
| --- | --- |
| `po_schedule_lines` | `line_id` ID (primary); `supplier_id` ID; `item_id` ID (opaque exported item identity, no item master inferred); `ordered_qty` positive quantity; `original_requested_receipt` date or null; `state` exactly `open` or `cancelled`. Here `open` means not cancelled; receipts determine remaining quantity even on a fully received line. |
| `receipt_events` | `event_id` ID (primary); `line_id` ID (schedule FK); `posted_on` date; `qty` positive quantity; `reversal_of` original receipt event ID or null. Every row is explicitly a posted-receipt export record; null means a positive receipt, non-null means a full void request. Positive quantities are used for both, not signed financial entries. |
| `confirmations` | `confirmation_id` ID (primary); `line_id` ID (schedule FK); `recorded_on` date (when evidence entered the snapshot); `confirmed_receipt` date or null (ETA, not ship date); `remaining_qty` nonnegative quantity already reflecting physical receipts in the export. |
| `requirements` | `requirement_id` ID (primary); `line_id` ID (schedule FK); `need_by` date; `unmet_qty` positive quantity; `criticality` exactly `critical` or `normal`. Already-unmet, line-pegged demand after exported stock/receipt accounting. |
| `suppliers` | `supplier_id` ID (primary); `buyer_role` role. This is the only owner mapping; missing mappings stay null. |

## Deterministic procedure and precedence

### 1. Intake (`input`)

Inventory actual raw row counts and config in the supplied snapshot. Preserve
separate source identities. Do not read other files to complete missing input.

### 2. Validate (`validation`)

Validate all shapes/fields/types/ranges in one phase. Collect all independent
shape errors, then reject if any. Do not proceed with partially valid tables.
Next group rows by primary ID. Exact identical rows collapse to one with
`DUPLICATE_COLLAPSED` and the number of extra copies. Any field disagreement
within an ID rejects as `CONFLICTING_ID`, even if a convenient order of rows
would appear to resolve it. Distinct IDs with matching values are not duplicates.

Then validate reversals and equal-recorded-date promises. A reversal must target
an existing original (`reversal_of = null`) receipt, on the **same line**, for
exactly the original positive quantity, with `posted_on >= original.posted_on`.
At most one distinct reversal may target an original. Reversing a reversal,
cycles, partial/oversized voids, unmatched targets, and repeated voids reject as
`INVALID_REVERSAL`. Validate structural reversal relations even when their
posting is future; only their *effect* is as-of filtered. Identical duplicate
reversal rows with the same ID collapse once.

For every `(line_id, recorded_on)` confirmation group recorded by as-of, all
`(confirmed_receipt, remaining_qty)` pairs must agree, including nulls.
Conflicting equal-date promises reject as `CONFLICTING_CONFIRMATION`, even on
an older eligible date or an orphan line. Future-recorded groups are not eligible
promise evidence and do not trigger this equal-date business comparison; their
field shape and same-primary-ID integrity still apply.
Any positive unmet requirement on a known cancelled line rejects as
`CANCELLED_LINE_DEMAND`.

Later quantity consistency uses actual reconciled open balances: all unique
requirements for a known non-cancelled line, **including beyond the horizon**,
must total no more than open quantity (`DEMAND_EXCEEDS_OPEN` otherwise).
The selected latest confirmation on a non-cancelled positive-open line must
have remaining quantity no greater than open quantity
(`CONFIRMATION_EXCEEDS_OPEN` otherwise), even when stale or outside scope.
Do not cap contradictory promises or drop excess requirements to obtain a pass.
A fully received or cancelled line retains confirmation evidence but does not
apply that remaining-quantity check or allocate supply.

Each fatal phase returns only that phase's fatal errors, not prior warnings,
with empty business outputs. A late quantity failure records the actual prior
stages and a repeated validation observation; it never emits a partial report.

### 3. Join purchase context (`join`)

Index schedule and supplier primary IDs. Group receipts, confirmations, and
requirements by exact `line_id`. Missing supplier master creates
`UNKNOWN_SUPPLIER`: preserve the exported supplier ID and null owner; known
line quantities/dates still support arithmetic and supplier-ID grouping.
No master or contact is fabricated. The buyer/material planner must resolve
unassigned work with procurement review.

Unknown line references produce `ORPHAN_RECEIPT`, `ORPHAN_CONFIRMATION`, or
`ORPHAN_REQUIREMENT`. Orphan receipt/confirmation rows cannot contribute to
known lines. Preserve every requirement with an unresolved-line assessment,
null coverage and shortage, and explicit unresolved quantity. Never interpret
null as zero availability or claim the unknown line has an open order.

### 4. Reconcile receipts (`decision`)

Only events with `posted_on <= as_of` have accounting effect. Each future event,
including a future reversal, gets `FUTURE_RECEIPT_EVENT`. Apply eligible full
voids by **removing the original receipt**, not by subtracting the quantity a
second time. A void removes its original even from historical on-time credit.
An eligible unvoided original is active; a future original is not active.

For each line, sum active receipts as `net_received_qty`; this is nonnegative.
`credited_received_qty = min(ordered_qty, net_received_qty)`.
`open_qty = ordered_qty - credited_received_qty`.
`overreceipt_qty = max(0, net_received_qty - ordered_qty)`; emit `OVERRECEIPT`
if positive. `open_qty` remains a nominal arithmetic balance on a cancelled
line, but that line never enters active-open totals, allocation, or the queue.

For a known deadline, `on_time_qty = min(ordered_qty, sum(active receipt qty
where posted_on <= deadline))`. Receipts must satisfy both as-of and deadline
boundaries. Unknown original date means null deadline and null on-time quantity,
not a fail or zero; emit `MISSING_REQUESTED_DATE` for every such line, including
cancelled lines. Preserve all linked, active, voided, applied-reversal, and
future event ID lists so every total is explainable.

### 5. Measure historical performance (`decision`)

Assign exactly one cohort status in this order:

1. `cancelled` if source state is cancelled.
2. `missing-requested-date` if original date is null.
3. `outside-reporting-month` if original date's month differs from config.
4. `future-requested-date` if original date is after as-of.
5. `included` otherwise.

Every non-included line appears once in `cohort_exclusions`; normal cancellation,
other months, and future requested dates are explanations, not extra exceptions.
Only included lines have boolean `otif`: true exactly when `on_time_qty`
equals ordered quantity, false otherwise. Confirmations never move the original
date or substitute for receipts. This is **line-count based**: split receipts
do not enlarge the denominator, and a large order is not weighted more heavily.

For overall and each supplier, `denominator = count(included lines)`,
`numerator = count(otif true)`. At denominator zero, `percent` and
`low_performance` are null. Otherwise `percent` is the exact rational
`100 * numerator / denominator` rounded **decimal half-up to two places**
and serialized as text without a percent sign (e.g. `"50.00"`).
Compute `low_performance` as `100*numerator < threshold*denominator` **before
rounding**, strictly below, never using the display string.

Included unsuccessful lines with `deadline > as_of` have
`performance_pending = true`, occur in `pending_line_ids`, and emit
`PENDING_TOLERANCE`. They remain in the stated denominator but are provisional:
the tolerance window can still receive evidence. Already-full included lines
are not pending even if their deadline is future. Non-included lines have
`otif = null` and `performance_pending = false`.

List suppliers from the union of supplied master IDs and line supplier IDs,
including unused masters and suppliers with no history. Do not fabricate a
0%/100% track record or buyer role. An empty **overall** cohort adds exactly one
`EMPTY_COHORT`; per-supplier empty histories are represented by nulls only.
This snapshot is not a final full-month ERP assessment. Future/unknown excluded
lines and pending tolerance make uncertainty explicit. Missing external
receipts cannot be discovered; calculations assume the supplied export's scope.

### 6. Select confirmations and scope (`join`)

Eligible evidence has `recorded_on <= as_of`, independently of its receipt
date. Per line choose greatest recorded date, then smallest confirmation ID
among equivalent equal-date promises. Earlier eligible IDs and unselected
equal-value ties are `superseded_confirmation_ids`; future-recorded IDs are
`future_confirmation_ids` and each produces `FUTURE_CONFIRMATION`.
Distinct agreeing IDs are not duplicate rows and do not multiply supply.

A line is in review scope if non-cancelled, positive-open, and at least one
condition holds: original date is unknown; known original date is through
`horizon_end`; or any pegged requirement is through `horizon_end`. There is
no lower date cutoff, so overdue work remains in scope. Historical inclusion
and review scope are independent.

Confirmation state precedence: `cancelled`; `not-open` for zero open quantity;
`missing` for no eligible selected record; `missing-eta` for a selected null
receipt date; `stale` for selected ETA strictly before as-of; `current`
otherwise. Selected fields remain visible even for cancelled/not-open lines.
Missing selection makes all four selected fields null. A same-day ETA is
current but **prospective**, never a posted receipt.

`supply_qty` is selected remaining quantity only for an in-scope `current`
line, otherwise zero usable prospective supply. In-scope missing, missing-ETA,
or stale states add the respective `MISSING_CONFIRMATION`, `MISSING_ETA`,
or `STALE_CONFIRMATION` exception. Out-of-scope or fulfilled lines do not
create those warnings merely because confirmation evidence is absent.

### 7. Allocate unmet requirements (`decision`)

A requirement is in scope exactly when `need_by <= horizon_end`.
Assessment precedence is unknown line (`unresolved-line`), then beyond horizon
(`outside-horizon`), then `allocated`. The first two have null covered/shortage
quantities. Unknown-line in-scope demand enters unresolved closure totals;
outside-horizon demand does not. Keep selected confirmation identity where the
line is known, even when outside scope or when the promise cannot cover it.

Within each known line, sort requirements by need date then ID. Start one local
remaining supply pool at that line's `supply_qty`. A requirement can draw only
if the selected ETA is current and `confirmed_receipt <= need_by`; coverage is
`min(unmet_qty, remaining pool)`, and subtract that coverage from the pool.
Otherwise coverage is zero and the pool is unchanged for later requirements.
`shortage_qty = unmet_qty - covered_qty`. Never share between lines, reuse a
pool for a second requirement, subtract historical receipts from unmet demand,
or make an out-of-horizon allocation. Criticality does not jump the documented
need-date/ID allocation order. Promise coverage is not inventory on hand.

### 8. Collect exceptions (`exception`)

Finalize the actual exceptions and unresolved evidence work. Each exception is
an object with exactly these base keys: nonempty string `code`, nonempty string
`message`, string `table` (logical table, `config`, or `payload`), `record_id`
(ID or null when no valid ID), and `field` (key string or null for a whole record
or cross-record issue). Optional fields are `related_id` (referenced ID), `count`
(positive integer extra identical copies removed), and `row_index` (zero-based
raw row index when a row has no valid primary identity). Do not add raw private
text or native evidence to exceptions.

Sort by `(code, table, record_id-or-empty, field-or-empty,
related_id-or-empty, row_index-or-minus-one, message)`, all text case-sensitive
ASCII. Only unidentified malformed rows depend on raw row indices.

Fatal codes and fixed message policy:

| Code | Message / identification |
| --- | --- |
| `MALFORMED_INPUT` | Field-specific messages: `Expected an object.`, `Missing required field.`, `Unknown field.`, `Expected an array with at most 200 rows.`, `Expected an ASCII identifier of 1-40 characters.`, `Expected a printable ASCII role of 1-80 characters without outer whitespace.`, `Expected YYYY-MM-DD in the range 2000-01-01 through 2100-12-31.`, `Expected YYYY-MM in the range 2000-01 through 2100-12.`, `Expected an integer from L through U.` with the documented decimal integer bounds substituted, `Expected one of: open, cancelled.`, `Expected one of: critical, normal.`, `Urgency must not exceed horizon days.`, or `Derived date exceeds 2100-12-31.`. Nullable validators accept null; otherwise use the same type message. |
| `CONFLICTING_ID` | `Rows with the same primary ID disagree.`; table, offending ID, primary-key field. |
| `INVALID_REVERSAL` | `Reversal must uniquely void an existing same-line receipt in full on or after its posting date.`; reversal ID, field `reversal_of`, related original ID. Each invalid reversal is reported, including each member of a repeated-void group. |
| `CONFLICTING_CONFIRMATION` | `Eligible confirmations recorded on the same date disagree.`; smallest ID in that conflicting group, field `recorded_on`, related line ID. |
| `CANCELLED_LINE_DEMAND` | `Unmet requirements on a cancelled line are contradictory.`; offending requirement, field `line_id`, related line ID. |
| `DEMAND_EXCEEDS_OPEN` | `Total unmet requirement quantity exceeds reconciled open quantity.`; schedule line, field `ordered_qty`. |
| `CONFIRMATION_EXCEEDS_OPEN` | `Latest remaining confirmation quantity exceeds reconciled open quantity.`; selected confirmation, field `remaining_qty`, related line ID. |

Nonfatal evidence codes and exact messages:

| Code | Message |
| --- | --- |
| `DUPLICATE_COLLAPSED` | `Identical rows with one primary ID were counted once.` |
| `FUTURE_RECEIPT_EVENT` | `Receipt event posted after as-of is excluded from receipt reconciliation.` |
| `FUTURE_CONFIRMATION` | `Confirmation recorded after as-of is excluded from promise selection.` |
| `ORPHAN_RECEIPT` | `Receipt references an unknown purchase line; excluded from receipt totals.` |
| `ORPHAN_CONFIRMATION` | `Confirmation references an unknown purchase line; excluded from promise selection.` |
| `ORPHAN_REQUIREMENT` | `Requirement references an unknown purchase line; coverage is unresolved.` |
| `UNKNOWN_SUPPLIER` | `Supplier master is missing; buyer ownership is unresolved.` |
| `MISSING_REQUESTED_DATE` | `Original requested receipt date is unknown; historical cohort is excluded.` |
| `OVERRECEIPT` | `Net receipt quantity exceeds ordered quantity; credited receipts are capped.` |
| `PENDING_TOLERANCE` | `Tolerance deadline is after as-of; the unsuccessful cohort result is provisional.` |
| `EMPTY_COHORT` | `No eligible purchase lines; performance percentage and low-performance flag are null.` |
| `MISSING_CONFIRMATION` | `No confirmation recorded by as-of for an in-scope open line.` |
| `MISSING_ETA` | `Latest confirmation has no receipt date for an in-scope open line.` |
| `STALE_CONFIRMATION` | `Past confirmed receipt date is not usable remaining supply.` |

Duplicate references use their table/primary field and `count`. Future events
use their own ID and `posted_on` or `recorded_on`. Orphans use their source ID,
`line_id`, and related missing line. Unknown suppliers use the schedule ID,
`supplier_id`, and related missing supplier. Date/pending warnings use the
schedule ID and `original_requested_receipt`; overreceipt uses `ordered_qty`.
Empty cohort uses schedule table, null record, and `original_requested_receipt`.
Missing confirmation uses schedule table/line ID and null field.
Missing/stale ETA uses the selected confirmation ID and `confirmed_receipt`.
Independent problems can generate multiple codes for the same source record.
Ordinary shortage, low history, and valid reversals are not errors by themselves.

### 9. Rank buyer work (`decision`)

Queue only in-scope positive-open lines with shortage, strictly overdue original
date (`original_requested_receipt < as_of`, not tolerance-adjusted), missing/
missing-ETA/stale confirmation, or unknown original date. No confirmation-free
fulfilled or cancelled line is queued.

Priority precedence: **P1** if any in-scope critical requirement has positive
shortage and `need_by <= urgency_end`, including overdue requirements; **P2**
otherwise if there is any in-scope shortage or a strictly overdue original
date; **P3** otherwise for remaining confirmation/original-date questions.
One line has one row regardless of how many questions it carries.

`earliest_need_by` is the minimum date of **all** its in-scope requirements,
including covered requirements; null if none. `shortage_qty` is the sum of
allocated in-scope requirement shortages, not open order quantity. Sort by
priority P1/P2/P3, earliest need ascending with null last, shortage descending,
then line ID ascending. Assign contiguous one-based `rank` after sorting.
History and buyer role join by supplier ID; neither changes allocated amounts.

Fixed reason and corresponding question ordering (skip false conditions):

| Reason | Condition and exact draft question |
| --- | --- |
| `critical-shortage` | P1; `Review uncovered critical demand and request a feasible receipt-date plan.` |
| `shortage` | Positive shortage but not P1, mutually exclusive with the preceding reason; `Review uncovered demand and request receipt-date evidence.` |
| `overdue-original` | Original date strictly before as-of; `Review the overdue original receipt date; any amendment needs buyer approval.` |
| `missing-confirmation` | Missing state; `Obtain a dated confirmation of remaining quantity and receipt date.` |
| `missing-eta` | Missing-ETA state; `Clarify the receipt date on the latest confirmation.` |
| `stale-confirmation` | Stale state; `Reconcile the past confirmed receipt date with posted receipts before using supply.` |
| `unknown-requested-date` | Null original date; `Resolve the missing original requested receipt date.` |

Every row has `send_status = "unsent"` and `approval_required = true`.
These are draft **questions**, not a sent email or authorized supplier promise.
Null buyer ownership must be resolved by procurement before any external action.

### 10. Close the report (`output`)

Reconcile every included/excluded line and the requirement totals. The closure
state is always `review-prepared`, owner `Buyer and material planner`, approval
required, `messages_sent = 0`, and `orders_changed = 0`. The boundary text is
exactly `Mock calendar-day review; no live purchasing or communication.`
Preparation may close with explicit unresolved work; that does not resolve the
underlying business issue or authorize execution.

## Exact result envelope and all business fields

The single JSON result object has **exactly**:

| Key | Type and meaning |
| --- | --- |
| `schema_version` | Integer `1`. |
| `status` | `completed` when the report has no exceptions; `completed_with_exceptions` for a completed report with one or more nonfatal evidence exceptions; `rejected` for a fatal validation phase. A shortage alone does not change status. |
| `outputs` | Object with the eight keys below on completion; exactly `{}` on rejection. |
| `exceptions` | Ordered array of the exception objects specified above; empty only for completed status. Rejection still exits successfully as a handled business result, not an infrastructure failure. |

Business keys on completion:

| Output | Container and ordering |
| --- | --- |
| `receipt_reconciliation` | One row per unique schedule line, ascending `line_id`. |
| `overall_performance` | One performance object. |
| `supplier_performance` | One supplier performance object per unioned supplier ID, ascending ID. |
| `cohort_exclusions` | Rows with exactly `line_id` (ID) and `reason` (non-included cohort status), ascending line ID. |
| `confirmation_review` | One row per unique schedule line, ascending line ID. |
| `requirement_coverage` | One row per unique requirement, ascending `(line_id, need_by, requirement_id)`. |
| `buyer_review_queue` | Ranked rows in the complete queue comparator above. |
| `review_closure` | One aggregate object. |

### Receipt reconciliation row

| Keys | Exact types/meaning |
| --- | --- |
| `line_id`, `supplier_id`, `item_id`, `state`, `ordered_qty`, `original_requested_receipt` | Preserve the validated schedule values and types. |
| `deadline` | Derived date or null for unknown original date. |
| `net_received_qty`, `credited_received_qty`, `open_qty`, `overreceipt_qty` | Nonnegative exact integers under the receipt formulas. |
| `on_time_qty` | Capped nonnegative integer, or null for unknown deadline. |
| `receipt_event_ids` | All unique linked event IDs, including future and reversal rows. |
| `active_receipt_ids` | As-of, non-voided positive receipt IDs. |
| `voided_receipt_ids` | Original receipt IDs voided by as-of. |
| `reversal_event_ids` | Applied as-of reversal IDs, not originals and not future voids. |
| `future_event_ids` | Linked event IDs posted after as-of, whether originals or reversals. |
| `cohort_status` | One of the five statuses in cohort precedence. |
| `otif` | Boolean for included line; null otherwise. |
| `performance_pending` | Boolean; true only for an included unsuccessful unelapsed tolerance window. |

All five ID arrays are distinct, ascending case-sensitive ASCII, without
duplicates. They are lineage sets, not chronological accounting order.

### Performance objects

Both overall and supplier objects contain exactly the following metric keys:
`numerator` and `denominator` (nonnegative integers), `percent` (two-place
decimal string or null), `low_performance` (boolean or null), `line_ids`
(ascending included line IDs), and `pending_line_ids` (ascending provisional
included line IDs). Supplier rows additionally contain `supplier_id` (ID) and
`buyer_role` (role string or null). Overall has no owner/ID fields.
Percent has no percent sign, thousands separator, exponent, or floating value.

### Confirmation review row

| Keys | Exact types/meaning |
| --- | --- |
| `line_id` | Schedule ID. |
| `confirmation_id`, `recorded_on`, `confirmed_receipt`, `remaining_qty` | Selected ID, date, nullable ETA, nonnegative integer respectively; all four are null if no selected confirmation. |
| `state` | `cancelled`, `not-open`, `missing`, `missing-eta`, `stale`, or `current` in the stated precedence. |
| `in_scope` | Boolean line review-scope predicate. |
| `supply_qty` | Nonnegative integer usable prospective pool before allocations; zero is not a posted receipt or an assertion that external inventory is zero. |
| `future_confirmation_ids`, `superseded_confirmation_ids` | Ascending unique source ID arrays, as defined in step 6. |

### Requirement coverage row

`requirement_id`, `line_id`, `need_by`, `unmet_qty`, and `criticality` preserve
the validated input types/values. `in_scope` is the boolean requirement horizon
predicate. `assessment` is `unresolved-line`, `outside-horizon`, or `allocated`.
`confirmation_id` is the known line's selected ID or null. `covered_qty` and
`shortage_qty` are nonnegative integers for allocated rows and both null for
the other assessments. No field is omitted because evidence is missing.

### Buyer queue row

`rank` is a positive integer; `line_id`/`supplier_id` are IDs; `buyer_role` is
a role or null; `priority` is `P1`, `P2`, or `P3`; `earliest_need_by` is a date
or null; `open_qty` is a positive integer; `shortage_qty` is a nonnegative
integer; `confirmed_receipt` is the selected ETA date or null (possibly stale,
never promoted to a receipt); `low_performance` is supplier boolean/null.
`reason_codes` is a nonempty ordered string array under step 9.
`draft_questions` is a same-length string array in one-to-one reason order,
using the exact texts above. `send_status` is the string `unsent`;
`approval_required` is boolean true. These are all row keys.

### Review closure object

| Keys | Exact types/meaning |
| --- | --- |
| `as_of`, `reporting_month` | Config date/month strings. |
| `horizon_end`, `urgency_end` | Derived inclusive date strings. |
| `tolerance_days`, `low_performance_percent` | Config integers. |
| `line_count` | Number of unique schedule lines, including cancelled. |
| `active_open_qty` | Sum of nominal open quantity on all non-cancelled lines, including outside review horizon. |
| `in_scope_unmet_qty` | Sum of all in-scope unmet requirements, including unknown-line demand. |
| `covered_qty`, `shortage_qty` | Sums on allocated in-scope requirement rows only. |
| `unresolved_requirement_count`, `unresolved_unmet_qty` | Count and unmet sum of in-scope unresolved-line requirements, not outside-horizon rows. |
| `queue_count`, `exception_count` | Exact lengths of queue and exceptions. |
| `state`, `owner_role`, `boundary` | Exact constant strings specified in step 10. |
| `approval_required` | Boolean true. |
| `messages_sent`, `orders_changed` | Integer zero, without exception. |

All counts/sums above are nonnegative integers. Always reconcile
`in_scope_unmet_qty = covered_qty + shortage_qty + unresolved_unmet_qty`.
Supplier included counts sum to overall denominator; successes sum to
overall numerator; included plus excluded lines equals line count.
Other than expressly ordered arrays, JSON object-key order is immaterial.
Booleans are not numbers. Nulls and zeroes are deliberately distinct.

## Public demo and developer baseline

The demo uses as-of 2026-09-14, September reporting, tolerance zero, horizon ten,
urgency three, and a below-90% history flag. P01 receives 60 on time and 40 late:
100 delivered but not OTIF. P03 delivers all 50 on its requested date. The exact
historical ratio is 1/2, displayed 50.00%. Future-requested P02/P04 are excluded.
P02's late ETA cannot cover its critical 50 due earlier; ten later needed units
can still draw once from that same promise pool. P04 lacks a confirmation.
The resulting P1 then P2 queue contains only buyer review questions.

For a **developer-only local baseline** from this scenario directory, with an
existing Python 3.11+ standard-library runtime, use fresh artifact paths:

```powershell
python -B baseline.py --input mock-data\demo.json --output baseline-output\manual-demo.json --trace baseline-output\manual-demo.trace.json
```

The standalone function is `solve(payload) -> (result, events)` and imports
only Python standard library plus the supplied `scenario_support.run_cli`.
The shared adapter writes JSON result and actual trace, binds trace to input
SHA-256, refuses existing outputs or input/output aliases, and does not read
evaluation answers. It does not perform business logic. No dependency install
is part of this procedure. Reusing an output filename fails explicitly; choose
a fresh pair instead of overwriting it. The authoritative shared pipeline has
separate controlled regeneration and evidence checking for developers.

Missing/unreadable files, invalid JSON bytes, unsupported encoding, duplicate
JSON keys, nonfinite JSON, invalid CLI paths, and unexpected runtime failures
are nonzero infrastructure failures, not successful business negatives.
Valid JSON with bad business data returns a rejected envelope with explicit
errors. The baseline does not mutate the input or any source documents.

## Actual trace and video boundary

Completed runs emit ten real deterministic stage snapshots in workflow order:
intake, validate-events, join-purchase-context, reconcile-receipts,
measure-performance, select-confirmations, evaluate-demand, collect-exceptions,
rank-queue, close-review. All six kinds occur; intake uses contract kind `input`.
Rejected cases may stop at validation; late capacity contradictions can show
previous observed stages and another validation event.

`events` is an array of objects with `step_id`, `kind`, nonempty `caption`
(at most 260 characters), `facts` (at most six named scalar JSON values), and
`tables` (one or two). Each table has `title`, one to six unique `columns`,
at most eight scalar-cell `rows`, `total_rows` including undisplayed rows, and
zero-based `highlight_rows` that refer only to displayed rows. Row widths match
columns. Tables show the first eight rows of the stated stable order and label
that subset only when more rows exist; long display cells may be truncated with
`...`, never the business results. Captions describe actual observations, not
a prerecorded successful script.

The helper adds contiguous one-based event `sequence` and wraps the trace in
`schema_version: 1`, `provenance: "synthetic-local-baseline"`,
`scenario_id: "manufacturing-02"`, `input_sha256` (64-character hex digest),
and `events`. There are no wall-clock dates in deterministic business results.
The parent/foundation will centrally render actual trace to
`demo/baseline.webm` with the label **Synthetic baseline execution visualization
- not Cowork or a live system**. A referenced video can be absent until that
rendering. No placeholder media, fake native screenshots, ZIP, or fabricated
native evidence should be created. Baseline stages prove local calculations,
not media comprehension, plugin creation, installation, or native execution.

## Native Creator staging and blocked gate

**Do not perform native creation, installation, publication, or invocation now.**
As of 2026-09-14, approved Computer Use tools **and** an unlocked accessible
session must both be restored, followed by parent-coordinated authorization.
No alternate browser, private API, token/cookie, shell, model/skill route,
custom runner, service, or installation bypass is permitted. Historical N00
publication was last `Publishing...`, outcome unknown, and Creator disabled.
The parent must inspect the real Installed state before any retry.

After the gate is actually cleared, the parent's Creator staging input is
**exactly this five-file allowlist**, with no additional files:

```text
HOW_TO.md
workflow.json
connections.json
mock-data/demo.json
demo/baseline.webm
```

Do not stage until the actual video exists. Record staging hashes separately
outside the Creator input directory. No implementation code, evaluator
material, source manifests, private cases, generated baseline reports, or
validation artifacts are inputs. The public research links are above.

The generated procedure must be implementable from this complete specification
and supplied logical-export payload, **without baseline source as native input**.
Ask the authorized Creator to prepare file-to-file review outputs under these
rules using only capabilities genuinely available in its host. Do not invent
native endpoints, connection identifiers, helper availability, or permissions.
Inspect the actual generated artifacts and installed state through approved
controls; read-only source inspection is not evidence of execution.

Only after actual creation and installation evidence may the parent perform an
independent native invocation with its separately controlled inputs, collect
real outputs and provenance, and compare them independently. Keep documented
procedure coverage, observed local stages, local result comparisons, and native
creation/install/invocation/comparison states separate. Local completion leaves
native creation blocked and installation/invocation/comparison not run.
