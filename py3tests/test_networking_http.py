"""networking.format and the plain-HTTP client stack on Python 3."""
import base64
import http.server
import io
import pickle
import socket
import threading

import pytest

from conary import conarycfg
from conary.lib import networking
from conary.lib.http import connection, opener, request


# --- networking.format ---

@pytest.mark.parametrize('text,useMask,expected', [
    ('10.1.2.3', None, '10.1.2.3'),
    ('10.1.2.3', True, '10.1.2.3/32'),
    ('10.1.2.3', False, '10.1.2.3'),
    ('10.0.0.0/8', None, '10.0.0.0/8'),
    ('10.0.0.0/8', True, '10.0.0.0/8'),
    ('10.0.0.0/8', False, '10.0.0.0'),
    ('2001:db8::1', None, '2001:db8::1'),
    ('2001:db8::1', True, '2001:db8::1/128'),
    ('2001:db8::1', False, '2001:db8::1'),
    ('2001:db8::/32', None, '2001:db8::/32'),
    ('2001:db8::/32', False, '2001:db8::'),
])
def test_format(text, useMask, expected):
    addr = networking.BaseAddress.parse(text)
    assert addr.format(useMask) == expected
    assert isinstance(addr.format(useMask), str)


@pytest.mark.parametrize('text', ['10.1.2.3', '10.0.0.0/8', '2001:db8::/32'])
def test_str_repr_pickle(text):
    addr = networking.BaseAddress.parse(text)
    assert str(addr) == addr.format()
    assert text.split('/')[0] in repr(addr)
    clone = pickle.loads(pickle.dumps(addr))
    assert clone == addr
    assert clone.format(True) == addr.format(True)


# --- HTTPHeaders ---

def test_headers_items():
    hdrs = request.HTTPHeaders({'x-foo': 'a', 'Content-type': 'b'})
    assert sorted(hdrs.items()) == [('Content-Type', 'b'), ('X-Foo', 'a')]
    assert sorted(hdrs.iteritems()) == sorted(hdrs.items())


# --- Basic auth ---

class FakeConn:
    def __init__(self):
        self.headers = []
        self.sent = []

    def putrequest(self, *a, **kw):
        pass

    def putheader(self, key, value):
        self.headers.append((key, value))

    def endheaders(self):
        pass

    def send(self, data):
        self.sent.append(data)


@pytest.mark.parametrize('user,password', [
    ('alice', 'secret'),
    ('böb', 'päss:word'),
])
def test_send_request_basic_auth(user, password):
    # Build the URL with the real credentials without URL-quoting concerns.
    url = request.URL('http', (user, password),
                      networking.HostPort('example.com', 80), '/x')
    req = request.Request(url)
    conn = FakeConn()
    req.sendRequest(conn)
    auth = dict(conn.headers)['Authorization']
    assert isinstance(auth, str)
    assert auth.startswith('Basic ')
    raw = base64.b64decode(auth[6:])
    assert raw == ('%s:%s' % (user, password)).encode('utf-8')


class FakeReq:
    def __init__(self):
        self.headers = request.HTTPHeaders()
        self.abortCheck = None

    def sendRequest(self, conn, isProxied=False):
        raise StopIteration


def test_request_once_proxy_auth_header():
    conn = connection.Connection.__new__(connection.Connection)
    conn.proxy = type('P', (), {'userpass': ('carol', 'pw')})()
    conn.doTunnel = False
    req = FakeReq()
    with pytest.raises(connection.http_error.RequestError):
        conn.requestOnce(None, req)
    value = req.headers['Proxy-Authorization']
    assert isinstance(value, str)
    assert base64.b64decode(value[6:]) == b'carol:pw'


# --- startTunnel ---

class FakeSock:
    def __init__(self, reply):
        self.sent = b''
        self._reply = io.BytesIO(reply)

    def sendall(self, data):
        assert isinstance(data, bytes)
        self.sent += data

    def makefile(self, mode='r', *a, **kw):
        return self._reply


def _tunnelConn(userpass):
    conn = connection.Connection.__new__(connection.Connection)
    conn.doTunnel = True
    conn.endpoint = type('E', (), {
        'hostport': networking.HostPort('example.com', 443)})()
    conn.userAgent = 'ua/1'
    conn.proxy = type('P', (), {'userpass': userpass,
                                '__str__': lambda s: 'proxy'})()
    return conn


def test_start_tunnel_bytes():
    sock = FakeSock(b'HTTP/1.0 200 OK\r\n\r\n')
    conn = _tunnelConn(('dave', 'pw'))
    assert conn.startTunnel(sock) is sock
    lines = sock.sent.split(b'\r\n')
    assert lines[0].startswith(b'CONNECT ')
    assert b'User-Agent: ua/1' in lines
    token = base64.b64encode(b'dave:pw')
    assert b'Proxy-Authorization: Basic ' + token in lines
    assert sock.sent.endswith(b'\r\n\r\n')


def test_start_tunnel_error_status():
    sock = FakeSock(b'HTTP/1.0 403 Forbidden\r\n\r\n')
    conn = _tunnelConn((None, None))
    with pytest.raises(socket.error):
        conn.startTunnel(sock)
    assert b'Proxy-Authorization' not in sock.sent


# --- ResponseWrapper ---

class FakeResponse:
    status = 200
    reason = 'OK'
    msg = {}
    version = 11

    def getheader(self, *a):
        return None

    def close(self):
        pass


def _wrapper(data):
    return opener.ResponseWrapper(io.BytesIO(data), FakeResponse())


def test_response_wrapper_readline_iter():
    w = _wrapper(b'one\ntwo\nthree')
    assert w.readline() == b'one\n'
    assert list(w) == [b'two\n', b'three']
    assert w.readline() == b''


@pytest.mark.parametrize('count,expected', [
    (None, b'ab\ncdef'), (3, b'ab\n'), (100, b'ab\ncdef')])
def test_response_wrapper_read(count, expected):
    assert _wrapper(b'ab\ncdef').read(count) == expected


def test_response_wrapper_read_after_readline():
    w = _wrapper(b'ab\ncdef')
    assert w.readline() == b'ab\n'
    assert w.read(2) == b'cd'
    assert w.read() == b'ef'


# --- cfg.readUrl end to end ---

def test_cfg_read_url_end_to_end():
    seen = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            seen.append(dict(self.headers))
            body = b'proxy http://localhost:1234/\n'
            self.send_response(200)
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(('127.0.0.1', 0), Handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        c = conarycfg.ConaryConfiguration(readConfigFiles=False)
        c.readUrl('http://127.0.0.1:%d/conf' % srv.server_address[1])
    finally:
        srv.shutdown()
        srv.server_close()
    assert seen
    assert 'X-Conary-Version' in seen[0]
    assert 'X-Conary-Config-Version' in seen[0]
    assert c.proxy
    assert 'localhost' in str(c.proxy)
