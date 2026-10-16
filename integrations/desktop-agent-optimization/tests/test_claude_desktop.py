import json
from pathlib import Path
import tempfile
import unittest

from verification import claude_desktop


class ClaudeDesktopTests(unittest.TestCase):
    def test_status_reports_names_not_values(self):
        """Given routing credentials in settings, when status is read, then only variable names appear and nothing changes."""
        with tempfile.TemporaryDirectory() as temporary:
            settings = Path(temporary) / 'settings.json'
            original = json.dumps({
                'env': {'ANTHROPIC_AUTH_TOKEN': 'PRIVATE-TOKEN', 'UNRELATED': 'x'},
                'hooks': {'PreToolUse': [{'matcher': 'Bash', 'hooks': [{'type': 'command', 'command': 'rtk hook claude'}]}]},
            })
            settings.write_text(original)
            result = claude_desktop.status(settings, Path(temporary) / 'support')
            self.assertEqual(result['settings_routing_env_keys'], ['ANTHROPIC_AUTH_TOKEN'])
            self.assertTrue(result['rtk_pre_tool_use_hook_configured'])
            self.assertNotIn('PRIVATE', json.dumps(result))
            self.assertEqual(settings.read_text(), original)

    def test_status_without_rtk_hook_is_not_ready(self):
        """Given settings with only an unrelated hook, when status is read, then RTK is not reported as configured."""
        with tempfile.TemporaryDirectory() as temporary:
            settings = Path(temporary) / 'settings.json'
            settings.write_text(json.dumps({
                'hooks': {'PreToolUse': [{'matcher': 'Bash', 'hooks': [{'type': 'command', 'command': 'rtk-lookalike claude'}]}]},
            }))
            result = claude_desktop.status(settings, Path(temporary) / 'support')
            self.assertFalse(result['rtk_pre_tool_use_hook_configured'])
            self.assertEqual(result['settings_routing_env_keys'], [])


if __name__ == '__main__':
    unittest.main()
