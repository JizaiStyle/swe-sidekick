# Validation report

Version: **0.3.0**. Checked **2026-09-15** on macOS with Python 3.14.7, Codex CLI 0.154.0 and Devin CLI 3000.10.21. Current release progress is maintained in [ROADMAP.md](docs/ROADMAP.md).

## Offline tests

```text
python3 -m unittest discover -s tests -v
Ran 86 tests in 41.949s
OK
```

The final suite ran after implementation writes finished. It covers bounded fake-worker execution, scope and Git guards, verification and apply gates, private evaluation records, read-only handoff, stale patch detection, task locks, malformed verification, state-specific continuation, and bracketed filenames as read-only inputs. Measurement fixtures cover current-root baselines, input/cache/output counters, report privacy, strict pairs, model mismatch, incomplete evidence, malformed rollouts, nonmonotonic counters and symlinks. Installer tests cover fresh installation, managed upgrades from 0.2.0 and the legacy release, same-version refresh, host-path migration, modified/unowned refusal, backups and injected-failure rollback.

The elapsed time above is the local test suite duration, not model latency. No paid Codex, Fable or SWE-2 inference was started for release validation.

## Current Codex rollout compatibility

A temporary local trial exercised `measure-start`, `measure-stop` and
`measurement-report` against the invoking Codex session's current rollout. It
passed with the installed schema fields for input, cached input, cache-write
input, output, reasoning output and total tokens. The smoke check also verified
that CLI/report JSON omitted session/thread/root-turn IDs, rollout timestamps,
ordinals and the cumulative baseline. Its temporary state was removed and its
token values were not published. This proves compatibility with the checked
Codex CLI build; the parser remains dependent on that private local schema.

## Native discovery and installation

- Codex `skills/list` with a forced reload discovered exactly one enabled `swe-sidekick` in the Codex-specific skill directory, with the updated host-neutral prompt.
- Devin `skills list --json` discovered exactly one `swe-sidekick`, `triggers: [user]`, and no skill warnings or errors.
- The canonical skill passed the Codex skill creator's `quick_validate.py`; its OpenAI metadata retains `allow_implicit_invocation: false`. The Devin rendering adds its user trigger without a model or subagent override.
- The managed installation was upgraded from 0.2.0 to 0.3.0 with a backup. The manifest covers 20 installed files and every recorded SHA-256 matched. The measurement module and cheat sheet are installed; no global model settings or task data changed.

Codex app-server `skills/list` with `forceReload` returned exactly one enabled
`swe-sidekick` without errors. Devin `skills list --json` returned exactly one
explicit-user `swe-sidekick` without warnings or errors. Discovery confirms
loading and metadata, not actual Fable/SWE-2 execution, output quality, sandbox
containment, billing or cache charging. Exact model availability and the
configured Devin version must still pass `doctor` before a real run.

## Public-tree checks

- Gitleaks 8.30.1 directory and fresh Git-history scans: no leaks detected. The scanner archive was checked against its published checksum before use.
- The public file list was inspected for personal absolute paths, private project references, real historical task IDs, raw logs, local state and credential material. None of those were included. Example Git identities are synthetic; publication uses a GitHub noreply commit address.
- Markdown relative links and canonical skill metadata passed validation. The v0.3 [hosted GitHub Actions run](https://github.com/JizaiStyle/swe-sidekick/actions/runs/34928507570) completed successfully on Ubuntu for Python 3.10, 3.12 and 3.14. This is separate from the local macOS result above. The later release-evidence-only documentation commit does not change the tested runtime, installer or tests.

GitHub checks confirmed that [the repository](https://github.com/JizaiStyle/swe-sidekick) remains public and accepted the reviewed v0.3 runtime commit `21f84c49b214c309b2a1b5e9122825ca4031cc20`. The original private development tree and its history were not imported.

Scanning is not a guarantee that arbitrary future task artifacts are safe to publish. Handoff snapshots, evaluation records, prompts and worker logs remain private local data.

## English documentation update (MP-14)

On 2026-09-15, the default evaluation guide, example task text, skill summary
and security heading were made English. `README_JA.md` remains a labelled
alternative translation. Review confirmed that task scope, verification argv,
schema version and the explicit invocation policy were unchanged. The packet
passed the runtime packet validator; metadata parsing, skill validation,
relative links, public-language scanning and managed payload rendering passed.
No runtime code changed, and the earlier full test suite was not rerun for this
update. Publication and the matching managed installation were refreshed.
