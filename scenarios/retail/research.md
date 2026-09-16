# Retail validation research catalog

**Phase 1 only. Research complete; parent catalog approval and build gate are
pending.** This catalog qualifies three bounded processes. It does not create
scenario fixtures, goldens, a baseline, a video, or a native plugin.

Research date: **2026-09-14**. All eight sources below were fetched from their
official publishers on that date, not accepted solely from search summaries.
The companion `research.json` is an evaluator-facing research catalog, not a
replacement for the shared scenario schema.

The approved interface is `scenarios/SCENARIO_CONTRACT.md`, version 1, introduced
by shared commit `d641b1f34328e5293e043d5975d0944b485236c0`. Construction must wait
until the parent approves the complete, at-least-15-scenario catalog. The
three proposed retail folders are:

| ID | Proposed slug | Workflow family | Human owner | Bounded result |
| --- | --- | --- | --- | --- |
| retail-01 | store-replenishment-proposal | constrained-inventory-allocation | Replenishment planner | Capacity-feasible store/DC proposal and shortage review packet |
| retail-02 | returns-refund-reconciliation | original-transaction-reconciliation | Returns reconciliation analyst | Original-order-linked quantity and refund proposal ledger |
| retail-03 | promotion-price-audit | temporal-pricing-rule-audit | Pricing operations analyst | Store/SKU/date price comparison and exception packet |

## Evidence ledger and limits

**R1 - Oracle, Replenishment.** [Official page][R1]. Retrieved 2026-09-14.
The overview describes replenishing stores or warehouses from suppliers or
warehouses, item/location inventory monitoring, recommendations as an
alternative to automatically creating orders, demand-forecast integration,
and supplier/location attributes for rounding and constraints. This supports
a recommendation-only process boundary. It does **not** specify this catalog's
DC case budget, priority queue, daily lost-demand model, or case-ceiling rule.
The URL is Oracle's unversioned `latest` documentation; no installed Oracle
version or integration is asserted.

**R2 - Microsoft, Replenishment methods and quantity modification.**
[Official page][R2]. Retrieved 2026-09-14. The sections "Coverage codes" and
"Impact of the order quantity from default order settings" document
period/requirement/minimum-maximum/manual planning and order quantities that
are multiples of a configured quantity. Microsoft's minimum-maximum examples
can choose a multiple below the maximum before considering an overshoot.
Our unconditional ceiling to whole cases is therefore a **sample policy**,
not a reproduction of that algorithm.

**R3 - Microsoft, Overview of the Forecast to plan business process areas.**
[Official page][R3]. Retrieved 2026-09-14. "Establish stocking and replenishment
policies", "Forecast supply and demand", and "Plan supply and replenishment"
connect demand, inventory, safety stock, replenishment lead times, planning
horizons, and capacity considerations. This is cross-product business-process
guidance, not an exact retail allocation formula or a live data guarantee.

**R4 - Microsoft, Create returns in POS.** [Official page][R4].
Retrieved 2026-09-14. "Process returns by using the return transaction
operation" describes original receipt/order/invoice lookup, original and
previously returned quantities, the available-to-return quantity limit, and
return reason codes. "Return processing improvements when the connection to
headquarters is down" explains that synchronized return quantities may be
stale. "Enable proper tax calculation for returns with partial quantity"
describes preserving originally charged tax across partial returns.
These concepts support reconciliation, but do not establish a universal
return window, condition policy, statutory entitlement, or penny allocation.
The nonvalidated "Return product" operation is not our process.

**R5 - Microsoft, Linked refunds of previously approved and confirmed
transactions.** [Official page][R5]. Retrieved 2026-09-14.
The introduction and supported/unsupported-flow sections describe full or
partial linked refunds against a previously approved and confirmed
transaction, bounded by the original authorization. Actual execution has
payment-configuration and connector prerequisites; some multi-invoice,
exchange, gift-card, and receiptless flows are unsupported. We copy no tokens,
configure no payment connector, and initiate no refund. An original
confirmation in a fixture is historical synthetic evidence, not permission
to act.

**R6 - Microsoft, Retail discounts.** [Official page][R6].
Retrieved 2026-09-14. "Manage discounts" describes enabled status, currency,
unit-of-measure and product applicability, pricing priority, exclusive/best
price/compounded concurrency, and exclusion lines overriding inclusion lines.
"Best practices" recommends a documented discount strategy and testing
configuration before enablement. The actual engine has many more discount
types and contextual rules than our single-unit audit.

**R7 - Microsoft, Pricing settings.** [Official page][R7].
Retrieved 2026-09-14. "Best price and compound concurrency control model",
"Discount compound behavior", and "Keep items on the same sales line for
discount price rounding" show that concurrency and rounding depend on
configuration. Different settings can produce different valid outcomes.
The catalog's precedence, one-time half-up rounding, and tolerance are
explicit sample policies, not a universal Commerce pricing algorithm.

**R8 - Microsoft, Retail price reports.** [Official page][R8].
Retrieved 2026-09-14. The report description and configuration table support
store-scoped, date-scoped review of recent, upcoming, and historical product
prices and an export for further analysis. The page's instruction to enable
the price-report parameter is older than R7's deprecation table, which says
that parameter was removed in October 2023. We rely only on the reporting
concept, not that setup instruction. Its documented seven-day report limit
is a product-feature limit, not a universal limit on a synthetic file audit.

## Shared research decisions

All company names, IDs, quantities, approvals, dates, policies, and money are
invented. IDs will use obvious `SYN-` prefixes and fixture dates in **2099**.
These are not current forecasts or exports of real customers, receipts,
inventory, card data, or store observations.

Each case will remain one parseable JSON object at the shared contract's
`mock-data/<case-id>.json` path. The tables below describe **independent
logical export files** and their draft business schemas. The intended input
bundle contains separately named export tables plus a configurable
role-to-filename map. It must not flatten unrelated sources into a single
prejoined answer. Renaming a logical file and changing its mapping must not
change the result. Physical payload serialization is finalized at the build
gate; this catalog introduces no runner, filesystem resolver, or competing
manifest schema.

Configuration includes the role-to-filename mapping, as-of date, applicable
period, and explicit company policy. All joins use exact keys; no fuzzy
receipt/SKU matching, silent deduplication, inferred dates, or default-zero
missing records. JSON numbers used as quantities are nonnegative integers,
not booleans. Money is integer minor units with an explicit currency. Rates
are integer basis points. Intermediate monetary arithmetic is exact decimal
or rational arithmetic, never binary floating-point comparison.

Structurally malformed records and duplicate primary keys reject the case
before proposals are produced. Contradictory or ambiguous business evidence
has the scenario-specific quarantine behavior below, with a visible reason.
An exception never silently converts missing evidence into a plausible
answer. Output arrays use documented stable ordering and do not depend on
input row order or a fixed number of demo records.

After approval, expected results must be written from these policies and
independent arithmetic **before** the baseline is executed. The seed results
below are research calculations, not existing golden files. Research,
goldens, baseline code/output, holdouts, and negative inputs remain withheld
from native authoring. Only the shared allowlist is staged: `HOW_TO.md`,
`workflow.json`, `connections.json`, demo input, and centrally generated
baseline video.

## retail-01: Store replenishment proposal

### Qualification, actors, and boundary

A replenishment planner receives a daily bundle from an inventory-reporting
analyst and a DC capacity coordinator. The trigger is an explicitly dated
planning run, not an external scheduler. The process starts with unjoined
synthetic store/DC snapshots, outstanding receipts, daily residual demand,
routes, and policy. It ends with a review-ready, whole-case proposal,
projected stock/shortage ledger, and DC capacity reconciliation.

No transfer, purchase order, reservation, shipment, or physical movement is
created. There is one chosen source DC per store/SKU, one dispatch day per
run, integer units, and nonperishable goods. Multi-DC optimization,
substitution, lots, expiry, truck routing, procurement, and forecast/model
training are out of scope. R1-R3 qualify the process; the exact algorithm is
the following mock company policy.

### Multi-file input design

| Logical file role | Draft fields | Keys and meaning |
| --- | --- | --- |
| planning-policy.json | as_of, review_days, policy_id, source_files, partial_cases_allowed | Positive review horizon; partial allocation means whole cases, never broken cases |
| store-stock.json | store_id, sku, snapshot_on, on_hand_units, reserved_units, blocked_units | Unique store/SKU; snapshot is start of as_of; reserved and blocked are disjoint subsets of physical on-hand |
| dc-stock.json | dc_id, sku, snapshot_on, on_hand_units, reserved_units, blocked_units | Unique DC/SKU; available quantity subtracts reserved and blocked exactly once |
| residual-demand.json | store_id, sku, demand_on, units | Unique store/SKU/day; complete daily coverage; demand excludes already reserved commitments |
| inbound.json | receipt_id, store_id, sku, eta, status, remaining_units | Unique receipt ID; in-transit quantities already left their origin; received/cancelled rows have zero remaining units |
| replenishment-routes.json | store_id, sku, dc_id, lead_days, case_pack, safety_units, priority | Unique store/SKU route; nonnegative lead/safety, positive case pack; lower priority number first |
| dc-capacity.json | dc_id, dispatch_on, remaining_case_capacity | Unique DC/day; remaining outbound whole-case capacity already excludes firm work |

### Sample policy and temporal semantics

Arrival is `as_of + lead_days`. Coverage runs from `as_of` through
`arrival + review_days - 1`, inclusive. Receipts arrive before that day's
demand. A snapshot and an inbound receipt cannot both represent the same
received stock: only positive, in-transit remaining quantities on or after
as_of qualify. An overdue in-transit ETA is inconsistent evidence and blocks
that store/SKU; a later-than-horizon ETA is listed but contributes no stock.
Received/cancelled receipts contribute zero. No incoming quantity is also
added to the DC's already measured on-hand.

Available store/DC stock is physical on-hand minus its disjoint reserved and
blocked quantities. Subsets larger than physical stock reject the case.
Forecast rows are **residual unreserved demand**, so reservations and their
underlying orders are not subtracted again as demand.

Before proposed arrival, simulate each day using nonnegative physical stock;
unfilled forecast is recorded as lost demand, not carried as a backorder.
At arrival, start with the surviving stock. For the remaining days, form a
cumulative, *unconstrained planning balance* without the proposed receipt:
opening stock plus due inbound minus cumulative demand. Required units are
the maximum of zero, the largest negative cumulative balance, and safety
units minus the closing cumulative balance. This covers both an early
shortage before a later receipt and end-of-horizon safety. Negative planning
balances are never reported as physical stock.

Round required units **up** to the next whole case. Sort candidates by
priority, store ID, and SKU. For each candidate, propose the minimum of
requested cases, remaining DC SKU stock expressed as whole cases, and
remaining DC/day case capacity. Debit only the hypothetical proposal
ledgers. A partial proposal contains whole cases; the unproposed remainder
and every binding limit are visible. Do not silently borrow another DC's
stock or tomorrow's capacity. If `partial_cases_allowed` is false and the
whole request cannot fit, propose zero for that candidate and consume no
stock/capacity. The three seed cases below enable partial whole-case proposals.

Re-simulate daily physical stock with the actual proposed receipt, record
pre/post-arrival lost demand and final safety shortfall, and preserve a
zero-proposal row when no need exists. Late delivery cannot repair an earlier
shortage. Case rounding may create excess closing stock; it is visible.

### Semantic steps and trace content

| Step | Kind | Actual work and useful trace table |
| --- | --- | --- |
| load-exports | input | Read configured export roles; show snapshot dates, row counts, DC case budgets |
| validate-stock-and-keys | validation | Validate types, unique keys, disjoint stock quantities, date coverage, and positive case packs |
| join-store-supply | join | Join store/SKU to route, DC stock, daily demand, and receipt IDs; show joined stock components |
| project-before-arrival | decision | Walk the actual pre-arrival days; show receipts, demand, available stock, and lost demand |
| calculate-case-requests | decision | Compute cumulative balances, safety need, raw units, case ceiling, and requested cases |
| allocate-dc-capacity | decision | Walk all prioritized candidates and debit shared SKU/case balances after each proposal |
| surface-shortfalls | exception | Re-simulate proposed receipts; list unproposed units, late/inconsistent evidence, and dated shortages |
| publish-review-packet | output | Produce proposal rows, daily projections, DC balance ledger, exceptions, and planner summary |

Loops range over all configured store/SKUs, coverage dates, and candidates.
Branches include no need, late receipt, invalid evidence, full allocation,
DC-stock-limited partial allocation, capacity-limited partial allocation,
and pre-arrival loss that cannot be fixed by this dispatch.

### Complete final artifacts

The result's `outputs` will contain a proposal table (store/SKU/DC, dispatch
and arrival, raw/requested/proposed units and cases, limits, deferred units);
a daily projection table (receipts, demand, fulfilled/lost units, closing
stock); a DC ledger (opening available stock/case budget, proposed usage,
remaining balances); and a review packet with totals, dated risks, owner,
required review actions, and `action_authorized: false`. Exceptions preserve
source keys and affected dates. Stable order is store/SKU for proposal rows,
store/SKU/day for projections, and DC/SKU for stock controls.

### Demo, two holdouts, and independent answers

These are evaluator-only seed designs, to be expanded into complete fixtures
and manually authored expected files after approval.

| Case | Changed inputs and independent derivation | Expected review result |
| --- | --- | --- |
| demo | As-of 2099-04-10; lead 2, review 3. A/BLUE: available 8 (11-2-1), demand 2/day, inbound 2 on arrival, safety 4, pack 3. Arrival stock 4; raw need 4; request 6. B/BLUE: available 3, demand 2/day, inbound 3 on final day, safety 3, pack 3. Pre-arrival loss 1; post-arrival planning balances -2,-4,-3; raw need 6; request 6. C/GOLD: available 4, demand 2/day, no inbound, safety 2, pack 4; raw/request 8. Priority A,B,C; DC available BLUE 9 and GOLD 40; case capacity 4. | Propose A=6, B=3 (stock limit), C=4 (case-capacity limit): 13 units/4 cases against 20 requested units/6 cases. Deferred 7 units. Closing A/B/C=6/1/0; pre-arrival lost units=1; post-arrival lost units=3; final safety shortfalls=0/2/2. |
| holdout-a | As-of 2099-05-01; lead 1, review 2; pack 5; DC available 22; capacity 3. A available 0, demand 1 before arrival then 2,3, safety 1: raw 6 -> request 10. B available 5, demand 1 then 2,2, safety 3: raw 3 -> request 5. | Propose 10 and 5; 15 units/3 cases; DC remainder 7. Both closing stocks 5. Pre-arrival loss 1 remains an exception despite full case requests. Different dates, horizon, pack, demands, stock and limit values, not renamed demo rows. |
| holdout-b | As-of 2099-06-15; lead 0, review 2; pack 4; capacity 1. A available 6, demand 1,1, safety 2: need 0; 11-unit inbound on June 17 is outside coverage. B available 1, demand 3,2, safety 2: raw 6 -> request 8; DC available 20. | A proposes 0, closes 4; late inbound not counted. B proposes 4, closes 0, has safety shortfall 2 but no lost demand. Total 4 units/1 case; unmet case request 4 units. |

Additional negative designs: `negative-malformed` (zero case pack or boolean
units, reject); `negative-contradictory` (reserved plus blocked exceeds
physical stock, reject); `negative-duplicate` (repeated receipt or snapshot
key, reject rather than double count); `negative-ambiguous-route` (two DC
routes for one store/SKU, reject); `negative-out-of-window` (snapshot not
as-of, reject); and an overdue-in-transit receipt (quarantine the pair, do not
invent its arrival). Incomplete daily demand is an explicit validation
failure, not zero demand.

Independent assertions include: requested/proposed quantities are exact
case multiples; proposed quantities never exceed requests, DC stock, or
case capacity; every hypothetical debit occurs once; missing/duplicate
stock cannot increase supply; the day-level conservation identity holds
(opening + receipts - fulfilled demand = closing, demand = fulfilled +
lost); late inbound cannot cure earlier loss; zero-need rows consume no
capacity; source-row permutations and filename remapping preserve results.

## retail-02: Returns/refund reconciliation

### Qualification, actors, and boundary

A returns reconciliation analyst receives an intake batch from a synthetic
store-service role and original-order/payment-history exports from a
finance-reporting role. The trigger is review of a closed reporting period.
The process starts with unjoined requests, original receipts/invoices/lines,
posted return history, and explicit sample policy. It ends with proposed
return quantities, original-price refund amounts, order-level controls, and
a human-review packet. R4-R5 qualify the process.

No refund, card operation, order amendment, customer contact, stock return,
disposition, fraud allegation, or legal/policy entitlement determination is
performed. Scope is whole-unit returns, one receipt/invoice and one confirmed
synthetic card-payment reference per original order, two-decimal currency,
and no shipping charges. Exchanges, serialized goods, receiptless
authorization, multiple captures, mixed tenders, tax recomputation, and
restocking fees are out of scope.

### Multi-file input design

| Logical file role | Draft fields | Keys and meaning |
| --- | --- | --- |
| return-policy.json | as_of, period_start, period_end, window_days, allow_partial_requests, allowed_reasons, allowed_conditions, source_files | Inclusive request period; period_end <= as_of; window is an invented calendar-day rule |
| original-orders.json | order_id, store_id, receipt_id, invoice_id, purchased_on, currency, payment_reference, confirmed, authorized_minor, captured_minor | Unique order and store/receipt; single invoice/payment reference; no actual token or account |
| original-lines.json | order_id, line_id, sku, fulfilled_qty, merchandise_paid_minor, tax_paid_minor, returnable | Unique order/line; original paid merchandise and allocated original tax |
| prior-returns.json | return_event_id, order_id, line_id, posted_on, state, qty, merchandise_minor, tax_minor | Unique event ID; posted rows consume eligibility; voided rows do not; all history predates period_start |
| return-requests.json | request_id, store_id, receipt_id, order_id, invoice_id, line_id, sku, requested_on, requested_qty, reason, condition | Unique request; supplied original identifiers must agree after exact joins |

### Sample policy and temporal semantics

The demo company window is 30 calendar days inclusive: age zero through
`window_days` can qualify. This is invented, configurable policy, not law or
a universal retailer rule. Requests must fall within the configured
inclusive period and on/before as-of; purchase date cannot be after request.
Condition, reason and original line eligibility must pass the sample policy.
Out-of-window or nonreturnable lines are review-only with zero proposal.

The history export is a closed opening ledger, complete strictly before
period_start. Posted history inside the current intake period, pending
events, contradictory order references, or impossible prior totals require
order-level quarantine; the program must not guess what already happened.
This deliberately avoids claiming that an offline export is live available
return quantity. Unknown receipts produce unresolved-request exceptions,
not an accusation.

For an original line with quantity Q, paid merchandise M and tax T, define
cumulative entitlements at returned quantity q as half-up-rounded integer
minor units `M*q/Q` and `T*q/Q`. A new proposal for a units after r already
returned/proposed units receives the **difference between cumulative
entitlements at r+a and r**. Original tax is allocated, not recalculated
using a tax rate or current price. This cumulative policy is our sample
choice, not a claim about Commerce's internal rounding.

Posted prior quantity must not exceed Q; prior merchandise and tax must
equal this policy's cumulative entitlements. Otherwise quarantine the
entire order. Original line totals must reconcile to captured amount; the
single captured amount cannot exceed original authorization. No hidden
shipping, pending capture, fee, or other refund is assumed absent from a
contradictory export.

Process requests by requested date then request ID. Remaining quantity is
fulfilled minus posted prior returns minus quantities reserved by earlier
proposals in this batch. If partial requests are allowed, propose the
minimum of requested and remaining units and explicitly defer the rest.
If not, an oversized request proposes zero and consumes no remaining
quantity. Check the order-level proposed-plus-prior amount against captured
and authorized amounts before making the proposal available for review.
Only a hypothetical ledger changes.

### Semantic steps and trace content

| Step | Kind | Actual work and useful trace table |
| --- | --- | --- |
| load-return-exports | input | Show intake, original-order/line, prior-event counts and policy dates |
| validate-return-records | validation | Validate keys, integer money/quantity, status vocabulary, policy, and dates |
| link-original-evidence | join | Join receipt/store and original order/invoice/line/SKU; expose unmatched or disagreeing keys |
| reconcile-opening-ledger | decision | Sum posted prior quantities/amounts, exclude voided events, reconcile original capture and prior entitlement |
| apply-return-policy | decision | Calculate age, reason, condition and returnability; show each policy outcome |
| reserve-proposed-quantities | decision | Walk requests in stable order; show prior quantity, earlier proposals, remaining and proposed quantities |
| calculate-original-refund | decision | Show cumulative merchandise/tax before and after, penny differences, and payment caps |
| quarantine-return-exceptions | exception | List unresolved, expired, oversized, unsupported or contradictory evidence and affected orders |
| publish-return-review | output | Emit request proposals, opening/projected ledgers, money controls, and review summary |

Loops range over all history events and all ordered requests, not a fixed
number of receipts. Branches cover exact/full proposal, partial proposal,
exhausted line, partial-disabled request, age/condition/reason exclusion,
unconfirmed payment, unmatched receipt, and quarantined history.

### Complete final artifacts

The `outputs` object will contain every request's disposition, joined
original keys, requested/available/proposed/deferred quantities, proposed
merchandise/tax/total in minor units, currency, reason, and original payment
reference; opening and projected order-line eligibility; original/prior/new/
remaining order money controls; and a review packet with totals and human
actions. Zero-proposal and unresolved requests remain visible. No field
asserts that a financial action occurred. Request rows sort by date/ID;
control rows sort by order/line. Totals are separated by currency.

### Demo, two holdouts, and independent answers

| Case | Changed inputs and independent derivation | Expected review result |
| --- | --- | --- |
| demo | Review date/period 2099-07-02, window 30, partial enabled. Order 1 purchased June 12: Q=3, M=1000, T=100, captured/authorized=1100. Prior posted quantity 1, merchandise 333 and tax 33. Request 1 asks 1: cumulative merchandise 667-333=334; tax 67-33=34. Request 2 asks 2 but only 1 remains: merchandise 1000-667=333; tax 100-67=33. Order 2 purchased June 1 (age 31), Q=1, M=2000, T=200, payment 2200; request 3 asks 1. Request 4 cites an unknown synthetic receipt. | Request 1 proposes 1 unit/368 minor units; request 2 proposes 1 unit/366 and defers 1; requests 3 and 4 propose zero with distinct age and join exceptions. New total 734 = merchandise 667 + tax 67. Prior 366 + new 734 = 1100; no quantity remains on order 1. |
| holdout-a | Review 2099-08-15; window changes to 14; purchase August 1 exactly on boundary. Q=4, M=1999, T=161, capture 2160. Prior 1 unit: round(1999/4)=500, round(161/4)=40. One new request asks 2. | New merchandise round(1999*3/4)-500 = 1499-500 = 999; tax 121-40 = 81; propose 2 units/1080. Remaining 1 unit/540; prior+new=1620. Tests changed quantity, amounts, window, date and penny distribution. |
| holdout-b | Review 2099-09-11; purchase September 4; window 7; partial disabled. Q=2, M=999, T=0, capture 999, no prior returns. Earlier request asks 3; later request asks 1. | Oversized first request proposes 0, leaving eligibility intact. Second proposes 1 unit/500 minor units by half-up rounding; remaining 1 unit/499. |

Negative designs: `negative-malformed` (fractional/boolean return quantity or
invalid money type, reject); `negative-contradictory` (prior quantity exceeds
fulfilled quantity, or prior amounts disagree with cumulative entitlements,
quarantine the order); `negative-duplicate` (duplicate request/event key,
reject); `negative-ambiguous-receipt` (multiple originals for store/receipt,
reject, never first-match); `negative-out-of-window` (age window+1, zero
proposal with review exception); and unconfirmed capture or a posted event
inside the intake period (quarantine order, not zero-history fallback).

Independent assertions include: every proposed unit links to exactly one
original line; prior plus current proposed quantity never exceeds fulfilled;
prior plus proposed money never exceeds capture/authorization; merchandise
and tax conserve their original totals when all units are returned; no
current catalog price or recomputed tax is used; rejected/expired requests
consume neither quantity nor money; two requests cannot independently
reuse the same availability; permutation and filename-remapping invariance;
and demo's exact 368/366 penny allocation versus naive equal-unit rounding.

## retail-03: Promotion price audit

### Qualification, actors, and boundary

A pricing operations analyst receives a bounded set of synthetic observed
unit-price rows from store-reporting staff, reference prices and promotion
exports from merchandising, and approved-exception fixtures from a pricing
reviewer. The trigger is a configured audit period, not publication of a
promotion. The process starts with unjoined observations, base-price
versions, promotion definitions/scopes, and exception windows. It ends with
expected-versus-observed comparisons, full rule-selection explanations, and
a review-ready exception packet. R6-R8 qualify the process.

No POS/ERP interaction, price publication, label change, transaction,
customer reimbursement, or compliance/legal judgment is performed. Scope
is one-unit, tax-exclusive, two-decimal-currency prices with exact store/SKU
scope. Basket/quantity/threshold offers, loyalty, coupons, affiliations,
personalized prices, shipping, currency conversion, and legal price-display
rules are excluded.

### Multi-file input design

| Logical file role | Draft fields | Keys and meaning |
| --- | --- | --- |
| audit-policy.json | as_of, audit_start, audit_end, tolerance_minor, rounding, source_files | Half-open audit window; half-up final rounding; sample integer tolerance |
| stores.json | store_id, currency, date_basis | Unique store; supplied dates already use the store's local calendar |
| products.json | sku, unit | Unique SKU; no unit conversion or variant inference |
| base-prices.json | price_id, store_id, sku, valid_from, valid_to, currency, unit, price_minor | Unique price ID; exactly one applicable base per observed store/SKU/date |
| promotions.json | promotion_id, enabled, valid_from, valid_to, currency, unit, priority, mode, type, value | Unique promotion; modes exclusive/best-price/compound; types amount-off minor units or percent-off basis points |
| promotion-scope.json | promotion_id, store_id, sku, line_type | Unique promotion/store/SKU/include-or-exclude; explicit exclusion overrides inclusion |
| price-exceptions.json | exception_id, store_id, sku, valid_from, valid_to, approved, approval_reference, price_minor | Unique exception; synthetic approval reference, not actual authority; at most one active approved exception |
| observed-prices.json | observation_id, store_id, sku, observed_on, currency, unit, observed_minor | Unique observation; observed unit price, not a customer order or sales amount |

### Sample policy and temporal semantics

Every price, promotion, exception, and audit window is half-open:
`start <= observed_on < end`. All inputs are already local calendar dates;
there is no timezone/DST inference. The audit's last included day must not
be after as-of. Observations outside its period are separately listed,
never evaluated as current observations. Invalid/reversed windows reject the
case. Missing or overlapping applicable base prices make the affected
observation not evaluable, not zero-priced.

The sample precedence is: one active approved explicit price exception;
otherwise the highest numeric priority among eligible promotions; within
that priority, exclusive discounts if present; otherwise competing
best-price singles and the combined compound set. Lower-priority discounts
never stack. At equal priority, exclusive candidates compete for the lowest
unrounded resulting price and prevent all other discounts on that row.
With no eligible promotion, use the unique base price.

An amount-off candidate floors at zero. A percent-off candidate uses
integer basis points from 1 through 10000. A compound set subtracts the sum
of amount-off values from base (floor zero), then multiplies all percentage
factors without intermediate rounding. Compare the unrounded candidate
values; an exact tie uses the lexicographically sorted promotion-ID tuple,
recording the tied candidates. This is deterministic sample policy, not
an ambiguity hidden by input order. Ambiguous base or approved exception
evidence is instead quarantined.

Round the chosen final unit price once to integer minor units using
`ROUND_HALF_UP`. Compute signed delta as observed minus expected. It is a
mismatch only when its absolute value exceeds configured tolerance. Demo
tolerance is zero; another mock company setting can allow one minor unit.
No accumulated "financial loss" is inferred from unit-price observations.

### Semantic steps and trace content

| Step | Kind | Actual work and useful trace table |
| --- | --- | --- |
| load-price-exports | input | Show observations, reference versions, promotion/scoping counts and audit period |
| validate-pricing-records | validation | Validate keys, rate/money types, supported modes, dates, units, and foreign keys |
| join-store-sku-prices | join | Join observations to store/product and date-valid base-price versions |
| select-active-promotions | decision | Show enabled/date/store/SKU/currency/unit filters and include/exclude outcomes |
| resolve-price-policy | decision | Resolve approved exception or priority/exclusive/best/compound candidates with reasons |
| round-and-compare | decision | Show exact candidate amount, half-up expected minor units, observed, delta and tolerance |
| register-audit-exceptions | exception | Surface mismatches, out-of-period observations, ambiguous references and non-evaluable rows |
| publish-price-review | output | Emit complete row audit, rule-selection ledger, issue queue and reviewer summary |

Loops range over every observation and its actual candidate rules/windows.
Branches cover excluded/disabled/expired rules, no promotion, competing
exclusive candidates, compound versus best price, exact ties, approved
exceptions, ambiguous references, and tolerance boundaries.

### Complete final artifacts

`outputs` will contain the included-observation audit (reference IDs,
eligible/excluded rules and reasons, chosen rules/exception, expected and
observed minor units, delta and result); a separate out-of-scope register;
an issue queue with owner and next human review action; and totals by store
and currency for matched, mismatched, non-evaluable and excluded records.
The review packet records the policy and period with
`action_authorized: false`. Non-evaluable prices are explicitly null, never
zero. Sort rows by observation date/store/SKU/observation ID, and rule IDs
lexicographically. Every input observation has exactly one disposition.

### Demo, two holdouts, and independent answers

| Case | Changed inputs and independent derivation | Expected review result |
| --- | --- | --- |
| demo | Audit [2099-10-10,2099-10-12), as-of October 11, tolerance 0. TEA base 1999: priority-20 exclusive amount-off 300 defeats same-priority best-price 50% and lower-priority 40%; observed 1699. SOAP base 999: priority-10 compound 10% and 20% gives 719.28; best-price 25% gives 749.25; observed 720. MUG base 1999: 50% gives 999.5; observed 999. TEA on October 11 has an approved exception of 1550; observed 1550. | Expected 1699,719,1000,1550; signed deltas 0,+1,-1,0; two matched and two mismatched rows. Half-up rounds 999.5 to 1000. The exception replaces promotion calculation only within its window. |
| holdout-a | Audit [2099-11-01,2099-11-03), as-of November 2; tolerance changes to 1. New base 1005: 10% gives 904.5 -> 905, observed 906. Another row has equal-priority exclusive `SYN-PROMO-A` at 20% (804) and `SYN-PROMO-B` at amount-off 201 (804), plus best-price 50% that is suppressed; observed 805. Third observation is on November 3, the exclusive audit end. | Two evaluated rows expected 905 and 804, both within tolerance at delta +1. Exact tie selects `SYN-PROMO-A` and records both candidates. Third row is explicitly out of period and has no expected price. |
| holdout-b | Audit [2099-12-05,2099-12-07), as-of December 6, tolerance 0. Base 1099; compound amount-off 99 then 12.5% gives (1099-99)*0.875=875; best-price 20% gives 879.2. All those promotions expire at December 6. Observed 875 on both December 5 and 6. | December 5 expects 875, matched; December 6 expects base 1099, delta -224 and mismatch. Tests amount/percentage compounding and the exact expiry boundary with changed dates/rules/values. |

Negative designs: `negative-malformed` (percent over 10000 basis points or
boolean price, reject); `negative-contradictory` (overlapping base windows
with different values, affected observation not evaluable);
`negative-duplicate` (duplicate observation or promotion key, reject);
`negative-ambiguous-exception` (two matching approved exceptions, not
evaluable); `negative-out-of-window` (observation at audit end, explicit
exclusion); and reversed/future audit configuration (reject). Unsupported
basket discount types must not be silently treated as simple discounts.

Independent assertions include: every chosen rule matches store, SKU,
currency, unit and date; excluded/disabled/expired rules cannot win;
exclusive discounts never stack; priority is resolved before price
competition; one approved exception suppresses promotions; ambiguity cannot
produce an expected price; the exact compound and half-up calculations above
hold; no observed value influences expected price; all observations appear
once in the disposition totals; input permutations, logical filename changes,
and changed row counts preserve documented behavior.

## Build handoff and evidence gates

After explicit approval, each owner-built scenario will follow the shared
layout and have one complete `HOW_TO.md`, `scenario.json`, `sources.json`,
`workflow.json`, `connections.json`, mock cases, prewritten independent
goldens, and a standard-library `baseline.py`. The baseline's
`solve(payload) -> (result, events)` performs the whole procedure and uses
only the approved shared CLI helper. It imports neither Creator code nor
generated-plugin logic, and never reads expected files.

Each demo will emit actual intermediate rows for all six shared step kinds,
including a meaningful exception stage and final review packet. The
foundation, not the sector baseline, renders the roughly 30-90 second video
from that trace. Required labeling is:
**Synthetic baseline execution visualization - not Cowork or a live system**.
There is no fake POS/ERP/native screen and no claim that video proves native
execution.

Input connection metadata is exported synthetic files plus existing native
file-output facilities: `mode: mock-exports-only`, `availability:
not-required`, no connections, endpoint, authentication, or invented service.
Any real commerce backend requirement remains **unverified**, not deployed.
No backend/API/custom MCP server, Azure resource, external model/media API,
DB, queue, workflow engine, gateway, device agent, custom UI runner,
scheduler, or runtime installer is part of these designs.

As of 2026-09-14, native creation, installation, and independent invocation
are **blocked and unrun**. Approved Computer Use tools were removed, and an
unlocked accessible native session is also required. There is no alternate
browser/Playwright/private API/cookie/token/shell route. Historical output
publication remains **unknown**, not Installed. Creator runtime 0.2.1,
release/proof/native-download files, and the main checkout remain untouched.
Suspected core defects must be reported to the parent before changes.

Actual native-generated standalone plugins may eventually be stored under
root `output` by the parent-authorized native process. This sector will not
produce placeholder/local native ZIPs or promote local comparisons into
native success. Native authors see only the allowed procedure/demo/video
inputs; holdouts and all evaluation answers remain withheld until
independent invocation. There is no real business data, credential, EULA
acceptance, or publication step in this research.

[R1]: https://docs.oracle.com/en/industries/retail/retail-merchandising-foundation-cloud/latest/rmpug/replenishment.htm
[R2]: https://learn.microsoft.com/dynamics365/supply-chain/master-planning/planning-optimization/replenishment-methods-quantity-modification
[R3]: https://learn.microsoft.com/dynamics365/guidance/business-processes/forecast-to-plan-areas
[R4]: https://learn.microsoft.com/dynamics365/commerce/pos-returns
[R5]: https://learn.microsoft.com/dynamics365/commerce/dev-itpro/linked-refunds
[R6]: https://learn.microsoft.com/dynamics365/commerce/retail-discounts-overview
[R7]: https://learn.microsoft.com/dynamics365/commerce/price-settings
[R8]: https://learn.microsoft.com/dynamics365/commerce/price-report
