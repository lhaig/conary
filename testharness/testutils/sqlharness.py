"""SQLite repository database harness.

start() returns one process-wide SqliteHarness; getDB(name) hands out
RepositoryDatabase objects backed by files under a private temp dir that is
removed at exit.  PostgreSQL and MySQL are not supported.
"""
import atexit
import os
import shutil
import tempfile

_harness = None


class RepositoryDatabase:
    """One SQLite database file, with the upstream testutils API."""

    driver = 'sqlite'

    def __init__(self, path):
        self.path = path
        self._conns = []

    def getDriver(self):
        return '%s %s' % (self.driver, self.path)

    def connect(self):
        from conary import dbstore
        db = dbstore.connect(self.path, driver=self.driver)
        self._conns.append(db)
        return db

    def _closeAll(self):
        conns, self._conns = self._conns, []
        for db in conns:
            try:
                db.close()
            except Exception:  # already closed or never usable
                pass

    def _reset(self):
        """Leave an empty database: no file, no journal."""
        self._closeAll()
        for suffix in ('', '-journal', '-wal', '-shm'):
            try:
                os.unlink(self.path + suffix)
            except FileNotFoundError:
                pass

    def reset(self):
        """Empty database, then the repository schema."""
        self._reset()
        self._createSchema()

    def _createSchema(self):
        from conary.server import schema
        db = self.connect()
        try:
            schema.loadSchema(db, doMigrate=True)
            db.commit()
            self._addTestUser(db)
        finally:
            self._conns.remove(db)
            db.close()

    @staticmethod
    def _addTestUser(db):
        """The user conary_test's default config logs in as (test/foo)."""
        from conary.repository.netrepos import netauth
        from conary.server import schema
        schema.setupTempTables(db)
        auth = netauth.NetworkAuthorization(db, [])
        auth.addRole('test')
        auth.addUser('test', 'foo')
        auth.addRoleMember('test', 'test')
        auth.addAcl('test', None, None, write=True, remove=True)
        auth.setAdmin('test', True)
        auth.setMirror('test', True)
        # anonymous: read-only access without credentials
        auth.addRole('anonymous')
        auth.addUser('anonymous', 'anonymous')
        auth.addRoleMember('anonymous', 'anonymous')
        auth.addAcl('anonymous', None, None)
        db.commit()

    def stop(self):
        self._closeAll()


class SqliteHarness:

    def __init__(self):
        self.dir = tempfile.mkdtemp(prefix='conary-sqlharness-')
        self.dbs = {}
        self._pid = os.getpid()

    def getDB(self, name='dbstore', keepExisting=False):
        db = self.dbs.get(name)
        if db is None:
            db = self.dbs[name] = RepositoryDatabase(
                os.path.join(self.dir, name + '.sqlite'))
        if not keepExisting:
            db._reset()
        elif not os.path.exists(db.path):
            db._createSchema()
        return db

    def cleanup(self):
        if os.getpid() != self._pid:
            return      # a forked child must not delete the parent's dir
        for db in self.dbs.values():
            db.stop()
        self.dbs = {}
        shutil.rmtree(self.dir, ignore_errors=True)


def start(*args, **kwargs):
    """Return the shared harness, creating it on first use."""
    global _harness
    if _harness is None or not os.path.isdir(_harness.dir):
        _harness = SqliteHarness()
    return _harness


def _cleanupAtExit():
    # Registered at import, so it runs after the cleanups that rephelp
    # registers later (ServerCache.cleanup still resets databases).
    if _harness is not None:
        _harness.cleanup()


atexit.register(_cleanupAtExit)
