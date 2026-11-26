"""requireChroot must not crash the process, and UserGroupIdCache must
always leave a chroot and restore the cwd, even when the lookup raises."""
import os
import subprocess
import sys

import pytest

from conary import files
import conary_test

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.mark.parametrize('text,expected', [
    (b'= cap_chown,cap_sys_chroot+ep', True),
    (b'cap_sys_chroot=ep', True),
    (b'=', False),
    (b'= cap_chown,cap_kill+ep', False),
    (b'', False),
])
def test_hasChrootCap(text, expected):
    assert conary_test._hasChrootCap(text) is expected


def test_requireChroot_subprocess_does_not_crash():
    script = (
        "from conary_test import requireChroot, ChrootError\n"
        "try:\n"
        "    requireChroot()\n"
        "except ChrootError:\n"
        "    print('skip')\n"
        "else:\n"
        "    print('ok')\n")
    env = dict(os.environ)
    env['PYTHONPATH'] = os.pathsep.join(
        [ROOT, os.path.join(ROOT, 'testharness')])
    r = subprocess.run([sys.executable, '-c', script], env=env,
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, (r.returncode, r.stderr[-2000:])
    assert r.stdout.strip() in ('ok', 'skip')


def test_missing_libcap_is_chroot_error(monkeypatch):
    def boom(name):
        raise OSError('libcap.so.2: cannot open shared object file')
    monkeypatch.setattr(conary_test.ctypes.cdll, 'LoadLibrary', boom)
    monkeypatch.setattr(conary_test, 'chrootCapability', None)
    with pytest.raises(conary_test.ChrootError):
        conary_test.requireChroot()
    # failure is cached, not retried as None
    assert conary_test.chrootCapability is False
    with pytest.raises(conary_test.ChrootError):
        conary_test.requireChroot()


def _fdCount():
    return len(os.listdir('/dev/fd'))


@pytest.fixture
def fakeChroot(monkeypatch, tmp_path):
    """Pretend to be root; record chroot calls instead of making them."""
    monkeypatch.chdir(tmp_path)
    calls = []
    monkeypatch.setattr(os, 'getuid', lambda: 0)
    monkeypatch.setattr(os, 'chroot', lambda p: calls.append(p))
    return calls


def _cache(lookup):
    return files.UserGroupIdCache('user', lookup, lambda i: ('x',))


def _seedOk(name):
    return ('root', 'x', 0)


@pytest.mark.parametrize('exc', [TypeError, KeyboardInterrupt])
def test_lookupName_restores_when_lookup_raises(fakeChroot, exc, tmp_path):
    state = {'seeded': False}

    def lookup(name):
        if not state['seeded']:
            state['seeded'] = True
            return ('root', 'x', 0)
        raise exc('boom')
    cache = _cache(lookup)
    cwd = os.getcwd()
    fds = _fdCount()
    with pytest.raises(exc):
        cache.lookupName('/some/root', 'bob')
    assert fakeChroot == ['/some/root', '.']
    assert os.getcwd() == cwd
    assert _fdCount() == fds


def test_lookupName_chroot_refused_does_not_leak(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(os, 'getuid', lambda: 0)
    calls = []

    def refuse(path):
        calls.append(path)
        raise PermissionError('no')
    monkeypatch.setattr(os, 'chroot', refuse)
    cache = _cache(_seedOk)
    cwd = os.getcwd()
    fds = _fdCount()
    with pytest.raises(PermissionError):
        cache.lookupName('/some/root', 'bob')
    # the failed chroot must not be "undone" with chroot('.')
    assert calls == ['/some/root']
    assert os.getcwd() == cwd
    assert _fdCount() == fds


def test_lookupId_restores_when_lookup_raises(fakeChroot):
    def idLookup(i):
        raise TypeError('boom')
    cache = files.UserGroupIdCache('user', _seedOk, idLookup)
    cwd = os.getcwd()
    fds = _fdCount()
    with pytest.raises(TypeError):
        cache.lookupId('/some/root', 5)
    assert fakeChroot == ['/some/root', '.']
    assert os.getcwd() == cwd
    assert _fdCount() == fds


def test_lookupName_success_restores(fakeChroot):
    cache = _cache(_seedOk)
    assert cache.lookupName('/some/root', 'bob') == 0
    assert fakeChroot == ['/some/root', '.']
