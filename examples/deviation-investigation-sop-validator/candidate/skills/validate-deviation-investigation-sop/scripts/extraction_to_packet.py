"""Convert a CONFIRMED normalized document extraction into the canonical packet.

Standard library only. This converter is deliberately unforgiving: it copies
explicitly-stated values and refuses everything else. It never infers a value
from narrative text, never fills a gap with a plausible default, and never runs
when the extraction has not been confirmed by the user.

Every leaf value in the extraction is a field object:

    {"value": <scalar or null>,
     "state": "explicitly-stated" | "explicitly-missing" | "unreadable"
              | "ambiguous" | "conflicting",
     "source": "<document id>",
     "section": "<section or table reference>"}

Only `explicitly-stated` (non-null value) and `explicitly-missing` (null value,
and only where the canonical model permits null) convert. `unreadable`,
`ambiguous` and `conflicting` always stop the run and are reported with their
document and section so a person can resolve them against the source.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

import sop_review
from sop_review import InputError, load_json, require, write_new_text

FIELD_KEYS = {"value", "state", "source", "section"}
CONVERTIBLE = {"explicitly-stated", "explicitly-missing"}
UNRESOLVED = {"unreadable", "ambiguous", "conflicting"}
NULLABLE = {"sop_versions.effective_to", "investigations.completed_on"}
ENVELOPE = ("as_of_date", "policy", "sop_versions", "requirements", "deviations",
            "investigations", "evidence", "open_review_tasks")
CONFIRMATION_KEYS = ("confirmed", "confirmed_by", "confirmed_sha256")
EXTRACTION_KEYS = ({"extraction_version", "sources"} | set(CONFIRMATION_KEYS) | set(ENVELOPE))
DIGEST_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def confirmation_digest(extraction: object) -> str:
    """Fingerprint of everything a confirmation covers.

    Covers the whole extraction content -- `value`, `state`, `source` and
    `section` of every field, the declared sources and the envelope -- and
    deliberately excludes the confirmation block itself. Any change to any of
    those after confirmation changes this digest, so the confirmation no longer
    applies and the converter refuses instead of proceeding.
    """
    require(isinstance(extraction, dict),
            "The extraction must be a JSON object.", "extraction", "invalid-extraction")
    content = {key: value for key, value in extraction.items() if key not in CONFIRMATION_KEYS}
    canonical = json.dumps(content, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def field(value: object, label: str, nullable: bool = False) -> object:
    require(isinstance(value, dict) and set(value) == FIELD_KEYS,
            f"{label}: every extracted value must be an object with exactly "
            "value, state, source and section.", label, "invalid-extraction")
    state = value["state"]
    require(isinstance(state, str) and state in CONVERTIBLE | UNRESOLVED,
            f"{label}: unknown extraction state {state!r}.", label, "invalid-extraction")
    require(isinstance(value["source"], str) and value["source"].strip() != "",
            f"{label}: every extracted value needs its source document.", label, "invalid-extraction")
    require(isinstance(value["section"], str) and value["section"].strip() != "",
            f"{label}: every extracted value needs its section reference.", label, "invalid-extraction")
    if state in UNRESOLVED:
        raise InputError(
            f"{label} is {state} in {value['source']} ({value['section']}). Resolve it against the "
            "source document and re-confirm; the converter never infers or substitutes a value.",
            "unresolved-extraction", label)
    if state == "explicitly-missing":
        require(nullable, f"{label} is stated as missing, but the canonical model has no null for it. "
                          "A required value cannot be inferred.", label, "unresolved-extraction")
        require(value["value"] is None, f"{label}: an explicitly-missing field must carry a null value.",
                label, "invalid-extraction")
        return None
    if value["value"] is None:
        # A stated value whose allowed form-normalization is null -- "Open-ended"
        # for effective_to, "Not completed" for completed_on -- stays
        # explicitly-stated. It was stated, so it is not missing. Everywhere the
        # canonical model forbids null, this is still a hard refusal.
        require(nullable, f"{label}: an explicitly-stated field must carry a value.",
                label, "invalid-extraction")
        return None
    return value["value"]


def row(raw: object, table: str, index: int, columns: tuple) -> dict:
    label = f"{table}[{index}]"
    require(isinstance(raw, dict) and set(raw) == set(columns),
            f"{label}: expected exactly the columns {sorted(columns)}.", label, "invalid-extraction")
    return {name: field(raw[name], f"{label}.{name}", nullable=f"{table}.{name}" in NULLABLE)
            for name in columns}


def convert(extraction: object) -> dict:
    require(isinstance(extraction, dict) and set(extraction) == EXTRACTION_KEYS,
            f"The extraction must contain exactly {sorted(EXTRACTION_KEYS)}.",
            "extraction", "invalid-extraction")
    require(extraction["extraction_version"] == 1 and type(extraction["extraction_version"]) is int,
            "extraction_version must be integer 1.", "extraction_version", "invalid-extraction")
    require(extraction["confirmed"] is True and extraction["confirmed_by"] == "user",
            "The deterministic review runs only after the user confirms the normalized extraction. "
            "Set confirmed true and confirmed_by 'user' once, and only once, the user has confirmed it.",
            "confirmed", "unconfirmed-extraction")
    digest = extraction["confirmed_sha256"]
    require(isinstance(digest, str) and DIGEST_PATTERN.match(digest) is not None,
            "confirmed_sha256 must be the lowercase 64-character digest of the extraction the user "
            "actually confirmed.", "confirmed_sha256", "invalid-extraction")
    actual = confirmation_digest(extraction)
    require(actual == digest,
            "The extraction changed after it was confirmed: its content digest is now "
            f"{actual}, but the recorded confirmation covers {digest}. A value, state, source or "
            "section was altered, so the confirmation no longer applies. Re-present the complete "
            "extraction and obtain a new explicit confirmation; never relabel a confirmed field "
            "and continue.", "confirmed_sha256", "unconfirmed-extraction")
    sources = extraction["sources"]
    require(isinstance(sources, list) and sources
            and all(isinstance(item, dict) and set(item) == {"id", "name"} for item in sources),
            "sources must list the actual source documents as id/name objects.",
            "sources", "invalid-extraction")
    known = {item["id"] for item in sources}
    require(len(known) == len(sources), "sources: duplicate document id.", "sources", "invalid-extraction")

    packet = {"schema_version": 1, "as_of_date": field(extraction["as_of_date"], "as_of_date")}
    policy = extraction["policy"]
    require(isinstance(policy, dict) and set(policy) == set(sop_review.POLICY_FIELDS),
            f"policy must contain exactly {sorted(sop_review.POLICY_FIELDS)}.", "policy", "invalid-extraction")
    packet["policy"] = {name: field(policy[name], f"policy.{name}") for name in sop_review.POLICY_FIELDS}
    for table, _key, columns in sop_review.TABLES:
        raw = extraction[table]
        require(isinstance(raw, list), f"{table} must be an array of extracted rows.", table, "invalid-extraction")
        packet[table] = [row(item, table, index, columns) for index, item in enumerate(raw)]

    # Provenance is checked but never emitted: the canonical packet stays exactly
    # the contract the deterministic helper validates.
    for table, _key, columns in sop_review.TABLES:
        for index, item in enumerate(extraction[table]):
            for name in columns:
                require(item[name]["source"] in known,
                        f"{table}[{index}].{name}: unknown source document {item[name]['source']!r}.",
                        table, "invalid-extraction")
    return packet


def run(extraction_path: Path, output_path: Path) -> dict:
    output_path = sop_review.check_new_output(output_path, ".json")
    packet = convert(load_json(extraction_path, max_bytes=8 * 1024 * 1024, max_depth=80))
    sop_review.validate_packet(packet)      # fail before writing anything
    write_new_text(output_path, json.dumps(packet, indent=2, ensure_ascii=False) + "\n")
    return packet


def main(argv: list | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--extraction", required=True, type=Path,
                        help="Path to the confirmed normalized extraction JSON.")
    parser.add_argument("--output", type=Path,
                        help="New .json filename for the canonical packet.")
    parser.add_argument("--digest", action="store_true",
                        help="Print the content digest of the extraction and exit without "
                             "converting. Run this on the extraction as presented, show the digest "
                             "with the table, and record it as confirmed_sha256 only once the user "
                             "has confirmed that exact extraction.")
    args = parser.parse_args(argv)
    if args.digest:
        try:
            value = confirmation_digest(load_json(args.extraction, max_bytes=8 * 1024 * 1024, max_depth=80))
        except InputError as exc:
            json.dump({"status": "rejected", "code": exc.code, "subject": exc.subject,
                       "message": str(exc)}, sys.stdout, indent=2)
            sys.stdout.write("\n")
            return 2
        json.dump({"status": "digest", "confirmed_sha256": value,
                   "note": "Content digest only. Nothing is confirmed, converted or authorized."},
                  sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0
    if args.output is None:
        parser.error("--output is required unless --digest is given.")
    try:
        packet = run(args.extraction, args.output)
    except InputError as exc:
        json.dump({"status": "rejected", "code": exc.code, "subject": exc.subject, "message": str(exc)},
                  sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 2
    except OSError as exc:
        json.dump({"status": "rejected", "code": "io-error", "subject": "extraction",
                   "message": f"Could not complete the conversion: {exc.strerror}."}, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 2
    json.dump({"status": "converted", "output_path": str(args.output),
               "deviations": len(packet["deviations"]), "requirements": len(packet["requirements"]),
               "evidence": len(packet["evidence"]), "open_review_tasks": len(packet["open_review_tasks"]),
               "note": "Canonical packet only. No review has been run and nothing is authorized."},
              sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
