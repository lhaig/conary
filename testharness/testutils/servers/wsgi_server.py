"""Stdlib WSGI app server standing in for gunicorn/uwsgi.

The parent side (StdlibWsgiServer) spawns this module as a subprocess:
    python -m testutils.servers.wsgi_server --port N --app module.name
which serves module.application with wsgiref, forking per request.
"""
import argparse
import atexit
import importlib
import os
import signal
import socketserver
import subprocess
import sys
import threading
import time
from wsgiref import simple_server

from testutils.base_server import BaseServer
from testutils.sock_utils import tryConnect

_live = []


def _killAll():
    for srv in list(_live):
        srv.stop()


atexit.register(_killAll)


def _reservePort():
    import socket
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    port = s.getsockname()[1]
    s.close()
    return port


class StdlibWsgiServer(BaseServer):

    name = 'wsgi_server'
    startTimeout = 20.0

    def __init__(self, serverDir, workers=1, application=None, environ=None,
                 **kwargs):
        self.serverDir = os.path.abspath(serverDir)
        self.workers = workers
        self.application = application
        self.environ = dict(environ or {})
        self.port = _reservePort()
        self.errorLog = os.path.join(self.serverDir, 'error.log')
        self.process = None
        self._pid = os.getpid()

    def getProxyTo(self):
        return 'http://127.0.0.1:%d' % self.port

    def getUrl(self, ssl=False):
        return self.getProxyTo()

    def getHostPort(self):
        return ('127.0.0.1', self.port)

    def isStarted(self):
        return self.process is not None and self.process.poll() is None

    def _childEnv(self):
        env = dict(os.environ)
        env.update(self.environ)
        here = os.path.dirname(os.path.abspath(__file__))
        harness = os.path.dirname(os.path.dirname(here))
        root = os.path.dirname(harness)
        paths = [root, harness] + [p for p in sys.path if p]
        env['PYTHONPATH'] = os.pathsep.join(paths)
        return env

    def _tail(self):
        try:
            with open(self.errorLog, errors='replace') as f:
                return f.read()[-2000:]
        except OSError:
            return ''

    def start(self):
        if self.isStarted():
            return
        os.makedirs(self.serverDir, exist_ok=True)
        self._pid = os.getpid()
        log = open(self.errorLog, 'ab')
        try:
            self.process = subprocess.Popen(
                [sys.executable, '-m', 'testutils.servers.wsgi_server',
                 '--port', str(self.port), '--app', self.application],
                env=self._childEnv(), cwd=self.serverDir,
                stdin=subprocess.PIPE, stdout=log, stderr=log,
                start_new_session=True)
        finally:
            log.close()
        _live.append(self)
        deadline = time.monotonic() + self.startTimeout
        while True:
            if self.process.poll() is not None:
                code = self.process.returncode
                tail = self._tail()
                self.stop()
                raise RuntimeError(
                    '%s exited with status %s during startup:\n%s'
                    % (self.name, code, tail))
            try:
                tryConnect('127.0.0.1', self.port, count=1)
                return
            except ConnectionRefusedError:
                pass
            if time.monotonic() > deadline:
                tail = self._tail()
                self.stop()
                raise RuntimeError('%s did not start listening:\n%s'
                                   % (self.name, tail))
            time.sleep(0.05)

    def stop(self):
        proc, self.process = self.process, None
        if self in _live:
            _live.remove(self)
        if os.getpid() != self._pid:
            return      # forked child: the server belongs to the parent
        if proc is None:
            return
        try:
            for sig in (signal.SIGTERM, signal.SIGKILL):
                try:
                    os.killpg(proc.pid, sig)
                except ProcessLookupError:
                    break
                try:
                    proc.wait(timeout=5)
                    break
                except subprocess.TimeoutExpired:
                    continue
        finally:
            if proc.stdin:
                try:
                    proc.stdin.close()
                except OSError:
                    pass
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass

    def reset(self):
        """Truncate the error log; the process keeps running."""
        try:
            with open(self.errorLog, 'r+b') as f:
                f.truncate(0)
        except FileNotFoundError:
            pass


class _ForkingWSGIServer(socketserver.ForkingMixIn,
                         simple_server.WSGIServer):
    request_queue_size = 64


class _QuietHandler(simple_server.WSGIRequestHandler):

    def log_message(self, format, *args):
        pass


def _watchParent():
    try:
        sys.stdin.buffer.read()
    finally:
        os._exit(0)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, required=True)
    parser.add_argument('--app', required=True)
    args = parser.parse_args(argv)
    app = importlib.import_module(args.app).application
    httpd = simple_server.make_server(
        '127.0.0.1', args.port, app, server_class=_ForkingWSGIServer,
        handler_class=_QuietHandler)
    signal.signal(signal.SIGTERM, lambda *a: os._exit(0))
    threading.Thread(target=_watchParent, daemon=True).start()
    httpd.serve_forever()


if __name__ == '__main__':
    main()
