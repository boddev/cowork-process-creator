# Native continuation after the desktop lock

N00 is **not complete**. Source implementation may continue provisionally
offline, but native acceptance, independent invocation and scheduling cannot.
Do not use a shell, alternate browser, sign-in change or other workaround to
bypass the locked Windows session or Computer Use's fail-closed response.

Last observed native actions, in order:

1. Cowork Process Creator was confirmed enabled.
2. Only that Creator was disabled and its toggle verified off. Unrelated
   plugins were preserved.
3. The exact downloaded `ready-items.zip` was selected.
4. **Only you** was verified in the native Publish dialog.
5. Publish was clicked once. The last observable state was **Publishing...**.

The output publication result is **unknown**, not failed and not Installed.
No fresh independent output task was started. The local 4/1/27.78 result is
not a substitute.

After the user normally unlocks the desktop, the native operator must inspect
the full Installed list and the relevant plugin detail before considering a
repeat publication. If the output is present, do not publish again. If absent,
first reconcile any still-pending operation or explicit failure. Preserve
native scope, account and unrelated plugin settings.

Only after output acceptance is observed, start a fresh native conversation
with the output skill and `examples\n00\input-new.json`, reporting month
2026-09 and a new Markdown filename. Keep the Creator inactive and original
procedure/video absent. Invoke the output helper through the skill using
`--input`, **`--month`**, and `--output`. Retrieve the actual report and compare
its rows/counts/total, without providing the expected result in the prompt.

The original output SHA256 is
`15d75761c98a1a20818a86ae6a1ec2e96bd83de92fdd4d08184ba6647adf7419`.
Expected evaluator-only result: four included, one excluded, total 27.78.
Direct canonical v1.28 acceptance still requires real publisher metadata;
native scheduling and broader media behavior remain separate unobserved gates.

Expanded v0.2.x artifacts are provisional offline candidates. They inherit
none of the installation or execution claims belonging to the original
v0.1.0 proof artifacts.
