# Restaurant bill splitter

**Current source: v1.1.0, native Microsoft Copilot Cowork manifest v1.28 only.**
No current plugin ZIP is available: approved app/publisher metadata has not
been supplied. The old compatible-source preview is archived, not a fallback
or a current native distributable.

Split a new itemized restaurant receipt among up to eight diners. The skill
calculates each person's share of the items, tax and tip, then uses Cowork's
existing spreadsheet facilities to create a new workbook.

## Native package and runtime prerequisites

The [current status](status.json) separates the blocked package from the
unchanged historical archive. An authorized maintainer must supply this app's
approved identity and publisher website/privacy/terms metadata, build the
native package, and separately observe installation before an end user can
invoke it. Do not invent metadata, reuse syntax-test identities, or import the
archived compatible-source ZIP as a substitute.

After the native access gate is open and Cowork confirms that the actual
native package is installed, select/enable it as permitted, start a new
conversation, attach your receipt and use a prompt such as:

> Use split-restaurant-bill to split this receipt between Ana, Bo and Cleo.
> Split every line evenly. Use the gratuity printed on the receipt; ask me
> what tip to use if none is printed. Create a new bill-split.xlsx workbook
> and show the amount each person owes.

The installed output does not require the Process Creator, original recording
or template workbook. You can optionally supply your own workbook template.
The bundled layout reference is sufficient to recreate the sheet without it.
End users do not install Python, packages or developer tooling.

Cowork must already provide the required receipt-reading, Python 3.10+ and
spreadsheet capabilities. The helper computes JSON; workbook creation is a
separate native step. If spreadsheet editing is unavailable, the skill reports
that limitation and returns the computed figures without claiming an XLSX file.

Native installation, independent invocation and workbook creation remain
unverified. A local package build is not native generation or host acceptance.
See [Microsoft packaging](../../docs/MICROSOFT_PACKAGING.md) for the required
manifest, metadata and no-fallback boundary.

## What is included

The candidate contains the `split-restaurant-bill` skill, its two owned
references and its two Python helpers. A native build adds root
`manifest.json`, `color.png` and `outline.png`. It includes no original receipt
images, video, workbook, development tests or Creator runtime.

For the manual procedure, synthetic inputs, expected amounts and provenance,
read [process.md](process.md). Editable source is under [candidate](candidate).

## Build the native package from source

These are **developer-only** source checks and packaging commands. From the
repository root, use an existing Python 3.10+ interpreter. The metadata file
below must already contain real approved values using the
[required metadata contract](../../docs/MICROSOFT_PACKAGING.md#publishing-metadata-is-a-real-prerequisite);
this repository supplies no default identity or publisher/legal URLs.

```powershell
New-Item -ItemType Directory -Force .local\bill-splitter | Out-Null
python -B appPackage\skills\build-output-plugin\scripts\creator_builder.py validate `
  --source examples\bill-splitter\candidate
python -B appPackage\skills\build-output-plugin\scripts\creator_builder.py build `
  --source examples\bill-splitter\candidate `
  --target cowork-v1.28 `
  --metadata .local\publishing\restaurant-bill-splitter.json `
  --output .local\bill-splitter\bill-splitter.zip `
  --report .local\bill-splitter\bill-splitter.report.json
```

The builder validates `plugin-spec.json` and owned resources, then emits only
the supported Microsoft manifest v1.28 package. Missing or invalid metadata
blocks packaging without creating a replacement-format ZIP. Source validation
alone does not satisfy project evidence/coverage checks. The commands do not
run the recorded process, create a workbook, or install anything in Cowork.
No dependencies beyond Python's standard library are required.

The output is `.local\bill-splitter\bill-splitter.zip`; the adjacent JSON report
records its checksum and contents. Existing outputs are never overwritten:
choose new output/report filenames if you have already run these commands.

Do not overwrite the archived ZIP or report when building a new version.
The example tests exercise the helper from both the frozen archive and a
temporary native-format syntax fixture; neither run is native invocation
evidence. Runtime source bytes are preserved by `.gitattributes`.

## Historical v1.0.1 archive

The [archived ZIP](archive/v1.0.1/bill-splitter.zip?raw=1) and its original
[report](archive/v1.0.1/bill-splitter.report.json) are preserved byte-for-byte.
They use `.claude-plugin/plugin.json`, target `compatible-source`, and remain
historical Draft source artifacts, not a native Microsoft package. The ZIP
is 37,037 bytes with SHA-256:

```text
d50f635cfa3d40e81087a4f80e261f812a1c095fb33a700aba38ea2738e7f5a3
```

The current packaging adaptation leaves the business procedure, arithmetic
helper, owned skill resources and complete independent fixture unchanged.
