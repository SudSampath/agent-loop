"""Report Claude desktop's RTK readiness without changing settings.

Claude desktop coverage is RTK-only: local Code sessions run the bundled
Claude Code runtime, which applies the user-level RTK PreToolUse hook. This
module never writes app, Claude Code, or Headroom configuration and reports
setting names, never values. Native execution proof comes from native_probe.
"""

import argparse
import json
from pathlib import Path
import plistlib

from adapters.codex.routing import atomic_write

SUPPORT = Path.home() / 'Library/Application Support'
SETTINGS = Path.home() / '.claude/settings.json'
# Variables that select a Claude Code inference route; values are never reported.
ROUTING_ENV = ('ANTHROPIC_BASE_URL', 'ANTHROPIC_AUTH_TOKEN', 'ANTHROPIC_API_KEY',
               'ANTHROPIC_CUSTOM_HEADERS', 'CLAUDE_CODE_USE_BEDROCK', 'CLAUDE_CODE_USE_VERTEX',
               'CLAUDE_CODE_USE_FOUNDRY')


def status(settings=SETTINGS, support=SUPPORT):
    info = Path('/Applications/Claude.app/Contents/Info.plist')
    runtimes = support / 'Claude/claude-code'
    config = json.loads(settings.read_text()) if settings.exists() else {}
    hooks = [hook.get('command', '') for group in config.get('hooks', {}).get('PreToolUse', [])
             for hook in group.get('hooks', [])]
    return {
        'app_version': plistlib.loads(info.read_bytes()).get('CFBundleShortVersionString') if info.exists() else None,
        'bundled_claude_code_versions': sorted(p.name for p in runtimes.iterdir()) if runtimes.exists() else [],
        'rtk_pre_tool_use_hook_configured': any(command.split()[:3] == ['rtk', 'hook', 'claude']
                                                for command in hooks),
        # Settings-file routing applies to every CLI session, including Orca's wrapped ones.
        'settings_routing_env_keys': sorted(set(config.get('env', {})) & set(ROUTING_ENV)),
        'third_party_inference_configured': (support / 'Claude-3p/configLibrary').exists() or any(
            Path('/Library/Managed Preferences').glob('*/com.anthropic.claudefordesktop.plist')),
        'headroom_inference': 'not routed; claude.ai sign-in sets the API host',
        'configuration_changed': False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['status'])
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    encoded = json.dumps(status(), indent=2) + '\n'
    if args.output:
        atomic_write(args.output, encoded.encode())
    print(encoded, end='')


if __name__ == '__main__':
    main()
