"""Binary ids and frozen blobs cross the XML-RPC wire as base64 text (str,
sent as <string>) and decode to the exact bytes on the server."""
import base64

import pytest

from conary.lib import util
from conary.repository import netclient, xmlshims
from conary.repository.netrepos import netserver

IDS = [b'\x00' * 20, b'\xff' * 20, bytes(range(20)), b'\x00\xff' * 10]


def _wire(arg):
    xml = util.xmlrpcDump((arg,), methodname='x')
    params, _ = util.xmlrpcLoad(xml)
    return xml, params[0]


def _assertStringOnWire(arg):
    assert isinstance(arg, str)
    xml, back = _wire(arg)
    text = xml.decode() if isinstance(xml, bytes) else xml
    assert '<string>' in text and '<base64>' not in text
    return back


def test_encode_fileids_round_trip():
    enc = netclient._encodeFileIds(IDS)
    back = _assertStringOnWire(enc)
    assert netserver._decodeFileIds(back) == set(IDS)


@pytest.mark.parametrize('arg', [None, '', b''])
def test_decode_empty(arg):
    assert netserver._decodeFileIds(arg) == set()


def test_decode_rejects_partial_id():
    with pytest.raises(AssertionError):
        netserver._decodeFileIds(base64.b64encode(b'x' * 21))


class _Server:
    def __init__(self):
        self.args = None

    def getProtocolVersion(self):
        return 62

    def getPackageBranchPathIds(self, *args):
        self.args = args
        return {}


class _Branch:
    def asString(self):
        return '/h@l:b'


def test_method_uses_helper():
    srv = _Server()
    client = netclient.NetworkRepositoryClient.__new__(
        netclient.NetworkRepositoryClient)
    client.c = {_Branch(): srv}
    br = list(client.c)[0]
    client.fromVersion = lambda v: v.asString()
    client.getPackageBranchPathIds('src', br, ['/a'], IDS)
    arg = srv.args[-1]
    assert netserver._decodeFileIds(_assertStringOnWire(arg)) == set(IDS)


class _Frozen:
    def __init__(self, data):
        self.data = data

    def freeze(self, skipSet=None):
        return self.data


@pytest.mark.parametrize('data', [b'\x00\xff\x80abc', 'éx', b''])
def test_b64text(data):
    enc = xmlshims.b64Text(data)
    back = _assertStringOnWire(enc)
    assert base64.b64decode(back) == (data if isinstance(data, bytes)
                                      else data.encode())


class _Rec:
    def __init__(self):
        self.calls = []

    def getProtocolVersion(self):
        return 100

    def __getattr__(self, name):
        def f(*a):
            self.calls.append((name, a))
            return 0
        return f


class _Ver:
    def __init__(self, host='h'):
        self.host = host

    def getHost(self):
        return self.host


def _client():
    client = netclient.NetworkRepositoryClient.__new__(
        netclient.NetworkRepositoryClient)
    client.fromVersion = lambda v: 'v'
    client.fromFlavor = lambda f: 'f'
    client.fromTroveTup = lambda t: t
    return client


def test_add_digital_signature_str_on_wire():
    rec = _Rec()
    ver = _Ver()
    client = _client()
    client.c = {ver: rec}
    client.addDigitalSignature('n', ver, None, _Frozen(b'\x00\xff\x01'))
    arg = rec.calls[0][1][-1]
    assert base64.b64decode(_assertStringOnWire(arg)) == b'\x00\xff\x01'


def test_add_metadata_items_str_on_wire():
    rec = _Rec()
    ver = _Ver()
    client = _client()
    client.c = {ver: rec, 'h': rec}

    class Item(_Frozen):
        def computeDigests(self):
            pass
    client.addMetadataItems([(('n', ver, None), Item(b'\x00\xff'))])
    arg = rec.calls[0][1][0][0][1]
    assert base64.b64decode(_assertStringOnWire(arg)) == b'\x00\xff'


@pytest.mark.parametrize('key', [b'\x00\xffkey', 'ascii'])
def test_add_new_pgp_key_str_on_wire(key):
    rec = _Rec()
    client = _client()
    client.c = {'l': rec}
    client.addNewPGPKey('l', 'u', key)
    arg = rec.calls[0][1][1]
    assert base64.b64decode(_assertStringOnWire(arg)) == (
        key if isinstance(key, bytes) else key.encode())


def test_set_trove_info_str_on_wire():
    rec = _Rec()
    ver = _Ver()
    client = _client()
    client.c = {'h': rec}
    client.setTroveInfo([(('n', ver, None), _Frozen(b'\x00\xffti'))])
    infoList = rec.calls[0][1][0]
    assert base64.b64decode(_assertStringOnWire(infoList[0][1])) == \
        b'\x00\xffti'
