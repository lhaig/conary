#
# Copyright (c) SAS Institute Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

"""
Digest helpers.

Rule: sha1String, md5String and nonstandardSha256String take bytes unchanged
and also accept str, which is encoded with C{encode('utf-8',
'surrogateescape')} (the bytes os.fsencode gives on Linux).  Any other type
raises TypeError.  Many callers hash text (paths, cache keys, joined
fingerprints) and pathIds and fingerprints are persisted identities that
Python 2 computed over the UTF-8 or on-disk bytes of that text, so this
encoding reproduces the Python 2 digests, and surrogateescape keeps
undecodable file names hashing the same as their on-disk bytes.  Callers that
build the input with "%s" or str() must make sure no operand is bytes, since
that renders as "b'...'".

digestlib is a plain hashlib re-export and is not wrapped: its direct callers
must pass bytes.
"""

import os
import stat
import struct

from conary.lib import digestlib

def sha1FileBin(path):
    oldmode = None
    mode = os.lstat(path)[stat.ST_MODE]
    if (mode & 0o400) != 0o400:
        oldmode = mode
        os.chmod(path, mode | 0o400)

    fd = os.open(path, os.O_RDONLY)
    if oldmode is not None:
        os.chmod(path, oldmode)

    m = digestlib.sha1()
    buf = os.read(fd, 40960)
    while len(buf):
        m.update(buf)
        buf = os.read(fd, 40960)
    os.close(fd)

    return m.digest()

def toBytes(buf):
    """Return buf as bytes under the module rule: str is UTF-8 encoded with
    surrogateescape, bytes-like passes through, anything else is a TypeError."""
    if isinstance(buf, str):
        return buf.encode('utf-8', 'surrogateescape')
    if isinstance(buf, (bytes, bytearray, memoryview)):
        return buf
    raise TypeError('cannot hash %s, expected bytes or str'
                    % type(buf).__name__)

def sha1String(buf):
    m = digestlib.sha1()
    m.update(toBytes(buf))
    return m.digest()

def sha1ToString(buf):
    assert(len(buf) == 20)
    return "%08x%08x%08x%08x%08x" % struct.unpack("!5I", buf)

def sha1FromString(val):
    assert(len(val) == 40)
    return struct.pack("!5I", int(val[ 0: 8], 16),
                        int(val[ 8:16], 16), int(val[16:24], 16),
                        int(val[24:32], 16), int(val[32:40], 16))

sha1Empty = b'\xda9\xa3\xee^kK\r2U\xbf\xef\x95`\x18\x90\xaf\xd8\x07\t'


def nonstandardSha256String(buf):
    return digestlib.sha256_nonstandard(toBytes(buf))

def sha256ToString(buf):
    assert(len(buf) == 32)
    return "%08x%08x%08x%08x%08x%08x%08x%08x" % struct.unpack("!8I", buf)

def sha256FromString(val):
    assert(len(val) == 64)
    return struct.pack("!8I", int(val[ 0: 8], 16),
                        int(val[ 8:16], 16), int(val[16:24], 16),
                        int(val[24:32], 16), int(val[32:40], 16),
                        int(val[40:48], 16), int(val[48:56], 16),
                        int(val[56:64], 16) )

def md5String(buf):
    m = digestlib.md5()
    m.update(toBytes(buf))
    return m.digest()

def md5ToString(buf):
    assert(len(buf) == 16)
    return "%08x%08x%08x%08x" % struct.unpack("!4I", buf)

def md5FromString(val):
    assert(len(val) == 32)
    return struct.pack("!4I", int(val[ 0: 8], 16),
                        int(val[ 8:16], 16), int(val[16:24], 16),
                        int(val[24:32], 16))
