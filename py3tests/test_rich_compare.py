"""Classes that only defined Python 2 __cmp__ must order and sort on Python 3."""
import functools
import importlib.util
import os

import pytest

from conary import trove, versions
from conary.dbstore import sqllib
from conary.deps import deps
from conary.lib.compat import CmpMixin, cmp


def _ver(s, stamp):
    v = versions.VersionFromString(s).copy()
    for rev in v.versions:
        if isinstance(rev, versions.Revision):
            rev.timeStamp = stamp
    v.hash = None
    v.strRep = None
    return v


def _py2sorted(items):
    return sorted(items, key=functools.cmp_to_key(lambda a, b: a.__cmp__(b)))


# --- SerialNumber --------------------------------------------------------

def test_serialnumber_order():
    s = [versions.SerialNumber(x) for x in ('1.10', '1.2', '1', '1.2.1', '0')]
    assert [str(x) for x in sorted(s)] == ['0', '1', '1.2', '1.2.1', '1.10']


def test_serialnumber_eq_hash_unchanged():
    a, b = versions.SerialNumber('1.2'), versions.SerialNumber('1.2')
    assert a == b and not a != b
    assert a <= b and a >= b and not a < b
    assert hash(a) == hash(b)
    assert len({a, b, versions.SerialNumber('1.3')}) == 2


def test_serialnumber_other_class_not_orderable():
    with pytest.raises(TypeError):
        versions.SerialNumber('1') < 3


# --- Revision / Version --------------------------------------------------

def test_revision_sorts_by_timestamp():
    r1 = versions.Revision('1.0-1-1'); r1.timeStamp = 30.0
    r2 = versions.Revision('1.0-1-2'); r2.timeStamp = 10.0
    r3 = versions.Revision('2.0-1-1'); r3.timeStamp = 20.0
    assert sorted([r1, r2, r3]) == [r2, r3, r1]
    assert r2 < r3 < r1
    assert r1 >= r3 and r1 > r2


def test_revision_tie_and_equality():
    r1 = versions.Revision('1.0-1-1'); r1.timeStamp = 5.0
    r2 = versions.Revision('1.0-1-2'); r2.timeStamp = 5.0
    # same timestamp: neither less, == still compares content
    assert not r1 < r2 and not r2 < r1
    assert r1 <= r2 and r1 >= r2
    assert r1 != r2
    assert sorted([r2, r1]) == [r2, r1]      # stable on ties
    assert hash(r1) == hash(versions.Revision('1.0-1-1'))


def test_revision_vs_other_class():
    r = versions.Revision('1.0-1-1'); r.timeStamp = 1.0
    with pytest.raises(TypeError):
        r < 'x'


def test_version_sorts_by_timestamp():
    a = _ver('/a.b@c:d/1.0-1-1', 30.0)
    b = _ver('/a.b@c:d/1.0-1-2', 10.0)
    c = _ver('/a.b@c:d/1.0-1-3', 20.0)
    assert sorted([a, b, c]) == [b, c, a]
    assert b < c < a
    assert a == a.copy()
    assert hash(a) == hash(a.copy())
    assert max([a, b, c]) is a


def test_version_tie_keeps_order_and_ne():
    a = _ver('/a.b@c:d/1.0-1-1', 7.0)
    b = _ver('/a.b@c:d/1.0-1-2', 7.0)
    assert not a < b and not b < a and a <= b
    assert a != b
    assert sorted([b, a]) == [b, a]


def test_version_vs_branch_not_orderable():
    v = _ver('/a.b@c:d/1.0-1-1', 1.0)
    br = versions.VersionFromString('/a.b@c:d')
    with pytest.raises(TypeError):
        v < br


# --- deps ----------------------------------------------------------------

def test_dependency_order_name_then_flags():
    a = deps.Dependency('a')
    b = deps.Dependency('b')
    a_x = deps.Dependency('a', [('x', deps.FLAG_SENSE_REQUIRED)])
    assert a < b and b > a
    assert a < a_x            # no flags sorts before flags
    assert sorted([b, a_x, a]) == [a, a_x, b]
    assert a == deps.Dependency('a')
    assert hash(a) == hash(deps.Dependency('a'))


def test_dependency_tie_is_equal_cmp():
    a = deps.Dependency('a', [('x', 1)])
    b = deps.Dependency('a', [('x', 1)])
    assert a <= b and a >= b and not a < b and a == b


def test_dependency_class_order():
    def cls(*names):
        dc = deps.InstructionSetDependency()
        for n in names:
            dc.addDep(deps.Dependency(n))
        return dc
    assert cls('x86') < cls('x86', 'x86_64')   # prefix sorts first
    assert cls('x86') < cls('x86_64')
    assert cls('x86') <= cls('x86') and cls('x86') >= cls('x86')
    assert sorted([cls('x86_64'), cls('x86')])[0] == cls('x86')


FLAVORS = ['is: x86', 'is: x86 x86_64', 'is: x86_64',
           'use: foo is: x86', 'use: foo', 'is: ppc']


def test_flavor_sorted_matches_py2_cmp():
    flavors = [deps.parseFlavor(x) for x in FLAVORS]
    assert sorted(flavors) == _py2sorted(flavors)


@pytest.mark.parametrize('a', FLAVORS)
@pytest.mark.parametrize('b', FLAVORS)
def test_flavor_operators_agree_with_cmp(a, b):
    fa, fb = deps.parseFlavor(a), deps.parseFlavor(b)
    c = fa.__cmp__(fb)
    assert (fa < fb) == (c < 0)
    assert (fa <= fb) == (c <= 0)
    assert (fa > fb) == (c > 0)
    assert (fa >= fb) == (c >= 0)
    # __eq__ / __hash__ are the pre-existing ones, not derived from __cmp__
    assert (fa == fb) == (a == b)
    if a == b:
        assert hash(fa) == hash(fb)


def test_flavor_missing_class_sorts_per_py2():
    # __cmp__: a tag only in self -> -1, only in other -> 1
    isOnly = deps.parseFlavor('is: x86')
    useOnly = deps.parseFlavor('use: foo')
    assert isOnly.__cmp__(useOnly) == -useOnly.__cmp__(isOnly)
    assert (isOnly < useOnly) == (isOnly.__cmp__(useOnly) < 0)


def test_dependency_set_vs_none():
    ds = deps.parseDep('trove: foo')
    assert ds.__cmp__(None) == -1
    assert ds < None
    assert not ds > None


def test_dependency_set_hashable_and_eq():
    a = deps.parseFlavor('is: x86')
    b = deps.parseFlavor('is: x86')
    assert a == b and hash(a) == hash(b)
    assert len({a, b}) == 1


# --- sqllib.DBversion ----------------------------------------------------

def test_dbversion_ordering_int_tuple_self():
    v = sqllib.DBversion(5, 2)
    assert v > 4 and v >= 5 and v < 6
    assert v > (5, 1) and v < (5, 3) and v >= (5, 2) and v <= (5, 2)
    assert v < sqllib.DBversion(5, 3) and v > sqllib.DBversion(4, 9)
    assert sorted([sqllib.DBversion(2, 1), sqllib.DBversion(1, 5),
                   sqllib.DBversion(2, 0)])[0].major == 1


def test_dbversion_equality_and_bool():
    assert sqllib.DBversion(3, 0) == 3
    assert sqllib.DBversion(3, 1) != 3
    assert sqllib.DBversion(3, 1) == (3, 1)
    assert sqllib.DBversion(3, 1) == sqllib.DBversion(3, 1)
    assert not sqllib.DBversion(0, 0)
    assert sqllib.DBversion(0, 1)
    assert sqllib.DBversion(1, 0)


def test_dbversion_incompatible_type_raises():
    with pytest.raises(RuntimeError):
        sqllib.DBversion(1, 0) < 'x'


# --- trove.py stream classes --------------------------------------------
#
# The StreamSet based classes cannot be instantiated until the C stream
# bytes/str work lands, so the wiring is checked on the classes and the
# __cmp__ bodies are exercised through stand-in objects.

TROVE_CMP_CLASSES = [
    trove.TroveTuple, trove.SearchPathItem, trove.SingleTroveRedirect,
    trove.DigitalSignature, trove.VersionedDigitalSignatures,
    trove.SingleRpmObsolete, trove.MsiComponent,
    trove.TroveScriptCompatibility, trove.Property,
    trove.AbstractTroveChangeSet,
]


@pytest.mark.parametrize('cls', TROVE_CMP_CLASSES, ids=lambda c: c.__name__)
def test_trove_cmp_classes_get_rich_ordering(cls):
    assert issubclass(cls, CmpMixin)
    assert any('__cmp__' in vars(c) for c in cls.__mro__)
    for op in ('__lt__', '__le__', '__gt__', '__ge__'):
        assert getattr(cls, op) is getattr(CmpMixin, op)


class _FakeNamed(object):
    """Stands in for a StreamSet whose name()/freeze() are streams."""
    def __init__(self, name, frozen):
        self._n, self._f = name, frozen

    def name(self):
        return self._n

    def freeze(self):
        return self._f


@pytest.mark.parametrize('cls', [trove.TroveTuple, trove.Property,
                                 trove.SingleRpmObsolete,
                                 trove.SingleTroveRedirect])
def test_trove_name_freeze_cmp_semantics(cls):
    class Fake(_FakeNamed, CmpMixin):
        __cmp__ = cls.__cmp__
        __hash__ = object.__hash__

    a, b = Fake('a', b'2'), Fake('a', b'3')
    c, d = Fake('b', b'1'), Fake('a', b'2')
    assert a < b < c
    assert sorted([c, b, a]) == [a, b, c]
    assert a <= d and a >= d and not a < d
    assert cmp(a.name(), c.name()) == a.__cmp__(c)


def test_trove_signature_field_cmp_semantics():
    class Sig(CmpMixin):
        __cmp__ = trove.DigitalSignature.__cmp__

        def __init__(self, fp, sig, ts):
            self.fingerprint, self.signature, self.timestamp = fp, sig, ts

    assert (Sig('a', 'x', 1) < Sig('a', 'x', 2) < Sig('a', 'y', 0)
            < Sig('b', '', 0))
    assert Sig('a', 'x', 1) <= Sig('a', 'x', 1)


# --- pure python stream fallback ----------------------------------------

def _load_py_streams():
    path = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), 'conary', 'lib', 'ext', 'streams.py')
    spec = importlib.util.spec_from_file_location('_py_streams_fallback', path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_python_value_stream_fallback_orders():
    mod = _load_py_streams()

    class IntS(mod._ValueStream):
        _valueDefault = 0

        def set(self, value):
            self._value = value

    a, b, c = IntS(1), IntS(2), IntS(2)
    assert a < b and b >= c and b <= c and not b > c
    assert a == IntS(1) and a != b
    assert sorted([b, a]) == [a, b]
    assert hasattr(a, '__cmp__')
    assert hash(a) == hash(1)
