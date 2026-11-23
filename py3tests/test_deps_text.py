"""Dependency and flavor strings are text; bytes only at the stream boundary."""
import pytest

from conary.deps import deps


def test_parse_flavor_str_and_freeze_roundtrip():
    f = deps.parseFlavor('ssl,!krb is: x86_64')
    frz = f.freeze()
    assert isinstance(frz, str)
    assert deps.ThawFlavor(frz) == f
    assert deps.ThawFlavor(frz.encode('ascii')) == f
    assert str(deps.ThawFlavor(frz)) == str(f)


@pytest.mark.parametrize('bad', ['is: x86 use: é', 'use: café'])
def test_parse_flavor_rejects_non_ascii(bad):
    with pytest.raises(deps.ParseError):
        deps.parseFlavor(bad)
    with pytest.raises(deps.ParseError):
        deps.ThawFlavor(bad)


def test_dependency_set_roundtrip_non_ascii_names():
    ds = deps.DependencySet()
    ds.addDep(deps.FileDependencies, deps.Dependency('/usr/bin/café'))
    ds.addDep(deps.FileDependencies, deps.Dependency('/usr/bin/other'))
    thawed = deps.ThawDependencySet(ds.freeze())
    assert thawed == ds
    assert sorted(d.name for d in thawed.iterDepsByClass(deps.FileDependencies)) \
        == ['/usr/bin/café', '/usr/bin/other']
