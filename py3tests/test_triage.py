"""devenv/triage.py: traceback signature and failure classification."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'devenv'))
import triage  # noqa: E402


def _tb(frames, exc):
    """Build a --tb=native style traceback from (path, func) frames."""
    lines = ['Traceback (most recent call last):']
    for i, (path, func) in enumerate(frames, 1):
        lines.append('  File "%s", line %d, in %s' % (path, i, func))
        lines.append('    some_code()')
        lines.append('    ~~~~~~~~~^^')
    lines.append(exc)
    return '\n'.join(lines)


TEST = ('/src/conary_test/foo_test.py', 'testIt')
STDLIB = ('/usr/lib64/python3.15/unittest/case.py', 'run')


def _case(frames, exc):
    return _tb([STDLIB, TEST] + frames, exc)


CASES = [
    # (frames below the test frame, final exception line, class)
    ([('/src/conary/lib/util.py', 'rmtree')],
     "AttributeError: module 'posixpath' has no attribute 'walk'",
     'removed stdlib module/API'),
    ([('/src/conary/build/use.py', '_setArch')],
     'AttributeError: No Such Arch aarch64', 'unsupported arch'),
    ([('/src/conary/lib/util.py', 'getId')],
     'TypeError: Strings must be encoded before hashing',
     'bytes/str: hashing'),
    ([('/src/conary/files.py', 'freeze')],
     'TypeError: can only concatenate str (not "bytes") to str',
     'bytes/str: streams/trove'),
    ([('/src/conary/lib/util.py', 'write')],
     "TypeError: a bytes-like object is required, not 'str'",
     'bytes/str: file I/O'),
    ([('/src/conary/repository/transport.py', 'request')],
     "TypeError: a bytes-like object is required, not 'str'",
     'bytes/str: network/xmlrpc'),
    ([('/src/conary/conaryclient/cml.py', 'iterFormat')],
     "TypeError: '>' not supported between instances of 'NoneType' and 'int'",
     'sort/compare'),
    ([('/src/conary/lib/util.py', 'tupleListBsearchInsert')],
     'TypeError: list indices must be integers or slices, not float',
     'integer division'),
    ([('/src/conary/repository/changeset.py', 'getNextFile')],
     "AttributeError: 'DictAsCsf' object has no attribute '__next__'",
     'iterator/dict-view'),
    ([], "NameError: name 'file' is not defined", 'py2 code in tests'),
    ([('/src/testharness/testrunner/testhelp.py', 'run')],
     'RuntimeError: boom', 'harness gap'),
    ([('/src/conary/lib/util.py', 'loadSourceModule')],
     "IsADirectoryError: [Errno 21] Is a directory: '/x'",
     'py3 semantics: other'),
    ([('/src/conary/lib/util.py', 'x')], 'ModuleNotFoundError: No module named q',
     'removed stdlib module/API'),
    ([('/src/conary_test/cvctest/crosstest.py', 'testIt')],
     "KeyError: 'aarch64'", 'arch-specific expectation'),
    ([('/src/conary_test/trovetest.py', 'testIt')],
     "AssertionError: Flavor('is: x86') != Flavor('is: aarch64')",
     'arch-specific expectation'),
    ([('/src/conary/trove.py', 'x')],
     "AssertionError: assert b'foo' == Flavor('is: x86')",
     'bytes/str: streams/trove'),
    ([('/src/conary/lib/util.py', 'x')], 'ValueError: nothing known',
     'unknown'),
]


@pytest.mark.parametrize('frames,exc,expected', CASES)
def test_classify(frames, exc, expected):
    sig = triage.signature(_case(frames, exc))
    assert triage.classify(sig) == expected


def test_signature_picks_innermost_conary_frame():
    text = _case([('/src/conary/trove.py', 'a'),
                  ('/usr/lib64/python3.15/re/__init__.py', 'sub'),
                  ('/src/conary/lib/util.py', 'b')], 'KeyError: 1')
    sig = triage.signature(text)
    assert (sig['exc'], sig['frame'], sig['tag']) == (
        'KeyError', 'conary/lib/util.py:b', 'conary')


def test_signature_falls_back_to_conary_test():
    sig = triage.signature(_tb([STDLIB, TEST], 'AssertionError: x'))
    assert (sig['frame'], sig['tag']) == (
        'conary_test/foo_test.py:testIt', 'conary_test')


def test_signature_uses_last_chained_exception():
    first = _tb([('/src/conary/lib/util.py', 'a')], 'OSError: first')
    text = first + '\n\nDuring handling of the above exception, another ' \
        'exception occurred:\n\n' + _tb([TEST], 'AssertionError: second')
    sig = triage.signature(text)
    assert sig['exc'] == 'AssertionError'
    assert sig['tag'] == 'conary_test'


def test_removed_attribute_in_chained_cause():
    cause = _tb([('/src/conary/build/loadrecipe.py', 'x')],
                "AttributeError: module 'types' has no attribute "
                "'UnboundMethodType'")
    text = cause + '\n\nDuring handling:\n\n' + _tb(
        [TEST], 'AssertionError: assert False')
    assert triage.classify(triage.signature(text)) == \
        'removed stdlib module/API'


@pytest.mark.parametrize('reason,group', [
    ('sqlharness: repository database harness not rebuilt yet', 'sqlharness'),
    ('memcache_server: web server harness not rebuilt yet',
     'server stand-ins (nginx/gunicorn/uwsgi/memcache)'),
    ('M2Crypto is not installed', 'M2Crypto'),
    ('cpio is not installed', 'binary/module not installed'),
    ('this test requires webunit', 'other'),
])
def test_skip_group(reason, group):
    assert triage.skip_group(reason) == group
