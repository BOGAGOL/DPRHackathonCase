import os
from unittest.mock import MagicMock

import httpx
import pytest

from dprcrypto import BlindIndexer, CryptoError, KeyManager, OpenBaoClient, OpenBaoError, index_message


def test_cross_column_batch_preserves_messages_version_null_and_order():
    client = MagicMock()
    expected = [os.urandom(32) for _ in range(3)]
    client.hmac_batch.return_value = expected
    indexer = BlindIndexer(client, key_version=2)
    items = [('no_ktp', '00-01'), ('email', ' A@EXAMPLE.COM '), ('email', None), ('pengguna', ' Case ')]
    assert indexer.digests(items) == [expected[0], expected[1], None, expected[2]]
    client.hmac_batch.assert_called_once_with([index_message(c, v) for c, v in items if v is not None], key_version=2)
    client.reset_mock()
    assert indexer.digests([]) == []
    assert indexer.digests([('email', None)]) == [None]
    client.hmac_batch.assert_not_called()
    for values in (None, [('email', 'x')] * 101, [('email',)], ['email']):
        with pytest.raises(CryptoError):
            indexer.digests(values)
    for response in ([], [b'short'], [os.urandom(32)] * 2, None):
        client.hmac_batch.return_value = response
        with pytest.raises(OpenBaoError):
            indexer.digests([('email', 'synthetic@example.com')])


def test_explicit_persistent_pool_keeps_verified_tls(bao, monkeypatch):
    factory = httpx.Client
    seen = {}
    def capture(**kwargs):
        seen.update(kwargs)
        return factory(**kwargs)
    monkeypatch.setattr(httpx, 'Client', capture)
    with OpenBaoClient(transport=httpx.MockTransport(bao.handler), clock=lambda: bao.now) as client:
        for _ in range(3):
            client.hmac(b'synthetic')
        assert seen['verify'].check_hostname
        assert seen['limits'].max_connections == 8
        assert seen['limits'].max_keepalive_connections == 8
        assert seen['limits'].keepalive_expiry == 60


def test_cache_counters_ttl_and_disabled_mode_do_not_export_keys(bao):
    key = bao.client.wrap('pii-kek', os.urandom(32))
    manager = KeyManager(bao.client, cache_ttl=60, max_entries=2, clock=lambda: bao.now)
    manager.unwrap('pii-kek', key)
    manager.unwrap('pii-kek', key)
    assert manager.cache_stats()['hits'] == manager.cache_stats()['misses'] == 1
    assert manager.cache_stats()['hit_rate'] == .5
    assert key not in str(manager.cache_stats())
    bao.now += 61
    manager.unwrap('pii-kek', key)
    assert manager.cache_stats()['misses'] == 2
    manager.close()
    assert manager.cache_stats()['entries'] == 0
    with KeyManager(bao.client, cache_ttl=0, max_entries=0, clock=lambda: bao.now) as off:
        off.unwrap('pii-kek', key)
        off.unwrap('pii-kek', key)
        assert off.cache_stats()['hits'] == off.cache_stats()['entries'] == 0
        assert off.cache_stats()['remote_batches'] == 2
