# Native desktop optimization (experimental)

An opt-in macOS adapter and verification tools for RTK shell filtering and Headroom inference routing in the native Codex/ChatGPT app. The core harness installer does not enable this integration. Python 3.11+ is required for this standalone component; the portable harness core retains its existing requirements.

Manual validation with ChatGPT desktop 26.930.61225, bundled Codex 0.160.1, and Headroom 0.37.0 established native RTK execution and a native Responses WebSocket connection through Headroom with ChatGPT sign-in retained for a synthetic tool workflow. These observations are version-specific. Boot, authentication renewal, broader UI behavior, and attributable native-session savings remain unverified. Automatic proxy-outage fallback is unimplemented.

## Components

- `adapters/codex/routing.py`: readiness-gated, reversible user-level routing with a private backup, edit-conflict protection, and HTTP/WebSocket transport correlation.
- `verification/backend_probe.py` and `native_route_preflight.py`: isolated bundled-backend configuration discovery without credentials or inference.
- `verification/proxy_probe.py`: a synthetic backend → separate Headroom → loopback mock comparison. The test runner guards egress, redirects the separate ChatGPT upstream to the mock in memory, and requires guard attestation before sending a proxied turn.
- `verification/native_probe.py`: a generated Git fixture whose supported fsmonitor callback distinguishes direct Git, RTK, and native-app executable ancestry.
- `verification/native_inference_fixture.py`: generated tool output with a fidelity marker.
- `verification/runtime_inventory.py` and `startup_readiness.py`: allowlisted runtime/configuration metadata and a read-only current-readiness audit.

No credentials, authentication stores, live client configs, machine-specific evidence, private planning records, or vault content belong in this directory. `evidence/` and generated `.probe-workspace/` files are ignored. Keep private local evidence outside shared commits.

## Verify before setup

Run these commands from this directory:

```sh
python3 -m unittest discover -s tests -v
python3 -m verification.native_route_preflight
python3 -m verification.startup_readiness
```

Unit tests use temporary config/state directories and synthetic data. Preflight needs the installed app-bundled Codex binary. Readiness inspection needs the existing macOS Headroom service; it does not start or install one. The expected service endpoint is loopback port 8787. Native probe constants reflect the tested app packaging and need revalidation after updates.

See [design and verification](DESIGN.md) for evidence boundaries, the mock runner's network isolation, and authentication considerations. Review current [official configuration documentation](https://learn.chatgpt.com/docs/config-file/config-reference) and [ChatGPT gateway sign-in](https://learn.chatgpt.com/docs/enterprise/sign-in-with-chatgpt-through-a-gateway) before enabling live routing.

## Opt-in native routing

With an existing healthy Headroom service, the adapter's explicit enable command adds one managed `openai_base_url` block to the current user's Codex configuration. It retains the built-in provider and refuses competing routes/custom-provider overrides. It does not select an API key, change the login service, or alter hooks, trust, model selection, or approvals.

```sh
python3 -m adapters.codex.routing enable
```

The route applies to other Codex clients using that home unless a higher-priority override selects another route. Private backup/state stay under `~/.local/state/desktop-agent-optimization/`. The existing Orca integration and its separate runtime home remain independent.

Reopen the native app and start a fresh local Codex conversation in this directory. Ask it to run `python3 -m verification.native_inference_fixture`, identify record 117's marker, then run:

```sh
python3 -m adapters.codex.routing report --output evidence/native-headroom.json
```

The expected marker is `KEEP-117-FIDELITY`. Inspect both native socket/request correlation and workflow fidelity. A proxy health response, MCP listing, or shared savings counter alone is insufficient. A separate controlling shell can inspect the running native app family with `report --inspect-native-app`; it must preserve the original native report rather than overwrite it.

For the RTK fixture, first run `python3 -m verification.native_probe prepare`, then have the native app execute exactly `git status --short` in `.probe-workspace/native-codex` without adding an RTK prefix. Run `python3 -m verification.native_probe report` and require both native Git and native RTK execution evidence.

## Recovery and limits

If inference fails, remove the managed route and reopen/start a fresh conversation:

```sh
python3 -m adapters.codex.routing disable
```

Rollback works without proxy health and preserves unrelated edits made after enablement. If the managed block itself was edited, it stops for review instead of replacing the whole config. Automatic outage failover remains future work.

An actual first-workflow-after-login test requires an operator-chosen restart. Capture the pre-restart `kernel_boot_time_unix` from readiness inspection, then verify the first native shell/inference workflow after a changed boot time without manually starting optimizers. Current service readiness alone is not boot proof. Do not reboot or restart shared services as part of automated tests.

Local interception does not establish coverage for cloud-owned Codex, Cowork, or chat execution. Claude Code desktop gateway controls differ from CLI environment/settings routing and need separate validation. See [continuation work](HANDOFF.md).
