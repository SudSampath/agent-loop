import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from adapters.codex import routing


ORIGINAL = b'''# existing personal settings\nmodel = "gpt-6.1-sol"\n[hooks.state]\n"synthetic-hook" = "reviewed-synthetic-hash"\n[mcp_servers.headroom]\ncommand = "headroom"\nargs = ["mcp", "serve"]\n'''


class RoutingTests(unittest.TestCase):
    def test_preserves_unrelated_bytes_and_round_trips(self):
        """Given hooks and model settings, when routed and rolled back, then bytes match."""
        changed = routing.enable_text(ORIGINAL)
        self.assertTrue(routing.active_route(changed))
        self.assertEqual(routing.disable_text(changed), ORIGINAL)

    def test_refuses_existing_route_and_custom_provider(self):
        """Given competing provider routing, when enabling, then no replacement is made."""
        for value in [b'openai_base_url="https://example.invalid/v1"\n',
                      b'model_provider="managed_gateway"\n',
                      b'[model_providers.openai]\nname="custom"\n']:
            with self.subTest(value=value), self.assertRaises(ValueError):
                routing.enable_text(value)

    def test_preserves_edits_made_after_enable(self):
        """Given later unrelated edits, when rolled back, then those edits survive."""
        later = b'\n# another session updated its settings\n'
        self.assertEqual(routing.disable_text(routing.enable_text(ORIGINAL) + later), ORIGINAL + later)

    def test_refuses_edited_managed_block(self):
        """Given a user changes the managed route, when rolling back, then edits are protected."""
        changed = routing.enable_text(ORIGINAL).replace(b'8787', b'9999')
        with self.assertRaises(ValueError):
            routing.disable_text(changed)

    def test_later_provider_selection_is_not_claimed_as_active(self):
        """Given another provider is selected, when coverage is checked, then it is inactive."""
        changed = routing.enable_text(b'model_provider="openai"\n')
        self.assertFalse(routing.active_route(changed.replace(b'="openai"', b'="other"')))

    @patch.object(routing, 'proxy_snapshot', side_effect=OSError('fixture outage'))
    def test_outage_prevents_enable(self, snapshot):
        """Given Headroom is unavailable, when enabling, then original config is untouched."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = root / 'config.toml'
            config.write_bytes(ORIGINAL)
            with self.assertRaises(OSError):
                routing.enable(config, root / 'state')
            self.assertEqual(config.read_bytes(), ORIGINAL)
            self.assertFalse((root / 'state/codex-routing.json').exists())

    @patch.object(routing, 'proxy_snapshot', return_value={'version': 'fixture', 'requests_total': 0})
    def test_enable_idempotence_private_backup_and_disable(self, snapshot):
        """Given a real temp config, when enabled twice then disabled, then rollback is exact."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = root / 'config.toml'
            config.write_bytes(ORIGINAL)
            config.chmod(0o640)
            state_dir = root / 'state'
            self.assertTrue(routing.enable(config, state_dir)['changed'])
            self.assertFalse(routing.enable(config, state_dir)['changed'])
            self.assertEqual(snapshot.call_count, 1)
            self.assertEqual((state_dir / 'codex-config.before-routing.toml').stat().st_mode & 0o777, 0o600)
            self.assertTrue(routing.disable(config, state_dir)['original_bytes_restored'])
            self.assertEqual(config.read_bytes(), ORIGINAL)
            self.assertEqual(config.stat().st_mode & 0o777, 0o640)
            self.assertFalse(routing.disable(config, state_dir)['changed'])

    @patch.object(routing, 'proxy_snapshot', return_value={'version': 'fixture', 'requests_total': 0})
    def test_interrupted_state_update_remains_recoverable(self, snapshot):
        """Given config applied before state completion, when disabling, then routing is removed."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = root / 'config.toml'
            config.write_bytes(ORIGINAL)
            state_dir = root / 'state'
            routing.enable(config, state_dir)
            path = state_dir / 'codex-routing.json'
            state = json.loads(path.read_text())
            state['enabled'] = False
            path.write_text(json.dumps(state))
            self.assertTrue(routing.disable(config, state_dir)['original_bytes_restored'])

    def test_protects_symlink_target(self):
        """Given a symlinked config, when enabling, then its owner is not replaced."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / 'target.toml'
            target.write_bytes(ORIGINAL)
            link = root / 'config.toml'
            link.symlink_to(target)
            with self.assertRaises(ValueError):
                routing.enable(link, root / 'state')
            self.assertEqual(target.read_bytes(), ORIGINAL)

    def test_log_parser_requires_native_peer_and_redacts_payload(self):
        """Given mixed proxy logs, when correlated, then only native peer metadata survives."""
        lines = [
            'event=proxy_inbound_request id=fixture-one method=POST path=/v1/responses client=127.0.0.1:50001 headers=PRIVATE_FIXTURE',
            'event=proxy_inbound_request id=other method=POST path=/v1/responses client=127.0.0.1:50002 headers=OTHER',
            'event=proxy_inbound_request id=health method=GET path=/health client=127.0.0.1:50001',
        ]
        result = routing.parse_native_requests(lines, {50001})
        self.assertEqual(result, [{'id': 'fixture-one', 'method': 'POST', 'path': '/v1/responses'}])
        self.assertNotIn('PRIVATE', json.dumps(result))

    def test_websocket_parser_matches_actual_address_format(self):
        """Given native and unrelated WebSockets, when correlated, then only native metadata survives."""
        lines = [
            "event=proxy_inbound_websocket request_id=native-ws session_id=PRIVATE path=/v1/responses client=Address(host='127.0.0.1', port=50001) header_count=22",
            "event=proxy_inbound_websocket request_id=other-ws path=/v1/responses client=Address(host='127.0.0.1', port=50002) header_count=22",
            "event=proxy_inbound_websocket_closed request_id=native-ws path=/v1/responses",
        ]
        result = routing.parse_native_websockets(lines, {50001})
        self.assertEqual(result, [{'id': 'native-ws', 'path': '/v1/responses'}])
        self.assertNotIn('PRIVATE', json.dumps(result))

    @patch.object(routing, 'process_table', return_value={
        1: (0, '/sbin/launchd'),
        10: (1, '/Applications/ChatGPT.app/Contents/MacOS/ChatGPT'),
        11: (10, '/Applications/ChatGPT.app/Contents/Resources/codex'),
        20: (1, '/Applications/Orca.app/Contents/MacOS/Orca'),
        21: (20, '/Applications/ChatGPT.app/Contents/Resources/codex'),
    })
    def test_app_inspection_excludes_same_binary_under_orca(self, processes):
        """Given the same bundled binary under two apps, when inspecting, then only native descendants qualify."""
        self.assertEqual([pid for pid, _ in routing.native_backends()], [10, 11])


if __name__ == '__main__':
    unittest.main()
