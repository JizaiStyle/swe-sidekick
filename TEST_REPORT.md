# Validation report

Version: **0.2.0**. Checked **2026-09-15** on macOS with Python 3.14.7, Codex CLI 0.154.0 and Devin CLI 3000.10.21. Current release progress is maintained in [ROADMAP.md](docs/ROADMAP.md).

## Offline tests

```text
python3 -m unittest discover -s tests -v
Ran 76 tests in 52.923s
OK
```

The final suite ran after implementation writes finished. It covers bounded fake-worker execution, scope and Git guards, verification and apply gates, private evaluation records, read-only handoff, stale patch detection, task locks, malformed verification, state-specific continuation, and bracketed filenames as read-only inputs. Installer tests cover fresh installation, managed upgrade, same-version refresh, legacy host-path migration, modified/unowned refusal, backups and injected-failure rollback.

The elapsed time above is the local test suite duration, not model latency. No real Codex, Fable or SWE-2 inference was performed for this release.

## Native discovery and installation

- Codex `skills/list` with a forced reload discovered exactly one enabled `swe-sidekick` in the Codex-specific skill directory, with the updated host-neutral prompt.
- Devin `skills list --json` discovered exactly one `swe-sidekick`, `triggers: [user]`, and no skill warnings or errors.
- The canonical skill passed the Codex skill creator's `quick_validate.py`; its OpenAI metadata retains `allow_implicit_invocation: false`. The Devin rendering adds its user trigger without a model or subagent override.
- The local managed installation was upgraded to 0.2.0 with a backup. Its old managed shared skill was removed to prevent duplicate Devin discovery. No global model settings or task data were changed.

Discovery confirms loading and metadata, not actual Fable/SWE-2 execution, output quality, sandbox containment, billing or cache behavior. Exact model availability and the configured Devin version must still pass `doctor` before a real run.

## Public-tree checks

- Gitleaks 8.30.1 directory scan: no leaks detected. The scanner archive was checked against its published checksum before use.
- The public file list was inspected for personal absolute paths, private project references, real historical task IDs, raw logs, local state and credential material. None of those were included. Example Git identities are synthetic; publication uses a GitHub noreply commit address.
- Markdown relative links and canonical skill metadata passed validation. The repository includes an offline GitHub Actions matrix for Python 3.10, 3.12 and 3.14; local results above do not imply that hosted CI has already run.

Scanning is not a guarantee that arbitrary future task artifacts are safe to publish. Handoff snapshots, evaluation records, prompts and worker logs remain private local data.
