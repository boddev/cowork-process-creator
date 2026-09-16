---
name: build-output-plugin
description: "Check, assemble and package a revisioned Creator project as a native Microsoft Copilot Cowork v1.28 plugin using the bundled toolkit. Use for runtime probing, JSON contracts, coverage and hash checks, approved publishing metadata, source checkpoints, verified resume and edit-preserving corrections. Never substitute a Claude-compatible manifest."
---

# Build and preserve a Creator project

Read `references\project-contract.md` before writing project files or command
arguments. Read `references\target-rules.md` before choosing a package target,
composing source metadata or declaring connections. These are the canonical
contracts; do not improvise fields, commands or undocumented manifest keys.

## Resolve this skill's own resources

Locate these companions through the actual native skill-resource listing:

- `scripts\creator_project.py`: project checks, assembly, builds and source
  checkpoint/resume/merge operations.
- `scripts\creator_builder.py`: the lower-level source subset checker and
  ZIP builder, including the minimal `probe`.
- `scripts\project_contracts.py`: the project contract implementation used
  by the sibling toolkit.

Keep the modules together in this skill. Do not use cross-skill imports,
developer paths, a separately installed CLI or newly improvised ZIP code.
Resolve filesystem separators for the actual host; JSON package paths use
the ZIP-style paths required by the contract.

Invoke the actual bundled builder's `probe` with the interpreter already
provided by Cowork. Preserve its real output. A probe measures this runtime
only, not media understanding, business access, host acceptance or scheduling.
If the required runtime is absent, stop this build path and return source
and the exact blocker without installing anything. Share available authored
native files; do not claim a verified checkpoint or ZIP was produced when
the toolkit could not execute.

## Use the project CLI, not a packaging shortcut

The following are argument shapes for `creator_project.py`, not a requirement
for an end user to install or run Python:

```text
init --project PATH --id ID --title TITLE --purpose PURPOSE
check --project PATH [--report NEW_JSON]
assemble --plan JSON --output NEW_CANDIDATE_DIR
build --project PATH --output NEW_ZIP --report NEW_JSON --target cowork-v1.28 --metadata APPROVED_JSON
checkpoint --project PATH --output NEW_ZIP
resume --bundle ZIP --output NEW_PROJECT_DIR
merge --base ZIP --current PROJECT --proposed PROJECT --output NEW_PROJECT
```

Use actual supplied native workspace paths. New project/candidate/output
paths must not exist; preserve prior revisions and reports.

1. **Initialize or verify.** Initialize only a new project. For existing
   source, check it or resume a verified source bundle rather than resetting
   files. Preserve observed input/source identifiers and hashes.
2. **Assemble.** Accept only the contract's assembly plan. `plugin` is the
   supported plugin specification; `skills` contains name, description,
   body and companions; companion/tool entries contain path and content.
   Do not fetch resources, install packages or execute supplied source.
3. **Check the whole project.** Validate evidence consistency, questions,
   current decisions, parameters/control flow, native mappings, every step's
   actual candidate bindings and evaluation coverage. Obtain the current
   evidence/blueprint/candidate fingerprints from this check. Changed source
   facts or observations invalidate blueprint `evidence_sha256`; merely
   relabeling unchanged access from `attached` to `recorded` does not.
4. **Evaluate and recheck.** Have Cowork perform permitted synthetic checks.
   Record actual outcomes in `evaluation-results.json` against
   `blueprint_revision`, `blueprint_sha256` and `candidate_sha256` from the
   current check. Recheck after changes; stale or missing evaluations are
   not silently passed or repaired by copying new hashes onto old results.
5. **Build.** Use the project `build` only when its coherence/coverage gates
   allow it. Treat diagnostics as failures to address, not reasons to omit
   requested steps or falsify host availability/user decisions.

The lower-level `creator_builder.py` commands `validate` and `build` inspect
and package the supported source subset. They cannot substitute for project
evidence/coverage checks or bypass a failed project build.

## Produce the Microsoft Cowork package

Use only **`cowork-v1.28`**: a root `manifest.json` with the official v1.28
schema and `agentSkills` declarations, icons and actual referenced resources.
Require supplied approved app identity and publisher/website/privacy/terms
metadata. Never invent legal URLs, registrations, endpoints or permissions.

Do not generate `.claude-plugin/plugin.json` or rely on host conversion.
If metadata or a necessary native binding is missing, return a clearly
incomplete source checkpoint and the precise gap, not an alternative-format
plugin or a fabricated native-ready ZIP.

The toolkit checks its emitted subset, not the full Microsoft schema, and
is not a sandbox. Synthetic profiles remain Draft even when local contract
checks succeed. Build plans, reports and readiness JSON are records, not
permissions or distributed execution authority.

## Checkpoint, resume and preserve corrections

Export a `checkpoint` before relying on a later conversation. It contains
authored project knowledge/code and an inventory of hashes; raw attachments
and publishing secrets are excluded by default. Return it through native
files. An ephemeral workspace alone is not persistent storage.

`resume` verifies the complete inventory, hashes and archive paths before
creating a new project. `merge` performs conservative file-level three-way
comparison against a base bundle, with the proposal advancing the base
revision once. Different concurrent edits to the same file produce conflicts
and no output project. Do not overwrite the user's current files.

Resume/merge preserve prior host/input/build/evaluation/coverage records
byte-for-byte under content-hashed `history`, reset live capability and
connection availability to unverified, relabel attached sources as recorded,
archive old evaluations and return to review. Unchanged historical notes
remain usable without asserting live reattachment. Reattach/reobserve only
as needed for uncertain or changed evidence; recheck actual native support
and refresh evaluations before packaging. Historical metadata provenance
does not supply current connection `availability_evidence`. History is not
inherited approval or fresh evidence of execution.

## Return artifacts and limitations

Return the actual new ZIP, build/check diagnostics and creation-source
bundle, or only source plus blockers when packaging is not possible. Identify
the plugin ZIP separately from a source-resume ZIP or outer Download All
archive. Do not return an old/partial ZIP as this build's success.

Route handoff and correction review to `review-output-plugin`. Keep Draft,
Package built, Installed, Manually exercised and Schedule exercised separate;
no offline action attests installation, independent invocation or scheduling.
Do not publish, change accounts/auth/EULAs, use production data or perform
native/remote actions outside the actual authorization.
