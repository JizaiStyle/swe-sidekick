# Validation report

Version: **0.3.0**. Current release progress is maintained in [ROADMAP.md](docs/ROADMAP.md).

## Bounded failure recovery (MP-23, 2026-09-18)

The worker changed only `worker_prompt` and one offline first-run/retry regression.
The selected SWE-2 High worker matched its exported model and completed in one
turn (613.416 seconds). Independent review confirmed that runtime AST outside
`worker_prompt` is unchanged, including sandbox/permission settings, task
state, retry limits and apply gates. Worker duration is not cost or quota data.

Independent `verify` ran the 59 wrapper tests successfully in 41.588 seconds.
After reviewed-hash apply, the source repository's new first-run/retry test
passed in 4.283 seconds. The fake worker exercises prompt generation and the
validated same-session retry; it does not simulate an OS sandbox or prove live
error recovery. The implementation run itself used the official Devin CLI
3000.10.31. No model inference is invoked by the tests.

Canonical skill validation passed using an isolated environment with PyYAML
after the default interpreter reported that dependency missing. Documentation
links, whitespace and public-content checks passed. Installed pnpm 11.21.0
help identifies `install --lockfile-only` as lockfile-only work; this is command
selection evidence, not a completed application dependency installation.
The managed same-version upgrade created a backup; all 20 payloads, modes and
manifest hashes matched the reviewed source and Codex/Devin renderings. The
[pull-request CI run](https://github.com/JizaiStyle/swe-sidekick/actions/runs/35314532688)
passed on Python 3.10, 3.12 and 3.14. [PR #1](https://github.com/JizaiStyle/swe-sidekick/pull/1)
merged at `5be39f57e382bb08b37b229b7214c9e7dedbaf9c`; GitHub reported it
merged on 2026-09-18. This final evidence update changes documentation only.
Earlier failed application work is not retroactively accepted.

## Earlier release validation (2026-09-15)

The following records were checked on macOS with Python 3.14.7, Codex CLI
0.154.0 and Devin CLI 3000.10.21; they are historical evidence, not reruns for
MP-23.

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
- Markdown relative links and canonical skill metadata passed validation. The v0.3 [hosted GitHub Actions run](https://github.com/JizaiStyle/swe-sidekick/actions/runs/34928507570) and the [MP-20/21 follow-up run](https://github.com/JizaiStyle/swe-sidekick/actions/runs/34957708680) both completed successfully on Ubuntu for Python 3.10, 3.12 and 3.14. The follow-up run covers the Git-maintenance guard, its regressions and the updated skill guidance. These results are separate from the local macOS result above.

GitHub checks confirmed that [the repository](https://github.com/JizaiStyle/swe-sidekick) remains public and accepted the reviewed follow-up source commit `a993e7f78337b55aed349650225e846b6d602794`. The final release-evidence commit changes only this report and the roadmap. The original private development tree and its history were not imported.

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
