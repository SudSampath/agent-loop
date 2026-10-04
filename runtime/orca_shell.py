"""Opt-in Bash/Zsh routing for agents started in Orca's ordinary terminals."""
import json
import os
from pathlib import Path
import shlex

from common import write
from platform_support import WINDOWS

START = '# >>> sudarshan-agent-loop Orca routing >>>'
END = '# <<< sudarshan-agent-loop Orca routing <<<'
ORCA = '${ORCA_WORKTREE_ID:-}${ORCA_WORKSPACE_ID:-}${ORCA_TAB_ID:-}'
BYPASS = {'codex': '--dangerously-bypass-approvals-and-sandbox', 'claude': '--dangerously-skip-permissions'}


def routing_block(launchers, skip_permissions=False):
    lines = [START, '# Bash/Zsh only. Keep external terminals and agent binaries unchanged.',
             f'if [ -n "{ORCA}" ]; then']
    for agent, launcher in launchers.items():
        quoted = shlex.quote(str(launcher))
        # The function keyword avoids alias expansion while parsing a definition.
        # Headroom invokes the real executable through PATH, not these functions.
        lines += [f'  function {agent} {{', f'    if [ -n "{ORCA}" ]; then']
        if skip_permissions:
            # Version/help must stay first so wrappers pass them through without optimizers.
            lines += ['      case "${1:-}" in',
                      f'        --version|-V|--help|-h) command {quoted} "$@" ;;',
                      f'        *) command {quoted} {BYPASS[agent]} "$@" ;;', '      esac']
        else:
            lines += [f'      command {quoted} "$@"']
        lines += ['    else', f'      command {agent} "$@"', '    fi', '  }']
    return '\n'.join([*lines, 'fi', END]) + '\n'


def merge_routing(old, block):
    if START in old or END in old:
        if old.count(START) != 1 or old.count(END) != 1 or old.index(START) > old.index(END):
            raise ValueError('Malformed Orca routing block; repair it before installing')
        before, rest = old.split(START)
        _, after = rest.split(END)
        return before + block.rstrip('\n') + after
    return old + ('\n' if old and not old.endswith('\n') else '') + block


def install(args):
    if WINDOWS:
        raise ValueError('Orca shell routing requires Bash/Zsh on macOS, Linux, or WSL2')
    prefix = Path(args.prefix).expanduser().resolve()
    if not args.codex_launcher or not args.claude_launcher:
        config = prefix / 'lib/sudarshan-agent-loop/machine.json'
        if not config.is_file() or not json.loads(config.read_text(encoding='utf-8')).get('optimizers'):
            raise ValueError('Install the harness with --optimizers before enabling Orca shell routing')
    launchers = {}
    for agent in ('codex', 'claude'):
        value = getattr(args, agent + '_launcher')
        launcher = Path(value).expanduser().absolute() if value else prefix / 'bin' / ('sudarshan-' + agent)
        if not launcher.is_file() or not os.access(launcher, os.X_OK):
            raise ValueError(f'Executable wrapper missing: {launcher}; install the harness with --optimizers first')
        # Routing straight back to the bare command would silently defeat the safeguard.
        if launcher.name == agent:
            raise ValueError(f'Select a named wrapper, not bare {agent}: {launcher}')
        launchers[agent] = launcher
    block = routing_block(launchers, args.skip_permissions)
    planned = {}
    for value in args.rc:
        target = Path(value).expanduser().absolute()
        if target.is_symlink():
            raise ValueError(f'Refusing to replace symlink: {target}')
        old = target.read_text(encoding='utf-8') if target.exists() else ''
        planned[target] = merge_routing(old, block)
    for target, content in planned.items():
        print(('Would update ' if args.dry_run else 'Update ') + str(target))
        if not args.dry_run:
            write(target, content)
    print(block, end='')
    print('Open a new Orca terminal after installing. Existing shells and running agents are unchanged.')
    print('Verify type codex and type claude there; aliases or explicit binary paths can bypass this routing.')
    if args.skip_permissions:
        print('Warning: Orca agents now skip approval prompts; Codex also runs without its sandbox.')
