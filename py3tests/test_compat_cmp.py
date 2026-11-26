"""compat.cmp and CmpMixin replace the Python 2 cmp() builtin and __cmp__."""
import functools

import pytest

from conary.lib import compat
from conary.lib.compat import CmpMixin, cmp


@pytest.mark.parametrize('a, b, expected', [
    (1, 2, -1), (2, 1, 1), (3, 3, 0),
    ('a', 'b', -1), ('b', 'a', 1), ('a', 'a', 0),
    ((1, 2), (1, 3), -1), ((1, 3), (1, 2), 1), ((1, 2), (1, 2), 0),
    ((1,), (1, 0), -1), ([], [], 0),
    (1.5, 2, -1),
])
def test_cmp_values(a, b, expected):
    assert cmp(a, b) == expected


@pytest.mark.parametrize('a, b, expected', [
    (None, None, 0), (None, 0, -1), (0, None, 1),
    (None, 'a', -1), ('a', None, 1),
])
def test_cmp_none_sorts_first(a, b, expected):
    assert cmp(a, b) == expected


def test_cmp_none_in_stable_sort():
    items = [(2, 'b'), (None, 'n1'), (1, 'a'), (None, 'n2'), (2, 'c')]
    got = sorted(items, key=functools.cmp_to_key(
        lambda x, y: cmp(x[0], y[0])))
    # Python 2: None first, ties keep their original order
    assert got == [(None, 'n1'), (None, 'n2'), (1, 'a'), (2, 'b'), (2, 'c')]


def test_cmp_unorderable_still_raises():
    with pytest.raises(TypeError):
        cmp(1, 'a')


class _Num(CmpMixin):
    def __init__(self, n):
        self.n = n

    def __cmp__(self, other):
        if not isinstance(other, _Num):
            return NotImplemented
        return cmp(self.n, other.n)

    def __eq__(self, other):
        return isinstance(other, _Num) and self.n == other.n

    def __hash__(self):
        return hash(self.n)


def test_mixin_ordering():
    a, b, c = _Num(1), _Num(2), _Num(2)
    assert a < b and a <= b and b > a and b >= a
    assert b <= c and b >= c
    assert not b < c and not b > c
    assert sorted([b, a, c]) == [a, b, c]
    assert max([a, b]) is b


def test_mixin_keeps_eq_and_hash():
    assert _Num(1) == _Num(1)
    assert _Num(1) != _Num(2)
    assert hash(_Num(5)) == hash(5)
    assert len({_Num(1), _Num(1), _Num(2)}) == 2


def test_mixin_notimplemented_gives_typeerror():
    with pytest.raises(TypeError):
        _Num(1) < 5


def test_mixin_does_not_define_equality():
    assert '__eq__' not in vars(CmpMixin)
    assert '__ne__' not in vars(CmpMixin)
    assert '__hash__' not in vars(CmpMixin)


def test_mixin_adds_no_instance_dict():
    class Slotted(CmpMixin):
        __slots__ = ('x',)
    assert not hasattr(Slotted(), '__dict__')


def test_module_exports():
    assert compat.cmp is cmp
