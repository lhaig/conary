from testutils.servers.wsgi_server import StdlibWsgiServer


class GunicornServer(StdlibWsgiServer):
    name = 'gunicorn_server'
