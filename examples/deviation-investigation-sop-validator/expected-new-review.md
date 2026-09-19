# Administrative review (review-only)

> **Review-only.** "Administratively complete" means only that the supplied metadata contains the required evidence types. This review does not authenticate evidence, assess narrative quality or scientific adequacy, establish root cause, approve an investigation, close or update a deviation, disposition product, create or change a task, or make any regulatory determination. A qualified quality investigation reviewer owns every decision.

- **Source:** `examples\deviation-investigation-sop-validator\input-new.json`
- **Result status:** `completed_with_exceptions`
- **As-of date:** `2026-02-20`
- **Policy:** `SYN-POLICY-DEV-03`
- **Packet state:** `review-only`

## Totals

| Measure | Count |
|---|---|
| Deviations | 1 |
| Reviews | 1 |
| Requirement checks | 2 |
| Draft queue rows | 1 |
| Exceptions | 1 |

**Review states:** administratively-complete 1, sop-gap 0, missing-investigation 0, data-review 0

**Due states:** on-track 0, due-soon 0, overdue 0, completed-on-time 0, completed-late 1

**Queue priorities:** high 0, medium 1, normal 0

## Reviews

| Deviation | Severity | Source status | SOP version | Investigation | Opened | Due | Due state | Review state |
|---|---|---|---|---|---|---|---|---|
| SYN-DEV-H2 | minor | closed | 1 | SYN-INV-H2 | 2026-02-01 | 2026-02-11 | completed-late | administratively-complete |

### SYN-DEV-H2

- Review state: `administratively-complete` · Due state: `completed-late` (due `2026-02-11`)
- Reason codes: `late-completion`

| Requirement | Code | Evidence type | State | Evidence IDs |
|---|---|---|---|---|
| SYN-REQ-APPROVAL-V1 | approval-evidence | approval | present | SYN-E-H2-APP |
| SYN-REQ-PROBLEM-V1 | problem-statement | problem-statement | present | SYN-E-H2-PRB |

## Draft review queue

_A proposal for qualified review. No task is created, changed, assigned or sent._

| Rank | Deviation | Priority | Drafted reasons | Suppressed reasons | Existing tasks |
|---|---|---|---|---|---|
| 1 | SYN-DEV-H2 | medium | late-completion | none | none |

Every queue row carries `approval_required: true` and `deviation_update_authorized: false`.

## Exceptions

| Code | Subject | Message |
|---|---|---|
| late-completion | SYN-DEV-H2 | Investigation SYN-INV-H2 completed 2026-02-15, after the due date 2026-02-11. |

## Authorization

- `investigation_approval_authorized`: `false`
- `deviation_closure_authorized`: `false`

