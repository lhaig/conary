from testutils.servers.wsgi_server import StdlibWsgiServer


class UwsgiServer(StdlibWsgiServer):
    name = 'uwsgi_server'
