# Promotion price audit: a synthetic, review-only file procedure

## Purpose, people and boundary

A **Pricing operations analyst** audits a configured period of observed store
unit prices. Merchandising supplies independent product, base-price,
promotion and scope exports; store reporting supplies observations; a pricing
reviewer supplies synthetic exception evidence. Start with the unjoined tables,
not a table of precomputed decisions. End with an auditable comparison,
rule-selection explanations, an excluded-observation register, an issue queue
and a reconciled review packet. A human reviews the packet; nothing is applied.

All identities start with `SYN-` and all dates are in **2099**. The scope is
**one unit, tax-exclusive prices in a supported two-decimal currency**.
There is no basket, quantity-break, threshold, coupon, loyalty, affiliation,
personalized-price, shipping, tax, currency conversion or unit conversion
calculation. There is no POS/ERP operation, price/label publication, sale,
refund or customer notification. Unit-price differences are **not financial
loss**, transaction totals or a legal/compliance conclusion. An
`approval_reference` is invented historical evidence, **not permission to act**.
Every review packet has `action_authorized: false`.

## Public research and deliberately chosen policy

These official pages were fetched and reviewed for the approved research on
**2026-09-14**:

* **R6, Microsoft, [Retail discounts](https://learn.microsoft.com/dynamics365/commerce/retail-discounts-overview)**:
  status, currency, unit and product/channel scope affect applicability;
  exclusion lines override inclusions; priorities and exclusive/best-price/
  compounded modes interact. Configuration should be documented and tested.
* **R7, Microsoft, [Pricing settings](https://learn.microsoft.com/dynamics365/commerce/price-settings)**:
  concurrency, successive-versus-original-price compounding and line rounding
  are configurable. The old **Enable price report for retail store** parameter
  was removed in **October 2023**.
* **R8, Microsoft, [Retail price reports](https://learn.microsoft.com/dynamics365/commerce/price-report)**:
  store/date reports support current, upcoming and historical price review,
  export and filtering. Its old enable-parameter setup instruction is
  superseded by R7's removal note; **do not follow that obsolete instruction**.
  The report feature's seven-day limit is not imposed on this file audit.

Those are source-backed concepts, **not a claim of Dynamics pricing-engine
parity**. The exact schemas, synthetic restrictions, half-open windows,
unique-evidence gate, highest-priority-only hierarchy, exception precedence,
amount-before-percent formula, exact tie ordering, final half-up rounding and
integer tolerance below are **mock sample policy**. `workflow.json` identifies
source-backed and sample rules separately. No installed product or connector
is inferred from research.

## Input bundle and configurable filenames

The input is one UTF-8 JSON object. Duplicate JSON object keys, nonfinite
numbers, invalid JSON and file-access errors are infrastructure failures, not
valid business negatives. The shared local adapter rejects inputs over 8 MiB
or deeper than 80 levels. The business schema has **exact keys** at every
object level: missing and unknown fields reject the bundle. No implicit
defaults, wildcard keys, fuzzy matching or silent deduplication are allowed.

Top-level keys:

| Key | Type and meaning |
| --- | --- |
| `schema_version` | Integer exactly `1`, never boolean. |
| `policy` | One object with all policy keys below. |
| `exports` | Object mapping each configured logical filename to an array of record objects. Exactly the seven mapped names must exist. |

`policy` keys:

| Key | Type and meaning |
| --- | --- |
| `as_of` | Date string; last included audit day must not be later than this supplied date. |
| `audit_start` | Inclusive local-calendar date string. |
| `audit_end` | Exclusive local-calendar date string, strictly after `audit_start`. |
| `tolerance_minor` | Nonnegative integer; inclusive allowed absolute unit-price difference. |
| `rounding` | String exactly `ROUND_HALF_UP`. |
| `source_files` | Object with exactly the seven role keys below, each mapped to a distinct logical `.json` filename. |

These are **logical export names within `exports`**, not paths to open. They
never resolve files, URLs or a service. The policy is the bundle's singleton
object, not an eighth table. Every filename must be a lowercase kebab-case
basename ending in `.json` (for example `my-store-export.json`); no directories,
backslashes, colon, whitespace, traversal or Windows device basenames
`con`, `prn`, `aux`, `nul`, `com1`–`com9`, `lpt1`–`lpt9`.

| `source_files` role | Demo filename | Primary key |
| --- | --- | --- |
| `stores` | `stores.json` | `store_id` |
| `products` | `products.json` | `sku` |
| `base_prices` | `base-prices.json` | `price_id` |
| `promotions` | `promotions.json` | `promotion_id` |
| `promotion_scope` | `promotion-scope.json` | `(promotion_id, store_id, sku, line_type)` |
| `price_exceptions` | `price-exceptions.json` | `exception_id` |
| `observations` | `observed-prices.json` | `observation_id` |

Renaming any logical export means changing its one map value and its
corresponding `exports` key. Do not rename role keys or change business
records. Decisions must be invariant under these filename changes. All seven
arrays are required even when empty. Empty arrays are actual evidence of zero
exported records, not replacements for missing arrays.

### Exact record schemas

In the tables below, **ID** is an ASCII string matching
`SYN-[A-Z0-9][A-Z0-9-]{0,63}`. IDs and joins are case-sensitive; no trimming or
normalization is performed. **Date** is a real, zero-padded `YYYY-MM-DD`
calendar date in 2099, with no time or timezone. **Currency** is exactly one
of `USD`, `EUR`, `GBP`, `CAD`, `AUD`; each has two fractional decimal places
in this sample. Other currencies are unsupported, not inferred from their
three-letter spelling. **Unit** matches `[A-Z][A-Z0-9-]{0,15}`; it is an exact
label such as `EA` or `CASE`, not a conversion instruction.

**Money** is a nonnegative integer number of minor units. **Positive integer**
means greater than zero. Numeric strings, floats (including `1.0`), booleans,
negative money and null money are invalid. Priority is any signed integer
(negative priorities are allowed), never boolean. All boolean fields require
JSON `true` or `false`, not strings or numeric flags.

| Role | Every required field and type |
| --- | --- |
| `stores` | `store_id`: ID; `currency`: Currency; `date_basis`: string exactly `store-local-calendar`. |
| `products` | `sku`: ID; `unit`: Unit. |
| `base_prices` | `price_id`: ID; `store_id`: ID; `sku`: ID; `valid_from`: Date; `valid_to`: Date; `currency`: Currency; `unit`: Unit; `price_minor`: Money. |
| `promotions` | `promotion_id`: ID; `enabled`: boolean; `valid_from`: Date; `valid_to`: Date; `currency`: Currency; `unit`: Unit; `priority`: integer; `mode`: `exclusive`, `best-price` or `compound`; `type`: `amount-off` or `percent-off`; `value`: positive integer, minor units for amount-off or **1 through 10000** basis points for percent-off. |
| `promotion_scope` | `promotion_id`: ID; `store_id`: ID; `sku`: ID; `line_type`: `include` or `exclude`. |
| `price_exceptions` | `exception_id`: ID; `store_id`: ID; `sku`: ID; `valid_from`: Date; `valid_to`: Date; `currency`: Currency; `unit`: Unit; `approved`: boolean; `approval_reference`: ID when approved, otherwise ID or explicit null; `price_minor`: Money. |
| `observations` | `observation_id`: ID; `store_id`: ID; `sku`: ID; `observed_on`: Date; `currency`: Currency; `unit`: Unit; `observed_minor`: Money. |

The final exception export explicitly carries currency and unit, rather than
assuming their units from an amount. All base, exception and observation
store/SKU references must exist. Their currency must equal the store's
currency and unit must equal the product's unit, or reject the bundle.
Every scope reference must resolve to a promotion, store and product.
A promotion may have another supported currency/unit: this makes it
ineligible for a differing observation; it is not a conversion. Promotions
without an explicit matching include do not apply.

All base, promotion and exception windows require `valid_from < valid_to`,
including disabled or unapproved records. Invalid records anywhere in a
bundle, including an out-of-audit observation or unused rule, reject the
bundle. Repeated primary keys reject even when their record values are
identical. One include and one exclude for the same promotion/store/SKU are
valid distinct scope keys; the exclude wins.

## Ordered procedure

### 1. Load and validate (`input`, `validation`)

Read the policy and all mapped arrays independently. Record the actual
filenames, record counts and supplied audit interval. Do not replace missing
tables or unknown values with zero or an empty array.

Validate the top-level shape, version, policy, filenames and array containers
before evaluating records. Visit roles in the table order above. Validate
record shapes, then process each role's records in canonical order (primary
key tuple, with canonical JSON as the secondary order for duplicate keys).
Check IDs, domains, supported rule modes/types, dates and windows before
cross-references. Foreign-key checks follow for bases, scopes, exceptions and
observations. Report the first deterministic validation error. A schema-error
record path uses its ordinal in canonical JSON order when a valid key cannot
be relied on; keyed paths otherwise use the record key. There is no
partial price audit of an invalid bundle.

Use only the supplied local calendar, not the computer's current date.
Require `audit_end - one day <= as_of`. Thus an audit ending the day **after**
`as_of` is valid: the exclusive end is not an included day.

### 2. Partition dates and join exact evidence (`join`)

Sort observations by `(observed_on, store_id, sku, observation_id)`.
An observation is included only when
`audit_start <= observed_on < audit_end`. Preserve every other observation in
`out_of_scope`, with `before-audit-start` or `at-or-after-audit-end`.
Do not join or price those excluded rows.

For each included observation:

1. Match base rows on the exact `(store_id, sku, unit, currency)` tuple.
   Record a date check for every such base version.
2. Active means `valid_from <= observed_on < valid_to`. Keep **all** active
   base IDs. Exactly one base is required, even if an approved exception exists.
3. Match exception rows on those same four dimensions, record each one's
   date check and approval flag, and keep every active **approved** exception.
   An unapproved record never applies; an approval reference never grants
   action authority.
4. Zero active bases means `MISSING_BASE_PRICE`; multiple active bases means
   `AMBIGUOUS_BASE_PRICE` even if their amounts agree. Multiple active approved
   exceptions means `AMBIGUOUS_APPROVED_EXCEPTION` even if their amounts agree.
   Report every applicable ambiguity code for that observation.

Any of these evidence errors makes the row `not-evaluable`. Preserve a
uniquely known base amount even if exceptions are ambiguous, but leave the
calculated/raw price, rounded price, delta and applied exception null. Do not
pick the first, latest or cheapest reference, guess zero, or use the observed
price as evidence of what the price should have been.

### 3. Explain applicability for every promotion (`decision`)

For **each included observation and every promotion**, in promotion-ID order,
record all failed filters in this fixed order:

1. `disabled`: `enabled` is false.
2. `outside-validity`: date is not in the promotion's half-open window.
3. `currency-mismatch`: currency differs from the observation.
4. `unit-mismatch`: unit differs from the observation.
5. `not-included`: no explicit include for the exact store/SKU.
6. `explicit-exclusion`: an exclude for the exact store/SKU exists.

The `reasons` array is empty **if and only if** the promotion is eligible.
Exclusion overrides inclusion. Continue to expose filter evidence on
not-evaluable rows, but compute no candidate prices for them.

### 4. Resolve the price policy (`decision`)

After the unique-evidence gate:

1. **One active approved exception:** use its `price_minor`, suppress every
   eligible promotion with reason `approved-exception`, and do not calculate
   promotion candidates.
2. **No eligible promotion:** use the unique base unchanged.
3. Otherwise retain the **highest numeric priority** among eligible
   promotions. Suppress every lower-priority rule as `lower-priority`.
4. If any retained rule is **exclusive**, form one candidate per exclusive
   rule. Suppress retained best-price/compound rules as `exclusive-present`.
   Exclusive candidates do not stack.
5. Otherwise form one candidate per **best-price** rule, plus **one** candidate
   containing **all** retained compound rules if any exist. Do not form
   compound subsets, stack priorities, or add an extra undiscounted base
   candidate.

For an amount-off single, candidate = maximum of zero and
`base_minor - value`. For a percent-off single, candidate =
`base_minor * (10000 - value) / 10000`. For the compound set:

* subtract the **sum** of its amount-off values from the original base;
* floor that subtotal at zero;
* multiply by **every** percent-off factor `(10000 - value) / 10000`.

Use exact decimal/rational arithmetic; **never round an intermediate**.
Observed price is not an input to selection. Choose the lowest **unrounded**
candidate. On an exact tie, compare each candidate's sorted promotion-ID tuple
lexicographically (ordinary string ordering, shorter equal-prefix tuple first).
Choose the smallest tuple and record **all** minimum-price tied tuples.
When there is no tie, the tie list is empty. Round-equivalent but unequal raw
prices are **not** a tie.

Eligible but unused rules retain a suppression reason: `higher-price` for a
losing candidate or `tie-break` for a nonwinning minimum-price candidate,
in addition to the precedence reasons above. For quarantined evidence, every
eligible rule is suppressed as `not-evaluable`. Selected rules are never also
listed as suppressed.

### 5. Round once and compare (`decision`)

Round the chosen final nonnegative unit price once, using `ROUND_HALF_UP`, to
integer minor units. Compute `delta_minor = observed_minor - expected_minor`.
The disposition is `mismatch` only when
`abs(delta_minor) > tolerance_minor`; equality to tolerance is a `match`.
This means a nonzero delta can legitimately be a tolerance match.

The demo illustrates the sample arithmetic:

* TEA: exclusive amount-off 300 at priority 20 on base 1999 gives **1699**,
  despite a same-priority 50% best-price and a lower-priority 40% offer.
* SOAP: compounded 10% and 20% on 999 gives **719.28**, lower than a 25%
  single's 749.25; final **719**, observed 720, delta **+1**.
* MUG: 50% of 1999 gives **999.5**, half-up **1000**, observed 999, delta **-1**.
* The next included day's approved TEA exception sets **1550**.

The demo SKUs have `01`, `02`, `03` components, so the documented row sort
places those three products in that order on the first date. Its four rows
give two matches and two mismatches at tolerance zero.

### 6. Register issues and publish (`exception`, `output`)

Create explicit exceptions for mismatches, not-evaluable rows and excluded
observations. Copy each into a human issue queue, including source IDs and the
next review action. A price tie is an explained deterministic decision, not
an exception. Reconcile all input observations exactly once:
`included = matched + mismatched + not_evaluable`,
`input = included + out_of_scope`.
Repeat these counts by store/currency, without summing money across
observations or currencies. Publish the complete output even when some
well-formed rows are quarantined.

## Exact result contract

All outputs are JSON, with no extra common-envelope keys:

| Key | Type and semantics |
| --- | --- |
| `schema_version` | Integer `1`. |
| `status` | `completed` if valid and no exceptions; `completed_with_exceptions` if valid but any mismatch, non-evaluable or excluded observation exists; `rejected` for the first business validation error. |
| `outputs` | Object with exactly the six keys below. |
| `exceptions` | Ordered array of the exception objects specified below; empty only for `completed`. |

The six `outputs` keys are `price_audit`, `rule_selection`, `out_of_scope`,
`issue_queue`, `reconciliation`, `review_packet`. The first four are arrays.

### `price_audit[]`: one row for every included observation

| Key | Type and semantics |
| --- | --- |
| `observation_id`, `observed_on`, `store_id`, `sku`, `currency`, `unit`, `observed_minor` | Exactly the corresponding validated observation fields and types. |
| `base_price_ids` | Sorted string array of all active exact-dimensional base IDs. |
| `base_minor` | Integer when exactly one base exists, otherwise null. |
| `active_exception_ids` | Sorted string array of active approved exact-dimensional exception IDs. |
| `applied_exception_id` | Chosen exception ID or null; null for non-evaluable rows. |
| `selected_promotion_ids` | Sorted winning candidate ID array, otherwise empty. |
| `pricing_basis` | `base`, `approved-exception`, `exclusive`, `best-price`, `compound`, or `not-evaluable`. |
| `unrounded_minor` | Exact nonnegative decimal **string**, no exponent, leading `+` or redundant trailing fractional zeros; integers have no decimal point. Null when not evaluable. |
| `expected_minor` | Final nonnegative integer minor units or null when not evaluable. |
| `delta_minor` | Signed integer observed-minus-expected or null when not evaluable. |
| `disposition` | `match`, `mismatch`, or `not-evaluable`. |

Null means **not calculated/not available**, never zero, not a wildcard and
not an amount to impute. Zero is a valid calculated price for a full discount.

### `rule_selection[]`: one explanation for every included observation

| Key | Type and semantics |
| --- | --- |
| `observation_id` | String linking to the audit row. |
| `base_checks` | Array of objects with exactly `price_id` (string) and `date_match` (boolean), for all matching four-dimension base versions, active or inactive. |
| `exception_checks` | Array of objects with exactly `exception_id` (string), `date_match` (boolean), `approved` (boolean), for all matching four-dimension exception versions. |
| `promotion_filters` | Array of objects with exactly `promotion_id` (string), `reasons` (string array using the six filter codes in fixed order). Includes every promotion, not just winners. |
| `winning_priority` | Signed integer used for promotion competition, otherwise null (including overrides, no offers and not-evaluable evidence). |
| `candidates` | Array of objects with exactly `promotion_ids` (sorted nonempty string array), `mode` (`exclusive`, `best-price`, `compound`), `unrounded_minor` (canonical exact decimal string). Only candidates that actually compete are priced. |
| `tied_promotion_sets` | Array of sorted promotion-ID arrays for all minimum-price candidates when at least two tie; otherwise empty. |
| `suppressed_promotions` | Array of objects with exactly `promotion_id` (string), `reason` (one of `approved-exception`, `lower-priority`, `exclusive-present`, `higher-price`, `tie-break`, `not-evaluable`). Only eligible but unused rules appear. |

### `out_of_scope[]`: one row for every excluded observation

Exactly the seven input observation keys (`observation_id`, `store_id`, `sku`,
`observed_on`, `currency`, `unit`, `observed_minor`), plus:
`expected_minor`: null; `delta_minor`: null;
`disposition`: `out-of-scope`; `reason`: `before-audit-start` or
`at-or-after-audit-end`. No expected price or selection ledger is created.

### Exceptions and `issue_queue[]`

Every envelope exception has exactly:
`code` (string from the table below), `message` (the exact fixed text below),
`path` (nonempty logical field/record path), `observation_id` (string or null),
`evidence_ids` (sorted unique string array).

Business-row paths are `observations.<observation_id>`. Validation paths
identify the role, record key and/or field; for a composite key its components
are joined with `|`. A shape path can use `[n]` for the zero-based canonical
record ordinal. Validation exceptions have null `observation_id` and empty
`evidence_ids` because the bundle is not yet validated.

| Code | Exact message |
| --- | --- |
| `INVALID_SCHEMA` | Fields or container types do not match the documented input schema. |
| `INVALID_IDENTIFIER` | Identifiers must use the SYN- synthetic identifier format. |
| `INVALID_VALUE` | A value has an unsupported type or domain. |
| `INVALID_DATE` | Dates must be real YYYY-MM-DD local-calendar dates in 2099. |
| `INVALID_WINDOW` | Window start must be before its exclusive end. |
| `FUTURE_AUDIT_WINDOW` | The final included audit day must not be after as_of. |
| `INVALID_SOURCE_MAP` | Source roles must map one-to-one to distinct bundled JSON export filenames. |
| `DUPLICATE_KEY` | An export contains a duplicate primary or scope key. |
| `UNKNOWN_REFERENCE` | A required export reference does not resolve exactly. |
| `DIMENSION_MISMATCH` | Currency or unit disagrees with the referenced store or product. |
| `UNSUPPORTED_RULE` | Only exclusive, best-price, compound, amount-off and percent-off rules are supported. |
| `INVALID_RATE` | Percent-off value must be an integer from 1 through 10000 basis points. |
| `UNSUPPORTED_POLICY` | Only ROUND_HALF_UP and store-local-calendar date basis are supported. |
| `MISSING_BASE_PRICE` | No base price matches the observation dimensions and date. |
| `AMBIGUOUS_BASE_PRICE` | More than one base price matches the observation dimensions and date. |
| `AMBIGUOUS_APPROVED_EXCEPTION` | More than one approved price exception matches the observation dimensions and date. |
| `PRICE_MISMATCH` | Absolute observed-minus-expected delta exceeds the configured tolerance. |
| `OUT_OF_AUDIT_WINDOW` | Observation is outside the half-open audit window; no price was evaluated. |

Mismatch evidence IDs are the sorted union of the chosen base, selected
promotions and applied exception. Base ambiguity lists all active base IDs;
exception ambiguity lists all active approved exception IDs. Missing-base and
out-of-window issues have an empty evidence list.

Each `issue_queue` row has exactly:

* `issue_id`: string `SYN-ISSUE-0001`, `SYN-ISSUE-0002`, ... in exception order
  (minimum four digits).
* `code`, `message`, `observation_id`, `evidence_ids`: same values and types as
  its envelope exception.
* `observed_on`, `store_id`, `sku`, `currency`: corresponding observation strings,
  or all null for rejected-bundle validation issues.
* `owner`: string exactly `Pricing operations analyst`.
* `next_action`: exact human-review instruction below.

| Issue | Exact `next_action` |
| --- | --- |
| Any business validation code | Correct the source export or policy and rerun the audit. |
| `MISSING_BASE_PRICE` | Obtain the missing dated base-price evidence before evaluating this observation. |
| `AMBIGUOUS_BASE_PRICE` | Resolve overlapping base-price versions; do not choose a price automatically. |
| `AMBIGUOUS_APPROVED_EXCEPTION` | Resolve the competing approvals and retain one authoritative synthetic exception. |
| `PRICE_MISMATCH` | Review the observation, chosen rules and rounding with the pricing reviewer. |
| `OUT_OF_AUDIT_WINDOW` | Confirm the intended audit period; keep this observation outside this review. |

### `reconciliation` and `review_packet`

For a valid bundle `reconciliation` has exactly these integer counts:
`input_observations`, `included_observations`, `matched`, `mismatched`,
`not_evaluable`, `out_of_scope`; plus `reconciled`: boolean indicating both
count identities above (must be true). Counts describe records, not financial
amounts. For a rejected bundle `reconciliation` is **null**, not six zeros.

`review_packet` always has exactly:

| Key | Type and semantics |
| --- | --- |
| `policy` | Object with `audit_start`, `audit_end`, `as_of` (Date strings), `tolerance_minor` (integer), `rounding` (`ROUND_HALF_UP`), `date_basis` (`store-local-calendar`); null on rejection. No filename map is copied into the decision output. |
| `owner_role` | `Pricing operations analyst`. |
| `review_state` | `ready-for-review` for completed/no issues, `review-required` for completed_with_exceptions, `input-rejected` for rejected. This is not a native installation or approval state. |
| `action_authorized` | Boolean **false**, always. |
| `counts_by_store_currency` | Array sorted by `(store_id, currency)`; each row has those two strings and the six integer count keys used by `reconciliation`. Only pairs occurring in observations appear; empty on rejection. |

On rejection, `price_audit`, `rule_selection` and `out_of_scope` are empty,
`issue_queue` and `exceptions` each have one validation issue, and no prices,
counts or even an apparently valid subset of the policy is certified.

### Stable ordering

Audit rows, explanation rows and excluded rows preserve the observation
date/store/SKU/ID order within their respective lists. Exceptions and issues
merge those dispositions in the same observation order, then sort by code for
multiple errors on a row. Evidence IDs, base checks, exception checks,
promotion filters and suppressed promotions are lexicographic by their ID.
Candidate members are sorted IDs; candidate and tie lists are sorted by those
ID tuples, **not by price**. JSON object-key order has no meaning; array order
does. Input record permutations must not change results. Filename remapping
changes only source-name trace evidence, not decisions.

## Local baseline and actual execution trace

The trusted local developer baseline uses only Python's standard library and
the shared CLI adapter. It reads the input bundle, does the procedure above,
and returns `(result, events)` without modifying the payload. It does not
call a service, Creator or any generated plugin.

From this scenario directory, with **fresh output filenames**:

```powershell
python -B baseline.py --input mock-data\demo.json --output baseline-output\demo.json --trace baseline-output\demo.trace.json
```

The shared adapter deliberately refuses to overwrite existing output/trace
files. The parent-owned shared evaluator handles explicit replacement of
generated local reports; do not delete or rewrite reference decisions to make
a comparison pass. A well-formed business rejection or mismatch result exits
0; malformed file bytes, filesystem errors and unexpected implementation
errors exit nonzero and cannot count as successful negative handling.

Each actual run captures eight documented stages in `workflow.json`, starting
with `input` and ending with `output`: source counts; validation; dimensional
and date joins; promotion filter outcomes; candidate selection and suppression;
raw/rounded comparison; real exceptions; reconciled review output.
Rejected business bundles can stop after the validation event.

An event has `step_id`, `kind`, `caption` (at most 260 characters),
`facts` (at most six scalar key/value pairs), and `tables` (one or two).
Each table has `title`, `columns` (one to six names), `rows` (up to eight
displayed arrays of scalar cells), `total_rows` (the **actual** full count)
and `highlight_rows` (displayed zero-based indices). Larger tables are honest
prefix samples of ordered actual rows, not a claim that omitted rows do not
exist. The adapter adds one-based `sequence` to each event and wraps them in
`schema_version: 1`, `provenance: synthetic-local-baseline`,
`scenario_id: retail-03`, `input_sha256` and `events`.

The parent/foundation centrally renders actual demo trace tables into
`demo\baseline.webm`; this scenario does not fabricate a video or native UI.
Every frame must say **Synthetic baseline execution visualization - not Cowork
or a live system**. Its media record binds inputs, actual results, trace,
encoder and fidelity checks. A video is a visualization of local execution,
not evidence that any plugin was created, installed or independently run.
If the central video is not present yet, report that prerequisite as pending.

## Native authoring, installation and independent invocation gate

**As of 2026-09-14: native creation BLOCKED/UNRUN, installation UNRUN,
independent invocation UNRUN, native comparison UNRUN.** Approved Computer
Use tools were removed. Both their restoration **and an unlocked accessible
native session**, followed by parent-coordinated authorization, are required.
There is no browser/Playwright, private API, cookie, token, shell, model or
skill alternative. Do not perform any native action while blocked.
Historical N00 publication was last `Publishing...`: its outcome is
**UNKNOWN, not Installed**; Creator was disabled. Inspect the actual Installed
state through the approved native path before any authorized retry.

Once the parent restores and authorizes that path:

1. Complete the centrally produced baseline video first. Stage **only** this
   exact allowlist: `HOW_TO.md`, `workflow.json`, `connections.json`,
   `mock-data/demo.json`, `demo/baseline.webm`. These five files must suffice
   for native creation. Do not include local implementation, evaluator
   material, other cases, reports or reference answers.
2. Through the approved visible native interface, ask Creator to implement
   this written file procedure and exact result contract, with configurable
   bundled source filenames and no live connections. Native instructions
   must not rely on reading or invoking `baseline.py`.
3. Record the actual creation/publication outcome; do not assume a historical
   attempt succeeded. Inspect real native installation state before claiming
   installation. Review generated artifacts through the authorized process;
   do not blindly execute downloaded code.
4. Independently invoke the installed native workflow against the supplied
   synthetic input using only the approved interface. Capture its actual
   output and native provenance. The parent evaluates it separately; a local
   comparison never becomes native evidence.

`connections.json` is `mock-exports-only`, `not-required`, with an empty
connection list. No access, connector metadata or availability is invented.
Never create a placeholder or locally assembled native ZIP. Creator runtime,
release/proof artifacts, historical downloads and the main checkout are out
of scope. Local success certifies only this trusted file-audit implementation
and its captured local evidence, not business authorization or native success.
