# Process Creator user guide

Use Creator inside **Microsoft Copilot Cowork** to turn a written procedure
and a demonstration into a reusable plugin. Install Creator to build the
plugin, then install that new plugin separately to use it with new inputs.

> [!NOTE]
> This guide covers [Creator v0.2.1 preview](https://github.com/boddev/cowork-process-creator/releases/tag/v0.2.1).
> Start with made-up sample data and check the results before relying on it.

## In this guide

| Step | What you will do |
|---|---|
| [Before you start](#before-you-start) | Check your Cowork access. |
| [1. Get the Creator plugin ZIP](#1-get-the-creator-plugin-zip) | Download the right file. |
| [2. Install Creator in Cowork](#2-install-creator-in-cowork) | Upload and enable Creator. |
| [3. Show Creator your process](#3-show-creator-your-process) | Attach your procedure and demonstration. |
| [4. Review and download the result](#4-review-and-download-the-result) | Check the design and save your plugin. |
| [5. Install and run your generated plugin](#5-install-and-run-your-generated-plugin) | Try it with new data. |
| [Continue editing later](#continue-editing-later) | Save and resume your work. |
| [Troubleshooting](#troubleshooting) | Fix common installation and usage problems. |

## Before you start

This browser walkthrough uses a **work or school account**. You need:

- A Microsoft 365 Copilot license.
- Cowork enabled for your account, including usage-based billing.
- Permission to upload custom plugins under your organization's policies.

Ask your IT administrator if any of these are missing. See
[Microsoft's setup requirements](https://learn.microsoft.com/en-us/microsoft-365/copilot/cowork/get-started).

**Everything happens in Cowork.** You do not need to clone the repository,
run terminal commands, or install Python or other developer tools.

## 1. Get the Creator plugin ZIP

1. Open the [Creator release page](https://github.com/boddev/cowork-process-creator/releases/tag/v0.2.1).
2. Under **Assets**, download **[creator.zip](https://github.com/boddev/cowork-process-creator/releases/download/v0.2.1/creator.zip)**.
3. Save the file on your computer. **Leave it zipped.**

Do not choose **Source code (zip)** or **Code > Download ZIP**. Those are
developer source downloads, not the plugin to install.

## 2. Install Creator in Cowork

Use the **Plugins** page to install the ZIP, not the chat attachment picker.
Only upload packages from sources you trust.

### Open Cowork

1. Open [Microsoft 365 Copilot](https://m365.cloud.microsoft) and sign in.
2. Select **Cowork** next to **Chat**.
3. Select **Customize** in the left navigation. You can also open
   **+ > Customize** from the conversation menu.

![Microsoft Cowork home page showing the Cowork toggle, New task, and Customize in the left navigation.](https://learn.microsoft.com/en-us/microsoft-365/copilot/cowork/media/cowork-overview-interface.png)

*Cowork home screen. Screenshot: [Microsoft Learn](https://learn.microsoft.com/en-us/microsoft-365/copilot/cowork/).
Your layout may vary.*

### Upload the package

1. Select the **Plugins** tab, not **Skills**.
2. Select **Upload plugin** at the top of the tab.
3. Choose the **creator.zip** you downloaded. Cowork automatically converts
   this preview's compatible package format during upload; do not unpack
   or modify it yourself.
4. In the **Share** dialog, choose **Only you** to keep the plugin available
   to your account.
5. Select **Apply** and wait for publishing to finish.
6. Find Creator (package name **cowork-process-creator**) under **Installed**.
   If it appears under **Discover** instead, open its card and select **Add**.

To share the plugin with colleagues, use **Specific users in your organization**
in the Share dialog. See Microsoft's [sharing instructions](https://learn.microsoft.com/en-us/microsoft-365/copilot/cowork/cowork-customize#share-skills-and-plugins).

![Microsoft Cowork Customize page showing the Plugins tab and installed plugin cards.](https://learn.microsoft.com/en-us/microsoft-365/copilot/cowork/media/customize-plugins.png)

*Plugins page with example plugins. Screenshot: [Microsoft Learn](https://learn.microsoft.com/en-us/microsoft-365/copilot/cowork/cowork-customize).*

### Enable Creator for a new task

Select **New task**, open **Sources & Skills**, and turn on Creator
(**cowork-process-creator**).

**Ready to continue:** Creator appears under Installed and is enabled for
your task. If publishing has not finished, use
[Troubleshooting](#troubleshooting) before uploading again.

## 3. Show Creator your process

Prepare three things, using synthetic or redacted data:

| Material | What to include |
|---|---|
| Written procedure | The goal, input fields, steps, calculations, outputs, exceptions, and required approvals. Explain what changes each time and what stays fixed. |
| Video or ordered screenshots | Show the process from input to result. Name screenshots in order, such as `01-input.png` and `02-result.png`, and explain any omitted steps. |
| Sample input | A representative file the new plugin should handle. Do not include credentials or private business data. |

Select **Add attachments (+) > Upload images and files** and choose the
files. You can also drag them into the conversation or use **Attach cloud
files** for OneDrive, SharePoint, or Teams. Wait for all uploads to finish.

For an included business scenario, use its
[five-file Creator input bundle](https://github.com/boddev/cowork-process-creator/blob/main/CONTRIBUTING.md#keep-evaluation-answers-out-of-creators-input).
The expected answers and extra test cases are for evaluating the result,
not for creating the plugin.

### Copy and adapt this authoring prompt

Adapt the goal, parameters, and data description before sending:

```text
Use create-process-plugin to turn my attached procedure and demonstration
into a reusable Microsoft Copilot Cowork plugin.

Goal: [describe the repeatable result I want].

Make the input file, reporting period, and output filename configurable.
Ask about missing or conflicting rules. Tell me if you cannot read part
of the demonstration, rather than guessing.

This is a file-only process using synthetic data. Do not install software,
publish anything, call external services, or take business actions.

Return a native Microsoft v1.28 plugin ZIP, a check report, an editable
creation-source bundle, and a prompt for running the plugin on new inputs.
If required publisher details or capabilities are missing, explain what
is needed and keep an editable draft.
```

For a connected workflow, replace the file-only statement with the real
connection requirements. Follow your organization's rules for access;
never put passwords or tokens in the prompt.

Answer Creator's questions about rules, rounding, dates, or output layout
before accepting the design. If Cowork cannot read the video, provide
ordered screenshots instead.

## 4. Review and download the result

Check that the proposed plugin follows your rules, handles new input values,
explains exceptions, and produces all the files you need.

**To build the requested Microsoft plugin**, Creator needs an approved app
ID, publisher name, and website/privacy/terms URLs. Get these from the person
responsible for publishing the plugin; do not make them up. If they are
unavailable, save the work as a draft.

Find the generated files in the right-side **Output folder** and download
them:

| File | What to do with it |
|---|---|
| **Plugin ZIP** | Install this in the next step. Ask Creator for its exact filename and the skill name to use. |
| **Creation-source bundle** | Save this to edit the plugin later. It is not an installable plugin. |
| **Check report and run instructions** | Read the limitations and use the supplied prompt to test the plugin with new data. |

Download the plugin ZIP individually if possible. If you use **Download All**,
extract that outer archive and find the plugin ZIP inside. **Upload the
inner plugin ZIP, not the Download All archive or creation-source bundle.**

If Creator cannot build a ZIP, save the files it has created and resolve
the reported problem before continuing. A completed build still needs to
be installed and tested in Cowork.

## 5. Install and run your generated plugin

1. Repeat [the upload steps](#upload-the-package), using your **new plugin
   ZIP** in place of `creator.zip`.
2. Confirm it appears under **Installed**, then select **New task**.
3. In **Sources & Skills**, turn **Creator off** and your **new plugin on**.
   Leave any built-in Cowork capabilities it needs enabled.
4. Attach only the new input files the plugin needs, not the original
   demonstration or creation-source bundle.
5. Send the run prompt supplied with the plugin. Use its actual skill name
   and a new output filename.
6. Open the results and compare them with what you expected, including
   calculations, missing-data handling, and exceptions.

A report plugin's prompt might look like this. Replace the skill name and
use parameters supported by your plugin:

```text
Use [generated-skill-name] with the newly attached input file.
Use reporting period 2026-10 and write a new file named october-review.md.
Validate the inputs first and tell me about any missing required fields.
```

**You are done when** the new plugin produces the right result without
Creator or the original demonstration. Keep the ZIP and test results so
you can compare later versions.

If the workflow uses an external service, complete the connection steps
shown by Cowork and review any action before approving it. Use test data
for the first run.

## Continue editing later

Keep the creation-source bundle and your original demonstration. The bundle
saves the authored instructions and code, not the original recording or
your account connections.

To make changes, start a new task, enable Creator, attach the bundle, and ask:

```text
Use create-process-plugin to resume this creation-source bundle into a new
project. Preserve my existing edits. Recheck current capabilities and ask
before changing the rules or resolving conflicting edits. Do not overwrite
the original bundle.
```

Creator may need the original files again and will recheck which tools and
connections are available. Keep the previous bundle until you have reviewed
and tested the updated plugin.

## Troubleshooting

| What you see | What to do |
|---|---|
| **Cowork is missing.** | Check that you are using the right account. Ask IT about the [access and billing requirements](https://learn.microsoft.com/en-us/microsoft-365/copilot/cowork/cowork-admin-governance). |
| **There is no Upload plugin button.** | Open **Customize > Plugins**, not Skills or the attachment picker. If it is still missing, ask IT whether custom uploads are permitted. |
| **Cowork rejects the ZIP.** | Use the original `creator.zip` download or the actual generated plugin ZIP, not a source download or Download All archive. Creator's preview format is converted automatically. Keep the error message and package version if you need help from the publisher. |
| **Publishing stays in progress.** | Check Installed and Discover before uploading again. If the outcome is still unclear, contact your administrator or the publisher rather than repeatedly publishing copies. |
| **The plugin is installed but not used.** | Enable it in **Sources & Skills**, start a new task, and name its skill. Creator's entry skill is `create-process-plugin`; your generated plugin has its own skill name. |
| **The video cannot be read.** | Provide ordered screenshots with short captions explaining missing steps. |
| **Creator returns a draft without a plugin ZIP.** | Read what is missing: publisher details, an unanswered question, or a required Cowork capability. Save the draft and resolve that issue before building again. |
| **A workbook or connected action is missing.** | Check that Cowork has the needed capability or connection. Calculating figures is not the same as creating an Excel workbook; the workflow may need both. |
| **The plugin still needs Creator or the old recording.** | Ask Creator to add the missing instructions or supporting files, then test the updated plugin in a fresh task. |

## Further reading

| Need | Reference |
|---|---|
| Release details | [Creator v0.2.1 preview](https://github.com/boddev/cowork-process-creator/releases/tag/v0.2.1) |
| Cowork basics | [Get started with Cowork](https://learn.microsoft.com/en-us/microsoft-365/copilot/cowork/get-started) |
| Uploading and sharing | [Customize Cowork](https://learn.microsoft.com/en-us/microsoft-365/copilot/cowork/cowork-customize#upload-a-plugin-package) |
| Managing plugins and connections | [Use plugins with Cowork](https://learn.microsoft.com/en-us/microsoft-365/copilot/cowork/cowork-plugins) |
| Contributing an example | [Contribution guide](https://github.com/boddev/cowork-process-creator/blob/main/CONTRIBUTING.md) |
| Building packages from source | [Developer packaging guide](https://github.com/boddev/cowork-process-creator/blob/main/docs/MICROSOFT_PACKAGING.md) |
