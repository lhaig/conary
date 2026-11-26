"""SQLite harness, stdlib WSGI app server and nginx pass-through."""
import os
import socket
import urllib.request

import pytest

from testrunner.testcase import SkipTestException
from testutils import sqlharness
from testutils.servers.gunicorn_server import GunicornServer
from testutils.servers.nginx_server import NginxServer
from testutils.servers.uwsgi_server import UwsgiServer

# --- sqlharness -----------------------------------------------------------


@pytest.fixture
def harness():
    h = sqlharness.SqliteHarness()
    yield h
    h.cleanup()


def _tables(db):
    cu = db.cursor()
    cu.execute("select name from sqlite_master where type = 'table'")
    return {r[0] for r in cu.fetchall()}


def test_start_is_singleton():
    assert sqlharness.start() is sqlharness.start()


def test_getdb_api(harness):
    db = harness.getDB('x')
    assert db.driver == 'sqlite'
    assert db.getDriver() == 'sqlite ' + db.path
    assert db.path.startswith(harness.dir)
    assert harness.getDB() is harness.getDB()  # default name


def test_connect_roundtrip_and_keep_existing(harness):
    db = harness.getDB('x')
    conn = db.connect()
    cu = conn.cursor()
    cu.execute('create table t (a integer)')
    cu.execute('insert into t values (7)')
    conn.commit()
    kept = harness.getDB('x', keepExisting=True)
    assert kept is db
    cu = kept.connect().cursor()
    cu.execute('select a from t')
    assert cu.fetchall() == [(7,)]


@pytest.mark.parametrize('how', ['getdb', '_reset'])
def test_fresh_database_is_empty(harness, how):
    db = harness.getDB('x')
    conn = db.connect()
    conn.cursor().execute('create table t (a integer)')
    conn.commit()
    if how == 'getdb':
        db = harness.getDB('x', keepExisting=False)
    else:
        db._reset()
    assert not os.path.exists(db.path)
    assert _tables(db.connect()) == set()


def test_keep_existing_on_missing_file_creates_schema(harness):
    from conary.server import schema
    db = harness.getDB('new', keepExisting=True)
    conn = db.connect()
    schema.checkVersion(conn)
    assert 'Users' in _tables(conn)


def test_reset_gives_repository_schema(harness):
    from conary.server import schema
    db = harness.getDB('x')
    db.reset()
    conn = db.connect()
    schema.checkVersion(conn)
    assert 'Users' in _tables(conn)
    cu = conn.cursor()
    cu.execute('select userName from Users order by userName')
    assert cu.fetchall() == [('anonymous',), ('test',)]


def test_stop_closes_connections(harness):
    db = harness.getDB('x')
    conn = db.connect()
    db.stop()
    assert db._conns == []
    assert conn.closed


def test_cleanup_removes_dir():
    h = sqlharness.SqliteHarness()
    h.getDB('x').connect()
    h.cleanup()
    assert not os.path.exists(h.dir)


# --- app server -----------------------------------------------------------

APP = '''
import os
def application(environ, start_response):
    if environ['PATH_INFO'] == '/boom':
        raise RuntimeError('boom')
    start_response('200 OK', [('Content-Type', 'text/plain')])
    return [os.environ.get('MARKER', 'unset').encode()
            + b'|' + environ['PATH_INFO'].encode()]
'''

DIES = 'raise SystemExit("cannot start")\n'


@pytest.fixture
def appmod(tmp_path, monkeypatch):
    def make(name, source):
        (tmp_path / (name + '.py')).write_text(source)
        monkeypatch.syspath_prepend(str(tmp_path))
        monkeypatch.setenv('PYTHONPATH', str(tmp_path))
        return name
    return make


@pytest.fixture
def server(tmp_path, appmod):
    made = []

    def make(app='sampleapp', source=APP, cls=GunicornServer, **kw):
        appmod(app, source)
        srv = cls(serverDir=str(tmp_path / 'srv'), workers=1,
                  application=app, environ={'MARKER': 'hello'}, **kw)
        made.append(srv)
        return srv
    yield make
    for srv in made:
        srv.stop()


def _get(srv, path):
    url = srv.getProxyTo() + path
    return urllib.request.urlopen(url, timeout=10).read()


def _refuses(port):
    try:
        socket.create_connection(('127.0.0.1', port), timeout=2).close()
    except OSError:
        return True
    return False


@pytest.mark.parametrize('cls', [GunicornServer, UwsgiServer])
def test_lifecycle(server, cls):
    srv = server(cls=cls)
    assert srv.getProxyTo() == 'http://127.0.0.1:%d' % srv.port
    assert not srv.isStarted()
    srv.start()
    assert srv.isStarted()
    assert _get(srv, '/x') == b'hello|/x'
    pid = srv.process.pid
    srv.stop()
    assert not srv.isStarted()
    assert _refuses(srv.port)
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)
    srv.stop()  # idempotent


def test_traceback_reaches_error_log_and_reset_truncates(server):
    srv = server()
    srv.start()
    with pytest.raises(urllib.error.HTTPError):
        _get(srv, '/boom')
    with open(srv.errorLog) as f:
        assert 'Traceback (most recent call last)' in f.read()
    srv.reset()
    assert os.path.getsize(srv.errorLog) == 0
    assert srv.isStarted()
    assert _get(srv, '/y') == b'hello|/y'


def test_child_dying_at_startup_raises_promptly(server):
    import time
    srv = server(app='deadapp', source=DIES)
    t = time.monotonic()
    with pytest.raises(RuntimeError, match='cannot start'):
        srv.start()
    assert time.monotonic() - t < 10
    assert not srv.isStarted()


def test_serves_wsgi_hooks_config(server, tmp_path):
    cfg = tmp_path / 'repository.cnr'
    cfg.write_text('')
    srv = server(app='conary.server.wsgi_hooks')
    srv.environ['CONARY_SERVER_CONFIG'] = str(cfg)
    srv.start()
    # no serverName configured: the router answers (error or not) over HTTP
    try:
        urllib.request.urlopen(srv.getProxyTo() + '/conary/', timeout=10)
    except urllib.error.HTTPError as err:
        assert err.code in (400, 404, 500, 501)
    assert srv.isStarted()


# --- nginx pass-through ------------------------------------------------------


def test_nginx_passthrough():
    ngx = NginxServer(serverDir='/x', proxyTo='http://127.0.0.1:4321')
    assert ngx.getUrl(ssl=True) == 'http://127.0.0.1:4321'
    assert ngx.getUrl(ssl=False) == 'http://127.0.0.1:4321'
    assert ngx.getHostPort() == ('127.0.0.1', 4321)
    assert ngx.start() is None and ngx.stop() is None and ngx.reset() is None


def test_nginx_ssl_skips_in_constructor():
    with pytest.raises(SkipTestException, match='SSL'):
        NginxServer(serverDir='/x', proxyTo='http://127.0.0.1:1',
                    sslCertAndKey=('a.crt', 'a.key'))
