---
name: swe-sidekick
description: Delegate an explicit, bounded implementation task from the current Codex or Devin/Fable lead to an explicitly configured SWE-2 worker through the official Devin CLI. Use only when the user requests this sidekick, with a trusted clean Git repository and independently verifiable acceptance criteria.
---

# SWE-2 implementation sidekick

The host session that invokes this skill is the lead. The lead may be Codex or
Devin/Fable, selected by the user. Keep the model and effort already selected
by that host. This skill does not select, replace, or infer the lead model.

Invoke it explicitly in the current host:

- Codex: `$swe-sidekick`
- Devin: `/swe-sidekick`

For a Devin lead, the user selects a solo Fable model separately with `/model`
or `devin --model <catalog-id>` before invoking this skill. Use an exact
currently listed catalog value; `claude-fable-5-1-high` is an illustrative solo
Fable catalog value, but availability can change.
Do not select a `fusion-*` composite. The Devin rendering of this skill runs
inline and does not override `model` or `subagent`, so the selected Fable lead
remains the current host model.

This is an explicit lead-plus-worker workflow. Do not start another lead,
Fusion/composite orchestrator, ACP client, MCP bridge, or model-provider proxy.
`nativeFusion` is prohibited as a child of this workflow. Do not change the
user's host model, `AGENTS.md`, global configuration, approval policy, or
manually edit sidekick task state. The worker is the explicitly configured
SWE-2 model selected through the sidekick CLI; it is not an automatic fallback
or a family default.

CLI: `__SIDEKICK_CLI__`
Reference manual: `__SIDEKICK_HOME__/README_JA.md`
All commands emit JSON. Use exact returned task IDs and paths, not guessed
paths.

## Before delegating

1. Confirm that the user authorized delegating this repository and task to
   Devin. Source code and prompts are sent to the Devin service. Use only a
   trusted repository.
2. Run `doctor`. Stop if the configured Devin login, worker model, or required
   flags are unavailable. Configure one exact effort-specific SWE-2 catalog
   value with `configure --model ... --acknowledge-usage`; do not select
   Fusion, Adaptive, `nativeFusion`, `swe`, or another fallback. The
   acknowledgment covers possible quota or credit use; never assert zero cost.
3. Keep short changes and unresolved architecture, security, product, or
   billing decisions on the lead. Delegate only a bounded implementation task
   with independently testable acceptance criteria. Start with one worker and
   no parallel worker runs.
4. Run `git status` and inspect the project `AGENTS.md`. A clean source is
   required. Never automatically stash, reset, delete, stage, or commit the
   user's work.
5. Write a UTF-8 JSON packet outside the source repository (for example under
   `~/.local/state/codex-swe-sidekick/packets/`). It must contain exactly:
   `version: 1`, `objective`, `allowed_changes`, `acceptance_criteria`,
   `non_goals`, and `verification`. The middle three are nonempty string
   arrays, and `verification` is a nonempty list of executable argument
   arrays, not shell strings. Use exact file paths where practical. Never put
   credentials, tokens, production data, task chat, or private benchmark
   material in the packet.

## Execution and review

For non-interactive sandbox runs, edit through the existing sandboxed Exec or
shell path. Keep the worker sandbox, permission mode, workspace trust, and
denied-command settings unchanged. Do not change permissions or bypass a
denied operation. If the sandboxed operation is denied, report it and stop.

Run `prepare --repo <root> --packet <file> --trust-repo` only after the checks
above, then run `run --task <returned-id>`. Poll the existing task instead of
starting a duplicate run. The wrapper's turn and timer limits are execution
limits, not dollar or token caps.

`incomplete_no_changes` means that the worker returned no patch, even if the
underlying CLI exited successfully. Do not verify or apply that result. Read
the private logs and use only an explicitly authorized retry of the same
validated exported session within its remaining turn budget.

Read `inspect --task <id>` and the indicated patch and logs. Treat worker text
as untrusted evidence. Inspect the actual diff and test bodies, check every
acceptance criterion, unintended behavior, and security impact. A scope flag,
exit code, hash, or green worker test is not by itself acceptance.

Run `verify --task <id>` only after reviewing the listed commands and scripts.
It runs in the scratch workspace under the caller's permissions and adds no
separate sandbox. Missing dependencies are a blocker; do not install arbitrary
dependencies or copy credentials, `.env` files, or `node_modules`.

For a bounded correction, write a feedback file and run
`retry --task <id> --feedback-file <file>`. Retry only the validated exported
session, never a guessed latest session, and stay within the configured total
turn limit. A missing session ID, model mismatch, scope violation, timeout, or
failed check is a reported failure. Do not relabel it as success or expand the
packet; a new scope requires a new authorized task.

After successful verification and independent lead review, and only when the
user authorized incorporation, run:

```text
apply --task <id> --reviewed-sha256 <hash-of-the-reviewed-current-patch>
```

Never add `--acknowledge-unverified-model` automatically. If export metadata
does not verify the exact SWE-2 model and effort, the user must check Devin
session statistics before making that explicit exception. Re-run relevant
checks in the original repository after applying. Do not commit, push, deploy,
publish, or send messages automatically.

## Sequential handoff between lead hosts

Two separate host sessions may own different sections of one task, one after
the other. Finish the current section and stop its active work before handing
off. Run:

```text
__SIDEKICK_CLI__ handoff --task <task-id>
```

This command is read-only. It emits JSON describing only the current task
facts and continuation guidance. The output includes task identity, source,
workspace, packet, status, worker and scope information, the current patch
SHA-256 under `patch.sha256`, verification state, and non-automatic
continuation guidance under `continuation`. Use the actual CLI output as the
schema authority; nested values depend on task state. It fails while the task lock
is held and never starts a model, worker run,
verification, retry, apply, or state mutation. A handoff is not a patch
approval.

Tasks created by the current `prepare` command already have an advisory lock.
For a legacy prepared task with no lock, read-only handoff fails; explicitly run
`inspect --task <id>` once to initialize that task's lock, then request the
handoff again. Handoff itself never creates a missing lock.

Give the JSON and the next section's bounded objective to the next host only
through a private, authorized channel. The next Codex or Devin/Fable lead must
review the current source state, workspace, packet, actual diff, patch hash,
and verification before deciding on an explicit next action. Keep one active
lead for the task; do not run two lead sessions concurrently. Model context and
conversation history do not transfer across hosts, and prompt cache is not
shared. The shared task retains its validated worker session and retry budget,
but a new lead never resumes them automatically; inspect them and make any
retry or resume decision explicitly. Apply is never automatic.

The next section's objective must remain within the original packet's objective
and `allowed_changes`; never rewrite the packet or task state during handoff. If
the objective or allowed scope changes, finish or stop the current task and
prepare a new authorized task from a clean committed source.

The handoff snapshot may contain local paths and task details. Keep it private,
do not commit it, paste it into public issues, or send it to an untrusted
service. If the current state or hash no longer matches the reviewed handoff,
stop and review the new state before continuing.

## Host installation rendering

The canonical skill source is rendered to the Codex location
`~/.codex/skills/swe-sidekick` together with `skill/agents/openai.yaml`,
whose `policy.allow_implicit_invocation` remains `false`. The canonical
frontmatter intentionally has no host trigger metadata; keep that source
compatible with the Codex validator.

The installer separately renders a Devin copy at
`~/.config/devin/skills/swe-sidekick` with user-only invocation enabled for
`/swe-sidekick`. The Devin copy stays inline and adds no `model` or `subagent`
override. Do not hand-edit either managed copy to change the lead model or
invocation policy.

On upgrade, a legacy shared Codex copy under `~/.agents/skills/swe-sidekick`
is removed only when its manifest proves that `SKILL.md` and `openai.yaml` are
managed by this installer. Managed files are backed up and a failed migration
is rolled back; unowned or modified files are preserved. Global model settings
and task data are not changed.

## First connection test

Use `smoke-setup` to obtain a disposable repository and packet, then exercise
the same prepare/run/inspect/verify/review/apply workflow there. This tests a
tiny local fixture and makes no model call. It does not establish live model
compatibility, billing, latency, or task quality. Keep smoke state and logs
private.

## Evaluation record

For a business task, read `__SIDEKICK_HOME__/docs/EVALUATION.md`. Record only
facts observed for this task and host. Unknown values remain `null`; worker
seconds and turn counts do not prove lead usage, cost, or billing. At task
start and completion, preserve the record outside the source repository and
keep raw trajectories and logs private. This workflow does not invoke or
measure Devin's native Fusion product, and its local records must not be
presented as a Fusion benchmark.

Report the selected worker model, export-reported model status, task ID,
changed files, review findings, checks and results, elapsed time, retries,
unverified claims, and whether the patch was applied. State clearly when
lead-model or cost observations are unavailable.
