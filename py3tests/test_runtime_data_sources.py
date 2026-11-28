"""Python data files conary loads at runtime from outside conary/ must parse.

config/components/*/*.py and the extensionless macro files are read through
util.loadSourceModule, but devenv/compile_check.sh does not cover them.
"""
import glob
import os
import sys
import types
import warnings

import pytest

from conary.build import packagepolicy

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COMPONENTS = os.path.join(ROOT, 'config', 'components')


def _globs(*patterns):
    out = []
    for pat in patterns:
        out.extend(sorted(glob.glob(os.path.join(ROOT, pat), recursive=True)))
    return [p for p in out
            if os.path.isfile(p) and os.path.basename(p) != 'Makefile']


LOCATIONS = [
    ('config/components', 24,
     ('config/components/*/*.py',)),
    ('config/macros', 2,
     ('config/macros', 'config/macros.solaris')),
    ('conary_test/archive/macros', 3,
     ('conary_test/archive/macros', 'conary_test/archive/macros.d/*')),
    ('conary_test/archive/components', 2,
     ('conary_test/archive/components/*/*.py',)),
]


@pytest.mark.parametrize('name,minimum,patterns', LOCATIONS,
                         ids=[x[0] for x in LOCATIONS])
def test_runtime_sources_parse(name, minimum, patterns):
    paths = _globs(*patterns)
    assert len(paths) >= minimum, paths
    for path in paths:
        with open(path, 'rb') as f:
            src = f.read()
        with warnings.catch_warnings():
            warnings.simplefilter('error', SyntaxWarning)
            compile(src, path, 'exec', dont_inherit=True)


class _Stub:
    loadFilterDirs = packagepolicy.ComponentSpec.loadFilterDirs
    loadFilter = packagepolicy.ComponentSpec.loadFilter

    def __init__(self):
        self.recipe = types.SimpleNamespace(
            cfg=types.SimpleNamespace(componentDirs=[COMPONENTS]))
        self.problems = []

    def warn(self, *args):
        self.problems.append(('warn', args))

    def error(self, *args):
        self.problems.append(('error', args))


def test_component_filters_load_through_real_loader():
    # loadSourceModule registers modules under bare names ('test', 'locale',
    # ...); restore sys.modules afterwards.
    saved = dict(sys.modules)
    try:
        stub = _Stub()
        stub.loadFilterDirs()
    finally:
        for key in list(sys.modules):
            if key not in saved:
                del sys.modules[key]
        sys.modules.update(saved)
    assert stub.problems == []
    assert ('config', ('%(sysconfdir)s/', None, 0o111)) in stub.baseFilters
