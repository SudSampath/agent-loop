import io
import json
from types import SimpleNamespace
import unittest

from verification.backend_probe import CHATGPT_FIXTURE_URL, FIXTURE_URL, ProtocolClient, isolated_environment, summarize


class BackendProbeTests(unittest.TestCase):
    def test_auth_required_gateway_configuration_is_distinct_from_a_login(self):
        """Given an auth-required gateway, when discovered without a turn, then authentication is still unverified."""
        result = summarize({'model_provider': 'desktop_probe', 'model_providers': {
            'desktop_probe': {'base_url': CHATGPT_FIXTURE_URL, 'requires_openai_auth': True},
        }}, {'data': []}, CHATGPT_FIXTURE_URL)
        self.assertTrue(result['openai_auth_required'])
        self.assertTrue(result['fixture_endpoint_loaded'])
        self.assertFalse(result['inference_requested'])
        self.assertFalse(result['native_ui_workflow_verified'])

    def test_notifications_before_response_are_retained(self):
        """Given completion arrives before an RPC response, when the response is read, then completion is retained."""
        process = SimpleNamespace(stdin=io.StringIO(), stdout=io.StringIO(
            json.dumps({'method': 'turn/completed', 'params': {'status': 'completed'}}) + '\n' +
            json.dumps({'id': 1, 'result': {'accepted': True}}) + '\n'
        ))
        client = ProtocolClient(process)
        self.assertTrue(client.request(1, 'turn/start', {})['accepted'])
        self.assertEqual(client.notification('turn/completed')['params']['status'], 'completed')
        client.reader.join(timeout=1)

    def test_closed_backend_fails_without_waiting_for_timeout(self):
        """Given a closed backend stream, when a request is made, then the probe reports closure."""
        client = ProtocolClient(SimpleNamespace(stdin=io.StringIO(), stdout=io.StringIO('')))
        with self.assertRaisesRegex(RuntimeError, 'Backend closed'):
            client.request(1, 'initialize', {}, timeout=1)
        client.reader.join(timeout=1)

    def test_parent_credentials_and_routing_are_not_inherited(self):
        """Given real parent credentials and routing, when isolated, then the probe cannot inherit them."""
        env = isolated_environment({
            'HOME': '/fixture/home', 'PATH': '/fixture/bin',
            'OPENAI_API_KEY': 'synthetic-secret', 'ANTHROPIC_API_KEY': 'synthetic-secret',
            'OPENAI_BASE_URL': 'https://example.invalid', 'CODEX_HOME': '/real/config',
            'ORCA_PANE_KEY': 'synthetic-session',
        }, '/temporary/config')
        self.assertEqual(env, {'HOME': '/fixture/home', 'PATH': '/fixture/bin', 'CODEX_HOME': '/temporary/config'})

    def test_discovery_cannot_be_claimed_as_execution(self):
        """Given a discovered untrusted hook, when summarized, then hook execution and native UI stay unverified."""
        result = summarize({'model_provider': 'desktop_probe', 'model_providers': {
            'desktop_probe': {'base_url': FIXTURE_URL, 'requires_openai_auth': False},
        }}, {'data': [{'hooks': [{'eventName': 'preToolUse', 'matcher': 'Bash', 'trustStatus': 'untrusted'}]}]})
        self.assertTrue(result['hook_discovered'])
        self.assertTrue(result['fixture_endpoint_loaded'])
        self.assertEqual(result['hook_trust_states'], ['untrusted'])
        self.assertFalse(result['hook_executed'])
        self.assertFalse(result['inference_requested'])
        self.assertFalse(result['native_ui_workflow_verified'])

    def test_missing_control_points_are_not_reported_as_ready(self):
        """Given no provider override and no hooks, when summarized, then readiness remains false."""
        result = summarize({}, {'data': []})
        self.assertFalse(result['provider_override_loaded'])
        self.assertFalse(result['fixture_endpoint_loaded'])
        self.assertFalse(result['hook_discovered'])


if __name__ == '__main__':
    unittest.main()
