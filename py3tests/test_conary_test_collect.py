"""conary_test must collect cleanly under pytest, and testhelp.context tags
must map to pytest markers."""
import os
import re
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Floor for the collected count, set a little under the real number.
COLLECT_FLOOR = 2750

NO_UNKNOWN_MARK = ['-W', 'error::pytest.PytestUnknownMarkWarning']


def _pytest(*args, timeout=300):
    return subprocess.run(
        [sys.executable, '-m', 'pytest', '--collect-only', '-q',
         '-p', 'no:cacheprovider'] + list(args),
        cwd=ROOT, capture_output=True, text=True, timeout=timeout)


def _summary(r):
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-2000:]
    summary = r.stdout.strip().splitlines()[-1]
    assert 'error' not in summary.lower(), summary
    return summary


def _selected(summary):
    m = re.search(r'(\d+)(?:/(\d+))? tests? collected', summary)
    assert m, summary
    return int(m.group(1))


def test_collect_all_conary_test():
    summary = _summary(_pytest('conary_test'))
    assert _selected(summary) >= COLLECT_FLOOR, summary


def test_context_marker_selects_real_tests():
    r = _pytest('conary_test/acltest.py', '-m', 'entitlements',
                *NO_UNKNOWN_MARK)
    summary = _summary(r)
    assert _selected(summary) == 9, summary
    assert 'deselected' in summary, summary


def test_context_marker_with_hyphen():
    r = _pytest('conary_test', '-m', 'trove-filter', *NO_UNKNOWN_MARK)
    summary = _summary(r)
    assert _selected(summary) >= 1, summary
    assert 'deselected' in summary, summary



@pytest.mark.parametrize('context', ['rpm', 'installed_conarydb'])
def test_context_marker_through_init_wrappers(context):
    # conary_test/__init__.py's rpm/installed_conarydb decorators wrap the
    # test and copy _contexts onto the wrapper; markers must survive that.
    r = _pytest('conary_test', '-m', context, *NO_UNKNOWN_MARK)
    summary = _summary(r)
    assert _selected(summary) >= 1, summary
    assert 'deselected' in summary, summary


def test_context_marker_synthetic():
    """A module under conary_test with a tagged test is selectable."""
    path = os.path.join(ROOT, 'conary_test', 'zz_synthetic_ctxtest.py')
    with open(path, 'w') as f:
        f.write(
            "from testrunner import testhelp\n"
            "def test_plain():\n    pass\n"
            "@testhelp.context('zzsynthetic')\n"
            "def test_tagged():\n    pass\n")
    try:
        r = _pytest(path, '-m', 'zzsynthetic', *NO_UNKNOWN_MARK)
        summary = _summary(r)
        assert _selected(summary) == 1, summary
        assert 'test_tagged' in r.stdout
        assert 'test_plain' not in r.stdout
    finally:
        os.unlink(path)
