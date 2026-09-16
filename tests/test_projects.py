from __future__ import annotations

import copy
import hashlib
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
import uuid
import zipfile
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import example_projects as examples

b, c, p = examples.b, examples.c, examples.p
LEARN = ROOT / "examples" / "offline" / "public-learn" / "learn-mcp-tools.json"


class ProjectTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture_temp = tempfile.TemporaryDirectory(prefix="creator-contract-fixture-")
        cls.base = Path(cls.fixture_temp.name) / "base"
        checked = examples.create_project(cls.base)
        if not checked["ready"]:
            raise AssertionError(checked["blockers"])

    @classmethod
    def tearDownClass(cls):
        cls.fixture_temp.cleanup()

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="creator-contract-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.project = self.root / "project"
        shutil.copytree(self.base, self.project)

    def doc(self, name):
        return b.read_json(self.project / name)

    def save(self, name, value):
        (self.project / name).write_bytes(b.json_bytes(value))

    def check(self):
        return c.validate_project(self.project)

    def codes(self):
        return {item["code"] for item in self.check()["blockers"]}

    def blueprint(self, mutate):
        doc = self.doc("workflow-blueprint.json")
        mutate(doc)
        self.save("workflow-blueprint.json", doc)

    def refresh_evidence(self):
        self.blueprint(lambda doc: doc.update(evidence_sha256=c.evidence_fingerprint(self.doc("inputs.json"), self.doc("observations.json"))))

    def refresh_results(self):
        checked = self.check()
        results = self.doc("evaluation-results.json")
        results.update(blueprint_revision=checked["blueprint_revision"], blueprint_sha256=checked["blueprint_sha256"], candidate_sha256=checked["candidate_sha256"])
        self.save("evaluation-results.json", results)

    def confirm_transform(self):
        observations = self.doc("observations.json")
        observations["questions"].append({"id": "reviewed-rule", "text": "Confirm this synthetic unit-test rule.", "evidence_ids": ["document-rules"]})
        self.save("observations.json", observations)
        self.blueprint(lambda doc: doc["steps"][1].update(decision_id="reviewed-answer"))
        self.refresh_evidence()
        blueprint = self.doc("workflow-blueprint.json")
        decisions = self.doc("decisions.json")
        decisions.update(
            blueprint_revision=blueprint["revision"],
            blueprint_sha256=hashlib.sha256((self.project / "workflow-blueprint.json").read_bytes()).hexdigest(),
            items=[{"id": "reviewed-answer", "question_id": "reviewed-rule",
                    "answer": "Confirmed only for this synthetic fixture.", "outcome": "confirmed", "source": "user"}],
        )
        self.save("decisions.json", decisions)
        self.refresh_results()

    def known_mutation_fixture(self):
        # Deliberately changed hint for a type/gate test, not a claim about Learn.
        tools = copy.deepcopy(json.loads(LEARN.read_bytes())["tools"])
        tools[0]["annotations"]["readOnlyHint"] = False
        host = self.doc("host-profile.json")
        host["capabilities"].append({"id": "business.tool", "status": "available", "evidence": "Synthetic unit-test capability only."})
        host["connections"] = [{
            "id": "mutation-fixture", "mode": "existing-native", "status": "available",
            "native_id": None, "tools": tools,
            "provenance": {"kind": "user-supplied", "reference": "Hypothetical mutated metadata for a unit test, not the public snapshot."},
            "availability_evidence": "Synthetic unit-test assumption only; no native connection.",
        }]
        self.save("host-profile.json", host)
        self.blueprint(lambda doc: doc["steps"][1].update(
            capability="business.tool", connection_id="mutation-fixture",
            tool_name="microsoft_docs_search", effect="local-write", approval="none", decision_id=None))
        self.refresh_results()

    def metadata(self):
        # Syntax fixture only; not approved publisher metadata and never shipped.
        path = self.root / "publishing.json"
        path.write_bytes(b.json_bytes({
            "app_id": str(uuid.uuid4()), "developer": {"name": "Syntax fixture only",
            "websiteUrl": "https://www.microsoft.com", "privacyUrl": "https://privacy.microsoft.com/privacystatement",
            "termsOfUseUrl": "https://www.microsoft.com/servicesagreement"},
        }))
        return path

    def add_remote(self):
        candidate = self.project / "candidate"
        (candidate / "tools").mkdir()
        (candidate / "tools" / "learn.json").write_bytes(LEARN.read_bytes())
        spec = b.read_json(candidate / "plugin-spec.json")
        spec["connectors"] = [{
            "id": "microsoft-learn", "display_name": "Microsoft Learn", "description": "Public documentation metadata fixture.",
            "server_url": "https://learn.microsoft.com/api/mcp", "authorization": {"type": "None"},
            "tools_file": "tools/learn.json", "provenance": {"kind": "user-supplied", "reference": "Public tools/list snapshot 2026-09-12T01:43:37Z; not a Cowork connection observation."},
        }]
        (candidate / "plugin-spec.json").write_bytes(b.json_bytes(spec))
        return spec

    def test_ready_fixture_still_has_no_native_claims(self):
        report = self.check()
        self.assertTrue(report["ready"])
        self.assertEqual(report["host_context"], "offline-synthetic")
        self.assertEqual(report["status"], "Draft")
        self.assertEqual(report["native_acceptance"], "unverified")
        self.assertEqual(report["step_order"], ["read-input", "transform", "deliver"])

    def test_empty_init_has_explicit_blockers_and_never_overwrites(self):
        destination = self.root / "new"
        p.init_project(destination, "new-project", "New project", "A deliberate draft.")
        result = c.validate_project(destination)
        self.assertFalse(result["ready"])
        self.assertIn("missing-procedure", {row["code"] for row in result["blockers"]})
        with self.assertRaises(b.BuildError):
            p.init_project(destination, "another", "Wrong", "No overwrite.")

    def test_source_hash_and_observation_edits_invalidate_support(self):
        inputs = self.doc("inputs.json")
        inputs["sources"][0]["sha256"] = "a" * 64
        self.save("inputs.json", inputs)
        self.assertIn("stale-observation", self.codes())
        self.assertIn("stale-blueprint-evidence", self.codes())
        observations = self.doc("observations.json")
        observations["items"][0]["source_sha256"] = "a" * 64
        observations["items"][0]["text"] += " Changed rule."
        self.save("observations.json", observations)
        self.assertNotIn("stale-observation", self.codes())
        self.assertIn("stale-blueprint-evidence", self.codes())

    def test_screenshot_order_and_fake_timing_rejected(self):
        inputs = self.doc("inputs.json")
        inputs["sources"][1]["order"] = 3
        self.save("inputs.json", inputs)
        with self.assertRaisesRegex(b.BuildError, "contiguous"):
            self.check()
        inputs["sources"][1]["order"] = 1
        self.save("inputs.json", inputs)
        observations = self.doc("observations.json")
        observations["items"][1]["locator"]["seconds"] = 2.5
        self.save("observations.json", observations)
        with self.assertRaisesRegex(b.BuildError, "non-video"):
            self.check()

    def test_inferences_do_not_become_observed_rules(self):
        observations = self.doc("observations.json")
        for item in observations["items"]:
            item["kind"] = "inferred"
        self.save("observations.json", observations)
        self.refresh_evidence()
        self.assertIn("unobserved-demonstration", self.codes())
        self.assertIn("unconfirmed-rule", self.codes())
        self.assertIn("inferred-control-flow", self.codes())

    def test_unresolved_and_stale_user_decisions(self):
        observations = self.doc("observations.json")
        observations["questions"].append({"id": "rule-question", "text": "Which conflicting rule is intended?", "evidence_ids": ["document-rules"]})
        self.save("observations.json", observations)
        self.refresh_evidence()
        self.assertIn("unresolved-question", self.codes())
        result = self.check()
        decisions = self.doc("decisions.json")
        decisions.update(blueprint_sha256=result["blueprint_sha256"], items=[
            {"id": "rule-answer", "question_id": "rule-question", "answer": "Use the written rule.", "outcome": "confirmed", "source": "user"},
        ])
        self.save("decisions.json", decisions)
        self.assertNotIn("unresolved-question", self.codes())
        self.blueprint(lambda doc: doc.update(purpose="A changed purpose."))
        self.assertIn("stale-decisions", self.codes())
        decisions["items"][0]["source"] = "assistant"
        self.save("decisions.json", decisions)
        with self.assertRaisesRegex(b.BuildError, "expected one of user"):
            self.check()

    def test_business_writes_never_drop_native_approval(self):
        self.blueprint(lambda doc: doc["steps"][1].update(effect="business-write"))
        with self.assertRaisesRegex(b.BuildError, "native per-run"):
            self.check()
        self.blueprint(lambda doc: doc["steps"][1].update(approval="native-each-run"))
        self.assertIn("unconfirmed-business-write", self.codes())
        self.blueprint(lambda doc: doc.update(invocation_mode="native-schedule"))
        self.assertIn("scheduled-approval-gap", self.codes())

    def test_known_nonreadonly_business_tool_cannot_be_local_write(self):
        self.known_mutation_fixture()
        checked = self.check()
        self.assertFalse(checked["ready"])
        self.assertIn("effect-mismatch", {entry["code"] for entry in checked["blockers"]})
        self.assertEqual(self.doc("workflow-blueprint.json")["steps"][1]["effect"], "local-write")
        self.blueprint(lambda doc: doc["steps"][1].update(effect="read"))
        self.assertIn("effect-mismatch", self.codes())

    def test_known_mutator_needs_business_write_decision_and_native_approval(self):
        self.known_mutation_fixture()
        self.blueprint(lambda doc: doc["steps"][1].update(effect="business-write"))
        with self.assertRaisesRegex(b.BuildError, "native per-run"):
            self.check()
        self.blueprint(lambda doc: doc["steps"][1].update(approval="native-each-run"))
        self.assertIn("unconfirmed-business-write", self.codes())
        self.confirm_transform()
        self.assertTrue(self.check()["ready"])
        self.blueprint(lambda doc: doc.update(invocation_mode="native-schedule"))
        self.assertIn("scheduled-approval-gap", self.codes())

    def test_current_user_confirmation_can_support_condition_and_repeat_without_media_refs(self):
        self.blueprint(lambda doc: doc["steps"][1].update(
            condition={"expression": "Apply the current user-confirmed condition.", "evidence_ids": []}))
        self.blueprint(lambda doc: doc["steps"][1]["repeat"].update(evidence_ids=[]))
        self.confirm_transform()
        self.assertTrue(self.check()["ready"], self.check()["blockers"])
        self.blueprint(lambda doc: doc.update(purpose="Changed after the user confirmation."))
        self.assertIn("stale-decisions", self.codes())
        self.assertIn("missing-support", self.codes())

    def test_confirmation_does_not_hide_invalid_or_stale_control_references(self):
        self.confirm_transform()
        self.blueprint(lambda doc: doc["steps"][1].update(
            condition={"expression": "Confirmed condition.", "evidence_ids": ["unknown-observation"]}))
        decisions = self.doc("decisions.json")
        decisions["blueprint_sha256"] = hashlib.sha256((self.project / "workflow-blueprint.json").read_bytes()).hexdigest()
        self.save("decisions.json", decisions)
        with self.assertRaisesRegex(b.BuildError, "unknown evidence"):
            self.check()
        self.blueprint(lambda doc: doc["steps"][1]["condition"].update(evidence_ids=["document-rules"]))
        decisions["blueprint_sha256"] = hashlib.sha256((self.project / "workflow-blueprint.json").read_bytes()).hexdigest()
        self.save("decisions.json", decisions)
        inputs = self.doc("inputs.json")
        inputs["sources"][0]["sha256"] = "e" * 64
        self.save("inputs.json", inputs)
        self.assertIn("stale-support", self.codes())

    def test_unverified_runtime_desktop_and_unknown_connections_block(self):
        host = self.doc("host-profile.json")
        host["capabilities"][2]["status"] = "unverified"
        self.save("host-profile.json", host)
        self.assertIn("native-capability-gap", self.codes())
        self.blueprint(lambda doc: doc["steps"][1].update(capability="desktop.arbitrary"))
        self.assertIn("native-capability-gap", self.codes())
        self.blueprint(lambda doc: doc["steps"][1].update(capability="business.tool"))
        self.assertIn("connection-metadata-missing", self.codes())

    def test_loop_bounds_cycles_and_dependency_consumption(self):
        self.blueprint(lambda doc: doc["steps"][1]["repeat"].update(max_items=0))
        with self.assertRaisesRegex(b.BuildError, "1-10000"):
            self.check()
        self.blueprint(lambda doc: doc["steps"][1]["repeat"].update(max_items=10000))
        self.blueprint(lambda doc: doc["steps"][0].update(depends_on=["deliver"]))
        with self.assertRaisesRegex(b.BuildError, "cycle"):
            self.check()
        self.blueprint(lambda doc: doc["steps"][0].update(depends_on=[]))
        self.blueprint(lambda doc: doc["steps"][1].update(depends_on=[]))
        with self.assertRaisesRegex(b.BuildError, "prerequisite"):
            self.check()

    def test_constants_defaults_and_types_are_checked(self):
        self.blueprint(lambda doc: doc["constants"][0].update(classification="unknown"))
        self.assertIn("unclassified-value", self.codes())
        self.blueprint(lambda doc: doc["inputs"][0].update(default="demo.json"))
        self.assertIn("unjustified-default", self.codes())
        self.blueprint(lambda doc: doc["inputs"][0].update(type="integer", default=True))
        with self.assertRaisesRegex(b.BuildError, "declared type"):
            self.check()
        self.blueprint(lambda doc: doc["inputs"][0].update(type="date", default="2026-02-30"))
        with self.assertRaisesRegex(b.BuildError, "declared type"):
            self.check()

    def test_source_blueprint_changes_and_missing_results_invalidate_evaluations(self):
        helper = self.project / "candidate" / "skills" / "cost-report" / "scripts" / "main.py"
        helper.write_bytes(helper.read_bytes() + b"\n# A changed source revision.\n")
        self.assertIn("stale-evaluations", self.codes())
        self.refresh_results()
        self.assertNotIn("stale-evaluations", self.codes())
        self.blueprint(lambda doc: doc.update(purpose="Changed semantics without revision bump."))
        self.assertIn("stale-evaluations", self.codes())
        (self.project / "evaluation-results.json").unlink()
        self.assertIn("missing-evaluations", self.codes())

    def test_binding_resources_and_negative_case_coverage(self):
        self.blueprint(lambda doc: doc["bindings"][0]["files"].append("skills/cost-report/scripts/missing.py"))
        self.assertIn("missing-implementation", self.codes())
        self.blueprint(lambda doc: doc["bindings"][1].update(test_ids=["changed-input"]))
        self.assertIn("helper-negative-case", self.codes())
        self.blueprint(lambda doc: doc["bindings"][1]["files"].append("skills/other/helper.py"))
        with self.assertRaisesRegex(b.BuildError, "another skill"):
            self.check()

    def test_source_assembly_refuses_unsafe_or_invalid_plans_without_partial_output(self):
        plan = examples.candidate_plan("priority-checklist")
        path = self.root / "plan.json"
        plan["skills"][0]["companions"][0]["path"] = "../escape.py"
        path.write_bytes(b.json_bytes(plan))
        destination = self.root / "candidate"
        with self.assertRaises(b.BuildError):
            p.assemble_candidate(path, destination)
        self.assertFalse(destination.exists())
        plan = examples.candidate_plan("priority-checklist")
        plan["skills"][0]["companions"][0]["content"] = "def broken("
        path.write_bytes(b.json_bytes(plan))
        with self.assertRaisesRegex(b.BuildError, "syntax error"):
            p.assemble_candidate(path, destination)
        self.assertFalse(destination.exists())

    def test_project_build_is_deterministic_and_provisional(self):
        a, ar, b_path, br = [self.root / name for name in ("one.zip", "one.json", "two.zip", "two.json")]
        metadata = self.metadata()
        result = p.build_project(self.project, a, ar, b.TARGET, metadata)
        p.build_project(self.project, b_path, br, b.TARGET, metadata)
        self.assertEqual(a.read_bytes(), b_path.read_bytes())
        self.assertEqual(result["status"], "Draft")
        self.assertTrue(result["provisional_offline"])
        self.assertEqual(result["host_acceptance"], "unverified")
        with zipfile.ZipFile(a) as archive:
            self.assertIn("manifest.json", archive.namelist())
            self.assertNotIn(".claude-plugin/plugin.json", archive.namelist())
        with self.assertRaisesRegex(b.BuildError, "requires --metadata"):
            p.build_project(self.project, self.root / "native.zip", self.root / "native.json", "cowork-v1.28")
        self.assertFalse((self.root / "native.zip").exists())

    def test_project_cannot_fallback_to_claude_source_when_metadata_is_absent(self):
        package, report = self.root / "alternative.zip", self.root / "alternative.json"
        with self.assertRaisesRegex(b.BuildError, "native Microsoft Cowork"):
            p.build_project(self.project, package, report, "compatible-source")
        self.assertFalse(package.exists())
        self.assertFalse(report.exists())

    def test_check_cli_reports_blockers_nonzero(self):
        self.blueprint(lambda doc: doc.update(status="draft"))
        result = subprocess.run(
            [sys.executable, "-E", "-s", "-B", str(examples.TOOLKIT / "creator_project.py"),
             "check", "--project", str(self.project)],
            cwd=self.root, capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertFalse(json.loads(result.stdout)["ready"])

    def test_checkpoint_is_deterministic_and_does_not_contain_raw_evidence(self):
        first, second = self.root / "one-source.zip", self.root / "two-source.zip"
        p.checkpoint(self.project, first)
        p.checkpoint(self.project, second)
        self.assertEqual(first.read_bytes(), second.read_bytes())
        with zipfile.ZipFile(first) as archive:
            self.assertIn("checkpoint.json", archive.namelist())
            self.assertFalse(any(name.endswith((".png", ".mp4", ".webm")) for name in archive.namelist()))
            meta = json.loads(archive.read("checkpoint.json"))
            self.assertEqual(set(meta["files"]), set(archive.namelist()) - {"checkpoint.json"})
            self.assertEqual(meta["status"], "Draft")

    def test_resume_preserves_code_and_archives_not_inherits_claims(self):
        bundle, destination = self.root / "source.zip", self.root / "resumed"
        original = p.snapshot_project(self.project)[0]
        p.checkpoint(self.project, bundle)
        result = p.resume(bundle, destination)
        self.assertTrue(result["requires_host_recheck"])
        self.assertEqual(b.read_json(destination / "host-profile.json")["context"], "unverified")
        self.assertEqual(b.read_json(destination / "build-state.json")["phase"], "review")
        self.assertTrue(all(source["availability"] == "recorded" for source in b.read_json(destination / "inputs.json")["sources"]))
        self.assertFalse((destination / "evaluation-results.json").exists())
        self.assertGreaterEqual(len(list((destination / "history").iterdir())), 4)
        for name, content in original.items():
            if name.startswith("candidate/"):
                self.assertEqual((destination / name).read_bytes(), content)
        self.assertFalse(c.validate_project(destination)["ready"])
        self.assertEqual(p.snapshot_project(self.project)[0], original)
        with self.assertRaises(b.BuildError):
            p.resume(bundle, destination)

    def test_checkpoint_preserves_invalid_draft_for_correction(self):
        file = self.project / "candidate" / "skills" / "cost-report" / "scripts" / "main.py"
        file.write_text("def broken(", encoding="utf-8")
        archive = self.root / "draft.zip"
        p.checkpoint(self.project, archive)
        files, metadata, _ = p.read_bundle(archive)
        self.assertIn("validation_error", metadata)
        self.assertEqual(files["candidate/skills/cost-report/scripts/main.py"], b"def broken(")
        p.resume(archive, self.root / "draft")
        self.assertEqual((self.root / "draft" / "candidate" / "skills" / "cost-report" / "scripts" / "main.py").read_bytes(), b"def broken(")

    def test_resume_archives_interrupted_evaluation_bytes_without_parsing_them(self):
        malformed = b"{"
        self.project.joinpath("evaluation-results.json").write_bytes(malformed)
        original = p.snapshot_project(self.project)[0]
        bundle, destination = self.root / "interrupted.zip", self.root / "resumed-interrupted"
        p.checkpoint(self.project, bundle)
        p.resume(bundle, destination)
        history = destination / "history" / (hashlib.sha256(malformed).hexdigest() + ".json")
        self.assertEqual(history.read_bytes(), malformed)
        self.assertFalse((destination / "evaluation-results.json").exists())
        self.assertEqual(b.read_json(destination / "host-profile.json")["context"], "unverified")
        self.assertEqual(b.read_json(destination / "build-state.json")["phase"], "review")
        self.assertEqual(p.snapshot_project(self.project)[0], original)
        self.assertFalse(c.validate_project(destination)["ready"])

    def test_resume_does_not_silently_default_malformed_required_controls(self):
        self.project.joinpath("host-profile.json").write_bytes(b"{")
        bundle, destination = self.root / "bad-host.zip", self.root / "bad-host-restored"
        p.checkpoint(self.project, bundle)
        with self.assertRaisesRegex(b.BuildError, "host-profile.json: invalid JSON"):
            p.resume(bundle, destination)
        self.assertFalse(destination.exists())

    def test_resume_detects_tamper_traversal_and_forged_native_claims(self):
        base = self.root / "base.zip"
        p.checkpoint(self.project, base)
        with zipfile.ZipFile(base) as archive:
            payload = {name: archive.read(name) for name in archive.namelist()}
        for variant in ("tamper", "traversal", "claims"):
            altered = dict(payload)
            if variant == "tamper":
                altered["inputs.json"] += b" "
            elif variant == "traversal":
                altered["../escape.txt"] = b"outside"
            else:
                meta = json.loads(altered["checkpoint.json"])
                meta["native_acceptance"] = "Installed"
                altered["checkpoint.json"] = b.json_bytes(meta)
            path = self.root / (variant + ".zip")
            path.write_bytes(b.zip_bytes(altered))
            destination = self.root / variant
            with self.subTest(variant=variant), self.assertRaises(b.BuildError):
                p.resume(path, destination)
            self.assertFalse(destination.exists())
        self.assertFalse((self.root / "escape.txt").exists())

    def test_three_way_merge_preserves_separate_edits_and_conflicts_are_atomic(self):
        base = self.root / "base.zip"
        p.checkpoint(self.project, base)
        proposed = self.root / "proposed"
        shutil.copytree(self.project, proposed)
        skill_path = Path("candidate") / "skills" / "cost-report" / "SKILL.md"
        main_path = Path("candidate") / "skills" / "cost-report" / "scripts" / "main.py"
        (self.project / skill_path).write_bytes((self.project / skill_path).read_bytes() + b"\nUser-authored constraint.\n")
        (proposed / main_path).write_bytes((proposed / main_path).read_bytes() + b"\n# Generated correction.\n")
        bp = b.read_json(proposed / "workflow-blueprint.json")
        bp["revision"] = 2
        (proposed / "workflow-blueprint.json").write_bytes(b.json_bytes(bp))
        merged = self.root / "merged"
        p.merge(base, self.project, proposed, merged)
        self.assertIn(b"User-authored", (merged / skill_path).read_bytes())
        self.assertIn(b"Generated correction", (merged / main_path).read_bytes())
        self.assertEqual(b.read_json(merged / "workflow-blueprint.json")["revision"], 2)
        self.assertFalse((merged / "evaluation-results.json").exists())
        (proposed / skill_path).write_bytes((proposed / skill_path).read_bytes() + b"\nDifferent generated edit.\n")
        with self.assertRaises(p.MergeConflict) as error:
            p.merge(base, self.project, proposed, self.root / "conflict")
        self.assertIn(skill_path.as_posix(), error.exception.paths)
        self.assertFalse((self.root / "conflict").exists())

    def test_checkpoint_excludes_unexpected_media_and_secret_shaped_values(self):
        (self.project / "recording.webm").write_bytes(b"synthetic")
        with self.assertRaisesRegex(b.BuildError, "unexpected"):
            p.checkpoint(self.project, self.root / "bad.zip")
        (self.project / "recording.webm").unlink()
        helper = self.project / "candidate" / "skills" / "cost-report" / "references" / "rules.md"
        helper.write_text('api_key: "' + "a" * 24 + '"', encoding="utf-8")
        with self.assertRaisesRegex(b.BuildError, "credential"):
            p.checkpoint(self.project, self.root / "secret.zip")

    def test_real_mcp_metadata_title_null_annotations_and_nullable_output_preserved(self):
        self.add_remote()
        candidate = self.project / "candidate"
        payload, _, _ = b.source_payload(candidate)
        self.assertEqual(payload["tools/learn.json"], LEARN.read_bytes())
        tools = json.loads(payload["tools/learn.json"])["tools"]
        self.assertEqual(tools[0]["title"], "Microsoft Docs Search")
        self.assertNotIn("required", tools[0]["inputSchema"])
        self.assertIsNone(tools[0]["inputSchema"]["properties"]["query"]["default"])
        self.assertNotIn("enum", tools[1]["inputSchema"]["properties"]["language"])
        self.assertIn("null", tools[0]["outputSchema"]["properties"]["results"]["items"]["properties"]["id"]["type"])
        package, _ = b.assemble(candidate, "cowork-v1.28", self.metadata())
        manifest = json.loads(package["manifest.json"])
        remote = manifest["agentConnectors"][0]["toolSource"]["remoteMcpServer"]
        self.assertEqual(remote["mcpToolDescription"]["file"], "./tools/learn.json")
        self.assertEqual(remote["authorization"], {"type": "None"})
        self.assertEqual(package["tools/learn.json"], LEARN.read_bytes())
        with self.assertRaisesRegex(b.BuildError, "Only native Microsoft"):
            b.assemble(candidate, "compatible-source")

    def test_connector_limits_missing_descriptors_auth_and_metadata_types(self):
        spec = self.add_remote()
        candidate = self.project / "candidate"
        first = spec["connectors"][0]
        spec["connectors"] = [dict(first, id=f"learn-{index}") for index in range(10)]
        (candidate / "plugin-spec.json").write_bytes(b.json_bytes(spec))
        self.assertEqual(len(b.source_payload(candidate)[2]), 10)
        spec["connectors"].append(dict(first, id="learn-10"))
        (candidate / "plugin-spec.json").write_bytes(b.json_bytes(spec))
        with self.assertRaisesRegex(b.BuildError, "maximum 10"):
            b.source_payload(candidate)
        spec["connectors"] = [first]
        for auth in ({"type": "ApiKeyPluginVault", "referenceId": "not-an-approved-id"},
                     {"type": "OAuthPluginVault"}, {"type": "None", "referenceId": "unexpected"},
                     {"type": []}):
            first["authorization"] = auth
            (candidate / "plugin-spec.json").write_bytes(b.json_bytes(spec))
            with self.subTest(auth=auth), self.assertRaises(b.BuildError):
                b.source_payload(candidate)
        first["authorization"] = {"type": "DynamicClientRegistration"}
        (candidate / "plugin-spec.json").write_bytes(b.json_bytes(spec))
        package, _ = b.assemble(candidate, "cowork-v1.28", self.metadata())
        remote = json.loads(package["manifest.json"])["agentConnectors"][0]["toolSource"]["remoteMcpServer"]
        self.assertNotIn("authorization", remote)
        invalid = json.loads(LEARN.read_bytes())
        invalid["tools"][0]["title"] = False
        (candidate / "tools" / "learn.json").write_bytes(b.json_bytes(invalid))
        with self.assertRaises(b.BuildError):
            b.source_payload(candidate)
        invalid = json.loads(LEARN.read_bytes())
        invalid["tools"][0]["outputSchema"]["$ref"] = "https://learn.microsoft.com/schema"
        (candidate / "tools" / "learn.json").write_bytes(b.json_bytes(invalid))
        with self.assertRaisesRegex(b.BuildError, "external schema"):
            b.source_payload(candidate)
        (candidate / "tools" / "learn.json").unlink()
        with self.assertRaises((b.BuildError, OSError)):
            b.source_payload(candidate)

    def test_public_metadata_is_not_native_availability(self):
        host = self.doc("host-profile.json")
        host["capabilities"].append({"id": "business.tool", "status": "unverified", "evidence": ""})
        host["connections"] = [{
            "id": "microsoft-learn", "mode": "existing-native", "status": "needs-setup",
            "native_id": None, "tools": json.loads(LEARN.read_bytes())["tools"],
            "provenance": {"kind": "user-supplied", "reference": "Actual public tools/list fixture, not a Cowork binding"},
            "availability_evidence": "",
        }]
        self.save("host-profile.json", host)
        self.blueprint(lambda doc: doc["steps"][1].update(capability="business.tool", connection_id="microsoft-learn", tool_name="microsoft_docs_search"))
        self.assertIn("connection-setup", self.codes())
        self.assertIn("native-capability-gap", self.codes())
        self.blueprint(lambda doc: doc["steps"][1].update(tool_name="fabricated_tool"))
        with self.assertRaisesRegex(b.BuildError, "absent"):
            self.check()


if __name__ == "__main__":
    unittest.main()
