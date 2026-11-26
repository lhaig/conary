"""Bytes in, str metadata out: magic, javadeps, rpmhelper, cpio, logger,
xmllog and the file container."""
import bz2
import gzip
import io
import os
import struct
import tarfile
import termios
import tty

import pytest

from conary import rpmhelper
from conary.lib import cpiostream, javadeps, logger, magic, util, xmllog
from conary.repository import filecontainer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARCHIVE = os.path.join(ROOT, 'conary_test', 'archive')


def _tarBytes():
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode='w', format=tarfile.GNU_FORMAT) as t:
        info = tarfile.TarInfo('a')
        info.size = 3
        t.addfile(info, io.BytesIO(b'abc'))
    return buf.getvalue()


@pytest.mark.parametrize('name,data,cls,contents', [
    ('x.gz', gzip.compress(b'hello'), 'gzip', {'compression': '1'}),
    ('x.tgz', gzip.compress(_tarBytes()), 'tar_gz', {'GNU': True}),
    ('x.bz2', bz2.compress(b'hello'), 'bzip', {'compression': '9'}),
    ('x.tbz', bz2.compress(_tarBytes()), 'tar_bz2', {'GNU': True}),
    ('x.xz', b'\xfd7zXZ\x00' + b'\x00' * 20, 'xz', {}),
    ('x.tar', _tarBytes(), 'tar', {'GNU': True}),
    ('run.sh', b'#!/bin/sh -e\necho hi\n', 'script',
     {'interpreter': '/bin/sh', 'line': '/bin/sh -e'}),
    ('lt', b'#!/bin/sh\n# This wrapper script should never be moved out of '
     b'the build directory.\n# If it is, it will not operate correctly.\n',
     'ltwrapper', {}),
], ids=lambda v: v if isinstance(v, str) and len(v) < 9 else None)
def test_magic_types_and_str_contents(tmp_path, name, data, cls, contents):
    p = tmp_path / name
    p.write_bytes(data)
    m = magic.magic(str(p))
    assert type(m).__name__ == cls
    for key, val in contents.items():
        assert m.contents[key] == val
        assert type(m.contents[key]) is type(val)


def test_magic_gzip_name_is_str(tmp_path):
    p = tmp_path / 'named.gz'
    with open(str(p), 'wb') as f:
        with gzip.GzipFile('inner.txt', 'wb', fileobj=f) as g:
            g.write(b'hello')
    m = magic.magic(str(p))
    assert m.contents['name'] == 'inner.txt'


def test_magic_script_without_trailing_newline(tmp_path):
    p = tmp_path / 'r.sh'
    p.write_bytes(b'#!/bin/sh')
    assert magic.magic(str(p)).contents['line'] == '/bin/sh'


def test_magic_detects_others(tmp_path):
    cases = {
        'a.zip': (b'PK\x03\x04', None),
        'c.cs': (b'\xEA\x3F\x81\xBB' + b'\0' * 10, 'changeset'),
        'l.lzo': (b'\x89\x4c\x5a\x4f\x00\x0d\x0a\x1a\x0a' + b'\0' * 10, 'lzo'),
        'w.wim': (magic.WIM_MAGIC_STRING + b'\0' * 10, 'WIM'),
        'm.msi': (magic.MSI_MAGIC_STRINGS[0] + b'\0' * 10, 'MSI'),
    }
    for name, (data, cls) in cases.items():
        if cls is None:
            continue
        p = tmp_path / name
        p.write_bytes(data)
        assert type(magic.magic(str(p))).__name__ == cls


def test_magic_cil_and_class(tmp_path):
    dos = b'MZ' + b'\0' * 76 + b'This program cannot be run in DOS mode.'
    data = dos + b'\0' * (128 - len(dos)) + b'PE' + b'\0' * 10
    p = tmp_path / 'a.exe'
    p.write_bytes(data)
    assert type(magic.magic(str(p))).__name__ == 'CIL'
    m = magic.magic(os.path.join(ARCHIVE, 'Expr.class'))
    assert type(m).__name__ == 'java'


def test_magic_rpm_values_are_plain_str():
    m = magic.magic(os.path.join(ARCHIVE, 'aaa_first-1.0-1.noarch.rpm'))
    assert type(m).__name__ == 'RPM'
    assert m.contents['name'] == 'aaa_first'
    assert m.contents['version'] == '1.0'
    assert isinstance(m.contents['epoch'], (int, type(None)))


def test_magic_buffers_are_bytes_only():
    # The helper that slices names out of a header buffer works on bytes
    assert magic._string(b'name\0rest') == b'name'
    assert magic._string(b'noterminator') == b'noterminator'
    assert magic._line(b'#!/bin/sh\nrest') == b'#!/bin/sh'


def test_jar_deps_are_str():
    m = magic.magic(os.path.join(ARCHIVE, 'test-deps.jar'))
    assert type(m).__name__ == 'jar'
    for prov in m.contents['provides']:
        assert isinstance(prov, str)
    for req in m.contents['requires']:
        assert isinstance(req, str)
    assert m.contents['provides']


def test_javadeps_on_real_class():
    with open(os.path.join(ARCHIVE, 'Expr.class'), 'rb') as f:
        prov, req = javadeps.getDeps(f.read())
    assert isinstance(prov, str)
    assert req and all(isinstance(x, str) for x in req)
    assert prov in ('Expr', 'org.Expr') or prov.endswith('Expr')


def test_javadeps_pool_string_with_bad_utf8_does_not_raise():
    data = struct.pack('>H', 3) + b'\xff\xfe\x80'
    val, end = javadeps._javaSymbolTable._asUtf8(data, 0)
    assert isinstance(val, str)
    assert end == 5


def test_rpmhelper_header_types():
    with open(os.path.join(ARCHIVE, 'aaa_first-1.0-1.noarch.rpm'), 'rb') as f:
        h = rpmhelper.readHeader(f)
        assert h[rpmhelper.NAME] == 'aaa_first'
        assert isinstance(h[rpmhelper.NAME], str)
        assert h[rpmhelper.VERSION] == '1.0'
        assert isinstance(h.get(rpmhelper.SIG_MD5), bytes)
        assert isinstance(h[rpmhelper.BASENAMES], list)
        assert all(isinstance(x, str) for x in h[rpmhelper.BASENAMES])


def test_rpmhelper_decodes_non_utf8_names_losslessly():
    # a one-entry STRING header whose value is not valid utf-8
    value = b'bad\xff\x00'
    entry = struct.pack('!iiii', rpmhelper.NAME, 6, 0, 1)
    blob = struct.pack('!ii', 1, len(value)) + entry + value
    h = rpmhelper.headerFromBlob(blob)
    got = h[rpmhelper.NAME]
    assert isinstance(got, str)
    assert os.fsencode(got) == b'bad\xff'


def test_cpio_header_round_trip():
    raw = b'070701' + b''.join(b'%08x' % n for n in range(1, 14))
    hdr = cpiostream.CpioHeader(raw)
    assert hdr.magic == b'070701'
    assert hdr.inode == 1 and hdr.namesize == 12
    assert hdr.serialize() == raw


def _cpioEntry(name, data, mode=0o100644):
    nm = name.encode() + b'\0'
    fields = [1, mode, 0, 0, 1, 0, len(data), 0, 0, 0, 0, len(nm), 0]
    hdr = b'070701' + b''.join(b'%08x' % n for n in fields)
    out = hdr + nm
    out += b'\0' * (-len(out) % 4)
    out += data
    out += b'\0' * (-len(out) % 4)
    return out


def test_cpio_stream_filenames_are_str():
    arch = (_cpioEntry('./dir/f\xe9', b'hello') +
            _cpioEntry('TRAILER!!!', b'', mode=0))
    seen = []
    for ent in cpiostream.CpioStream(io.BytesIO(arch)):
        seen.append((ent.filename, ent.payload.read(), ent.payload.read()))
    assert seen == [('./dir/f\xe9', b'hello', b'')]


def test_cpio_extract_files(tmp_path):
    arch = (_cpioEntry('./a', b'AAA') + _cpioEntry('TRAILER!!!', b'', 0))
    res = rpmhelper.extractFilesFromCpio(io.BytesIO(arch), ['/a'],
                                         tmpDir=str(tmp_path))
    assert res[0].read() == b'AAA'


def test_logger_termios_cc_values_are_ints(monkeypatch):
    seen = []
    cc = [b'\x00'] * 32
    monkeypatch.setattr(termios, 'tcgetattr', lambda fd: [0, 0, 0, 0, 0, 0, cc])
    monkeypatch.setattr(termios, 'tcsetattr',
                        lambda fd, when, attrs: seen.append(attrs))
    monkeypatch.setattr(tty, 'setraw', lambda fd: None)

    class Fake:
        def fileno(self):
            return 7
    monkeypatch.setattr(logger.sys, 'stdout', Fake())
    monkeypatch.setattr(logger.sys, 'stderr', Fake())
    monkeypatch.setattr(logger.sys, 'stdin', Fake())
    monkeypatch.setattr(os, 'dup', lambda fd: 99)
    monkeypatch.setattr(os, 'dup2', lambda a, b: None)
    monkeypatch.setattr(os, 'close', lambda fd: None)
    lg = logger.Logger(withStdin=False)
    lg._becomeLogSlave(5, 1234)
    assert seen
    assert seen[0][6][termios.VTIME] == 0
    assert seen[0][6][termios.VMIN] == 1
    assert type(seen[0][6][termios.VMIN]) is int
    lg.logging = False      # no child to reap in __del__


@pytest.mark.parametrize('suffix,opener', [
    ('.log', lambda p: open(p, 'rb')),
    ('.log.gz', lambda p: gzip.GzipFile(p, 'rb')),
    ('.log.bz2', lambda p: bz2.BZ2File(p, 'rb')),
])
def test_open_path_writes_text_in_every_compression(tmp_path, suffix, opener):
    path = str(tmp_path / ('t' + suffix))
    f = logger.openPath(path)
    f.write('caf\xe9 test')
    f.flush()
    f.close()
    with opener(path) as r:
        assert r.read() == 'caf\xe9 test'.encode('utf-8')


@pytest.mark.parametrize('suffix', ['.xml', '.xml.gz', '.xml.bz2'])
def test_xmllog_handler_compressed(tmp_path, suffix):
    import logging
    path = str(tmp_path / ('log' + suffix))
    h = xmllog.XmlHandler(path)
    h.emit(logging.LogRecord('n', logging.INFO, 'p', 1, 'hello', (), None))
    h.close()
    opener = {'.xml': open, '.xml.gz': gzip.open, '.xml.bz2': bz2.open}[suffix]
    with opener(path, 'rb') as f:
        data = f.read()
    assert data.startswith(b'<?xml')
    assert b'hello' in data


def test_filecontainer_round_trip(tmp_path):
    from conary.repository import filecontents
    path = str(tmp_path / 'fc')
    f = util.ExtendedFile(path, 'w+', buffering=False)
    fc = filecontainer.FileContainer(f)
    fc.addFile(b'name1', filecontents.FromString(b'contents one'), b'tag1')
    fc.addFile(b'name2', filecontents.FromString(PAYLOAD_SMALL), b'tag2',
               precompressed=False)
    f.close()
    assert open(path, 'rb').read(4) == filecontainer.FILE_CONTAINER_MAGIC
    f = util.ExtendedFile(path, 'r', buffering=False)
    fc = filecontainer.FileContainer(f)
    name, tag, fobj = fc.getNextFile()
    assert (name, tag) == (b'name1', b'tag1')
    assert gzip.decompress(fobj.read()) == b'contents one'
    name, tag, fobj = fc.getNextFile()
    assert gzip.decompress(fobj.read()) == PAYLOAD_SMALL


PAYLOAD_SMALL = bytes(range(256)) * 3


def test_filecontainer_pack_file_header_is_bytes():
    header, footer = filecontainer.FileContainer._packFileHeader(
        b'n', b't', 5)
    assert isinstance(header, bytes) and footer == b''
    header, footer = filecontainer.FileContainer._packFileHeader(
        b'n', b't', 0x100000000)
    assert isinstance(header, bytes) and len(footer) == 4


# -- util file helpers changed for bytes ---------------------------------------

def test_line_reader_rejoins_split_utf8_and_escapes_bad_bytes():
    r, w = os.pipe()
    try:
        reader = util.LineReader(r)
        data = 'caf\u00e9\n'.encode('utf-8') + b'bad\xff\n'
        # split inside the two-byte UTF-8 sequence
        os.write(w, data[:4])
        got = reader.readlines()
        os.write(w, data[4:])
        got += reader.readlines()
        assert got == ['caf\u00e9\n', os.fsdecode(b'bad\xff\n')]
    finally:
        os.close(w)
        os.close(r)


@pytest.mark.parametrize('cls,compress', [
    ('BZ2File', bz2.compress),
    ('LZMAFile', None),
])
def test_compressed_file_reads_bytes(tmp_path, cls, compress):
    payload = bytes(range(256)) * 50
    if compress is None:
        import lzma
        compress = lzma.compress
    p = tmp_path / 'data'
    p.write_bytes(compress(payload))
    with open(str(p), 'rb') as f:
        obj = getattr(util, cls)(f)
        out = obj.read(1000)
        rest = obj.read(len(payload))
        while True:
            more = obj.read(len(payload))
            if not more:
                break
            rest += more
        if hasattr(obj, 'close'):
            obj.close()
    assert isinstance(out, bytes)
    assert out + rest == payload


def test_deterministic_gzip_has_zero_mtime(tmp_path):
    p = tmp_path / 'x.gz'
    with open(str(p), 'wb') as raw:
        g = util.DeterministicGzipFile(fileobj=raw, mode='wb')
        g.write(b'payload')
        g.close()
    data = p.read_bytes()
    assert data[4:8] == b'\0\0\0\0'
    assert gzip.decompress(data) == b'payload'
