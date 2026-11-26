"""Small Py3 semantics fixes: integer division in the bsearch helper,
trovetup string parsing, id cache '+name' fallback, logger name check."""

import pytest

from conary import errors, files, trovetup
from conary.lib import logger, util


def _cmp(a, b):
    return (a > b) - (a < b)


@pytest.mark.parametrize('haystack, item, expected', [
    ([], 1, [1]),
    ([1, 3, 5, 7], 4, [1, 3, 4, 5, 7]),
    ([1, 3, 5, 7], 0, [0, 1, 3, 5, 7]),
    ([1, 3, 5, 7], 9, [1, 3, 5, 7, 9]),
    ([1, 3, 5, 7, 9, 11], 8, [1, 3, 5, 7, 8, 9, 11]),
    ([1, 3, 5, 7], 5, [1, 3, 5, 7]),
])
def test_tuple_list_bsearch_insert(haystack, item, expected):
    util.tupleListBsearchInsert(haystack, item, _cmp)
    assert haystack == expected


@pytest.mark.parametrize('text', [
    'foo=/a@b:c/10.000:1-1-1[is: x86]',
    b'foo=/a@b:c/10.000:1-1-1[is: x86]',
])
def test_trovetuple_from_string_str_and_bytes(text):
    tt = trovetup.TroveTuple.fromString(text)
    assert tt.name == 'foo'
    assert tt.version.freeze() == '/a@b:c/10.000:1-1-1'
    assert str(tt.flavor) == 'is: x86'


@pytest.mark.parametrize('text', [
    'foo=/a@b:c/10.000:1-1-1--/a@b:c/20.000:2-1-1',
    b'foo=/a@b:c/10.000:1-1-1--/a@b:c/20.000:2-1-1',
])
def test_jobtuple_from_string_str_and_bytes(text):
    jt = trovetup.JobTuple.fromString(text)
    assert jt[0] == 'foo'
    assert jt[1][0].freeze() == '/a@b:c/10.000:1-1-1'
    assert jt[2][0].freeze() == '/a@b:c/20.000:2-1-1'


@pytest.mark.parametrize('cls', [trovetup.TroveTuple, trovetup.JobTuple])
def test_from_string_non_ascii_is_parse_error(cls):
    with pytest.raises(errors.ParseError, match='ASCII'):
        cls.fromString('foo=café')
    with pytest.raises(errors.ParseError, match='ASCII'):
        cls.fromString('foo=café'.encode('utf-8'))


def _idCache():
    return files.UserGroupIdCache(
        'user', lambda name: (name, 'x', 5, 5), lambda i: ('n%d' % i,))


@pytest.mark.parametrize('name, expected', [
    ('+42', 42),
    ('+notanumber', 0),
    ('+', 0),
    ('root', 0),
    ('someone', 5),
])
def test_lookup_name_plus_ids(name, expected):
    assert _idCache().lookupName('/', name) == expected


def test_lookup_name_plus_bad_id_cached_as_root():
    c = _idCache()
    assert c.lookupName('/', '+bad') == 0
    assert c.nameCache['+bad'] == 0


@pytest.mark.parametrize('key, ok', [
    ('good_key', True),
    ('a-b.c', True),
    ('1bad', False),
    ('bad key', False),
    ('bad<', False),
])
def test_xml_log_record_data_key_check(key, ok):
    w = logger.XmlLogWriter('/dev/null')
    if ok:
        w.addRecordData(key, 'v')
        assert w._getRecordData()[key] == 'v'
    else:
        with pytest.raises(RuntimeError, match='not a legal XML name'):
            w.addRecordData(key, 'v')


@pytest.mark.parametrize('pathId, fileId, expected', [
    (b'p' * 16, b'f' * 20, b'p' * 16 + b'f' * 20),
    ('p' * 16, b'f' * 20, b'p' * 16 + b'f' * 20),
    (b'p' * 16, 'f' * 20, b'p' * 16 + b'f' * 20),
    ('\xe9' * 4, b'f', '\xe9\xe9\xe9\xe9'.encode('utf-8') + b'f'),
])
def test_changeset_make_key_accepts_str_and_bytes(pathId, fileId, expected):
    from conary.repository import changeset
    assert changeset.makeKey(pathId, fileId) == expected
