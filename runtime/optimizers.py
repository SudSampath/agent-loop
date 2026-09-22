import fcntl
import json
from pathlib import Path
import shlex
import shutil
import sys

from common import write


def configure(home, agent):
    rtk = shutil.which('rtk')
    if not rtk:
        raise ValueError('RTK missing from PATH')
    command = (shlex.join([sys.executable, str(Path(__file__).parent / 'rtk_hook.py')])
               if agent == 'codex' else shlex.join([rtk, 'hook', 'claude']))
    target = home / ('hooks.json' if agent == 'codex' else 'settings.json')
    with (home / '.agent-loop-hooks.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        data = json.loads(target.read_text()) if target.exists() else {}
        groups = data.setdefault('hooks', {}).setdefault('PreToolUse', [])
        # Preserve existing RTK integrations instead of rewriting twice.
        if not any('rtk' in h.get('command', '').lower() for g in groups for h in g.get('hooks', [])):
            groups.append({'matcher': 'Bash', 'hooks': [{'type': 'command', 'command': command, 'timeout': 5}]})
            write(target, json.dumps(data, indent=2) + '\n')
