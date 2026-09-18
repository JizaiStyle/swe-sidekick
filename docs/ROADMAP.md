# SWE Sidekick Roadmap

Updated: 2026-09-18
Requirements: [MASTER_PLAN.md](MASTER_PLAN.md)

This file is the single source of truth for current progress. Status values are **Not started**, **In progress**, **Partially complete**, **Complete**, and **On hold**; implementation, validation, installation, and publication are recorded separately.

| ID | Priority / dependency | Status | Completed | Remaining work and completion evidence |
|---|---|---|---|---|
| MP-10 | 1 / existing safety model | Complete | Host-neutral guidance and sequential handoff are implemented. Native Codex and Devin discovery passed with one skill per host and explicit invocation metadata. Files: `skill/**`, `docs/HOSTS.md`, `docs/EVALUATION.md`, `sidekick_evaluation.py`, `README*`. | No remaining implementation work. Real model execution is outside this release's validation scope. Evidence: [TEST_REPORT.md](../TEST_REPORT.md). |
| MP-11 | 1 / MP-10 interface | Complete | Read-only handoff schema v1, shared locking, current/stale patch hashes, malformed-state handling, state/scope continuation guards and bracketed input compatibility are implemented and tested. Files: `swe_sidekick.py`, `tests/test_sidekick.py`. | No remaining implementation work. Sol integration findings were corrected; final offline suite passed. Evidence: [TEST_REPORT.md](../TEST_REPORT.md). |
| MP-12 | 2 / MP-10, MP-11 | Complete | Host-specific installation, managed ownership checks, legacy migration, backups, rollback and same-version refresh are implemented and tested. The local managed installation was upgraded to 0.2.0; native discovery passed. Files: `install.py`, `tests/test_install.py`. | No remaining implementation work. Existing tasks and global model settings were preserved. Evidence: [TEST_REPORT.md](../TEST_REPORT.md). |
| MP-13 | 3 / MP-10–12 | Complete | The separate public tree passed the final 76-test suite, skill validation, link checks, privacy inspection and Gitleaks tree/history scans. [JizaiStyle/swe-sidekick](https://github.com/JizaiStyle/swe-sidekick) was created as a public repository and pushed; GitHub's `main` SHA matched the reviewed local release commit. Files: `README*`, `SECURITY.md`, `TEST_REPORT.md`, `.github/workflows/test.yml`, `.gitignore`, `AGENTS.md`, this roadmap. | No release requirement remains. No real model was executed; live compatibility and performance remain unmeasured. Hosted CI evidence is linked from [TEST_REPORT.md](../TEST_REPORT.md). |
| MP-14 | 4 / MP-10, MP-13 | Complete | Default public text is English; the Japanese README is explicitly labelled as an alternative. The evaluation guide, example packet, skill summary and headings were reviewed and translated. Files: `README.md`, `SECURITY.md`, `docs/EVALUATION.md`, `examples/packet.json`, `skill/agents/openai.yaml`, plan, roadmap and validation report. | Example schema, unchanged executable fields, metadata, links and language checks passed. The update is published and the managed installation refreshed; runtime behavior is unchanged. Evidence: [TEST_REPORT.md](../TEST_REPORT.md). |
| MP-15 | 5 / MP-10, MP-14 | Complete | English operator cheat sheet added and linked from both READMEs and the host guide. Files: `docs/CHEATSHEET.md`, `docs/HOSTS.md`, `README*`, plan and roadmap. Lead model/effort and worker configuration are explicitly independent. | Documentation validation passed as recorded below. No runtime, installation or active model setting changed. Remote HEAD is checked at publication. |
| MP-16 | 6 / MP-10 | Complete | `measure-start` and `measure-stop` bind to the invoking Codex rollout, include the current root turn, retain only counters/metadata in private state, and emit no binding IDs or cumulative baseline. Synthetic and current-rollout checks passed. Files: `sidekick_measurement.py`, `swe_sidekick.py`, tests. | No implementation work remains. The private Codex rollout schema is an explicit compatibility dependency. Evidence: [TEST_REPORT.md](../TEST_REPORT.md). |
| MP-17 | 7 / MP-16 | Complete | `measurement-report` preserves sanitized observations and calculates per-counter saved values and percentages only for exactly one complete arm of each kind with the same case/model/effort. Missing, duplicate, inconsistent and mismatched evidence is excluded with a reason. Files: measurement module and tests. | A real matched business-task pair is still needed to produce a project-specific savings result. Raw parent counters do not prove weekly-limit or cost effects. |
| MP-18 | 8 / MP-16, MP-17 | Complete | CLI/installer version 0.3.0, skill workflow, English/Japanese usage, cheat sheet, evaluation protocol, security notes and tests are published. The 86-test local suite, current-rollout schema smoke, CLI help, skill validation, links, privacy/secret scans, managed upgrade, manifest hashes, native discovery and hosted Python 3.10/3.12/3.14 matrix passed. | No release work remains. A matched real-task pair is the next operational measurement, not a missing release artifact. Evidence: [TEST_REPORT.md](../TEST_REPORT.md). |
| MP-19 | 9 / MP-10, MP-12 | Complete | Delegate implementation/repairs promptly; lead owns direction/review/necessary acceptance, with direct implementation only by explicit user direction. Distinguish worker starts, preparation and lead tools. The guidance is published with v0.3.0; canonical and installed host renderings passed validation/discovery. Files: `skill/SKILL.md`, master plan and this roadmap. | No remaining work. |
| MP-23 | 13 / MP-19–22 | Complete | Worker prompt, canonical skill, English/Japanese README and security guidance implement operation-level stopping, lead diagnosis, bounded recovery and explicit dependency preparation. Independent 59-test verification, post-apply first-run/retry regression, 20 managed payload/hash/mode comparisons and the hosted Python matrix passed. [PR #1](https://github.com/JizaiStyle/swe-sidekick/pull/1) merged on 2026-09-18. | No remaining skill-release work. Recovery of application tasks requires its own new evidence; no earlier failed attempt is accepted by this release. Validation: [TEST_REPORT.md](../TEST_REPORT.md#bounded-failure-recovery-mp-23-2026-09-18). |

| MP-20 | 10 / MP-10 | Complete | Command-scoped gc.auto=0 and maintenance.auto=false prevent deferred Git mutation. SWE-2 High changed CLI helper and two focused tests. Exact metadata tamper checks remain unchanged. The fix is published and installed. | The 58-test local suite, large-repository prepare/clean inspection, deliberate info/refs rejection, two focused post-apply regressions and hosted three-version suite passed. Evidence: [TEST_REPORT.md](../TEST_REPORT.md). |

| MP-21 | 11 / MP-19, MP-12 | Complete | Clarified authorization continuity, task-specific worker selection, resumption and actor-labelled updates. Files: `skill/SKILL.md`, master plan and this roadmap. The guidance is published; managed Codex and Devin copies are updated. | Canonical and installed Codex skill validation, diff whitespace check and all managed payload byte comparisons passed. No runtime change or paid worker run. |

| MP-22 | 12 / MP-20, MP-21 | Complete | Preserved the existing plan, runtime-fix and guidance commits and published them through the public `main`. Version remains 0.3.0 under the installer's tested same-version refresh path because there is no tagged/package release. | Changed-boundary tests, skill validation, links, privacy/secret scans, managed installation hashes, hosted CI and remote verification passed. No remaining release work. |

## Validation record

2026-09-15 — MP-20–22 publication: commits `957006c`, `10429c2` and `a993e7f` were pushed without rewriting history. GitHub Actions run [34957708680](https://github.com/JizaiStyle/swe-sidekick/actions/runs/34957708680) passed the complete suite on Python 3.10, 3.12 and 3.14. Gitleaks scanned all nine pre-evidence commits without findings. The managed 0.3.0 installation was refreshed with a backup; its manifest and rendered skill payloads matched the reviewed source. This final evidence update changes only `TEST_REPORT.md` and this roadmap.

2026-09-15 — MP-22 started after the user asked for the optimal handling of the unpublished repository state. The release will preserve the two existing commits and commit MP-21 separately. A 0.3.1 installer migration was rejected as unnecessary scope: the project has no tag or packaged release and already tests backed-up same-version upgrades. This decision changes publication status only; MP-20 behavior and MP-21 guidance remain unchanged.

2026-09-15 — MP-21: reviewed continuation, model-selection and external-action boundaries against existing delegation rules. The default Python lacked PyYAML; the cached offline uv environment validated canonical and installed Codex skills successfully. Managed upgrade completed with backup, and every installed payload matched its canonical rendering. This was lead-owned skill documentation work; no SWE run, application change or deployment was performed.

2026-09-15 — MP-10–13 requirements, ownership, dependencies, safety boundaries, and completion conditions were added before implementation. No implementation, installation, model execution, repository publication, or remote mutation is claimed by this entry.

2026-09-15 — MP-10/12: host-specific invocation metadata is rendered separately because Devin uses `triggers: [user]` while the canonical Codex skill validator rejects that extension. Both hosts must preserve explicit-only invocation. This adds one managed Devin skill file and changes no global model settings. MP-13: release integration is in progress; publication is still pending.

2026-09-15 — MP-10/12 correction from native discovery: placing both a shared `.agents` skill and a Devin-specific skill causes Devin to namespace them as `agents:swe-sidekick` and `devin:swe-sidekick`, with implicit invocation still enabled on the shared copy. The release therefore uses `.codex/skills` for Codex and `.config/devin/skills` for Devin. Upgrade must back up and remove only the old managed shared skill files, restoring them on failure. This supersedes the initial shared-directory design; global model configuration and existing tasks remain outside the change.

2026-09-15 — MP-10–12 implementation, offline validation and native installation/discovery completed. The final suite passed 76 tests in 52.923 seconds. MP-13 publication remains pending; detailed evidence and validation limits are in [TEST_REPORT.md](../TEST_REPORT.md).

2026-09-15 — MP-13 publication completed. GitHub API confirmed public visibility and `main` at the initial reviewed release commit `68024d1e02e70749bad26fe2c32da4c485e4121c`. Gitleaks scanned that fresh Git history with no findings. Publication used a contributor label and GitHub noreply address, without importing private repository history. The release evidence documentation is maintained in subsequent commits; source and test results are unchanged.

2026-09-15 — MP-13 hosted verification completed: the initial GitHub Actions run passed its Ubuntu Python 3.10, 3.12 and 3.14 matrix. The final evidence-only documentation update does not repeat the unchanged test suite. Native discovery, the full local test suite and public CI are all verified; live model execution remains outside scope.

2026-09-15 — MP-14: English public documentation and examples completed. Japanese remains only in the labelled alternative README and its language link. This documentation/metadata update uses focused validation; the previous runtime suite was not rerun.

2026-09-15 — MP-15: added the operator cheat sheet after checking the canonical skill, worker launch arguments and installed Devin CLI help. Verified relative links in all six changed documents, eight CLI command/flag interfaces using `--help`, English-only cheat sheet content, absence of private filesystem paths and whitespace integrity. An initial strict ASCII check rejected typographic ellipses; they were normalized and the focused checks passed. Full runtime tests and model inference were not run for this documentation-only change. `/effort` support is explicitly host-dependent rather than asserted universally.

2026-09-15 — MP-16–18 planned after operational review showed that the v0.2
report measured worker time and outcomes but had no recorded parent tokens in
14 included tasks. Read-only inspection confirmed that Codex rollout records
contain the required counters and model/effort metadata, and that environment
session IDs can bind the invoking host to the correct rollout. The new design
uses explicit local measurement arms so an observed token count is not
mislabelled as a counterfactual reduction. Official OpenAI API documentation
confirms response usage exposes input/output totals and cached-input details;
it does not establish how a ChatGPT/Codex weekly subscription limit maps to
these local counters, so that conversion remains outside scope.

2026-09-15 — MP-19 completed locally. Canonical skill and managed Codex/Devin renderings now prioritize SWE implementation over lead-written fixes. A private stable installer snapshot retained existing application payloads to avoid deploying in-progress measurement code. Ownership manifest and byte comparisons passed; no legacy shared-skill duplicate exists. The skill validator initially lacked PyYAML in the selected interpreter; an isolated uv environment supplied it and validation passed. No CLI behavior or global model setting changed, and no paid model was invoked for this skill validation.

2026-09-15 — MP-16–18 implementation validation: the final offline suite passed
86 tests in 41.949 seconds. A content-free live schema smoke exercised start,
stop and reporting against the current invoking Codex rollout, then removed its
temporary state. CLI/report output contained no session/thread/root-turn IDs,
rollout positions or cumulative baseline. The skill validator, CLI help,
relative-link scan, privacy scan and installer upgrade preview passed. No
SWE-2, Fable or additional paid Codex inference was started for validation.

2026-09-15 — MP-18 local installation: the managed 0.2.0 installation upgraded
to 0.3.0 with a backup. All 20 manifest hashes matched, including the new
measurement module and installed cheat sheet. Forced Codex discovery returned
one enabled skill without errors; Devin returned one user-triggered skill
without warnings/errors. Global model settings and existing task data were not
changed. At that point publication was the only unfinished release step.

2026-09-15 — MP-18/19 publication: the reviewed v0.3 runtime commit
`21f84c49b214c309b2a1b5e9122825ca4031cc20` was pushed to the public `main`.
GitHub Actions run
[34928507570](https://github.com/JizaiStyle/swe-sidekick/actions/runs/34928507570)
passed the 86-test suite on Python 3.10, 3.12 and 3.14. The final documentation
update records release evidence only; runtime, installer and tests are unchanged.

2026-09-15 — MP-20 completed locally. Initial worker investigation produced no patch after an optional PATH-shim experiment was denied; that operation was not retried. A bounded source/test-only retry completed with matching SWE-2 High export. Both turns were retained (271.375s and 277.916s). Independent wrapper verification passed 58 tests; real large-repository preparation preserved clean source and unexpected Git metadata remained rejected. Two affected regressions passed after apply. Managed installation changed only the CLI and plan payloads; model settings and task-state protections were preserved. No public release was made for this fix.
