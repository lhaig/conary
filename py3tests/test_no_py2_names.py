"""conary/ no longer uses the Python 2 only names or positional comparators."""
import ast
import os
import re
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONARY = os.path.join(ROOT, 'conary')


def _sources():
    for dirpath, dirnames, filenames in os.walk(CONARY):
        for fn in filenames:
            if fn.endswith('.py'):
                path = os.path.join(dirpath, fn)
                with open(path, encoding='utf-8') as f:
                    yield path, f.read()


def test_pyflakes_reports_no_undefined_py2_names():
    pytest.importorskip('pyflakes')
    proc = subprocess.run([sys.executable, '-m', 'pyflakes', CONARY],
                          capture_output=True, text=True, cwd=ROOT)
    # pyflakes exits 1 when it has warnings; anything else is a crash
    assert proc.returncode in (0, 1), proc.stderr
    bad = [l for l in proc.stdout.splitlines()
           if re.search(r"undefined name '(file|cmp|xmlrpclib)'", l)]
    assert bad == []


def test_no_tuple_parameter_placeholders():
    hits = [p for p, src in _sources() if 'xxx_todo_changeme' in src]
    assert hits == []


def test_no_positional_sort_comparators():
    hits = []
    for path, src in _sources():
        tree = ast.parse(src, path)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            f = node.func
            if isinstance(f, ast.Attribute) and f.attr == 'sort' and node.args:
                # NodeData.sort(sortAlg) and friends take a comparator and
                # wrap it themselves; list.sort takes keywords only.
                if not _is_nodedata_sort(f):
                    hits.append('%s:%d' % (path, node.lineno))
            if (isinstance(f, ast.Name) and f.id == 'sorted'
                    and len(node.args) > 1):
                hits.append('%s:%d' % (path, node.lineno))
    assert hits == []


def _is_nodedata_sort(attr):
    value = attr.value
    return isinstance(value, ast.Name) and value.id == 'nodeData'


def test_no_cmp_keyword_argument():
    for path, src in _sources():
        for node in ast.walk(ast.parse(src, path)):
            if isinstance(node, ast.Call):
                assert all(k.arg != 'cmp' for k in node.keywords), (
                    '%s:%d' % (path, node.lineno))


def test_every_dunder_cmp_class_gets_ordering():
    import importlib
    from conary.lib.compat import CmpMixin
    missing = []
    for path, src in _sources():
        if '__cmp__' not in src or path.endswith('compat.py'):
            continue
        tree = ast.parse(src, path)
        modname = os.path.relpath(path, ROOT)[:-3].replace(os.sep, '.')
        if modname.endswith('.streams') and 'ext' in modname:
            continue    # loaded by path in test_rich_compare
        mod = importlib.import_module(modname)
        for node in ast.walk(tree):
            if (isinstance(node, ast.ClassDef) and any(
                    isinstance(n, ast.FunctionDef) and n.name == '__cmp__'
                    for n in node.body)):
                cls = getattr(mod, node.name, None)
                if cls is not None and not issubclass(cls, CmpMixin):
                    missing.append('%s.%s' % (modname, node.name))
    assert missing == []
