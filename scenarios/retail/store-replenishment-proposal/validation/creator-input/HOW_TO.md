# Store replenishment proposal

## Purpose and boundary

Prepare a **review-only** replenishment proposal from independent synthetic
store-stock, distribution-center (DC) stock, residual demand, in-transit
receipts, routes and dispatch-capacity exports. The replenishment planner
owns the final review; inventory-reporting and DC-capacity roles supply the
dated evidence. A human starts one dated run. Finish with complete proposal,
daily projection, receipt-disposition and DC-control tables, not just a
recommended quantity.

All supplied identities are visibly `SYN-` prefixed and demonstration dates
are invented. Never use real customers, store inventories, accounts or
transactions. No transfer, purchase order, reservation, shipment or physical
stock movement is created. There is one source DC per store/SKU and one
dispatch day. This is nonperishable whole-unit planning, not multi-DC
optimization, substitution, lot/expiry management, routing or forecasting
model training.

## Research and explicit sample policy

The following primary pages were fetched and reviewed on **2026-09-14**:

| Source | Supported concept | Limit |
| --- | --- | --- |
| [Oracle: Replenishment](https://docs.oracle.com/en/industries/retail/retail-merchandising-foundation-cloud/latest/rmpug/replenishment.htm) | Refill store/warehouse inventory; recommendation-only versus automatic order creation; item/location inventory, forecast integration, rounding and constraints | `latest` is unversioned; does not specify this DC case allocation or lost-demand algorithm |
| [Microsoft: Replenishment methods and quantity modification](https://learn.microsoft.com/dynamics365/supply-chain/master-planning/planning-optimization/replenishment-methods-quantity-modification) | Replenishment coverage methods and configured order-quantity multiples | Its minimum-maximum multiple selection is **not** our unconditional ceiling rule |
| [Microsoft: Forecast to plan business process areas](https://learn.microsoft.com/dynamics365/guidance/business-processes/forecast-to-plan-areas) | Inventory, expected demand, safety, lead times, horizons and capacity considerations | Process concepts, not an exact store/DC formula or live inventory guarantee |

Every threshold, horizon, priority, stock-export convention, lost-demand
choice, case ceiling and exception behavior below is an **invented company
policy**. It is not an Oracle/Dynamics implementation, a universal retailer
rule or a production recommendation.

## Input contract

Input is a single UTF-8 JSON object with exactly `schema_version` (integer
`1`), `synthetic` (boolean `true`), `policy` (object) and `files` (object).
Reject duplicate JSON member names, nonfinite numbers and non-object input.
No input source is overwritten.

`files` preserves six independent logical export tables as filename-to-array
entries. These are not prejoined data and are not actual filesystem paths.
`policy.source_files` maps roles to those entries. A consistent rename of a
logical file and its mapping leaves business results unchanged. Never open
a URL, endpoint or arbitrary path from a logical filename. Physical bundle
input/output filenames are caller supplied separately.

`policy` has exactly these fields:

| Field | Type and rule |
| --- | --- |
| policy_id | Synthetic identifier |
| as_of | Valid `YYYY-MM-DD` calendar date; snapshots are start of this day |
| review_days | Integer 1 through 366 |
| partial_cases_allowed | Boolean; whether a request may receive fewer whole cases |
| source_files | Object with exactly `store_stock`, `dc_stock`, `demand`, `inbound`, `routes`, `capacity` |

Each mapping value is distinct and matches
`[A-Za-z0-9][A-Za-z0-9_-]{0,63}\.json`. `files` has exactly the six mapped
keys, no unreferenced extra source. Filenames are identifiers only. There
are no required magic filenames.

All record objects have exactly the fields in the following table.
Unspecified extra or missing fields are rejected. Each table is a nonempty
array except `inbound`, which may be empty. All quantities are **JSON
integers**, never booleans, decimal fractions, negative values or numeric
strings. Identifiers are case-sensitive, at most 80 characters and match
`SYN-[A-Z0-9]+(?:-[A-Z0-9]+)*`. Dates are valid, zero-padded `YYYY-MM-DD`.

| Role | Fields | Unique key |
| --- | --- | --- |
| store_stock | store_id, sku, snapshot_on, on_hand_units, reserved_units, blocked_units | store_id + sku |
| dc_stock | dc_id, sku, snapshot_on, on_hand_units, reserved_units, blocked_units | dc_id + sku |
| demand | store_id, sku, demand_on, units | store_id + sku + demand_on |
| inbound | receipt_id, store_id, sku, eta, status, remaining_units | receipt_id |
| routes | store_id, sku, dc_id, lead_days, case_pack, safety_units, priority | store_id + sku |
| capacity | dc_id, dispatch_on, remaining_case_capacity | dc_id + dispatch_on |

All `_id` and `sku` fields are synthetic identifiers. `snapshot_on`,
`demand_on`, `eta`, `dispatch_on` are dates. `status` is exactly
`in-transit`, `received` or `cancelled`. All other table fields are
nonnegative integers, except `case_pack` must be positive.

`reserved_units` and `blocked_units` are **disjoint subsets** of physical
`on_hand_units`; their sum cannot exceed on-hand. Available stock is on-hand
minus both, once. Demand is explicitly **residual unreserved forecast**:
already reserved commitments are not also included as daily demand.

Stock snapshots and capacity dispatch dates must equal as-of. A route's
`lead_days + review_days` must not exceed 366 and its full horizon must fit
within supported calendar dates. Lower numeric priority is processed first.
All store-stock pairs must have exactly one route, and vice versa. Each
route requires matching DC/SKU stock and DC/as-of capacity. Extra unused DC
stock/capacity rows are permitted and remain visible in final controls.
There must be one demand row for every routed pair/day in its entire
coverage horizon: neither missing days nor out-of-horizon/unknown-pair
demand is allowed. Inbound must reference a routed store/SKU.

In-transit receipts have strictly positive `remaining_units` and have
already left their original location. `received`/`cancelled` receipts have
zero remaining units. Received stock is already in the physical snapshot;
do not add it again. Remaining DC capacity is already net of firm work.
This run consumes only hypothetical capacity for new proposals.

## Ordered procedure

1. **Load and validate.** Read the six mapped exports and policy. Validate
   fields/types, unique keys, stock accounting, same-day snapshots and full
   demand coverage. Stop with an explicit rejection on invalid evidence;
   do not deduplicate, fuzzy-match, infer missing days, or default stock to
   zero. Validation order is envelope/policy/mapping, then the role order
   above (source row order, field order shown), then sorted join/coverage
   checks. Report the first validation failure.
2. **Join and classify receipts.** Arrival is as-of plus lead days; coverage
   is as-of through arrival plus review days minus one, inclusive. Closed
   receipts are `ignored-closed`. In-transit ETA before as-of is `overdue`
   and blocks that store/SKU. ETA after coverage is `after-coverage` and
   contributes no stock. Otherwise it is `counted`, added once on its ETA.
   All receipts remain in the register. `counted` describes temporal
   eligibility; if another receipt blocks the same pair, no projection for
   that pair is made. Do not add inbound to DC on-hand.
3. **Project before arrival.** Starting from available store stock, walk
   every day before proposed arrival. Receive counted inbound first,
   fulfill the smaller of demand and available stock, and record the
   remainder as lost forecast. Closing physical stock is nonnegative.
   Lost forecast is not a backorder and cannot be repaired retroactively.
4. **Calculate the request.** Start with surviving physical stock at
   arrival, before that day's receipts/demand. For each coverage day from
   arrival, calculate the unconstrained cumulative planning balance:
   opening plus cumulative counted inbound minus cumulative demand, without
   a new proposal. Raw required units are the maximum of zero, the largest
   negative cumulative balance, and safety units minus the final balance.
   This covers an early shortfall even if a large receipt arrives later.
   Negative planning balance is **not** negative physical inventory.
   Round raw units up to whole cases using integer ceiling division.
5. **Allocate shared supply.** Sort candidates by priority, store ID, SKU.
   Proposed cases are the minimum of requested cases, remaining DC SKU
   stock divided by case pack (floor), and remaining DC dispatch-day case
   capacity. Debit the hypothetical stock and capacity once. `dc-stock`
   and/or `dc-capacity` are limits whenever their pre-allocation case count
   is below the request. If partial cases are disabled and the full
   request does not fit, propose zero, add `partial-disabled` and debit
   nothing. Never break a case, pool another DC or borrow future capacity.
   Zero-need rows remain in the allocation ledger and consume nothing;
   blocked rows do not enter it.
6. **Re-project actual proposed supply.** Re-run each unblocked pair's
   complete daily physical ledger, adding proposed units once on arrival
   before demand. Record day-specific lost units, pre/post-arrival totals,
   closing stock and final safety shortfall. Excess from case rounding is
   visible. Each limited request, each lost-demand day and each final
   safety shortfall generates its own review exception.
7. **Close the review packet.** Reconcile requested/proposed/deferred units,
   case counts and remaining DC controls. Preserve all receipt and proposal
   dispositions. Publish the result below, including next human action.
   Stop before any real inventory/order/reservation action.

Loops follow the supplied pairs, dates and candidates, never a hard-coded
number of demo rows. All quantities and ceiling/floor operations use exact
integer arithmetic. This scenario has no money or currency conversion.

## Complete output contract

The output file is a JSON review packet with exactly:

```json
{
  "schema_version": 1,
  "status": "completed",
  "outputs": {},
  "exceptions": []
}
```

The example illustrates the **envelope only**, not a completed empty
business result. `status` is `completed` only when no exceptions exist,
`completed_with_exceptions` for a validated calculation with review
exceptions (including quarantined pairs), or `rejected` after the first
validation failure. A rejected result has `outputs: {}` and exactly one
validation exception. Valid calculations always contain all seven business
keys below, even if some tables are empty.

### proposals

An array sorted by `store_id`, then `sku`. Exactly one row per routed pair:

| Keys | Type and meaning |
| --- | --- |
| store_id, sku, dc_id | Synthetic identifiers |
| dispatch_on, arrival_on, coverage_end | Dates; end is inclusive |
| priority, case_pack | Input integers |
| opening_available_units | Nonnegative net opening stock |
| arrival_opening_units | Stock after pre-arrival simulation, before arrival-day receipts |
| raw_required_units | Maximum prefix-deficit/final-safety need before case rounding |
| requested_units, requested_cases | Rounded whole-case request |
| proposed_units, proposed_cases | Allocated hypothetical supply, nonnegative; zero if blocked |
| deferred_units | requested_units minus proposed_units |
| rounding_excess_units | requested_units minus raw_required_units |
| closing_units | Final physical projected stock |
| pre_arrival_lost_units, post_arrival_lost_units | Lost forecast on either side of arrival |
| safety_shortfall_units | max(0, safety_units minus closing_units) |
| status | `no-need`, `full`, `partial`, `unallocated`, or `blocked` |
| limits | Ordered string array: `dc-stock`, then `dc-capacity`, then `partial-disabled`, only if applicable; blocked rows contain only `overdue-inbound` |

All quantity fields are nonnegative integers for unblocked pairs. For
blocked pairs, `arrival_opening_units`, `raw_required_units`,
`requested_units`, `requested_cases`, `deferred_units`,
`rounding_excess_units`, `closing_units`, both lost-unit fields and
`safety_shortfall_units` are **null**, not guessed zero. Only actual
hypothetical proposal units/cases are zero.

`no-need` means request zero; `full` means positive request fully allocated;
`partial` means some but not all requested cases allocated; `unallocated`
means a positive request gets zero; `blocked` means unresolved receipt
timing prevented calculation.

### daily_projection

Array sorted by store ID, SKU, day; no rows for blocked pairs. Each row has
exactly `store_id`, `sku`, `day` (date), `phase` (`before-arrival` or
`coverage`) and integer `opening_units`, `inbound_units`, `proposed_units`,
`demand_units`, `fulfilled_units`, `lost_units`, `closing_units`.
`proposed_units` is nonzero only on arrival day. The conservation identities
are opening + inbound + proposed - fulfilled = closing, and
demand = fulfilled + lost.

### inbound_register

Array sorted by receipt ID. Every input receipt has exactly `receipt_id`,
`store_id`, `sku`, `eta` (date), `remaining_units` (integer) and `disposition`
(`counted`, `ignored-closed`, `after-coverage`, `overdue`). No implicit
deduplication or disappearing late receipts.

### dc_stock_controls and dc_capacity_controls

`dc_stock_controls` is sorted by DC ID/SKU. Each row has `dc_id`, `sku`,
`opening_available_units`, `proposed_units`, `remaining_units`, with integer
balances and opening minus proposed = remaining. All supplied DC stock
rows appear, including unused ones.

`dc_capacity_controls` is sorted by DC ID. Each row has `dc_id`,
`dispatch_on` (date), `opening_case_capacity`, `proposed_cases`,
`remaining_case_capacity`. These are integer **cases**, not units or truck
space. Opening minus proposed = remaining. Include unused DC capacity.

### allocation_ledger

Array in priority/store/SKU execution order; includes unblocked zero-need
rows. Every row has `store_id`, `sku`, `dc_id`, `requested_cases`,
`stock_cases_before`, `capacity_cases_before`, `proposed_cases`,
`stock_units_after`, `capacity_cases_after`. All numeric fields are
nonnegative integers. `stock_cases_before` floors available DC units by
that row's case pack; after-stock remains in **units**. Ledger debits must
reconcile to the final DC controls.

### review_packet

Object with exactly `policy_id`, `as_of`, `review_days`, `owner_role`
(literal `Replenishment planner`), `action_authorized` (always false),
`review_required` (whether any exceptions exist), `totals` and `next_action`.
Even a result without exceptions still requires a human to authorize any
separate real action; `review_required` flags issues, not action permission.

`totals` has exactly integer `pairs`, `blocked_pairs`, `requested_units`,
`requested_cases`, `proposed_units`, `proposed_cases`, `deferred_units`,
`lost_units`, `safety_shortfall_units`, `exception_count`. Quantity totals
sum **known unblocked pairs only**; they are not a claim that blocked needs
are zero. `pairs` includes blocked rows and `blocked_pairs` makes the
unquantified scope explicit. `lost_units` includes both phases.

`next_action` is exactly:
`Review proposal quantities, dated shortages, and DC controls before any separate business action.`

## Exceptions and failure handling

Every exception has string `code`, `message`, `reference`. Validation
exceptions have only those keys. A reference is a field path, or
`role:key-part|key-part`, or the documented join key. Business exceptions
also have `store_id`, `sku`, `on` (date) and `units` (positive integer).
Their reference is `store_id|sku`, except receipt issues use receipt ID.
Sort business exceptions by code, store ID, SKU, date, reference.

| Code | Exact message / meaning |
| --- | --- |
| invalid-record | `<reference> must <requirement>.`; reject invalid shape, type, identifier, date, mapping or horizon |
| duplicate-key | `Duplicate <role> key.`; reject all duplicates, including conflicting DC routes |
| snapshot-date-mismatch | `Inventory snapshot must match as_of.` |
| contradictory-stock | `Reserved and blocked units exceed physical on-hand.` |
| contradictory-receipt | `Closed receipts must have zero remaining units.` |
| capacity-date-mismatch | `Capacity dispatch date must match as_of.` |
| unmatched-route | `Every store/SKU must have exactly one route and stock row.`; reference `store_stock/routes` |
| missing-dc-evidence | `Route requires matching DC stock and dispatch capacity.`; reference store/SKU |
| missing-demand | `Every coverage day requires an explicit residual-demand row.`; first sorted missing store/SKU/day reference |
| out-of-window-demand | `Demand row has no routed store/SKU coverage day.`; first sorted extra key |
| unmatched-inbound | `Receipt requires a routed store/SKU.`; reference receipt ID |
| overdue-inbound | `Overdue in-transit evidence blocks this store/SKU proposal.`; units = receipt remainder |
| late-inbound | `Receipt is after coverage and contributes no stock.`; units = receipt remainder |
| allocation-limited | `Whole-case request exceeds available DC stock or capacity.`; units = deferred request, on = dispatch |
| lost-demand | `Forecast demand is unfilled on the stated day.`; units = dated lost forecast |
| safety-shortfall | `Projected closing stock is below safety policy.`; units = final safety gap, on = coverage end |

For `invalid-record`, requirements are exact phrases: `be an object with
exactly these fields: <alphabetically sorted comma-space field list>`;
`be integer 1`; `be true`; `be boolean`; `be a SYN-prefixed uppercase
alphanumeric identifier`; `be a valid YYYY-MM-DD date`; `be a positive
integer`; `be a nonnegative integer`; `not exceed 366 days`; `be a portable
JSON leaf filename`; `assign a distinct filename to every role`; `be an
array`; `be a nonempty array`; `be in-transit, received, or cancelled`;
`be positive for in-transit receipts`; `keep lead_days plus review_days at
most 366`; or `allow the complete coverage horizon within supported dates`.
Field references use zero-based source row indices such as
`routes[0].case_pack`, root `input`, or role names for whole-array errors.

The first eleven codes above reject the whole input; the last five are
explicit review issues after successful validation. A malformed JSON file,
unreadable file or unexpected implementation error is an execution failure,
not a business-negative pass. Surface it; do not emit a success-shaped
fallback. Unknown stock, dates or receipts never silently become zero.

## Demonstration and execution evidence

The supplied demo requests 6, 6 and 8 units for three pairs. Shared BLUE
stock limits the second pair, and a four-case DC budget limits the third.
The final proposal is 6, 3 and 4 units (13 units, four cases), with seven
dated/quantity exceptions. Closing stocks are 6, 1 and 0. Two closed
receipts contribute no extra stock.

Local developer baseline command, from this scenario directory:

```powershell
python -B baseline.py --input mock-data\demo.json --output baseline-output\manual-demo.json --trace baseline-output\manual-demo.trace.json
```

Choose fresh output/trace filenames; the CLI refuses existing paths and
input/output/trace aliasing. Local execution needs an already available
developer Python; it is **not an end-user installation requirement**.
Native authoring must implement the procedure independently and must not
depend on this baseline file or developer runner.

The baseline emits actual input, validation, join, pre-arrival decision,
request decision, allocation decision, exception and output snapshots.
Tables show bounded readable subsets and true total row counts. The
central producer will render `demo/baseline.webm` from this actual trace
with the label **Synthetic baseline execution visualization - not Cowork
or a live system**. No POS/ERP/native UI is shown or claimed. A missing
video means the media step is not yet ready, not permission to substitute
fabricated screenshots. Local arithmetic/trace evidence is not native
creation, installation or invocation evidence.

## Native handoff: blocked, no substitute route

As of **2026-09-14**, approved Computer Use tools are removed; an unlocked
accessible native session is also required. Native creation, installation
and independent invocation are **blocked and unrun**. Historical output
publication is **unknown**, not Installed. Do not use Playwright, another
browser, a private API, cookies, tokens or shell automation as an alternate
native route. Runtime 0.2.1 and historical artifacts are frozen.

After the parent explicitly restores and authorizes the native gate, give
the actual Native Creator only this `HOW_TO.md`, `workflow.json`,
`connections.json`, the demo input and the real centrally produced video.
Use existing native attachment/file and permitted execution facilities.
Do not supply evaluator-only materials. Ask it to generate a standalone
review-only output plugin implementing this complete procedure and exact
result contract for arbitrary valid bundles, not hard-coded demo values.

The parent then inspects the actual generated output, records provenance,
stores only actual native-generated artifacts under root `output`, installs
through the approved native experience, and independently invokes it on
fresh inputs. Do not mark generated, installed or compared without the
corresponding observed evidence. Do not create a placeholder ZIP.

Connection metadata is honest synthetic-file input/native-file output:
`mock-exports-only`, `not-required`, no connections, endpoint or auth.
A real commerce backend is unverified and unnecessary here. No backend,
custom MCP server, Azure resource, external model/media API, DB/queue,
workflow engine, gateway, device agent, custom UI runner, scheduler or
runtime installer may become a dependency. Stop before financial or
physical business actions; a completed proposal is never permission to
perform one.
