"""devenv/policy_src.sh: resolves the conary-policy checkout for devenv/run
and conary_test_baseline.sh. Run through bash, as the scripts source it."""
import os
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HELPER = os.path.join(ROOT, 'devenv', 'policy_src.sh')

SNIPPET = ('. "$1"; for a in ${policy_args[@]+"${policy_args[@]}"}; do'
           ' echo "arg=$a"; done; echo "head=$policy_head"')


def source(root, **env):
    full = {'PATH': os.environ['PATH']}
    full.update(env)
    return subprocess.run(
        ['bash', '-c', 'set -eu; ROOT=$2; ' + SNIPPET, 'bash', HELPER,
         str(root)], env=full, capture_output=True, text=True)


@pytest.fixture
def layout(tmp_path):
    root = tmp_path / 'conary'
    root.mkdir()
    return tmp_path, root


def mkpolicy(path):
    (path / 'policy').mkdir(parents=True)
    return path


def test_default_present(layout):
    base, root = layout
    pol = mkpolicy(base / 'conary-policy')
    r = source(root)
    assert r.returncode == 0, r.stderr
    real = os.path.realpath(pol)
    assert r.stdout.splitlines() == [
        'arg=-v', 'arg=%s:/policy:ro' % real, 'arg=-e',
        'arg=CONARY_POLICY_PATH=/policy/policy', 'head=unknown']


def test_default_absent_runs_with_one_stderr_line(layout):
    base, root = layout
    r = source(root)
    assert r.returncode == 0
    assert r.stdout.splitlines() == ['head=absent']
    assert len(r.stderr.strip().splitlines()) == 1


def test_override_used(layout):
    base, root = layout
    pol = mkpolicy(base / 'elsewhere')
    mkpolicy(base / 'conary-policy')
    r = source(root, CONARY_POLICY_SRC=str(pol))
    assert r.returncode == 0, r.stderr
    assert 'arg=%s:/policy:ro' % os.path.realpath(pol) in r.stdout.splitlines()


@pytest.mark.parametrize('name', ['missing', 'a:b', 'a,b', 'a b'])
def test_bad_override_exits_2(layout, name):
    base, root = layout
    mkpolicy(base / 'conary-policy')
    target = base / name
    if name == 'missing':
        pass
    else:
        mkpolicy(target)
    r = source(root, CONARY_POLICY_SRC=str(target))
    assert r.returncode == 2, (r.stdout, r.stderr)
    assert r.stdout == ''
    assert r.stderr.strip()


def test_override_without_policy_dir_exits_2(layout):
    base, root = layout
    (base / 'empty').mkdir()
    r = source(root, CONARY_POLICY_SRC=str(base / 'empty'))
    assert r.returncode == 2
