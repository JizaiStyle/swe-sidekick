# Security boundary / 安全性の範囲

This is an un-audited, single-user prototype for trusted repositories, not a containment system for hostile code.

## Implemented controls

- No credential reading/copying/symlinking by the wrapper. Official Devin CLI uses its existing login store.
- Environment allowlist does not forward API tokens, SSH agent sockets, provider selection overrides or interpreter injection variables.
- Explicit SWE-2 catalog name/ID and current Devin CLI version are selected at configuration; no automatic model/provider fallback.
- Mandatory `--sandbox` with the documented [Autonomous permission mode](https://docs.devin.ai/cli/reference/permissions#autonomous-mode); no dangerous/bypass retry. Additional per-run permissions deny MCP calls, common Git mutations, nested agent commands and some credential/source paths.
- Independent scratch Git repository, no source Git history/remotes/index sharing. Source remains untouched by wrapper until explicit apply.
- Clean source required. Agent configuration directories are omitted from the snapshot; AGENTS.md retained. No untracked/ignored dependency or .env copying.
- Packet validation, strict relative scope, protected paths, rejection of symlinks/submodules/LFS pointers and conservative size caps.
- Bracketed filenames may be included as read-only snapshot inputs; edits to them remain outside the supported writable scope.
- Post-run scope/HEAD/refs/logical-index/config/hooks checks. No automatic reset/revert.
- Per-task advisory lock; explicit session-ID resume; default three-turn cap and 15-minute per-turn timeout; process-group cleanup.
- Verification tied to the exact patch; explicit reviewed SHA-256 and current source HEAD/clean check before apply. Patch regenerated, not trusted from a saved file.
- Logs/state live outside the workspace with owner-oriented permissions; no external log upload by this wrapper.

## Not guaranteed

ACP is not used. The current wrapper does not reimplement or verify Devin's OS sandbox; that is the official CLI's responsibility. Its sandbox is research preview and its network filtering is documented as unstable. A successful help/doctor check is not an operational sandbox test.

HOME remains the real user's home for official login. Global Devin hooks, plugins, MCP-server startup and enterprise policies may still affect execution. `read_config_from=false` and MCP-tool deny rules are not a guarantee that every global integration is disabled or no hook executes. Review your installed integrations before any real run.

The independent snapshot isolates normal working-tree/Git operations, not an adversarial process that can access the host. Same-user malicious processes may tamper with task state. Do not run untrusted repositories or store production secrets in the test environment.

Test scripts run by `verify` are arbitrary project code under the caller's inherited permissions; the wrapper adds no OS sandbox to that step. Execute only reviewed commands from trusted code, preferably under Codex's own sandbox/approval controls. Shell-free argv invocation does not make the target program harmless.

Git scope checks are after-the-fact. They cannot detect all read access, network effects, detached processes, temporary Git mutations restored before the check, ignored artifacts or semantic scope violations. Not all credential patterns are scanned. The source should not be edited concurrently by other applications during apply. The per-task lock does not lock every other program accessing the source.

A command deny list is defense-in-depth, not proof that equivalent actions cannot be performed via another executable. This wrapper is not suitable for multi-tenant execution, production deployment automation, payment/credential administration or operating hostile code.

The model export is checked conservatively, but server-side model routing and billing can differ. Metadata comparison is not a pricing guarantee. A timeout/turn count is not a dollar cap or a guarantee that remote inference stops immediately. No automatic cleanup of logs or provider-side stored sessions is performed.

Raw prompts, logs, trajectories, diffs and verification outputs can include private source or sensitive data. Do not publish them automatically. The simple error-message redactor is not a comprehensive DLP system. Keep the state directory private, inspect content before sharing, and remove retained sessions/logs according to your policies.

## Validation status

See [TEST_REPORT.md](TEST_REPORT.md) for this release's checks. Offline fixtures cover control flow and Git guards; they do not establish live model compatibility, sandbox containment or billing. No security certification or performance guarantee is made.

The read-only handoff snapshot includes task metadata, source/workspace paths, the task packet and verification details. Treat it as private local data. Changing the lead host does not redact that data or transfer conversation history, authentication, model context or caches. Use one active lead per task.


## Local evaluation data

Manual evaluation records and summaries are private local observations, not telemetry uploads. They may include timing, usage readings and short reviewer notes; do not copy credentials or full trajectories into them. Unknown costs and lead settings remain null. Worker duration excludes lead planning/review. Vendor-published Fusion results use different tasks and conditions and do not establish relative performance on a private business task.
