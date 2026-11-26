"""TestCase base class and helpers used by conary_test.

Helper semantics were inferred from the call sites in conary_test and from
conary_test/testhelptest.py.  assertContent is deliberately absent: it comes
from webunit's WebTestCase (webtest.py), and webtest skips without webunit.
"""
import io
import os
import socket
import sys
import tempfile
import unittest

from testrunner.testcase import (  # noqa: F401  (re-exports)
    LogFilter, SkipTestException, TestCaseWithWorkDir, safe_repr)
from testutils import mock as testutils_mock


def context(*names):
    """Tag a test function with contexts (func._contexts, read by
    conary_test/__init__.py).  Mutates and returns the same function."""
    def deco(func):
        if not hasattr(func, '_contexts'):
            func._contexts = []
        func._contexts.extend(names)
        return func
    return deco


def getTempDir(prefix):
    """Fresh temporary directory (rephelp.py:196)."""
    return tempfile.mkdtemp(prefix=prefix)


def findPorts(num=1):
    """Return a list of `num` distinct free TCP ports on 127.0.0.1.  All
    sockets are held until the last one is bound so ports differ."""
    socks = []
    try:
        for _ in range(num):
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            socks.append(s)
            s.bind(('127.0.0.1', 0))
        return [s.getsockname()[1] for s in socks]
    finally:
        for s in socks:
            s.close()


class TestCase(unittest.TestCase):
    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self.logFilter = LogFilter()
        self._undo = []     # LIFO stack of restore callables
        self._rootUndo = []
        self.chownLog = []
        self.chmodLog = []
        self.mknodLog = []

    def assertRaises(self, excClass, *args, **kw):
        """unittest's assertRaises, except that the callable form returns
        the exception instance (callers inspect args and attributes).  The
        context-manager form, with its msg= option, is unchanged."""
        if not args:
            return super().assertRaises(excClass, **kw)
        func, args = args[0], args[1:]
        try:
            func(*args, **kw)
        except excClass as e:
            return e
        if isinstance(excClass, tuple):
            name = ', '.join(c.__name__ for c in excClass)
        else:
            name = excClass.__name__
        self.fail('%s not raised' % name)

    def tearDown(self):
        self.logFilter.remove()
        self.unmock()
        # Also undo testutils.mock.mock() patches: a separate stack, and some
        # tests never call unmockAll (updatecmdtest) or only on success
        # (rpmtest).
        testutils_mock.unmockAll()
        self.realRoot()

    # -- mocking --------------------------------------------------------

    def mock(self, obj, name, value):
        """Replace obj.name with value until unmock()/tearDown, restoring in
        LIFO order.  The raw __dict__ entry is saved, so an attribute that
        was only inherited (or missing) is deleted again rather than pinned
        on obj.  A staticmethod/classmethod stays one (testhelptest.py)."""
        self._undo.append(testutils_mock.patch(obj, name, value))

    def unmock(self):
        """Undo every mock() in reverse order."""
        while self._undo:
            testutils_mock.restore(self._undo.pop())

    # -- output capture -------------------------------------------------

    def captureOutput(self, fn, *args, **kw):
        """Call fn(*args, **kw); return (result, stdout text).  Captures fd 1
        (C code, subprocesses) and sys.stdout (print under pytest, where
        sys.stdout is not fd 1).  Seen as `rc, s = self.captureOutput(...)`
        (rephelp.py:778).

        _returnException=True returns the exception fn raised as the result
        instead of raising it (openpgptest.py, buildtest/sourcetest.py);
        logLevel=N sets the conary log verbosity for the call.
        _printOnError=True (rephelp.cookObject, derivedtest.py:115) writes
        the captured text to the real stdout when fn raises, before the
        exception propagates; with _returnException=True the error is a
        value, not a failure, so nothing is echoed.
        _removeBokenPipeErrors=True (tagtest.py:460, upstream's spelling)
        drops captured lines that report EPIPE ('Broken pipe' /
        '[Errno 32]'); every other line is kept unchanged.
        All four are consumed here and not passed to fn."""
        from conary.lib import log
        returnException = kw.pop('_returnException', False)
        printOnError = kw.pop('_printOnError', False)
        removeBrokenPipe = kw.pop('_removeBokenPipeErrors', False)
        logLevel = kw.pop('logLevel', None)
        pending = None
        oldLevel = log.getVerbosity()
        sys.stdout.flush()
        saved_stdout = sys.stdout
        saved_fd = os.dup(1)
        with tempfile.TemporaryFile() as tmp:
            os.dup2(tmp.fileno(), 1)
            sys.stdout = io.TextIOWrapper(
                io.FileIO(os.dup(1), 'w'), encoding='utf-8',
                errors='replace', write_through=True)
            try:
                try:
                    # set inside the try so the finally always restores it
                    if logLevel is not None:
                        log.setVerbosity(logLevel)
                    result = fn(*args, **kw)
                except Exception as err:
                    if not returnException:
                        pending = err
                    else:
                        result = err
            finally:
                log.setVerbosity(oldLevel)
                try:
                    sys.stdout.flush()
                    sys.stdout.close()
                finally:
                    sys.stdout = saved_stdout
                    os.dup2(saved_fd, 1)
                    os.close(saved_fd)
            tmp.seek(0)
            text = tmp.read().decode('utf-8', 'replace')
        if removeBrokenPipe:
            text = ''.join(
                line for line in text.splitlines(True)
                if 'Broken pipe' not in line and '[Errno 32]' not in line)
        if pending is not None:
            if printOnError:
                saved_stdout.write(text)
                saved_stdout.flush()
            raise pending
        return result, text

    def discardOutput(self, fn, *args, **kw):
        """captureOutput, returning only fn's result."""
        return self.captureOutput(fn, *args, **kw)[0]

    # -- files ----------------------------------------------------------

    def writeFile(self, path, contents, mode=None):
        """Write str (text) or bytes to path, creating parent directories;
        optionally chmod (verifytest.py:37, updatetest.py:320)."""
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        if isinstance(contents, str):
            with open(path, 'w') as f:
                f.write(contents)
        else:
            with open(path, 'wb') as f:
                f.write(contents)
        if mode is not None:
            os.chmod(path, mode)

    # FOLLOW-UP: assertContent is not provided.  It comes from webunit's
    # WebTestCase (webtest.py:22), which webtest skips without; revisit when
    # webtest is enabled.

    # -- log checking ---------------------------------------------------

    def logCheck(self, fn, args, logList, kwargs=None, regExp=False):
        """Call fn(*args, **kwargs) with log capture and compare the log to
        logList (str or list; regexes if regExp).  Returns fn's result
        (updatetest.py:1735, sourcetest.py:405, lookasidetest.py:172)."""
        self.logFilter.add()
        try:
            result = fn(*args, **(kwargs or {}))
        finally:
            self.logFilter.remove()
        if regExp:
            self.logFilter.regexpCompare(logList)
        else:
            self.logFilter.compare(logList)
        return result

    def logCheck2(self, logList, fn, *args, **kw):
        """logCheck with the call spelled naturally; verbosity= (log level
        set for the call) and regExp= are consumed, the rest goes to fn
        (shadowtest.py:673, sourcetest.py:978, clonetest.py:670)."""
        from conary.lib import log
        verbosity = kw.pop('verbosity', None)
        regExp = kw.pop('regExp', False)
        old = log.getVerbosity()
        if verbosity is not None:
            log.setVerbosity(verbosity)
        try:
            return self.logCheck(fn, args, logList, kw, regExp=regExp)
        finally:
            log.setVerbosity(old)

    # -- fake root ------------------------------------------------------

    def mimicRoot(self):
        """Pretend to be root (filestest.py:270-315): getuid/geteuid return
        0; chown/lchown/mknod are logged to chownLog/mknodLog and not run;
        chmod is logged to chmodLog and still run."""
        if self._rootUndo:
            return
        self.chownLog = []
        self.chmodLog = []
        self.mknodLog = []
        real_chmod = os.chmod

        def chmod(path, mode, *a, **kw):
            self.chmodLog.append((path, mode))
            return real_chmod(path, mode, *a, **kw)

        patches = {
            'getuid': lambda: 0,
            'geteuid': lambda: 0,
            'chown': lambda path, uid, gid, *a, **kw:
                self.chownLog.append((path, uid, gid)),
            'lchown': lambda path, uid, gid:
                self.chownLog.append((path, uid, gid)),
            'mknod': lambda path, mode=0o600, device=0, *a, **kw:
                self.mknodLog.append((path, mode, device)),
            'chmod': chmod,
        }
        for name, value in patches.items():
            self._rootUndo.append((name, getattr(os, name)))
            setattr(os, name, value)

    def realRoot(self):
        """Undo mimicRoot(); harmless if not mimicking."""
        while self._rootUndo:
            name, original = self._rootUndo.pop()
            setattr(os, name, original)
__all__ = ["LogFilter", "SkipTestException", "TestCaseWithWorkDir", "safe_repr", "TestCase", "context", "findPorts", "getTempDir"]
