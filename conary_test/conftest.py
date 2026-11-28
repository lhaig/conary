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

"""pytest setup for conary_test.

sys.path (repo root and testharness/) is set by pytest.ini, because
conary_test/__init__.py imports testrunner before this file is loaded.
The C extensions are built explicitly, not here:
    make -C conary/lib/ext && make -C conary_test
"""

import os
import sqlite3
import sys
import warnings

import pytest

# Modules that cannot be collected yet, each with the reason.
collect_ignore = []

# Some transport tests are affected by proxy environment settings
for _transport in ('http', 'https', 'ftp', 'all', 'no'):
    os.environ.pop('%s_proxy' % _transport, None)
    os.environ.pop('%s_PROXY' % _transport, None)

if sqlite3.sqlite_version_info < (3, 7, 0):
    warnings.warn("the system sqlite3 is linked against a too-old system "
            "sqlite that is known to have bugs affecting the repository.")

# Turn off rpm locking via a DSO override. The handle must stay referenced or
# dlclose() is called on it. RPM keeps the lock file location in a global, so
# without the override only one root directory can be used per process. This
# has to happen before anything imports rpm.
_norpmlock_handle = None
_so = os.path.join(os.path.dirname(os.path.abspath(__file__)), '_norpmlock.so')
if os.path.exists(_so):
    if 'rpm._rpm' in sys.modules:
        warnings.warn("rpm was imported before the norpmlock override could "
                "be loaded; rpm locking is not disabled")
    else:
        try:
            from conary_test import norpmlock
            _norpmlock_handle = norpmlock.open(_so)
        except (ImportError, RuntimeError) as err:
            warnings.warn("could not load the norpmlock override: %s" % err)


_runnerPid = os.getpid()


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_protocol(item, nextitem):
    """Backstop for testhelp.TestCase._callTestMethod: a process forked
    during a test (cook's child) that gets back into the runner, e.g. from
    setUp, must not run further tests or write the junit file."""
    yield
    if os.getpid() != _runnerPid:
        for f in (sys.stdout, sys.stderr):
            try:
                f.flush()
            except Exception:   # closed or redirected stream
                pass
        os._exit(1)


def pytest_collection_modifyitems(config, items):
    """Map testhelp.context tags (func._contexts) to pytest markers."""
    registered = set()
    for item in items:
        tags = list(getattr(getattr(item, 'obj', None), '_contexts', ()))
        tags += getattr(getattr(item, 'cls', None), '_contexts', ())
        for tag in tags:
            if tag not in registered:
                registered.add(tag)
                config.addinivalue_line(
                    'markers', '%s: testhelp.context tag' % tag)
            item.add_marker(tag)
