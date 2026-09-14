# Restaurant bill splitter

A contributed example generated from a recorded manual restaurant-bill
splitting process, then adapted to the repository's reviewable source layout.
The runtime skill reads a new receipt, confirms diners and shares, calculates
exact per-person amounts, and uses existing native spreadsheet facilities to
create a new workbook. No business connection, sending or scheduling is involved.

For a ready-to-download package and Cowork import instructions, start with the
[quick start](README.md). End users do not need to run the development commands
below.

## Layout and runtime boundary

Like `examples/n00`, this example contains `candidate/plugin-spec.json`,
one owning skill under `candidate/skills`, a procedure, and held-out input
and expected-output fixtures. The candidate uses the current
`creator-plugin-1` schema; it does not downgrade to the older N00 schema.

| File | Purpose |
|---|---|
| `README.md` | Download link, Cowork quick start and source-build instructions |
| `bill-splitter.zip` / `bill-splitter.report.json` | Generated runtime-only preview and its source-only build report |
| `candidate/skills/split-restaurant-bill/SKILL.md` | Receipt-reading, clarification, calculation and workbook workflow |
| `candidate/skills/split-restaurant-bill/scripts/split_bill.py` | Bounded standard-library JSON-to-JSON arithmetic helper |
| `candidate/skills/split-restaurant-bill/scripts/safe_json.py` | Owned copy of the bounded JSON pattern, adapted for exact numeric parsing |
| `candidate/skills/split-restaurant-bill/references/helper-contract.md` | Inputs, outputs, amount limits and rounding rules |
| `candidate/skills/split-restaurant-bill/references/template-layout.md` | Workbook layout and formulas, including fixed printed gratuity |
| `input-new.json` / `expected-new-split.json` | Synthetic held-out data and independently specified expected result |
| `../../tests/test_bill_splitter.py` | Discoverable helper, rejection and extracted-package tests |

The original video and receipt images are creation evidence, not runtime
dependencies. The original workbook is optional: the owned layout reference
describes how to recreate it, or a user can supply a template on a future run.
None of those original attachments, the original source archive, or workbook
lock files is included in this contribution or its output package. The
downloadable `bill-splitter.zip` is newly built from this adapted candidate,
not a copy of the original archive.

An invocation requires a new receipt and 1-8 diner names. Confirm the share
assignments and tip basis before calculating; support at most 20 receipt
lines. Allocate each line by whole-number shares (0-99 per diner), not
necessarily by the printed quantity. Allocate tax and tip in proportion to
each person's items, then reconcile each component to whole cents using
largest remainders with diner-order tie breaking. Never invent unreadable
amounts, skip unclaimed lines, or overwrite an input or existing output.

The helper returns JSON only. Workbook creation requires existing native
spreadsheet capabilities and is a separate step; neither the helper nor the
repository tests attest an XLSX output. Do not install Python, packages or
external OCR/media tools in Cowork. If a native capability is missing, report
that limitation instead of pretending that the full workflow succeeded.

## Synthetic held-out example

The fixture is independent of the recorded restaurant receipts. Ana and Bo
share a 10.00 soup; all three diners share 6.00 fries; Cleo has a 30.00 steak;
Ana takes both shares of a 9.00 beer line. Their item amounts are 16.00, 7.00
and 32.00. On the 55.00 subtotal, tax is 5.00 and a 20% tip is 11.00.

After independent largest-remainder allocation of the three components,
Ana owes **20.65**, Bo **9.04**, and Cleo **41.31**. These sum to **71.00**.
`expected-new-split.json` records the entire expected result, not just the
grand total. These names and amounts are invented test data.

## Local development

Run from the repository root using the existing standard-library test runner:

```powershell
python -B -m unittest discover -s tests -p test_bill_splitter.py -v
```

To exercise the helper or export its source, use new output paths. The commands
below refuse to overwrite earlier files; choose another name on a subsequent
run.

```powershell
New-Item -ItemType Directory -Force .local\bill-splitter | Out-Null
python -B examples\bill-splitter\candidate\skills\split-restaurant-bill\scripts\split_bill.py --input examples\bill-splitter\input-new.json --output .local\bill-splitter\split.json
python -B appPackage\skills\build-output-plugin\scripts\creator_builder.py validate --source examples\bill-splitter\candidate
python -B appPackage\skills\build-output-plugin\scripts\creator_builder.py build --source examples\bill-splitter\candidate --target compatible-source --output .local\bill-splitter\bill-splitter.zip --report .local\bill-splitter\bill-splitter.report.json
```

The compatible-source export is **Draft**, not a canonical v1.28 package or
workflow-readiness attestation. The supplied archive was an output plugin,
not a creation-source checkpoint: no canonical blueprint, host profile,
coverage ledger or revision-bound evaluation record was supplied. These
source-only commands do not replace `creator_project.py check` for an
authoring project and must not be represented as a passing project check.
No authoring history or native evaluation evidence has been fabricated.

## Provenance and adaptations

Original supplied archive: `restaurant-bill-splitter-source.zip`.
SHA-256: `939527c87777887134b4986534621c88c0ce185baff37eb0148afc2e897636f9`.
The original archive and local source assets remain unchanged.
The original plugin was version 1.0.0; this adapted candidate is version 1.0.1
so it can be distinguished from that generated artifact.

The contribution adds the repository's source manifest and moves the original
standalone test cases into the root `unittest` suite rather than shipping
development tests as runtime companions. It retains the generated workflow
and owned references, with these corrections:

- Bounded exact decimal parsing and integer-cent allocation avoid hidden
  fractional cents, extreme-number tracebacks and ambient precision effects.
- All output monetary strings have exactly two decimal places, and filesystem
  errors identify the failing path rather than always blaming the input.
- Workbook guidance preserves fixed printed gratuity, labels reconciled
  amounts as snapshots, and distinguishes pre-tip totals from total paid.
- Native resource lookup, capability limits, optional-template independence,
  worksheet naming, and explicit responses before fallbacks are documented.

The contributor's generation run is provenance, not proof that this adapted
revision was installed or independently invoked. Native receipt observation,
workbook creation and invocation remain unverified for this revision. This
example is separate from the three synthetic release families; it does not
change the Creator version, release inventory or historical native status.
