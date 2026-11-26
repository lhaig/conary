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

import ctypes
import os

from testrunner import testhelp

class ChrootError(Exception):
    pass

def _loadLibcap():
    """Load libcap with typed prototypes; a missing library is ChrootError."""
    try:
        libcap = ctypes.cdll.LoadLibrary('libcap.so.2')
        libcap.cap_get_pid.argtypes = [ctypes.c_int]
        libcap.cap_get_pid.restype = ctypes.c_void_p
        libcap.cap_to_text.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        libcap.cap_to_text.restype = ctypes.c_void_p
        libcap.cap_free.argtypes = [ctypes.c_void_p]
        libcap.cap_free.restype = ctypes.c_int
    except (OSError, AttributeError) as err:
        raise ChrootError(str(err))
    return libcap


def _hasChrootCap(text):
    """True if the libcap text form (bytes) grants cap_sys_chroot."""
    return b'cap_sys_chroot' in text


def _probeChrootCapability():
    libcap = _loadLibcap()
    cap = libcap.cap_get_pid(os.getpid())
    if not cap:
        raise ChrootError('cap_get_pid failed')
    try:
        textPtr = libcap.cap_to_text(cap, None)
        if not textPtr:
            raise ChrootError('cap_to_text failed')
        try:
            return _hasChrootCap(ctypes.string_at(textPtr))
        finally:
            libcap.cap_free(textPtr)
    finally:
        libcap.cap_free(cap)


# singleton
chrootCapability = None
def requireChroot():
    global chrootCapability
    if chrootCapability is None:
        try:
            chrootCapability = _probeChrootCapability()
        except ChrootError:
            chrootCapability = False
            raise

    if chrootCapability is False:
        raise ChrootError

    return


def rpm(func):
    # mark the context as rpm
    testhelp.context('rpm')(func)

    def run(*args, **kwargs):
        try:
            __import__('rpm')
            requireChroot()
        except ImportError:
            raise testhelp.SkipTestException('RPM module not present')
        except ChrootError:
            raise testhelp.SkipTestException('"sudo setcap cap_sys_chroot=ep /usr/bin/python" to run RPM module tests')
        else:
            return func(*args, **kwargs)

    run.__name__ = func.__name__
    run._contexts = func._contexts

    return run

def installed_conarydb(func):
    # mark the context as installed_conarydb
    testhelp.context('installed_conarydb')(func)

    def run(*args, **kwargs):
        if os.path.exists('/var/lib/conarydb/conarydb'):
            return func(*args, **kwargs)
        else:
            raise testhelp.SkipTestException('Test requires system conary database')

    run.__name__ = func.__name__
    run._contexts = func._contexts

    return run
