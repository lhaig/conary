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
Access to telnetlib for the epdb remote debugger.

telnetlib was removed from the standard library in Python 3.13.  The remote
debugger subclasses telnetlib.Telnet, so where it is gone the module must
still import (it is imported by epdb), but the telnet client and server
refuse to start.  Where telnetlib exists it is used unchanged.
"""

try:
    import telnetlib
    from telnetlib import IAC, IP, SB, SE, DO, DONT, WILL, TM, NAWS
except ImportError:
    telnetlib = None
    # RFC 854 / RFC 1073 command bytes, the values telnetlib defines.
    IAC = bytes([255])
    DONT = bytes([254])
    DO = bytes([253])
    WILL = bytes([251])
    SB = bytes([250])
    SE = bytes([240])
    IP = bytes([244])
    TM = bytes([6])
    NAWS = bytes([31])

    class _Telnet(object):
        def __init__(self, *args, **kw):
            raise RuntimeError('the epdb telnet remote debugger needs '
                               'telnetlib, which was removed in Python 3.13')

    class _TelnetModule(object):
        Telnet = _Telnet

    telnetlib = _TelnetModule
