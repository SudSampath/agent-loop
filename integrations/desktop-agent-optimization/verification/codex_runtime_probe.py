"""Check that the app-bundled Codex runtime still applies the user's RTK hook.

This runs without the app UI, so it can follow every app update. An isolated
Codex home receives a copy of the user's RTK PreToolUse handlers and their
saved trust. A loopback mock model requests `git status --short` in a
synthetic fixture, and the fixture's fsmonitor callback records whether RTK
ran under the bundled runtime. The user's Codex home is read, never written;
no credentials, conversations, or paid inference are involved.
"""

import argparse
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import tomllib

from verification import native_probe
from verification.backend_probe import DEFAULT_BINARY, ProtocolClient, isolated_environment
from verification.codex_desktop import CODEX_HOME, RTK_HOOK_EXECUTABLES
from verification.proxy_probe import stop

# Newer model families offer no tools to a custom provider; this one offers exec_command.
MODEL = 'gpt-5.5'
COMMAND = 'git status --short'
STAGE = 'bundled_runtime_probe'


def copy_rtk_hooks(user_home, probe_home):
    """Copy only RTK PreToolUse handlers and re-key their saved trust to the probe home."""
    source = user_home / 'hooks.json'
    data = json.loads(source.read_text()) if source.exists() else {}
    config = user_home / 'config.toml'
    trust = tomllib.loads(config.read_text()).get('hooks', {}).get('state', {}) if config.exists() else {}
    groups, state = [], {}
    for group_index, group in enumerate(data.get('hooks', {}).get('PreToolUse', [])):
        handlers = [(index, handler) for index, handler in enumerate(group.get('hooks', []))
                    if Path((handler.get('command') or ' ').split()[0]).name in RTK_HOOK_EXECUTABLES]
        if not handlers:
            continue
        for handler_index, (index, _) in enumerate(handlers):
            saved = trust.get(f'{source}:pre_tool_use:{group_index}:{index}', {})
            if 'trusted_hash' in saved:
                state[f'{probe_home / "hooks.json"}:pre_tool_use:{len(groups)}:{handler_index}'] = saved
        groups.append({**group, 'hooks': [handler for _, handler in handlers]})
    (probe_home / 'hooks.json').write_text(json.dumps({'hooks': {'PreToolUse': groups}}))
    return state, sum(len(group['hooks']) for group in groups)


def write_config(probe_home, endpoint, state):
    lines = [f'model="{MODEL}"', 'model_provider="desktop_probe"', 'web_search="disabled"',
             '[analytics]', 'enabled=false', '[model_providers.desktop_probe]', 'name="Local mock"',
             f'base_url="{endpoint}"', 'wire_api="responses"', 'env_key="DESKTOP_PROBE_API_TOKEN"',
             'requires_openai_auth=false', 'supports_websockets=false']
    for key, entry in state.items():
        lines.append(f'[hooks.state.{json.dumps(key)}]')
        lines += [f'{name}={json.dumps(value)}' for name, value in entry.items()
                  if name in ('trusted_hash', 'enabled')]
    (probe_home / 'config.toml').write_text('\n'.join(lines) + '\n')


class ScriptedModel(BaseHTTPRequestHandler):
    """Ask for one shell command, then finish once its output is returned."""

    def log_message(self, *args):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))))
        tools = {tool.get('name') for tool in body.get('tools') or []}
        returned = any(isinstance(item, dict) and item.get('type') == 'function_call_output'
                       for item in body.get('input', []))
        # Only shapes are kept; prompts and tool output are never persisted.
        self.server.observations.append({'shell_tool_offered': 'exec_command' in tools,
                                         'tool_output_returned': returned})
        if 'exec_command' in tools and not returned:
            item = {'type': 'function_call', 'id': 'fc_probe', 'call_id': 'call_probe', 'status': 'completed',
                    'name': 'exec_command', 'arguments': json.dumps({'cmd': COMMAND, 'workdir': self.server.workdir})}
        else:
            item = {'type': 'message', 'id': 'msg_probe', 'role': 'assistant', 'status': 'completed',
                    'content': [{'type': 'output_text', 'text': 'LOCAL_PROBE_OK', 'annotations': []}]}
        response = {'id': 'resp_probe', 'object': 'response', 'model': body.get('model'), 'status': 'completed',
                    'output': [item], 'usage': {'input_tokens': 1, 'output_tokens': 1, 'total_tokens': 2}}
        events = [{'type': 'response.created', 'response': {**response, 'status': 'in_progress', 'output': []}},
                  {'type': 'response.output_item.done', 'output_index': 0, 'item': item},
                  {'type': 'response.completed', 'response': response}]
        encoded = ''.join('data: ' + json.dumps(event) + '\n\n' for event in events).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream')
        self.send_header('Content-Length', str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


def start_backend(binary, probe_home, cwd):
    env = isolated_environment(os.environ, probe_home)
    env.update({'DESKTOP_PROBE_API_TOKEN': 'synthetic-local-only', 'DAO_PROBE_STAGE': STAGE})
    process = subprocess.Popen([str(binary), 'app-server', '--listen', 'stdio://'],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        text=True, cwd=cwd, env=env)
    client = ProtocolClient(process)
    client.request(1, 'initialize', {'clientInfo': {'name': 'desktop_runtime_rtk_probe', 'version': '0.1.0'},
                                     'capabilities': {'experimentalApi': True}})
    client.send({'method': 'initialized', 'params': {}})
    return process, client


def close_backend(process, client):
    stop(process)
    process.stdin.close()
    process.stdout.close()
    client.reader.join(timeout=2)


def rtk_hook_metadata(client, cwd):
    listed = client.request(2, 'hooks/list', {'cwds': [str(cwd)]})
    return [hook for entry in listed.get('data', []) for hook in entry.get('hooks', [])
            if hook.get('eventName') == 'preToolUse' and hook.get('source') == 'user']


def run_turn(client, repo):
    thread = client.request(3, 'thread/start', {
        'ephemeral': True, 'cwd': str(repo), 'approvalPolicy': 'never',
        # The mock fixes the command; the fsmonitor callback must write inside .git.
        'sandbox': 'danger-full-access',
    })
    client.request(4, 'turn/start', {'threadId': thread['thread']['id'],
                                     'input': [{'type': 'text', 'text': 'Run the fixture command.'}]})
    completed = client.notification('turn/completed', timeout=60)
    hooks = [message['params']['run'] for message in client.notifications
             if message.get('method') == 'hook/completed'
             and message.get('params', {}).get('run', {}).get('eventName') == 'preToolUse']
    return completed['params']['turn']['status'], sorted({run.get('status') for run in hooks})


def trust_accepted(hooks):
    """Codex runs a user hook only while its saved hash matches; `modified` and `untrusted` are skipped."""
    return bool(hooks) and all(hook.get('trustStatus') == 'trusted' for hook in hooks)


def summarize(events, hooks_copied, saved_trust, turn_status, hook_runs, observations):
    runtime = [event for event in events if event.get('bundled_backend_ancestor')
               and not event.get('native_app_ancestor')]
    result = {
        'rtk_hooks_copied': hooks_copied,
        'saved_trust_valid_for_runtime': saved_trust,
        'shell_tool_offered': any(o['shell_tool_offered'] for o in observations),
        'tool_output_returned': any(o['tool_output_returned'] for o in observations),
        'turn_status': turn_status,
        'pre_tool_use_hook_runs': hook_runs,
        'bundled_runtime_git_observed': bool(runtime),
        'bundled_runtime_rtk_observed': any(event['rtk_ancestor'] for event in runtime),
    }
    result['checks_passed'] = bool(
        hooks_copied and saved_trust and result['shell_tool_offered'] and turn_status == 'completed'
        and hook_runs == ['completed'] and result['bundled_runtime_rtk_observed'])
    return result


def probe(binary=DEFAULT_BINARY, user_home=CODEX_HOME):
    version = subprocess.run([str(binary), '--version'], capture_output=True, text=True,
                             check=True, timeout=10).stdout.strip()
    model = ThreadingHTTPServer(('127.0.0.1', 0), ScriptedModel)
    model.observations = []
    worker = threading.Thread(target=model.serve_forever, daemon=True)
    worker.start()
    try:
        with tempfile.TemporaryDirectory(prefix='desktop-runtime-rtk-') as tmp:
            root = Path(tmp).resolve()
            probe_home, repo = root / 'codex-home', root / 'fixture'
            probe_home.mkdir()
            native_probe.prepare(repo)
            model.workdir = str(repo)
            endpoint = f'http://127.0.0.1:{model.server_port}/v1'
            state, copied = copy_rtk_hooks(user_home, probe_home)
            write_config(probe_home, endpoint, state)
            process, client = start_backend(binary, probe_home, root)
            try:
                hooks = rtk_hook_metadata(client, repo)
            finally:
                close_backend(process, client)
            saved_trust = trust_accepted(hooks)
            # Trust the copies regardless so a stale hash and a broken hook path are reported separately.
            write_config(probe_home, endpoint, {hook['key']: {'trusted_hash': hook['currentHash']} for hook in hooks})
            process, client = start_backend(binary, probe_home, root)
            try:
                turn_status, hook_runs = run_turn(client, repo)
            finally:
                close_backend(process, client)
            events = native_probe.events_for(repo)
            return {
                'observed_at': datetime.now(timezone.utc).isoformat(),
                'backend_version': version,
                'scope': 'app-bundled Codex runtime with a copy of the user RTK hook and trust; not the app UI',
                'hook_trust_statuses': sorted({h.get('trustStatus') for h in hooks}),
                **summarize(events, copied, saved_trust, turn_status, hook_runs, model.observations),
                'native_ui_workflow_verified': False,
                'paid_provider_requests': 0,
            }
    finally:
        model.shutdown()
        model.server_close()
        worker.join(timeout=2)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', type=Path, default=DEFAULT_BINARY)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = probe(args.binary)
    encoded = json.dumps(result, indent=2) + '\n'
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded)
    print(encoded, end='')
    if not result['checks_passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
