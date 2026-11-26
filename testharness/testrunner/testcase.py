"""Shared pieces of the harness: SkipTestException, LogFilter,
TestCaseWithWorkDir and safe_repr."""
import difflib
import re
import shutil
import tempfile
import unittest


class SkipTestException(unittest.SkipTest):
    """Raise in setUp or a test body to skip; pytest and unittest both
    report it as a skip.  testhelp and runner re-export this one class."""


def safe_repr(obj, short=False, maxlen=80):
    """repr() that never raises and truncates long results."""
    try:
        result = repr(obj)
    except Exception:
        result = object.__repr__(obj)
    if short and len(result) > maxlen:
        return result[:maxlen] + ' [truncated]...'
    if len(result) > 500:
        return result[:500] + ' [truncated]...'
    return result


class LogFilter:
    """Capture conary log messages instead of printing them.

    Inferred from ~600 call sites (updatetest.py:219, callbackstest.py:73).
    add() starts capturing (and resets records, but keeps ignore() patterns:
    callers usually call ignore() before add()), remove() stops, clear()
    drops what was captured and the ignores.  records holds the formatted messages as
    conary.lib.log writes them ('warning: msg', '+ msg').  compare() checks
    them against a str (one message per line) or a list, after dropping
    messages matching a regex given to ignore().  A str is ONE record (it may
    contain newlines: callbackstest.py:93, deptest.py:772).  Implemented as a logging
    Filter on the 'conary' logger that returns False, so nothing reaches the
    console handler while active and the logger's handlers are untouched.
    """

    def __init__(self):
        self.records = []
        self.ignored = []
        self._active = False

    def _logger(self):
        from conary.lib import log
        return log.logger

    def filter(self, record):
        self.records.append(record.getMessage())
        return False

    def add(self):
        self.records = []
        if not self._active:
            self._logger().addFilter(self)
            self._active = True

    def remove(self):
        if self._active:
            self._logger().removeFilter(self)
            self._active = False

    def clear(self):
        self.records = []
        self.ignored = []
        self.remove()

    def ignore(self, regexp):
        self.ignored.append(re.compile(regexp))

    def _kept(self):
        return [r for r in self.records
                if not any(i.match(r) for i in self.ignored)]

    @staticmethod
    def _lines(expected):
        if isinstance(expected, str):
            return [expected] if expected else []
        return list(expected)

    def compare(self, expected, allowMissing=False):
        """Fail unless the kept records equal expected exactly.  With
        allowMissing (destdirpolicytest.py:390) every expected entry must be
        among the records but extra records are allowed."""
        want = self._lines(expected)
        got = self._kept()
        if allowMissing:
            ok = all(w in got for w in want)
        else:
            ok = got == want
        if not ok:
            diff = '\n'.join(difflib.unified_diff(
                want, got, 'expected', 'logged', lineterm=''))
            raise AssertionError('log records differ:\n' + diff)

    def regexpCompare(self, expected):
        """Like compare() but each expected entry is a regex that must match
        the whole record."""
        want = self._lines(expected)
        got = self._kept()
        ok = len(got) == len(want) and all(
            re.match('(?:%s)\\Z' % w, g) for w, g in zip(want, got))
        if not ok:
            raise AssertionError('log records do not match:\nexpected '
                                 '%r\nlogged   %r' % (want, got))


class TestCaseWithWorkDir(unittest.TestCase):
    """setUp creates self.workDir under mkdtemp(prefix=self.testDirName);
    tearDown removes it (proxytest.py:78, cpiostreamtest.py:26)."""
    testDirName = 'testcase-'

    def setUp(self):
        self.workDir = tempfile.mkdtemp(prefix=self.testDirName)

    def tearDown(self):
        shutil.rmtree(self.workDir, ignore_errors=True)
