# Emitted package subset and native gates

Rules snapshot: 2026-09-14. Target: **Microsoft Copilot Cowork, M365 Unified
App Manifest v1.28**.

Product rule confirmed by the user: generated plugins must use Microsoft's
native `manifest.json` and syntax, not a Claude Cowork/source manifest.
The only plugin build target is `cowork-v1.28`. Missing approved publishing
metadata blocks the package; it never selects another format. A source-resume
archive is useful editable data, not an installable plugin.

## First-party sources

- https://learn.microsoft.com/en-us/microsoft-365/copilot/cowork/cowork-plugin-development
- https://developer.microsoft.com/json-schemas/teams/v1.28/MicrosoftTeams.schema.json
- https://learn.microsoft.com/en-us/microsoft-365/copilot/cowork/cowork-customize
- https://learn.microsoft.com/en-us/microsoft-365/copilot/cowork/use-cowork
- https://learn.microsoft.com/en-us/microsoft-365/copilot/cowork/cowork-faq
- https://learn.microsoft.com/en-us/microsoft-365/copilot/cowork/cowork-admin-governance

No API call, runtime download or separate service is required by the toolkit.
The schema URL is an identification/reference string, not a runtime validator.

## Source format

A source directory contains `plugin-spec.json`, `skills`, and optionally
`tools`. Unexpected root files fail; keep raw attachments and generated
reports outside candidate source.

`plugin-spec.json` has exactly: `schema_version`, `name`, `title`, `version`,
`summary`, `description`, `skills`, `connectors`.

| Field | Emitted subset |
|---|---|
| schema_version | `creator-plugin-1` |
| name | 1-64 lowercase alphanumeric/hyphen characters, no repeated/edge hyphens |
| title | 1-30 single-line characters |
| version | Three decimal components, without redundant leading zeros |
| summary | 1-80 single-line characters |
| description | 1-4000 characters, including ordinary multiline prose |
| skills | 1-20 unique kebab-case skill folder names |
| connectors | 0-10 remote connector definitions; no implicit service creation |

Legacy `n00-1` source remains accepted with its original seven fields and
without connectors. See the legacy source-format reference only when
working with an old source project; do not downgrade a current project.

Each skill has its own `SKILL.md`. The emitted YAML subset is exactly an
opening delimiter, unquoted matching name, JSON-quoted single-line
description, and closing delimiter; follow it with nonempty Markdown.
Name is 1-64 characters and description 1-1024. Other YAML forms are not
silently reinterpreted.

Companions are UTF-8 Python, JSON, Markdown or text in this initial source
subset. Binary/template media beyond generated root icons is not supported
by this checker; this is a Creator subset limitation, not a claim about all
Cowork-supported companion formats.

## Limits, paths and dependencies

Per skill: at most 20 companions, each at most 5 MB and at most 10 MB total.
The toolkit uses conservative decimal byte ceilings. The native companion
download timeout is documented as 15 seconds; small source does not prove
that a particular native download succeeded.

Additional local safety ceilings: 1 MB per SKILL.md, 32 MB candidate/source
payload, 5 MB per authoring JSON file, nesting at most 32, and at most 1000
source-bundle files. These are not claimed whole-plugin platform limits.

Package paths are relative, at most 256 characters in this subset. Reject
traversal, backslashes, null bytes, hidden path components, Windows reserved
names, trailing spaces/dots, unsafe characters, symlinks/junctions and
case-insensitive collisions. ZIP members use slash separators independent
of the operating system. Actual filesystem arguments use native syntax.

The Python checker permits a small standard-library allowlist and local
modules present in the same packaged directory. It rejects missing,
third-party, cross-skill and relative package imports, dynamic evaluation,
and bundled modules shadowing the standard library. This is not a sandbox
or proof of arbitrary-code safety. Cowork must inspect generated code and
exercise it with synthetic data under native controls.

Use normal file-based Python invocation so same-directory modules can load.
For developer isolation, `-E -s -B` keeps the script directory while ignoring
environment/user-site additions and avoiding bytecode side files. Python
`-I` removes the script directory too and is not the correct launch mode
for a multi-file sibling-module package.

## Real remote connector source

A connector has exactly `id`, `display_name`, `description`, `server_url`,
`authorization`, `tools_file`, `provenance`.

The ID is a local kebab-case alias, at most64 characters. Display name is
at most128, description at most4000. Server URL is real supplied HTTPS,
without credentials, query/fragment, local/example domains or invented
future services. Provenance has `kind` (`user-supplied` or `native-discovery`)
and a nonempty `reference` to its actual source. This is not proof that the
connection exists, is available in Cowork, or has sign-in/approval authority.

`tools_file` points to a packaged JSON file below the candidate's `tools`
directory. It contains exactly a `tools` array. Each actual tool has
`name`, `description`, `inputSchema`; optional supported metadata is
`title`, `outputSchema`, `annotations`, `execution`. Tool names are unique;
descriptions may be multiline. Titles and known annotation hints are typed.
Input schema must describe an object; required names must be declared
properties and local schema references must resolve.

Preserve actual metadata. The checker does not treat JSON Schema default
annotations as instance values, invent missing required/enum constraints,
or reject legitimate nullable output-schema type arrays. It does not claim
full arbitrary JSON Schema/MCP conformance. Unsupported fields or external
schema references fail explicitly instead of being silently projected away.

Authorization subset:

- `None`: no reference ID and no embedded credentials.
- `OAuthPluginVault`: real supplied registration `referenceId`, not a
  provider client ID, guessed string, or automatically generated placeholder.
- Source `DynamicClientRegistration`: emit no authorization object, using
  the documented native DCR path only for an actually suitable existing
  endpoint. Never fabricate a registration. The explicit manifest DCR
  object/reference variant is not emitted by this subset.

API-key auth is rejected: its schema enum is not sufficient evidence of
runtime Cowork support. Native setup/approval remains the platform's job.

Every emitted v1.28 remote connector gets `mcpToolDescription.file`, and the
referenced actual tool JSON travels in the archive. Use real supplied metadata
or reuse a verified existing native connection. Do not drop required bindings,
invent conversion fields or switch to another host's manifest.

## Publishing metadata and package claims

Canonical packaging requires a separate supplied object with exactly
`app_id` and `developer`. App ID is a non-nil canonical UUID, not an OAuth
registration. Developer has `name` (1-32), `websiteUrl`, `privacyUrl`,
`termsOfUseUrl`. URLs must be real approved HTTPS. Offline checks verify
syntax/common placeholders, not ownership, legal adequacy or consent.
No approved publishing metadata is bundled by default.

Native output has a root `manifest.json`, generated 192x192 color and 32x32
outline PNGs, skill folders and optional descriptor files. Emit only the
supported v1.28 properties, not `packageName` or invented schedule fields.
The root manifest identifies `manifestVersion: "1.28"`, the official v1.28
schema, supplied app/developer identity, and `agentSkills[].folder`. It must
not be replaced by `.claude-plugin/plugin.json`, a root portable `plugin.json`
or a `devPreview` manifest. Historical compatible-source artifacts are not
native Microsoft package examples and are not regenerated by this toolkit.
Use short, descriptive ZIP filenames conservatively. A filename choice is
not itself evidence of native acceptance.

Draft, Package built, Installed, Manually exercised and Schedule exercised
are separate claims. Structural success does not establish host acceptance.
New expanded candidates inherit no native claims from earlier artifacts.

## Current host and user authorization

Determine media, file, script and connection support in the current host.
An existing permitted decoder is optional; no decoder installer/dependency
belongs in the Creator baseline. Describe actual inspected views and
limitations instead of generalizing a sample to universal video, narration
or all-frame support.

Do not inherit another session's blocked state, permissions or acceptance
claims. A downloadable package request does not automatically authorize
installation/publication or account changes. If an authorized native action
has an uncertain outcome, inspect its actual current state before retrying.
Never substitute a local result, lower permissions, or add an access workaround.
