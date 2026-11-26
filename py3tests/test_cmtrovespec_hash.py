"""CMTroveSpec compares equal to plain tuples/TroveSpec on its first three
fields, so it must hash the same way."""

from conary import trovetup
from conary.conaryclient import cml


def _spec(name='foo'):
    return cml.CMTroveSpec(name, '1.0', None)


def test_hash_matches_plain_tuple():
    s = _spec()
    t = ('foo', '1.0', None)
    assert s == t
    assert hash(s) == hash(t)
    assert {s: 1}[t] == 1
    assert t in {s}


def test_hash_matches_trovespec():
    s = _spec()
    ts = trovetup.TroveSpec('foo', '1.0', None)
    assert s == ts
    assert hash(s) == hash(ts)
    assert ts in {s}


def test_pinned_does_not_change_hash():
    pinned = cml.CMTroveSpec('foo==1.0')
    assert pinned.pinned
    assert pinned == _spec()
    assert hash(pinned) == hash(_spec())


def test_different_specs_distinct_in_set():
    a = cml.CMTroveSpec('foo', '1.0', None)
    b = cml.CMTroveSpec('bar', '1.0', None)
    assert len({a, b}) == 2
