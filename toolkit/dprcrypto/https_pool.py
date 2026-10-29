"""Bounded verified HTTPS pool; buffered HTTP/1.1 requests, no retries or secrets logs."""

import http.client
import json
import ssl
import threading
import time
from urllib.parse import urlsplit

import httpx


class VerifiedHTTPSPool(httpx.BaseTransport):
    """Keep verified connections alive with a small, bounded HTTP/1.1 session."""
    def __init__(self, address, context, *, timeout=5.0, maximum=8, idle_expiry=60.0,
                 clock=time.monotonic, factory=http.client.HTTPSConnection):
        origin = urlsplit(address)
        if (origin.scheme != 'https' or not origin.hostname or origin.username or origin.password
                or origin.path not in ('', '/') or origin.query or origin.fragment
                or context.verify_mode != ssl.CERT_REQUIRED or not context.check_hostname
                or context.minimum_version < ssl.TLSVersion.TLSv1_2
                or type(maximum) is not int or not 1 <= maximum <= 8
                or not 0 < timeout <= 300 or not 0 < idle_expiry <= 60):
            raise ValueError('Invalid verified HTTPS pool configuration')
        self._host, self._port = origin.hostname, origin.port or 443
        self._context, self._timeout = context, timeout
        self._maximum, self._expiry = maximum, idle_expiry
        self._clock, self._factory = clock, factory
        self._condition = threading.Condition()
        self._idle, self._live, self._closed = [], 0, False
        self._opened = self._reused = self._requests = self._failures = 0

    def _acquire(self):
        deadline = self._clock() + self._timeout
        with self._condition:
            while True:
                if self._closed:
                    raise httpx.TransportError('HTTPS pool closed')
                while self._idle:
                    connection, returned = self._idle.pop()
                    if self._clock() - returned >= self._expiry:
                        connection.close()
                        self._live -= 1
                    else:
                        self._reused += 1
                        return connection
                if self._live < self._maximum:
                    connection = self._factory(self._host, self._port, timeout=self._timeout,
                                               context=self._context)
                    self._live += 1
                    return connection
                remaining = deadline - self._clock()
                if remaining <= 0:
                    raise httpx.PoolTimeout('HTTPS pool acquisition timed out')
                self._condition.wait(remaining)

    def _release(self, connection, reusable):
        with self._condition:
            if reusable and not self._closed:
                self._idle.append((connection, self._clock()))
            else:
                connection.close()
                self._live -= 1
            self._condition.notify_all()

    def _exchange(self, method, path, body, headers):
        if not path.startswith('/v1/') or '..' in path or '\r' in path or '\n' in path:
            raise httpx.TransportError('Invalid Transit path')
        connection, reusable = self._acquire(), False
        try:
            if connection.sock is None:
                connection.connect()
                with self._condition:
                    self._opened += 1
            connection.request(method, path, body=body, headers=headers)
            response = connection.getresponse()
            body = response.read(4 * 1024 * 1024 + 1)
            if len(body) > 4 * 1024 * 1024:
                raise ValueError('Oversized Transit response')
            result = response.status, response.getheaders(), body
            reusable = not response.will_close
            response.close()
            with self._condition:
                self._requests += 1
            return result
        except (http.client.HTTPException, OSError, ValueError):
            with self._condition:
                self._failures += 1
            raise httpx.NetworkError('Verified HTTPS request failed') from None
        finally:
            self._release(connection, reusable)

    def request_bytes(self, method, path, payload, headers):
        """Workload JSON path without per-call HTTPX request/transport dispatch overhead."""
        body = None if payload is None else json.dumps(payload, separators=(',', ':'),
                                                       ensure_ascii=False, allow_nan=False).encode('utf-8')
        status, _, content = self._exchange(method, path, body,
            {**headers, 'Content-Type': 'application/json', 'Accept': 'application/json',
             'Accept-Encoding': 'identity'})
        return status, content

    def handle_request(self, request):
        if (request.url.scheme != 'https' or request.url.host != self._host
                or (request.url.port or 443) != self._port):
            raise httpx.TransportError('HTTPS origin mismatch')
        status, headers, content = self._exchange(request.method, request.url.raw_path.decode('ascii'),
                                                  request.read(), dict(request.headers))
        return httpx.Response(status, headers=headers, content=content, request=request,
                              extensions={'http_version': b'HTTP/1.1'})

    def stats(self):
        with self._condition:
            return {'opened_connections': self._opened, 'reused_connections': self._reused,
                    'requests': self._requests, 'failures': self._failures,
                    'live_connections': self._live, 'maximum_connections': self._maximum}

    def close(self):
        with self._condition:
            self._closed = True
            for connection, _ in self._idle:
                connection.close()
                self._live -= 1
            self._idle.clear()
            self._condition.notify_all()
