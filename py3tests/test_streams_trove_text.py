"""Text streams: str above the wire, bytes on the wire.

TextStream holds the same bytes as StringStream but its call returns str
(UTF-8, surrogateescape), so the file, changelog and trove layers get str
and the frozen data does not change.
"""
import pytest

from conary import changelog, files, streams, trove, versions
from conary.deps import deps
from conary.lib import sha1helper

PATHID = b'\x01' * 16
NONASCII = 'éè-中'
RAW = b'caf\xe9\xff'


# ------------------------------------------------------------- helpers

@pytest.mark.parametrize('raw', [b'', b'abc', NONASCII.encode(), RAW,
                                 b'\x00\xfe\x80'])
def test_toStr_round_trip(raw):
    text = sha1helper.toStr(raw)
    assert isinstance(text, str)
    assert sha1helper.toBytes(text) == raw


def test_toStr_str_passthrough_and_type_error():
    assert sha1helper.toStr('abc') == 'abc'
    assert sha1helper.toStr(bytearray(b'abc')) == 'abc'
    with pytest.raises(TypeError):
        sha1helper.toStr(5)


# ----------------------------------------------------------- TextStream

@pytest.mark.parametrize('val', ['', 'abc', NONASCII,
                                 RAW.decode('utf-8', 'surrogateescape')])
def test_textstream_str_in_str_out(val):
    t = streams.TextStream()
    t.set(val)
    assert t() == val
    assert isinstance(t(), str)
    assert t.freeze() == sha1helper.toBytes(val)
    assert streams.TextStream(val)() == val
    # thaw takes wire bytes
    assert streams.TextStream(sha1helper.toBytes(val))() == val
    t2 = streams.TextStream()
    t2.thaw(sha1helper.toBytes(val))
    assert t2() == val


def test_textstream_accepts_bytes_in_set():
    t = streams.TextStream()
    t.set(NONASCII.encode())
    assert t() == NONASCII


@pytest.mark.parametrize('val', ['abc', NONASCII])
def test_textstream_wire_identical_to_stringstream(val):
    s = streams.StringStream()
    s.set(sha1helper.toBytes(val))
    t = streams.TextStream()
    t.set(val)
    assert s.freeze() == t.freeze()
    assert s.freeze() == sha1helper.toBytes(val)
    # == compares same-typed streams; thawing the wire bytes gives equal ones
    assert streams.TextStream(s.freeze()) == t


def test_textstream_diff_twm():
    old = streams.TextStream('old')
    new = streams.TextStream(NONASCII)
    d = new.diff(old)
    assert isinstance(d, bytes)
    assert d == NONASCII.encode()
    old.twm(d, old)
    assert old() == NONASCII
    assert old == new
    assert new.diff(new) is None


# ---------------------------------------------------------------- files

def _inode(f, owner='root', group='wheel'):
    f.inode.perms.set(0o755)
    f.inode.mtime.set(1234567)
    f.inode.owner.set(owner)
    f.inode.group.set(group)
    f.flags.set(0)


def _regular(owner='root', group='wheel'):
    f = files.RegularFile(PATHID)
    _inode(f, owner, group)
    f.contents.size.set(5)
    f.contents.sha1.set(b'\x02' * 20)
    return f


def _symlink(owner='root', group='wheel', target='/tmp/' + NONASCII):
    f = files.SymbolicLink(PATHID)
    _inode(f, owner, group)
    f.target.set(target)
    return f


def _device(cls):
    def make(owner='root', group='wheel'):
        f = cls(PATHID)
        _inode(f, owner, group)
        f.devt.major.set(8)
        f.devt.minor.set(1)
        return f
    return make


def _directory(owner='root', group='wheel'):
    f = files.Directory(PATHID)
    _inode(f, owner, group)
    return f


FILE_CASES = [
    pytest.param(_regular, id='regular'),
    pytest.param(_symlink, id='symlink'),
    pytest.param(_device(files.CharacterDevice), id='chardev'),
    pytest.param(_device(files.BlockDevice), id='blockdev'),
    pytest.param(_directory, id='directory'),
]


@pytest.mark.parametrize('make', FILE_CASES)
def test_file_freeze_thaw(make):
    f = make(owner='rööt', group=NONASCII)
    frz = f.freeze()
    assert isinstance(frz, bytes)
    assert frz[0:1] == f.lsTag.encode()
    g = files.ThawFile(frz, PATHID)
    assert g == f
    assert g.__class__ is f.__class__
    assert g.freeze() == frz
    assert isinstance(g.inode.owner(), str)
    assert g.inode.owner() == 'rööt'
    assert g.inode.group() == NONASCII
    assert f.copy() == f


@pytest.mark.parametrize('make', FILE_CASES)
def test_file_diff_twm(make):
    old = make()
    new = make(owner='daemon', group='bin')
    new.inode.perms.set(0o700)
    d = new.diff(old)
    assert isinstance(d, bytes)
    assert files.fileStreamIsDiff(d)
    assert not files.fileStreamIsDiff(new.freeze())
    assert files.fieldsChanged(d)
    merged = old.copy()
    merged.twm(d, merged)
    assert merged == new
    assert merged.inode.owner() == 'daemon'


@pytest.mark.parametrize('make', FILE_CASES)
def test_file_diff_other_type_is_full_freeze(make):
    new = make()
    other = _directory() if new.lsTag != 'd' else _regular()
    assert new.diff(other) == new.freeze()
    assert not files.fileStreamIsDiff(new.diff(other))
    assert new.diff(None) == new.freeze()


def test_symlink_target_str():
    f = files.ThawFile(_symlink().freeze(), PATHID)
    assert f.target() == '/tmp/' + NONASCII
    assert isinstance(f.target(), str)


def test_symlink_target_invalid_utf8_round_trips():
    raw = b'/tmp/\xff\xfe'
    f = files.SymbolicLink(PATHID)
    _inode(f)
    f.target.set(raw)
    assert f.target() == sha1helper.toStr(raw)
    g = files.ThawFile(f.freeze(), PATHID)
    assert sha1helper.toBytes(g.target()) == raw


def test_file_mode_string_and_frozen_helpers():
    f = _regular()
    assert f.modeString().startswith('-rwx')
    frz = f.freeze()
    assert files.frozenFileHasContents(frz)
    assert not files.frozenFileHasContents(_directory().freeze())


def test_contents_changed():
    old = _regular()
    new = _regular()
    new.contents.sha1.set(b'\x03' * 20)
    assert files.contentsChanged(new.diff(old))
    new2 = _regular()
    new2.inode.perms.set(0o700)
    assert not files.contentsChanged(new2.diff(old))
    assert not files.contentsChanged(_directory().diff(_directory()))


# --------------------------------------------------- OptionalFlavorStream

def _flavor(s):
    return deps.parseFlavor(s)


@pytest.mark.parametrize('old,new', [
    (None, None),
    (None, 'is: x86'),
    ('is: x86', None),
    ('is: x86', 'is: x86_64'),
    ('is: x86', 'is: x86'),
])
def test_optional_flavor_diff_twm(old, new):
    o = streams.OptionalFlavorStream()
    o.set(None if old is None else _flavor(old))
    n = streams.OptionalFlavorStream()
    n.set(None if new is None else _flavor(new))
    d = n.diff(o)
    applied = streams.OptionalFlavorStream(o.freeze())
    if old == new:
        assert d is None
    else:
        assert isinstance(d, bytes)
        applied.twm(d, applied)
    assert applied == n
    assert applied.freeze() == n.freeze()
    assert streams.OptionalFlavorStream(n.freeze()) == n


# ------------------------------------------------------------ changelog

def test_changelog_text():
    cl = changelog.ChangeLog(NONASCII, 'a@example.com', 'msg ' + NONASCII + '\n')
    assert cl.getName() == NONASCII
    assert cl.getContact() == 'a@example.com'
    assert cl.getMessage() == 'msg ' + NONASCII + '\n'
    frz = cl.freeze()
    assert isinstance(frz, bytes)
    th = changelog.ChangeLog(frz)
    assert th == cl
    assert isinstance(th.getName(), str)
    assert th.getName() == NONASCII
    assert th.getMessage() == cl.getMessage()


def test_changelog_diff_twm():
    old = changelog.ChangeLog('a', 'b', 'c\n')
    new = changelog.ChangeLog(NONASCII, 'b', 'd\n')
    d = new.diff(old)
    assert isinstance(d, bytes)
    merged = changelog.ChangeLog(old.freeze())
    merged.twm(d, merged)
    assert merged == new
    assert merged.getName() == NONASCII


# ---------------------------------------------------------------- trove

def _trove():
    v = versions.ThawVersion('/localhost@rpl:linux/1:1.0-1-1')
    t = trove.Trove('foo:runtime', v, deps.parseFlavor('is: x86'),
                    changeLog=changelog.ChangeLog(NONASCII, 'a@b', 'm ' + NONASCII + '\n'))
    t.setSourceName('foo:source')
    return t


def test_trove_text_fields():
    t = _trove()
    assert t.getName() == 'foo:runtime'
    assert isinstance(t.getName(), str)
    assert t.getSourceName() == 'foo:source'
    assert isinstance(t.getSourceName(), str)
    assert t.getChangeLog().getName() == NONASCII


def test_trove_freeze_thaw():
    t = _trove()
    frz = t.freeze()
    assert isinstance(frz, bytes)
    ti = trove.TroveInfo(t.troveInfo.freeze())
    assert ti.sourceName() == 'foo:source'
    assert isinstance(ti.sourceName(), str)
    assert ti == t.troveInfo


def test_trove_full_round_trip():
    # The whole trove, not only troveinfo: absolute changeset -> new Trove.
    t = _trove()
    trvCs = t.diff(None, absolute=True)[0]
    back = trove.Trove(trvCs)
    assert back == t
    assert back.getName() == 'foo:runtime'
    assert isinstance(back.getName(), str)
    assert back.getVersion() == t.getVersion()
    assert back.getFlavor() == t.getFlavor()
    cl = back.getChangeLog()
    assert (cl.getName(), cl.getContact(), cl.getMessage()) == (
        NONASCII, 'a@b', 'm ' + NONASCII + '\n')
    assert back.getSourceName() == 'foo:source'
    # and through the frozen trove changeset bytes
    thawed = trove.Trove(trove.ThawTroveChangeSet(trvCs.freeze()))
    assert thawed == t


def test_trove_diff_apply():
    old = _trove()
    new = old.copy()
    new.setSourceName('bar:source')
    new.changeChangeLog(changelog.ChangeLog('n', 'c', 'x ' + NONASCII + '\n'))
    trvCs = new.diff(old)[0]
    merged = old.copy()
    merged.applyChangeSet(trvCs)
    assert merged.getSourceName() == 'bar:source'
    assert merged.getChangeLog().getMessage() == 'x ' + NONASCII + '\n'
    assert merged.getName() == 'foo:runtime'


def test_trove_metadata_text():
    md = trove.MetadataItem()
    md.id.set(b'\x01' * 20)
    md.shortDesc.set('short ' + NONASCII)
    md.longDesc.set('long')
    md.url.set('http://x')
    md.language.set('C')
    th = trove.MetadataItem(md.freeze())
    assert th == md
    assert th.shortDesc() == 'short ' + NONASCII
    assert th.id() == b'\x01' * 20
