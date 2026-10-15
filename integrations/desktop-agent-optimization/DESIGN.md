# Evidence and design boundaries

The integration separates configured controls, isolated backend proof, actual native workflow proof, and boot proof. Installed hooks or MCP tools alone do not establish execution or inference routing.

## Native adapter

The adapter changes only the built-in provider's `openai_base_url`, preserving its authentication behavior. It writes a private backup and transaction state before atomically applying a managed TOML block. Conflicting provider settings, symlinks, changed managed blocks, and concurrent edits stop the mutation. Removing the exact managed block preserves later unrelated settings. Tests cover interrupted transaction recovery and idempotent operations.

Native transport verification uses process executable ancestry and native backend TCP peers, then matches allowlisted Headroom HTTP or WebSocket ingress metadata. The same bundled binary under an unrelated launcher does not qualify as native app execution. Evidence includes request fingerprints rather than headers, credentials, raw prompts, or connection IDs.

WebSocket ingress uses connection request IDs while Headroom 0.37.0 outcome stats use separate `hr_*` request IDs. Public request-stat rows do not expose this join, so the observer cannot attribute shared-proxy token savings to the native fixture. A correct fixture marker verifies fidelity, not savings. Authentication renewal, full UI streaming/continuation, attachments, cancellation, app updates, boot behavior, and outage fallback need additional validation.

## Isolated mock probe

Headroom routes ChatGPT account authentication to a separate ChatGPT target; overriding the ordinary OpenAI target alone does not redirect it. The fixture launcher redirects both targets in memory. It uses synthetic credentials and a generated prompt, never real authentication stores.

The upstream Headroom CLI may re-execute itself to set thread environment variables, discarding process-local guards. The runner uses an embedding entry point to avoid that re-execution. Python socket guards alone are insufficient for native uvloop connections, so HTTPX is also guarded above transport. Offline pricing/model metadata avoids startup network fetches. An attestation endpoint precedes Headroom's catch-all route and verifies that an external HTTPX destination is rejected and the serving PID matches before the fixture turn is sent.

The guarded run returned the expected local reply and preserved synthetic bearer/account headers. Its small structural reduction is a plumbing result, not a cost/quality benchmark. Treat missing guard attestation as a failure; do not replace the launcher with an unguarded `headroom proxy` invocation.

## Other surfaces

Claude Code desktop documents separate third-party inference controls; CLI environment variables alone do not prove desktop gateway routing. Cowork and chat can execute remotely. Verify the selected account/mode and current supported controls before claiming coverage. A localhost optimizer on the Mac does not cover a cloud runtime.

References: [Codex hooks](https://learn.chatgpt.com/docs/hooks), [gateway compatibility](https://learn.chatgpt.com/docs/enterprise/gateway-compatibility), [Claude desktop gateway controls](https://code.claude.com/docs/en/llm-gateway-connect#desktop-app), and [Cowork execution boundaries](https://support.claude.com/en/articles/15520349-use-claude-cowork-on-web-desktop-and-mobile).
