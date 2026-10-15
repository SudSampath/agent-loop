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
BASE_URL = PROXY + '/p/codex-desktop-native/v1'
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
        'request_logs': [{
            'request_id': str(item.get('request_id', '')),
            'error': bool(item.get('error')),
            'savings_percent': item.get('savings_percent', 0),
        } for item in stats.get('request_logs', [])],
    }


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


def report(config_path=CONFIG, state_dir=STATE_DIR, inspect_native_app=False):
    state = json.loads((Path(state_dir) / 'codex-routing.json').read_text())
    snapshot = proxy_snapshot()
    baseline = state['proxy_baseline']
    ancestors = native_backends() if inspect_native_app else native_ancestors()
    peers = native_peer_ports(ancestors)
    lines, log_rotated = [], False
    if LOG.exists():
        stat = LOG.stat()
        log_rotated = stat.st_ino != state['log_inode'] or stat.st_size < state['log_offset']
        if not log_rotated:
            with LOG.open('rb') as handle:
                handle.seek(state['log_offset'])
                lines = handle.read(16 * 1024 * 1024).decode(errors='replace').splitlines()
    matched = parse_native_requests(lines, peers)
    websockets = parse_native_websockets(lines, peers)
    native_ids = {request['id'] for request in matched}
    correlated = [entry for entry in snapshot['request_logs'] if entry['request_id'] in native_ids]
    counters_reset = snapshot['requests_total'] < baseline['requests_total']
    return {
        'observed_at': datetime.now(timezone.utc).isoformat(),
        'routing_enabled': active_route(Path(config_path).read_bytes()),
        'headroom_version': snapshot['version'],
        'native_app_ancestry_observed': bool(ancestors),
        'process_observation_scope': 'running native app family' if inspect_native_app else 'executing tool ancestry',
        'native_backend_proxy_socket_observed': bool(peers),
        'native_proxy_http_requests_observed': len(matched),
        'native_proxy_websocket_connections_observed': len(websockets),
        'native_inference_transport_verified': bool(matched or websockets),
        'native_proxy_request_fingerprints': [digest(r['id'].encode()) for r in matched],
        'native_websocket_connection_fingerprints': [digest(r['id'].encode()) for r in websockets],
        'native_request_stats_correlated': len(correlated),
        'native_request_optimization_observed': any((r['savings_percent'] or 0) > 0 for r in correlated),
        'aggregate_requests_since_enable': snapshot['requests_total'] - baseline['requests_total'],
        'aggregate_compression_tokens_since_enable': snapshot['compression_tokens_saved'] - baseline['compression_tokens_saved'],
        'aggregate_savings_attributable_to_native_fixture': False,
        'proxy_counters_reset': counters_reset,
        'proxy_log_rotated': log_rotated,
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
