"""Recipe.__init__ wraps methods defined by recipe subclasses so calls can
be tracked; inherited Recipe methods and classmethods are left alone."""
import types

from conary.build import recipe


class _Cfg:
    defaultMacros = []


class Base(recipe.Recipe):
    name = 'base'

    def baseMethod(self):
        return 'base'

    def overridden(self):
        return 'base-overridden'


class Child(Base):
    def childMethod(self):
        return 'child'

    def overridden(self):
        return 'child-overridden'

    @classmethod
    def clsMethod(cls):
        return 'cls'


def test_subclass_methods_wrapped_and_recorded():
    r = Child(_Cfg())
    assert ('Child', 'childMethod') in r.unusedMethods
    assert ('Child', 'overridden') in r.unusedMethods
    assert ('Base', 'baseMethod') in r.unusedMethods
    # the wrapper still calls through
    assert r.childMethod() == 'child'
    assert r.overridden() == 'child-overridden'
    assert r.baseMethod() == 'base'


def test_inherited_recipe_methods_not_wrapped():
    r = Child(_Cfg())
    assert not any(c == 'Recipe' for c, _ in r.unusedMethods)
    # fetchLocalSources is a plain Recipe method: stays a bound method
    assert isinstance(r.fetchLocalSources, types.MethodType)


def test_classmethod_not_wrapped():
    r = Child(_Cfg())
    assert ('Child', 'clsMethod') not in r.unusedMethods
    assert r.clsMethod() == 'cls'


def test_methods_called_recorded():
    r = Child(_Cfg())
    r._recordMethodCalls = True
    r.childMethod()
    assert r.methodsCalled == [(1, 'Child', 'childMethod')]
    assert ('Child', 'childMethod') not in r.unusedMethods
