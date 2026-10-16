import json
from pathlib import Path
import tempfile
import unittest

from verification import codex_desktop

ORCA_HOOK = {'type': 'command', 'command': ': orca-agent-hook-form=1; /bin/sh hook.sh || :'}
RTK_HOOK = {'type': 'command', 'command': '/fixture/lib/rtk-codex-hook.py'}


def write_home(root, groups, trust):
    (root / 'hooks.json').write_text(json.dumps({'hooks': {'PreToolUse': groups}}))
    lines = ['openai_base_url = "http://127.0.0.1:8787/v1"']
    for key, entry in trust.items():
        lines.append(f'[hooks.state."{root / "hooks.json"}:{key}"]')
        lines += [f'{name} = {json.dumps(value)}' for name, value in entry.items()]
    (root / 'config.toml').write_text('\n'.join(lines) + '\n')


class CodexDesktopTests(unittest.TestCase):
    def test_trusted_rtk_hook_after_orca_hook_is_ready(self):
        """Given Orca's hook then a trusted RTK hook, when status is read, then RTK is configured and trusted without hashes."""
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            write_home(home, [{'hooks': [ORCA_HOOK]}, {'matcher': 'Bash', 'hooks': [RTK_HOOK]}],
                       {'pre_tool_use:0:0': {'trusted_hash': 'PRIVATE-HASH-A'},
                        'pre_tool_use:1:0': {'trusted_hash': 'PRIVATE-HASH-B'}})
            before = (home / 'config.toml').read_text(), (home / 'hooks.json').read_text()
            result = codex_desktop.status(home, home / 'missing.app')
            self.assertTrue(result['rtk_pre_tool_use_hook_configured'])
            self.assertTrue(result['rtk_hook_trust_entry_present'])
            self.assertEqual(result['headroom_route'], 'local Headroom endpoint')
            self.assertNotIn('PRIVATE', json.dumps(result))
            self.assertEqual(((home / 'config.toml').read_text(), (home / 'hooks.json').read_text()), before)

    def test_untrusted_or_disabled_rtk_hook_is_not_ready(self):
        """Given an RTK hook trusted only at another position or disabled, when status is read, then trust is not reported."""
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            write_home(home, [{'hooks': [RTK_HOOK]}], {'pre_tool_use:1:0': {'trusted_hash': 'x'}})
            result = codex_desktop.status(home, home / 'missing.app')
            self.assertTrue(result['rtk_pre_tool_use_hook_configured'])
            self.assertFalse(result['rtk_hook_trust_entry_present'])
            write_home(home, [{'hooks': [RTK_HOOK]}], {'pre_tool_use:0:0': {'trusted_hash': 'x', 'enabled': False}})
            self.assertFalse(codex_desktop.status(home, home / 'missing.app')['rtk_hook_trust_entry_present'])

    def test_missing_codex_home_reports_nothing_configured(self):
        """Given no Codex home files, when status is read, then RTK and the route are reported absent."""
        with tempfile.TemporaryDirectory() as temporary:
            result = codex_desktop.status(Path(temporary), Path(temporary) / 'missing.app')
            self.assertFalse(result['rtk_pre_tool_use_hook_configured'])
            self.assertEqual(result['headroom_route'], 'not configured')


if __name__ == '__main__':
    unittest.main()
