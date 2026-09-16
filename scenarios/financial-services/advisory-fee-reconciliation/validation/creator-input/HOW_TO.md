# Advisory fee billing reconciliation

## 1. Purpose, authority, and hard boundary

A billing operations analyst supplies synthetic exports for **SYN-FIN
Demonstration Company**, a fictional company, and a closed billing period.
Prepare a complete review packet for the **Billing manager or compliance
reviewer**. Recompute annual marginal asset-value fees from effective-dated
evidence; compare drafts without changing them. Source owners resolve missing
agreement, approval, and value evidence. Every result, including rejection,
has `human_review = pending` and `live_action = none`.

The catalog author approved these **sample policies**, not actual customer
authorization. This procedure does not interpret signed agreements, authorize
fees, create or submit fee invoices, debit, refund, post, trade, price assets,
give investment advice, or provide a regulatory opinion. No householding,
whole-balance cliff tiers, performance/flat/trade-linked fees, taxes, minimums,
cash-flow adjustments, or securities-level exclusions are inferred.

### Verified context, not a universal billing rule

- **f1-advisor-fees:** Interactive Brokers,
  [Advisor Fees](https://www.interactivebrokers.com/en/pricing/advisor-fees.php),
  accessed 2026-09-14. The Automatic Billing/Blended Fee sections describe
  annualized value-based fees and separate value ranges/rates; the notes state
  pending configuration requests are not in effect. Fee notices describe
  method, amount, and period. Only those narrow vendor-specific concepts are
  source-backed. Synthetic approval does not establish real client consent.
- **f2-billing-methods:** Interactive Brokers,
  [Automatic Billing Methods and Examples](https://www.interactivebrokers.com/en/general/advisor-client-fee-examples.php),
  accessed 2026-09-14. The actual annualized-percentage example divides by
  **252 business days**. It demonstrates why the basis must be explicit; it
  does **not** establish our invented 365/366 calendar-day agreement policy.
  The vendor's flat-fee example is not implemented here.

The SEC fee-calculations PDF and announcement returned HTTP 403 during
research; their full contents were **not fetched or verified**. No regulatory
requirements, examination findings, quotations, or compliance claims are
attributed to them. All keys, dates, limits, joins, rounding, tolerances,
exception precedence, and sample fee formulas below are fictional policies.

## 2. Exact input contract

Input is one UTF-8 JSON object. Duplicate JSON keys, nonfinite numbers,
unparseable JSON, and invalid file encoding are file errors, not successful
business rejections. Unknown fields are rejected at **every** object level.
All fields below are required except the two explicitly optional fields.
Null is accepted only where explicitly listed; omission is not null.

| Top-level key | Type and meaning |
| --- | --- |
| `schema_version` | True integer exactly `1`, not boolean |
| `as_of` | Offset-bearing RFC3339 string with uppercase `T`, seconds, optional 1-6 fractional digits, and `Z` or signed `HH:MM`; a valid calendar instant. No leap seconds, omitted offset, lowercase suffix, or unknown `-00:00` offset. |
| `business_utc_offset_minutes` | True integer -840 through 840; fixed offset, not inferred DST |
| `billing_configuration` | Object defined below |
| `engagements` | Array of 0-5000 engagement objects |
| `schedule_versions` | Array of 0-5000 schedule objects |
| `synthetic_value_intervals` | Array of 0-5000 value objects |
| `draft_fee_lines` | Array of 0-5000 draft objects |

True integers reject boolean, float (even `1.0`), numeric string, and null;
no coercion occurs. Money/value input integers are nonnegative cents bounded
by 1,000,000,000,000. Currency is exactly `USD` or `EUR`, both exponent 2;
one configuration currency per case, with no conversion. Output monetary
amounts use integer cents, not currency-unit floats. Bps integers are 0-10000.
Every ID is 5-80 characters matching `SYN-[A-Z0-9][A-Z0-9-]{0,75}`;
no trimming, case folding, punctuation removal, or fuzzy matching applies.
Date-only strings are valid Gregorian `YYYY-MM-DD` in years 0001-9999.

### Billing configuration

Exact required keys: `control_version` (synthetic ID), `approval_state`
(`approved` or `pending`), `period_start` and `period_end` (dates), `currency`,
`day_count_basis` (`actual-calendar-year` or `act-365-fixed`), and
`rounding_mode` (`half-up` or `half-even`). Optional
`variance_tolerance_minor` is a true integer 0-1,000,000,000,000 cents,
**default 1 only when omitted**; null is invalid. No other defaults exist.
Unknown settings such as householding or market-price policies are invalid.

The period is `[period_start, period_end)`, 1-366 calendar days. Its exclusive
end is local midnight in the supplied fixed offset and must be no later than
`as_of`. Convert instants to the fixed offset, never the computer timezone.
Do not approximate DST, holidays, or a business-day calendar. An instant that
cannot be represented in the documented Gregorian range is invalid.
Top-level pending controls produce `policy-not-approved` before business
decisions; unknown approval values are malformed.

### Engagement objects

Exact keys: `billing_account_id` (primary synthetic ID), `agreement_id`
(synthetic ID), `currency`, `active_from` (date, included), and `active_to`
(date, excluded, or explicit null for no end). Non-null end must follow
start. Currency must equal configuration currency. Account IDs are strictly
unique, even for identical repeated rows. Agreement IDs may be shared;
each schedule must reference the agreement of its exact account.

Billable interval is the intersection of engagement and billing period.
If empty, the account is `not-billable`, not an invented zero fee.

### Schedule version objects

Exact keys: `schedule_id` (globally unique within this source),
`billing_account_id`, `agreement_id`, `effective_from`, `effective_to`,
`approval_state` (`approved` or `pending`), `approved_at`, and `bands`.
Both effective dates are required finite dates with start before end.
Account must exist and agreement must equal its engagement's agreement.
Approved rows require an RFC3339 `approved_at`; pending rows require null.
An approved timestamp after `as_of` is valid but **ineligible** evidence.

`bands` is a nonempty ordered array of at most 5000 objects. Each has exactly
`upper_value_minor` (positive bounded integer cents or null) and
`annual_rate_bps` (true integer 0-10000). Finite upper bounds strictly increase.
Only the final band is unbounded (`upper_value_minor = null`) and it is
required. The first lower bound is implicitly zero; each next lower bound is
the preceding upper bound. This representation cannot encode an independent
gap/overlap lower bound: extra lower-bound fields are invalid. A finite zero,
decrease, repeated upper bound, intermediate null, or missing final null is
invalid. Band order is semantically meaningful and must not be sorted.

### Synthetic value interval objects

Exact keys: `valuation_id` (globally unique within this source),
`billing_account_id`, `currency`, `from_date`, `to_date`, and
`billable_value_minor` (nonnegative bounded integer cents). Account must exist;
currency must equal configuration currency. Start must precede finite
exclusive end. Value is explicitly constant for precisely that interval;
no pricing, interpolation, zero default, or forward-fill is allowed.

### Draft fee line objects

Exact required keys: `draft_id` (globally unique within this source),
`billing_account_id`, `period_start`, `period_end`, `currency`, and
`amount_minor` (nonnegative bounded integer cents). Optional
`source_schedule_id` is a synthetic ID or null, **default null when omitted**.
It is an opaque context label: it need not identify an eligible or existing
schedule and never changes the calculation or triggers its own exception.
Draft period start must precede exclusive end. An unknown account or
otherwise valid wrong period/currency is a business exception, not malformed.

Technical IDs are unique within each of the four sources; equal text in
different source types is not a duplicate. Different draft IDs with the same
business key `(billing_account_id, period_start, period_end, currency)` are
duplicates for comparison: never sum them or select the first.

## 3. Validation and business precedence

1. Validate root fields, version, `as_of`, offset, configuration shape and
   scalar values, period length, and fixed-offset closure, in that order.
   Check pending controls after these configuration validations.
2. Validate sources in this order: engagements, schedules, values, drafts.
   Each source must be an array within its cap. Establish row object shape
   and valid primary IDs, detect duplicate primary IDs, then validate rows
   by ascending primary ID. Inspect fields in their order in section 2;
   bands remain in supplied order. Unknown/missing fields are diagnosed at
   the containing object. No truncation or silent invalid-row exclusion.
3. Validate schedule and value account references, then schedule agreements
   and authoritative currencies, in source/ID order. Approved schedules
   known by `as_of` are eligible. Pending and later-approved rows are not.
4. Check **entire supplied intervals**, not just the billing intersection,
   for overlaps among eligible schedules, then among authoritative values.
   Accounts are sorted; interval pairs are considered by start/end/ID.
   Touching endpoints are adjacent and valid. Any nonempty overlap rejects
   the **whole** case, even with equal values/rates or outside billable dates.
   Excluded pending/future-approved schedules do not create contradictions.
5. Integrity rejection returns the first diagnostic and **no financial
   outputs**. It is a normal rejected business result, not a process crash.
6. For a valid case, intersect billable intervals and eligible schedule/value
   boundaries; additionally split January 1 under `actual-calendar-year`.
   Pending/future versions do not introduce calculation boundaries.
   Each slice requires exactly one eligible schedule and one value.
   Any missing slice holds the **entire account**: retain coverage/evidence
   segments but no partial fee, band calculations, or account rounding.
   Each missing schedule/value produces its own interval exception.
7. Show every pending or later-approved version in `pending_changes`.
   It is a review exception and account flag only if its effective dates
   intersect that account's billable interval. Eligible evidence still wins.
8. Classify each draft first by unknown account, then wrong period, then wrong
   currency, then no billable days. Only remaining rows join the exact key.
   For an active account, duplicate exact-key rows take precedence over
   per-draft `uncomputed-account`; a unique draft on a coverage-held account
   gets `uncomputed-account`. No exact-key draft produces `missing-draft`
   even on a coverage-held account. Each excluded row remains visible.
9. Account comparison precedence is `not-billable`, then `uncomputed`, then
   `missing-draft`, then `duplicate-drafts`, then the unique comparison.
   All applicable flags remain visible despite this precedence.
10. A unique computed comparison uses `delta_minor = draft - computed`.
    `abs(delta) <= tolerance` is `matched`, even with a nonzero delta.
    Otherwise positive means `draft-overstatement`, negative means
    `draft-understatement`. Pending changes still require review on a match.

## 4. Exact marginal arithmetic

For each coverage-complete constant segment, let a band's implicit lower
bound be the previous upper bound (zero for the first). Allocate
`max(0, min(value, upper) - lower)` cents, treating unbounded upper as the
segment value. Include all bands in output, including zero slices.
Band `annual_numerator = band_value_minor * annual_rate_bps`, with units
**cent-basis-points**, not yet cents. Segment annual numerator is their sum.

`segment fee in cents = annual_numerator * days / (10000 * day_count_denominator)`.

Use exact integer rational arithmetic and reduce fractions to numerator and
positive denominator. `actual-calendar-year` uses 366 for a Gregorian leap
year, otherwise 365, and splits each year boundary. `act-365-fixed` always
uses 365 and does not add year-only boundaries. Start is included; exclusive
end/termination day is not. Use all calendar days, not weekdays.

Sum **all exact segment fractions** for one account, then round once to cents.
Never round a day, a band, an annual fee, or a segment before the account sum.
For nonnegative fees, quotient/remainder decides rounding: zero remainder is
`exact`, less than half is `below-half-down`, greater is `above-half-up`.
An exact half is `half-up` in that mode; in half-even it is
`half-even-down` when the lower integer is even, otherwise `half-even-up`.
No binary float or display-only decimal substitutes for exact fractions.

Demo illustration: a 150,000-dollar account uses 100/50 bps marginal tiers
for 15 days, then 80/40 for 15 days in April 2026. Annual cents are 125000
and 100000; their combined fraction is 675000/73 cents, rounded once to
9247 cents. A 10274-cent draft overstates by 1027 cents. An absent draft is
not a zero draft; a real zero is valid and may be compared.

## 5. Exact output contract

The top envelope has exactly `schema_version` (integer 1), `status`,
`outputs` (object), and `exceptions` (array). `status` is `completed` when
there are no exceptions, `completed_with_exceptions` when a valid packet
has any exception, or `rejected` for integrity/policy failure. A pending
human review alone does not force `completed_with_exceptions`.

All keys in this section are **always present** in their described object,
including nullable values; there are no optional output fields. Each exact
fraction is exactly `{"numerator": integer, "denominator": positive integer}`,
reduced, with zero represented as `0/1`. Computed sums can exceed individual
input bounds; use unbounded integer arithmetic. Integers are not booleans.

### Rejected outputs

Exactly `validation` and `review`. `validation` has
`accepted: false` and `rejected_before_calculation: true`. `review` is the
constant object below. No account, segment, draft, or population figures are
returned. `exceptions` contains exactly the first integrity diagnostic.

### Valid outputs

Exactly `billing_period`, `account_reviews`, `calculation_segments`,
`draft_comparisons`, `pending_changes`, `evidence_dispositions`,
`population_totals`, and `review`:

**`billing_period`**: `period_start`, `period_end`, `currency`, `as_of`
(the original supplied string), `business_utc_offset_minutes`,
`day_count_basis`, `rounding_mode`, `variance_tolerance_minor`; types and
normalized optional tolerance are as in section 2.

**`account_reviews`**, one row per engagement:

| Keys | Types and semantics |
| --- | --- |
| `billing_account_id`, `agreement_id`, `currency` | Input strings |
| `active_start`, `active_end` | Clipped billable date strings; both null when no billable interval |
| `active_days` | Nonnegative integer |
| `calculation_status` | `computed`, `held-missing-coverage`, or `not-billable` |
| `exact_fee_minor` | Reduced account fraction; null unless computed |
| `computed_fee_minor` | Rounded integer cents; null unless computed |
| `rounding_decision` | One of the six decisions in section 4; null unless computed |
| `draft_ids` | Sorted IDs of exact-key, billable-account candidates, including duplicates; excludes all externally classified draft rows |
| `comparison_status` | `not-billable`, `uncomputed`, `missing-draft`, `duplicate-drafts`, `matched`, `draft-overstatement`, or `draft-understatement` |
| `draft_fee_minor` | The unique exact-key draft amount even if uncomputed; otherwise null, never a duplicate sum |
| `delta_minor` | Signed integer only for comparable accounts, otherwise null |
| `pending_change_ids` | Sorted IDs of pending/future-approved schedules intersecting billable dates |
| `review_flags` | Sorted distinct exception codes scoped to this account, including excluded drafts |

**`calculation_segments`**, one row per split billable interval:
`billing_account_id` (ID), `segment_index` (one-based integer within account),
`segment_start`, `segment_end` (dates), `days` (positive integer),
`day_count_denominator` (365 or 366), `schedule_id` (eligible ID or null),
`valuation_id` (ID or null), `coverage` (`complete`, `missing-schedule`,
`missing-value`, `missing-schedule-and-value`), `calculation_status`
(`computed` or `held-account`), `billable_value_minor` (integer if value
exists, else null), `annual_numerator` (integer or null), `bands` (array),
and `exact_fee_minor` (fraction or null). A held account retains **every**
segment's actual coverage/evidence/value but has empty `bands` and null
annual numerator/fraction on **all** segments, even complete ones.

Each segment band has exactly `band_index` (one-based), `lower_value_minor`
(integer cents), `upper_value_minor` (integer cents or final null),
`annual_rate_bps` (integer), `band_value_minor` (integer cents), and
`annual_numerator` (integer cent-bps). Segment numbering does not skip gaps.

**`draft_comparisons`**, one row for **every** input draft:
`draft_id`, `billing_account_id`, `currency`, `period_start`, `period_end`,
`source_schedule_id` (ID or null), `amount_minor` (integer cents),
`disposition` (`orphan-account`, `wrong-period`, `wrong-currency`,
`not-billable-account`, `duplicate-draft`, `uncomputed-account`, or `compared`),
`computed_fee_minor`, `delta_minor` (integers, both null unless compared),
and `comparison_status` (`matched`, `draft-overstatement`, or
`draft-understatement`, otherwise null).

**`pending_changes`**, one row for every ineligible schedule:
`billing_account_id`, `schedule_id`, `approval_state`, `approved_at`
(input instant or null), `effective_from`, `effective_to`,
`exclusion_reason` (`pending-approval` or `approved-after-as-of`), and
`intersects_billable_period` (boolean).

**`evidence_dispositions`** has exactly three arrays:
- `engagements`: every row has `billing_account_id` and `disposition`
  (`billable` or `not-billable`).
- `schedule_versions`: every row has `schedule_id`, `billing_account_id`,
  and `disposition` (`joined`, `outside-billable-period`, `pending-approval`,
  or `approved-after-as-of`).
- `synthetic_value_intervals`: every row has `valuation_id`,
  `billing_account_id`, and `disposition` (`joined` or
  `outside-billable-period`).

`joined` means used as coverage evidence, including on held accounts, not
necessarily calculated or approved for charging. Draft closure is in
`draft_comparisons`; these arrays close all other source rows.

**`population_totals`** has:
- `currency` (configuration string) and `account_count` (all engagements).
- `computed`: `account_count` and `fee_minor` (sum of account-rounded cents).
- `comparable`: `account_count`, `computed_fee_minor`, `draft_fee_minor`,
  `delta_minor` (integers). Only computed accounts with exactly one exact-key
  draft contribute, regardless of matched/variance outcome.
- `computed_missing_draft`: `account_count` and `computed_fee_minor`.
- `computed_duplicate_drafts`: `account_count` and `computed_fee_minor`.
- `uncomputed`: `account_count` and sorted `billing_account_ids`.
- `not_billable`: `account_count` and sorted `billing_account_ids`.

Computed = comparable + computed-missing + computed-duplicate, both in
count and cents. All accounts = computed + uncomputed + not-billable.
Uncomputed/not-billable populations deliberately have **no monetary total**.
Empty computed/comparable populations have zero counts and zero sums over
their empty sets; that does not manufacture a fee for an unknown account.

**`review`**, on every result, is exactly:

```json
{
  "human_review": "pending",
  "live_action": "none",
  "owner_role": "Billing manager or compliance reviewer",
  "summary": "Synthetic review only; no fee invoice, debit, refund, trade, advice, or regulatory opinion."
}
```

### Exception shape, exact codes, and exact messages

Every exception has exactly `code`, `message`, `billing_account_id`,
`record_id`, `related_ids`, `from_date`, `to_date`, and `field`.
Code/message are nonempty strings. Account/record are IDs or null.
`related_ids` is a sorted distinct ID array, empty when not applicable.
Date fields are both dates or both null; `field` is a dotted validation
path or null. Source row paths use `source[PRIMARY-ID]`, bands use zero-based
`bands[index]`; source array errors use the source name. Row shape errors use
`source[index]`, and malformed primary IDs use `source[index].id_key`, in
input order. After these structural/ID checks, row scalar field paths use
`source[PRIMARY-ID].field_name`. Root is `$`.

Validation scope records are null for root/configuration errors. For row
errors, use the valid row primary ID and syntactically valid account ID if
available. Engagement record/account are its primary ID. Duplicate IDs have
that ID as record and the sole related ID; the field is `source.id_key`.
Choose the smallest duplicated primary ID; if its rows name different
accounts, use the lexically smallest syntactically valid account (null sorts
before a valid ID). This diagnoses the contradiction, not an authoritative
row selection.
References/currencies use their row field path; bad approval uses
`source[ID].approved_at`. Source interval errors use the row path;
band-structure errors use `source[ID].bands`. Overlap diagnostics identify
the account, lexically smaller conflicting ID as record, both related IDs,
their exact intersection dates, and null field. Reject first as in section 3.

Root scalar errors use `schema_version`, `as_of`, or
`business_utc_offset_minutes`; configuration scalar/date errors use
`billing_configuration.field_name`. A configuration shape or `invalid-period`
error uses `billing_configuration`; closure uses
`billing_configuration.period_end`; pending controls use
`billing_configuration.approval_state`. Band array type/size/empty/structure
errors use the bands path. Band object errors use `bands[index]`; rate/bound
integer errors append their actual field name. Validate a band's upper-bound
scalar, then rate scalar, then final-unbounded/increasing structure, before
continuing to the next band. Finite bounds outside 1-1,000,000,000,000 produce
`invalid-integer`, not a coercion or a generic missing-band diagnostic.

| Integrity code | Exact message |
| --- | --- |
| `invalid-object` | Expected an object with the documented fields. |
| `invalid-fields` | Object fields do not match the documented contract. |
| `invalid-array` | Expected an array with at most 5000 rows. |
| `invalid-integer` | Expected an integer from {minimum} through {maximum}. |
| `invalid-enum` | Unsupported value; allowed: {allowed values in ASCII order, separated by comma and space}. |
| `invalid-id` | Expected a 5-80 character uppercase ASCII synthetic ID beginning SYN-. |
| `invalid-date` | Expected a valid YYYY-MM-DD calendar date. |
| `invalid-timestamp` | Expected an offset-bearing RFC3339 timestamp with seconds and at most six fractional digits. |
| `invalid-interval` | Interval start must precede its exclusive end. |
| `invalid-period` | Billing period must contain 1 through 366 calendar days. |
| `period-not-closed` | Billing period has not ended at the supplied business offset as of as_of. |
| `policy-not-approved` | Top-level synthetic billing controls are pending; financial decisions are blocked. |
| `duplicate-id` | Technical identifiers must be unique, including identical duplicate rows. |
| `unknown-account` | Authoritative evidence references an unknown billing account. |
| `agreement-mismatch` | Schedule agreement does not match its engagement. |
| `currency-mismatch` | Authoritative currency does not match the billing configuration. |
| `invalid-approval` | Approved schedules require approved_at; pending schedules require null. |
| `invalid-bands` | Marginal bands require strictly increasing positive finite upper bounds and one final unbounded band. |
| `overlapping-approved-schedules` | Approved schedules overlap; no authoritative schedule can be selected. |
| `overlapping-value-intervals` | Authoritative value intervals overlap; no value can be selected. |

Business gap exceptions use account as record, the split gap dates, existing
schedule/value IDs as related IDs, and null field. Pending/future exceptions
use schedule as record, its sole ID as related, and effective/billable
intersection dates. Missing draft uses account as record and empty related
IDs. Duplicate drafts use the smallest draft ID as record and all candidate
IDs as related. Other draft exceptions use draft as record and its sole ID
as related. All draft/missing/duplicate exception dates are the **configured**
billing period, even when the excluded draft itself names a different period.
All business exception fields are null.

| Business code | Exact message |
| --- | --- |
| `missing-schedule-coverage` | No eligible approved schedule covers this billable interval; the account is held. |
| `missing-value-coverage` | No explicit value covers this billable interval; the account is held. |
| `pending-approval` | Pending schedule does not override approved evidence; review the request. |
| `approved-after-as-of` | Schedule approval is after as_of and is not eligible; review the excluded version. |
| `missing-draft` | No draft matches the account/period/currency key; no zero draft is inferred. |
| `duplicate-drafts` | Multiple drafts share the account/period/currency key; comparison is held. |
| `orphan-draft` | Draft references an unknown billing account and is excluded. |
| `wrong-period-draft` | Draft period differs from the billing period and is excluded. |
| `wrong-currency-draft` | Draft currency differs from the billing currency and is excluded. |
| `not-billable-draft` | Draft account has no billable days in this period and is excluded. |
| `uncomputed-draft` | Draft cannot be compared because account coverage is incomplete. |
| `draft-overstatement` | Draft exceeds the recomputed fee beyond the inclusive tolerance. |
| `draft-understatement` | Draft is below the recomputed fee beyond the inclusive tolerance. |

### Deterministic ordering and immutability

Sort account reviews by account ID. Segments sort by account then start,
with one-based index per account. Bands retain schedule order. Draft rows
sort by account, period start, period end, currency, draft ID. Pending changes
sort by account then schedule ID. Evidence arrays sort by account then
technical ID. ID arrays and unique review codes sort lexically.
Exceptions sort by account (null as empty), record (null as empty), code,
from date, to date, field (null as empty), then related IDs. Sorting must not
mutate source objects or source arrays. Permuting source rows cannot change
valid-case output or trace; permuting bands intentionally changes semantics.

## 6. Ordered operations and actual demonstration

Use all eight steps in `workflow.json`: intake, validation, effective join,
marginal slices, exact proration/rounding, draft join, exception routing,
review output. Capture the actual state after each operation, not a narrated
answer key. Input is first, output last, with the six kinds input, validation,
join, decision, exception, output. Rejection records intake, failing
validation, and a review-only rejection output, not fabricated later work.

Trace events have `step_id`, `kind`, `caption` (1-260 characters), `facts`
(up to six scalar entries), and one or two `tables`. Each table has `title`,
`columns` (1-6 names), `rows` (0-8 scalar-cell rows), `total_rows` (full
actual count), and `highlight_rows` (valid distinct zero-based row indices).
Show actual IDs, interval days, marginal band cents/bps, exact fractions,
rounded amounts, comparison populations and decisions. Large tables display
only their first eight sorted rows, explicitly labeled a subset, preserving
the real total. The local adapter alone assigns one-based `sequence`.

The foundation centrally renders the actual compared demo trace as
`demo/baseline.webm`, about 30-90 seconds, labeled **Synthetic baseline
execution visualization - not Cowork or a live system**. It must preserve
observed tables/facts, hashes and rendering fidelity; it is not fake
application UI. No video exists merely because that path is declared.

## 7. Connections and native Creator instructions

Connection metadata is exactly `mode: mock-exports-only`,
`availability: not-required`, `connections: []`; no endpoint or auth.
Actual agreement access/interpretation, approval provenance, custody/billing
exports, billable-value completeness, business calendars, and approved native
connections remain unverified. Host-local file/media understanding and
permitted execution must be verified later; offline success does not prove
those capabilities. No backend, custom MCP, Azure resource, model/media
service, database, queue, gateway, scheduler, runner, device agent, or installer.

**Creator build instruction:** implement the complete input/output contract
and ordered review-only procedure in sections 1-6 using supplied synthetic
exports. Enforce strict validation and exact fractions, include every row
disposition, and return the documented envelope. Treat the demonstrated
export as one example, not fixed constants. Do not perform live actions or
provision dependencies. Native input is only `HOW_TO.md`, `workflow.json`,
`connections.json`, `mock-data/demo.json`, and the **actual** rendered
`demo/baseline.webm`. Do not include research, scenario/source metadata,
implementation/shared code, answer files, private test cases, generated local
outputs, or validation evidence. Do not infer missing content or availability.

**Native creation, installation, and independent invocation are NOT RUN /
BLOCKED.** Approved Computer Use tools **and** an unlocked accessible session
must both be restored, with parent-coordinated permission, before any native
action. No substitute browser, Playwright, API, cookie, token, shell, or
model/skill channel. Historical N00 was last `Publishing...`, outcome
**UNKNOWN**, with Creator disabled; inspect real Installed state before retry.
Once authorized, use only the approved native workflow to create, observe
installation, and independently invoke; record actual artifact/evidence
identities and compare every output field. Local success is not generated,
Installed, or a native pass. Never fabricate a native ZIP or claim publication.

## 8. Developer-only local reference

This command is a local development adapter check, **not** a Creator
implementation instruction, native invocation, or dependency to ship. The
public procedure above is sufficient without reading the reference code.
From this scenario directory, choose fresh output files:

```powershell
python -B baseline.py --input mock-data\demo.json --output baseline-output\demo.json --trace baseline-output\demo.trace.json
```

The trusted local function is `solve(payload) -> (result, events)`. It uses
only Python standard library plus the scenario CLI adapter, makes no external
calls, and does not modify inputs. Business rejection exits normally; file,
unexpected implementation, or infrastructure errors do not masquerade as
passed negatives. Foundation validation, independent comparisons and native
evidence gates remain separate.
