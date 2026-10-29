import http.client
import ssl
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import httpx
import pytest

from dprcrypto.https_pool import VerifiedHTTPSPool


class Connection:
    def __init__(self, *args, **kwargs):
        self.sock = None
        self.requests = []
        self.failure = self.will_close = False
        self.body = b'{"data":{"ok":true}}'
    def connect(self): self.sock = object()
    def close(self): self.sock = None
    def request(self, *args, **kwargs):
        self.requests.append((args, kwargs))
        if self.failure: raise http.client.RemoteDisconnected('PRIVATE_RESPONSE_DETAIL')
    def getresponse(self):
        return SimpleNamespace(status=200, will_close=self.will_close,
            read=lambda n: self.body, close=lambda: None,
            getheaders=lambda: [('content-type', 'application/json')])


def pool(clock=lambda: 0, **kwargs):
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    return VerifiedHTTPSPool('https://bao.example:8200', context, factory=Connection,
                             clock=clock, **kwargs)


def request():
    return httpx.Request('POST', 'https://bao.example:8200/v1/transit/hmac/search-hmac/sha2-256',
                         json={'input': 'synthetic'}, headers={'X-Vault-Token': 'synthetic-test-token'})


def test_reuse_idle_expiry_close_and_same_https_origin():
    now = [0]
    p = pool(clock=lambda: now[0])
    assert p.handle_request(request()).json()['data']['ok']
    c = p._idle[0][0]
    assert len(c.requests) == 1
    assert p.handle_request(request()).status_code == 200
    assert p.stats()['opened_connections'] == 1
    assert p.stats()['reused_connections'] == 1
    now[0] = 61
    p.handle_request(request())
    assert c.sock is None and p.stats()['opened_connections'] == 2
    for url in ('http://bao.example:8200', 'https://other.example:8200', 'https://bao.example:8443'):
        with pytest.raises(httpx.TransportError): p.handle_request(httpx.Request('POST', url))
    p.close(); p.close()
    assert p.stats()['live_connections'] == 0
    with pytest.raises(httpx.TransportError): p.handle_request(request())


def test_no_retry_no_sensitive_exception_and_bounded_response():
    p = pool()
    p.handle_request(request())
    c = p._idle[0][0]
    c.failure = True
    with pytest.raises(httpx.NetworkError) as caught:
        p.handle_request(request())
    assert 'PRIVATE_RESPONSE_DETAIL' not in str(caught.value)
    assert len(c.requests) == 2 and c.sock is None
    assert p.stats()['failures'] == 1
    p.handle_request(request())
    assert p.stats()['opened_connections'] == 2
    c = p._idle[0][0]
    c.body = b'x' * (4 * 1024 * 1024 + 1)
    with pytest.raises(httpx.NetworkError): p.handle_request(request())
    assert p.stats()['live_connections'] == 0
    p.handle_request(request())
    p._idle[0][0].will_close = True
    p.handle_request(request())
    assert p.stats()['live_connections'] == 0
    p.close()


def test_tls_pool_bounds_and_parallel_reuse():
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    for changes in ({'maximum': 0}, {'maximum': 9}, {'idle_expiry': 61}, {'timeout': 0}):
        with pytest.raises(ValueError):
            VerifiedHTTPSPool('https://bao.example:8200', context, **changes)
    context.check_hostname = False
    with pytest.raises(ValueError): VerifiedHTTPSPool('https://bao.example:8200', context)
    p = pool(maximum=2)
    with ThreadPoolExecutor(max_workers=8) as executor:
        assert all(r.status_code == 200 for r in executor.map(lambda _: p.handle_request(request()), range(100)))
    assert p.stats()['live_connections'] <= 2
    p.close()


def test_pool_timeout_and_active_close():
    p = pool(clock=__import__('time').monotonic, maximum=1, timeout=.01)
    c = p._acquire()
    with pytest.raises(httpx.PoolTimeout): p._acquire()
    p.close()
    p._release(c, True)
    assert p.stats()['live_connections'] == 0


def test_direct_json_session_and_restricted_path():
    import json
    p = pool()
    status, content = p.request_bytes('POST', '/v1/transit/hmac/search-hmac/sha2-256',
                                     {'input': 'synthetic'}, {'X-Vault-Token': 'synthetic'})
    assert status == 200 and json.loads(content)['data']['ok']
    connection = p._idle[0][0]
    args, kwargs = connection.requests[-1]
    assert json.loads(kwargs['body']) == {'input': 'synthetic'}
    assert kwargs['headers']['Accept-Encoding'] == 'identity'
    p.request_bytes('GET', '/v1/auth/token/lookup-self', None, {})
    assert connection.requests[-1][1]['body'] is None
    for path in ('https://other.example/', '//other.example/', '/v1/../sys/seal', '/v1/x\r\nOther:x'):
        with pytest.raises(httpx.TransportError): p.request_bytes('POST', path, {}, {})
    p.close()
