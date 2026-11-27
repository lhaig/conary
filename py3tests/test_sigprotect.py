"""sigprotect.call keeps and re-raises the original exception, restores
signal handlers on every path and skips handler setup off the main thread."""

import os
import signal
import threading
import traceback

import pytest

from conary.lib import sigprotect

SIG = signal.SIGUSR2


@pytest.fixture
def recorder():
    """A Python handler for SIG that records and does not raise."""
    seen = []

    def handler(sigNum, frame):
        seen.append(sigNum)

    old = signal.signal(SIG, handler)
    try:
        yield handler, seen
    finally:
        signal.signal(SIG, old)


def test_plain_exception_same_object_and_traceback(recorder):
    handler, _ = recorder
    raised = []

    def _raiser():
        err = ValueError('boom')
        raised.append(err)
        raise err

    @sigprotect.sigprotect(SIG)
    def fn():
        _raiser()

    with pytest.raises(ValueError) as excinfo:
        fn()
    assert excinfo.value is raised[0]
    assert str(excinfo.value) == 'boom'
    names = [f.name for f in traceback.extract_tb(excinfo.value.__traceback__)]
    assert '_raiser' in names
    assert signal.getsignal(SIG) is handler


def test_return_value_passes_through(recorder):
    handler, _ = recorder

    @sigprotect.sigprotect(SIG)
    def fn(a, b=2):
        assert signal.getsignal(SIG) is sigprotect.signalHandler
        return (a, b)

    assert fn(1, b=3) == (1, 3)
    assert signal.getsignal(SIG) is handler


def test_signal_sent_to_self_is_reraised(recorder):
    handler, seen = recorder

    @sigprotect.sigprotect(SIG)
    def fn():
        assert signal.getsignal(SIG) is sigprotect.signalHandler
        os.kill(os.getpid(), SIG)
        return 'not reached'

    rc = fn()
    assert isinstance(rc, sigprotect.SignalException)
    assert rc.sigNum == SIG
    assert seen == [SIG]
    assert signal.getsignal(SIG) is handler


def test_signal_exception_raised_directly_is_reraised(recorder):
    handler, seen = recorder

    @sigprotect.sigprotect(SIG)
    def fn():
        raise sigprotect.SignalException(SIG)

    rc = fn()
    assert isinstance(rc, sigprotect.SignalException)
    assert seen == [SIG]
    assert signal.getsignal(SIG) is handler


@pytest.mark.parametrize('exc', [ValueError('x'), KeyboardInterrupt(),
                                 SystemExit(3)])
def test_handlers_restored_on_exception_paths(recorder, exc):
    handler, _ = recorder

    @sigprotect.sigprotect(SIG)
    def fn():
        assert signal.getsignal(SIG) is sigprotect.signalHandler
        raise exc

    with pytest.raises(type(exc)) as excinfo:
        fn()
    assert excinfo.value is exc
    assert signal.getsignal(SIG) is handler


def test_non_main_thread_bypasses_handler_setup(recorder):
    handler, _ = recorder
    result = {}

    @sigprotect.sigprotect(SIG)
    def fn():
        result['handler'] = signal.getsignal(SIG)
        return 'ok'

    def target():
        try:
            result['rc'] = fn()
        except BaseException as err:
            result['err'] = err

    t = threading.Thread(target=target)
    t.start()
    t.join()
    if 'err' in result:
        raise result['err']
    assert result['rc'] == 'ok'
    assert result['handler'] is handler
    assert result['handler'] is not sigprotect.signalHandler


def test_no_deprecated_threading_apis():
    with open(sigprotect.__file__) as f:
        src = f.read()
    assert 'currentThread' not in src
    assert '_MainThread' not in src
