"""A forked child (cook.cookCommand's) must not tear down the parent's harness."""
import atexit
import os
import sys
import urllib.request

import pytest

from testrunner import testhelp
from testutils import sqlharness
from testutils.servers import wsgi_server


def _runForked(childFn):
    """Fork, run childFn in the child, return the wait status."""
    pid = os.fork()
    if pid == 0:
        code = 0
        try:
            childFn()
        except BaseException:
            code = 99
        finally:
            os._exit(code)
    _, status = os.waitpid(pid, 0)
    return os.waitstatus_to_exitcode(status)


@pytest.fixture
def harness():
    old = sqlharness._harness
    sqlharness._harness = None
    h = sqlharness.start()
    yield h
    h.cleanup()
    sqlharness._harness = old


def _assertDbUsable(h):
    db = h.dbs['x']
    assert os.path.isdir(h.dir)
    assert os.path.exists(db.path)
    conn = db.connect()
    try:
        assert conn.cursor().execute('select 1').fetchall()[0][0] == 1
    finally:
        conn.close()


def _childAtexit():
    sqlharness._cleanupAtExit()
    wsgi_server._killAll()
    atexit._run_exitfuncs()


@pytest.fixture
def db(harness):
    harness.getDB('x').reset()
    return harness


def test_child_cleanup_keeps_parent_sqlite_harness(db):
    assert _runForked(_childAtexit) == 0
    _assertDbUsable(db)


def test_child_sys_exit_keeps_parent_sqlite_harness(db):
    # A child leaving through sys.exit runs the same registered cleanups.
    def child():
        try:
            sys.exit(0)
        except SystemExit:
            sqlharness._cleanupAtExit()
    assert _runForked(child) == 0
    _assertDbUsable(db)


def test_cleanup_runs_in_creating_pid(db):
    d = db.dir
    sqlharness._cleanupAtExit()
    assert not os.path.exists(d)


@pytest.fixture
def server(tmp_path, monkeypatch):
    (tmp_path / 'forkok_app.py').write_text(
        "def application(environ, start_response):\n"
        "    start_response('200 OK', [('Content-Type', 'text/plain')])\n"
        "    return [b'ok']\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setenv('PYTHONPATH', str(tmp_path))
    srv = wsgi_server.StdlibWsgiServer(
        str(tmp_path / 'srv'), application='forkok_app')
    srv.start()
    try:
        yield srv
    finally:
        srv.stop()


def _fetch(srv):
    with urllib.request.urlopen(srv.getUrl(), timeout=10) as r:
        return r.read()


def test_child_does_not_stop_parent_wsgi_server(server):
    def child():
        wsgi_server._killAll()
        server.stop()
    assert _runForked(child) == 0
    assert server.isStarted()
    assert _fetch(server) == b'ok'


def test_wsgi_cleanup_runs_in_creating_pid(server):
    proc = server.process
    wsgi_server._killAll()
    assert proc.poll() is not None
    assert not server.isStarted()


def test_serverCache_cleanup_is_pid_guarded(tmp_path):
    from conary_test import rephelp
    cache = rephelp.ServerCache()
    cache._topDir = str(tmp_path / 'top')
    os.mkdir(cache._topDir)
    try:
        assert _runForked(cache.cleanup) == 0
        assert os.path.isdir(cache._topDir)
    finally:
        atexit.unregister(cache.cleanup)
    cache.cleanup()
    assert not os.path.exists(str(tmp_path / 'top'))


def test_child_leaving_test_method_exits_without_teardown(tmp_path):
    import unittest
    sentinel = str(tmp_path / 'sentinel')
    parentPid = os.getpid()

    class Case(testhelp.TestCase):
        def tearDown(self):
            if os.getpid() != parentPid:
                with open(sentinel, 'w') as f:
                    f.write('tearDown ran in child')
            super().tearDown()

        def testFork(self):
            pid = os.fork()
            if pid == 0:
                raise SystemExit(3)
            _, status = os.waitpid(pid, 0)
            self.status = os.waitstatus_to_exitcode(status)

    case = Case('testFork')
    result = unittest.TestResult()
    case.run(result)
    assert result.wasSuccessful(), result.errors
    assert case.status == 3
    assert not os.path.exists(sentinel)


@pytest.mark.parametrize('exc,expected', [
    (SystemExit(3), 3), (SystemExit(None), 1), (SystemExit('msg'), 1),
    (ValueError('x'), 1)])
def test_child_exit_codes(exc, expected, tmp_path):
    import unittest

    class Case(testhelp.TestCase):
        def testFork(self):
            pid = os.fork()
            if pid == 0:
                raise exc
            _, status = os.waitpid(pid, 0)
            self.status = os.waitstatus_to_exitcode(status)

    case = Case('testFork')
    result = unittest.TestResult()
    case.run(result)
    assert result.wasSuccessful(), result.errors
    assert case.status == expected
