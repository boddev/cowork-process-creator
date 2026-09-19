# Input contract, classification rules and output envelope

This reference is owned by the `validate-deviation-investigation-sop` skill and
describes the canonical packet reached by **both** input modes. Document mode
converts a confirmed extraction into exactly this contract first; see
`references/document-mode.md`.
Every rule below is invented sample policy for a synthetic scenario. None of
it is a regulatory requirement, and none of it authorizes a quality decision.

## Input envelope

One UTF-8 JSON object, at most 8 MiB, with unique object keys, finite
numbers and nesting no deeper than 80 levels. The top level contains exactly:

`schema_version`, `as_of_date`, `policy`, `sop_versions`, `requirements`,
`deviations`, `investigations`, `evidence`, `open_review_tasks`.

- `schema_version` is integer `1`. A JSON boolean is not an integer.
- Dates are real Gregorian `YYYY-MM-DD` values from `2000-01-01` through
  `2100-12-31`.
- IDs are uppercase ASCII beginning `SYN-`, at most 64 characters, in single
  hyphen-separated alphanumeric segments.
- Codes are lowercase ASCII matching `[a-z][a-z0-9-]{0,39}`.
- Null is accepted only for `sop_versions.effective_to` and
  `investigations.completed_on`.

### `policy`

Exactly `policy_id` (ID), `investigation_due_days` (integer 0-3650),
`due_soon_days` (integer 0-365, not greater than `investigation_due_days`),
`max_rows_per_table` (integer 1-1000) and `max_total_rows` (integer 1-5000).

### Tables

| Table / primary key | Fields |
|---|---|
| `sop_versions` / `sop_version` | `sop_version` integer 1-1000000; `effective_from` date; `effective_to` date or null |
| `requirements` / `requirement_id` | `requirement_id`; `sop_version`; `minimum_severity` (`minor`/`major`/`critical`); `requirement_code`; `evidence_type` |
| `deviations` / `deviation_id` | `deviation_id`; `opened_on`; `occurred_on`; `department_code`; `severity`; `owner_role_id`; `status` (`open`/`under-review`/`closed`) |
| `investigations` / `investigation_id` | `investigation_id`; `deviation_id`; `sop_version`; `started_on`; `completed_on` or null |
| `evidence` / `evidence_id` | `evidence_id`; `investigation_id`; `evidence_type`; `recorded_on`; `source_ref` |
| `open_review_tasks` / `task_id` | `task_id`; `deviation_id`; `reason_code`; `opened_on` |

Each row carries exactly its listed fields — no extras, no omissions.

## Rejection rules

The whole packet is rejected, with `status: rejected`, empty `outputs` and
one explicit exception, when:

| Code | Cause |
|---|---|
| `invalid-input` | Envelope, field, type, grammar, range or date failure. |
| `row-ceiling-exceeded` | Raw rows exceed `max_rows_per_table` or `max_total_rows`. Counted **before** duplicate collapse. |
| `contradictory-evidence` | Different rows share one primary identifier; one deviation has more than one investigation; more than one SOP interval contains one opened date. |
| `oversized-input` / `missing-input` | Input above the byte ceiling, or absent. |
| `output-exists` / `invalid-output-path` | Either output file exists, has the wrong suffix (`.json` / `.md`), or its directory is absent. Both paths are checked before either is written, so nothing partial is left behind and existing files stay byte-for-byte unchanged. |
| `unresolved-extraction` / `unconfirmed-extraction` | Document mode only: a field is unreadable, ambiguous, conflicting or a required value is stated as missing; or the extraction was not confirmed by the user, or its content no longer matches the `confirmed_sha256` the user confirmed. No canonical packet is written. |

Identical rows sharing a primary key are **not** a rejection: they collapse
into one record and raise a `duplicate-record` exception.

## Classification

**Severity ladder.** `minor` < `major` < `critical`. A requirement applies
when its `minimum_severity` rank is no greater than the deviation severity,
so a critical deviation inherits the minor and major requirements.

**Evidence matching.** Exact investigation ID and exact `evidence_type`.
Evidence with `recorded_on` after `as_of_date` raises `future-evidence` and
cannot satisfy a requirement. Among several eligible rows the earliest
`recorded_on`, then the lowest `evidence_id`, is reported.

**Due states.** `due_date = opened_on + policy.investigation_due_days`
calendar days. Unfinished: `overdue` when `as_of_date` is past the due date;
`due-soon` when zero through `due_soon_days` remain; otherwise `on-track`.
Completed: `completed-late` when `completed_on` is after the due date;
otherwise `completed-on-time`.

**Review-state precedence.** `data-review`, then `missing-investigation`,
then `sop-gap`, then `administratively-complete`.

- `data-review` is raised by a missing SOP version for the opened date, or
  an investigation whose `sop_version` differs from the selected version.
- An unknown reference — evidence naming an absent investigation, an
  investigation naming an absent deviation, a task naming an absent
  deviation — stays visible as an `unknown-reference` exception. It owns no
  review row, so it cannot change any deviation's review state.
- A `closed` source status never converts a missing requirement to a pass.

**Reason codes.** A missing requirement contributes `missing-` joined to its
`requirement_code` (so `requirement_code: approval-evidence` yields
`missing-approval-evidence`, not `missing-approval`). A deviation with no
investigation contributes `missing-investigation` **and** one
`missing-<requirement_code>` per unmet requirement. `overdue`, `due-soon`,
`late-completion`, `missing-sop-version` and `sop-version-mismatch` are
reason codes in their own right. Reason codes are sorted and deduplicated.

`completed-late` is a **due-state value only and is never a reason code**. A
completed investigation finishing after its due date carries
`due_state: completed-late` and the reason code `late-completion`, and also
raises one `late-completion` exception naming the deviation. Because `status`
is derived from the exception count, any late completion therefore reports
`completed_with_exceptions`. An existing task suppresses a late completion
only when its `reason_code` is exactly `late-completion`; a task carrying the
old `completed-late` code suppresses nothing.

**Queue.** A deviation joins `draft_review_queue` only when it has at least
one **unsuppressed** draft reason. Priority is `high` for
`missing-investigation`, `data-review` or `overdue`; `medium` for `sop-gap`,
`due-soon` or `completed-late`; otherwise `normal`. An existing task with
`opened_on` on or before `as_of_date` suppresses only its exact
`(deviation_id, reason_code)` pair; a task opened after `as_of_date` raises
`future-task` and suppresses nothing. Suppressed codes remain listed under
`suppressed_reason_codes` and on the review row.

## Output envelope

Exactly `schema_version`, `status`, `outputs`, `exceptions`.
`status` is `completed_with_exceptions` when any exception exists, otherwise
`completed`; a rejected packet is `rejected`.

`outputs` contains `as_of_date`, `policy_id`, `packet_state: review-only`,
`reviews`, `draft_review_queue`, `totals`,
`investigation_approval_authorized: false` and
`deviation_closure_authorized: false`.

- A **review** carries exactly `deviation_id`, `due_date`, `due_state`,
  `investigation_id`, `opened_on`, `owner_role_id`, `reason_codes`,
  `requirement_checks`, `review_state`, `selected_sop_version`, `severity` and
  `source_status`. Each requirement check carries exactly `evidence_ids` (an
  array, empty when nothing eligible matched), `evidence_type`,
  `requirement_code`, `requirement_id` and `state`, where `state` is `present`
  or `missing`. Checks are sorted by `requirement_id`.
- A **queue row** carries `rank`, `deviation_id`, `priority`,
  `review_state`, `due_state`, `existing_task_ids`,
  `suppressed_reason_codes`, `draft_reason_codes`,
  `approval_required: true` and `deviation_update_authorized: false`.
- **totals** reconciles `deviations`, `reviews`, `review_states`,
  `due_states`, `queue_rows`, `queue_priorities`, `requirement_checks` and
  `exceptions`.

Both modes emit these same fields, and both also write the human-readable
Markdown review derived from this packet — never from a separate judgement.

**Ordering.** Reviews by deviation ID; requirement checks by requirement ID;
queue rows by `high`, `medium`, `normal` then deviation ID; exceptions by
code, then subject, then message. Identical input produces a byte-identical
packet.
