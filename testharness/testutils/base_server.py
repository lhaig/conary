"""Base class for test servers.

Subclasses (rephelp.HTTPProxy, HTTPServerController) define their own
__init__ without calling super, so this holds no state.
"""


class BaseServer:

    def start(self):
        raise NotImplementedError

    def stop(self):
        raise NotImplementedError

    def reset(self):
        pass

    def isStarted(self):
        return False

    def getHostPort(self):
        raise NotImplementedError
