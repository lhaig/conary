"""Tests that the C/Cython extensions in conary/lib/ext are built for
Python 3 and behave sanely."""
import hashlib
import importlib
import importlib.util
import os
import subprocess
import sys
import zlib

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXTDIR = os.path.join(ROOT, 'conary', 'lib', 'ext')

MODULES = ['dep_freeze', 'digest_uncompress', 'pack', 'streams',
           'file_utils', 'sha256_nonstandard', 'system']


def _load(name):
    """Load the compiled extension directly from its .so, bypassing the
    conary package (whose __init__ may not import under Python 3 yet)."""
    mod = sys.modules.get('_ext_test_' + name)
    if mod is not None:
        return mod
    so = os.path.join(EXTDIR, name + '.so')
    assert os.path.exists(so), "%s has not been built" % so
    spec = importlib.util.spec_from_file_location(name, so)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    sys.modules['_ext_test_' + name] = mod
    return mod


@pytest.mark.parametrize('name', MODULES)
def test_compiled_module(name):
    mod = _load(name)
    assert mod.__file__.endswith('.so')


@pytest.mark.parametrize('name', MODULES)
def test_preferred_over_fallback(name):
    """Normal package import must pick the .so over the .py fallback."""
    spec = importlib.machinery.PathFinder.find_spec(
        name, [EXTDIR])
    assert spec.origin.endswith('.so')


def test_constants_generated():
    path = os.path.join(ROOT, 'conary', 'constants.py')
    assert os.path.exists(path)
    ns = {}
    with open(path) as f:
        exec(f.read(), ns)
    assert ns['version'] == '2.5.9'


def test_fopenIfExists(tmp_path):
    fu = _load('file_utils')
    p = tmp_path / 'a.txt'
    p.write_text('hello')
    f = fu.fopenIfExists(str(p), 'r')
    assert f is not None
    assert f.read() == 'hello'
    f.close()
    f = fu.fopenIfExists(str(p).encode(), 'rb')
    assert f.read() == b'hello'
    f.close()
    assert fu.fopenIfExists(str(tmp_path / 'missing'), 'r') is None


def test_path_functions(tmp_path):
    fu = _load('file_utils')
    d = str(tmp_path / 'sub')
    assert fu.lexists(d) is False
    assert fu.mkdirIfMissing(d) is True
    assert fu.mkdirIfMissing(d) is False
    assert fu.lexists(d) is True
    assert fu.lexists(d.encode()) is True
    f = str(tmp_path / 'f')
    open(f, 'w').close()
    assert fu.removeIfExists(f) is True
    assert fu.removeIfExists(f) is False
    assert not os.path.exists(f)


def test_pread_pwrite(tmp_path):
    fu = _load('file_utils')
    with open(tmp_path / 'x', 'w+b') as f:
        assert fu.pwrite(f, b'abcdef', 2) == 6
        assert fu.pread(f, 4, 3) == b'bcde'


def test_system_loads():
    sysmod = _load('system')
    assert sysmod.__file__.endswith('.so')


def test_sha256_nonstandard():
    import ctypes
    mod = _load('sha256_nonstandard')
    data = b'abc'
    out = mod.digest(data)
    assert isinstance(out, bytes) and len(out) == 32
    # same helper through ctypes (what the pure-Python fallback does)
    helper = ctypes.CDLL(os.path.join(EXTDIR, 'helper_sha256_nonstandard.so'))
    buf = ctypes.create_string_buffer(32)
    helper.sha256ns_digest(data, len(data), buf)
    assert buf.raw == out
    assert out == hashlib.sha256(data).digest()  # identical for short ASCII input


def test_digest_uncompress(tmp_path):
    import gzip
    mod = _load('digest_uncompress')
    data = b'some data to compress' * 100
    comp = gzip.compress(data)
    p = tmp_path / 'c'
    p.write_bytes(b'xx' + comp)
    expected = hashlib.sha1(data).digest()
    fd = os.open(str(p), os.O_RDONLY)
    try:
        ofd = os.open(str(tmp_path / 'o'), os.O_WRONLY | os.O_CREAT)
        try:
            assert mod.sha1Copy((fd, 2, len(comp)), [ofd]) == expected
        finally:
            os.close(ofd)
        assert (tmp_path / 'o').read_bytes() == comp
        sha, path = mod.sha1Uncompress(fd, 2, len(comp), str(tmp_path),
                                       'base')
        assert sha == expected
        assert open(path, 'rb').read() == data
    finally:
        os.close(fd)


def test_pack_roundtrip():
    # The C module works on bytes (format and data), unlike the str-based
    # pure-Python fallback.
    mod = _load('pack')
    packed = mod.pack(b'!BSI', 1, b'abc')
    assert packed == b'\x01\x00\x00\x00\x03abc'
    off, vals = mod.unpack(b'!BSI', 0, packed)
    assert (off, list(vals)) == (8, [1, b'abc'])
    packed = mod.pack(b'!SH', b'hello')
    assert packed == b'\x00\x05hello'
    off, vals = mod.unpack(b'!SH', 0, packed)
    assert list(vals) == [b'hello']


def test_dep_freeze_split():
    mod = _load('dep_freeze')
    assert mod.depSplit(b'foo:~bar:baz') == (b'foo', [b'~bar', b'baz'])


@pytest.mark.xfail(strict=True, reason="depSetSplit builds its frozen "
        "element with s# so it returns str while depSplit returns bytes; "
        "bytes/str semantics are out of scope for the build task")
def test_dep_set_split_bytes():
    mod = _load('dep_freeze')
    nxt, tag, frozen = mod.depSetSplit(0, b'4#foo:bar|5#baz')
    assert (nxt, tag, frozen) == (10, 4, b'foo:bar')


def test_streams_freeze_thaw_compare():
    cs = _load('streams')
    a = cs.IntStream(5)
    b = cs.IntStream(5)
    c = cs.IntStream(6)
    assert a == b
    assert not (a != b)
    assert a != c
    assert a < c and c > a and a <= b and a >= b
    thawed = cs.IntStream(a.freeze())
    assert thawed == a
    s = cs.StringStream(b'abc')
    s2 = cs.StringStream()
    s2.thaw(s.freeze())
    assert s2 == s
    assert s2 != cs.StringStream(b'abd')
    assert s2 < cs.StringStream(b'abd')
    # a value with an embedded length forces the s# parse path
    assert cs.StringStream(s.freeze()) == s
