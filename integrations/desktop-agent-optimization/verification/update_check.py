"""Re-verify desktop RTK coverage whenever an app or its bundled runtime changes.

`run` records app and bundled-runtime versions, runs the read-only Codex and
Claude status checks and the bundled Codex runtime probe, and keeps the result
in private state. `install` adds a user LaunchAgent that runs it when the app
bundles change and once a day; `uninstall` removes it. Nothing here edits app,
agent, hook, or Headroom configuration. The native UI check stays manual.
"""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import plistlib
import subprocess
import sys

from adapters.codex.routing import STATE_DIR, atomic_write
from verification import claude_desktop, codex_desktop, codex_runtime_probe

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LABEL = 'com.agent-loop.desktop-update-check'
LAUNCH_AGENTS = Path.home() / 'Library/LaunchAgents'
WATCH_PATHS = (
    '/Applications/ChatGPT.app/Contents/Info.plist',
    '/Applications/ChatGPT.app/Contents/Resources/codex-cli/codex-package.json',
    '/Applications/Claude.app/Contents/Info.plist',
    # Claude desktop updates its bundled Claude Code separately from the app.
    str(claude_desktop.SUPPORT / 'Claude/claude-code'),
)


def notify(message):
    # The message is passed as an argument, never interpolated into the script.
    subprocess.run(['osascript', '-e', 'on run argv', '-e',
                    'display notification (item 1 of argv) with title "Desktop RTK check"',
                    '-e', 'end run', message], capture_output=True, timeout=10)


def run(state_dir=STATE_DIR, alert=False):
    codex, claude = codex_desktop.status(), claude_desktop.status()
    versions = {'chatgpt': codex['app_version'], 'codex': codex['bundled_codex_version'],
                'claude': claude['app_version'], 'claude_code': claude['bundled_claude_code_versions']}
    path = Path(state_dir) / 'update-check.json'
    previous = json.loads(path.read_text()) if path.exists() else {}
    try:
        runtime = codex_runtime_probe.probe()
    except (OSError, RuntimeError, TimeoutError, subprocess.SubprocessError) as error:
        runtime = {'checks_passed': False, 'error': type(error).__name__}
    checks = {
        'codex_rtk_hook_trusted': codex['rtk_pre_tool_use_hook_configured'] and codex['rtk_hook_trust_entry_present'],
        'codex_runtime_applies_rtk': runtime['checks_passed'],
        'claude_rtk_hook_configured': claude['rtk_pre_tool_use_hook_configured'],
    }
    result = {
        'observed_at': datetime.now(timezone.utc).isoformat(),
        'versions': versions,
        'versions_changed': bool(previous) and versions != previous.get('versions'),
        'checks': checks,
        'passed': all(checks.values()),
        'codex_runtime_probe': runtime,
        'native_ui_workflow_verified': False,
    }
    atomic_write(path, (json.dumps(result, indent=2) + '\n').encode())
    if alert and not result['passed']:
        notify('RTK coverage check failed: ' + ', '.join(name for name, ok in checks.items() if not ok))
    elif alert and result['versions_changed']:
        notify('App updated; RTK coverage still passes. Native UI check is optional.')
    return result


def launch_agent(python, state_dir):
    return {
        'Label': LABEL,
        'ProgramArguments': [python, '-m', 'verification.update_check', 'run', '--alert'],
        'WorkingDirectory': str(PROJECT_ROOT),
        'EnvironmentVariables': {'PATH': os.environ.get('PATH', '/usr/bin:/bin')},
        'WatchPaths': list(WATCH_PATHS),
        'StartCalendarInterval': {'Hour': 9, 'Minute': 30},
        'ThrottleInterval': 60,
        'ProcessType': 'Background',
        'StandardOutPath': str(Path(state_dir) / 'update-check.log'),
        'StandardErrorPath': str(Path(state_dir) / 'update-check.log'),
    }


def install(launch_agents=LAUNCH_AGENTS, state_dir=STATE_DIR, python=sys.executable, load=True):
    target = Path(launch_agents) / f'{LABEL}.plist'
    if load:
        uninstall(launch_agents)
    atomic_write(target, plistlib.dumps(launch_agent(python, state_dir)), mode=0o644)
    if load:
        subprocess.run(['launchctl', 'bootstrap', f'gui/{os.getuid()}', str(target)], check=True, timeout=10)
    return {'installed': str(target), 'loaded': load}


def uninstall(launch_agents=LAUNCH_AGENTS):
    target = Path(launch_agents) / f'{LABEL}.plist'
    subprocess.run(['launchctl', 'bootout', f'gui/{os.getuid()}/{LABEL}'], capture_output=True, timeout=10)
    target.unlink(missing_ok=True)
    return {'removed': str(target)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['run', 'install', 'uninstall'])
    parser.add_argument('--alert', action='store_true', help='Post a notification on failure or app update')
    args = parser.parse_args()
    result = {'run': lambda: run(alert=args.alert), 'install': install, 'uninstall': uninstall}[args.action]()
    print(json.dumps(result, indent=2))
    if args.action == 'run' and not result['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
