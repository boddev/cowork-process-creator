---
name: ready-items-report
description: "Create a ready-items cost report from an attached JSON inventory and an explicitly supplied reporting month. Use when asked to report ready inventory costs, total ready items, or run the ready-items report for a new month. Produces a new Markdown file using exact decimal arithmetic."
---

# Ready-items report

Request the runtime input JSON, reporting month (`YYYY-MM`) and a new output
filename if absent. Do not default to values from a previous demonstration.
Read `references/input-contract.md` for the exact fields and error behavior.

Locate this skill's bundled `scripts/report.py` in the native skill
resources. Use Cowork's existing Python 3.10+ interpreter to invoke the file
with `--input`, `--period`, and `--output`, each followed by the actual
value. The helper uses only the standard library. Do not install Python or
packages, call a service, or approximate the total in model reasoning if
the helper cannot execute.

The helper validates all rows, filters `ready` items, multiplies each
quantity by its exact decimal unit cost, and totals the whole retained
collection. It preserves order and reports included/excluded row counts.
An empty collection produces zero. Errors are explicit and existing output
files are not overwritten.

Return the actual generated Markdown file through the native file surface.
Do not send it to anyone or write to a business system. If an error occurs,
report it and request a corrected input or new output destination. Do not
substitute a stale report or assert a successful result from a filename.

This output is independent: its only runtime inputs are the new inventory,
month and output location. It does not load the Creator, original procedure,
recording, screenshot sequence, development checkout, or creation session.
Scheduling has not been exercised; invoke manually.
