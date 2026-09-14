# Enterprise scenario contract (version 1)

This is a development-only, synthetic validation corpus, not a workflow engine
or a claim that Cowork generated, installed, or ran anything. All scenario
artifacts live under `scenarios`; only actual native plugin artifacts and their
native status belong under root `output`. The Creator v0.2.1 runtime, release ZIP,
and historical proof artifacts are frozen.

## Ownership and layout

Sector owners implement their approved business procedures, independent
goldens, mock data, baseline, research, and one complete `HOW_TO.md`. The shared
foundation validates and renders their actual baseline traces centrally.

```text
scenarios/<industry>/<slug>/
  scenario.json
  HOW_TO.md
  sources.json
  workflow.json
  connections.json
  baseline.py
  mock-data/demo.json
  mock-data/holdout-a.json
  mock-data/holdout-b.json
  mock-data/negative-malformed.json
  mock-data/negative-contradictory.json
  expected/<case-id>.json
  baseline-output/<case-id>.json          # produced by the shared CLI
  baseline-output/<case-id>.trace.json    # produced by the shared CLI
  validation/                           # produced evidence and staging manifests
  demo/baseline.webm                    # centrally rendered actual baseline trace
  demo/baseline.media.json              # encoder, timeline, hashes, fidelity
```

JSON is UTF-8, finite, and has no duplicate keys. Paths in JSON are
scenario-relative POSIX-style identifiers (for portability); CLI commands use
the platform's path separators. No absolute paths, traversal, backslashes,
symlinks, junctions, or paths outside the scenario are permitted in manifests.
Use lowercase kebab-case scenario, case, step, and rule IDs.

## `scenario.json`

The following is the exact field contract; replace illustrative values, do not
copy an example as an implemented scenario.

```json
{
  "schema_version": 1,
  "id": "sector-01",
  "title": "Approved scenario title",
  "industry": "manufacturing",
  "workflow_family": "multi-source-reconciliation",
  "description": "Business goal and bounded output.",
  "owner_role": "Human reviewer role",
  "risk_level": "medium",
  "procedure": "HOW_TO.md",
  "sources": "sources.json",
  "workflow": "workflow.json",
  "connections": "connections.json",
  "baseline": "baseline.py",
  "video": "demo/baseline.webm",
  "sample_policy": {
    "synthetic_only": true,
    "no_live_actions": true,
    "description": "Invented thresholds; not production, clinical, or legal advice."
  },
  "golden_provenance": {
    "method": "independent-manual-derivation",
    "author": "Sector owner",
    "description": "How results were derived independently from the written rules."
  },
  "cases": [
    {
      "id": "demo",
      "kind": "demo",
      "input": "mock-data/demo.json",
      "expected": "expected/demo.json",
      "expected_status": "completed_with_exceptions",
      "covers": ["rule-one"],
      "failure_modes": [],
      "derivation": "Independent arithmetic and decision reasoning for this case."
    }
  ]
}
```

Require exactly one `demo`, at least two `holdout` and at least two `negative`
cases. Case IDs are unique; input and expected paths are unique, distinct,
and match `mock-data/<case-id>.json` and `expected/<case-id>.json`.
`demo` is always the demo case ID. Negative cases collectively declare
`malformed-input` and `contradictory-evidence` in `failure_modes`.
Inputs themselves remain parseable JSON objects: malformed records exercise
business validation; the shared tests separately cover malformed JSON bytes.
Every rule must be covered by at least one case. Held-out sets must contain
different data, not copies or relabelings of demo input. Explain the difference
and each case's expected decisions in `derivation`.

Supported `risk_level`: `low`, `medium`, `high`.
Supported `expected_status`: `completed`, `completed_with_exceptions`, `rejected`.
`workflow_family` describes actual mechanics, not just a renamed industry.
Corpus reporting measures both industry and family diversity.

Goldens are written from the procedure before baseline execution. Never set
`expected = baseline(input)`, copy generated baseline results into `expected`,
or import/read expected files in a baseline. Provenance is an author
declaration, not proof of independent human review. The runner fingerprints
goldens before and after execution and reports exact semantic mismatches;
it does not regenerate or "repair" goldens.

## Procedure, research, rules, and connections

`HOW_TO.md` is the complete procedure: business purpose, research links,
mock-only boundaries, all input/output fields, ordered steps and joins,
explicit sample rules and precedence, decimal/date/ordering semantics,
exceptions and human review, baseline command, video explanation, and native
Creator/install/independent-execution instructions with the current blocked
gate. Do not include private holdout values, expected files, hidden markers,
or evaluation answers in this public procedure. Demo examples are allowed.
Native instructions may not rely on the baseline implementation.

`sources.json` has `schema_version: 1` and `sources`, an array of at least two
objects with `id`, `title`, `url`, `publisher`, `accessed` (ISO date), `scope`,
`supported_claims` (nonempty string array), and `limitations`. Public source
URLs must be real research references; distinguish source-backed constraints
from invented sample policies. The local validator does not verify a web page.

`workflow.json` has `schema_version: 1`, `rules`, and `steps`.
Each rule has `id`, `description`, and `provenance` with `kind`
(`source-backed` or `sample-policy`), `source_ids` (array), and `note`.
Source-backed rules cite at least one actual ID in `sources.json`.
Each step has `id`, `kind`, `title`, `rule_ids` (array), and `procedure`.
Step kinds are `input`, `validation`, `join`, `decision`, `exception`, `output`.
Include all six kinds, representing real source loading, validation, a join or
cross-reference, decisions, explicit exception handling, and completed output.
The workflow documents business steps; the foundation does not interpret it
as an executable engine.

`connections.json` has `schema_version: 1`, `mode: "mock-exports-only"`,
`availability: "not-required"`, `connections: []`, and a nonempty `note`.
Mock exports imply no native connection. Do not invent connection IDs,
availability, publisher metadata, credentials, or live business access.

## Baseline executable and result

Each trusted, locally authored `baseline.py` uses only the Python standard
library and may import the shared CLI helper. It must not import Creator code
or a generated plugin, use network/services, install anything, or modify input,
expected, documentation, or unrelated files. It is not an untrusted-code sandbox.

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "_shared"))
from scenario_support import run_cli

def solve(payload):
    # Implement the documented business rules, returning actual observed events.
    result = {"schema_version": 1, "status": "completed",
              "outputs": {}, "exceptions": []}
    events = []
    return result, events

if __name__ == "__main__":
    run_cli(solve, scenario_id="sector-01")
```

The stub above is an interface only; empty events do not pass validation.
The helper is supplied at `scenarios/_shared/scenario_support.py`.

```powershell
python -B baseline.py --input mock-data\demo.json --output baseline-output\demo.json --trace baseline-output\demo.trace.json
```

The result and every golden have exactly the common envelope
`schema_version: 1`, `status`, `outputs` (object), and `exceptions` (array of
objects with nonempty `code` and `message`, plus optional business fields).
Place all business outputs in `outputs`. Use decimal strings or integer minor
units for money. A rejected or partially quarantined business case still exits
0 with an explicit result; invalid files, unexpected errors, or infrastructure
failures exit nonzero and cannot count as a passed negative.

Comparison ignores object-key order, compares finite JSON numbers
mathematically, distinguishes booleans from numbers, and preserves array order.
No hidden ignored fields or floating tolerance. Document stable row ordering.

## Actual trace and central video interface

`solve` returns `(result, events)`. Each event is an actual deterministic
snapshot captured during the baseline run, not text invented from the golden:

```json
{
  "step_id": "join-records",
  "kind": "join",
  "caption": "Matched the two mock exports by record ID; one row has no match.",
  "facts": {"matched": 2, "unmatched": 1},
  "tables": [
    {
      "title": "Joined records",
      "columns": ["record_id", "match", "decision"],
      "rows": [["DEMO-01", "yes", "review"], ["DEMO-02", "no", "exception"]],
      "total_rows": 2,
      "highlight_rows": [1]
    }
  ]
}
```

`step_id` must identify a workflow step with the same `kind`.
`caption` is nonempty and at most 260 characters. `facts` is an object of up to
six named scalar JSON values. `tables` has one or two tables, each with a title,
one to six named columns, zero to eight rows of the same width, `total_rows`
(at least the displayed row count), and `highlight_rows` (zero-based indices).
Cells are scalar JSON values; keep them short and use a faithful labeled
subset if needed. No omitted-row claim when `total_rows` equals displayed rows.

Every demo has at least six meaningful events and all six step kinds; first
is `input`, last is `output`. Negative cases may stop early at validation.
The helper adds one-based `sequence` and writes the trace envelope:
`schema_version: 1`, `provenance: "synthetic-local-baseline"`, `scenario_id`,
`input_sha256`, and `events`. No wall-clock dates inside deterministic results.

The central producer reruns DEMO, compares it to its independent golden,
renders actual trace tables/facts/captions with active-row/progress highlighting,
and makes a roughly 30-90 second silent WebM. It labels every frame
**Synthetic baseline execution visualization - not Cowork or a live system**.
It records the exact commands, encoder identity, source/result/trace hashes,
frame count, timeline, decoded fidelity, and limitations. Pillow and an
already-present FFmpeg are optional developer-only tools, never plugin or
end-user dependencies. Sector owners supply trace, not fake UI screenshots.

## Native staging and evidence gates

Creator input is an exact allowlist: `HOW_TO.md`, `workflow.json`,
`connections.json`, `mock-data/demo.json`, and `demo/baseline.webm`.
Nothing else is copied. In particular, no `scenario.json`, `sources.json`,
`baseline.py`, shared code, `expected`, baseline outputs, holdouts, negative
cases, validation answers, or hidden markers. Research links belong in the
public procedure. Staging records hashes outside the input directory.

Per-case reporting separates **documented** procedure/rule coverage,
**observed** baseline stages, **local** comparisons, and **native** evidence.
States include `prepared`, `baseline_pass`, `native_creation_blocked`/`not_run`,
`generated`, `installed`, and `compared`; local success never implies a later
native state. Missing, stale, mock, or merely declared native evidence cannot
pass. Read-only ZIP/source inspection is not execution or native provenance.
Never blindly execute a downloaded plugin.

As of 2026-09-14, native creation/install/independent execution are blocked.
Both approved Computer Use tools and an unlocked accessible session must be
restored, with parent-coordinated authorization, before any native action.
No alternate browser, private API, token, cookie, shell, or model/skill route
may substitute. The old N00 publication was last `Publishing...`; outcome is
unknown and Creator was disabled. Inspect real Installed state before retrying.
No native ZIP or successful native result is generated by this foundation.
