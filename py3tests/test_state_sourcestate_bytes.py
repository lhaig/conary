"""SourceState keeps pathIds and fileIds as bytes through CONARY round trip."""
import pytest

from conary import checkin, state, versions
from conary.lib import sha1helper

PLACEHOLDER = b'0' * 20


def _committed_state():
    v = versions.VersionFromString('/localhost@rpl:linux/1.0-1',
                                   timeStamps=[1234567890.0])
    ss = state.SourceState('foo:source', v, v.branch())
    pathId = sha1helper.md5String(b'committed')
    fileId = sha1helper.sha1String(b'x')
    ss.addFile(pathId, 'committed.txt', v, fileId, isConfig=True,
               isAutoSource=False)
    return ss, pathId, fileId, v


@pytest.mark.parametrize('names', [
    ['foo.recipe'],
    ['foo.recipe', 'a.txt', 'b.txt'],
])
def testAddFilesWritesBytesIds(tmp_path, monkeypatch, names):
    monkeypatch.chdir(tmp_path)
    ss, cPathId, cFileId, cVersion = _committed_state()
    state.ConaryState(None, ss).write('CONARY')
    for n in names:
        (tmp_path / n).write_text('hello\n')

    checkin.addFiles(names, text=True)

    text = (tmp_path / 'CONARY').read_text()
    assert '30' * 20 in text
    assert sha1helper.sha1ToString(cFileId) in text

    back = state.ConaryStateFromFile('CONARY').getSourceState()
    entries = {e[1]: e for e in back.iterFileList()}
    assert set(entries) == set(names) | {'committed.txt'}
    for pathId, path, fileId, version in entries.values():
        assert isinstance(pathId, bytes) and len(pathId) == 16
        assert isinstance(fileId, bytes) and len(fileId) == 20
    assert entries['committed.txt'][0] == cPathId
    assert entries['committed.txt'][2] == cFileId
    assert entries['committed.txt'][3] == cVersion
    for n in names:
        assert entries[n][2] == PLACEHOLDER
        assert entries[n][3] == versions.NewVersion()

    # round trip is stable
    state.ConaryState(None, back).write('CONARY2')
    assert (tmp_path / 'CONARY2').read_text() == text
