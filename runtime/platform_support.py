"""Small platform boundary; no third-party dependencies."""
import base64
from contextlib import contextmanager
import errno
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import time

WINDOWS = os.name == 'nt'


@contextmanager
def file_lock(path, timeout=30):
    """Lock byte zero on Windows, or the file on POSIX; always release."""
    with Path(path).open('a+b') as handle:
        if WINDOWS:
            import msvcrt
            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write(b'\0')
                handle.flush()
            deadline = time.monotonic() + timeout
            while True:
                handle.seek(0)
                try:
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError as error:
                    if error.errno not in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                        raise
                    if time.monotonic() >= deadline:
                        raise TimeoutError(f'Timed out waiting for {path}') from error
                    time.sleep(0.05)
            try:
                yield
            finally:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)


def ps_quote(value):
    return "'" + str(value).replace("'", "''") + "'"


def launcher_content(python, runtime, agent, windows=WINDOWS):
    if windows:
        return ("#requires -Version 7.4\n$ErrorActionPreference = 'Stop'\n"
                "$PSNativeCommandArgumentPassing = 'Standard'\n"
                f'& {ps_quote(python)} {ps_quote(runtime)} {ps_quote(agent)} @args\n'
                'exit $LASTEXITCODE\n')
    return '#!/bin/sh\nexec ' + shlex.join([str(python), str(runtime), agent]) + ' "$@"\n'


def find_agent(name):
    if not WINDOWS:
        return shutil.which(name)
    # Respect PATH order, but prefer native exe/PowerShell over a cmd.exe shim.
    for directory in os.environ.get('PATH', '').split(os.pathsep):
        if not directory:
            continue
        for suffix in ('.exe', '.ps1', '.cmd', '.bat'):
            candidate = Path(directory.strip('"')) / (name + suffix)
            if candidate.is_file():
                return str(candidate)
    return None


def run_agent(binary, args):
    if not WINDOWS:
        os.execv(binary, [binary, *args])
    if Path(binary).suffix.lower() in ('.cmd', '.bat'):
        raise SystemExit(f'Only a batch launcher was found: {binary}. Install the native CLI or its npm PowerShell shim (.ps1).')
    if Path(binary).suffix.lower() == '.ps1':
        pwsh = shutil.which('pwsh')
        if not pwsh:
            raise SystemExit('PowerShell 7.4+ (pwsh) is required for this CLI shim.')
        # Encode a script made entirely from literal-quoted data; never pass prompts through cmd.exe.
        script = ("$ErrorActionPreference = 'Stop'; $PSNativeCommandArgumentPassing = 'Standard'; "
                  + '& ' + ps_quote(binary) + ' ' + ' '.join(ps_quote(a) for a in args)
                  + '; exit $LASTEXITCODE')
        encoded = base64.b64encode(script.encode('utf-16-le')).decode('ascii')
        command = [pwsh, '-NoLogo', '-NoProfile', '-EncodedCommand', encoded]
    else:
        command = [binary, *args]
    # Inherit terminal handles/environment so interactive login and TUI sessions work.
    raise SystemExit(subprocess.call(command))
