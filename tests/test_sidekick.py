from __future__ import annotations

import argparse
import copy
from contextlib import redirect_stdout, redirect_stderr
import datetime as dt
import io
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import swe_sidekick as s


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="swe-sidekick-test-")
        self.root = Path(self.tmp.name)
        self.repo = self.root / "repo with spaces"
        self.repo.mkdir()
        (self.repo / "src").mkdir()
        (self.repo / "tests").mkdir()
        (self.repo / ".gitignore").write_text("__pycache__/\n.env\nnode_modules/\n")
        (self.repo / "src/add.py").write_text("def add(a, b):\n    return a - b\n")
        (self.repo / "tests/test_add.py").write_text(
            "import unittest\nfrom src.add import add\nclass AddTest(unittest.TestCase):\n"
            "    def test_add(self): self.assertEqual(add(2, 3), 5)\n")
        self.g("init", "-q")
        self.g("add", "-A")
        self.g("-c", "user.name=fixture", "-c", "user.email=fixture@localhost", "commit", "-qm", "initial")
        self.state = self.root / "state"
        self.fake = self.root / "fake-devin"
        shutil.copy2(ROOT / "tests/fake_devin.py", self.fake)
        self.fake.chmod(0o755)
        self.packet = {"version": 1, "objective": "Fix add to sum its two arguments.",
                       "allowed_changes": ["src/add.py"], "acceptance_criteria": ["add(2,3) returns 5"],
                       "non_goals": ["Do not change public signatures"],
                       "verification": [[sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"]]}
        self.packet_file = self.root / "packet.json"
        self.write_packet()
        self.task_id = None

    def tearDown(self):
        self.tmp.cleanup()

    def g(self, *args):
        return s.git(self.repo, *args)

    def write_packet(self):
        self.packet_file.write_text(json.dumps(self.packet))

    def mode(self, **kwargs):
        (self.root / "fake-mode.json").write_text(json.dumps(kwargs))

    def cmd(self, *args, ok=True):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = s.main(["--state-dir", str(self.state), *map(str, args)])
        if ok:
            self.assertEqual(code, 0, out.getvalue() + err.getvalue())
            return json.loads(out.getvalue())
        self.assertNotEqual(code, 0, out.getvalue() + err.getvalue())
        return out.getvalue() + err.getvalue()

    def configure(self):
        return self.cmd("configure", "--devin-path", self.fake, "--model", "swe-2-high", "--acknowledge-usage")

    def prepare(self):
        data = self.cmd("prepare", "--repo", self.repo, "--packet", self.packet_file, "--trust-repo")
        self.task_id = data["task_id"]
        return Path(data["task_dir"])

    def run(self, *args, **kwargs):
        # unittest.TestCase.run must keep its normal behavior.
        return super().run(*args, **kwargs)

    def worker(self, ok=True):
        return self.cmd("run", "--task", self.task_id, ok=ok)

    def successful(self):
        self.configure(); task = self.prepare(); report = self.worker()
        return task, report


class PacketTests(Base):
    def test_valid_packet(self): self.assertEqual(s.packet_from(self.packet_file), self.packet)

    def test_duplicate_json_keys(self):
        self.packet_file.write_text('{"version":1,"version":1}')
        with self.assertRaises(s.SidekickError): s.packet_from(self.packet_file)

    def test_unknown_field(self):
        self.packet["other"] = 1; self.write_packet()
        with self.assertRaises(s.SidekickError): s.packet_from(self.packet_file)

    def test_boolean_version_rejected(self):
        self.packet["version"] = True; self.write_packet()
        with self.assertRaises(s.SidekickError): s.packet_from(self.packet_file)

    def test_bad_scope_paths(self):
        for scope in ("../x", "/tmp/x", "src/../x", "src//x", "src/*", "**", ".git/config", ".devin/config.json", ".env", "AGENTS.md", "src/.gitignore", "src\\x"):
            with self.subTest(scope=scope):
                self.packet["allowed_changes"] = [scope]; self.write_packet()
                with self.assertRaises(s.SidekickError): s.packet_from(self.packet_file)

    def test_subtree_does_not_allow_protected_files(self):
        self.packet["allowed_changes"] = ["src/**"]
        self.assertTrue(s.allowed("src/sub/a.py", self.packet))
        self.assertFalse(s.allowed("src2/a.py", self.packet))
        self.assertFalse(s.allowed("src/.env.production", self.packet))

    def test_verification_argv_required(self):
        self.packet["verification"] = ["echo x && rm y"]; self.write_packet()
        with self.assertRaises(s.SidekickError): s.packet_from(self.packet_file)

    def test_symlink_packet_rejected(self):
        link = self.root / "link.json"; link.symlink_to(self.packet_file)
        with self.assertRaises(s.SidekickError): s.packet_from(link)

    def test_oversized_packet_rejected(self):
        self.packet_file.write_text(" " * (s.MAX_PACKET + 1))
        with self.assertRaises(s.SidekickError): s.packet_from(self.packet_file)


class SetupTests(Base):
    def test_prepare_cli_rejects_symlink_packet(self):
        link = self.root / "packet-link.json"
        link.symlink_to(self.packet_file)
        self.cmd("prepare", "--repo", self.repo, "--packet", link, "--trust-repo", ok=False)
        self.assertFalse((self.state / "tasks").exists())

    def test_doctor_is_non_inference(self):
        report = self.cmd("doctor", "--devin-path", self.fake)
        self.assertIn("swe-2-high", report["swe2_catalog_values"])
        self.assertFalse(report["live_model_invoked"])

    def test_model_must_be_available(self):
        self.cmd("configure", "--devin-path", self.fake, "--model", "swe-2-superhigh", "--acknowledge-usage", ok=False)

    def test_moving_alias_rejected(self):
        self.cmd("configure", "--devin-path", self.fake, "--model", "swe", "--acknowledge-usage", ok=False)

    def test_config_requires_usage_ack(self):
        self.cmd("configure", "--devin-path", self.fake, "--model", "swe-2-high", ok=False)

    def test_dirty_source_is_not_stashed(self):
        (self.repo / "src/add.py").write_text("my work")
        self.cmd("prepare", "--repo", self.repo, "--packet", self.packet_file, "--trust-repo", ok=False)
        self.assertEqual((self.repo / "src/add.py").read_text(), "my work")

    def test_untracked_source_blocks_prepare(self):
        (self.repo / "my-notes.txt").write_text("notes")
        self.cmd("prepare", "--repo", self.repo, "--packet", self.packet_file, "--trust-repo", ok=False)

    def test_ignored_env_not_copied(self):
        (self.repo / ".env").write_text("SECRET=test fixture")
        task = self.prepare()
        self.assertFalse((task / "workspace/.env").exists())

    def test_tracked_secret_blocks_prepare(self):
        (self.repo / ".env").write_text("dummy")
        self.g("add", "-f", ".env")
        self.g("-c", "user.name=fixture", "-c", "user.email=fixture@localhost", "commit", "-qm", "fixture")
        self.cmd("prepare", "--repo", self.repo, "--packet", self.packet_file, "--trust-repo", ok=False)

    def test_tracked_symlink_blocks_prepare(self):
        (self.repo / "link").symlink_to("src/add.py")
        self.g("add", "link"); self.g("-c", "user.name=fixture", "-c", "user.email=fixture@localhost", "commit", "-qm", "fixture")
        self.cmd("prepare", "--repo", self.repo, "--packet", self.packet_file, "--trust-repo", ok=False)

    def test_tracked_agent_configs_omitted(self):
        (self.repo / ".devin").mkdir(); (self.repo / ".devin/config.json").write_text("{}")
        self.g("add", ".devin"); self.g("-c", "user.name=fixture", "-c", "user.email=fixture@localhost", "commit", "-qm", "fixture")
        task = self.prepare()
        self.assertFalse((task / "workspace/.devin").exists())
        self.assertIn(".devin/config.json", s.read_json(task / "state.json")["omitted_paths"])

    def test_snapshot_has_no_remote_or_shared_git(self):
        task = self.prepare()
        self.assertEqual(s.git(task / "workspace", "remote"), b"")
        self.assertTrue((task / "workspace/.git").is_dir())
        self.assertNotEqual(s.git(task / "workspace", "rev-parse", "HEAD"), self.g("rev-parse", "HEAD"))

    def test_sidekick_git_disables_auto_maintenance(self):
        seen = []

        def fake_capture(argv, **kwargs):
            seen.append(argv)
            return b""

        with patch.object(s, "capture", fake_capture):
            s.git(self.repo, "status", "--porcelain=v1")
            s.git(self.repo, "-c", "user.name=fixture", "commit", "--quiet", "-m", "x")
        self.assertEqual(len(seen), 2)
        for argv in seen:
            self.assertEqual(argv[:2], ["git", "--literal-pathspecs"])
            self.assertIn("-C", argv)
            for flag in ("core.hooksPath=/dev/null", "core.fsmonitor=false", "core.autocrlf=false",
                         "gc.auto=0", "maintenance.auto=false"):
                self.assertIn(flag, argv)
            for flag in ("gc.auto=0", "maintenance.auto=false"):
                pos = argv.index(flag)
                self.assertEqual(argv[pos - 1], "-c")
                self.assertLess(pos, argv.index("-C"))

    def test_new_git_metadata_info_refs_violates_scope(self):
        task = self.prepare()
        state = s.read_json(task / "state.json")
        self.assertTrue(s.inspect_scope(task, state)["scope_ok"])
        info = task / "workspace/.git/info"
        self.assertTrue(info.is_dir())
        (info / "refs").write_text("late auto-maintenance output\n")
        report = s.inspect_scope(task, state)
        self.assertFalse(report["scope_ok"])
        self.assertIn("Git HEAD/refs/index/config/hooks changed", "; ".join(report["violations"]))
        (info / "refs").unlink()
        self.assertTrue(s.inspect_scope(task, state)["scope_ok"])
        (info / "exclude").write_text("tampered\n")
        self.assertFalse(s.inspect_scope(task, state)["scope_ok"])

    def test_prepare_records_utc_created_at(self):
        task = self.prepare()
        state = s.read_json(task / "state.json")
        created_at = dt.datetime.fromisoformat(state["created_at"])
        self.assertIsNotNone(created_at.tzinfo)
        self.assertEqual(created_at.utcoffset(), dt.timedelta(0))

    def test_worker_prompt_requires_sandbox_exec_and_keeps_denials(self):
        self.configure(); task = self.prepare()
        self.mode(behavior="no_changes")
        self.worker(ok=False)
        prompt = (task / "turn-01/prompt.txt").read_text()
        self.assertIn("sandbox's Exec", prompt)
        self.assertIn("direct edit/write", prompt)
        self.assertIn("Never bypass a denied sandboxed command", prompt)
        config = s.read_json(task / "turn-01/devin-config.json")
        denied = config["permissions"]["deny"]
        self.assertIn("Exec(git commit)", denied)
        self.assertIn("Exec(git push)", denied)
        self.assertEqual(config["sandbox"]["excluded"]["deny"], ["Exec(*)"])

    def test_prompt_recovery_and_dependency_bounds_hold_across_turns(self):
        self.configure()
        self.mode(behavior="no_changes")
        task = self.prepare()
        self.worker(ok=False)
        feedback = self.root / "feedback.md"
        feedback.write_text("Continue the same task within the unchanged scope.")
        self.mode(expect_resume=True)
        self.cmd("retry", "--task", self.task_id, "--feedback-file", feedback)

        expected = ["Never bypass a denied sandboxed command",
                    "stops only the affected operation",
                    "exact command, exit status and diagnostic without secrets",
                    "partial work",
                    "EPERM or EACCES",
                    "Dependency preparation is forbidden by default",
                    "lifecycle scripts disabled",
                    "scratch-local temporary/cache paths",
                    "lockfile-only command"]
        prompts = [(task / f"turn-{index:02d}/prompt.txt").read_text() for index in (1, 2)]
        for prompt in prompts:
            for phrase in expected:
                self.assertIn(phrase, prompt)
        self.assertTrue(prompts[1].startswith(prompts[0]))
        self.assertIn("LEAD REVIEW FEEDBACK FOR THIS SAME TASK", prompts[1])
        self.assertIn(feedback.read_text().strip(), prompts[1])

        for index in (1, 2):
            config = s.read_json(task / f"turn-{index:02d}/devin-config.json")
            denied = config["permissions"]["deny"]
            self.assertIn("Exec(git commit)", denied)
            self.assertIn("Exec(git push)", denied)
            self.assertEqual(config["sandbox"]["excluded"]["deny"], ["Exec(*)"])
        argv = s.read_json(task / "turn-02/command.json")["argv"]
        self.assertIn("--resume", argv)
        self.assertIn("fixture-session-123", argv)

    def test_bracketed_inventory_file_is_snapshot_readable_but_not_writable(self):
        bracketed = self.repo / "src/[id].tsx"
        bracketed.write_text("export const id = '[id]';\n")
        self.g("add", "src/[id].tsx")
        self.g("-c", "user.name=fixture", "-c", "user.email=fixture@localhost", "commit", "-qm", "bracketed fixture")
        task = self.prepare()
        self.assertEqual((task / "workspace/src/[id].tsx").read_text(), bracketed.read_text())
        snapshot = self.cmd("handoff", "--task", self.task_id)
        self.assertTrue(snapshot["scope"]["ok"])
        self.assertFalse(s.allowed("src/[id].tsx", self.packet))
        state = s.read_json(task / "state.json")
        (task / "workspace/src/[id].tsx").write_text("changed\n")
        report = s.inspect_scope(task, state)
        self.assertFalse(report["scope_ok"])
        self.assertTrue(any("src/[id].tsx" in item for item in report["violations"]))
        snapshot = self.cmd("handoff", "--task", self.task_id)
        self.assertFalse(snapshot["scope"]["ok"])
        self.assertIn("Stop", snapshot["continuation"]["next"])


class WorkflowTests(Base):
    def _task_bytes(self, task):
        return {path.relative_to(task).as_posix(): path.read_bytes()
                for path in task.rglob("*") if path.is_file() and not path.is_symlink()}

    def test_handoff_valid_snapshot_is_read_only_and_private(self):
        task = self.prepare()
        before = self._task_bytes(task)
        snapshot = self.cmd("handoff", "--task", self.task_id)
        after = self._task_bytes(task)
        self.assertEqual(before, after)
        self.assertEqual(snapshot["schema_version"], 1)
        self.assertEqual(snapshot["task_id"], self.task_id)
        self.assertEqual(snapshot["task_path"], str(task))
        self.assertEqual(snapshot["source"]["path"], str(self.repo.resolve()))
        self.assertEqual(snapshot["workspace"]["path"], str(task / "workspace"))
        self.assertEqual(snapshot["packet"], self.packet)
        self.assertEqual(snapshot["status"], "prepared")
        self.assertFalse(snapshot["applied"])
        self.assertEqual(snapshot["worker"]["turn_count"], 0)
        self.assertEqual(snapshot["patch"]["bytes"], 0)
        self.assertEqual(snapshot["patch"]["sha256"], s.digest(b""))
        self.assertEqual(snapshot["patch"]["saved"]["status"], "missing")
        self.assertTrue(snapshot["sharing"]["private"])
        self.assertTrue(snapshot["sharing"]["contains_private_paths"])
        self.assertFalse(snapshot["continuation"]["automatic"])
        self.assertIsNone(snapshot["continuation"]["lead_model"])
        self.assertFalse(snapshot["continuation"]["transfers"]["chat_history"])
        self.assertIn("explicitly run", snapshot["continuation"]["next"])
        self.assertNotIn("retry", snapshot["continuation"]["next"])
        self.assertIsNone(snapshot["continuation"]["retry_eligible"])
        self.assertNotIn("task", snapshot)
        self.assertNotIn("source_path", snapshot)
        self.assertNotIn("current_patch_sha256", snapshot)
        self.assertFalse((task / "report.json").exists())
        self.assertFalse((task / "diff.patch").exists())


    def test_handoff_rejects_missing_lock_without_writing(self):
        task = self.prepare()
        lock = task / ".lock"
        lock.unlink()
        before = self._task_bytes(task)
        error = self.cmd("handoff", "--task", self.task_id, ok=False)
        self.assertIn("Task lock is missing", error)
        self.assertFalse(lock.exists())
        self.assertEqual(before, self._task_bytes(task))


    def test_handoff_rejects_busy_task_without_writing(self):
        task = self.prepare()
        with s.locked_task(self.state, self.task_id):
            before = self._task_bytes(task)
            self.cmd("handoff", "--task", self.task_id, ok=False)
            self.assertEqual(before, self._task_bytes(task))

    def test_handoff_handles_invalid_and_incomplete_tasks(self):
        task = self.prepare()
        state_path = task / "state.json"
        state_path.write_text("{}")
        self.cmd("handoff", "--task", self.task_id, ok=False)
        self.assertEqual(self._task_bytes(task)["state.json"], b"{}")

        self.mode(behavior="no_changes")
        self.configure(); task = self.prepare(); self.worker(ok=False)
        snapshot = self.cmd("handoff", "--task", self.task_id)
        self.assertEqual(snapshot["status"], "incomplete_no_changes")
        self.assertEqual(snapshot["patch"]["bytes"], 0)
        self.assertIn("explicitly retry", snapshot["continuation"]["next"])

    def test_handoff_continuation_stops_for_failed_mismatch_and_unknown_states(self):
        for status in ("worker_failed", "model_mismatch", "interrupted", "scope_violation", "unexpected", []):
            with self.subTest(status=status):
                task = self.prepare()
                state_path = task / "state.json"
                state = s.read_json(state_path)
                state["status"] = status
                if status == "worker_failed":
                    state["session_id"] = None
                    state["retry_max_turns"] = 3
                s.write_json(state_path, state)
                snapshot = self.cmd("handoff", "--task", self.task_id)
                next_step = snapshot["continuation"]["next"]
                self.assertNotIn("verify", next_step.lower())
                self.assertNotIn("verify", json.dumps(snapshot["continuation"]).lower())
                if status == "worker_failed":
                    self.assertIn("worker logs", next_step)
                    self.assertIn("new task", next_step)
                    self.assertIsNone(snapshot["continuation"]["retry_eligible"])
                else:
                    self.assertIn("Stop", next_step)

    def test_handoff_rejects_malformed_verification_as_json_error_without_writing(self):
        task = self.prepare()
        state_path = task / "state.json"
        state = s.read_json(state_path)
        state["status"] = "needs_review"
        state["verification"] = "passed"
        s.write_json(state_path, state)
        before = self._task_bytes(task)
        error = self.cmd("handoff", "--task", self.task_id, ok=False)
        self.assertIn("Task verification is invalid", error)
        self.assertEqual(before, self._task_bytes(task))

    def test_handoff_reports_current_hash_when_saved_diff_is_stale(self):
        task, report = self.successful()
        saved_hash = report["patch_sha256"]
        (task / "workspace/src/add.py").write_text("def add(a, b):\n    return a + b + 10\n")
        before = self._task_bytes(task)
        snapshot = self.cmd("handoff", "--task", self.task_id)
        self.assertEqual(before, self._task_bytes(task))
        self.assertNotEqual(snapshot["patch"]["sha256"], saved_hash)
        self.assertEqual(snapshot["patch"]["saved"]["sha256"], saved_hash)
        self.assertEqual(snapshot["patch"]["saved"]["status"], "stale")
        self.assertFalse(snapshot["patch"]["saved"]["matches_current"])
        self.assertEqual(snapshot["verification"], None)

    def test_handoff_includes_verification_state_without_rerunning_checks(self):
        task, _ = self.successful()
        checked = self.cmd("verify", "--task", self.task_id)
        before = self._task_bytes(task)
        snapshot = self.cmd("handoff", "--task", self.task_id)
        self.assertEqual(before, self._task_bytes(task))
        self.assertTrue(snapshot["verification"]["passed"])
        self.assertEqual(snapshot["verification"]["patch_sha256"], checked["patch_sha256"])
        self.assertEqual(snapshot["patch"]["sha256"], checked["patch_sha256"])
        self.assertIn("explicitly apply", snapshot["continuation"]["next"])

    def test_bundled_smoke_fixture_offline(self):
        self.configure()
        smoke = self.cmd("smoke-setup")
        self.assertFalse(smoke["model_invoked"])
        self.repo = Path(smoke["repo"])
        self.packet_file = Path(smoke["packet"])
        task = self.prepare()
        report = self.worker()
        self.assertEqual(report["status"], "needs_review")
        report = self.cmd("verify", "--task", self.task_id)
        self.assertTrue(report["verification"]["passed"])
        result = self.cmd("apply", "--task", self.task_id,
                          "--reviewed-sha256", report["patch_sha256"])
        self.assertEqual(result["status"], "applied_uncommitted")
        self.assertIn("a + b", (self.repo / "src/add.py").read_text())

    def test_full_offline_flow_and_review_gate(self):
        task, report = self.successful()
        self.assertTrue(report["scope_ok"])
        self.assertEqual(report["turns"][0]["model_check"], "matches_requested")
        self.assertEqual(self.g("status", "--porcelain"), b"")
        self.assertIn("a - b", (self.repo / "src/add.py").read_text())
        self.cmd("apply", "--task", self.task_id, "--reviewed-sha256", report["patch_sha256"], ok=False)
        verified = self.cmd("verify", "--task", self.task_id)
        self.assertTrue(verified["verification"]["passed"])
        self.cmd("apply", "--task", self.task_id, "--reviewed-sha256", "wrong", ok=False)
        applied = self.cmd("apply", "--task", self.task_id, "--reviewed-sha256", verified["patch_sha256"])
        self.assertEqual(applied["status"], "applied_uncommitted")
        self.assertIn("a + b", (self.repo / "src/add.py").read_text())
        self.assertIn(b"src/add.py", self.g("diff", "--name-only"))
        self.cmd("apply", "--task", self.task_id, "--reviewed-sha256", verified["patch_sha256"], ok=False)

    def test_resume_uses_explicit_exported_id(self):
        task, report = self.successful()
        feedback = self.root / "feedback.md"; feedback.write_text("Review again, keep the same scope.")
        self.mode(expect_resume=True)
        second = self.cmd("retry", "--task", self.task_id, "--feedback-file", feedback)
        self.assertEqual(len(second["turns"]), 2)
        argv = s.read_json(task / "turn-02/command.json")["argv"]
        self.assertIn("--resume", argv)
        self.assertNotIn("--continue", argv)

    def test_no_changes_is_incomplete_and_requires_explicit_session_retry(self):
        self.mode(behavior="no_changes")
        self.configure(); task = self.prepare()
        first = self.worker(ok=False)
        state = s.read_json(task / "state.json")
        self.assertEqual(state["status"], "incomplete_no_changes")
        self.assertEqual(len(state["turns"]), 1)
        self.assertTrue(state["retry_eligible"])
        self.assertIn("retry --task", first)
        self.assertFalse((task / "turn-02").exists())
        self.cmd("inspect", "--task", self.task_id, ok=False)
        self.cmd("verify", "--task", self.task_id, ok=False)
        self.cmd("apply", "--task", self.task_id, "--reviewed-sha256", "none", ok=False)

        feedback = self.root / "feedback.md"; feedback.write_text("Use the sandbox Exec shell to edit src/add.py.")
        self.mode()
        second = self.cmd("retry", "--task", self.task_id, "--feedback-file", feedback)
        self.assertEqual(second["status"], "needs_review")
        self.assertEqual(len(second["turns"]), 2)

    def test_evaluation_cli_dispatch_and_error_translation(self):
        record = self.root / "record.json"; record.write_text('{"outcome":"passed"}')
        calls = []
        module = types.ModuleType("sidekick_evaluation")

        def record_evaluation(root, task_id, payload, replace=False):
            calls.append((root, task_id, payload, replace))
            return {"task_id": task_id, "replace": replace, "outcome": payload["outcome"]}

        def build_evaluation_report(root, include_smoke=False):
            calls.append((root, include_smoke))
            return {"include_smoke": include_smoke, "tasks": []}

        module.record_evaluation = record_evaluation
        module.build_evaluation_report = build_evaluation_report
        with patch.dict(sys.modules, {"sidekick_evaluation": module}):
            result = self.cmd("evaluate", "--task", "20260101T000000-aaaaaaaaaa", "--record", record, "--replace")
            report = self.cmd("evaluation-report", "--include-smoke")
        self.assertTrue(result["replace"])
        self.assertEqual(report["include_smoke"], True)
        self.assertEqual(calls[0][2], {"outcome": "passed"})

        failing = types.ModuleType("sidekick_evaluation")

        def fail(*args, **kwargs):
            raise ValueError("invalid evaluation record")

        failing.record_evaluation = fail
        with patch.dict(sys.modules, {"sidekick_evaluation": failing}):
            error = self.cmd("evaluate", "--task", "20260101T000000-aaaaaaaaaa", "--record", record, ok=False)
        self.assertIn("invalid evaluation record", error)

    def test_no_automatic_fresh_retry_without_session(self):
        self.mode(no_export=True)
        task, report = self.successful()
        feedback = self.root / "feedback"; feedback.write_text("retry")
        self.cmd("retry", "--task", self.task_id, "--feedback-file", feedback, ok=False)
        self.assertFalse((task / "turn-02").exists())

    def test_missing_export_requires_ack_for_apply(self):
        self.mode(no_export=True)
        task, report = self.successful()
        checked = self.cmd("verify", "--task", self.task_id)
        self.cmd("apply", "--task", self.task_id, "--reviewed-sha256", checked["patch_sha256"], ok=False)
        self.cmd("apply", "--task", self.task_id, "--reviewed-sha256", checked["patch_sha256"], "--acknowledge-unverified-model")

    def test_model_mismatch_blocks_acceptance(self):
        self.mode(reported_model="gpt-6-astra")
        self.configure(); task = self.prepare(); self.worker(ok=False)
        self.assertEqual(s.read_json(task / "state.json")["status"], "model_mismatch")
        self.cmd("apply", "--task", self.task_id, "--reviewed-sha256", "none", "--acknowledge-unverified-model", ok=False)

    def test_out_of_scope_stops_without_reverting_evidence(self):
        self.mode(behavior="out_of_scope")
        self.configure(); task = self.prepare(); self.worker(ok=False)
        self.assertTrue((task / "workspace/outside.txt").exists())
        self.assertFalse((self.repo / "outside.txt").exists())

    def test_worker_commit_detected(self):
        self.mode(behavior="commit")
        self.configure(); self.prepare(); self.worker(ok=False)
        self.assertEqual(self.g("rev-list", "--count", "HEAD").strip(), b"1")

    def test_git_config_mutation_detected(self):
        self.mode(behavior="index")
        self.configure(); self.prepare(); self.worker(ok=False)

    def test_worker_symlink_rejected(self):
        self.mode(behavior="symlink")
        self.configure(); self.prepare(); self.worker(ok=False)

    def test_source_edits_block_apply_and_are_preserved(self):
        task, _ = self.successful()
        checked = self.cmd("verify", "--task", self.task_id)
        (self.repo / "src/add.py").write_text("my edits")
        self.cmd("apply", "--task", self.task_id, "--reviewed-sha256", checked["patch_sha256"], ok=False)
        self.assertEqual((self.repo / "src/add.py").read_text(), "my edits")

    def test_stale_review_and_verification_block_apply(self):
        task, _ = self.successful()
        checked = self.cmd("verify", "--task", self.task_id)
        (task / "workspace/src/add.py").write_text("def add(a,b):\n    return a+b+10\n")
        self.cmd("apply", "--task", self.task_id, "--reviewed-sha256", checked["patch_sha256"], ok=False)
        latest = self.cmd("inspect", "--task", self.task_id)
        self.cmd("apply", "--task", self.task_id, "--reviewed-sha256", latest["patch_sha256"], ok=False)

    def test_exported_patch_tampering_not_used(self):
        task, _ = self.successful()
        checked = self.cmd("verify", "--task", self.task_id)
        (task / "diff.patch").write_text("malicious saved patch")
        self.cmd("apply", "--task", self.task_id, "--reviewed-sha256", checked["patch_sha256"])
        self.assertIn("a + b", (self.repo / "src/add.py").read_text())

    def test_version_change_blocks_another_turn(self):
        self.configure(); task = self.prepare(); self.mode(version="new fixture version")
        self.worker(ok=False)
        self.assertFalse((task / "turn-01").exists())

    def test_turn_budget_enforced(self):
        self.cmd("configure", "--devin-path", self.fake, "--model", "swe-2-high", "--max-turns", "1", "--acknowledge-usage")
        self.prepare(); self.worker()
        feedback = self.root / "feedback"; feedback.write_text("retry")
        self.cmd("retry", "--task", self.task_id, "--feedback-file", feedback, ok=False)

    def test_new_file_export(self):
        self.packet["allowed_changes"] = ["src/**"]; self.write_packet(); self.mode(behavior="new_file")
        task, _ = self.successful(); checked = self.cmd("verify", "--task", self.task_id)
        self.cmd("apply", "--task", self.task_id, "--reviewed-sha256", checked["patch_sha256"])
        self.assertEqual((self.repo / "src/new.txt").read_text(), "new file\n")

    def test_binary_export(self):
        self.packet["allowed_changes"] = ["src/**"]; self.write_packet(); self.mode(behavior="binary")
        task, _ = self.successful(); checked = self.cmd("verify", "--task", self.task_id)
        self.cmd("apply", "--task", self.task_id, "--reviewed-sha256", checked["patch_sha256"])
        self.assertEqual((self.repo / "src/blob.bin").read_bytes(), b"\x00\x01NEW\xff\n")

    def test_mode_change_export(self):
        self.mode(behavior="executable")
        task, _ = self.successful(); checked = self.cmd("verify", "--task", self.task_id)
        self.cmd("apply", "--task", self.task_id, "--reviewed-sha256", checked["patch_sha256"])
        self.assertTrue((self.repo / "src/add.py").stat().st_mode & 0o111)

    def test_worker_error_does_not_become_success(self):
        self.mode(exit_code=7)
        self.configure(); task = self.prepare(); self.worker(ok=False)
        self.cmd("verify", "--task", self.task_id, ok=False)

    def test_verification_failure_blocks_apply(self):
        self.packet["verification"] = [[sys.executable, "-c", "raise SystemExit(1)"]]; self.write_packet()
        task, _ = self.successful(); self.cmd("verify", "--task", self.task_id, ok=False)
        report = self.cmd("inspect", "--task", self.task_id)
        self.cmd("apply", "--task", self.task_id, "--reviewed-sha256", report["patch_sha256"], ok=False)


class ProcessTests(Base):
    def test_timeout_terminates_child(self):
        result = s.bounded_process([sys.executable, "-c", "import time; time.sleep(20)"], self.root,
                                   self.root / "out", self.root / "err", 0.15)
        self.assertEqual(result["stop"], "timeout")
        self.assertLess(result["elapsed_seconds"], 5)

    def test_sensitive_env_not_forwarded(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "fake", "WINDSURF_API_KEY": "fake", "SSH_AUTH_SOCK": "fake",
                                     "DEVIN_MODEL": "unexpected", "NODE_OPTIONS": "unexpected", "GIT_DIR": "unexpected"}):
            env = s.environment()
        for key in ("OPENAI_API_KEY", "WINDSURF_API_KEY", "SSH_AUTH_SOCK", "DEVIN_MODEL", "NODE_OPTIONS", "GIT_DIR"):
            self.assertNotIn(key, env)

    def test_cleanup_denial_on_timeout_is_sanitized_and_not_retried(self):
        with patch.object(s.os, "killpg", side_effect=PermissionError(13, "fixture /private/path detail")) as deny:
            result = s.bounded_process([sys.executable, "-c", "import time; time.sleep(0.3)"],
                                       self.root, self.root / "out", self.root / "err", 0.05)
        self.assertEqual(result["stop"], "timeout")
        self.assertEqual(deny.call_count, 1)
        self.assertEqual(deny.call_args.args[1], signal.SIGTERM)
        cleanup = result["cleanup"]
        self.assertFalse(cleanup["ok"])
        self.assertEqual(cleanup["error"], "PermissionError")
        self.assertEqual(cleanup["errno"], 13)
        self.assertEqual(cleanup["signal"], "SIGTERM")
        self.assertEqual(cleanup["termination"], "unconfirmed")
        self.assertNotIn("private/path", json.dumps(result))
        self.assertNotIn("time.sleep", json.dumps(cleanup))

    def _run_json(self, *cli):
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(io.StringIO()):
            code = s.main(["--state-dir", str(self.state), *map(str, cli)])
        return code, json.loads(out.getvalue())

    def test_cleanup_denial_on_normal_exit_fails_successful_child(self):
        self.configure(); task = self.prepare()
        with patch.object(s.os, "killpg", side_effect=PermissionError(13, "fixture denial")) as deny:
            code, report = self._run_json("run", "--task", self.task_id)
        self.assertNotEqual(code, 0)
        self.assertEqual(deny.call_count, 1)
        self.assertEqual(report["status"], "worker_failed")
        state = s.read_json(task / "state.json")
        self.assertEqual(state["status"], "worker_failed")
        self.assertFalse(state["interrupted_attempt"])
        self.assertEqual(len(state["turns"]), 1)
        turn = state["turns"][0]
        self.assertEqual(turn["stop"], "exit")
        self.assertEqual(turn["returncode"], 0)
        self.assertEqual(turn["model_check"], "matches_requested")
        self.assertIsInstance(turn["elapsed_seconds"], (int, float))
        self.assertFalse(turn["cleanup"]["ok"])
        self.assertEqual(turn["cleanup"]["termination"], "unconfirmed")
        self.assertNotIn("fixture denial", json.dumps(turn))

    def test_cleanup_denial_on_timeout_records_failed_turn(self):
        self.configure()
        cfg = s.read_json(self.state / "config.json")
        cfg["timeout_seconds"] = 1
        s.write_json(self.state / "config.json", cfg)
        self.mode(behavior="timeout")
        task = self.prepare()
        with patch.object(s.os, "killpg", side_effect=PermissionError(1, "denied")) as deny:
            code, report = self._run_json("run", "--task", self.task_id)
        self.assertNotEqual(code, 0)
        self.assertEqual(deny.call_count, 1)
        self.assertEqual(report["status"], "worker_failed")
        state = s.read_json(task / "state.json")
        self.assertEqual(state["status"], "worker_failed")
        self.assertFalse(state["interrupted_attempt"])
        turn = state["turns"][0]
        self.assertEqual(turn["stop"], "timeout")
        self.assertFalse(turn["cleanup"]["ok"])
        self.assertEqual(turn["cleanup"]["termination"], "unconfirmed")

    def test_cleanup_denial_fails_verification(self):
        self.packet["verification"] = [[sys.executable, "-c", "pass"],
                                       [sys.executable, "-c", "raise SystemExit('must not run')"]]
        self.write_packet()
        task, _ = self.successful()
        with patch.object(s.os, "killpg", side_effect=PermissionError(13, "denied")) as deny:
            code, report = self._run_json("verify", "--task", self.task_id)
        self.assertNotEqual(code, 0)
        self.assertEqual(deny.call_count, 1)
        self.assertFalse(report["verification"]["passed"])
        self.assertEqual(len(report["verification"]["results"]), 1)
        result = report["verification"]["results"][0]
        self.assertEqual(result["stop"], "exit")
        self.assertEqual(result["returncode"], 0)
        self.assertFalse(result["cleanup"]["ok"])
        logs = Path(report["verification"]["logs"])
        self.assertTrue((logs / "1.stdout.log").exists())
        self.assertFalse((logs / "2.stdout.log").exists())

    def test_cleanup_succeeds_for_exited_and_missing_groups(self):
        result = s.bounded_process([sys.executable, "-c", "pass"], self.root,
                                   self.root / "o", self.root / "e", 5)
        self.assertEqual(result["stop"], "exit")
        self.assertEqual(result["returncode"], 0)
        self.assertEqual(result["cleanup"], {"ok": True})

        proc = subprocess.Popen([sys.executable, "-c", "pass"], start_new_session=True)
        proc.wait()
        with patch.object(s.os, "killpg", side_effect=ProcessLookupError) as gone:
            cleanup = s.kill_group(proc)
        self.assertEqual(cleanup, {"ok": True})
        self.assertEqual(gone.call_count, 1)


if __name__ == "__main__": unittest.main()
