"""Observe a native git tool call without modifying app settings or hook trust.

A synthetic repository uses Git's supported fsmonitor hook to record the
executable ancestry of git status. Only process paths and derived booleans are
inspected; command arguments, credentials, and conversations are never read.
The baseline and explicit RTK controls are distinct from the native UI sample.
"""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPO = PROJECT_ROOT / '.probe-workspace' / 'native-codex'
NATIVE_MAIN_PATHS = {
    '/Applications/ChatGPT.app/Contents/MacOS/ChatGPT',
    '/Applications/Codex.app/Contents/MacOS/Codex',
    '/Applications/Claude.app/Contents/MacOS/Claude',
}
# Runtimes the apps bundle; the same binaries also run outside the apps.
BUNDLED_BACKENDS = ('/Contents/Resources/codex-cli/', '/Application Support/Claude/claude-code/')


def classify_ancestry(executables):
    """Require the native application's main process, not a bundled CLI alone."""
    apps = [Path(p).name for p in executables if p in NATIVE_MAIN_PATHS]
    return {
        'rtk_ancestor': any(Path(p).name == 'rtk' for p in executables),
        'native_app_ancestor': bool(apps),
        'native_app': apps[0] if apps else None,
        'bundled_backend_ancestor': any(
            marker in p for p in executables for marker in BUNDLED_BACKENDS
        ),
    }


def process_ancestry():
    result = subprocess.run(
        ['ps', '-axo', 'pid,ppid,comm'], capture_output=True, text=True,
        timeout=5, check=True,
    )
    rows = {}
    for line in result.stdout.splitlines()[1:]:
        fields = line.strip().split(None, 2)
        if len(fields) == 3:
            rows[int(fields[0])] = (int(fields[1]), fields[2])
    paths, seen, pid = [], set(), os.getppid()
    while pid in rows and pid not in seen and len(paths) < 32:
        seen.add(pid)
        pid, executable = rows[pid]
        paths.append(executable)
    return paths


def record_fsmonitor(repo):
    marker = repo / '.git' / 'desktop-probe'
    if not (marker / 'owned-fixture').exists():
        raise ValueError('Not a desktop optimization fixture')
    try:
        paths = process_ancestry()
        event = {
            'observed_at': datetime.now(timezone.utc).isoformat(),
            'stage': os.environ.get('DAO_PROBE_STAGE', 'native_pending'),
            **classify_ancestry(paths),
            'ancestor_names': [Path(p).name for p in paths],
        }
        with (marker / 'events.jsonl').open('a', encoding='utf-8') as handle:
            handle.write(json.dumps(event) + '\n')
    except (OSError, subprocess.SubprocessError):
        # Observability must not change git status behavior.
        pass
    # fsmonitor v2: a token followed by '/' requests a complete worktree scan.
    sys.stdout.buffer.write(b'desktop-probe-token\0/\0')


def events_for(repo):
    path = repo / '.git' / 'desktop-probe' / 'events.jsonl'
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def prepare(repo):
    if repo.exists():
        raise ValueError('Fixture already exists; use report or choose a new --repo')
    repo.mkdir(parents=True)
    subprocess.run(['git', 'init', '--quiet', str(repo)], check=True, timeout=10)
    marker = repo / '.git' / 'desktop-probe'
    marker.mkdir()
    (marker / 'owned-fixture').write_text('synthetic desktop optimization fixture\n')
    for index in range(40):
        (repo / f'fixture-{index:02d}.txt').write_text(f'Synthetic fixture {index}\n')
    command = shlex.join([sys.executable, str(Path(__file__).resolve()), 'fsmonitor', str(repo)])
    subprocess.run(['git', '-C', str(repo), 'config', 'core.fsmonitor', command], check=True, timeout=5)
    subprocess.run(['git', '-C', str(repo), 'config', 'core.untrackedCache', 'false'], check=True, timeout=5)
    controls = []
    for stage, argv in (
        ('direct_control', ['git', 'status', '--short']),
        ('explicit_rtk_control', [shutil.which('rtk') or 'rtk', 'git', 'status', '--short']),
    ):
        env = dict(os.environ, DAO_PROBE_STAGE=stage)
        try:
            result = subprocess.run(argv, cwd=repo, env=env, capture_output=True, text=True, timeout=15)
            controls.append({'stage': stage, 'exit_code': result.returncode, 'output_bytes': len(result.stdout.encode())})
        except FileNotFoundError:
            controls.append({'stage': stage, 'unavailable': True})
    (marker / 'controls.json').write_text(json.dumps(controls, indent=2) + '\n')
    return {'fixture': str(repo), 'controls': controls, 'observations': events_for(repo)}


def report(repo):
    marker = repo / '.git' / 'desktop-probe'
    if not (marker / 'owned-fixture').exists():
        raise ValueError('Not a desktop optimization fixture')
    events = events_for(repo)
    native = [e for e in events if e['stage'] == 'native_pending' and e['native_app_ancestor']]
    controls = json.loads((marker / 'controls.json').read_text())
    return {
        'fixture': str(repo),
        'controls': controls,
        'direct_control_observed': any(e['stage'] == 'direct_control' for e in events),
        'explicit_rtk_control_observed': any(e['stage'] == 'explicit_rtk_control' and e['rtk_ancestor'] for e in events),
        'native_git_execution_observed': bool(native),
        'native_rtk_execution_observed': any(e['rtk_ancestor'] for e in native),
        # Events recorded before per-app classification carry no app name.
        'native_rtk_execution_by_app': {
            app: any(e['rtk_ancestor'] for e in native if e.get('native_app') == app)
            for app in sorted({e.get('native_app') or 'unrecorded' for e in native})
        },
        'headroom_inference': 'not measured by this shell probe',
        'observations': events,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'report', 'fsmonitor'))
    parser.add_argument('repo', nargs='?', type=Path, default=DEFAULT_REPO)
    parser.add_argument('fsmonitor_arguments', nargs='*')
    args = parser.parse_args()
    if args.action == 'fsmonitor':
        record_fsmonitor(args.repo.resolve())
    else:
        result = prepare(args.repo.resolve()) if args.action == 'prepare' else report(args.repo.resolve())
        print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
