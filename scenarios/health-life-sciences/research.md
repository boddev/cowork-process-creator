# Health and Life Sciences research catalog

**Three qualified administrative scenarios; construction is not authorized yet.**
Research retrieved on **2026-09-14**. The full 15-scenario catalog must be
approved by the parent before scenario implementation begins. Shared contract
v1 is already approved for interfaces; that is not approval to build this pack.

The machine-readable counterpart is [research.json](research.json). It includes
source IDs, retrieval facts, claim boundaries, proposed payload fields and joins,
ordered stages, sample policies, five case designs per scenario, and independent
golden strategies. This document and the JSON are internal evaluation-design
artifacts, **not native Creator inputs**.

## Scope and gate

Work begins from `1915f046b59c30c576cdaecb50ecfb6e092d23a2`. The only owned
phase-1 artifacts are these two research files. The separately imported shared
contract comes from `d641b1f34328e5293e043d5975d0944b485236c0`;
[`SCENARIO_CONTRACT.md`](../SCENARIO_CONTRACT.md) owns all manifest, result,
trace, connection, and native-staging interfaces.

All three workflows are **intake-to-review-ready exported-data processes**,
not end-to-end physical or clinical operations. All IDs start with `SYN-`;
role identifiers are synthetic role tokens, not names or provider IDs.
No real people, patients, PHI, trial data, client exports, credentials,
demographics, clinical observations, diagnoses, or test results are used.

Qualified reviewers retain actual clinical, trial, laboratory, and quality
disposition. A completed packet means file processing completed. It does not
approve a site, enroll a participant, accept or reject a specimen, authorize a
test, release or discard inventory, or establish regulatory compliance. A
`rejected` result concerns an invalid **input packet**, never a person,
specimen, or product.

| ID | Proposed folder | Distinct operational mechanics |
|---|---|---|
| hls-01 | `site-essential-document-review` | Contextual requirement grid, temporal document versions, expiry and evidence gaps |
| hls-02 | `cold-chain-excursion-review` | Product-specific time-series evaluation intersected with inventory occupancy and evidence coverage |
| hls-03 | `specimen-accession-reconciliation` | Multi-source exact-key reconciliation, dated order state, cardinality, and administrative backlog aging |

## Primary-source evidence

All sources below were actually retrieved. Search summaries were used only to
discover candidates, never as evidence. Quotations are deliberately short;
source documents and full text extractions are not copied into the repository.

| Source ID | Retrieved primary source | Exact scope used |
|---|---|---|
| hls-src-ich-e6r3 | [ICH E6(R3), final 2025-01-06](https://database.ich.org/sites/default/files/ICH_E6%28R3%29_Step4_FinalGuideline_2025_0106.pdf) | Appendix C.2, printed pp. 63-64 / PDF pp. 70-71; C.3 and essential-record table, printed pp. 64-68 / PDF pp. 71-75 |
| hls-src-fda-e6r3 | [FDA E6(R3) final-guidance announcement](https://www.fda.gov/regulatory-information/search-fda-guidance-documents/e6r3-good-clinical-practice-gcp) | Final-guidance availability, proportionality, and sponsor/investigator responsibilities; not detailed checklist rules |
| hls-src-cdc-temperature | [CDC Temperature Monitoring](https://www.cdc.gov/vaccines/hcp/storage-handling/temp-monitoring.html) | Temperature Excursions and documentation/handling sections |
| hls-src-cdc-storage | [CDC Vaccine Storage and Handling](https://www.cdc.gov/vaccines/hcp/storage-handling/index.html) | Product-specific guidance, toolkit update explicitly dated 2026-07-14, and compliance-language caveat |
| hls-src-cms-clia-manual | [CMS State Operations Manual, Appendix C](https://www.cms.gov/Regulations-and-Guidance/Guidance/Manuals/downloads/som107ap_c_lab.pdf) | D5203; D5301-D5309; D5311-D5313; D5391 |
| hls-src-cms-clia-overview | [CMS CLIA program overview](https://www.cms.gov/medicare/quality/clinical-laboratory-improvement-amendments) | Program scope and distinctions by test-method complexity |
| hls-src-who-lqms | [WHO Laboratory quality management system handbook overview](https://www.who.int/publications/i/item/9789241548274) | Administrative stakeholders are part of laboratory quality management; overview only |

The ICH PDF cover says final version adopted 06 January 2025. Its SHA-256 is
`e6ce19e36ce7d2e294f89ee89492b9e035178c3cca48984392bbd92eec9b002c`.
The CMS PDF cover says **Rev. 236, issued 2026-01-23**; the cited sections
carry **Rev. 233, issued/effective/implementation 2025-09-12**. Its SHA-256 is
`b6937df6f41c22541e55094f5345912289e3406e1fea6e0a4f28b86bb7566f66`.
Both were downloaded from their official public hosts and read with existing
PDF tools; nothing was installed. HTML hashes and unobserved page dates are
not invented.

Important source boundaries:

- ICH C.2.1 says records should be identifiable and appropriately version
  controlled; C.2.4-C.2.6 address locations, filing, completeness, readability,
  availability, and traceable alterations. C.3 makes essentiality contextual.
  It does **not** supply this mock's checklist or a universal annual expiry.
- CDC defines excursions by relevant product instructions, describes
  documentation of timing/temperature/lots, and says **"Do not discard these
  vaccines."** Actual physical response and viability decisions remain outside
  this file workflow. Vaccine guidance is not generalized to every supply.
- CMS D5309 / 493.1241(e) concerns accurate transcription into a record system
  or LIS. D5313 / 493.1242(b) says: **"The laboratory must document the date and
  time it receives a specimen."** These concepts support reconciliation, not
  an invented accession SLA or automated specimen suitability decision.
- The WHO overview supplies quality-management context only. No unexamined
  handbook chapter, ISO requirement, or accreditation claim is attributed to it.

Discovery failures were recorded rather than hidden. Search output included
incorrect ICH section labels, an incorrect PDF URL, and unverified CLIA
section titles. The linked FDA PDF attempt returned `Not found`; detailed
claims instead use the retrieved ICH PDF. eCFR returned an automated-access
notice; no bypass was attempted. Guessed govinfo section URLs and an obsolete
CMS path returned error pages and are not cited as substantive evidence.

## 1. Site essential-document completeness and expiry review

**Purpose:** Turn a dated synthetic document manifest into a contextual
requirement matrix, evidence register, and draft clarification queue. It is
not a site-activation or enrollment gate.

**Trigger and roles:** An on-demand review requested by a synthetic
trial-operations coordinator; a document-control reviewer receives the
packet. A qualified trial reviewer owns real interpretation and disposition.

**Start:** `as_of_date`, sample policy, trial/site exports, a site-kind
requirement table, document metadata, artifact-manifest metadata, and existing
open review tasks.

**End:** An evidence-linked matrix for every applicable site/requirement,
site rollups, selected/excluded version references, and deduplicated draft
requests. No actual CTMS/eTMF is read or changed.

### Payload, joins, and output

The proposed tables are `trials`, `sites`, `requirements`, `documents`,
`artifacts`, and `open_review_tasks`; exact proposed fields are in the JSON.
The first join expands in-scope sites and their trial context against the
site-kind checklist so missing documents remain visible. The next joins
documents by `(site_id, document_type)`, then the selected document to its
artifact-manifest reference. Finally, review reasons join existing tasks by
`(site_id, requirement_id, reason_code)` to avoid duplicate draft work.

Documents have separate effective and recorded dates, integer version
sequence, optional explicit expiry, a signature-recorded indicator, and an
artifact reference. The export's availability/readability indicators are
**reported evidence**, not independent verification of a real document,
signature, or repository.

Business outputs under the shared envelope are `requirement_matrix`,
`site_summary`, `evidence_register`, and `draft_review_queue`, plus the
as-of/policy identifiers and `human_review_required: true`.

### Eight meaningful stages

1. Load the review export and its as-of/policy/provenance.
2. Validate fields, dates, identifiers, bounds, and duplicate/conflicting evidence.
3. Expand the contextual site/requirement grid through the trial/site join.
4. Select as-of documents and join artifact availability.
5. Assess version, signature metadata, expiry, and missing evidence.
6. Isolate exceptions and link existing review tasks without sending or closing them.
7. Reconcile grid counts and unique draft-queue keys.
8. Produce the review-ready packet with the human boundary.

### Proposed decision rules

Only records both effective and recorded by `as_of_date` participate.
Choose the unique highest version sequence, retaining future and superseded
references. An unsigned or unavailable latest document must not fall back to
an older apparently good record. Conflicting highest versions require review.
Issuance after effectiveness or expiry before issuance is contradictory
chronology, not a reason to silently choose another version.

The supplied checklist, protocol-version requirement, signature metadata
requirement, optional refresh period, expiry policy, warning window, and draft
follow-up window are **sample policies**. They are not automatically
applicable regulatory requirements. Proposed demo warning window is 30 days
and draft follow-up is two days.

Effective expiry is the earlier available explicit expiry and
`issued_on + refresh_days`. A null refresh period creates no annual expiry.
When expiry evidence is required but absent, report it as missing. Expiry is
inclusive through its date: expiry before as-of is expired; zero through
`warning_days` remaining is a warning. A no-expiry record with no expiry
requirement is not automatically deficient.

Keep all reasons; priority is conflict, missing document, unavailable evidence,
missing signature evidence, protocol mismatch, missing expiry evidence,
expired, then expiring soon. Reasons generate draft evidence-review requests,
not trial or ethics approvals.

### Case and independent-golden design

| Case | Changed evidence and independently reasoned target |
|---|---|
| demo | Two sites x four requirements = eight cells: three without exception, one same-day expiry warning, four review cells for expired, wrong protocol, unavailable, and missing evidence |
| holdout-a | New site/protocol/dates; future-recorded higher version excluded; +30-day warning included and +31 excluded; null expiry remains valid when not required; existing task referenced once |
| holdout-b | Changed site-kind applicability and seven-day warning window; changed refresh policy; out-of-scope site excluded; unsigned newest version cannot fall back; identical duplicate does not multiply rows |
| negative-malformed | Invalid calendar date, boolean version, or over-limit variant explicitly rejects the input packet |
| negative-contradictory | Conflicting highest-version evidence quarantines its requirement; unrelated valid requirement survives; multiple existing task IDs remain visible without another draft task |

Before baseline execution, independently enumerate the requirement grid,
eligible version keys, date differences, and ordered reason sets. Assert
`required = no_exception + warning + review`, one queue entry per
requirement/reason key, and complete provenance. This is a proposed oracle
strategy; expected files have not yet been created.

## 2. Cold-chain immunization inventory excursion review

**Refined scope:** CDC sources specifically support immunization-product
storage concepts. The scenario therefore uses **synthetic immunization-like
inventory**, not a claim about all medical supplies or real product labeling.

**Trigger and roles:** A simulated alarm or manual retrospective review
request from an inventory coordinator; a quality-review coordinator receives
the packet. Actual manufacturer, public-health, or quality disposition is
outside the simulation.

**Start:** A review window, mock inventory/placement exports, product/profile
tables, sensor assignments, calibration references, timestamped readings,
and prior correspondence references.

**End:** A lot-level evidence packet, interval ledger, gap/conflict register,
unique affected-inventory totals, and draft quality-review requests.
Nothing is physically held, moved, released, discarded, administered, or sent.

### Payload, joins, and output

Join `inventory -> products -> profiles`, then `placements ->
sensor_assignments -> calibrations/readings` using both keys and time
intersections. Join `correspondence` by lot for provenance, never permission.
Each lot moves as a whole; simultaneous locations or unsupported split-lot
quantity evidence require review rather than guessing a distribution.

Temperatures are integer **tenths Celsius**, not floating-point measurements.
Proposed mock profiles are 20..80 and -250..-150, both inclusive. These are
invented fixture profiles, not recommendations for any actual licensed product.

Business outputs include `lot_review`, `interval_ledger`,
`inventory_summary`, `draft_quality_requests`, and prior correspondence,
with `physical_actions_performed: false` and
`quality_disposition_required: true`. Unknown model results are null or
explicitly unknown, not success-shaped zeroes.

### Eight meaningful stages

1. Load the bounded review window and mock exports.
2. Validate timestamp/integer types, profiles, bounds, and conflicting keys.
3. Join lots, profiles, occupancy, assigned sensors, and calibration evidence.
4. Reconstruct covered intervals and clip to the actual mock occupancy.
5. Classify observations against each product's supplied band.
6. Isolate gaps, missing profiles/calibration, and ambiguous attribution.
7. Aggregate unique lots/units and reconcile duration accounting.
8. Produce the evidence packet and draft reviewer requests.

### Proposed decision rules

The review window and occupancy are half-open `[start,end)` intervals.
For this **invented model only**, hold a reading's value until the next
reading or as-of when that full interval is at most `max_gap_seconds`
(demo 600 seconds). Intersect with occupancy and valid sensor-assignment/
calibration intervals. A predecessor reading can cover the start of the window.
Assignments and calibration are also half-open. Point flags apply only within
the lot's window and occupancy under an unambiguous assignment; an endpoint
reading may close an interval without flagging an unoccupied lot.

An adjacent-reading gap larger than the threshold is wholly unknown; do not
bridge even part of it. Missing calibration or a missing product profile is
an evidence gap, not a reason to assume normal conditions. Retain outside-band
point readings even when their exposure duration cannot be estimated.
Reported modeled duration is **not measured continuous exposure or viability**.

Conflicting sensor/time readings, overlapping primary assignments, and
simultaneous lot locations quarantine affected evaluations. No arbitrary
sensor or location wins. For unresolvable lot attribution,
or a missing profile, `modeled_outside_seconds` is null and the union of
occupied time is unknown, without double-counting overlapping placements.
Quantity totals count each reviewed lot
once, not once per excursion, reading, or move.

Any excursion observation, modeled outside duration, missing profile,
coverage gap, or conflict creates a draft review request. Existing
correspondence is untrusted evidence, not a release instruction. Even a
no-observed-exception result never means safe to use.

### Case and independent-golden design

| Case | Changed evidence and independently reasoned target |
|---|---|
| demo | Window 09:00-09:30 UTC; outside interval 09:10-09:20. A 10-unit lot present throughout has 600 outside seconds; a 6-unit lot entering 09:15 has 300. Two reviewed lots total 16 units. A 4-unit frozen-profile lot at valid endpoints is not judged using the refrigerated band |
| holdout-a | Outside interval 09:05-09:10 plus an excessive 09:10-09:25 gap: first lot has 300 outside and 900 unknown seconds; a lot entering 09:10 has no preceding-excursion overlap but still has unknown coverage; future reading excluded |
| holdout-b | Changed profiles, whole-lot moves, exact calibration-expiry boundary, missing profile, and identical duplicate; a prior note claiming release cannot authorize it |
| negative-malformed | Inverted profile, boolean temperature, invalid UTC timestamp, or over-limit variant explicitly rejects only the data packet |
| negative-contradictory | Conflicting same-time readings and overlapping locations quarantine attribution; outside duration is null, not zero; unrelated lot remains reportable |

Independently draw intervals and calculate endpoint differences and
intersections using integer seconds before baseline execution. For resolvable
attribution assert `occupied = covered + unknown`, `outside <= covered`,
and one inventory-quantity contribution per lot. No oracle file or execution
result exists in this research phase.

## 3. Specimen accession/order reconciliation exception report

**Purpose:** Reconcile exported administrative records into a review-ready
mismatch/backlog report. The complete endpoint is the report and draft
clarification queue, not real LIS processing or clinical specimen disposition.

**Trigger and roles:** Manual request from a synthetic accession coordinator;
an order-management reviewer receives the report. A qualified laboratory
reviewer retains all actual interpretation, correction, and disposition.

**Start:** Orders, order lines, dated state events, specimen receipts,
accessions, synthetic test-code metadata, clarification references, and
as-of/SLA policy.

**End:** Exact-key ledger, unmatched-record register, administrative age/SLA
indicators, distinct specimen/line counts, and draft clarification requests.

### Payload, joins, and output

Join `orders -> order_lines/order_events`, then explicit receipt order IDs,
accession specimen IDs, and accession order-line IDs. Cross-reference the
synthetic test-code catalog and compare subject tokens and exported specimen
labels across the linked records. Append clarification references without
editing source data.

One primary specimen can fulfill multiple lines; the sample permits only
one primary specimen per line and one distinct accession per
`(specimen_id, order_line_id)`. Multiple competing links are review cases,
not guessed aliquot, recollection, or retesting behavior.

Subject tokens contain no real identity or clinical data. This deliberately
limited schema is **not a complete CLIA requisition** and omits demographic,
authorized-provider, clinical-result, and suitability fields.

Business outputs are `reconciliation_rows`, `unmatched_records`, `summary`,
and `draft_clarification_queue`, with
`clinical_disposition_performed: false` and
`qualified_review_required: true`.

### Eight meaningful stages

1. Load as-of policy and the bounded mock exports.
2. Validate fields, dates, bounds, identifiers, and conflicting/duplicate evidence.
3. Resolve imported as-of order state from eligible dated events.
4. Join receipts, accessions, order lines, and synthetic test metadata, retaining orphans.
5. Assess identity/label consistency, cardinality, and chronology.
6. Isolate contradictory, missing, cancelled, and unmatched records.
7. Age eligible unaccessioned pairs and reconcile line/specimen denominators.
8. Produce the sorted exception report and draft clarification queue.

### Proposed decision rules

An order event must be effective and recorded by as-of; select its unique
highest sequence. Missing or conflicting state is not assumed active.
Future receipts, accessions, or future-recorded accessions cannot repair
an as-of gap.

Use explicit exact keys only. Missing identities, mismatched subject tokens,
wrong test-code or specimen-label metadata, orphan links, cancelled orders,
multiple competing accessions, and impossible chronology require review.
Do not synthesize collection times, repair IDs by matching names, or infer
test suitability. Clarification text cannot reactivate an order or authorize
acceptance/testing.

Only an unambiguous active order/receipt pair without an accession enters
ordinary backlog aging. Age is `as_of - received_at`; proposed demo SLA is
**60 minutes**, with overdue strictly **greater than** the SLA. Equality
is within-window. Missing receipt means missing age, not zero. This is an
invented administrative SLA, not a CLIA time limit or specimen-stability rule.

Retain all reason codes with structural/identity/cancellation issues ahead
of ordinary pending/overdue classification. Count unique specimens separately
from order lines, and keep every unmatched source record visible.

### Case and independent-golden design

| Case | Changed evidence and independently reasoned target |
|---|---|
| demo | Six receipts: one matched accession; three pending ages 30, 60, and 61 minutes; one orphan; one identity conflict. Partition: one reconciled, two within-window, three review. Five linked order lines are not six specimens |
| holdout-a | Changed day, IDs, and 30-minute SLA; equality/one-minute-over boundary; actual cancellation versus future cancellation; future-recorded accession excluded |
| holdout-b | One specimen validly serves two lines; unmatched active line, missing collection time, label mismatch, and identical duplicate; a note requesting acceptance changes no disposition |
| negative-malformed | Invalid UTC timestamp, boolean sequence, invalid SLA, or derived-pair-limit variant explicitly rejects only the input packet |
| negative-contradictory | Competing accession IDs disagree on identity; another receipt predates collection; no arbitrary winner or negative-age pending case; unrelated valid pair remains visible |

Before baseline execution, enumerate the exact-key join truth table and
unmatched counterparts, apply eligible state events and reason precedence,
then subtract UTC timestamps as integer seconds. Assert ledger partition
conservation, distinct specimen versus line counts, and that an identity
conflict cannot be classified reconciled.

## Determinism, bounded execution, and evidence separation

Proposed configurable ceilings are 1,000 rows per table, 5,000 total rows,
and 10,000 derived pairs. Exceeding a ceiling explicitly rejects the input
packet before an unbounded expansion. No business loop polls a gate, retries
until success, truncates hidden work, or depends on an external scheduler.

Date-only values use `YYYY-MM-DD`; timestamps use whole-second UTC
`YYYY-MM-DDTHH:MM:SSZ`. Temperature/duration arithmetic is integer-based.
Malformed required fields or policies are rejected explicitly; business
contradictions quarantine the affected entity and remain visible.
Exact repeated records collapse with duplicate counts and an exception.
Arrays use documented business-key ordering; output contains no wall clock.
Provenance preserves table/record IDs, policy IDs, chosen/excluded evidence,
and duplicate multiplicity.

After approval, each scenario will have at least five concrete cases:
demo, two genuinely changed holdouts, malformed-record input, and
contradictory-evidence input. Boundary variants are additional targeted
tests, not a claim that five uncreated fixture files already contain them.
Expected JSON is written **before baseline execution**, from documented
independent reasoning and arithmetic. Baseline implementation/results are
never the oracle. Sector-author provenance is not a claim of independent
human review.

Each developer-only Python-stdlib baseline will implement
`solve(payload) -> (result, events)` and use the shared `run_cli`. Its events
must reflect actual intermediate values, with all six shared step kinds
and input/output endpoints. Shared tooling owns the 30-90-second video
rendered from the actual trace and labeled:

**Synthetic baseline execution visualization - not Cowork or a live system**

Internal visual-only storyboard suggestions are in the JSON: an expanded
document-provenance strip, distinct unknown-versus-excursion interval
styling, and separate line/specimen counters. These are presentation
observations, not hidden safety rules or native-authorship answers. They
must not be copied into the native authoring prompt.

## Native capabilities, gaps, and handoff

Future native work needs actual file reading/writing, reasoning and allowed
execution, real media observation, and independent output-plugin execution.
None is newly observed or established by this research. Existing CTMS,
LIS/EHR, sensor, inventory, manufacturer, or public-health connections are
**unverified and not provisioned**. Connection metadata will be exactly the
shared `mock-exports-only` shape, with no endpoints, authentication, or
invented connection IDs.

As of **2026-09-14**, native creation, installation, and independent execution
are **blocked/not run**. Both approved Computer Use tools and an unlocked
accessible session must be restored with parent authorization. No alternate
browser/Playwright, private API, cookie, token, shell, or other workaround is
permitted. The older publication outcome remains **unknown**.

The future Creator allowlist is the shared contract's `HOW_TO.md`,
`workflow.json`, `connections.json`, `mock-data/demo.json`, and
`demo/baseline.webm`. Research, scenario metadata, baselines, expected files,
baseline outputs, holdouts, negatives, and validation answers stay withheld.
No source ZIP, placeholder plugin, fake native video, or local comparison
may be represented as an actual native result.

**Handoff:** These two files establish this sector's three researched
proposals only. No claim is made that the full 15-scenario catalog is
approved. No scenario construction, mock-data/golden generation, baseline
execution, media generation, native action, publication, or runtime change
has been performed. Wait for the parent's full-catalog approval before
implementing the three owned folders and pack tests.
