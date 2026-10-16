import json
import os
from pathlib import Path
import plistlib
import stat
import tempfile
import unittest
from unittest.mock import patch

from verification import update_check

CODEX = {'app_version': '1.0', 'bundled_codex_version': '0.1.0',
         'rtk_pre_tool_use_hook_configured': True, 'rtk_hook_trust_entry_present': True}
CLAUDE = {'app_version': '2.0', 'bundled_claude_code_versions': ['2.1.0'],
          'rtk_pre_tool_use_hook_configured': True}


@patch.object(update_check, 'notify')
@patch.object(update_check.claude_desktop, 'status', return_value=CLAUDE)
class UpdateCheckTests(unittest.TestCase):
    def test_runtime_update_is_rechecked_and_announced(self, claude, notify):
        """Given a passing check, when the bundled Codex version changes, then the rerun passes and announces the update."""
        with tempfile.TemporaryDirectory() as temporary, \
                patch.object(update_check.codex_runtime_probe, 'probe', return_value={'checks_passed': True}), \
                patch.object(update_check.codex_desktop, 'status', return_value=CODEX):
            first = update_check.run(temporary, alert=True)
            self.assertTrue(first['passed'])
            self.assertFalse(first['versions_changed'])
            notify.assert_not_called()
            update_check.codex_desktop.status.return_value = {**CODEX, 'bundled_codex_version': '0.2.0-alpha.1'}
            second = update_check.run(temporary, alert=True)
            self.assertTrue(second['versions_changed'])
            self.assertIn('still passes', notify.call_args.args[0])
            state = Path(temporary) / 'update-check.json'
            self.assertEqual(json.loads(state.read_text())['versions']['codex'], '0.2.0-alpha.1')
            self.assertEqual(stat.S_IMODE(state.stat().st_mode), 0o600)

    def test_probe_error_fails_and_alerts(self, claude, notify):
        """Given the bundled runtime cannot start, when the check runs, then it fails and names the failed check."""
        with tempfile.TemporaryDirectory() as temporary, \
                patch.object(update_check.codex_runtime_probe, 'probe', side_effect=TimeoutError('fixture')), \
                patch.object(update_check.codex_desktop, 'status', return_value=CODEX):
            result = update_check.run(temporary, alert=True)
            self.assertFalse(result['passed'])
            self.assertEqual(result['codex_runtime_probe'], {'checks_passed': False, 'error': 'TimeoutError'})
            self.assertIn('codex_runtime_applies_rtk', notify.call_args.args[0])

    def test_install_without_loading_writes_watching_agent_only(self, claude, notify):
        """Given a temporary LaunchAgents folder, when installed without loading, then launchctl is never called."""
        with tempfile.TemporaryDirectory() as temporary, \
                patch.object(update_check.subprocess, 'run') as launchctl:
            update_check.install(temporary, Path(temporary) / 'state', python='/fixture/python3', load=False)
            agent = plistlib.loads((Path(temporary) / f'{update_check.LABEL}.plist').read_bytes())
            launchctl.assert_not_called()
            self.assertEqual(agent['ProgramArguments'],
                             ['/fixture/python3', '-m', 'verification.update_check', 'run', '--alert'])
            self.assertIn('/Applications/ChatGPT.app/Contents/Resources/codex-cli/codex-package.json',
                          agent['WatchPaths'])
            self.assertTrue(os.path.isabs(agent['WorkingDirectory']))
            self.assertNotIn('RunAtLoad', agent)


if __name__ == '__main__':
    unittest.main()
