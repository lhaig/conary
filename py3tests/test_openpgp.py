"""
Port of the relevant cases of conary_test/libtest/openpgptest.py to pytest.

Cases that need the rephelp repository harness (the trust graph in
OpenPGPTrustTest, ServerInteractionTest) are covered by 3.14.  Key caches,
S2K variants, CAST5/gnu-dummy secret keys and v3 keys and signatures are in
test_openpgp_paths.py, which also lists the paths that stay untested for
lack of archive keys.  testMerge* is covered indirectly by the keyring add
test below.
"""

import ast
import io
import os
import time

import pytest

from conary.lib import openpgpfile, openpgpkey, util
from conary.lib.openpgpfile import (BadPassPhrase, BadSelfSignature,
                                    KeyNotFound, MalformedKeyRing,
                                    PGPError, SignatureError)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARCHIVE = os.path.join(ROOT, 'conary_test', 'archive')
KEYS = os.path.join(ARCHIVE, 'pgp-keys')

FP_KEY_ASC = '95B457D16843B21EA3FC73BBC7C32FC1F94E405E'


def keyring(name):
    return os.path.join(KEYS, name)


def archive(name):
    return os.path.join(ARCHIVE, name)


def _load_legacy_constants():
    # pubkey4/seckey4 (bytes) and pubkeya4 (armor text) live in the
    # conary_test module. Read them without importing it (it needs
    # testrunner).
    path = os.path.join(ROOT, 'conary_test', 'libtest', 'openpgptest.py')
    tree = ast.parse(open(path).read())
    out = {}
    for node in tree.body:
        if (isinstance(node, ast.Assign) and
                getattr(node.targets[0], 'id', None) in
                ('pubkey4', 'seckey4', 'pubkeya4')):
            out[node.targets[0].id] = ast.literal_eval(node.value)
    return out

_legacy = _load_legacy_constants()
PUBKEY4 = _legacy['pubkey4']
SECKEY4 = _legacy['seckey4']
PUBKEYA4 = _legacy['pubkeya4']


# --------------------------------------------------------------------------
# Lookup and parsing

@pytest.mark.parametrize('ring', ['pubring.gpg', 'secring.gpg'])
def test_find_keys(ring):
    path = archive(ring)
    # a main key, and a subkey
    assert openpgpfile.getFingerprint('C7C32FC1F94E405E', path) == FP_KEY_ASC
    assert len(openpgpfile.getFingerprint('017111F7', path)) == 40


def test_fingerprint_is_hex_str():
    fp = openpgpfile.getFingerprint(FP_KEY_ASC[-16:], archive('pubring.gpg'))
    assert isinstance(fp, str)
    assert fp == FP_KEY_ASC


def test_seek_missing_key():
    with open(archive('pubring.gpg'), 'rb') as f:
        assert not openpgpfile.seekKeyById('NOTAVALIDFINGERPRINT', f)
    assert openpgpfile.seekKeyById('C7C32FC1F94E405E',
                                   '/no/such/keyring') is False
    with pytest.raises(KeyNotFound):
        openpgpfile.getFingerprint('DEADBEEF', archive('pubring.gpg'))


def test_seek_key_by_id_returns_key_with_ids():
    key = openpgpfile.seekKeyById('C7C32FC1F94E405E', archive('pubring.gpg'))
    assert key.getKeyFingerprint() == FP_KEY_ASC
    assert key.getKeyId() == 'A3FC73BBC7C32FC1F94E405E'[-16:]
    ids = key.getUserIds()
    assert ids and all(isinstance(x, str) for x in ids)


def test_fingerprint_to_internal_key_id():
    fp = "112233445566778899AABBDD00EEFF1122334455"
    intKeyId = openpgpfile.fingerprintToInternalKeyId(fp)
    assert intKeyId == b'\x00\xee\xff\x11"3DU'
    assert len(intKeyId) == 8
    assert openpgpfile.fingerprintToInternalKeyId('') == b''


def test_s2k():
    data = [
        ('', 'DA39A3EE5E6B4B0D3255BFEF95601890',
             '89D14893B12A0116A88A1AEB5530FDE8',
             '006A5A5D2422D19051A4ABC141C1F510'),
        ('a', '86F7E437FAA5A7FCE15D1DDCB9EAEAEA',
              '529B38BD89A90F873D1D51E30B57C96B',
              '09A377456C27F8D8A6D527D0CF4C419D'),
        ('aa', 'E0C9035898DD52FC65C41454CEC9C4D2',
               '89CDA9A5D0393DFF564BB2A1D769F36E',
               'E18D17331021E559DAE2EFD280931B5C'),
        ('abcde', '03DE6C570BFE24BFC328CCD7CA46B76E',
                  'C62BE1A3D54633B3D2A00806DC51CB74',
                  'B2FD7438E58039F8ADD455527421BD8B'),
    ]
    s2a = openpgpfile.stringToAscii
    hashAlg = openpgpfile.digestlib.sha1
    for s, e1, e2, e3 in data:
        assert s2a(openpgpfile.simpleS2K(s, hashAlg, 128)) == e1
        assert s2a(openpgpfile.saltedS2K(s, hashAlg, 128, b'some-salt')) == e2
        assert s2a(openpgpfile.iteratedS2K(s, hashAlg, 128, b'some-salt',
                                           2)) == e3
        # bytes passphrases give the same answer
        assert s2a(openpgpfile.simpleS2K(s.encode(), hashAlg, 128)) == e1


def test_hash_set():
    sioc = util.ExtendedStringIO
    items = [sioc(b''), sioc(b'a'), sioc(b'aa'), sioc(b'abcde')]
    exp = ['03DE6C570BFE24BFC328CCD7CA46B76EADAF4334',
           'DA39A3EE5E6B4B0D3255BFEF95601890AFD80709',
           'E0C9035898DD52FC65C41454CEC9C4D2611BFB37',
           '86F7E437FAA5A7FCE15D1DDCB9EAEAEA377667B8']
    got = openpgpfile.PGP_Packet._hashSet(items)
    assert sorted(openpgpfile.stringToAscii(x) for x in got) == sorted(exp)


def test_xor_str():
    s1 = b'abc'
    s2 = b'\0\0\0'
    assert openpgpfile.xorStr(s1, s2) == s1
    assert openpgpfile.xorStr(s1, s1) == s2
    assert openpgpfile.xorStr(s1 + s1, s2) == s1
    assert openpgpfile.xorStr(s1 + s2, s1) == s2
    assert isinstance(openpgpfile.xorStr(s1, s2), bytes)


def test_crc24():
    data = [(b'', b'\xb7\x04\xce', 'twTO'),
            (b'a', b'\xf2\x57\x13', '8lcT'),
            (b'aa', b'\xad\x83\xdb', 'rYPb'),
            (b'abc', b'\xba\x1c\x7b', 'uhx7')]
    for src, exp, b64exp in data:
        assert openpgpfile.crc24(src) == exp
        assert openpgpfile.crc24base64(src) == b64exp
        # streams work too
        assert openpgpfile.crc24(io.BytesIO(src)) == exp


def test_mpi_ops():
    tests = [0, 1, 127, 511, 987654321987654321987654321987654321987654321,
             0, 1]
    wr = openpgpfile.PGP_Signature._writeMPI
    rd = openpgpfile.PGP_Signature._readCountMPIs
    stream = util.ExtendedStringIO()
    for i, tst in enumerate(tests):
        stream.seek(0, 2)
        wr(stream, tst)
        stream.seek(0)
        assert rd(stream, i + 1, discard=False) == tests[:i + 1]


def test_num_helpers():
    assert openpgpfile.num_bitLen(0) == 0
    assert openpgpfile.num_bitLen(255) == 8
    assert openpgpfile.num_bitLen(256) == 9
    q = (1 << 160) - 47
    for _ in range(5):
        r = openpgpfile.num_getRelPrime(q)
        assert 2 <= r < q
        assert openpgpfile.num_gcd(r, q - 1) == 1


# --------------------------------------------------------------------------
# Armor

def test_parse_ascii_armor_key():
    assert openpgpfile.parseAsciiArmorKey(PUBKEYA4) == PUBKEY4
    # bytes input is accepted as well
    assert openpgpfile.parseAsciiArmorKey(PUBKEYA4.encode()) == PUBKEY4

    # Bad CRC
    with pytest.raises(PGPError):
        openpgpfile.parseAsciiArmorKey(PUBKEYA4.replace('MgNw', 'zero'))
    # No CRC is ok
    assert openpgpfile.parseAsciiArmorKey(
        PUBKEYA4.replace('=MgNw\n', '')) == PUBKEY4

    assert openpgpfile.parseAsciiArmorKey('') is None
    assert openpgpfile.parseAsciiArmorKey(
        '-\nSome text\n\n\0+++\n-\n') is None
    assert openpgpfile.parseAsciiArmorKey('-\nSome text\n\nA\n-\n') is None


def test_parse_ascii_armor_streams():
    sio = util.ExtendedStringIO()
    openpgpfile.parseAsciiArmor(util.ExtendedStringIO(PUBKEYA4.encode()), sio)
    sio.seek(0)
    assert sio.read() == PUBKEY4
    # Binary key passes through untouched
    sio = util.ExtendedStringIO()
    openpgpfile.parseAsciiArmor(util.ExtendedStringIO(PUBKEY4), sio)
    sio.seek(0)
    assert sio.read() == PUBKEY4


def test_import_armored_key_asc():
    data = open(archive('key.asc'), 'rb').read()
    binary = openpgpfile.parseAsciiArmorKey(data)
    assert isinstance(binary, bytes) and binary[0] & 0x80
    key = openpgpfile.newKeyFromString(binary)
    assert key.getKeyFingerprint() == FP_KEY_ASC
    pkpkt, cryptoKey = key.verifySelfSignatures()
    assert openpgpfile.key_type(cryptoKey) == 'RSA'
    assert openpgpfile.countKeys(util.ExtendedStringIO(binary)) == 1
    # Armoring again round-trips
    out = util.ExtendedStringIO()
    openpgpfile.armorKeyData(binary, out)
    assert openpgpfile.parseAsciiArmorKey(out.getvalue()) == binary


def test_export_key_armored_roundtrip():
    sio = openpgpfile.exportKey(FP_KEY_ASC[-16:], archive('pubring.gpg'))
    binary = sio.read()
    sio = openpgpfile.exportKey(FP_KEY_ASC[-16:], archive('pubring.gpg'),
                                armored=True)
    armored = sio.read()
    assert armored.startswith(b'-----BEGIN PGP PUBLIC KEY BLOCK-----')
    assert openpgpfile.parseAsciiArmorKey(armored) == binary
    with pytest.raises(KeyNotFound):
        openpgpfile.exportKey('NOSUCHKEY', keyring('pk1.gpg'))


# --------------------------------------------------------------------------
# Self signatures and key parsing

def test_verify_self_signatures_inline_keys():
    s = util.ExtendedStringIO(PUBKEY4)
    openpgpfile.verifySelfSignatures('91E3E6C5', s)
    with pytest.raises(KeyNotFound):
        openpgpfile.verifySelfSignatures('NOSUCHKEY', s)
    for blob in (PUBKEY4, SECKEY4):
        msg = openpgpfile.PGP_Message(util.ExtendedStringIO(blob))
        for pkt in msg.iterKeys():
            pkt.verifySelfSignatures()
            for sub in pkt.iterSubKeys():
                sub.verifySelfSignatures()
                if sub.bindingSig:
                    old = sub.bindingSig.hashSig
                    sub.bindingSig.setShortSigHash(b'\0\0')
                    sub.bindingSig._sigDigest = None
                    with pytest.raises(BadSelfSignature):
                        sub.verifySelfSignatures()
                    sub.bindingSig.hashSig = old


def test_sig_v3_key():
    msg = openpgpfile.PGP_Message(keyring('v3key.gpg'))
    key = next(msg.iterKeys())
    key.verifySelfSignatures()
    assert key.getKeyId() == '7123BC13ED9D77D5'
    assert key.getKeyFingerprint() == 'D334F25FD714E0906203EF2D7E4AA598'
    next(msg.iterByKeyId('ED9D77D5'))
    next(msg.iterByKeyId('EF2D7E4AA598'))


def test_count_keys_and_fingerprints():
    assert openpgpfile.countKeys(util.ExtendedStringIO(PUBKEY4)) == 1
    fps = openpgpfile.getFingerprints(archive('pubring.gpg'))
    assert FP_KEY_ASC in fps


def test_end_of_life():
    key = openpgpfile.seekKeyById('29BF4FCA', keyring('pubringrev.gpg'))
    key.verifySelfSignatures()
    revoked, ts = key.getEndOfLife()
    assert revoked


# --------------------------------------------------------------------------
# Secret keys

def test_secret_key_decrypt_des3():
    msg = openpgpfile.PGP_Message(util.ExtendedStringIO(SECKEY4))
    pkt = next(msg.iterKeys())
    assert pkt.decrypt('key32') == [708255119797086932650717083595073066992696472566]
    with pytest.raises(BadPassPhrase):
        pkt.decrypt('blah')
    with pytest.raises(BadPassPhrase):
        pkt.decrypt(None)


def test_secret_key_dsa_and_elgamal():
    skey = openpgpfile.seekKeyById('29BF4FCA', keyring('sk1.gpg'))
    cryptoKey = skey.makePgpKey(passPhrase='key-revoc')
    assert openpgpfile.key_type(cryptoKey) == 'DSA'
    assert cryptoKey.has_private()
    with pytest.raises(BadPassPhrase):
        skey.makePgpKey(passPhrase='wrong')

    skey = openpgpfile.seekKeyById('CBAE99C8', keyring('sk1.gpg'))
    with pytest.raises(MalformedKeyRing):
        skey.makePgpKey(passPhrase='key-revoc')
    with pytest.raises(MalformedKeyRing):
        skey.toPublicKey().makePgpKey()


def _recrypt(newPass):
    msg = openpgpfile.PGP_Message(util.ExtendedStringIO(SECKEY4))
    pkt = next(msg.iterKeys())
    mpis = pkt.decrypt('key32')
    subMpis = [sk.decrypt('key32') for sk in pkt.iterSubKeys()]
    assert pkt.recrypt('key32', newPass)
    sio = util.ExtendedStringIO()
    pkt.rewriteAll(sio)
    sio.seek(0)
    pkt = next(openpgpfile.PGP_Message(sio).iterKeys())
    assert pkt.decrypt(newPass) == mpis
    assert [sk.decrypt(newPass) for sk in pkt.iterSubKeys()] == subMpis
    if newPass is not None:
        with pytest.raises(BadPassPhrase):
            pkt.decrypt('key32')


def test_secret_key_recrypt_no_pass():
    _recrypt(None)


def test_secret_key_recrypt_with_pass():
    _recrypt('dodo')


def test_secret_key_recrypt_unchanged_noop():
    msg = openpgpfile.PGP_Message(util.ExtendedStringIO(SECKEY4))
    pkt = next(msg.iterKeys())
    assert pkt.recrypt('key32', 'key32') is False


@pytest.mark.parametrize('keyId,passphrase,ring,alg', [
    ('7A746BAE', 'key20', 'secringrev.gpg', 'DSA'),
    ('D5E8FF1A', 'key-rsa', 'sk6.gpg', 'RSA'),
])
def test_secret_key_types(keyId, passphrase, ring, alg):
    skey = openpgpfile.seekKeyById(keyId, keyring(ring))
    cryptoKey = skey.makePgpKey(passPhrase=passphrase)
    assert openpgpfile.key_type(cryptoKey) == alg
    pub = skey.toPublicKey().makePgpKey()
    assert not pub.has_private()
    if alg == 'RSA':
        assert pub.n == cryptoKey.n and pub.e == cryptoKey.e
    else:
        assert pub.y == cryptoKey.y and pub.q == cryptoKey.q


# --------------------------------------------------------------------------
# Signing round trips

SIGNERS = [('7A746BAE', 'secringrev.gpg', 'key20'),
           ('D5E8FF1A', 'sk6.gpg', 'key-rsa')]


@pytest.mark.parametrize('keyId,ring,passphrase', SIGNERS,
                         ids=['dsa', 'rsa'])
def test_sign_uid_roundtrip(keyId, ring, passphrase):
    key = openpgpfile.seekKeyById('29BF4FCA', keyring('pk3.gpg'))
    sigkey = openpgpfile.seekKeyById(keyId, keyring(ring))
    uid = key.uids[2]
    cb = lambda x=None: passphrase

    trustRegex = r'<[^>]+[@.]rpath\.com>$'
    expsec = 3600 * 24 * 7
    cryptoKey = sigkey.toPublicKey().makePgpKey()
    sigkey.sign(uid, expiration=expsec, trustLevel=1, trustAmount=40,
                trustRegex=trustRegex, passwordCallback=cb)

    sig = uid.signatures[-1]
    sig.verify(cryptoKey, key.getKeyId())
    assert sig.getExpiration() == expsec
    pkts = [x[1] for x in sig.decodeHashedSubpackets()
            if x[0] == openpgpfile.SIG_SUBPKT_TRUST]
    assert len(pkts) == 1
    pkts[0].seek(0)
    assert sig._readBin(pkts[0], 2) == [1, 40]
    pkts = [x[1] for x in sig.decodeHashedSubpackets()
            if x[0] == (0x80 | openpgpfile.SIG_SUBPKT_REGEX)]
    assert len(pkts) == 1
    pkts[0].seek(0)
    assert pkts[0].read() == trustRegex.encode() + b'\0'
    assert sig.getTrust() == (1, 40, trustRegex)

    # The signature survives being serialised and parsed back
    sio = util.ExtendedStringIO()
    sig.write(sio)
    sio.seek(0)
    sig2 = openpgpfile.readSignature(sio)
    assert sig2.getSigId() == sig.getSigId()
    assert sig2.parseMPIs() == sig.parseMPIs()
    assert sig2.getTrust() == (1, 40, trustRegex)

    # Non-expiring signature
    sigkey.sign(uid, expiration=-1, sigType=openpgpfile.SIG_TYPE_CERT_3,
                passwordCallback=cb)
    sig = uid.signatures[-1]
    sig.verify(cryptoKey, key.getKeyId())
    assert sig.getExpiration() is None
    assert sig.sigType == openpgpfile.SIG_TYPE_CERT_3

    # Verification against a different key fails
    other = openpgpfile.seekKeyById(
        'D5E8FF1A' if keyId != 'D5E8FF1A' else '7A746BAE',
        keyring('sk6.gpg' if keyId != 'D5E8FF1A' else 'secringrev.gpg'))
    otherKey = other.toPublicKey().makePgpKey()
    with pytest.raises(openpgpfile.BadSelfSignature):
        sig.verify(otherKey, key.getKeyId())


@pytest.mark.parametrize('keyId,ring,passphrase', SIGNERS,
                         ids=['dsa', 'rsa'])
def test_sign_revoked_key_refused(keyId, ring, passphrase):
    sigkey = openpgpfile.seekKeyById(keyId, keyring(ring))
    key = openpgpfile.seekKeyById('29BF4FCA', keyring('pk7.gpg'))
    uid = key.uids[2]
    assert uid.getExpiration() == -1
    with pytest.raises(SignatureError):
        sigkey.sign(uid, passwordCallback=lambda x=None: passphrase)


@pytest.mark.parametrize('keyId,ring,passphrase', SIGNERS,
                         ids=['dsa', 'rsa'])
def test_tampered_signature_fails(keyId, ring, passphrase):
    key = openpgpfile.seekKeyById('29BF4FCA', keyring('pk2.gpg'))
    sigkey = openpgpfile.seekKeyById(keyId, keyring(ring))
    uid = key.uids[2]
    cryptoKey = sigkey.toPublicKey().makePgpKey()
    sigkey.sign(uid, passwordCallback=lambda x=None: passphrase)
    sig = uid.signatures[-1]
    sig.verify(cryptoKey, key.getKeyId())

    # Flip a bit in the signature MPIs: the short hash still matches but the
    # math must fail
    data = bytearray(sig.mpiFile.pread(sig.mpiFile.size, 0))
    data[-1] ^= 0x01
    sig.mpiFile = util.ExtendedStringIO(bytes(data))
    with pytest.raises(BadSelfSignature):
        sig.verify(cryptoKey, key.getKeyId())
    assert sig.getVerifies() is False


# --------------------------------------------------------------------------
# Document signatures

def test_verify_document_signature():
    key = openpgpfile.seekKeyById('29BF4FCA', keyring('pubringrev.gpg'))
    docPath = keyring('pk2.gpg')
    doc = open(docPath, 'rb')
    msg = openpgpfile.PGP_Message(keyring('pk2.gpg.sig'))
    sig = next(msg.iterPackets())
    cryptoKey = key.getCryptoKey()
    sig.getDocumentHash(doc)
    sig.verifyDocument(cryptoKey, doc)

    # Text signature type is not supported
    sig.sigType = openpgpfile.SIG_TYPE_TEXT_DOC
    with pytest.raises(PGPError):
        sig.verifyDocument(cryptoKey, doc)
    sig.sigType = openpgpfile.SIG_TYPE_BINARY_DOC

    # Alter the short hash
    hashSig = sig.getShortSigHash()
    sig.setShortSigHash(b'AA')
    with pytest.raises(SignatureError):
        sig.verifyDocument(cryptoKey, doc)
    sig.setShortSigHash(hashSig)
    sig.verifyDocument(cryptoKey, doc)

    # Alter the signature MPI
    x = util.ExtendedStringIO(sig.mpiFile.pread(sig.mpiFile.size, 0))
    x.seek(12)
    x.write(b'\0')
    sig.mpiFile = x
    with pytest.raises(SignatureError):
        sig.verifyDocument(cryptoKey, doc)

    # Unsupported signature version
    sig.version = 5
    with pytest.raises(openpgpfile.InvalidKey):
        sig.getDocumentHash(doc)

    # v4 signature
    sig = openpgpfile.readSignature(open(keyring('pk2.gpg.sig2'), 'rb'))
    sig.verifyDocument(cryptoKey, doc)
    doc.close()


def test_verify_document_tampered_document():
    key = openpgpfile.seekKeyById('29BF4FCA', keyring('pubringrev.gpg'))
    cryptoKey = key.getCryptoKey()
    data = open(keyring('pk2.gpg'), 'rb').read()
    sig = openpgpfile.readSignature(open(keyring('pk2.gpg.sig'), 'rb'))
    # the untouched document verifies
    sig.verifyDocument(cryptoKey, io.BytesIO(data))
    bad = bytearray(data)
    bad[len(bad) // 2] ^= 0xFF
    with pytest.raises(SignatureError):
        sig.verifyDocument(cryptoKey, io.BytesIO(bytes(bad)))
    with pytest.raises(SignatureError):
        sig.verifyDocument(cryptoKey, io.BytesIO(data + b'x'))


def _document_cases():
    keyToHash = {
        '1024-160': ('C1B4DE0894D38E40', [1, 224, 256, 384, 512]),
        '2048-224': ('3727440041FBF40E', [224, 256, 384, 512]),
        '3072-256': ('1AB3C4DBD1DE62B3', [256, 384, 512]),
        '7680-384': ('85F71CA5DCF45B60', [384, 512]),
    }
    cases = []
    for name, (keyId, hashes) in sorted(keyToHash.items()):
        for h in hashes:
            cases.append(('DSA2-Tests/keys/DSA-%s.pub' % name, keyId,
                          'DSA2-Docs/DSA-%s-SHA%s.doc' % (name, h),
                          'DSA2-Docs/DSA-%s-SHA%s.doc.sig' % (name, h)))
    # SHA224 RSA is known to fail upstream and is not part of the original
    # matrix
    for h in (1, 256, 384, 512):
        cases.append(('pk6.gpg', '07E6FBC8D5E8FF1A',
                      'RSA-Tests/RSA-SHA%s.doc' % h,
                      'RSA-Tests/RSA-SHA%s.doc.sig' % h))
    return cases

DOC_CASES = _document_cases()


@pytest.mark.parametrize('pubring,keyId,doc,docSig', DOC_CASES,
                         ids=[c[3].split('/')[-1] for c in DOC_CASES])
def test_verify_document_signatures_matrix(pubring, keyId, doc, docSig):
    key = openpgpfile.seekKeyById(keyId, keyring(pubring))
    data = open(keyring(doc), 'rb').read()
    sig = openpgpfile.readSignature(open(keyring(docSig), 'rb'))
    cryptoKey = key.getCryptoKey()
    sig.verifyDocument(cryptoKey, io.BytesIO(data))
    # The same signature must not verify a modified document
    bad = bytearray(data)
    bad[0] ^= 0x01
    sig2 = openpgpfile.readSignature(open(keyring(docSig), 'rb'))
    with pytest.raises(SignatureError):
        sig2.verifyDocument(cryptoKey, io.BytesIO(bytes(bad)))


def test_distcc_detached_signature():
    # distcc-2.9.tar.bz2.asc is a v3 DSA signature by 3C63CA3FA0B3E88B, whose
    # (armored) key is in 0xA0B3E88B.pgp
    docPath = archive('distcc-2.9.tar.bz2')
    sigData = open(archive('distcc-2.9.tar.bz2.asc'), 'rb').read()
    sig = openpgpfile.readSignature(io.BytesIO(sigData))
    sig.parse()
    assert sig.version == 3
    assert sig.getSignerKeyId() == '3C63CA3FA0B3E88B'

    keyData = openpgpfile.parseAsciiArmorKey(
        open(archive('0xA0B3E88B.pgp'), 'rb').read())
    key = openpgpfile.newKeyFromString(keyData)
    assert key.getKeyId().endswith('A0B3E88B')
    cryptoKey = key.getCryptoKey()
    assert openpgpfile.key_type(cryptoKey) == 'DSA'

    with open(docPath, 'rb') as doc:
        sig.verifyDocument(cryptoKey, doc)

    # One flipped bit in the data must break it
    data = bytearray(open(docPath, 'rb').read())
    data[len(data) // 3] ^= 0x10
    sig = openpgpfile.readSignature(io.BytesIO(sigData))
    with pytest.raises(SignatureError):
        sig.verifyDocument(cryptoKey, io.BytesIO(bytes(data)))


def test_sig_v3_detached_armored():
    sig = openpgpfile.readSignature(open(keyring('ver3.sig.asc'), 'rb'))
    sig.parse()
    assert sig.version in (2, 3)
    assert len(sig.getSignerKeyId()) == 16


def test_read_signature():
    sig = openpgpfile.readSignature(open(keyring('pk2.gpg.sig'), 'rb'))
    assert len(sig.getSignerKeyId()) == 16
    with pytest.raises(openpgpfile.InvalidPacketError):
        openpgpfile.readSignature(io.BytesIO(b''))
    with pytest.raises(openpgpfile.InvalidPacketError):
        openpgpfile.readSignature(open(keyring('pk2.gpg'), 'rb'))


def test_get_signature_hash():
    msg = openpgpfile.PGP_Message(keyring('pk2.gpg'))
    pkt = next(msg.iterKeys())
    sig = pkt.uids[0].signatures[0]
    shash = sig.getSignatureHash()
    assert openpgpfile.stringToAscii(shash) == \
        'B7719A5519EF8CFCDF91074A465CDAC4E0848FDC'
    assert sig.hashSig == b'\xB7\x71'
    sig._sigDigest = None
    sig._parentPacket = pkt.uids[0].signatures[1]
    with pytest.raises(openpgpfile.InvalidPacketError):
        sig.getSignatureHash()


# --------------------------------------------------------------------------
# Raw key objects

def test_raw_rsa_key_math():
    # tiny textbook key: p=61 q=53 n=3233 e=17 d=2753
    k = openpgpfile._RSAKey(3233, 17, 2753, 61, 53, 38)
    assert k.has_private()
    pub = k.publickey()
    assert not pub.has_private()
    (s,) = k.sign(65, 0)
    assert s == pow(65, 2753, 3233)
    assert pub.verify(65, (s,))
    assert not pub.verify(66, (s,))
    # bytes message
    (s,) = k.sign(b'\x00\x41', 0)
    assert pub.verify(b'\x41', (s,))


def test_raw_dsa_key_math():
    # toy parameters: q | p-1, g of order q
    p, q = 23, 11
    g = pow(2, (p - 1) // q, p)
    x = 7
    y = pow(g, x, p)
    k = openpgpfile._DSAKey(p, q, g, y, x)
    assert k.has_private()
    pub = k.publickey()
    assert not pub.has_private()
    r, s = k.sign(5, 3)
    assert pub.verify(5, (r, s))
    assert not pub.verify(4, (r, s))
    assert not pub.verify(5, (0, s))
    assert not pub.verify(5, (r, q))


def test_finalize_signature_rsa_padding():
    key = openpgpfile.seekKeyById('D5E8FF1A', keyring('sk6.gpg'))
    cryptoKey = key.toPublicKey().makePgpKey()
    digest = b'\x11' * 20
    padded = openpgpfile.PGP_Signature.finalizeSignature(
        digest, cryptoKey, openpgpfile.PK_ALGO_RSA, 2)
    k = (cryptoKey.n.bit_length() + 7) // 8
    assert len(padded) == k - 1  # leading 0x00 of EMSA-PKCS1-v1_5 is implicit
    assert padded[0] == 1 and padded[1] == 0xFF
    assert padded.endswith(openpgpfile.PGP_Signature.HashAlgPads[2] + digest)


# --------------------------------------------------------------------------
# Key cache / keyring round trips

def test_key_cache_sign_verify_string():
    kc = openpgpkey.OpenPGPKeyFileCache()
    kc.setPublicPath(archive('pubring.gpg'))
    kc.setPrivatePath(archive('secring.gpg'))
    priv = kc.getPrivateKey(FP_KEY_ASC, '111111')
    pub = kc.getPublicKey(FP_KEY_ASC)
    assert priv.getFingerprint() == FP_KEY_ASC
    assert pub.getFingerprint() == FP_KEY_ASC

    for data in (b'some data to sign', 'some text to sign'):
        sig = priv.signString(data)
        assert sig[0] == FP_KEY_ASC
        assert pub.verifyString(data, sig) == pub.getTrustLevel()
        assert pub.verifyString(data, sig) != -1
        # tampered data
        assert pub.verifyString(b'tampered', sig) == -1
        # tampered timestamp
        assert pub.verifyString(data, (sig[0], sig[1] + 1, sig[2])) == -1

    kc2 = openpgpkey.OpenPGPKeyFileCache()
    kc2.setPrivatePath(archive('secring.gpg'))
    with pytest.raises(BadPassPhrase):
        kc2.getPrivateKey(FP_KEY_ASC, 'bad-passphrase')


def test_key_cache_dsa_sign_verify_string():
    kc = openpgpkey.OpenPGPKeyFileCache()
    kc.setPublicPath(keyring('pubringrev.gpg'))
    kc.setPrivatePath(keyring('secringrev.gpg'))
    pk = kc.getPublicKey('91E3E6C5')
    assert pk.isDSA()
    with pytest.raises(BadPassPhrase):
        kc.getPrivateKey('91E3E6C5', 'bad-passphrase')
    priv = kc.getPrivateKey('91E3E6C5', 'key32')
    sig = priv.signString(b'payload')
    assert pk.verifyString(b'payload', sig) != -1
    assert pk.verifyString(b'payloaD', sig) == -1


def test_public_keyring_add_and_lookup(tmp_path):
    ring = str(tmp_path / 'pubring.gpg')
    tsdb = str(tmp_path / 'tsdb')
    kr = openpgpfile.PublicKeyring(ring, tsdb)
    fps = kr.addKeysAsStrings([PUBKEYA4], timestamp=1234567)
    assert fps == ['A47FB129D45AC2472DFA5D59A8E762BF91E3E6C5']
    assert kr.getKeyTimestamp(fps[0]) == 1234567
    key = kr.getKey('91E3E6C5')
    assert key.getKeyFingerprint() == fps[0]
    # Adding the same key again merges rather than duplicating
    kr.addKeysAsStrings([PUBKEY4], timestamp=1234568)
    assert openpgpfile.countKeys(ring) == 1
    assert kr.getKeyTimestamp(fps[0]) == 1234568
    # Add a second key from a keyring file
    msg = openpgpfile.PGP_Message(archive('pubring.gpg'))
    kr.addKeys(msg.iterMainKeys())
    assert openpgpfile.countKeys(ring) > 1
    assert FP_KEY_ASC in openpgpfile.getFingerprints(ring)


def test_timestamp_packet_roundtrip():
    pkt = openpgpfile.KeyTimestampPacket(util.ExtendedStringIO())
    pkt.setKeyId('A47FB129D45AC2472DFA5D59A8E762BF91E3E6C5')
    pkt.setRefreshTimestamp(1700000000)
    pkt.rewriteBody()
    pkt.parse()
    assert pkt.getKeyId() == 'A8E762BF91E3E6C5'
    assert pkt.getRefreshTimestamp() == 1700000000


def test_no_pycrypto_imports():
    import subprocess
    out = subprocess.run(
        ['grep', '-rnE', r'^\s*(from|import)\s+Crypto(\.|\s|$)',
         os.path.join(ROOT, 'conary'), '--include=*.py'],
        capture_output=True, text=True)
    assert out.stdout == ''
