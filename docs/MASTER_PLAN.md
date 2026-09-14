# SWE Sidekick v0.2.0 Master Plan

Updated: 2026-09-15

## Purpose and target state

Publish a host-neutral SWE Sidekick skill that lets the user keep either Codex or Devin Fable as the current lead while delegating bounded implementation work to an explicitly configured SWE-2 worker. A long task may move between lead hosts section by section through an explicit, read-only handoff; the skill never selects or changes the lead model itself.

The public v0.2.0 release must preserve the existing safety boundaries: trusted clean source, an isolated snapshot, sandboxed worker execution, explicit session resume, bounded retries, independent verification, reviewed patch hashes, and unknown values instead of inferred usage or cost.

## Scope and constraints

This release changes the CLI, installer, skill guidance, public documentation, tests, and release repository. It does not add automatic lead routing, concurrent lead sessions, cloud orchestration, paid-model tests, task migration, automatic resume, global Codex/Devin configuration changes, or modification of existing task state during installation.

Only sanitized source files belong in the public repository. Credentials, raw logs, local state, real task IDs, personal filesystem paths, and conversation-derived material must not be committed. Tests use fake workers and isolated temporary directories.

## Requirements and phases

| Phase | ID | Requirement | Completion condition |
|---|---|---|---|
| P4 | MP-10 | Host-neutral lead workflow | The skill documents Codex or Devin Fable as a user-selected current lead. Section handoff uses separate, sequential lead sessions for the same task; model selection and automatic resume remain outside the skill. Host-specific instructions preserve the same worker and review boundaries. |
| P4 | MP-11 | Read-only task handoff | `handoff --task ID` emits JSON containing task, source, workspace, packet, status, current patch hash, verification state, and non-automatic continuation guidance. It fails while the task lock is held and never starts a run, model, verification, apply, retry, or state mutation. Tests cover valid, locked, invalid, and incomplete tasks. |
| P5 | MP-12 | Safe host-skill installer | Version 0.2.0 installs the canonical skill at `~/.codex/skills/swe-sidekick` and renders a Devin copy at `~/.config/devin/skills/swe-sidekick` with `triggers: [user]`. Codex retains `allow_implicit_invocation: false`; neither copy overrides the lead model. `--upgrade` accepts only an existing managed installation whose owned files still match its manifest, creates a backup, migrates the old managed shared skill files to avoid duplicate Devin discovery, and rolls back on failure. It rejects unowned or modified installations and does not change global model settings or task data. Install, upgrade, refusal, migration, backup, and rollback tests pass. |
| P6 | MP-13 | Sanitized public release | A clean public repository is created at `JizaiStyle/swe-sidekick` from the approved file allowlist. Privacy and secret checks, focused tests, public HEAD verification, and installed-skill discovery in Codex and Devin pass. Release notes state that no real model was executed for this release. |
| P7 | MP-14 | English public content | Default public documentation, comments, skill descriptions and runnable examples are readable in English. A labelled Japanese translation may remain. Preserve workflow semantics, validate examples, metadata and links, publish the update and refresh the managed installation. |
| P8 | MP-15 | Operator cheat sheet | Publish an English quick reference for lead model/effort selection, independent worker configuration, explicit invocation, review gates and sequential handoff. Validate commands against the CLI and links against the repository; no model execution or configuration changes. |

## Architecture and ownership

- CLI work owns `swe_sidekick.py` and `tests/test_sidekick.py`, including the read-only handoff interface.
- Installer work owns `install.py` and `tests/test_install.py`, including managed upgrade and rollback.
- Skill guidance owns `skill/**`, `docs/HOSTS.md`, and `docs/EVALUATION.md`.
- Integration owns `README*`, `SECURITY.md`, `TEST_REPORT.md`, `.gitignore`, workflows, final validation, repository publication, and public HEAD verification.
- This plan and current progress are maintained only in `docs/MASTER_PLAN.md` and `docs/ROADMAP.md`.

Shared interfaces are fixed before integration. Contributors must not overwrite another workstream's files. The final build and publication happen after all writes finish.

## Execution order

1. Implement and test MP-10 and MP-11 against fake local state.
2. Implement and test MP-12 without changing current tasks or global host settings.
3. Integrate host documentation, security guidance, and release validation.
4. Audit the public tree and history, publish MP-13, verify the remote HEAD, then verify skill discovery without invoking a model.

## Completion and evidence

The release is complete only when every requirement's completion condition is supported by a current test or inspection result, the installed files match the released source, the public remote HEAD matches the reviewed local HEAD, and [ROADMAP.md](ROADMAP.md) records changed files, validation evidence, remaining issues, and the update date. A successful skill discovery check is not evidence that a real Codex, Fable, or SWE-2 model ran.
