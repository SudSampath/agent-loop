"""Test-only Headroom launcher: loopback egress guard and synthetic OAuth target.

Run with Headroom's installed Python environment. This changes only this
temporary process; it does not edit the installed package or user settings.
"""

import argparse
import os
from pathlib import Path
import sys
from urllib.parse import urlsplit


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from verification.network_guard import install_guard, loopback_host, validate_destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mock-upstream', required=True)
    args, remaining = parser.parse_known_args()
    target = urlsplit(args.mock_upstream)
    if target.scheme != 'http' or not loopback_host(target.hostname or '') or not target.port:
        raise SystemExit('The synthetic upstream must be an explicit HTTP loopback port')
    install_guard(target.port)

    # HTTPX must be guarded above its transport: uvloop can perform connections
    # in native code without calling Python's socket.connect wrapper.
    import httpx
    original_async_send = httpx.AsyncClient.send
    original_send = httpx.Client.send

    async def guarded_async_send(client, request, *positional, **keywords):
        validate_destination((request.url.host, request.url.port), target.port)
        return await original_async_send(client, request, *positional, **keywords)

    def guarded_send(client, request, *positional, **keywords):
        validate_destination((request.url.host, request.url.port), target.port)
        return original_send(client, request, *positional, **keywords)

    httpx.AsyncClient.send = guarded_async_send
    httpx.Client.send = guarded_send

    # ChatGPT auth deliberately selects a separate upstream in Headroom 0.37.
    # Inject that target in memory as well as setting the normal OpenAI target.
    import headroom.providers.codex.endpoints as endpoints
    import headroom.providers.proxy_targets as targets
    root = f'http://{target.netloc}'
    endpoints.CHATGPT_BACKEND_API_URL = root
    endpoints.CHATGPT_BACKEND_WS_URL = f'ws://{target.netloc}'
    targets.CHATGPT_BACKEND_API_URL = root

    from headroom.proxy import server
    original_create_app = server.create_app

    async def attest_guard():
        active = httpx.AsyncClient.send is guarded_async_send
        blocked = False
        if active:
            try:
                async with httpx.AsyncClient() as client:
                    await client.get('https://example.invalid/fixture-egress-check')
            except OSError:
                blocked = True
        return {'guard_active': active, 'external_request_blocked': blocked,
                'allowed_mock_port': target.port, 'pid': os.getpid()}

    def guarded_create_app(*positional, **keywords):
        app = original_create_app(*positional, **keywords)
        app.add_api_route('/__desktop_probe_guard', attest_guard, methods=['GET'])
        # Headroom has a catch-all route; the probe must precede it.
        app.router.routes.insert(0, app.router.routes.pop())
        return app

    server.create_app = guarded_create_app

    from headroom.cli import main as headroom_main
    # Keep the actual embedding script identity. Calling this 'headroom' makes
    # the upstream CLI re-exec itself to set thread env, discarding guards.
    sys.argv = [str(Path(__file__).resolve()), *remaining]
    headroom_main()


if __name__ == '__main__':
    main()
