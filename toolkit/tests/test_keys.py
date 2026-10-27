from concurrent.futures import ThreadPoolExecutor
import os

import pytest

from dprcrypto import CryptoError, KeyManager, OpenBaoError


def decrypt_calls(bao):
    return sum("/decrypt/" in path for path in bao.calls)


def test_new_domain_keys_per_record_and_safe_repr(bao):
    with KeyManager(bao.client, clock=lambda: bao.now) as manager:
        one, two = manager.create_record_keys(), manager.create_record_keys()
        keys = [one.pii.dek, one.finance.dek, two.pii.dek, two.finance.dek]
        assert all(len(key) == 32 for key in keys) and len(set(keys)) == 4
        assert manager.unwrap("pii-kek", one.pii.wrapped) == one.pii.dek
        assert manager.unwrap("finance-kek", one.finance.wrapped) == one.finance.dek
        assert all(repr(key) not in repr(one) + repr(one.pii) + repr(manager) for key in keys)
        with pytest.raises(OpenBaoError):
            manager.unwrap("finance-kek", one.pii.wrapped)
    with pytest.raises(OpenBaoError):
        manager.wrap("pii-kek", os.urandom(32))


def test_batch_dedup_chunking_order_and_cache_hits(bao):
    manager = KeyManager(bao.client, clock=lambda: bao.now)
    records = [manager.new_dek("pii-kek") for _ in range(205)]
    inputs = [item.wrapped for item in records] + [records[0].wrapped, records[-1].wrapped]
    result = manager.unwrap_many("pii-kek", inputs)
    assert result == [item.dek for item in records] + [records[0].dek, records[-1].dek]
    assert decrypt_calls(bao) == 3
    assert manager.unwrap_many("pii-kek", inputs) == result
    assert decrypt_calls(bao) == 3
    assert manager.unwrap_many("pii-kek", []) == []
    manager.clear()
    assert not manager._cache


def test_ttl_lru_bound_and_best_effort_wipe(bao):
    manager = KeyManager(bao.client, cache_ttl=15, max_entries=2, clock=lambda: bao.now)
    first, second, third = [manager.new_dek("pii-kek") for _ in range(3)]
    manager.unwrap_many("pii-kek", [first.wrapped, second.wrapped])
    evicted = manager._cache[("pii-kek", second.wrapped)][0]
    manager.unwrap("pii-kek", first.wrapped)  # first becomes most recently used
    manager.unwrap("pii-kek", third.wrapped)
    assert len(manager._cache) == 2 and not any(evicted)
    assert ("pii-kek", second.wrapped) not in manager._cache
    previous = manager._cache[("pii-kek", first.wrapped)][0]
    bao.now += 16
    manager.unwrap("pii-kek", first.wrapped)
    assert not any(previous) and decrypt_calls(bao) == 3
    active = manager._cache[("pii-kek", first.wrapped)][0]
    manager.close()
    assert not any(active) and not manager._cache


def test_token_scope_change_expiry_and_no_cache_bypass(bao, monkeypatch):
    manager = KeyManager(bao.client, cache_ttl=60, clock=lambda: bao.now)
    key = manager.new_dek("pii-kek")
    manager.unwrap("pii-kek", key.wrapped)
    previous = next(iter(manager._cache.values()))[0]
    monkeypatch.setenv("OPENBAO_TOKEN", bao.tokens["svc-verify"])
    with pytest.raises(OpenBaoError):
        manager.unwrap("pii-kek", key.wrapped)
    assert not manager._cache and not any(previous)
    monkeypatch.setenv("OPENBAO_TOKEN", bao.tokens["svc-app"])
    bao.now = 390
    manager.unwrap("pii-kek", key.wrapped)
    assert next(iter(manager._cache.values()))[1] == 400
    bao.now = 400
    with pytest.raises(OpenBaoError):
        manager.unwrap("pii-kek", key.wrapped)
    assert not manager._cache


def test_partial_failure_across_chunks_never_populates_cache(bao, monkeypatch):
    manager = KeyManager(bao.client, batch_size=1, clock=lambda: bao.now)
    wrapped = [manager.new_dek("pii-kek").wrapped for _ in range(2)]
    original = bao.client.unwrap_batch
    count = 0
    def failing_second(kek, chunk):
        nonlocal count
        count += 1
        if count == 2:
            raise OpenBaoError(503)
        return original(kek, chunk)
    monkeypatch.setattr(bao.client, "unwrap_batch", failing_second)
    with pytest.raises(OpenBaoError):
        manager.unwrap_many("pii-kek", wrapped)
    assert not manager._cache and count == 2


def test_hits_do_not_extend_lease_and_revocation_takes_effect_after_lease(bao):
    manager = KeyManager(bao.client, cache_ttl=15, clock=lambda: bao.now)
    key = manager.new_dek("pii-kek")
    manager.unwrap("pii-kek", key.wrapped)
    bao.revoked.add(bao.tokens["svc-app"])
    bao.now = 110
    assert manager.unwrap("pii-kek", key.wrapped) == key.dek
    assert next(iter(manager._cache.values()))[1] == 115
    bao.now = 116
    with pytest.raises(OpenBaoError):
        manager.unwrap("pii-kek", key.wrapped)
    assert not manager._cache


def test_observed_auth_failure_in_another_operation_invalidates_cached_scope(bao):
    manager = KeyManager(bao.client, clock=lambda: bao.now)
    key = manager.new_dek("pii-kek")
    manager.unwrap("pii-kek", key.wrapped)
    bao.revoked.add(bao.tokens["svc-app"])
    with pytest.raises(OpenBaoError):
        bao.client.hmac(b"synthetic")
    with pytest.raises(OpenBaoError):
        manager.unwrap("pii-kek", key.wrapped)
    assert not manager._cache


@pytest.mark.parametrize("setting", [{"cache_ttl": 0}, {"max_entries": 0}])
def test_can_disable_cache(bao, setting):
    manager = KeyManager(bao.client, clock=lambda: bao.now, **setting)
    key = manager.new_dek("pii-kek")
    manager.unwrap("pii-kek", key.wrapped)
    manager.unwrap("pii-kek", key.wrapped)
    assert not manager._cache and decrypt_calls(bao) == 2


def test_thread_safety_for_shared_page_cache(bao):
    with KeyManager(bao.client, clock=lambda: bao.now) as manager:
        key = manager.new_dek("pii-kek")
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda _: manager.unwrap("pii-kek", key.wrapped), range(32)))
        assert all(value == key.dek for value in results)
        assert decrypt_calls(bao) == 1


@pytest.mark.parametrize("settings", [{"cache_ttl": -1}, {"cache_ttl": 61}, {"cache_ttl": float("nan")},
    {"max_entries": -1}, {"max_entries": 4097}, {"max_entries": True}, {"batch_size": 0}, {"batch_size": 101}])
def test_reject_unbounded_cache_settings(bao, settings):
    with pytest.raises(CryptoError):
        KeyManager(bao.client, **settings)
