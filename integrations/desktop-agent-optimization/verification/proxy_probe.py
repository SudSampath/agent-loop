"""Run the desktop-bundled backend through isolated Headroom to a local mock.

This is a synthetic transport/compression probe, not native UI or subscription
verification. The guarded Headroom process can reach only the local mock.
User config and the existing port-8787 proxy are untouched. The temporary
proxy is stateless. DESIGN.md describes the separate ChatGPT upstream and
the process-local guard required to keep synthetic traffic on loopback.
"""

import argparse
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import shlex
import socket
import subprocess
import tempfile
import threading
import time
from urllib.error import URLError
from urllib.request import urlopen

from verification.backend_probe import DEFAULT_BINARY, ProtocolClient, isolated_environment


class LocalProvider(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))))
        # Retain measurements only; prompts and headers are never persisted.
        self.server.observations.append({
            'path': self.path,
            'synthetic_authorization_preserved': self.headers.get('Authorization') == 'Bearer synthetic-local-only',
            'synthetic_account_header_preserved': self.headers.get('ChatGPT-Account-ID') == 'synthetic-local-account',
            'input_characters': len(json.dumps(body.get('input', []))),
            'input_text_characters': sum(
                len(part.get('text', '')) for item in body.get('input', [])
                if isinstance(item, dict) and item.get('role') == 'user'
                for part in item.get('content', []) if isinstance(part, dict)
            ),
        })
        message = {'id': 'msg_local_fixture', 'type': 'message', 'role': 'assistant',
                   'status': 'completed', 'content': [{'type': 'output_text', 'text': 'LOCAL_PROBE_OK', 'annotations': []}]}
        response = {'id': 'resp_local_fixture', 'object': 'response', 'model': body.get('model'),
                    'status': 'completed', 'output': [message],
                    'usage': {'input_tokens': 1, 'output_tokens': 1, 'total_tokens': 2}}
        events = [
            {'type': 'response.created', 'response': {**response, 'status': 'in_progress', 'output': []}},
            {'type': 'response.output_item.done', 'output_index': 0, 'item': message},
            {'type': 'response.completed', 'response': response},
        ]
        encoded = ''.join('data: ' + json.dumps(event) + '\n\n' for event in events).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream')
        self.send_header('Content-Length', str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


def stop(process):
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def local_turn(binary, root, endpoint, prompt):
    home = root / 'home'
    home.mkdir(parents=True)
    (home / 'config.toml').write_text(
        'model="gpt-6.1-sol"\nmodel_provider="desktop_probe"\nweb_search="disabled"\n'
        '[analytics]\nenabled=false\n[model_providers.desktop_probe]\n'
        f'name="Local mock"\nbase_url="{endpoint}"\nwire_api="responses"\n'
        'env_key="DESKTOP_PROBE_API_TOKEN"\nrequires_openai_auth=false\nsupports_websockets=false\n'
        'env_http_headers={"ChatGPT-Account-ID"="DESKTOP_PROBE_ACCOUNT_ID"}\n'
    )
    env = isolated_environment(os.environ, home)
    env['DESKTOP_PROBE_API_TOKEN'] = 'synthetic-local-only'
    env['DESKTOP_PROBE_ACCOUNT_ID'] = 'synthetic-local-account'
    process = subprocess.Popen([str(binary), 'app-server', '--listen', 'stdio://'],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        text=True, cwd=root, env=env)
    client = ProtocolClient(process)
    try:
        client.request(1, 'initialize', {'clientInfo': {'name': 'desktop_transport_probe', 'version': '0.1.0'}})
        client.send({'method': 'initialized', 'params': {}})
        thread = client.request(2, 'thread/start', {
            'ephemeral': True, 'cwd': str(root), 'approvalPolicy': 'on-request',
            'sandbox': 'read-only', 'baseInstructions': 'Local synthetic transport probe. Never execute tools.',
        })
        client.request(3, 'turn/start', {
            'threadId': thread['thread']['id'], 'input': [{'type': 'text', 'text': prompt}],
        })
        completed = client.notification('turn/completed', timeout=30)
        replies = [message.get('params', {}).get('item', {}).get('text', '')
                   for message in client.notifications
                   if message.get('method') == 'item/completed'
                   and message.get('params', {}).get('item', {}).get('type') == 'agentMessage']
        return {'status': completed['params']['turn']['status'],
                'error': completed['params']['turn'].get('error'),
                'expected_mock_reply_received': 'LOCAL_PROBE_OK' in replies}
    finally:
        stop(process)
        process.stdin.close()
        process.stdout.close()
        client.reader.join(timeout=2)


def probe(binary=DEFAULT_BINARY, headroom=None):
    headroom = headroom or shutil.which('headroom')
    if not headroom:
        raise FileNotFoundError('Headroom is not installed')
    shebang = Path(headroom).resolve().read_text().splitlines()[0]
    interpreter = shlex.split(shebang[2:]) if shebang.startswith('#!') else []
    if len(interpreter) != 1 or not Path(interpreter[0]).name.startswith('python'):
        raise RuntimeError('The probe requires Headroom installed with a direct Python launcher')
    runner = Path(__file__).with_name('guarded_headroom.py')
    provider = ThreadingHTTPServer(('127.0.0.1', 0), LocalProvider)
    provider.observations = []
    worker = threading.Thread(target=provider.serve_forever, daemon=True)
    worker.start()
    upstream = f'http://127.0.0.1:{provider.server_port}/v1'
    with tempfile.TemporaryDirectory(prefix='desktop-proxy-probe-') as tmp:
        root = Path(tmp)
        prompt = json.dumps([{'id': i, 'status': 'ok', 'detail': 'synthetic repeated fixture ' * 8} for i in range(200)])
        proxy = None
        try:
            baseline = local_turn(binary, root / 'baseline', upstream, prompt)
            baseline_count = len(provider.observations)
            with socket.socket() as allocation:
                allocation.bind(('127.0.0.1', 0))
                port = allocation.getsockname()[1]
            endpoint = f'http://127.0.0.1:{port}'
            env = isolated_environment(os.environ, root / 'unused')
            env.pop('CODEX_HOME', None)
            env.update({'HEADROOM_CCR_BACKEND': 'memory', 'HEADROOM_COMPRESS_USER_MESSAGES': 'true',
                        'HEADROOM_SAVINGS_PROFILE': 'coding', 'HEADROOM_MIN_TOKENS': '10',
                        'LITELLM_LOCAL_MODEL_COST_MAP': 'True', 'HF_HUB_OFFLINE': '1',
                        'TRANSFORMERS_OFFLINE': '1'})
            with (root / 'proxy-stderr.log').open('w') as log:
                proxy = subprocess.Popen([interpreter[0], str(runner), '--mock-upstream', upstream,
                    'proxy', '--host', '127.0.0.1', '--port', str(port),
                    '--stateless', '--no-telemetry', '--no-cache', '--no-rate-limit',
                    '--disable-kompress', '--disable-kompress-fallback', '--compressor', 'smart_crusher',
                    '--openai-api-url', upstream], stdout=subprocess.DEVNULL, stderr=log, cwd=root, env=env)
                deadline = time.monotonic() + 20
                while True:
                    try:
                        with urlopen(endpoint + '/health', timeout=1) as response:
                            health = json.load(response)
                        break
                    except (OSError, URLError):
                        if proxy.poll() is not None or time.monotonic() >= deadline:
                            raise RuntimeError('Isolated proxy startup failed: ' + (root / 'proxy-stderr.log').read_text()[-4000:])
                        time.sleep(.1)
                with urlopen(endpoint + '/__desktop_probe_guard', timeout=3) as response:
                    protection = json.load(response)
                if not (protection.get('guard_active')
                        and protection.get('external_request_blocked')
                        and protection.get('allowed_mock_port') == provider.server_port
                        and protection.get('pid') == proxy.pid):
                    raise RuntimeError('Outbound mock isolation was not attested; refusing to send a fixture turn')
                optimized = local_turn(binary, root / 'optimized', endpoint + '/v1', prompt)
                with urlopen(endpoint + '/stats', timeout=5) as response:
                    stats = json.load(response)
                return {
                    'observed_at': datetime.now(timezone.utc).isoformat(),
                    'scope': 'desktop-bundled backend -> isolated Headroom -> local mock; not native UI',
                    'outbound_network_guard': 'only the explicit loopback mock port is permitted',
                    'chatgpt_target_injected_for_fixture': True,
                    'outbound_guard_attested': True,
                    'baseline_turn': baseline, 'headroom_turn': optimized,
                    'baseline_upstream_requests': baseline_count,
                    'headroom_upstream_requests': len(provider.observations) - baseline_count,
                    'upstream_measurements': provider.observations,
                    'headroom_version': health.get('version'),
                    'compression_tokens_saved': stats.get('tokens', {}).get('proxy_compression_saved'),
                    'native_ui_workflow_verified': False,
                    'subscription_auth_verified': False,
                    'mock_usage_is_synthetic': True,
                    'paid_provider_requests': 0,
                }
        finally:
            if proxy is not None:
                stop(proxy)
            provider.shutdown()
            provider.server_close()
            worker.join(timeout=2)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', type=Path, default=DEFAULT_BINARY)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = probe(args.binary)
    result['checks_passed'] = (
        all(result[name]['status'] == 'completed'
            and result[name]['expected_mock_reply_received']
            for name in ('baseline_turn', 'headroom_turn'))
        and result['baseline_upstream_requests'] == 1
        and result['headroom_upstream_requests'] == 1
        and (result['compression_tokens_saved'] or 0) > 0
        and all(observation['synthetic_authorization_preserved']
                and observation['synthetic_account_header_preserved']
                for observation in result['upstream_measurements'])
    )
    encoded = json.dumps(result, indent=2) + '\n'
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded)
    print(encoded, end='')
    if not result['checks_passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
