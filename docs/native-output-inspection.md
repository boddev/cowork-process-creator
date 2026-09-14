# Native-generated output inspection

**No blocker found for the bounded N00 file/report invocation.** The actual
native-generated output is not the developer baseline. All source was read
before executing its helper. The original download and staged helper remain
unchanged. Independent native output installation/invocation is still owned
by the parent operator and is not established by these local results.

| Item | Observed value |
|---|---|
| Native task | Synthetic N00 authoring run; private task identifier omitted |
| Original archive | `ready-items.zip`, 10,591 bytes |
| Archive SHA256 | `15d75761c98a1a20818a86ae6a1ec2e96bd83de92fdd4d08184ba6647adf7419` |
| Native build-report SHA256 | `8f1ace9f20ff6b8308430a75edaf0cbdfbaa8023c0d0abf9d2bf174bd4c4525b` |
| Source plugin | `ready-items`, version `0.1.0`, compatible-source/Draft |
| Entry skill | `ready-items-report` |
| Helper | `skills\ready-items-report\scripts\ready_items_report.py` |
| Helper SHA256 | `aa4fdbe508526e6b3ce881f8c94779f1c80d8b7ba0b3af886adb83e61a125ee6` |
| Arguments | Required `--input`, `--month`, `--output`; no defaults |
| Local regression host | Python 3.13.14 on Windows; not native Cowork execution |

The native build report exactly matches the archive size/hash and all three
entries' sizes/hashes: the compatible manifest, `SKILL.md` and the helper.
It accurately leaves host acceptance/manual invocation unverified and
scheduling unexercised. The builder version is 0.1.0. No canonical v1.28
manifest, legal URLs, registrations, connections or credentials were invented.

The separately downloaded evidence-only `n00-evidence.zip` is preserved at
the scoped inspection location, SHA256
`fda9fd0ed6a1dc037ea583fde26d19c1a19059cfffcce206ad496ff8a0a77bf1`.
It has exactly five artifacts. Its inner plugin and build report byte-match
the separate downloads. The probe records builder 0.1.0 under Linux
Python 3.12.14; the native test report has exactly 81 cases, all marked passed,
and matches the inspected helper hash. Those native records are separate from
the 15 local regression groups below.

## Behavior and independence

The only imports are `argparse`, `json`, `re`, `sys`, and `pathlib`.
There is no network client, subprocess, installer, external package, Creator
import, original-evidence dependency or OS-specific API. The code is compatible
with the observed native Python 3.12 environment by API inspection; that is
distinct from actually invoking the installed output there.

The helper validates every row before creating output, including held rows.
It rejects duplicate JSON keys, bad types/states/IDs/months and numeric
fractions/exponents where JSON integers are required. It computes in integer
hundredths, so totals do not depend on floats or Decimal context precision.
It repeats over the whole collection, preserves input order and exclusively
creates a new `.md` destination.

The exact new input produced these retained line costs:

| ID | Quantity | Unit cost | Line cost |
|---|---:|---:|---:|
| N901 | 4 | 1.25 | 5.00 |
| N903 | 3 | 0.10 | 0.30 |
| N904 | 2 | 9.99 | 19.98 |
| N905 | 1 | 2.50 | 2.50 |

**Included 4; excluded 1; grand total 27.78.** `N902` is excluded.
The native output's Markdown heading differs from the developer baseline;
the required table, month, counts and result agree.

Fifteen targeted regression groups passed, including 100 seeded input sets
compared to an independent Decimal reference, the exact 10,000-row maximum,
maximum quantity/cost, malformed input, empty/all-held input, no overwrite,
and literal paths containing spaces/shell characters.

Run them explicitly after staging the reviewed hash:
`python -B -m unittest discover -s tests\native -v`.
The isolated snapshot, persisted report and machine-readable comparison
results are under `.local\native-output-15d75761c98a`. These optional artifact
tests are separate from the Creator's normal source regression suite.

## Nonblocking limitations

A 20,011-byte invalid JSON input with 10,000 nesting levels produced an
uncaught `RecursionError` on local Python 3.13.14: exit 1, empty stdout and no
output file. The parse at helper lines 107-112 has no depth limit and the CLI
handlers at lines 124-137 do not catch that error type. This fails closed,
but does not provide the helper's normal concise `Error:` diagnostic.
The helper also reads the input fully before enforcing the row limit; there
is no explicit byte-size ceiling. These are hardening notes, not evidence of
an incorrect result on declared flat inputs. No source was patched.

The user-facing filename-only rule is in the skill. The helper intentionally
accepts the resolved native output path and does not itself enforce workspace
containment; the caller and native platform still govern that boundary.
Do not describe the helper or static inspection as a security sandbox.

## Native media method and limits

The native task could not directly view the video. Its pre-existing
`imageio_ffmpeg` decoder extracted 24 frames with original timestamps without
installing anything or calling an external service. Cowork's own native
parent inspected original frames 1, 9 and 17 at 0, 4 and 8 seconds, and passed
those observations to its own authoring worker. This was not visual-answer
input from the external coordinating or coding session.

All expected rows, states, quantities, costs, retained/excluded IDs, line
costs, sample month, screen note and displayed total match the withheld
reference. This does not establish visual review of every frame, exact step
interval boundaries, narration, continuous real UI behavior or a portable
direct-video viewer. The observed decoder is an optional existing native
capability, not a new bundled or install-required Creator dependency.
