"""The conary_test C extensions (_norpmlock.so, norpmlock.so) must build
and load."""
import os
import shutil
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CT = os.path.join(ROOT, 'conary_test')

pytestmark = pytest.mark.skipif(
    not sys.platform.startswith('linux') or not shutil.which('make')
    or not shutil.which('gcc'),
    reason='needs Linux with make and gcc')

SCRIPT = """
import sys
from conary_test import norpmlock
assert norpmlock.__file__.endswith('norpmlock.so'), norpmlock.__file__
norpmlock.open(sys.argv[1])
try:
    norpmlock.open('/nonexistent.so')
except RuntimeError:
    pass
else:
    raise SystemExit('open of a missing file did not raise RuntimeError')
print('ok')
"""


def test_build_and_load():
    r = subprocess.run(['make', '-C', CT], capture_output=True, text=True,
                       timeout=300)
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-2000:]
    env = dict(os.environ)
    env['PYTHONPATH'] = os.pathsep.join(
        [ROOT, os.path.join(ROOT, 'testharness')])
    r = subprocess.run(
        [sys.executable, '-c', SCRIPT, os.path.join(CT, '_norpmlock.so')],
        capture_output=True, text=True, env=env, cwd=ROOT, timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr
    assert r.stdout.strip() == 'ok'
