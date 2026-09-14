# N00 native operator handoff

Status: **Draft source exports; native gate pending.**
The operator in the parent session owns Cowork browser access. This repository
does not automate the browser or sign-in. Do not publish, share, modify tenant
permissions, accept EULAs, or perform production writes for this test.

## Artifacts

Run the development-only `python scripts\build_n00.py` to reproduce the
current v0.1.1 artifacts below. The original v0.1.0 files at the root of
`dist` remain unchanged for the ongoing native attempt; record the exact
version/hash used rather than mixing results across revisions.

| Artifact | Role |
|---|---|
| `dist\n00-v0.1.1\creator-n00.zip` | One-skill Creator with its bundled builder; native compatible-source upload candidate |
| `dist\n00-v0.1.1\creator-n00.report.json` | Source-export inventory and hash; no native acceptance claim |
| `examples\n00\process.md` | Synthetic procedure and no-connection metadata; attach |
| `dist\n00-v0.1.1\n00-fixtures\01-source-inventory.png` | First screenshot; attach |
| `dist\n00-v0.1.1\n00-fixtures\02-retained-calculations.png` | Second screenshot; attach |
| `dist\n00-v0.1.1\n00-fixtures\03-report-result.png` | Third screenshot; attach |
| `examples\n00\input-new.json` | Held-out runtime input; attach only for independent output invocation |
| `examples\n00\expected-new-report.md` | Independently written expected table/counts/total; evaluator only, do not attach during invocation |
| `examples\n00\observation-ground-truth.json` | Evaluator reference; do not attach for observation |
| `dist\n00-v0.1.1\output-n00.zip` | Developer baseline, not an output generated natively; do not use as evidence of native authoring |
| `dist\n00-video\n00-process-demo.webm` | Optional synthetic silent video input, produced with existing development tools only |
| `dist\n00-video\n00-process-demo.fixture.json` | Evaluator-only video timeline, hash, encoding details and limitations |

No FFmpeg was on the development PATH, but a narrow lookup found an already
installed Playwright-cache encoder. It and the already installed Pillow
package produced a 12-second WebM/VP8 fixture without any installation or
download. Neither tool is a Creator/output runtime dependency.
The video is synthetic static screens with transitions, not continuous
desktop actions or narration. All 24 frames were decoded locally and
matched their correct source screens. This does not prove native video
reading. No native media support is inferred from developer capabilities.
Separately, the parent native operator has observed Python 3.12.14 and a
byte-checked ZIP download in actual Cowork. This establishes useful native
primitives, not installed-skill execution or the complete N00 round trip.

## First prompt

Upload the Creator through the documented native compatible-plugin route if
available and authorized. Keep it private. Record every blocking consent or
metadata prompt without bypassing it. Start a new conversation using the
Creator and attach only the procedure and three ordered screenshots.

> Use the Process Creator proof skill to create a reusable file-only plugin
> from the attached procedure and ordered screenshots. First describe the
> changing values, retained/excluded rows, final result and the displayed
> screen note using the actual images. Separate document rules from observed
> behavior and do not invent timestamps. Then locate and execute the installed
> skill's bundled creator_builder.py probe using Cowork's already available
> native runtime. Author your own candidate skill and any deterministic helper,
> not a summary of the demonstration. Make input file, reporting month and
> output filename explicit runtime parameters. We have no approved publisher
> legal URLs, so use the builder's explicit compatible-source target and label
> it a Draft source export, not a canonical v1.28 package. Return the exact
> plugin ZIP, build report, runtime probe and observations as downloadable
> files. If a native capability is unavailable, report that step as blocked;
> do not install tools or call external services.

Do not tell Cowork the hidden note or expected total before observation.

## Separate video observation

Use a fresh native conversation with only the procedure and
`n00-process-demo.webm`, not screenshots, ground truth, prior observations or
the fixture JSON report. This avoids mistaking memory of the screenshots
for actual video understanding.

> Read this attached synthetic process video itself, not only its filename
> or metadata. Describe the initial values, the displayed screen note, the
> retained and excluded rows, the repeated calculation and final displayed
> result. Identify changes in order. Report any unreadable detail; use
> timestamps only if the native tools actually provide them. This is a silent
> synthetic demonstration, not evidence of general desktop access or audio
> understanding. Do not install software or call a media-analysis service.

The evaluator timeline is initial inventory [0,4 seconds), calculations
[4,8 seconds), result [8,12 seconds). Frame cadence is two per second.
The [Cowork FAQ](https://learn.microsoft.com/en-us/microsoft-365/copilot/cowork/cowork-faq)
explicitly lists `.webm` as an attachment type; the actual attachment and
semantic observation still need native proof.

Optional development reproduction uses `scripts\make_video_fixture.py`
with `--ffmpeg` set to an already installed encoder, `--frames` set to the
existing synthetic screenshot directory, and `--output` set to a new
`.webm` path. The script intentionally has no installer/downloader and is
not included in either plugin.

## Bundled helper invocation

The native resource path must be discovered, not hardcoded. With the actual
interpreter and actual installed companion path, pass `probe`.

For the native build, invoke that same companion with arguments:
`build`, `--source` followed by the generated candidate directory, `--output`
followed by a new ZIP path, `--report` followed by a new JSON report path,
and `--target compatible-source`.

Canonical native composition is implemented for the emitted subset but
blocked until real approved `app_id` and developer metadata are supplied.
Never copy example/finance/future-repository legal URLs to unblock it.

## Independent invocation

Download the exact ZIP returned from Cowork, not the local baseline and not
an outer Download All container. Preserve its build hash. Upload that output
as a separate plugin. In a fresh conversation with the Creator inactive,
attach `input-new.json` and invoke:

> Use the ready-items workflow from the output plugin on this new inventory
> for reporting month 2026-09. Create a new Markdown report. Do not use the
> Creator, original document, original media or prior conversation.

Expected runtime result: four included rows, one excluded row and total
27.78. This differs in row count and values from the demonstration.
Record the generated output's actual skill name if Cowork chose another.

## Native gate record

Record each step independently with observed evidence or its exact blocker:
native access, Creator upload/conversion, document reading, screenshot reading,
video reading, bundled helper probe, native candidate authorship, bundled ZIP
build, exact ZIP download, output upload, independent changed-input invocation.
Do not change an unobserved step to passed because a previous step worked.

N00 remains incomplete without native recording observation and the required
native package round trip. A successful source-conversion experiment is a
useful bootstrap result, not canonical v1.28 acceptance. N01-N09 require
explicit follow-on authorization.

## Native upload attempts

The parent operator reported that the v0.1.0 compatible-source attempt,
scoped to **Only you**, returned exactly: `There was an error processing
the request`. The UI displayed the ZIP's
34-character basename rather than the internal plugin name. A shorter
filename retry (`creator-n00.zip`) with identical bytes subsequently
completed: **Cowork Process Creator** appeared under Installed with Enable
on. Before the retry, the full installed list contained no Creator.

Record both attempts; filename length is not conclusively the root cause
because a transient failure is also possible. Use short distributable
filenames going forward as a conservative compatibility choice. This
observes compatible-source conversion/install, not direct canonical v1.28
archive acceptance. Consult `native-status.json` for evidence and hashes.
