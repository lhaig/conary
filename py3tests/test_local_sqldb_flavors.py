"""Empty flavors (NULL in the local Flavors table) thaw as Flavor()."""
import pytest

from conary import files, trove
from conary.deps import deps
from conary.errors import DatabasePathConflicts
from conary.lib.sha1helper import md5FromString
from conary.local import sqldb
from conary.versions import ThawVersion

V10 = ThawVersion("/conary.rpath.com@test:trunk/10:1.2-10")
X86 = deps.parseFlavor('is: x86')


@pytest.mark.parametrize('frz', [None, '', b''])
def test_thaw_flavor_empty(frz):
    f = deps.ThawFlavor(frz)
    assert f == deps.Flavor()
    assert f.isEmpty()


@pytest.mark.parametrize('conv', [str, lambda s: s.encode('ascii')])
def test_thaw_flavor_roundtrip(conv):
    assert deps.ThawFlavor(conv(X86.freeze())) == X86


@pytest.mark.parametrize('frz', ['is: x86é', 'is: x86é'.encode('utf-8')])
def test_thaw_flavor_non_ascii(frz):
    with pytest.raises(deps.ParseError):
        deps.ThawFlavor(frz)


def _addTrove(db, name, flavor, children=(), files_=()):
    trv = trove.Trove(name, V10, flavor, None)
    for (pathId, path, f) in files_:
        trv.addFile(pathId, path, V10, f.fileId())
    for child in children:
        trv.addTrove(*child)
    info = db.addTrove(trv)
    for (pathId, path, f) in files_:
        db.addFile(info, pathId, path, f.fileId(), V10,
                   fileStream=f.freeze())
    db.addTroveDone(info)
    return info[1]


@pytest.fixture
def db(tmp_path):
    d = sqldb.Database(str(tmp_path / 'db'))
    yield d
    d.close()


def test_local_db_flavors(db):
    empty = deps.Flavor()
    _addTrove(db, 'empty:runtime', empty)
    _addTrove(db, 'x86:runtime', X86)
    _addTrove(db, 'group-foo', empty,
              children=[('empty:runtime', V10, empty),
                        ('x86:runtime', V10, X86)])
    db.commit()

    assert list(db.iterVersionByName('empty:runtime', True)) == [(V10, empty)]
    got = list(db.iterVersionByName('x86:runtime', True))
    assert got == [(V10, X86)]

    kids = db.getTroveTroves([('group-foo', V10, empty)])[0]
    assert sorted(kids) == sorted([('empty:runtime', V10, empty),
                                   ('x86:runtime', V10, X86)])
    for (_, _, fl) in kids:
        assert isinstance(fl, deps.Flavor)


def test_check_path_conflicts_thaws_null_flavor(db, tmp_path):
    empty = deps.Flavor()
    p1 = tmp_path / 'a'
    p1.write_text('one')
    p2 = tmp_path / 'b'
    p2.write_text('two!')
    id1 = md5FromString("00010001000100010001000100010001")
    id2 = md5FromString("00010001000100010001000100010002")
    f1 = files.FileFromFilesystem(str(p1), id1)
    f2 = files.FileFromFilesystem(str(p2), id2)

    _addTrove(db, 'existing:runtime', empty, files_=[(id1, '/bin/x', f1)])
    db.commit()
    instId = _addTrove(db, 'added:runtime', X86,
                       files_=[(id2, '/bin/x', f2)])

    with pytest.raises(DatabasePathConflicts) as ei:
        db.checkPathConflicts([instId], lambda path: False, {})
    conflicts = ei.value.getConflicts()
    assert len(conflicts) == 1
    path, (eid, existing), (aid, addedInfo) = conflicts[0]
    assert path == '/bin/x'
    assert existing == ('existing:runtime', V10, empty)
    assert existing[2] == deps.Flavor()
    assert addedInfo == ('added:runtime', V10, X86)
