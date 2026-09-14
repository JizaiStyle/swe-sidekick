# Business evaluation and measurements for a host-selected lead

## Invoke from the target project

The host that invokes SWE Sidekick is the current lead: either Codex or a
user-selected model in Devin, including Fable. The lead handles design, review
and acceptance. The wrapper delegates bounded implementation to an explicitly
configured SWE-2 worker. Select the lead model and reasoning effort in the
current host; do not infer or change them through the wrapper or evaluation
records.

```text
Codex: $swe-sidekick
Devin: /swe-sidekick
```

For a Fable lead in Devin, select an exact, currently available solo Fable
catalog entry through `/model` or `devin --model <catalog-id>` before invoking
`/swe-sidekick`. This selection is separate from the SWE-2 worker configuration.
Do not treat a composite model or automatic routing choice as evidence of this
workflow's configuration or results.

## Recording workflow

1. At the start of a business task, establish acceptance criteria, allowed scope,
   task category and lead host. Record start time and usage readings only when
   observed; do not reconstruct missing timestamps or waiting time from guesses.
2. Follow `prepare → run → inspect → independent lead review → verify → apply
   with the reviewed hash`. Record failure reasons too. `incomplete_no_changes`
   is not successful completion and must not proceed to verification or apply.
3. To change the lead between sections, stop active work before running the
   read-only `handoff --task <task-id>`. Privately give the next host the JSON and
   the next section's objective. The new lead reviews current state, the diff,
   patch hash and verification before explicitly choosing an action. Chat
   history, model context and prompt caches do not transfer across hosts. The
   shared task retains its validated worker session and retry budget, but the
   new lead does not automatically resume or apply. Sections of the same task
   must stay within its immutable packet; a changed objective or scope needs a
   new task, as described in [HOSTS.md](HOSTS.md).
4. At completion, interruption or handback to the lead, save a record outside
   the source repository using the [JSON example](../examples/evaluation-record.json).
   Include only observed values. Use the actual local task ID in `task_id`, but
   do not save the record in a public repository or public log.
5. Record it with `swe-sidekick evaluate --task <task-id> --record <absolute-json-path>`.
   Inspect the existing record before adding `--replace` to correct it.
6. Generate the current local report with `swe-sidekick evaluation-report`.
   `--include-smoke` is for diagnostics; smoke tasks are excluded from business
   results.

The authoritative local records are
`~/.local/state/codex-swe-sidekick/tasks/<task-id>/state.json` and
`evaluation.json`. Generate reports from these records rather than duplicating
manually maintained results in the public tree. Evaluation recording does not
run a task, infer missing values from logs or modify the source project. Treat
raw trajectories, worker logs and handoff snapshots as private local data.

## Fields and interpretation

- Set `schema_version` to 1 and `task_id` to the actual local task ID. Unknown
  values are JSON `null`; use zero only when zero was actually observed.
- `acceptance_met` records the lead's independent review of requirements and
  the actual diff. `independent_tests_passed` records independent verification
  performed by the lead. `post_apply_tests_passed` records verification in the
  source repository after applying. Worker claims, exit codes, scope flags and
  apply alone do not justify setting these fields to true.
- `lead_review_minutes` is the measured time the lead spent reviewing this
  task's diff. `total_minutes` is measured elapsed time from task start to
  completion, interruption or handback. Both apply to either a Codex or
  Devin/Fable lead; neither is derived from worker seconds. For sections led by
  multiple hosts, sum intervals only when all intervals were observed. Leave
  incomplete measurements null and briefly describe their coverage in `notes`.
- Fill `parent_model`, `parent_effort` and `parent_model_evidence` together only
  when confirmed in the current lead host. Intended settings, user preferences,
  previous conversations and fixed model/effort pairings are not evidence.
  Otherwise leave all three null. For tasks spanning hosts, distinguish each
  section's model evidence in `notes` rather than collapsing it into an
  unconfirmed single value.
- `codex_usage_before` and `codex_usage_after` are for directly observed Codex
  host usage. Do not insert Devin/Fable readings into Codex fields. Leave these
  null for Fable unless directly observed equivalent facts satisfy the fields'
  meaning and their scope, units and observation times can be stated.
- `devin_usage_before` and `devin_usage_after` contain only usage displayed and
  directly observed in Devin. Do not infer usage or billing from worker elapsed
  seconds, turns or model output. Unobserved values remain null. For account-wide
  readings that include concurrent work, state the scope in `notes` and do not
  convert them into per-task costs.
- Set `observed_total_cost_usd` only when the total cost of both lead and worker
  for this task was actually confirmed. Describe the display, units and scope
  in `cost_evidence`. Do not infer total cost from Devin-only readings,
  subscription allowances, token counts, free allowances or worker seconds.
- Keep `notes` brief: task category, lead host, acceptance findings,
  failure/handback reasons, measurement coverage and reasons for missing data.
  Do not include credentials, full conversations, personal local paths, actual
  task IDs, raw logs or private benchmark values in free-form notes.

Automatically collected worker duration, selected model, export-reported
metadata and turn counts are separate from lead review time, total elapsed
time and usage. Model exports are evidence, but do not independently establish
provider billing or host settings. Include failed and unevaluated tasks in the
report. Read rates together with their denominators and unevaluated counts.
Means over observed values must include observed and missing counts; entirely
missing measurements are not zero. `rates.accepted` is accepted tasks divided
by executed tasks; `accepted_among_assessed` is a supplementary rate using
assessed tasks as its denominator. Use the final outcome after retries for
acceptance, while retaining earlier failures in `failed_attempts` and `retries`.
Treat interruptions and explicit rejection as failure or unknown, not success.

## Comparison limits

These local measurements are not directly comparable to external results with
different tasks, grading methods, repositories, lead hosts, models, reasoning
effort or billing conditions. Do not describe native Devin Fusion results as
runs of this wrapper, or start Fusion/composite runs or additional paid
experiments merely to fill evaluation gaps. Published results may provide
background, but do not calculate a Fusion win rate, relative speed or savings
percentage from unrelated business acceptance rates, costs or worker duration.

For each business task, briefly report the actual changes, independent tests,
acceptance outcome, remaining issues, confirmed lead settings, worker selection
and export checks, observed review time, total time and usage, total and
unevaluated counts, retry patterns, and the limits of any comparison. Unknown
lead settings, Fable-equivalent readings, usage and costs remain null. A small
set of business examples can help identify suitable tasks; it does not prove
superiority.
