"""Held-out synthetic checks for sop_review. Standard library only.

Run:  python -E -s -B scripts/test_sop_review.py
Values here are invented for testing and are deliberately not copied from any
demonstration packet.
"""
from __future__ import annotations

import contextlib
import io
import json
import tempfile
from pathlib import Path

import extraction_to_packet
import sop_review

FAILURES: list = []


def invoke(input_path: Path, output_path: Path, markdown_path: Path | None = None) -> tuple[int, str]:
    """Call the bundled helper in-process and capture its printed diagnostic."""
    markdown_path = markdown_path if markdown_path is not None else output_path.with_suffix(".md")
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        code = sop_review.main(["--input", str(input_path), "--output", str(output_path),
                                "--markdown", str(markdown_path)])
    return code, stream.getvalue()


def seal(extraction: dict) -> dict:
    """Record the confirmation digest of this exact extraction content."""
    extraction["confirmed_sha256"] = extraction_to_packet.confirmation_digest(extraction)
    return extraction


def convert(extraction: dict, output_path: Path, seal_first: bool = True) -> tuple[int, str]:
    """Call the bundled document-mode converter in-process.

    `seal_first` mirrors a user confirming the extraction as it then stands.
    Pass False to prove that content altered AFTER confirmation is refused.
    """
    if seal_first and isinstance(extraction, dict):
        seal(extraction)
    stream = io.StringIO()
    source = output_path.parent / "extraction.json"
    source.write_text(json.dumps(extraction), encoding="utf-8")
    with contextlib.redirect_stdout(stream):
        code = extraction_to_packet.main(["--extraction", str(source), "--output", str(output_path)])
    return code, stream.getvalue()


def base_packet() -> dict:
    return {
        "schema_version": 1,
        "as_of_date": "2031-04-30",
        "policy": {"policy_id": "SYN-POLICY-QX-77", "investigation_due_days": 21,
                   "due_soon_days": 7, "max_rows_per_table": 20, "max_total_rows": 60},
        "sop_versions": [
            {"sop_version": 4, "effective_from": "2030-01-01", "effective_to": "2031-01-31"},
            {"sop_version": 5, "effective_from": "2031-02-01", "effective_to": None},
        ],
        "requirements": [
            {"requirement_id": "SYN-REQ-A-V5", "sop_version": 5, "minimum_severity": "minor",
             "requirement_code": "containment-note", "evidence_type": "containment"},
            {"requirement_id": "SYN-REQ-B-V5", "sop_version": 5, "minimum_severity": "major",
             "requirement_code": "risk-review", "evidence_type": "risk-review"},
            {"requirement_id": "SYN-REQ-C-V4", "sop_version": 4, "minimum_severity": "minor",
             "requirement_code": "legacy-note", "evidence_type": "legacy-note"},
        ],
        "deviations": [
            {"deviation_id": "SYN-DEV-ALPHA", "opened_on": "2031-03-02", "occurred_on": "2031-03-01",
             "department_code": "warehouse", "severity": "major", "owner_role_id": "SYN-ROLE-A",
             "status": "closed"},
            {"deviation_id": "SYN-DEV-BETA", "opened_on": "2031-04-26", "occurred_on": "2031-04-25",
             "department_code": "utilities", "severity": "minor", "owner_role_id": "SYN-ROLE-B",
             "status": "open"},
            {"deviation_id": "SYN-DEV-GAMMA", "opened_on": "2029-06-01", "occurred_on": "2029-05-30",
             "department_code": "metrology", "severity": "minor", "owner_role_id": "SYN-ROLE-C",
             "status": "open"},
        ],
        "investigations": [
            {"investigation_id": "SYN-INV-ALPHA", "deviation_id": "SYN-DEV-ALPHA", "sop_version": 5,
             "started_on": "2031-03-03", "completed_on": "2031-04-10"},
            {"investigation_id": "SYN-INV-BETA", "deviation_id": "SYN-DEV-BETA", "sop_version": 4,
             "started_on": "2031-04-27", "completed_on": None},
            {"investigation_id": "SYN-INV-GAMMA", "deviation_id": "SYN-DEV-GAMMA", "sop_version": 5,
             "started_on": "2029-06-02", "completed_on": None},
        ],
        "evidence": [
            {"evidence_id": "SYN-EV-A1", "investigation_id": "SYN-INV-ALPHA", "evidence_type": "containment",
             "recorded_on": "2031-03-04", "source_ref": "SYN-REF-A1"},
            {"evidence_id": "SYN-EV-A2", "investigation_id": "SYN-INV-ALPHA", "evidence_type": "risk-review",
             "recorded_on": "2031-03-05", "source_ref": "SYN-REF-A2"},
            {"evidence_id": "SYN-EV-B1", "investigation_id": "SYN-INV-BETA", "evidence_type": "containment",
             "recorded_on": "2031-05-20", "source_ref": "SYN-REF-B1"},
            {"evidence_id": "SYN-EV-X1", "investigation_id": "SYN-INV-ORPHAN", "evidence_type": "containment",
             "recorded_on": "2031-04-01", "source_ref": "SYN-REF-X1"},
        ],
        "open_review_tasks": [
            {"task_id": "SYN-TASK-B1", "deviation_id": "SYN-DEV-BETA",
             "reason_code": "missing-containment-note", "opened_on": "2031-04-28"},
        ],
    }


def run_helper(packet: object, name: str = "packet.json", preexisting: str | None = None) -> tuple[int, dict | None, str]:
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        source = root / "in.json"
        if isinstance(packet, (bytes, str)):
            source.write_bytes(packet if isinstance(packet, bytes) else packet.encode("utf-8"))
        else:
            source.write_text(json.dumps(packet), encoding="utf-8")
        target = root / name
        if preexisting is not None:
            target.write_text(preexisting, encoding="utf-8")
        status, printed = invoke(source, target)
        written = None
        if target.exists():
            content = target.read_text(encoding="utf-8")
            if preexisting is not None and content == preexisting:
                written = {"__unchanged__": True}
            else:
                written = json.loads(content)
        return status, written, printed


def check(label: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"PASS  {label}")
    else:
        print(f"FAIL  {label} {detail}")
        FAILURES.append(label)


def review_of(packet: dict, deviation_id: str) -> dict:
    return next(row for row in packet["outputs"]["reviews"] if row["deviation_id"] == deviation_id)


def codes(packet: dict) -> list:
    return [row["code"] for row in packet["exceptions"]]


# ------------------------------------------------------- case-changed-inputs
def test_changed_inputs() -> None:
    status, packet, _ = run_helper(base_packet())
    check("changed-inputs: exits 0", status == 0, f"got {status}")
    if packet is None:
        return
    alpha = review_of(packet, "SYN-DEV-ALPHA")
    check("changed-inputs: late completion", alpha["due_state"] == "completed-late", alpha["due_state"])
    check("changed-inputs: alpha complete", alpha["review_state"] == "administratively-complete", alpha["review_state"])
    check("changed-inputs: alpha due date", alpha["due_date"] == "2031-03-23", alpha["due_date"])
    check("changed-inputs: closed status is not a pass shortcut",
          all(row["state"] == "present" and row["evidence_ids"] for row in alpha["requirement_checks"]))
    check("changed-inputs: review row matches the observed baseline field set",
          sorted(alpha) == ["deviation_id", "due_date", "due_state", "investigation_id", "opened_on",
                            "owner_role_id", "reason_codes", "requirement_checks", "review_state",
                            "selected_sop_version", "severity", "source_status"], str(sorted(alpha)))
    check("changed-inputs: requirement check matches the observed baseline field set",
          sorted(alpha["requirement_checks"][0]) == ["evidence_ids", "evidence_type", "requirement_code",
                                                     "requirement_id", "state"])
    beta = review_of(packet, "SYN-DEV-BETA")
    check("changed-inputs: version mismatch raises data-review",
          beta["review_state"] == "data-review", beta["review_state"])
    check("changed-inputs: future evidence does not satisfy",
          beta["requirement_checks"][0]["state"] == "missing"
          and beta["requirement_checks"][0]["evidence_ids"] == [])
    check("changed-inputs: beta on-track", beta["due_state"] == "on-track", beta["due_state"])
    check("changed-inputs: minor severity excludes major requirement",
          [row["requirement_id"] for row in beta["requirement_checks"]] == ["SYN-REQ-A-V5"])
    gamma = review_of(packet, "SYN-DEV-GAMMA")
    check("changed-inputs: no interval contains 2029 opened date",
          gamma["selected_sop_version"] is None and gamma["review_state"] == "data-review")
    check("changed-inputs: unmatched version yields no requirement checks",
          gamma["requirement_checks"] == [])
    check("changed-inputs: exception codes",
          sorted(set(codes(packet))) == ["future-evidence", "late-completion", "missing-sop-version",
                                         "sop-version-mismatch", "unknown-reference"],
          str(sorted(set(codes(packet)))))
    check("changed-inputs: orphan evidence retained as unknown reference",
          any(row["subject"] == "SYN-EV-X1" for row in packet["exceptions"]))
    check("changed-inputs: suppression removed the matching reason only",
          "missing-containment-note" not in next(row for row in packet["outputs"]["draft_review_queue"]
                                                 if row["deviation_id"] == "SYN-DEV-BETA")["draft_reason_codes"])
    check("changed-inputs: suppressed reason is still reported on the review",
          "missing-containment-note" in beta["reason_codes"])
    ranks = [(row["rank"], row["priority"], row["deviation_id"]) for row in packet["outputs"]["draft_review_queue"]]
    check("changed-inputs: deterministic queue order",
          ranks == [(1, "high", "SYN-DEV-BETA"), (2, "high", "SYN-DEV-GAMMA"), (3, "medium", "SYN-DEV-ALPHA")], str(ranks))
    check("changed-inputs: a late completion is medium, not high",
          next(row for row in packet["outputs"]["draft_review_queue"]
               if row["deviation_id"] == "SYN-DEV-ALPHA")["draft_reason_codes"] == ["late-completion"])
    totals = packet["outputs"]["totals"]
    check("changed-inputs: totals reconcile",
          totals["deviations"] == totals["reviews"] == 3
          and sum(totals["review_states"].values()) == 3
          and sum(totals["due_states"].values()) == 3
          and totals["queue_rows"] == len(packet["outputs"]["draft_review_queue"])
          and totals["exceptions"] == len(packet["exceptions"]))
    check("changed-inputs: packet stays review-only and non-authorizing",
          packet["outputs"]["packet_state"] == "review-only"
          and packet["outputs"]["investigation_approval_authorized"] is False
          and packet["outputs"]["deviation_closure_authorized"] is False
          and all(row["approval_required"] is True and row["deviation_update_authorized"] is False
                  for row in packet["outputs"]["draft_review_queue"]))
    check("changed-inputs: envelope keys exact",
          sorted(packet) == ["exceptions", "outputs", "schema_version", "status"])


def test_missing_investigation_reasons() -> None:
    packet_input = base_packet()
    packet_input["investigations"] = [packet_input["investigations"][0]]
    packet_input["evidence"] = packet_input["evidence"][:2]
    packet_input["open_review_tasks"] = []
    status, packet, _ = run_helper(packet_input)
    beta = review_of(packet, "SYN-DEV-BETA")
    check("missing-investigation: state", beta["review_state"] == "missing-investigation", beta["review_state"])
    check("missing-investigation: per-requirement reasons are emitted",
          beta["reason_codes"] == ["missing-containment-note", "missing-investigation"],
          str(beta["reason_codes"]))
    check("missing-investigation: checks carry no evidence",
          all(row["state"] == "missing" and row["evidence_ids"] == [] for row in beta["requirement_checks"]))
    check("missing-investigation: high priority",
          next(row for row in packet["outputs"]["draft_review_queue"]
               if row["deviation_id"] == "SYN-DEV-BETA")["priority"] == "high")
    check("missing-investigation: exit code 0 with exceptions", status == 0)


def test_duplicate_collapse_and_on_track() -> None:
    packet_input = base_packet()
    packet_input["evidence"].append(dict(packet_input["evidence"][0]))
    packet_input["as_of_date"] = "2031-03-10"
    status, packet, _ = run_helper(packet_input)
    check("duplicate: collapsed with an exception",
          "duplicate-record" in codes(packet), str(codes(packet)))
    check("duplicate: counted once",
          sum(1 for row in packet["exceptions"] if row["code"] == "duplicate-record") == 1)
    beta = review_of(packet, "SYN-DEV-BETA")
    check("duplicate: unopened future deviation stays on-track",
          beta["due_state"] == "on-track", beta["due_state"])
    check("duplicate: exit 0", status == 0)


def test_boundary_due_soon() -> None:
    packet_input = base_packet()
    packet_input["open_review_tasks"] = []
    packet_input["evidence"] = []
    packet_input["deviations"] = [packet_input["deviations"][1]]
    packet_input["investigations"] = []
    packet_input["as_of_date"] = "2031-05-17"      # due 2031-05-17 -> zero days remain
    status, packet, _ = run_helper(packet_input)
    check("boundary: zero days remaining is due-soon, not overdue",
          review_of(packet, "SYN-DEV-BETA")["due_state"] == "due-soon")
    packet_input["as_of_date"] = "2031-05-18"
    status, packet, _ = run_helper(packet_input)
    check("boundary: one day past due is overdue",
          review_of(packet, "SYN-DEV-BETA")["due_state"] == "overdue")


def test_empty_tables() -> None:
    packet_input = base_packet()
    for table in ("sop_versions", "requirements", "deviations", "investigations", "evidence", "open_review_tasks"):
        packet_input[table] = []
    status, packet, _ = run_helper(packet_input)
    check("empty: completes with no reviews",
          status == 0 and packet["status"] == "completed" and packet["outputs"]["reviews"] == []
          and packet["outputs"]["totals"]["deviations"] == 0)


# --------------------------------------------------------------- rejections
def test_reject_envelope() -> None:
    packet_input = base_packet()
    del packet_input["evidence"]
    status, packet, _ = run_helper(packet_input)
    check("reject-envelope: exit 2", status == 2, f"got {status}")
    check("reject-envelope: rejected envelope",
          packet["status"] == "rejected" and packet["outputs"] == {} and len(packet["exceptions"]) == 1)
    packet_input = base_packet()
    packet_input["as_of_date"] = "2031-02-30"
    status, packet, _ = run_helper(packet_input)
    check("reject-envelope: impossible calendar date",
          status == 2 and "not a real Gregorian date" in packet["exceptions"][0]["message"])
    packet_input = base_packet()
    packet_input["as_of_date"] = "1999-12-31"
    status, packet, _ = run_helper(packet_input)
    check("reject-envelope: out-of-range date", status == 2)
    packet_input = base_packet()
    packet_input["schema_version"] = True
    status, packet, _ = run_helper(packet_input)
    check("reject-envelope: boolean is not integer 1", status == 2)
    packet_input = base_packet()
    packet_input["policy"]["due_soon_days"] = 22
    status, packet, _ = run_helper(packet_input)
    check("reject-envelope: due_soon above due days", status == 2)
    packet_input = base_packet()
    packet_input["deviations"][0]["deviation_id"] = "DEV-ALPHA"
    status, packet, _ = run_helper(packet_input)
    check("reject-envelope: identifier grammar", status == 2)
    packet_input = base_packet()
    packet_input["deviations"][0]["department_code"] = "Warehouse"
    status, packet, _ = run_helper(packet_input)
    check("reject-envelope: code grammar", status == 2)
    packet_input = base_packet()
    packet_input["deviations"][0]["extra"] = 1
    status, packet, _ = run_helper(packet_input)
    check("reject-envelope: unexpected row field", status == 2)
    status, packet, _ = run_helper('{"schema_version": 1, "schema_version": 2}')
    check("reject-envelope: duplicate JSON key", status == 2)
    status, packet, out = run_helper(b'\xff\xfe not utf8')
    check("reject-envelope: invalid UTF-8 reported without a packet file",
          status == 2 and packet is None and "UTF-8" in out)
    status, packet, out = run_helper("[" * 400 + "]" * 400)
    check("reject-envelope: deep nesting rejected as a friendly error",
          status == 2 and "nesting" in out.lower(), out[:120])


def test_reject_contradictory() -> None:
    packet_input = base_packet()
    clash = dict(packet_input["deviations"][0])
    clash["severity"] = "critical"
    packet_input["deviations"].append(clash)
    status, packet, _ = run_helper(packet_input)
    check("reject-contradictory: different rows share a key",
          status == 2 and packet["exceptions"][0]["code"] == "contradictory-evidence")
    packet_input = base_packet()
    second = dict(packet_input["investigations"][0])
    second["investigation_id"] = "SYN-INV-ALPHA-2"
    packet_input["investigations"].append(second)
    status, packet, _ = run_helper(packet_input)
    check("reject-contradictory: two investigations for one deviation",
          status == 2 and packet["exceptions"][0]["code"] == "contradictory-evidence")
    packet_input = base_packet()
    packet_input["sop_versions"][1]["effective_from"] = "2030-06-01"
    packet_input["deviations"][0]["opened_on"] = "2030-08-01"
    packet_input["deviations"][0]["occurred_on"] = "2030-07-31"
    status, packet, _ = run_helper(packet_input)
    check("reject-contradictory: overlapping SOP intervals",
          status == 2 and packet["exceptions"][0]["code"] == "contradictory-evidence")


def test_row_ceiling() -> None:
    packet_input = base_packet()
    packet_input["policy"]["max_rows_per_table"] = 3
    original = packet_input["evidence"][0]
    packet_input["evidence"] = [dict(original) for _ in range(5)]
    status, packet, _ = run_helper(packet_input)
    check("row-ceiling: raw counts checked before duplicate collapse",
          status == 2 and packet["exceptions"][0]["code"] == "row-ceiling-exceeded",
          json.dumps(packet["exceptions"])[:160])
    packet_input = base_packet()
    packet_input["policy"]["max_total_rows"] = 5
    status, packet, _ = run_helper(packet_input)
    check("row-ceiling: combined ceiling", status == 2 and packet["exceptions"][0]["code"] == "row-ceiling-exceeded")


def test_refuse_overwrite() -> None:
    marker = '{"existing": "do not overwrite"}'
    status, packet, out = run_helper(base_packet(), preexisting=marker)
    check("refuse-overwrite: exit 2", status == 2, f"got {status}")
    check("refuse-overwrite: existing file untouched", packet == {"__unchanged__": True}, str(packet)[:120])
    check("refuse-overwrite: explicit diagnostic", "output-exists" in out, out[:160])


def test_missing_input_file() -> None:
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        status, printed = invoke(root / "absent.json", root / "out.json")
        check("missing-input: exit 2 and no output file",
              status == 2 and not (root / "out.json").exists() and "missing-input" in printed)


def test_output_path_guards() -> None:
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        source = root / "in.json"
        source.write_text(json.dumps(base_packet()), encoding="utf-8")
        status, printed = invoke(source, root / "packet.txt")
        check("output-guard: non-json suffix refused", status == 2 and "invalid-output-path" in printed)
        status, printed = invoke(source, root / "absent-dir" / "packet.json")
        check("output-guard: missing directory refused", status == 2 and "invalid-output-path" in printed)


def test_clean_deviation_has_no_queue_row() -> None:
    packet_input = base_packet()
    packet_input["deviations"] = [packet_input["deviations"][0]]
    packet_input["investigations"] = [packet_input["investigations"][0]]
    packet_input["investigations"][0]["completed_on"] = "2031-03-20"   # inside the 21-day window
    packet_input["evidence"] = packet_input["evidence"][:2]
    packet_input["open_review_tasks"] = []
    status, packet, _ = run_helper(packet_input)
    alpha = review_of(packet, "SYN-DEV-ALPHA")
    check("clean: administratively-complete and on time",
          alpha["review_state"] == "administratively-complete" and alpha["due_state"] == "completed-on-time")
    check("clean: no reason codes", alpha["reason_codes"] == [])
    check("clean: no queue row", packet["outputs"]["draft_review_queue"] == [])
    check("clean: status completed with no exceptions",
          status == 0 and packet["status"] == "completed" and packet["exceptions"] == [])


def test_determinism() -> None:
    first = run_helper(base_packet())[1]
    second = run_helper(base_packet())[1]
    check("determinism: identical input yields byte-identical packets",
          json.dumps(first, sort_keys=False) == json.dumps(second, sort_keys=False))



# ------------------------------------------------------- document-mode cases
REPORT, CHECKLIST = "doc-report", "doc-checklist"


def fld(value: object, source: str = CHECKLIST, section: str = "1. Document control",
        state: str = "explicitly-stated") -> dict:
    return {"value": value, "state": state, "source": source, "section": section}


def base_extraction() -> dict:
    """A held-out synthetic extraction: invented identifiers, not demonstration values."""
    ident = "1. Record identification"
    return {
        "extraction_version": 1, "confirmed": True, "confirmed_by": "user",
        "confirmed_sha256": "",     # sealed by convert() / seal() at confirmation time
        "sources": [{"id": REPORT, "name": "report.docx"}, {"id": CHECKLIST, "name": "checklist.docx"}],
        "as_of_date": fld("2033-08-31"),
        "policy": {"policy_id": fld("SYN-POLICY-DOC-ZZ"), "investigation_due_days": fld(14),
                   "due_soon_days": fld(3), "max_rows_per_table": fld(50), "max_total_rows": fld(200)},
        "sop_versions": [{"sop_version": fld(9), "effective_from": fld("2033-01-01"),
                          "effective_to": fld(None, state="explicitly-missing")}],
        "requirements": [
            {"requirement_id": fld("SYN-REQ-DOC-ONE-V9"), "sop_version": fld(9),
             "minimum_severity": fld("minor"), "requirement_code": fld("intake-note"),
             "evidence_type": fld("intake")},
            {"requirement_id": fld("SYN-REQ-DOC-TWO-V9"), "sop_version": fld(9),
             "minimum_severity": fld("major"), "requirement_code": fld("scope-review"),
             "evidence_type": fld("scope-review")},
        ],
        "deviations": [{"deviation_id": fld("SYN-DEV-DOC-ZZ", REPORT, ident),
                        "opened_on": fld("2033-08-20", REPORT, ident),
                        "occurred_on": fld("2033-08-19", REPORT, ident),
                        "department_code": fld("calibration", REPORT, ident),
                        "severity": fld("major", REPORT, ident),
                        "owner_role_id": fld("SYN-ROLE-DOC-ZZ", REPORT, ident),
                        "status": fld("under-review", REPORT, ident)}],
        "investigations": [{"investigation_id": fld("SYN-INV-DOC-ZZ", REPORT, ident),
                            "deviation_id": fld("SYN-DEV-DOC-ZZ", REPORT, ident),
                            "sop_version": fld(9, REPORT, ident),
                            "started_on": fld("2033-08-21", REPORT, ident),
                            "completed_on": fld(None, REPORT, ident, "explicitly-missing")}],
        "evidence": [{"evidence_id": fld("SYN-EV-DOC-ZZ", REPORT, "2. Intake"),
                      "investigation_id": fld("SYN-INV-DOC-ZZ", REPORT, "2. Intake"),
                      "evidence_type": fld("intake", REPORT, "2. Intake"),
                      "recorded_on": fld("2033-08-21", REPORT, "2. Intake"),
                      "source_ref": fld("SYN-REF-DOC-ZZ", REPORT, "2. Intake")}],
        "open_review_tasks": [],
    }


def test_document_mode_conversion() -> None:
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        status, printed = convert(base_extraction(), root / "canonical.json")
        check("document-mode: confirmed extraction converts", status == 0, printed[:200])
        if status != 0:
            return
        packet = json.loads((root / "canonical.json").read_text(encoding="utf-8"))
        check("document-mode: canonical envelope only, no provenance leaks",
              sorted(packet) == sorted(("schema_version", "as_of_date", "policy", "sop_versions",
                                        "requirements", "deviations", "investigations", "evidence",
                                        "open_review_tasks")))
        check("document-mode: explicitly-missing became a real null",
              packet["investigations"][0]["completed_on"] is None
              and packet["sop_versions"][0]["effective_to"] is None)
        status, _ = invoke(root / "canonical.json", root / "packet.json", root / "review.md")
        review = json.loads((root / "packet.json").read_text(encoding="utf-8"))["outputs"]["reviews"][0]
        check("document-mode: deterministic logic applies unchanged",
              status == 0 and review["review_state"] == "sop-gap"
              and review["due_state"] == "due-soon" and review["due_date"] == "2033-09-03"
              and review["reason_codes"] == ["due-soon", "missing-scope-review"],
              str(review["reason_codes"]) + " " + review["due_state"])
        check("document-mode: a Markdown review is written beside the packet",
              (root / "review.md").exists()
              and "Administrative review (review-only)" in (root / "review.md").read_text(encoding="utf-8"))


def test_document_mode_refuses_unresolved() -> None:
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        for index, state in enumerate(("unreadable", "ambiguous", "conflicting")):
            extraction = base_extraction()
            extraction["deviations"][0]["severity"] = fld("major", REPORT, "1. Record identification", state)
            status, printed = convert(extraction, root / f"out-{index}.json")
            check(f"document-mode: {state} value stops the run",
                  status == 2 and "unresolved-extraction" in printed
                  and "1. Record identification" in printed, printed[:200])
            check(f"document-mode: {state} value writes no canonical packet",
                  not (root / f"out-{index}.json").exists())


def test_document_mode_no_inference() -> None:
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        extraction = base_extraction()
        extraction["deviations"][0]["opened_on"] = fld(None, REPORT, "3. Narrative", "explicitly-missing")
        status, printed = convert(extraction, root / "out.json")
        check("document-mode: a required field stated as missing is never inferred",
              status == 2 and "unresolved-extraction" in printed
              and "cannot be inferred" in printed, printed[:200])
        extraction = base_extraction()
        extraction["deviations"][0]["severity"] = {"value": "major", "state": "explicitly-stated",
                                                   "source": "doc-elsewhere", "section": "1."}
        status, printed = convert(extraction, root / "out2.json")
        check("document-mode: a value must cite a declared source document",
              status == 2 and "unknown source document" in printed)
        extraction = base_extraction()
        del extraction["deviations"][0]["severity"]["section"]
        status, printed = convert(extraction, root / "out3.json")
        check("document-mode: every value needs value/state/source/section",
              status == 2 and "invalid-extraction" in printed)


def test_document_mode_requires_confirmation() -> None:
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        extraction = base_extraction()
        extraction["confirmed"] = False
        status, printed = convert(extraction, root / "out.json")
        check("document-mode: unconfirmed extraction never runs",
              status == 2 and "unconfirmed-extraction" in printed
              and not (root / "out.json").exists(), printed[:200])
        extraction = base_extraction()
        extraction["confirmed_by"] = "agent"
        status, printed = convert(extraction, root / "out2.json")
        check("document-mode: only a user confirmation counts",
              status == 2 and "unconfirmed-extraction" in printed)


def test_markdown_collision_leaves_no_partial_packet() -> None:
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        source = root / "in.json"
        source.write_text(json.dumps(base_packet()), encoding="utf-8")
        existing = root / "review.md"
        existing.write_text("# keep me\n", encoding="utf-8")
        status, printed = invoke(source, root / "packet.json", existing)
        check("markdown-collision: refused with no partial JSON left behind",
              status == 2 and "output-exists" in printed and not (root / "packet.json").exists()
              and existing.read_text(encoding="utf-8") == "# keep me\n", printed[:200])
        status, printed = invoke(source, root / "packet.json", root / "review.txt")
        check("markdown-collision: the Markdown path must end in .md",
              status == 2 and "invalid-output-path" in printed)


def test_markdown_reports_rejection_honestly() -> None:
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        packet_input = base_packet()
        del packet_input["evidence"]
        source = root / "in.json"
        source.write_text(json.dumps(packet_input), encoding="utf-8")
        status, _ = invoke(source, root / "packet.json", root / "review.md")
        document = (root / "review.md").read_text(encoding="utf-8")
        check("markdown: a rejected packet produces an honest rejection review",
              status == 2 and "rejected before business joins" in document
              and "No review rows were produced" in document and "## Reviews" not in document)


# ------------------------------------------ case-late-completion-distinction
def late_completion_packet() -> dict:
    """A record completed after its due date, with every applicable evidence type present.

    Invented values, chosen so the ONLY finding is the late completion itself.
    """
    return {
        "schema_version": 1,
        "as_of_date": "2026-02-28",
        "policy": {"policy_id": "SYN-POLICY-LATE-01", "investigation_due_days": 10,
                   "due_soon_days": 3, "max_rows_per_table": 10, "max_total_rows": 40},
        "sop_versions": [{"sop_version": 7, "effective_from": "2026-01-01", "effective_to": None}],
        "requirements": [
            {"requirement_id": "SYN-REQ-LATE-A", "sop_version": 7, "minimum_severity": "minor",
             "requirement_code": "intake-note", "evidence_type": "intake"},
            {"requirement_id": "SYN-REQ-LATE-B", "sop_version": 7, "minimum_severity": "major",
             "requirement_code": "closure-note", "evidence_type": "closure"},
        ],
        "deviations": [
            {"deviation_id": "SYN-DEV-LATE", "opened_on": "2026-02-01", "occurred_on": "2026-01-31",
             "department_code": "packaging", "severity": "major", "owner_role_id": "SYN-ROLE-L",
             "status": "under-review"},
        ],
        "investigations": [
            {"investigation_id": "SYN-INV-LATE", "deviation_id": "SYN-DEV-LATE", "sop_version": 7,
             "started_on": "2026-02-02", "completed_on": "2026-02-15"},
        ],
        "evidence": [
            {"evidence_id": "SYN-EV-L1", "investigation_id": "SYN-INV-LATE", "evidence_type": "intake",
             "recorded_on": "2026-02-03", "source_ref": "SYN-REF-L1"},
            {"evidence_id": "SYN-EV-L2", "investigation_id": "SYN-INV-LATE", "evidence_type": "closure",
             "recorded_on": "2026-02-14", "source_ref": "SYN-REF-L2"},
        ],
        "open_review_tasks": [],
    }


def test_late_completion_is_not_the_due_state_code() -> None:
    """`completed-late` is a due state; `late-completion` is the reason code and an exception."""
    status, packet, _ = run_helper(late_completion_packet())
    check("late-completion: exits 0", status == 0, f"got {status}")
    if packet is None:
        return
    review = review_of(packet, "SYN-DEV-LATE")
    check("late-completion: due date is opened_on plus the supplied due days",
          review["due_date"] == "2026-02-11", review["due_date"])
    check("late-completion: due state stays completed-late",
          review["due_state"] == "completed-late", review["due_state"])
    check("late-completion: all evidence present keeps the review administratively-complete",
          review["review_state"] == "administratively-complete", review["review_state"])
    check("late-completion: reason code is late-completion, never the due-state value",
          review["reason_codes"] == ["late-completion"], str(review["reason_codes"]))
    check("late-completion: the due-state value is never reused as a reason code",
          all("completed-late" not in row["reason_codes"] for row in packet["outputs"]["reviews"]))
    row = packet["outputs"]["draft_review_queue"][0]
    check("late-completion: one queue row at medium priority",
          len(packet["outputs"]["draft_review_queue"]) == 1 and row["priority"] == "medium",
          row["priority"])
    check("late-completion: draft reason codes carry late-completion only",
          row["draft_reason_codes"] == ["late-completion"], str(row["draft_reason_codes"]))
    check("late-completion: exactly one exception, coded late-completion",
          codes(packet) == ["late-completion"], str(codes(packet)))
    check("late-completion: the exception names the deviation",
          packet["exceptions"][0]["subject"] == "SYN-DEV-LATE", str(packet["exceptions"][0]))
    check("late-completion: an exception makes the run completed_with_exceptions",
          packet["status"] == "completed_with_exceptions", packet["status"])
    check("late-completion: totals count the exception",
          packet["outputs"]["totals"]["exceptions"] == 1
          and packet["outputs"]["totals"]["due_states"]["completed-late"] == 1)
    check("late-completion: still review-only and non-authorizing",
          packet["outputs"]["investigation_approval_authorized"] is False
          and packet["outputs"]["deviation_closure_authorized"] is False)


def test_late_completion_suppression_is_a_clean_break() -> None:
    """Only an exact `late-completion` task suppresses; a legacy `completed-late` task does not."""
    stale = late_completion_packet()
    stale["open_review_tasks"] = [{"task_id": "SYN-TASK-OLD", "deviation_id": "SYN-DEV-LATE",
                                   "reason_code": "completed-late", "opened_on": "2026-02-20"}]
    _, packet, _ = run_helper(stale)
    if packet is not None:
        queue = packet["outputs"]["draft_review_queue"]
        check("late-completion: a legacy completed-late task suppresses nothing",
              len(queue) == 1 and queue[0]["draft_reason_codes"] == ["late-completion"]
              and queue[0]["suppressed_reason_codes"] == [], str(queue))

    current = late_completion_packet()
    current["open_review_tasks"] = [{"task_id": "SYN-TASK-NEW", "deviation_id": "SYN-DEV-LATE",
                                     "reason_code": "late-completion", "opened_on": "2026-02-20"}]
    _, packet, _ = run_helper(current)
    if packet is not None:
        check("late-completion: an exact late-completion task suppresses the only draft reason",
              packet["outputs"]["draft_review_queue"] == [], str(packet["outputs"]["draft_review_queue"]))
        check("late-completion: the suppressed code stays on the review row",
              review_of(packet, "SYN-DEV-LATE")["reason_codes"] == ["late-completion"])
        check("late-completion: suppression does not remove the exception",
              codes(packet) == ["late-completion"], str(codes(packet)))


# -------------------------------------------- case-stated-null-normalization
def test_document_mode_stated_open_ended_is_not_missing() -> None:
    """`Open-ended` / `Not completed` normalize to null and stay explicitly-stated."""
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        extraction = base_extraction()
        extraction["sop_versions"][0]["effective_to"] = fld(
            None, CHECKLIST, "1. Document control - Effective to: Open-ended")
        extraction["investigations"][0]["completed_on"] = fld(
            None, REPORT, "1. Record identification - Not completed")
        status, printed = convert(extraction, root / "canonical.json")
        check("stated-null: explicitly-stated Open-ended converts", status == 0, printed[:300])
        if status != 0:
            return
        packet = json.loads((root / "canonical.json").read_text(encoding="utf-8"))
        check("stated-null: effective_to became a real null",
              packet["sop_versions"][0]["effective_to"] is None)
        check("stated-null: completed_on became a real null",
              packet["investigations"][0]["completed_on"] is None)
        status, _ = invoke(root / "canonical.json", root / "packet.json", root / "review.md")
        review = json.loads((root / "packet.json").read_text(encoding="utf-8"))["outputs"]["reviews"][0]
        check("stated-null: an open-ended interval still selects its SOP version",
              status == 0 and review["selected_sop_version"] == 9, str(review["selected_sop_version"]))

        # A null that the canonical model does not permit is still a hard refusal.
        bad = base_extraction()
        bad["deviations"][0]["severity"] = fld(None, REPORT, "1. Record identification")
        status, printed = convert(bad, root / "never.json")
        check("stated-null: a null is still refused where the model forbids it",
              status == 2 and "must carry a value" in printed and not (root / "never.json").exists(),
              printed[:200])


# ------------------------------------------ case-post-confirmation-mutation
def test_document_mode_refuses_post_confirmation_mutation() -> None:
    """No change of value, state, source or section may reach conversion unconfirmed."""
    mutations = {
        "value": lambda e: e["deviations"][0]["severity"].__setitem__("value", "critical"),
        "state": lambda e: e["investigations"][0]["completed_on"].__setitem__(
            "state", "explicitly-stated"),
        "source": lambda e: e["deviations"][0]["status"].__setitem__("source", CHECKLIST),
        "section": lambda e: e["deviations"][0]["opened_on"].__setitem__("section", "9. Appendix"),
        "added row": lambda e: e["open_review_tasks"].append(
            {"task_id": fld("SYN-TASK-DOC-NEW", REPORT, "7. Tasks"),
             "deviation_id": fld("SYN-DEV-DOC-ZZ", REPORT, "7. Tasks"),
             "reason_code": fld("missing-scope-review", REPORT, "7. Tasks"),
             "opened_on": fld("2033-08-30", REPORT, "7. Tasks")}),
        "declared source": lambda e: e["sources"].append({"id": "doc-extra", "name": "extra.docx"}),
    }
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        for index, (what, mutate) in enumerate(mutations.items()):
            extraction = seal(base_extraction())      # the user confirms THIS content
            mutate(extraction)                        # ... and then it is altered
            target = root / f"mutated-{index}.json"
            status, printed = convert(extraction, target, seal_first=False)
            check(f"post-confirmation: a changed {what} is refused",
                  status == 2 and "unconfirmed-extraction" in printed, printed[:240])
            check(f"post-confirmation: a changed {what} writes no canonical packet",
                  not target.exists())
            check(f"post-confirmation: the refusal says to re-present and re-confirm",
                  "new explicit confirmation" in printed and "changed after it was confirmed" in printed,
                  printed[:240])

        # The exact reported defect: a stated "Open-ended" null is confirmed, then
        # silently relabelled explicitly-missing to get past a converter refusal.
        relabelled = base_extraction()
        relabelled["sop_versions"][0]["effective_to"] = fld(
            None, CHECKLIST, "1. Document control - Effective to: Open-ended")
        seal(relabelled)
        relabelled["sop_versions"][0]["effective_to"]["state"] = "explicitly-missing"
        status, printed = convert(relabelled, root / "relabelled.json", seal_first=False)
        check("post-confirmation: silently relabelling a confirmed stated null is refused",
              status == 2 and "unconfirmed-extraction" in printed
              and not (root / "relabelled.json").exists(), printed[:240])

        # The honest route: re-present, get a new confirmation, then convert.
        reconfirmed = seal(base_extraction())
        reconfirmed["deviations"][0]["severity"]["value"] = "critical"
        seal(reconfirmed)                              # a NEW confirmation of the new content
        status, printed = convert(reconfirmed, root / "reconfirmed.json", seal_first=False)
        check("post-confirmation: a re-confirmed extraction converts", status == 0, printed[:240])

        # A malformed or absent digest is refused rather than ignored.
        for label, digest in (("absent", ""), ("not a digest", "CONFIRMED"), ("wrong length", "abc123")):
            broken = seal(base_extraction())
            broken["confirmed_sha256"] = digest
            status, printed = convert(broken, root / f"broken-{label.split()[0]}.json", seal_first=False)
            check(f"post-confirmation: {label} digest is refused", status == 2, printed[:200])


def main() -> int:
    for test in (test_changed_inputs, test_late_completion_is_not_the_due_state_code,
                 test_late_completion_suppression_is_a_clean_break, test_missing_investigation_reasons, test_duplicate_collapse_and_on_track,
                 test_boundary_due_soon, test_empty_tables, test_reject_envelope, test_reject_contradictory,
                 test_row_ceiling, test_clean_deviation_has_no_queue_row, test_refuse_overwrite,
                 test_document_mode_conversion, test_document_mode_stated_open_ended_is_not_missing,
                 test_document_mode_refuses_post_confirmation_mutation,
                 test_document_mode_refuses_unresolved,
                 test_document_mode_no_inference, test_document_mode_requires_confirmation,
                 test_markdown_collision_leaves_no_partial_packet, test_markdown_reports_rejection_honestly, test_missing_input_file, test_output_path_guards,
                 test_determinism):
        test()
    print()
    if FAILURES:
        print(f"{len(FAILURES)} check(s) failed: " + "; ".join(FAILURES))
        return 1
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
