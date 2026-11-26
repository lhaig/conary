import os
import stat

import pytest

from conary.lib import util

needs_nonroot = pytest.mark.skipif(
    os.geteuid() == 0, reason='root ignores directory modes')


@pytest.fixture
def warnings(monkeypatch):
    seen = []
    monkeypatch.setattr(util.log, 'warning',
                        lambda msg, *a: seen.append(msg % a))
    return seen


def _mkfile(path, data='x'):
    with open(path, 'w') as f:
        f.write(data)


def test_plain_file(tmp_path):
    f = tmp_path / 'f'
    _mkfile(f)
    util.rmtree(str(f))
    assert not f.exists()
    assert tmp_path.exists()


def test_nested_dirs(tmp_path):
    root = tmp_path / 'a'
    (root / 'b' / 'c').mkdir(parents=True)
    _mkfile(root / 'b' / 'c' / 'f')
    _mkfile(root / 'g')
    util.rmtree(str(root))
    assert not root.exists()


@needs_nonroot
@pytest.mark.parametrize('mode', [0o000, 0o500])
def test_bad_modes(tmp_path, warnings, mode):
    root = tmp_path / 'a'
    sub = root / 'sub'
    deep = sub / 'deep'
    deep.mkdir(parents=True)
    _mkfile(deep / 'f')
    deep.chmod(mode)
    sub.chmod(mode)
    try:
        util.rmtree(str(root))
    finally:
        for p in (root, sub, deep):
            if p.exists():
                p.chmod(0o700)
    assert not root.exists()
    assert len(warnings) == 2
    assert all('illegal mode' in w for w in warnings)


@needs_nonroot
def test_symlink_inside_tree_not_followed(tmp_path):
    outside = tmp_path / 'outside'
    locked = outside / 'locked'
    locked.mkdir(parents=True)
    locked.chmod(0o500)
    root = tmp_path / 'root'
    root.mkdir()
    os.symlink(str(outside), str(root / 'link'))
    try:
        util.rmtree(str(root))
        assert not root.exists()
        assert locked.is_dir()
        assert stat.S_IMODE(locked.stat().st_mode) == 0o500
    finally:
        locked.chmod(0o700)


def test_toplevel_symlink(tmp_path):
    target = tmp_path / 'target'
    target.mkdir()
    _mkfile(target / 'f')
    link = tmp_path / 'link'
    os.symlink(str(target), str(link))
    util.rmtree(str(link))
    assert not os.path.lexists(link)
    assert (target / 'f').exists()


def test_dangling_symlink(tmp_path):
    link = tmp_path / 'link'
    os.symlink(str(tmp_path / 'nowhere'), str(link))
    util.rmtree(str(link))
    assert not os.path.lexists(link)


def test_globs(tmp_path):
    for n in ('a', 'b', 'c'):
        (tmp_path / n).mkdir()
        _mkfile(tmp_path / n / 'f')
    util.rmtree(str(tmp_path / '{a,b}'))
    assert not (tmp_path / 'a').exists()
    assert not (tmp_path / 'b').exists()
    assert (tmp_path / 'c').exists()
    util.rmtree(str(tmp_path / '*'))
    assert list(tmp_path.iterdir()) == []


def test_missing_path(tmp_path):
    missing = str(tmp_path / 'missing')
    with pytest.raises(OSError):
        util.rmtree(missing)
    util.rmtree(missing, ignore_errors=True)


def test_copytree_names_and_modes(tmp_path):
    src = tmp_path / 'src'
    (src / 'd').mkdir(parents=True)
    _mkfile(src / 'd' / 'f')
    _mkfile(src / 'g')
    dest = tmp_path / 'dest'
    dest.mkdir()
    names = util.copytree(str(src), str(dest), filemode=0o640, dirmode=0o750)
    base = str(dest / 'src')
    assert sorted(names) == sorted(
        [base + '/d', base + '/d/f', base + '/g'])
    assert stat.S_IMODE((dest / 'src').stat().st_mode) == 0o750
    # _copyVisit applies the modes to the source tree (existing behaviour)
    assert stat.S_IMODE((src / 'd').stat().st_mode) == 0o750
    assert stat.S_IMODE((src / 'g').stat().st_mode) == 0o640


def test_policy_do_walks_every_path(tmp_path):
    # Runs Policy.do itself, so the os.walk loop in policy.py is exercised.
    from conary.build import policy
    root = tmp_path / 'root'
    (root / 'a' / 'b').mkdir(parents=True)
    _mkfile(root / 'a' / 'b' / 'f')
    os.symlink(str(root / 'a'), str(root / 'ln'))

    class Fake:
        rootdir = str(root)
        recursive = True
        filetree = policy.DIR
        subtrees = None
        macros = {}
        _pathAllowed = lambda self, p: True
        doFile = lambda self, p: self.seen.append(p)
        walkDir = policy.Policy.walkDir
        do = policy.Policy.do

    f = Fake()
    f.seen = []
    f.invariantsubtrees = []
    f.do()
    # the symlink is reported but not followed into
    assert sorted(f.seen) == ['/a', '/a/b', '/a/b/f', '/ln']
