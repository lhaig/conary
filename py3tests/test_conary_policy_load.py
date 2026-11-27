"""The conary-policy modules in $CONARY_POLICY_PATH parse and import on
Python 3 through conary's own loader (util.loadSourceModule, the call
policy.loadPolicy makes), and policy.loadPolicy accepts them as a set.

devenv/run mounts ../conary-policy and sets CONARY_POLICY_PATH. Unset is a
failure, not a skip: without the mount every cook ends in SystemExit."""
import os
import sys
import types
import warnings

import pytest

from conary.build import policy
from conary.deps import deps
from conary.lib import util

# policy/*.py of conary-policy: a deleted or renamed module must fail too.
EXPECTED = [
    'autodoc', 'badfilecontents', 'badpathnames', 'bootstraptrovedeps',
    'eggrequires', 'enforcebuildreqs', 'group_versionconflicts', 'httpdconf',
    'lang', 'libraries', 'manifest', 'metadata', 'nonpackagefiles',
    'normalize', 'permissions', 'phprequires', 'pkgconfig',
    'resolvefiledeps', 'strip', 'stubs', 'symlinks', 'xinetd',
]
# internalPolicyModules of the package and derived recipe classes
INTERNAL = ('destdirpolicy', 'packagepolicy', 'derivedpolicy')


def policyDirs():
    path = os.environ.get('CONARY_POLICY_PATH')
    if not path:
        pytest.fail('CONARY_POLICY_PATH is unset: run through devenv/run with '
                    'a ../conary-policy checkout (or set CONARY_POLICY_SRC)')
    return [x for x in path.split(':') if x]


def policyFiles():
    files = []
    for d in policyDirs():
        assert os.path.isdir(d), d
        files.extend(os.path.join(d, f) for f in sorted(os.listdir(d))
                     if f.endswith('.py'))
    return files


@pytest.fixture(autouse=True)
def _restore_modules():
    before = set(sys.modules)
    yield
    for name in set(sys.modules) - before:
        del sys.modules[name]


def test_module_set_is_the_pinned_set():
    names = sorted(os.path.basename(f)[:-3] for f in policyFiles())
    assert names == EXPECTED


@pytest.mark.parametrize('name', EXPECTED)
def test_module_loads_through_loadSourceModule(name):
    fullpath = None
    for f in policyFiles():
        if os.path.basename(f) == name + '.py':
            fullpath = f
    assert fullpath, '%s.py not found in CONARY_POLICY_PATH' % name
    with warnings.catch_warnings():
        warnings.simplefilter('error', SyntaxWarning)
        m = util.loadSourceModule(name, fullpath)
    classes = [v for k, v in vars(m).items()
               if isinstance(v, type) and k[0].isupper()
               and issubclass(v, policy.BasePolicy) and v.__module__ == name]
    assert classes, 'no Policy subclass defined in %s' % fullpath


class _Cfg:
    def __init__(self, dirs):
        self.policyDirs = dirs
        self.defaultMacros = []


def test_loadPolicy_accepts_the_policy_set():
    # policies that need a database take it from recipe._db at init
    recipe = types.SimpleNamespace(cfg=_Cfg(policyDirs()), _db=object(),
        _buildFlavor=deps.Flavor())
    with warnings.catch_warnings():
        warnings.simplefilter('error', SyntaxWarning)
        pathMap, policies = policy.loadPolicy(
            recipe, internalPolicyModules=INTERNAL)
    assert sorted(os.path.basename(p)[:-3] for p in pathMap) == EXPECTED
    names = {type(p).__name__ for ps in policies.values() for p in ps}
    assert 'SharedLibrary' in names


@pytest.mark.parametrize('name', EXPECTED)
def test_module_has_no_undefined_names(name):
    # On Python 3.14+ (PEP 758) a leftover `except X, e:` parses and imports
    # as a tuple of exception types; only the undefined name `e` shows it.
    from pyflakes import api, messages, reporter

    class Collect(reporter.Reporter):
        def __init__(self):
            self.found = []

        def flake(self, msg):
            if isinstance(msg, messages.UndefinedName):
                self.found.append(str(msg))

        def syntaxError(self, filename, msg, lineno, offset, text):
            self.found.append('%s:%s: %s' % (filename, lineno, msg))

        def unexpectedError(self, filename, msg):
            self.found.append('%s: %s' % (filename, msg))

    fullpath = [f for f in policyFiles()
                if os.path.basename(f) == name + '.py']
    assert fullpath, '%s.py not found in CONARY_POLICY_PATH' % name
    rep = Collect()
    api.checkPath(fullpath[0], rep)
    assert rep.found == []
