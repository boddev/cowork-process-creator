"""Render a human-readable Markdown administrative review from a review packet.

Standard library only, and deliberately free of judgement: every figure is read
from the deterministic packet produced by sop_review. This module derives
nothing, re-classifies nothing and never assesses scientific adequacy.
"""
from __future__ import annotations

TITLE = "# Administrative review (review-only)"
BOUNDARY = (
    "> **Review-only.** \"Administratively complete\" means only that the supplied metadata "
    "contains the required evidence types. This review does not authenticate evidence, assess "
    "narrative quality or scientific adequacy, establish root cause, approve an investigation, "
    "close or update a deviation, disposition product, create or change a task, or make any "
    "regulatory determination. A qualified quality investigation reviewer owns every decision."
)


def escape(value: object) -> str:
    return str(value).replace("|", "\\|")


def join(values: list) -> str:
    return ", ".join(f"`{escape(item)}`" for item in values) if values else "_none_"


def table(header: list, rows: list) -> list:
    lines = ["| " + " | ".join(header) + " |",
             "|" + "|".join("---" for _ in header) + "|"]
    for row in rows:
        lines.append("| " + " | ".join(escape(cell) for cell in row) + " |")
    return lines


def render(packet: dict, source_label: str) -> str:
    lines = [TITLE, "", BOUNDARY, "",
             f"- **Source:** `{escape(source_label)}`",
             f"- **Result status:** `{escape(packet.get('status'))}`"]

    if packet.get("status") == "rejected":
        lines += ["- **Packet state:** rejected before business joins", "",
                  "## Why the packet was rejected", ""]
        lines += table(["Code", "Subject", "Message"],
                       [[row["code"], row["subject"], row["message"]] for row in packet.get("exceptions", [])])
        lines += ["", "No review rows were produced. Nothing was inferred or substituted for the "
                  "rejected values; ask the supplier for a corrected export.", ""]
        return "\n".join(lines) + "\n"

    outputs = packet.get("outputs", {})
    totals = outputs.get("totals", {})
    lines += [f"- **As-of date:** `{escape(outputs.get('as_of_date'))}`",
              f"- **Policy:** `{escape(outputs.get('policy_id'))}`",
              f"- **Packet state:** `{escape(outputs.get('packet_state'))}`", ""]

    lines += ["## Totals", ""]
    lines += table(["Measure", "Count"],
                   [["Deviations", totals.get("deviations")],
                    ["Reviews", totals.get("reviews")],
                    ["Requirement checks", totals.get("requirement_checks")],
                    ["Draft queue rows", totals.get("queue_rows")],
                    ["Exceptions", totals.get("exceptions")]])
    lines += [""]
    for label, key in (("Review states", "review_states"), ("Due states", "due_states"),
                       ("Queue priorities", "queue_priorities")):
        counts = totals.get(key, {})
        lines += [f"**{label}:** " + ", ".join(f"{name} {value}" for name, value in counts.items()), ""]

    lines += ["## Reviews", ""]
    reviews = outputs.get("reviews", [])
    if not reviews:
        lines += ["_No deviations were present in this packet._", ""]
    else:
        lines += table(["Deviation", "Severity", "Source status", "SOP version", "Investigation",
                        "Opened", "Due", "Due state", "Review state"],
                       [[row["deviation_id"], row["severity"], row["source_status"],
                         row["selected_sop_version"] if row["selected_sop_version"] is not None else "none",
                         row["investigation_id"] or "none", row["opened_on"], row["due_date"],
                         row["due_state"], row["review_state"]] for row in reviews])
        lines += [""]
        for row in reviews:
            lines += [f"### {escape(row['deviation_id'])}", "",
                      f"- Review state: `{escape(row['review_state'])}` · Due state: "
                      f"`{escape(row['due_state'])}` (due `{escape(row['due_date'])}`)",
                      f"- Reason codes: {join(row['reason_codes'])}", ""]
            if row["requirement_checks"]:
                lines += table(["Requirement", "Code", "Evidence type", "State", "Evidence IDs"],
                               [[check["requirement_id"], check["requirement_code"], check["evidence_type"],
                                 check["state"], ", ".join(check["evidence_ids"]) or "none"]
                                for check in row["requirement_checks"]])
            else:
                lines += ["_No requirement checks applied: no SOP version was selected for this deviation._"]
            lines += [""]

    lines += ["## Draft review queue", "",
              "_A proposal for qualified review. No task is created, changed, assigned or sent._", ""]
    queue = outputs.get("draft_review_queue", [])
    if not queue:
        lines += ["_No deviation carries an unsuppressed draft reason._", ""]
    else:
        lines += table(["Rank", "Deviation", "Priority", "Drafted reasons", "Suppressed reasons", "Existing tasks"],
                       [[row["rank"], row["deviation_id"], row["priority"],
                         ", ".join(row["draft_reason_codes"]) or "none",
                         ", ".join(row["suppressed_reason_codes"]) or "none",
                         ", ".join(row["existing_task_ids"]) or "none"] for row in queue])
        lines += ["", "Every queue row carries `approval_required: true` and "
                  "`deviation_update_authorized: false`.", ""]

    lines += ["## Exceptions", ""]
    exceptions = packet.get("exceptions", [])
    if not exceptions:
        lines += ["_No exceptions were raised._", ""]
    else:
        lines += table(["Code", "Subject", "Message"],
                       [[row["code"], row["subject"], row["message"]] for row in exceptions])
        lines += [""]

    lines += ["## Authorization", "",
              f"- `investigation_approval_authorized`: "
              f"`{str(outputs.get('investigation_approval_authorized')).lower()}`",
              f"- `deviation_closure_authorized`: "
              f"`{str(outputs.get('deviation_closure_authorized')).lower()}`", ""]
    return "\n".join(lines) + "\n"
