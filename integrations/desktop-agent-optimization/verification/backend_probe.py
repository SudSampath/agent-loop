"""Probe the desktop-bundled Codex backend with an isolated, unauthenticated home.

Only initialize, config/read and hooks/list are called. This performs no model
turns, paid inference, hook execution, or writes to the user's agent home.
"""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import queue
import subprocess
import tempfile
import threading
import time


DEFAULT_BINARY = Path('/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex')
FIXTURE_URL = 'http://127.0.0.1:1/v1'
CHATGPT_FIXTURE_URL = 'http://127.0.0.1:1/backend-api/codex'
SAFE_ENVIRONMENT = {'PATH', 'HOME', 'USER', 'LOGNAME', 'SHELL', 'TMPDIR', 'LANG', 'LC_ALL'}


def isolated_environment(parent, codex_home):
    result = {key: value for key, value in parent.items() if key in SAFE_ENVIRONMENT}
    result['CODEX_HOME'] = str(codex_home)
    return result


class ProtocolClient:
    def __init__(self, process):
        self.process = process
        self.messages = queue.Queue()
        self.notifications = []
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()

    def _read(self):
        for line in self.process.stdout:
            try:
                self.messages.put(json.loads(line))
            except json.JSONDecodeError:
                continue
        self.messages.put(None)

    def send(self, value):
        self.process.stdin.write(json.dumps(value) + '\n')
        self.process.stdin.flush()

    def request(self, request_id, method, params, timeout=15):
        self.send({'id': request_id, 'method': method, 'params': params})
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f'{method} timed out')
            try:
                message = self.messages.get(timeout=remaining)
            except queue.Empty as error:
                raise TimeoutError(f'{method} timed out') from error
            if message is None:
                raise RuntimeError(f'Backend closed before {method} completed')
            if message.get('id') == request_id:
                if 'error' in message:
                    raise RuntimeError(f'{method}: {message["error"]}')
                return message['result']
            self.notifications.append(message)

    def notification(self, method, timeout=20):
        deadline = time.monotonic() + timeout
        while True:
            for index, message in enumerate(self.notifications):
                if message.get('method') == method:
                    return self.notifications.pop(index)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f'{method} timed out')
            try:
                message = self.messages.get(timeout=remaining)
            except queue.Empty as error:
                raise TimeoutError(f'{method} timed out') from error
            if message is None:
                raise RuntimeError(f'Backend closed before {method}')
            self.notifications.append(message)



def summarize(config, hooks, expected_endpoint=FIXTURE_URL):
    provider = config.get('model_providers', {}).get('desktop_probe', {})
    discovered = [hook for group in hooks.get('data', []) for hook in group.get('hooks', [])]
    return {
        'provider_override_loaded': config.get('model_provider') == 'desktop_probe',
        'fixture_endpoint_loaded': provider.get('base_url') == expected_endpoint,
        'openai_auth_required': provider.get('requires_openai_auth'),
        'hook_discovered': any(h.get('eventName') == 'preToolUse' and h.get('matcher') == 'Bash' for h in discovered),
        'hook_trust_states': sorted({h.get('trustStatus', 'unknown') for h in discovered}),
        'hook_executed': False,
        'inference_requested': False,
        'native_ui_workflow_verified': False,
        'scope': 'isolated desktop-bundled backend protocol; not the running native UI',
    }


def probe(binary=DEFAULT_BINARY, require_chatgpt_auth=False):
    version = subprocess.run([str(binary), '--version'], capture_output=True, text=True, check=True, timeout=10).stdout.strip()
    with tempfile.TemporaryDirectory(prefix='desktop-agent-backend-') as tmp:
        home = Path(tmp) / 'codex-home'
        home.mkdir()
        endpoint = CHATGPT_FIXTURE_URL if require_chatgpt_auth else FIXTURE_URL
        auth_required = 'true' if require_chatgpt_auth else 'false'
        (home / 'config.toml').write_text(
            'model_provider="desktop_probe"\nweb_search="disabled"\n'
            '[analytics]\nenabled=false\n'
            '[model_providers.desktop_probe]\nname="Local fixture"\n'
            f'base_url="{endpoint}"\nwire_api="responses"\n'
            f'requires_openai_auth={auth_required}\nsupports_websockets=false\n'
        )
        (home / 'hooks.json').write_text(json.dumps({'hooks': {'PreToolUse': [
            {'matcher': 'Bash', 'hooks': [{'type': 'command', 'command': '/usr/bin/true'}]},
        ]}}))
        process = subprocess.Popen(
            [str(binary), 'app-server', '--listen', 'stdio://'],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, cwd=tmp, env=isolated_environment(os.environ, home),
        )
        client = ProtocolClient(process)
        try:
            client.request(1, 'initialize', {
                'clientInfo': {'name': 'desktop_optimization_probe', 'version': '0.1.0'},
                'capabilities': {'experimentalApi': True},
            })
            client.send({'method': 'initialized', 'params': {}})
            config = client.request(2, 'config/read', {'includeLayers': False})
            hooks = client.request(3, 'hooks/list', {'cwds': [tmp]})
            return {
                'observed_at': datetime.now(timezone.utc).isoformat(),
                'backend_version': version,
                'chatgpt_auth_configuration_requested': require_chatgpt_auth,
                'subscription_auth_verified': False,
                **summarize(config['config'], hooks, endpoint),
            }
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
            process.stdin.close()
            process.stdout.close()
            client.reader.join(timeout=2)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', type=Path, default=DEFAULT_BINARY)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--chatgpt-route', action='store_true',
                        help='Discover an auth-required ChatGPT gateway route without signing in or making inference requests')
    args = parser.parse_args()
    result = probe(args.binary, args.chatgpt_route)
    encoded = json.dumps(result, indent=2) + '\n'
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded)
    print(encoded, end='')
    if not (result['provider_override_loaded'] and result['fixture_endpoint_loaded']
            and result['hook_discovered']
            and result['openai_auth_required'] is args.chatgpt_route):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
