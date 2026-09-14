from __future__ import annotations

import json
import fcntl
import math
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import sidekick_evaluation as evaluation


class EvaluationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="sidekick-evaluation-")
        self.root = Path(self.tmp.name) / "state"
        (self.root / "tasks").mkdir(parents=True, mode=0o700)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def add_task(self, task_id: str, **overrides: object) -> Path:
        task = self.root / "tasks" / task_id
        task.mkdir(mode=0o700)
        state: dict[str, object] = {
            "version": 1,
            "id": task_id,
            "source": str(self.root / "work-repo"),
            "source_commit": "a" * 40,
            "status": "prepared",
            "turns": [],
            "applied": False,
            "interrupted_attempt": False,
            "verification": None,
        }
        state.update(overrides)
        (task / "state.json").write_text(json.dumps(state), encoding="utf-8")
        return task

    def test_report_keeps_failures_unrecorded_and_excludes_smoke_legacy_source(self) -> None:
        prepared = "20260914T120000-aaaaaaaaaa"
        failed = "20260914T120001-bbbbbbbbbb"
        incomplete = "20260914T120002-cccccccccc"
        interrupted = "20260914T120003-dddddddddd"
        smoke = "20260914T120004-eeeeeeeeee"
        self.add_task(prepared)
        self.add_task(
            failed,
            status="worker_failed",
            turns=[{"returncode": 1, "stop": "exit", "elapsed_seconds": 0.25}],
            verification={"passed": False},
        )
        self.add_task(
            incomplete,
            status="needs_review",
            turns=[{"returncode": 0, "stop": "exit", "elapsed_seconds": None}],
        )
        self.add_task(interrupted, interrupted_attempt=True)
        self.add_task(smoke, source="smoke/legacy/repo", status="needs_review")
        legacy_storage = self.root / "smoke" / "tasks" / "20260914T120015-aaaaaaaaaa"
        legacy_storage.mkdir(parents=True, mode=0o700)
        (legacy_storage / "state.json").write_text(
            json.dumps({"id": legacy_storage.name, "status": "prepared"}),
            encoding="utf-8",
        )
        legacy_direct = self.root / "smoke" / "20260914T120016-bbbbbbbbbb"
        legacy_direct.mkdir(parents=True, mode=0o700)
        (legacy_direct / "state.json").write_text(
            json.dumps({"id": legacy_direct.name, "status": "prepared"}),
            encoding="utf-8",
        )

        report = evaluation.build_evaluation_report(self.root)
        rows = {row["task_id"]: row for row in report["rows"]}
        self.assertEqual(set(rows), {prepared, failed, incomplete, interrupted})
        self.assertEqual(report["summary"]["excluded_smoke"], 3)
        self.assertEqual(
            set(report["excluded_smoke_tasks"]),
            {smoke, legacy_storage.name, legacy_direct.name},
        )
        self.assertEqual(rows[failed]["status"], "failed")
        self.assertEqual(rows[failed]["outcome"], "failed")
        self.assertEqual(rows[prepared]["evaluation_status"], "unrecorded")
        self.assertEqual(rows[incomplete]["worker_elapsed_seconds"], None)
        self.assertEqual(report["metrics"]["worker_elapsed_seconds"]["missing_count"], 3)
        self.assertGreater(report["summary"]["unknown"], 0)

        with_smoke = evaluation.build_evaluation_report(self.root, include_smoke=True)
        self.assertEqual(len(with_smoke["rows"]), 7)
        self.assertTrue(next(row for row in with_smoke["rows"] if row["task_id"] == smoke)["smoke"])

    def test_corrupt_state_and_prepare_failure_are_visible(self) -> None:
        mismatch = "20260914T120005-fffffffffa"
        corrupt = "20260914T120006-1111111111"
        prepare_failed = "20260914T120007-2222222222"
        self.add_task(mismatch, id="20260914T120005-0000000000")
        corrupt_task = self.add_task(corrupt)
        (corrupt_task / "state.json").write_text("{broken", encoding="utf-8")
        failed_task = self.root / "tasks" / prepare_failed
        failed_task.mkdir(mode=0o700)
        (failed_task / "PREPARE_FAILED.txt").write_text("failure details", encoding="utf-8")

        report = evaluation.build_evaluation_report(self.root)
        rows = {row["task_id"]: row for row in report["rows"]}
        self.assertIn(mismatch, report["invalid_state_entries"])
        self.assertIn(corrupt, report["invalid_state_entries"])
        self.assertEqual(rows[prepare_failed]["status"], "failed")
        self.assertEqual(rows[prepare_failed]["outcome"], "failed")
        self.assertTrue(any(item["task_id"] == corrupt for item in report["errors"]))
        self.assertNotIn("failure details", json.dumps(report))

    def test_record_round_trip_is_private_and_defaults_null(self) -> None:
        task_id = "20260914T120008-3333333333"
        task = self.add_task(
            task_id,
            verification={"passed": True},
            status="needs_review",
            turns=[{"returncode": 0, "stop": "exit", "elapsed_seconds": 0.1}],
        )
        payload = {
            "acceptance_met": True,
            "independent_tests_passed": True,
            "post_apply_tests_passed": None,
            "lead_review_minutes": 1.5,
            "total_minutes": 4,
            "codex_usage_before": {"observation": "manual"},
            "codex_usage_after": "unknown",
            "devin_usage_before": None,
            "devin_usage_after": None,
            "parent_model": "Codex Astra",
            "parent_effort": "high",
            "parent_model_evidence": "session metadata",
            "observed_total_cost_usd": 0.5,
            "cost_evidence": "provider receipt",
            "notes": "reviewed",
        }
        record = evaluation.record_evaluation(self.root, task_id, payload)
        self.assertEqual(record["schema_version"], 1)
        self.assertEqual(record["task_id"], task_id)
        self.assertTrue(record["recorded_at"])
        self.assertIsNone(record["post_apply_tests_passed"])
        self.assertEqual(stat.S_IMODE((task / "evaluation.json").stat().st_mode), 0o600)

        stored = json.loads((task / "evaluation.json").read_text(encoding="utf-8"))
        expected_keys = set(evaluation._EVALUATION_KEYS)
        self.assertEqual(set(stored), expected_keys)
        report = evaluation.build_evaluation_report(self.root)
        row = report["rows"][0]
        self.assertEqual(row["outcome"], "accepted")
        self.assertEqual(row["observed_total_cost_usd"], 0.5)
        self.assertEqual(report["metrics"]["observed_total_cost_usd"]["sum"], 0.5)

    def test_record_validation_rejects_unknown_types_and_unproven_claims(self) -> None:
        task_id = "20260914T120009-4444444444"
        self.add_task(task_id, verification={"passed": True})
        invalid_payloads = [
            {"unknown": 1},
            {"acceptance_met": 1},
            {"lead_review_minutes": True},
            {"lead_review_minutes": math.nan},
            {"total_minutes": float("inf")},
            {"total_minutes": -1},
            {"acceptance_met": True, "independent_tests_passed": False},
            {"parent_model": "Codex Astra"},
            {"observed_total_cost_usd": 1},
        ]
        for payload in invalid_payloads:
            with self.subTest(payload=payload):
                with self.assertRaises(ValueError):
                    evaluation.record_evaluation(self.root, task_id, payload)
        with self.assertRaises(ValueError):
            evaluation.record_evaluation(
                self.root,
                task_id,
                {
                    "acceptance_met": True,
                    "independent_tests_passed": True,
                    "observed_total_cost_usd": 1,
                    "cost_evidence": "",
                },
            )

        failed_native = "20260914T120010-5555555555"
        self.add_task(failed_native, verification={"passed": False})
        with self.assertRaises(ValueError):
            evaluation.record_evaluation(
                self.root,
                failed_native,
                {"acceptance_met": True, "independent_tests_passed": True},
            )

    def test_overwrite_requires_replace_and_preserves_previous_record(self) -> None:
        task_id = "20260914T120011-6666666666"
        task = self.add_task(task_id)
        first = evaluation.record_evaluation(self.root, task_id, {"notes": "first"})
        with self.assertRaises(ValueError):
            evaluation.record_evaluation(self.root, task_id, {"notes": "second"})
        second = evaluation.record_evaluation(self.root, task_id, {"notes": "second"}, replace=True)
        self.assertEqual(second["notes"], "second")
        previous = json.loads((task / "evaluation.json.previous").read_text(encoding="utf-8"))
        self.assertEqual(previous["notes"], first["notes"])
        self.assertEqual(stat.S_IMODE((task / "evaluation.json.previous").stat().st_mode), 0o600)

    def test_corrupt_evaluation_is_reported_without_being_counted(self) -> None:
        task_id = "20260914T120013-8888888888"
        task = self.add_task(task_id, verification={"passed": True})
        (task / "evaluation.json").write_text('{"schema_version": 1, "oops": true}', encoding="utf-8")
        os.chmod(task / "evaluation.json", 0o600)
        report = evaluation.build_evaluation_report(self.root)
        row = report["rows"][0]
        self.assertEqual(row["evaluation_status"], "invalid")
        self.assertEqual(row["outcome"], "unknown")
        self.assertEqual(report["metrics"]["observed_total_cost_usd"]["observed_count"], 0)
        self.assertTrue(report["errors"])

    def test_record_uses_nonblocking_per_task_lock(self) -> None:
        task_id = "20260914T120014-9999999999"
        task = self.add_task(task_id)
        lock_path = task / ".lock"
        with lock_path.open("a+") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            try:
                with self.assertRaises(OSError):
                    evaluation.record_evaluation(self.root, task_id, {})
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)

    def test_retry_history_does_not_fail_a_successful_latest_attempt(self) -> None:
        task_id = "20260914T120017-aaaaaaaaaa"
        self.add_task(
            task_id,
            status="applied_uncommitted",
            applied=True,
            turns=[
                {"returncode": 1, "stop": "exit", "elapsed_seconds": 0.2},
                {"returncode": 0, "stop": "exit", "elapsed_seconds": 0.3},
            ],
            verification={"passed": True},
        )
        evaluation.record_evaluation(
            self.root,
            task_id,
            {"acceptance_met": True, "independent_tests_passed": True},
        )

        row = evaluation.build_evaluation_report(self.root)["rows"][0]
        self.assertEqual(row["status"], "applied")
        self.assertEqual(row["outcome"], "accepted")
        self.assertEqual(row["retries"], 1)
        self.assertEqual(row["failed_attempts"], 1)

    def test_missing_native_verification_keeps_acceptance_unknown(self) -> None:
        task_id = "20260914T120018-bbbbbbbbbb"
        self.add_task(
            task_id,
            status="needs_review",
            turns=[{"returncode": 0, "stop": "exit", "elapsed_seconds": 0.1}],
            verification=None,
        )
        evaluation.record_evaluation(
            self.root,
            task_id,
            {"acceptance_met": True, "independent_tests_passed": True},
        )

        row = evaluation.build_evaluation_report(self.root)["rows"][0]
        self.assertIsNone(row["native_verification_passed"])
        self.assertEqual(row["outcome"], "unknown")
        self.assertEqual(row["assessed"], True)
        self.assertEqual(evaluation.build_evaluation_report(self.root)["summary"]["accepted"], 0)

    def test_interrupted_manual_failure_is_assessed_but_null_is_unknown(self) -> None:
        failed_id = "20260914T120019-cccccccccc"
        unknown_id = "20260914T120020-dddddddddd"
        common = {
            "status": "interrupted",
            "interrupted_attempt": True,
            "turns": [{"returncode": 0, "stop": "signal", "elapsed_seconds": 0.2}],
            "verification": None,
        }
        self.add_task(failed_id, **common)
        self.add_task(unknown_id, **common)
        evaluation.record_evaluation(
            self.root,
            failed_id,
            {"acceptance_met": False, "independent_tests_passed": False},
        )
        evaluation.record_evaluation(self.root, unknown_id, {})

        rows = {row["task_id"]: row for row in evaluation.build_evaluation_report(self.root)["rows"]}
        self.assertEqual(rows[failed_id]["native_status"], "interrupted")
        self.assertEqual(rows[failed_id]["status"], "interrupted")
        self.assertEqual(rows[failed_id]["outcome"], "failed")
        self.assertTrue(rows[failed_id]["assessed"])
        self.assertEqual(rows[unknown_id]["outcome"], "unknown")
        self.assertFalse(rows[unknown_id]["assessed"])

    def test_accepted_rate_uses_attempted_denominator_and_keeps_assessed_rate(self) -> None:
        accepted_id = "20260914T120021-eeeeeeeeee"
        failed_id = "20260914T120022-fffffffffa"
        unknown_id = "20260914T120023-1111111111"
        prepared_id = "20260914T120024-2222222222"
        self.add_task(
            accepted_id,
            status="applied_uncommitted",
            applied=True,
            turns=[{"returncode": 0, "stop": "exit", "elapsed_seconds": 0.1}],
            verification={"passed": True},
        )
        self.add_task(
            failed_id,
            status="worker_failed",
            turns=[{"returncode": 1, "stop": "exit", "elapsed_seconds": 0.1}],
            verification={"passed": False},
        )
        self.add_task(
            unknown_id,
            status="needs_review",
            turns=[{"returncode": 0, "stop": "exit", "elapsed_seconds": 0.1}],
            verification=None,
        )
        self.add_task(prepared_id)
        evaluation.record_evaluation(
            self.root,
            accepted_id,
            {"acceptance_met": True, "independent_tests_passed": True},
        )

        summary = evaluation.build_evaluation_report(self.root)["summary"]
        self.assertEqual(summary["attempted"], 3)
        self.assertEqual(summary["assessed"], 1)
        self.assertEqual(summary["accepted"], 1)
        self.assertEqual(summary["rates"]["accepted"]["denominator"], 3)
        self.assertEqual(summary["rates"]["accepted_among_assessed"]["denominator"], 1)

    def test_paths_symlinks_and_task_id_are_rejected(self) -> None:
        task_id = "20260914T120012-7777777777"
        task = self.add_task(task_id)
        with self.assertRaises(ValueError):
            evaluation.record_evaluation(self.root, "../escape", {})
        with self.assertRaises(OSError):
            evaluation.record_evaluation(self.root, "20260914T120013-8888888888", {})

        state = task / "state.json"
        state.unlink()
        state.symlink_to(self.root / "elsewhere.json")
        with self.assertRaises(ValueError):
            evaluation.record_evaluation(self.root, task_id, {})

        state.unlink()
        state.write_text(json.dumps({"id": "20260914T000000-0000000000"}), encoding="utf-8")
        with self.assertRaises(ValueError):
            evaluation.record_evaluation(self.root, task_id, {})


if __name__ == "__main__":
    unittest.main()
