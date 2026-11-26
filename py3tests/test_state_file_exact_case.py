"""Exact-case CONARY state file detection (case-insensitive mounts)."""
import os

import pytest

from conary import state
from conary import checkin
from conary.build import cook


def _make(tmp_path, kind, name):
    p = tmp_path / name
    if kind == 'file':
        p.write_text('')
    elif kind == 'dir':
        p.mkdir()
    return p


@pytest.mark.parametrize('kind,name,expected', [
    ('file', 'CONARY', True),
    (None, None, False),
    ('dir', 'CONARY', False),
    ('dir', 'conary', False),
    ('file', 'Conary', False),
])
def testStateFileExists(tmp_path, monkeypatch, kind, name, expected):
    if kind:
        _make(tmp_path, kind, name)
    monkeypatch.chdir(tmp_path)
    assert state.stateFileExists('CONARY') is expected
    assert state.stateFileExists(str(tmp_path / 'CONARY')) is expected


def testStateFileExistsPrefixedPath(tmp_path, monkeypatch):
    sub = tmp_path / 'sub'
    sub.mkdir()
    (sub / 'CONARY').write_text('')
    other = tmp_path / 'other'
    other.mkdir()
    monkeypatch.chdir(other)
    assert state.stateFileExists(str(sub / 'CONARY')) is True
    assert state.stateFileExists(os.path.join('..', 'sub', 'CONARY')) is True


@pytest.mark.parametrize('rel', [
    'nodir/CONARY',
    'afile/CONARY',
])
def testStateFileExistsBadParent(tmp_path, rel):
    (tmp_path / 'afile').write_text('')
    assert state.stateFileExists(str(tmp_path / rel)) is False


@pytest.mark.parametrize('name,exc', [
    ('conary', state.CONARYFileMissing),
    ('CONARY', state.CONARYNotFile),
])
def testConaryStateFromFileErrors(tmp_path, monkeypatch, name, exc):
    (tmp_path / name).mkdir()
    monkeypatch.chdir(tmp_path)
    with pytest.raises(exc):
        state.ConaryStateFromFile('CONARY')


def _foldedExists(monkeypatch):
    """Make os.path.exists behave like a case-insensitive filesystem."""
    real = os.path.exists

    def exists(p):
        if p == 'CONARY':
            return real('CONARY') or real('conary')
        return real(p)
    monkeypatch.setattr(os.path, 'exists', exists)
    monkeypatch.setattr(os.path, 'isfile', lambda p, _r=os.path.isfile:
                        _r(p) or (p == 'CONARY' and _r('conary')))


def testGuessSourceVersionIgnoresConaryDir(tmp_path, monkeypatch):
    (tmp_path / 'conary').mkdir()
    monkeypatch.chdir(tmp_path)
    _foldedExists(monkeypatch)
    result = cook.guessSourceVersion(None, 'foo', '1.0', None)
    assert result == (None, None, None)


def testSetContextIgnoresConaryDir(tmp_path, monkeypatch):
    class FakeCfg:
        context = None

        def getContext(self, name):
            return None

    (tmp_path / 'conary').mkdir()
    monkeypatch.chdir(tmp_path)
    _foldedExists(monkeypatch)
    assert checkin.setContext(FakeCfg(), 'nosuch') is None
