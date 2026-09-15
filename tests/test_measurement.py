from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import io
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
import sys

sys.path.insert(0, str(ROOT))
import sidekick_measurement as measurement
import swe_sidekick


def counters(input_tokens, output_tokens, cached=0, cache_write=0, reasoning=0):
    return {
        "input_tokens": input_tokens,
        "cached_input_tokens": cached,
        "cache_write_input_tokens": cache_write,
        "output_tokens": output_tokens,
        "reasoning_output_tokens": reasoning,
        "total_tokens": input_tokens + output_tokens,
    }


class MeasurementTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="measurement-test-")
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.rollout = self.home / ".codex/sessions/2026/09"
        self.rollout.mkdir(parents=True)
        self.state = self.root / "state"
        self.session = "session-test-1"
        self.thread = "thread-test-1"
        self.root_turn = "root-turn-1"
        self.turn = "turn-1"
        self.model = "gpt-test"
        self.effort = "high"
        self.lines = []
        self._append("session_meta", {"id": self.thread, "session_id": self.session})
        self._append("turn_context", {"turn_id": self.turn,
                                       "root_turn_id": self.root_turn, "model": self.model,
                                       "effort": self.effort})
        self.append_usage(100, 10, 20, 2, 3, 500, 50, 200, 5, 11)
        self.write_rollout()
        self.env = {"HOME": str(self.home), "CODEX_SESSION_ID": self.session,
                    "CODEX_THREAD_ID": self.thread}

    def tearDown(self):
        self.tmp.cleanup()

    def _append(self, kind, payload):
        self.lines.append({"timestamp": f"2026-09-15T00:00:{len(self.lines):02d}Z",
                           "ordinal": len(self.lines), "type": kind, "payload": payload})

    def append_usage(self, usage_i, usage_o, usage_c, usage_w, usage_r,
                     thread_i, thread_o, thread_c, thread_w, thread_r):
        self._append("token_usage_record", {
            "session_id": self.session,
            "thread_id": self.thread,
            "turn_id": self.turn,
            "root_turn_id": self.root_turn,
            "response_id": "response-secret",
            "usage": counters(usage_i, usage_o, usage_c, usage_w, usage_r),
            "thread_token_usage": counters(thread_i, thread_o, thread_c, thread_w, thread_r),
            "turn_token_usage": counters(usage_i, usage_o, usage_c, usage_w, usage_r),
            "message": "prompt-secret-response-secret",
        })

    def write_rollout(self, name="rollout.jsonl"):
        self.path = self.rollout / name
        self.path.write_text("\n".join(json.dumps(line) for line in self.lines) + "\n", encoding="utf-8")

    def append_snapshot(self, thread_i, thread_o, thread_c, thread_w, thread_r,
                        turn_i=0, turn_o=0, turn_c=0, turn_w=0, turn_r=0,
                        model=None, effort=None):
        if model is not None or effort is not None:
            context = {"turn_id": self.turn,
                       "root_turn_id": self.root_turn,
                       "model": model or self.model, "effort": effort or self.effort}
            self._append("turn_context", context)
        self.append_usage(1, 1, 0, 0, 0, thread_i, thread_o, thread_c, thread_w, thread_r)
        self.lines[-1]["payload"]["turn_token_usage"] = counters(
            turn_i, turn_o, turn_c, turn_w, turn_r)
        self.write_rollout()

    def new_turn(self, number):
        self.turn = f"turn-{number}"
        self.root_turn = f"root-turn-{number}"
        self._append("turn_context", {"turn_id": self.turn,
                                       "root_turn_id": self.root_turn, "model": self.model,
                                       "effort": self.effort})
        self.write_rollout()

    def invoke(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with patch.dict(os.environ, self.env, clear=False), redirect_stdout(out), redirect_stderr(err):
            code = swe_sidekick.main(["--state-dir", str(self.state), *args])
        return code, out.getvalue(), err.getvalue()

    def start(self, case="case-1", arm="lead-only"):
        code, out, err = self.invoke("measure-start", "--case", case, "--arm", arm)
        self.assertEqual(code, 0, out + err)
        return json.loads(out)

    def test_start_baseline_subtracts_current_root_turn_and_hides_content(self):
        result = self.start()
        expected = counters(400, 40, 180, 0, 8)
        expected["cache_write_input_tokens"] = 3
        self.assertEqual(set(result), {
            "trial_id", "case", "arm", "status", "consistent", "eligible", "model", "effort",
        })
        self.assertNotIn("baseline", result)
        public = json.dumps(result)
        for private_value in (self.session, self.thread, self.root_turn, "2026-09-15T"):
            self.assertNotIn(private_value, public)
        self.assertEqual(result["status"], "in_progress")
        trial_files = list((self.state / "measurements").glob("*.json"))
        self.assertEqual(len(trial_files), 1)
        self.assertEqual(stat.S_IMODE((self.state).stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE((self.state / "measurements").stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(trial_files[0].stat().st_mode), 0o600)
        private_trial = json.loads(trial_files[0].read_text(encoding="utf-8"))
        self.assertEqual(private_trial["baseline"]["counters"], expected)
        self.assertEqual(private_trial["session_id"], self.session)
        self.assertEqual(private_trial["thread_id"], self.thread)
        self.assertEqual(private_trial["root_turn_id"], self.root_turn)
        raw = trial_files[0].read_text(encoding="utf-8")
        self.assertNotIn("response-secret", raw)
        self.assertNotIn("prompt-secret", raw)
        self.assertNotIn("message", raw)
        self.assertNotIn("response_id", raw)

    def test_stop_records_cache_counters_and_coverage_note(self):
        trial = self.start()
        self.append_snapshot(650, 70, 250, 8, 15, 250, 20, 50, 3, 6)
        code, out, err = self.invoke("measure-stop", "--trial", trial["trial_id"])
        self.assertEqual(code, 0, out + err)
        result = json.loads(out)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["deltas"], counters(250, 30, 70, 5, 7))
        self.assertIn("Content after the stop snapshot is not covered", result["coverage_note"])
        self.assertEqual(set(result), {
            "trial_id", "case", "arm", "status", "consistent", "eligible", "model", "effort",
            "deltas", "coverage_note",
        })
        report = json.loads(self.invoke("measurement-report")[1])
        self.assertEqual(set(report["trials"][0]), {
            "trial_id", "case", "arm", "status", "model", "effort", "consistent", "eligible",
            "deltas", "ineligible_reasons",
        })
        report_text = json.dumps(report)
        for private_value in (self.session, self.thread, self.root_turn, "2026-09-15T"):
            self.assertNotIn(private_value, report_text)
        for private_key in ("session_id", "thread_id", "root_turn_id", "baseline", "ordinal", "timestamp"):
            self.assertNotIn(private_key, report_text)

    def test_same_session_and_identity_failures(self):
        trial = self.start()
        self.env["CODEX_THREAD_ID"] = "different-thread"
        code, _, err = self.invoke("measure-stop", "--trial", trial["trial_id"])
        self.assertNotEqual(code, 0)
        self.assertIn("session changed", err)

    def test_model_change_completes_but_is_ineligible(self):
        trial = self.start()
        self.append_snapshot(650, 70, 250, 8, 15, 250, 20, 50, 3, 6, model="gpt-other")
        code, out, err = self.invoke("measure-stop", "--trial", trial["trial_id"])
        self.assertEqual(code, 0, out + err)
        result = json.loads(out)
        self.assertFalse(result["consistent"])
        self.assertFalse(result["eligible"])
        self.assertIn("model changed during trial", result["ineligible_reasons"])

    def test_report_excludes_pair_with_different_confirmed_model(self):
        lead = self.start(case="model-mismatch", arm="lead-only")
        self.append_snapshot(650, 70, 250, 8, 15, 250, 20, 50, 3, 6)
        code, _, err = self.invoke("measure-stop", "--trial", lead["trial_id"])
        self.assertEqual(code, 0, err)

        # The first trial has already stopped under gpt-test.  Change the
        # confirmed context before starting the sidekick arm; both trials can
        # therefore be individually eligible while their pair is incomparable.
        self.append_snapshot(700, 75, 255, 8, 16, 300, 25, 55, 3, 7, model="gpt-other")
        side = self.start(case="model-mismatch", arm="sidekick")
        self.append_snapshot(750, 80, 260, 8, 17, 350, 30, 60, 3, 8, model="gpt-other")
        code, _, err = self.invoke("measure-stop", "--trial", side["trial_id"])
        self.assertEqual(code, 0, err)

        report = json.loads(self.invoke("measurement-report", "--case", "model-mismatch")[1])
        self.assertEqual(report["groups"], [])
        self.assertEqual(len(report["trials"]), 2)
        self.assertTrue(all(trial["eligible"] for trial in report["trials"]))
        self.assertTrue(any(
            issue.get("reason") == "paired trials have mismatched model or effort; comparison excluded"
            for issue in report["issues"]
        ))

    def test_report_pairs_negative_savings_and_zero_denominator(self):
        lead = self.start(case="pair", arm="lead-only")
        self.append_snapshot(650, 70, 250, 8, 15, 250, 20, 50, 3, 6)
        self.invoke("measure-stop", "--trial", lead["trial_id"])
        side = self.start(case="pair", arm="sidekick")
        self.append_snapshot(700, 80, 255, 8, 16, 300, 30, 55, 3, 7)
        self.invoke("measure-stop", "--trial", side["trial_id"])
        result = json.loads(self.invoke("measurement-report")[1])
        group = result["groups"][0]
        self.assertEqual(group["counters"]["input_tokens"], {
            "lead_only": 250, "sidekick": 300, "saved": -50,
            "reduction_percent": -20.0})
        # Add a valid pair where the lead denominator is zero.
        self.new_turn(2)
        zero_lead = self.start(case="zero", arm="lead-only")
        self.append_snapshot(700, 80, 255, 8, 16, 0, 0, 0, 0, 0)
        self.invoke("measure-stop", "--trial", zero_lead["trial_id"])
        zero_side = self.start(case="zero", arm="sidekick")
        self.append_snapshot(710, 81, 260, 8, 17, 10, 1, 5, 0, 1)
        self.invoke("measure-stop", "--trial", zero_side["trial_id"])
        result = json.loads(self.invoke("measurement-report", "--case", "zero")[1])
        self.assertIsNone(result["groups"][0]["counters"]["input_tokens"]["reduction_percent"])

    def test_unpaired_arm_is_reported_without_reduction(self):
        trial = self.start(case="unpaired", arm="lead-only")
        self.append_snapshot(650, 70, 250, 8, 15, 250, 20, 50, 3, 6)
        self.invoke("measure-stop", "--trial", trial["trial_id"])
        result = json.loads(self.invoke("measurement-report", "--case", "unpaired")[1])
        self.assertEqual(result["groups"], [])
        self.assertTrue(any("exactly one" in issue.get("reason", "") for issue in result["issues"]))

    def test_ambiguous_malformed_symlink_and_nonmonotonic_fail_closed(self):
        self.start()
        self.lines[-1]["ordinal"] = 2
        self.lines.append(dict(self.lines[-1]))
        self.write_rollout()
        with self.assertRaises(measurement.MeasurementError):
            measurement.measure_start(self.state, "duplicate", "lead-only", environ=self.env)

        self.lines[-1]["ordinal"] = 3
        self.lines[-1]["payload"] = dict(self.lines[-1]["payload"])
        self.lines[-1]["payload"]["thread_token_usage"] = counters(1, 1)
        self.write_rollout("bad.jsonl")
        with self.assertRaises(measurement.MeasurementError):
            measurement.measure_start(self.state, "bad", "lead-only", environ=self.env)

        self.path.unlink()
        self.path = self.rollout / "link.jsonl"
        self.path.symlink_to(self.rollout / "bad.jsonl")
        with self.assertRaises(measurement.MeasurementError):
            measurement.measure_start(self.state, "symlink", "lead-only", environ=self.env)

    def test_invalid_case_trial_id_and_duplicate_start_are_rejected(self):
        with self.assertRaises(measurement.MeasurementError):
            measurement.validate_case("../unsafe")
        trial = self.start()
        self.assertRegex(trial["trial_id"], measurement.TRIAL_RE)
        # The generated id is owned by the state file; a second start is a new
        # id and therefore does not overwrite it.
        second = self.start()
        self.assertNotEqual(trial["trial_id"], second["trial_id"])


if __name__ == "__main__":
    unittest.main()
