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
        p = self.prefix / 'bin' / ('agent-loop-' + agent + ('.ps1' if WINDOWS else ''))
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
        p = self.codex / 'skills/draft-prd/SKILL.md'
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
        self.assertTrue((active / 'skills/draft-prd/SKILL.md').exists())

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
        (self.codex / 'AGENTS.md').write_text('<!-- agent-loop:start -->')
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

    def orca_shell(self, *extra, ok=True):
        result = subprocess.run([sys.executable, str(ROOT / 'bootstrap.py'), 'orca-shell',
            '--prefix', str(self.prefix), '--rc', str(self.base / 'shell rc'), *extra],
            capture_output=True, text=True, env=self.env)
        self.assertEqual(result.returncode, 0 if ok else 1, result.stderr)
        return result

    @unittest.skipIf(WINDOWS, 'Optional Bash/Zsh integration')
    def test_orca_worktree_shell_routes_through_optimizers(self):
        """Given a new Git worktree in Orca, when bare agents start, then wrap them and retain RTK and Orca hooks."""
        self.install('--optimizers')
        self.orca_shell()
        repo, worktree = self.base / 'repo', self.base / 'new worktree'
        subprocess.run(['git', 'init', str(repo)], capture_output=True, check=True)
        subprocess.run(['git', '-C', str(repo), '-c', 'user.name=Fixture', '-c',
                        'user.email=fixture@example.invalid', 'commit', '--allow-empty', '-m', 'fixture'],
                       capture_output=True, check=True)
        subprocess.run(['git', '-C', str(repo), 'worktree', 'add', '-b', 'fixture', str(worktree)],
                       capture_output=True, check=True)
        active = self.base / 'active runtime'
        active.mkdir()
        old = {'hooks': {'PreToolUse': [{'matcher': 'Bash', 'hooks': [{'command': 'orca-tool'}]}]}}
        (active / 'hooks.json').write_text(json.dumps(old))
        shells = [shutil.which(name) for name in ('bash', 'zsh') if shutil.which(name)]
        self.assertTrue(shells)
        import shlex
        rc = shlex.quote(str(self.base / 'shell rc'))
        prompt = 'spaces; $(never-execute) "quotes"'
        for shell in shells:
            for agent in ('codex', 'claude'):
                with self.subTest(shell=shell, agent=agent):
                    env = dict(self.env, ORCA_WORKTREE_ID=str(worktree), ORCA_TEST='preserve',
                               CODEX_HOME=str(active), CLAUDE_CONFIG_DIR=str(active))
                    result = subprocess.run([shell, '-c', f'. {rc}; {agent} "$1"', 'fixture', prompt],
                                            cwd=worktree, env=env, capture_output=True, text=True, check=True)
                    out = json.loads(result.stdout)
                    self.assertEqual(out['args'], ['wrap', agent, '--port', '8787', '--code-memory', 'none', '--', prompt])
                    self.assertEqual(out['orca'], 'preserve')
                    self.assertEqual(out['codex_home'], str(active))
        hooks = json.loads((active / 'hooks.json').read_text())['hooks']['PreToolUse']
        self.assertEqual(hooks[0], old['hooks']['PreToolUse'][0])
        self.assertEqual(len(hooks), 2)
        self.assertIn('rtk_hook.py', hooks[1]['hooks'][0]['command'])

    @unittest.skipIf(WINDOWS, 'Optional Bash/Zsh integration')
    def test_orca_shell_preserves_external_shell_and_help(self):
        """Given shell routing, when outside Orca or requesting help, then avoid optimizer startup and home mutations."""
        self.install('--optimizers')
        self.orca_shell()
        import shlex
        rc = shlex.quote(str(self.base / 'shell rc'))
        env = {k: v for k, v in self.env.items() if not k.startswith('ORCA_')}
        unused = self.base / 'unused runtime'
        env['CODEX_HOME'] = str(unused)
        for shell in filter(None, (shutil.which('bash'), shutil.which('zsh'))):
            for marker, arg in [({}, 'hello'), ({'ORCA_TAB_ID': 'fixture'}, '--help')]:
                result = subprocess.run([shell, '-c', f'. {rc}; codex "$1"', 'fixture', arg],
                                        env=dict(env, **marker), capture_output=True, text=True, check=True)
                self.assertEqual(json.loads(result.stdout)['args'], [arg])
                self.assertFalse(unused.exists())
            launcher = self.prefix / 'bin/agent-loop-codex'
            content = launcher.read_bytes()
            launcher.unlink()
            result = subprocess.run([shell, '-c', f'. {rc}; codex hello'],
                                    env=dict(env, ORCA_TAB_ID='fixture'), capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)  # Never silently fall back to an unwrapped launch.
            self.assertEqual(result.stdout, '')
            launcher.write_bytes(content)
            launcher.chmod(0o700)

    @unittest.skipIf(WINDOWS, 'Optional Bash/Zsh integration')
    def test_orca_shell_skip_permissions_is_opt_in_and_keeps_help_direct(self):
        """Given routing with --skip-permissions, when agents start in Orca, then bypass approvals but not for help or external shells."""
        self.install('--optimizers')
        self.orca_shell('--skip-permissions')
        import shlex
        rc = shlex.quote(str(self.base / 'shell rc'))
        env = {k: v for k, v in self.env.items() if not k.startswith('ORCA_')}
        for shell in filter(None, (shutil.which('bash'), shutil.which('zsh'))):
            for agent, flag in [('codex', '--dangerously-bypass-approvals-and-sandbox'),
                                ('claude', '--dangerously-skip-permissions')]:
                with self.subTest(shell=shell, agent=agent):
                    run = lambda marker, arg: json.loads(subprocess.run(
                        [shell, '-c', f'. {rc}; {agent} "$1"', 'fixture', arg], env=dict(env, **marker),
                        capture_output=True, text=True, check=True).stdout)['args']
                    self.assertEqual(run({'ORCA_TAB_ID': 'fixture'}, 'a b')[-3:], ['--', flag, 'a b'])
                    self.assertEqual(run({'ORCA_TAB_ID': 'fixture'}, '--version'), ['--version'])
                    self.assertEqual(run({}, 'a b'), ['a b'])
        self.orca_shell()
        self.assertNotIn('dangerously', (self.base / 'shell rc').read_text())

    @unittest.skipIf(WINDOWS, 'Optional Bash/Zsh integration')
    def test_orca_shell_preview_preservation_and_validation(self):
        """Given existing startup files, when routing is installed, then preview safely, preserve content, and validate all files first."""
        self.install('--optimizers')
        rc = self.base / 'shell rc'
        rc.write_text('# existing startup\nexport KEEP=unchanged\n')
        before = rc.read_bytes()
        self.orca_shell('--dry-run')
        self.assertEqual(rc.read_bytes(), before)
        self.orca_shell()
        first = rc.read_bytes()
        self.orca_shell()
        self.assertEqual(rc.read_bytes(), first)
        self.assertTrue(first.startswith(before))
        self.assertEqual(len(list(self.base.glob('shell rc.agent-loop-backup-*'))), 1)
        malformed = self.base / 'broken rc'
        malformed.write_text('# >>> agent-loop Orca routing >>>')
        self.orca_shell('--rc', str(malformed), ok=False)
        self.assertEqual(rc.read_bytes(), first)
        self.orca_shell('--codex-launcher', str(self.bin / 'codex'), ok=False)
        link = self.base / 'rc link'
        link.symlink_to(rc)
        self.orca_shell('--rc', str(link), ok=False)

    def dream_schedule(self, *extra, ok=True):
        result = subprocess.run([sys.executable, str(ROOT / 'bootstrap.py'), 'dream-schedule',
            '--prefix', str(self.prefix), '--no-load', *extra],
            capture_output=True, text=True, env=dict(self.env, HOME=str(self.base / 'home')))
        self.assertEqual(result.returncode, 0 if ok else 1, result.stderr)
        return result

    @unittest.skipIf(WINDOWS, 'Optional launchd/systemd integration')
    def test_dream_schedule_runs_unattended_dream_nightly(self):
        """Given an installed harness with a vault, when Dream is scheduled, then run it nightly from the workspace through the launcher."""
        vault = self.base / 'my vault'
        vault.mkdir()
        (vault / 'INDEX.md').write_text('# Index\n')
        self.install('--vault', str(vault))
        self.dream_schedule('--dry-run', '--hour', '4', '--minute', '30')
        script = self.prefix / 'lib/agent-loop/dream-nightly.sh'
        self.assertFalse(script.exists())
        self.dream_schedule('--hour', '4', '--minute', '30')
        home = self.base / 'home'
        if sys.platform == 'darwin':
            unit = (home / 'Library/LaunchAgents/com.agent-loop.dream.plist').read_text()
            self.assertIn('<integer>4</integer>', unit)
            self.assertIn('<integer>30</integer>', unit)
        else:
            timer = (home / '.config/systemd/user/agent-loop-dream.timer').read_text()
            self.assertIn('OnCalendar=*-*-* 04:30:00', timer)
            unit = (home / '.config/systemd/user/agent-loop-dream.service').read_text()
            self.assertIn(f'ExecStart="{script}"', unit)  # Quoted: the prefix contains spaces.
        self.assertIn(str(script), unit)
        result = subprocess.run([str(script)], env=dict(self.env, CLAUDE_CONFIG_DIR=str(self.claude)),
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        log = next((self.prefix / 'state/agent-loop/dream').glob('*.log')).read_text()
        out = json.loads(log.splitlines()[1])
        self.assertEqual(out['args'], ['-p', '/dream --unattended', '--dangerously-skip-permissions', '--add-dir', str(vault.resolve())])
        self.assertIn('rc=0', log)
        self.dream_schedule('--propose-only')
        self.assertIn("'/dream --unattended --dry-run'", script.read_text())

    @unittest.skipIf(WINDOWS, 'Optional launchd/systemd integration')
    def test_dream_schedule_requires_vault_launcher_and_valid_time(self):
        """Given missing prerequisites or a bad time, when Dream is scheduled, then refuse without writing; explicit paths work without the harness."""
        import shlex
        self.dream_schedule(ok=False)
        self.install()
        self.dream_schedule(ok=False)
        vault = self.base / 'vault'
        vault.mkdir()
        (vault / 'INDEX.md').write_text('# Index\n')
        self.install('--vault', str(vault))
        self.dream_schedule('--hour', '24', ok=False)
        self.dream_schedule('--claude-launcher', str(self.base / 'missing'), ok=False)
        self.assertFalse((self.base / 'home').exists())
        self.assertFalse((self.prefix / 'lib/agent-loop/dream-nightly.sh').exists())
        bare = self.base / 'bare prefix'
        launcher = self.base / 'existing-claude'
        launcher.write_text('#!/bin/sh\n')
        launcher.chmod(0o700)
        self.dream_schedule('--prefix', str(bare), '--claude-launcher', str(launcher),
                            '--workspace', str(self.base), '--vault', str(vault))
        self.assertIn(shlex.quote(str(launcher)), (bare / 'lib/agent-loop/dream-nightly.sh').read_text())


    def test_dream_follows_up_on_previous_recommendations_and_drafts(self):
        """Given a previous digest and pending drafts, when Dream runs, then it reports follow-up status and confirms, readies, or retires drafts."""
        skill = (ROOT / 'skills/dream/SKILL.md').read_text(encoding='utf-8')
        follow_up = skill.split('## 4. Follow-up')[1].split('## 5. Digest')[0]
        for term in ('`done`', '`open`', '`dropped`', 'First dream: nothing to follow up',
                     '`confirmations >= 2`', '`status: ready`', '14 days', 'drafts/archive/', '--dry-run'):
            self.assertIn(term, follow_up)
        self.assertLess(skill.index('## Follow-up'), skill.index('## Activity summary'))
        self.assertIn('`addresses`', skill)

    def test_dream_review_installs_for_both_clients_with_scoped_targets(self):
        """Given ready drafts, when dream-review is installed and read, then both clients get it and it defines scoped, approved promotion."""
        self.install()
        for home in (self.codex, self.claude):
            self.assertTrue((home / 'skills/dream-review/SKILL.md').is_file())
        skill = (ROOT / 'skills/dream-review/SKILL.md').read_text(encoding='utf-8')
        for term in ('`status: ready`', 'memory root', '`me/`', 'templates/core.md', 'explicit approval',
                     'promoted_from', 'drafts/archive/', 'Defer', 'none'):
            self.assertIn(term, skill)

    def test_dream_reports_whether_promoted_lessons_hold(self):
        """Given promoted lessons, when Dream runs, then it reports each as recurring, holding, or untested without editing it."""
        skill = (ROOT / 'skills/dream/SKILL.md').read_text(encoding='utf-8')
        follow_up = skill.split('## 4. Follow-up')[1].split('## 5. Digest')[0]
        for term in ('promoted_from', '`addresses`', '`recurring`', '`holding`', '`untested`', '30 days',
                     'never edit a promoted lesson'):
            self.assertIn(term, follow_up)
        self.assertIn('No promoted lessons yet', skill)
        self.assertLess(skill.index('## Lesson effectiveness'), skill.index('## Activity summary'))

    def test_vault_profile_files_are_referenced_not_copied(self):
        """Given a vault with some profile files, when installed, then instructions point to the existing ones without copying their content."""
        vault = self.base / 'vault'
        (vault / 'me').mkdir(parents=True)
        (vault / 'INDEX.md').write_text('# Index\n')
        (vault / 'me/voice.md').write_text('PRIVATE VOICE DETAIL\n')
        (vault / 'me/profile.md').write_text('PRIVATE PROFILE DETAIL\n')
        self.install('--vault', str(vault))
        for home, name in ((self.codex, 'AGENTS.md'), (self.claude, 'CLAUDE.md')):
            text = (home / name).read_text()
            self.assertIn('## The user', text)
            self.assertIn(str((vault / 'me/voice.md').resolve()), text)
            self.assertIn(str((vault / 'me/profile.md').resolve()), text)
            self.assertNotIn('audiences.md', text)
            self.assertNotIn('PRIVATE', text)
        self.install()
        self.assertNotIn('## The user', (self.codex / 'AGENTS.md').read_text())

    def test_pre_rename_instructions_are_migrated_not_duplicated(self):
        """Given an instruction block from before the rename, when reinstalled, then it is replaced in place exactly once."""
        self.codex.mkdir()
        (self.codex / 'AGENTS.md').write_text('Keep me\n<!-- sudarshan-agent-loop:start -->\nold\n<!-- sudarshan-agent-loop:end -->\nAfter\n')
        self.install()
        text = (self.codex / 'AGENTS.md').read_text()
        self.assertNotIn('sudarshan', text)
        self.assertEqual(text.count('<!-- agent-loop:start -->'), 1)
        self.assertTrue(text.startswith('Keep me\n') and text.endswith('After\n'))
        self.assertNotIn('\nold\n', text)

    @unittest.skipIf(WINDOWS, 'Optional Bash/Zsh integration')
    def test_pre_rename_shell_block_is_migrated_not_duplicated(self):
        """Given an Orca shell block from before the rename, when routing is reinstalled, then it is replaced in place exactly once."""
        self.install('--optimizers')
        rc = self.base / 'shell rc'
        rc.write_text('# mine\n# >>> sudarshan-agent-loop Orca routing >>>\nold\n# <<< sudarshan-agent-loop Orca routing <<<\n')
        self.orca_shell()
        text = rc.read_text()
        self.assertNotIn('sudarshan', text)
        self.assertEqual(text.count('# >>> agent-loop Orca routing >>>'), 1)
        self.assertTrue(text.startswith('# mine\n'))

    @unittest.skipIf(WINDOWS, 'Optional launchd/systemd integration')
    def test_dream_schedule_retires_pre_rename_job(self):
        """Given a nightly Dream job from before the rename, when Dream is scheduled, then the old job is removed so Dream runs once."""
        vault = self.base / 'vault'
        vault.mkdir()
        (vault / 'INDEX.md').write_text('# Index\n')
        self.install('--vault', str(vault))
        home = self.base / 'home'
        if sys.platform == 'darwin':
            old = [home / 'Library/LaunchAgents/com.sudarshan-agent-loop.dream.plist']
        else:
            old = [home / '.config/systemd/user' / ('sudarshan-agent-loop-dream' + ext) for ext in ('.timer', '.service')]
        for path in old:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('old job')
        self.dream_schedule('--dry-run')
        self.assertTrue(all(path.exists() for path in old))
        self.dream_schedule()
        self.assertFalse(any(path.exists() for path in old))

if __name__ == '__main__':
    unittest.main()
