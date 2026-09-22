import json
import os
from pathlib import Path
import subprocess
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
WINDOWS = os.name == 'nt'


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='agent loop test ')
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.prefix = self.base / 'install'
        self.codex = self.base / 'codex'
        self.claude = self.base / 'claude'
        self.bin = self.base / 'bin'
        self.bin.mkdir()
        self.env = dict(os.environ, PATH=str(self.bin) + os.pathsep + os.environ['PATH'])
        self.env.pop('CODEX_HOME', None)
        self.env.pop('CLAUDE_CONFIG_DIR', None)
        for name in ('codex', 'claude', 'headroom', 'rtk'):
            p = self.bin / name
            p.write_text('#!' + sys.executable + '\nimport os,sys,json\nprint(json.dumps({"args":sys.argv[1:],"codex_home":os.getenv("CODEX_HOME"),"orca":os.getenv("ORCA_TEST")}))\n')
            p.chmod(0o700)
            if WINDOWS:
                shim = self.bin / (name + '.ps1')
                quote = lambda value: "'" + str(value).replace("'", "''") + "'"
                shim.write_text("$PSNativeCommandArgumentPassing = 'Standard'\n& " + quote(sys.executable) + ' ' + quote(p) + ' @args\nexit $LASTEXITCODE\n', encoding='utf-8')

    def launcher(self, agent):
        p = self.prefix / 'bin' / ('sudarshan-' + agent + ('.ps1' if WINDOWS else ''))
        return [shutil.which('pwsh'), '-NoProfile', '-File', str(p)] if WINDOWS else [str(p)]

    def install(self, *extra, ok=True):
        result = subprocess.run([sys.executable, str(ROOT / 'bootstrap.py'), 'install',
            '--workspace', str(self.base), '--prefix', str(self.prefix),
            '--codex-home', str(self.codex), '--claude-home', str(self.claude), *extra],
            capture_output=True, text=True, encoding='utf-8', env=self.env)
        self.assertEqual(result.returncode, 0 if ok else 1, result.stderr)
        return result

    def test_repeat_install_preserves_existing_instructions(self):
        """Given existing instructions, when installed twice, then preserve them without duplicates."""
        self.codex.mkdir()
        p = self.codex / 'AGENTS.md'
        p.write_text('Existing project-independent rules\n')
        self.install()
        first = p.read_bytes()
        self.install()
        self.assertEqual(first, p.read_bytes())
        self.assertTrue(p.read_text().startswith('Existing project-independent rules'))
        self.assertEqual(len(list(self.codex.glob('AGENTS.md.agent-loop-backup-*'))), 1)

    def test_preview_and_skill_conflict_make_no_install(self):
        """Given preview or conflicting skills, when installing, then leave destinations untouched."""
        self.install('--dry-run')
        self.assertFalse(self.prefix.exists())
        p = self.codex / 'skills/sudarshan-prd/SKILL.md'
        p.parent.mkdir(parents=True)
        p.write_text('Different local version')
        self.install(ok=False)
        self.assertFalse(self.prefix.exists())
        self.assertFalse((self.codex / 'AGENTS.md').exists())
        self.assertEqual(p.read_text(), 'Different local version')

    def test_spaces_and_injected_runtime_home(self):
        """Given Orca environment and spaced paths, when launched, then forward arguments and load runtime context."""
        self.install()
        active = self.base / 'orca runtime'
        env = dict(self.env, CODEX_HOME=str(active), ORCA_TEST='preserve')
        result = subprocess.run([*self.launcher('codex'), 'a prompt with spaces', '--search'],
                                env=env, capture_output=True, text=True, encoding='utf-8', check=True)
        out = json.loads(result.stdout)
        self.assertEqual(out['args'], ['a prompt with spaces', '--search'])
        self.assertEqual(out['orca'], 'preserve')
        self.assertEqual(out['codex_home'], str(active))
        self.assertTrue((active / 'AGENTS.md').exists())
        self.assertTrue((active / 'skills/sudarshan-prd/SKILL.md').exists())

    def test_help_does_not_mutate_runtime(self):
        """Given a fresh runtime home, when help is requested, then no configuration is created."""
        self.install()
        active = self.base / 'unused'
        subprocess.run([*self.launcher('codex'), '--help'],
                       env=dict(self.env, CODEX_HOME=str(active)), capture_output=True, check=True)
        self.assertFalse(active.exists())

    @unittest.skipIf(WINDOWS, 'Optional POSIX optimizer integration')
    def test_optional_hooks_preserve_orca_and_do_not_duplicate(self):
        """Given Orca hooks, when optimizers are installed twice, then keep them and add only one RTK hook."""
        self.codex.mkdir()
        p = self.codex / 'hooks.json'
        old = {'hooks': {'Stop': [{'hooks': [{'command': 'orca-stop'}]}],
                         'PreToolUse': [{'hooks': [{'command': 'orca-tool'}]}]}}
        p.write_text(json.dumps(old))
        self.install('--optimizers')
        self.install('--optimizers')
        data = json.loads(p.read_text())
        self.assertEqual(data['hooks']['Stop'], old['hooks']['Stop'])
        self.assertEqual(data['hooks']['PreToolUse'][0], old['hooks']['PreToolUse'][0])
        self.assertEqual(len(data['hooks']['PreToolUse']), 2)
        result = subprocess.run([*self.launcher('claude'), 'hello'], env=self.env,
                                capture_output=True, text=True, encoding='utf-8', check=True)
        self.assertEqual(json.loads(result.stdout)['args'], ['wrap', 'claude', '--port', '8787', '--code-memory', 'none', '--', 'hello'])

    def test_invalid_vault_and_malformed_block(self):
        """Given invalid input, when installing, then fail before changing other destinations."""
        self.install('--vault', str(self.base), ok=False)
        self.codex.mkdir()
        (self.codex / 'AGENTS.md').write_text('<!-- sudarshan-agent-loop:start -->')
        self.install(ok=False)
        self.assertFalse(self.prefix.exists())

    def test_doctor_checks_installed_state(self):
        """Given a complete local fixture, when doctor runs, then report success without authentication claims."""
        self.install()
        result = subprocess.run([sys.executable, str(ROOT / 'bootstrap.py'), 'doctor', '--prefix', str(self.prefix)],
                                env=self.env, capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn('require the live smoke checks', result.stdout)

    def test_hook_passes_through_bad_input(self):
        """Given malformed hook input, when adapter runs, then leave normal tool execution usable."""
        result = subprocess.run([sys.executable, str(ROOT / 'runtime/rtk_hook.py')], input='not json',
                                capture_output=True, text=True, encoding='utf-8', env=self.env)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, '')

    @unittest.skipIf(WINDOWS, 'Optional POSIX optimizer integration')
    def test_hook_rewrite_preserves_other_tool_fields(self):
        """Given a recognized command, when RTK rewrites it, then preserve unrelated tool input."""
        (self.bin / 'rtk').write_text('#!/bin/sh\nprintf "rtk git status\\n"\nexit 3\n')
        event = {'hook_event_name': 'PreToolUse', 'tool_name': 'Bash',
                 'tool_input': {'command': 'git status', 'timeout_ms': 1000}}
        result = subprocess.run([sys.executable, str(ROOT / 'runtime/rtk_hook.py')], input=json.dumps(event),
                                capture_output=True, text=True, encoding='utf-8', env=self.env, check=True)
        output = json.loads(result.stdout)['hookSpecificOutput']
        self.assertEqual(output['updatedInput'], {'command': 'rtk git status', 'timeout_ms': 1000})

    @unittest.skipIf(WINDOWS, 'Optional POSIX optimizer integration')
    def test_invalid_hook_config_stops_before_install(self):
        """Given malformed existing hook configuration, when installing, then preserve it and stop."""
        self.codex.mkdir()
        p = self.codex / 'hooks.json'
        p.write_text('{broken')
        self.install('--optimizers', ok=False)
        self.assertEqual(p.read_text(), '{broken')
        self.assertFalse(self.prefix.exists())


if __name__ == '__main__':
    unittest.main()
