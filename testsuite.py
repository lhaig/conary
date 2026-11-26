#!/usr/bin/python3
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

"""Thin wrapper around ``pytest conary_test``.

The environment setup that used to live in Suite.setupPaths (proxy
variables, sqlite check, rpm lock override) now lives in
conary_test/conftest.py, and sys.path is set up by pytest.ini.
Build the C extensions first: make -C conary/lib/ext && make -C conary_test
"""

import os
import sys


if __name__ == '__main__':
    import pytest
    sys.exit(pytest.main(
        [os.path.join(os.path.dirname(os.path.abspath(__file__)), 'conary_test')]
        + sys.argv[1:]))
