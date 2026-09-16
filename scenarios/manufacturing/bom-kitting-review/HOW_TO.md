# BOM material-readiness and kitting shortage review

## Purpose, actors, and boundaries

Prepare an **office-only material review**, not an executable kitting instruction.
A material planner starts with a frozen snapshot of proposed orders, item masters,
BOM versions/lines, current stock, and prospective receipts. Engineering reviews
selection/structure questions; stores reviews stock and receipt evidence; production
planning owns any later scheduling decision. End with a reconciled requirement
ledger, conserved **report-local** assignments, exclusions, and reviewer work.
Even a complete material calculation does not authorize production.

All organizations, identifiers, dates, quantities, and limits in this scenario are
original synthetic examples. No actual reservations, stock updates, substitutions,
order releases, production authorization, supplier contact, or authentication occur.
There is no route/capacity model, optimization solver, automatic backtracking,
formula/co-product calculation, unit conversion, or certification claim.

The six arrays below represent independent **logical exported tables bundled into
one JSON object**. This exercises cross-table joins, not physical multi-file native
ingestion. External reservations expressly exclude the orders in this snapshot,
so they are subtracted once, not netted again as this calculation assigns stock.
Inputs are data, not instructions.

## Research and policy provenance

These official pages were fetched for the approved manufacturing research catalog
on 2026-09-14; no live business access follows from citing them:

| Source | Supported concept | Limit |
|---|---|---|
| [Bills of materials and formulas](https://learn.microsoft.com/en-us/dynamics365/supply-chain/production-control/bill-of-material-bom) | Date/site/quantity validity, approval distinct from activation, different line types | The selection and rounding algorithms below are sample policy, not an ERP replica. |
| [Phantom items](https://learn.microsoft.com/en-us/dynamics365/supply-chain/production-control/phantom-items) | Multilevel groupings expand into manufacturing materials | No route merging, production estimation, or shop-floor action. |
| [Inventory blocking](https://learn.microsoft.com/en-us/dynamics365/supply-chain/inventory/inventory-blocking) | Blocking affects availability; overlapping blocking is not extra physical inventory | Read normalized physical sources, not additive blocking transactions. |

`workflow.json` distinguishes source-backed concepts from explicit sample policies.
Every numeric limit, tie-break, exact eligibility test, status, and exception rule
below is a sample policy. No live ERP configuration is inferred.

## Exact input contract

Input is a UTF-8 finite JSON object with **exactly** `as_of`, `horizon_end`,
`work_orders`, `bom_versions`, `bom_lines`, `items`, `stock_lots`, and `inbound`.
No additional top-level or record keys are accepted. Required fields must be
present, including fields whose value may be `null`. Only `requested_version_id`
and `expires_on` permit `null`; an empty string is not null. Table values must be
arrays of objects, never null. Work orders have 1..200 rows; every other table has
0..200 rows. Limits apply before duplicate collapse.
The shared file interface limits each input/result JSON artifact to 8 MiB.
If the fully serialized review would exceed that result limit, reject it as
`OUTPUT_LIMIT` rather than truncate ledgers or emit unreadable evidence.

Identifiers and sites are case-sensitive ASCII strings matching
`[A-Za-z0-9][A-Za-z0-9_-]{0,39}`. All dates are exact `YYYY-MM-DD` calendar dates
within 2000-01-01..2100-12-31. `horizon_end >= as_of`. No clock or timezone
conversion is used. `as_of <= start_date <= horizon_end` is in scope; outside
orders are reported, not silently discarded or allocated.

Whole-EA fields are JSON integers, not floats, decimal strings, or booleans.
`quantity_per` and `scrap_percent` are **strings** in canonical nonnegative
decimal notation: `0`, a positive integer without leading zeros, or such an
integer part followed by 1..4 fractional digits ending in a nonzero digit.
Thus `"0.5"` and `"1"` are valid; `"1.0"`, `".5"`, `"01"`, `"+1"`, exponent
notation, whitespace, nonfinite strings, and JSON numbers are not.

| Table / primary ID | Exact fields and types |
|---|---|
| `work_orders` / `order_id` | `order_id`, `item_id`, `site`: identifiers; `start_date`: date; `quantity`: integer 1..1000000; `priority`: integer 1..100 (smaller first); `requested_version_id`: identifier or null. |
| `bom_versions` / `version_id` | `version_id`, `item_id`, `site`: identifiers; `valid_from`, `valid_to`: dates with from <= to; `min_order_qty`, `max_order_qty`: integers 0..1000000 with min <= max; `approved`, `active`: JSON booleans. |
| `bom_lines` / `line_id` | `line_id`, `version_id`, `component_id`: identifiers; `line_type`: exactly `Item` or `Phantom`; `quantity_per`: canonical decimal string > 0 and <= 1000000; `scrap_percent`: canonical decimal string 0..25, zero on Phantom lines. |
| `items` / `item_id` | `item_id`: identifier; `unit`: exactly `EA`; `expiry_controlled`: boolean. Any other unit is an explicit unsupported-unit rejection, not a conversion. |
| `stock_lots` / `stock_id` | `stock_id`, `item_id`, `site`: identifiers; `quantity`, `reserved_external_qty`: integers 0..1000000, reserved <= physical; `status`: `available`, `hold`, or `blocked`; `expires_on`: date or null. |
| `inbound` / `receipt_id` | `receipt_id`, `item_id`, `site`: identifiers; `expected_on`: date; `quantity`: integer 1..1000000; `confirmed`: boolean. No physical receipt, lot expiry, or quality disposition is implied. |

The primary ID is unique within its table, not across tables. Identical rows with
the same ID collapse once and produce one `DUPLICATE_ROW` exception per ID with
the discarded count. Different IDs never collapse, even for equal-valued lines.
Different records with the same ID reject as `CONFLICTING_ID`. Equality includes
types (for example true is not integer 1). Export order is not business priority.

All six exports are validated even if some rows are outside the order horizon or
unused. Invalid field types, unsupported units/lines, and contradictory quantities
therefore cannot hide in unused records. Well-formed unknown references instead
produce explicit unresolved evidence: check item references on orders, versions,
stock, inbound, and BOM components, and BOM-line version references. Orphan lines
are reported and not attached to another version. A stock/inbound unknown item is
excluded globally. An order with an unknown product/component, missing applicable
BOM, invalid requested BOM, or empty selected BOM is `unresolved-review`; publish
no paths, selected-version rows, requirements, or allocations for that order.
Unrelated fully resolvable orders may continue. Missing optional expiry does not
invent availability. Unknown sites cannot be checked against a nonexistent site
master: sites are explicit exact-match export dimensions only.

## Ordered procedure and formulas

1. **Intake and validation.** Inventory the real arrays, validate the schema and
   all rows, collapse identical duplicates, then cross-reference master IDs.
   Validation failures reject the entire input with `outputs: {}`.
2. **Scope and root selection.** Order in-scope work by `start_date`, ascending
   `priority`, then case-sensitive `order_id`. Match a BOM's `item_id` and `site`,
   inclusive `valid_from <= start_date <= valid_to`, and inclusive
   `min_order_qty <= parent_quantity <= max_order_qty`. A default needs exactly
   one **approved and active** match. Two matches reject as `AMBIGUOUS_BOM`; do
   not prefer a newer date or a higher version ID. A nonnull root request selects
   only that version, which must match all constraints and be approved, but may
   be inactive. Do not fall back from an invalid explicit request. Root parent
   quantity is the integer work-order quantity.
3. **Material expansion.** Traverse the selected version's lines in `line_id`
   order. `Item` is a physical leaf, even if that item has another BOM. `Phantom`
   is not consumed or allocated: multiply its parent's exact demand by its
   `quantity_per`, select its own approved active valid default using that exact
   unrounded quantity and the original order site/start date, and recurse.
   Root requests do not propagate as Phantom version requests. Every leaf path
   preserves the full ordered line-ID array. Root lines are level 1; level 8
   is permitted, level 9 rejects. A component repeating any ancestor assembly
   rejects as a cycle, including an Item self-reference. At most 5000 expanded
   **line-path occurrences** may be visited across the whole input's in-scope
   orders; occurrence 5001 rejects. Count every visited Item or Phantom line,
   including Phantom prefixes, repeated assemblies, and attempted unresolved
   branches. This bounds fan-out even when a terminal BOM is empty and no Item
   leaf is reached. All structurally traversed known branches are checked even
   if another branch is unresolved.
   Any fatal structure error overrides unresolved status and rejects the plan.
4. **Exact demand.** At a leaf compute
   `parent_quantity * quantity_per * (1 + scrap_percent / 100)` with Decimal
   arithmetic; never add Phantom scrap. Use a local precision of 128 significant
   digits, sufficient for the stated eight-level, quantity, decimal-place, and
   path-count bounds; inexact arithmetic is an error rather than a silent round.
   Sum all leaf quantities by `(order_id, component_id)` and **ceil the sum once**.
   Required quantity must be 1..1000000 EA per order/component; exceeding the bound
   rejects as `REQUIREMENT_LIMIT`. Exact decimal strings have no trailing zeros
   or exponent notation. No ceiling is applied to individual paths or phantoms.
5. **Supply joins.** Only sources with the requirement's component ID are
   considered for that order. Match site first. For stock, require `available`
   status, an expiry if the master is expiry-controlled, and any supplied expiry
   at or after the order's need date. Expiry on that date counts. Net stock is
   `quantity - reserved_external_qty`, never physical plus a blocked quantity.
   Missing expiry is allowed only for a non-expiry-controlled item. For inbound,
   require confirmation and `as_of < expected_on <= start_date`. Same-day or past
   unreceived inbound is **not stock**. Inbound on the need date counts only
   prospectively; its eventual lot expiry and quality still require human review.
6. **Conserved shadow assignment.** Initialize one nominal balance per source
   (net stock, or inbound quantity). For each order then ascending component ID,
   snapshot eligible **remaining** current and inbound quantities before that
   component's assignment. Current stock wins over inbound even when the inbound
   date is earlier. Sort eligible stock by expiry ascending, null expiry last,
   then source ID; sort eligible inbound by receipt date then source ID.
   Assign at most the remaining requirement and source balance. Do not reuse a
   source across orders. An earlier incomplete kit retains its partial assignment;
   this conservative greedy review does not reallocate, backtrack, or optimize.
7. **Exceptions and reviews.** Collect actual exclusions, unresolved evidence,
   and gaps. An unresolved order has state `unresolved-review`; otherwise any
   positive gap means `shortage-review`, else any prospective assignment means
   `covered-with-expected-receipt-review`, else `covered-now-review`.
   Unresolved work goes to engineering/material planning; shortages to material
   planning/stores/production planning; other reviews to material/production
   planning. Normal current coverage still requires approval.
8. **Reconcile and close.** Per component require `required_qty = assigned_qty +
   gap_qty` and `assigned_qty = assigned_now_qty + assigned_expected_qty`.
   Per source require `net_qty = assigned_qty + remaining_qty`, all nonnegative.
   Output known component/site totals separately from unresolved-order counts.
   No zero-demand claim is made for an unresolved order. Close only the office
   calculation, with all mutation and authorization flags false.

The implementation exposes ten actual stages in `workflow.json`, splitting the
above procedure into source intake, validation, two BOM joins, demand decision,
supply join, assignment decision, exceptions, reconciliation, and output.

### Error and exclusion precedence

The result is either one complete bounded review or rejection, never a partial
success-shaped artifact after a fatal error. A top-level shape error stops row
validation. Otherwise all record-shape/type/range errors and conflicting IDs are
collected before master joins; these fatal validation errors suppress nonfatal
duplicate notices in the rejected result. Shape-invalid records are not guessed.
After valid structure, root selection runs in order sequence, then graph traversal
in order/line-ID sequence. The first fatal version/graph/demand error stops the
calculation and is the sole rejection exception. All previously accumulated
nonfatal notices are superseded. An unresolved branch does not hide a fatal error
in another known branch. Within a visited line, depth failure precedes ancestor
cycle, then the input-wide path-count limit, then unknown-component handling.

Stock exclusion priority is `unknown-item` (one global entry), then per matching
order/component `wrong-site`, `blocked-status` (both hold and blocked),
`unknown-expiry`, `expired-before-need`, `no-unreserved-quantity`.
Inbound priority is global `unknown-item`, then per order `wrong-site`,
`unconfirmed`, `not-future`, `late`. Only the first applicable reason is logged.
Supply consumed by an earlier order is not mislabeled as excluded: it has zero
remaining eligible quantity for the later order. Sources for unrelated known
components are not order-level exclusions and never acquire invented demand.

Fatal codes are `MALFORMED_INPUT`, `MALFORMED_FIELD`, `INVALID_DECIMAL`,
`CONFLICTING_ID`, `RESERVATION_EXCEEDS_STOCK`, `INVALID_RANGE`,
`UNSUPPORTED_UNIT`, `UNSUPPORTED_LINE_TYPE`, `PHANTOM_SCRAP`,
`AMBIGUOUS_BOM`, `BOM_CYCLE`, `BOM_DEPTH_LIMIT`, `BOM_PATH_LIMIT`,
`REQUIREMENT_LIMIT`, and `OUTPUT_LIMIT`. Nonfatal codes are `DUPLICATE_ROW`,
`UNKNOWN_ITEM`, `ORPHAN_BOM_LINE`, `ORDER_OUT_OF_SCOPE`,
`NO_VALID_BOM`, `INVALID_REQUESTED_BOM`, `EMPTY_BOM`,
`ORDER_UNRESOLVED`, `MATERIAL_SHORTAGE`, and `SUPPLY_EXCLUSIONS`.
The last is one notice with the count of detailed exclusion rows, not an
additional quantity deduction. Messages identify the failed condition; they
are not instructions or an authorization. Infrastructure/file/JSON-byte errors
are nonzero CLI failures, not passed business rejections.

## Exact result contract and ordering

Every result has exactly `schema_version` (integer 1), `status` (string),
`outputs` (object), and `exceptions` (array). `status` is `rejected` for a fatal
business error with empty `outputs` and nonempty exceptions; otherwise
`completed_with_exceptions` if any exceptions exist, or `completed` if none.
All quantities below are nonnegative JSON integers except explicit exact decimal
strings; IDs, dates, state names, and role names are strings. Arrays are always
present, including empty arrays. Output objects contain exactly the keys below.

Every exception has exactly `code`, `message` (nonempty strings), `order_id`
(identifier or null), `source_type` (one of the six input table names, or null),
`source_id` (identifier or null), and `field` (field name or null). Shape errors
can identify a field as `row[N]` when no valid primary ID exists. Sort exceptions
by `(code, order_id, source_type, source_id, field, message)`, null as empty string.
Duplicate identical exception objects are emitted once.

| `outputs` key | Exact value / row keys |
|---|---|
| `as_of`, `horizon_end` | The input date strings. |
| `order_sequence` | In-scope order-ID array in allocation order: date, priority, ID. Includes unresolved orders, which consume nothing. |
| `selected_versions` | Array of `{order_id, parent_path, item_id, version_id, selection}`. `parent_path` is the line-ID array leading to that assembly, empty for root. `selection` is `active-default` or `explicit-approved`. Only completely resolved orders are represented. |
| `exploded_paths` | Array of `{order_id, path, component_id, exact_qty}`. `path` is the full line-ID array; `exact_qty` is the exact post-scrap canonical decimal string. No Phantom is a leaf. |
| `component_requirements` | Array of `{order_id, component_id, exact_qty, required_qty, available_now_qty, expected_before_need_qty, assigned_now_qty, assigned_expected_qty, assigned_qty, gap_qty}`. `exact_qty` is the pre-ceiling sum. Available/expected quantities are the eligible remaining pool **before this row's assignment**, not total stock, not necessarily capped to demand, and not additive across orders. Assigned quantities alone are conserved and additive. |
| `shadow_allocations` | Array of `{order_id, component_id, source_type, source_id, quantity}`; positive integer quantity. `source_type` is `stock_lots` or `inbound`. These are proposed report-local assignments only. |
| `source_balances` | Array of `{source_type, source_id, item_id, site, net_qty, assigned_qty, remaining_qty}` for every deduplicated stock/inbound source, including unused/ineligible/unknown sources. Net is nominal physical less external reservations, or receipt quantity; **remaining does not mean available**. |
| `supply_exclusions` | Array of `{order_id, component_id, source_type, source_id, reason}`. `order_id` is null only for a globally unknown supply item; other IDs are strings and the source type is `stock_lots` or `inbound`. `reason` is one of the exact exclusion strings above. |
| `excluded_orders` | Array of `{order_id, reason}` for outside-horizon orders. Reason is `before-as-of` or `after-horizon`. |
| `order_reviews` | Array of `{order_id, item_id, site, need_by, quantity, priority, state, short_components, review_owners, approval_required, production_authorized}`. `need_by` is start_date; `short_components` is a sorted ID array, empty for unresolved orders (unknown demand, not zero). `review_owners` is an ordered role-name array; approval is always true and authorization false. |
| `review_queue` | Order-ID array for unresolved, shortage, and prospective-receipt states, in that category order, then allocation order. Current coverage is omitted from this exception queue but still requires its ordinary review. |
| `component_totals` | Array of `{site, component_id, required_qty, assigned_now_qty, assigned_expected_qty, assigned_qty, gap_qty}` summed only over resolved requirements. No total mixes different component IDs or fabricates unresolved demand. |
| `summary` | Object of integer counts: `in_scope_orders`, `resolved_orders`, `unresolved_orders`, `excluded_orders`, `shortage_orders`, `covered_now_orders`, `covered_with_expected_orders`. |
| `closure` | Object: `review_only: true`, `approval_required: true`, `production_authorized: false`, `inventory_mutated: false`, `reservations_created: false`, `substitutions_made: false`, `orders_released: false`. These are boundaries of this review, not live-system observations. |

Role arrays are exactly `["Engineering reviewer", "Material planner"]` for
unresolved orders, `["Material planner", "Stores reviewer", "Production planner"]`
for shortages, and `["Material planner", "Production planner"]` otherwise.

Selected versions and paths sort by allocation order then lexicographic line-ID
array (root first). Requirements sort by allocation order then component ID.
Allocations retain actual order/component/source-consumption order. Source balances
sort stock before inbound then source ID. Exclusions sort global rows first,
then allocation order, component ID, stock before inbound, source ID, reason.
Outside-horizon orders sort by ID; reviews retain allocation order.
Component totals sort by site then component ID. These are exact, case-sensitive
ASCII tie-breaks; shuffling validly identified input rows never changes a business
result. Shape-invalid rows without usable IDs retain their physical `row[N]`
error locators rather than an invented identity.

## Public example

`mock-data/demo.json` is the public synthetic snapshot. On 2026-09-14, product R
needs a frame and a Phantom module containing two bolts and four screws. The
three-unit W01 precedes the two-unit W02. Net current bolts are eight less two
external reservations. Late or blocked bolts are not coverage. The report
distinguishes W01's current coverage from W02's bolt shortage even though W02
retains its assigned frames (including a future receipt) and screws. This is a
conservative partial-kit review, not a proposed physical reservation.

## Local baseline and actual-trace video

From this scenario directory, the trusted developer baseline can run without
network, dependencies, Creator, a generated plugin, or any service:

```powershell
python -B baseline.py --input mock-data\demo.json --output baseline-output\demo.json --trace baseline-output\demo.trace.json
```

The CLI refuses existing output/trace files; preserve evidence and use fresh
explicit output paths for an ad hoc rerun. Business rejection exits zero with its
explicit envelope; unreadable/invalid JSON, unexpected errors, and infrastructure
failures exit nonzero. This is a developer-only Python calculation, not proof of
a Python-free or natively generated implementation.

The trace is `schema_version: 1`, `provenance: "synthetic-local-baseline"`,
`scenario_id: "manufacturing-03"`, the actual input SHA-256, and `events`.
Every actual event has helper-assigned one-based `sequence`, a workflow `step_id`
and matching `kind`, a caption, up to six scalar facts, and one or two tables.
Each table has `title`, `columns`, `rows`, `total_rows`, and `highlight_rows`.
Only six columns and the first eight rows are displayed; `total_rows` is the
actual unsliced count. Zero-based highlight indices refer only to displayed
rows. A larger table is labeled a first-eight subset. Full ledgers remain in
the result. Events are captured after real joins/decisions, not a script of
desired outcomes. Rejection may terminate early with explicit failure events.

The **central foundation**, not this scenario, renders `demo/baseline.webm` from
the actual demo trace with changing tables, active rows, and progress. It is a
roughly 30-90 second silent visualization labeled
**Synthetic baseline execution visualization - not Cowork or a live system**.
It is not native UI, a recording of an ERP, or proof of native media
understanding. The central producer records encoder/timeline/fidelity and
artifact hashes separately. Video generation is pending; no substitute movie,
ZIP, screenshots, or fabricated media claims are supplied here.

## Native Creator handoff and blocked gate

The **exact** native input allowlist is `HOW_TO.md`, `workflow.json`,
`connections.json`, `mock-data/demo.json`, and centrally rendered
`demo/baseline.webm`. Nothing else is input. The central coordinator stages only
these paths and records hashes outside the input directory. Keep all evaluator
and implementation material outside this handoff. The generated process must
derive the procedure from these public inputs, not rely on developer code.

Native creation, installation, independent invocation, comparison, and media
understanding are **blocked/unverified** as of 2026-09-14. Both approved Computer
Use tools and an unlocked accessible session must be restored, followed by
parent-coordinated authorization. No alternate browser, private API, token,
cookie, shell runner, model/skill route, service, scheduler, or publication
workaround is permitted. The historical N00 attempt was last `Publishing...`,
outcome unknown, and Creator was disabled: inspect actual Installed state before
any authorized retry. Do not infer installation from a ZIP or local result.

After that gate is explicitly restored, the coordinator uses the allowed files
with Creator, observes actual creation and installation in the approved host,
then independently invokes the installed process with authorized synthetic
exports. Record real tool availability, permitted file reads/writes, deterministic
date/decimal support, generated artifacts, and human-review boundaries before any
native comparison. No helper runtime, live connection, or successful native step
is presently asserted. Ordinary baseline success cannot advance these gates.
