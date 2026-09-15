#!/usr/bin/env python3
"""Private, opt-in measurement of counters in the invoking Codex rollout.

The module deliberately understands only the metadata and usage records needed
for a measurement.  It never copies a rollout path, response id, prompt,
message, tool call or response into Sidekick state.

Case identifiers use ``^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$``.  They are bounded
plain identifiers, rather than paths or free-form labels.  Trial ids are
generated as ``m-<UTC timestamp>-<uuid hex>`` and are accepted only when they
match ``^[A-Za-z0-9][A-Za-z0-9._-]{7,127}$``.
"""
from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
import re
import stat
import tempfile
import uuid


SCHEMA_VERSION = 1
TRIALS_DIRNAME = "measurements"
CASE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
TRIAL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{7,127}$")
IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
COUNTERS = (
    "input_tokens",
    "cached_input_tokens",
    "cache_write_input_tokens",
    "output_tokens",
    "reasoning_output_tokens",
    "total_tokens",
)
MAX_ROLLOUT_BYTES = 128 * 1024 * 1024
MAX_ROLLOUT_LINE = 4 * 1024 * 1024
MAX_ROLLOUT_LINES = 2_000_000
MAX_ROLLOUT_FILES = 20_000
MAX_TRIAL_BYTES = 4 * 1024 * 1024
MAX_REPORT_TRIALS = 10_000
MAX_COUNTER = 10**18

TOKEN_TYPES = {"token_usage_record", "token_usage"}
CONTEXT_TYPES = {"turn_context", "turn_context_record"}
META_TYPES = {"session_meta", "session_metadata"}

CAVEAT = (
    "Observed Codex parent token counts do not establish subscription quota, "
    "weekly-limit consumption, price/cost, or Devin/Fable worker tokens."
)
COVERAGE_NOTE = "Content after the stop snapshot is not covered by this trial."


class MeasurementError(Exception):
    """A fail-closed measurement error safe to show to a caller."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise MeasurementError(message)


def _reject_duplicate_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _safe_identifier(value, *, name: str) -> str:
    _require(isinstance(value, str) and IDENTIFIER_RE.fullmatch(value) is not None,
             f"Invalid {name}")
    return value


def validate_case(value: str) -> str:
    """Validate and return a bounded plain trial case identifier."""
    _require(isinstance(value, str) and CASE_RE.fullmatch(value) is not None,
             "Case must match ^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
    return value


def validate_arm(value: str) -> str:
    _require(value in {"lead-only", "sidekick"}, "Arm must be lead-only or sidekick")
    return value


def validate_trial_id(value: str) -> str:
    _require(isinstance(value, str) and TRIAL_RE.fullmatch(value) is not None,
             "Invalid trial id")
    return value


def _json_bytes(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")


def _ensure_private_dir(path: Path) -> Path:
    """Create a private directory while rejecting symlink components."""
    path = Path(path).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    # Check existing ancestors without resolving away a symlink supplied by a
    # caller.  A missing chain is created one component at a time.
    parts = path.parts
    current = Path(parts[0])
    for part in parts[1:]:
        current = current / part
        created = False
        try:
            info = current.lstat()
        except FileNotFoundError:
            current.mkdir(mode=0o700)
            info = current.lstat()
            created = True
        except OSError as exc:
            raise MeasurementError("Could not inspect measurement state") from exc
        # Platform-managed ancestors such as macOS ``/var`` may themselves
        # be symlinks.  The selected state directory and its own trial
        # directory must be real private directories; an ancestor outside the
        # selected path is allowed to resolve normally.
        if stat.S_ISLNK(info.st_mode):
            if current == path:
                raise MeasurementError("Measurement state must contain private directories")
            continue
        if not stat.S_ISDIR(info.st_mode):
            raise MeasurementError("Measurement state must contain private directories")
        if created or current == path:
            try:
                os.chmod(current, 0o700)
            except OSError as exc:
                raise MeasurementError("Could not protect measurement state") from exc
    return path


def _state_trials(state_dir: Path, *, create: bool) -> Path:
    root = Path(state_dir).expanduser()
    if not root.is_absolute():
        root = Path.cwd() / root
    if create:
        _ensure_private_dir(root)
        return _ensure_private_dir(root / TRIALS_DIRNAME)
    try:
        root_info = root.lstat()
    except FileNotFoundError:
        return root / TRIALS_DIRNAME
    except OSError as exc:
        raise MeasurementError("Could not inspect measurement state") from exc
    _require(stat.S_ISDIR(root_info.st_mode) and not stat.S_ISLNK(root_info.st_mode),
             "Measurement state must be a private directory")
    _require(stat.S_IMODE(root_info.st_mode) == 0o700,
             "Measurement state permissions are unsafe")
    trials = root / TRIALS_DIRNAME
    try:
        info = trials.lstat()
    except FileNotFoundError:
        return trials
    _require(stat.S_ISDIR(info.st_mode) and not stat.S_ISLNK(info.st_mode),
             "Measurement state must be a private directory")
    _require(stat.S_IMODE(info.st_mode) == 0o700, "Measurement state permissions are unsafe")
    return trials


def _atomic_create(path: Path, value) -> None:
    """Atomically create a new 0600 JSON file without replacing an old trial."""
    data = _json_bytes(value)
    try:
        info = path.lstat()
    except FileNotFoundError:
        info = None
    except OSError as exc:
        raise MeasurementError("Could not inspect trial state") from exc
    _require(info is None, "Trial already exists")
    temporary = None
    fd = None
    try:
        fd, temporary = tempfile.mkstemp(prefix=".measurement-", dir=str(path.parent))
        with os.fdopen(fd, "wb") as handle:
            fd = None
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        # A hard link makes publication atomic and fails if another writer won
        # the name race.  The temporary file is then removed.
        os.link(temporary, path)
        try:
            dir_fd = os.open(path.parent, os.O_RDONLY)
        except OSError:
            dir_fd = None
        if dir_fd is not None:
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
    except FileExistsError as exc:
        raise MeasurementError("Trial already exists") from exc
    except OSError as exc:
        raise MeasurementError("Could not save trial state") from exc
    finally:
        if fd is not None:
            os.close(fd)
        if temporary is not None:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass


def _atomic_update(path: Path, value) -> None:
    """Atomically replace an existing owned regular trial file."""
    try:
        info = path.lstat()
    except FileNotFoundError as exc:
        raise MeasurementError("Trial does not exist") from exc
    _require(stat.S_ISREG(info.st_mode) and not stat.S_ISLNK(info.st_mode),
             "Trial is not a regular file")
    _require(stat.S_IMODE(info.st_mode) == 0o600, "Trial permissions are unsafe")
    temporary = None
    fd = None
    try:
        fd, temporary = tempfile.mkstemp(prefix=".measurement-", dir=str(path.parent))
        with os.fdopen(fd, "wb") as handle:
            fd = None
            handle.write(_json_bytes(value))
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
        temporary = None
    except OSError as exc:
        raise MeasurementError("Could not update trial state") from exc
    finally:
        if fd is not None:
            os.close(fd)
        if temporary is not None:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass


def _read_json(path: Path):
    try:
        info = path.lstat()
    except FileNotFoundError as exc:
        raise MeasurementError("Trial does not exist") from exc
    except OSError as exc:
        raise MeasurementError("Could not inspect trial state") from exc
    _require(stat.S_ISREG(info.st_mode) and not stat.S_ISLNK(info.st_mode),
             "Trial is not a regular file")
    _require(stat.S_IMODE(info.st_mode) == 0o600, "Trial permissions are unsafe")
    _require(info.st_size <= MAX_TRIAL_BYTES, "Trial state is too large")
    try:
        raw = path.read_text(encoding="utf-8")
        value = json.loads(raw, object_pairs_hook=_reject_duplicate_pairs)
    except (OSError, UnicodeError, ValueError) as exc:
        raise MeasurementError("Invalid trial state") from exc
    _require(isinstance(value, dict), "Invalid trial state")
    return value


def _home_from_environment(environ=None) -> Path:
    env = os.environ if environ is None else environ
    value = env.get("HOME")
    if not isinstance(value, str) or not value or "\x00" in value:
        raise MeasurementError("HOME is unavailable")
    home = Path(value).expanduser()
    try:
        info = home.lstat()
    except (FileNotFoundError, OSError) as exc:
        raise MeasurementError("HOME is unavailable") from exc
    _require(stat.S_ISDIR(info.st_mode) and not stat.S_ISLNK(info.st_mode),
             "HOME is unavailable")
    return home


def _scan_rollout_files(home: Path):
    roots = []
    codex = home / ".codex"
    try:
        codex_info = codex.lstat()
    except FileNotFoundError:
        codex_info = None
    except OSError as exc:
        raise MeasurementError("Could not inspect Codex rollout roots") from exc
    if codex_info is not None:
        _require(stat.S_ISDIR(codex_info.st_mode) and not stat.S_ISLNK(codex_info.st_mode),
                 "Codex rollout root is not a regular directory")
    for name in ("sessions", "archived_sessions"):
        root = codex / name
        try:
            info = root.lstat()
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise MeasurementError("Could not inspect Codex rollout roots") from exc
        _require(stat.S_ISDIR(info.st_mode) and not stat.S_ISLNK(info.st_mode),
                 "Codex rollout root is not a regular directory")
        roots.append(root)
    _require(roots, "No Codex rollout root is available")

    found = []
    visited = [(root, 0) for root in roots]
    while visited:
        directory, depth = visited.pop()
        _require(depth <= 32, "Codex rollout tree is too deep")
        try:
            entries = list(os.scandir(directory))
        except OSError as exc:
            raise MeasurementError("Could not inspect Codex rollout roots") from exc
        for entry in entries:
            try:
                info = entry.stat(follow_symlinks=False)
            except OSError as exc:
                raise MeasurementError("Could not inspect Codex rollout roots") from exc
            if stat.S_ISLNK(info.st_mode):
                raise MeasurementError("Symlinks are not accepted in Codex rollout roots")
            entry_path = Path(entry.path)
            if stat.S_ISDIR(info.st_mode):
                visited.append((entry_path, depth + 1))
            elif stat.S_ISREG(info.st_mode) and entry_path.suffix == ".jsonl":
                found.append(entry_path)
                _require(len(found) <= MAX_ROLLOUT_FILES, "Too many Codex rollout files")
    return found


def _record_type(record):
    value = record.get("type")
    if not isinstance(value, str):
        value = record.get("kind")
    if not isinstance(value, str):
        value = record.get("event")
    return value


def _payload(record):
    payload = record.get("payload")
    return payload if isinstance(payload, dict) else record


def _string(value, max_len=256):
    return isinstance(value, str) and bool(value) and "\x00" not in value and len(value) <= max_len


def _counter_map(value, name: str):
    if not isinstance(value, dict):
        raise ValueError(f"missing {name}")
    result = {}
    for key in COUNTERS:
        item = value.get(key)
        if not _is_int(item) or item < 0 or item > MAX_COUNTER:
            raise ValueError(f"invalid {name}")
        result[key] = item
    if result["total_tokens"] != result["input_tokens"] + result["output_tokens"]:
        raise ValueError(f"inconsistent {name}")
    if result["cached_input_tokens"] > result["input_tokens"]:
        raise ValueError(f"inconsistent {name}")
    if result["cache_write_input_tokens"] > result["input_tokens"]:
        raise ValueError(f"inconsistent {name}")
    if result["reasoning_output_tokens"] > result["output_tokens"]:
        raise ValueError(f"inconsistent {name}")
    return result


def _identity(record, payload, record_type):
    session = payload.get("session_id", record.get("session_id"))
    thread = payload.get("thread_id", record.get("thread_id"))
    if record_type in META_TYPES:
        if thread is None:
            thread = payload.get("id")
    return session, thread


def _parse_rollout(path: Path, wanted_session: str, wanted_thread: str):
    """Parse a candidate into sanitized evidence only.

    The parser intentionally holds only scalar metadata and counter maps.  It
    never returns the original path or any unrecognised JSON value.
    """
    try:
        info = path.lstat()
    except OSError as exc:
        raise MeasurementError("Could not inspect Codex rollout") from exc
    _require(stat.S_ISREG(info.st_mode) and not stat.S_ISLNK(info.st_mode),
             "Codex rollout is not a regular file")
    _require(info.st_size <= MAX_ROLLOUT_BYTES, "Codex rollout is too large")

    records = []
    contexts = []
    session_values = set()
    thread_values = set()
    exact_identity = False
    bad_json = False
    errors = []
    previous_ordinal = None
    line_number = 0
    metadata_count = 0
    try:
        handle = path.open("rb")
    except OSError as exc:
        raise MeasurementError("Could not read Codex rollout") from exc
    with handle:
        for raw_line in handle:
            line_number += 1
            _require(line_number <= MAX_ROLLOUT_LINES, "Codex rollout has too many records")
            if len(raw_line) > MAX_ROLLOUT_LINE:
                bad_json = True
                continue
            try:
                line = raw_line.decode("utf-8")
                record = json.loads(line, object_pairs_hook=_reject_duplicate_pairs)
            except (UnicodeError, ValueError, json.JSONDecodeError):
                bad_json = True
                continue
            if not isinstance(record, dict):
                continue
            record_type = _record_type(record)
            if record_type not in TOKEN_TYPES | CONTEXT_TYPES | META_TYPES:
                continue
            payload = _payload(record)
            if not isinstance(payload, dict):
                errors.append("malformed relevant record")
                continue
            ordinal = record.get("ordinal")
            timestamp = record.get("timestamp")
            if not _is_int(ordinal) or ordinal < 0 or not _string(timestamp):
                errors.append("malformed relevant record")
                continue
            if previous_ordinal is not None and ordinal <= previous_ordinal:
                errors.append("duplicate or nonmonotonic ordinal")
            previous_ordinal = ordinal
            session, thread = _identity(record, payload, record_type)
            if session is not None:
                if not _string(session, 128):
                    errors.append("malformed identity")
                else:
                    session_values.add(session)
            if thread is not None:
                if not _string(thread, 128):
                    errors.append("malformed identity")
                else:
                    thread_values.add(thread)
            if session == wanted_session and thread == wanted_thread:
                exact_identity = True
            elif (session == wanted_session) != (thread == wanted_thread):
                errors.append("changed session identity")

            if record_type in META_TYPES:
                metadata_count += 1
                if metadata_count > 1:
                    errors.append("duplicate session metadata")
                # Metadata is useful for binding, but a missing thread is
                # tolerated because older records expose it as ``id``.
                if session is None or thread is None:
                    errors.append("malformed session metadata")
                continue

            if record_type in CONTEXT_TYPES:
                turn_id = payload.get("turn_id")
                root_turn_id = payload.get("root_turn_id", turn_id)
                model = payload.get("model")
                effort = payload.get("effort", payload.get("reasoning_effort"))
                if not (_string(turn_id, 128) and _string(root_turn_id, 128)
                        and _string(model, 256) and _string(effort, 64)):
                    errors.append("malformed turn context")
                    continue
                contexts.append({
                    "ordinal": ordinal,
                    "timestamp": timestamp,
                    "turn_id": turn_id,
                    "root_turn_id": root_turn_id,
                    "model": model,
                    "effort": effort,
                })
                continue

            # Token usage records are the only records retained in a trial.
            session = payload.get("session_id", record.get("session_id"))
            thread = payload.get("thread_id", record.get("thread_id"))
            turn_id = payload.get("turn_id")
            root_turn_id = payload.get("root_turn_id", turn_id)
            model = payload.get("model")
            effort = payload.get("effort", payload.get("reasoning_effort"))
            try:
                usage = _counter_map(payload.get("usage"), "usage")
                thread_usage = _counter_map(payload.get("thread_token_usage"), "thread usage")
                turn_usage = _counter_map(payload.get("turn_token_usage"), "turn usage")
            except ValueError:
                errors.append("malformed token usage")
                continue
            if not (_string(session, 128) and _string(thread, 128)
                    and _string(turn_id, 128) and _string(root_turn_id, 128)):
                errors.append("malformed token identity")
                continue
            if model is not None and not _string(model, 256):
                errors.append("malformed model")
                model = None
            if effort is not None and not _string(effort, 64):
                errors.append("malformed effort")
                effort = None
            # Re-evaluate exact identity with the token's authoritative fields.
            if session == wanted_session and thread == wanted_thread:
                exact_identity = True
            elif (session == wanted_session) != (thread == wanted_thread):
                errors.append("changed session identity")
            records.append({
                "ordinal": ordinal,
                "timestamp": timestamp,
                "session_id": session,
                "thread_id": thread,
                "turn_id": turn_id,
                "root_turn_id": root_turn_id,
                "model": model,
                "effort": effort,
                "usage": usage,
                "thread_token_usage": thread_usage,
                "turn_token_usage": turn_usage,
            })
    return {
        "records": records,
        "contexts": contexts,
        "session_values": session_values,
        "thread_values": thread_values,
        "exact_identity": exact_identity,
        "bad_json": bad_json,
        "errors": errors,
    }


def _find_rollout(session_id: str, thread_id: str, *, environ=None):
    home = _home_from_environment(environ)
    candidates = []
    paths = _scan_rollout_files(home)
    # Official rollout filenames carry the session/thread identifier.  Use
    # that hint first so a normal home with a large archive remains quick,
    # while falling back to every file when a synthetic fixture uses a plain
    # filename or when the hint produced no match.
    hinted = [path for path in paths if session_id in path.name or thread_id in path.name]
    parse_paths = hinted or paths
    for path in parse_paths:
        evidence = _parse_rollout(path, session_id, thread_id)
        if evidence["exact_identity"]:
            candidates.append(evidence)
    if not candidates and hinted and len(hinted) < len(paths):
        for path in paths:
            if path in hinted:
                continue
            evidence = _parse_rollout(path, session_id, thread_id)
            if evidence["exact_identity"]:
                candidates.append(evidence)
    _require(len(candidates) == 1, "Codex rollout identity is missing or ambiguous")
    evidence = candidates[0]
    if any(record["session_id"] != session_id or record["thread_id"] != thread_id
           for record in evidence["records"]):
        evidence["errors"].append("changed session identity")
    _require(not evidence["bad_json"] and not evidence["errors"],
             "Codex rollout has malformed or inconsistent relevant evidence")
    _require(evidence["records"], "Codex rollout has no token usage evidence")
    return evidence


def _validate_sequence(records):
    previous_thread = None
    previous_turn = {}
    seen_root_for_turn = {}
    for record in records:
        thread_usage = record["thread_token_usage"]
        if previous_thread is not None:
            for key in COUNTERS:
                if thread_usage[key] < previous_thread[key]:
                    raise MeasurementError("Codex counters are nonmonotonic")
        previous_thread = thread_usage
        turn_id = record["turn_id"]
        if turn_id in previous_turn:
            for key in COUNTERS:
                if record["turn_token_usage"][key] < previous_turn[turn_id][key]:
                    raise MeasurementError("Codex turn counters are nonmonotonic")
        previous_turn[turn_id] = record["turn_token_usage"]
        root = record["root_turn_id"]
        old_root = seen_root_for_turn.get(turn_id)
        if old_root is not None and old_root != root:
            raise MeasurementError("Codex turn identity is inconsistent")
        seen_root_for_turn[turn_id] = root


def _contexts_for(evidence):
    contexts = sorted(evidence["contexts"], key=lambda item: item["ordinal"])
    records = evidence["records"]
    for record in records:
        matches = [item for item in contexts
                   if item["ordinal"] <= record["ordinal"] and item["turn_id"] == record["turn_id"]]
        if matches:
            context = matches[-1]
            if record["model"] is None:
                record["model"] = context["model"]
            if record["effort"] is None:
                record["effort"] = context["effort"]
            if record["root_turn_id"] != context["root_turn_id"]:
                raise MeasurementError("Codex turn context is inconsistent")
    return contexts


def _latest_model_effort(records):
    latest = records[-1]
    _require(_string(latest.get("model"), 256) and _string(latest.get("effort"), 64),
             "Codex model/effort metadata is unavailable")
    return latest["model"], latest["effort"]


def _required_identity(environ=None):
    env = os.environ if environ is None else environ
    session = env.get("CODEX_SESSION_ID")
    thread = env.get("CODEX_THREAD_ID")
    _safe_identifier(session, name="CODEX_SESSION_ID")
    _safe_identifier(thread, name="CODEX_THREAD_ID")
    return session, thread


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def _new_trial_id() -> str:
    value = "m-" + dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + "-" + uuid.uuid4().hex
    validate_trial_id(value)
    return value


def _trial_summary(trial):
    result = {
        "trial_id": trial["trial_id"],
        "case": trial["case"],
        "arm": trial["arm"],
        "status": trial["status"],
        "consistent": trial.get("consistent"),
        "eligible": trial.get("eligible"),
        "model": trial.get("model"),
        "effort": trial.get("effort"),
    }
    if trial.get("status") == "completed":
        result["deltas"] = trial["stop"]["deltas"]
        result["coverage_note"] = COVERAGE_NOTE
        if trial.get("ineligible_reasons"):
            result["ineligible_reasons"] = list(trial["ineligible_reasons"])
    return result


def measure_start(state_dir: Path, case: str, arm: str, *, environ=None) -> dict:
    """Start a trial and capture a content-free cumulative baseline."""
    case = validate_case(case)
    arm = validate_arm(arm)
    session_id, thread_id = _required_identity(environ)
    evidence = _find_rollout(session_id, thread_id, environ=environ)
    _validate_sequence(evidence["records"])
    contexts = _contexts_for(evidence)
    latest = evidence["records"][-1]
    model, effort = _latest_model_effort(evidence["records"])
    start_context = contexts[-1] if contexts else None
    if start_context is not None and start_context["ordinal"] >= latest["ordinal"]:
        # A context can be appended before the first usage record of the
        # current root turn.  Its model/effort is still the confirmed setting
        # for the trial even though the latest counters belong to the prior
        # turn and therefore must not be root-turn subtracted.
        model, effort = start_context["model"], start_context["effort"]
    root_turn_id = (start_context["root_turn_id"] if start_context is not None
                    else latest["root_turn_id"])
    includes_current_root_turn = latest["root_turn_id"] == root_turn_id
    baseline = dict(latest["thread_token_usage"])
    if includes_current_root_turn:
        for key in COUNTERS:
            _require(latest["thread_token_usage"][key] >= latest["turn_token_usage"][key],
                     "Codex counters are inconsistent")
            baseline[key] = latest["thread_token_usage"][key] - latest["turn_token_usage"][key]

    trial_id = _new_trial_id()
    trial = {
        "schema_version": SCHEMA_VERSION,
        "trial_id": trial_id,
        "case": case,
        "arm": arm,
        "status": "in_progress",
        "consistent": True,
        "eligible": False,
        "created_at": _now(),
        "session_id": session_id,
        "thread_id": thread_id,
        "root_turn_id": root_turn_id,
        "model": model,
        "effort": effort,
        "baseline": {
            "counters": baseline,
            "thread_counters": dict(latest["thread_token_usage"]),
            "turn_counters": dict(latest["turn_token_usage"]),
            "ordinal": latest["ordinal"],
            "timestamp": latest["timestamp"],
            "root_turn_id": root_turn_id,
            "includes_current_root_turn": includes_current_root_turn,
        },
    }
    trials_dir = _state_trials(state_dir, create=True)
    _atomic_create(trials_dir / (trial_id + ".json"), trial)
    return _trial_summary(trial)


def _validate_stored_trial(trial, trial_id: str):
    _require(trial.get("schema_version") == SCHEMA_VERSION and trial.get("trial_id") == trial_id,
             "Invalid trial state")
    validate_case(trial.get("case"))
    validate_arm(trial.get("arm"))
    _safe_identifier(trial.get("session_id"), name="trial session")
    _safe_identifier(trial.get("thread_id"), name="trial thread")
    _safe_identifier(trial.get("root_turn_id"), name="trial root turn")
    _require(_string(trial.get("model"), 256) and _string(trial.get("effort"), 64),
             "Invalid trial model/effort")
    baseline = trial.get("baseline")
    _require(isinstance(baseline, dict), "Invalid trial baseline")
    for name in ("counters", "thread_counters", "turn_counters"):
        try:
            _counter_map(baseline.get(name), "trial baseline")
        except ValueError as exc:
            raise MeasurementError("Invalid trial baseline") from exc
    _require(_is_int(baseline.get("ordinal")) and baseline["ordinal"] >= 0,
             "Invalid trial baseline")


def measure_stop(state_dir: Path, trial_id: str, *, environ=None) -> dict:
    """Capture the latest cumulative counters and atomically complete a trial."""
    trial_id = validate_trial_id(trial_id)
    trials_dir = _state_trials(state_dir, create=False)
    path = trials_dir / (trial_id + ".json")
    trial = _read_json(path)
    _validate_stored_trial(trial, trial_id)
    _require(trial.get("status") == "in_progress", "Trial is already stopped")
    session_id, thread_id = _required_identity(environ)
    _require(session_id == trial["session_id"] and thread_id == trial["thread_id"],
             "Codex session changed since measurement start")
    evidence = _find_rollout(session_id, thread_id, environ=environ)
    _validate_sequence(evidence["records"])
    contexts = _contexts_for(evidence)
    latest = evidence["records"][-1]
    baseline = trial["baseline"]["counters"]
    _require(latest["ordinal"] >= trial["baseline"]["ordinal"],
             "Codex rollout moved before measurement start")
    deltas = {}
    for key in COUNTERS:
        value = latest["thread_token_usage"][key] - baseline[key]
        _require(value >= 0, "Codex counters moved backwards")
        deltas[key] = value

    ineligible_reasons = []
    start_model = trial["model"]
    start_effort = trial["effort"]
    observed = {(start_model, start_effort)}
    for record in evidence["records"]:
        if record["ordinal"] >= trial["baseline"]["ordinal"]:
            if record.get("model") is not None or record.get("effort") is not None:
                observed.add((record.get("model"), record.get("effort")))
    for context in contexts:
        if context["ordinal"] > trial["baseline"]["ordinal"]:
            observed.add((context["model"], context["effort"]))
    if any(model != start_model for model, _ in observed):
        ineligible_reasons.append("model changed during trial")
    if any(effort != start_effort for _, effort in observed):
        ineligible_reasons.append("effort changed during trial")
    try:
        latest_model, latest_effort = _latest_model_effort(evidence["records"])
    except MeasurementError:
        latest_model, latest_effort = None, None
        ineligible_reasons.append("model/effort metadata unavailable at stop")
    if latest_model is not None and latest_model != start_model and "model changed during trial" not in ineligible_reasons:
        ineligible_reasons.append("model changed during trial")
    if latest_effort is not None and latest_effort != start_effort and "effort changed during trial" not in ineligible_reasons:
        ineligible_reasons.append("effort changed during trial")
    trial["status"] = "completed"
    trial["consistent"] = not ineligible_reasons
    trial["eligible"] = not ineligible_reasons
    trial["ineligible_reasons"] = ineligible_reasons
    trial["stop"] = {
        "counters": dict(latest["thread_token_usage"]),
        "deltas": deltas,
        "ordinal": latest["ordinal"],
        "timestamp": latest["timestamp"],
        "coverage_note": COVERAGE_NOTE,
    }
    _atomic_update(path, trial)
    return _trial_summary(trial)


def _sanitized_trial(trial, *, fallback_id=None):
    """Return report-safe evidence, rejecting malformed private state."""
    trial_id = trial.get("trial_id", fallback_id)
    validate_trial_id(trial_id)
    _validate_stored_trial(trial, trial_id)
    result = {
        "trial_id": trial_id,
        "case": trial["case"],
        "arm": trial["arm"],
        "status": trial.get("status"),
        "model": trial["model"],
        "effort": trial["effort"],
    }
    if trial.get("status") == "in_progress":
        result.update({"consistent": None, "eligible": False})
    elif trial.get("status") == "completed":
        stop = trial.get("stop")
        _require(isinstance(stop, dict), "Invalid completed trial")
        try:
            _counter_map(stop.get("counters"), "trial stop counters")
            deltas = _counter_map(stop.get("deltas"), "trial deltas")
        except ValueError as exc:
            raise MeasurementError("Invalid completed trial") from exc
        _require(_is_int(stop.get("ordinal")) and stop["ordinal"] >= 0
                 and _string(stop.get("timestamp")), "Invalid completed trial")
        _require(isinstance(trial.get("consistent"), bool)
                 and isinstance(trial.get("eligible"), bool), "Invalid completed trial")
        eligible = trial["status"] == "completed" and trial["consistent"] and trial["eligible"]
        reasons = trial.get("ineligible_reasons") or []
        _require(isinstance(reasons, list) and all(
            reason in {"model changed during trial", "effort changed during trial",
                       "model/effort metadata unavailable at stop"}
            for reason in reasons
        ), "Invalid completed trial")
        result.update({
            "consistent": trial["consistent"],
            "eligible": eligible,
            "deltas": deltas,
            "ineligible_reasons": list(reasons),
        })
    else:
        raise MeasurementError("Invalid trial status")
    return result


def measurement_report(state_dir: Path, case: str | None = None) -> dict:
    """Return sanitized trial evidence and strictly paired comparisons."""
    if case is not None:
        case = validate_case(case)
    trials_dir = _state_trials(state_dir, create=False)
    trials = []
    issues = []
    try:
        entries = list(trials_dir.iterdir()) if trials_dir.is_dir() and not trials_dir.is_symlink() else []
    except OSError as exc:
        raise MeasurementError("Could not inspect measurement state") from exc
    _require(len(entries) <= MAX_REPORT_TRIALS, "Too many measurement trials")
    for entry in sorted(entries, key=lambda p: p.name):
        if entry.name.startswith("."):
            continue
        stem = entry.stem if entry.suffix == ".json" else entry.name
        if entry.suffix != ".json" or TRIAL_RE.fullmatch(stem) is None:
            issues.append({"reason": "invalid trial filename"})
            continue
        try:
            value = _read_json(entry)
            sanitized = _sanitized_trial(value, fallback_id=stem)
        except MeasurementError:
            trials.append({"trial_id": stem, "status": "invalid", "eligible": False,
                           "reason": "invalid trial evidence"})
            continue
        if case is None or sanitized["case"] == case:
            trials.append(sanitized)

    grouped = {}
    for trial in trials:
        if trial.get("status") == "completed" and trial.get("consistent") and trial.get("eligible"):
            grouped.setdefault(trial["case"], {"lead-only": [], "sidekick": []})[trial["arm"]].append(trial)
    groups = []
    for group_case in sorted(grouped):
        arms = grouped[group_case]
        if len(arms["lead-only"]) == 1 and len(arms["sidekick"]) == 1:
            lead = arms["lead-only"][0]
            side = arms["sidekick"][0]
            if (lead["model"], lead["effort"]) != (side["model"], side["effort"]):
                issues.append({
                    "case": group_case,
                    "reason": "paired trials have mismatched model or effort; comparison excluded",
                })
                continue
            counters = {}
            for key in COUNTERS:
                lead_value = lead["deltas"][key]
                side_value = side["deltas"][key]
                saved = lead_value - side_value
                counters[key] = {
                    "lead_only": lead_value,
                    "sidekick": side_value,
                    "saved": saved,
                    "reduction_percent": None if lead_value == 0 else saved / lead_value * 100,
                }
            groups.append({
                "case": group_case,
                "trial_ids": {"lead-only": lead["trial_id"], "sidekick": side["trial_id"]},
                "counters": counters,
            })
        else:
            arms_seen = {arm: len(items) for arm, items in arms.items() if items}
            issues.append({"case": group_case,
                           "reason": "pair requires exactly one completed consistent lead-only and sidekick trial",
                           "arms": arms_seen})

    # Incomplete, invalid and inconsistent trials are evidence in ``trials``;
    # this compact issue list explains why no reduction was invented for them.
    for trial in trials:
        if trial.get("status") == "in_progress":
            issues.append({"case": trial["case"], "trial_id": trial["trial_id"],
                           "reason": "trial is incomplete"})
        elif trial.get("status") == "invalid":
            issues.append({"trial_id": trial["trial_id"], "reason": "invalid trial evidence"})
        elif trial.get("status") == "completed" and not trial.get("eligible"):
            issues.append({"case": trial["case"], "trial_id": trial["trial_id"],
                           "reason": "trial is inconsistent and is excluded from pairing"})
    result = {
        "schema_version": SCHEMA_VERSION,
        "case": case,
        "trials": trials,
        "groups": groups,
        "comparisons": groups,
        "issues": issues,
        "caveat": CAVEAT,
    }
    return result


# Descriptive aliases keep the small module convenient for callers that prefer
# verb-first names while the CLI uses the concise command names.
start_measurement = measure_start
stop_measurement = measure_stop
build_measurement_report = measurement_report
