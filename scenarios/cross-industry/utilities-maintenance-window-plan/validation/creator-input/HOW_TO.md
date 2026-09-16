# Maintenance readiness and resource-window conflict plan

## Purpose and non-operational boundary

An energy/utilities maintenance planning coordinator reviews a frozen bundle of
**synthetic exports** and prepares a contingent resource-window plan. Start with
the supplied cutoff and planning horizon; finish with one disposition for every
work order, proposed crew/area/tool intervals, rejected-candidate explanations,
resource load, and an owned review queue.

**This is planning review only, not safe-to-work clearance or authorization.**
Do not operate equipment, instruct physical maintenance, perform isolation or
lockout, approve permits, dispatch people, change a real schedule, procure or
move material, or write to a business system. `plan_approved` is administrative
snapshot metadata, not authority to work. An internal predecessor's proposed
finish is a contingent planning bound, not evidence of completed work.

Public context, fetched 2026-09-14:

- IBM [Work orders overview](https://www.ibm.com/docs/en/maximo-manage/cd?topic=tracking-work-orders-overview):
  work orders describe tasks and required labor, material, services, and tools.
- IBM [Scheduling work based on resource availability](https://www.ibm.com/docs/en/maximo-manage/cd?topic=view-scheduling-work-based-resource-availability):
  planning considers required resources and start/end constraints.
- IBM [Resource planning in schedules](https://www.ibm.com/docs/en/maximo-manage/cd?topic=overview-resource-planning-in-schedules):
  resource views distinguish required and available craft hours and other
  resource/calendar availability.

Those documents establish context only. Every grid, capacity, priority,
kit-reservation rule, search limit, and tie-break below is fictional sample
policy. This is neither IBM's scheduling algorithm nor a global optimizer,
regulatory method, maintenance instruction, or safety standard.

## Exact input bundle

The input is a UTF-8 JSON object with exactly `config` and `files`. `files`
contains exactly the seven logical filenames below, each mapped to an array
of row objects. Filenames are export labels inside the attachment; never open
them as paths or infer a connection from them. Empty arrays are allowed.
No endpoints, credentials, personal information, or real business data belong
in the input.

`config` has exactly:

| Key | Type and constraint |
|---|---|
| `as_of` | Whole-second offset-aware timestamp; no later than horizon start |
| `horizon_start`, `horizon_end` | Offset-aware, minute-aligned timestamps; positive horizon at most 31 days |
| `slot_minutes` | Integer 1-1440, not boolean; grid anchored at horizon start |
| `max_search_starts` | Integer 1-10000, not boolean; per-order bound on examined start slots |

All timestamps use `YYYY-MM-DDTHH:MM:SSZ` or an explicit `+HH:MM`/`-HH:MM`
offset and are normalized to UTC. No machine-local timezone, daylight-saving
inference, or timezone database is needed. IDs are nonempty strings of at most
80 printable ASCII characters with no surrounding whitespace. Quantities are
integers up to 1000000; booleans are not integers. Unknown or missing keys are
invalid. Each export is limited to 5000 rows; at most 100 work orders and
200 resources are accepted as a local review workload bound.

| Export | Exact row keys and types |
|---|---|
| `work-orders.json` | `work_order_id`: ID; `priority`: integer 1-1000000; `earliest_start`, `due_at`: timestamps with due later than earliest; `duration_minutes`: integer 1-44640; `craft_code`, `area_resource_id`, `owner`: IDs; `tool_resource_id`: ID or null; `predecessors`: array of distinct IDs; `plan_approved`: boolean |
| `requirements.json` | `work_order_id`, `item_id`: IDs; `required_quantity`: integer 1-1000000 |
| `kit-components.json` | `kit_component_id`, `work_order_id`, `item_id`: IDs; `reserved_quantity`: integer 0-1000000; `available_at`: timestamp |
| `resources.json` | `resource_id`: ID; `kind`: `crew`, `tool`, or `area`; `craft_code`: ID for a crew, null otherwise; `capacity`: integer exactly 1 |
| `resource-windows.json` | `window_id`, `resource_id`: IDs; `start`, `end`: minute-aligned timestamps with end later than start |
| `commitments.json` | `commitment_id`, `resource_id`: IDs; `start`, `end`: minute-aligned timestamps with end later than start |
| `prerequisite-status.json` | `prerequisite_id`: external ID; `state`: `complete` or `open`; `recorded_at`: timestamp; `completed_at`: timestamp when complete and null when open; completion no later than recording |

Primary IDs must be unique within their export. Requirements are unique by
`(work_order_id, item_id)`. Each predecessor array has at most 5000 IDs.
Kits reference a real order/requirement pair;
quantities are reserved to that order, not a shared stock pool. Work orders
reference an existing area, an optional existing tool, and a craft. A craft
without any crew is an explicit scheduling deferral, not malformed data.
Windows and commitments reference existing resources. Every commitment must
fit one of that resource's supplied windows; two commitments on a capacity-one
resource may adjoin but must not overlap.

An external prerequisite ID cannot also be an internal work-order ID.
An internal dependency graph must be acyclic. A missing external record is
unresolved evidence, not an assumed completion. Future external records are
also unresolved at the cutoff. Future reserved-kit arrival is a planning
estimate that can legitimately constrain a future proposal.

## Procedure and deterministic decisions

1. **Intake.** Freeze `config` and all seven exports. Count records and retain
   their synthetic IDs. Never retrieve a live schedule or change input files.
2. **Validate.** Check every schema and reference above, then reject dependency
   cycles and overlapping existing commitments. Return the rejected envelope
   below on the first validation failure. Do not emit partial plans from
   malformed or internally impossible planning data.
3. **Join.** Attach required items and reserved components to each work order;
   map craft to lexicographically ordered eligible crews; map fixed area/tool
   IDs to their windows/bookings; join internal/external predecessors.
4. **Assess readiness.** Sum reserved quantity for each required item.
   If insufficient, report required/reserved/missing, without purchasing or
   reallocating anything. Otherwise sort that item's components by
   `(available_at UTC, kit_component_id)` and find the first time cumulative
   reserved units reach the requirement; later unneeded surplus does not delay
   readiness. The latest such item time is the material bound. Explicit external
   completion at or before cutoff is required. Preliminary readiness does not
   resolve internal predecessors.
5. **Allocate in dependency order.** Repeatedly select from orders whose
   internal predecessors have all been processed, sorting that set by
   `(priority ascending, due_at UTC, work_order_id)`. Recompute the set after
   every decision. A deferred predecessor blocks its successor.
   Primary deferral precedence is `planning-approval-missing`, `kit-shortage`,
   `prerequisite-unresolved`, then `no-eligible-crew`, then the window search.
   Always retain independently found shortages and pending predecessor IDs.
6. **Search resource windows.** For an eligible order, take the maximum of
   horizon start, order earliest start, material readiness, external completion,
   and internal predecessors' proposed end. Round up to the first horizon-grid
   point; expose this `ready_at` even when no full window will fit. At successive
   grid starts, require end no later than due time and horizon end. Check fixed
   area first, then optional tool. For each, require full containment in one
   supplied availability window, then no existing booking, then no previous
   proposal. Only when fixed resources pass, examine crews by crew ID with the
   same checks. The first feasible crew at the earliest feasible start wins.
7. **Explain exceptions.** For each failed fixed-resource check record one
   conflict with null crew; for each failed crew check record that crew.
   Stop at the first failed constraint per candidate, not every possible cause.
   Existing bookings sort by `(start, commitment_id)` and take precedence over
   proposed bookings, which sort by `(start, work_order_id)`. If no slot fits,
   defer as `no-feasible-window`. If another slot could be examined but the
   configured start limit was reached, defer as `search-limit`, never claim the
   unexamined range is infeasible. Assign an explicit next action to each
   deferred order's owner. No queue entry is an instruction to perform work.
8. **Close the plan.** Emit every order's disposition, proposals, conflict
   explanations, review queue, resource loads, summary and the boundary notice.
   Count proposed minutes once per order for job totals and once per required
   resource for resource load. Leave existing bookings and kit records unchanged.

All intervals are half-open `[start, end)`: equality at a booking endpoint is
not overlap. A proposal occupies one crew, its fixed area and optional tool for
its full duration. Adjacent availability windows are **not stitched** to fit
a job. Overlapping windows are allowed; union them only for computing available
minutes. Available and committed minutes are clipped to the planning horizon.
Proposal minutes already lie inside it. No overtime, extra capacity, split work,
partial kit use across orders, or global optimization is inferred.

## Exact output envelope and business schema

Return exactly `schema_version: 1`, `status`, `outputs`, and `exceptions`.
`status` is `completed` when no orders are deferred, including an empty batch;
otherwise `completed_with_exceptions`. A schema/reference/cycle/commitment
validation failure returns `rejected`, `outputs: {}`, and one explicit exception.
No time-of-execution field is included. Results are deterministic.

For either non-rejected status, `outputs` has exactly:

| Key | Value |
|---|---|
| `notice` | Exact string `Planning review only; not safe-to-work clearance or authorization.` |
| `planning_window` | Object with `as_of`, `start`, `end` normalized UTC timestamps, plus integer `slot_minutes`, `max_search_starts` copied from config |
| `orders` | Array ordered by work-order ID of the rows defined below |
| `proposals` | Array ordered by `(start UTC, work_order_id)` of the rows defined below |
| `conflicts` | Array in actual processing order, then grid start, fixed-resource/crew check order; no post-sort or truncation |
| `review_queue` | One row per deferred order, sorted by work-order ID |
| `resource_load` | One row per resource, sorted by resource ID, including unused resources |
| `summary` | Object: integer `work_orders`, `proposed`, `deferred`, `job_minutes`, `rejected_candidates` (number of conflict rows) |

Each `orders` row has exactly `work_order_id` (ID), `disposition`
(`proposed`/`deferred`), `reason` (null for proposed, one queue code below
otherwise), `ready_at` (UTC grid timestamp or null when an approval/material/
predecessor gate prevents a lower bound), `missing_materials` (array sorted by
item ID), `pending_predecessors` (sorted IDs), and integer `search_starts`.
Each missing-material row has `item_id`, `required`, `reserved`, `missing`,
with the latter three integers and `missing = required - reserved > 0`.
Orders with no eligible crew still expose their computed ready bound.
`search_starts` counts examined grid starts, not crew trials; gated orders and
orders whose duration cannot fit the remaining horizon have zero starts.

Each `proposals` row has exactly `work_order_id`, `start`, `end`,
`duration_minutes`, `crew_id`, `area_id`, `tool_id` (ID or null), and
`contingent_on` (sorted internal predecessor IDs; no external IDs).

Each `conflicts` row has exactly `work_order_id`, `candidate_start`,
`crew_id` (ID or null for fixed resources), `resource_id`,
`reason` (`outside-window`, `existing-booking`, or `proposed-booking`), and
`blocking_id` (commitment/work-order ID; null for outside-window).

Each `review_queue` row has exactly `work_order_id`, `code`, `owner`,
`next_action`. Non-rejected `exceptions` is a matching sorted array with
`code`, `message`, and `work_order_id`; fixed messages/actions are:

| Code | Exception message | Queue next_action |
|---|---|---|
| `planning-approval-missing` | `Administrative planning approval is missing.` | `Request administrative planning evidence; do not authorize work.` |
| `kit-shortage` | `Reserved kit quantity is insufficient.` | `Review the order-specific reservation shortage with the material planner.` |
| `prerequisite-unresolved` | `A prerequisite lacks an eligible completion or contingent proposal.` | `Clarify predecessor evidence or replan the dependent order.` |
| `no-eligible-crew` | `No crew matches the required craft.` | `Ask the planner to review craft coverage; do not assign unqualified resources.` |
| `no-feasible-window` | `No complete resource window fits the order.` | `Review candidate windows, due time, and resource conflicts.` |
| `search-limit` | `The configured search-start limit was reached.` | `Review the unexamined range or an explicitly revised search limit.` |

Each `resource_load` row has exactly `resource_id`, `kind`, integer
`available_minutes`, `committed_minutes`, `proposed_minutes`, and
`total_booked_minutes = committed_minutes + proposed_minutes`. This is
planning occupancy, not utilization certification or authorization.

Rejected exceptions contain exactly `code`, `message`, `path`. Validation paths
use `config.<field>`, `files.<logical-name>[<zero-based-row>].<field>`, or the
relevant object/table path. Validation checks run in declared export order and
input row order; business processing/output is row-order invariant for valid
data. Codes are `invalid-shape`, `invalid-id`, `invalid-integer`,
`invalid-duration`, `invalid-time`, `invalid-value`, `duplicate-id`,
`missing-reference`, `cyclic-prerequisite`, or `contradictory-commitments`.
The last two messages are respectively
`Internal prerequisites contain a cycle.` and
`Existing capacity-one commitments overlap.`.

Invalid JSON bytes (including duplicate keys, nonfinite/deep JSON), file errors,
and existing destination paths are CLI failures with nonzero exit status, not
successful business-negative results. A malformed-record business rejection
is a successful execution with explicit `rejected` data.

## Local demonstration and future native use

The developer-only baseline command, from this scenario folder, is:

```powershell
python -B baseline.py --input mock-data\demo.json --output baseline-output\demo.json --trace baseline-output\demo.trace.json
```

Use fresh destinations; never overwrite inputs or prior output/trace files.
The local baseline uses bundled Python standard-library functions and the
shared adapter, not Creator or any generated plugin. End users do not install
Python, FFmpeg, a scheduler, a database, an agent, or any developer tool.

The foundation centrally renders the **actual local execution trace**, including
joined rows, readiness gates, selected windows, rejected candidates and final
load, into a short silent video. It is labeled
`Synthetic baseline execution visualization - not Cowork or a live system`.
Do not represent it as a native application recording.

For future parent-authorized native creation, supply only this HOW_TO,
`workflow.json`, `connections.json`, `mock-data/demo.json`, and the centrally
rendered `demo/baseline.webm`. Implement the documented procedure and output
contract, not a call into developer baseline source. Research, sources,
scenario metadata, baseline code, oracles, other cases and validation answers
are private evaluation material and are not Creator inputs.

**Native creation, installation, and independent invocation are not run and
blocked as of 2026-09-14.** Both restored approved Computer Use tools and an
unlocked accessible session, with parent-coordinated authorization, are required.
No browser/Playwright, private API, cookie/token, shell or other alternative
access route is permitted. When legitimately available, native Creator must
produce a real standalone plugin; a fresh invocation on withheld data is later
compared privately with the independently expected/baseline results. Do not
manufacture a local output ZIP or claim that these files prove native execution.
