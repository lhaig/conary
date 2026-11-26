import hashlib
import os

import pytest

from conary.lib import sha1helper

# Known digests of b'abc'.
SHA1_ABC = 'a9993e364706816aba3e25717850c26c9cd0d89d'
MD5_ABC = '900150983cd24fb0d6963f7d28e17f72'
SHA256_ABC = 'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad'

HELPERS = [
    (sha1helper.sha1String, lambda b: hashlib.sha1(b).digest()),
    (sha1helper.md5String, lambda b: hashlib.md5(b).digest()),
]


@pytest.mark.parametrize('helper,hexdigest', [
    (sha1helper.sha1String, SHA1_ABC),
    (sha1helper.md5String, MD5_ABC),
])
def test_bytes_known_digest(helper, hexdigest):
    assert helper(b'abc').hex() == hexdigest


@pytest.mark.parametrize('helper,ref', HELPERS)
def test_bytes_matches_hashlib(helper, ref):
    assert helper(b'\xff\x00data') == ref(b'\xff\x00data')


def test_nonstandard_sha256_known_vector():
    # The nonstandard variant only differs from SHA-256 on longer inputs;
    # for a short message it must give the standard digest.
    out = sha1helper.nonstandardSha256String(b'abc')
    assert out.hex() == SHA256_ABC


ALL_HELPERS = [sha1helper.sha1String, sha1helper.md5String,
               sha1helper.nonstandardSha256String]


@pytest.mark.parametrize('helper', ALL_HELPERS)
@pytest.mark.parametrize('text', ['abc', 'café', '', 'a\0b'])
def test_str_is_utf8_encoded(helper, text):
    assert helper(text) == helper(text.encode('utf-8'))


@pytest.mark.parametrize('helper', ALL_HELPERS)
def test_surrogateescape_matches_disk_bytes(helper):
    assert helper(os.fsdecode(b'\xff')) == helper(b'\xff')


@pytest.mark.parametrize('helper', ALL_HELPERS)
@pytest.mark.parametrize('bad', [1, None, 1.5, ['a']])
def test_other_types_raise(helper, bad):
    with pytest.raises(TypeError):
        helper(bad)


def test_bytearray_and_memoryview_accepted():
    want = sha1helper.sha1String(b'abc')
    assert sha1helper.sha1String(bytearray(b'abc')) == want
    assert sha1helper.sha1String(memoryview(b'abc')) == want


def test_sha1_empty_is_bytes():
    assert isinstance(sha1helper.sha1Empty, bytes)
    assert sha1helper.sha1Empty == sha1helper.sha1String(b'')


def test_rule_documented():
    assert 'surrogateescape' in sha1helper.__doc__


# Other layers share the same encode rule through sha1helper.toBytes.
def test_fromstring_holds_bytes():
    from conary.repository import filecontents
    for given, want in [('v1 2', b'v1 2'), (b'\xffraw', b'\xffraw'),
                        ('café', 'café'.encode('utf-8'))]:
        fc = filecontents.FromString(given)
        assert fc.get().read() == want
        assert fc == given and fc == want
        assert fc.copy() == fc
    assert filecontents.FromString('a') != 'b'


def test_fingerprint_mixes_text_and_bytes():
    import base64
    from conary.repository.netrepos import fingerprints
    tup = ('foo:runtime', '/localhost@rpl:1/1-1-1', 'is: x86_64')
    assert fingerprints._troveFp(tup, None, None) == sha1helper.sha1String(
        b'\0'.join(x.encode() for x in tup))
    sig = base64.encodebytes(b'\x00sig\xff')
    # the signature block may come back from the database as text
    for block in (sig, sig.decode('ascii')):
        assert fingerprints._troveFp(tup, (1, block), (0, None)) == \
            sha1helper.sha1String(b'\x00sig\xff')
    assert fingerprints._troveFp(tup, (0, None), (0, None)) == \
        sha1helper.sha1String(b'\0'.join([b'missing'] +
                                          [x.encode() for x in tup]))
