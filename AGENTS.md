# SWE Sidekick contributor instructions

Use docs/MASTER_PLAN.md for requirements and docs/ROADMAP.md for current progress. Update the relevant requirement and validation evidence before reporting completion.

Support a host-selected Codex or Devin lead and an explicitly configured SWE-2 worker. Never infer or change the lead model. Preserve sandbox, clean-source, explicit session resume, bounded retries, reviewed patch hashes and unknown usage values.

Keep changes within assigned files and preserve other contributors’ work. Tests use fake workers and isolated temporary directories; do not invoke paid models from tests. Do not publish local state, credentials, real task IDs, private filesystem paths or raw logs.
