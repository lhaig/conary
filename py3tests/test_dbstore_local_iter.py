"""Python 3 iterator, dict and sqlite-connection behaviour of the dbstore,
local database, changeset and file container code."""
import io

import pytest

from conary import dbstore
from conary.dbstore import idtable, sqlerrors, sqllib
from conary.lib import cfg, util
from conary.local import database, sqldb
from conary.repository import changeset, filecontainer, filecontents


@pytest.fixture
def path(tmp_path):
    return str(tmp_path / 'db')


# -- sqlite connection attribute and timeout --------------------------------

def test_connection_accepts_begin_attribute(path):
    db = dbstore.connect(path, driver='sqlite', timeout=200)
    try:
        assert db.dbh._BEGIN == "begin immediate"
        db.dbh._BEGIN = "BEGIN"
        assert db.dbh._BEGIN == "BEGIN"
    finally:
        db.close()


def _two(path, begin):
    first = dbstore.connect(path, driver='sqlite', timeout=100)
    cu = first.cursor()
    cu.execute("CREATE TABLE t (a INTEGER)")
    first.commit()
    if begin:
        first.dbh._BEGIN = begin
    second = dbstore.connect(path, driver='sqlite', timeout=100)
    return first, second


def test_default_implicit_begin_takes_write_lock(path):
    first, second = _two(path, None)
    try:
        first.cursor().execute("INSERT INTO t VALUES (1)")
        with pytest.raises(sqlerrors.DatabaseLocked):
            second.cursor().execute("BEGIN IMMEDIATE")
    finally:
        first.close()
        second.close()


@pytest.mark.parametrize('begin,want', [
    (None, 'begin immediate'),   # driver default
    ('BEGIN', 'BEGIN'),          # what sqldb.Database sets for the local db
])
def test_implicit_begin_uses_connection_attribute(path, begin, want):
    # A write outside a transaction must start one with the connection's own
    # _BEGIN statement, not the class-wide default.
    first, second = _two(path, begin)
    second.close()
    sent = []
    first.dbh.set_trace_callback(sent.append)
    try:
        first.cursor().execute("INSERT INTO t VALUES (1)")
        begins = [s for s in sent if s.upper().startswith('BEGIN')]
        assert begins == [want]
    finally:
        first.dbh.set_trace_callback(None)
        first.close()


def test_sqldb_database_stores_timeout(tmp_path):
    db = sqldb.Database(str(tmp_path / 'local.db'), timeout=12345)
    try:
        assert db.db.timeout == 12345
        assert db.db.dbh._BEGIN == "BEGIN"
    finally:
        db.close()


# -- cursor next() and IdTable lists -----------------------------------------

def test_next_on_cursor(path):
    db = dbstore.connect(path, driver='sqlite')
    try:
        cu = db.cursor()
        cu.execute("SELECT 5")
        assert next(cu)[0] == 5
        with pytest.raises(StopIteration):
            next(cu)
    finally:
        db.close()


def test_idtable_lists(path):
    db = dbstore.connect(path, driver='sqlite')
    try:
        db.loadSchema()
        idtable.createIdTable(db, 'Things', 'thingId', 'thing')
        t = idtable.IdTable(db, 'Things', 'thingId', 'thing')
        a = t.getOrAddId('a')
        b = t.getOrAddId('b')
        assert sorted(t.keys()) == ['a', 'b']
        assert sorted(t.values()) == sorted([a, b])
        assert sorted(t.items()) == sorted([('a', a), ('b', b)])
        assert isinstance(t.keys(), list)
        assert t.has_key('a') and not t.has_key('c')
        assert t['a'] == a
    finally:
        db.close()


# -- generator termination (PEP 479) -----------------------------------------

def test_iterable_queue_ends_cleanly():
    q = util.IterableQueue()
    assert list(q) == []
    q.add(1)
    q.add(2)
    assert list(q) == [1, 2]


def test_peek_iterator_exhausts_cleanly():
    assert list(util.PeekIterator(iter([1, 2, 3]))) == [1, 2, 3]
    assert list(util.PeekIterator(iter([]))) == []
    it = util.PeekIterator(iter([1]))
    assert it.peek() == 1
    assert next(it) == 1
    with pytest.raises(StopIteration):
        it.peek()


def test_job_prescripts_for_jobset_without_scripts():
    uj = database.UpdateJob(None)
    uj._jobPreScriptsByJob = None
    uj._jobPreScripts = []
    assert list(uj.iterJobPreScriptsForJobSet(0)) == []


# -- DictAsCsf and FileContainer walks ---------------------------------------

class _Contents:
    def __init__(self, data):
        self.data = data

    def get(self):
        return io.BytesIO(self.data)


def test_dict_as_csf_walk_and_reset():
    contents = {
        'b': ('0 file', _Contents(b'two'), True),
        'a': ('0 file', _Contents(b'one'), True),
    }
    csf = changeset.DictAsCsf(contents)
    names = []
    while True:
        item = csf.getNextFile()
        if item is None:
            break
        names.append(item[0])
        assert item[2].read() in (b'one', b'two')
    assert names == ['a', 'b']
    assert csf.getNextFile() is None
    csf.reset()
    assert csf.getNextFile()[0] == 'a'


def test_file_container_walk_and_reset(tmp_path):
    p = tmp_path / 'fc'
    fc = filecontainer.FileContainer(util.ExtendedFile(
        str(p), 'w+', buffering=False))
    fc.addFile(b'one', filecontents.FromString(b'1111'), b'0 file')
    fc.addFile(b'two', filecontents.FromString(b'22'), b'0 file')
    fc.close()
    fobj = util.ExtendedFile(str(p), 'r', buffering=False)
    fc = filecontainer.FileContainer(fobj)
    names = []
    while True:
        item = fc.getNextFile()
        if item is None:
            break
        names.append(item[0])
    assert names == [b'one', b'two']
    fc.reset()
    assert fc.getNextFile()[0] == b'one'


# -- ChangeSetFileDict and config items --------------------------------------

def test_changeset_file_dict_items_and_contains():
    d = changeset.ChangeSetFileDict()
    d[(None, b'new')] = 'x'
    d[(b'old', b'new2')] = 'y'
    assert (None, b'new') in d
    assert (b'old', b'new2') in d
    assert (None, b'nope') not in d
    assert sorted(d.items(), key=repr) == sorted(
        [((None, b'new'), 'x'), ((b'old', b'new2'), 'y')], key=repr)
    assert isinstance(d.items(), list)


def test_changeset_file_dict_freeze_does_not_recurse():
    d = changeset.ChangeSetFileDict()
    d[(None, b'new')] = b''
    try:
        d.freeze()
    except RecursionError:
        pytest.fail("ChangeSetFileDict.freeze recursed")
    except (TypeError, AttributeError):
        # bytes/str follow-ups in the stream code are tracked elsewhere
        pass


def test_config_items_list():
    class Cfg(cfg.ConfigFile):
        name = cfg.CfgString
    c = Cfg()
    c.name = 'v'
    items = dict(c.items())
    assert items['name'] == 'v'


# -- CaselessDict ------------------------------------------------------------

def test_caseless_dict():
    d = sqllib.CaselessDict({'Foo': 1, 'Bar': 2})
    assert 'foo' in d and 'FOO' in d and 'baz' not in d
    assert d == {'foo': 1, 'bar': 2}
    assert d != {'foo': 1}
    assert d != {'foo': 1, 'baz': 2}
    assert sorted(d) == ['Bar', 'Foo']
    assert sorted(d.iteritems()) == [('Bar', 2), ('Foo', 1)]
    assert sorted(d.iterkeys()) == ['Bar', 'Foo']
    assert sorted(d.itervalues()) == [1, 2]
    assert not hasattr(d, 'has_key')
