import io
import os

import pytest

from conary import versions
from conary.build import cook

SENTINEL = object()


class PseudoStdin(io.StringIO):
    """stdin without a file descriptor, like pytest's DontReadFromInput."""

    def fileno(self):
        raise io.UnsupportedOperation(
            'redirected stdin is pseudofile, has no fileno()')

    def isatty(self):
        return False


def _ident(st):
    return (st.st_dev, st.st_ino)


@pytest.fixture
def fd0(monkeypatch):
    """Point fd 0 at a pipe and make sys.stdin a pseudofile."""
    saved = os.dup(0)
    r, w = os.pipe()
    os.dup2(r, 0)
    monkeypatch.setattr(cook.sys, 'stdin', PseudoStdin())
    try:
        yield _ident(os.fstat(r))
    finally:
        os.dup2(saved, 0)
        for fd in (saved, r, w):
            os.close(fd)


@pytest.fixture
def stub(monkeypatch):
    seen = {}

    def fake(*args, **kwargs):
        seen['kwargs'] = kwargs
        seen['during'] = _ident(os.fstat(0))
        if seen.get('raise'):
            raise RuntimeError('boom')
        return SENTINEL

    monkeypatch.setattr(cook, '_cookPackageObject', fake)
    return seen


def test_no_log_build(fd0, stub):
    assert cook._cookPackageObjWrap(logBuild=False) is SENTINEL
    assert stub['kwargs']['redirectStdin'] is False
    assert stub['during'] == fd0
    assert _ident(os.fstat(0)) == fd0


@pytest.mark.parametrize('label', [None, versions.CookLabel()])
def test_log_build_redirects_and_restores(fd0, stub, label):
    devnull = _ident(os.stat(os.devnull))
    assert fd0 != devnull
    assert cook._cookPackageObjWrap(logBuild=True,
                                    targetLabel=label) is SENTINEL
    assert stub['kwargs']['redirectStdin'] is True
    assert 'targetLabel' not in stub['kwargs']
    assert stub['during'] == devnull
    assert _ident(os.fstat(0)) == fd0


def test_restored_after_exception(fd0, stub):
    stub['raise'] = True
    with pytest.raises(RuntimeError, match='boom'):
        cook._cookPackageObjWrap(logBuild=True)
    assert stub['during'] == _ident(os.stat(os.devnull))
    assert _ident(os.fstat(0)) == fd0


@pytest.mark.parametrize('withStdin', [False, True])
def test_logger_slave_with_pseudofile_stdin(monkeypatch, withStdin):
    from conary.lib import logger

    monkeypatch.setattr(logger.sys, 'stdin', PseudoStdin())
    saved = [os.dup(fd) for fd in (0, 1, 2)]
    masterFd, slaveFd = os.openpty()
    log = logger.Logger(withStdin=withStdin)
    try:
        log._becomeLogSlave(slaveFd, 0)
        assert log.oldTermios is None
        assert log.logging
        # fd 0 is only saved, and later restored, when stdin is being logged
        assert (log.oldStdin != 0) == withStdin
    finally:
        for fd, old in zip((0, 1, 2), saved):
            os.dup2(old, fd)
            os.close(old)
        for name in ('oldStderr', 'oldStdout'):
            if hasattr(log, name):
                os.close(getattr(log, name))
        if withStdin and hasattr(log, 'oldStdin'):
            os.close(log.oldStdin)
        log.logging = False
        os.close(masterFd)
