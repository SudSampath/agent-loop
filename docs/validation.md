# Validation record — 2026-09-22

Validated on macOS with Python standard-library unittest, using temporary homes and stub agent/optimizer executables. Ten Given/When/Then checks cover repeated installation, preservation/backups, dry-run behavior, conflicting skills, paths containing spaces, argument and Orca environment forwarding, runtime-home instructions/skills, help without mutations, additive hooks, wrapping arguments, malformed configuration, doctor output, and hook rewrite/pass-through behavior.

These tests do not authenticate providers, spend tokens, start Headroom, install a login service, or edit the active Mac's harness. The source Mac runbook records successful live Claude/Codex proxy sessions on 2026-09-21; that is evidence for the original integration, not an end-to-end test of this new installer.

Before calling another computer ready, complete the live smoke checks in setup.md: correct account, loaded instructions and skills, intended vault, actual tool call, proxy routing if enabled, and a read check for each connected service. Linux and WSL2 have not been exercised on a real target in this task.
