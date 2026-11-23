#
# Copyright (c) SAS Institute Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#


""" Defines an on-demand importer that only actually loads modules when their
    attributes are accessed.  NOTE: if the ondemand module is viewed using
    introspection, like dir(), isinstance, etc, it will appear as a
    ModuleProxy, not a module, and will not have the correct attributes.
    Barring introspection, however, the module will behave as normal.
"""
import importlib.machinery
import importlib.util
import sys
import types

def _loadFromSpec(name, spec):
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    try:
        spec.loader.exec_module(mod)
    except BaseException:
        sys.modules.pop(name, None)
        raise
    return mod

def makeImportedModule(name, spec, scope):
    """ Returns a ModuleProxy that has access to a closure w/
        information about the module to load, but is otherwise
        empty.  On an attempted access of any member of the module,
        the module is loaded.
    """
    pathname = spec.origin

    def _loadModule():
        """ Load the given module, and insert it into the parent
            scope, and also the original importing scope.
        """

        mod = sys.modules.get(name, None)
        if mod is None or not isinstance(mod, types.ModuleType):
            mod = _loadFromSpec(name, spec)

        scope[name] = mod

        frame = sys._getframe(2)
        global_scope = frame.f_globals
        local_scope = frame.f_locals

        # check to see if this module exists for any part of the name
        # we are importing, e.g. if you are importing foo.bar.baz,
        # look for foo.bar.baz, bar.baz, and baz.
        moduleParts = name.split('.')
        names = [ '.'.join(moduleParts[-x:]) for x in range(len(moduleParts)) ]
        for modulePart in names:
            if modulePart in local_scope:
                if (hasattr(local_scope[modulePart], '__class__')
                    and local_scope[modulePart].__class__.__name__ == 'ModuleProxy'):
                    # FIXME: this makes me cringe, but I haven't figured out a
                    # better way to ensure that the module proxy we're
                    # looking at is actually a proxy for this module
                    if pathname in repr(local_scope[modulePart]):
                        local_scope[modulePart] = mod
            if modulePart in global_scope:
                if (hasattr(global_scope[modulePart], '__class__')
                    and global_scope[modulePart].__class__.__name__ == 'ModuleProxy'):
                    if pathname in repr(global_scope[modulePart]):
                        global_scope[modulePart] = mod

        return mod

    class ModuleProxy(object):
        __slots__ = []
        # we don't add any docs for the module in case the
        # user tries accessing '__doc__'
        def __hasattr__(self, key):
            mod = _loadModule()
            return hasattr(mod, key)

        def __getattr__(self, key):
            mod = _loadModule()
            try:
                return getattr(mod, key)
            except AttributeError:
                # A nicer error to compensate for the extra stack frame the
                # lazy importer adds.
                raise AttributeError("Module %r has no attribute %r" % (name,
                    key))

        def __setattr__(self, key, value):
            mod = _loadModule()
            return setattr(mod, key, value)

        def __repr__(self):
            return "<moduleProxy '%s' from '%s'>" % (name, pathname)

    return ModuleProxy()

class OnDemandLoader(object):
    """ The loader takes a name and info about the module to load and
        "loads" it - in this case returning loading a proxy that
        will only load the class when an attribute is accessed.
    """
    def __init__(self, name, spec, scope):
        self.name = name
        self.spec = spec
        self.pathname = spec.origin
        self.scope = scope

    def create_module(self, spec):
        fullname = spec.name
        if fullname in __builtins__:
            mod = _loadFromSpec(self.name, self.spec)
        else:
            mod = makeImportedModule(self.name, self.spec, self.scope)
        sys.modules[fullname] = mod
        return mod

    def exec_module(self, module):
        # create_module already did the work (or returned a lazy proxy)
        pass

class OnDemandImporter(object):
    """ The on-demand importer imports a module proxy that
        inserts the desired module into the calling scope only when
        an attribute from the module is actually used.
    """

    def find_spec(self, fullname, path=None, target=None):
        origName = fullname
        if not path:
            mod = sys.modules.get(fullname, False)
            if mod is None or mod and isinstance(mod, types.ModuleType):
                return None

        frame = sys._getframe(1)
        global_scope = frame.f_globals
        # this is the scope in which import <fullname> was called

        if '.' in fullname:
            head, fullname = fullname.rsplit('.', 1)

            # this import protocol works such that if I am going to be
            # able to import fullname, then everything in front of the
            # last . in fullname must already be loaded into sys.modules.
            mod = sys.modules.get(head,None)
            if mod is None:
                return None

            if hasattr(mod, '__path__'):
                path = mod.__path__

        spec = importlib.machinery.PathFinder.find_spec(fullname, path)
        if spec is None or spec.origin is None or spec.loader is None:
            # don't raise an import error.  That will stop
            # the automated search mechanism from working.
            return None
        return importlib.util.spec_from_loader(
            origName, OnDemandLoader(origName, spec, global_scope),
            origin=spec.origin)

def install():
    if hasattr(sys, 'pypy_version_info'):
        # The lazy importer doesn't work on PyPy right now, but it could be
        # made to.
        return
    sys.meta_path.append(OnDemandImporter())
