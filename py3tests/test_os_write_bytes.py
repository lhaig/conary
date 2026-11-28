"""Every os.write in conary/ receives bytes on Python 3.  Each test calls the
real function and checks the bytes (or the decoded str) on the other side."""
import os
import types

import pytest

from conary import trove, versions
from conary.build import build, cook
from conary.conaryclient import update as clientupdate
from conary.deps import deps
from conary.lib.epdb_embedded import epdb_server
from conary.build.macros import Macros
from conary.local import sqldb
from conary.local import update as localupdate

NONASCII = 'föö'


def _addTroves(ldb, specs):
    for name, ver, flavor in specs:
        t = trove.Trove(name, versions.VersionFromString(
            ver, timeStamps=[1000000000.0]), deps.parseFlavor(flavor))
        ldb.addTroveDone(ldb.addTrove(t))
    ldb.commit()


@pytest.fixture
def ldb(tmp_path):
    db = sqldb.Database(str(tmp_path / 'local.db'))
    yield db
    db.close()


def _client(root, dbPath, db):
    cfg = types.SimpleNamespace(root=root, dbPath=dbPath)
    return types.SimpleNamespace(cfg=cfg, db=db)


# -- conaryclient/update.py recordManifest ---------------------------------

def test_record_manifest_exact_bytes(tmp_path, ldb):
    _addTroves(ldb, [
        ('zed:runtime', '/localhost@rpl:linux/2.0-1-1', 'is: x86'),
        ('abc', '/localhost@rpl:linux/1.0-1-1', ''),
        ('mid:data', '/localhost@rpl:linux/1.0-1-1', 'is: x86_64'),
    ])
    (tmp_path / 'var').mkdir()
    clientupdate.ClientUpdate.recordManifest(_client(str(tmp_path), 'var', ldb))
    data = (tmp_path / 'var' / 'manifest').read_bytes()
    assert isinstance(data, bytes)
    # Python 2 layout: sorted text lines, UTF-8 on disk
    assert data == (
        b'abc=/localhost@rpl:linux/1.0-1-1[]\n'
        b'mid:data=/localhost@rpl:linux/1.0-1-1[is: x86_64]\n'
        b'zed:runtime=/localhost@rpl:linux/2.0-1-1[is: x86]\n')
    # no leftover temp files
    assert [p.name for p in (tmp_path / 'var').iterdir()] == ['manifest']


class _FakeDb:
    """Trove names, versions and flavors are validated, so a non-ASCII or
    undecodable name can only reach recordManifest through a stand-in db."""
    def __init__(self, rows):
        self.rows = rows

    def iterAllTroves(self):
        return iter(self.rows)


@pytest.mark.parametrize('name,want', [
    (NONASCII, b'f\xc3\xb6\xc3\xb6'),
    (os.fsdecode(b'ab\xffc'), b'ab\xffc'),    # surrogate-escaped byte
])
def test_record_manifest_non_ascii_round_trip(tmp_path, name, want):
    (tmp_path / 'var').mkdir()
    db = _FakeDb([(name, 'V', 'F')])
    clientupdate.ClientUpdate.recordManifest(_client(str(tmp_path), 'var', db))
    assert (tmp_path / 'var' / 'manifest').read_bytes() == want + b'=V[F]\n'


@pytest.mark.parametrize('root,dbPath', [(':memory:', 'var'),
                                         ('/nonexistent-root', ':memory:')])
def test_record_manifest_memory_writes_nothing(tmp_path, ldb, root, dbPath):
    _addTroves(ldb, [('abc', '/localhost@rpl:linux/1.0-1-1', '')])
    clientupdate.ClientUpdate.recordManifest(_client(root, dbPath, ldb))
    assert not os.path.exists('/nonexistent-root')
    assert list(tmp_path.iterdir()) == [tmp_path / 'local.db']


# -- build/cook.py changeset path pipe -------------------------------------

@pytest.mark.parametrize('path', ['/tmp/foo-1.ccs', '/tmp/föö.ccs',
                                  os.fsdecode(b'/tmp/a\xffb.ccs'), ''])
def test_cook_changeset_path_pipe(path):
    r, w = os.pipe()
    try:
        if path:
            cook._sendChangeSetPath(w, path)
        os.close(w)
        w = None
        got = cook._recvChangeSetPath(r)
    finally:
        os.close(r)
        if w is not None:
            os.close(w)
    assert isinstance(got, str)
    assert got == path


# -- local/update.py tag handler stdin feed --------------------------------

class _Tag:
    def __init__(self, tag):
        self.tag = tag


def _feed(datasource, hi, tagInfo):
    errors = []
    cmd = localupdate.TagCommand(types.SimpleNamespace(error=errors.append))
    r, w = os.pipe()
    try:
        cmd._writeHandlerInput(w, datasource, hi, tagInfo)
        os.close(w)
        w = None
        chunks = []
        while True:
            c = os.read(r, 4096)
            if not c:
                break
            chunks.append(c)
    finally:
        os.close(r)
        if w is not None:
            os.close(w)
    assert errors == []
    return b''.join(chunks)


def test_tag_handler_stdin_feed():
    hi = localupdate.HandlerInfo()
    t = _Tag('t')
    hi.update(t, ['/b/fö', '/a', os.fsdecode(b'/c\xff')])
    assert _feed('stdin', hi, t) == b'/a\n/b/f\xc3\xb6\n/c\xff\n'


def test_tag_handler_multitag_feed():
    hi = localupdate.HandlerInfo()
    t1, t2 = _Tag('one'), _Tag('two')
    hi.update(t1, ['/x', '/y'])
    hi.update(t2, ['/x'])
    assert _feed('multitag', hi, None) == b'one two\n/x\none\n/y\n'


# -- local/update.py runTroveScript (script file and exec-failure message) -

class _Callback:
    def __init__(self):
        self.out = []
        self.failures = []

    def troveScriptStarted(self, scriptId):
        pass

    def troveScriptOutput(self, scriptId, line):
        self.out.append(line)

    def troveScriptFinished(self, scriptId):
        pass

    def troveScriptFailure(self, scriptId, rc):
        self.failures.append(rc)

    def warning(self, *args):
        pass


@pytest.fixture(autouse=True)
def _syslog():
    from conary.lib import log
    old = log.syslog
    log.openSysLog('/', None)
    yield
    log.syslog = old


def _run(tmp_path, script):
    cb = _Callback()
    job = ('foo', (None, None), (versions.VersionFromString(
        '/localhost@rpl:linux/1.0-1-1'), deps.Flavor()), False)
    rc = localupdate.runTroveScript(job, script, None, str(tmp_path), '/', cb)
    return rc, cb


@pytest.mark.parametrize('script', [
    b'#!/bin/sh\necho hello\n',
    '#!/bin/sh\necho hello\n',          # str script is encoded, not rejected
])
def test_run_trove_script_writes_script(tmp_path, script):
    rc, cb = _run(tmp_path, script)
    assert cb.failures == []
    assert [x.strip() for x in cb.out] == [type(cb.out[0])('hello')]
    assert list(tmp_path.iterdir()) == []


def test_run_trove_script_exec_failure_message(tmp_path):
    # no interpreter line: execve fails and the child writes str(e) to fd 2
    rc, cb = _run(tmp_path, b'echo hi\n')
    assert cb.failures == [1]
    # exactly the one message line: a child that died in the except block
    # would print a traceback instead
    assert len(cb.out) == 1
    line = cb.out[0]
    line = line if isinstance(line, str) else line.decode()
    assert line.startswith('[Errno 8] Exec format error')
    assert line.endswith('.trvscript\'\n')


# -- build/build.py Replace ------------------------------------------------

def _replace(tmp_path, content, pattern, sub):
    f = tmp_path / 'file'
    f.write_bytes(content)
    r = build.Replace.__new__(build.Replace)
    r.regexps = [(pattern, sub)]
    r.lines = None
    r.min = r.max = r.lineMatch = None
    r.allowNoChange = False
    r.manifest = None
    r.paths = [str(f)]
    macros = Macros()
    macros.destdir = '/nonexistent'
    macros.builddir = 'x'
    return f, r, macros


def test_replace_writes_bytes(tmp_path):
    f, r, macros = _replace(tmp_path, b'one f\xc3\xb6\xc3\xb6\r\ntwo\n', 'one', 'ONE')
    _doReplace(r, macros)
    assert f.read_bytes() == b'ONE f\xc3\xb6\xc3\xb6\r\ntwo\n'


def test_replace_preserves_non_utf8_bytes(tmp_path):
    f, r, macros = _replace(tmp_path, b'a \xff b\n', 'a', 'A')
    _doReplace(r, macros)
    assert f.read_bytes() == b'A \xff b\n'


def _doReplace(r, macros):
    import conary.build.action as action
    orig = action._expandPaths
    action._expandPaths = lambda paths, m, error=False: list(paths)
    try:
        r.do(macros)
    finally:
        action._expandPaths = orig


# -- lib/epdb_embedded/epdb_server.py interrupt ---------------------------

def test_epdb_interrupt_writes_ctrl_c():
    local_r, local_w = os.pipe()
    try:
        h = epdb_server.TelnetServerProtocolHandler.__new__(
            epdb_server.TelnetServerProtocolHandler)
        h.local = local_w
        h.process_IAC(None, epdb_server.IP, None)
        assert os.read(local_r, 10) == b'\x03'
    finally:
        os.close(local_r)
        os.close(local_w)
