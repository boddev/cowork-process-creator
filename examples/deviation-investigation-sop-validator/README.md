# Deviation investigation SOP validator

This synthetic, file-only example reviews one deviation investigation against
an invented versioned SOP checklist. It supports:

- **document mode:** one Word deviation report plus one Word SOP/checklist;
- **structured mode:** one canonical JSON export.

Both modes reach the same standard-library deterministic helper and write a
review-only JSON packet plus a human-readable Markdown review. The skill never
connects to Veeva or another quality system, approves an investigation, closes
or updates a deviation, creates a task, assesses scientific adequacy, or makes
a regulatory determination.

## What is included

| Path | Purpose |
|---|---|
| `candidate/` | Reviewable version 2.2.0 plugin source |
| `documents/` | Synthetic Word report and SOP/checklist for a manual run |
| `input-new.json` | Equivalent structured fixture |
| `expected-new-packet.json` | Complete deterministic JSON oracle |
| `expected-new-review.md` | Expected human-readable review |
| `archive/v2.2.0/` | Tested compatible-source ZIP and its Creator build report |
| `process.md` | Procedure, expected business result and provenance |
| `status.json` | Packaging and host-validation state |

The Word files and JSON contain invented `SYN-` identifiers only. They contain
no patient, employee, product, batch, tenant, credential, signature, or
confidential SOP data.

## Download the tested preview package

The repository follows the same direct-download pattern as the historical bill
splitter example:

**[Download deviation-investigation-sop 2.2.0](archive/v2.2.0/deviation-investigation-sop-2.2.0-source.zip?raw=1)**

This is a compatible-source **Draft preview**, not a canonical Microsoft
v1.28 package. It was accepted, enabled and manually exercised in the
contributor's Cowork environment. A user whose Cowork preview supports this
format can download the ZIP, upload it in plugin management, enable it, start
a fresh conversation, and select `validate-deviation-investigation-sop`.

## Try the document workflow

Install the tested preview package above or an approved package built from
`candidate/`, enable
`validate-deviation-investigation-sop`, start a fresh Cowork conversation, and
attach both files under `documents/`. Ask the skill to show the normalized
extraction first and wait for confirmation. After confirming the exact
extraction, request new JSON and Markdown output paths.

The example's result is administratively complete because both required
evidence types are present, but the investigation completed four days after
its invented due date. The output is therefore
`completed_with_exceptions`, with due state `completed-late` and reason code
`late-completion`.

Version 2.2.0 of the compatible-source Draft was accepted, enabled and
manually exercised in the contributor's Cowork environment with this document
pair. That is scoped host evidence, not a claim of organization-wide support
or canonical Microsoft v1.28 acceptance.

## Developer validation

From the repository root:

```powershell
python -B -m unittest scenarios.tests.test_health_deviation -v
python -B -m unittest tests.test_deviation_investigation_sop_example -v
python -B examples\deviation-investigation-sop-validator\candidate\skills\validate-deviation-investigation-sop\scripts\test_sop_review.py
python -B appPackage\skills\build-output-plugin\scripts\creator_builder.py validate --source examples\deviation-investigation-sop-validator\candidate
```

These commands validate source and deterministic behavior. They do not install
the plugin or attest Cowork host acceptance.

## Distribution boundary

The archive preserves only the final tested 2.2.0 compatible-source Draft, not
the intermediate packages. Organization-wide distribution should still use
the packaging route approved by the maintainers. Canonical Microsoft packaging
requires an approved app ID and publisher name, website, privacy, and terms
URLs; none are invented here.
