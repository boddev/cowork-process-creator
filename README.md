# Cowork Process Creator

**Turn a process you demonstrate into a Cowork plugin you can reuse.**

[Microsoft Copilot Cowork](https://learn.microsoft.com/en-us/microsoft-365/copilot/cowork/)
lets you describe work in a conversation and have Copilot carry it out.
Process Creator is a plugin for Cowork that helps turn a written procedure
and a video or ordered screenshots into another, task-specific plugin.

For example, you could demonstrate how to split a restaurant receipt.
Instead of explaining the calculation again next time, you would use the
resulting bill-splitting plugin with a new receipt.

> [!NOTE]
> **Get Creator:** [Download creator.zip (v0.2.1 preview)](https://github.com/boddev/cowork-process-creator/releases/download/v0.2.1/creator.zip),
> then follow the [installation guide](docs/user-guide.md#1-get-the-creator-plugin-zip).
> Read the [release notes](https://github.com/boddev/cowork-process-creator/releases/tag/v0.2.1)
> for known limitations before trying the preview.

## Start here

| I want to... | Go to |
|---|---|
| Understand how Creator works | [How it works](#how-it-works) |
| Install Creator and make my first plugin | [Step-by-step user guide, with screenshots](docs/user-guide.md) |
| See what kinds of processes are included | [Examples and scenarios](#examples-and-scenarios) |
| Find my way around the files | [Repository map](#repository-map) |
| Contribute an example, scenario, or improvement | [Contribution guide](CONTRIBUTING.md) |
| Build packages or change Creator's behavior | [Maintainer references](#maintainer-references) |

## How it works

A **plugin** adds capabilities to Cowork. It contains **skills**: instructions
for performing particular tasks. Creator's skills help you build your own
plugin without writing those instructions from scratch.

1. **Show the process.** Supply its written rules, a demonstration, and
   safe sample inputs.
2. **Review the design.** Confirm what should change each time, what stays
   fixed, and how exceptions should be handled.
3. **Get the plugin.** Creator builds a plugin ZIP and an editable copy of
   the project. If something is missing, it explains what you need to finish.
4. **Use it again.** Install the output plugin and start a new Cowork task
   with new inputs. It should not need Creator or the original recording.

Everything runs inside Cowork; you do not need to install developer tools.
Creator uses capabilities Cowork already provides. It does not replay
arbitrary desktop clicks or set up business-system connections for you.

## Examples and scenarios

An **example** shows a particular plugin and how it is intended to be used.
A **scenario** supplies a documented process and synthetic (made-up) data
for learning and evaluation; it is not necessarily an installable plugin.

| Collection | What you can explore | What is available now |
|---|---|---|
| [Restaurant bill splitter](examples/bill-splitter/README.md) | Split receipt items, tax, and tip among diners, then create a workbook. | Draft: procedure, editable source, and sample calculations. No current plugin ZIP. |
| [15 business scenarios](scenarios/VALIDATION_REPORT.md) | Manufacturing, health/life sciences, financial services, retail, and other business processes. | Procedures, demonstration videos, and synthetic test data. These are examples to learn from, not ready-made plugins. |
| [Developer examples](examples/offline) | Cost reports, priority checklists, exception ledgers, and connector metadata. | Reusable code patterns and test inputs for plugin developers. |

For a business scenario, start with its `HOW_TO.md`. The accompanying video
illustrates a reference program running on synthetic data; it is not a
recording of Cowork or a live business system. You can also browse the
[combined procedure collection](scenarios/ALL_SCENARIOS_HOW_TO.md).

## Repository map

| Location | What belongs here | Who it is for |
|---|---|---|
| [`appPackage`](appPackage) | Creator's eight skills, package specification, and supporting scripts and references. | Plugin developers |
| [`docs`](docs) | Installation and user guides, technical references, and maintainer notes. | Users and maintainers |
| [`examples`](examples) | Example plugin source, sample inputs/results, developer patterns, and older demonstration artifacts. Each example documents its own status. | Learners and contributors |
| [`scenarios`](scenarios) | Business procedures, synthetic data, expected results, reference programs, videos, and evaluation tools. | Scenario authors and evaluators |
| [`output`](output/README.md) | Plugin ZIPs and results downloaded from Cowork during scenario evaluations. Currently contains status information only. | Evaluators |
| [`scripts`](scripts) | Utilities for building releases and producing example projects, test data, and videos. | Maintainers |
| [`tests`](tests) | Python tests for packaging, authoring projects, helpers, and examples. | Developers |
| [`evals`](evals) | Prompts for evaluating Creator and records of which evaluations have been run. | Evaluators |

At the root, [CONTRIBUTING.md](CONTRIBUTING.md) explains contribution
requirements, and [LICENSE](LICENSE) contains the MIT license.
[`.gitignore`](.gitignore) excludes local build output and scratch files;
[`.gitattributes`](.gitattributes) preserves files used in package and evidence
checks. The `dist` and `.local` directories contain local developer output
and are not committed.

## Contributing

Documentation improvements and new processes are welcome. A completed,
ready-to-use example must include the **authoring prompt, process video,
current plugin ZIP, editable source, and a repeatable new-input run with
expected results**. The [contribution guide](CONTRIBUTING.md) provides the
full checklist, recommended layout, and the additional rules for benchmark
scenarios.

Drafts are welcome. Label them **Draft** and list what is missing so readers
know what they can try.

## Maintainer references

| Topic | Reference |
|---|---|
| Current Microsoft package format, publisher metadata, and release build command | [Microsoft packaging](docs/MICROSOFT_PACKAGING.md) |
| Adding or changing skills, helpers, and capability mappings | [Extension guide](docs/extensions.md) |
| Authoring files, checks, packaging, checkpoints, resume, and merge | [Project contract](appPackage/skills/build-output-plugin/references/project-contract.md) |
| Supported package contents and limits | [Target rules](appPackage/skills/build-output-plugin/references/target-rules.md) |
| Running the synthetic scenario corpus | [Scenario development how-to](scenarios/HOW_TO.md) |
| Known gaps and artifact maintenance | [Maintainer notes](docs/maintainer-notes.md) |

## License

The repository's original code, plugin instructions, documentation, and
examples are available under the [MIT License](LICENSE). You can use,
modify, and redistribute them, including commercially, while preserving
the copyright and license notice.

Third-party material, including Microsoft's documentation, screenshots,
and service metadata, remains subject to its owners' terms; this license
does not relicense that material. See
[License and attribution](CONTRIBUTING.md#license-and-attribution) for
contribution and redistribution guidance.
