#!/usr/bin/env python3
"""Offline CLI fixture, NOT an implementation of Devin or its sandbox."""
import json
from pathlib import Path
import subprocess
import sys
import time

args = sys.argv[1:]
control = Path(__file__).with_name("fake-mode.json")
mode = json.loads(control.read_text()) if control.exists() else {}
if args == ["--version"]:
    print(mode.get("version", "devin-test-fixture 1")); raise SystemExit(0)
if args == ["--help"]:
    print("--model --sandbox --permission-mode --prompt-file --print --export --resume --config --respect-workspace-trust"); raise SystemExit(0)
if args == ["auth", "status"]:
    print("Authenticated (offline fixture only)"); raise SystemExit(0)
if args[:2] == ["models", "list"]:
    print(json.dumps({"families": [{"name": "SWE", "models": [
        {"id": "swe-2-high", "display_name": "SWE-2 High"},
        {"id": "swe-2-medium", "display_name": "SWE-2 Medium"},
        {"id": "swe-2-max", "display_name": "SWE-2 Max"}]}]})); raise SystemExit(0)
if "--print" not in args:
    raise SystemExit("unexpected command in fixture")
assert "--sandbox" in args
assert args[args.index("--permission-mode") + 1] == "autonomous"
assert "--continue" not in args
if mode.get("expect_resume"):
    assert "--resume" in args
    assert args[args.index("--resume") + 1] == "fixture-session-123"
ws = Path.cwd()
kind = mode.get("behavior", "success")
if kind == "timeout": time.sleep(20)
if kind == "no_changes":
    pass
elif kind == "out_of_scope":
    (ws / "outside.txt").write_text("not authorized")
elif kind == "symlink":
    (ws / "src/add.py").unlink()
    (ws / "src/add.py").symlink_to("/etc/passwd")
elif kind == "index":
    subprocess.run(["git", "config", "user.name", "changed"], check=True)
else:
    (ws / "src/add.py").write_text("def add(a, b):\n    return a + b\n")
    if kind == "new_file": (ws / "src/new.txt").write_text("new file\n")
    if kind == "delete": (ws / "src/old.txt").unlink()
    if kind == "binary": (ws / "src/blob.bin").write_bytes(b"\x00\x01NEW\xff\n")
    if kind == "executable": (ws / "src/add.py").chmod(0o755)
    if kind == "commit":
        subprocess.run(["git", "add", "-A"], check=True)
        subprocess.run(["git", "-c", "user.name=fixture", "-c", "user.email=fixture@localhost", "commit", "-m", "bad"], check=True, capture_output=True)
if not mode.get("no_export"):
    exported = {"schema_version": "ATIF-v1.0", "session_id": "fixture-session-123",
                "agent": {"name": "fixture", "model_name": mode.get("reported_model", "swe-2-high")},
                "steps": []}
    Path(args[args.index("--export") + 1]).write_text(json.dumps(exported))
if kind == "no_changes":
    print("Offline fixture made no changes; this is not evidence of a real Devin call.")
else:
    print("Offline fixture changed src/add.py; this is not evidence of a real Devin call.")
raise SystemExit(mode.get("exit_code", 0))
