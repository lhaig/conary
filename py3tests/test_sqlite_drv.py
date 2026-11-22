"""Tests for the dbstore sqlite driver on top of the stdlib sqlite3 module."""
import pytest

from conary import dbstore
from conary.dbstore import sqlerrors


@pytest.fixture
def path(tmp_path):
    return str(tmp_path / 'db')


@pytest.fixture
def db(path):
    d = dbstore.connect(path, driver='sqlite', timeout=200)
    yield d
    d.close()


def _open(path):
    return dbstore.connect(path, driver='sqlite', timeout=200)


def test_positional_and_named_binds(db):
    cu = db.cursor()
    cu.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, name TEXT)")
    cu.execute("INSERT INTO t (id, name) VALUES (?, ?)", 1, "one")
    cu.execute("INSERT INTO t (id, name) VALUES (?, ?)", (2, "two"))
    cu.execute("INSERT INTO t (id, name) VALUES (:id, :name)",
               id=3, name="three")
    cu.execute("INSERT INTO t (id, name) VALUES (:id, :name)",
               {'id': 4, 'name': "four"})
    cu.executemany("INSERT INTO t (id, name) VALUES (?, ?)",
                   [(5, "five"), (6, "six")])
    cu.execute("SELECT name FROM t WHERE id = ?", 3)
    assert cu.fetchone()[0] == "three"
    cu.execute("SELECT name FROM t WHERE id = :id", id=6)
    assert cu.fetchone()[0] == "six"
    cu.execute("SELECT id, name FROM t ORDER BY id")
    assert [tuple(r) for r in cu.fetchall()] == [
        (1, "one"), (2, "two"), (3, "three"), (4, "four"), (5, "five"),
        (6, "six")]
    db.commit()


def test_blob_roundtrip(db):
    cu = db.cursor()
    cu.execute("CREATE TABLE b (id INTEGER, data BLOB)")
    raw = b'\xff\x00\x80'
    cu.execute("INSERT INTO b VALUES (?, ?)", 1, cu.binary(raw))
    cu.execute("SELECT data, typeof(data) FROM b")
    row = cu.fetchone()
    assert row[0] == raw and isinstance(row[0], bytes)
    assert row[1] == 'blob'
    assert cu.frombinary(row[0]) == raw
    assert cu.binary(None) is None
    assert cu.binary(bytearray(raw)) == raw
    with pytest.raises(TypeError):
        cu.binary("text")
    # bytes bind as BLOB and can be matched by equality
    cu.execute("SELECT id FROM b WHERE data = ?", cu.binary(raw))
    assert cu.fetchone()[0] == 1


def test_binary_column_keeps_blob(db):
    cu = db.cursor()
    cu.execute("CREATE TABLE b (h %s)" % db.keywords['BINARY20'])
    raw = bytes(range(20))
    cu.execute("INSERT INTO b VALUES (?)", cu.binary(raw))
    cu.execute("SELECT h FROM b")
    assert cu.fetchone()[0] == raw


def test_text_roundtrip(db):
    cu = db.cursor()
    cu.execute("CREATE TABLE s (v TEXT)")
    cu.execute("INSERT INTO s VALUES (?)", "café")
    cu.execute("SELECT v, typeof(v) FROM s")
    row = cu.fetchone()
    assert row[0] == "café" and isinstance(row[0], str)
    assert row[1] == 'text'
    cu.execute("SELECT count(*) FROM s WHERE v = ?", "café")
    assert cu.fetchone()[0] == 1


def test_commit_persists_and_rollback_discards(path):
    d = _open(path)
    cu = d.cursor()
    cu.execute("CREATE TABLE t (id INTEGER)")
    cu.execute("INSERT INTO t VALUES (1)")
    d.commit()
    cu.execute("INSERT INTO t VALUES (2)")
    d.rollback()
    cu.execute("SELECT id FROM t")
    assert [r[0] for r in cu.fetchall()] == [1]
    cu.execute("INSERT INTO t VALUES (3)")
    d.commit()
    d.close()

    d = _open(path)
    try:
        cu = d.cursor()
        cu.execute("SELECT id FROM t ORDER BY id")
        assert [r[0] for r in cu.fetchall()] == [1, 3]
    finally:
        d.close()


def test_ddl_is_transactional(db):
    cu = db.cursor()
    cu.execute("CREATE TABLE t (id INTEGER)")
    db.commit()
    cu.execute("CREATE TABLE u (id INTEGER)")
    db.rollback()
    db.loadSchema()
    assert 't' in db.tables and 'u' not in db.tables


def test_transaction_state(db):
    assert not db.inTransaction()
    db.transaction()
    assert db.inTransaction()
    db.transaction()    # idempotent
    assert db.inTransaction()
    db.rollback()
    assert not db.inTransaction()
    cu = db.cursor()
    cu.execute("CREATE TABLE t (id INTEGER)")
    assert db.inTransaction()
    db.commit()
    assert not db.inTransaction()
    cu.execute("SELECT * FROM t")
    assert not db.inTransaction()
    cu.execute("INSERT INTO t VALUES (?)", 1, start_transaction=False)
    assert not db.inTransaction()


def test_locked_database(path):
    a = _open(path)
    b = _open(path)
    try:
        a.transaction()
        with pytest.raises(sqlerrors.DatabaseLocked):
            b.transaction()
        a.rollback()
        b.transaction()
        assert b.inTransaction()
        b.rollback()
    finally:
        a.close()
        b.close()


def test_unique_violation(db):
    cu = db.cursor()
    cu.execute("CREATE TABLE u (id INTEGER PRIMARY KEY, n TEXT UNIQUE)")
    cu.execute("INSERT INTO u VALUES (1, 'a')")
    with pytest.raises(sqlerrors.ColumnNotUnique):
        cu.execute("INSERT INTO u VALUES (2, 'a')")
    with pytest.raises(sqlerrors.ColumnNotUnique):
        cu.execute("INSERT INTO u VALUES (1, 'b')")
    db.rollback()


def test_other_constraint_and_missing_table(db):
    cu = db.cursor()
    cu.execute("CREATE TABLE n (id INTEGER NOT NULL)")
    with pytest.raises(sqlerrors.ConstraintViolation):
        cu.execute("INSERT INTO n VALUES (NULL)")
    with pytest.raises(sqlerrors.InvalidTable):
        cu.execute("SELECT * FROM nonesuch")
    cu.execute("CREATE TABLE d (a INTEGER)")
    with pytest.raises(sqlerrors.DuplicateColumnName):
        cu.execute("ALTER TABLE d ADD COLUMN a INTEGER")
    db.rollback()


def test_sql_functions(db):
    cu = db.cursor()
    cu.execute("SELECT 'abc' REGEXP 'a.c', 'abc' REGEXP 'x'")
    assert tuple(cu.fetchone()) == (1, 0)
    cu.execute("SELECT unix_timestamp()")
    assert cu.fetchone()[0] > 1000000000


def test_sequence_nextval(db):
    db.loadSchema()
    seq = db.sequence('foo')
    first = seq.nextval()
    second = seq.nextval()
    assert second == first + 1
    assert seq.currval() == second
    db.commit()
    db.loadSchema()
    assert 'foo' in db.sequences


def test_load_schema(db):
    cu = db.cursor()
    cu.execute("CREATE TABLE a (id INTEGER)")
    cu.execute("CREATE INDEX a_idx ON a (id)")
    cu.execute("CREATE VIEW v AS SELECT id FROM a")
    db.commit()
    db.loadSchema()
    assert 'a' in db.tables
    assert 'a_idx' in db.tables['a']
    assert 'v' in db.views


def test_rename_column(db):
    cu = db.cursor()
    cu.execute("CREATE TABLE r (id INTEGER PRIMARY KEY, oldname TEXT)")
    cu.execute("INSERT INTO r VALUES (1, 'x')")
    db.commit()
    db.renameColumn('r', 'oldname', 'newname')
    db.commit()
    cu.execute("SELECT newname FROM r")
    assert cu.fetchone()[0] == 'x'
    with pytest.raises(sqlerrors.CursorError):
        cu.execute("SELECT oldname FROM r")
    db.rollback()


def test_drop_column(db):
    cu = db.cursor()
    cu.execute("CREATE TABLE r (id INTEGER, junk TEXT)")
    cu.execute("INSERT INTO r VALUES (1, 'x')")
    db.commit()
    db.dropColumn('r', 'junk')
    db.commit()
    cu.execute("SELECT * FROM r")
    assert [d[0] for d in cu.description] == ['id']
    assert tuple(cu.fetchone()) == (1,)


def test_analyze(db):
    cu = db.cursor()
    cu.execute("CREATE TABLE t (id INTEGER)")
    db.commit()
    db.loadSchema()
    db.analyze()
    assert not db.inTransaction()
    cu.execute("SELECT name FROM sqlite_master WHERE name = 'sqlite_stat1'")
    assert cu.fetchone() is not None


def test_compile_and_execstmt(db):
    # local/sqldb.py prepares a statement once with compile() and runs it
    # repeatedly with execstmt(); the stdlib driver has no prepared
    # statements, so this checks the shim still binds each call's args.
    cu = db.cursor()
    cu.execute("CREATE TABLE p (a INTEGER, b INTEGER)")
    stmt = cu.compile("INSERT INTO p (a, b) VALUES (?, ?)")
    for x in (1, 2, 3):
        cu.execstmt(stmt, x, 2 * x)
    cu.execute("SELECT a, b FROM p ORDER BY a")
    assert [tuple(r) for r in cu.fetchall()] == [(1, 2), (2, 4), (3, 6)]
    db.commit()
