# Restaurant bill splitter

**[Download bill-splitter.zip](bill-splitter.zip?raw=1)** - version **1.0.1**,
**compatible-source preview**.

Split a new itemized restaurant receipt among up to eight diners. The skill
calculates each person's share of the items, tax and tip, then uses Cowork's
existing spreadsheet facilities to create a new workbook.

## Try it in Cowork

1. Download **[bill-splitter.zip](bill-splitter.zip?raw=1)**. If GitHub shows a
   file page, use **Download raw file**. Do not download the whole repository
   or zip the `candidate` folder yourself.
2. Use the native plugin upload/import experience available in your Cowork
   environment, including its compatible-source conversion route. Follow the
   actual prompts and your organization's approval requirements. If that route
   is unavailable, stop; merely attaching the ZIP to a chat is not proof of
   installation.
3. Once Cowork confirms the plugin is available, select/enable it as permitted,
   start a new conversation, attach your receipt and use a prompt such as:

> Use split-restaurant-bill to split this receipt between Ana, Bo and Cleo.
> Split every line evenly. Use the gratuity printed on the receipt; ask me
> what tip to use if none is printed. Create a new bill-split.xlsx workbook
> and show the amount each person owes.

You do **not** need to clone this repository, install Python or packages on
your computer, install the Process Creator, or supply the original recording
or template workbook. You can optionally supply your own workbook template.
The bundled layout reference is sufficient to recreate the sheet without it.

Cowork must already provide the required receipt-reading, Python 3.10+ and
spreadsheet capabilities. The helper computes JSON; workbook creation is a
separate native step. If spreadsheet editing is unavailable, the skill reports
that limitation and returns the computed figures without claiming an XLSX file.

**Status:** this is a Draft compatible-source export, not a canonical v1.28
package. Native import/conversion, independent invocation and workbook creation
for this revision remain unverified. See the [build report](bill-splitter.report.json)
for the archive's SHA-256, file inventory and readiness labels, and the
[package-target guide](../../docs/user-guide.md#understand-package-targets-and-downloads)
for the conversion boundary.

## What is included

The ZIP contains the compatible plugin manifest, the `split-restaurant-bill`
skill, its two owned references and its two Python helpers. It contains no
original receipt images, video, workbook, development tests or Creator runtime.

The small generated ZIP is checked in beside this example so the download
travels with the contribution without requiring a separate upstream release.
The repository's existing Creator release artifacts remain separate.

For the manual procedure, synthetic inputs, expected amounts and provenance,
read [process.md](process.md). Editable source is under [candidate](candidate).

## Build the ZIP from source

This is a **developer-only** alternative to downloading the ZIP. From the
repository root, use an existing Python 3.10+ interpreter:

```powershell
New-Item -ItemType Directory -Force .local\bill-splitter | Out-Null
python -B appPackage\skills\build-output-plugin\scripts\creator_builder.py build `
  --source examples\bill-splitter\candidate `
  --target compatible-source `
  --output .local\bill-splitter\bill-splitter.zip `
  --report .local\bill-splitter\bill-splitter.report.json
```

The builder validates `plugin-spec.json` and the owned skill resources, emits
`.claude-plugin/plugin.json`, and packages only the runtime files. It does not
run the recorded process, create a workbook, or install anything in Cowork.
No dependencies beyond Python's standard library are required.

The output is `.local\bill-splitter\bill-splitter.zip`; the adjacent JSON report
records its checksum and contents. Existing outputs are never overwritten:
choose new output/report filenames if you have already run these commands.

When updating the example, rebuild to new paths, deliberately replace both
the checked-in ZIP and its report with the new outputs, and include them with
the source changes. The example tests require the download to match the
candidate and execute the helper extracted from that actual download.
Runtime source bytes are preserved by `.gitattributes` so checkout line-ending
conversion cannot silently change the package.
