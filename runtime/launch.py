import json
import os
from pathlib import Path
import shutil
import sys

from common import instructions, write


def main():
    cfg = json.loads((Path(__file__).parent / 'machine.json').read_text())
    agent, *args = sys.argv[1:]
    binary = shutil.which(agent)
    if not binary:
        raise SystemExit(f'{agent} is missing from PATH; see the setup guide')
    if args and args[0] in ('--version', '-V', '--help', '-h'):
        os.execv(binary, [binary, *args])
    env_key, filename = ('CODEX_HOME', 'AGENTS.md') if agent == 'codex' else ('CLAUDE_CONFIG_DIR', 'CLAUDE.md')
    home = os.environ.get(env_key, cfg[agent + '_home'])
    os.environ[env_key] = home
    for source in (Path(__file__).parent / 'skills').rglob('*.md'):
        target = Path(home) / 'skills' / source.relative_to(Path(__file__).parent / 'skills')
        if target.exists() and target.read_bytes() != source.read_bytes():
            raise SystemExit(f'Conflicting skill in active runtime home: {target}')
        write(target, source.read_text())
    instructions(home, filename, cfg['instructions'])
    if cfg['optimizers']:
        from optimizers import configure
        configure(Path(home), agent)
        headroom = shutil.which('headroom')
        if not headroom:
            raise SystemExit('headroom missing; install dependencies or reinstall without --optimizers')
        os.execv(headroom, [headroom, 'wrap', agent, '--port', str(cfg['port']), '--code-memory', 'none', '--', *args])
    os.execv(binary, [binary, *args])


if __name__ == '__main__':
    main()
