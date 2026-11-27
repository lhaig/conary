"""Runtime Python 3 behaviour of conary-policy modules from
$CONARY_POLICY_PATH: dict views mutated while iterated, and file payload
rewrites in normalize.py done in bytes.

Each test loads the real module through util.loadSourceModule and calls the
real policy method; nothing copies the policy loop. Run under `python3 -bb`
so a bytes/str comparison raises instead of quietly returning False."""
import gzip
import os
import types

import pytest

from conary.build.macros import Macros
from conary.lib import util

import test_conary_policy_load as _load

policyFiles = _load.policyFiles
# the autouse fixture that drops modules a test loaded
_restore_modules = _load._restore_modules

# non-UTF-8 bytes: lone 0xff and Latin-1 e-acute
RAW = b'caf\xe9 \xff payload\n'


def loadPolicyModule(name):
    for f in policyFiles():
        if os.path.basename(f) == name + '.py':
            return util.loadSourceModule(name, f)
    raise AssertionError('%s.py not found in CONARY_POLICY_PATH' % name)


def makeMacros(**kw):
    m = Macros()
    m.update(kw)
    return m


def makePolicy(cls, macros, **recipeAttrs):
    recipe = types.SimpleNamespace(macros=macros, **recipeAttrs)
    p = cls(recipe)
    p.macros = macros
    return p


# ---- libraries.py: dirmap.keys() view grown inside test() -----------------

def test_libraries_test_expands_dirmap_on_lib64():
    mod = loadPolicyModule('libraries')
    macros = makeMacros(lib='lib64', prefix='/usr', libdir='/usr/lib64')
    p = makePolicy(mod.FixupMultilibPaths, macros)
    # policy.do() calls invariantsubtrees.extend(subtrees): needs a list
    assert isinstance(p.invariantsubtrees, list)
    assert p.test() is True
    assert p.dirmap['/usr/lib'] == '/usr/lib64'
    assert p.dirmap['/lib'] == '/lib64'


def test_libraries_test_is_a_noop_on_lib():
    mod = loadPolicyModule('libraries')
    macros = makeMacros(lib='lib', prefix='/usr', libdir='/usr/lib')
    p = makePolicy(mod.FixupMultilibPaths, macros)
    before = dict(p.dirmap)
    assert p.test() is False
    assert p.dirmap == before


# ---- badpathnames.py: invariantinclusions is a list ----------------------

def test_badpathnames_invariantinclusions_is_a_list(monkeypatch):
    mod = loadPolicyModule('badpathnames')
    from conary.build import policy
    seen = []
    monkeypatch.setattr(policy.EnforcementPolicy, 'doProcess',
        lambda self, recipe: seen.append(self.invariantinclusions))
    p = makePolicy(mod.NonLSBPaths, makeMacros())
    p.doProcess(p.recipe)
    assert isinstance(seen[0], list)
    assert sorted(seen[0]) == ['/usr/local', '/usr/usr']


# ---- enforcebuildreqs.py: openStanzas popped while iterated ----------------

def test_enforcebuildreqs_closing_a_stanza_does_not_mutate_during_iteration(
        tmp_path):
    mod = loadPolicyModule('enforcebuildreqs')
    builddir = str(tmp_path)
    macros = makeMacros(builddir=builddir, bindir='/usr/bin',
                        prefix='/usr', includedir='/usr/include')
    p = makePolicy(mod.EnforceConfigLogBuildRequirements, macros,
        ignoreDeps=False,
        autopkg=types.SimpleNamespace(components={}),
        cfg=types.SimpleNamespace(root='/nonexistent'))
    p.exceptions = None
    assert p.test() is True
    (tmp_path / 'config.log').write_bytes(
        b'configure:100: checking for foo\n'
        b'configure:101: result: no\n'
        b'configure:102: checking for bar\n'
        b'configure:103: result: no\n')
    p.doFile('/config.log')
    assert p.foundPaths == set()


# ---- normalize.py -----------------------------------------------------------

@pytest.fixture
def normalize():
    return loadPolicyModule('normalize')


def test_changeInterpLine_preserves_non_utf8_bytes(normalize, tmp_path):
    path = tmp_path / 'script'
    path.write_bytes(b'#!/usr/bin/env python\n' + RAW + b'\xff\xfe\n')
    p = makePolicy(normalize.NormalizeInterpreterPaths, makeMacros())
    p._changeInterpLine(str(path), '#!/usr/bin/python3\n')
    assert path.read_bytes() == b'#!/usr/bin/python3\n' + RAW + b'\xff\xfe\n'


def test_changeInterpLine_shrinking_leaves_no_garbage(normalize, tmp_path):
    path = tmp_path / 'script'
    path.write_bytes(b'#!/usr/bin/env python\n' + RAW)
    p = makePolicy(normalize.NormalizeInterpreterPaths, makeMacros())
    p._changeInterpLine(str(path), '#!/bin/x\n')
    assert path.read_bytes() == b'#!/bin/x\n' + RAW


def test_pam_config_rewrite_preserves_non_utf8_bytes(normalize, tmp_path):
    destdir = tmp_path
    (destdir / 'etc/pam.d').mkdir(parents=True)
    f = destdir / 'etc/pam.d/login'
    f.write_bytes(
        b'# caf\xe9 \xff\n'
        b'auth required /lib/security/$ISA/pam_unix.so\n'
        b'auth required pam_stack.so service=system-auth\n')
    p = makePolicy(normalize.NormalizePamConfig,
                   makeMacros(destdir=str(destdir)))
    p.doFile('/etc/pam.d/login')
    assert f.read_bytes() == (
        b'# caf\xe9 \xff\n'
        b'auth required pam_unix.so\n'
        b'auth  include system-auth\n')  # group 1 keeps its space


def test_python_interpreter_version_rewrite_preserves_bytes(normalize,
                                                           tmp_path):
    destdir = tmp_path
    (destdir / 'usr/bin').mkdir(parents=True)
    f = destdir / 'usr/bin/tool'
    f.write_bytes(b'#!/usr/bin/python\n' + RAW)
    macros = makeMacros(destdir=str(destdir))
    magic = {'/usr/bin/tool': types.SimpleNamespace(name='script',
        contents={'interpreter': '/usr/bin/python',
                  'line': '/usr/bin/python'})}
    p = makePolicy(normalize.NormalizePythonInterpreterVersion, macros,
                   magic=magic)
    p.versionMap = {'/usr/bin/python': '/usr/bin/python3.12'}
    p.preProcess()
    p.doFile('/usr/bin/tool')
    assert f.read_bytes() == b'#!/usr/bin/python3.12\n' + RAW
    assert '/usr/bin/tool' not in magic


@pytest.mark.parametrize('initdir,old', [
    ('/etc/init.d', b'/etc/rc.d/init.d'),
    ('/etc/rc.d/init.d', b'/etc/init.d'),
])
def test_initscript_rewrite_preserves_non_utf8_bytes(normalize, tmp_path,
                                                     initdir, old):
    destdir = tmp_path
    (destdir / 'etc/init.d').mkdir(parents=True)
    f = destdir / 'etc/init.d/svc'
    f.write_bytes(b'. ' + old + b'/functions\n' + RAW)
    requires = []
    macros = makeMacros(destdir=str(destdir), initdir=initdir)
    p = makePolicy(normalize.NormalizeInitscriptContents, macros,
        Requires=lambda *a: requires.append(a))
    p.doFile('/etc/init.d/svc')
    assert f.read_bytes() == (b'. ' + initdir.encode() + b'/functions\n'
                              + RAW)
    assert len(requires) == 1


def test_initscript_unmodified_is_not_rewritten(normalize, tmp_path):
    (tmp_path / 'etc/init.d').mkdir(parents=True)
    f = tmp_path / 'etc/init.d/svc'
    f.write_bytes(b'# nothing\n' + RAW)
    macros = makeMacros(destdir=str(tmp_path), initdir='/etc/init.d')
    p = makePolicy(normalize.NormalizeInitscriptContents, macros,
                   Requires=lambda *a: None)
    p.doFile('/etc/init.d/svc')
    assert f.read_bytes() == b'# nothing\n' + RAW


def test_manpages_do_over_a_tree_with_non_utf8_pages(normalize, tmp_path):
    destdir = tmp_path / 'dest'
    man1 = destdir / 'usr/share/man/man1'
    man1.mkdir(parents=True)
    dd = str(destdir)
    latin1 = b'.TH FOO 1\ncaf\xe9 ' + dd.encode() + b'/usr/bin/foo\n'
    (man1 / 'foo.1').write_bytes(latin1)
    # valid UTF-8 containing destdir
    (man1 / 'ok.1').write_bytes(
        'café /'.encode() + dd.lstrip('/').encode() + b'/x\n')
    # a .so redirect with a Latin-1 comment line before it
    (man1 / 'alias.1').write_bytes(b'.\\" caf\xe9\n.so man1/foo.1\n')
    # undecodable as UTF-8 but valid iso-8859-1 is the only fallback, so
    # every byte string decodes; \xff stays as U+00FF
    macros = makeMacros(destdir=dd, mandir='/usr/share/man',
                        x11prefix='/nonexistent-x11',
                        krbprefix='/nonexistent-krb')
    p = makePolicy(normalize.NormalizeManPages, macros,
                   recordMove=lambda *a: None)
    p.gzip = 'gzip'
    p.test()
    p.do()
    foo = gzip.open(str(man1 / 'foo.1.gz')).read()
    assert foo == ('.TH FOO 1\ncafé /usr/bin/foo\n').encode('utf-8')
    ok = gzip.open(str(man1 / 'ok.1.gz')).read()
    assert ok == 'café /x\n'.encode('utf-8')
    assert os.path.islink(str(man1 / 'alias.1.gz'))
    assert os.readlink(str(man1 / 'alias.1.gz')) == 'foo.1.gz'
