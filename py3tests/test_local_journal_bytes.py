"""JobJournal keeps paths as str above the stream layer and raw bytes on disk;
the rollback stack writes that revert hid are byte-correct."""
import os
import struct

from conary.local import database
from conary.local.journal import (JobJournal, JOURNAL_ENTRY_CREATE,
        JOURNAL_ENTRY_MKDIR, JOURNAL_ENTRY_RENAME)


class Warnings:
    def __init__(self):
        self.msgs = []

    def warning(self, fmt, *args):
        self.msgs.append(fmt % args)


def _write(path, data, mode=0o640, mtime=1000000000):
    with open(path, 'wb') as f:
        f.write(data)
    os.chmod(path, mode)
    os.utime(path, (mtime, mtime))


def test_revert_all_kinds(tmp_path):
    root = str(tmp_path)
    jpath = str(tmp_path / 'journal')
    _write(root + '/orig', b'original')
    _write(root + '/old', b'moved')
    j = JobJournal(jpath, root, create=True)
    j.backup(root + '/orig')
    # real updates replace the file, they do not write the backed-up inode
    _write(root + '/orig.tmp', b'changed', mode=0o600, mtime=1100000000)
    os.rename(root + '/orig.tmp', root + '/orig')
    j.rename(root + '/old', root + '/new')
    os.rename(root + '/old', root + '/new')
    j.create(root + '/made')
    _write(root + '/made', b'x')
    j.mkdir(root + '/dir')
    os.mkdir(root + '/dir')
    j.close()

    warn = Warnings()
    JobJournal(jpath, root, callback=warn).revert()
    assert warn.msgs == []
    assert open(root + '/orig', 'rb').read() == b'original'
    st = os.stat(root + '/orig')
    assert st.st_mode & 0o7777 == 0o640
    assert int(st.st_mtime) == 1000000000
    assert open(root + '/old', 'rb').read() == b'moved'
    assert not os.path.exists(root + '/new')
    assert not os.path.exists(root + '/made')
    assert not os.path.exists(root + '/dir')
    # no leftover backup links
    assert sorted(os.listdir(root)) == ['journal', 'old', 'orig']


def test_non_utf8_roundtrip(tmp_path):
    root = str(tmp_path)
    jpath = str(tmp_path / 'journal')
    name = os.fsdecode(b'caf\xe9')
    j = JobJournal(jpath, root, create=True)
    j.create(root + '/' + name)
    _write(root + '/' + name, b'x')
    j.close()
    entries = list(JobJournal(jpath, root))
    assert entries[0][1].new() == '/' + name
    assert isinstance(entries[0][1].new(), str)
    JobJournal(jpath, root).revert()
    assert not os.path.exists(os.fsencode(root) + b'/caf\xe9')


def test_iteration_reverse_order_str(tmp_path):
    root = str(tmp_path)
    jpath = str(tmp_path / 'journal')
    j = JobJournal(jpath, root, create=True)
    j.rename(root + '/a', root + '/b')
    j.create(root + '/c')
    j.mkdir(root + '/d')
    j.close()
    got = [(k, e.old(), e.new()) for k, e in JobJournal(jpath, root)]
    assert got == [(JOURNAL_ENTRY_MKDIR, '', '/d'),
                   (JOURNAL_ENTRY_CREATE, '', '/c'),
                   (JOURNAL_ENTRY_RENAME, '/a', '/b')]


def test_commit_and_remove(tmp_path):
    root = str(tmp_path)
    jpath = str(tmp_path / 'journal')
    _write(root + '/f', b'data')
    os.mkdir(root + '/empty')
    os.mkdir(root + '/full')
    _write(root + '/full/x', b'')
    j = JobJournal(jpath, root, create=True)
    j.backup(root + '/f')
    assert any('.ct' in n for n in os.listdir(root))
    j.tryCleanupDir(root + '/empty')
    j.tryCleanupDir(root + '/full')
    j.close()
    j = JobJournal(jpath, root)
    j.commit()
    assert not any('.ct' in n for n in os.listdir(root))
    assert not os.path.exists(root + '/empty')
    assert os.path.isdir(root + '/full')
    assert os.path.exists(root + '/f')
    j.removeJournal()
    assert not os.path.exists(jpath)


def test_failed_revert_warns_with_str(tmp_path):
    root = str(tmp_path)
    jpath = str(tmp_path / 'journal')
    j = JobJournal(jpath, root, create=True)
    j.rename(root + '/gone', root + '/missing')
    j.close()
    warn = Warnings()
    JobJournal(jpath, root, callback=warn).revert()
    assert len(warn.msgs) == 1
    assert warn.msgs[0].startswith('could not restore file %s/missing: ' % root)


def _frz(old, new):
    # StreamSet wire layout for DYNAMIC streams: tag(B) size(H) data
    out = b''
    if old:
        out += struct.pack('!BH', 1, len(old)) + old
    if new:
        out += struct.pack('!BH', 2, len(new)) + new
    return out


def test_on_disk_format(tmp_path):
    jpath = str(tmp_path / 'journal')
    j = JobJournal(jpath, '/r', create=True)
    j.rename('/r/a', '/r/b')
    j.create('/r/c')
    j.mkdir('/r/d')
    j.create('/r/' + os.fsdecode(b'caf\xe9'))
    j.close()
    expected = struct.pack('!H', 1)
    for kind, old, new in [(0, b'/a', b'/b'), (2, b'', b'/c'),
                           (4, b'', b'/d'), (2, b'', b'/caf\xe9')]:
        frz = _frz(old, new)
        expected += frz + struct.pack('!BH', kind, len(frz))
    data = open(jpath, 'rb').read()
    assert data == expected
    assert b'caf\xe9' in data


def test_rollback_stack_writes(tmp_path):
    d = str(tmp_path / 'rb')
    os.mkdir(d)
    jpath = str(tmp_path / 'journal')
    j = JobJournal(jpath, str(tmp_path), create=True)
    stack = database.RollbackStack(d, str(tmp_path), None, None)
    rb = stack.new(j)
    j.close()
    assert open(d + '/status', 'rb').read() == b'0 0\n'
    again = database.RollbackStack(d, str(tmp_path), None, None)
    assert (again.first, again.last) == (0, 0)

    class Cs:
        def __init__(self, data):
            self.data = data

        def writeToFile(self, path, mode=0o600):
            with open(path, 'wb') as f:
                f.write(self.data)

    j = JobJournal(str(tmp_path / 'journal2'), str(tmp_path), create=True)
    rb.add(j, Cs(b'r'), Cs(b'l'), None)
    j.close()
    assert open(rb.dir + '/count', 'rb').read() == b'1\n'


def test_rollback_new_saves_system_model(tmp_path):
    class Model:
        def modified(self):
            return False

    class ModelFile:
        model = Model()

        def read(self):
            return ['install foo=\u00e9\n', 'x\n'], None

    d = str(tmp_path / 'rb')
    j = JobJournal(str(tmp_path / 'journal'), str(tmp_path), create=True)
    stack = database.RollbackStack(d, str(tmp_path), None, ModelFile())
    rb = stack.new(j)
    j.close()
    got = open(rb.dir + '/system-model', 'rb').read()
    assert got == 'install foo=\u00e9\nx\n'.encode('utf-8')
