"""testutils.mock semantics, each case mirroring a conary_test call site."""
import ast
import copy
import os
import re
import subprocess
import sys
import unittest

import pytest

from conftest import ROOT, HARNESS
from testutils import mock
from testutils.mock import MockInstance, MockObject, MockParams


@pytest.fixture(autouse=True)
def _clean():
    mock.unmockAll()
    yield
    mock.unmockAll()


# -- resolve scans (2.3 widens these to the other testutils modules) --------

def _conary_test_sources():
    for dp, dns, fns in os.walk(os.path.join(ROOT, 'conary_test')):
        dns[:] = [d for d in dns if d != '__pycache__']
        for fn in fns:
            if fn.endswith('.py'):
                yield os.path.join(dp, fn)


def _parse_all():
    for path in _conary_test_sources():
        with open(path, encoding='utf-8') as f:
            yield ast.parse(f.read(), path)


def collect_mock_names():
    """mock.X accesses on aliases bound to testutils.mock, plus names
    imported with `from testutils.mock import`."""
    names = set()
    for tree in _parse_all():
        aliases = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.module == 'testutils':
                    for a in node.names:
                        if a.name == 'mock':
                            aliases.add(a.asname or 'mock')
                elif node.module == 'testutils.mock':
                    names.update(a.name for a in node.names)
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and \
                    isinstance(node.value, ast.Name) and \
                    node.value.id in aliases:
                names.add(node.attr)
    return names


def collect_manager_names():
    """Every <expr>._mock.<attr> in conary_test."""
    names = set()
    for tree in _parse_all():
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and \
                    isinstance(node.value, ast.Attribute) and \
                    node.value.attr == '_mock':
                names.add(node.attr)
    return names


def test_scans_find_the_known_names():
    assert {'MockObject', 'MockInstance', 'MockParams', 'mock', 'mockMethod',
            'mockClass', 'unmockAll'} <= collect_mock_names()
    assert {'set', 'assertCalled', 'setDefaultReturn', 'calls', 'setReturn',
            'enableMethod', 'assertNotCalled', 'appendReturn',
            'raiseErrorOnAccess'} <= collect_manager_names()


def test_mock_names_resolve_in_subprocess():
    code = (
        "import testutils.mock as m\n"
        "assert 'testharness' in m.__file__, m.__file__\n"
        "missing = [n for n in %r if not hasattr(m, n)]\n"
        "assert not missing, missing\n" % (sorted(collect_mock_names()),))
    env = dict(os.environ, PYTHONPATH=HARNESS)
    r = subprocess.run([sys.executable, '-c', code], env=env,
                       capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 0, r.stdout + r.stderr


def test_manager_has_every_used_name():
    for name in collect_manager_names():
        assert hasattr(MockObject()._mock, name), name


# -- MockObject --------------------------------------------------------------

def test_attribute_autocreation_is_cached():
    m = MockObject()
    assert m.foo is m.foo
    assert m._private is m._private
    assert m.foo is not m.bar


def test_dunders_raise_and_default_protocols_hold():
    m = MockObject()
    for name in ('__len__', '__fspath__', '__iter__'):
        assert not hasattr(m, name)
    assert copy.copy(m) is not None
    assert bool(m) is True
    assert m == m and m != MockObject()
    assert not hasattr(type(m), '__get__')


def test_not_a_descriptor_when_set_on_a_class():
    class C:
        pass
    m = MockObject()
    C.attr = m
    assert C().attr is m


def test_kwargs_and_plain_setattr():
    m = MockObject(a=1)
    m.write = MockObject()
    m.x = 5
    assert (m.a, m.x) == (1, 5)
    assert m.write is not m.other


def test_calls_format():
    m = MockObject()
    m('a', k=1, b=2)
    args, keywords = m._mock.calls[-1]
    assert args == ('a',)
    assert keywords == (('b', 2), ('k', 1))
    m._mock.calls.remove((args, keywords))
    assert not m._mock.calls
    m(1, 2)
    m(3, 4)
    assert set(x[0][1] for x in m._mock.calls) == {2, 4}


def test_default_return_is_one_stable_object():
    m = MockObject()
    first = m(1)
    assert m(2, x=3) is first
    assert m() is first
    first.sendmail('x')
    first.sendmail._mock.assertCalled('x')


def test_return_precedence():
    m = MockObject()
    m._mock.setDefaultReturn('default')
    m._mock.setReturn('set', 1)
    m._mock.appendReturn('q1', 1)
    m._mock.appendReturn('q2', 1)
    assert [m(1), m(1), m(1), m(1)] == ['q1', 'q2', 'set', 'set']
    assert m(2) == 'default'


def test_append_return_matches_keywords():
    m = MockObject()
    m._mock.appendReturn('r', 53, False, headers=[('a', 'b')])
    assert m(53, False, headers=[('a', 'b')]) == 'r'
    # queue consumed: falls through to the stable default child
    assert isinstance(m(53, False, headers=[('a', 'b')]), MockObject)


def test_set_return_replaces_same_args():
    m = MockObject()
    m._mock.setReturn('a', 1)
    m._mock.setReturn('b', 1)
    assert m(1) == 'b'


def test_set_sets_real_attributes():
    m = MockObject()
    m._mock.set(a=1, b=2)
    assert (m.a, m.b) == (1, 2)


def test_assert_called_consumes_the_call():
    m = MockObject()
    m(1, k=2)
    m._mock.assertCalled(1, k=2)
    m._mock.assertNotCalled()
    with pytest.raises(AssertionError, match='not found'):
        m._mock.assertCalled(1, k=2)


def test_assert_called_failure_lists_calls():
    m = MockObject()
    m('other')
    with pytest.raises(AssertionError, match='other'):
        m._mock.assertCalled('wanted')


def test_assert_not_called_fails_when_called():
    m = MockObject()
    m()
    with pytest.raises(AssertionError):
        m._mock.assertNotCalled()


class _Boom(Exception):
    pass


@pytest.mark.parametrize('err', [_Boom, _Boom('x')])
def test_raise_error_on_access(err):
    parent = MockObject()
    parent.lookup._mock.setReturn('AA', '1.2.3.4')
    parent.lookup._mock.raiseErrorOnAccess(err)
    with pytest.raises(_Boom):
        parent.lookup('1.2.3.4')
    # the geoip shape: fetched and called inside try/except
    try:
        parent.lookup('x')
    except _Boom:
        pass
    else:
        raise AssertionError('no error')


# -- MockInstance ------------------------------------------------------------

class ModelFile:
    KIND = 'model'

    def __init__(self):
        raise AssertionError('__init__ must not run')

    def fullName(self):
        return self.fileFullName

    def exists(self):
        return self.fullName() == 'present'

    def read(self):
        self.mtime = 42
        return self.model

    def closeSnapshot(self):
        raise AssertionError('must be mocked')

    @property
    def prop(self):
        return 'real'


def test_mock_instance_enable_method():
    mi = MockInstance(ModelFile)
    assert isinstance(mi, ModelFile)
    mi._mock.set(fileFullName='present', model='M')
    mi._mock.enableMethod('read')
    mi._mock.enableMethod('exists')
    mi._mock.enableMethod('fullName')
    assert mi.exists() is True
    assert mi.read() == 'M'
    assert mi.mtime == 42
    mi.closeSnapshot('a')
    mi.closeSnapshot._mock.assertCalled('a')
    mi.closeSnapshot._mock.assertNotCalled()


def test_mock_instance_disabled_method_not_run_and_stable():
    mi = MockInstance(ModelFile)
    assert mi.read is mi.read
    assert mi.exists() is mi.exists()


def test_mock_instance_class_data_passes_through_properties_mocked():
    mi = MockInstance(ModelFile)
    assert mi.KIND == 'model'
    assert isinstance(mi.prop, MockObject)
    mi._mock.enableMethod('prop')
    assert mi.prop == 'real'


def test_mock_instance_kwargs():
    mi = MockInstance(ModelFile, a=1)
    assert mi.a == 1


# -- MockParams / mockClass --------------------------------------------------

class Jar:
    def __init__(self, path):
        raise AssertionError('__init__ must not run')

    def contents(self):
        return 'real'


def test_mock_params_stores_args():
    p = MockParams(1, x=2)
    assert p.args == (1,) and p.kw == {'x': 2}


def test_mock_class_is_real_class_and_isinstance_works():
    cls = mock.mockClass(Jar, mock_set=MockParams(depsContents='deps'))
    assert isinstance(cls, type) and issubclass(cls, Jar)
    obj = cls('some/path', extra=1)
    assert isinstance(obj, cls) and isinstance(obj, Jar)
    assert obj.depsContents == 'deps'
    assert isinstance(obj.contents(), MockObject)


def test_mock_class_without_args_and_mock_enable():
    obj = mock.mockClass(Jar, mock_enable=['contents'])()
    assert obj.contents() == 'real'


def test_mock_class_patched_onto_module():
    mod = type(sys)('fakemagic')
    mod.jar = Jar
    mock.mock(mod, 'jar', mock.mockClass(Jar))
    assert isinstance(mod.jar('p'), mod.jar)
    mock.unmockAll()
    assert mod.jar is Jar


# -- mock / mockMethod / unmockAll -------------------------------------------

class Base:
    inherited = 'orig'

    def method(self, x):
        return x


class Child(Base):
    pass


def test_mock_default_replacement_and_return_value():
    obj = Base()
    installed = mock.mock(obj, 'method')
    assert isinstance(installed, MockObject)
    assert obj.method is installed
    obj.method(1)
    installed._mock.assertCalled(1)
    mock.unmockAll()
    assert obj.method(7) == 7


def test_mock_explicit_replacement():
    sentinel = lambda: 'x'  # noqa: E731
    assert mock.mock(Base, 'inherited', sentinel) is sentinel
    assert Base.inherited is sentinel


def test_unmock_all_deletes_inherited_attribute_and_is_lifo():
    mock.mock(Child, 'inherited', 'one')
    mock.mock(Child, 'inherited', 'two')
    assert Child.inherited == 'two'
    mock.unmockAll()
    assert 'inherited' not in Child.__dict__
    assert Child.inherited == 'orig'


def test_mock_keeps_staticmethod():
    class S:
        @staticmethod
        def f(x):
            return x
    mock.mock(S, 'f', lambda x: x + 1)
    assert S().f(1) == 2
    mock.unmockAll()
    assert S().f(1) == 1


def test_mock_method_records_args_without_self():
    obj = Base()
    m = mock.mockMethod(obj.method, 'ret')
    assert obj.method('a', 'b') == 'ret'
    assert m._mock.calls[0][0] == ('a', 'b')
    mock.unmockAll()
    assert obj.method(3) == 3


# -- TestCase wiring ---------------------------------------------------------

def test_testcase_teardown_restores_mock_mock_patches():
    from testrunner import testhelp

    class Holder:
        value = 'orig'

    class T(testhelp.TestCase):
        def testIt(self):
            mock.mock(Holder, 'value', 'patched')
            self.mock(Holder, 'value', 'patched2')
            assert Holder.value == 'patched2'

    result = unittest.TestResult()
    T('testIt').run(result)
    assert result.wasSuccessful(), result.errors + result.failures
    assert Holder.value == 'orig'


def test_testhelptest_still_passes():
    env = dict(os.environ, PYTHONPATH=HARNESS + os.pathsep + ROOT)
    r = subprocess.run(
        [sys.executable, '-m', 'pytest', '-q', '-p', 'no:cacheprovider',
         '--rootdir', ROOT, '-c', os.devnull,
         'conary_test/testhelptest.py'],
        env=env, capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 0, r.stdout + r.stderr
    assert re.search(r'^8 passed\b', r.stdout.splitlines()[-1]), r.stdout
