"""Pass-through stand-in for the nginx reverse proxy.

There is no nginx in the harness: the front end is the app server itself.
"""
from urllib.parse import urlparse

from testrunner.testcase import SkipTestException

from testutils.base_server import BaseServer


class NginxServer(BaseServer):

    name = 'nginx_server'

    def __init__(self, serverDir, proxyTo, sslCertAndKey=None, **kwargs):
        # Raised here, before ConaryServer starts the app server, so a skip
        # leaves no subprocess behind.
        if sslCertAndKey:
            raise SkipTestException(
                '%s: SSL/TLS web server harness not available (the stdlib '
                'harness has no nginx)' % self.name)
        self.serverDir = serverDir
        self.proxyTo = proxyTo

    def start(self):
        pass

    def stop(self):
        pass

    def reset(self):
        pass

    def isStarted(self):
        return True

    def getUrl(self, ssl=False):
        return self.proxyTo

    def getHostPort(self):
        parsed = urlparse(self.proxyTo)
        return (parsed.hostname, parsed.port)
