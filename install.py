#!/usr/bin/env python3
"""Plan-first installer for the shared SWE Sidekick skill.

The installer writes only the public application payload, the Codex and Devin
skill discovery files, and the local command wrapper.  It never edits global
host settings or the sidekick task/configuration state directory.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import stat
import sys
import tempfile
import uuid


ROOT = Path(__file__).resolve().parent
VERSION = "0.3.0"
PREVIOUS_VERSION = "0.2.0"
LEGACY_VERSION = "0.1.1-local.1"

# The source payload is deliberately explicit.  Adding a file here is a
# release decision, rather than an accidental consequence of walking ROOT.
PUBLIC_PAYLOADS = (
    "swe_sidekick.py",
    "sidekick_measurement.py",
    "sidekick_evaluation.py",
    "README.md",
    "README_JA.md",
    "SECURITY.md",
    "LICENSE",
    "TEST_REPORT.md",
    "docs/HOSTS.md",
    "docs/CHEATSHEET.md",
    "docs/EVALUATION.md",
    "docs/MASTER_PLAN.md",
    "docs/ROADMAP.md",
    "examples/packet.json",
    "examples/evaluation-record.json",
    "examples/evaluation.csv",
)

# Exact payloads written by the immediately previous managed release. Keep an
# explicit allowlist so files introduced after 0.2.0 are never treated as
# owned by an older manifest during a 0.3.0 upgrade.
PREVIOUS_PAYLOADS = (
    "swe_sidekick.py",
    "sidekick_evaluation.py",
    "README.md",
    "README_JA.md",
    "SECURITY.md",
    "LICENSE",
    "TEST_REPORT.md",
    "docs/HOSTS.md",
    "docs/EVALUATION.md",
    "docs/MASTER_PLAN.md",
    "docs/ROADMAP.md",
    "examples/packet.json",
    "examples/evaluation-record.json",
    "examples/evaluation.csv",
)

# These are the exact files written by the original local installer.  They
# are retained only as a compatibility allowlist while upgrading an existing
# 0.1.1-local.1 installation; no new install copies them.
LEGACY_PAYLOADS = (
    "swe_sidekick.py",
    "sidekick_evaluation.py",
    "README_JA.md",
    "SECURITY.md",
    "LICENSE",
    "TEST_REPORT.md",
    "docs/DECISIONS.md",
    "docs/EVALUATION.md",
    "docs/FUSION_REFERENCE.json",
    "docs/MASTER_PLAN.md",
    "docs/ROADMAP.md",
    "docs/INSTALLATION_REPORT.md",
    "docs/LOCAL_VALIDATION.md",
    "examples/evaluation-record.json",
    "examples/evaluation.csv",
    "examples/packet.json",
)

APP_BASE = Path(".local/share/codex-swe-sidekick")
STATE_BASE = Path(".local/state/codex-swe-sidekick")
# Codex discovers user skills below ~/.codex.  The original local installer
# used ~/.agents, which is also a Devin discovery root and therefore caused a
# duplicate skill exposure.  Keep the old path only for migration cleanup.
CODEX_SKILL_BASE = Path(".codex/skills/swe-sidekick")
LEGACY_CODEX_SKILL_BASE = Path(".agents/skills/swe-sidekick")
DEVIN_SKILL_BASE = Path(".config/devin/skills/swe-sidekick")
CLI_RELATIVE = Path(".local/bin/swe-sidekick")
MANIFEST_RELATIVE = APP_BASE / "install-manifest.json"

_MUTATION_COUNT = 0
# Tests may set this hook to raise after a selected mutation.  It is inert in
# normal use and keeps failure-injection tests independent of real home paths.
MUTATION_HOOK = None


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _safe_mode(value):
    return stat.S_IMODE(value)


def _is_regular(path: Path) -> bool:
    try:
        return stat.S_ISREG(path.lstat().st_mode)
    except FileNotFoundError:
        return False


def _check_home(home: Path) -> None:
    if home.is_symlink() or not home.is_dir():
        raise RuntimeError(f"Home must be an existing directory: {home}")


def _check_parent_chain(path: Path, home: Path) -> None:
    """Reject symlink/file ancestors before any path is written."""
    try:
        path.relative_to(home)
    except ValueError as exc:
        raise RuntimeError(f"Path is outside selected home: {path}") from exc
    current = path.parent
    while True:
        if current == home:
            break
        try:
            info = current.lstat()
        except FileNotFoundError:
            current = current.parent
            continue
        if stat.S_ISLNK(info.st_mode):
            raise RuntimeError(f"Refusing symlink directory: {current}")
        if not stat.S_ISDIR(info.st_mode):
            raise RuntimeError(f"Path component is not a directory: {current}")
        current = current.parent
        try:
            current.relative_to(home)
        except ValueError as exc:
            raise RuntimeError(f"Path is outside selected home: {path}") from exc


def _mkdir_private(path: Path, home: Path) -> None:
    _check_parent_chain(path / ".placeholder", home)
    try:
        if path.is_symlink():
            raise RuntimeError(f"Refusing symlink directory: {path}")
        if path.exists() and not path.is_dir():
            raise RuntimeError(f"Path is not a directory: {path}")
        path.mkdir(parents=True, exist_ok=True, mode=0o700)
        if path.is_symlink():
            raise RuntimeError(f"Refusing symlink directory: {path}")
        os.chmod(path, 0o700)
    except OSError as exc:
        raise RuntimeError(f"Could not create private directory {path}: {exc}") from exc


def _skill_text(home: Path, app: Path) -> str:
    source = ROOT / "skill/SKILL.md"
    if source.is_symlink() or not source.is_file():
        raise RuntimeError(f"Missing canonical skill: {source}")
    text = source.read_text(encoding="utf-8")
    replacements = {
        "__SIDEKICK_CLI__": str(home / CLI_RELATIVE),
        "__SIDEKICK_BIN__": str(home / CLI_RELATIVE),
        "__SIDEKICK_HOME__": str(app),
    }
    for key, value in replacements.items():
        text = text.replace(key, value)
    return text


def _devin_skill_text(canonical: str) -> str:
    """Add only Devin's discovery trigger to the shared skill frontmatter."""
    if not canonical.startswith("---\n"):
        raise RuntimeError("Canonical skill is missing YAML frontmatter")
    end = canonical.find("\n---\n", 4)
    if end < 0:
        raise RuntimeError("Canonical skill has incomplete YAML frontmatter")
    frontmatter = canonical[4:end]
    # Codex's validator rejects custom frontmatter keys, so the source skill
    # must remain untouched.  Replace an accidental duplicate deterministically
    # in the Devin rendering only.
    lines = [line for line in frontmatter.splitlines() if not line.startswith("triggers:")]
    rendered = "---\n" + "\n".join(lines) + "\ntriggers: [user]\n---\n"
    return rendered + canonical[end + len("\n---\n"):]


def payloads(home: Path):
    """Return target path -> (bytes, mode) for the current release."""
    app = home / APP_BASE / VERSION
    codex_skill = home / CODEX_SKILL_BASE
    devin_skill = home / DEVIN_SKILL_BASE
    cli = home / CLI_RELATIVE
    files = {}

    for relative in PUBLIC_PAYLOADS:
        source = ROOT / relative
        if source.is_symlink() or not source.is_file():
            raise RuntimeError(f"Missing allowlisted public payload: {source}")
        files[app / relative] = (source.read_bytes(), 0o644)

    canonical = _skill_text(home, app)
    files[codex_skill / "SKILL.md"] = (canonical.encode("utf-8"), 0o644)
    openai_source = ROOT / "skill/agents/openai.yaml"
    if openai_source.is_symlink() or not openai_source.is_file():
        raise RuntimeError(f"Missing canonical Codex agent config: {openai_source}")
    files[codex_skill / "agents/openai.yaml"] = (openai_source.read_bytes(), 0o644)
    files[devin_skill / "SKILL.md"] = (_devin_skill_text(canonical).encode("utf-8"), 0o644)

    wrapper = (
        "#!/bin/sh\nexec "
        + shlex.quote(sys.executable)
        + " "
        + shlex.quote(str(app / "swe_sidekick.py"))
        + ' "$@"\n'
    )
    files[cli] = (wrapper.encode("utf-8"), 0o755)
    return files


def _known_paths(home: Path, version: str):
    """Return exact manifest paths and their canonical modes.

    A manifest path is accepted only if it is one of these values.  In
    particular, a path merely below a managed directory is not sufficient.
    """
    app = home / APP_BASE / version
    if version == VERSION:
        payloads_for_version = PUBLIC_PAYLOADS
    elif version == PREVIOUS_VERSION:
        payloads_for_version = PREVIOUS_PAYLOADS
    else:
        payloads_for_version = LEGACY_PAYLOADS
    paths = {app / relative: 0o644 for relative in payloads_for_version}
    codex_skill_base = CODEX_SKILL_BASE if version in (VERSION, PREVIOUS_VERSION) else LEGACY_CODEX_SKILL_BASE
    paths.update({
        home / codex_skill_base / "SKILL.md": 0o644,
        home / codex_skill_base / "agents/openai.yaml": 0o644,
        home / CLI_RELATIVE: 0o755,
    })
    if version in (VERSION, PREVIOUS_VERSION):
        paths[home / DEVIN_SKILL_BASE / "SKILL.md"] = 0o644
    return paths


def _manifest_path(home: Path) -> Path:
    return home / MANIFEST_RELATIVE


def _reject_duplicate_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate manifest key: {key}")
        result[key] = value
    return result


def _read_manifest(path: Path):
    if path.is_symlink() or not _is_regular(path):
        raise RuntimeError(f"No valid installation manifest: {path}")
    try:
        if path.stat().st_size > 4 * 1024 * 1024:
            raise RuntimeError("Installation manifest is too large")
        raw = path.read_text(encoding="utf-8")
        value = json.loads(raw, object_pairs_hook=_reject_duplicate_pairs)
    except (OSError, UnicodeError, ValueError) as exc:
        raise RuntimeError(f"Invalid installation manifest: {path}") from exc
    if not isinstance(value, dict):
        raise RuntimeError("Installation manifest must be an object")
    return value, raw.encode("utf-8"), _safe_mode(path.lstat().st_mode)


def _manifest_records(home: Path, state):
    if not isinstance(state, dict):
        raise RuntimeError("Installation manifest must be an object")
    version = state.get("version")
    if not isinstance(version, str) or version not in (VERSION, PREVIOUS_VERSION, LEGACY_VERSION):
        raise RuntimeError("Unsupported installation manifest version")
    if "app_version" in state and state["app_version"] != version:
        raise RuntimeError("Manifest app version does not match version")
    records = state.get("created")
    if not isinstance(records, list) or not records:
        raise RuntimeError("Installation manifest has no managed files")
    known = _known_paths(home, version)
    result = []
    seen = set()
    for record in records:
        if not isinstance(record, dict):
            raise RuntimeError("Invalid manifest file record")
        path_value = record.get("path")
        if not isinstance(path_value, str) or path_value in seen:
            raise RuntimeError("Invalid or duplicate manifest path")
        seen.add(path_value)
        expected_path = Path(path_value)
        if path_value != str(expected_path) or expected_path not in known:
            raise RuntimeError(f"Manifest path is outside the managed package: {path_value}")
        digest = record.get("sha256")
        if not isinstance(digest, str) or len(digest) != 64:
            raise RuntimeError(f"Invalid manifest hash: {path_value}")
        try:
            int(digest, 16)
        except ValueError as exc:
            raise RuntimeError(f"Invalid manifest hash: {path_value}") from exc
        mode = record.get("mode")
        if mode is not None and (
            isinstance(mode, bool) or not isinstance(mode, int) or mode < 0 or mode > 0o777
        ):
            raise RuntimeError(f"Invalid manifest mode: {path_value}")
        if version == VERSION and mode is None:
            raise RuntimeError(f"Current manifest is missing mode: {path_value}")
        result.append({
            "path": expected_path,
            "sha256": digest.lower(),
            "mode": mode,
            "canonical_mode": known[expected_path],
        })
    return version, result


def _validate_owned_files(home: Path, version: str, records):
    for record in records:
        path = record["path"]
        _check_parent_chain(path, home)
        if path.is_symlink() or not _is_regular(path):
            raise RuntimeError(f"Managed file is missing or not regular: {path}")
        actual_mode = _safe_mode(path.lstat().st_mode)
        expected_mode = record["mode"] if record["mode"] is not None else record["canonical_mode"]
        if actual_mode != expected_mode:
            raise RuntimeError(f"Managed file mode changed; refusing update: {path}")
        if sha(path.read_bytes()) != record["sha256"]:
            raise RuntimeError(f"Managed file changed; refusing update: {path}")


def _check_manifest_location(home: Path):
    manifest = _manifest_path(home)
    _check_parent_chain(manifest, home)
    if manifest.is_symlink():
        raise RuntimeError("Installation manifest is a symlink")
    return manifest


def _check_targets(home: Path, files, owned, *, upgrade: bool):
    for path, (_, mode) in files.items():
        _check_parent_chain(path, home)
        if path.is_symlink():
            raise RuntimeError(f"Refusing symlink target: {path}")
        if not path.exists():
            continue
        if not _is_regular(path):
            raise RuntimeError(f"Conflict; target is not a regular file: {path}")
        if path not in owned:
            raise RuntimeError(f"Unowned conflict; nothing changed: {path}")
        # Owned files have already been checked against the existing manifest.
        if _safe_mode(path.lstat().st_mode) != mode:
            raise RuntimeError(f"Target mode conflict; nothing changed: {path}")


def _mutation_gate(action: str, path: Path):
    global _MUTATION_COUNT
    _MUTATION_COUNT += 1
    hook = MUTATION_HOOK
    if callable(hook):
        hook(action, path)
    injected = os.environ.get("SWE_SIDEKICK_INSTALL_FAIL_AFTER")
    if injected is not None:
        try:
            threshold = int(injected)
        except ValueError as exc:
            raise RuntimeError("Invalid SWE_SIDEKICK_INSTALL_FAIL_AFTER") from exc
        if _MUTATION_COUNT > threshold:
            raise RuntimeError("Injected installer failure")


def _ensure_parent_dirs(path: Path, home: Path, created_dirs=None):
    _check_parent_chain(path, home)
    missing = []
    current = path.parent
    while current != home and not current.exists():
        missing.append(current)
        current = current.parent
    path.parent.mkdir(parents=True, exist_ok=True)
    if created_dirs is not None:
        created_dirs.extend(reversed(missing))


def _write_atomic(path: Path, data: bytes, mode: int, home: Path, *, gate=True, created_dirs=None):
    _check_parent_chain(path, home)
    if path.is_symlink():
        raise RuntimeError(f"Refusing symlink target: {path}")
    _ensure_parent_dirs(path, home, created_dirs)
    temporary = None
    try:
        fd, temporary = tempfile.mkstemp(prefix=".swe-sidekick-", dir=str(path.parent))
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
        os.chmod(temporary, mode)
        if gate:
            _mutation_gate("write", path)
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass


def _backup_installation(home: Path, manifest_raw: bytes, manifest_mode: int, records):
    base = home / STATE_BASE / "install-backups"
    _mkdir_private(base, home)
    backup = base / (VERSION + "-" + uuid.uuid4().hex)
    backup.mkdir(mode=0o700)
    files_dir = backup / "files"
    files_dir.mkdir(mode=0o700)
    manifest_copy = backup / "install-manifest.json"
    _write_atomic(manifest_copy, manifest_raw, manifest_mode, home, gate=False)
    copied = []
    for index, record in enumerate(records):
        source = record["path"]
        actual_mode = _safe_mode(source.lstat().st_mode)
        data = source.read_bytes()
        target = files_dir / f"{index:04d}.bin"
        _write_atomic(target, data, actual_mode, home, gate=False)
        copied.append({
            "path": str(source),
            "backup": str(target.relative_to(backup)),
            "sha256": sha(data),
            "mode": actual_mode,
        })
    metadata = {
        "format": 1,
        "version": VERSION,
        "source_manifest_sha256": sha(manifest_raw),
        "manifest": {
            "path": str(_manifest_path(home)),
            "backup": "install-manifest.json",
            "sha256": sha(manifest_raw),
            "mode": manifest_mode,
        },
        "files": copied,
    }
    _write_atomic(
        backup / "backup.json",
        (json.dumps(metadata, indent=2, sort_keys=True) + "\n").encode(),
        0o600,
        home,
        gate=False,
    )
    return backup


def _restore_file(path: Path, data: bytes, mode: int, home: Path):
    # Rollback deliberately bypasses the mutation hook.  It must be able to
    # restore the transaction after the injected failure itself.
    _write_atomic(path, data, mode, home, gate=False)


def _rollback(home, originals, created, created_dirs, manifest, old_manifest, old_manifest_mode):
    failures = []
    for path in reversed(created):
        try:
            if path.exists() or path.is_symlink():
                if path.is_symlink() or _is_regular(path):
                    path.unlink()
        except OSError as exc:
            failures.append(f"remove {path}: {exc}")
    for path, (data, mode) in reversed(list(originals.items())):
        try:
            _restore_file(path, data, mode, home)
        except (OSError, RuntimeError) as exc:
            failures.append(f"restore {path}: {exc}")
    try:
        if old_manifest is None:
            if manifest.exists() or manifest.is_symlink():
                manifest.unlink()
        else:
            _restore_file(manifest, old_manifest, old_manifest_mode, home)
    except (OSError, RuntimeError) as exc:
        failures.append(f"restore manifest {manifest}: {exc}")
    for directory in reversed(created_dirs):
        try:
            if directory.is_dir() and not directory.is_symlink():
                directory.rmdir()
        except OSError:
            # A pre-existing/unknown entry makes the directory non-empty; the
            # files owned by this transaction have already been rolled back.
            pass
    if failures:
        raise RuntimeError("Rollback failed: " + "; ".join(failures))


def _new_manifest(files, previous_app_version=None):
    records = []
    for path, (data, mode) in files.items():
        records.append({"path": str(path), "sha256": sha(data), "mode": mode})
    value = {"version": VERSION, "app_version": VERSION, "created": records}
    if previous_app_version is not None:
        value["previous_app_version"] = previous_app_version
    return value


def _manifest_owned(records):
    return {record["path"]: record for record in records}


def _legacy_cleanup(home: Path, version: str, records):
    """Return only old shared skill files owned by the legacy manifest.

    The legacy installer placed Codex's skill below ``~/.agents``.  That
    directory is a Devin discovery root too, so a managed upgrade must remove
    the two exact legacy files after writing their current replacements.  Any
    other entry below the old directory remains untouched.
    """
    if version != LEGACY_VERSION:
        return []
    owned = _manifest_owned(records)
    candidates = (
        home / LEGACY_CODEX_SKILL_BASE / "SKILL.md",
        home / LEGACY_CODEX_SKILL_BASE / "agents/openai.yaml",
    )
    return [{"path": path} for path in candidates if path in owned]


def _install_or_upgrade(home: Path, *, apply: bool, upgrade: bool):
    manifest = _check_manifest_location(home)
    existing_state = None
    old_manifest_raw = None
    old_manifest_mode = None
    old_version = None
    old_records = []
    if manifest.exists():
        existing_state, old_manifest_raw, old_manifest_mode = _read_manifest(manifest)
        old_version, old_records = _manifest_records(home, existing_state)
        _validate_owned_files(home, old_version, old_records)
        if not upgrade and old_version != VERSION:
            raise RuntimeError(f"Existing {old_version} installation requires --upgrade")
    elif upgrade:
        raise RuntimeError("--upgrade requires an existing managed installation")

    files = payloads(home)
    owned = _manifest_owned(old_records)
    _check_targets(home, files, owned, upgrade=upgrade)
    legacy_cleanup = _legacy_cleanup(home, old_version, old_records) if upgrade else []

    if existing_state and not upgrade:
        # A current, unchanged install is idempotent.  A source change needs an
        # explicit upgrade so a normal invocation cannot overwrite local files.
        if all(
            path.is_file()
            and not path.is_symlink()
            and path.read_bytes() == data
            and _safe_mode(path.lstat().st_mode) == mode
            for path, (data, mode) in files.items()
        ):
            for path in files:
                print("SAME  ", path)
            print("Already installed; no files changed.")
            return 0
        raise RuntimeError("Installed files differ; pass --upgrade to update them")

    for path in files:
        print("UPDATE " if path.exists() else "CREATE ", path)
    for record in legacy_cleanup:
        print("REMOVE ", record["path"])
    if not apply:
        print("Plan only. No files were changed. Pass --apply to continue.")
        return 0

    global _MUTATION_COUNT
    _MUTATION_COUNT = 0
    backup = None
    originals = {}
    created = []
    created_dirs = []
    try:
        overwritten = []
        if upgrade:
            for path in files:
                if path.exists() and path in owned:
                    overwritten.append({"path": path})
            overwritten.extend(legacy_cleanup)
            backup = _backup_installation(home, old_manifest_raw, old_manifest_mode, overwritten)
        for path, (data, mode) in files.items():
            if path.exists():
                originals[path] = (path.read_bytes(), _safe_mode(path.lstat().st_mode))
            else:
                created.append(path)
            _write_atomic(path, data, mode, home, created_dirs=created_dirs)
        # Remove the legacy shared skill only after all current payloads have
        # been written.  Track its bytes for rollback if a later mutation
        # fails, and gate the unlink so failure injection covers this step.
        for record in legacy_cleanup:
            path = record["path"]
            if path.is_symlink() or not _is_regular(path):
                raise RuntimeError(f"Legacy managed file changed; refusing update: {path}")
            originals[path] = (path.read_bytes(), _safe_mode(path.lstat().st_mode))
            _mutation_gate("remove", path)
            path.unlink()
        manifest_data = (
            json.dumps(
                _new_manifest(files, old_version if upgrade else None),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8")
        if manifest.exists():
            originals[manifest] = (manifest.read_bytes(), _safe_mode(manifest.lstat().st_mode))
        else:
            created.append(manifest)
        _write_atomic(manifest, manifest_data, 0o600, home, created_dirs=created_dirs)
    except Exception:
        try:
            _rollback(home, originals, created, created_dirs, manifest, old_manifest_raw, old_manifest_mode)
        except Exception as rollback_error:
            raise RuntimeError(f"Install failed and rollback failed: {rollback_error}")
        raise

    if backup:
        print("Backup ", backup)
    print("Installed. Global model settings were not modified.")
    return 0


def _uninstall(home: Path, *, apply: bool):
    manifest = _check_manifest_location(home)
    if not manifest.exists():
        raise RuntimeError("No valid installation manifest")
    state, _, _ = _read_manifest(manifest)
    _, records = _manifest_records(home, state)
    _validate_owned_files(home, state["version"], records)
    for record in records:
        print("REMOVE", record["path"])
    print("KEEP  ", home / STATE_BASE, "(tasks, configuration and logs)")
    if not apply:
        print("Plan only. Pass --apply to uninstall these unchanged files.")
        return 0
    for record in records:
        record["path"].unlink()
    manifest.unlink()
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--home", type=Path, default=Path.home())
    parser.add_argument("--apply", action="store_true")
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--uninstall", action="store_true")
    actions.add_argument("--upgrade", action="store_true")
    args = parser.parse_args(argv)
    if sys.version_info < (3, 10):
        raise SystemExit("Python 3.10 or newer is required")
    try:
        selected_home = args.home.expanduser()
        if selected_home.is_symlink():
            raise RuntimeError(f"Home must not be a symlink: {selected_home}")
        home = selected_home.resolve()
        _check_home(home)
        if args.uninstall:
            return _uninstall(home, apply=args.apply)
        return _install_or_upgrade(home, apply=args.apply, upgrade=args.upgrade)
    except (OSError, ValueError, RuntimeError) as exc:
        print("error:", exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
