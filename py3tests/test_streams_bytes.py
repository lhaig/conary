"""bytes/str rule at the stream and pack C boundary.

Frozen/wire data is bytes; StreamSet tag names and pack formats are str;
StringStream holds bytes (str is UTF-8 encoded on the way in); deps and
flavor streams keep their text freeze() but thaw bytes or str.
"""
import importlib.util
import os

import pytest

from conary import streams, versions
from conary.deps import deps
from conary.lib.ext import pack as cpack

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXTDIR = os.path.join(ROOT, 'conary', 'lib', 'ext')


def _load_fallback(name):
    spec = importlib.util.spec_from_file_location(
        '_fallback_' + name, os.path.join(EXTDIR, name + '.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(params=['c', 'py'])
def packmod(request):
    if request.param == 'c':
        assert cpack.__file__.endswith('.so')
        return cpack
    return _load_fallback('pack')


# ---------------------------------------------------------------- pack

PACK_CASES = [
    ('!BSH', (7, b'abc'), b'\x07\x00\x03abc'),
    ('!SI', (b'\xff\xfe',), b'\x00\x00\x00\x02\xff\xfe'),
    ('!S3B', (b'xyz', 1), b'xyz\x01'),
]


@pytest.mark.parametrize('fmt, args, expected', PACK_CASES)
def test_pack_str_format_bytes_data(packmod, fmt, args, expected):
    out = packmod.pack(fmt, *args)
    assert isinstance(out, bytes)
    assert out == expected


UNPACK_CASES = [
    ('!BSH', b'\x07\x00\x03abc', [7, b'abc']),
    ('!SI', b'\x00\x00\x00\x02\xff\xfe', [b'\xff\xfe']),
    ('!S3B', b'xyz\x01', [b'xyz', 1]),
    ('!D', b'\x02\xff\xfe', [b'\xff\xfe']),
]


@pytest.mark.parametrize('fmt, data, expected', UNPACK_CASES)
def test_unpack_str_format_bytes_data(packmod, fmt, data, expected):
    end, vals = packmod.unpack(fmt, 0, data)
    assert end == len(data)
    assert list(vals) == expected
    for v in vals:
        assert isinstance(v, (int, bytes))


def test_pack_dynamic_size(packmod):
    for size in (3, 200, 20000):
        sz = packmod.dynamicSize(size)
        assert isinstance(sz, bytes)
        data = sz + b'\xff' * size
        end, (val,) = packmod.unpack('!D', 0, data)
        assert end == len(data)
        assert val == b'\xff' * size


def test_pack_bytes_format_rejected(packmod):
    with pytest.raises(TypeError):
        packmod.pack(b'!BSH', 1, b'a')
    with pytest.raises(TypeError):
        packmod.unpack(b'!B', 0, b'\x01')


def test_pack_str_data_rejected(packmod):
    with pytest.raises(TypeError):
        packmod.pack('!SH', 'abc')
    with pytest.raises(TypeError):
        packmod.unpack('!B', 0, '\x01')


# ------------------------------------------------- StringStream & friends

def test_stringstream_str_is_utf8_bytes():
    assert streams.StringStream('abc')() == b'abc'
    s = streams.StringStream()
    s.set('naïve')
    assert s() == 'naïve'.encode('utf-8')
    assert streams.StringStream('naïve') == s


BYTES_STREAMS = [
    (streams.StringStream, b'\xff\x00\xfe binary'),
    (streams.Sha1Stream, b'\xff' * 20),
    (streams.AbsoluteSha1Stream, b'\xfe' * 20),
    (streams.Md5Stream, b'\xff' * 16),
    (streams.NonStandardSha256Stream, b'\xfd' * 32),
]


@pytest.mark.parametrize('cls, value', BYTES_STREAMS)
def test_bytes_stream_roundtrip(cls, value):
    s = cls()
    s.set(value)
    frozen = s.freeze()
    assert isinstance(frozen, bytes)
    assert frozen == value
    t = cls()
    t.thaw(frozen)
    assert t == s
    assert cls(frozen) == s
    assert t() == value


NUMERIC = [
    (streams.IntStream, 0x12345678),
    (streams.ShortStream, -5),
    (streams.ByteStream, 200),
    (streams.LongLongStream, 2 ** 40 + 3),
]


@pytest.mark.parametrize('cls, value', NUMERIC)
def test_numeric_roundtrip(cls, value):
    s = cls(value)
    frozen = s.freeze()
    assert isinstance(frozen, bytes)
    assert cls(frozen) == s
    t = cls()
    t.thaw(frozen)
    assert t() == value
    with pytest.raises(TypeError):
        cls().thaw('abcd')


def test_numeric_empty_freeze_is_bytes():
    assert streams.IntStream().freeze() == b''


VER = '/localhost@rpl:linux/1.0-1-1'


def _frozen_version():
    v = versions.VersionFromString(VER)
    v.resetTimeStamps(1234567890.0)
    return v


def test_frozen_version_stream():
    s = streams.FrozenVersionStream()
    s.set(_frozen_version())
    frozen = s.freeze()
    assert isinstance(frozen, bytes)
    assert streams.FrozenVersionStream(frozen) == s
    assert streams.FrozenVersionStream().freeze() == b''


def test_string_version_stream():
    s = streams.StringVersionStream()
    s.set(versions.VersionFromString(VER))
    frozen = s.freeze()
    assert frozen == VER.encode('ascii')
    assert streams.StringVersionStream(frozen) == s
    assert streams.StringVersionStream().freeze() == b''


def test_strings_stream():
    s = streams.StringsStream()
    s.set('b')
    s.set('a')
    frozen = s.freeze()
    assert frozen == b'a\0b'
    t = streams.StringsStream(frozen)
    assert list(t) == ['a', 'b']
    assert t == s
    assert streams.StringsStream().freeze() == b''
    u = streams.OrderedStringsStream()
    u.set('z')
    u.set('a')
    assert u.freeze() == b'z\0a'
    assert list(streams.OrderedStringsStream(u.freeze())) == ['z', 'a']


def test_ordered_binary_strings_stream():
    s = streams.OrderedBinaryStringsStream()
    s.set(b'\xff\x00')
    s.set(b'x' * 100)
    frozen = s.freeze()
    assert isinstance(frozen, bytes)
    t = streams.OrderedBinaryStringsStream(frozen)
    assert list(t) == [b'\xff\x00', b'x' * 100]
    assert streams.OrderedBinaryStringsStream().freeze() == b''


def test_optional_flavor_stream():
    none = streams.OptionalFlavorStream()
    none.set(None)
    assert none.freeze() == b'\0'
    assert streams.OptionalFlavorStream(b'\0').deps is None
    flv = deps.parseFlavor('is: x86')
    s = streams.OptionalFlavorStream()
    s.set(flv)
    frozen = s.freeze()
    assert isinstance(frozen, bytes)
    t = streams.OptionalFlavorStream(frozen)
    assert t == s
    assert t.deps.freeze() == flv.freeze()
    t.twm(b'\0', s)
    assert t.deps is None


def test_referenced_trove_list():
    flv = deps.parseFlavor('is: x86')
    v = _frozen_version()
    s = streams.ReferencedTroveList()
    s.append(('foo:runtime', v, flv))
    s.append(('bar', v, deps.Flavor()))
    frozen = s.freeze()
    assert isinstance(frozen, bytes)
    t = streams.ReferencedTroveList(frozen)
    assert [x[0] for x in t] == ['foo:runtime', 'bar']
    assert t[0][1] == v
    assert t[0][2] == flv
    assert streams.ReferencedTroveList().freeze() == b''


def test_deps_streams_text_freeze_bytes_thaw():
    flv = deps.parseFlavor('is: x86 x86_64')
    fs = streams.FlavorsStream()
    fs.set(flv)
    frozen = fs.freeze()
    assert isinstance(frozen, str)
    for form in (frozen, frozen.encode('utf-8')):
        t = streams.FlavorsStream()
        t.thaw(form)
        assert t == fs
        assert streams.FlavorsStream(form) == fs
    dset = deps.DependencySet()
    dset.addDep(deps.TroveDependencies, deps.Dependency('foo:runtime'))
    ds = streams.DependenciesStream()
    ds.set(dset)
    frozen = ds.freeze()
    assert isinstance(frozen, str)
    assert streams.DependenciesStream(frozen.encode('utf-8')) == ds


class _Coll(streams.StreamCollection):
    streamDict = {1: streams.StringStream, 2: streams.IntStream}


def test_stream_collection_bytes():
    c = _Coll()
    c.addStream(1, streams.StringStream(b'\xff\xfe'))
    c.addStream(2, streams.IntStream(7))
    frozen = c.freeze()
    assert isinstance(frozen, bytes)
    assert _Coll(frozen) == c
    base = _Coll(frozen)
    c.addStream(1, streams.StringStream(b'new'))
    diff = c.diff(base)
    assert isinstance(diff, bytes)
    assert base.diff(base) is None
    base.twm(diff, _Coll(frozen))
    assert base == c


class _Ordered(streams.OrderedStreamCollection):
    streamDict = {1: streams.StringStream}


def test_ordered_stream_collection_bytes():
    c = _Ordered()
    c.addStream(1, streams.StringStream(b'\xff'))
    c.addStream(1, streams.StringStream(b'abc'))
    frozen = c.freeze()
    assert isinstance(frozen, bytes)
    assert [x() for x in _Ordered(frozen).getStreams(1)] == [b'\xff', b'abc']
    sc = streams.StringOrderedStreamCollection()
    sc.append('hello')
    assert list(sc) == [b'hello']


# ------------------------------------------------------------- StreamSet

class Inner(streams.StreamSet):
    streamDict = {
        1: (streams.SMALL, streams.IntStream, 'num'),
        2: (streams.SMALL, streams.StringStream, 'blob'),
    }


class Outer(streams.StreamSet):
    streamDict = {
        1: (streams.SMALL, streams.StringStream, 'name'),
        2: (streams.SMALL, streams.IntStream, 'size'),
        3: (streams.SMALL, streams.Sha1Stream, 'sha1'),
        4: (streams.SMALL, streams.FlavorsStream, 'flavor'),
        5: (streams.SMALL, streams.DependenciesStream, 'requires'),
        6: (streams.DYNAMIC, Inner, 'inner'),
        7: (streams.SMALL, streams.FrozenVersionStream, 'version'),
        8: (streams.SMALL, streams.StringsStream, 'tags'),
    }


def _populated():
    o = Outer()
    o.name.set(b'\xff\xfebinary')
    o.size.set(1234)
    o.sha1.set(b'\xff' * 20)
    o.flavor.set(deps.parseFlavor('is: x86'))
    dset = deps.DependencySet()
    dset.addDep(deps.TroveDependencies, deps.Dependency('foo:runtime'))
    o.requires.set(dset)
    o.inner.num.set(9)
    o.inner.blob.set(b'\x80\x81')
    o.version.set(_frozen_version())
    o.tags.set('x')
    o.tags.set('y')
    return o


def test_streamset_subclass_roundtrip():
    o = _populated()
    frozen = o.freeze()
    assert isinstance(frozen, bytes)
    t = Outer(frozen)
    assert t == o
    assert t.name() == b'\xff\xfebinary'
    assert t.sha1() == b'\xff' * 20
    assert t.inner.blob() == b'\x80\x81'
    assert list(t.tags()) == ['x', 'y']
    assert t.version() == o.version()
    u = Outer()
    u.thaw(frozen)
    assert u == o
    assert Outer(frozen, 0) == o
    assert Outer.find(1, frozen)() == b'\xff\xfebinary'
    assert Outer.find(2, frozen)() == 1234
    assert Inner().freeze() == b''
    t.size.set(1)
    assert t != o


def test_streamset_attribute_names_are_str():
    o = Outer()
    assert o.name.__class__ is streams.StringStream
    assert getattr(o, 'sha1').__class__ is streams.Sha1Stream


def test_streamset_diff_twm():
    base = _populated()
    target = Outer(base.freeze())
    target.size.set(99)
    target.sha1.set(b'\xfe' * 20)
    target.inner.num.set(10)
    diff = target.diff(base)
    assert isinstance(diff, bytes)
    merged = Outer(base.freeze())
    assert merged.twm(diff, base) is None
    assert merged == target
    assert merged.sha1() == b'\xfe' * 20


def test_streamset_twm_conflict_detected():
    base = _populated()
    a = Outer(base.freeze())
    a.size.set(2)
    b = Outer(base.freeze())
    b.size.set(3)
    # StreamSet.twm does not report conflicts; the member streams do
    assert b.size.twm(a.size.diff(base.size), base.size)


class Keep(streams.StreamSet):
    ignoreUnknown = streams.PRESERVE_UNKNOWN
    streamDict = {1: (streams.SMALL, streams.IntStream, 'num')}


def test_streamset_preserve_unknown():
    frozen = b'\x01\x00\x04\x00\x00\x00\x05' + b'\x09\x00\x02\xff\xfe'
    k = Keep(frozen)
    assert k.num() == 5
    assert k.freeze() == frozen


def test_streamset_thaw_rejects_str():
    with pytest.raises(TypeError):
        Outer('abc')


# ------------------------------------------- pure Python streams fallback

def test_fallback_streams_follow_the_rule():
    fb = _load_fallback('streams')

    class Pair(fb.StreamSet):
        streamDict = {
            1: (fb.SMALL, fb.StringStream, 'blob'),
            2: (fb.SMALL, fb.IntStream, 'num'),
        }

    p = Pair()
    p.blob.set(b'\xff\x00')
    p.num.set(5)
    frozen = p.freeze()
    assert isinstance(frozen, bytes)
    assert Pair(frozen) == p
    assert fb.StringStream('abc')() == b'abc'
    assert fb.IntStream().freeze() == b''
    q = Pair(frozen)
    q.num.set(6)
    diff = q.diff(p)
    assert isinstance(diff, bytes)
    r = Pair(frozen)
    r.twm(diff, p)
    assert r == q
