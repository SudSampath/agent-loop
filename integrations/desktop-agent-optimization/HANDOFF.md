# Continuation for Claude or Codex

Scope: continue the experimental native desktop optimizer adapter in this directory. Read root AGENTS.md, README.md, docs/design.md, then this directory's README.md and DESIGN.md. Inspect Git status and preserve simultaneous work; use a separate branch/worktree for overlapping edits.

Implemented: reversible native Codex base-URL routing, isolated backend/preflight probes, guarded Headroom mock transport, a synthetic native RTK fsmonitor fixture, generated inference output, current startup-readiness audit, and native HTTP/WebSocket evidence correlation. The portable bootstrap installer is unchanged.

Validation: 31 standalone Given/When/Then tests pass. A manual local Codex workflow returned the expected fixture marker, and a native backend peer matched a Headroom Responses WebSocket connection. RTK ancestry was separately observed in an unprefixed native Git command. ChatGPT sign-in was retained for the observed workflow. Private machine evidence lives outside this public repo.

Unfinished: per-native-session optimization attribution, authentication renewal, broader streaming/tool continuation/attachment/cancellation behavior, native Claude/Code/Cowork/chat compatibility, startup races, app-update behavior, and automatic outage fallback. Current readiness does not prove boot coverage. Boot verification is deferred; do not reboot, schedule it, or restart shared services unless the user explicitly resumes that work.

Exact next action: run the standalone tests, inspect the existing transport observer and Headroom's supported stats, then implement the smallest supported way to correlate actual native inference outcomes with optimization metrics. Preserve streaming, WebSockets, tool identifiers, and ChatGPT authentication; shared savings counters cannot establish fixture savings. If current stats cannot expose that join, document the limitation before adding a second proxy or modifying upstream packages.

Keep subsequent fixes focused and testable with synthetic fixtures. Live enable/disable commands change the current user's settings; use temporary homes in tests and preserve private backups. Do not infer remote execution coverage from host-local installation. Consult current official product documentation when controls have changed.

Checks from this directory: `python3 -m unittest discover -s tests -v`. From repository root, run the root test suite as specified in AGENTS.md. Optional backend/preflight probes need the installed app; the mock probe needs its guarded Headroom environment. No paid provider calls belong in automated validation.

The current publication includes code and portable documentation only. It grants no blanket authorization to commit or push future changes; follow the user's active task instructions.
