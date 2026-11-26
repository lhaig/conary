"""Arch detection: aarch64 and x86_64 load from arch data files.

conary/build/use.py holds no per-arch definitions. ArchCollection._setArch only
finds major arches that flavorcfg loaded from archDirs, so a missing data file
shows up as 'No Such Arch <name>'.
"""
import os
import shutil

import pytest

from conary import conarycfg
from conary.build import use
from conary.deps import arch, deps

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEST_USE = os.path.join(ROOT, 'conary_test', 'archive', 'use')
ARCH_DIRS = {
    'conary_test': os.path.join(ROOT, 'conary_test', 'archive', 'arch'),
    'config': os.path.join(ROOT, 'config', 'arch'),
}
USE_DIRS = {
    'conary_test': TEST_USE,
    'config': os.path.join(ROOT, 'config', 'use'),
}


def _copyWithoutMakefile(src, dst):
    # config/ directories carry a Makefile that the flavor config parser rejects.
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns('Makefile'))
    return str(dst)


@pytest.fixture(autouse=True)
def restore_arch_state():
    saved = (arch.baseArch, arch.currentArch)
    use.clearFlags()
    yield
    arch.baseArch, arch.currentArch = saved
    use.clearFlags()


def _load(machine, archDir, useDir):
    arch.baseArch = machine
    arch.currentArch = [[deps.Dependency(machine)]]
    arch.initializeArch()
    cfg = conarycfg.ConaryConfiguration(False)
    cfg.useDirs = [useDir]
    cfg.archDirs = [archDir]
    cfg.initializeFlavors()
    use.setBuildFlagsFromFlavor('', cfg.buildFlavor, error=False)
    return cfg


@pytest.fixture(params=sorted(ARCH_DIRS))
def dirs(request, tmp_path):
    src = request.param
    return (_copyWithoutMakefile(ARCH_DIRS[src], tmp_path / 'arch'),
            _copyWithoutMakefile(USE_DIRS[src], tmp_path / 'use'))


@pytest.mark.parametrize('machine', ['aarch64', 'x86_64'])
def test_current_major_arch(machine, dirs):
    _load(machine, *dirs)
    cur = use.Arch.getCurrentArch()
    assert cur._name == machine
    assert use.Arch[machine]._get() is True
    assert use.Arch.bits64 is True
    assert use.Arch.bits32 is False
    assert use.Arch.LE is True
    assert use.Arch.BE is False


@pytest.mark.parametrize('machine', ['aarch64', 'x86_64'])
def test_flavor_string_round_trips(machine, dirs):
    _load(machine, *dirs)
    isDep = use.Arch.getCurrentArch()._toDependency()
    if machine == 'aarch64':
        assert str(isDep) == 'is: aarch64'
    assert str(deps.parseFlavor(str(isDep))) == str(isDep)
    assert machine in str(isDep)


def test_missing_data_file_still_raises(tmp_path):
    archDir = tmp_path / 'arch'
    _copyWithoutMakefile(ARCH_DIRS['config'], archDir)
    (archDir / 'aarch64').unlink(missing_ok=True)
    useDir = _copyWithoutMakefile(USE_DIRS['config'], tmp_path / 'use')
    with pytest.raises(AttributeError, match='No Such Arch aarch64'):
        _load('aarch64', str(archDir), useDir)


def test_state_is_restored_between_tests():
    # The autouse fixture restores arch.baseArch; a leaked 'aarch64' from a
    # neighbouring test would be a pollution bug.
    import os as _os
    assert arch.baseArch == _os.uname()[4]
