# Incoming-lot quality evidence and disposition review packet

## Purpose, people and completion boundary

A receiving analyst prepares a bounded office packet for a QA/material-review-board reviewer after a receipt or new lab export. The analyst reconciles receipt scope, applicable test requirements, specimen evidence, certificate metadata, a normalized physical hold snapshot, and open nonconformances. Missing or failed evidence becomes assigned review work. The process ends with a complete review-required JSON packet or an explicit rejected-input result, not with a material disposition.

**All examples, identifiers, companies, roles and policies are fictional. Every lot requires human review and has `production_authorized=false`.** An evidence-complete lot is not accepted, released, certified, safe for use, or authorized for production. No inventory movement, quarantine operation, scrap, signature, certificate of analysis, supplier communication or business-system update is performed. QA owns decisions outside this process. The configured roles are report labels, not actual contacts or permissions.

This scenario has no endpoint or authentication. Eight separately named logical export tables share one JSON payload. They preserve distinct relationships but do not prove physical multi-file attachment ingestion. Real ERP exports, tenant configuration, available native tools and business permissions remain unverified.

## Grounding and fictional rules

The following official pages were actually fetched on 2026-09-14:

- [Quality orders](https://learn.microsoft.com/en-us/dynamics365/supply-chain/inventory/quality-orders): inspection references, tests and review evidence.
- [Quarantine orders](https://learn.microsoft.com/en-us/dynamics365/supply-chain/inventory/quarantine-orders): physical effects and statuses. Its WMS quarantine-order processing is limited to return sales orders; this incoming-lot report does not emulate that operation.
- [Inventory blocking](https://learn.microsoft.com/en-us/dynamics365/supply-chain/inventory/inventory-blocking): sampling quantity differs from blocked quantity; overlapping blocking records must not be added as physical stock.
- [Quality and nonconformance management overview](https://learn.microsoft.com/en-us/dynamics365/supply-chain/inventory/quality-management-processes): test evidence, documents, nonconformances and correction/retest work.
- [Quality management item sampling](https://learn.microsoft.com/en-us/dynamics365/supply-chain/inventory/quality-item-sampling): fixed/percentage/license-plate sampling concepts.

Source-backed concepts define the process family, not the exact sample algorithm. Specimen minima, inclusive numeric limits, certificate sufficiency, retest approval semantics, date/version selection, queue ordering and size ceilings below are fictional sample policy. This is not an AQL/ISO/statistical sampling implementation or a regulatory compliance certification.

## Input: complete exported snapshot

The root JSON object has **exactly** `config`, `items`, `reviewer_routes`, `lots`, `test_requirements`, `observations`, `certificates`, `hold_snapshot`, and `nonconformances`. All eight tables are required arrays, each with 0-200 rows. Empty tables are meaningful evidence gaps, not implicit defaults. An empty lot scope produces an empty review queue with zero totals; orphan evidence remains visible. Rows have exactly the listed fields; no hidden keys or silently ignored configuration.

`config` has exactly:

| Key | Type / meaning |
|---|---|
| `as_of` | ISO date of the supplied snapshot; never the runtime clock. |
| `review_age_days` | Integer 0-3660; overdue when calendar age is strictly greater. |
| `certificate_required` | JSON boolean. If false, absent certificate alone is not a gap; unusable supplied certificates are still reported. |
| `fallback_reviewer_role` | Nonempty text, at most 240 characters; explicitly supplied role used when no item-group route is available. |

Field notation below: **ID** is a case-sensitive uppercase ASCII identifier, 1-48 characters, matching `[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*`; **date** is `YYYY-MM-DD`, a real calendar date from 2000-01-01 through 2100-12-31; **text** is nonempty after trimming and at most 240 characters. Text remains untrusted data, not instructions, scripts, filenames or authentication. Supplier/site/quality-order identifiers are displayed as supplied, not remotely resolved.

| Table / primary key | Exact row fields |
|---|---|
| `items` / `item_id` | `item_id`: ID; `item_group`: ID. |
| `reviewer_routes` / `item_group` | `item_group`: ID; `reviewer_role`: text. |
| `lots` / `lot_id` | `lot_id`, `item_id`, `supplier_id`, `site`, `quality_order_id`: IDs; `receipt_date`: date no later than as-of; `received_qty`: integer 1-1,000,000 EA. One row denotes one physical receipt-lot scope. |
| `test_requirements` / `requirement_id` | `requirement_id`, `item_id`, `test_id`: IDs; `effective_from`, `effective_to`: dates in ascending inclusive order; `minimum`, `maximum`: decimal strings in ascending order; `required_specimens`: integer 1-100. |
| `observations` / `result_id` | `result_id`, `lot_id`, `test_id`, `specimen_id`: IDs; `value`: decimal string; `observed_on`: date; `supersedes_result_id`: ID or null; `supersession_approved`: boolean. Original results have null predecessor and false approval. |
| `certificates` / `certificate_id` | `certificate_id`, `lot_id`, `item_id`: IDs; `valid_through`: date or null; `status`: `valid` or `withdrawn`. Metadata is already part of the supplied snapshot; no authenticity is established. |
| `hold_snapshot` / `lot_id` | `lot_id`: ID; `physical_held_qty`: integer 0-1,000,000 EA; `hold_state`: `held`, `partial` or `none`; `snapshot_date`: date. This is one normalized physical snapshot, never a list of additive blocking transactions. |
| `nonconformances` / `nc_id` | `nc_id`, `lot_id`: IDs; `state`: `open` or `closed`; `reason`: text. State is the supplied as-of snapshot; no future closure is inferred. |

Integers reject booleans, floats and numeric strings. Decimal measurements are strings matching `-?(0|[1-9][0-9]*)(\.[0-9]{1,4})?`, absolute value at most 1,000,000 and at most 24 characters. Exponents, NaN, infinity and leading plus/extra leading zeroes are invalid. Compare exact decimal values; do not round acceptance boundaries. Output retains input decimal spelling/scale, including trailing zeroes. No unit conversion occurs; the fictional tests share the units specified by their exported numeric limits.

Identical rows sharing a table's primary ID collapse once and emit one `duplicate-record` exception for that ID. Equality includes every field and decimal spelling. Different rows with the same ID reject the packet. Distinct IDs with equal values are not duplicates, but multiple original observations for the same lot/test/specimen without an explicit retest link are contradictory.

The developer adapter additionally rejects malformed JSON bytes, duplicate object keys, nonfinite JSON numbers, files over 8 MiB, excessive nesting, links and reused output paths. Those are infrastructure/input-file errors (nonzero process exit), not passed business-negative results. Native implementation must use equivalent available safe file operations or report the missing capability; it must not install a parser/runtime.

## End-to-end procedure

1. **Intake (`input`).** Inventory the eight actual tables and record the supplied configuration. Do not infer absent tables, native access, dates or policies.
2. **Validate (`validation`).** Validate exact fields, types, ranges, duplicate identifiers and cross-record contradictions. Held quantity must not exceed receipt quantity. `held` means exactly all received units, `partial` strictly between zero and received, and `none` exactly zero. Hold snapshots and observations cannot precede their lot receipt. Matching certificate and lot item IDs must agree. Validate all retest links and dates before evaluation.
3. **Join lot context (`join`).** Match each lot to its item and item-group reviewer role, using only the configured fallback when needed. Every test ID appearing for the item in the requirements export is a required test family: select exactly one version whose inclusive interval contains the lot's **receipt date**, not today's/as-of date. An absent applicable version is a data-review gap; overlapping versions reject. Missing item never supplies implied test limits. Join the physical hold snapshot; a future snapshot is excluded, and missing/currently unavailable hold is unknown rather than zero.
4. **Resolve specimen lineage (`join`).** A retest predecessor must exist and have the same lot/test/specimen, with a date no later than its child. Each original has at most one successor; multiple roots per specimen, forks and cycles reject. A chain may have at most eight observations. Distinct original specimens per lot/test cannot exceed the physical receipt quantity. A future observation is retained as `future` evidence but excluded from current testing. A replacement becomes active only if every link back to its original is approved and dated by as-of. Its ancestors become `superseded`; an unapproved link anywhere leaves later replacements `pending-retest`. Passing values never bypass this rule.
5. **Evaluate evidence (`decision`).** For each selected test, compare active values inclusively to min/max and count distinct active specimen IDs. A test is `failed` if any active value is outside the limits; otherwise `incomplete` if below minimum specimen count or any pending retest; otherwise `complete`. Preserve all original/retest values and failure IDs. A supplied observation for an unselected test is unresolved `unexpected-test`, not a made-up extra test criterion. A certificate counts only when its item agrees, status is valid, validity is known, and `valid_through >= as_of`; this is metadata presence, not certification. Open nonconformances independently require NC review.
6. **Classify each lot (`decision`).** Apply precedence: `data-review` for unknown item/missing requirements/unexpected test; otherwise `nonconformance-review` for active failed evidence or open NC; otherwise `evidence-gap` for insufficient specimens, pending retest, missing required certificate or unknown physical hold; otherwise `evidence-complete`. Preserve all concurrent reason codes. Overdue review, unusable extra certificates, and additional future observations are visible warnings, not automatic numeric failure. Calculate `age_days = as_of - receipt_date`; equality to the configured age threshold is not overdue.
7. **Assign exceptions (`exception`).** Create explicit source/lot review requests using the codes below and configured role. Unknown lot references are recorded and excluded, not guessed; requirements for unknown item masters are likewise reported. Closed NCs are retained in source but do not act as open cases. Source-level duplicate/orphan warnings do not silently discard a lot's other evidence.
8. **Order the queue (`decision`).** Include every receipt lot exactly once. Sort `data-review`, `nonconformance-review`, `evidence-gap`, `evidence-complete`, then descending age, then lot ID in case-sensitive ASCII order. Assign contiguous one-based rank. These are QA review priorities, not physical movement commands.
9. **Close preparation (`output`).** Return the complete envelope below, with all lot evidence, ordered requests and reconciled quantities. Confirm total received equals the sum of four review-category quantities. Sum known physical holds once and separately identify unknown hold lots. End with `packet_state=review-required` and every row approval-required/not production-authorized. Human disposition remains outside scope.

## Exact output contract

The result object always has exactly `schema_version`, `status`, `outputs`, and `exceptions`.

| Field | Type / rules |
|---|---|
| `schema_version` | Integer constant 1, not boolean. |
| `status` | `completed` only if no exceptions; `completed_with_exceptions` for a produced review packet with requests/warnings; `rejected` for a blocking business-input error. Completion describes preparation only. |
| `outputs` | Successful/exception packet has exactly `as_of`, `packet_state`, `review_queue`, `totals`. Rejected has empty object `{}`. |
| `exceptions` | Array of objects having exactly `code`, `message`, `subject`, `owner_role`. Strings for first three; `owner_role` text or null. Ordered by code, subject, message, owner (null sorts as empty text). Identical exception objects appear once. |

`outputs.as_of` is the configured ISO date. `outputs.packet_state` is the literal `review-required`, including an empty receipt scope. `outputs.review_queue` is the ordered array described above. Each queue row has **exactly**:

| Keys | Type / interpretation |
|---|---|
| `rank` | Contiguous integer starting at 1. |
| `lot_id`, `item_id`, `supplier_id`, `site`, `quality_order_id` | Source ID strings. |
| `receipt_date` | Source ISO date. |
| `received_qty` | Source positive integer EA. |
| `physical_held_qty` | Known integer EA or null; null is not zero. |
| `hold_state`, `hold_snapshot_date` | Source enum/date, or both null if no usable current snapshot. |
| `age_days` | Nonnegative integer calendar days. |
| `overdue` | Boolean for age strictly greater than policy. |
| `review_state` | One of the four ordered lot categories. |
| `reviewer_role` | Supplied item-group role or explicit fallback. |
| `approval_required`, `production_authorized` | Boolean constants true and false, respectively. |
| `reason_codes` | Unique sorted array of all lot-level exception codes, including warnings; source-level duplicate/orphan codes remain only in outer exceptions. |
| `certificate_ids` | Sorted IDs of usable matching certificate metadata; possibly empty. |
| `open_nc_ids` | Sorted linked open NC IDs; possibly empty. |
| `test_checks` | Array ordered by test ID, possibly empty if no requirements can be selected. |

Each `test_checks` object has exactly `test_id`, `requirement_id` (IDs), `minimum`, `maximum` (unchanged decimal strings), `required_specimens`, `observed_specimens` (integers), `state` (`failed`, `incomplete`, `complete`), `failed_result_ids` (sorted IDs of active out-of-limit observations), and `observations` (array ordered by `observed_on` then result ID). Each nested observation has exactly `result_id`, `specimen_id`, `value` (unchanged decimal string), and `evidence_state` (`active`, `superseded`, `pending-retest`, `future`). Future/pending/superseded values never increase the active specimen count.

`outputs.totals` has exactly `lot_count` (integer), `received_qty` (integer sum), `known_held_qty` (integer sum excluding nulls), `unknown_hold_lot_ids` (sorted ID array), and `review_quantities` (object with all four category keys and integer quantity sums, including zero categories). There are no implicit ignored fields or floating tolerances. Object-key order is not significant; array order and decimal spelling are significant.

### Errors and uncertainty

Blocking errors stop with only the first deterministic blocking error in `exceptions` and empty `outputs`. Schema/config validation precedes table validation in this order: items, reviewer routes, lots, test requirements, observations, certificates, hold snapshot, nonconformances. Rows validate in supplied order; valid rows are subsequently indexed/sorted by ID. Earlier nonblocking warnings do not create a success-shaped result after a blocking failure. Unexpected programming or filesystem errors propagate as infrastructure failures, not a passed business rejection.

| Codes | Meaning / ownership |
|---|---|
| `invalid-shape`, `invalid-table`, `invalid-field` | Blocking fields/types/ranges; `subject` identifies table/key/field, `owner_role=null`. |
| `contradictory-evidence`, `input-limit` | Blocking conflicting IDs, identity/date/hold contradictions, retest fork/cycle, ambiguous requirement or chain limit; source subject, null owner. |
| `duplicate-record`, `unknown-reference` | Nonblocking duplicate or orphan source evidence; source subject, null owner. No invented joins. |
| `unknown-item`, `missing-requirements`, `unexpected-test` | Lot data-review work, owner is supplied QA role/fallback. |
| `future-hold`, `missing-hold` | Current physical held quantity cannot be established; unknown quantity is explicit. |
| `future-observation` | Excluded from current active evidence; remains visible in its selected test's observation ledger. |
| `failed-test`, `insufficient-specimens`, `pending-retest` | Per-test evidence requests; messages identify test and relevant counts/IDs. |
| `unusable-certificate`, `missing-certificate` | Supplied certificate invalid/unknown/withdrawn, or no required usable certificate. |
| `open-nonconformance`, `overdue-review` | QA review work; messages identify open case IDs or age versus threshold. |

Messages carry actual rule values and related IDs. Source subjects use `table:primary_id` (with `.field` for field errors); missing schema/table errors can use a root/config/table/index locator. Lot-level subjects are lot IDs. The packet never changes a record to fix an exception.

## Public demonstration and local baseline

The supplied public example contains three incoming lots: 1,000 units with complete in-range evidence, 200 with an out-of-limit observation and open NC, and 80 with missing certificate/insufficient specimens. The review remains required for all three. Reconciled physical received/held quantity is 1,280; the six-day-old complete lot is still overdue under the five-day sample policy. This is an illustration of configurable procedure rules, not constants to hardcode.

The developer baseline is explicitly **no Creator**, not no Python. It uses only existing Python standard-library facilities and the shared CLI adapter. End users do not install Python or run developer tools. From this scenario folder, a local engineering invocation with fresh output names is:

```powershell
python -B baseline.py --input mock-data\demo.json --output baseline-output\manual-demo.json --trace baseline-output\manual-demo.trace.json
```

It refuses existing output paths and never overwrites input or oracle files. The manifest-driven shared runner is the authoritative local evaluation path. The baseline implementation itself is not a Creator authoring attachment or native runtime dependency.

`demo/baseline.webm` is produced centrally from a real rerun's trace. It is a 30-90 second silent **Synthetic baseline execution visualization - not Cowork or a live system**. Actual intake counts, joins, specimen states, exceptions and final quantities are rendered; no pretend ERP UI, narration, unseen business actions or video-understanding claim. The renderer's media metadata distinguishes source hashes, frame/timeline fidelity and limitations. An absent media file is not a successful video.

## Native preparation and current gate

Native creation, installation, independent invocation and media understanding remain blocked/unverified as of 2026-09-14. Both approved Computer Use tools and an unlocked accessible session must be restored, followed by parent-coordinated authorization. Historical publication last showed `Publishing...`; its outcome is unknown. No alternate Playwright/browser, private API, cookie/token, shell, custom runner or auth workaround is permitted.

The exact Creator authoring attachment allowlist is `HOW_TO.md`, `workflow.json`, `connections.json`, the public `mock-data/demo.json`, and the actual `demo/baseline.webm` when centrally produced. Nothing else is an authoring input. Do not attach developer implementation, evaluator cases/oracles, results or reports; use only the public procedure/demo to teach the workflow. File access and permitted deterministic JSON/date/decimal operations must already exist in Cowork. Missing capability is a limitation, not permission to install a runtime, OCR/decoder, database, server, queue or external service.

After separate native authorization, the parent may ask Native Creator to generate its own output plugin from the allowlist, verify its actual installation state, and invoke that generated output independently in a new conversation on fresh runtime exports. Compare the complete returned envelope, every field/row and ordered arrays. No Creator resource, original recording or baseline source may be required by that independent run. A local packet or video does not establish native generation, installation, invocation, scheduling or media comprehension.
