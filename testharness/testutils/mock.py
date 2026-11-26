"""Mock objects used by conary_test (a rebuild of the SAS testutils.mock).

Semantics were inferred from the conary_test call sites; only the API those
use is provided.  This module must not import testrunner (testrunner imports
it).
"""
import inspect
import types

_MISSING = object()


def _key(args, kw):
    return (tuple(args), tuple(sorted(kw.items())))


class _Manager:
    """The `_mock` attribute of a mock: call log, configured returns and the
    assertion API."""

    def __init__(self, owner):
        self._owner = owner
        self.calls = []         # [(args, sorted-kw-items)], mutable on purpose
        self._children = {}
        self._enabled = set()
        self._appended = []     # [(key, [values])]
        self._returns = []      # [(key, value)]
        self._default = _MISSING
        self._stable = None
        self._error = None

    # -- configuration --------------------------------------------------

    def set(self, **kw):
        for name, value in kw.items():
            setattr(self._owner, name, value)

    def setDefaultReturn(self, value):
        self._default = value

    def setReturn(self, value, *args, **kw):
        """Persistent return for exactly these arguments."""
        key = _key(args, kw)
        self._returns = [(k, v) for k, v in self._returns if k != key]
        self._returns.append((key, value))

    def appendReturn(self, value, *args, **kw):
        """Queue a return for exactly these arguments; one is consumed per
        matching call."""
        key = _key(args, kw)
        for k, queue in self._appended:
            if k == key:
                queue.append(value)
                return
        self._appended.append((key, [value]))

    def enableMethod(self, name):
        """MockInstance only: run the real method instead of mocking it."""
        self._enabled.add(name)

    def raiseErrorOnAccess(self, error):
        """Raise error (class or instance) when called or fetched from its
        parent."""
        self._error = error

    # -- assertions -----------------------------------------------------

    def assertCalled(self, *args, **kw):
        """Fail unless this exact call was made; the call is consumed, so a
        later assertNotCalled sees it as handled (updatecmdtest:1071/1082)."""
        call = _key(args, kw)
        if call not in self.calls:
            raise AssertionError(
                'expected call %r not found; recorded calls: %r'
                % (call, self.calls))
        self.calls.remove(call)

    def assertNotCalled(self):
        if self.calls:
            raise AssertionError('unexpected calls: %r' % (self.calls,))

    # -- internals ------------------------------------------------------

    def _raise(self):
        if self._error is not None:
            raise self._error

    def _child(self, name):
        child = self._children.get(name)
        if child is None:
            child = self._children[name] = MockObject()
        child._mock._raise()
        return child

    def _call(self, args, kw):
        self._raise()
        key = _key(args, kw)
        self.calls.append(key)
        for k, queue in self._appended:
            if k == key and queue:
                return queue.pop(0)
        for k, value in self._returns:
            if k == key:
                return value
        if self._default is not _MISSING:
            return self._default
        # One stable object whatever the arguments (changemailtest:40/49).
        if self._stable is None:
            self._stable = MockObject()
        return self._stable


def _is_dunder(name):
    return name.startswith('__') and name.endswith('__')


class MockObject:
    """Any attribute exists (a cached child MockObject) and the object is
    callable.  Deliberately no __len__/__bool__/__eq__/__get__: truthiness
    and equality stay default, and it is not a descriptor, so it can be set
    on a class without being bound."""

    def __init__(self, **kw):
        object.__setattr__(self, '_mock', _Manager(self))
        for name, value in kw.items():
            setattr(self, name, value)

    def __getattr__(self, name):
        if _is_dunder(name) or name == '_mock':
            raise AttributeError(name)
        return self._mock._child(name)

    def __call__(self, *args, **kw):
        return self._mock._call(args, kw)


class MockInstance:
    """Stand-in for an instance of cls without running cls.__init__.  Class
    functions, properties and other callables are mocked (cached
    MockObjects) unless enabled with _mock.enableMethod(name), which runs the
    real function bound to this object.  Plain class data is passed through;
    any other missing name auto-creates a child like MockObject."""

    def __init__(self, cls, **kw):
        object.__setattr__(self, '_cls', cls)
        object.__setattr__(self, '_mock', _Manager(self))
        for name, value in kw.items():
            setattr(self, name, value)

    @property
    def __class__(self):
        return self._cls

    def __getattr__(self, name):
        if _is_dunder(name) or name in ('_mock', '_cls'):
            raise AttributeError(name)
        mgr = self._mock
        static = inspect.getattr_static(self._cls, name, _MISSING)
        if static is not _MISSING:
            if name in mgr._enabled:
                if isinstance(static, property):
                    return static.fget(self)
                if isinstance(static, (staticmethod, classmethod)):
                    return getattr(self._cls, name)
                return types.MethodType(static, self)
            if not (callable(static) or isinstance(
                    static, (property, staticmethod, classmethod))):
                return static
        return mgr._child(name)

    def __call__(self, *args, **kw):
        return self._mock._call(args, kw)


class MockParams:
    """Holder for mockClass(mock_set=...): keyword values to set on the
    instance."""

    def __init__(self, *args, **kw):
        self.args = args
        self.kw = kw


def mockClass(cls, mock_enable=(), mock_set=None):
    """Return a real subclass of cls (so isinstance against it works) whose
    construction yields a MockInstance and never runs cls.__init__."""
    def __new__(klass, *args, **kw):
        inst = MockInstance(klass, **(mock_set.kw if mock_set else {}))
        for name in mock_enable:
            inst._mock.enableMethod(name)
        return inst
    return type(cls.__name__, (cls,), {'__new__': __new__})


# -- patching ---------------------------------------------------------------

def patch(obj, name, value):
    """Set obj.name = value and return an undo record for restore().  The raw
    __dict__ entry is saved so an inherited or missing attribute is deleted
    again, and a staticmethod/classmethod stays one.  Shared with
    testrunner.testhelp.TestCase.mock."""
    saved = getattr(obj, '__dict__', {}).get(name, _MISSING)
    if isinstance(saved, staticmethod) and \
            not isinstance(value, staticmethod):
        value = staticmethod(value)
    elif isinstance(saved, classmethod) and \
            not isinstance(value, classmethod):
        value = classmethod(value)
    setattr(obj, name, value)
    return (obj, name, saved)


def restore(record):
    obj, name, saved = record
    if saved is _MISSING:
        try:
            delattr(obj, name)
        except AttributeError:
            pass
    else:
        setattr(obj, name, saved)


# TestCase.mock keeps its own stack; if a test patches one attribute through
# both, cross-stack LIFO order is lost.  tearDown unwinds the TestCase stack
# first, then this one.
_undo = []


def mock(obj, attr, replacement=None):
    """Replace obj.attr (default: a new MockObject) until unmockAll();
    returns the installed value."""
    if replacement is None:
        replacement = MockObject()
    _undo.append(patch(obj, attr, replacement))
    return replacement


def mockMethod(method, returnValue=None):
    """Replace a bound method with a MockObject that records its args (no
    self) and returns returnValue."""
    m = mock(method.__self__, method.__name__)
    m._mock.setDefaultReturn(returnValue)
    return m


def unmockAll():
    while _undo:
        restore(_undo.pop())
