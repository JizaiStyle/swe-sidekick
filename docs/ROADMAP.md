# SWE Sidekick v0.2.0 Roadmap

Updated: 2026-09-15
Requirements: [MASTER_PLAN.md](MASTER_PLAN.md)

This file is the single source of truth for current progress. Status values are **Not started**, **In progress**, **Partially complete**, **Complete**, and **On hold**; implementation, validation, installation, and publication are recorded separately.

| ID | Priority / dependency | Status | Completed | Remaining work and completion evidence |
|---|---|---|---|---|
| MP-10 | 1 / existing safety model | Complete | Host-neutral guidance and sequential handoff are implemented. Native Codex and Devin discovery passed with one skill per host and explicit invocation metadata. Files: `skill/**`, `docs/HOSTS.md`, `docs/EVALUATION.md`, `sidekick_evaluation.py`, `README*`. | No remaining implementation work. Real model execution is outside this release's validation scope. Evidence: [TEST_REPORT.md](../TEST_REPORT.md). |
| MP-11 | 1 / MP-10 interface | Complete | Read-only handoff schema v1, shared locking, current/stale patch hashes, malformed-state handling, state/scope continuation guards and bracketed input compatibility are implemented and tested. Files: `swe_sidekick.py`, `tests/test_sidekick.py`. | No remaining implementation work. Sol integration findings were corrected; final offline suite passed. Evidence: [TEST_REPORT.md](../TEST_REPORT.md). |
| MP-12 | 2 / MP-10, MP-11 | Complete | Host-specific installation, managed ownership checks, legacy migration, backups, rollback and same-version refresh are implemented and tested. The local managed installation was upgraded to 0.2.0; native discovery passed. Files: `install.py`, `tests/test_install.py`. | No remaining implementation work. Existing tasks and global model settings were preserved. Evidence: [TEST_REPORT.md](../TEST_REPORT.md). |
| MP-13 | 3 / MP-10–12 | Complete | The separate public tree passed the final 76-test suite, skill validation, link checks, privacy inspection and Gitleaks tree/history scans. [JizaiStyle/swe-sidekick](https://github.com/JizaiStyle/swe-sidekick) was created as a public repository and pushed; GitHub's `main` SHA matched the reviewed local release commit. Files: `README*`, `SECURITY.md`, `TEST_REPORT.md`, `.github/workflows/test.yml`, `.gitignore`, `AGENTS.md`, this roadmap. | No release requirement remains. No real model was executed; live compatibility and performance remain unmeasured. Hosted CI evidence is linked from [TEST_REPORT.md](../TEST_REPORT.md). |

## Validation record

2026-09-15 — MP-10–13 requirements, ownership, dependencies, safety boundaries, and completion conditions were added before implementation. No implementation, installation, model execution, repository publication, or remote mutation is claimed by this entry.

2026-09-15 — MP-10/12: host-specific invocation metadata is rendered separately because Devin uses `triggers: [user]` while the canonical Codex skill validator rejects that extension. Both hosts must preserve explicit-only invocation. This adds one managed Devin skill file and changes no global model settings. MP-13: release integration is in progress; publication is still pending.

2026-09-15 — MP-10/12 correction from native discovery: placing both a shared `.agents` skill and a Devin-specific skill causes Devin to namespace them as `agents:swe-sidekick` and `devin:swe-sidekick`, with implicit invocation still enabled on the shared copy. The release therefore uses `.codex/skills` for Codex and `.config/devin/skills` for Devin. Upgrade must back up and remove only the old managed shared skill files, restoring them on failure. This supersedes the initial shared-directory design; global model configuration and existing tasks remain outside the change.

2026-09-15 — MP-10–12 implementation, offline validation and native installation/discovery completed. The final suite passed 76 tests in 52.923 seconds. MP-13 publication remains pending; detailed evidence and validation limits are in [TEST_REPORT.md](../TEST_REPORT.md).

2026-09-15 — MP-13 publication completed. GitHub API confirmed public visibility and `main` at the initial reviewed release commit `68024d1e02e70749bad26fe2c32da4c485e4121c`. Gitleaks scanned that fresh Git history with no findings. Publication used a contributor label and GitHub noreply address, without importing private repository history. The release evidence documentation is maintained in subsequent commits; source and test results are unchanged.

2026-09-15 — MP-13 hosted verification completed: the initial GitHub Actions run passed its Ubuntu Python 3.10, 3.12 and 3.14 matrix. The final evidence-only documentation update does not repeat the unchanged test suite. Native discovery, the full local test suite and public CI are all verified; live model execution remains outside scope.
