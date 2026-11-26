"""file() became open(): binary data must survive, text stays text."""
import gzip
import hashlib
import os

import pytest

from conary.lib import javadeps, logger, logparse, magic, util
from conary.lib.ext import digest_uncompress

PAYLOAD = bytes(range(256)) * 40 + b'\xff\xfe\x00tail'


def test_sha1_copy_binary_round_trip(tmp_path):
    comp = gzip.compress(PAYLOAD)
    src = tmp_path / 'src.bin'
    # pad so the compressed stream does not start at offset 0
    src.write_bytes(b'JUNKJUNK' + comp + b'TRAILER')
    out = tmp_path / 'out.bin'
    fd = os.open(str(src), os.O_RDONLY)
    outFd = os.open(str(out), os.O_WRONLY | os.O_CREAT, 0o600)
    try:
        digest = digest_uncompress.sha1Copy((fd, 8, len(comp)), [outFd])
    finally:
        os.close(fd)
        os.close(outFd)
    assert digest == hashlib.sha1(PAYLOAD).digest()
    assert out.read_bytes() == comp


def test_magic_reads_binary_files(tmp_path):
    p = tmp_path / 'data.gz'
    p.write_bytes(gzip.compress(PAYLOAD))
    # Binary content must be readable (a text mode open() would raise
    # UnicodeDecodeError on the 0x8b byte); sniffing the bytes against the
    # str signatures in magic.py is a separate bytes/str port item.
    magic.magic(str(p))

    elf = tmp_path / 'x.elf'
    elf.write_bytes(b'\x7fELF' + b'\x00' * 60)
    # the ELF reader may reject the stub, but opening and sniffing must
    # not raise a decode error
    magic.magic(str(elf))

    junk = tmp_path / 'junk'
    junk.write_bytes(b'\xff\xfe\xfd' * 2000)
    assert magic.magic(str(junk)) is None


def test_javadeps_main_reads_bytes(tmp_path):
    cls = tmp_path / 'A.class'
    cls.write_bytes(b'\xca\xfe\xba\xbe\x00\x00\x00\x34' + b'\x00' * 8)
    with open(str(cls), 'rb') as f:
        # Reading bytes must not raise; an empty string pool yields no deps.
        assert javadeps.getDeps(f.read()) == (None, None)


# magic.py and javadeps.py now read bytes but still compare against str
# signatures, so detection silently fails. These encode the correct
# behaviour and flip to passing when the signatures become bytes.
@pytest.mark.xfail(strict=True, reason='magic.py compares bytes to str signatures')
@pytest.mark.parametrize('name,data,cls', [
    ('data.gz', gzip.compress(PAYLOAD), 'gzip'),
    ('run.sh', b'#!/bin/sh\necho hi\n', 'script'),
], ids=['gzip', 'script'])
def test_magic_detects_type(tmp_path, name, data, cls):
    p = tmp_path / name
    p.write_bytes(data)
    assert isinstance(magic.magic(str(p)), getattr(magic, cls))


@pytest.mark.xfail(strict=True, reason='javadeps.py compares bytes to a str magic')
def test_javadeps_recognises_class_magic():
    # Valid magic with an empty pool must fail on the pool, not the magic.
    data = b'\xca\xfe\xba\xbe\x00\x00\x00\x34' + b'\x00' * 8
    with pytest.raises(ValueError, match='no string pool'):
        javadeps._parseSymbolTable(data)


def test_bounded_stringio_spills_to_file_and_keeps_writing():
    b = util.BoundedStringIO(maxMemorySize=16)
    b.write('x' * 10)
    assert b._backendType == 'memory'
    b.write('y' * 30)           # spills to a temporary file
    assert b._backendType == 'file'
    b.write('z' * 5)            # the file backend branch of _writeImpl
    b.seek(0)
    assert b.read() == 'x' * 10 + 'y' * 30 + 'z' * 5
    b.seek(5)
    b.truncate(8)               # the file backend branch of _truncateImpl
    b.seek(0)
    assert b.read() == 'x' * 8


def test_bounded_stringio_truncate_memory_backend():
    b = util.BoundedStringIO('hello world')
    b.truncate(5)
    b.seek(0)
    assert b.read() == 'hello'


def test_logparse_reads_text(tmp_path):
    p = tmp_path / 'conary.log'
    p.write_text('2020-01-01 one\n  two  \n', encoding='utf-8')
    assert logparse.getConaryLogLineList(str(p)) == [
        '2020-01-01 one', 'two']


def test_log_sync_file_seeks_from_end_in_binary(tmp_path):
    # SubscriptionLogWriter.synchronize() does seek(-n, 2), which only works
    # on a binary file object in Python 3
    p = tmp_path / 'sync.log'
    p.write_text('line\n1234.5678\n')
    with open(str(p), 'rb') as f:
        f.seek(-(len('1234.5678') + 1), 2)
        assert f.read(len('1234.5678')) == '1234.5678'.encode()
    src = open(logger.__file__).read()
    assert "syncFile = open(self.syncPath, 'rb')" in src
    assert 'timestamp.encode()' in src


def test_pickle_in_status_file_is_read_as_bytes(tmp_path):
    import inspect
    from conary.repository.netrepos import netserver
    src = inspect.getsource(netserver)
    assert "buf = open(path, 'rb').read()" in src
