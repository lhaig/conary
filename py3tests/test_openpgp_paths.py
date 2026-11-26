"""
OpenPGP paths that conary_test/libtest/openpgptest.py cannot cover without
the repository harness, or that the archive keys can exercise directly:
key caches (keyring and disk callbacks), the S2K functions with MD5 and
RIPEMD160, CAST5 secret key decryption with iterated+salted SHA1 S2K,
gnu-dummy S2K (sk8) and v3 keys and signatures.

Not tested, with the reason:
  - AES and Blowfish secret key decryption: no archive key uses them
    (generating new fixtures is out of scope).
  - user attribute packets, partial body lengths: no archive key has them.
  - v3 signature creation: PGP_Signature only writes v4 signatures
    (_writeSigV4); v3 signatures can only be read and verified.
  - the trust graph against a repository: covered under 3.14.
  - signing: covered by test_openpgp.py (test_sign_uid_roundtrip and
    friends).
  - xorStr: covered by test_openpgp.py::test_xor_str.
"""

import hashlib
import os

import pytest

from conary.lib import openpgpfile, openpgpkey, util
from conary.lib.openpgpfile import (BadPassPhrase, IncompatibleKey,
                                    KeyNotFound)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARCHIVE = os.path.join(ROOT, 'conary_test', 'archive')
KEYS = os.path.join(ARCHIVE, 'pgp-keys')

FP_KEY_ASC = '95B457D16843B21EA3FC73BBC7C32FC1F94E405E'


def keyring(name):
    return os.path.join(KEYS, name)


def _binaryKeyAsc():
    with open(os.path.join(ARCHIVE, 'key.asc'), 'rb') as f:
        return openpgpfile.parseAsciiArmorKey(f.read())


@pytest.fixture
def srcKeyring(tmp_path):
    """A binary keyring holding only the key.asc key."""
    path = tmp_path / 'src-keyring.gpg'
    path.write_bytes(_binaryKeyAsc())
    return str(path)


# --------------------------------------------------------------------------
# Key caches

def test_keyring_cache_callback_fetches_key(tmp_path, srcKeyring):
    pubRing = str(tmp_path / 'test-pubring.gpg')
    callback = openpgpkey.KeyringCacheCallback(srcKeyring)
    cache = openpgpkey.OpenPGPKeyFileCache(callback=callback)
    cache.setPublicPath(pubRing)

    key = cache.getPublicKey(FP_KEY_ASC)
    assert key.getFingerprint() == FP_KEY_ASC
    # The key was copied into the first public keyring
    assert FP_KEY_ASC in openpgpfile.getFingerprints(pubRing)

    # A fresh cache with no callback source finds it in the keyring now
    cache2 = openpgpkey.OpenPGPKeyFileCache()
    cache2.setPublicPath(pubRing)
    assert cache2.getPublicKey(FP_KEY_ASC).getFingerprint() == FP_KEY_ASC


def test_keyring_cache_callback_missing_key(tmp_path):
    pubRing = str(tmp_path / 'test-pubring.gpg')
    # source keyring that does not exist, then one that lacks the key
    cb = openpgpkey.KeyringCacheCallback(str(tmp_path / 'no-such-keyring'))
    cache = openpgpkey.OpenPGPKeyFileCache(callback=cb)
    cache.setPublicPath(pubRing)
    with pytest.raises(KeyNotFound):
        cache.getPublicKey(FP_KEY_ASC)
    # negative results are cached
    assert cache.publicDict[FP_KEY_ASC] is None

    other = tmp_path / 'other-keyring.gpg'
    other.write_bytes(open(keyring('pk1.gpg'), 'rb').read())
    cache = openpgpkey.OpenPGPKeyFileCache(
        callback=openpgpkey.KeyringCacheCallback(str(other)))
    cache.setPublicPath(pubRing)
    with pytest.raises(KeyNotFound):
        cache.getPublicKey(FP_KEY_ASC)


def test_keyring_cache_negative_entry_is_sticky(tmp_path, srcKeyring):
    pubRing = str(tmp_path / 'test-pubring.gpg')
    emptySrc = tmp_path / 'late-keyring.gpg'
    cache = openpgpkey.OpenPGPKeyFileCache(
        callback=openpgpkey.KeyringCacheCallback(str(emptySrc)))
    cache.setPublicPath(pubRing)
    with pytest.raises(KeyNotFound):
        cache.getPublicKey(FP_KEY_ASC)
    # Adding the key to the source afterwards does not change the cached
    # answer until the entry is removed
    emptySrc.write_bytes(_binaryKeyAsc())
    with pytest.raises(KeyNotFound):
        cache.getPublicKey(FP_KEY_ASC)
    cache.remove(FP_KEY_ASC)
    assert cache.getPublicKey(FP_KEY_ASC).getFingerprint() == FP_KEY_ASC


def test_disk_cache_callback(tmp_path):
    keyDir = tmp_path / 'public-key-dir'
    keyDir.mkdir()
    pubRing = str(tmp_path / 'test-pubring.gpg')
    cache = openpgpkey.OpenPGPKeyFileCache(
        callback=openpgpkey.DiskKeyCacheCallback(str(keyDir)))
    cache.setPublicPath(pubRing)
    with pytest.raises(KeyNotFound):
        cache.getPublicKey(FP_KEY_ASC)

    # keys are stored as <lowercase keyid>.asc
    cache.remove(FP_KEY_ASC)
    with open(os.path.join(ARCHIVE, 'key.asc'), 'rb') as f:
        (keyDir / ('%s.asc' % FP_KEY_ASC.lower())).write_bytes(f.read())
    key = cache.getPublicKey(FP_KEY_ASC)
    assert key.getFingerprint() == FP_KEY_ASC
    assert FP_KEY_ASC in openpgpfile.getFingerprints(pubRing)


def test_disk_cache_unreadable_key_file(tmp_path):
    if os.geteuid() == 0:
        pytest.skip('permission bits do not apply to root')
    keyDir = tmp_path / 'public-key-dir'
    keyDir.mkdir()
    keyFile = keyDir / ('%s.asc' % FP_KEY_ASC.lower())
    keyFile.write_bytes(_binaryKeyAsc())
    keyFile.chmod(0)
    cb = openpgpkey.DiskKeyCacheCallback(str(keyDir))
    with pytest.raises(KeyNotFound):
        cb.findOpenPGPKey(None, FP_KEY_ASC)


def test_key_cache_paths():
    cache = openpgpkey.OpenPGPKeyFileCache()
    cache.setPublicPath('/a')
    assert cache.publicPaths == ['/a']
    cache.addPublicPath('/b')
    cache.addPublicPath(['/c', '/d'])
    assert cache.publicPaths == ['/a', '/b', '/c', '/d']
    cache.setPublicPath(['/x'])
    assert cache.publicPaths == ['/x']
    cache.setPrivatePath('/priv')
    assert cache.privatePath == '/priv'


def test_key_cache_private_key_found_via_privatepath():
    cache = openpgpkey.OpenPGPKeyFileCache()
    cache.setPublicPath(keyring('pubringrev.gpg'))
    cache.setPrivatePath(keyring('secringrev.gpg'))
    cache.getPublicKey('91E3E6C5')
    with pytest.raises(BadPassPhrase):
        cache.getPrivateKey('91E3E6C5', 'bad-passphrase')
    assert cache.getPrivateKey('91E3E6C5', 'key32')
    cache.reset()
    assert cache.publicDict == {} and cache.privateDict == {}


# --------------------------------------------------------------------------
# S2K with MD5 and RIPEMD160

# RFC 1320/RIPEMD-160 reference digests, independent of the code under test
RIPEMD160_ABC = '8eb208f7e05d987a9b044a8e98c6b087f15a0bfc'
RIPEMD160_EMPTY = '9c1185a5c5e9fc54612808977ee8f548b2258d31'


@pytest.mark.parametrize('passphrase,expected', [
    (b'', RIPEMD160_EMPTY),
    (b'abc', RIPEMD160_ABC),
    ('abc', RIPEMD160_ABC),
])
def test_s2k_simple_ripemd160(passphrase, expected):
    out = openpgpfile.simpleS2K(passphrase, openpgpfile._hashRIPEMD160, 160)
    assert isinstance(out, bytes)
    assert out.hex() == expected
    # a smaller key is a prefix of the digest
    short = openpgpfile.simpleS2K(passphrase, openpgpfile._hashRIPEMD160, 128)
    assert short.hex() == expected[:32]


def test_s2k_ripemd160_longer_than_digest():
    # RFC 4880 3.7.1.1: more key bytes than digest bytes preloads one more
    # zero octet per extra hash instance
    out = openpgpfile.simpleS2K(b'abc', openpgpfile._hashRIPEMD160, 256)
    assert len(out) == 32
    second = openpgpfile._hashRIPEMD160(b'\x00' + b'abc').hexdigest()
    assert out.hex() == RIPEMD160_ABC + second[:24]


@pytest.mark.parametrize('passphrase', [b'', b'abc', 'abc'])
def test_s2k_md5(passphrase):
    raw = passphrase.encode() if isinstance(passphrase, str) else passphrase
    salt = b'12345678'
    assert openpgpfile.simpleS2K(passphrase, hashlib.md5, 128) == \
        hashlib.md5(raw).digest()
    assert openpgpfile.saltedS2K(passphrase, hashlib.md5, 128, salt) == \
        hashlib.md5(salt + raw).digest()


def test_s2k_salted_and_iterated_ripemd160():
    salt = b'12345678'
    expected = openpgpfile._hashRIPEMD160(salt + b'abc').hexdigest()
    assert openpgpfile.saltedS2K(b'abc', openpgpfile._hashRIPEMD160, 160,
                                 salt).hex() == expected

    # Iterated: count byte 0 means (16 + 0) << 6 == 1024 octets of
    # repeated salt+passphrase, truncated to the count
    buf = salt + b'abc'
    stream = (buf * (1024 // len(buf) + 1))[:1024]
    expected = openpgpfile._hashRIPEMD160(stream).hexdigest()
    assert openpgpfile.iteratedS2K(b'abc', openpgpfile._hashRIPEMD160, 160,
                                   salt, 0).hex() == expected


def test_s2k_iterated_md5_count_shorter_than_buffer():
    # RFC 4880 3.7.1.3: the count is a minimum; salt+passphrase is always
    # hashed at least once, in full
    salt = b'12345678'
    passphrase = b'p' * 2000
    out = openpgpfile.iteratedS2K(passphrase, hashlib.md5, 128, salt, 0)
    assert out == hashlib.md5(salt + passphrase).digest()


def test_s2k_iterated_md5_partial_last_copy():
    salt = b'12345678'
    buf = salt + b'pass'
    stream = (buf * (1024 // len(buf) + 1))[:1024]
    assert openpgpfile.iteratedS2K(b'pass', hashlib.md5, 128, salt, 0) == \
        hashlib.md5(stream).digest()


# --------------------------------------------------------------------------
# CAST5 + iterated/salted SHA1 secret keys, gnu-dummy S2K

@pytest.mark.parametrize('ring,keyId,passphrase', [
    ('sk1.gpg', '29BF4FCA', 'key-revoc'),
    ('sk6.gpg', 'D5E8FF1A', 'key-rsa'),
])
def test_secret_key_cast5_iterated_salted_sha1(ring, keyId, passphrase):
    skey = openpgpfile.seekKeyById(keyId, keyring(ring))
    skey.parse()
    # RFC 4880: s2k usage 254 (SHA1 checksum), cipher 3 (CAST5), s2k
    # type 3 (iterated and salted), hash 2 (SHA1)
    assert skey.s2k == openpgpfile.ENCRYPTION_TYPE_SHA1_CHECK
    assert skey.symmEncAlg == 3
    assert skey.s2kType == 3
    assert skey.hashAlg == 2

    mpis = skey.decrypt(passphrase)
    assert mpis and all(isinstance(x, int) for x in mpis)
    # the secret MPIs rebuild a usable crypto key
    assert skey.makePgpKey(passPhrase=passphrase).has_private()
    with pytest.raises(BadPassPhrase):
        skey.decrypt('not-the-passphrase')
    with pytest.raises(BadPassPhrase):
        skey.decrypt(None)


def test_secret_key_cast5_bytes_passphrase_matches_str():
    skey = openpgpfile.seekKeyById('D5E8FF1A', keyring('sk6.gpg'))
    assert skey.decrypt(b'key-rsa') == skey.decrypt('key-rsa')


def test_sk5_cast5_parameters():
    # sk5 has a CAST5 iterated+salted SHA1 key (no known passphrase), so
    # only the parsed S2K parameters and the failure mode are checked
    skey = openpgpfile.seekKeyById('F3C198B6', keyring('sk5.gpg'))
    skey.parse()
    assert (skey.symmEncAlg, skey.s2kType, skey.hashAlg) == (3, 3, 2)
    with pytest.raises(BadPassPhrase):
        skey.decrypt('wrong')


def test_gnu_dummy_s2k_main_key():
    skey = openpgpfile.seekKeyById('0FD4B672', keyring('sk8.gpg'))
    skey.parse()
    assert skey.s2kType == 101
    with pytest.raises(IncompatibleKey) as exc:
        skey.decrypt('anything')
    assert 'string-to-key type 101' in str(exc.value)
    # No private key can be built from the stub, but the public half is
    # usable
    pub = skey.toPublicKey()
    assert not pub.makePgpKey().has_private()
    assert pub.getKeyFingerprint() == '99F3EA61523474E5147938BA45AD480E0FD4B672'


def test_gnu_dummy_s2k_subkey_self_signatures():
    # The main key is a stub; verifying a subkey must use the public part
    # instead of decrypting
    key = openpgpfile.seekKeyById('0FD4B672', keyring('sk8.gpg'))
    assert len(key.subkeys) >= 2
    key.subkeys[1].verifySelfSignatures()
    for sub in key.subkeys:
        sub.parse()
        assert sub.s2kType == 3 and sub.symmEncAlg == 3


# --------------------------------------------------------------------------
# v3 keys and signatures

@pytest.mark.parametrize('ring', ['v3key.gpg', 'v3key2.gpg'])
def test_v3_key_self_signatures(ring):
    msg = openpgpfile.PGP_Message(keyring(ring))
    key = next(msg.iterMainKeys())
    assert key.version in (2, 3)
    assert key.verifySelfSignatures()
    # v3 key ids and fingerprints are unrelated; both resolve to the key
    assert len(key.getKeyFingerprint()) == 32
    assert len(key.getKeyId()) == 16


def test_v3_signature_ids_are_bytes():
    with open(keyring('ver3.sig.asc'), 'rb') as f:
        data = openpgpfile.parseAsciiArmorKey(f.read())
    msg = openpgpfile.PGP_Message(util.ExtendedStringIO(data))
    sig = next(msg.iterPackets())
    assert sig.getSigId() == b'\xc8k\xa0jQ}\x0f\x0e'
    sig.parse()
    assert sig.version in (2, 3)
    assert sig.getSignerKeyId() == 'C86BA06A517D0F0E'


def test_v3_signature_cannot_be_rewritten_as_v3():
    # PGP_Signature only produces v4 signatures; a v3 signature cannot be
    # signed or hashed over its own subpackets
    with open(keyring('ver3.sig.asc'), 'rb') as f:
        data = openpgpfile.parseAsciiArmorKey(f.read())
    sig = next(openpgpfile.PGP_Message(
        util.ExtendedStringIO(data)).iterPackets())
    sig.parse()
    assert hasattr(sig, '_writeSigV4')
    assert not hasattr(sig, '_writeSigV3')
