# Financial services scenario research

**Phase 1 only - proposed catalog entries, not implemented scenarios.**
Research date: **2026-09-14**. The three processes below use only invented
exports for **SYN-FIN Demonstration Company**, a fictional enterprise. No real
bank, brokerage, customer, account, balance, invoice, or transaction data is
included. Dollar values below are arithmetic examples, not actual holdings.

Build is gated on the parent's explicit **"15-scenario research catalog
approved/build"** message and the shared foundation contract. Contract v1 at
commit `d641b1f34328e5293e043d5975d0944b485236c0` was read without changing
shared files. No fixtures, goldens, baseline, trace, video, native plugin, or
successful execution claim is delivered in this phase.

| Proposed ID / directory | Process family | Bounded deliverable |
| --- | --- | --- |
| `financial-services-01` / `bank-ledger-reconciliation` | Evidence-constrained bank/ledger matching | Per-account reconciliation bridge, candidate matches, unresolved items, and a controller review packet |
| `financial-services-02` / `ap-three-way-match` | Procurement quantity/price exception matching | Invoice/PO/receipt comparisons, non-overlapping proposed receipt allocations, and an AP review queue |
| `financial-services-03` / `advisory-fee-reconciliation` | Effective-dated, tiered fee recomputation | Independently recomputed draft fees, variance and missing-evidence queues, and a billing review report |

All three end in **review-ready files**, not a posting, payment, debit, trade,
real approval, financial recommendation, or attestation of compliance.

## 1. Primary-source evidence and limits

Each reference below was retrieved and its actual relevant text read on
2026-09-14. Microsoft pages were read with the Microsoft Learn full-page
documentation tool. The two Interactive Brokers pages returned HTTP 200;
their public HTML was read with Python's standard-library HTTP/HTML parser
because the generic readability extractor selected their cookie notices.
No browser, account login, cookie manipulation, or native UI was used.

| ID | Exact primary page | What the retrieved text supports | Limits |
| --- | --- | --- | --- |
| B1 | Microsoft, [Reconcile bank statements by using advanced bank reconciliation](https://learn.microsoft.com/dynamics365/finance/cash-bank-management/reconcile-bank-statements-advanced-bank-reconciliation) | The **Validate the bank statement** section checks account, currency, prior closing/opening continuity, non-overlapping statement dates, line dates, and opening plus lines equals ending. **Reconcile the bank statement** describes cutoff dates, matched/unmatched amounts, one-to-one and grouped matches, and penny differences. | This is product behavior, not an accounting standard. Some described behavior changes with Modern bank reconciliation. The product can post corrections and journals; this corpus never does. |
| B2 | Microsoft, [Set up bank reconciliation matching rules](https://learn.microsoft.com/dynamics365/finance/cash-bank-management/set-up-bank-reconciliation-matching-rules) | The introduction explicitly says the default can take the first matching document and documents the **Require manual matching ... multiple documents that match on amount** setting. **Set up bank reconciliation matching rule sets** specifies ordered rules. | The proposed corpus deliberately requires ambiguity review, not the product's first-match default. Its manifest-constrained batching and stronger collision handling are fictional sample policies. |
| B3 | Microsoft, [Advanced bank reconciliation setup process](https://learn.microsoft.com/dynamics365/finance/cash-bank-management/configure-advanced-bank-reconciliation) | **Transaction code mapping**, **Cash and bank management parameters**, and **Bank account reconciliation options** describe account-specific code mappings, date-difference constraints, penny tolerance, signs, and time-zone interpretation. | No claim that our JSON is a supported Finance import schema or that a Finance connection exists. No universal date window or amount tolerance follows from this page. |
| P1 | Microsoft, [Accounts payable invoice matching overview](https://learn.microsoft.com/dynamics365/finance/accounts-payable/accounts-payable-invoice-matching) | The introduction and **Three-way matching** compare invoice/PO prices and invoice/selected-receipt quantities. **Two-way, price totals matching** explains percentage/amount tolerances, including the case where either exceeded limit is a discrepancy. **Related functionality** describes discrepancy review. | The sample's symmetric unit-price test plus line amount cap is an explicit simplification, not a complete reimplementation of Finance price-total matching. Tax, charges, discounts, currency conversion, and last-invoice cumulative checks are not silently approximated. |
| P2 | Microsoft, [Vendor invoices overview](https://learn.microsoft.com/dynamics365/finance/accounts-payable/vendor-invoices-overview) | **Preventing invoice submission to workflow** documents duplicate posted invoice-number controls when configured. **Matching vendor invoices to product receipts** permits partial receipt quantities and explains received quantities available through the current date. | The sample duplicate key and case normalization are invented controls. A matching result is not approval for posting or payment. Product workflow, batch posting, and recovery functions are excluded. |
| P3 | Microsoft, [Record vendor invoice and match against received quantity](https://learn.microsoft.com/dynamics365/finance/accounts-payable/tasks/record-vendor-invoice-match-against-received-quantity) | Identifies AP/accounting-manager actors, three-way matching, discrepancy approval configuration, and receipt/matching-details review. | This product walkthrough uses Microsoft's own demo company. Our company, numbers, thresholds, approval labels, and files are separately invented; no product walkthrough is being executed. |
| F1 | Interactive Brokers, [Advisor Fees](https://www.interactivebrokers.com/en/pricing/advisor-fees.php) | **Automatic Billing** lists annualized net-liquidation-value fees and **Blended Fee** with separate net-asset-value ranges/rates. Its notes say fee configuration requests pending client authorization are not in effect. **Send Fee Invoice Notifications to Your Clients** describes method, amount, and period in notices. | Vendor-specific options, not a universal fee rule or regulatory conclusion. Its actual automatic billing/debit, client consent, investment, and invoice submission functions are excluded. The synthetic approval field grants no permission. |
| F2 | Interactive Brokers, [Automatic Billing Methods and Examples](https://www.interactivebrokers.com/en/general/advisor-client-fee-examples.php) | **Percent of Net Liquidation Value** gives an annualized-percentage daily calculation using 252 business days; **Flat Fee** also states its 252-day allocation convention. | This is useful evidence that basis and timing must be specified, NOT support for our fictional actual-calendar-day formula. We intentionally do not copy 252-day billing or model flat/performance fees. |

### SEC retrieval gap, not a substituted citation

The indexed primary URL
[SEC, Division of Examinations Observations: Investment Advisers' Fee Calculations](https://www.sec.gov/files/exams-risk-alert-fee-calculations.pdf)
was discovered, but direct retrieval returned **HTTP 403**. The SEC
[announcement page](https://www.sec.gov/newsroom/whats-new/division-examinations-observations-investment-advisers-fee-calculations)
also returned 403. Their full contents are **not verified here**, and neither
is a normative or source-backed rule in this pack. Search-generated alternate
filenames, quotations, and summaries are not adopted as evidence. The fee
scenario instead relies on the two retrieved official vendor pages for its
limited process context. No statement about SEC requirements, examination
findings, jurisdictional duties, or regulatory compliance is inferred.

## 2. Common design and approval boundaries

**Every company-specific choice below is a fictional sample policy awaiting
catalog approval.** Source-backed concepts are cited separately from chosen
keys, tolerance values, exception precedence, schedules, and rounding.

| Concern | Proposed explicit rule |
| --- | --- |
| File inputs | UTF-8 JSON exports; finite values; reject duplicate JSON keys. JSON objects containing malformed business records remain valid negative-case files. No spreadsheet, PDF, OCR, banking-message, or broker-format parser is implied. |
| Identifiers | Nonempty ASCII synthetic IDs beginning `SYN-`; strict primary-key uniqueness even if duplicate rows are identical. Reference/number normalization trims outer ASCII whitespace and uppercases ASCII letters only; preserve punctuation and leading zeros. Never fuzzy-match names or descriptions. |
| Money and precision | Integer minor units only for exported money; USD/EUR have exponent 2. Fee calculations use exact integer numerators/denominators until one final rounding. Quantity is an integer number of thousandths; rates are integer basis points. Boolean, float, numeric-string, null, or nonfinite money/quantity/rate values are rejected, not coerced. |
| Numeric bounds | Sample bounds: absolute money/value at most `1,000,000,000,000` minor units, quantity at most `1,000,000,000` milliunits, rate/tolerance at most `10,000` basis points. Explicit source-row limit defaults to 5,000; exceeding it rejects rather than truncates. |
| Clock | Required `as_of` is an offset-bearing RFC 3339 timestamp; never use the wall clock. Required `business_utc_offset_minutes` is a true integer in [-840, 840]. Convert instants to this fixed offset before deriving business dates. Date-only fields are strict `YYYY-MM-DD` calendar dates. |
| Time-zone limitation | Fixed offset, not an IANA zone or an implicit local-machine default. No daylight-saving/holiday calendar approximation. A real DST/business-day workflow requires a supplied, verified calendar or a newly approved scope; no runtime package install. |
| Stable results | Sort scopes by legal entity/account/currency, invoice or billing account IDs, then source row IDs. Sort exception records by scope, record ID, and code. Preserve source IDs and explicit exclusion reasons. Never choose a candidate based on input order. |
| Integrity failures | Invalid scalar/key/date/configuration or mutually contradictory authoritative evidence rejects the entire input case before trusted financial outputs. Rejected results contain validation diagnostics, not plausible partial totals. Ordinary unmatched/late/pending/duplicate-business-document items become explicit business exceptions. |
| Approval | Approved synthetic policies permit deterministic classification only. All completed packets have `human_review = pending` and `live_action = none`. No output field is an access-control grant or permission to post, pay, charge, or trade. |
| Closure | Every input row is included, explicitly excluded, or rejected; every eligible business item has a disposition. Completing a report can coexist with unresolved items. Do not label outstanding differences as settled or an entire account as reconciled without its review evidence. |

The supplied top-level control configuration must be marked `approved` in
the synthetic dataset. A `pending` control configuration rejects the case
with `policy-not-approved` before financial decisions; an unknown approval
enum is malformed. This is distinct from a pending PO or pending fee-schedule
version, which is valid business evidence handled by its scenario's rules.

The common result envelope will follow foundation v1:
`schema_version`, `status`, `outputs`, and `exceptions`. Status is one of
`completed`, `completed_with_exceptions`, or `rejected`. Monetary comparisons
are exact; array ordering is part of the expected output.

### Files, native capabilities, and integrations

The development baseline will use only existing Python standard-library
facilities (`json`, `datetime`, integer arithmetic, `fractions` or `decimal`,
`collections`, `pathlib`) plus foundation `scenario_support.run_cli`.
It will expose `solve(payload) -> (result, events)`, have no Creator/generated
plugin dependency, and perform no external calls. It is a local comparison
baseline, not a deployed workflow engine.

Planned native input is the exact foundation allowlist: `HOW_TO.md`,
`workflow.json`, `connections.json`, `mock-data/demo.json`, and
`demo/baseline.webm`. Native receives procedure, actual-trace demonstration,
demo export, and connection metadata only. Research includes private test
designs and **must not be staged to Creator**, nor may baseline code, shared
code, sources/scenario metadata, expected files, outputs, holdouts, negatives,
or validation answers be staged.

Connection metadata will be `mode = mock-exports-only`,
`availability = not-required`, `connections = []`, with a note describing
supplied synthetic exports and native output files. There is no endpoint,
credential, auth flow, invented connection ID, or provisioned resource.
Actual export integrations remain unverified and are named per scenario
below. Host-native file/media understanding and permitted execution are
requirements to verify later, not claims established by offline Python.

**Native creation, installation, and independent invocation: NOT RUN /
BLOCKED as of 2026-09-14.** Both restored approved Computer Use tools and an
unlocked accessible session, with parent authorization, are required. No
alternate browser/Playwright, private API, cookies, tokens, or shell route
may substitute. Historical N00 stopped at `Publishing...`; its outcome is
UNKNOWN, not a pass. Frozen Creator 0.2.1 and historical artifacts stay
unchanged. No backend, custom MCP server, Azure resource, database, queue,
gateway, external scheduler/model/media service, runner, device agent, or
runtime installer is proposed.

## 3. FS-01: Bank-statement-to-ledger review packet

### Actors, trigger, and boundary

A treasury operations analyst receives a complete synthetic statement close,
ledger snapshot, and control export. The accounting controller reviews the
packet; source owners resolve missing or conflicting records. Trigger is an
operator-supplied closed statement/cutoff date, not a scheduler. Scope is one
statement period per synthetic bank account/currency, with multiple
independent scopes in an input. This models the validation and worksheet
concepts in B1-B3, not Finance posting or its full import/reversal machinery.

### Data and joins

- Statement headers: `legal_entity_id`, `account_id`, `statement_id`,
  `currency`, inclusive `from_date`/`through_date`, opening/closing minor units,
  and prior statement closing/date metadata. Header key is
  `(legal_entity_id, account_id, statement_id)`; periods for an account cannot
  overlap.
- Statement lines: unique `bank_line_id`, header key, `booked_at`, signed
  amount, bank transaction code, reference, optional explicit `batch_id`.
- Ledger snapshot headers and lines: matching account/currency/period,
  opening/closing, unique `ledger_line_id`, `posted_at`, signed amount,
  mapped ledger type/reference, and optional `expected_bank_date`.
  Extra ledger rows outside the period or after `as_of` are visibly excluded
  and are not part of the snapshot closing checksum.
- Approved sample controls: source sign orientation, one account-specific
  mapping per bank code, currency, cutoff, date gap, single-match amount
  tolerance, and timing/staleness windows.
- Explicit batch manifests: unique account-scoped `batch_id` and exact,
  nonempty member ledger IDs. No missing members, duplicate members, or member
  reuse across manifests. No subset-sum search or inference from equal totals.

This bounded design does not ingest prior-period open transaction detail.
A difference between bank and ledger opening balances remains an explicit
opening-difference exception; it is not manufactured into a current match.
Prior statement continuity checks refer to the bank's own previous close.

### Full workflow and actual-trace plan

| Step / kind | Actual operation and evidence to show after build |
| --- | --- |
| `intake-exports` / input | Load headers, line counts, control version, cutoff, source IDs; show the synthetic label. |
| `validate-close` / validation | Check types, unique keys, bank opening continuity, non-overlapping dates, line/header scope, and both close checksums. Show stated versus computed closes. |
| `normalize-cutoff` / validation | Apply declared sign orientation, transaction mappings, fixed-offset business dates, and visible cutoff exclusions. |
| `join-candidates` / join | Resolve complete batch membership; build all eligible single-match edges. Show member IDs, sums, date gaps, and candidate counts. |
| `decide-matches` / decision | Accept exact unambiguous batch groups and symmetric-unique single pairs only; show matched source IDs and amount delta. |
| `route-unresolved` / exception | Route ambiguity, amount/date/type mismatch, unmapped code, incomplete batch, bank-only fee, timing, and stale ledger items with owner/reason. |
| `bridge-balances` / decision | Compute closing difference and its opening/matched-delta/unmatched components; never hide a penny adjustment. |
| `emit-review-packet` / output | Emit all groups, remaining items, exclusions, per-scope bridge totals, pending controller review, and no live action. |

### Proposed sample parameters and numerical semantics

Default sample settings: `max_match_calendar_days = 2`,
`single_amount_tolerance_minor = 0`, `timing_grace_calendar_days = 2`,
`stale_after_calendar_days = 5`, currency USD, fixed offset UTC.
The cutoff must equal the statement's through-date and cannot exceed the
business date of `as_of`. Both source closes cover exactly the included
period/cutoff. Signed positive means increase in the company's cash; sign
reversal is applied only when explicitly declared by the source control.
Raw opening/closing/previous-close and line amounts must share their source's
declared orientation; normalize all of them together, never just the lines.

Batch members are reserved before single matching, including a failed batch,
so its lines cannot silently fall back to unrelated singles. A batch requires
one bank line, its exact manifest, same scope/type, each member's date within
the configured gap, and an **exact signed sum**. Multiple bank lines claiming
one batch are ambiguous and all remain unresolved.

Singles require the same scope, nonempty canonical reference, compatible
type, date gap at most the configured number of calendar days, and absolute
minor-unit difference at most the single tolerance. Build the entire
bipartite candidate graph before assignment. A connected component with more
than one candidate on either side is entirely held; no first, nearest-date,
closest-amount, or maximum-cardinality guess. Unmapped codes do not match.
Amount-only or free-text fallback is forbidden.

A tolerated nonzero delta can yield a candidate pair, but its adjustment
remains pending human review. No ledger is changed. Unmatched ledger rows
with an explicit expected bank date after cutoff and within the grace window
are `pending-clearance`, not proven cleared. Other unmatched rows remain
unresolved; age beyond the configured staleness window adds an investigation
reason. Age equals the threshold is not stale. Bank-only fees are proposed
items, never automatically booked.

Per scope, with `delta = bank matched sum - ledger matched sum`:

```text
closing_bank - closing_ledger
  = opening_bank - opening_ledger
    + sum(unmatched_bank) - sum(unmatched_ledger) + sum(match_deltas)
```

The bridge is an arithmetic identity plus explanations, not proof that a
match is correct. Every included row must participate exactly once in a
matched group or the unmatched partitions. Unexplained opening differences,
unmatched items, or nonzero proposed adjustments prevent a clean disposition.

### Concrete case designs (not fixture files)

| Case | Invented inputs and independently reasoned target |
| --- | --- |
| `demo` | June 2026, one USD account, both openings 100,000 cents. Bank rows: +12,000 direct, -7,500 batch, -250 bank-only fee, +3,000 ambiguous. Ledger rows: +12,000 direct, -5,000 and -2,500 explicit batch members, two +3,000 rows with the same ambiguous reference, and -4,000 June 30 pending clearance expected July 1. Bank close is 107,250; ledger close is 106,500. Exactly two match groups consume two bank/three ledger rows. Two bank and three ledger rows remain unmatched. Bridge is 2,750 - 2,000 = 750 cents, not zero. `completed_with_exceptions`. |
| `holdout-a` | Different cardinality and scopes: account A has bank +3,000 against an explicit three-member +1,000/+1,500/+500 batch, and +10,002 against +10,000 with a two-day gap and tolerance 2 cents. A bank -1,000 and ledger -1,000 share a reference but have a five-day gap, so neither matches. Zero openings give closes 12,002 and 12,000; only the 2-cent candidate correction explains the gap. Account B opens at 50,000 and has a separate +7,000 pair with the same reference as another account: close 57,000 on both sides. Three groups total, no cross-account match, no posted penny correction. `completed_with_exceptions`. |
| `holdout-b` | Different timing and amount boundaries: offset -300 minutes, `as_of = 2026-08-01T04:59:59Z`, July close. A +20,000 bank row at `2026-08-01T04:30:00Z` is July 31 locally and matches +20,000. A +1,003 bank row versus +1,000 ledger fails a 2-cent tolerance. Ledger -1,500 expects August 1 clearing; +9,900 at `2026-08-01T05:00:00Z` is after cutoff and excluded. Zero openings yield bank close 21,003 and included ledger close 19,500. One match, one timing item, one excluded future row; difference 1,503 = 1,003 - (1,000 - 1,500). `completed_with_exceptions`. |
| `negative-malformed` | Valid JSON with a bank amount `true`, alongside otherwise valid rows. Reject the whole case at validation; do not coerce to one cent or emit trusted matches/totals. `rejected`. |
| `negative-contradictory` | Internally well-typed header claims closing 100,001 when opening plus all eligible bank lines equals 100,000. Reject the contradictory close before matching rather than fabricate a one-cent correction. `rejected`. |

Additional post-gate targeted checks: shared batch membership, duplicate
technical IDs, same-ledger competition across bank rows, missing type mapping,
wrong currency, exact date/tolerance/staleness boundaries, unsupported
timestamp offsets, and source-row permutation invariance. These are planned
checks, not claims of tests already run.

### Expected-output independence, closure, and gaps

Before implementing the baseline, enumerate candidate graphs and batch
members on paper; independently add the signed partitions and both close
checksums. Write the five expected envelopes from these derivations, not
from program output. Assert membership and reasons, not just equal totals.
Planned outputs include `matches`, `unmatched_bank`, `unmatched_ledger`,
`excluded`, `scope_summaries`, `review`, and rule/control provenance.

Accepted sample mechanics can classify candidates. Controller acceptance,
opening-balance explanation, fee booking, penny correction, and ambiguity
resolution remain pending outside this process. A changed source export
requires a new deterministic report; it does not mutate the original.

Actual bank statement/ledger exports, mapping ownership, source integrity,
statement completeness, real bank identifiers, and any approved Finance or
bank connection remain unverified. No BAI2/MT940/CAMT.053 parser, reversal
engine, journal connector, posting permission, or live balance lookup is
provided.

## 4. FS-02: AP invoice/PO/receipt exception review

### Actors, trigger, and boundary

An AP analyst reviews an incoming batch of synthetic vendor invoices against
approved PO lines, posted receipt exports, and historical invoice/receipt
allocation records. Procurement and receiving owners resolve discrepancies;
an AP manager reviews the packet. Trigger is an operator-supplied export
batch and `as_of`. The process stops before posting or any payment step.
P1-P3 ground the business process, not the invented numbers or policies.

### Data and joins

- Invoice headers have unique `invoice_id`, legal entity, vendor, currency,
  vendor invoice number, invoice timestamp, and net total; lines have unique
  `(invoice_id, line_id)`, PO line key, unit of measure, quantity in
  milliunits, unit price in minor units, declared line net, and explicit
  selected receipt IDs/quantities when supplied.
- PO lines are unique by `(legal_entity_id, po_id, po_line_id)` and carry
  vendor, currency, unit, ordered quantity, price, and approval status/time.
- Receipt lines have unique `receipt_line_id`, exact PO line key, quantity,
  unit, and received/posted timestamps. Only posted receipts available by
  `as_of` can satisfy quantity; physical receipt before cutoff does not make
  a later posting available.
- Historical invoice headers and prior allocation rows have their own unique
  IDs. Each prior allocation refers to an existing posted historical invoice,
  PO line, and receipt line. Total historical use cannot exceed a receipt or
  PO's quantity; contradiction rejects rather than clamps to zero. History
  includes `posted_at` and allocations include `recorded_at`; future records
  are visibly excluded from as-of duplicate/capacity calculations. An
  allocation already recorded by cutoff against an invoice not yet posted
  by cutoff is contradictory evidence, not usable prior consumption.
- Sample tolerance configuration has a declared approved state, default
  unit-price tolerance of 200 basis points and per-line cap of 500 cents.

Duplicate business-document key is
`(legal_entity_id, vendor_id, canonical_vendor_invoice_number)`.
Matching a posted historical key blocks an incoming invoice. Two incoming
invoices with distinct IDs but this same key both enter the duplicate queue;
neither wins. Unlike a duplicate primary key, this is a business exception,
not invalid JSON. History uses one header per invoice, not one duplicate
header per allocation.

### Full workflow and actual-trace plan

| Step / kind | Actual operation and visible evidence |
| --- | --- |
| `intake-documents` / input | Load invoice, PO, receipt, history, and control counts; display batch/as-of identity. |
| `validate-documents` / validation | Validate primary keys, scalar types, line/header sums, quantities, dates, and historical capacity integrity. |
| `join-duplicates-and-pos` / join | Compare canonical document keys with current/history sets; join exact PO lines and verify entity/vendor/currency/unit/approval. |
| `join-receipt-evidence` / join | Resolve explicit partial receipt quantities or identify a sole eligible receipt; show historical use, availability, and late/missing evidence. |
| `evaluate-price-and-quantity` / decision | Display exact line net, percentage cross-products, absolute variance, and receipt demand. Apply both price limits and exact selected quantity. |
| `resolve-capacity-conflicts` / decision | Detect all competing eligible invoices before accepting any proposed allocation; show every oversubscribed receipt/PO and held invoice. |
| `route-invoice-holds` / exception | Emit atomic per-invoice holds with duplicate, price, quantity, missing approval, selection, timing, and conflict reasons/owners. |
| `emit-ap-review` / output | Emit line comparisons, proposed allocations, remaining capacities, ready/held amounts, and pending AP manager review. No posting/payment instruction. |

### Proposed sample parameters and numerical semantics

Quantities are integer milliunits, enabling values such as 1.250 units without
binary floating point. Prices are cents per whole unit. Declared line net
must equal `ROUND_HALF_UP(quantity_milliunits * unit_price_minor / 1000)`.
All invoice header totals must equal the sum of their independently rounded
lines. All charges, discounts, tax, and freight must be zero in this bounded
sample; a nonzero value creates an explicit unsupported-scope invoice hold,
not an ignored amount. Such an invoice is held before applying the
zero-component line formula; the declared header must still equal its
declared line-net sum. Do not reinterpret its nonzero components as a price
variance or conceal them in ready totals.

For positive PO unit price, both limits must pass, inclusively:

```text
abs(invoice_unit_price - po_unit_price) * 10000
    <= po_unit_price * unit_tolerance_bps
abs(invoice_line_net - rounded_po_price_for_invoice_quantity)
    <= line_amount_cap_minor
```

This symmetric test is a **fictional policy**. It is not a claim that Finance
uses symmetric tolerances, this exact combination, or per-invoice line caps
for its full cumulative price-total validation. A zero-price PO requires
zero invoice price/net; never divide by zero. Negative quantities/prices,
credit notes, returns/reversals, currency conversion, and unit conversion
are outside the approved sample scope.

Explicit selected receipt quantities must sum exactly to invoiced quantity.
Partial use and multiple selected receipts are supported. Without explicit
selection, the candidate set must contain exactly one eligible
positive-capacity receipt, and it must have sufficient capacity. Several
eligible positive-capacity receipts require selection even if only one could
satisfy the full quantity; do not use FIFO or a subset search. A short
receipt never authorizes part of an invoice.

Before competition, remove every invoice with any duplicate, missing
approval, unsupported scope, invalid selection, individual capacity, or price
hold. Then aggregate proposed demand across all remaining invoices, both
per receipt and per PO line, net of historical allocations. For every
oversubscribed resource, hold **all** competing invoices. Do not choose an
input-order winner, retry freed capacity in the same run, or partially release
an invoice. Retain all original line evaluations for diagnostics. Remaining
accepted allocations are proposals in the output only and cannot change
history or consume real capacity.

### Concrete case designs (not fixture files)

| Case | Invented inputs and independently reasoned target |
| --- | --- |
| `demo` | Four incoming invoices. A: 6 units at 1,010 cents against PO 1,000, net 6,060; selected receipts 3 + 3 units from receipts of 3 and 4 units with 1 unit historically used on the second. Price variance 1%, line variance 60 cents, quantity 6: ready for review. B: 5 units at 2,000, net 10,000, but only 3 receipted: hold all 5 with shortage 2. C: net 5,000 and vendor number ` SYN-DUP-09 ` duplicates posted `SYN-DUP-09`: hold, allocate nothing. D: 1 unit at 10,300 against 10,000: 3% fails even though 300 cents is below the 500-cent cap. Ready amount 6,060; held amount 25,300; intake total 31,360. `completed_with_exceptions`. |
| `holdout-a` | Two distinct invoices each request 1 unit from the same 1-unit available receipt at 20,000 cents: hold both, never accept the first. An independent 1.250-unit line at 816 versus PO 800 cents is exactly 2%: net 1,020 versus 1,000, accepted as a proposal. Another invoice for 100 units at 1,010 versus PO 1,000 has 1% unit variance but a 1,000-cent line variance exceeding the 500-cent cap: hold. Ready 1,020; held 141,000; intake 142,020. This changes competition, fractional quantity, and which tolerance is decisive. `completed_with_exceptions`. |
| `holdout-b` | Offset -300 minutes, `as_of = 2026-08-01T04:59:59Z`. A: 1.250 units at 1,002 cents gives 1,252.5 cents, rounded once to 1,253; its receipt posted at 04:30Z is available July 31 locally. B: 2 units at 3,000, net 6,000, has a physically received receipt posted at 05:00Z, after cutoff: hold. C: net 4,000 has a pending PO approval: hold. D/E each net 500 use `  syn-mix-12  ` and `SYN-MIX-12` with distinct IDs for the same vendor/entity: both held as incoming duplicates. Ready 1,253; held 11,000; intake 12,253. `completed_with_exceptions`. |
| `negative-malformed` | Valid JSON with `quantity_milliunits = true`. Reject the case before arithmetic or allocation; no coercion and no partial ready invoice. `rejected`. |
| `negative-contradictory` | Historical authoritative allocation says 1,001 milliunits used from a receipt that contains only 1,000. Reject inconsistent capacity evidence instead of clamping the remaining quantity or allowing another allocation. `rejected`. |

Post-gate targeted checks also include exact zero-price behavior, duplicate
technical IDs versus duplicate business keys, missing multi-receipt selection,
cross-vendor/unit/currency joins, multiple lines sharing PO capacity, invoice
atomicity, nonzero unsupported charges, and permutation invariance.

### Expected-output independence, closure, and gaps

Before coding, make a document-key ledger and a receipt/PO capacity worksheet.
Mark duplicate and other individual holds first; compute each line's price
cross-products/net independently; mark all oversubscribed-resource
participants simultaneously. Independently total ready and held invoices.
The expected files will explicitly list row dispositions and allocations so
a baseline cannot pass merely by reaching the same total.

Planned outputs: `invoice_reviews`, `line_comparisons`,
`proposed_allocations`, `remaining_capacity`, `excluded_receipts`,
`summary`, and `review`. The AP manager, procurement owner, or receiving owner
must resolve each hold in real operations. The report never changes invoice
quantities, updates a PO, posts an invoice, or proposes an actual payment.

ERP invoice/PO/receipt/history exports, trustworthy prior allocation history,
real approval identity, vendor-master mapping, and existing approved Finance
connections remain unverified. There is no invoice capture/OCR, AP posting,
payment connector, tax engine, procurement API, or automated workflow service.

## 5. FS-03: Advisory fee billing reconciliation

### Actors, trigger, and boundary

A billing operations analyst compares synthetic draft fee lines with
effective-dated sample agreements, approved/pending schedules, synthetic
billable-value intervals, and engagement dates. A billing manager/compliance
reviewer receives the complete exception packet. Trigger is a supplied closed
billing period and `as_of`; it is not a trade event, market feed, or scheduler.
F1-F2 establish that rate ranges, basis, billing timing, and pending
configuration are real vendor concerns. All formula choices here are invented.

### Data and temporal joins

- Engagements: unique `billing_account_id`, currency, `active_from`, exclusive
  `active_to` (or null), and exact agreement ID. IDs and values are fictional,
  not real customer accounts or assets.
- Schedule versions: unique `schedule_id`, account/agreement, exclusive
  effective interval, `approval_state`, approval timestamp when approved, and
  marginal bands with upper bounds in minor units and integer annual bps.
- Synthetic billable-value intervals: unique `valuation_id`, account,
  currency, inclusive start/exclusive end, and nonnegative value in cents.
  Values are declared constant for that exact interval, not interpolated
  prices or inferred daily balances.
- Draft fee lines: unique `draft_id`, account, exact period start/end,
  currency, nonnegative amount in cents, and source schedule ID if supplied. Business key
  is `(billing_account_id, period_start, period_end, currency)`.
- Approved fictional configuration: period, fixed-offset timezone, day-count
  basis, rounding mode, currency, and variance tolerance. No asset positions,
  securities, orders, performance, or real debits are input.

For every active billable day there must be exactly one approved schedule
known by `as_of` and exactly one value interval. Split at engagement changes,
approved schedule boundaries, valuation boundaries, and January 1 when using
actual-calendar-year day counts. Missing evidence holds the affected account;
no forward-fill or latest-version guess. Overlapping approved schedules or
overlapping authoritative value intervals are contradictory evidence and
reject the entire case. A pending schedule does not override a complete
approved schedule, but remains a visible pending-change flag. An approval
after `as_of` is not eligible; its status is explicitly shown.

### Full workflow and actual-trace plan

| Step / kind | Actual operation and visible evidence |
| --- | --- |
| `intake-billing-exports` / input | Show engagement, schedule, value, and draft counts plus supplied period/as-of. |
| `validate-billing-evidence` / validation | Validate keys, finite integer units, currency, contiguous tier coverage, period closure, and noncontradictory intervals. |
| `join-effective-segments` / join | Intersect active dates, approved schedule versions, and value intervals; show each segment's days and exact evidence IDs. |
| `calculate-marginal-tiers` / decision | Show value apportioned into each marginal band and annual rate numerators; never apply the last tier to the whole value. |
| `prorate-and-round` / decision | Show segment day-count denominators and exact fee fractions, then one final account-period rounding. |
| `join-draft-fees` / join | Join exact account/period/currency keys; distinguish one draft, no draft, and duplicate drafts; show comparable amounts and signed deltas. |
| `route-billing-exceptions` / exception | Queue missing coverage, pending changes, duplicate/wrong-period drafts, overstatement, and understatement without charging or refunding anything. |
| `emit-billing-review` / output | Emit full account review table, calculation segments, comparable-only totals, uncomputed/missing-draft populations, and pending human review. |

### Proposed sample formula and precision

Default fictional policy: USD, marginal annual rates of 100 bps on the first
100,000 dollars and 50 bps above it, `day_count_basis = actual-calendar-year`,
`rounding_mode = half-up`, and `variance_tolerance_minor = 1`.
Schedules and parameters are inputs, not embedded company rules.

Intervals are half-open `[start, end)` in local calendar dates. The period
must have ended by `as_of` at midnight in the supplied fixed offset.
Opening day is included; termination/effective-end day is excluded.
Maximum approved sample period length is 366 days. Leap years use 366 and
other years 365 under `actual-calendar-year`; `act-365-fixed` is a separate
explicitly supported option, not a silent substitute.

For each constant segment, value is sliced into consecutive marginal bands,
starting at zero, with strictly increasing upper bounds and a final unbounded
band. Negative/overlapping/gapped bounds, boolean rates, or rates outside
0..10,000 bps are invalid. No household aggregation, whole-balance cliff
tiers, performance fees, cash-flow adjustment, securities exclusions, fee
minimums, or tax are inferred.

```text
segment_fee_in_minor_units
  = sum(band_value_minor * annual_rate_bps) * active_calendar_days
    / (10000 * day_count_denominator)

account_period_fee_minor
  = round_once(sum(all exact segment fee fractions), rounding_mode)
```

Use exact integer rational arithmetic throughout; integer precision is
unbounded, exported values have the declared bounds, and output money has
two decimal places. No intermediate segment/daily cent rounding. `half-up`
rounds an exact half cent upward for these nonnegative fees; `half-even`
rounds a tie to the even minor unit. Only these explicit modes are supported.
Display-only decimals in a future trace must not replace the exact arithmetic.

The 365/366 calendar-day method, mid-period effective changes, marginal
formula, rounding frequency, and tolerance are **fictional agreement
policies**, not SEC rules or an IBKR replica. F2 actually documents a
252-business-day example; its different basis must not be silently blended
with this one.

Exactly one valid draft permits `delta = draft - computed`.
Positive is draft overstatement; negative is understatement; absolute delta
at most tolerance is within the sample comparison policy. Duplicate drafts
are never summed or chosen arbitrarily. Missing drafts or uncomputable
accounts are not treated as zero. Report totals for comparable accounts
separately from computed-but-missing-draft and uncomputed populations.
Orphan, wrong-period, and wrong-currency drafts remain explicit exception
rows rather than disappearing in an inner join. A draft's optional schedule
label is context, not authority to override the approved temporal join.
Even an amount match with a pending schedule change requires visible review.

### Concrete case designs (not fixture files)

| Case | Invented inputs and independently reasoned target |
| --- | --- |
| `demo` | April 1-May 1, 2026. A has value 150,000 dollars: first 15 days use 100/50 bps bands (annual fee 1,250 dollars), next 15 use an approved 80/40 bps schedule (annual fee 1,000 dollars). Fee is `(125000*15 + 100000*15)/365 = 9246.575...` cents, rounded once to 9,247. Draft 10,274 overstates by 1,027. B opens April 11, value 100,000 dollars, 20 days at 100 bps: `100000*20/365 = 5479.452...` cents -> 5,479, matching its draft. B also has an overlapping pending 50-bps request: show it but do not apply it. C has 50,000 dollars for 30 days at 100 bps: `50000*30/365` -> 4,110 cents, with no draft. Computed total 18,836; comparable computed 14,726 versus draft 15,753; comparable delta +1,027; missing-draft computed amount 4,110. `completed_with_exceptions`. |
| `holdout-a` | Leap February 2024. A is active Feb 15-Mar 1: seven days at value 100,000 dollars (annual fee 100,000 cents), then eight days at 200,000 dollars (annual fee 150,000 cents). `(100000*7 + 150000*8)/366` -> 5,191 cents. Draft 5,205 incorrectly resembles a 365-day calculation: +14 variance. B terminates Feb 11 after 10 billable days at 50,000 dollars: `50000*10/366` -> 1,366 cents; two different draft IDs each carry that amount for the same period, so comparison is blocked, not summed. Computed total 6,557; only A contributes to comparable totals. This changes leap basis, value segments, start/end proration, and duplicate handling. `completed_with_exceptions`. |
| `holdout-b` | One-day closed period Jan 1-Jan 2, 2026, offset -300, `as_of = 2026-01-02T05:00:00Z`, `act-365-fixed`, zero variance tolerance, half-up. A has value 365 dollars and a 50-bps single band: `36500*50/(10000*365) = 0.5` cent exactly -> 1 cent; draft 0 is a 1-cent understatement. B has value 100,000.01 dollars with 100/50 bps marginal bands: the last band contains only one cent, not the whole value, and the one-day fee rounds to 274 cents; draft 274 matches. Computed total 275 versus draft 274, signed delta -1. A separate parameter-only check with half-even must change A to 0 without changing B. `completed_with_exceptions` for the half-up holdout. |
| `negative-malformed` | Valid JSON with `annual_rate_bps = true`. Reject before creating rate segments; do not coerce it to one basis point. `rejected`. |
| `negative-contradictory` | Two approved, known-by-as-of schedule versions cover the same account/day, with different rates. Reject the conflicting authoritative policy instead of selecting the newest ID/date or generating a plausible fee. `rejected`. |

Further post-gate checks: exact tier boundary, missing value day, adjacent
versus overlapping intervals, approval timestamp after as-of, year-crossing
denominators, termination-day exclusion, wrong-period/currency draft,
unsupported household/performance settings, and input-order invariance.

### Expected-output independence, closure, and gaps

Manually build a date-segment/tier worksheet first. Record each segment's
inclusive day count, exclusive endpoint, band allocation, exact numerator
and denominator, final tie decision, and comparison population. Construct
expected JSON before baseline execution. Do not derive goldens by rerunning
the baseline, copying its outputs, importing it, or using generated plugin
results. Assertions must cover approved-versus-pending schedule IDs and
uncomputed/duplicate populations, not just rounded sums.

Planned outputs: `account_reviews`, `calculation_segments`,
`draft_comparisons`, `pending_changes`, `population_totals`, and `review`.
The billing reviewer must accept any corrected draft outside this process.
No fee is sent to a client, debited, refunded, or posted. No trading,
investment advice, asset valuation, contract interpretation, or compliance
opinion is delivered.

Actual signed agreement interpretation, schedule approval provenance,
billable-value completeness, custody/billing exports, calendars, and real
approved connections remain unverified. No brokerage endpoint, client
authorization, market feed, pricing service, advisor portal runner, or debit
integration is fabricated.

## 6. Post-approval implementation and evidence plan

After the explicit catalog/build gate, create exactly the foundation layout
for each proposed directory: scenario/workflow/source/connection metadata,
one complete `HOW_TO.md`, demo plus two changed holdouts and two negatives,
independently derived expected JSON, stdlib baseline, and generated baseline
outputs and actual traces. Keep sector commits separate from foundation.

Expected derivation is independent **of the implementation** and should be
written first, with arithmetic reasoning preserved. This is an author
declaration, not proof that an independent human has approved the material.
Any external reviewer acceptance remains pending.

Use foundation's existing stdlib validation/comparison tools when supplied.
Run all five cases per scenario and sector-specific boundary tests, compare
exact envelopes, and confirm expected files were unchanged. Check row
conservation, capacity conservation, and fee coverage invariants. Failures
must remain visible; do not regenerate goldens to make a baseline pass.

Each demo will produce at least the eight meaningful observed states above,
with input first and output last and all six foundation kinds. Future trace
tables will show actual IDs, amounts, joins, thresholds, intermediate
calculations, decisions, and final exceptions, with at most six columns and
eight displayed rows per table; label any faithful subset. No trace is
invented from a golden or emitted before execution.

Foundation centrally renders 30-90 second readable videos from those actual
traces, labeled **Synthetic baseline execution visualization - not Cowork or
a live system**. Video/trace/output artifacts remain under `scenarios`.
Native-generated plugins belong only in the parent's later root `output`
workflow after approved access returns. No local mock plugin ZIP,
`Installed`, native `passed`, or publication-success status is fabricated.
