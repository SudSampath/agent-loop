import datetime
import fcntl
import os
from pathlib import Path
import tempfile

START = '<!-- sudarshan-agent-loop:start -->'
END = '<!-- sudarshan-agent-loop:end -->'


def merge(old, body):
    block = START + '\n' + body.rstrip() + '\n' + END
    if START in old or END in old:
        if old.count(START) != 1 or old.count(END) != 1 or old.index(START) > old.index(END):
            raise ValueError('Malformed managed instruction block; repair it before installing')
        a, rest = old.split(START)
        _, b = rest.split(END)
        return a + block + b
    return old + ('\n\n' if old else '') + block + '\n'


def write(path, content, executable=False):
    path = Path(path)
    if path.is_symlink():
        raise ValueError(f'Refusing to replace symlink: {path}')
    if path.exists() and path.read_text() == content:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        stamp = datetime.datetime.now().strftime('%Y%m%d%H%M%S%f')
        backup = path.with_name(path.name + '.agent-loop-backup-' + stamp)
        backup.write_bytes(path.read_bytes())
        backup.chmod(0o600)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix='.agent-loop-')
    try:
        with os.fdopen(fd, 'w') as f:
            f.write(content)
        os.chmod(tmp, 0o700 if executable else 0o600)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def instructions(home, filename, body):
    home = Path(home)
    home.mkdir(parents=True, exist_ok=True)
    with (home / '.agent-loop.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        p = home / filename
        write(p, merge(p.read_text() if p.exists() else '', body))
