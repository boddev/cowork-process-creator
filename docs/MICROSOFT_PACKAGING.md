# Native Microsoft Copilot Cowork packaging

This guide is for developers building plugin packages. To install Creator,
follow the [user guide](user-guide.md).

The builder targets Microsoft's native app package format, using
`cowork-v1.28`. See the
[Microsoft developer guide](https://learn.microsoft.com/en-us/microsoft-365/copilot/cowork/cowork-plugin-development)
and [M365 v1.28 schema](https://developer.microsoft.com/json-schemas/teams/v1.28/MicrosoftTeams.schema.json).
It validates the subset it generates, not every feature in the Microsoft schema.

## Required ZIP layout

The archive has `manifest.json` at its root, with
`manifestVersion: "1.28"`, the official `$schema`, app ID, developer details,
name/description, `icons`, `accentColor`, and `agentSkills[].folder`.
The declared folders contain `SKILL.md` and all resources needed by each
skill. Root `color.png` is 192x192; `outline.png` is 32x32.

Skills use the shared Agent Skills standard: a `SKILL.md` file with YAML
frontmatter, plus any supporting files.

Optional real remote connectors are declared in `agentConnectors`; every
`remoteMcpServer` includes `mcpToolDescription.file` pointing to its included
tool-description JSON. Do not invent endpoints, tool names or registrations.

A `.claude-plugin/plugin.json`, `.cursor-plugin` or `devPreview` manifest
does not satisfy this native output format. The builder does not convert
to another format when required information is missing.

## Publishing metadata is a real prerequisite

Supply a JSON object containing exactly:

| Field | Required value |
|---|---|
| `app_id` | A supplied non-nil canonical UUID for this independently installed app |
| `developer.name` | Approved publisher name, 1-32 characters |
| `developer.websiteUrl` | Real approved HTTPS website |
| `developer.privacyUrl` | Real approved HTTPS privacy statement |
| `developer.termsOfUseUrl` | Real approved HTTPS terms |

Use details approved for the publisher. Do not substitute test identities
or someone else's legal URLs. The builder does not register an app, create
credentials, or grant account permissions.

For a single candidate, use the owning build skill's bundled project CLI:

```text
creator_project.py build --project PROJECT --output NEW_PLUGIN.zip --report NEW_REPORT.json --metadata APPROVED_METADATA.json
```

Its default and only target is `cowork-v1.28`. The lower-level
`creator_builder.py build --source SOURCE ... --metadata APPROVED_METADATA.json`
has the same native-only requirement but checks source structure rather than
project evidence/coverage. Do not bypass a failed project check with it.

For the developer release plus its three examples:

```powershell
python -B scripts\build_release.py --metadata-dir .local\publishing
```

That directory must contain `cowork-process-creator.json`, `cost-report.json`,
`priority-checklist.json`, and `exception-ledger.json`, each using the object
above and a distinct app ID. All are checked before building. Missing/invalid
metadata produces an explicit failure and no replacement-format package.
The directory is local-only and should not contain credentials.

## Current native-build status

The v0.3.0 native release build still needs approved publishing metadata.
See [native-manifest-status.json](native-manifest-status.json) for its status.

A successful build creates a package; it does not install or test it in
Cowork. Upload **the ZIP you built** using the
[installation steps](user-guide.md#upload-the-package), then test the
installed plugin in a fresh task with new inputs.
