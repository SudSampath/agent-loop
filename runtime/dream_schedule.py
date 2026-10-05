"""Opt-in nightly unattended Dream run through the Claude launcher (macOS launchd, Linux/WSL2 systemd)."""
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys

from common import write
from platform_support import WINDOWS

LABEL = 'com.sudarshan-agent-loop.dream'
UNIT = 'sudarshan-agent-loop-dream'


def script_content(launcher, workspace, vault, logs, propose_only):
    prompt = '/dream --unattended' + (' --dry-run' if propose_only else '')
    # One Claude run covers both clients: the skill reads Claude and Codex transcripts.
    # Unattended file moves need the bypass flag; the skill itself never commits or pushes.
    return '\n'.join([
        '#!/bin/sh', 'set -u',
        f'cd {shlex.quote(str(workspace))} || exit 1',
        f'mkdir -p {shlex.quote(str(logs))}',
        f'log={shlex.quote(str(logs))}/"$(date +%F).log"',
        '{', '  echo "== dream start $(date)"', '  rc=0',
        f'  {shlex.quote(str(launcher))} -p {shlex.quote(prompt)} --dangerously-skip-permissions \\',
        f'    --add-dir {shlex.quote(str(vault))} </dev/null || rc=$?',
        '  echo "== dream end $(date) rc=$rc"', '} >>"$log" 2>&1', 'exit "$rc"', ''])


def launchd_plist(script, hour, minute, logs):
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>{LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>{script}</string>
  </array>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key>
    <integer>{hour}</integer>
    <key>Minute</key>
    <integer>{minute}</integer>
  </dict>
  <key>StandardErrorPath</key>
  <string>{logs}/launchd.err</string>
</dict>
</plist>
'''


def systemd_units(script, hour, minute):
    # systemd splits ExecStart on whitespace unless the path is double-quoted.
    quoted = '"' + str(script).replace('\\', '\\\\').replace('"', '\\"') + '"'
    service = f'[Unit]\nDescription=Nightly unattended Dream review\n\n[Service]\nType=oneshot\nExecStart={quoted}\n'
    # Persistent catches up a run missed while the machine was off or asleep.
    timer = (f'[Unit]\nDescription=Nightly unattended Dream review\n\n[Timer]\n'
             f'OnCalendar=*-*-* {hour:02d}:{minute:02d}:00\nPersistent=true\n\n[Install]\nWantedBy=timers.target\n')
    return service, timer


def install(args):
    if WINDOWS:
        raise ValueError('Scheduled Dream requires macOS launchd or Linux/WSL2 systemd')
    if not (0 <= args.hour <= 23 and 0 <= args.minute <= 59):
        raise ValueError('Hour must be 0-23 and minute 0-59')
    prefix = Path(args.prefix).expanduser().resolve()
    config = prefix / 'lib/sudarshan-agent-loop/machine.json'
    cfg = json.loads(config.read_text(encoding='utf-8')) if config.is_file() else {}
    # Explicit paths let an existing launcher setup schedule Dream without the full harness.
    workspace = Path(args.workspace or cfg.get('workspace') or '').expanduser().resolve()
    vault = Path(args.vault or cfg.get('vault') or '').expanduser().resolve()
    if not (args.workspace or cfg.get('workspace')) or not workspace.is_dir():
        raise ValueError('Workspace missing; install the harness or pass --workspace')
    if not (args.vault or cfg.get('vault')) or not (vault / 'INDEX.md').is_file():
        raise ValueError('Dream needs a vault with INDEX.md; install the harness with --vault or pass --vault')
    launcher = Path(args.claude_launcher).expanduser().absolute() if args.claude_launcher else prefix / 'bin/sudarshan-claude'
    if not launcher.is_file() or not os.access(launcher, os.X_OK):
        raise ValueError(f'Executable Claude launcher missing: {launcher}')
    home = Path.home()
    logs = prefix / 'state/sudarshan-agent-loop/dream'
    script = prefix / 'lib/sudarshan-agent-loop/dream-nightly.sh'
    planned = {script: script_content(launcher, workspace, vault, logs, args.propose_only)}
    if sys.platform == 'darwin':
        planned[home / f'Library/LaunchAgents/{LABEL}.plist'] = launchd_plist(script, args.hour, args.minute, logs)
        domain = f'gui/{os.getuid()}'
        target = home / f'Library/LaunchAgents/{LABEL}.plist'
        load = [['launchctl', 'bootout', f'{domain}/{LABEL}'], ['launchctl', 'bootstrap', domain, str(target)]]
    else:
        units = home / '.config/systemd/user'
        service, timer = systemd_units(script, args.hour, args.minute)
        planned[units / f'{UNIT}.service'], planned[units / f'{UNIT}.timer'] = service, timer
        load = [['systemctl', '--user', 'daemon-reload'], ['systemctl', '--user', 'enable', '--now', f'{UNIT}.timer']]
    for target in planned:
        if target.is_symlink():
            raise ValueError(f'Refusing to replace symlink: {target}')
    for target, content in planned.items():
        print(('Would write ' if args.dry_run else 'Install ') + str(target))
        if not args.dry_run:
            write(target, content, executable=target == script)
    print(planned[script], end='')
    if args.dry_run or args.no_load:
        print('Not loaded. Load with: ' + ' && '.join(shlex.join(c) for c in load[1:]))
        return 0
    # bootout fails harmlessly when nothing is loaded yet; reloading picks up a changed schedule.
    subprocess.run(load[0], capture_output=True)
    for command in load[1:]:
        if subprocess.run(command).returncode:
            raise ValueError(f'Scheduler command failed: {shlex.join(command)}; files were written')
    print(f'Scheduled Dream daily at {args.hour:02d}:{args.minute:02d} local time. Logs: {logs}')
    print('Warning: the run skips Claude permission prompts so it can archive memories and compress notes unattended.')
    return 0
