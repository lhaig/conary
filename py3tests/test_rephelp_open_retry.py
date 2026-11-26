"""RepositoryHelper.openRepository must not retry a skip from the start."""
import unittest

import pytest

from conary_test import rephelp
from testrunner import testhelp


def _helper(stub, monkeypatch):
    sleeps = []
    monkeypatch.setattr(rephelp.time, 'sleep', sleeps.append)
    h = object.__new__(rephelp.RepositoryHelper)
    h._RepositoryHelper__openRepository = stub
    return h, sleeps


def _raiser(calls, exc, failures=None, result=None):
    def stub(**kw):
        calls.append(kw)
        if failures is None or len(calls) <= failures:
            raise exc
        return result
    return stub


@pytest.mark.parametrize('exc', [
    testhelp.SkipTestException('no sql'),
    unittest.SkipTest('plain skip'),
])
def test_skip_propagates_without_retry(monkeypatch, exc):
    calls = []
    h, sleeps = _helper(_raiser(calls, exc), monkeypatch)
    with pytest.raises(unittest.SkipTest):
        h.openRepository()
    assert len(calls) == 1
    assert sleeps == []


def test_transient_error_is_retried(monkeypatch):
    calls = []
    sentinel = object()
    h, sleeps = _helper(
        _raiser(calls, RuntimeError('boom'), failures=2, result=sentinel),
        monkeypatch)
    assert h.openRepository() is sentinel
    assert len(calls) == 3
    assert sleeps == [0.5, 1.0]


def test_persistent_error_propagates_after_four_tries(monkeypatch):
    calls = []
    h, sleeps = _helper(_raiser(calls, RuntimeError('boom')), monkeypatch)
    with pytest.raises(RuntimeError, match='boom'):
        h.openRepository()
    assert len(calls) == 4
    assert sleeps == [0.5, 1.0, 1.5]
