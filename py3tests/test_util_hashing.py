import base64
import hashlib
import io
import stat
import uuid

import pytest

from conary.lib import digestlib, util
from conary.conaryclient import filetypes


def _py2Id(node):
    sha = hashlib.sha256(str(node).encode('ascii'))
    return base64.b64encode(sha.hexdigest().encode('ascii')).decode('ascii')


def test_getid_default_is_str_stable(monkeypatch):
    monkeypatch.setattr(uuid, 'getnode', lambda: 123456789)
    a = util.SystemIdFactory(None).getId()
    b = util.SystemIdFactory(None).getId()
    assert isinstance(a, str)
    assert a == b == _py2Id(123456789)


def test_getid_cached_on_instance():
    f = util.SystemIdFactory(None)
    assert f.getId() is f.getId()


def test_getid_real_node_matches_formula():
    assert util.SystemIdFactory(None).getId() == _py2Id(uuid.getnode())


def test_getid_script(tmp_path):
    script = tmp_path / 'id.sh'
    script.write_text('#!/bin/sh\nprintf hello\n')
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    out = util.SystemIdFactory(str(script)).getId()
    assert isinstance(out, str)
    assert out == base64.b64encode(b'hello').decode('ascii')


@pytest.mark.parametrize('size,bufSize,sizeLimit', [
    (10, 128 * 1024, None),
    (1000, 64, None),
    (300000, 128 * 1024, None),
    (1000, 64, 500),
    (1000, 128 * 1024, 300),
])
def test_copyfileobj_digest(size, bufSize, sizeLimit):
    data = bytes(range(256)) * (size // 256 + 1)
    data = data[:size]
    src, dst = io.BytesIO(data), io.BytesIO()
    digest = digestlib.sha1()
    copied = util.copyfileobj(src, dst, digest=digest, bufSize=bufSize,
                              sizeLimit=sizeLimit)
    want = data[:sizeLimit] if sizeLimit else data
    assert copied == len(want)
    assert dst.getvalue() == want
    assert digest.hexdigest() == hashlib.sha1(want).hexdigest()


@pytest.mark.parametrize('contents', ['foo1', b'foo1', io.BytesIO(b'foo1')])
def test_regularfile_sha1(contents):
    pathId = b'\x01' * 16
    f = filetypes.RegularFile(contents=contents).get(pathId)
    assert f.contents.sha1() == hashlib.sha1(b'foo1').digest()
    assert f.contents.size() == 4
