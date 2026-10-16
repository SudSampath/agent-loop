import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from adapters.codex import routing


ORIGINAL = b'''# existing personal settings\nmodel = "gpt-6.1-sol"\n[hooks.state]\n"synthetic-hook" = "reviewed-synthetic-hash"\n[mcp_servers.headroom]\ncommand = "headroom"\nargs = ["mcp", "serve"]\n'''
SNAPSHOT = {'version': 'fixture', 'requests_total': 0, 'compression_tokens_saved': 0}
PREFIX = '2026-01-01 00:00:00,000 - headroom.proxy - INFO - '
NATIVE_OPEN = PREFIX + ("event=proxy_inbound_websocket request_id=hr_1_000001 session_id=PRIVATE "
                        "path=/v1/responses client=Address(host='127.0.0.1', port=50001) header_count=20")
NATIVE_TURNS = [
    PREFIX + ('[hr_1_000001] PERF model=fixture msgs=3 tok_before=1000 tok_after=700 tok_saved=300 '
              'tok_inflated=0 tool_saved=0 total_saved=300 cache_read=50 cache_write=0 cache_hit_pct=5 '
              'opt_ms=4 total_ms=90 tok_out=20 ttfb_ms=30 savings=tok_saved=999 '
              'transforms=read_lifecycle:stale:/PRIVATE/fixture/path client=codex'),
    PREFIX + ('[hr_1_000002] PERF model=fixture msgs=3 tok_before=9000 tok_after=4000 tok_saved=5000 '
              'tok_inflated=0 tool_saved=0 total_saved=5000 cache_read=0 tok_out=9 savings=x transforms=none'),
    PREFIX + ('[hr_1_000001] PERF model=fixture msgs=5 tok_before=1200 tok_after=1100 tok_saved=100 '
              'tok_inflated=0 tool_saved=0 total_saved=100 cache_read=900 tok_out=10 savings=x transforms=none'),
]
NATIVE_CLOSED = '\n'.join([
    PREFIX + ('[hr_1_000001] WS /v1/responses completed (tokens_saved=400, cause=client_disconnect, '
              'client_frames=3, upstream_frames=40, cancel_frames=1, client_disconnect=True, '
              'last_client_type=response.cancel, last_upstream_type=PRIVATE)'),
    PREFIX + ('event=proxy_inbound_websocket_closed request_id=hr_1_000001 session_id=PRIVATE '
              'path=/v1/responses cause=client_disconnect duration_ms=10.00'),
])


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

    def test_session_outcomes_join_only_native_perf_counts(self):
        """Given PERF lines for native and shared connections, when joined, then only native counts survive."""
        native = routing.digest(b'hr_1_000001')
        lines = [NATIVE_OPEN, *NATIVE_TURNS, *NATIVE_CLOSED.splitlines()]
        [session] = routing.session_outcomes(lines, [native])
        self.assertEqual(session['fingerprint'], native)
        self.assertEqual(session['outcome_records'], 2)
        self.assertEqual(session['tokens_before'], 2200)
        self.assertEqual(session['tokens_saved'], 400)
        self.assertEqual(session['total_tokens_saved'], 400)
        self.assertEqual(session['cache_read_tokens'], 950)
        self.assertEqual((session['client_frames'], session['cancel_frames']), (3, 1))
        self.assertEqual(session['close_cause'], 'client_disconnect')
        self.assertNotIn('PRIVATE', json.dumps(session))
        self.assertNotIn('hr_1', json.dumps(session))

    def test_log_reader_follows_rotation_and_reports_gaps(self):
        """Given the enable-time log was rotated, when reading since enable, then both files are read in order."""
        with tempfile.TemporaryDirectory() as temporary:
            log = Path(temporary) / 'proxy.log'
            log.write_text('before-enable\nafter-one\n')
            inode, offset = log.stat().st_ino, len('before-enable\n')
            log.rename(log.with_name('proxy.log.1'))
            log.write_text('after-two\n')
            self.assertEqual(routing.log_lines_since(log, inode, offset), (['after-one', 'after-two'], True))
            log.with_name('proxy.log.1').unlink()
            self.assertEqual(routing.log_lines_since(log, inode, offset), ([], False))

    @patch.object(routing, 'project_counters', return_value={'requests': 2, 'tokens_saved': 300, 'total_input_tokens': 10000})
    @patch.object(routing, 'native_ancestors', return_value=[(10, '/Applications/ChatGPT.app/Contents/MacOS/ChatGPT')])
    @patch.object(routing, 'native_peer_ports')
    @patch.object(routing, 'proxy_snapshot')
    def test_report_keeps_closed_session_attribution_during_outage(self, snapshot, peers, ancestors, projects):
        """Given a native session reported while open, when its socket closes and Headroom is down, then savings stay attributed."""
        with tempfile.TemporaryDirectory() as temporary, patch.object(routing, 'LOG', Path(temporary) / 'proxy.log'):
            root = Path(temporary)
            routing.LOG.write_text('earlier unrelated traffic\n')
            config = root / 'config.toml'
            config.write_bytes(ORIGINAL)
            snapshot.return_value = SNAPSHOT
            routing.enable(config, root / 'state')
            with routing.LOG.open('a') as handle:
                handle.write('\n'.join([NATIVE_OPEN, *NATIVE_TURNS[:2]]) + '\n')
            peers.return_value = {50001}
            snapshot.return_value = {**SNAPSHOT, 'requests_total': 2, 'compression_tokens_saved': 5300}
            open_report = routing.report(config, root / 'state')
            self.assertTrue(open_report['native_session_optimization_attributed'])
            self.assertEqual(open_report['native_session_tokens_saved'], 300)
            self.assertEqual(open_report['aggregate_compression_tokens_since_enable'], 5300)
            self.assertEqual(open_report['route_project_lifetime']['tokens_saved'], 300)

            with routing.LOG.open('a') as handle:
                handle.write('\n'.join([NATIVE_TURNS[2], NATIVE_CLOSED]) + '\n')
            peers.return_value = set()
            snapshot.side_effect = OSError('fixture outage')
            closed_report = routing.report(config, root / 'state')
            self.assertTrue(closed_report['routing_enabled'])
            self.assertFalse(closed_report['proxy_ready'])
            self.assertFalse(closed_report['native_inference_transport_verified'])
            self.assertIsNone(closed_report['aggregate_compression_tokens_since_enable'])
            self.assertIsNone(closed_report['route_project_lifetime'])
            [session] = closed_report['native_sessions']
            self.assertEqual((session['outcome_records'], session['close_cause']), (2, 'client_disconnect'))
            self.assertEqual(closed_report['native_session_tokens_saved'], 400)
            self.assertTrue(closed_report['proxy_log_since_enable_complete'])
            self.assertFalse(closed_report['aggregate_savings_attributable_to_native_fixture'])

    @patch.object(routing, 'proxy_snapshot', return_value=SNAPSHOT)
    def test_rollback_does_not_need_proxy_during_outage(self, snapshot):
        """Given routing is enabled, when Headroom is down and routing is disabled, then the config is restored."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = root / 'config.toml'
            config.write_bytes(ORIGINAL)
            routing.enable(config, root / 'state')
            snapshot.side_effect = OSError('fixture outage')
            self.assertTrue(routing.disable(config, root / 'state')['original_bytes_restored'])
            self.assertEqual(config.read_bytes(), ORIGINAL)
            self.assertEqual(snapshot.call_count, 1)


if __name__ == '__main__':
    unittest.main()
