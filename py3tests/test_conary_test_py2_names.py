"""conary_test no longer uses Python 2 only names, imports or idioms.

The AST walks only see code.  Recipe strings and other embedded text are
string constants and are never parsed, so they are excluded without any
string stripping (they belong to the recipe port task).
"""
import ast
import os
import re
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONARY_TEST = os.path.join(ROOT, 'conary_test')

# Paths to leave out of the scan (relative to the repo root).  Deliberately
# empty: every conary_test module is scanned.
OWNED_BY_STREAMS_TASK = ()

PY2_NAMES = ('file|cmp|unicode|long|basestring|xmlrpclib|cPickle|StringIO|'
             'cStringIO|raw_input|reduce|unichr|execfile|xrange')
PY2_MODULES = frozenset([
    'cPickle', 'StringIO', 'cStringIO', 'xmlrpclib', 'urllib2', 'urlparse',
    'httplib', 'Queue', 'ConfigParser', 'commands'])
PY2_DICT_METHODS = frozenset(['has_key', 'iteritems', 'itervalues',
                              'iterkeys'])


def _excluded(path):
    rel = os.path.relpath(path, ROOT)
    return any(rel.startswith(x) for x in OWNED_BY_STREAMS_TASK)


def _sources(root=None):
    for dirpath, dirnames, filenames in os.walk(root or CONARY_TEST):
        for fn in sorted(filenames):
            if fn.endswith('.py'):
                path = os.path.join(dirpath, fn)
                if _excluded(path):
                    continue
                with open(path, encoding='utf-8') as f:
                    yield path, f.read()


def _pyflakes_lines():
    proc = subprocess.run([sys.executable, '-m', 'pyflakes', CONARY_TEST],
                          capture_output=True, text=True, cwd=ROOT)
    # pyflakes exits 1 when it has warnings; anything else is a crash
    assert proc.returncode in (0, 1), proc.stderr
    return proc.stdout.splitlines()


def test_pyflakes_reports_no_undefined_py2_names():
    pytest.importorskip('pyflakes')
    bad = [l for l in _pyflakes_lines()
           if re.search(r"undefined name '(%s)'" % PY2_NAMES, l)
           and not _excluded(os.path.join(ROOT, l.split(':')[0]))]
    assert bad == []


def test_pyflakes_reports_no_shadowed_module_locals():
    pytest.importorskip('pyflakes')
    bad = [l for l in _pyflakes_lines()
           if 'referenced before assignment' in l]
    assert bad == []


def _py2_idioms(src, path):
    tree = ast.parse(src, path)
    hits = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Attribute):
                if f.attr in PY2_DICT_METHODS:
                    hits.append('%s:%d %s' % (path, node.lineno, f.attr))
                if f.attr == 'sort' and node.args:
                    hits.append('%s:%d positional sort' % (path, node.lineno))
                if f.attr == 'next' and not node.args:
                    hits.append('%s:%d .next()' % (path, node.lineno))
                if f.attr in ('encodestring', 'decodestring'):
                    hits.append('%s:%d %s' % (path, node.lineno, f.attr))
                if f.attr == 'assertEquals':
                    hits.append('%s:%d assertEquals' % (path, node.lineno))
            if (isinstance(f, ast.Name) and f.id == 'sorted'
                    and len(node.args) > 1):
                hits.append('%s:%d positional sorted' % (path, node.lineno))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split('.')[0] in PY2_MODULES:
                    hits.append('%s:%d import %s' % (path, node.lineno,
                                                     alias.name))
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.module.split('.')[0] in PY2_MODULES:
                hits.append('%s:%d from %s' % (path, node.lineno,
                                               node.module))
    return hits


def test_no_py2_idioms_in_conary_test_code():
    hits = []
    for path, src in _sources():
        hits.extend(_py2_idioms(src, path))
    assert hits == []


@pytest.mark.parametrize('src, expected', [
    ('d.has_key(1)\n', 1),
    ('for k, v in d.iteritems(): pass\n', 1),
    ('x.sort(lambda a, b: 0)\n', 1),
    ('sorted(x, f)\n', 1),
    ('it.next()\n', 1),
    ('base64.decodestring(x)\n', 1),
    ('next(it)\n', 0),
    ('import cPickle\n', 1),
    ('from StringIO import StringIO\n', 1),
    ('self.assertEquals(1, 1)\n', 1),
    ('x = "d.has_key(1); import cPickle"\n', 0),
    ('x.sort(key=len)\nimport pickle\n', 0),
])
def test_idiom_scanner_bites(src, expected):
    assert len(_py2_idioms(src, 'scratch.py')) == expected


def test_pyflakes_scan_bites(tmp_path, monkeypatch):
    pytest.importorskip('pyflakes')
    (tmp_path / 'bad.py').write_text('x = file("a")\n')
    proc = subprocess.run([sys.executable, '-m', 'pyflakes', str(tmp_path)],
                          capture_output=True, text=True)
    assert re.search(r"undefined name '(%s)'" % PY2_NAMES, proc.stdout)
