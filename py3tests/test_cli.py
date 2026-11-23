"""Basic CLI entry points run cleanly (exit code, output, empty stderr)."""
import os
import re
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _version():
    with open(os.path.join(ROOT, 'conary', 'constants.py')) as f:
        return re.search(r"^version\s*=\s*['\"]([^'\"]+)['\"]", f.read(),
                         re.M).group(1)


def _run(tmp_path, script, flag):
    env = {'PATH': os.environ.get('PATH', ''), 'PYTHONPATH': ROOT,
           'PYTHONDONTWRITEBYTECODE': '1', 'HOME': str(tmp_path)}
    return subprocess.run(
        [sys.executable, os.path.join(ROOT, 'commands', script), flag],
        env=env, cwd=str(tmp_path), capture_output=True, text=True,
        stdin=subprocess.DEVNULL, timeout=120)


@pytest.mark.parametrize('script', ['conary', 'cvc'])
def test_version(tmp_path, script):
    r = _run(tmp_path, script, '--version')
    assert r.returncode == 0
    assert r.stdout.strip() == _version() == '2.5.9'
    assert r.stderr == ''


# Bare --help exits 1 by upstream design (mainhandler.usage(rc=1)).
@pytest.mark.parametrize('script,words', [
    ('conary', ['update', 'query']),
    ('cvc', ['cook']),
])
def test_help(tmp_path, script, words):
    r = _run(tmp_path, script, '--help')
    assert r.returncode == 1
    for w in words:
        assert w in r.stdout
    assert r.stderr == ''
