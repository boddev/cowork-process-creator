# Maintainer notes

Known gaps and housekeeping work for examples and supporting artifacts.
See [Contributing](../CONTRIBUTING.md) for new examples and
[Microsoft packaging](MICROSOFT_PACKAGING.md) for package builds.

## Complete the example bundles

The [bill splitter](../examples/bill-splitter/README.md) has source and sample
calculations, but lacks a current native ZIP and the original recording.
Add a shareable demonstration and complete the installation/new-input
walkthrough before describing it as ready to use. Preserve the older ZIP
under `archive\v1.0.1` as a versioned artifact.

The [small report example](../examples/n00) is a historical test fixture.
Some of its referenced media lives in uncommitted build directories.
Either supply accessible demonstration assets or keep it clearly labeled
as a developer fixture.

The business scenarios have local reference results and videos, but their
Cowork-generated plugins and run records are still pending. Track those
separately in [output status](../output/status.json).

## Review generated-file storage

Scenario staging duplicates the demonstration videos and procedures so
authors can select a complete input bundle. The staged videos add about
22.7 MB of duplicate data. The
[combined procedure collection](../scenarios/ALL_SCENARIOS_HOW_TO.md) also
repeats the individual guides for convenient offline reading.

Consider generated downloads or release assets if repository size becomes
a problem. Preserve the [five-file staging contract](../scenarios/SCENARIO_CONTRACT.md#native-staging-and-evidence-gates)
and hash checks when changing storage; do not remove copies that the current
workflow still needs.

## Keep historical records separate from current instructions

[Native proof](native-proof.md), [output inspection](native-output-inspection.md),
[operator continuation](operator-continuation.md), and the related status
files describe specific older runs. Some build commands and prompts in those
records predate the current package format. Use the packaging guide for new
builds, and preserve the original evidence when reorganizing historical files.

Some industry research files and validation logs also describe incomplete
work that later records show as finished. Label them as historical where
needed. Check reporting dependencies before moving research files; some are
used to classify scenarios.

## Remove machine-specific paths from public records

`scenarios\cross-industry\services-billing-draft-review\validation\unittest.json`
contains an absolute checkout path in `discovery_start`. Replace it with a
portable identifier when updating that evidence record, including any
affected hash/index records.
