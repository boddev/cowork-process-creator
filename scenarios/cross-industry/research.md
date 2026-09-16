# Cross-industry scenario research

Research date: **2026-09-14**. State: **research only; awaiting full
15-scenario catalog approval before implementation**.

This pack proposes three additional industries, not three variations on the
same report. Its checkout started at
`1915f046b59c30c576cdaecb50ecfb6e092d23a2`. Shared contract v1 at
`d641b1f34328e5293e043d5975d0944b485236c0` was read for interface alignment;
this research does not replace or modify that contract.

| Candidate | Industry / owner | Process family | Bounded completion |
|---|---|---|---|
| cross-industry-01 | Logistics / freight audit analyst | Delivery-evidence and charge reconciliation | A shipment/invoice review packet, exception queue, and proposed case closures |
| cross-industry-02 | Energy and utilities / maintenance planning coordinator | Readiness and constrained window allocation | A proposed resource plan, unresolved-work backlog, and conflict explanations |
| cross-industry-03 | Professional services / project accountant | Approval-aware billing draft reconciliation | A local billing-review packet with candidate amounts, draft differences, and holds |

The machine-readable companion is `research.json`. Both files contain private
evaluation designs and **must not be supplied to Creator**. They are research
proposals, not implemented fixtures, a native demonstration, or an execution
claim. Expected facts below were reasoned from the stated policies before
writing or running any baseline.

## Verified primary sources

All nine URLs below were fetched successfully on **2026-09-14**, and the
returned primary body supported the narrow claim stated here. Search answers
were used only to discover candidates: some suggested IBM and Oracle URLs
differed from their actual citations. The URLs below are the fetched URLs, not
unverified search prose. No government, regulatory, or industry-standard rule
is asserted by these scenarios.

| ID | Fetched primary URL | Supported claim and boundary |
|---|---|---|
| oracle-pod | [Recording Proof of Delivery](https://docs.oracle.com/en/applications/jd-edwards/supply-chain-manufacturing/9.2/eoatm/recording-proof-of-delivery.html) | Oracle JD Edwards EnterpriseOne 9.2 records delivery date, delivery time, and received-by information. It does not establish our POD revision policy or carrier pricing. |
| oracle-freight-match | [Understanding Invoice Matching](https://docs.oracle.com/en/applications/jd-edwards/supply-chain-manufacturing/9.2/eoatm/understanding-invoice-matching.html) | Freight invoice matching compares invoiced amounts with calculated shipment charges. The documented downstream AP voucher is expressly outside this scenario. |
| oracle-freight-fields | [Matching Freight Invoices](https://docs.oracle.com/en/applications/jd-edwards/supply-chain-manufacturing/9.2/eoatm/matching-freight-invoices-1.html) | The product associates invoice header information with selected freight charges. Our neutral export fields are not claimed to be an Oracle import/API schema. |
| ibm-work-orders | [Work orders overview](https://www.ibm.com/docs/en/maximo-manage/cd?topic=tracking-work-orders-overview) | IBM Maximo work orders identify tasks and needed labor, materials, services, and tools. No actual maintenance instructions are reproduced. |
| ibm-resource-scheduling | [Scheduling work based on resource availability](https://www.ibm.com/docs/en/maximo-manage/cd?topic=view-scheduling-work-based-resource-availability) | Planning considers start/end requirements and craft, asset, location, item, and tool availability, with schedule adjustments. This does not authorize work or establish an optimization algorithm. |
| ibm-resource-view | [Resource planning in schedules](https://www.ibm.com/docs/en/maximo-manage/cd?topic=overview-resource-planning-in-schedules) | Maximo distinguishes required/available craft hours and other-resource availability, including calendar context. Our capacity-one grid search is an invented teaching policy, not Maximo's solver or a safety standard. |
| ms-approvals | [Approvals overview](https://learn.microsoft.com/dynamics365/project-operations/approvals/approvals-overview) | Project Operations approval records concern time, expense, and material entries; approval creates actuals and cancel/recall can reverse them. We read synthetic status snapshots and perform none of those actions. |
| ms-proforma | [Proforma invoices](https://learn.microsoft.com/dynamics365/project-operations/proforma-invoicing/create-manual-proforma-invoice) | For Project Operations Integrated with ERP, proforma review is an additional review of approved/unbilled transactions; draft adjustments precede confirmation. Automated creation, confirmation, and ERP integration are not implemented here. |
| ms-confirm | [Confirm a proforma project-based invoice](https://learn.microsoft.com/dynamics365/project-operations/proforma-invoicing/confirm-proforma-invoice) | Confirmation makes the invoice read-only and creates financial actuals. This supports the stop-before-confirmation boundary, not permission to post or send invoices. |

## Common mock, arithmetic, and execution contract

Each case is one `mock-data/<case-id>.json` attachment under shared contract
v1. Inside it, `config` supplies explicit fictional policy, while `files` holds
separate **logical file exports**, for example `shipments.json` and
`pod-events.json`. Each logical filename is a table label, not a path to load
from disk. This preserves multi-file joins without adding an undeclared
connection or attachments outside the shared native staging allowlist.

The typed export schemas and proposed fields are in `research.json`; final
scenario metadata will follow the shared contract after the build gate.

- JSON must be finite and duplicate-key-free. IDs are nonempty strings;
  booleans are not accepted as numbers. Unknown fields that would change a
  decision are not silently ignored.
- Currency values use fixed two-decimal strings and Python `Decimal`.
  Rates/fractions are decimal strings; money rounds **per documented line**
  with `ROUND_HALF_UP`, then totals sum rounded values. There is no FX, tax,
  universal tariff, statutory overtime, or inferred cap.
- Timestamps require an explicit offset. Normalize to UTC for comparisons
  and output; do not infer a machine-local zone or depend on a timezone-data
  installation. Durations are integer minutes and timestamps have whole
  seconds. Date-only service/rate periods use ISO dates and half-open bounds.
- Evidence is eligible when `recorded_at <= as_of`; a future revision never
  overrides an eligible earlier revision. Two conflicting highest revisions
  are held for clarification, never decided by filename or row order.
- Row IDs must be unique in each export. Malformed records reject the whole
  bundle before business outputs. Well-formed but contradictory business
  evidence is explicitly quarantined at the affected entity, except an
  unschedulable dependency cycle, which rejects the planning bundle.
- Results must account for every input business entity as proposed,
  reconciled, deferred, excluded, or quarantined. Unknown expected amounts
  remain null/uncomputed, not zero. Do not subtract partially computed
  expected totals from a complete invoice total.
- Output arrays have explicit stable ordering. Results and actual stage traces
  are written to new destinations only through shared `scenario_support`.
  Inputs, expected files, existing outputs, and business systems stay unchanged.

All tolerances, pricing, capacities, ordering, required evidence, receipt
thresholds, and cutoffs below are **fictional scenario configuration**. Public
product documentation justifies the operational context, not these values.

## 1. Logistics: delivery/POD/carrier charge exception review

**Role and trigger.** A freight audit analyst receives a day-close bundle from
a fictional carrier settlement desk. Several shipment deliveries, POD
revisions, rate cards, carrier invoices, charge lines, and prior review cases
must be reconciled together.

**Start.** Freeze the supplied snapshot and cutoff; inventory all six exports.
**End.** Produce a local shipment reconciliation, per-invoice rollup, an owned
exception queue, and proposed reopen/close decisions for prior review cases.
No delivery confirmation, carrier contact, AP voucher, payment authorization,
or TMS update occurs. `ready-for-review` means only a human can review the
matched evidence; it never means approved for payment.

### Inputs and ordered process

The six logical files are `shipments.json`, `pod-events.json`,
`rate-cards.json`, `carrier-invoices.json`, `invoice-lines.json`, and
`review-history.json`. Shipments identify carrier, lane, planned delivery,
currency, and shipped units. POD revisions provide received-by, delivered
units, delivery time, gate times, and recorded time. Rates are effective-dated.
Invoice headers and charge lines are independent exports; history relates a
shipment and issue code to a prior review state.

1. **Intake:** inventory each export and record the supplied cutoff and policy.
2. **Validate:** check types, unique row IDs, charge codes, monetary strings,
   timestamp ordering, positive block lengths, and header/line coherence.
3. **Join:** associate invoice lines with invoice and shipment; cross-check
   carrier/currency, then join POD, rate candidates, and prior cases.
4. **Select evidence:** use the unique highest eligible POD revision and the
   unique rate active on the shipment's planned-delivery UTC date. Missing,
   revoked, conflicting, or quantity-inconsistent POD prevents pricing.
5. **Price:** calculate linehaul, rounded fuel, and capped detention from
   observed gate intervals using the selected fictional rate.
6. **Reconcile:** compare supported billed charges with expected charges,
   applying an inclusive absolute/relative tolerance to the shipment total.
7. **Triage:** explain missing evidence, late evidence requests, ambiguous
   rates, header mismatches, duplicates, or positive/negative charge variance.
8. **Revisit cases:** re-evaluate each previous issue against current evidence;
   propose closed, still-open, or reopened states without mutating history.
9. **Close the packet:** account for all shipments and invoices, separate
   computed/uncomputed totals, assign review owners, and emit the review packet.

### Decision semantics

For a priced shipment:

```text
fuel = round_cents(linehaul * fuel_fraction)
excess_seconds = max(0, gate_out - gate_in - free_wait_minutes * 60)
blocks = ceil(excess_seconds / (detention_block_minutes * 60))
detention = min(detention_cap, blocks * detention_block_amount)
expected = linehaul + fuel + detention
variance = billed - expected
tolerance = max(absolute_tolerance, round_cents(expected * relative_tolerance))
within_tolerance = abs(variance) <= tolerance
```

A zero excess has zero blocks; no duration is rounded before the ceiling.
Both overcharges and undercharges outside tolerance require review.
`as_of - planned_delivery > missing_pod_grace_hours` makes missing POD overdue;
exactly the grace interval is not overdue. Invoice totals must equal their
line totals; multiple billings of the same shipment/charge are held, not
deduplicated silently. Output shipments sort by shipment ID; invoices by
invoice ID; issues by shipment ID and issue code.

### Independent case designs

**Demo:** four shipments, two invoices, two prior cases. Default tolerance is
USD 5.00 absolute / 0 relative; missing-POD grace is 24 hours. Rates use 10%
fuel, 60 free minutes, 30-minute detention blocks at USD 25.00, capped at
USD 100.00. The cutoff is `2026-09-14T12:00:00Z`.

| Shipment | Independently reasoned result |
|---|---|
| LG-D01 | Linehaul 1000.00; 75-minute dwell gives 25.00 detention; expected 1125.00; billed 1130.00; +5.00 is exactly within tolerance. |
| LG-D02 | Linehaul 800.00; 130-minute dwell gives three blocks / 75.00; expected 955.00; billed 1000.00; +45.00 is held; the previously resolved variance case is proposed reopened. |
| LG-D03 | Billed 660.00; no eligible POD; planned delivery was September 12 at 09:00Z, so age is 51 hours; expected remains uncomputed and evidence is overdue. |
| LG-D04 | Linehaul 400.00; exactly 60-minute dwell gives zero detention; expected/billed 440.00; prior missing-POD case is proposed closed. |

Invoice LG-INV-D1 contains D01/D02: billed 2130.00, expected 2080.00.
LG-INV-D2 contains D03/D04: billed 1100.00, known expected 440.00 but
**incomplete**. Total billed is 3230.00; review-ready line amount is 1570.00;
held line amount is 1660.00. Computable billed 2570.00 minus known expected
2520.00 equals 50.00. The uncomputed shipment is never treated as zero.

**Holdout A:** three new shipments, new carrier/lane contracts, different
block lengths and caps, tolerance 2.00 / 1%, and an effective-date boundary.
A01 selects the new 900.00 rate on October 1 UTC, not the expiring 850.00 rate.
At 12.5% fuel and 46 minutes of dwell against 45 free minutes, one 15-minute
block at 20.00 gives expected 1032.50. Billed 1042.83 differs by 10.33, exactly
the rounded 1% tolerance, so it is review-ready. A02 uses linehaul 500.00,
8% fuel, and 121-minute dwell; six blocks are capped at 60.00: expected
600.00, billed 615.00, held. A03's newly eligible POD closes a prior missing
case; a future void revision is ignored; expected/billed is 770.00.
Totals: billed 2427.83, expected 2402.50, variance 25.33,
review-ready 1812.83, held 615.00.

**Holdout B:** four new shipments, tolerance 1.00 / 2%, four-hour grace, an
as-of exclusion, an ambiguous rate, and an undercharge. B01 has only future
POD and is one hour after planned delivery: 220.00 held, not overdue. B02
has two simultaneously active rates: 330.00 held and uncomputed. B03 has
linehaul 100.00, 7% fuel, exactly 30 free minutes of dwell: expected 107.00,
billed 100.00, variance -7.00 beyond 2.14 tolerance. B04 matches at 220.00.
Totals: billed 870.00; ready 220.00; held 650.00; computable billed 320.00,
known expected 327.00, variance -7.00. Both ambiguous amounts stay uncomputed.

**Malformed negative:** one charge amount is `"12oops"`; reject the bundle,
`outputs: {}`, with an explicit invalid-amount issue before pricing.
**Contradictory negative:** C01 has two highest eligible POD revisions that
disagree on delivered units; hold its 550.00 with no price. C02 independently
matches at 110.00. Billed 660.00 is accounted for as ready 110.00 / held
550.00; only 110.00 participates in the computed comparison.

## 2. Energy/utilities: maintenance readiness and resource-window plan

**Role and trigger.** A utility maintenance planning coordinator receives a
weekly export of fictional work packages, reserved kits, resources, candidate
windows, existing bookings, and prerequisite status.

**Start.** Freeze the planning horizon and validate the administrative
planning data. **End.** Produce a proposed, contingent resource schedule,
readiness matrix, conflict explanations, utilization totals, and deferred-work
queue for a human planner. The report is **not safe-to-work clearance**.
It provides no equipment operations, isolation/lockout instructions,
permit/authorization decisions, dispatch, or actual schedule changes.
Administrative `plan_approved` is only exported planning metadata.

### Inputs and ordered process

Seven logical files are `work-orders.json`, `requirements.json`,
`kit-components.json`, `resources.json`, `resource-windows.json`,
`commitments.json`, and `prerequisite-status.json`. Crews, tools, and planning
areas are capacity-one resource tokens. An area's availability window is only
a candidate planning constraint, not evidence that physical work is permitted.
Kits are pre-reserved **for a particular work order**, not a shared stock pool
that the baseline can allocate or procure.

1. **Intake:** inventory work, planning horizon, grid, and seven exports.
2. **Validate:** check aware dates, durations, resource references, unique
   keys, required quantities, and the internal prerequisite graph.
3. **Join:** attach requirements, work-order-specific reserved kits, eligible
   crews, fixed area/tool resources, and prerequisite evidence to each order.
4. **Assess readiness:** defer missing planning approval, insufficient reserved
   quantity, unresolved external predecessors, or predecessors already deferred.
   Known future kit arrival changes the earliest possible proposed start.
5. **Allocate windows:** repeatedly choose the highest-priority order whose
   internal predecessors have been processed. Search permissible start slots,
   then eligible crew IDs, respecting every required resource's window.
6. **Explain conflicts:** retain observed rejected-slot reasons and IDs of
   clashing commitments/proposals; an exhausted search becomes a deferred item.
7. **Roll up load:** calculate proposed minutes by resource separately from
   existing committed minutes and report unfilled requirements.
8. **Close the plan:** account for every order and emit contingent proposals,
   deferred-work actions, and a prominent no-authorization boundary.

### Temporal and numeric semantics

The configured horizon, availability, commitments, and proposals are
half-open intervals `[start, end)`. Ending at another booking's start does not
overlap. A job must fit wholly inside one availability window for **each**
required resource and finish no later than its due time and horizon end.
Adjacent windows are not silently stitched into a longer staffing window.

Each proposal consumes one crew, its fixed area, and its optional fixed tool
for the full duration; resources have capacity one. Candidates are evaluated
by increasing UTC start, then lexicographic crew ID. Grid points are relative
to horizon start; round the earliest bound up to the next grid point.
Select dependency-resolved work by `(priority ascending, due_at, work_order_id)`,
recomputing that set after every decision. This is a deterministic greedy
planner, **not a global optimizer or Maximo algorithm**.

An internal predecessor's proposed end is a contingent earliest bound, not
proof of completed work. An external predecessor must have explicit completed
evidence at/before the snapshot cutoff. Reserved kit quantities below
requirements defer the order; no material is purchased, moved, or consumed.
A cycle rejects the planning bundle rather than guessing an order.
Proposals sort by start then work-order ID; readiness/backlog by work-order
ID; load by resource ID. Conflict examples retain actual search order.

### Independent case designs

**Demo:** six orders; October 5, 2026, 08:00-16:00Z; 30-minute grid.
Electrical crew CE1 is available 08:00-16:00; mechanical crew CM1,
08:00-12:00. Tool T1 is available 08:00-16:00. CE1 has an existing
09:00-10:00 booking and T1 an 11:00-12:00 booking. Areas: A1
08:00-12:00, A2 09:00-15:00, A3 08:00-12:00, A4 08:00-16:00.
Priorities follow D01 through D06. All required kits/approval are ready at
08:00 except the explicitly deficient D04; external prerequisite EXT-OPEN
for D05 is unresolved.

| Order | Independently reasoned result |
|---|---|
| UT-D01 | Electrical, A1/T1, 60 minutes, earliest 08:00, due 12:00: propose CE1 at 08:00-09:00; adjacent CE1 booking is not an overlap. |
| UT-D02 | Electrical, A2/T1, 120 minutes, earliest 09:00, due 15:00: reject 09:00 through 11:30 starts against crew/tool conflicts; propose CE1 at 12:00-14:00. |
| UT-D03 | Mechanical, A3, 60 minutes, after D01, due 12:00: propose CM1 at 09:00-10:00, contingent on D01's proposed finish. |
| UT-D04 | Electrical, A4, 60 minutes: needs three kit units, has one; defer with a two-unit shortage. |
| UT-D05 | Mechanical, A3, 60 minutes: unresolved external prerequisite; defer without a proposed start. |
| UT-D06 | Mechanical, A3, 90 minutes, earliest 10:00, due 12:00: propose CM1 at 10:00-11:30. |

Four proposals total 330 job-minutes (5.50 hours); two orders are deferred.
Crew proposal minutes: CE1 180 and CM1 150. Tool T1 proposal minutes: 180.
Existing minutes are reported separately: CE1 60 and T1 60. Total booked
crew fractions are 240/480 for CE1 and 150/240 for CM1; no implicit overtime
or extra capacity is introduced.

**Holdout A:** four new orders on November 2, 13:00-18:00Z, with explicit
`-05:00` input offsets and a 30-minute grid. Two electrical crews CE-A01 and
CE-A02 have whole-horizon availability; CE-A01 is booked 13:00-14:00.
Tool T-A1 is booked 15:00-16:00; areas A/B span the horizon.
A01 is 90 minutes, area A/tool, due 18:00: use CE-A02 at 13:00-14:30,
because earliest start outranks lexicographic crew. A02 is 60 minutes,
area B/tool: earliest feasible is CE-A01 at 16:00-17:00. A03 is 30
minutes, area A/no tool, after A01: CE-A01 at 14:30-15:00.
A04 is 60 minutes, area B/no tool, with its reserved kit available only at
17:30 and due 18:00: no full slot, so defer.
Three proposals total 180 minutes; each crew receives 90 proposed minutes;
the tool receives 150, separately from its 60 committed minutes.

**Holdout B:** five new orders on December 1, 08:00-12:00Z; a 15-minute
grid; electrical E-B1 and mechanical M-B1; tool T-B1; area X 08:00-10:00
and area Y 09:00-12:00. B02 has priority 1 but depends on priority-2 B01:
B01 first takes E-B1/X/tool at 08:00-09:00 (60 minutes), then B02 takes
M-B1/Y/tool at 09:00-09:45 (45 minutes). Priority-3 B03 needs 60 minutes
of E-B1/X/tool after 09:00 and by 10:00; the remaining window cannot fit,
so defer. Priority-4 B04 uses E-B1/Y without the tool at 09:45-10:15
(30 minutes), exactly adjoining B02. B05 lacks administrative planning
approval and is deferred. Three proposals total 135 minutes; crew loads are
90/45 minutes and tool load is 105 minutes.

**Malformed negative:** `duration_minutes: true` is not the integer one;
reject before proposing any schedule.
**Contradictory negative:** two otherwise valid work orders require each
other as an internal prerequisite; reject with `cyclic-prerequisite`,
`outputs: {}`, rather than presenting a feasible or safe plan.

## 3. Professional services: approved time/expense-to-billing draft review

**Role and trigger.** A project accountant receives billing-cutoff exports
for several fictional projects and clients, with approved/pending/recalled
entries, rate changes, prior billing, and existing draft line snapshots.

**Start.** Freeze cutoff, service period, policies, and the nine exports.
**End.** Produce a local candidate-charge table, invoice-line reconciliation,
per-project cap calculations, and an owned correction/hold packet.
No time approval, expense reimbursement, actual invoice creation or send,
proforma confirmation, AR/GL posting, customer communication, or tax advice
is performed.

### Inputs and ordered process

Nine files are `projects.json`, `rates.json`, `time-entries.json`,
`expense-entries.json`, `approval-events.json`, `billed-transactions.json`,
`draft-invoices.json`, `draft-lines.json`, and `expense-policies.json`.
All people and clients are synthetic IDs. Previously billed history can
include earlier entries absent from the current intake export; those records
still consume the configured period cap. A current entry's billed identity
must agree with its project/currency.

1. **Intake:** inventory exports, explicit service period, and snapshot cutoff.
2. **Validate:** check IDs, typed minutes/amounts, currencies, date intervals,
   approval enums, and header/line references.
3. **Join:** relate entries to projects, effective rates or expense policies,
   approval histories, prior billing, and draft lines.
4. **Resolve eligibility:** select the latest eligible approval; quarantine
   conflicting top revisions. Exclude out-of-period, nonchargeable, already
   billed, pending/rejected/recalled entries; never infer approval.
5. **Price and check policy:** price eligible time per line; check expense
   category caps and receipt evidence. Hold disallowed expenses rather than
   truncating, reimbursing, or converting them.
6. **Reconcile drafts:** identify missing, mismatched, duplicate, and
   ineligible draft details, retaining entry-level evidence for correction.
7. **Check project caps:** add prior billed-in-period amounts to eligible new
   amounts; if the cap would be exceeded, hold the entire project's new
   candidate amount rather than picking arbitrary billable entries.
8. **Triage:** assign questions and proposed add/update/remove actions.
   Ambiguous evidence requires clarification, not speculative removal.
9. **Close the packet:** account for every entry, draft, and project; emit
   separate per-currency totals and hold/correction summaries for human review.

### Decision semantics

Service dates use `[period_start, period_end)`. Rates also use half-open
date ranges and match project, role, and currency; exactly one must match.
Time amount is `round_cents(minutes * hourly_rate / 60)` **per entry**.
No weekly aggregation, overtime premium, tax, FX, or inferred rate is used.
Expense caps are per entry/category/currency in supplied policy.
At or above `receipt_required_at`, a nonempty synthetic receipt reference is
required. Exceeding `max_amount` holds the entire expense, without truncation.

Well-formed identity contradictions take precedence over eligibility
exclusions. Otherwise check period, chargeability, prior billing, latest
approval, then pricing/expense evidence. Prior posted entries are wholly
excluded from new charges; partial billing/credits are not in this fictional
scope and must not be inferred. Known prior period billing is still included
in cap consumption.

Draft differences use zero monetary tolerance. A cap is exceeded only when
`prior_billed + eligible_new > period_cap`; equality is allowed. A cap hold
blocks the whole project, but diagnostic draft differences remain visible.
Two active draft invoices for the same project/period or duplicate draft
entry details are ambiguous and require clarification, not arbitrary choice.
Uncomputable entries do not participate in a full-total variance.
Entries sort by `(entry_type, entry_id)`, projects by project ID, draft
differences by `(draft_id, entry_type, entry_id, line_id)`. Currencies are
reported separately; a USD/EUR grand total is forbidden.

### Independent case designs

**Demo:** September service period; cutoff October 2, 2026, 12:00Z.
P1 has USD 2000.00 period cap and 100.00/hour consultant rate; P2 has
500.00 cap and 120.00/hour. Travel cap is 100.00, meals cap 50.00;
receipts are required at/above 50.00.

| Evidence | Independently reasoned result |
|---|---|
| P1 time T1/T2 | Approved 120/90 minutes at 100.00/hour gives 200.00 and 150.00. |
| P1 time T3/T6 | T3's 60 minutes are pending, so excluded. T6's approved 60 minutes were already billed at 100.00, so excluded from new charges. |
| P1 expenses E1/E2 | Receipted travel 80.00 is eligible; receipted meals 60.00 exceed the 50.00 cap and are held, not reduced to 50.00. |
| P2 time T4/T5 | Approved 120/30 minutes at 120.00/hour gives 240.00 and 60.00. |
| P2 expenses E3/E4 | Travel 90.00 lacks a required receipt and is held; receipted meals 40.00 are eligible. |

P1 eligible new amount is 430.00; prior billed 100.00 plus new is 530.00,
within cap. Its draft contains T1 200.00, T2 160.00, T3 100.00, and
already-billed T6 100.00: raw total 560.00. Proposed corrections:
add E1 80.00, reduce T2 by 10.00, remove T3 100.00 and T6 100.00.
`560 - 10 - 100 - 100 + 80 = 430`.

P2 eligible new is 340.00. Earlier period billing of 200.00 makes proposed
consumption 540.00, exceeding cap by 40.00; hold all 340.00, not just 40.00.
Its draft contains T4 240.00 and E4 40.00, total 280.00; the missing T5
60.00 is diagnostic only while the project is held.
Across USD projects, eligible new is 770.00, draft total 840.00, and prior
billed 300.00. No invoice is created or updated.

**Holdout A:** new October period and one different project, cap 1000.00;
rate 150.00 through October 14, then 180.00 effective October 15.
A1: 50 minutes on October 14 -> 125.00; A2: 75 minutes October 15 ->
225.00. A3's approved 20 minutes are subsequently recalled before cutoff,
and a future reapproval is ignored. A4 is explicitly nonchargeable.
Travel policy changes to a 150.00 cap: 49.99 without receipt is eligible,
50.00 without receipt is held at the inclusive receipt threshold.
Receipted meals 40.00 fit the new 60.00 meals cap.
Eligible new is 439.99; prior billed 560.01 consumes exactly 1000.00 with
new charges, so there is **no cap hold**. The draft has all eligible
439.99 plus recalled A3 at 60.00: 499.99. Remove that 60.00 only.

**Holdout B:** new November period, two projects in different currencies,
changed receipt threshold 30.00. P-B1 is USD: two separate one-minute
approved time entries at 100.00/hour each round to 1.67, totaling **3.34**,
not the 3.33 obtained by aggregating minutes before rounding. An eligible
20.00 expense makes new amount 23.34. An EUR 15.00 expense against this
USD project is held, without conversion. The USD draft contains one time
line at 1.66 and the 20.00 expense: 21.66; propose +0.01 on that line and
add the missing 1.67.
P-B2 is EUR: 60 minutes at 90.00/hour gives 90.00; an unreceipted 30.00
expense is held exactly at the threshold. A December 1 time entry is out
of the November period. Prior billed 160.00 plus new 90.00 equals its
250.00 cap. Its 90.00 draft matches. Expected currency totals remain
USD 23.34 and EUR 90.00, never added together.

**Malformed negative:** expense amount `"-12.00"` is outside this positive
charge-only schema; reject with invalid-amount and `outputs: {}` rather than
inventing a credit/reimbursement.
**Contradictory negative:** C1 has two highest eligible approval revisions,
one approved and one recalled, for an otherwise 100.00 time entry already
on a draft. Hold it for clarification; do not choose an approval or suggest
removal as if recall were established. A separate project C2's valid
30 minutes at 120.00/hour matches its 60.00 draft. Computable expected and
draft totals are both 60.00; quarantined draft amount is 100.00.

## Planned trace, tests, and runtime requirements

After approval, each baseline will implement `solve(payload) -> (result,
events)` and call the shared `scenario_support.run_cli`. It will not import
Creator code or a generated plugin. Python's standard-library `json`,
`decimal`, `datetime`, `collections`, `pathlib`, and the shared helper suffice;
no dependency install is proposed. File hashing/output guarantees belong to
the shared helper rather than three independent implementations.

Each demo trace will contain at least six **observed** stages and all six
contract kinds: input, validation, join, decision, exception, output.
Tables will show actual selected rows, intermediate calculations, attempted
slots or approval branches, and final artifact facts. Repeated work loops may
produce additional events or faithful labeled subsets within the shared table
limits. Negative records may stop at validation.

The foundation, not these baselines, will centrally render the actual demo
trace as a short labeled synthetic video. No native/live-system screenshot,
recording, or external media service is needed or claimed. At the future native
gate the native host must already provide approved attachment/media inspection,
local file facilities, and any permitted bundled-stdlib execution required by
the generated standalone plugin. If those native facilities are absent, stop;
do not install a runtime, decoder, agent, scheduler, or service.

Planned tests include independent demo/two-holdout comparisons; rejected
malformed records; contradictory evidence; exact numeric/date boundaries;
future revisions; input-order invariance; duplicate IDs; zero/one/many-item
loops; ambiguity instead of arbitrary tie-breaking; missing joins; monetary
rounding; no-overwrite of output/trace; and malformed/deep/duplicate-key or
nonfinite JSON through the shared CLI. Planning adds cycle detection, resource
adjacency, prerequisite propagation, and impossible windows. Billing adds
currency separation, rate-range overlap, recalled approvals, and whole-project
cap holds. Goldens will be authored independently **before** any baseline run,
then fingerprinted; generated output cannot be copied into their oracle.

## Build and native gates

Only these two research files are phase-1 outputs. No scenario baseline,
expected fixture, video, ZIP, installer, native UI action, or production write
has been produced as part of this research.

Implementation must wait for the parent's explicit
`research15-catalog-approved/build` message. The parent owns shared
`scenarios/SCENARIO_CONTRACT.md`, helper, schema, and central media pipeline.
This owner is limited to `scenarios/cross-industry/` and owned tests.
Runtime 0.2.1, `appPackage`, root `output`, old release/native artifacts,
historical documents, and the main checkout remain untouched.

After implementation, Creator's exact input allowlist is the approved
`HOW_TO.md`, `workflow.json`, `connections.json`, demo payload, and centrally
rendered demo video. Research, baseline source, expected data, holdouts,
negatives, baseline results, and validation answers remain private.
`connections.json` will declare `mock-exports-only`, `not-required`, and an
empty connections array, with no endpoints, credentials, or inferred native
availability.

**Native not run / blocked as of 2026-09-14.** Both restored approved Computer
Use tools and an unlocked accessible session, plus parent authorization, are
required before native work. This owner performs no native UI activity.
No Playwright/browser, private API, cookie/token, shell, or other access route
may substitute. Historical N00 publication remains unknown after
`Publishing...`; local research cannot establish creation, installation, or
fresh native output invocation. Only the parent can coordinate those later
evidence gates.
