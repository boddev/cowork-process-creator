# Native Microsoft Copilot Cowork packaging

The current Creator emits **Microsoft Copilot Cowork packages**, not Claude
Cowork plugins. Starting with source v0.3.0, both package build APIs/CLIs and
the release builder require `cowork-v1.28`. They reject alternative targets
instead of silently switching formats.

The rule comes from the user's explicit requirement and the
[Microsoft Cowork developer guide](https://learn.microsoft.com/en-us/microsoft-365/copilot/cowork/cowork-plugin-development).
The emitted subset identifies the
[M365 v1.28 schema](https://developer.microsoft.com/json-schemas/teams/v1.28/MicrosoftTeams.schema.json).
This is not a claim to validate every arbitrary Microsoft schema feature.

## Required ZIP layout

The archive has `manifest.json` at its root, with
`manifestVersion: "1.28"`, the official `$schema`, app ID, developer details,
name/description, `icons`, `accentColor`, and `agentSkills[].folder`.
The declared folders contain `SKILL.md` and all resources needed by each
skill. Root `color.png` is 192x192; `outline.png` is 32x32.

`SKILL.md` and its YAML frontmatter remain correct: Microsoft uses the shared
Agent Skills standard. The package manifest and supported capabilities are
what distinguish the Microsoft package from a Claude plugin.

Optional real remote connectors are declared in `agentConnectors`; every
`remoteMcpServer` includes `mcpToolDescription.file` pointing to its included
tool-description JSON. Do not invent endpoints, tool names or registrations.

A `.claude-plugin/plugin.json`, `.cursor-plugin` or `devPreview` manifest
does not satisfy this output contract. The older v0.2.1 compatible-source
preview and native-prototype downloads remain unchanged historical artifacts;
they are not newly generated Microsoft manifest packages.

## Publishing metadata is a real prerequisite

Supply a JSON object containing exactly:

| Field | Required value |
|---|---|
| `app_id` | A supplied non-nil canonical UUID for this independently installed app |
| `developer.name` | Approved publisher name, 1-32 characters |
| `developer.websiteUrl` | Real approved HTTPS website |
| `developer.privacyUrl` | Real approved HTTPS privacy statement |
| `developer.termsOfUseUrl` | Real approved HTTPS terms |

The public GitHub repository is not implicit approval to invent legal
documents or use somebody else's privacy/terms. No metadata, secrets, OAuth
registration or consent is generated automatically. Unit tests use temporary
syntax fixtures only; those values are never release metadata.

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

## Current status

No approved publishing metadata has been supplied for a v0.3.0 release. The
code path is implemented, but no real native-ready release package is
claimed. Preserve useful editable source/checkpoints while this is blocked.

The 15 enterprise scenarios have mock data, baseline outputs and videos, but
**zero scenario plugins have been generated or installed in native Cowork**.
Their native access gate is separately blocked. Future generation prompts
explicitly require the Microsoft manifest, and the scenario import gate
rejects Claude-layout and wrong-version packages before comparison.

`evals/n00.json` preserves the original historical proof prompts, not current
packaging instructions. Active authoring prompts use v0.3.0;
`evals/intent-case-status.json` explicitly supersedes the original disclosed
intent case that allowed compatible-source export, without rewriting its
historical bytes or claiming a new model run.

Passing local manifest/source checks is not actual Cowork acceptance,
independent execution, or scheduling. Record those stages separately once
the approved native tools and accessible session are available.
