"""Every testrunner name conary_test and testsuite.py use must resolve.

Scans the sources with ast for `from testrunner[.x] import a` statements and
for `<alias>.<attr>` accesses on imported testrunner modules, then resolves
them in a subprocess with testharness/ on the path.
"""
import ast
import os
import re
import subprocess
import sys

from conftest import ROOT, HARNESS

def _sources():
    yield os.path.join(ROOT, 'testsuite.py')
    for dp, dns, fns in os.walk(os.path.join(ROOT, 'conary_test')):
        dns[:] = [d for d in dns if d != '__pycache__']
        for fn in fns:
            if fn.endswith('.py'):
                yield os.path.join(dp, fn)


def collect_names():
    """Return a sorted list of (module, attribute) pairs to resolve."""
    names = set()
    for path in _sources():
        with open(path, encoding='utf-8') as f:
            tree = ast.parse(f.read(), path)
        aliases = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and \
                    node.module.split('.')[0] == 'testrunner':
                for a in node.names:
                    if node.module == 'testrunner':
                        aliases[a.asname or a.name] = 'testrunner.' + a.name
                        names.add(('testrunner', a.name))
                    else:
                        names.add((node.module, a.name))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    if a.name.split('.')[0] == 'testrunner':
                        # `import testrunner.x` is accessed as full dotted
                        # name; just require the module to import.
                        names.add((a.name, '__name__'))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and \
                    isinstance(node.value, ast.Name) and \
                    node.value.id in aliases:
                names.add((aliases[node.value.id], node.attr))
    return sorted(names)


def test_scan_finds_the_known_names():
    names = collect_names()
    for expected in [('testrunner.testhelp', 'context'),
                     ('testrunner.testhelp', 'TestCase'),
                     ('testrunner.testcase', 'safe_repr'),
                     ('testrunner.decorators', 'requireBinary'),
                     ('testrunner.runner', 'SkipTestException'),
                     ('testrunner.testcase', 'LogFilter'),
                     ('testrunner.testcase', 'TestCaseWithWorkDir'),
                     ('testrunner.testhelp', 'findPorts'),
                     ('testrunner.suite', 'TestSuite')]:
        assert expected in names


def test_all_names_resolve():
    code = (
        "import importlib, sys\n"
        "missing = []\n"
        "for mod, attr in %r:\n"
        "    m = importlib.import_module(mod)\n"
        "    if hasattr(m, attr):\n"
        "        continue\n"
        "    try:\n"
        "        importlib.import_module(mod + '.' + attr)\n"
        "    except ImportError:\n"
        "        missing.append(mod + '.' + attr)\n"
        "print('\\n'.join(missing))\n"
        "sys.exit(1 if missing else 0)\n" % (collect_names(),))
    env = dict(os.environ, PYTHONPATH=HARNESS)
    r = subprocess.run([sys.executable, '-c', code], env=env,
                       capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 0, r.stdout + r.stderr


def test_single_skip_exception_class():
    code = (
        "from testrunner import testhelp, testcase, runner\n"
        "import unittest\n"
        "assert testhelp.SkipTestException is testcase.SkipTestException\n"
        "assert testhelp.SkipTestException is runner.SkipTestException\n"
        "assert issubclass(testhelp.SkipTestException, unittest.SkipTest)\n")
    env = dict(os.environ, PYTHONPATH=HARNESS)
    r = subprocess.run([sys.executable, '-c', code], env=env,
                       capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 0, r.stderr


def test_testhelptest_cases_pass():
    """All cases of conary_test/testhelptest.py (the harness spec).

    The file defines 8 collectable tests (test1-4, testStaticMethods1/2,
    testClassMethods1/2); the task text's "12" counted the helper classes.
    """
    env = dict(os.environ, PYTHONPATH=HARNESS + os.pathsep + ROOT)
    r = subprocess.run(
        [sys.executable, '-m', 'pytest', '-q', '-p', 'no:cacheprovider',
         '--rootdir', ROOT, '-c', os.devnull,
         'conary_test/testhelptest.py'],
        env=env, capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 0, r.stdout + r.stderr
    assert re.search(r'^8 passed\b', r.stdout.splitlines()[-1]), r.stdout


def test_suite_module_constructs():
    code = (
        "from testrunner import suite\n"
        "class S(suite.TestSuite):\n"
        "    pass\n"
        "s = S()\n"
        "assert callable(s.setup) and callable(s.main) and callable(s.run)\n")
    env = dict(os.environ, PYTHONPATH=HARNESS)
    r = subprocess.run([sys.executable, '-c', code], env=env,
                       capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 0, r.stderr
