"""Opt-in daily unattended skill runs through the Claude launcher (macOS launchd, Linux/WSL2 systemd)."""
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys

from common import write
from platform_support import WINDOWS

JOBS = {
    # One Claude run covers both clients: Dream reads Claude and Codex transcripts.
    'dream': {'name': 'Dream', 'skill': '/dream', 'label': 'com.agent-loop.dream', 'unit': 'agent-loop-dream',
              'script': 'dream-nightly.sh', 'description': 'Nightly unattended Dream review',
              # Jobs installed before the project was renamed; retired so Dream never runs twice a night.
              'legacy': ('com.sudarshan-agent-loop.dream', 'sudarshan-agent-loop-dream'),
              'bypass': 'archive memories and compress notes'},
    'meetings': {'name': 'Meeting sync', 'skill': '/sync-meetings', 'label': 'com.agent-loop.meetings',
                 'unit': 'agent-loop-meetings', 'script': 'meetings-daily.sh',
                 'description': 'Daily unattended meeting transcript sync', 'legacy': None,
                 'bypass': 'read meeting connectors and write vault notes'},
}


def script_content(job, launcher, workspace, vault, logs, propose_only):
    prompt = JOBS[job]['skill'] + ' --unattended' + (' --dry-run' if propose_only else '')
    # Unattended vault writes need the bypass flag; the skills never commit or push.
    return '\n'.join([
        '#!/bin/sh', 'set -u',
        f'cd {shlex.quote(str(workspace))} || exit 1',
        f'mkdir -p {shlex.quote(str(logs))}',
        f'log={shlex.quote(str(logs))}/"$(date +%F).log"',
        '{', f'  echo "== {job} start $(date)"', '  rc=0',
        f'  {shlex.quote(str(launcher))} -p {shlex.quote(prompt)} --dangerously-skip-permissions \\',
        f'    --add-dir {shlex.quote(str(vault))} </dev/null || rc=$?',
        f'  echo "== {job} end $(date) rc=$rc"', '} >>"$log" 2>&1', 'exit "$rc"', ''])


def launchd_plist(label, script, hour, minute, logs):
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>{label}</string>
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


def systemd_units(description, script, hour, minute):
    # systemd splits ExecStart on whitespace unless the path is double-quoted.
    quoted = '"' + str(script).replace('\\', '\\\\').replace('"', '\\"') + '"'
    service = f'[Unit]\nDescription={description}\n\n[Service]\nType=oneshot\nExecStart={quoted}\n'
    # Persistent catches up a run missed while the machine was off or asleep.
    timer = (f'[Unit]\nDescription={description}\n\n[Timer]\n'
             f'OnCalendar=*-*-* {hour:02d}:{minute:02d}:00\nPersistent=true\n\n[Install]\nWantedBy=timers.target\n')
    return service, timer


def install(args):
    job = JOBS[args.job]
    name, label, unit = job['name'], job['label'], job['unit']
    if WINDOWS:
        raise ValueError(f'Scheduled {name} requires macOS launchd or Linux/WSL2 systemd')
    if not (0 <= args.hour <= 23 and 0 <= args.minute <= 59):
        raise ValueError('Hour must be 0-23 and minute 0-59')
    prefix = Path(args.prefix).expanduser().resolve()
    config = prefix / 'lib/agent-loop/machine.json'
    cfg = json.loads(config.read_text(encoding='utf-8')) if config.is_file() else {}
    # Explicit paths let an existing launcher setup schedule a job without the full harness.
    workspace = Path(args.workspace or cfg.get('workspace') or '').expanduser().resolve()
    vault = Path(args.vault or cfg.get('vault') or '').expanduser().resolve()
    if not (args.workspace or cfg.get('workspace')) or not workspace.is_dir():
        raise ValueError('Workspace missing; install the harness or pass --workspace')
    if not (args.vault or cfg.get('vault')) or not (vault / 'INDEX.md').is_file():
        raise ValueError(f'{name} needs a vault with INDEX.md; install the harness with --vault or pass --vault')
    launcher = Path(args.claude_launcher).expanduser().absolute() if args.claude_launcher else prefix / 'bin/agent-loop-claude'
    if not launcher.is_file() or not os.access(launcher, os.X_OK):
        raise ValueError(f'Executable Claude launcher missing: {launcher}')
    home = Path.home()
    logs = prefix / 'state/agent-loop' / args.job
    script = prefix / 'lib/agent-loop' / job['script']
    planned = {script: script_content(args.job, launcher, workspace, vault, logs, args.propose_only)}
    legacy, unload = [], []
    if sys.platform == 'darwin':
        target = home / f'Library/LaunchAgents/{label}.plist'
        planned[target] = launchd_plist(label, script, args.hour, args.minute, logs)
        domain = f'gui/{os.getuid()}'
        load = [['launchctl', 'bootout', f'{domain}/{label}'], ['launchctl', 'bootstrap', domain, str(target)]]
        if job['legacy']:
            legacy = [home / f'Library/LaunchAgents/{job["legacy"][0]}.plist']
            unload = [['launchctl', 'bootout', f'{domain}/{job["legacy"][0]}']]
    else:
        units = home / '.config/systemd/user'
        service, timer = systemd_units(job['description'], script, args.hour, args.minute)
        planned[units / f'{unit}.service'], planned[units / f'{unit}.timer'] = service, timer
        load = [['systemctl', '--user', 'daemon-reload'], ['systemctl', '--user', 'enable', '--now', f'{unit}.timer']]
        if job['legacy']:
            legacy = [units / f'{job["legacy"][1]}.timer', units / f'{job["legacy"][1]}.service']
            unload = [['systemctl', '--user', 'disable', '--now', f'{job["legacy"][1]}.timer']]
    for target in planned:
        if target.is_symlink():
            raise ValueError(f'Refusing to replace symlink: {target}')
    for target, content in planned.items():
        print(('Would write ' if args.dry_run else 'Install ') + str(target))
        if not args.dry_run:
            write(target, content, executable=target == script)
    legacy = [path for path in legacy if path.exists()]
    for path in legacy:
        print(('Would retire ' if args.dry_run else 'Retire ') + str(path))
    if legacy and not args.dry_run:
        if not args.no_load:
            for command in unload:
                subprocess.run(command, capture_output=True)
        for path in legacy:
            path.unlink()
    print(planned[script], end='')
    if args.dry_run or args.no_load:
        print('Not loaded. Load with: ' + ' && '.join(shlex.join(c) for c in load[1:]))
        return 0
    # bootout fails harmlessly when nothing is loaded yet; reloading picks up a changed schedule.
    subprocess.run(load[0], capture_output=True)
    for command in load[1:]:
        if subprocess.run(command).returncode:
            raise ValueError(f'Scheduler command failed: {shlex.join(command)}; files were written')
    print(f'Scheduled {name} daily at {args.hour:02d}:{args.minute:02d} local time. Logs: {logs}')
    print(f'Warning: the run skips Claude permission prompts so it can {job["bypass"]} unattended.')
    return 0
