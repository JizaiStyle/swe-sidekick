# Host selection and section handoff

SWE Sidekick keeps the current lead where the user selected it and delegates
only a bounded implementation task to the explicitly configured SWE-2 worker.
The lead can be a Codex host or a Devin host running a user-selected lead
model, including Fable. The skill does not choose or change that model.

The lead also keeps the effort selected in its host. Use the host's reasoning
control (`/effort` only where supported); command availability varies. Worker
effort is configured independently through an exact SWE-2 catalog value and is
not inherited from the lead. See the [cheat sheet](CHEATSHEET.md) for quick steps.

Invoke the skill explicitly in the host where the lead is running:

| Lead host | Invocation | Lead model selection |
| --- | --- | --- |
| Codex | `$swe-sidekick` | Keep the model and effort already selected in the Codex session. |
| Devin | `/swe-sidekick` | Choose the lead separately with `/model`, or with `devin --model <catalog-id>`. |

For a Devin/Fable lead, choose an exact solo Fable catalog entry before
invoking the skill. `claude-fable-5-1-high` is an illustrative solo choice;
availability is catalog-dependent, so verify the current value in `/model` or
`devin models list` and use that exact value. Do not choose a `fusion-*` composite for this workflow. A Devin
skill copy is inline and does not set `model` or `subagent`, which leaves the
selected lead model in control.

“Codex parent” can describe two different arrangements. A Codex application
host uses `$swe-sidekick`. A Codex-family model selected inside a Devin host is
still running in the Devin host and uses `/swe-sidekick`; its model choice is
controlled by Devin's model selection. Keep these cases distinct in records
and handoff notes. The skill does not assume that a model family name means a
particular host or that a host has a model that is absent from its catalog.

If the Devin CLI supports changing a conversation's model, the user may select
that model with the native `/model` command or the documented
`devin --continue`/`devin --resume` option together with `--model <catalog-id>`.
That is a Devin host operation outside this skill. It does not transfer a
Codex host conversation into Devin or imply that chat history, prompt cache,
worker session, or lead state is shared across hosts.

## Shared worker and gates

The host choice does not change the worker boundary. The lead must authorize
delegation, verify a trusted clean source repository, inspect `AGENTS.md`,
write the exact packet outside the source tree, and select an exact
effort-specific SWE-2 catalog value with `doctor` and `configure`. The normal
sequence remains:

```text
prepare --trust-repo → run → inspect → independent lead review → verify → apply reviewed hash
```

The worker stays sandboxed, uses one explicit bounded task, and cannot choose a
lead model or spawn a child orchestrator. No Fusion/composite, Adaptive, or
`nativeFusion` child is allowed. No automatic model fallback, retry, resume,
apply, commit, push, deployment, or publication is performed. The lead must
review the actual diff, acceptance criteria, test bodies, security impact, and
current patch hash before applying anything.

## Moving between host sessions

Separate host sessions may own separate sections of the same task, but only
sequentially. Finish the active section and stop its lead work before opening
the next host session. While the task is active, do not run two lead sessions
or two worker runs against it.

The current lead exports a read-only handoff with:

```text
swe-sidekick handoff --task <task-id>
```

The command emits one JSON object with the current task facts and continuation
guidance. The following is a realistic shape excerpt from the CLI; it is not a
complete or fixed schema, and placeholder values keep private data out of the
documentation:

```json
{
  "task_id": "<task-id>",
  "task_path": "<private-task-path>",
  "source": {
    "path": "<trusted-source-path>",
    "commit": "<source-commit>"
  },
  "workspace": {
    "path": "<isolated-workspace-path>"
  },
  "packet": {
    "objective": "<bounded-objective>",
    "allowed_changes": ["<repo-relative-path>"],
    "acceptance_criteria": ["<independent-criterion>"],
    "non_goals": ["<excluded-change>"],
    "verification": [["<executable>", "<argument>"]]
  },
  "status": "<current-status>",
  "worker": {
    "session_id": "<private-worker-session-or-null>"
  },
  "scope": {
    "ok": true,
    "changed_files": ["<repo-relative-path>"]
  },
  "patch": {
    "sha256": "<current-patch-sha256>"
  },
  "verification": null,
  "continuation": {
    "automatic": false,
    "requires_new_lead_session": true,
    "next": "<non-automatic-next-step>"
  },
  "parent_model": null,
  "sharing": {
    "private": true,
    "conversation_history_transferred": false,
    "model_context_transferred": false,
    "prompt_cache_transferred": false
  }
}
```

Values and omitted fields in the excerpt are placeholders. The command does
not start a model, worker run, verification, retry, or apply, and does not
mutate task state. It fails while the task lock is held. Tasks from the current
`prepare` command have that lock already; a legacy prepared task without one
must first be explicitly inspected with `inspect --task <task-id>` so the lock
can be initialized, after which handoff can be retried. A successful handoff is
an evidence snapshot, not approval to continue or apply a patch.

The next lead receives the snapshot and a new bounded objective through a
private, authorized channel. Before any action, that lead reviews the current
source state, packet, workspace, actual diff, patch hash, status, and
verification. If the state or hash changed after the snapshot, stop and review
the new state. A new lead does not inherit the previous lead's model context,
chat history, or prompt cache. The shared task retains its validated worker
session and retry budget, but the new lead must inspect them and explicitly
decide whether a valid retry or resume is allowed; nothing resumes
automatically. Any application must be an explicit action that passes the same
gates. The next section's objective must remain inside the original packet's
objective and `allowed_changes`; do not rewrite the packet or task state. If the
objective or allowed scope changes, finish or stop the current task and prepare
a new authorized task from a clean committed source.

The snapshot can contain local paths and task details. Keep it outside the
repository and private; do not commit it, paste it into a public issue, or send
it to an untrusted service. Do not put a real task ID, local personal path, raw
trajectory, credential, or private benchmark measurement in public examples or
documentation.

## Installed skill copies

The installer renders the canonical source into the Codex skill path
`~/.codex/skills/swe-sidekick` and keeps
`skill/agents/openai.yaml`'s `policy.allow_implicit_invocation` set to
`false`. The canonical skill source deliberately has no `triggers` field;
adding one would fail Codex validation.

It separately renders a Devin copy into
`~/.config/devin/skills/swe-sidekick`, adding `triggers: [user]` so Devin only
invokes the skill when the user asks for `/swe-sidekick`. That copy remains
inline and has no `model` or `subagent` override. The installer does not change
global host settings or existing task state.

During an upgrade, the installer may remove the legacy shared Codex copy under
`~/.agents/skills/swe-sidekick` only when the existing manifest proves that its
`SKILL.md` and `openai.yaml` are installer-owned. It backs up the managed files
and rolls back a failed migration; unowned or modified files are left in place.
Global model configuration and task data are not changed.

These paths are standard host locations, not handoff payloads. Keep generated
copies managed by the installer and select the lead model in the active host.

## Official Devin references

The Devin host rendering follows the official skill format and invocation
rules documented in [Skills Overview](https://docs.devin.ai/cli/extensibility/skills/overview)
and [Creating Skills](https://docs.devin.ai/cli/extensibility/skills/creating-skills).
Those documents describe user triggers, inline skill prompts, model overrides,
and subagent behavior. SWE Sidekick intentionally leaves model and subagent
unset in the Devin copy so the active host selection remains authoritative.
