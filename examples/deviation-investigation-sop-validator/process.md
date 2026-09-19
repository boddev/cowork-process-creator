# Deviation investigation SOP review process

## Goal

Compare one synthetic deviation investigation with the applicable version of
an invented SOP checklist. Report whether the required evidence types are
present, calculate the sample-policy due state, and prepare a draft review
queue without changing a source record.

In simple terms:

1. The SOP/checklist supplies the rules.
2. The deviation report supplies the case.
3. Document mode transcribes labelled values and asks the user to confirm the
   exact extraction.
4. A fingerprint prevents changed extraction content from reusing the earlier
   confirmation.
5. The deterministic helper compares the case with the rules.
6. It writes a JSON packet for machines and a Markdown review for people.

## Independent synthetic fixture

The fixture was not part of the original document-mode demonstration:

- the deviation opened on `2026-02-01`;
- the invented policy allows 10 days, making `2026-02-11` the due date;
- the investigation completed on `2026-02-15`;
- both applicable evidence types are present;
- no open review task suppresses the timing reason.

The expected result is:

| Field | Expected |
|---|---|
| Status | `completed_with_exceptions` |
| Review state | `administratively-complete` |
| Due state | `completed-late` |
| Reason and draft reason | `late-completion` |
| Queue priority | `medium` |
| Exceptions | one `late-completion` exception |
| Approval or closure authorized | `false` |

`administratively-complete` means only that the supplied metadata contains the
required evidence types. It is not an approval or compliance conclusion.

## Document confirmation boundary

Every extracted field carries its value, state, source document and section.
`Open-ended` may normalize to a null `effective_to`, and `Not completed` may
normalize to a null `completed_on`; both remain `explicitly-stated`.

The user confirms one exact extraction. The converter requires a
`confirmed_sha256` over the presented extraction and refuses if a value, state,
source, section, row, or declared source changes afterward. Any correction
requires the full extraction to be presented and confirmed again.

## Provenance and corrections

This contribution began as scenario `hls-04`, then was generated and manually
exercised in Cowork using synthetic Word documents. An independent late
completion case found that an early candidate used the due-state label
`completed-late` as a reason code and omitted the exception. Version 2.1.0
corrected that distinction. A second run found an inconsistent document
normalization path that could relabel a confirmed open-ended field. Version
2.2.0 accepts the explicitly stated null only on the two nullable fields and
binds confirmation to the exact extraction fingerprint.

The final candidate includes those regression tests. The independent fixture
and complete expected outputs are checked in so future changes can be compared
without relying on conversation summaries.

The tested compatible-source ZIP and its hash-inventoried Creator report are
preserved under `archive/v2.2.0/`, matching the repository's bill-splitter
direct-download pattern. Intermediate revision ZIPs are intentionally omitted.
