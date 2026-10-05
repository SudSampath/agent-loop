# Sudarshan's Agent Loop

Clone this private repository to bring the same working habits, seven reviewed skills, and Codex/Claude launchers to a new computer or job. It packages the useful parts of my Obsidian setup into a repeatable installation.

The loop is **orient → define completion → implement → verify → hand off → retain durable lessons**. Codex and Claude run their own agent loops; this harness supplies shared context and continuity. It does not run an unattended queue.

## Start on a new computer

Requires Git, Python 3.10+, and authenticated Codex and Claude Code CLIs. Supports macOS, Linux, native Windows (PowerShell 7.4+), and WSL2. [Native Windows setup](docs/windows.md) uses `install.ps1`; the commands below are for macOS/Linux/WSL2. [Full setup instructions](docs/setup.md) include the optional POSIX Headroom/RTK/Orca layer.

```sh
gh auth login
gh repo clone SudSampath/sudarshans-agent-loop
cd sudarshans-agent-loop
mkdir -p "$HOME/Projects"
python3 bootstrap.py install --workspace "$HOME/Projects" --dry-run
python3 bootstrap.py install --workspace "$HOME/Projects"
export PATH="$HOME/.local/bin:$PATH"
python3 bootstrap.py doctor
cd "$HOME/Projects/your-project"
sudarshan-codex
# Or:
sudarshan-claude
```

To attach an Obsidian vault, finish syncing it and add `--vault "/path/to/your/vault"` to the install command. The installer requires its INDEX.md. Rerun with all desired options when changing settings; omitted `--vault` or `--optimizers` turns that option off in the launcher configuration.

## What comes with it

- One shared set of working instructions, adapted to local paths for both clients.
- PRD, GTM, tickets, organize, handoff, dream, and follow-up check skills, with portable references.
- Repeatable installer with preview, backups, conflict checks, and a doctor command.
- Launchers that preserve Orca's injected environment and support its separate runtime home.
- Optional Headroom proxy and additive RTK hooks.
- Opt-in Orca shell routing so bare agent commands in worktree terminals also reach the wrappers.
- Opt-in nightly unattended Dream run across both clients (launchd or systemd).
- [Daily workflow](docs/workflow.md), [new job and migration guidance](docs/setup.md#another-job), and a [handoff template](templates/handoff.md).

Credentials, connected accounts, employer data, and session history are configured locally. Cloning this repo does not authenticate the agents or connect Obsidian Sync.

## Development

```sh
python3 -m unittest discover -s tests -v
```

See [design and provenance](docs/design.md) for the source notes and platform limits. See [validation record](docs/validation.md) for what was actually tested.
