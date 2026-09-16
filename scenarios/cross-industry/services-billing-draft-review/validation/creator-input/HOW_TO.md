# Professional Services: time and expense billing draft review

## Purpose, owner and stop boundary

A project accountant receives a frozen set of synthetic time, expense,
approval, rate, prior-billing and invoice-draft exports. Produce a **local
review packet**, not an invoice: candidate charges, definite exclusions,
evidence holds, exact draft-detail differences, project cap calculations,
currency-separated subtotals and owned human-review items.

All clients, people, receipts, owners and transaction identifiers are fictional.
Only supplied exported files are used. No connection, account, credential,
network request, real customer data or product installation is required.
Never approve or recall time, reimburse an expense, create/send an invoice,
confirm a proforma, create financial actuals, post AR/GL, contact customers,
or decide taxes or FX. “Add”, “update” and “remove” below mean **proposed
local review diagnostics**, never changes to a business system.

### Research context versus fictional policy

These primary documents were fetched and checked on 2026-09-14:

- [Approvals overview](https://learn.microsoft.com/dynamics365/project-operations/approvals/approvals-overview):
  Project Operations approval records concern time/expense/material entries;
  approval creates actuals and cancel/recall can reverse them. We only read
  synthetic decision evidence.
- [Proforma invoices](https://learn.microsoft.com/dynamics365/project-operations/proforma-invoicing/create-manual-proforma-invoice):
  Project Operations Integrated with ERP adds draft review of approved,
  unbilled transactions before confirmation. We do not implement that product.
- [Confirm a proforma project-based invoice](https://learn.microsoft.com/dynamics365/project-operations/proforma-invoicing/confirm-proforma-invoice):
  confirmation makes the invoice read-only and creates financial actuals.
  This procedure stops before that boundary.

The documents establish context, **not** our field schema, rates, receipt
rules, revision precedence, rounding, tolerances or caps. All those rules are
explicit fictional sample policy. These neutral exports are not a Dynamics
API or import schema, a general accounting standard, or legal/tax advice.

## Input attachment and exact field dictionary

Read a single UTF-8 JSON object with exactly `config` and `files`.
`files` contains exactly the nine named arrays below. Logical names such as
`projects.json` are table labels **inside the attachment**, not filesystem
paths to open. Every array may have zero, one or many rows. Do not infer
missing tables, fields, policy, approval, rates, defaults or joins.

Types used below:

| Type | Exact representation |
|---|---|
| ID | Nonempty JSON string with no leading/trailing whitespace. Case-sensitive, never coerced from a number. |
| currency | Exactly three uppercase ASCII letters. Preserve the supplied code; no conversion or whitelist inference. |
| money | Nonnegative finite decimal **string**, regex `(?:0|[1-9][0-9]*)\.[0-9]{2}`. No sign, exponent, comma, leading zeros, or numeric JSON value. Zero is permitted. |
| positive integer | JSON integer greater than zero. Booleans and decimal/numeric strings are not integers. |
| boolean | JSON `true` or `false`, never an integer or text. |
| date | Valid canonical `YYYY-MM-DD` calendar date. |
| instant | Valid `YYYY-MM-DDTHH:MM:SSZ` or `YYYY-MM-DDTHH:MM:SS+HH:MM`/`-HH:MM`; explicit offset, whole seconds only. Normalize to UTC for comparison/output. |
| nullable ID | ID or JSON `null`; empty/whitespace-only receipt strings are malformed, not evidence. |
| enum | One of the exact case-sensitive strings specified. |

No unknown object keys are ignored. Reject malformed row types/fields, missing
keys, invalid intervals, invalid amounts or duplicate primary keys before
computing business outputs. Invalid JSON bytes, duplicate JSON object keys,
nonfinite numbers, excessive nesting or unreadable files are file errors, not
successful business rejections.

`config` has exactly:

| Key | Type and meaning |
|---|---|
| `as_of` | instant; inclusive cutoff for recorded approvals and billed transactions. |
| `period_start` | date; inclusive service-period start. |
| `period_end` | date; exclusive service-period end, strictly later than start. |
| `draft_tolerance` | money; must be exactly `"0.00"` for this procedure. Other tolerance values are unsupported, not silently used. |

The row dictionaries below enumerate **every required key**. Primary keys
must be unique within their logical array, even for otherwise identical rows.
Time and expense IDs occupy separate namespaces.

| Export / primary key | Required row keys and types |
|---|---|
| `projects.json` / `project_id` | `project_id`: ID; `client_id`: ID; `contract_id`: ID; `currency`: currency; `period_cap`: money; `owner`: ID of the synthetic human review owner. |
| `rates.json` / `rate_id` | `rate_id`: ID; `project_id`: ID; `role_code`: ID; `currency`: currency; `valid_from`: date inclusive; `valid_to`: date exclusive and later than `valid_from`; `hourly_rate`: money. |
| `time-entries.json` / `time_id` | `time_id`: ID; `project_id`: ID; `person_id`: ID; `role_code`: ID; `service_date`: date; `minutes`: positive integer; `chargeable`: boolean. Time currency comes only from the project join. |
| `expense-entries.json` / `expense_id` | `expense_id`: ID; `project_id`: ID; `person_id`: ID; `service_date`: date; `category`: ID; `amount`: money; `currency`: currency; `receipt_reference`: nullable ID; `chargeable`: boolean. |
| `approval-events.json` / `approval_event_id` | `approval_event_id`: ID; `entry_type`: enum `time` or `expense`; `entry_id`: ID in that namespace; `revision`: positive integer; `recorded_at`: instant; `decision`: enum `approved`, `pending`, `rejected`, `recalled`. |
| `billed-transactions.json` / `billed_id` | `billed_id`: ID; `entry_type`: enum `time` or `expense`; `entry_id`: ID; `project_id`: ID; `invoice_id`: ID; `service_date`: date; `amount`: money; `currency`: currency; `billed_at`: instant. Historical entry IDs may be absent from current intake. |
| `draft-invoices.json` / `draft_id` | `draft_id`: ID; `project_id`: ID; `currency`: currency; `period_start`: date inclusive; `period_end`: date exclusive and later than start; `state`: enum `draft` only. |
| `draft-lines.json` / `line_id` | `line_id`: ID; `draft_id`: ID; `entry_type`: enum `time` or `expense`; `entry_id`: ID; `amount`: money. Currency and project come from the header, not an inferred line field. |
| `expense-policies.json` / (`category`, `currency`) | `category`: ID; `currency`: currency; `max_amount`: money per expense; `receipt_required_at`: money, inclusive threshold. |

## Joins and comparison scope

1. Time/expense `project_id` -> project, supplying owner/client/contract/currency/cap.
2. Time -> rate where project, role and **project currency** match and
   `valid_from <= service_date < valid_to`; exactly one effective row is needed.
3. Expense -> policy by `(category, currency)`; expense and project currencies
   must agree before applying that policy.
4. Approval/prior-billed/detail -> `(entry_type, entry_id)`. Never join on ID alone.
5. Detail `draft_id` -> header -> project, currency and exact service period.
6. Raw prior billing -> project, independently of current time/expense presence.
   A prior row counts toward cap if its project/currency is valid,
   `billed_at <= as_of` and its own `service_date` lies in the configured period.

Current prior-billing identity must agree with the source project, currency
and service date. Multiple as-of billed rows for one current entry are
ambiguous because credits/partial billing are outside scope. Do not infer
deduplication or a remaining balance. Valid raw ledger amounts still count
toward their stated project's cap even when a current source identity is
contradictory: dropping posted history would understate consumption.

An active draft has exactly the configured period. Different-period draft
headers and all their lines are explicitly deferred, never changed. More than
one active draft for a project, duplicate current-period details for an entry,
missing headers/source entries, or wrong header project/currency are
clarification items, not an arbitrary choice of invoice or removal.
Missing project/rate/policy joins are local quarantines. Unmatched as-of
approval rows and rates referencing missing projects become owned export
review issues. Future approval rows never establish a business join or decision.

## Ordered procedure (independent of any development code)

### 1. Intake and freeze

Inventory all nine arrays, their row counts, the cutoff, and half-open period.
Read only the supplied attachment; keep it unchanged. Normalize the cutoff
to whole-second UTC ending `Z`. Retain source IDs throughout the packet.

### 2. Validate the entire bundle

Check exact dictionaries, every row and type, unique primary keys and valid
date ranges. An expense negative amount is invalid, not a credit. Collect
field-specific errors with stable messages; reject the complete bundle with
`outputs: {}` and `fix-input` exceptions. Do not calculate a “good rows” packet
from a malformed bundle. A well-formed but contradictory join is handled in
the following steps, not disguised as malformed syntax.

### 3. Cross-reference independent evidence

Build the six joins above and retain all matched approval/billing/detail IDs.
Count raw source-absent history rather than requiring a source entry.
Expose missing joins, wrong project/currency/service date, duplicate details,
and multiple active drafts. Two rows sharing a primary ID reject intake;
two distinct IDs asserting conflicting business evidence quarantine it.

### 4. Select as-of approval and resolve eligibility

Filter approval events using `recorded_at <= as_of`. Ignore and retain the IDs
of future events. Among remaining events choose the largest integer revision.
Use it only if **one event** exists at that revision. A later timestamp within
the same revision, input position, identifier spelling or file order is never
a tie-break. Different top decisions mean `contradictory-approval`; identical
top decisions on separate events are still `ambiguous-approval`. Earlier
revisions are superseded. No event means `not-approved`.

For each entry apply this deterministic precedence:

1. Missing project, expense currency mismatch, conflicting/multiple current
   billed identity, current draft identity mismatch, then top approval
   ambiguity: `quarantined`, `expected_amount: null`. Retain any known expense
   source amount as `held_amount`; do not invent a time charge. These
   contradictions take precedence even over nonchargeable or period exclusions.
2. Outside `[period_start, period_end)` -> `excluded`, `out-of-period`.
3. `chargeable: false` -> `excluded`, `nonchargeable`.
4. One consistent as-of billed transaction -> `excluded`, `already-billed`;
   exclude the entire current entry regardless of billed amount.
5. Missing/nonapproved latest evidence -> `excluded`, `not-approved`,
   `pending`, `rejected` or `recalled`, as applicable.
6. Otherwise continue to pricing/evidence checks.

Definite exclusions have `expected_amount: "0.00"` because they contribute
no new permitted draft charge; this is not an estimate of their value.
Excluded time is not priced. Approval revision/IDs remain visible even when
another rule determines eligibility.

### 5. Price each time entry; check each expense

For approved time require the unique effective rate. A missing or overlapping
effective rate is a quarantine, never an inferred or cheapest rate.
Calculate `minutes * hourly_rate / 60` in decimal arithmetic and round
**each entry** to cents with `ROUND_HALF_UP`, then sum rounded charges.
Do not aggregate minutes before rounding. There is no overtime, tax or FX.

For an approved same-currency expense require its explicit policy. A missing
policy leaves the amount uncomputed. First compare amount to `max_amount`;
only `amount > max_amount` holds the whole amount (`expense-cap`).
Equality to the cap is allowed. Next require a non-null receipt when
`amount >= receipt_required_at` (`receipt-required` if absent).
Equality to the receipt threshold requires evidence. Never truncate to a cap,
reimburse, or convert. These determinate policy holds have status `held`,
permitted charge `"0.00"` and the whole original `held_amount`.

Passing entries have status `candidate` and their computed amount. They are
candidates for review, not authorization to bill. The selected `rate_id` or
`category/currency` policy key is recorded only when that pricing stage is reached.

### 6. Reconcile every draft line and every missing candidate

Retain every actual `line_id` and raw amount exactly once. For a unique active,
valid header and uniquely referenced computable entry:

- Candidate present at equal amount -> `match`.
- Candidate present at a different amount -> `update`.
- Definitively excluded or policy-held entry present -> `remove`, even if its
  raw amount is zero. The entry's exclusion/hold reason remains in `entries`.
- Candidate absent -> `add` with `line_id` and `draft_amount` null.

All deltas equal computed permitted charge minus original draft amount.
For a missing candidate only, absence supplies zero as the subtraction basis;
the raw amount stays null to distinguish “no line” from an existing zero line.
Tolerance is exactly zero. Do not add rows for absent excluded/held entries.

Unknown entry amount, missing header/source, identity mismatch, multiple
active drafts or duplicate details -> `clarify-not-remove`, null amount/delta,
`diagnostic_only: true`. Retain **all** ambiguous lines; never count the same
entry's computed amount several times. A known candidate with no active
draft gets one null-`draft_id` diagnostic `add` (`missing-draft`), not creation
of an invoice. With several active drafts it gets one null-draft clarification
instead of an arbitrary assignment. Uncomputed entries absent from all active
details remain accounted for in `entries` and their owned exception.

An out-of-period header's details get `defer`, null comparison and a review
issue. This historical draft does not prevent a missing current candidate
diagnostic. Header-level ambiguity must be reported even for an empty draft.

### 7. Apply project period caps

Sum every countable raw prior row in the project currency, plus the project's
rounded `candidate` charges. `known_consumption` is that **known subtotal**.
`calculation_complete` is false if any project entry amount or in-period
prior cap contribution is uncomputed. Then `proposed_consumption` is null,
not the known subtotal presented as a complete amount.

If `known_consumption > period_cap`, the known lower bound already proves
overage: set `cap_hold: true`, show that overage, and hold **all** known
candidate charges for the project, not only the excess or arbitrary entries.
At equality there is no cap hold. If no known overage but calculation is
incomplete, `cap_overage` is null; `cap_hold: false` is **not clearance**.
Otherwise overage is `"0.00"`.

Keep candidate amounts intact for diagnostics. Set their `cap_held` flags
and all affected detail `diagnostic_only` flags. Draft differences remain
visible, but cap-held add/update/remove suggestions are diagnostic-only.
`reviewable_new_amount` is the known candidate subtotal not subject to a
proven cap hold; it is never a financial approval and does not clear an
incomplete project or ambiguous draft.

### 8. Assign exception review

Use the project's supplied owner whenever a matching project exists;
otherwise use `data-steward`. Validation belongs to `input-provider`.
Held entries get `hold-entry`; uncomputed entries get `clarify-evidence`;
proven project cap excess gets `hold-project`. Detail differences get
`review-add`, `review-update`, `review-remove`, `clarify-not-remove` or
`review-export` for deferred details. Keep the project/entry/draft/line IDs
and explicit reason messages. Entry and detail issues may both exist: one
asks for evidence, the other protects the current draft.

Humans must resolve identity/revision/rate gaps, supply valid receipts and
policies, review cap constraints and determine a new approved snapshot.
Never resolve an approval conflict by assuming recall and removing the line.
No automatic financial action follows even a zero variance.

### 9. Close complete, currency-separated output

Account for every input entry, prior row, draft line, draft header and project.
Include projects/drafts with zero entries/lines. Provide known comparison
subtotals separately from complete comparisons; never subtract a partial
computed total from a complete raw draft total. Keep currencies separate.
An uncomputed time entry with a missing project has currency null, remains
in `entries`, and is not assigned to an invented currency bucket.

Emit the exact common envelope and business dictionary below, plus actual
stage observations. Empty inputs with valid configuration produce empty
arrays and a completed zero-count packet, not fictitious transactions.

## Exact result dictionary

JSON object key order is immaterial; array order is significant. All keys below
are required, including nulls. `money` is the input money-string format.
`signed-money` also permits a minus sign for nonzero differences; canonical
zero is `"0.00"`, never `"-0.00"`. `count` is a nonnegative JSON integer.
`text` is a nonempty string. `nullable` means JSON null, never a missing key.

The envelope has **exactly**:

| Key | Type and meaning |
|---|---|
| `schema_version` | integer constant `1`. |
| `status` | `completed` when no exceptions; `completed_with_exceptions` for a valid review packet with holds/clarifications/corrections; `rejected` for malformed business input. |
| `outputs` | object below, or exactly `{}` on business rejection. |
| `exceptions` | ordered array of the fixed exception objects below; empty only for `completed`. |

Nonrejected `outputs` has exactly `snapshot`, `entries`, `prior_billing`,
`draft_details`, `drafts`, `projects`, `currency_totals`, `closure`.

### `snapshot` object

`as_of`: instant normalized to UTC `Z`; `period_start`: date; `period_end`:
date; `review_only`: boolean constant true.

### `entries` array — order (`entry_type`, `entry_id`)

| Keys | Types / semantics |
|---|---|
| `entry_type`, `entry_id`, `project_id` | type enum `expense`/`time`, ID, supplied project ID, respectively. |
| `currency` | currency; null only for time with a missing project. Expense retains its source currency even on mismatch. |
| `approval_revision` | positive integer highest as-of revision; null when none. |
| `approval_event_ids` | sorted ID array of all events at the highest eligible revision (possibly empty or ambiguous). |
| `future_approval_event_ids` | sorted ID array of future events ignored for this entry. |
| `rate_id`, `policy_key` | nullable ID and nullable text; selected effective rate or `category/currency`, respectively; null if not reached/not uniquely matched. |
| `billed_ids` | sorted ID array of all as-of prior rows referencing this type/ID, including contradictory rows; future rows are not included. |
| `status` | enum `candidate`, `excluded`, `held`, `quarantined`. |
| `reason`, `message` | text machine reason code and human explanation. |
| `expected_amount` | money for a candidate, `"0.00"` for a definite exclusion/policy hold, null for uncomputed/contradictory evidence. No FX inference. |
| `held_amount` | original expense money when held/quarantined; null for candidates, exclusions and unpriced time. |
| `cap_held` | boolean; true only for a candidate whose project has a proven cap hold. |

### `prior_billing` array — order `billed_id`

`billed_id`: ID; `entry_type`: type enum; `entry_id`: ID; `project_id`: supplied
ID; `currency`: supplied currency; `amount`: raw money; `source_present`:
boolean indicating a current type/ID join; `cap_amount`: money for countable
history, `"0.00"` for future/out-of-period history, null for an unresolved
project/currency cap join; `disposition`: enum `counted`, `future-ignored`,
`out-of-period`, `quarantined`; `reason`, `message`: text.

Missing project or wrong project currency after the future filter quarantines
the prior row. Its unknown cap contribution is not relabeled zero. A current
source mismatch independently quarantines the entry but does not erase valid
raw prior history.

### `draft_details` array — order (`draft_id`, `entry_type`, `entry_id`, `line_id`)

Null sorting components precede strings. Actual lines and generated missing
candidate diagnostics share this array.

| Keys | Types / semantics |
|---|---|
| `draft_id`, `line_id` | nullable IDs; source line IDs remain unchanged; nulls identify missing-draft or missing-line diagnostics. |
| `project_id`, `currency` | nullable ID/currency. Use header identity when available. Without a header, project may come from the source entry for ownership, but an actual line's currency stays null: never infer its denomination. A generated missing-line/draft candidate may use its known entry currency. |
| `entry_type`, `entry_id` | type enum and ID. |
| `draft_amount` | nullable money; null only for an absent line. |
| `expected_amount` | nullable money for the uniquely computable permitted amount. |
| `delta` | nullable signed-money; charge minus raw draft, only for computable detail comparisons. |
| `action` | enum `match`, `add`, `update`, `remove`, `clarify-not-remove`, `defer`. |
| `diagnostic_only` | boolean; always true for ambiguity/defer/missing draft or project cap hold. False still means human-review proposal only. |
| `reason`, `message` | text reason code and explanation. |

### `drafts` array — order `draft_id`

`draft_id`, `project_id`: IDs; `currency`: header currency; `line_count`: count
of actual input lines only; `draft_amount`: money raw sum of those lines;
`computable_draft_amount`: money subtotal of lines with known comparison;
`quarantined_draft_amount`: money raw subtotal excluded from comparison,
including deferred lines; `computable_expected_amount`: money known comparison
subtotal, including missing candidate diagnostics assigned to this draft;
`comparison_complete`: boolean requiring a unique valid active header, no
uncomputed details, and a complete project calculation;
`expected_amount`: nullable money, equal to the computed subtotal only when
comparison is complete; `variance`: nullable signed-money, complete charge
minus **complete** raw draft only when complete.

`status` is enum `deferred`, `held`, `clarification`, `corrections`,
`reconciled`, with precedence in that order: another-period draft, proven
project cap hold, incomplete/ambiguous comparison, known nonmatch details,
otherwise reconciled. Empty ambiguous headers are not “reconciled”.

### `projects` array — order `project_id`

`project_id`: ID; `currency`: project currency; `owner`: ID; `entry_count`:
count of all current entries referencing it; `eligible_new_amount`: money
known candidate subtotal; `prior_billed_amount`: money known countable raw
prior subtotal; `period_cap`: supplied money; `known_consumption`: money sum
of those two known subtotals; `proposed_consumption`: nullable money, that sum
only when complete; `cap_overage`: nullable money (known positive excess,
complete zero, or null when unresolved with no proven excess); `cap_hold`:
boolean; `cap_held_amount`: money, whole known candidate subtotal if held,
otherwise zero; `reviewable_new_amount`: money candidate subtotal minus
cap-held subtotal; `calculation_complete`: boolean; `draft_ids`: sorted array
of all draft IDs referencing the project, including deferred drafts.

### `currency_totals` array — order `currency`

Every currency occurring in projects, entries, raw prior rows or draft headers/
details gets a bucket. No mixed-currency total is emitted.

`currency`: currency. The following are money **known subtotals**, not estimates
of uncomputed amounts:

- `eligible_new_amount`: candidates in this currency.
- `prior_billed_amount`: countable raw prior rows in this currency.
- `cap_held_amount`, `reviewable_new_amount`: project-level known subtotals.
- `known_entry_hold_amount`: original held/quarantined expenses in their
  **source currency**, including currency-mismatched expenses.
- `draft_amount`: every known-currency raw detail amount, including orphans
  and deferred details, counted once.
- `computable_draft_amount`: only raw details with a computable comparison.
- `quarantined_draft_amount`: remaining raw details.
- `computable_expected_amount`: known comparable detail charges, including
  missing-line diagnostics; ambiguous assignments do not count the same
  candidate multiple times.

`uncomputed_entry_count`: count whose entry amount is null in this currency.
`computable_variance`: signed-money, **computable** charge subtotal minus
**computable** draft subtotal, never the whole raw total.
`comparison_complete`: boolean false if any same-currency uncomputed entry,
incomplete project, incomplete draft, unresolved prior cap row, or
unassigned/deferred/ambiguous detail affects the bucket. Cross-currency
identity contradictions can therefore make both related buckets incomplete.
An actual line without a header has unknown currency: retain its raw amount
only in that detail row, exclude it from currency arithmetic, and mark its
known source project's/entry's currency comparison incomplete. Do not infer
the line denomination from that source. Known matching lines remain useful
even when a complete comparison is null.

### `closure` object

Exactly six counts: `entry_count`, `draft_count`, `project_count`,
`prior_billing_count`, `diagnostic_count` (all non-`match` detail rows),
`exception_count` (length of envelope exceptions). Zero is permitted.

### Fixed exception object and reason conventions

Every exception has exactly `code`: text; `message`: text; `owner`: text;
`project_id`: nullable ID; `entry_type`: nullable type enum; `entry_id`:
nullable ID; `draft_id`: nullable ID; `line_id`: nullable ID; `action`: text
enum `fix-input`, `hold-entry`, `clarify-evidence`, `hold-project`,
`review-add`, `review-update`, `review-remove`, `clarify-not-remove`,
`review-export`; `diagnostic_only`: boolean.

Sort by (`project_id`, `entry_type`, `entry_id`, `draft_id`, `line_id`,
`code`, `message`), treating null as empty text. This also makes multiple
schema errors stable. Record identities for orphan evidence can be included
in `message` when no dedicated output field exists.

Principal reason codes and meanings are:

| Codes | Meaning / human handling |
|---|---|
| `invalid-schema`, `invalid-id`, `invalid-amount`, `invalid-integer`, `invalid-boolean`, `invalid-currency`, `invalid-date`, `invalid-instant`, `invalid-enum`, `invalid-interval`, `duplicate-id`, `unsupported-tolerance` | Reject the bundle; message identifies the exact export/record/field. Repair input, never invent values. |
| `candidate-time`, `candidate-expense` | Unique approved price or compliant expense. Review-only candidate. |
| `out-of-period`, `nonchargeable`, `already-billed`, `not-approved`, `pending`, `rejected`, `recalled` | Definite new-charge exclusion; not itself an exception unless draft correction is needed. |
| `missing-project`, `currency-mismatch`, `billed-identity-mismatch`, `ambiguous-billing`, `draft-identity-mismatch`, `contradictory-approval`, `ambiguous-approval`, `missing-rate`, `ambiguous-rate`, `missing-policy` | Unknown/contradictory entry; clarify evidence, preserve null and protect existing draft lines. |
| `expense-cap`, `receipt-required` | Determinate whole-expense hold, not truncation or reimbursement. |
| `in-period-prior`, `future-billing`, `prior-out-of-period`, `prior-project-missing`, `prior-currency-mismatch` | Raw prior consumption, exclusion or unresolved join; retain the original transaction. |
| `draft-match`, `draft-add`, `draft-update`, `draft-remove`, `missing-draft`, `duplicate-drafts`, `duplicate-details`, `missing-draft-header`, `missing-draft-entry`, `draft-project-missing`, `draft-currency-mismatch`, `draft-out-of-period` | Exact detail/header outcome; ambiguity always clarifies, definite ineligibility alone permits a proposed removal. |
| `orphan-approval`, `orphan-rate` | As-of evidence without its source/project; data steward reviews export. |
| `project-cap` | Proven excess holds all known new candidates for that project. |

### Canonical messages for interoperable output

Use these exact message strings, not paraphrases, in entry, prior-billing and
detail rows and their corresponding exceptions. Reuse an entry's reason and
message when an otherwise valid draft line points to an uncomputed entry.

| Reason code | Exact message |
|---|---|
| `candidate-time` | Approved time priced at the unique effective rate. |
| `candidate-expense` | Approved expense satisfies currency, cap, and receipt policy. |
| `expense-cap` | Expense exceeds its per-entry policy cap; hold the entire amount. |
| `receipt-required` | Expense meets the inclusive receipt threshold but has no receipt reference. |
| `currency-mismatch` | Expense currency differs from its project currency; hold without conversion. |
| `out-of-period` | Service date is outside the half-open billing period. |
| `nonchargeable` | Entry is explicitly nonchargeable; exclude from new charges. |
| `already-billed` | Entry has a prior as-of billed transaction; exclude the entire entry. |
| `not-approved` | No approval event is available at the cutoff; exclude from new charges. |
| `pending` | Latest as-of approval is pending; exclude from new charges. |
| `rejected` | Latest as-of approval is rejected; exclude from new charges. |
| `recalled` | Latest as-of approval is recalled; exclude from new charges. |
| `contradictory-approval` | Highest as-of approval revision conflicts; clarification is required. |
| `ambiguous-approval` | Highest as-of approval revision is not unique; clarification is required. |
| `missing-project` | Entry has no matching project; amount remains uncomputed. |
| `billed-identity-mismatch` | Prior billing identity conflicts with this entry; clarification is required. |
| `ambiguous-billing` | Multiple as-of billed transactions reference this entry; no partial billing is inferred. |
| `draft-identity-mismatch` | Current draft identity conflicts with this entry; clarification is required. |
| `missing-rate` | No effective project-role-currency rate matches; amount remains uncomputed. |
| `ambiguous-rate` | Multiple effective project-role-currency rates match; amount remains uncomputed. |
| `missing-policy` | No category-currency expense policy matches; amount remains uncomputed. |
| `in-period-prior` | As-of billed amount consumes this project's period cap. |
| `future-billing` | Billing was recorded after the cutoff; ignore it for this snapshot. |
| `prior-out-of-period` | Billed service date is outside this period; it does not consume this period's cap. |
| `prior-project-missing` | Billed transaction has no matching project; its cap contribution is uncomputed. |
| `prior-currency-mismatch` | Billed transaction currency differs from its project; no cap conversion is inferred. |
| `draft-add` | Eligible entry is missing from the active draft. |
| `draft-update` | Draft amount differs from the computed entry amount. |
| `draft-remove` | Draft contains a definitively ineligible entry. |
| `draft-match` | Draft amount matches the computed entry amount. |
| `missing-draft` | No active draft is available; this is a diagnostic candidate only. |
| `duplicate-drafts` | Multiple active drafts reference this project and period; do not choose one. |
| `duplicate-details` | Multiple active draft details reference this entry; do not choose or remove a line. |
| `missing-draft-header` | Draft line has no matching header; clarify its identity instead of removing it. |
| `missing-draft-entry` | Draft line has no matching source entry; absence does not establish ineligibility. |
| `draft-project-missing` | Draft header has no matching project; clarify the export. |
| `draft-currency-mismatch` | Draft currency differs from its project currency; no conversion is inferred. |
| `draft-out-of-period` | Draft belongs to another service period; defer it without changes. |
| `project-cap` | Prior billed plus new candidate charges exceed the project period cap; hold all new candidate charges. |

For `prior-project-missing`/`prior-currency-mismatch`, the prior output row
uses the table message. Its exception appends ` Billed row {billed_id}.`
to identify the original transaction. Braces in these templates mean
substitution of a supplied field, not literal braces.

Orphan exception templates are `Approval event {approval_event_id} has no
matching current entry.` (`orphan-approval`) and `Rate {rate_id} has no
matching project.` (`orphan-rate`). They use `review-export`, the
`data-steward` owner and `diagnostic_only: true`.

For validation, an export row label is `{filename}[{primary-key}]`, joining
a composite primary key with `/`; use `invalid-key` when the key is absent
or invalid. Configuration label is `config`. Field-error message format is
`{label}.{field} must be {description}.` with the exact descriptions:

| Input type / code | Description substitution |
|---|---|
| ID / `invalid-id` | a nonempty trimmed string |
| nullable ID / `invalid-id` | a nonempty trimmed string or null |
| money / `invalid-amount` | a nonnegative fixed-two-decimal string |
| positive integer / `invalid-integer` | a positive JSON integer, not a boolean |
| boolean / `invalid-boolean` | a JSON boolean |
| currency / `invalid-currency` | three uppercase ASCII letters |
| date / `invalid-date` | a canonical valid YYYY-MM-DD date |
| instant / `invalid-instant` | a whole-second ISO timestamp with an explicit valid offset |
| entry type / `invalid-enum` | time or expense |
| approval decision / `invalid-enum` | approved, pending, rejected, or recalled |
| draft state / `invalid-enum` | draft |

Other validation templates:

- `invalid-schema`: `{label} must be an object.`, `{filename} must be an
  array.`, `{label} is missing fields: {sorted-list}.`, or `{label} has
  unsupported fields: {sorted-list}.` Lists are sorted field names separated
  by comma and space; root/table-map labels are `input` and `files`.
- `invalid-interval`: `{label}.{end-field} must be later than {start-field}.`
- `duplicate-id`: `Duplicate primary key in {filename}: {primary-key}.`
  Emit once per duplicated key, without choosing a duplicate.
- `unsupported-tolerance`: `config.draft_tolerance must be "0.00".`

Validate present fields even if other keys are missing, but do not attempt
child-field validation when its enclosing object/array has the wrong type.
Missing `files` produces both its missing-field and nonobject-map issue;
missing `config` produces its root missing-field issue. Every validation
exception has all entity IDs/type null, `owner: "input-provider"`,
`action: "fix-input"` and `diagnostic_only: true`.

## Actual observations and central synthetic video

Capture actual input counts, validation results, join matches/selected IDs,
approval branches, time rate/minutes/intermediate amounts, receipt decisions,
raw/computed draft differences, cap arithmetic, owned exceptions and final
counts during execution. Nine ordered workflow stages provide all six kinds:
`input`, `validation`, `join`, `decision`, `exception`, `output`.
Malformed business input may stop after validation.

Each observation has `step_id`, `kind`, `caption` (at most 260 characters),
`facts` (at most six scalar fields), and one or two `tables`. Each table has
`title`, one to six `columns`, zero to eight scalar `rows`, the actual
`total_rows`, and zero-based `highlight_rows`. Display a faithfully labeled
first-eight subset when needed; never fabricate omitted records or a stage.
The local adapter adds one-based `sequence` and an input-byte SHA-256 binding.

The foundation centrally renders the **actual synthetic baseline trace** into
`demo/baseline.webm`, roughly 30–90 seconds, with the on-frame label
“Synthetic baseline execution visualization - not Cowork or a live system”.
It records encoding/timeline/hashes and visual fidelity separately. The video
explains observed decisions, not native UI interaction. This scenario owner
does not make a substitute video, screenshot, fake interface, or native claim.
If the central video is not yet present, native staging remains incomplete.

## Native Creator, installation and independent execution — BLOCKED

As of 2026-09-14, creation, installation and independent native invocation
are **not run**. Before any such action, both approved Computer Use tools
**and an unlocked accessible session** must be restored, followed by
parent-coordinated authorization. No browser automation alternative, private
API, token/cookie extraction, shell route, model/skill substitution or
credential workaround is permitted.

After the parent verifies that gate, the intended native procedure is:

1. Use only the approved native UI and inspect real Installed state before
   retrying anything. The old N00 was last `Publishing...`, outcome unknown,
   and Creator was disabled. Do not infer publication or installation.
2. Stage the exact allowlist only: this `HOW_TO.md`, `workflow.json`,
   `connections.json`, `mock-data/demo.json`, and the centrally rendered
   `demo/baseline.webm`. Hashes/provenance stay outside that input directory.
   Do not include implementation, research, evaluation data, validation
   answers, source manifests or generated local results.
3. Ask Creator through its approved UI to build a standalone review-only
   process implementing the dictionaries, joins and ordered steps here,
   using synthetic exports and no native connection. Do not point it at
   the development baseline or hidden evaluation artifacts.
4. Record actual generated artifact identity and creation outcome. Inspect
   the generated contents and declared behavior before any authorized
   installation. A ZIP or source inspection is not proof of execution.
5. Install only with parent-coordinated authorization through the approved
   native mechanism; observe and record real Installed state. Do not
   silently execute a downloaded plugin.
6. Independently invoke the installed process on a fresh authorized synthetic
   attachment and fresh output destinations. The host must already supply
   approved attachment/media inspection, local file facilities, and permitted
   bundled-stdlib execution if generated output needs it. If unavailable,
   stop; do not install a runtime, decoder, service or infrastructure.
7. Obtain the actual returned review packet and evidence. A separate parent
   evaluator may compare it; local baseline success, a generation message,
   an unexecuted ZIP or this document cannot establish native success.

## Developer-only baseline command (not part of native execution)

The repository's private stdlib baseline is a development reference, not a
Creator dependency or generated plugin. From this scenario directory, use
fresh paths that do not already exist:

```powershell
python -B baseline.py --input mock-data\demo.json --output baseline-output\manual-demo.json --trace baseline-output\manual-demo.trace.json
```

The shared adapter reads only the input, adds trace provenance, and refuses
identical paths, linked/reparse paths, existing result or trace files, JSON
over 8 MiB, duplicate keys, nonfinite values and nesting above 80. It does not
call any business system. Business rejection is a successful exit with the
rejected envelope; malformed bytes/path/infrastructure failures exit nonzero
and do not count as a passed business case. Do not overwrite a previous run
or input to make a comparison pass.
