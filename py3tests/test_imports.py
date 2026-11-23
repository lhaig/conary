"""Every module under conary/ must import on Python 3.

Each module is imported in its own interpreter so that one module cannot
pass only because another one already imported its dependencies, and so a
failed import cannot leave half-initialised modules behind.

The C extensions must be built first: `make -C conary/lib/ext` and
`make -C conary/lib elf.so`.
"""
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# module -> missing dependency name. Only for dependencies that have no
# Python 3 package at all.
#   pgsql: SAS's own PostgreSQL binding, Python 2 only, not packaged.
#   kid:   the Python-2-only template engine used by the web UI.
ALLOWED_FAILURES = {
    'conary.dbstore.postgresql_drv': 'pgsql',
    'conary.dbstore.pgpool_drv': 'pgsql',   # imports postgresql_drv
    'conary.server.templates': 'kid',
    'conary.web.repos_web': 'kid',
}


def _modules():
    mods = []
    base = os.path.join(ROOT, 'conary')
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = sorted(d for d in dirnames if d != '__pycache__')
        for fn in sorted(filenames):
            if not fn.endswith('.py'):
                continue
            rel = os.path.relpath(os.path.join(dirpath, fn), ROOT)[:-3]
            parts = rel.split(os.sep)
            if parts[-1] == '__init__':
                parts.pop()
            mods.append('.'.join(parts))
    return sorted(mods)


def _run(code):
    env = dict(os.environ, PYTHONPATH=ROOT, PYTHONDONTWRITEBYTECODE='1')
    return subprocess.run([sys.executable, '-c', code], cwd=ROOT, env=env,
                          capture_output=True, text=True, timeout=120)


@pytest.mark.parametrize('module', _modules())
def test_import(module):
    if module in ALLOWED_FAILURES:
        dep = ALLOWED_FAILURES[module]
        r = _run('import %s' % module)
        assert r.returncode != 0, '%s now imports; drop it from ALLOWED_FAILURES' % module
        r = _run('try:\n import %s\nexcept ModuleNotFoundError as e:\n'
                 ' print("MISSING=" + str(e.name))\n' % module)
        assert 'MISSING=%s' % dep in r.stdout, (r.stdout, r.stderr[-2000:])
        return
    r = _run('import %s' % module)
    assert r.returncode == 0, r.stderr[-3000:]


def test_allowed_failures_are_real_modules():
    assert set(ALLOWED_FAILURES) <= set(_modules())
