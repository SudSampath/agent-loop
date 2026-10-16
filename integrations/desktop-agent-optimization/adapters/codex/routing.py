"""Enable reversible native Codex routing without changing authentication.

Only the built-in OpenAI provider's base URL is changed. Credentials, hooks,
model selection, and Orca's separate runtime home are never modified.
"""

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import tomllib
from urllib.request import urlopen

PROXY = 'http://127.0.0.1:8787'
PROJECT = 'codex-desktop-native'
BASE_URL = PROXY + f'/p/{PROJECT}/v1'
BLOCK = ('# desktop-agent-optimization: native Codex routing\n'
         f'openai_base_url = "{BASE_URL}"\n'
         '# desktop-agent-optimization: end\n')
CONFIG = Path.home() / '.codex/config.toml'
STATE_DIR = Path.home() / '.local/state/desktop-agent-optimization'
LOG = Path.home() / '.headroom/logs/proxy.log'
NATIVE_APPS = {
    '/Applications/ChatGPT.app/Contents/MacOS/ChatGPT',
    '/Applications/Codex.app/Contents/MacOS/Codex',
}
# Headroom 0.37.0 PERF fields and WebSocket termination causes; nothing else is kept.
PERF_FIELDS = {'tok_before': 'tokens_before', 'tok_after': 'tokens_after',
               'tok_saved': 'tokens_saved', 'total_saved': 'total_tokens_saved',
               'tok_inflated': 'tokens_inflated', 'cache_read': 'cache_read_tokens',
               'tok_out': 'output_tokens'}
CLOSE_CAUSES = {'client_disconnect', 'upstream_disconnect', 'upstream_error', 'client_error',
                'client_cancel', 'response_completed', 'client_timeout', 'unknown'}
PROJECT_FIELDS = ('requests', 'tokens_saved', 'total_input_tokens')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def enable_text(original):
    """Refuse competing routes and preserve every unrelated configuration byte."""
    config = tomllib.loads(original.decode())
    if config.get('model_provider', 'openai') != 'openai':
        raise ValueError('A custom model provider is already selected')
    if config.get('model_providers', {}).get('openai'):
        raise ValueError('The built-in provider has custom overrides; review required')
    if 'openai_base_url' in config:
        raise ValueError('A provider route already exists; refusing to overwrite it')
    updated = BLOCK.encode() + original
    parsed = tomllib.loads(updated.decode())
    if parsed.pop('openai_base_url') != BASE_URL or parsed != config:
        raise ValueError('Routing edit changed unrelated settings')
    return updated


def disable_text(current):
    block = BLOCK.encode()
    if current.count(block) != 1:
        raise ValueError('Managed routing block changed; refusing to overwrite user edits')
    original = current.replace(block, b'', 1)
    before = tomllib.loads(current.decode())
    if before.pop('openai_base_url', None) != BASE_URL:
        raise ValueError('Routing value changed')
    if tomllib.loads(original.decode()) != before:
        raise ValueError('Rollback would change unrelated settings')
    return original


def active_route(data):
    config = tomllib.loads(data.decode())
    return (config.get('model_provider', 'openai') == 'openai'
            and not config.get('model_providers', {}).get('openai')
            and config.get('openai_base_url') == BASE_URL)


def atomic_write(path, data, mode=0o600):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=path.name + '.', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'wb') as handle:
            os.fchmod(handle.fileno(), mode)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


@contextmanager
def mutation_lock(state_dir):
    state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock = state_dir / 'routing.lock'
    descriptor = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.close(descriptor)
        yield
    finally:
        lock.unlink()


def proxy_snapshot():
    with urlopen(PROXY + '/health', timeout=5) as response:
        health = json.load(response)
    if health.get('status') != 'healthy' or health.get('ready') is False:
        raise RuntimeError('Existing Headroom service is not ready; routing was not changed')
    with urlopen(PROXY + '/stats', timeout=5) as response:
        stats = json.load(response)
    return {
        'version': health.get('version'),
        'requests_total': stats.get('requests', {}).get('total', 0),
        'requests_failed': stats.get('requests', {}).get('failed', 0),
        'compression_tokens_saved': stats.get('tokens', {}).get('proxy_compression_saved', 0),
    }


def project_counters(name):
    """Headroom's lifetime counters for one /p/<name> route; its clients share them."""
    with urlopen(PROXY + '/stats-lifetime', timeout=5) as response:
        project = json.load(response).get('projects', {}).get(name, {})
    return {field: project.get(field, 0) for field in PROJECT_FIELDS}


def enable(config_path=CONFIG, state_dir=STATE_DIR):
    config_path, state_dir = Path(config_path), Path(state_dir)
    if config_path.is_symlink():
        raise ValueError('Refusing to replace a symlinked configuration')
    with mutation_lock(state_dir):
        state_path = state_dir / 'codex-routing.json'
        saved = json.loads(state_path.read_text()) if state_path.exists() else {}
        owned = BLOCK.encode() in config_path.read_bytes()
        if saved and (saved.get('enabled') or owned):
            if not owned or not active_route(config_path.read_bytes()):
                raise ValueError('Saved routing state conflicts with current configuration')
            if not saved.get('enabled'):
                saved['enabled'] = True
                atomic_write(state_path, (json.dumps(saved, indent=2) + '\n').encode())
            return {'enabled': True, 'changed': False, 'base_url': BASE_URL}
        original = config_path.read_bytes()
        updated = enable_text(original)
        snapshot = proxy_snapshot()
        mode = config_path.stat().st_mode & 0o777
        log_stat = LOG.stat() if LOG.exists() else None
        state = {
            'enabled': False,
            'started_at': datetime.now(timezone.utc).isoformat(),
            'original_hash': digest(original),
            'applied_hash': digest(updated),
            'proxy_baseline': snapshot,
            'log_offset': log_stat.st_size if log_stat else 0,
            'log_inode': log_stat.st_ino if log_stat else None,
        }
        # Private backup/state stay outside the project; no authentication files copied.
        atomic_write(state_dir / 'codex-config.before-routing.toml', original)
        atomic_write(state_path, (json.dumps(state, indent=2) + '\n').encode())
        if config_path.read_bytes() != original:
            raise ValueError('Configuration changed concurrently; retry after reviewing it')
        atomic_write(config_path, updated, mode)
        state['enabled'] = True
        atomic_write(state_path, (json.dumps(state, indent=2) + '\n').encode())
        return {'enabled': True, 'changed': True, 'base_url': BASE_URL,
                'headroom_version': snapshot['version'],
                'authentication_configuration_changed': False}


def disable(config_path=CONFIG, state_dir=STATE_DIR):
    config_path, state_dir = Path(config_path), Path(state_dir)
    if config_path.is_symlink():
        raise ValueError('Refusing to replace a symlinked configuration')
    with mutation_lock(state_dir):
        state_path = state_dir / 'codex-routing.json'
        state = json.loads(state_path.read_text())
        if not state.get('enabled') and BLOCK.encode() not in config_path.read_bytes():
            return {'enabled': False, 'changed': False}
        current = config_path.read_bytes()
        restored = disable_text(current)
        if config_path.read_bytes() != current:
            raise ValueError('Configuration changed concurrently; refusing rollback')
        atomic_write(config_path, restored, config_path.stat().st_mode & 0o777)
        state['enabled'] = False
        atomic_write(state_path, (json.dumps(state, indent=2) + '\n').encode())
        return {'enabled': False, 'changed': True,
                'original_bytes_restored': digest(restored) == state['original_hash']}


def process_table():
    result = subprocess.run(['ps', '-axo', 'pid=,ppid=,comm='],
                            capture_output=True, text=True, check=True, timeout=5)
    processes = {}
    for line in result.stdout.splitlines():
        parts = line.strip().split(None, 2)
        if len(parts) == 3:
            processes[int(parts[0])] = (int(parts[1]), parts[2])
    return processes


def native_ancestors():
    processes = process_table()
    chain, seen, pid = [], set(), os.getpid()
    while pid in processes and pid not in seen:
        seen.add(pid)
        parent, executable = processes[pid]
        chain.append((pid, executable))
        pid = parent
    if not any(path in NATIVE_APPS for _, path in chain):
        return []
    return [(pid, path) for pid, path in chain
            if path in NATIVE_APPS or Path(path).name == 'codex']


def native_backends():
    """Inspect running app descendants without treating an Orca CLI as native."""
    processes = process_table()
    roots = {pid for pid, (_, path) in processes.items() if path in NATIVE_APPS}
    family = set(roots)
    while True:
        children = {pid for pid, (parent, _) in processes.items() if parent in family}
        if children <= family:
            break
        family |= children
    return [(pid, path) for pid, (_, path) in processes.items()
            if pid in family and (pid in roots or Path(path).name == 'codex')]


def native_peer_ports(ancestors):
    if not ancestors:
        return set()
    result = subprocess.run([
        'lsof', '-nP', '-a', '-p', ','.join(str(pid) for pid, _ in ancestors),
        '-iTCP:8787', '-sTCP:ESTABLISHED', '-Fpn'],
        capture_output=True, text=True, timeout=10)
    return {int(match.group(1)) for match in re.finditer(
        r'^n127\.0\.0\.1:(\d+)->127\.0\.0\.1:8787$', result.stdout, re.M)}


def parse_native_requests(lines, peer_ports):
    """Extract allowlisted transport metadata, never headers or request bodies."""
    requests = []
    for line in lines:
        if 'event=proxy_inbound_request ' not in line:
            continue
        peer = re.search(r'\bclient=127\.0\.0\.1:(\d+)\b', line)
        if not peer or int(peer.group(1)) not in peer_ports:
            continue
        method = re.search(r'\bmethod=(GET|POST)\b', line)
        path = re.search(r'\bpath=([^\s?]+)', line)
        request_id = re.search(r'\bid=([A-Za-z0-9_-]+)\b', line)
        if method and path and request_id and path.group(1).endswith('/responses'):
            requests.append({'id': request_id.group(1), 'method': method.group(1),
                             'path': path.group(1)})
    return requests


def parse_native_websockets(lines, peer_ports):
    connections = []
    for line in lines:
        if 'event=proxy_inbound_websocket ' not in line:
            continue
        peer = re.search(r"\bclient=Address\(host='127\.0\.0\.1', port=(\d+)\)", line)
        request_id = re.search(r'\brequest_id=([A-Za-z0-9_-]+)\b', line)
        path = re.search(r'\bpath=([^\s?]+)', line)
        if (peer and int(peer.group(1)) in peer_ports and request_id
                and path and path.group(1).endswith('/responses')):
            connections.append({'id': request_id.group(1), 'path': path.group(1)})
    return connections


def log_lines_since(log, inode, offset):
    """Read from the enable offset, following RotatingFileHandler renames."""
    files = [path for path in [log, *(log.with_name(f'{log.name}.{n}') for n in range(1, 10))]
             if path.exists()]
    start = next((index for index, path in enumerate(files) if path.stat().st_ino == inode), None)
    if start is None or files[start].stat().st_size < offset:
        return [], False
    lines = []
    for index in range(start, -1, -1):
        with files[index].open('rb') as handle:
            handle.seek(offset if index == start else 0)
            lines += handle.read().decode(errors='replace').splitlines()
    return lines, True


def session_outcomes(lines, fingerprints):
    """Join native WebSocket connections to Headroom's per-turn PERF records.

    Each WebSocket turn's outcome row gets a fresh request ID, but its PERF
    line keeps the connection's inbound request ID. Only counts are kept.
    """
    sessions = {fingerprint: {'fingerprint': fingerprint, 'outcome_records': 0,
                              **dict.fromkeys(PERF_FIELDS.values(), 0),
                              'client_frames': None, 'cancel_frames': None, 'close_cause': None}
                for fingerprint in fingerprints}
    for line in lines:
        perf = re.search(r'\[([A-Za-z0-9_-]+)\] PERF (.*)', line)
        completed = re.search(r'\[([A-Za-z0-9_-]+)\] WS /v1/responses completed \((.*)\)', line)
        closed = re.search(r'event=proxy_inbound_websocket_closed request_id=([A-Za-z0-9_-]+) '
                           r'.*?\bcause=([a-z_]+)', line)
        match = perf or completed or closed
        session = match and sessions.get(digest(match.group(1).encode()))
        if not session:
            continue
        if perf:
            session['outcome_records'] += 1
            # The encoded savings breakdown and transform labels follow; labels can hold paths.
            counts = perf.group(2).split(' savings=', 1)[0]
            for name, value in re.findall(r'\b([a-z_]+)=(\d+)\b', counts):
                if name in PERF_FIELDS:
                    session[PERF_FIELDS[name]] += int(value)
        elif completed:
            # Frame counts only; the line also names frame types.
            for name, value in re.findall(r'\b(client_frames|cancel_frames)=(\d+)\b', completed.group(2)):
                session[name] = int(value)
        else:
            session['close_cause'] = closed.group(2) if closed.group(2) in CLOSE_CAUSES else 'unrecognized'
    return list(sessions.values())


def remember_sessions(state_dir, fingerprints):
    """Keep native connection fingerprints so outcomes stay attributable after sockets close."""
    path = Path(state_dir) / 'codex-routing.json'
    known = json.loads(path.read_text()).get('native_websocket_fingerprints', [])
    if set(fingerprints) <= set(known):
        return known
    with mutation_lock(Path(state_dir)):
        state = json.loads(path.read_text())
        known = state.setdefault('native_websocket_fingerprints', [])
        known.extend(fingerprint for fingerprint in dict.fromkeys(fingerprints) if fingerprint not in known)
        atomic_write(path, (json.dumps(state, indent=2) + '\n').encode())
        return known


def report(config_path=CONFIG, state_dir=STATE_DIR, inspect_native_app=False):
    state = json.loads((Path(state_dir) / 'codex-routing.json').read_text())
    try:
        snapshot = proxy_snapshot()
    except (OSError, RuntimeError):
        # Log-based attribution still works while the proxy is down.
        snapshot = None
    baseline = state['proxy_baseline']
    ancestors = native_backends() if inspect_native_app else native_ancestors()
    peers = native_peer_ports(ancestors)
    lines, log_complete = log_lines_since(LOG, state['log_inode'], state['log_offset'])
    matched = parse_native_requests(lines, peers)
    websockets = parse_native_websockets(lines, peers)
    fingerprints = [digest(r['id'].encode()) for r in websockets]
    sessions = session_outcomes(lines, remember_sessions(state_dir, fingerprints))

    def since_enable(name):
        return snapshot[name] - baseline[name] if snapshot else None

    return {
        'observed_at': datetime.now(timezone.utc).isoformat(),
        'routing_enabled': active_route(Path(config_path).read_bytes()),
        'proxy_ready': snapshot is not None,
        'headroom_version': snapshot['version'] if snapshot else None,
        'native_app_ancestry_observed': bool(ancestors),
        'process_observation_scope': 'running native app family' if inspect_native_app else 'executing tool ancestry',
        'native_backend_proxy_socket_observed': bool(peers),
        'native_proxy_http_requests_observed': len(matched),
        'native_proxy_websocket_connections_observed': len(websockets),
        'native_inference_transport_verified': bool(matched or websockets),
        'native_proxy_request_fingerprints': [digest(r['id'].encode()) for r in matched],
        'native_websocket_connection_fingerprints': fingerprints,
        'native_http_request_attribution_supported': False,
        'native_sessions': sessions,
        'native_session_optimization_attributed': any(s['outcome_records'] for s in sessions),
        'native_session_tokens_saved': sum(s['total_tokens_saved'] for s in sessions),
        # Every Codex client using this home shares the route; the name exists only for it.
        'route_project_lifetime': project_counters(PROJECT) if snapshot else None,
        'aggregate_requests_since_enable': since_enable('requests_total'),
        'aggregate_compression_tokens_since_enable': since_enable('compression_tokens_saved'),
        'aggregate_savings_attributable_to_native_fixture': False,
        'proxy_counters_reset': since_enable('requests_total') < 0 if snapshot else None,
        'proxy_log_since_enable_complete': log_complete,
        'authentication_configuration_changed': False,
        'subscription_inference_verified': False,
        'boot_verified': False,
        'automatic_outage_fallback_implemented': False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['enable', 'disable', 'report'])
    parser.add_argument('--output', type=Path)
    parser.add_argument('--inspect-native-app', action='store_true',
                        help='Correlate running native app descendants instead of caller ancestry')
    args = parser.parse_args()
    if args.action == 'report':
        result = report(inspect_native_app=args.inspect_native_app)
    else:
        result = {'enable': enable, 'disable': disable}[args.action]()
    encoded = json.dumps(result, indent=2) + '\n'
    if args.output:
        atomic_write(args.output, encoded.encode())
    print(encoded, end='')


if __name__ == '__main__':
    main()
