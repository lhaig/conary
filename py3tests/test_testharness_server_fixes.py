"""Py3 fixes needed to serve a repository to the test harness."""
import types

import pytest

from conary.repository.netrepos import netauth, netserver, reposlog


class _Db:
    def inTransaction(self, default=None):
        return True

    def rollback(self):
        self.rolledBack = True

    def commit(self):
        pass


def _server(callLog=None):
    srv = object.__new__(netserver.NetworkRepositoryServer)
    srv.readOnlyRepository = False
    srv.callLog = callLog
    srv.db = _Db()
    srv.reopen = lambda: None
    srv.repos = types.SimpleNamespace(troveStore=None)  # for __del__
    return srv


@pytest.mark.parametrize('withLog', [False, True])
def test_callWrapper_reraises_original_exception(withLog):
    logged = []
    callLog = types.SimpleNamespace(
        log=lambda *a, **kw: logged.append(kw.get('exception')))
    srv = _server(callLog if withLog else None)

    def boom(*args):
        raise ValueError('boom')
    srv._callWrapper = boom
    with pytest.raises(ValueError, match='boom') as info:
        srv.callWrapper(None, None, 'checkVersion', None, [50], {}, 'ip')
    assert srv.db.rolledBack
    assert logged == ([info.value] if withLog else [])


def test_callWrapper_success_returns_result():
    srv = _server()
    srv._callWrapper = lambda *a: 'ok'
    assert srv.callWrapper(None, None, 'checkVersion', None, [50], {},
                           'ip') == 'ok'


def test_repository_call_log_is_binary(tmp_path):
    path = str(tmp_path / 'calls.log')
    logger = reposlog.RepositoryCallLogger(path, ['localhost'])
    logger.log('1.2.3.4', ('user', 'pw', []), 'checkVersion', [50],
               exception=ValueError('x'), latency=0.5)
    logger.close()
    entries = list(reposlog.RepositoryCallLogger(path, ['localhost'],
                                                 readOnly=True).__iter__())
    assert len(entries) == 1
    assert entries[0].methodName == 'checkVersion'
    assert entries[0].exceptionStr == 'x'
    assert entries[0].user == 'user'


@pytest.mark.parametrize('frozen', [None, '', b''])
def test_null_accept_flags_is_empty_flavor(frozen):
    assert netauth._thawFlavor(frozen).isEmpty()


def test_password_salt_roundtrip():
    # salt is stored as hex text and read back as bytes for the md5 check
    salt = b'\x00\xffab'
    assert bytes.fromhex(netauth._text(salt.hex())) == salt


def test_addUser_then_checkPassword(tmp_path):
    # addUser stores a random salt as hex; checkPassword must read it back
    # and accept only the right password
    from conary import dbstore
    from conary.server import schema
    db = dbstore.connect(str(tmp_path / 'auth.sqlite'), driver='sqlite')
    schema.loadSchema(db, doMigrate=True)
    db.commit()
    auth = netauth.NetworkAuthorization(db, [])
    auth.addUser('alice', 'secret')
    cu = db.cursor()
    cu.execute("SELECT salt FROM Users WHERE userName='alice'")
    stored = cu.fetchall()[0][0]
    assert len(bytes.fromhex(netauth._text(stored))) == 4
    assert auth.checkPassword(('alice', 'secret'))
    assert not auth.checkPassword(('alice', 'wrong'))
    assert not auth.checkPassword(('nobody', 'secret'))


def test_sqlite_renameColumn_with_dependent_view(tmp_path):
    from conary import dbstore
    db = dbstore.connect(str(tmp_path / 'r.sqlite'), driver='sqlite')
    cu = db.cursor()
    cu.execute('CREATE TABLE items (id INTEGER PRIMARY KEY, item TEXT)')
    cu.execute('CREATE VIEW itemview AS SELECT item FROM items')
    cu.execute("INSERT INTO items (item) VALUES ('a')")
    db.commit()
    db.loadSchema()
    assert db.renameColumn('items', 'item', 'i') is True
    cu.execute('SELECT i FROM items')
    assert cu.fetchall() == [('a',)]
    # the legacy-alter pragma must not leak out of the call
    assert db.dbh.execute('PRAGMA legacy_alter_table').fetchone() == (0,)
    db.close()


@pytest.mark.parametrize('ent', ['abc', 'x' * 100, 'a\xffb'])
def test_entitlement_wire_roundtrip(ent):
    from conary.repository import xmlshims
    conv = xmlshims.NetworkConvertors()
    wire = conv.fromEntitlement(ent)
    assert isinstance(wire, str)
    assert conv.toEntitlement(wire) == ent
