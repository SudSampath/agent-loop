"""Read-only current readiness audit; does not claim a cold-boot test."""

import json
import os
from pathlib import Path
import plistlib
import re
import shutil
import subprocess
from urllib.request import urlopen

from adapters.codex.routing import CONFIG, PROXY, active_route
from verification.backend_probe import DEFAULT_BINARY


def audit():
    plist = Path.home() / 'Library/LaunchAgents/com.headroom.orca.plist'
    configuration = plistlib.loads(plist.read_bytes()) if plist.exists() else {}
    job = subprocess.run(['launchctl', 'print', f'gui/{os.getuid()}/com.headroom.orca'],
                         capture_output=True, text=True, timeout=10)
    state = re.search(r'^\s*state = ([a-z_]+)\s*$', job.stdout, re.M)
    login = subprocess.run([str(DEFAULT_BINARY), 'login', 'status'],
                           capture_output=True, text=True, timeout=20)
    login_text = (login.stdout + login.stderr).lower()
    try:
        with urlopen(PROXY + '/health', timeout=5) as response:
            health = json.load(response)
        ready = health.get('status') == 'healthy' and health.get('ready') is not False
    except OSError:
        ready = False
    rtk = shutil.which('rtk')
    boot = subprocess.run(['sysctl', '-n', 'kern.boottime'],
                          capture_output=True, text=True, timeout=5)
    boot_time = re.search(r'\bsec\s*=\s*(\d+)', boot.stdout)
    return {
        'scope': 'current user-session readiness; no restart or fault injection',
        'launch_agent_file_present': plist.exists(),
        'launch_agent_registered': job.returncode == 0,
        'launch_agent_state': state.group(1) if state else 'unverified',
        'launch_at_login_configured': configuration.get('RunAtLoad') is True,
        'keep_alive_configuration': configuration.get('KeepAlive'),
        'headroom_ready_now': ready,
        'native_route_persisted': active_route(CONFIG.read_bytes()),
        'chatgpt_login_reported': login.returncode == 0 and 'logged in' in login_text and 'chatgpt' in login_text,
        'rtk_executable_available': bool(rtk and os.access(rtk, os.X_OK)),
        'kernel_boot_time_unix': int(boot_time.group(1)) if boot_time else None,
        'cold_boot_workflow_verified': False,
        'startup_race_verified': False,
        'outage_fallback_verified': False,
        'configuration_changed': False,
    }


if __name__ == '__main__':
    print(json.dumps(audit(), indent=2))
