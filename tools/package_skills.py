"""Build free, reproducible Agent Skills archives without installing anything."""

import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import tempfile
import os
import posixpath
import zipfile

ROOT = Path(__file__).resolve().parents[1]
RESOURCE_DIRS = {'references', 'scripts', 'assets', 'agents'}
MARKER = '.agent-loop-skills-output'


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def metadata(text):
    """Read the repository's one-line scalar identity fields, not general YAML."""
    lines = text.splitlines()
    if not lines or lines[0] != '---':
        raise ValueError('SKILL.md must start with YAML frontmatter')
    try:
        end = lines.index('---', 1)
    except ValueError as error:
        raise ValueError('SKILL.md frontmatter is not closed') from error
    result = {}
    for line in lines[1:end]:
        match = re.fullmatch(r'(name|description|license):\s*(.+)', line)
        if match:
            key, value = match.groups()
            if key in result:
                raise ValueError(f'Duplicate skill field: {key}')
            if value.startswith('"'):
                value = json.loads(value)
            elif value.startswith("'") and value.endswith("'"):
                value = value[1:-1].replace("''", "'")
            if not isinstance(value, str) or not value.strip() or value in {'|', '>'}:
                raise ValueError(f'Use a nonempty one-line scalar for {key}')
            result[key] = value
    if set(result) != {'name', 'description', 'license'}:
        raise ValueError('Skill requires name, description, and license metadata')
    if result['license'] != 'MIT':
        raise ValueError('The free bundle contains MIT skills only')
    return result


def skill_files(folder, license_data):
    if folder.is_symlink():
        raise ValueError('Symlinked skill directories are not packaged')
    files = {}
    for path in sorted(folder.rglob('*')):
        relative = path.relative_to(folder)
        if path.is_symlink():
            raise ValueError(f'Symlinked resource: {relative}')
        if '__pycache__' in relative.parts or path.name in {'.DS_Store'} or path.suffix == '.pyc':
            continue
        if path.is_dir():
            continue
        if relative.as_posix() != 'SKILL.md' and relative.parts[0] not in RESOURCE_DIRS:
            raise ValueError(f'Unexpected skill file: {relative}')
        files[relative.as_posix()] = path.read_bytes()
    if 'SKILL.md' not in files:
        raise ValueError(f'Missing SKILL.md: {folder.name}')
    # Keep independently shared archives under the repository's existing license.
    files['LICENSE'] = license_data
    return files


def archive_bytes(files):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        for name, data in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.compress_type = zipfile.ZIP_DEFLATED
            mode = 0o100755 if '/scripts/' in name else 0o100644
            info.external_attr = mode << 16
            archive.writestr(info, data)
    return buffer.getvalue()


def validate_references(files):
    for name, data in files.items():
        if not name.endswith('.md'):
            continue
        # Instructions can show template links inside inline/fenced code.
        text = re.sub(r'(`+).*?\1', '', data.decode('utf-8'), flags=re.S)
        text = re.sub(r'^~{3,}[^\n]*\n.*?^~{3,}[ \t]*$', '', text, flags=re.S | re.M)
        for link in re.findall(r'\[[^\]]*\]\(([^\s)]+)\)', text):
            if link.startswith(('#', 'https://', 'http://', 'mailto:')):
                continue
            target = link.split('#', 1)[0]
            resolved = posixpath.normpath(posixpath.join(posixpath.dirname(name), target))
            if resolved not in files:
                raise ValueError(f'Missing bundled reference: {name} -> {link}')


def atomic_write(path, data):
    descriptor, temporary = tempfile.mkstemp(prefix=path.name + '.', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'wb') as handle:
            handle.write(data)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def build(root=ROOT, output=None):
    root = Path(root).resolve()
    requested_output = Path(output) if output is not None else root / 'dist/skills'
    if requested_output.is_symlink():
        raise ValueError('Output directory must not be a symlink')
    output = requested_output.resolve()
    source = root / 'skills'
    if output == root or output == source or source in output.parents:
        raise ValueError('Output must not replace the checkout or skill sources')
    if output.exists() and any(output.iterdir()):
        marker = output / MARKER
        if not marker.is_file() or marker.read_text(encoding='utf-8') != 'agent-loop-free-skills-v1\n':
            raise ValueError('Refusing to write into a nonempty unmanaged output directory')

    catalog = json.loads((source / 'catalog.json').read_text(encoding='utf-8'))
    if catalog.get('license') != 'MIT' or catalog.get('price') != 'free':
        raise ValueError('Catalog must describe the free MIT bundle')
    license_data = (root / 'LICENSE').read_bytes()
    guide = (root / 'docs/skills.md').read_bytes()
    entries = catalog['skills']
    names = [entry['name'] for entry in entries]
    if len(names) != len(set(names)):
        raise ValueError('Duplicate skill in catalog')
    actual = {path.parent.name for path in source.glob('*/SKILL.md')}
    if set(names) != actual:
        raise ValueError('Catalog must include each skill directory exactly once')

    manifest = {'format_version': 1, 'license': 'MIT', 'price': 'free', 'skills': []}
    generated = {'README.md': guide}
    combined = {'LICENSE': license_data, 'README.md': guide}
    for entry in entries:
        name = entry['name']
        if len(name) > 64 or not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', name):
            raise ValueError('Invalid skill name')
        files = skill_files(source / name, license_data)
        validate_references(files)
        identity = metadata(files['SKILL.md'].decode('utf-8'))
        if identity['name'] != name:
            raise ValueError('Skill name must match its directory')
        prefixed = {f'{name}/{path}': data for path, data in files.items()}
        generated[f'{name}.zip'] = archive_bytes(prefixed)
        combined.update({f'skills/{name}/{path}': data for path, data in files.items()})
        manifest['skills'].append({
            **entry, 'description': identity['description'], 'license': identity['license'],
            'files': [{'path': path, 'bytes': len(data), 'sha256': sha256(data)}
                      for path, data in sorted(files.items())],
        })
    encoded_manifest = (json.dumps(manifest, indent=2, ensure_ascii=False) + '\n').encode()
    generated['catalog.json'] = encoded_manifest
    combined['catalog.json'] = encoded_manifest
    generated['agent-loop-skills.zip'] = archive_bytes(combined)
    generated['SHA256SUMS'] = ''.join(
        f'{sha256(data)}  {name}\n' for name, data in sorted(generated.items())).encode()

    output.mkdir(parents=True, exist_ok=True)
    for name, data in generated.items():
        atomic_write(output / name, data)
    atomic_write(output / MARKER, b'agent-loop-free-skills-v1\n')
    return {'skills': len(entries), 'license': 'MIT', 'price': 'free',
            'output_directory': str(output), 'bundle': str(output / 'agent-loop-skills.zip'),
            'individual_archives': [f'{name}.zip' for name in names]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path)
    args = parser.parse_args()
    print(json.dumps(build(output=args.output_dir), indent=2))


if __name__ == '__main__':
    main()
