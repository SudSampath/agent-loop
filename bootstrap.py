#!/usr/bin/env python3
"""Install the portable harness using only the Python standard library."""
import argparse
import json
import os
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'runtime'))
from common import instructions, merge, write
from platform_support import WINDOWS, find_agent, launcher_content


def path(value):
    return Path(value).expanduser().resolve()


def install(args):
    prefix = path(args.prefix)
    homes = {'codex': path(args.codex_home), 'claude': path(args.claude_home)}
    workspace = path(args.workspace)
    if not workspace.is_dir():
        raise ValueError(f'Workspace does not exist: {workspace}')
    vault = path(args.vault) if args.vault else None
    if vault and not (vault / 'INDEX.md').is_file():
        raise ValueError('Selected vault must exist and contain INDEX.md; finish syncing first')
    if args.optimizers:
        if WINDOWS:
            raise ValueError('Native Windows supports the core harness. Use WSL2 for --optimizers; no files were changed.')
        for tool in ('headroom', 'rtk'):
            if not shutil.which(tool):
                raise ValueError(f'Install {tool} before enabling --optimizers; see docs/setup.md')
    body = (ROOT / 'templates/core.md').read_text(encoding='utf-8')
    body += f'\n## This machine\n\nProject root: `{workspace}`.\n'
    body += (f'Active knowledge vault: `{vault}`. Read its INDEX.md before relevant research.\n' if vault
             else 'No knowledge vault configured. Use repository context; ask for missing personal context when needed.\n')
    runtime = prefix / 'lib/sudarshan-agent-loop'
    planned = {}
    # Validate every conflict before writing anything.
    for agent, home in homes.items():
        filename = 'AGENTS.md' if agent == 'codex' else 'CLAUDE.md'
        target = home / filename
        planned[target] = merge(target.read_text(encoding='utf-8') if target.exists() else '', body)
        for source in (ROOT / 'skills').rglob('*.md'):
            target = home / 'skills' / source.relative_to(ROOT / 'skills')
            content = source.read_text(encoding='utf-8')
            if target.exists() and target.read_text(encoding='utf-8') != content:
                raise ValueError(f'Existing skill differs: {target}. Review/merge it before reinstalling.')
            planned[target] = content
        if args.optimizers:
            settings = home / ('hooks.json' if agent == 'codex' else 'settings.json')
            if settings.is_symlink():
                raise ValueError(f'Refusing symlink: {settings}')
            if settings.exists():
                data = json.loads(settings.read_text(encoding='utf-8'))
                groups = data.get('hooks', {}).get('PreToolUse', [])
                if not isinstance(groups, list) or any(not isinstance(g, dict) or not isinstance(g.get('hooks', []), list) or any(not isinstance(h, dict) for h in g.get('hooks', [])) for g in groups):
                    raise ValueError(f'Unexpected hook schema: {settings}')
    for source in (ROOT / 'runtime').glob('*.py'):
        planned[runtime / source.name] = source.read_text(encoding='utf-8')
    for source in (ROOT / 'skills').rglob('*.md'):
        planned[runtime / 'skills' / source.relative_to(ROOT / 'skills')] = source.read_text(encoding='utf-8')
    cfg = {'instructions': body, 'workspace': str(workspace), 'vault': str(vault) if vault else None,
           'optimizers': args.optimizers, 'port': args.port,
           **{agent + '_home': str(home) for agent, home in homes.items()}}
    planned[runtime / 'machine.json'] = json.dumps(cfg, indent=2) + '\n'
    for agent in homes:
        suffix = '.ps1' if WINDOWS else ''
        planned[prefix / 'bin' / ('sudarshan-' + agent + suffix)] = launcher_content(sys.executable, runtime / 'launch.py', agent)
    for target in planned:
        if target.is_symlink():
            raise ValueError(f'Refusing to replace symlink: {target}')
    for target, content in planned.items():
        print(('Would write ' if args.dry_run else 'Install ') + str(target))
        if not args.dry_run:
            write(target, content, executable=target.parent == prefix / 'bin')
    if args.optimizers and not args.dry_run:
        # Import installed adapter so hook command paths point to the installation.
        import importlib.util
        spec = importlib.util.spec_from_file_location('installed_optimizers', runtime / 'optimizers.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        for agent, home in homes.items():
            module.configure(home, agent)
    print('Preview complete.' if args.dry_run else f'Ready. Add {prefix / "bin"} to PATH; authenticate each CLI and run doctor.')


def doctor(args):
    prefix = path(args.prefix)
    config = prefix / 'lib/sudarshan-agent-loop/machine.json'
    if not config.exists():
        print('MISSING installation; run install first')
        return 1
    cfg = json.loads(config.read_text(encoding='utf-8'))
    checks = {tool + ' on PATH': bool(find_agent(tool)) for tool in ('git', 'codex', 'claude')}
    if WINDOWS:
        checks['PowerShell 7 on PATH'] = bool(shutil.which('pwsh'))
        for agent in ('codex', 'claude'):
            binary = find_agent(agent)
            checks[agent + ' native executable or PowerShell shim'] = bool(binary and Path(binary).suffix.lower() in ('.exe', '.ps1'))
    checks['workspace exists'] = Path(cfg['workspace']).is_dir()
    for agent, name in [('codex', 'AGENTS.md'), ('claude', 'CLAUDE.md')]:
        home = Path(cfg[agent + '_home'])
        p = home / name
        checks[agent + ' instructions'] = p.exists() and cfg['instructions'].strip() in p.read_text(encoding='utf-8')
        launcher = prefix / 'bin' / ('sudarshan-' + agent + ('.ps1' if WINDOWS else ''))
        checks[agent + ' launcher'] = launcher.is_file() if WINDOWS else os.access(launcher, os.X_OK)
        checks[agent + ' reviewed skills'] = all((home / 'skills' / p.relative_to(ROOT / 'skills')).exists() and (home / 'skills' / p.relative_to(ROOT / 'skills')).read_bytes() == p.read_bytes() for p in (ROOT / 'skills').rglob('*.md'))
    if cfg['vault']:
        checks['vault INDEX.md'] = (Path(cfg['vault']) / 'INDEX.md').is_file()
    if cfg['optimizers']:
        for tool in ('headroom', 'rtk'):
            checks[tool + ' on PATH'] = bool(shutil.which(tool))
    for name, ok in checks.items():
        print(('OK      ' if ok else 'MISSING ') + name)
    print('Authentication, hook trust, proxy routing, and knowledge loading require the live smoke checks in docs/setup.md.')
    return 0 if all(checks.values()) else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('install')
    p.add_argument('--prefix', default='~/.local')
    p.add_argument('--workspace', required=True)
    p.add_argument('--vault')
    p.add_argument('--codex-home', default=os.environ.get('CODEX_HOME', '~/.codex'))
    p.add_argument('--claude-home', default=os.environ.get('CLAUDE_CONFIG_DIR', '~/.claude'))
    p.add_argument('--optimizers', action='store_true')
    p.add_argument('--port', type=int, choices=range(1024, 65536), metavar='PORT', default=8787)
    p.add_argument('--dry-run', action='store_true')
    p = sub.add_parser('doctor')
    p.add_argument('--prefix', default='~/.local')
    p = sub.add_parser('orca-shell', help='Route bare agent commands in Orca Bash/Zsh terminals through wrappers')
    p.add_argument('--prefix', default='~/.local')
    p.add_argument('--rc', action='append', required=True, help='Bash/Zsh startup file; repeat for multiple files')
    p.add_argument('--codex-launcher', help='Existing Codex wrapper (default: PREFIX/bin/sudarshan-codex)')
    p.add_argument('--claude-launcher', help='Existing Claude wrapper (default: PREFIX/bin/sudarshan-claude)')
    p.add_argument('--skip-permissions', action='store_true',
                   help='Start routed agents with approval prompts (and the Codex sandbox) bypassed')
    p.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    try:
        if args.command == 'orca-shell':
            from orca_shell import install as install_orca_shell
            return install_orca_shell(args)
        return install(args) if args.command == 'install' else doctor(args)
    except (ValueError, OSError, TypeError, AttributeError) as error:
        print(f'Error: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
