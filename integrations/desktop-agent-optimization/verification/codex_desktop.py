"""Report ChatGPT desktop's Codex RTK readiness without changing settings.

Local Codex sessions in the app run the bundled Codex runtime, which applies
user-level PreToolUse hooks from the Codex home once they are trusted. This
module never writes app, Codex, or Headroom configuration; it reports hook
presence and trust, never hook hashes. Native execution proof comes from
native_probe.
"""

import argparse
import json
from pathlib import Path
import plistlib
import tomllib

from adapters.codex.routing import atomic_write
from verification.runtime_inventory import endpoint_kind

CODEX_HOME = Path.home() / '.codex'
APP = Path('/Applications/ChatGPT.app')
# RTK has no Codex hook processor; a wrapper adapts `rtk rewrite` to the hook contract.
RTK_HOOK_EXECUTABLES = ('rtk', 'rtk-codex-hook.py')


def rtk_handlers(hooks_file):
    """Trust-state keys for PreToolUse handlers that invoke RTK."""
    data = json.loads(hooks_file.read_text()) if hooks_file.exists() else {}
    return [f'{hooks_file}:pre_tool_use:{group_index}:{handler_index}'
            for group_index, group in enumerate(data.get('hooks', {}).get('PreToolUse', []))
            for handler_index, handler in enumerate(group.get('hooks', []))
            if Path((handler.get('command') or ' ').split()[0]).name in RTK_HOOK_EXECUTABLES]


def status(home=CODEX_HOME, app=APP):
    config = tomllib.loads((home / 'config.toml').read_text()) if (home / 'config.toml').exists() else {}
    trust = config.get('hooks', {}).get('state', {})
    handlers = rtk_handlers(home / 'hooks.json')
    info, package = app / 'Contents/Info.plist', app / 'Contents/Resources/codex-cli/codex-package.json'
    return {
        'app_version': plistlib.loads(info.read_bytes()).get('CFBundleShortVersionString') if info.exists() else None,
        'bundled_codex_version': json.loads(package.read_text()).get('version') if package.exists() else None,
        'hooks_feature': config.get('features', {}).get('hooks', 'default'),
        'rtk_pre_tool_use_hook_configured': bool(handlers),
        # Codex skips untrusted hooks; a later hooks.json edit can make a saved hash stale.
        'rtk_hook_trust_entry_present': any(
            'trusted_hash' in trust.get(key, {}) and trust[key].get('enabled', True) for key in handlers),
        'headroom_route': endpoint_kind(config.get('openai_base_url')),
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
