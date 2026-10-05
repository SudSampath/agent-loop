# Native Windows setup

Use Windows and PowerShell directly. WSL is not required for the shared instructions, seven skills, launchers, vault integration, backups, or doctor checks. The Headroom/RTK hook layer is currently available through macOS/Linux/WSL2 only; `--optimizers` on native Windows stops before writing files.

## Install prerequisites once

Use PowerShell 7.4 or newer (`pwsh`), Python 3.10+, Git, GitHub CLI, Codex CLI, and Claude Code. If using WinGet:

```powershell
winget install --id Microsoft.PowerShell --exact
winget install --id Python.Python.3.12 --exact
winget install --id Git.Git --exact
winget install --id GitHub.cli --exact
winget install --id Anthropic.ClaudeCode --exact
```

Install Codex using the current [official CLI installer](https://learn.chatgpt.com/docs/codex/cli). An existing npm installation also works when its `codex.ps1` shim and Node executable are on PATH. Native `.exe` installs are the simplest route. Claude's [official Windows guidance](https://code.claude.com/docs/en/setup#set-up-on-windows) covers native installation and Git for Windows.

Open a new PowerShell 7 terminal after installation. Verify:

```powershell
$PSVersionTable.PSVersion
python --version
git --version
gh --version
codex --version
claude --version
```

If `python` opens the Microsoft Store, select the installed interpreter explicitly using `-Python 'C:\path\to\python.exe'` when running install.ps1. Do not pass a multiword command such as `py -3` as the Python path. Scripts run under your existing execution policy; the installer does not change it or bypass organization policy. If execution is blocked, follow your organization's approved PowerShell policy. On a personal machine, review `Get-ExecutionPolicy -List` and use an appropriate user policy such as RemoteSigned if desired.

## Clone and install

Run from a normal PowerShell terminal, outside an existing managed agent session:

```powershell
gh auth login
gh repo clone SudSampath/agent-loop
Set-Location agent-loop
New-Item -ItemType Directory -Force "$HOME\Projects" | Out-Null
.\install.ps1 -Workspace "$HOME\Projects" -DryRun
.\install.ps1 -Workspace "$HOME\Projects"
$env:PATH = "$HOME\.local\bin;$env:PATH"
python .\bootstrap.py doctor
```

For Obsidian, finish syncing first, then rerun with `-Vault "C:\Users\YourName\Documents\My Knowledge"`. INDEX.md must exist. Specify all desired options each time; omitted Vault clears the configured vault. No credentials or vault files are copied into this repository.

The default destinations are `$HOME\.codex\AGENTS.md`, `$HOME\.claude\CLAUDE.md`, each client's skills directory, and `$HOME\.local\bin\agent-loop-{codex,claude}.ps1`. Existing CODEX_HOME and CLAUDE_CONFIG_DIR values take precedence unless you pass `-CodexHome` / `-ClaudeHome`. Existing content outside the managed block is retained. Backups are created before changed files are replaced.

The PATH change above applies only to the current terminal. Add the launcher directory through Windows' user Environment Variables UI to keep it across terminals; this installer does not alter your global PATH or PowerShell profile.

## Launch and verify

```powershell
Set-Location "$HOME\Projects\your-project"
agent-loop-codex.ps1
# Or:
agent-loop-claude.ps1
```

Sign in to the intended account in each client. Ask each agent to report loaded instructions, selected vault, and available skills, then read git status without changing anything. Verify a small synthetic PRD uses the intended skill. `doctor` verifies installation files and executable discovery, not authentication, interactive terminal behavior, or actual model loading.

To invoke from an app that requires an executable, use `pwsh.exe` as the executable with arguments `-NoProfile -File "C:\full\path\agent-loop-codex.ps1"` (or the Claude equivalent). Native Windows Orca UI integration has not been verified; use terminal launchers unless the app supports separate executable/argument fields. Injected CODEX_HOME, CLAUDE_CONFIG_DIR, and ORCA_* values are preserved.

## Separate job or account

```powershell
New-Item -ItemType Directory -Force "$HOME\Work\Projects" | Out-Null
.\install.ps1 -Workspace "$HOME\Work\Projects" -Prefix "$HOME\.local\agent-loop-work" -CodexHome "$HOME\.codex-work" -ClaudeHome "$HOME\.claude-work"
$env:CODEX_HOME = "$HOME\.codex-work"
$env:CLAUDE_CONFIG_DIR = "$HOME\.claude-work"
& "$HOME\.local\agent-loop-work\bin\agent-loop-codex.ps1"
```

Authenticate again in those homes and attach only an approved work vault. Use a separate OS account when stronger isolation is needed. Separate agent homes do not restrict filesystem access or necessarily separate provider credentials in OS stores.

## Update or remove

Pull updates, run `python -m unittest discover -s tests -v`, and rerun install.ps1 with the same options. Launchers run installed copies. If the Python interpreter moves, reinstall to refresh its absolute path. Files use UTF-8 on every platform, including non-ASCII vault paths.

To stop using the harness, launch the bare clients. Remove only the managed instruction blocks, unchanged harness skill copies, the two `.ps1` launchers, and the selected prefix's `lib\agent-loop` directory. Preserve newer unrelated edits; restore backups only after reviewing them. No Windows service, scheduled task, or authentication configuration is installed by this harness.
