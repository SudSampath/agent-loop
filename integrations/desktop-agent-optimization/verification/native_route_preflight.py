"""Verify the native routing setting with the bundled backend, without inference."""

import json
import os
from pathlib import Path
import subprocess
import tempfile

from adapters.codex.routing import BASE_URL
from verification.backend_probe import DEFAULT_BINARY, ProtocolClient, isolated_environment


def probe():
    with tempfile.TemporaryDirectory(prefix='native-route-preflight-') as temporary:
        home = Path(temporary) / 'home'
        home.mkdir()
        (home / 'config.toml').write_text(
            f'openai_base_url="{BASE_URL}"\nweb_search="disabled"\n'
            '[analytics]\nenabled=false\n')
        process = subprocess.Popen(
            [str(DEFAULT_BINARY), 'app-server', '--listen', 'stdio://'],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, cwd=temporary, env=isolated_environment(os.environ, home))
        client = ProtocolClient(process)
        try:
            client.request(1, 'initialize', {
                'clientInfo': {'name': 'native_route_preflight', 'version': '0.1.0'},
                'capabilities': {'experimentalApi': True}})
            client.send({'method': 'initialized', 'params': {}})
            config = client.request(2, 'config/read', {'includeLayers': False})['config']
            result = {
                'scope': 'isolated bundled-backend configuration discovery only',
                'built_in_provider_retained': config.get('model_provider') in (None, 'openai'),
                'native_base_url_accepted': config.get('openai_base_url') == BASE_URL,
                'inference_performed': False,
                'credentials_loaded': False,
                'subscription_auth_verified': False,
            }
            if not (result['built_in_provider_retained'] and result['native_base_url_accepted']):
                raise RuntimeError('The bundled backend did not accept the built-in route')
            return result
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


if __name__ == '__main__':
    print(json.dumps(probe(), indent=2))
