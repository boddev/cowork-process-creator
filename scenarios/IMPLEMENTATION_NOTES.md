# Implementation and validation notes

This corpus exercises **15 distinct, bounded review-preparation workflows**,
not live factory, clinical, financial, retail or infrastructure operations.
The five directory packs cover seven business industries. All policies and
data not specifically supported by a cited source are labeled synthetic.

## Independent expected results

Each sector owner wrote complete expected result envelopes and derivations
before executing its baseline. Golden locks preserve input/expected byte
hashes, not just a total or assertion count. The final runner compares every
object field, array order, exact decimal string and exception against those
files and checks protected bytes after execution. Author independence from
the implementation is not a claim of independent human certification.

The corpus contains 96 cases: 15 demos, 33 changed holdouts and 48 negatives.
Some negatives produce a completed review with explicit business exceptions;
others reject invalid packets. A crashed process or absent result cannot
count as a passing negative.

## Defects found while preparing the corpus

The initial reduced subprocess environment omitted Windows OS directory
variables. Windows Store Python consequently created incidental cache files
under a literal environment-variable directory in several scenario folders.
The runner now retains a minimal OS-path allowlist while excluding credential
and Python search-path variables. Actual Windows subprocess tests and the
full 96-case run completed without those cache files returning.

Four cache files accidentally entered an early **local-only** scenario
commit and were removed by a separate scoped cleanup commit. They were not
business workflow databases, were not inspected for content, and were never
pushed. Before any future public push of this new corpus, review the local
commit history as well as the current tree; do not publish those intermediate
objects. Repository integration must use a reviewed current-tree squash on
published main, without making private development ancestry reachable. Keep
the source branch untouched and audit outgoing object reachability before
publication. Repository publication does not authorize native Cowork actions.

The read-only native ZIP inspector initially trusted `ZipExtFile`'s clipped
read length. An underdeclared stored or DEFLATE member could therefore be
accepted with only its prefix hash. A failing-first reproduction now rejects
that case using bounded actual-stream length, end-of-stream and CRC checks,
while preserving valid stored, DEFLATE, ZIP64 and data-descriptor handling.
No downloaded plugin code was executed to find or fix this defect.

One long media run completed and published its validated video/report pair,
then encountered a transient Windows sharing violation while deleting a
temporary PNG. Cleanup now retries only Windows sharing/lock errors, within
a short fixed bound; other or persistent failures still surface. The already
published pair was checked, the exact leftover staging directory removed,
and only the remaining unrendered scenarios were continued. Baseline results
and goldens were not changed to recover from this host cleanup issue.

These are corpus-tooling fixes, not observed errors in a native-generated
enterprise plugin. The frozen Creator v0.2.1 source/release and earlier native
proof artifacts were not changed.

## Integration regression isolation

The combined regression suite initially exposed three scenario tests that
reran directly in the retained corpus, changing 24 validation-report timing
fields. Those tests now execute copied scenarios and the shared CLI adapter
in temporary test corpora. The original reports were restored byte-for-byte;
business inputs, independent goldens, results, traces and videos were not
revised. A regression case checks that executing a copied scenario leaves
all original source and evidence bytes unchanged.

Historical sector notes retain their original observations, with supersession
labels pointing to the completed catalog. Current Creator source is v0.3.0
and native-only; the frozen earlier releases and native proofs remain
historical, not current packaging or acceptance claims.

## Runtime and media evidence

The development corpus tools require existing Python 3.11+ and were exercised
on Windows Python 3.13.14. The optional video producer uses already-installed
Pillow and the existing Playwright-cache FFmpeg binary; neither is included
in generated workflow plugins or required of end users.

Videos show actual baseline trace tables, validation, joins, decisions,
exceptions and completed output. Every frame says that it is a **synthetic
baseline execution visualization**, not Cowork or a live system. Every decoded
frame is checked against its source image and expected sequence; shortening
of displayed text is explicitly marked and listed in the media report.
Silent visualizations do not prove native video/narration understanding.

## Remaining native work

Actual native Creator generation, plugin installation, fresh independent
invocation and comparison remain **not run**. Approved Computer Use tools
must be restored and an unlocked accessible session must be available.
Do not substitute another UI channel, private API, cookie/token, shell,
model or CLI for that missing access.

The original N00 publication result remains unknown after `Publishing...`.
Reconcile Installed state before retrying once approved access is restored.
Root `output` contains pending metadata, not fabricated plugin ZIPs. Use the
input-only bundles and the documented native protocol after the gate opens;
withhold baseline source, expected files and holdouts during authoring.
