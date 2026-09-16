# Bank-statement-to-ledger reconciliation review packet

## Purpose, source context, and non-action boundary

Prepare a controller review packet for **SYN-FIN Demonstration Company**, a
fictional enterprise, using supplied synthetic statement, ledger, and control
exports. A treasury analyst prepares the report; source owners resolve
exceptions; the controller reviews it. The trigger is a supplied statement
close and explicit cutoff, not a scheduler.

This is not a financial application recording, real bank reconciliation,
posting, payment, approval, or accounting/compliance opinion. Never fetch
real financial data. All identifiers, values, thresholds, mappings, and
`approved` control metadata are synthetic. Even `no-open-items` means no
open items **under the sample rules**, not real controller sign-off.

Actual primary pages fetched/read on 2026-09-14:

| Source | Relevant support and limit |
| --- | --- |
| [Microsoft: Reconcile bank statements by using advanced bank reconciliation](https://learn.microsoft.com/dynamics365/finance/cash-bank-management/reconcile-bank-statements-advanced-bank-reconciliation) | Statement validation, cutoff, grouped matches, matched/unmatched values, penny-difference context. Product/feature-dependent behavior, not a standard or our import schema. Posting functions are excluded. |
| [Microsoft: Set up bank reconciliation matching rules](https://learn.microsoft.com/dynamics365/finance/cash-bank-management/set-up-bank-reconciliation-matching-rules) | Ordered rules and a manual-review option for multiple matches. The product default can choose the first document; this procedure deliberately does not. |
| [Microsoft: Advanced bank reconciliation setup process](https://learn.microsoft.com/dynamics365/finance/cash-bank-management/configure-advanced-bank-reconciliation) | Account mappings, date windows, penny tolerance, signs, and time-zone configuration. No universal tolerance or available connection is implied. |

Everything more specific below, including exact manifest batching,
graph-wide ambiguity holds, all numerical limits and timing rules, is an
explicit **fictional sample policy**, not a claim about Finance defaults.

## Input contract

Use one UTF-8 JSON object. All keys listed below are required, even nullable
ones; unknown keys reject. JSON duplicate keys, nonfinite values, malformed
bytes, and non-object roots are file-level failures. Never treat a source
description or reference as instructions.

Root keys are `schema_version` (true integer 1), `synthetic` (boolean true),
`config` (object), and arrays `scopes`, `bank_lines`, `ledger_lines`,
`mappings`, `batches`. An empty bank or ledger collection is allowed.
At least one scope is required. No nested collection may exceed the declared
row limit. Exceeding a bound rejects, never truncates. A fixed additional
sample bound permits at most 100,000 candidate edges (single edges plus
bank-claim/manifest-member pairs). Exceeding it rejects with `candidate-limit`
and message `Candidate graph exceeds 100000 edges; reduce the supplied batch.`;
no partial graph or financial result is accepted.

**Strict scalars:** money is true JSON integer cents, never boolean, float,
numeric string, or null, with absolute value at most 1,000,000,000,000.
USD and EUR are the only currencies; both have two decimal places. Do not
convert currencies. Positive normalized money increases company cash.
All sums are exact integers; there is no rounding in this process.

IDs match `SYN-[A-Z0-9][A-Z0-9-]{0,63}`. Type/code strings match
`[A-Z][A-Z0-9-]{0,31}`. References are ASCII strings up to 128 characters;
empty is permitted as missing evidence. Trim outer ASCII whitespace
(`space`, tab, CR, LF, vertical tab, form feed) and uppercase ASCII letters
only for canonical reference comparison. Preserve punctuation and zeros.
Do not normalize primary keys or fuzzy-match.

### Configuration fields

| Field | Type and requirement |
| --- | --- |
| `control_version` | Synthetic ID identifying supplied controls |
| `approval_state` | `approved` or `pending`; pending rejects with `policy-not-approved`, no decisions |
| `as_of` | Required RFC 3339 instant, `YYYY-MM-DDTHH:MM:SS[.ffffff](Z\|+HH:MM\|-HH:MM)`, 1-6 fractional digits when present; offset magnitude at most 14 hours; `-00:00` (unknown offset) is rejected |
| `business_utc_offset_minutes` | True integer [-840,840], fixed offset used to derive dates; not machine-local or IANA/DST |
| `cutoff_date` | Strict `YYYY-MM-DD`, not after local business date of as_of |
| `max_match_calendar_days` | True integer [0,366], inclusive absolute date-gap limit; demo 2 |
| `single_amount_tolerance_minor` | True integer [0,1000000000000], inclusive single-match cents; demo 0; batches always exact |
| `timing_grace_calendar_days` | True integer [0,366], allowed post-cutoff expected-clearing distance; demo 2 |
| `stale_after_calendar_days` | True integer [0,366], stale only when age is strictly greater; demo 5 |
| `max_rows_per_source` | True integer [1,5000], demo 5000; applies to every root source array and each manifest's members |

Date-only values use strict Gregorian `YYYY-MM-DD`. Timestamp offsets are
explicit; seconds must be 00-59, so leap seconds are unsupported. No holiday
or daylight-saving calendar is inferred. A different real calendar requires
verified data and a separately approved scope, not an installer.

### Source row fields and keys

| Array | Exact row fields |
| --- | --- |
| `scopes` | `scope_id`, `legal_entity_id`, `account_id`, `statement_id` (IDs); `currency` (USD/EUR); `from_date`, `through_date`, `prior_statement_through_date` (dates); `bank_opening_minor`, `bank_closing_minor`, `prior_bank_closing_minor`, `ledger_opening_minor`, `ledger_closing_minor` (signed cents); `bank_sign`, `ledger_sign` (true integers +1 or -1) |
| `bank_lines` | `bank_line_id`, `scope_id` (IDs); `booked_at` (timestamp); `amount_minor` (signed source cents); `bank_code` (code); `reference` (ASCII); `batch_id` (ID or null) |
| `ledger_lines` | `ledger_line_id`, `scope_id` (IDs); `posted_at` (timestamp); `amount_minor` (signed source cents); `ledger_type` (code); `reference` (ASCII); `expected_bank_date` (date or null) |
| `mappings` | `scope_id` (ID), `bank_code`, `ledger_type` (codes) |
| `batches` | `scope_id`, `batch_id` (IDs), `member_ledger_ids` (nonempty array of ledger IDs) |

`scope_id`, each bank ID, and each ledger ID must be unique in their source
arrays. A natural statement key `(legal_entity_id, account_id, statement_id)`
is also unique. Mapping key is `(scope_id, bank_code)`; batch key is
`(scope_id, batch_id)`. Duplicate technical keys reject even identical rows.
An account has one currency, non-overlapping statement periods, and each
scope's `through_date` equals global cutoff. `from_date <= through_date`;
prior through-date is exactly the day before from-date. Bank opening equals
previous bank closing after normalization.

Every row scope and manifest member must exist. Every manifest member belongs
to that scope and is unique, including across manifests. Missing referenced
ledger IDs or scope conflicts are contradictory evidence. In contrast, a
bank's batch label with no supplied manifest is a business `batch-incomplete`
hold, not an invented group.

Normalize **all** source opening/closing/previous-close values and their
lines using the appropriate `bank_sign`/`ledger_sign`. A -1 sign declares that
the whole source uses the opposite orientation. Do not reverse just lines.
Bank rows must be inside the scope's dates and no later than as_of; violations
contradict the claimed complete statement. Ledger extras after as_of are
excluded as `after-as-of`; otherwise out-of-period extras are excluded as
`outside-period`. Record each excluded row and its normalized value/date.
They never enter the ledger checksum. Opening plus included lines must equal
closing on **each** side before any trusted matching output.

## Ordered procedure and decisions

1. **Intake:** load supplied exports and control identity/counts.
2. **Validate:** apply strict shapes/scalars, keys, reference integrity,
   account/period/previous-close checks, and both closing checksums.
3. **Normalize:** align whole-source signs and local dates and expose ledger
   cutoff exclusions. Do not mask a header discrepancy as a correction.
4. **Join:** reserve every manifest member first. Build exact manifest joins
   and complete single-candidate sets without consuming candidates greedily.
5. **Decide:** select eligible isolated single pairs and valid complete
   batch groups; preserve all ambiguous candidates.
6. **Exceptions:** assign every unmatched bank/ledger row a reason and route
   it for human review; proposed penny differences remain pending.
7. **Bridge:** compute the signed per-scope reconciliation identity.
8. **Output:** emit full immutable row dispositions, groups, exclusions,
   summaries and pending controller review. Stop; never update a ledger.

### Batch precedence

For a manifest, reserve **all** its ledger IDs even if some are excluded at
cutoff, no bank claims it, or it later fails. These cannot fall back to singles.
A bank line with `batch_id` cannot fall back either. One bank claim, all
members included, mapped bank type equal to every member's type, every member
within the date window, and exact signed sum are required. References of
individual batch members need not equal the bank reference.

Two or more bank claims for one supplied manifest make all claims and
included members `ambiguous`, regardless of sums. No claims or unavailable
members produce `batch-incomplete`; invalid amount/type/date produces
`batch-mismatch`; both use disposition `batch-held`. A missing manifest
holds that bank line as `batch-incomplete`. These are manual cases; no subset
search is allowed.

### Singles and whole-component ambiguity

Only unreserved ledger rows and bank rows without a batch label enter the
single graph. An edge requires same scope, same nonempty canonical reference,
known compatible transaction type, absolute local-calendar-date gap at most
the configured limit, and absolute signed-amount delta within tolerance.
No description, amount-only, nearest-date, or cross-account fallback.

A single pair is accepted only when the bank has exactly one eligible ledger
candidate **and** that ledger has exactly that one bank candidate. Every
other vertex with edges stays `ambiguous`. Equivalently only isolated
two-vertex components are accepted; the rest of a connected component cannot
be peeled off by input-order or iterative matching.

Zero delta is `candidate-match`. Nonzero tolerated delta is
`candidate-with-correction` on both rows and creates one group whose
`delta_minor = bank_minor - ledger_minor`. Emit a `pending-correction` reason
on each side; this duplicated review reference is **one** correction amount
in the group's bridge, not two corrections. No actual adjustment is posted.

### Unmatched precedence and messages

For an unreserved unmatched row without graph edges, find same-scope
unreserved opposite-side rows with the same nonempty reference, using the
full original candidate universe, not just remaining unmatched rows.
Bank reasons have precedence: unmapped code, missing reference, no counterpart,
type mismatch, date mismatch, amount mismatch. A no-counterpart bank row
mapped to `FEE` uses `bank-only-fee` instead. A ledger with a declared expected
bank date strictly after cutoff and no more than the grace limit becomes
`pending-clearance` **before** mismatch classification. Other unmatched
ledger rows use missing reference/no counterpart/type/date/amount order,
with `stale-ledger` added when `cutoff - local_date` exceeds its threshold.
Timing never changes ambiguity/batch holds; those stay the dominant reason.
All `reason_codes` are lexically sorted.

| Code | Exact business exception message |
| --- | --- |
| `ambiguous-match` | Multiple eligible candidates require manual matching. |
| `batch-incomplete` | Batch evidence is incomplete or unavailable at cutoff. |
| `batch-mismatch` | Batch amount, type, or date constraints are not satisfied. |
| `unmapped-code` | Bank code has no approved mapping. |
| `missing-reference` | A nonempty reference is required for single matching. |
| `no-counterpart` | No eligible same-scope reference counterpart was supplied. |
| `type-mismatch` | Reference candidates have incompatible transaction types. |
| `date-mismatch` | Reference/type candidates exceed the date window. |
| `amount-mismatch` | Reference/type candidates exceed the amount tolerance. |
| `bank-only-fee` | Bank-only fee requires a separate source-owner review. |
| `pending-clearance` | Expected clearing is after cutoff within the configured grace window. |
| `stale-ledger` | Unmatched ledger age exceeds the configured staleness window. |
| `pending-correction` | Candidate penny difference requires controller review; no posting. |
| `opening-difference` | Bank and ledger opening balances differ. |

`malformed-input` is a structural/type/range/unsupported-enum failure.
`duplicate-key` identifies repeated technical evidence; it never deduplicates.
`contradictory-evidence` covers referential, date, continuity, currency and
header contradictions. These reject the entire case with one explicit
diagnostic. `policy-not-approved` rejects pending top-level controls with
message `Synthetic control configuration is pending approval.`. Report
first failure in validation order: root/config, scopes in source order,
bank rows, ledger rows, mappings, batches, then sorted-scope integrity.
No success-shaped partial financial totals are emitted on rejection.

Malformed messages identify a dotted/indexed field and rule, e.g.
`bank_lines[0].amount_minor must be a true integer in [-1000000000000, 1000000000000].`.
Use `record_id = input`, `scope_id = null` for structural/key diagnostics.
Scope integrity diagnostics use both IDs equal to the affected `scope_id`.
Bank checksum message is `Normalized bank opening plus included lines does not equal closing.`;
ledger checksum substitutes `ledger` for `bank`. Other integrity messages
identify the violated named condition rather than attempting a correction.

### Bridge and completion

```text
closing_difference_minor = closing_bank_minor - closing_ledger_minor
opening_difference_minor = opening_bank_minor - opening_ledger_minor
bridge_minor = opening_difference_minor
             + unmatched_bank_minor - unmatched_ledger_minor
             + sum(each matched group's delta_minor once)
```

Bridge must equal closing difference exactly. Every included bank/ledger row
is in exactly one group or unmatched partition. Unmatched sums are signed;
opposite signs or cancellation do not erase individual issues. A nonzero
opening difference adds `opening-difference`; earlier-period open items are
not manufactured into current matches. Zero opening difference, no unresolved
rows, and **no nonzero correction group** yields `no-open-items`; otherwise
`review-required`, even if net deltas cancel.

Demo arithmetic: bank close 107,250 cents versus ledger 106,500; unmatched
bank 2,750 minus unmatched ledger 2,000 explains 750 cents. The ambiguous
three-row component is not solved simply to make balances agree.

## Complete result contract

The JSON object has exactly:
`schema_version: 1`, `status`, `outputs` (object), `exceptions` (array).
`status` is `completed` only with no exceptions,
`completed_with_exceptions` for a finished packet with business exceptions,
or `rejected` for the first integrity/policy failure. A business rejection
is still an explicit result, distinct from a failed file read or process.

For a rejected case `outputs` contains only
`review: {"human_review":"pending","live_action":"none"}`. For completed
packets `outputs` contains exactly `controls`, `matches`, `bank_reviews`,
`ledger_reviews`, `excluded`, `scope_summaries`, `review`:

| Output/row | Exact fields, types and semantics |
| --- | --- |
| `controls` | Exact validated `config` object, preserving supplied as_of representation and parameters. Approved is synthetic metadata only. |
| `matches[]` | `scope_id`, `bank_line_id` strings; `ledger_line_ids` sorted string array; `kind` = `single`/`batch`; `bank_minor`, `ledger_minor`, `delta_minor` signed integer cents; `max_date_gap_days` nonnegative integer; `decision` = `candidate-match`/`candidate-with-correction`. One bank row per group. |
| `bank_reviews[]` | `scope_id`, `bank_line_id`, `local_date`, `canonical_reference` strings; `amount_minor` normalized signed integer cents; `mapped_type` string or null; `candidate_ledger_ids` sorted string array; `disposition` enum below; `reason_codes` sorted string array. For batches candidate IDs are all supplied manifest members, including unavailable members; for singles only eligible graph edges. |
| `ledger_reviews[]` | `scope_id`, `ledger_line_id`, `local_date`, `canonical_reference`, `ledger_type` strings; `amount_minor` normalized cents; `expected_bank_date` date string or null; `candidate_bank_ids` sorted array; `disposition`; `reason_codes`. Reserved rows list bank claims to their manifest; single rows list eligible edges. Excluded rows have no review row. |
| `excluded[]` | `scope_id`, `record_id`, `local_date` strings; `source` = `ledger`; `amount_minor` normalized signed cents; `reason` = `after-as-of`/`outside-period`. Exclusions are visible control outcomes, not themselves business exceptions. |
| `scope_summaries[]` identity | `scope_id`, `legal_entity_id`, `account_id`, `statement_id`, `currency`, `from_date`, `through_date` strings copied from validated scope |
| `scope_summaries[]` money | `opening_bank_minor`, `opening_ledger_minor`, `closing_bank_minor`, `closing_ledger_minor`, `unmatched_bank_minor`, `unmatched_ledger_minor`, `match_delta_minor`, `opening_difference_minor`, `closing_difference_minor`, `bridge_minor`: signed integer cents, no currency netting |
| `scope_summaries[]` counts | `included_bank_count`, `included_ledger_count`, `matched_group_count`, `matched_bank_count`, `matched_ledger_count`, `unresolved_bank_count`, `unresolved_ledger_count`: nonnegative true integers; unresolved counts exclude both candidate-match types |
| `scope_summaries[]` disposition | `no-open-items` or `review-required` according to bridge/completion rules, not real approval |
| `review` | Exactly `human_review: pending`, `live_action: none` |
| `exceptions[]` | Exactly `scope_id` string/null, `record_id` string, `code` string, `message` string. One per review reason plus opening differences, or one rejection diagnostic. Codes/messages above; IDs preserve accountability. |

Review dispositions are `candidate-match`, `candidate-with-correction`,
`ambiguous`, `batch-held`, `unmatched`, or ledger-only `pending-clearance`.
Empty arrays mean none, not unknown. Nullable evidence remains null, never
an empty/zero guess.

Sort scopes by `(legal_entity_id, account_id, currency, scope_id)`.
Sort matches/bank reviews by that scope order then bank ID; ledger reviews
by scope order then ledger ID; exclusions by scope order then record ID.
Sort exception rows by scope order then record ID then code. Structural
rejections contain one null-scope diagnostic. Member/candidate/reason arrays
are lexically sorted. Source permutation cannot change business output.
Object-key order is immaterial; array order and all field values are not.

## Local demonstration and human closure

This repository's local baseline uses Python's existing standard library and
the shared CLI adapter, independently of Creator or any generated plugin.
From this scenario directory, using fresh output names:

```powershell
python -B baseline.py --input mock-data\demo.json --output baseline-output\manual-demo.json --trace baseline-output\manual-demo.trace.json
```

Existing output paths are refused. The command is a developer baseline,
not a runtime installer or native app test. The JSON result and actual trace
are separate outputs. The eight states display input counts, both close
checksums, normalized rows, candidate IDs/counts, selected groups/deltas,
unresolved reasons, signed bridge, and the final review population.
Trace tables show at most eight rows with actual `total_rows`; any subset
is explicitly labeled.

Foundation renders the supplied actual trace into `demo/baseline.webm`,
30-90 seconds, labeled **Synthetic baseline execution visualization - not
Cowork or a live system**. Until that file and its provenance exist, media
preparation is incomplete; do not fabricate a screen recording. Local
comparison success does not imply generated/installed/native success.

Source owners must resolve missing mappings, batches, timing or contradictory
exports; the controller must separately review fee booking, penny
corrections, ambiguity and opening differences. This process changes no
records and cannot record real sign-off. Updated evidence requires a new
packet, leaving the original unchanged.

## Host-only Creator and blocked native procedure

Host-native reasoning, files, media and permitted execution, plus only
existing supported verified connections, are the allowed surface. Here,
`connections.json` declares supplied synthetic exports and native output
files with no endpoint/auth or real connection. Actual bank/ledger export
access, source completeness, mapping authority, financial statement parsers
and native Finance/bank access remain unverified. No external calls, backend,
authoring API, custom MCP, Azure resources, model/media service, database,
queue, gateway, scheduler, workflow engine, browser/desktop runner, device
agent, or installer is required or allowed.

**Native creation, installation, and independent invocation NOT RUN /
BLOCKED as of 2026-09-14.** Approved Computer Use tools were removed. Both
restored approved tools and an unlocked accessible session plus parent
authorization are required. No Playwright/browser/private-API/cookie/token/
shell workaround. Old N00 was last `Publishing...`; its result is UNKNOWN,
not passed. Frozen Creator 0.2.1 and historical evidence remain unchanged.

After that gate is genuinely restored, the authorized native operator:

1. Gives Creator **only** this `HOW_TO.md`, `workflow.json`,
   `connections.json`, `mock-data/demo.json`, and the actual
   `demo/baseline.webm`. No baseline implementation, private cases, research,
   oracle artifacts, answers or local validation evidence are supplied.
2. Requests a reusable review-packet process implementing this procedure,
   without a backend, external resources, live access, or automatic action.
   Missing host capabilities are explicit blockers, not provisioned services.
3. Records real generated output and provenance; only actual native-generated
   plugins enter the parent's later root output workflow. No local mock ZIP.
4. Inspects actual installation/publication state before attempting install
   or retry, and separately records installation and independent invocation.
   A generated file or Installed view is not evidence of independent execution.
5. Supplies evaluation inputs separately to the real generated process and
   compares the complete result contract, without revealing withheld answers
   to Creator. Record observed outcomes honestly; stop on a missing capability
   or ambiguous result. Never fabricate native `passed` or financial actions.
