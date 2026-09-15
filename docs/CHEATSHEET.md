# SWE Sidekick cheat sheet

The **lead** is the host session where you invoke the skill. The **worker** is
the separate SWE-2 process launched by Sidekick. Their settings are independent.

## Model and effort

| Setting | Where to change it | Effect |
| --- | --- | --- |
| Lead model | Your host's model selector; `/model` where supported | Sidekick keeps the model selected by the host. |
| Lead effort | Your host's reasoning selector; `/effort` only where supported | Sidekick keeps the host-selected effort; it does not impose `high`. |
| Worker model and effort | `swe-sidekick configure --model 'EXACT_SWE2_CATALOG_VALUE' --acknowledge-usage` | Selects the separate SWE-2 worker, including its effort-specific catalog variant. |

Changing the lead's effort does **not** change the worker's effort. For example,
a host-selected Fable lead at medium effort can use a configured SWE-2 High
worker, if those options are available in the respective catalogs. This is a
configuration example, not a claim that those models ran or were benchmarked.

Slash commands and effort options vary by host, version and model. Check the
host's help and active setting display; `/effort` is not a universal command.
In Devin, select an exact solo model with `/model` or
`devin --model MODEL_ID`. Where effort is part of a catalog entry, choose the
desired variant. Do not select a native Fusion composite for this workflow.
Sidekick has no flag to change the lead model or effort.

## Start a task

1. Open the intended project in Codex or Devin and select the lead model/effort.
2. Invoke `$swe-sidekick` in Codex, or `/swe-sidekick` in Devin.
3. Give the lead a bounded objective, allowed files and testable acceptance
   criteria. The source repository must be trusted and clean before preparation.

Example instruction after invoking the skill:

> Keep this session's selected model and effort as the lead. Use the configured
> SWE-2 worker to implement the following bounded task. Independently review and
> verify its patch before applying it. Objective: ... Allowed files: ... Acceptance
> criteria: ...

Check worker availability before configuring it:

```sh
swe-sidekick doctor
swe-sidekick configure --model 'SWE-2 High' --acknowledge-usage
```

Use the example model name only if `doctor` lists it; otherwise use an exact
listed SWE-2 name or ID. `doctor` does not run a model. Configuration stores the
worker selection and usage acknowledgement; `run` and `retry` invoke the worker
and can consume quota or credits. Changing worker configuration is separate from
switching the lead; keep it stable during a task or comparison trial.

If the shell cannot find `swe-sidekick`, use `~/.local/bin/swe-sidekick`.

## Measure Codex parent tokens

Use the same non-sensitive case key for one lead-only arm and one Sidekick arm.
Keep the starting revision, task requirements, acceptance method, lead model
and lead effort fixed.

| Action | Command |
| --- | --- |
| Start lead-only arm | `swe-sidekick measure-start --case CASE --arm lead-only` |
| Start Sidekick arm | `swe-sidekick measure-start --case CASE --arm sidekick` |
| Stop either arm | `swe-sidekick measure-stop --trial TRIAL_ID` |
| Compare the pair | `swe-sidekick measurement-report --case CASE` |

Start before planning and stop after the last acceptance action. The stop
snapshot excludes later content. The report shows observed parent input,
cached-input, cache-write-input, output, reasoning-output and total counts plus
absolute and percentage differences. A pair requires exactly one completed arm
of each kind with matching model and effort. It does not include worker tokens
or convert raw counters to subscription quota, weekly limits or cost.

## CLI reference

Replace uppercase placeholders with actual local values. Keep packet, feedback
and handoff files outside the source repository. These are workflow steps, not
a script to execute without the intervening review.

| Action | Command | Required boundary |
| --- | --- | --- |
| Prepare | `swe-sidekick prepare --repo /path/to/repo --packet /private/path/packet.json --trust-repo` | Review repository instructions and the packet first; save the returned task ID. |
| Run worker | `swe-sidekick run --task TASK_ID` | Explicitly authorize delegation and service usage. |
| Inspect | `swe-sidekick inspect --task TASK_ID` | Independently review the actual diff, scope, acceptance criteria and tests. |
| Verify | `swe-sidekick verify --task TASK_ID` | Review the verification commands before executing project code. |
| Apply | `swe-sidekick apply --task TASK_ID --reviewed-sha256 REVIEWED_PATCH_SHA256` | Use the current independently reviewed hash and successful verification. |
| Request a correction | `swe-sidekick retry --task TASK_ID --feedback-file /private/path/feedback.txt` | Review the failure and give bounded feedback; the total turn limit still applies. |
| Export handoff | `swe-sidekick handoff --task TASK_ID` | Finish active work first; keep the JSON private. |
| Start token trial | `swe-sidekick measure-start --case CASE --arm {lead-only,sidekick}` | Codex host only; run before planning and keep the case key non-sensitive. |
| Stop token trial | `swe-sidekick measure-stop --trial TRIAL_ID` | Use the generated ID in the same Codex session after acceptance. |
| Compare token pair | `swe-sidekick measurement-report --case CASE` | Requires one matched completed arm of each kind; raw parent counters are not quota or cost. |

If exact worker model/effort metadata is unverified, apply requires an additional
explicit acknowledgement after checking Devin session statistics. Do not add it
as a routine bypass. See the [skill](../skill/SKILL.md) for the complete gates.

## Switch the lead

- **New independent task:** select the desired model in the intended host and
  invoke its skill. No handoff is needed.
- **Same task, another host:** finish active work, export the handoff, open the
  same project in the destination host, select its lead, invoke the skill, and
  provide the JSON and continuation objective. The new lead checks the current
  workspace, patch hash and verification before continuing.
- **Another available model inside Devin:** use Devin's native model selector.
  This does not turn a Codex application conversation into a Devin conversation.

Use one active lead per task. Handoff retains task facts; it does not automatically
transfer chat history, model context or caches, resume a worker, or reset its retry
budget. Continuation must stay within the original objective and allowed files.
A new scope needs a new task prepared from a clean committed source.

For a legacy prepared task whose lock is missing, handoff refuses to create it.
Explicitly run `inspect --task TASK_ID` to initialize that lock, then retry
handoff. See [host selection and handoff](HOSTS.md) for state-specific limits.

No model inference was used to validate this reference. It documents local CLI
and skill behavior. A real matched pair is still required to establish token
savings for a task, and the result does not establish provider quota effects.
