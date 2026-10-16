import json
from http.server import ThreadingHTTPServer
from pathlib import Path
import tempfile
import threading
import tomllib
import unittest
from urllib.request import Request, urlopen

from verification import codex_runtime_probe

ORCA_HOOK = {'type': 'command', 'command': ': orca-agent-hook-form=1; /bin/sh hook.sh || :'}
RTK_HOOK = {'type': 'command', 'command': '/fixture/lib/rtk-codex-hook.py'}


class CodexRuntimeProbeTests(unittest.TestCase):
    def test_only_rtk_hooks_and_their_trust_are_copied(self):
        """Given Orca and RTK hooks with saved trust, when copied, then only RTK's handler and hash move, re-keyed."""
        with tempfile.TemporaryDirectory() as temporary:
            user, probe = Path(temporary) / 'user', Path(temporary) / 'probe'
            user.mkdir(), probe.mkdir()
            (user / 'hooks.json').write_text(json.dumps({'hooks': {'PreToolUse': [
                {'hooks': [ORCA_HOOK]}, {'matcher': 'Bash', 'hooks': [RTK_HOOK]}]}}))
            (user / 'config.toml').write_text(
                f'[hooks.state."{user}/hooks.json:pre_tool_use:0:0"]\ntrusted_hash = "orca-hash"\n'
                f'[hooks.state."{user}/hooks.json:pre_tool_use:1:0"]\ntrusted_hash = "rtk-hash"\n')
            state, copied = codex_runtime_probe.copy_rtk_hooks(user, probe)
            self.assertEqual(copied, 1)
            self.assertEqual(state, {f'{probe}/hooks.json:pre_tool_use:0:0': {'trusted_hash': 'rtk-hash'}})
            self.assertEqual(json.loads((probe / 'hooks.json').read_text()),
                             {'hooks': {'PreToolUse': [{'matcher': 'Bash', 'hooks': [RTK_HOOK]}]}})
            codex_runtime_probe.write_config(probe, 'http://127.0.0.1:1/v1', state)
            config = tomllib.loads((probe / 'config.toml').read_text())
            self.assertEqual(config['hooks']['state'], state)
            self.assertEqual(config['model_providers']['desktop_probe']['base_url'], 'http://127.0.0.1:1/v1')

    def test_scripted_model_requests_one_command_then_finishes(self):
        """Given the shell tool, when the mock is called before and after tool output, then it asks once and then replies."""
        server = ThreadingHTTPServer(('127.0.0.1', 0), codex_runtime_probe.ScriptedModel)
        server.observations, server.workdir = [], '/fixture/repo'
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()

        def call(items):
            body = json.dumps({'model': 'fixture', 'tools': [{'type': 'function', 'name': 'exec_command'}],
                               'input': items}).encode()
            request = Request(f'http://127.0.0.1:{server.server_port}/v1/responses', data=body)
            with urlopen(request, timeout=5) as response:
                events = [json.loads(line[6:]) for line in response.read().decode().splitlines() if line]
            return events[-1]['response']['output'][0]

        try:
            first = call([{'type': 'message', 'role': 'user', 'content': 'PRIVATE prompt'}])
            self.assertEqual(first['name'], 'exec_command')
            self.assertEqual(json.loads(first['arguments']),
                             {'cmd': 'git status --short', 'workdir': '/fixture/repo'})
            second = call([{'type': 'function_call_output', 'call_id': 'call_probe', 'output': 'PRIVATE output'}])
            self.assertEqual(second['type'], 'message')
            self.assertNotIn('PRIVATE', json.dumps(server.observations))
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=2)

    def test_stale_trust_or_native_events_cannot_pass(self):
        """Given a modified trust hash, or RTK only under the native app, when summarized, then the check fails."""
        offered = [{'shell_tool_offered': True, 'tool_output_returned': True}]
        runtime_rtk = [{'bundled_backend_ancestor': True, 'native_app_ancestor': False, 'rtk_ancestor': True}]
        passing = codex_runtime_probe.summarize(runtime_rtk, 1, True, 'completed', ['completed'], offered)
        self.assertTrue(passing['checks_passed'])
        stale = codex_runtime_probe.summarize(runtime_rtk, 1, False, 'completed', ['completed'], offered)
        self.assertFalse(stale['checks_passed'])
        self.assertTrue(stale['bundled_runtime_rtk_observed'])
        native_only = [{'bundled_backend_ancestor': True, 'native_app_ancestor': True, 'rtk_ancestor': True}]
        result = codex_runtime_probe.summarize(native_only, 1, True, 'completed', ['completed'], offered)
        self.assertFalse(result['bundled_runtime_git_observed'])
        self.assertFalse(result['checks_passed'])


if __name__ == '__main__':
    unittest.main()
