# Original-order returns and refund proposal reconciliation

## Purpose, authority and boundaries

A **returns reconciliation analyst** reviews a closed intake period. Store-service
staff supply synthetic requests, while finance-reporting staff supply original
orders, original lines and a complete opening return ledger. Link the independent
exports, establish original remaining entitlement, and prepare a review-only
proposal for every request, including unsuccessful requests.

All business identifiers are invented `SYN-` references; all business dates are
in 2099. Nothing authorizes a refund, card operation, customer contact, order
amendment, inventory return, disposition, fraud allegation, or determination of
legal rights. A historical `confirmed: true` value is evidence in a fixture,
**not execution permission**. The review packet always says
`action_authorized: false`.

Supported scope: whole units, one original invoice and one synthetic single-card
payment reference per order, separately recorded original paid merchandise and
allocated tax, and the two-decimal currencies USD, EUR, GBP, CAD and AUD. There is
no shipping, fee, exchange, serialized-item handling, mixed-tender allocation,
multiple capture, restocking fee, currency conversion, current-price lookup or
tax-rate computation. Do not invent missing information.

## Public evidence and invented policy

These exact public references were retrieved in the approved research on
**2026-09-14**:

* [Create returns in POS — Microsoft](https://learn.microsoft.com/dynamics365/commerce/pos-returns).
  The original-transaction return operation describes original receipt/order/
  invoice lookup, available-to-return quantities and return reasons. The sections
  on headquarters disconnection and partial-quantity tax describe stale offline
  quantities and preserving original tax. This procedure does not use the
  nonvalidated **Return product** operation.
* [Linked refunds of previously approved and confirmed transactions — Microsoft](https://learn.microsoft.com/dynamics365/commerce/dev-itpro/linked-refunds).
  Linked refunds refer to a previously approved and confirmed transaction and
  may be partial, bounded by original authorization. Operational execution needs
  payment configuration and connector prerequisites and excludes some
  multi-invoice, exchange, gift-card and receiptless flows.

Neither source specifies our return window, conditions, exact joins, cumulative
penny allocation, closed-opening certificate or quarantine rules. Those are
**invented sample company policy**, not a description of the complete Commerce
engine, statutory entitlement or production guidance. Our captured-money cap is
an additional conservative restriction. No source proves an offline export is
live. No new service access is needed to follow this procedure.

## Input: one standalone bundle of independent logical exports

Input is a finite UTF-8 JSON object with no duplicate JSON object keys. Every
object below has **exactly** its listed keys; missing and unknown fields are
invalid, including token/account fields. Arrays must actually be arrays; null is
not an empty export. Each export can be authored independently and bundled under
its own logical filename. Never join records by array index or filename.

The top-level keys are:

| Key | Type | Meaning |
| --- | --- | --- |
| `schema_version` | integer, exactly 1 | Boolean true is not version 1. |
| `source_files` | object | Exactly the five roles below, each mapped to a distinct filename string. |
| `files` | object | Exactly those five mapped filenames, each containing its export's JSON value; no other entries. |

The roles are `policy`, `original_orders`, `original_lines`, `prior_returns`,
and `requests`. Example mapping:

```json
{
  "policy": "return-policy.json",
  "original_orders": "original-orders.json",
  "original_lines": "original-lines.json",
  "prior_returns": "prior-returns.json",
  "requests": "return-requests.json"
}
```

Filenames are logical labels only: lowercase kebab-case followed by `.json`,
at most 80 characters; no path separators, traversal, drive names or reserved
device stems (`con`, `prn`, `aux`, `nul`, `com1` through `com9`, `lpt1` through
`lpt9`). Renaming all labels consistently must not change any decision.
There are no external file reads or native connections.

### Shared record domains

* Every identifier field (`*_id`, `sku`, `payment_reference`) is a string of at
  most 64 characters matching `SYN-[A-Z0-9]+(-[A-Z0-9]+)*`. Equality is exact and
  case-sensitive, with no trimming, prefix matching or fuzzy matching.
* A date is an actual calendar date written **exactly** `2099-MM-DD`. No time,
  timezone, abbreviated date, implicit current date or invalid leap day.
* Money is a nonnegative integer count of minor units. Quantity is a positive
  integer unless an output explicitly allows zero. Booleans, fractional JSON
  numbers (including `1.0`), numeric strings and null are not integers.
  Compute using exact integers, not binary floating point.
* A policy/reason/condition token is a lowercase kebab-case string of at most
  48 characters. A policy set is a nonempty array of distinct tokens.
* All booleans are actual JSON booleans. Row arrays may be empty. In particular,
  a certified empty opening history is explicit evidence of no posted events;
  a missing or uncertified history must not become zero.

### `policy` export: object

| Key | Type | Meaning |
| --- | --- | --- |
| `as_of` | date | Closed review date, supplied, never the system clock. |
| `period_start`, `period_end` | dates | Inclusive intake bounds; start <= end <= as_of. |
| `window_days` | nonnegative integer | Inclusive maximum calendar age since original purchase; zero allows same-day requests only. |
| `allow_partial_requests` | boolean | Whether an oversized request can receive only the available units. |
| `allowed_reasons`, `allowed_conditions` | token arrays | Exact sample-policy membership sets; their array order is immaterial. |

### `original_orders` export: array of objects

| Key | Type | Meaning |
| --- | --- | --- |
| `order_id` | identifier | Unique original order key. |
| `store_id`, `receipt_id` | identifiers | Their ordered pair must identify exactly one original order. |
| `invoice_id` | identifier | Unique original invoice; one per order, not shared across orders. |
| `purchased_on` | date | Original purchase calendar date. |
| `currency` | string enum | USD, EUR, GBP, CAD or AUD; no conversion. |
| `payment_reference` | identifier | Unique synthetic historical reference, never a token; not shared across orders. |
| `payment_method` | enum | `card`, `gift-card`, `mixed`, `other`; only `card` is within proposal scope. Other values in this enum trigger order quarantine, not reinterpretation as card. |
| `confirmed` | boolean | Original confirmation; false quarantines the whole order. |
| `authorized_minor`, `captured_minor` | nonnegative integers | Original payment amounts. Original line merchandise + tax must equal captured <= authorized. |

### `original_lines` export: array of objects

| Key | Type | Meaning |
| --- | --- | --- |
| `order_id`, `line_id`, `sku` | identifiers | Unique `(order_id,line_id)`; order must exist. SKU need not be unique across lines. |
| `fulfilled_qty` | positive integer | Original fulfilled whole units, called Q below. |
| `merchandise_paid_minor`, `tax_paid_minor` | nonnegative integers | Original allocated merchandise M and tax T, not a unit price or tax rate. |
| `returnable` | boolean | Original line returnability under sample policy. |

### `prior_returns` export: object

| Key | Type | Meaning |
| --- | --- | --- |
| `complete_before` | date | Exclusive closing boundary certified by the mock supplier; must equal period_start for usable eligibility. |
| `is_complete` | boolean | Must be true for usable eligibility. False or a mismatched boundary quarantines all original orders. This is a declared fixture certificate, not verified freshness. |
| `records` | array | Every history event, with the exact fields below. An explicit empty array is valid. |

Each event has:

| Key | Type | Meaning |
| --- | --- | --- |
| `return_event_id` | identifier | Globally unique event key. |
| `order_id`, `line_id` | identifiers | Original order/line references. |
| `posted_on` | date | Must precede period_start and not precede purchase, including voided and pending rows. |
| `state` | enum | `posted`, `voided`, `pending`. Posted consumes entitlement; voided contributes no quantity or money; pending quarantines its order. |
| `qty` | positive integer | Whole units described by the event. |
| `merchandise_minor`, `tax_minor` | nonnegative integers | Actual recorded historical money, kept separately. |

An event for a nonexistent original order has no safe quarantine boundary and
rejects the bundle (`unattributable-history`), not zero-history fallback. A
known order with an unknown line quarantines that entire order. All observed
posted rows remain visible in order-level raw totals, including mislinked and
non-opening rows. Line-level raw totals include only exact matching lines.

### `requests` export: array of objects

| Key | Type | Meaning |
| --- | --- | --- |
| `request_id` | identifier | Globally unique intake key. |
| `store_id`, `receipt_id`, `order_id`, `invoice_id`, `line_id`, `sku` | identifiers | All supplied original identifiers; none may override contradictory receipt evidence. |
| `requested_on` | date | Intake date, used for stable processing order. |
| `requested_qty` | positive integer | Units asked for; may exceed available quantity. |
| `reason`, `condition` | tokens | Supplied reason and physical-condition category; syntax is validated, then policy membership is evaluated. |

## Complete ordered procedure

1. **Load named exports.** Resolve only the five mapped values in the bundle.
   Capture actual row counts, policy bounds and declared history completeness.
   Missing or malformed values cannot be guessed from another role.
2. **Validate before deciding.** Check bundle shape and mapping, policy, original
   orders, original lines, history certificate/events and requests, in that
   order. Within each role check the field order in the tables above (the
   original-line numeric fields follow its three identifiers). Check one row
   at a time in supplied order for malformed fields. After all fields pass,
   check primary keys in role order: orders, lines, history, requests; then
   store/receipt ambiguity, shared invoice/reference keys, line order foreign
   keys and history order foreign keys. Return the first structural error as a
   `rejected` result, `outputs: {}`, with exactly one input exception.
3. **Join every request before allocating.** Look up exact `(store_id,receipt_id)`.
   No match means `unknown-receipt`, unresolved, with no attributed order or
   money. Even a supplied known order ID cannot substitute for an unknown
   receipt. Otherwise verify supplied order/invoice, then `(order_id,line_id)`,
   then SKU. The join outcome is `matched`, `conflicting-identifiers`,
   `missing-line`, or `sku-mismatch` in that precedence. A contradiction
   quarantines the receipt-resolved order and any existing order separately
   referenced by the supplied order ID or invoice ID. Do this for the entire
   batch before considering earlier requests, so a late contradiction cannot
   leave earlier proposals live. Unknown receipts alone do not quarantine
   their unverified claimed order.
4. **Reconcile original and opening evidence for every order**, even if it has
   no requests. Require at least one original line, single-card method,
   confirmation, line totals equal captured, and captured <= authorized.
   Require the opening certificate to be complete with its boundary exactly
   period_start. Check every event's state, date and line link; never silently
   ignore a pending, current-period or future event. Dates are strictly before
   period_start, not merely <= as_of. Void rows consume nothing, but their
   references/dates must still be coherent. Sum posted quantity, merchandise and
   tax per exact original line. For total posted quantity r, require r <= Q,
   recorded merchandise = E(M,r,Q) and recorded tax = E(T,r,Q).
   If r > Q report only the quantity error for that line, not a derived
   out-of-domain entitlement error. Any fault quarantines **every line and
   request of the affected order**, not just the failing line.
5. **Apply policy to matched, nonquarantined requests.** Sort globally by
   `(requested_on,request_id)` ascending, using ordinary string ID ordering.
   Compute age as date difference in calendar days. Collect all applicable
   exclusions in this exact order: outside inclusive reporting period;
   purchase after request; age > window; original nonreturnability; disallowed
   reason; disallowed condition. Age is retained even when negative. An
   excluded request is `ineligible` and consumes nothing. Quarantine and
   unknown-receipt take precedence over these policy tests.
6. **Reserve hypothetical quantity.** For each safe original line let r be
   validated posted prior quantity and b earlier proposed quantity in the
   globally ordered batch. Available = Q-r-b. For an otherwise eligible
   request n: if available=0, defer all with `quantity-exhausted`. If n >
   available and partial is disabled, defer all with `partial-not-allowed`
   and consume **zero**. Otherwise propose a=min(n,available); a<n is `partial`
   with `partial-quantity`, otherwise `proposed`. Defer n-a in all outcomes.
   This is an unfulfilled review quantity, not a promise of later acceptance.
7. **Allocate original pennies, never current prices.** Define E(A,q,Q) as
   ROUND_HALF_UP(A*q/Q) to integer minor units. For nonnegative integers it is
   exactly `(2*A*q + Q) // (2*Q)`, where `//` is integer floor division.
   Independently allocate merchandise E(M,...) and tax E(T,...).
   The new merchandise is E(M,r+b+a,Q)-E(M,r+b,Q); tax is the corresponding
   tax difference. Do not round a per-unit price and multiply it. Record the
   cumulative quantity and both entitlements before and after each request.
   A known safe zero proposal has equal before/after entitlements. Unknown or
   quarantined eligibility has null entitlements, not fabricated zero history.
   Only add proposed quantities to b.
8. **Verify controls before release.** For each safe order prior+proposed money
   must not exceed captured or authorized. If this last guard fails, quarantine
   the whole order and withdraw all its provisional allocations, then rebuild
   its request and line controls. Do not release a partial unsafe ledger.
   Remaining line money is original minus cumulative money at r+b, not remaining
   units times rounded unit price. At complete return, original merchandise and
   tax are separately conserved. A safe order's remaining money equals captured
   minus prior minus new; original and safe currency controls must balance.
9. **Publish exceptions and review artifacts.** Sort order exceptions by
   `(entity_id,code,message)` first; exact repeated exceptions are emitted once.
   Follow them with request exceptions in request processing order and the
   exclusion precedence above; append the single quantity code when applicable.
   No incidental source-array ordering affects accepted results or traces.
   Produce every original line and order, including quarantined ones, and every
   request. Do not omit zeros. All money totals remain separated by currency.

### Demo arithmetic

On July 2, a June 12 original line Q=3, M=1000, T=100 has one posted prior unit
with M=333 and T=33. The first one-unit request advances cumulative entitlements
to M=667,T=67: new M=334,T=34,total=368. A second request asks two but only one
remains: new M=333,T=33,total=366; defer one. New total **734**, and prior
366 + new734 = original1100. A June1 purchase is age31, outside a 30-day window.
An unknown receipt has no original payment attribution and remains unresolved.

## Exact result schema

The result has **only** these four top-level keys:

| Key | Type | Meaning |
| --- | --- | --- |
| `schema_version` | integer 1 | Common output version. |
| `status` | enum | `rejected` for structural failure; otherwise `completed_with_exceptions` when any exception exists, or `completed` when none exists. |
| `outputs` | object | Empty for rejection; otherwise exactly the five artifacts below. |
| `exceptions` | array of objects | Ordered exceptions with exactly `code`, `message`, `scope`, `entity_id`. No hidden ignored fields. |

Each exception's `code` and `message` are nonempty strings. `scope` is `input`,
`order` or `request`. `entity_id` is a string: input role/record key for structural
errors, original order ID for quarantine, request ID for request review. A line
key in input errors is `order_id/line_id`; a receipt key is `store_id/receipt_id`.
For missing/malformed primary identifiers or row shapes use the role name; for
policy/bundle/history-header failures use `policy`, `bundle`, `prior_returns`.

### `outputs.request_proposals`: array, sorted by requested_on/request_id

| Key | Type | Meaning |
| --- | --- | --- |
| `request_id`, `requested_on` | identifier, date | Original intake identity and processing date. |
| `supplied_keys` | object | Exactly `store_id`, `receipt_id`, `order_id`, `invoice_id`, `line_id`, `sku` as submitted, all identifiers. |
| `reason`, `condition` | strings | Submitted tokens. |
| `requested_qty` | positive integer | Original request, never clipped. |
| `join_status` | enum | `matched`, `unknown-receipt`, `conflicting-identifiers`, `missing-line`, `sku-mismatch`. |
| `original` | object or null | Null only for unknown receipt; otherwise exactly `order_id`, `store_id`, `receipt_id`, `invoice_id`, `line_id`, `sku`, `currency`, `payment_reference`. The first four and last two come from receipt-resolved original order. `line_id` and `sku` are identifiers when an exact supplied line exists on that order, otherwise null; they are not untrusted supplied values. |
| `disposition` | enum | `proposed`, `partial`, `deferred`, `ineligible`, `unresolved`, `quarantined`, as defined in steps above. |
| `reason_codes` | array of strings | This request's exception codes in precedence order; empty for full proposal. Order-level cause codes belong to order controls, not duplicated here. |
| `age_days` | integer or null | Calendar age from resolved purchase, including negative age; null only for unknown receipt. |
| `prior_qty`, `earlier_proposed_qty`, `available_qty` | nonnegative integers or null | Opening validated quantity, earlier batch reservations and Q-prior-earlier at this request. All null when unresolved/quarantined. |
| `proposed_qty`, `deferred_qty` | nonnegative integers | New proposal and requested-proposed; zero proposal for unresolved/quarantined/ineligible/deferred. |
| `entitlement_before`, `entitlement_after` | object or null | Exactly `qty`, `merchandise_minor`, `tax_minor`, all nonnegative integers. Before is cumulative prior+earlier; after adds this proposal. Both null when unresolved/quarantined. |
| `proposed_merchandise_minor`, `proposed_tax_minor`, `proposed_total_minor` | nonnegative integers | Separate cumulative differences and their sum; zero is the actual absence of a new proposal, not a history assumption. |

### `outputs.line_eligibility`: array, sorted by order_id/line_id

| Key | Type | Meaning |
| --- | --- | --- |
| `order_id`, `line_id`, `sku`, `currency` | strings | Original identifiers/currency. |
| `quarantined` | boolean | True for every line of an affected order. |
| `original_qty` | positive integer | Fulfilled Q. |
| `original_merchandise_minor`, `original_tax_minor` | nonnegative integers | Original M and T. |
| `observed_posted_qty`, `observed_posted_merchandise_minor`, `observed_posted_tax_minor` | nonnegative integers | Raw sums of all posted exact-line events, including contradictory or non-opening ones. Not authoritative eligibility. Voided/pending values do not enter these raw posted sums. |
| `prior_qty`, `prior_merchandise_minor`, `prior_tax_minor` | nonnegative integers or null | Validated opening values; null for whole-order quarantine. |
| `proposed_qty`, `proposed_merchandise_minor`, `proposed_tax_minor` | nonnegative integers | Batch proposals on the line; zero for quarantine. |
| `remaining_qty`, `remaining_merchandise_minor`, `remaining_tax_minor` | nonnegative integers or null | Original minus authoritative prior and proposals; null for quarantine. |

### `outputs.order_money_controls`: array, sorted by order_id

| Key | Type | Meaning |
| --- | --- | --- |
| `order_id`, `currency`, `payment_reference`, `payment_method` | strings | Original order/payment identity, never operational instructions. |
| `confirmed`, `quarantined` | booleans | Original confirmation and computed quarantine. |
| `reason_codes` | array of strings | Distinct order cause codes sorted lexicographically. |
| `authorized_minor`, `captured_minor` | nonnegative integers | Observed original payment amounts, including quarantined originals. |
| `original_merchandise_minor`, `original_tax_minor`, `original_total_minor` | nonnegative integers | Sum of original line merchandise, tax and their sum, even when inconsistent with capture. |
| `observed_posted_minor` | nonnegative integer | Raw posted merchandise+tax for all this order's events, including unmatched lines. |
| `prior_minor` | nonnegative integer or null | Validated opening refund total; null for quarantine. |
| `proposed_merchandise_minor`, `proposed_tax_minor`, `proposed_minor` | nonnegative integers | New proposal sums; zero for quarantine. |
| `prior_plus_proposed_minor`, `remaining_minor` | nonnegative integers or null | Authoritative projected refund and captured minus it; null for quarantine. |
| `cap_ok` | true or null | True only for a reconciled, within-cap order. Quarantine is null, not a claim the order passed. |

### `outputs.currency_controls`: array, sorted by currency

Each object has a string `currency`, integer `order_count`,
`quarantined_order_count`, `reconciled_order_count`, and nonnegative integer
money fields `captured_minor`, `reconciled_captured_minor`, `prior_minor`,
`proposed_merchandise_minor`, `proposed_tax_minor`, `proposed_minor`,
`prior_plus_proposed_minor`, `remaining_minor`.

`captured_minor` sums **all observed** originals of that currency. All other
money fields sum **only reconciled orders**, including explicit zero when there
are none. Counts disclose this exclusion; zero must never imply that quarantined
orders have zero historical refunds or zero remaining entitlement. Unknown
receipts cannot be assigned a guessed currency and contribute no money. There
is no grand money total across currencies.

### `outputs.review_packet`: object

| Key | Type | Meaning |
| --- | --- | --- |
| `action_authorized` | false | Required literal; proposals grant no authority. |
| `owner_role` | string | Exactly `Returns reconciliation analyst`. |
| `as_of`, `period_start`, `period_end` | dates | Exact supplied review dates. |
| `window_days`, `allow_partial_requests` | integer, boolean | Exact applied sample-policy settings. |
| `request_count`, `proposed_qty`, `deferred_qty`, `exception_count` | nonnegative integers | Request count, sums of the indicated request quantities and exact exception count. No cross-currency money sum. |
| `unresolved_request_ids` | identifier array | Unknown receipts in request processing order. |
| `quarantined_order_ids` | identifier array | Affected originals sorted by ID. |
| `review_request_ids` | identifier array | All non-`proposed` requests, including partial requests, in processing order. |
| `next_actions` | string array | Exactly the three review instructions below, in order. |

The exact `next_actions` strings are:

1. `Verify source completeness and resolve every exception with the original transaction owner.`
2. `Review proposals against current authorized return and payment policy; this packet grants no approval.`
3. `Use an authorized operational process only after separate approval; no refund, order or stock change was executed.`

## Exact exception codes and messages

Braces below denote literal substitution of the actual field, role or identifier,
not braces in the returned message. Messages include the punctuation shown.
Input validation emits the first failure only. Type/domain failures use
`invalid-policy` for policy fields and `invalid-record` for export rows or the
history certificate. Their field label is `role.field` (no filename/index).
The bundle/mapping failure code is `invalid-bundle`.

| Code / situation | Exact message |
| --- | --- |
| invalid-bundle, schema version | `bundle.schema_version must be the integer 1.` |
| invalid-bundle, wrong object shape | `{label} must be an object with exactly these keys: {keys}.` |
| invalid-bundle, mapping filename | `source_files.{role} must be a safe lowercase kebab-case JSON filename.` |
| invalid-bundle, repeated filename | `source_files must map every role to a distinct filename.` |
| invalid-bundle, file labels | `files must contain exactly the mapped logical filenames.` |
| invalid-policy/record, wrong object shape | `{label} must be an object with exactly these keys: {keys}.` |
| invalid-record, wrong row array | `{role} must be an array of records.` |
| invalid-policy/record, identifier | `{field} must be a synthetic SYN- identifier of at most 64 characters.` |
| invalid-policy/record, date | `{field} must be a YYYY-MM-DD date in 2099.` |
| invalid-policy/record, positive integer | `{field} must be a positive integer; booleans and fractions are invalid.` |
| invalid-policy/record, nonnegative integer | `{field} must be a nonnegative integer; booleans and fractions are invalid.` |
| invalid-policy/record, boolean | `{field} must be a boolean.` |
| invalid-policy/record, token | `{field} must be a lowercase kebab-case string of at most 48 characters.` |
| invalid-policy, allowed token array | `{field} must be a nonempty array of distinct lowercase kebab-case strings.` |
| invalid-record, enum | `{field} must be one of: {values}.` |
| invalid-policy, chronology | `policy dates must satisfy period_start <= period_end <= as_of.` |
| duplicate-key | `{role} repeats primary key {key}.` |
| duplicate-key, invoice/reference | `original_orders repeats {field} {key}.` |
| ambiguous-receipt | `original_orders contains multiple orders for store/receipt {key}.` |
| unknown-original-order | `original_lines references unknown order {order_id}.` |
| unattributable-history | `History event {return_event_id} references an unknown original order; no safe quarantine boundary exists.` |

For shape messages, `{label}` is `bundle`, `source_files`, `files`, `policy`,
the row role, or `prior_returns` for its certificate/header and events. `{keys}`
is the required key set sorted lexicographically and joined by comma-space.
Enum `{values}` is its allowed set sorted lexicographically and joined by
comma-space. Validation uses the row's primary identifier as `entity_id` when
it is syntactically valid, otherwise the role; line keys require both IDs.
Duplicate and ambiguity keys become `entity_id`. Foreign-key failures use the
line's composite key or the history event ID.

The following **order-scope** codes each quarantine the entire `entity_id`
order. Multiple independent faults are all reported, sorted as specified.

| Code | Exact message |
| --- | --- |
| contradictory-request-evidence | `Request {request_id} has contradictory original identifiers; quarantine the whole order.` |
| missing-original-lines | `No original lines exist for this order; quarantine the whole order.` |
| unsupported-payment-method | `Original payment method is not a single card; quarantine the whole order.` |
| payment-not-confirmed | `Original payment is not confirmed; quarantine the whole order.` |
| capture-exceeds-authorization | `Captured amount exceeds original authorization; quarantine the whole order.` |
| original-payment-mismatch | `Original line merchandise plus tax does not equal captured amount; quarantine the whole order.` |
| history-not-closed | `Opening history is not certified complete strictly before period_start; quarantine the whole order.` |
| pending-history | `History event {return_event_id} is pending; quarantine the whole order.` |
| non-opening-history | `History event {return_event_id} is not strictly before period_start; quarantine the whole order.` |
| history-before-purchase | `History event {return_event_id} predates the original purchase; quarantine the whole order.` |
| unknown-history-line | `History event {return_event_id} references an unknown original line; quarantine the whole order.` |
| prior-quantity-exceeds-fulfilled | `Posted quantity exceeds fulfilled quantity on line {line_id}; quarantine the whole order.` |
| prior-entitlement-mismatch | `Posted merchandise or tax disagrees with cumulative entitlement on line {line_id}; quarantine the whole order.` |
| refund-cap-exceeded | `Prior plus proposed refunds exceed captured or authorized money; quarantine the whole order.` |

The following **request-scope** messages are exact and become the request's
`reason_codes`. Unknown receipt or quarantine emits only that request code;
otherwise all policy exclusions are collected in table order. Quantity codes
are mutually exclusive and apply only if policy passed.

| Code | Exact message |
| --- | --- |
| unknown-receipt | `No original order matches the exact store/receipt; unresolved, not an accusation.` |
| order-quarantined | `The original order is quarantined; propose zero pending evidence review.` |
| request-outside-period | `Request date is outside the inclusive reporting period.` |
| purchase-after-request | `Request date precedes the original purchase date.` |
| return-window-exceeded | `Request age exceeds the configured inclusive return window.` |
| original-not-returnable | `The original line is not returnable under the sample policy.` |
| reason-not-allowed | `Return reason is not allowed by the sample policy.` |
| condition-not-allowed | `Item condition is not allowed by the sample policy.` |
| quantity-exhausted | `No original fulfilled quantity remains after prior returns and earlier proposals.` |
| partial-not-allowed | `Requested quantity exceeds remaining quantity and partial requests are disabled.` |
| partial-quantity | `Only the remaining quantity is proposed; defer the unfilled requested quantity.` |

## Trace, human review and local development

Capture actual stages, not repeated answers or predetermined captions. The
workflow's nine steps correspond to source counts; schema validation; receipt/
line joins; opening quantity/money checks; age/condition decisions; ordered
reservations; before/after merchandise/tax pennies and payment caps; exceptions;
and final currency/review summaries. The first event is input and last is output.
Structural negatives can stop after input and validation.

Each event has `step_id`, `kind`, a caption at most 260 characters, at most six
scalar `facts`, and one or two tables. Each table has `title`, one to six string
`columns`, at most eight scalar-cell `rows`, actual `total_rows`, and valid
zero-based `highlight_rows`. Larger stages show a stable first-eight-row subset,
not a claim that hidden rows were processed differently. The CLI adds contiguous
one-based `sequence` and wraps events with `schema_version:1`,
`provenance:"synthetic-local-baseline"`, `scenario_id:"retail-02"`,
and `input_sha256` binding the actual input bytes.

The analyst checks every exception, raw versus authoritative history, all
original-to-payment controls, cumulative pennies, unknown receipts and excluded
currency amounts. Quarantined controls are null on purpose: obtain corrected
complete evidence, then perform a separate review rather than edit totals to
make them fit. A subsequent financial/stock action requires its own authorized
operational process; this procedure never performs it.

For local developers, from this folder, with **fresh** destination paths:

```powershell
python -B baseline.py --input mock-data\demo.json --output baseline-output\manual-demo.json --trace baseline-output\manual-demo.trace.json
```

This executes trusted standard-library reconciliation only, not Creator. The
adapter refuses existing output paths and returns nonzero for invalid JSON bytes,
I/O failures or unexpected defects. A well-formed business rejection is an
explicit `rejected` JSON result with exit zero. Native implementation must follow
the procedure above independently, not rely on this command or source code.

The centrally produced demonstration video, when available, visualizes these
actual synthetic trace tables, facts and highlights. It must be labeled
**Synthetic baseline execution visualization - not Cowork or a live system**.
A missing video is a missing prerequisite, not permission to fabricate one.

## Native authoring, installation and independent execution gate

As of **2026-09-14**, approved **Computer Use tools were removed** and the session
is not an unlocked accessible native-authoring session. Native creation,
installation and independent execution remain blocked. **Both** the approved
tools and an unlocked accessible session must be restored, and parent-coordinated
authorization is required before any native action.

There is **no alternate browser, private API, cookie, token, shell, model or skill
route** around this gate. Do not call a payment API or configure a connector.
Historical N00 publication was last `Publishing...`; its outcome is **UNKNOWN**,
not Installed, and Creator was disabled. Inspect actual Installed state before
any retry after the gate is legitimately restored.

Once legitimately unblocked, the authorized operator supplies Creator only:
this `HOW_TO.md`, `workflow.json`, `connections.json`, the standalone
`mock-data/demo.json`, and the centrally rendered `demo/baseline.webm`. Creator
must implement the schema, exact joins, precedence, cumulative arithmetic,
quarantine and review artifacts described here, using mock bundle inputs only.
If the video is absent, wait for the central producer; do not create a placeholder.

Inspect the generated artifact read-only first; installation and an independent
invocation in the real native surface need their own observed evidence and
authorization. Never blindly execute a downloaded artifact. Supply a bundle to
the independently authored native process and obtain its complete result and
review packet; never substitute a local baseline invocation for native execution.
Record actual creation, installation and invocation outcomes separately. Local
calculations, a ZIP, or historical publication do not prove native creation,
Installed state, execution or success.
