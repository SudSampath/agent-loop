"""Outcome-based checks for synthetic native execution evidence."""

import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from verification.native_probe import classify_ancestry, prepare, report


class NativeEvidenceTests(unittest.TestCase):
    def test_bundled_binary_alone_is_not_native_ui_evidence(self):
        """Given an Orca CLI uses the bundled binary, when classified, then native UI is unverified."""
        result = classify_ancestry([
            '/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex',
            '/Applications/Orca.app/Contents/MacOS/Orca',
        ])
        self.assertTrue(result['bundled_backend_ancestor'])
        self.assertFalse(result['native_app_ancestor'])

    def test_rtk_and_native_evidence_are_independent(self):
        """Given RTK runs under a CLI, when classified, then it does not prove desktop coverage."""
        result = classify_ancestry(['/opt/homebrew/bin/rtk', '/usr/bin/python3'])
        self.assertTrue(result['rtk_ancestor'])
        self.assertFalse(result['native_app_ancestor'])

    def test_native_parent_and_rtk_are_detected(self):
        """Given RTK descends from native ChatGPT, when classified, then both execution paths are observed."""
        result = classify_ancestry([
            '/opt/homebrew/bin/rtk', '/Applications/ChatGPT.app/Contents/MacOS/ChatGPT',
        ])
        self.assertTrue(result['rtk_ancestor'])
        self.assertTrue(result['native_app_ancestor'])

    def test_control_run_cannot_satisfy_native_acceptance(self):
        """Given an explicit RTK control, when reported, then native acceptance remains unverified."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            marker = repo / '.git' / 'desktop-probe'
            marker.mkdir(parents=True)
            (marker / 'owned-fixture').write_text('test')
            (marker / 'controls.json').write_text('[]')
            (marker / 'events.jsonl').write_text(json.dumps({
                'stage': 'explicit_rtk_control', 'native_app_ancestor': True,
                'rtk_ancestor': True,
            }) + '\n')
            result = report(repo)
            self.assertTrue(result['explicit_rtk_control_observed'])
            self.assertFalse(result['native_rtk_execution_observed'])

    def test_unowned_directory_is_not_a_fixture(self):
        """Given an ordinary directory, when inspected, then it is rejected without modification."""
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                report(Path(tmp))
            self.assertEqual(list(Path(tmp).iterdir()), [])

    @unittest.skipUnless(shutil.which('git'), 'Git is required for the synthetic execution probe')
    def test_git_status_behavior_and_control_observation(self):
        """Given a fresh synthetic repository, when git status runs, then all fixture files remain visible."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / 'fixture'
            with patch('verification.native_probe.shutil.which', return_value=None):
                prepare(repo)
            result = subprocess.run(['git', 'status', '--short'], cwd=repo, text=True, capture_output=True, timeout=15)
            self.assertEqual(result.returncode, 0)
            for index in range(40):
                self.assertIn(f'fixture-{index:02d}.txt', result.stdout)
            self.assertTrue(report(repo)['direct_control_observed'])


if __name__ == '__main__':
    unittest.main()
