"""Local, evidence-preserving metrics for SWE sidekick tasks.

The module deliberately has no dependency on :mod:`swe_sidekick`.  The sidekick
CLI and this recorder share the task directory on disk, while the recorder only
reads ``state.json`` and writes the private ``evaluation.json`` belonging to a
task.  It never executes a task, reads its logs, or changes the source project.
"""

from __future__ import annotations

import contextlib
import datetime as _datetime
import fcntl
import json
import math
import os
from pathlib import Path
import re
import stat
import tempfile
from typing import Any, Iterator


SCHEMA_VERSION = 1
TASK_ID_RE = re.compile(r"[0-9]{8}T[0-9]{6}-[0-9a-f]{10}\Z")

# State files are produced by the sidekick and may contain packet metadata, but
# evaluation output is intentionally much smaller.  These limits also keep a
# malformed local file from becoming an unbounded report.
MAX_STATE_BYTES = 16 * 1024 * 1024
MAX_EVALUATION_BYTES = 256 * 1024
MAX_SHORT_TEXT = 4096
MAX_MANUAL_BYTES = 32 * 1024
MAX_MANUAL_DEPTH = 5
MAX_MANUAL_ITEMS = 256

_EVALUATION_INPUT_KEYS = {
    "schema_version",
    "task_id",
    "acceptance_met",
    "independent_tests_passed",
    "post_apply_tests_passed",
    "lead_review_minutes",
    "total_minutes",
    "codex_usage_before",
    "codex_usage_after",
    "devin_usage_before",
    "devin_usage_after",
    "parent_model",
    "parent_effort",
    "parent_model_evidence",
    "observed_total_cost_usd",
    "cost_evidence",
    "notes",
}
_EVALUATION_KEYS = _EVALUATION_INPUT_KEYS | {"recorded_at"}
_OPTIONAL_EVALUATION_KEYS = _EVALUATION_INPUT_KEYS - {"schema_version", "task_id"}
_BOOLEAN_KEYS = {
    "acceptance_met",
    "independent_tests_passed",
    "post_apply_tests_passed",
}
_NUMBER_KEYS = {
    "lead_review_minutes",
    "total_minutes",
    "observed_total_cost_usd",
}
_USAGE_KEYS = {
    "codex_usage_before",
    "codex_usage_after",
    "devin_usage_before",
    "devin_usage_after",
}
_PARENT_KEYS = {"parent_model", "parent_effort", "parent_model_evidence"}
_FAILURE_NATIVE_STATUSES = {
    "failed",
    "worker_failed",
    "model_mismatch",
    "scope_violation",
    "prepare_failed",
}
_KNOWN_NATIVE_STATUSES = _FAILURE_NATIVE_STATUSES | {
    "prepared",
    "needs_review",
    "incomplete_no_changes",
    "interrupted",
    "running",
    "retrying",
    "applied",
    "applied_uncommitted",
    "complete",
    "completed",
}


class _TaskLockedError(OSError):
    """A task was changing while a read-only report tried to inspect it."""


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _json_bytes(value: Any) -> bytes:
    try:
        return (
            json.dumps(
                value,
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, UnicodeError, ValueError, OverflowError) as exc:
        raise ValueError("value is not JSON serializable") from exc


def _short_text(value: Any, field: str, *, nonempty: bool = False) -> str:
    if not isinstance(value, str) or "\x00" in value or len(value) > MAX_SHORT_TEXT:
        raise ValueError(f"{field} must be a short string")
    if nonempty and not value.strip():
        raise ValueError(f"{field} must be nonempty")
    return value


def _finite_nonnegative(value: Any, field: str) -> int | float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be a finite nonnegative number or null")
    try:
        finite = math.isfinite(float(value))
    except (OverflowError, ValueError):
        finite = False
    if not finite or value < 0:
        raise ValueError(f"{field} must be a finite nonnegative number or null")
    return value


def _validate_manual_value(value: Any, field: str) -> Any:
    """Validate a short, JSON-like manual observation and return it unchanged."""

    if value is None:
        return None
    if isinstance(value, str):
        return _short_text(value, field)
    if not isinstance(value, dict):
        raise ValueError(f"{field} must be null, a short string, or an object")

    count = 0

    def visit(item: Any, depth: int) -> None:
        nonlocal count
        if depth > MAX_MANUAL_DEPTH:
            raise ValueError(f"{field} object is too deeply nested")
        count += 1
        if count > MAX_MANUAL_ITEMS:
            raise ValueError(f"{field} object is too large")
        if item is None or isinstance(item, bool):
            return
        if isinstance(item, str):
            _short_text(item, field)
            return
        if isinstance(item, (int, float)):
            if isinstance(item, float) and not math.isfinite(item):
                raise ValueError(f"{field} contains a non-finite number")
            return
        if isinstance(item, list):
            for child in item:
                visit(child, depth + 1)
            return
        if isinstance(item, dict):
            for key, child in item.items():
                _short_text(key, f"{field} key", nonempty=True)
                visit(child, depth + 1)
            return
        raise ValueError(f"{field} contains a non-JSON value")

    visit(value, 0)
    if len(_json_bytes(value)) > MAX_MANUAL_BYTES:
        raise ValueError(f"{field} object is too large")
    return value


def _validate_task_id(task_id: Any) -> str:
    if not isinstance(task_id, str) or not TASK_ID_RE.fullmatch(task_id):
        raise ValueError("invalid task ID")
    return task_id


def _lstat(path: Path) -> os.stat_result | None:
    try:
        return path.lstat()
    except FileNotFoundError:
        return None


def _require_directory(path: Path, label: str) -> None:
    info = _lstat(path)
    if info is None:
        raise OSError(f"{label} is missing")
    if stat.S_ISLNK(info.st_mode):
        raise ValueError(f"{label} is a symlink")
    if not stat.S_ISDIR(info.st_mode):
        raise OSError(f"{label} is not a directory")


def _root_and_tasks(root: Path | os.PathLike[str], *, require_tasks: bool) -> tuple[Path, Path]:
    if not isinstance(root, (Path, str, os.PathLike)):
        raise ValueError("root must be a path")
    root_path = Path(root).expanduser()
    _require_directory(root_path, "evaluation root")
    tasks = root_path / "tasks"
    if _lstat(tasks) is None:
        if require_tasks:
            raise OSError("tasks directory is missing")
        return root_path, tasks
    _require_directory(tasks, "tasks directory")
    return root_path, tasks


def _regular_mode(path: Path, label: str, *, max_bytes: int | None = None) -> os.stat_result:
    info = _lstat(path)
    if info is None:
        raise OSError(f"{label} is missing")
    if stat.S_ISLNK(info.st_mode):
        raise ValueError(f"{label} is a symlink")
    if not stat.S_ISREG(info.st_mode):
        raise ValueError(f"{label} is not a regular file")
    if max_bytes is not None and info.st_size > max_bytes:
        raise ValueError(f"{label} is too large")
    return info


def _open_read_nofollow(path: Path, label: str, *, max_bytes: int) -> bytes:
    _regular_mode(path, label, max_bytes=max_bytes)
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise OSError(f"could not open {label}") from exc
    try:
        info = os.fstat(fd)
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
            raise ValueError(f"{label} is not a regular file")
        if info.st_size > max_bytes:
            raise ValueError(f"{label} is too large")
        with os.fdopen(fd, "rb") as handle:
            fd = -1
            data = handle.read(max_bytes + 1)
        if len(data) > max_bytes:
            raise ValueError(f"{label} is too large")
        return data
    finally:
        if fd != -1:
            os.close(fd)


def _read_json_file(path: Path, label: str, *, max_bytes: int) -> Any:
    data = _open_read_nofollow(path, label, max_bytes=max_bytes)
    try:
        text = data.decode("utf-8")
        return json.loads(text, object_pairs_hook=_reject_duplicate_keys)
    except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
        # Keep report errors independent of paths and of any raw file content.
        if isinstance(exc, ValueError) and str(exc) == "duplicate JSON key":
            raise
        raise ValueError(f"invalid {label} JSON") from exc


def _atomic_write(path: Path, data: bytes, *, mode: int = 0o600) -> None:
    info = _lstat(path)
    if info is not None and stat.S_ISLNK(info.st_mode):
        raise ValueError("refusing to replace a symlink")
    if info is not None and not stat.S_ISREG(info.st_mode):
        raise ValueError("output path is not a regular file")
    parent_info = _lstat(path.parent)
    if parent_info is None:
        raise OSError("output directory is missing")
    if stat.S_ISLNK(parent_info.st_mode) or not stat.S_ISDIR(parent_info.st_mode):
        raise ValueError("output directory is invalid")
    fd, temporary = tempfile.mkstemp(prefix=".evaluation-", dir=str(path.parent))
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, "wb") as handle:
            fd = -1
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        final_info = _lstat(path)
        if final_info is None or stat.S_ISLNK(final_info.st_mode) or not stat.S_ISREG(final_info.st_mode):
            raise OSError("atomic evaluation write did not produce a regular file")
        if stat.S_IMODE(final_info.st_mode) != mode:
            os.chmod(path, mode)
    finally:
        if fd != -1:
            os.close(fd)
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def _lock_fd(path: Path, *, create: bool) -> int:
    info = _lstat(path)
    if info is not None and stat.S_ISLNK(info.st_mode):
        raise ValueError("task lock is a symlink")
    flags = os.O_RDWR
    if create:
        flags |= os.O_CREAT
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        return os.open(path, flags, 0o600)
    except OSError as exc:
        raise OSError("could not open task lock") from exc


@contextlib.contextmanager
def _exclusive_task_lock(root: Path, task_id: str) -> Iterator[Path]:
    task = root / "tasks" / task_id
    task_info = _lstat(task)
    if task_info is None:
        raise OSError("task is missing")
    if stat.S_ISLNK(task_info.st_mode) or not stat.S_ISDIR(task_info.st_mode):
        raise ValueError("task directory is invalid")
    lock_path = task / ".lock"
    fd = _lock_fd(lock_path, create=True)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise OSError("task is already locked") from exc
        yield task
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


@contextlib.contextmanager
def _shared_existing_task_lock(task: Path) -> Iterator[bool]:
    """Take a nonblocking shared lock when the task already has one.

    Reports should not create lock files in every task merely by reading them.
    The writer path always creates and takes the same per-task lock.
    """

    task_info = _lstat(task)
    if task_info is None:
        raise OSError("task is missing")
    if stat.S_ISLNK(task_info.st_mode) or not stat.S_ISDIR(task_info.st_mode):
        raise ValueError("task directory is invalid")
    path = task / ".lock"
    info = _lstat(path)
    if info is None:
        yield False
        return
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise ValueError("task lock is invalid")
    fd = _lock_fd(path, create=False)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise _TaskLockedError("task is already locked") from exc
        yield True
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


def _native_verification(state: dict[str, Any]) -> bool | None:
    verification = state.get("verification")
    if verification is None:
        return None
    if not isinstance(verification, dict):
        raise ValueError("state verification is invalid")
    passed = verification.get("passed")
    if passed is not None and not isinstance(passed, bool):
        raise ValueError("state verification result is invalid")
    return passed


def _validate_turns(turns: Any) -> list[dict[str, Any]]:
    if not isinstance(turns, list):
        raise ValueError("state turns is invalid")
    result: list[dict[str, Any]] = []
    for turn in turns:
        if not isinstance(turn, dict):
            raise ValueError("state turn is invalid")
        for key in ("returncode",):
            if key in turn and (isinstance(turn[key], bool) or not isinstance(turn[key], int)):
                raise ValueError("state turn return code is invalid")
        for key in ("elapsed_seconds", "worker_elapsed_seconds"):
            if key in turn:
                _finite_nonnegative(turn[key], f"state turn {key}")
        for key in ("selected_model", "model_check"):
            if key in turn:
                _short_text(turn[key], f"state turn {key}")
        if "reported_models" in turn:
            models = turn["reported_models"]
            if not isinstance(models, list):
                raise ValueError("state reported models are invalid")
            if len(models) > MAX_MANUAL_ITEMS:
                raise ValueError("state reported models are too many")
            for model in models:
                _short_text(model, "state reported model")
        if "stop" in turn:
            _short_text(turn["stop"], "state turn stop", nonempty=True)
        result.append(turn)
    return result


def _validate_state(task_id: str, state: Any) -> dict[str, Any]:
    if not isinstance(state, dict):
        raise ValueError("state JSON must be an object")
    state_id = state.get("id")
    alternate_id = state.get("task_id")
    if state_id is None:
        state_id = alternate_id
    elif alternate_id is not None and alternate_id != state_id:
        raise ValueError("state task IDs disagree")
    if state_id != task_id:
        raise ValueError("state task ID does not match task directory")

    source_commit = state.get("source_commit")
    if source_commit is not None:
        _short_text(source_commit, "state source commit", nonempty=True)
    status = state.get("status", "incomplete")
    _short_text(status, "state status", nonempty=True)
    turns = _validate_turns(state["turns"] if "turns" in state else [])
    applied = state.get("applied")
    if applied is not None and not isinstance(applied, bool):
        raise ValueError("state applied flag is invalid")
    interrupted = state.get("interrupted_attempt", False)
    if not isinstance(interrupted, bool):
        raise ValueError("state interrupted flag is invalid")
    native_verification = _native_verification(state)
    source = state.get("source")
    if source is not None:
        _short_text(source, "state source")
    return {
        "source": source,
        "source_commit": source_commit,
        "status": status,
        "turns": turns,
        "applied": applied,
        "interrupted_attempt": interrupted,
        "native_verification_passed": native_verification,
    }


def _normalise_evaluation(
    task_id: str,
    payload: Any,
    *,
    state_info: dict[str, Any] | None = None,
    recorded_at: str | None = None,
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("evaluation payload must be an object")
    unknown = set(payload) - _EVALUATION_INPUT_KEYS
    if "recorded_at" in payload:
        # recorded_at is controlled by this module, so callers cannot spoof it.
        raise ValueError("recorded_at is assigned automatically")
    if unknown:
        raise ValueError("evaluation contains unknown keys")
    schema_version = payload.get("schema_version", SCHEMA_VERSION)
    if isinstance(schema_version, bool) or not isinstance(schema_version, int) or schema_version != SCHEMA_VERSION:
        raise ValueError("unsupported evaluation schema version")
    payload_task_id = payload.get("task_id", task_id)
    if payload_task_id != task_id:
        raise ValueError("evaluation task ID does not match task")

    record: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "task_id": task_id,
    }
    for key in _OPTIONAL_EVALUATION_KEYS:
        value = payload.get(key)
        if key in _BOOLEAN_KEYS:
            if value is not None and not isinstance(value, bool):
                raise ValueError(f"{key} must be boolean or null")
            record[key] = value
        elif key in _NUMBER_KEYS:
            record[key] = _finite_nonnegative(value, key)
        elif key in _USAGE_KEYS:
            record[key] = _validate_manual_value(value, key)
        elif key in _PARENT_KEYS:
            # The all-or-none check below gives the useful error for partial
            # parent proof; validate strings here when present.
            if value is not None:
                record[key] = _short_text(value, key, nonempty=True)
            else:
                record[key] = None
        elif key == "cost_evidence":
            if value is not None:
                record[key] = _short_text(value, key, nonempty=True)
            else:
                record[key] = None
        elif key == "notes":
            record[key] = _short_text(value, key) if value is not None else None
        else:  # pragma: no cover - the key sets above are exhaustive.
            raise ValueError(f"unsupported evaluation field: {key}")

    parent_values = [record[key] for key in _PARENT_KEYS]
    if any(value is not None for value in parent_values) and not all(
        isinstance(value, str) and value.strip() for value in parent_values
    ):
        raise ValueError("parent model, effort, and evidence must be all null or all nonempty")

    if record["observed_total_cost_usd"] is not None:
        evidence = record["cost_evidence"]
        if not isinstance(evidence, str) or not evidence.strip():
            raise ValueError("cost_evidence is required when cost is recorded")

    if record["acceptance_met"] is True and record["independent_tests_passed"] is False:
        raise ValueError("acceptance_met cannot be true when independent tests failed")
    if state_info is not None and record["acceptance_met"] is True:
        if state_info["native_verification_passed"] is False:
            raise ValueError("acceptance_met conflicts with failed native verification")

    record["recorded_at"] = recorded_at or _utc_now()
    return record


def _validate_stored_evaluation(task_id: str, value: Any, *, state_info: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("evaluation JSON must be an object")
    if set(value) - _EVALUATION_KEYS:
        raise ValueError("evaluation contains unknown keys")
    for required in ("schema_version", "task_id", "recorded_at"):
        if required not in value:
            raise ValueError(f"evaluation is missing {required}")
    _short_text(value["recorded_at"], "evaluation recorded_at", nonempty=True)
    # Reuse all type and semantic checks, then retain the stored timestamp.
    payload = {key: value[key] for key in _EVALUATION_INPUT_KEYS if key in value}
    return _normalise_evaluation(
        task_id,
        payload,
        state_info=state_info,
        recorded_at=value["recorded_at"],
    )


def _utc_now() -> str:
    return _datetime.datetime.now(_datetime.timezone.utc).isoformat().replace("+00:00", "Z")


def _smoke_source(root: Path, source: Any) -> bool:
    if not isinstance(source, str) or not source:
        return False
    try:
        source_path = Path(source)
        if not source_path.is_absolute():
            source_path = root / source_path
        smoke_root = (root / "smoke").resolve(strict=False)
        resolved = source_path.resolve(strict=False)
        resolved.relative_to(smoke_root)
        return True
    except (OSError, RuntimeError, ValueError):
        return False


def _base_row(task_id: str) -> dict[str, Any]:
    return {
        "task_id": task_id,
        "smoke": False,
        "source_commit": None,
        "status": "invalid_state",
        "native_status": None,
        "state_status": None,
        "turns_count": None,
        "retries": None,
        "failed_attempts": None,
        "worker_elapsed_seconds": None,
        "selected_models": [],
        "reported_models": [],
        "model_status": "unverified",
        "model_statuses": [],
        "applied": None,
        "native_verification_passed": None,
        "verification_passed": None,
        "evaluation_status": "unrecorded",
        "recorded_at": None,
        "acceptance_met": None,
        "independent_tests_passed": None,
        "post_apply_tests_passed": None,
        "lead_review_minutes": None,
        "total_minutes": None,
        "codex_usage_before": None,
        "codex_usage_after": None,
        "devin_usage_before": None,
        "devin_usage_after": None,
        "parent_model": None,
        "parent_effort": None,
        "parent_model_evidence": None,
        "observed_total_cost_usd": None,
        "cost_evidence": None,
        "notes": None,
        "outcome": "unknown",
        "attempted": False,
        "assessed": False,
        "first_pass_accepted": False,
        "errors": [],
    }


def _error_row(task_id: str, message: str, *, status: str = "invalid_state") -> dict[str, Any]:
    row = _base_row(task_id)
    row["status"] = status
    row["errors"] = [message]
    row["outcome"] = "failed" if status == "failed" else "unknown"
    return row


def _state_status(
    native_status: str,
    *,
    interrupted: bool,
    prepare_failed: bool,
    native_verification: bool | None,
    turns: list[dict[str, Any]],
) -> str:
    if interrupted or native_status == "interrupted":
        return "interrupted"
    if prepare_failed or native_status in _FAILURE_NATIVE_STATUSES or native_verification is False:
        return "failed"
    # A retry may contain an earlier failed worker attempt.  The native state
    # describes the current/latest attempt, so only that turn determines the
    # current lifecycle status; the full turn history remains available through
    # turns_count/retries and failed_attempts.
    latest = turns[-1] if turns else None
    if latest is not None:
        returncode = latest.get("returncode")
        if (
            isinstance(returncode, int)
            and not isinstance(returncode, bool)
            and returncode != 0
        ) or (isinstance(latest.get("stop"), str) and latest["stop"] != "exit"):
            return "failed"
    if native_status == "prepared":
        return "prepared"
    if native_status in {"applied", "applied_uncommitted"}:
        return "applied"
    if native_status in {"complete", "completed"}:
        return "complete"
    return "incomplete"


def _model_status(statuses: list[str]) -> str:
    if not statuses:
        return "unverified"
    unique = set(statuses)
    if "mismatch" in unique or "session_mismatch" in unique:
        return "mismatch"
    if len(unique) == 1:
        return next(iter(unique))
    return "mixed"


def _fill_from_state(row: dict[str, Any], state_info: dict[str, Any], *, prepare_failed: bool) -> None:
    turns = state_info["turns"]
    native_status = state_info["status"]
    safe_native_status = native_status if native_status in _KNOWN_NATIVE_STATUSES else "unknown"
    row.update(
        {
            "source_commit": state_info["source_commit"],
            "native_status": safe_native_status,
            "state_status": safe_native_status,
            "turns_count": len(turns),
            "retries": max(0, len(turns) - 1),
            "failed_attempts": sum(
                1
                for turn in turns
                if (
                    isinstance(turn.get("returncode"), int)
                    and not isinstance(turn.get("returncode"), bool)
                    and turn["returncode"] != 0
                )
                or (isinstance(turn.get("stop"), str) and turn["stop"] != "exit")
            ),
            "applied": state_info["applied"],
            "native_verification_passed": state_info["native_verification_passed"],
            "verification_passed": state_info["native_verification_passed"],
            "status": _state_status(
                native_status,
                interrupted=state_info["interrupted_attempt"],
                prepare_failed=prepare_failed,
                native_verification=state_info["native_verification_passed"],
                turns=turns,
            ),
            "attempted": (
                bool(turns)
                or state_info["interrupted_attempt"]
                or native_status == "interrupted"
            ),
        }
    )

    selected: set[str] = set()
    reported: set[str] = set()
    statuses: list[str] = []
    elapsed: list[int | float] = []
    all_elapsed = bool(turns)
    for turn in turns:
        selected_model = turn.get("selected_model")
        if isinstance(selected_model, str):
            selected.add(selected_model)
        for model in turn.get("reported_models", []):
            if isinstance(model, str):
                reported.add(model)
        model_check = turn.get("model_check")
        if isinstance(model_check, str):
            statuses.append(model_check)
        if "elapsed_seconds" in turn:
            elapsed.append(turn["elapsed_seconds"])
        elif "worker_elapsed_seconds" in turn:
            elapsed.append(turn["worker_elapsed_seconds"])
        else:
            all_elapsed = False
    if not turns:
        all_elapsed = False
    row["selected_models"] = sorted(selected)
    row["reported_models"] = sorted(reported)
    row["model_statuses"] = sorted(set(statuses))
    row["model_status"] = _model_status(statuses)
    if all_elapsed and all(_finite_nonnegative(value, "turn elapsed") is not None for value in elapsed):
        elapsed_total = sum(elapsed)
        try:
            elapsed_finite = math.isfinite(float(elapsed_total))
        except (OverflowError, ValueError):
            elapsed_finite = False
        if elapsed_finite:
            row["worker_elapsed_seconds"] = elapsed_total


def _apply_evaluation(row: dict[str, Any], evaluation: dict[str, Any] | None, evaluation_status: str) -> None:
    row["evaluation_status"] = evaluation_status
    if evaluation is None:
        return
    for key in _OPTIONAL_EVALUATION_KEYS:
        row[key] = evaluation.get(key)
    row["recorded_at"] = evaluation.get("recorded_at")


def _outcome(row: dict[str, Any]) -> str:
    if row["status"] == "failed":
        return "failed"
    if row["status"] == "invalid_state" or row["evaluation_status"] != "valid":
        return "unknown"
    acceptance = row["acceptance_met"]
    independent = row["independent_tests_passed"]
    post_apply = row["post_apply_tests_passed"]
    if acceptance is False or independent is False or post_apply is False:
        return "failed"
    if row["status"] == "interrupted":
        return "unknown"
    if (
        acceptance is True
        and independent is True
        and row["attempted"]
        and row["native_verification_passed"] is True
    ):
        return "accepted"
    return "unknown"


def _finalise_row(row: dict[str, Any]) -> dict[str, Any]:
    row["assessed"] = (
        row["evaluation_status"] == "valid"
        and row["status"] != "invalid_state"
        and row["acceptance_met"] is not None
        and row["independent_tests_passed"] is not None
    )
    row["outcome"] = _outcome(row)
    row["first_pass_accepted"] = bool(
        row["outcome"] == "accepted"
        and row["turns_count"] == 1
        and row["retries"] == 0
    )
    return row


def _scan_task(
    root: Path,
    task: Path,
    *,
    include_smoke: bool,
    storage_smoke: bool = False,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    task_id = task.name
    if storage_smoke and not include_smoke:
        return None, {"task_id": task_id, "reason": "smoke task path excluded"}
    if not TASK_ID_RE.fullmatch(task_id):
        return _error_row(task_id, "invalid task directory name"), None
    task_info = _lstat(task)
    if task_info is None:
        return _error_row(task_id, "task directory disappeared"), None
    if stat.S_ISLNK(task_info.st_mode) or not stat.S_ISDIR(task_info.st_mode):
        return _error_row(task_id, "task directory is invalid"), None

    state_path = task / "state.json"
    marker = task / "PREPARE_FAILED.txt"
    marker_info = _lstat(marker)
    prepare_failed = marker_info is not None and stat.S_ISREG(marker_info.st_mode)
    marker_error = marker_info is not None and not prepare_failed
    state_info_raw: Any
    if _lstat(state_path) is None:
        if prepare_failed:
            row = _error_row(task_id, "prepare failed placeholder", status="failed")
            if marker_error:
                row["errors"].append("prepare failure marker is invalid")
            return _finalise_row(row), None
        return _error_row(task_id, "state.json is missing"), None
    try:
        state_info_raw = _read_json_file(state_path, "state", max_bytes=MAX_STATE_BYTES)
    except (ValueError, OSError):
        row = _error_row(task_id, "state.json is unreadable or corrupt")
        if prepare_failed:
            row["status"] = "failed"
            row["outcome"] = "failed"
            row["errors"] = ["prepare failed placeholder", "state.json is unreadable or corrupt"]
        return _finalise_row(row), None

    # A source field is safe to inspect only for smoke classification; it is
    # never returned in report rows.
    raw_source = state_info_raw.get("source") if isinstance(state_info_raw, dict) else None
    smoke = storage_smoke or _smoke_source(root, raw_source)
    if smoke and not include_smoke:
        return None, {"task_id": task_id, "reason": "smoke source excluded"}

    try:
        state_info = _validate_state(task_id, state_info_raw)
    except ValueError as exc:
        row = _error_row(task_id, str(exc))
        if marker_error:
            row["errors"].append("prepare failure marker is invalid")
        row["smoke"] = smoke
        return _finalise_row(row), None

    row = _base_row(task_id)
    _fill_from_state(row, state_info, prepare_failed=prepare_failed)
    row["smoke"] = smoke
    if marker_error:
        row["errors"].append("prepare failure marker is invalid")
    if state_info["status"] not in _KNOWN_NATIVE_STATUSES:
        row["errors"].append("state status is unknown")

    evaluation_path = task / "evaluation.json"
    evaluation_info = _lstat(evaluation_path)
    evaluation: dict[str, Any] | None = None
    if evaluation_info is None:
        evaluation_status = "unrecorded"
    elif stat.S_ISLNK(evaluation_info.st_mode):
        evaluation_status = "invalid"
        row["errors"].append("evaluation.json is a symlink")
    elif not stat.S_ISREG(evaluation_info.st_mode):
        evaluation_status = "invalid"
        row["errors"].append("evaluation.json is not a regular file")
    elif stat.S_IMODE(evaluation_info.st_mode) != 0o600:
        evaluation_status = "invalid"
        row["errors"].append("evaluation.json is not private")
    else:
        try:
            stored = _read_json_file(evaluation_path, "evaluation", max_bytes=MAX_EVALUATION_BYTES)
            evaluation = _validate_stored_evaluation(task_id, stored, state_info=state_info)
            evaluation_status = "valid"
        except (ValueError, OSError):
            evaluation_status = "invalid"
            row["errors"].append("evaluation.json is unreadable or invalid")
    _apply_evaluation(row, evaluation, evaluation_status)
    return _finalise_row(row), None


def _metric(values: list[int | float | None]) -> dict[str, int | float | None]:
    observed = [value for value in values if value is not None]
    if not observed:
        return {"observed_count": 0, "missing_count": len(values), "sum": None, "mean": None}
    total = sum(observed)
    try:
        total_finite = math.isfinite(float(total))
    except (OverflowError, ValueError):
        total_finite = False
    if not total_finite:
        return {
            "observed_count": len(observed),
            "missing_count": len(values) - len(observed),
            "sum": None,
            "mean": None,
        }
    return {
        "observed_count": len(observed),
        "missing_count": len(values) - len(observed),
        "sum": total,
        "mean": total / len(observed),
    }


def _build_summary(rows: list[dict[str, Any]], excluded_smoke: int) -> dict[str, Any]:
    included = len(rows)
    attempted = sum(1 for row in rows if row["attempted"])
    assessed = sum(1 for row in rows if row["assessed"])
    accepted = sum(1 for row in rows if row["outcome"] == "accepted")
    first_pass = sum(1 for row in rows if row["first_pass_accepted"])
    unknown = sum(1 for row in rows if row["outcome"] == "unknown")
    failures = sum(1 for row in rows if row["outcome"] == "failed")
    status_counts: dict[str, int] = {}
    for row in rows:
        status = row["status"]
        status_counts[status] = status_counts.get(status, 0) + 1

    # Counts are integers for machine consumers; each rate-like item carries
    # its denominator explicitly so an unknown result cannot silently vanish.
    return {
        "included_tasks": included,
        "excluded_smoke": excluded_smoke,
        "status": status_counts,
        "outcome": {"accepted": accepted, "failed": failures, "unknown": unknown},
        "attempted": attempted,
        "assessed": assessed,
        "accepted": accepted,
        "first_pass_accepted": first_pass,
        "unknown": unknown,
        "failures": failures,
        "failed": failures,
        "denominators": {
            "attempted": included,
            "assessed": included,
            "accepted": attempted,
            "accepted_among_assessed": assessed,
            "first_pass_accepted": attempted,
        },
        "rates": {
            "attempted": {"count": attempted, "denominator": included},
            "assessed": {"count": assessed, "denominator": included},
            "accepted": {"count": accepted, "denominator": attempted},
            "accepted_among_assessed": {"count": accepted, "denominator": assessed},
            "first_pass_accepted": {"count": first_pass, "denominator": attempted},
        },
    }


def record_evaluation(
    root: Path,
    task_id: str,
    payload: dict[str, Any],
    replace: bool = False,
) -> dict[str, Any]:
    """Record one manual evaluation under a task's private state directory.

    ``payload`` accepts the schema fields listed in ``_EVALUATION_INPUT_KEYS``;
    ``schema_version`` and ``task_id`` are optional consistency checks.  The
    returned record and the on-disk file always contain every optional key,
    ``schema_version=1``, the supplied task ID, and a generated ``recorded_at``.
    """

    task_id = _validate_task_id(task_id)
    if not isinstance(replace, bool):
        raise ValueError("replace must be boolean")
    root_path, tasks = _root_and_tasks(root, require_tasks=True)
    task = tasks / task_id
    task_info = _lstat(task)
    if task_info is None:
        raise OSError("task is missing")
    if stat.S_ISLNK(task_info.st_mode) or not stat.S_ISDIR(task_info.st_mode):
        raise ValueError("task directory is invalid")

    with _exclusive_task_lock(root_path, task_id) as locked_task:
        state_path = locked_task / "state.json"
        state = _read_json_file(state_path, "state", max_bytes=MAX_STATE_BYTES)
        state_info = _validate_state(task_id, state)
        record = _normalise_evaluation(task_id, payload, state_info=state_info)
        evaluation_path = locked_task / "evaluation.json"
        evaluation_info = _lstat(evaluation_path)
        if evaluation_info is not None:
            if stat.S_ISLNK(evaluation_info.st_mode):
                raise ValueError("evaluation.json is a symlink")
            if not replace:
                raise ValueError("evaluation already exists; pass replace=True to replace it")
            previous_path = locked_task / "evaluation.json.previous"
            previous_info = _lstat(previous_path)
            if previous_info is not None and stat.S_ISLNK(previous_info.st_mode):
                raise ValueError("previous evaluation is a symlink")
            old_bytes = _open_read_nofollow(
                evaluation_path,
                "existing evaluation",
                max_bytes=MAX_EVALUATION_BYTES,
            )
            _atomic_write(previous_path, old_bytes)
        _atomic_write(evaluation_path, _json_bytes(record))
        return record


def build_evaluation_report(root: Path, include_smoke: bool = False) -> dict[str, Any]:
    """Scan every task and return sanitized local evaluation metrics.

    Native state evidence is kept separate from manual evaluation fields.  A
    missing or invalid manual record becomes an unknown row, while explicit
    failed states and failed manual assertions remain failures.
    """

    if not isinstance(include_smoke, bool):
        raise ValueError("include_smoke must be boolean")
    root_path, tasks = _root_and_tasks(root, require_tasks=False)
    rows: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    excluded_tasks: list[str] = []
    try:
        entries: list[tuple[Path, bool]] = []
        if _lstat(tasks) is not None:
            entries.extend(
                (task, False) for task in sorted(tasks.iterdir(), key=lambda path: path.name)
            )
        # Older local revisions could place disposable smoke tasks below
        # root/smoke/tasks.  Include those when they contain task markers,
        # while ignoring the ordinary smoke fixture repository itself.
        smoke_root = root_path / "smoke"
        legacy_tasks = smoke_root / "tasks"
        legacy_info = _lstat(legacy_tasks)
        if legacy_info is not None and stat.S_ISDIR(legacy_info.st_mode) and not stat.S_ISLNK(legacy_info.st_mode):
            entries.extend(
                (task, True)
                for task in sorted(legacy_tasks.iterdir(), key=lambda path: path.name)
            )
        legacy_smoke_info = _lstat(smoke_root)
        if legacy_smoke_info is not None and stat.S_ISDIR(legacy_smoke_info.st_mode) and not stat.S_ISLNK(legacy_smoke_info.st_mode):
            for legacy_task in sorted(smoke_root.iterdir(), key=lambda path: path.name):
                if legacy_task == legacy_tasks:
                    continue
                legacy_task_info = _lstat(legacy_task)
                if legacy_task_info is None or stat.S_ISLNK(legacy_task_info.st_mode) or not stat.S_ISDIR(legacy_task_info.st_mode):
                    continue
                if _lstat(legacy_task / "state.json") is not None or _lstat(legacy_task / "PREPARE_FAILED.txt") is not None:
                    entries.append((legacy_task, True))
    except OSError as exc:
        raise OSError("could not scan tasks directory") from exc
    for task, storage_smoke in entries:
        if storage_smoke and not include_smoke:
            excluded_tasks.append(task.name)
            continue
        try:
            with _shared_existing_task_lock(task) as _locked:
                row, excluded = _scan_task(
                    root_path,
                    task,
                    include_smoke=include_smoke,
                    storage_smoke=storage_smoke,
                )
        except _TaskLockedError:
            row = _error_row(task.name, "task is currently running", status="in_progress")
            excluded = None
        except (OSError, ValueError):
            task_id = task.name
            row = _error_row(task_id, "task could not be read")
            excluded = None
        if excluded is not None:
            excluded_tasks.append(excluded["task_id"])
            continue
        if row is None:
            continue
        rows.append(row)
        if row["errors"]:
            errors.append({"task_id": row["task_id"], "errors": list(row["errors"])})

    invalid_state_entries = [row["task_id"] for row in rows if row["status"] == "invalid_state"]
    summary = _build_summary(rows, len(excluded_tasks))
    metrics = {
        "turns_count": _metric([row["turns_count"] for row in rows]),
        "retries": _metric([row["retries"] for row in rows]),
        "worker_elapsed_seconds": _metric([row["worker_elapsed_seconds"] for row in rows]),
        "lead_review_minutes": _metric([row["lead_review_minutes"] for row in rows]),
        "total_minutes": _metric([row["total_minutes"] for row in rows]),
        # Costs are intentionally sourced only from manually recorded,
        # evidenced observed_total_cost_usd values.
        "observed_total_cost_usd": _metric([row["observed_total_cost_usd"] for row in rows]),
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _utc_now(),
        "include_smoke": include_smoke,
        "rows": rows,
        "tasks": rows,
        "task_ids": [row["task_id"] for row in rows],
        "errors": errors,
        "invalid_state_entries": invalid_state_entries,
        "excluded_smoke_tasks": excluded_tasks,
        "excluded_smoke_count": len(excluded_tasks),
        "status_counts": summary["status"],
        "summary": summary,
        "counts": summary,
        "metrics": metrics,
        "caveat": (
            "This is a local operational record, not a direct same-task benchmark against external vendor figures. "
            "The current lead may be a Codex host or a Devin/Fable host; this report confirms only explicitly observed host, model, and effort metadata."
        ),
    }


__all__ = ["SCHEMA_VERSION", "record_evaluation", "build_evaluation_report"]
