# Deviation investigation SOP compliance review packet

## Purpose and hard boundary

A synthetic quality coordinator supplies a bounded export of deviations,
investigations, versioned sample-SOP requirements, evidence metadata, and open
review tasks. Produce an administrative requirement review, gap register, and
**draft** follow-up queue for a qualified quality investigation reviewer.

This scenario is Veeva-style because the records resemble a quality-event
export, but it has no Veeva dependency or connection. Use only invented
`SYN-` identifiers and fictional records. Do not include real employees,
patients, products, batches, deviations, investigations, credentials, tenant
metadata, electronic signatures, or confidential SOP text.

`administratively-complete` means only that the supplied metadata contains the
invented checklist's required evidence types. It does not authenticate evidence,
assess narrative quality, establish root cause, approve an investigation, close
a deviation, disposition product, authorize regulated work, or conclude
regulatory compliance. A qualified reviewer owns every real decision.

## Research and sample-policy boundary

The FDA quality-systems guidance landing page supports quality-system and
risk-management context. FDA's OOS landing page supports preserving
investigation evidence when supplied test results fall outside established
criteria. FDA's data-integrity landing page supports reliable and accurate data
and risk-based data-integrity controls.

Those sources do not define this validator. The schemas, `SYN-` grammar,
severity ladder, checklist, evidence codes, inclusive version dates, exact joins,
30-day example due period, due-soon window, priority, task suppression, and
output ordering are explicitly invented sample policy.

## Input contract

Input is one UTF-8 JSON object no larger than 8 MiB, with unique JSON keys,
finite numbers, and nesting no deeper than 80. The top level contains exactly:

`schema_version`, `as_of_date`, `policy`, `sop_versions`, `requirements`,
`deviations`, `investigations`, `evidence`, and `open_review_tasks`.

`schema_version` is integer `1`. Dates are real Gregorian `YYYY-MM-DD` values
from 2000-01-01 through 2100-12-31. IDs are uppercase ASCII strings beginning
with `SYN-`, at most 64 characters, with single hyphen-separated alphanumeric
segments. Codes are lowercase ASCII strings matching
`[a-z][a-z0-9-]{0,39}`. Null is accepted only where stated.

`policy` has exactly:

| Field | Type |
|---|---|
| `policy_id` | ID |
| `investigation_due_days` | integer 0-3650 |
| `due_soon_days` | integer 0-365, no greater than `investigation_due_days` |
| `max_rows_per_table` | integer 1-1000 |
| `max_total_rows` | integer 1-5000 |

Every table row has exactly these fields:

| Table / primary key | Fields |
|---|---|
| `sop_versions` / `sop_version` | `sop_version`: integer 1-1000000; `effective_from`: date; `effective_to`: date or null |
| `requirements` / `requirement_id` | `requirement_id`: ID; `sop_version`: integer; `minimum_severity`: `minor`, `major`, or `critical`; `requirement_code`: code; `evidence_type`: code |
| `deviations` / `deviation_id` | `deviation_id`: ID; `opened_on`: date; `occurred_on`: date; `department_code`: code; `severity`: `minor`, `major`, or `critical`; `owner_role_id`: ID; `status`: `open`, `under-review`, or `closed` |
| `investigations` / `investigation_id` | `investigation_id`: ID; `deviation_id`: ID; `sop_version`: integer; `started_on`: date; `completed_on`: date or null |
| `evidence` / `evidence_id` | `evidence_id`: ID; `investigation_id`: ID; `evidence_type`: code; `recorded_on`: date; `source_ref`: ID |
| `open_review_tasks` / `task_id` | `task_id`: ID; `deviation_id`: ID; `reason_code`: code; `opened_on`: date |

Raw table counts are checked before duplicate collapse. Each table must not
exceed `max_rows_per_table`, and their combined count must not exceed
`max_total_rows`. Identical rows with one primary key collapse and produce a
`duplicate-record` exception. Different rows with one primary key reject the
entire packet as `contradictory-evidence`.

## Invented sample SOP

The input supplies the sample checklist so versions remain explicit. The demo
uses:

| Requirement | Minimum severity | Evidence type |
|---|---|---|
| Problem statement | minor | `problem-statement` |
| Immediate correction | minor | `immediate-correction` |
| Approval evidence | minor | `approval` |
| Root-cause analysis | major | `root-cause-analysis` |
| Impact assessment | major | `impact-assessment` |

Critical deviations inherit minor and major requirements. Requirements are
metadata checks only; an evidence row does not prove that its content is
scientifically adequate, signed, attributable, complete, or approved.

## Ordered procedure

1. **Load and validate.** Validate the exact envelope, fields, types, dates,
   row ceilings, and primary identifiers. Reject malformed packets before
   business joins.
2. **Collapse exact duplicates.** Collapse identical rows and retain an
   exception. Reject different records sharing a primary identifier.
3. **Select SOP version.** Select the one interval where
   `effective_from <= deviation.opened_on <= effective_to`; null end is open.
   No match is `missing-sop-version`. Multiple matches reject as contradictory.
4. **Join investigation.** Match by exact `deviation_id`. More than one
   investigation for one deviation rejects as contradictory. A missing
   investigation produces `missing-investigation`.
5. **Expand requirements.** Select requirements for the applicable SOP version
   whose severity rank is no greater than the deviation severity.
6. **Match evidence.** Match by exact investigation ID and evidence type.
   Evidence recorded after `as_of_date` is future evidence and cannot satisfy
   a requirement. Unknown references remain visible.
7. **Review dates.** Due date is opened date plus
   `investigation_due_days`. An unfinished record is `overdue` after the due
   date, `due-soon` when zero through `due_soon_days` remain, otherwise
   `on-track`. A completed investigation is `completed-late` when
   `completed_on` is after the due date, otherwise `completed-on-time`.
8. **Classify.** Precedence is `data-review`, `missing-investigation`,
   `sop-gap`, then `administratively-complete`. Closed source status never
   changes a missing requirement into a pass.
9. **Prepare draft queue.** High priority is missing investigation, data review,
   or overdue. Medium is a SOP gap, due soon, or late completion. Existing
   nonfuture tasks suppress only their exact `(deviation_id, reason_code)`
   from `draft_reason_codes`; no task is created or changed. Include a queue
   row only when at least one unsuppressed draft reason remains.
10. **Order and close.** Reviews sort by deviation ID. Requirement checks sort
    by requirement ID. Queue rows sort high, medium, normal and then deviation
    ID. Exceptions sort by code, subject, and message.

## Output contract

Return exactly `schema_version`, `status`, `outputs`, and `exceptions`.
Rejected input has `status: rejected`, empty `outputs`, and explicit exceptions.
Otherwise `outputs` contains:

- `as_of_date`, `policy_id`, and `packet_state: review-only`;
- `reviews`, one row per deviation with selected SOP/investigation references,
  dates, due state, review state, reason codes, and requirement checks;
- `draft_review_queue`, with rank, priority, existing tasks, unsuppressed draft
  reasons, `approval_required: true`, and `deviation_update_authorized: false`;
- `totals`, reconciling deviation, review-state, and due-state counts;
- `investigation_approval_authorized: false` and
  `deviation_closure_authorized: false`.

Status is `completed_with_exceptions` when any exception exists, otherwise
`completed`. A successful packet is still review-only.

## Local baseline and native boundary

From the repository root:

```powershell
python -B -m scenarios validate --all --full
python -B -m scenarios run --scenario hls-04 --case demo --replace-generated
```

The local standard-library baseline is a reference implementation, not a
Creator plugin or Veeva integration. Expected files are independently authored
and protected before execution. Native Creator generation, installation, and a
fresh independent Cowork run remain separate evidence gates.
