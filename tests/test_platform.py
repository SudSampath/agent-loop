import base64
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'runtime'))
from platform_support import file_lock, launcher_content, run_agent


class PlatformTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('pwsh'), 'PowerShell is needed for native launcher tests')
    def test_powershell_launcher_roundtrips_arguments_and_exit(self):
        """Given special paths/prompts, when PowerShell launches Python, then preserve literal arguments and exit status."""
        with tempfile.TemporaryDirectory(prefix="agent's space ") as temp:
            root = Path(temp)
            fake = root / 'fake.py'
            fake.write_text('import sys,json\nprint(json.dumps(sys.argv[1:]))\nsys.exit(23)\n', encoding='utf-8')
            launcher = root / 'launch.ps1'
            launcher.write_text(launcher_content(sys.executable, fake, 'codex', windows=True), encoding='utf-8')
            expected = ['two words', '', '"quoted"', "O'Brien", '$env:HOME', '$(throw "oops")', 'a&b|c;d', '100% !', '日本語', 'C:\\space dir\\']
            result = subprocess.run(['pwsh', '-NoProfile', '-File', str(launcher), *expected], capture_output=True, text=True, encoding='utf-8')
            self.assertEqual(result.returncode, 23, result.stderr)
            self.assertEqual(json.loads(result.stdout), ['codex', *expected])

    @unittest.skipUnless(shutil.which('pwsh'), 'PowerShell is needed for shim tests')
    def test_windows_powershell_shim_roundtrips_arguments(self):
        """Given an npm-style PowerShell shim, when launching on Windows, then pass data without cmd evaluation."""
        with tempfile.TemporaryDirectory(prefix="shim's space ") as temp:
            shim = Path(temp) / 'codex.ps1'
            shim.write_text('ConvertTo-Json -InputObject @($args) -Compress\nexit 17\n', encoding='utf-8')
            expected = ['', 'hello world', "O'Brien", '$(throw "oops")', '& | % !', '日本語', '--search']
            captured = []
            def run(command):
                result = subprocess.run(command, text=True, encoding='utf-8', capture_output=True)
                captured.append(result)
                return result.returncode
            with patch('platform_support.WINDOWS', True), patch('platform_support.subprocess.call', side_effect=run):
                with self.assertRaises(SystemExit) as error:
                    run_agent(str(shim), expected)
            self.assertEqual(error.exception.code, 17, captured[0].stderr)
            self.assertEqual(json.loads(captured[0].stdout), expected)

    def test_file_lock_serializes_processes(self):
        """Given a held lock, when another process requests it, then wait until release."""
        with tempfile.TemporaryDirectory() as temp:
            lock = Path(temp) / 'lock'
            marker = Path(temp) / 'acquired'
            ready = Path(temp) / 'ready'
            script = ('import sys; from pathlib import Path; '
                      f'sys.path.insert(0, {str(ROOT / "runtime")!r}); '
                      'from platform_support import file_lock\n'
                      f'Path({str(ready)!r}).touch()\n'
                      f'with file_lock({str(lock)!r}): Path({str(marker)!r}).touch()\n')
            with file_lock(lock):
                child = subprocess.Popen([sys.executable, '-c', script])
                try:
                    import time
                    deadline = time.monotonic() + 10
                    while not ready.exists() and time.monotonic() < deadline:
                        time.sleep(0.02)
                    self.assertTrue(ready.exists())
                    time.sleep(0.1)
                    self.assertFalse(marker.exists())
                except BaseException:
                    child.kill()
                    child.wait()
                    raise
            self.assertEqual(child.wait(timeout=10), 0)
            self.assertTrue(marker.exists())

    def test_windows_batch_only_fails_with_actionable_message(self):
        """Given a batch-only CLI, when launching, then stop rather than reinterpret the prompt in cmd.exe."""
        with patch('platform_support.WINDOWS', True):
            with self.assertRaisesRegex(SystemExit, 'native CLI'):
                run_agent('codex.cmd', ['hello'])

    @unittest.skipUnless(os.name == 'nt', 'Windows-specific installer boundary')
    def test_windows_rejects_optimizers_before_writes(self):
        """Given native Windows, when optimizers are requested, then fail before installing anything."""
        with tempfile.TemporaryDirectory() as temp:
            prefix = Path(temp) / 'install'
            result = subprocess.run([sys.executable, str(ROOT / 'bootstrap.py'), 'install', '--workspace', temp,
                                     '--prefix', str(prefix), '--optimizers'], capture_output=True, text=True, encoding='utf-8')
            self.assertEqual(result.returncode, 1)
            self.assertIn('Native Windows', result.stderr)
            self.assertFalse(prefix.exists())

    @unittest.skipUnless(shutil.which('pwsh'), 'PowerShell is needed for installer tests')
    def test_powershell_installer_preview_is_nonmutating(self):
        """Given the PowerShell entrypoint, when previewing, then validate options without creating homes."""
        with tempfile.TemporaryDirectory(prefix="install's space ") as temp:
            prefix = Path(temp) / 'install'
            result = subprocess.run(['pwsh', '-NoProfile', '-File', str(ROOT / 'install.ps1'),
                '-Workspace', temp, '-Prefix', str(prefix), '-CodexHome', str(Path(temp) / 'codex'),
                '-ClaudeHome', str(Path(temp) / 'claude'), '-Python', sys.executable, '-DryRun'],
                text=True, encoding='utf-8', capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('Preview complete', result.stdout)
            self.assertFalse(prefix.exists())


if __name__ == '__main__':
    unittest.main()
