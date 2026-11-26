"""Repository database harness: not rebuilt yet.

Follow-up for the 2.7 baseline: a SQLite-only harness would unlock the
repository-backed and dbstore tests that this skip currently hides.
"""
from testrunner.testcase import SkipTestException


def start(*args, **kwargs):
    raise SkipTestException(
        'sqlharness: repository database harness not rebuilt yet '
        '(PostgreSQL/server tests are out of scope until a later phase)')
