"""Every testutils name conary_test and testsuite.py use must resolve.

Same approach as test_testharness_resolve.py, extended to submodule imports
at any testutils package level.
"""
import ast
import os
import subprocess
import sys

import pytest

from conftest import ROOT, HARNESS


def _sources():
    yield os.path.join(ROOT, 'testsuite.py')
    for dp, dns, fns in os.walk(os.path.join(ROOT, 'conary_test')):
        dns[:] = [d for d in dns if d != '__pycache__']
        for fn in fns:
            if fn.endswith('.py'):
                yield os.path.join(dp, fn)


def _isTestutils(module):
    return module.split('.')[0] == 'testutils'


def _isModule(modName):
    """True if modName is a testutils module file or package on disk."""
    base = os.path.join(HARNESS, *modName.split('.'))
    return os.path.isfile(base + '.py') or os.path.isdir(base)


def collect_names():
    """Return a sorted list of (module, attribute) pairs to resolve."""
    names = set()
    for path in _sources():
        with open(path, encoding='utf-8') as f:
            tree = ast.parse(f.read(), path)
        aliases = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and \
                    _isTestutils(node.module):
                for a in node.names:
                    names.add((node.module, a.name))
                    # `from testutils.servers import memcache_server`: the
                    # name is a submodule, so attribute accesses on it
                    # resolve inside testutils.servers.memcache_server.
                    # Only names that are modules on disk become aliases;
                    # a missing one still fails at the entry above.
                    sub = node.module + '.' + a.name
                    if _isModule(sub):
                        aliases[a.asname or a.name] = sub
            elif isinstance(node, ast.Import):
                for a in node.names:
                    if _isTestutils(a.name):
                        names.add((a.name, '__name__'))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and \
                    isinstance(node.value, ast.Name) and \
                    node.value.id in aliases:
                names.add((aliases[node.value.id], node.attr))
    return sorted(names)


def test_scan_finds_the_known_names():
    names = collect_names()
    for expected in [('testutils.sock_utils', 'tryConnect'),
                     ('testutils.os_utils', 'effectiveUser'),
                     ('testutils.os_utils', 'effectiveGroup'),
                     ('testutils.base_server', 'BaseServer'),
                     ('testutils.sqlharness', 'start'),
                     ('testutils.servers.nginx_server', 'NginxServer'),
                     ('testutils.servers.gunicorn_server', 'GunicornServer'),
                     ('testutils.servers.uwsgi_server', 'UwsgiServer'),
                     ('testutils.servers.memcache_server', 'MemcacheServer')]:
        assert expected in names


def _byModule():
    mods = {}
    for mod, attr in collect_names():
        mods.setdefault(mod, []).append(attr)
    return sorted(mods.items())


@pytest.mark.parametrize('mod,attrs', _byModule(), ids=lambda v: str(v)[:40])
def test_names_resolve(mod, attrs):
    # One subprocess per module: in-process ordering hides import failures.
    code = (
        "import importlib, sys\n"
        "m = importlib.import_module(%r)\n"
        "missing = []\n"
        "for attr in %r:\n"
        "    if attr == '__name__' or hasattr(m, attr):\n"
        "        continue\n"
        "    try:\n"
        "        importlib.import_module(%r + '.' + attr)\n"
        "    except ImportError:\n"
        "        missing.append(attr)\n"
        "print(missing)\n"
        "sys.exit(1 if missing else 0)\n" % (mod, attrs, mod))
    env = dict(os.environ, PYTHONPATH=HARNESS)
    r = subprocess.run([sys.executable, '-c', code], env=env,
                       capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 0, r.stdout + r.stderr
    assert r.stdout.strip() == '[]'
