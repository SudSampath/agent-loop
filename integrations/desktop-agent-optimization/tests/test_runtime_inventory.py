import json
from pathlib import Path
import tempfile
import unittest

from verification.runtime_inventory import claude_snapshot, codex_snapshot, endpoint_kind


class RuntimeInventoryTests(unittest.TestCase):
    def test_configured_hook_does_not_establish_execution(self):
        """Given a configured RTK hook, when inventoried, then execution remains unverified."""
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            (home / 'hooks.json').write_text(json.dumps({'hooks': {'PreToolUse': [
                {'matcher': 'Bash', 'hooks': [{'command': '/fixture/rtk-hook.py'}]},
            ]}}))
            result = codex_snapshot(home)
            self.assertEqual(result['rtk_hook_entries'], 1)
            self.assertFalse(result['execution_verified'])

    def test_codex_configuration_secrets_are_not_collected(self):
        """Given credentials and URL secrets in configuration, when inventoried, then only allowlisted metadata is emitted."""
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            (home / 'config.toml').write_text(
                'openai_base_url="https://user:synthetic-secret@example.invalid/v1?token=synthetic-secret"\n'
                '[mcp_servers.headroom]\ncommand="headroom"\n'
                '[mcp_servers.headroom.env]\nAPI_KEY="synthetic-secret"\n'
            )
            result = codex_snapshot(home)
            self.assertNotIn('synthetic-secret', json.dumps(result))
            self.assertNotIn('example.invalid', json.dumps(result))
            self.assertTrue(result['headroom_mcp_configured'])

    def test_claude_settings_secrets_are_not_collected(self):
        """Given unrelated Claude settings and secrets, when inventoried, then they are excluded."""
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            (home / '.claude').mkdir()
            (home / '.claude/settings.json').write_text(json.dumps({
                'env': {'ANTHROPIC_API_KEY': 'synthetic-secret', 'ANTHROPIC_BASE_URL': 'http://localhost:8787'},
            }))
            result = claude_snapshot(home)
            self.assertNotIn('synthetic-secret', json.dumps(result))
            self.assertEqual(result['code_endpoint'], 'local Headroom endpoint')

    def test_endpoint_classification_checks_host_and_port(self):
        """Given a lookalike endpoint, when classified, then it is not mistaken for local Headroom."""
        self.assertEqual(endpoint_kind('http://127.0.0.1:8787/v1'), 'local Headroom endpoint')
        self.assertEqual(endpoint_kind('https://localhost.example.invalid:8787/v1'), 'other endpoint configured')
        self.assertEqual(endpoint_kind(None), 'not configured')


if __name__ == '__main__':
    unittest.main()
