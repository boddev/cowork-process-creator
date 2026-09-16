# Contributing

Help make reusable Cowork processes easier to understand, reproduce, and
improve. Documentation fixes are welcome on their own; you do not need to
build a plugin to fix a guide.

An example should give another person everything they need to understand
the process, install the plugin, and try it with their own inputs.

## Choose the right location

| Contribution | Location and starting point |
|---|---|
| A self-contained example plugin | `examples\<short-kebab-name>`; see the [bill splitter](examples/bill-splitter/README.md) for a source-and-sample-data layout. |
| A synthetic business scenario with reference results | `scenarios\<industry>\<short-kebab-name>`; follow the [scenario contract](scenarios/SCENARIO_CONTRACT.md) and [requirements below](#additional-requirements-for-business-scenarios). |
| A scenario plugin and results exported from Cowork | `output\<scenario-id>`, with the [creation, installation, and run records](scenarios/HOW_TO.md#future-authorized-native-procedure). |
| Creator instructions, helper code, or generation patterns | The owning skill in `appPackage\skills`, with appropriate tests; read the [extension guide](docs/extensions.md). |
| User-facing documentation | `README.md`, `docs\user-guide.md`, or the relevant example guide. Keep developer commands outside the normal end-user path. |

Open an issue before proposing a new service, dependency, package format, or
major change to the scenario contract. Creator is designed to use Cowork's
existing facilities, not a separately deployed automation platform.

## Required bundle for a completed example

Include the following before describing a new example as ready to use.
Filenames are suggestions unless the scenario contract specifies them.
New example plugins must use the
[native Microsoft package format](docs/MICROSOFT_PACKAGING.md).

| Required item | What it must contain |
|---|---|
| **Overview (`README.md`)** | Who the process helps, required inputs, expected outputs, prerequisites, limitations, download links, and installation instructions. |
| **User prompt (`prompt.md`)** | The exact shareable prompt used to create the plugin, attachment names, and important clarification answers. Keep this separate from the prompt used to run it. |
| **Written process (`process.md`)** | Ordered steps, business rules, configurable values, calculations, output format, exceptions, and approvals. Cite sources and label invented sample policies. |
| **Process video (`demo\process.webm`, or a versioned link)** | A shareable demonstration showing the process and result. Redact private data and explain omissions. Label synthetic visualizations accurately. Screenshots can supplement the video. |
| **Plugin ZIP** | The installable Microsoft package for the documented version, its SHA-256 checksum, and build report. Supply the file or a stable release-asset link, not a repository source ZIP or editing checkpoint. |
| **Editable source (`candidate`)** | The package specification, skills, and supporting files needed to rebuild the plugin. Include the creation-source bundle when available. |
| **New test inputs and expected results** | Synthetic inputs beyond the demonstration, including invalid or ambiguous cases. Calculate expected results from the written rules, not by copying the plugin's output. |
| **Run instructions and results** | A copyable run prompt, required attachments, and actual results from a fresh Cowork task with Creator disabled. Record which package was installed and tested. |
| **Attribution and status** | Sources, redistribution permissions, known limitations, and any missing deliverables. Keep local test results separate from observed Cowork runs. |

**Drafts are welcome.** Mark the overview **Draft** and list missing items.
Call an example ready to use only after the bundle is complete and the
installed plugin has been tested with new inputs.

For ordinary examples, large videos and ZIPs can be versioned release assets.
Use links that do not expire or require access to a personal account. Keep
small test inputs and editable source in the repository. Business scenarios
follow the specific file layout in the scenario contract.

## Add an example

1. **Choose a bounded process.** Explain the intended user, why reuse helps,
   what the output should be, and which actions still need human review.
2. **Prepare shareable evidence.** Write the procedure, record the video,
   and save the authoring prompt and clarification answers. Use synthetic
   data. If redaction changes behavior, reproduce the demonstration with
   safe data instead of claiming the original run is still exact evidence.
3. **Author and review the plugin.** Follow the
   [user guide](docs/user-guide.md). Make inputs configurable, check
   exceptions, and ensure the output owns its needed instructions/helpers.
4. **Build with approved metadata.** Follow
   [Microsoft packaging](docs/MICROSOFT_PACKAGING.md). Each new native output
   plugin needs its own supplied app ID and approved publisher
   website, privacy, and terms URLs. Test identities and guessed legal URLs
   are not shipping metadata.
5. **Exercise it independently.** Install the exact ZIP in an authorized
   Cowork account, disable Creator, and start a fresh task with new runtime
   inputs. Compare the complete result with independently expected results.
   Do not supply the original recording or Creator's source as a workaround.
6. **Open a focused pull request.** Include the required bundle, explain
   what was actually observed, and identify any remaining gaps. Link the new
   example from the repository README without calling a draft ready to use.

## Additional requirements for business scenarios

Business scenarios compare a plugin's results with independently calculated
answers. Follow the [scenario contract](scenarios/SCENARIO_CONTRACT.md) for
file formats and the [development how-to](scenarios/HOW_TO.md) for commands.
Keep some inputs out of the demonstration: these **holdouts** test whether
the plugin follows the rules on data it has not seen before.

| Requirement | Minimum |
|---|---|
| Procedure and research | A complete `HOW_TO.md`, `scenario.json`, `workflow.json`, `sources.json` with at least two real public references, and `connections.json` declaring mock exports only. Separate source-backed constraints from sample policy. |
| Cases | Exactly one `demo`, at least two distinct holdouts, and at least two negatives covering malformed business input and contradictory evidence. Cover every rule and record each independent derivation. |
| Expected results | Author `expected` files from the procedure before running the reference implementation. Preserve the full result envelope, row ordering, decimal representation, and exception content. |
| Local reference implementation | A trusted, standard-library `baseline.py` implementing the documented rules without reading expected answers, calling external services, or depending on Creator. |
| Video and evidence | The shared producer's visualization of the actual baseline trace, media metadata, case evidence, golden lock, and exact staged input bundle. The video must remain labeled synthetic, not native Cowork footage. |
| Prompt and plugin ZIP | Save the authoring message and important clarification answers, for example in `prompt.md`. Place the plugin downloaded from Cowork and its installation/run records under `output`. Until those exist, report only the local reference results. |

### Keep evaluation answers out of Creator's input

The staged `validation\creator-input` directory contains **exactly five files**:

| File | Why Creator receives it |
|---|---|
| `HOW_TO.md` | The full public procedure and output contract |
| `workflow.json` | The documented steps and rules |
| `connections.json` | The explicit mock-only connection boundary |
| `mock-data\demo.json` | Demonstration input |
| `demo\baseline.webm` | The synthetic demonstration video |

The authoring prompt is the **conversation message**, not a sixth staged
attachment. Do not attach the whole scenario folder, baseline implementation,
expected answers, holdouts, negatives, validation records, or previous results.
Holdouts and negatives are supplied as runtime inputs only when evaluating
the installed output plugin in fresh tasks; expected answers stay with the
reviewer.

Keep actual native exports separate from local reference output. Use the
existing [native inspection/import protocol](scenarios/HOW_TO.md#future-authorized-native-procedure)
to record them, not a new status format or a locally assembled ZIP presented
as something Cowork produced.

## Developer checks

Run commands from the repository root. Core toolkit work needs Python 3.10+
with its standard library; scenario tooling needs Python 3.11+. These are
contributor requirements, **not things end users install**.

| Change | Existing check |
|---|---|
| Core skills, builder, project contracts, or release tooling | `python -B -m unittest discover -s tests -v` |
| Bill-splitter helper or fixtures | `python -B -m unittest discover -s tests -p test_bill_splitter.py -v` |
| Scenario data/contracts | `python -B -m scenarios validate --all --full` |
| Scenario code or shared tooling | `python -B scenarios\run_tests.py` |
| Ordinary documentation | Check links, headings, filenames, prompts, and current package availability. No release build or corpus regeneration is needed. |

When updating installation instructions, check the download links and file
format against the [release notes](https://github.com/boddev/cowork-process-creator/releases).

For baseline execution, video generation, staging, and reporting, follow the
[scenario commands](scenarios/HOW_TO.md). Those commands write generated
artifacts; do not run them as an incidental documentation check. A change to
a hash-bound scenario procedure is a scenario change even though it is Markdown.
Do not rewrite expected answers, their locks, historical packages, or native
observations to make a check pass.

Keep runtime resources inside their owning skill. Route between skills by
name rather than importing another installed skill's files. Generated output
must not depend on Creator, the repository checkout, the original media, or
software installation at run time. See the
[extension guide](docs/extensions.md#put-resources-in-their-owning-skill).

## Pull request checklist

- [ ] The scope, intended user, changed behavior, and known limitations are clear.
- [ ] A new example includes every required deliverable, or is explicitly a Draft with missing items listed.
- [ ] Prompts, documentation, media, inputs, and outputs agree with one another.
- [ ] Local results are not described as native creation, installation, or independent invocation.
- [ ] Relevant existing checks were run; docs-only work did not regenerate unrelated evidence.
- [ ] No credentials, private business data, personal checkout paths, or unapproved publishing metadata were added.
- [ ] All included code/media can be redistributed, and its sources are credited.
- [ ] Redistributed source and plugin packages include the applicable copyright and license notices.
- [ ] Navigation links and the example's current status were updated.

## License and attribution

Original contributions to this repository are made under its
[MIT License](LICENSE). Contribute only material you own or have permission
to provide under those terms, and retain existing copyright and license
notices. Contributors retain their copyright.

When redistributing repository code or substantial portions of it, include
the MIT copyright and permission notice. This applies to copied or adapted
code in plugin ZIPs and creation-source bundles as well as source downloads.
Using Creator does not require independently authored output to be licensed
under MIT; preserve the required notices for repository code you include.

Third-party code, documentation, screenshots, recordings, and service
metadata remain subject to their owners' terms. Identify their source and
applicable terms, retain required attribution, and confirm redistribution
permission before including copies. The repository's MIT license does not
grant rights to someone else's material merely because it is linked,
referenced, or bundled here.
