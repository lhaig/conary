"""Unit tests for the rebuilt testrunner helpers (testharness/testrunner)."""
import logging
import os
import socket
import stat
import sys

import pytest

from testrunner import decorators, runner, testcase, testhelp
from testrunner.testhelp import SkipTestException


class Case(testhelp.TestCase):
    """Instantiable TestCase; unittest needs a real method name."""
    def runTest(self):
        pass


@pytest.fixture
def tc():
    t = Case()
    t.setUp()
    yield t
    t.tearDown()


# ---- context / skip / misc -------------------------------------------

def test_context_appends_and_returns_same_func():
    def f():
        pass
    assert testhelp.context('a')(f) is f
    assert f._contexts == ['a']
    testhelp.context('b', 'c')(f)
    assert f._contexts == ['a', 'b', 'c']


def test_skip_exception_is_unittest_skip():
    import unittest
    assert issubclass(SkipTestException, unittest.SkipTest)
    assert runner.SkipTestException is SkipTestException
    assert testcase.SkipTestException is SkipTestException


def test_get_temp_dir(tmp_path):
    d = testhelp.getTempDir('harness-test-')
    try:
        assert os.path.isdir(d)
        assert os.path.basename(d).startswith('harness-test-')
    finally:
        os.rmdir(d)


@pytest.mark.parametrize('num', [1, 2, 5])
def test_find_ports(num):
    ports = testhelp.findPorts(num)
    assert isinstance(ports, list)
    assert len(ports) == num == len(set(ports))
    for p in ports:  # sockets were released, so the port can be bound
        s = socket.socket()
        try:
            s.bind(('127.0.0.1', p))
        finally:
            s.close()


def test_find_ports_default_is_one():
    assert len(testhelp.findPorts()) == 1


def test_safe_repr():
    assert testcase.safe_repr([1, 2]) == '[1, 2]'

    class Bad:
        def __repr__(self):
            raise ValueError('boom')
    assert 'Bad' in testcase.safe_repr(Bad())
    long = testcase.safe_repr('x' * 10000)
    assert len(long) < 1000


def test_require_binary_runs_when_present():
    @decorators.requireBinary('python3')
    def f(a):
        return a + 1
    assert f(1) == 2


def test_require_binary_skips_when_missing():
    @decorators.requireBinary('no-such-binary-xyzzy')
    def f():
        return 1
    with pytest.raises(SkipTestException):
        f()


def test_require_binary_keeps_name_and_contexts():
    @decorators.requireBinary('python3')
    @testhelp.context('x')
    def f():
        pass
    assert f.__name__ == 'f'
    assert f._contexts == ['x']


# ---- TestCaseWithWorkDir ---------------------------------------------

def test_testcase_with_workdir():
    class T(testcase.TestCaseWithWorkDir):
        testDirName = 'harness-wd-'

        def runTest(self):
            pass
    t = T()
    t.setUp()
    d = t.workDir
    assert os.path.isdir(d)
    assert os.path.basename(d).startswith('harness-wd-')
    t.tearDown()
    assert not os.path.exists(d)


# ---- writeFile ---------------------------------------------------------

def test_write_file_text_bytes_mode(tc, tmp_path):
    p = str(tmp_path / 'a' / 'b' / 'f')
    tc.writeFile(p, 'hello\n')
    assert open(p).read() == 'hello\n'
    tc.writeFile(p, b'\x00\xff')
    assert open(p, 'rb').read() == b'\x00\xff'
    tc.writeFile(p, 'x', mode=0o755)
    assert stat.S_IMODE(os.stat(p).st_mode) == 0o755


# ---- captureOutput / discardOutput -------------------------------------

def test_capture_output_stdout_and_fd(tc):
    def fn(a, b=2):
        print('via print')
        os.write(1, b'via fd\n')
        return a + b
    rc, s = tc.captureOutput(fn, 1, b=5)
    assert rc == 6
    assert isinstance(s, str)
    assert 'via print' in s and 'via fd' in s


def test_capture_output_restores_on_error(tc):
    before = sys.stdout

    def boom():
        print('x')
        raise ValueError('bad')
    with pytest.raises(ValueError):
        tc.captureOutput(boom)
    assert sys.stdout is before
    rc, s = tc.captureOutput(lambda: print('again'))
    assert s == 'again\n'


def test_discard_output(tc, capfd):
    def fn():
        print('hidden')
        os.write(1, b'hidden fd\n')
        return 7
    assert tc.discardOutput(fn) == 7
    assert 'hidden' not in capfd.readouterr().out


# ---- mock / unmock -----------------------------------------------------

class _Base:
    foo = 'A'


class _Child(_Base):
    pass


class _Static:
    @staticmethod
    def f():
        return 1


class _Cls:
    @classmethod
    def f(cls):
        return 1


def test_mock_existing_missing_and_restore(tc):
    class O:
        x = 1
    o = O()
    tc.mock(o, 'x', 2)
    tc.mock(o, 'new', 3)
    assert (o.x, o.new) == (2, 3)
    tc.unmock()
    assert o.x == 1 and not hasattr(o, 'new')


def test_mock_lifo_same_attribute(tc):
    class O:
        x = 1
    tc.mock(O, 'x', 2)
    tc.mock(O, 'x', 3)
    assert O.x == 3
    tc.unmock()
    assert O.x == 1


def test_mock_inherited_attribute_is_deleted_on_restore(tc):
    tc.mock(_Child, 'foo', 'B')
    assert _Child.foo == 'B'
    tc.unmock()
    assert 'foo' not in vars(_Child)
    assert _Child.foo == 'A'


def test_mock_static_and_class_methods(tc):
    tc.mock(_Static, 'f', lambda: 2)
    assert _Static.f() == 2 and _Static().f() == 2
    tc.mock(_Cls, 'f', lambda cls: 3)
    assert _Cls.f() == 3 and _Cls().f() == 3
    tc.unmock()
    assert _Static.f() == 1 and _Cls.f() == 1
    assert isinstance(vars(_Static)['f'], staticmethod)
    assert isinstance(vars(_Cls)['f'], classmethod)


def test_teardown_unmocks():
    class O:
        x = 1
    t = Case()
    t.setUp()
    t.mock(O, 'x', 2)
    t.tearDown()
    assert O.x == 1


# ---- mimicRoot / realRoot ----------------------------------------------

def test_mimic_root(tc, tmp_path):
    real_uid = os.getuid()
    p = str(tmp_path / 'f')
    open(p, 'w').close()
    tc.mimicRoot()
    try:
        assert os.getuid() == 0 and os.geteuid() == 0
        os.chown(p, 5, 6)
        os.lchown(p, 7, 8)
        os.chmod(p, 0o6755)
        assert tc.chownLog == [(p, 5, 6), (p, 7, 8)]
        assert tc.chmodLog == [(p, 0o6755)]
        assert stat.S_IMODE(os.stat(p).st_mode) == 0o6755  # executed
        os.mknod(p + 'dev', stat.S_IFCHR, os.makedev(1, 2))
        assert tc.mknodLog == [(p + 'dev', stat.S_IFCHR, os.makedev(1, 2))]
        assert not os.path.exists(p + 'dev')
    finally:
        tc.realRoot()
    assert os.getuid() == real_uid


def test_real_root_idempotent_and_teardown_restores():
    real_chown = os.chown
    t = Case()
    t.setUp()
    t.realRoot()  # without mimicRoot: harmless
    t.mimicRoot()
    assert os.chown is not real_chown
    t.tearDown()  # test failed before realRoot: tearDown must restore
    assert os.chown is real_chown
    t.realRoot()
    assert os.chown is real_chown


def test_mimic_root_initialises_logs(tc):
    assert tc.chownLog == [] and tc.chmodLog == []


# ---- LogFilter ---------------------------------------------------------

@pytest.fixture
def log():
    from conary.lib import log
    return log


def test_logfilter_records_and_suppresses(tc, log, capfd):
    lf = tc.logFilter
    handlers = list(log.logger.handlers)
    lf.add()
    log.warning('careful %s', 'now')
    log.error('bad')
    lf.remove()
    assert lf.records == ['warning: careful now', 'error: bad']
    assert capfd.readouterr().err == ''
    assert log.logger.handlers == handlers
    assert not log.logger.filters


def test_logfilter_compare_str_list_and_mismatch(tc, log):
    lf = tc.logFilter
    lf.add()
    log.warning('a')
    log.warning('b')
    lf.remove()
    lf.compare(['warning: a', 'warning: b'])
    with pytest.raises(AssertionError):
        lf.compare('warning: a\nwarning: b')  # a str is one record
    with pytest.raises(AssertionError):
        lf.compare('warning: a')
    with pytest.raises(AssertionError):
        lf.compare(['warning: a', 'warning: c'])


def test_logfilter_ignore_clear_and_regexp(tc, log):
    lf = tc.logFilter
    lf.add()
    lf.ignore('warning: noise.*')
    log.warning('noise 1')
    log.warning('real 7')
    lf.remove()
    lf.compare('warning: real 7')
    lf.regexpCompare(['warning: real \\d+'])
    with pytest.raises(AssertionError):
        lf.regexpCompare(['warning: real x'])
    lf.clear()
    assert lf.records == []


def test_logfilter_respects_verbosity(tc, log):
    lf = tc.logFilter
    old = log.getVerbosity()
    try:
        log.setVerbosity(logging.ERROR)
        lf.add()
        log.warning('quiet')
        lf.remove()
        assert lf.records == []
    finally:
        log.setVerbosity(old)


def test_logfilter_standalone_and_teardown_removes(log):
    lf = testcase.LogFilter()
    lf.add()
    log.warning('x')
    lf.compare('warning: x')
    lf.clear()
    assert lf.records == [] and not log.logger.filters

    t = Case()
    t.setUp()
    t.logFilter.add()
    t.tearDown()
    assert not log.logger.filters


def test_logfilter_ignore_before_add(tc, log):
    # call-site order from destdirpolicytest.py:383-384
    lf = tc.logFilter
    lf.ignore('warning: noise.*')
    lf.add()
    log.warning('noise')
    log.warning('real')
    lf.remove()
    lf.compare(['warning: real'])
    lf.clear()
    lf.add()
    log.warning('noise')
    lf.remove()
    lf.compare(['warning: noise'])  # clear() dropped the ignore


def test_logfilter_multiline_single_record(tc, log):
    # callbackstest.py:93, deptest.py:772
    lf = tc.logFilter
    lf.add()
    log.error('a\nb')
    lf.remove()
    lf.compare('error: a\nb')
    lf.compare(['error: a\nb'])
    assert len(lf.records) == 1


def test_logfilter_allow_missing(tc, log):
    lf = tc.logFilter
    lf.add()
    log.warning('a')
    log.warning('extra')
    lf.remove()
    lf.compare(('warning: a',), allowMissing=True)
    with pytest.raises(AssertionError):
        lf.compare(('warning: a',))
    with pytest.raises(AssertionError):
        lf.compare(('warning: zzz',), allowMissing=True)


# ---- logCheck / logCheck2 ----------------------------------------------

def test_log_check(tc, log):
    def fn(a, b=1):
        log.warning('got %s %s', a, b)
        return a + b
    assert tc.logCheck(fn, (1,), 'warning: got 1 1') == 2
    assert tc.logCheck(fn, (1,), ['warning: got 1 4'], {'b': 4}) == 5
    assert tc.logCheck(fn, (1,), ['warning: got 1 \\d'], kwargs={'b': 4},
                       regExp=True) == 5
    with pytest.raises(AssertionError):
        tc.logCheck(fn, (1,), 'warning: other')
    assert not log.logger.filters  # removed even on failure


def test_log_check2(tc, log):
    def fn(a, b=1):
        log.warning('got %s %s', a, b)
        return a + b
    assert tc.logCheck2('warning: got 1 1', fn, 1) == 2
    assert tc.logCheck2(['warning: got 1 4'], fn, 1, b=4) == 5
    assert tc.logCheck2(['warning: got \\d 1'], fn, 1, regExp=True) == 2
    with pytest.raises(AssertionError):
        tc.logCheck2('warning: nope', fn, 1)


def test_log_check2_verbosity_restored(tc, log):
    def fn():
        log.debug('detail')
        return log.getVerbosity()
    old = log.getVerbosity()
    assert tc.logCheck2('+ detail', fn, verbosity=logging.DEBUG) == \
        logging.DEBUG
    assert log.getVerbosity() == old
