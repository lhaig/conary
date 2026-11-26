"""Changeset file container: names, tags and contents are bytes end to end."""
import gzip

import pytest

from conary.lib import sha1helper
from conary.repository import changeset, filecontainer, filecontents
from conary.repository.changeset import ChangedFileTypes

CFT = ChangedFileTypes

PATHIDS = [bytes([i]) * 16 for i in (1, 2, 3, 4)]
FILEIDS = [bytes([i]) * 20 for i in (0x11, 0x22, 0x33, 0x44)]
CONTENTS = {
    'cfg': b'config line\n',
    'diff': b'@@ -1,1 +1,1 @@\n-a\n+b\n',
    'reg': b'regular \xff\xfe contents\n',
}


def _buildChangeSet():
    cs = changeset.ChangeSet()
    cs.addFileContents(PATHIDS[0], FILEIDS[0], CFT.file,
                       filecontents.FromString(CONTENTS['cfg']), True)
    cs.addFileContents(PATHIDS[1], FILEIDS[1], CFT.diff,
                       filecontents.FromString(CONTENTS['diff']), True)
    cs.addFileContents(PATHIDS[2], FILEIDS[2], CFT.file,
                       filecontents.FromString(CONTENTS['reg']), False)
    return cs


def _drain(cs):
    """Return {key: (tag, data)} for every file in the container."""
    out = {}
    for name, tag, f in _iterContainer(cs):
        out[name] = (tag, gzip.GzipFile(None, 'r', fileobj=f).read())
    return out


def _iterContainer(cs):
    csf = cs.fileContainers[0]
    csf.reset()
    first = csf.getNextFile()
    assert first[0] == b'CONARYCHANGESET'
    while True:
        nxt = csf.getNextFile()
        if nxt is None:
            return
        yield nxt


class TestFileContainerStrictBytes:

    @pytest.mark.parametrize('name,tag', [
        ('name', b'tag'),
        (b'name', 'tag'),
        ('né', b''),
        (b'name', None),
    ])
    def test_addFileRejectsStr(self, tmp_path, name, tag):
        with open(tmp_path / 'c', 'w+b') as f:
            fc = filecontainer.FileContainer(f)
            with pytest.raises(TypeError):
                fc.addFile(name, filecontents.FromString(b'x'), tag)

    def test_addFileBytesRoundTrip(self, tmp_path):
        p = tmp_path / 'c'
        with open(p, 'w+b') as f:
            fc = filecontainer.FileContainer(f)
            fc.addFile(b'n1', filecontents.FromString(b'data'), b'0 file')
        fc = filecontainer.FileContainer(util_extfile(p))
        name, tag, sub = fc.getNextFile()
        assert (name, tag) == (b'n1', b'0 file')
        assert gzip.GzipFile(None, 'r', fileobj=sub).read() == b'data'


def util_extfile(path):
    from conary.lib import util
    return util.ExtendedFile(str(path), 'rb', buffering=False)


class TestTagHelpers:

    @pytest.mark.parametrize('early,contType,expected', [
        (True, CFT.file, b'1 file'),
        (False, CFT.file, b'0 file'),
        (True, CFT.diff, b'1 diff'),
        (False, CFT.refr, b'0 refr'),
        (False, CFT.ptr, b'0 ptr'),
    ])
    def test_csfTag(self, early, contType, expected):
        tag = changeset._csfTag(early, contType)
        assert isinstance(tag, bytes)
        assert tag == expected

    @pytest.mark.parametrize('tag,expected', [
        (b'1 file', True), (b'1 diff', True),
        (b'0 file', False), (b'0 refr', False),
    ])
    def test_tagIsConfig(self, tag, expected):
        assert changeset._tagIsConfig(tag) is expected

    @pytest.mark.parametrize('tag,expected', [
        (b'1 file', CFT.file), (b'0 diff', CFT.diff),
        (b'0 ptr', CFT.ptr), (b'1 refr', CFT.refr),
    ])
    def test_tagType(self, tag, expected):
        got = changeset._tagType(tag)
        assert isinstance(got, str)
        assert got == expected

    @pytest.mark.parametrize('tag,contType,expected', [
        (b'0 file', CFT.file, True),
        (b'1 file', CFT.file, True),
        (b'0 diff', CFT.file, False),
        (b'0 refr', CFT.refr, True),
        (b'1 refr', CFT.diff, False),
    ])
    def test_tagIs(self, tag, contType, expected):
        assert changeset._tagIs(tag, contType) is expected


class TestFileDictFreeze:

    def test_freezeMixedNoneOldFileId(self):
        d = changeset.ChangeSetFileDict()
        d[(FILEIDS[2], FILEIDS[3])] = b'cs2'
        d[(None, FILEIDS[1])] = b'cs1'
        d[(FILEIDS[0], FILEIDS[1])] = b'cs0'
        frozen = d.freeze()
        assert isinstance(frozen, bytes)
        # None old fileId sorts first (empty), then by oldFileId
        expected = b''.join(
            len(s).to_bytes(4, 'big') + s for s in (
                changeset.FileInfo(b'', FILEIDS[1], b'cs1').freeze(),
                changeset.FileInfo(FILEIDS[0], FILEIDS[1], b'cs0').freeze(),
                changeset.FileInfo(FILEIDS[2], FILEIDS[3], b'cs2').freeze()))
        assert frozen == expected


class TestWriteReadRoundTrip:

    def test_roundTrip(self, tmp_path):
        cs = _buildChangeSet()
        path = str(tmp_path / 'out.ccs')
        cs.writeToFile(path)

        back = changeset.ChangeSetFromFile(path)
        csf = back.fileContainers[0]
        csf.reset()
        name, tag, _ = csf.getNextFile()
        assert name == b'CONARYCHANGESET'
        assert tag == b''
        seen = {}
        while True:
            nxt = csf.getNextFile()
            if not nxt:
                break
            seen[nxt[0]] = nxt[1]
        keys = [changeset.makeKey(PATHIDS[i], FILEIDS[i]) for i in range(3)]
        assert seen == {keys[0]: b'1 file', keys[1]: b'1 diff',
                        keys[2]: b'0 file'}

        back = changeset.ChangeSetFromFile(path)
        tag, cont = back.getFileContents(PATHIDS[0], FILEIDS[0])
        assert (tag, cont.get().read()) == (CFT.file, CONTENTS['cfg'])
        tag, cont = back.getFileContents(PATHIDS[1], FILEIDS[1])
        assert (tag, cont.get().read()) == (CFT.diff, CONTENTS['diff'])
        tag, cont = back.getFileContents(PATHIDS[2], FILEIDS[2])
        assert (tag, cont.get().read()) == (CFT.file, CONTENTS['reg'])

    def test_iterRegularFileContentsNonEmpty(self, tmp_path):
        cs = _buildChangeSet()
        path = str(tmp_path / 'out.ccs')
        cs.writeToFile(path)
        back = changeset.ChangeSetFromFile(path)
        # iterRegularFileContents needs file streams to map fileId -> sha1
        sha1 = sha1helper.sha1String(CONTENTS['reg'])
        key = FILEIDS[2]

        import conary.repository.changeset as mod

        orig = mod.files
        class FakeFilesMod:
            frozenFileHasContents = staticmethod(lambda s: True)
            frozenFileContentInfo = staticmethod(
                lambda s: type('C', (), {'sha1': lambda self: sha1})())
            @staticmethod
            def frozenFileFlags(s):
                return type('F', (), {
                    'isEncapsulatedContent': lambda self: False})()
        back.files = {(None, key): b'stream'}
        mod.files = FakeFilesMod
        try:
            got = [(s, gzip.GzipFile(None, 'r', fileobj=f).read())
                   for s, f in back.iterRegularFileContents()]
            assert got == [(sha1, CONTENTS['reg'])]
            back.reset()
            got = [s for s, f in back.iterRegularFileContents()]
            assert got == [sha1]
        finally:
            mod.files = orig

    def test_mergeReadOnlyThenWrite(self, tmp_path):
        a = _buildChangeSet()
        pa = str(tmp_path / 'a.ccs')
        a.writeToFile(pa)

        b = changeset.ChangeSet()
        b.addFileContents(PATHIDS[3], FILEIDS[3], CFT.file,
                          filecontents.FromString(b'other\n'), False)
        pb = str(tmp_path / 'b.ccs')
        b.writeToFile(pb)

        merged = changeset.ReadOnlyChangeSet()
        merged.merge(changeset.ChangeSetFromFile(pa))
        merged.merge(changeset.ChangeSetFromFile(pb))
        pm = str(tmp_path / 'm.ccs')
        merged.writeToFile(pm)

        back = changeset.ChangeSetFromFile(pm)
        for i, data in ((0, CONTENTS['cfg']), (1, CONTENTS['diff']),
                        (2, CONTENTS['reg']), (3, b'other\n')):
            tag, cont = back.getFileContents(PATHIDS[i], FILEIDS[i])
            assert cont.get().read() == data

    def test_dictAsCsfTags(self):
        csf = changeset.DictAsCsf({
            b'a': (CFT.file, filecontents.FromString(b'x'), False)})
        csf.addConfigs({b'b': (CFT.diff, filecontents.FromString(b'y'),
                               False)})
        names = []
        while True:
            n = csf.getNextFile()
            if not n:
                break
            names.append((n[0], n[1]))
        assert names == [(b'b', b'1 diff'), (b'a', b'0 file')]


class TestFileDictThaw:

    def test_freezeThawRoundTrip(self):
        d = changeset.ChangeSetFileDict()
        d[(None, FILEIDS[1])] = b'cs1'
        d[(FILEIDS[0], FILEIDS[2])] = b'cs0'
        e = changeset.ChangeSetFileDict()
        e.thaw(d.freeze())
        assert sorted(e.items(), key=lambda kv: kv[0][0] or b'') == [
            ((None, FILEIDS[1]), b'cs1'), ((FILEIDS[0], FILEIDS[2]), b'cs0')]
        assert (None, FILEIDS[1]) in e


class TestWireBase64:

    @pytest.mark.parametrize('data', [b'', b'\x00\xff' * 3, b'x' * 100])
    def test_roundTrip(self, data):
        wire = sha1helper.toBase64(data)
        assert isinstance(wire, str)
        assert sha1helper.fromBase64(wire) == data
        assert sha1helper.fromBase64(wire.encode('ascii')) == data
