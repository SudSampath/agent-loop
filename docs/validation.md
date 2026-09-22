# Validation record — 2026-09-22

Validated on macOS with Python standard-library unittest, using temporary homes and stub agent/optimizer executables. Ten Given/When/Then checks cover repeated installation, preservation/backups, dry-run behavior, conflicting skills, paths containing spaces, argument and Orca environment forwarding, runtime-home instructions/skills, help without mutations, additive hooks, wrapping arguments, malformed configuration, doctor output, and hook rewrite/pass-through behavior.

These tests do not authenticate providers, spend tokens, start Headroom, install a login service, or edit the active Mac's harness. The source Mac runbook records successful live Claude/Codex proxy sessions on 2026-09-21; that is evidence for the original integration, not an end-to-end test of this new installer.

Before calling another computer ready, complete the live smoke checks in setup.md: correct account, loaded instructions and skills, intended vault, actual tool call, proxy routing if enabled, and a read check for each connected service.

## Native Windows implementation

Added a PowerShell installer and launchers, Windows file locking, UTF-8 files, native executable and PowerShell shim dispatch, and a Windows setup guide. The expanded 16-test suite includes real PowerShell execution on the development Mac for argument/exit-code forwarding, shim dispatch, and installer previews, plus a two-process lock test. The Windows-only optimizer rejection test is skipped on macOS; three POSIX optimizer tests are skipped on Windows. GitHub Actions runs the suite on windows-latest, macos-latest, and ubuntu-latest. Check the [latest CI run](https://github.com/SudSampath/sudarshans-agent-loop/actions/workflows/test.yml) for the tested commit and result.

Native Windows model authentication, interactive TUI behavior, and Orca desktop integration still require a real user smoke check. CI uses synthetic executable/script fixtures and no provider credentials. WSL2 is not a separate CI target. Native Windows optimizer hooks are deliberately rejected until that integration is validated.
