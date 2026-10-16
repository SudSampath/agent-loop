"""Collect allowlisted app/configuration metadata without reading conversation stores."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import plistlib
import tomllib
from urllib.parse import urlsplit
from urllib.request import urlopen


def endpoint_kind(value):
    if not value:
        return 'not configured'
    try:
        parsed = urlsplit(value)
        return 'local Headroom endpoint' if parsed.hostname in ('127.0.0.1', 'localhost', '::1') and parsed.port == 8787 else 'other endpoint configured'
    except ValueError:
        return 'invalid endpoint'


def codex_snapshot(home):
    result = {'configuration_present': (home / 'config.toml').exists(), 'execution_verified': False}
    if result['configuration_present']:
        data = tomllib.loads((home / 'config.toml').read_text())
        result.update({
            'openai_base_url': endpoint_kind(data.get('openai_base_url')),
            'custom_model_provider': bool(data.get('model_provider')),
            'hooks_enabled': data.get('features', {}).get('hooks', 'default'),
            'headroom_mcp_configured': 'headroom' in data.get('mcp_servers', {}),
            'saved_hook_trust_entries': len(data.get('hooks', {}).get('state', {})),
        })
    hooks = home / 'hooks.json'
    result['rtk_hook_entries'] = 0
    if hooks.exists():
        data = json.loads(hooks.read_text())
        result['rtk_hook_entries'] = sum(
            'rtk' in handler.get('command', '').lower()
            for group in data.get('hooks', {}).get('PreToolUse', [])
            for handler in group.get('hooks', [])
        )
    return result


def claude_snapshot(home):
    result = {'execution_verified': False}
    code = home / '.claude' / 'settings.json'
    if code.exists():
        data = json.loads(code.read_text())
        result['code_rtk_hook_entries'] = sum(
            'rtk' in handler.get('command', '').lower()
            for group in data.get('hooks', {}).get('PreToolUse', [])
            for handler in group.get('hooks', [])
        )
        result['code_endpoint'] = endpoint_kind(data.get('env', {}).get('ANTHROPIC_BASE_URL'))
    for label, path in (
        ('code_headroom_mcp_configured', home / '.claude.json'),
        ('chat_headroom_mcp_configured', home / 'Library/Application Support/Claude/claude_desktop_config.json'),
    ):
        result[label] = 'headroom' in json.loads(path.read_text()).get('mcpServers', {}) if path.exists() else False
    return result


def collect():
    home = Path.home()
    apps = []
    for root in (Path('/Applications'), home / 'Applications'):
        if not root.exists():
            continue
        for app in root.glob('*.app'):
            if app.stem.lower() not in ('claude', 'chatgpt', 'codex', 'orca'):
                continue
            info = app / 'Contents' / 'Info.plist'
            if info.exists():
                data = plistlib.loads(info.read_bytes())
                apps.append({'name': app.stem, 'bundle_id': data.get('CFBundleIdentifier'),
                             'version': data.get('CFBundleShortVersionString'), 'build': data.get('CFBundleVersion')})
    result = {
        'observed_at': datetime.now(timezone.utc).isoformat(),
        'platform': {'system': platform.system(), 'architecture': platform.machine()},
        'apps': apps,
        'codex_user_config': codex_snapshot(home / '.codex'),
        'orca_codex_config': codex_snapshot(home / 'Library/Application Support/orca/codex-runtime-home/home'),
        'claude': claude_snapshot(home),
        'account_plan_and_execution_modes': 'unverified; app UI access required',
        'scope': 'configuration metadata only; no command execution or inference coverage claims',
    }
    try:
        with urlopen('http://127.0.0.1:8787/health', timeout=3) as response:
            health = json.load(response)
        result['existing_headroom_service'] = {key: health.get(key) for key in ('status', 'version', 'ready')}
    except OSError:
        result['existing_headroom_service'] = {'status': 'unreachable'}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    encoded = json.dumps(collect(), indent=2) + '\n'
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded)
    print(encoded, end='')


if __name__ == '__main__':
    main()
