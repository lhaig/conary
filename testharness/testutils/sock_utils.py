"""Socket helpers for tests."""
import socket
import time


def tryConnect(host, port, count=100, interval=0.1):
    """Wait until host:port accepts a TCP connection.

    Inferred from call sites: every caller ignores the result and calls this
    right after forking a server child that is still binding, so it retries
    on connection errors up to count attempts, interval seconds apart, then
    raises ConnectionRefusedError. The probe socket is always closed.
    """
    lastErr = None
    for attempt in range(count):
        try:
            sock = socket.create_connection((host, port), timeout=5)
        except OSError as err:
            lastErr = err
            if attempt + 1 < count:
                time.sleep(interval)
            continue
        sock.close()
        return
    raise ConnectionRefusedError(
        "could not connect to %s:%s after %d attempts: %s"
        % (host, port, count, lastErr))
