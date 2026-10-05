# Agent Loop

A portable harness that gives Codex and Claude Code the same working habits, skills, and memory on any computer. Install it once and both agents share one set of instructions, eight reviewed skills, and launchers that work inside Orca worktrees. A nightly Dream review reads both agents' sessions and turns confirmed lessons into durable instructions.

The repository is deliberately generic: it refers to "the user". Who the user is, how they write, and who they write for stay in their own knowledge vault (`me/profile.md`, `me/voice.md`, `me/audiences.md`, and similar). The installer points both agents at those files instead of copying them, so personal context never enters this repository and is always current.

The loop is **orient → define completion → implement → verify → hand off → retain durable lessons**. Codex and Claude run their own agent loops; this harness supplies shared context and continuity. It does not run an unattended queue.

## Start on a new computer

Requires Git, Python 3.10+, and authenticated Codex and Claude Code CLIs. Supports macOS, Linux, native Windows (PowerShell 7.4+), and WSL2. [Native Windows setup](docs/windows.md) uses `install.ps1`; the commands below are for macOS/Linux/WSL2. [Full setup instructions](docs/setup.md) include the optional POSIX Headroom/RTK/Orca layer.

```sh
gh auth login
gh repo clone SudSampath/agent-loop
cd agent-loop
mkdir -p "$HOME/Projects"
python3 bootstrap.py install --workspace "$HOME/Projects" --dry-run
python3 bootstrap.py install --workspace "$HOME/Projects"
export PATH="$HOME/.local/bin:$PATH"
python3 bootstrap.py doctor
cd "$HOME/Projects/your-project"
agent-loop-codex
# Or:
agent-loop-claude
```

To attach an Obsidian vault, finish syncing it and add `--vault "/path/to/your/vault"` to the install command. The installer requires its INDEX.md and references any profile files it finds in the vault's `me/` folder. Rerun with all desired options when changing settings; omitted `--vault` or `--optimizers` turns that option off in the launcher configuration.

## What comes with it

- One shared set of working instructions, adapted to local paths for both clients.
- PRD, GTM, tickets, organize, handoff, dream, dream-review, and follow-up check skills, with portable references.
- Repeatable installer with preview, backups, conflict checks, and a doctor command.
- Launchers that preserve Orca's injected environment and support its separate runtime home.
- Optional Headroom proxy and additive RTK hooks.
- Opt-in Orca shell routing so bare agent commands in worktree terminals also reach the wrappers.
- Opt-in nightly unattended Dream run across both clients (launchd or systemd).
- [Daily workflow](docs/workflow.md), [new job and migration guidance](docs/setup.md#another-job), and a [handoff template](templates/handoff.md).

Credentials, connected accounts, employer data, and session history are configured locally. Cloning this repo does not authenticate the agents or connect Obsidian Sync.

## The learning loop

Dream (nightly or on demand) reviews the vault, both agents' transcripts, and git activity across every repository and worktree. It writes a digest, follows up on its previous recommendations, and drafts candidate lessons. Drafts confirmed by later evidence are marked ready; `dream-review` walks the user through them and promotes each to project memory, the vault, or this repository's shared instructions. Later dreams check whether each promoted lesson is holding.

## Development

```sh
python3 -m unittest discover -s tests -v
```

See [design and provenance](docs/design.md) for the source notes and platform limits. See [validation record](docs/validation.md) for what was actually tested.

## License

[MIT](LICENSE)
