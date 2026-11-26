"""util.XMLRPCMarshaller / xmlrpcDump on Py3."""
import base64
import io
import xmlrpc.client

import pytest

from conary.lib import util


def _dump(value, **kw):
    return util.xmlrpcDump((value,), **kw)


def test_arbitrary_instance_key_in_dispatch():
    assert '_arbitrary_instance' in util.XMLRPCMarshaller.dispatch


@pytest.mark.parametrize('value, expected', [
    ('abc', '<value><string>abc</string></value>'),
    ('a<b&c', '<value><string>a&lt;b&amp;c</string></value>'),
    (util.ProtectedString('secret'), '<value><string>secret</string></value>'),
    (util.ProtectedTemplate('tmpl'), '<value><string>tmpl</string></value>'),
])
def test_ascii_string_goes_out_as_string(value, expected):
    assert expected in _dump(value)


def test_non_ascii_string_goes_out_as_base64():
    text = _dump('café')
    b64 = base64.b64encode('café'.encode('utf-8')).decode()
    assert b64 in text
    assert '<base64>' in text
    assert '<string>' not in text


def test_surrogate_escaped_string_sends_original_bytes():
    # A str decoded from raw bytes (os.fsdecode / sha1helper.toStr) must send
    # those raw bytes, which is what Py2 put on the wire.
    raw = b'abc\x80'
    text = _dump(raw.decode('utf-8', 'surrogateescape'))
    assert base64.b64encode(raw).decode() in text


def test_bytes_goes_out_as_base64():
    text = _dump(b'\x00\x01')
    assert '<base64>' in text
    assert base64.b64encode(b'\x00\x01').decode() in text


class _Plain:
    def __init__(self):
        self.a = 1
        self.b = 'x'


def test_plain_object_marshalled_as_struct():
    text = _dump(_Plain())
    assert '<struct>' in text
    assert '<name>a</name>' in text
    assert '<i4>1</i4>' in text or '<int>1</int>' in text


def test_str_subclass_not_in_dispatch_rejected():
    class Sub(str):
        pass
    with pytest.raises(TypeError, match='cannot marshal'):
        _dump(Sub('x'))


def test_object_without_dict_rejected():
    with pytest.raises(TypeError, match='cannot marshal'):
        _dump(object())


def test_dump_returns_text_without_stream():
    text = util.xmlrpcDump((1,))
    assert isinstance(text, str)
    assert text.startswith('<params>')


def test_dump_writes_to_stream():
    out = io.StringIO()
    assert util.xmlrpcDump(('x',), stream=out) == ''
    assert '<string>x</string>' in out.getvalue()


def test_methodname_wrapping():
    text = util.xmlrpcDump(('x',), methodname='proc')
    assert text.startswith("<?xml version='1.0'?>\n<methodCall>\n")
    assert '<methodName>proc</methodName>' in text
    assert text.endswith('</methodCall>\n')


def test_methodresponse_wrapping():
    text = util.xmlrpcDump(('x',), methodresponse=True)
    assert '<methodResponse>' in text
    assert text.endswith('</methodResponse>\n')


def test_fault_is_a_response():
    text = util.xmlrpcDump(xmlrpc.client.Fault(3, 'bad'))
    assert '<methodResponse>' in text
    assert '<fault>' in text
    assert '<int>3</int>' in text or '<i4>3</i4>' in text


def test_encoding_header():
    text = util.xmlrpcDump(('x',), methodresponse=True, encoding='latin-1')
    assert text.startswith("<?xml version='1.0' encoding='latin-1'?>\n")


@pytest.mark.parametrize('value', ['plain', 'café'])
def test_roundtrip_through_loads(value):
    text = util.xmlrpcDump((value,), methodresponse=True)
    params, _ = xmlrpc.client.loads(text)
    got = params[0]
    if isinstance(got, xmlrpc.client.Binary):
        got = got.data.decode('utf-8')
    assert got == value
