from testutils.servers import SkippedServer


class GunicornServer(SkippedServer):
    name = 'gunicorn_server'
