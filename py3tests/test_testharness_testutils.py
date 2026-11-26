"""Behaviour of the rebuilt testutils modules (except mock)."""
import grp
import os
import pwd
import socket
import threading
import time
import unittest

import pytest

from testrunner.testcase import SkipTestException
from testutils import base_server, os_utils, sock_utils
from testutils.servers import memcache_server


def _listener(host='127.0.0.1'):
    s = socket.socket()
    s.bind((host, 0))
    s.listen(5)
    return s


def _closedPort():
    s = _listener()
    port = s.getsockname()[1]
    s.close()
    return port


def _fdCount():
    fdDir = '/proc/self/fd' if os.path.isdir('/proc/self/fd') else '/dev/fd'
    return len(os.listdir(fdDir))


@pytest.mark.parametrize('host', ['127.0.0.1', 'localhost'])
def test_tryConnect_listening(host):
    s = _listener()
    try:
        assert sock_utils.tryConnect(host, s.getsockname()[1]) is None
    finally:
        s.close()


def test_tryConnect_waits_for_late_listener():
    # Mirrors fork-then-connect: the server binds after tryConnect started.
    port = _closedPort()
    holder = []

    def bindLate():
        time.sleep(0.3)
        s = socket.socket()
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(('127.0.0.1', port))
        s.listen(5)
        holder.append(s)

    t = threading.Thread(target=bindLate)
    t.start()
    try:
        sock_utils.tryConnect('127.0.0.1', port, count=100, interval=0.05)
    finally:
        t.join()
        for s in holder:
            s.close()
    assert holder


def test_tryConnect_closed_port_raises():
    port = _closedPort()
    start = time.monotonic()
    with pytest.raises(ConnectionRefusedError, match=str(port)):
        sock_utils.tryConnect('127.0.0.1', port, count=3, interval=0.05)
    assert time.monotonic() - start < 1


def test_tryConnect_leaks_no_fd():
    s = _listener()
    try:
        before = _fdCount()
        sock_utils.tryConnect('127.0.0.1', s.getsockname()[1])
        assert _fdCount() == before
    finally:
        s.close()
    port = _closedPort()
    before = _fdCount()
    with pytest.raises(ConnectionRefusedError):
        sock_utils.tryConnect('127.0.0.1', port, count=2, interval=0.01)
    assert _fdCount() == before


def test_effective_user_and_group():
    assert isinstance(os_utils.effectiveUser, str)
    assert isinstance(os_utils.effectiveGroup, str)
    try:
        user = pwd.getpwuid(os.geteuid()).pw_name
    except KeyError:
        user = str(os.geteuid())
    try:
        group = grp.getgrgid(os.getegid()).gr_name
    except KeyError:
        group = str(os.getegid())
    assert os_utils.effectiveUser == user
    assert os_utils.effectiveGroup == group
    line = 'cache_effective_user %s\ncache_effective_group %s' % (
        os_utils.effectiveUser, os_utils.effectiveGroup)
    assert user in line and group in line


def test_name_fallback_without_entry():
    assert os_utils._userName(2 ** 31 - 2) == str(2 ** 31 - 2)
    assert os_utils._groupName(2 ** 31 - 2) == str(2 ** 31 - 2)


def test_base_server_as_subclassed():
    class Srv(base_server.BaseServer):
        def __init__(self):  # never calls super, like rephelp's servers
            self.port = 1

    s = Srv()
    assert s.isStarted() is False
    assert s.reset() is None
    with pytest.raises(NotImplementedError):
        s.start()
    with pytest.raises(NotImplementedError):
        s.stop()
    with pytest.raises(NotImplementedError):
        s.getHostPort()


@pytest.mark.parametrize('cls,kwargs', [
    (memcache_server.MemcacheServer, {}),
])
def test_memcache_skips_on_start(cls, kwargs):
    srv = cls(**kwargs)  # must not raise
    # checkForTracebacks (conary_test/lib/repserver.py) opens errorLog.
    with open(srv.errorLog) as f:
        assert 'Traceback' not in f.read()
    assert isinstance(srv.getProxyTo(), str)
    with pytest.raises(SkipTestException, match=cls.name):
        srv.start()
    with pytest.raises(SkipTestException):
        srv.getUrl(ssl=True)
    with pytest.raises(SkipTestException):
        srv.getHostPort()
    # Cleanup paths run after a failed start.
    assert srv.stop() is None
    assert srv.reset() is None
    assert srv.isStarted() is False
    assert issubclass(SkipTestException, unittest.SkipTest)
