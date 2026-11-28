"""conary_test's StatWrapper (sourcetest/shadowtest fake-owner stat) must
accept the keyword arguments the stdlib passes, e.g. shutil.rmtree's
os.lstat(name, dir_fd=fd); otherwise a patched os.lstat breaks teardown."""
import os
import shutil

from conary_test.cvctest.sourcetest import StatWrapper


def test_lstat_and_stat_accept_dir_fd(tmp_path):
    (tmp_path / 'f').write_text('x')
    w = StatWrapper(os.stat, os.lstat, 7, 8)
    fd = os.open(tmp_path, os.O_RDONLY)
    try:
        for fn in (w.lstat, w.stat):
            sb = fn('f', dir_fd=fd)
            assert (sb.st_uid, sb.st_gid) == (7, 8)
    finally:
        os.close(fd)


def test_rmtree_with_patched_lstat(tmp_path, monkeypatch):
    d = tmp_path / 'tree'
    (d / 'sub').mkdir(parents=True)
    (d / 'sub' / 'f').write_text('x')
    w = StatWrapper(os.stat, os.lstat, os.getuid(), os.getgid())
    monkeypatch.setattr(os, 'lstat', w.lstat)
    monkeypatch.setattr(os, 'stat', w.stat)
    shutil.rmtree(d)
    assert not d.exists()
