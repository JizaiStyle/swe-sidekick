# SWE Sidekick

An opt-in skill for a **Codex or Devin/Fable lead** to delegate bounded implementation work to **SWE-2**, using the official Devin CLI. The lead keeps planning, review and acceptance. The wrapper creates an isolated Git snapshot, checks scope, verifies changes and requires an explicitly reviewed patch hash before applying.

[Japanese / 日本語](README_JA.md) · [Host selection and handoff](docs/HOSTS.md) · [Security boundary](SECURITY.md) · [Validation](TEST_REPORT.md)

This is a single-user prototype for trusted repositories on macOS/Linux with Python 3.10+, Git, and an installed, authenticated Devin CLI. It is not native Devin Fusion and does not select the lead model. Live model compatibility, latency, quota savings and cost savings are not established by the offline tests.

## Install

```sh
git clone https://github.com/JizaiStyle/swe-sidekick.git
cd swe-sidekick
python3 install.py                  # inspect the installation plan
python3 install.py --apply
```

The installer puts the CLI in `~/.local/bin/swe-sidekick`, versioned code under `~/.local/share/codex-swe-sidekick`, the Codex skill in `~/.codex/skills/swe-sidekick`, and a Devin-specific rendering in `~/.config/devin/skills/swe-sidekick`. Both skill configurations require explicit invocation. Ensure `~/.local/bin` is on your PATH; reopen the host session if needed. Global model settings are not modified.

To upgrade an existing managed installation:

```sh
python3 install.py --upgrade
python3 install.py --upgrade --apply
```

Upgrade refuses modified or unowned files, backs up overwritten managed files and rolls back a failed operation. Previous version files and private task state are retained. `python3 install.py --uninstall --apply` removes the current unchanged managed installation; task state and upgrade backups remain private local data.

## Use

In Codex, explicitly invoke `$swe-sidekick`. In Devin, select the desired Fable model with `/model`, then invoke `/swe-sidekick`. Model names depend on the currently available catalog. The skill keeps the lead model selected in that session.

First inspect available worker settings:

```sh
swe-sidekick doctor
swe-sidekick configure --model 'SWE-2 High' --acknowledge-usage
```

Use the exact effort-specific SWE-2 name or ID returned by `doctor`; the example is valid only if that catalog value is available. Configuration acknowledges service usage. `run` and `retry` send task source and prompts to Devin and can consume your subscription quota or credits.

Give the lead a clean, trusted Git repository and a bounded task with independently testable acceptance criteria. [examples/packet.json](examples/packet.json) shows the packet format. The workflow is:

```text
prepare → run → inspect → independent review → verify → apply reviewed hash
```

No automatic commit, push, deployment, fallback model or unlimited retry is performed. See the [skill](skill/SKILL.md) for the full gates and the [security document](SECURITY.md) before running project code.

## Change the lead between sections

Yes: finish a section in one host, stop active work, and export a local snapshot:

```sh
swe-sidekick handoff --task TASK_ID
```

Open a separate Codex or Devin/Fable session and provide that snapshot and the next section's objective. The next lead reviews the current workspace, patch hash and verification before continuing. Use one active lead per task. This transfers task facts, not chat history, model context or prompt caches. The snapshot can contain private paths and source details; keep it local. See [HOSTS.md](docs/HOSTS.md) for the exact procedure and limits.

Sections within one task must stay inside its original objective and allowed files. A different scope or objective needs a new task prepared from a clean source repository; handoff does not rewrite the existing packet.

If “Codex” means a model offered inside Devin, the user can instead use Devin's native model selector to change between available lead models within that host. This is distinct from handing a task between the Codex and Devin applications.

## Measurements and development

[EVALUATION.md](docs/EVALUATION.md) describes local evaluation records, missing measurements and comparison limits. Unknown token counts, costs or lead settings remain unknown; vendor results are not measurements of this wrapper.

Run offline tests without model inference:

```sh
python3 -m unittest discover -s tests -v
```

Requirements live in [MASTER_PLAN.md](docs/MASTER_PLAN.md); [ROADMAP.md](docs/ROADMAP.md) is the sole current progress record. Update the relevant requirement and validation evidence with each meaningful change. See [AGENTS.md](AGENTS.md) for contributor boundaries. Distributed under the [MIT license](LICENSE).
