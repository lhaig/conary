"""Helpers changed on the repository commit path (task 3.16)."""
import pytest

from conary import dbstore, versions
from conary.dbstore import idtable
from conary.lib import util


@pytest.fixture
def db(tmp_path):
    d = dbstore.connect(str(tmp_path / 'h.sqlite'), driver='sqlite')
    yield d
    d.close()


def test_sqlite_encoded_str_matches_text(db):
    # netserver binds cu.encode(troveName); on sqlite that must stay str so
    # it compares equal to the TEXT column (a bytes BLOB never matches)
    cu = db.cursor()
    cu.execute("CREATE TABLE t (v TEXT)")
    cu.execute("INSERT INTO t VALUES ('abc')")
    assert cu.encode('abc') == 'abc'
    cu.execute("SELECT count(*) FROM t WHERE v = ?", (cu.encode('abc'),))
    assert cu.fetchall() == [(1,)]


@pytest.mark.parametrize('value, expected', [
    (b'abc', 'abc'),
    ('abc', 'abc'),
    (None, None),
])
def test_sqlite_decode(db, value, expected):
    assert db.cursor().decode(value) == expected


def test_idtable_contains(db):
    cu = db.cursor()
    cu.execute("CREATE TABLE Labels (labelId INTEGER PRIMARY KEY, "
               "label TEXT)")
    t = idtable.IdTable(db, 'Labels', 'labelId', 'label')
    t.addId('a@b:c')
    assert 'a@b:c' in t
    assert 'x@y:z' not in t


def test_saved_exception_rethrows_multi_arg_instance():
    try:
        b'\xff'.decode('utf-8')
    except UnicodeDecodeError:
        saved = util.SavedException()
    with pytest.raises(UnicodeDecodeError) as info:
        saved.throw()
    assert info.value is saved.value


def test_saved_exception_from_type_and_message():
    saved = util.SavedException((ValueError, 'msg', None))
    with pytest.raises(ValueError, match='msg'):
        saved.throw()


@pytest.mark.parametrize('func', [versions.ThawVersion,
                                  versions.VersionFromString])
def test_new_version_from_bytes(func):
    assert isinstance(func(b'@NEW@'), versions.NewVersion)
    assert isinstance(func('@NEW@'), versions.NewVersion)
