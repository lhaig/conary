"""Test decorators."""
import functools
import shutil

from testrunner.testcase import SkipTestException


def requireBinary(binary):
    """Skip the test (at call time) when `binary` is not on PATH."""
    def deco(func):
        @functools.wraps(func)
        def wrapper(*args, **kw):
            if shutil.which(binary) is None:
                raise SkipTestException('%s is not installed' % binary)
            return func(*args, **kw)
        wrapper._contexts = getattr(func, '_contexts', [])
        return wrapper
    return deco
