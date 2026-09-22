# Machine setup

## 1. Install prerequisites

On macOS with Homebrew already installed:

```sh
brew install git gh python node
npm install -g @openai/codex
brew install --cask claude-code
```

On Linux or WSL2, install Git, GitHub CLI, Python 3.10+, and a supported Node LTS using your distribution/organization's package management. Install Codex using `npm install -g @openai/codex`. Use the native Linux installer from the official Claude setup page. Native Windows users can instead follow [the PowerShell setup](windows.md), with no WSL requirement.

Check `python3 --version`, `git --version`, `gh --version`, `codex --version`, and `claude --version`. Open `codex` and `claude` directly and complete their login flows with the intended account. On a managed work machine, use the organization's approved provider and installation method.

Installation references: [Codex CLI](https://learn.chatgpt.com/docs/codex/cli), [Claude Code setup](https://code.claude.com/docs/en/setup), [GitHub CLI](https://cli.github.com/). Agent startup instructions: [Codex AGENTS.md](https://learn.chatgpt.com/docs/agent-configuration/agents-md), [Claude memory](https://code.claude.com/docs/en/memory). Check these when versions change.

## 2. Clone and install

Follow the README quickstart. Add the printed launcher directory to your shell's PATH persistently, e.g. `export PATH="$HOME/.local/bin:$PATH"` in your shell startup file. Do not replace existing startup content. Run from a normal terminal so an existing Orca session's CODEX_HOME does not accidentally select its managed home; alternatively pass explicit `--codex-home` and `--claude-home` values.

The installer prints every destination, appends a managed instruction block, and backs up changed existing files as `*.agent-loop-backup-TIMESTAMP`. It never replaces existing authentication/configuration files. Differing skill files stop installation before writes; merge the intended version manually and retry. Do not run concurrent installers against the same homes. Close agents while changing their configuration.

For a vault: install Obsidian, connect your chosen Sync vault, wait for Fully Synced, and confirm INDEX.md exists. Then:

```sh
python3 bootstrap.py install --workspace "$HOME/Projects" --vault "$HOME/Documents/My Knowledge"
```

The repository's reviewed skills remain its portable snapshot. Changes to vault skill definitions are not automatically imported. Review and synchronize intentional updates into this repository, then reinstall. Context such as profile and voice remains in the selected vault.

## 3. Optional optimizers (macOS/Linux/WSL2)

The reference Mac used Headroom 0.37.0 and RTK 0.49.0. To reproduce that Headroom baseline:

```sh
brew install uv rtk
uv tool install --python 3.12 'headroom-ai[proxy]==0.37.0'
```

On Linux/WSL2 install uv and RTK from their upstream instructions, then use the same uv command. Homebrew installs the available RTK version; confirm its `rewrite` and `hook claude` commands remain compatible before enabling. Upstream: [Headroom](https://github.com/headroomlabs-ai/headroom), [RTK](https://github.com/rtk-ai/rtk).

Rerun installation with `--optimizers` (and your vault/path options). The launchers use `headroom wrap` on demand; no separate service is required for this mode. They add RTK hooks alongside existing hooks, or retain an existing RTK integration. Codex may ask to trust the new hook; review it interactively. The installer never adds permission-bypass flags or hook-trust hashes. The Codex adapter's `allow` response is required by the locally tested rewrite contract; native approval and sandbox checks still apply to the rewritten command. Rewriting can affect command classification, so inspect approval prompts normally.

For an optional persistent macOS proxy, explicitly run:

```sh
headroom install apply --preset persistent-service --profile agent-loop --scope provider --providers manual --port 8787 --mode cache --no-telemetry
```

This is a separate operator step that creates a login service. Do not run it if a working proxy already owns that port. Use the same `--port` in bootstrap if choosing a different port. Linux/WSL2 users can keep on-demand wrapping; this repo does not install systemd services.

## 4. Orca

Install Orca separately. In Settings → Agents → Command overrides, select the full printed paths to `sudarshan-codex` and `sudarshan-claude`. Make sure the Orca process PATH includes the real agent binaries plus Headroom/RTK if enabled; restart the app after changing PATH. Do not edit Orca's live state JSON. Keep its existing managed environment and hooks. Review Default args separately; this harness does not add bypass flags.

Orca may supply a separate CODEX_HOME. The launcher adds its managed instructions and reviewed skills there at launch. Authentication and other Orca-managed configuration remain Orca's responsibility. Different jobs should use different Orca profiles or OS accounts; do not route a personal-vault launcher into a work profile.

## 5. Verify in a real session

```sh
python3 bootstrap.py doctor
sudarshan-codex --version
sudarshan-claude --version
```

Then open each agent in a disposable repository and ask: “List the instruction sources you loaded, the selected knowledge location, and the available Sudarshan skills. Read git status, make no changes, and report the result.” Verify both report the right paths and account context. Try a synthetic PRD outline to verify skill references. These live calls consume your normal agent usage.

If optimizers are enabled, check the proxy health at `http://127.0.0.1:8787/health` after a wrapped session starts. Check Headroom's logs/status and an actual tool invocation, not just binary presence. Bare CLI launches bypass Headroom. The original Mac runbook observed wrapped Claude Remote Control limitations and other custom-endpoint feature differences; use the bare CLI for features that require the normal endpoint.

Connect MCP/plugins afresh using the correct account. Run a harmless read in each service and confirm the organization before marking it ready. Do not copy cookies, token files, auth databases, or an old employer's MCP configuration.

## Another job

Create a separate OS account when work policy requires isolation. For convenience separation in one account, use separate homes and install prefix:

```sh
mkdir -p "$HOME/Work/Projects"
python3 bootstrap.py install --workspace "$HOME/Work/Projects" --prefix "$HOME/.local/agent-loop-work" --codex-home "$HOME/.codex-work" --claude-home "$HOME/.claude-work"
CODEX_HOME="$HOME/.codex-work" CLAUDE_CONFIG_DIR="$HOME/.claude-work" "$HOME/.local/agent-loop-work/bin/sudarshan-codex"
CODEX_HOME="$HOME/.codex-work" CLAUDE_CONFIG_DIR="$HOME/.claude-work" "$HOME/.local/agent-loop-work/bin/sudarshan-claude"
```

Authenticate those homes afresh. Add only an approved work vault using `--vault`; omit it to start from repository context. Separate homes are not a security sandbox: both processes still have your OS account's file access, and provider credentials may use OS-level stores. Never move employer data between jobs. Reuse generic methods and templates only.

## Updates and rollback

Pull intentional repository updates, rerun tests, preview installation with the same options, then install. Launchers run installed copies, so pulling alone does not update them. Keep your install command in a local machine note outside Git. Reinstall after moving/removing the Python interpreter used at install time.

To stop using the harness, point Orca back to the original binaries and use bare `codex`/`claude`. Remove only the delimited agent-loop blocks from AGENTS.md/CLAUDE.md. Remove only hook entries pointing to this installation's `rtk_hook.py`; a pre-existing RTK hook should remain. The Claude hook is shared by name (`rtk hook claude`); compare the preinstall backup to establish whether this install added it. Remove only unchanged harness skill copies. Finally remove the two launcher files and the `lib/sudarshan-agent-loop` directory under the selected prefix. Backups can restore exact earlier files, but merge instead if newer edits exist. If you explicitly installed the service, `headroom install remove --profile agent-loop` removes it. Reinstalling without `--optimizers` stops proxy wrapping but does not remove RTK hooks; use this rollback procedure to remove them.
