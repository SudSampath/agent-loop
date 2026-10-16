import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from tools import package_skills


def fixture(root):
    skill = root / 'skills/example-skill'
    (skill / 'references').mkdir(parents=True)
    (skill / 'SKILL.md').write_text(
        '---\nname: example-skill\ndescription: Inspect synthetic examples.\nlicense: MIT\n---\n'
        'Read the [reference](references/example.md).\n', encoding='utf-8')
    (skill / 'references/example.md').write_text('Synthetic reference.\n', encoding='utf-8')
    (root / 'docs').mkdir()
    (root / 'docs/skills.md').write_text('Synthetic package guide.\n', encoding='utf-8')
    (root / 'LICENSE').write_text('MIT License\nSynthetic fixture\n', encoding='utf-8')
    (root / 'skills/catalog.json').write_text(json.dumps({
        'license': 'MIT', 'price': 'free',
        'skills': [{'name': 'example-skill', 'group': 'standalone',
                    'requires': ['Synthetic input'], 'example': 'Inspect this example.'}]}),
        encoding='utf-8')
    return skill


class SkillPackageTests(unittest.TestCase):
    def test_repository_bundle_contains_all_skills_and_original_resources(self):
        """Given the real skill sources, when bundled, then all eight retain their resources and license."""
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / 'distribution'
            result = package_skills.build(output=output)
            self.assertEqual(result['skills'], 8)
            catalog = json.loads((output / 'catalog.json').read_text())
            with zipfile.ZipFile(output / 'agent-loop-skills.zip') as combined:
                for skill in catalog['skills']:
                    name = skill['name']
                    self.assertEqual(
                        combined.read(f'skills/{name}/SKILL.md'),
                        (package_skills.ROOT / 'skills' / name / 'SKILL.md').read_bytes())
                    with zipfile.ZipFile(output / f'{name}.zip') as individual:
                        for entry in skill['files']:
                            data = individual.read(f'{name}/{entry["path"]}')
                            self.assertEqual(len(data), entry['bytes'])
                            self.assertEqual(hashlib.sha256(data).hexdigest(), entry['sha256'])
                            self.assertEqual(combined.read(f'skills/{name}/{entry["path"]}'), data)
                        self.assertEqual(individual.read(f'{name}/LICENSE'),
                                         (package_skills.ROOT / 'LICENSE').read_bytes())
                self.assertFalse(any('evidence/' in name or '/.git/' in name for name in combined.namelist()))
            for line in (output / 'SHA256SUMS').read_text().splitlines():
                expected, name = line.split('  ', 1)
                self.assertEqual(hashlib.sha256((output / name).read_bytes()).hexdigest(), expected)

    def test_archives_are_reproducible_and_sources_are_unchanged(self):
        """Given identical sources in two builds, when packaged, then archive bytes match without source edits."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / 'source'
            fixture(root)
            before = {str(p.relative_to(root)): p.read_bytes() for p in root.rglob('*') if p.is_file()}
            first, second = Path(temporary) / 'one', Path(temporary) / 'two'
            package_skills.build(root, first)
            package_skills.build(root, second)
            for path in first.iterdir():
                self.assertEqual(path.read_bytes(), (second / path.name).read_bytes())
            self.assertEqual(before, {str(p.relative_to(root)): p.read_bytes() for p in root.rglob('*') if p.is_file()})

    def test_unmanaged_output_is_preserved(self):
        """Given user files in an output directory, when building, then they are not overwritten."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / 'source'
            fixture(root)
            output = Path(temporary) / 'output'
            output.mkdir()
            (output / 'README.md').write_text('User-owned artifact')
            with self.assertRaises(ValueError):
                package_skills.build(root, output)
            self.assertEqual((output / 'README.md').read_text(), 'User-owned artifact')

    def test_sources_cannot_be_used_as_output(self):
        """Given a source-directory output request, when building, then the checkout is protected."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixture(root)
            for output in [root, root / 'skills', root / 'skills/example-skill/build']:
                with self.subTest(output=output), self.assertRaises(ValueError):
                    package_skills.build(root, output)

    def test_missing_reference_fails_before_creating_output(self):
        """Given an incomplete skill, when packaging, then the broken archive is not emitted."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / 'source'
            skill = fixture(root)
            (skill / 'references/example.md').unlink()
            output = Path(temporary) / 'output'
            with self.assertRaises(ValueError):
                package_skills.build(root, output)
            self.assertFalse(output.exists())

    def test_example_links_in_code_are_not_treated_as_resources(self):
        """Given Markdown examples inside code, when packaging, then placeholders are preserved without false missing-file errors."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / 'source'
            skill = fixture(root)
            path = skill / 'SKILL.md'
            path.write_text(path.read_text() + '\nExample: `- [Name](<filename>)`\n'
                            '```md\n[Example](not-a-resource.md)\n```\n')
            output = Path(temporary) / 'output'
            package_skills.build(root, output)
            with zipfile.ZipFile(output / 'example-skill.zip') as archive:
                self.assertEqual(archive.read('example-skill/SKILL.md'), path.read_bytes())

    def test_symlinked_resource_is_not_copied(self):
        """Given a resource linked to private data, when packaging, then it is rejected."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / 'source'
            skill = fixture(root)
            private = Path(temporary) / 'private.txt'
            private.write_text('Synthetic private fixture')
            try:
                (skill / 'references/leak.txt').symlink_to(private)
            except OSError:
                self.skipTest('Creating symlinks requires privileges on this platform')
            with self.assertRaises(ValueError):
                package_skills.build(root, Path(temporary) / 'output')

    def test_catalog_cannot_omit_a_skill(self):
        """Given an unlisted skill source, when packaging, then catalog drift is reported."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / 'source'
            fixture(root)
            extra = root / 'skills/unlisted'
            extra.mkdir()
            (extra / 'SKILL.md').write_text('Synthetic unlisted skill')
            with self.assertRaises(ValueError):
                package_skills.build(root, Path(temporary) / 'output')

    def test_undeclared_top_level_private_file_is_rejected(self):
        """Given an unexpected private file beside SKILL.md, when packaging, then it cannot leak."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / 'source'
            skill = fixture(root)
            (skill / 'account.json').write_text('{"synthetic": true}')
            with self.assertRaises(ValueError):
                package_skills.build(root, Path(temporary) / 'output')


if __name__ == '__main__':
    unittest.main()
