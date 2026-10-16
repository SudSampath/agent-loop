# Evidence and design boundaries

The integration separates configured controls, isolated backend proof, actual native workflow proof, and boot proof. Installed hooks or MCP tools alone do not establish execution or inference routing.

## Native adapter

The adapter changes only the built-in provider's `openai_base_url`, preserving its authentication behavior. It writes a private backup and transaction state before atomically applying a managed TOML block. Conflicting provider settings, symlinks, changed managed blocks, and concurrent edits stop the mutation. Removing the exact managed block preserves later unrelated settings. Tests cover interrupted transaction recovery and idempotent operations.

Native transport verification uses process executable ancestry and native backend TCP peers, then matches allowlisted Headroom HTTP or WebSocket ingress metadata. The same bundled binary under an unrelated launcher does not qualify as native app execution. Evidence includes request fingerprints rather than headers, credentials, raw prompts, or connection IDs.

## Optimization attribution

Headroom 0.37.0 logs each inbound WebSocket connection with an `hr_*` request ID. Each turn's request-stat row receives a fresh ID, but its PERF log line keeps the connection's ID. The report joins native connection fingerprints to those PERF lines and to the session-completed and closed events. It keeps token counts, client/cancel frame counts, and an allowlisted termination cause. Transform labels and the encoded savings breakdown are discarded because labels can contain file paths. For the observed native connection, the joined PERF total matched Headroom's own session-end total.

Totals cover the whole connection, so they are not fixture-only savings. Shared `/stats` counters remain unattributable. Native HTTP Responses requests are also unattributable: inbound HTTP log IDs (`inbound-*`) differ from handler outcome IDs. The report follows `RotatingFileHandler` renames from the enable-time inode and flags incomplete log coverage. The join depends on Headroom's log format; revalidate it after upgrades. A correct fixture marker verifies fidelity, not savings.

Full UI streaming, attachments, cancellation from the UI, app updates, and boot behavior need manual validation. The session fields make continuation (`client_frames`, `outcome_records`) and cancellation (`cancel_frames`, `close_cause`) observable during those checks.

## Authentication renewal

Token refresh does not use `openai_base_url`, so the route does not affect proactive renewal. Reactive renewal is at risk. For ChatGPT-authenticated WebSockets, Headroom 0.37.0 accepts the client socket before connecting upstream. If the upstream handshake fails, it retries with the same headers, falls back to HTTP, and sends a non-200 upstream status to the client as a `server_error` event over the open socket. An expired token therefore reaches Codex as a server error rather than an HTTP 401. Bundled Codex 0.160.1 includes a WebSocket-to-HTTP transport fallback, and Headroom's HTTP Responses path has returned upstream 401 statuses to clients. Whether that sequence triggers Codex's refresh is unverified.

Verification needs a synthetic probe: an isolated Codex home with synthetic ChatGPT tokens, `CODEX_REFRESH_TOKEN_URL_OVERRIDE` pointed at a loopback mock, and a guarded Headroom whose mock rejects the first token. The guarded launcher redirects the ChatGPT WebSocket target in memory but does not guard `websockets.connect` above transport. Add and attest that guard, and isolate the Codex process's own egress, before sending any WebSocket probe.

## Outage behavior

The route has no alternate path; while Headroom is unavailable, routed Codex clients using this home cannot reach inference. The service's LaunchAgent KeepAlive restarts an exited proxy, not a hung one. Rollback never contacts the proxy, and `report` degrades to log-only attribution with `proxy_ready` false. Recovery requires reopening the app or starting a fresh conversation, so an automatic configuration edit would likely not rescue an active conversation. Automatic failover is unimplemented and needs a design decision before it changes live settings unattended.

## Isolated mock probe

Headroom routes ChatGPT account authentication to a separate ChatGPT target; overriding the ordinary OpenAI target alone does not redirect it. The fixture launcher redirects both targets in memory. It uses synthetic credentials and a generated prompt, never real authentication stores.

The upstream Headroom CLI may re-execute itself to set thread environment variables, discarding process-local guards. The runner uses an embedding entry point to avoid that re-execution. Python socket guards alone are insufficient for native uvloop connections, so HTTPX is also guarded above transport. Offline pricing/model metadata avoids startup network fetches. An attestation endpoint precedes Headroom's catch-all route and verifies that an external HTTPX destination is rejected and the serving PID matches before the fixture turn is sent.

The guarded run returned the expected local reply and preserved synthetic bearer/account headers. Its small structural reduction is a plumbing result, not a cost/quality benchmark. Treat missing guard attestation as a failure; do not replace the launcher with an unguarded `headroom proxy` invocation.

## Claude desktop and Cowork

Reviewed 2026-10-15 against Claude Desktop 2.42304.0 with bundled Claude Code 2.1.299 and current documentation.

Local Code sessions run on the Mac and read the CLI's settings files. A synthetic Git command in a local Code session ran as Claude.app → bundled runtime → shell → RTK → Git, so the user-level RTK `PreToolUse` hook applies. The probe excludes the same bundled runtime under another parent.

Claude desktop coverage is RTK-only by decision. Headroom inference routing has no supported path while the app is signed in to claude.ai. With a project `.claude/settings.local.json` and then the local environment editor setting `ANTHROPIC_BASE_URL`, sessions completed but started with `ANTHROPIC_BASE_URL=https://api.anthropic.com`, connected directly to Anthropic, and left Headroom's route without requests. The app bundle explains the editor result: the Code-session environment merges the editor's variables first, then the host's signed-in block, which sets `ANTHROPIC_BASE_URL` to the account's API host. Do not set it in `~/.claude/settings.json` either: settings-file values override shell variables for every CLI session, including Orca's wrapped sessions.

The documented desktop inference route is the third-party inference configuration (`inferenceProvider: gateway`, `inferenceGatewayBaseUrl`, and a gateway credential). It was not adopted. Gateway mode authenticates with that credential instead of claude.ai sign-in, and Headroom forwards the client credential, so the upstream needs an Anthropic API key with separate per-token billing. The mode applies to the whole app (Chat, Cowork, and Code) and removes Anthropic cloud environments and Remote Control. Whether it accepts an HTTP loopback base URL is unverified. HTTP inbound log IDs do not join to outcome IDs, so any future gateway route could be attributed per route prefix but not per request.

New Pro/Max Cowork tasks have run in Anthropic's cloud since 2026-10-06, with no local option. Host RTK and Headroom cannot cover them, and Cowork does not read `~/.claude`. Where local Cowork remains, shell commands run in a Linux VM outside host RTK. Chat has no local shell, and its inference uses claude.ai.

## Other surfaces

Cloud-owned Codex execution and remote Claude SSH sessions need coverage in their own runtimes; a gateway at this Mac's localhost is not reachable from an SSH host. Verify the selected account/mode and current supported controls before claiming coverage.

References: [Codex hooks](https://learn.chatgpt.com/docs/hooks), [gateway compatibility](https://learn.chatgpt.com/docs/enterprise/gateway-compatibility), [Claude desktop gateway controls](https://code.claude.com/docs/en/llm-gateway-connect#desktop-app), [third-party gateway](https://claude.com/docs/third-party/claude-desktop/gateway) and [configuration](https://claude.com/docs/third-party/claude-desktop/configuration), [Claude Code desktop](https://code.claude.com/docs/en/desktop), [Cowork architecture](https://support.claude.com/en/articles/14479288-claude-cowork-architecture-overview), and [Cowork execution boundaries](https://support.claude.com/en/articles/15520349-use-claude-cowork-on-web-desktop-and-mobile).
