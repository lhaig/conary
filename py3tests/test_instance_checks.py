"""Py2 types.InstanceType checks replaced for Py3 (no old-style classes)."""
import io
import sys

import pytest

from conary.build import explain
from conary.lib import formattrace


class Plain:
    """Plain doc"""
    def method(self):
        """method doc"""


class WithSafeStr:
    def __safe_str__(self):
        return '<safe>'


class ModuleProxy:
    # shouldSafeStr refuses types by name
    def __safe_str__(self):
        return '<never>'


@pytest.mark.parametrize('obj, expected', [
    (WithSafeStr(), True),
    (Plain(), False),
    (ModuleProxy(), False),
    (3, False),
])
def test_should_safe_str(obj, expected):
    assert formattrace.shouldSafeStr(obj) is expected


def test_format_locals_instance_and_unrepresentable():
    class Bad:
        def __safe_str__(self):
            raise RuntimeError('no safe str')

    def f():
        good = WithSafeStr()
        bad = Bad()
        frame = sys._getframe()
        out = io.StringIO()
        formattrace.formatLocals(frame, out)
        return out.getvalue(), good, bad

    text, _, _ = f()
    assert '<safe>' in text
    assert "unrepresentable object of type 'Bad'" in text
    assert 'error: RuntimeError' in text


@pytest.mark.parametrize('obj, expected', [
    (Plain(), Plain),
    (Plain, Plain),
    (Plain.method, Plain.method),
    (len, len),
    (explain, explain),
    ('a string', 'a string'),
])
def test_instance_to_class(obj, expected):
    assert explain._instanceToClass(obj) == expected
