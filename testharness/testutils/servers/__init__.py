"""Web/cache server stand-ins: importable and constructible, skip on start."""
import os

from testrunner.testcase import SkipTestException

from testutils.base_server import BaseServer


class SkippedServer(BaseServer):
    """Accepts any constructor arguments; start() and address lookups skip."""

    name = 'server'

    def __init__(self, *args, **kwargs):
        self.kwargs = kwargs
        # ConaryServer.checkForTracebacks opens this on stop/reset.
        self.errorLog = os.devnull

    def _skip(self):
        raise SkipTestException(
            '%s: web server harness not rebuilt yet (server tests are out '
            'of scope until a later phase)' % self.name)

    def start(self):
        self._skip()

    def stop(self):
        pass

    def getProxyTo(self):
        # Called by ConaryServer.__init__ before start(); must not raise.
        return 'unix:/nonexistent'

    def getUrl(self, ssl=False):
        self._skip()

    def getHostPort(self):
        self._skip()
